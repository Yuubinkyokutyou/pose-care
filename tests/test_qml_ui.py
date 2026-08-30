from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")

from PySide6.QtCore import QObject, Property, QSize, QUrl, Signal, Slot
from PySide6.QtGui import QImage
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent
from PySide6.QtWidgets import QApplication

from pose_care.config import SettingsStore
from pose_care.history import PostureHistory
from pose_care.models import AppSettings, PoseFeature
from pose_care.notifications import WindowsNotifier
from pose_care.startup import StartupRegistration, StartupRegistrationError
from pose_care.ui.controller import PoseCareController
from pose_care.ui.image_provider import CameraImageProvider
from pose_care.ui.style import make_app_icon


class FakeUpdateController(QObject):
    updateChanged = Signal()

    def __init__(self):
        super().__init__()
        self._app_version = "0.2.0"
        self._latest_version = ""
        self._update_state = "idle"
        self._update_status = ""
        self._update_progress = 0.0
        self.check_calls = 0
        self.install_calls = 0

    appVersion = Property(
        str, lambda self: self._app_version, notify=updateChanged
    )
    latestVersion = Property(
        str, lambda self: self._latest_version, notify=updateChanged
    )
    updateState = Property(
        str, lambda self: self._update_state, notify=updateChanged
    )
    updateStatus = Property(
        str, lambda self: self._update_status, notify=updateChanged
    )
    updateProgress = Property(
        float, lambda self: self._update_progress, notify=updateChanged
    )

    def set_update(
        self,
        state: str,
        *,
        latest_version: str = "",
        status: str = "",
        progress: float = 0.0,
    ) -> None:
        self._update_state = state
        self._latest_version = latest_version
        self._update_status = status
        self._update_progress = progress
        self.updateChanged.emit()

    @Slot()
    def checkForUpdates(self) -> None:
        self.check_calls += 1

    @Slot()
    def installUpdate(self) -> None:
        self.install_calls += 1


def _application() -> QApplication:
    return QApplication.instance() or QApplication([])


class FakeStartupRegistration(StartupRegistration):
    def __init__(self, enabled: bool = False):
        self.enabled = enabled

    def is_enabled(self) -> bool:
        return self.enabled

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled


class FailingStartupRegistration(FakeStartupRegistration):
    def set_enabled(self, enabled: bool) -> None:
        raise StartupRegistrationError("スタートアップに登録できませんでした")


def test_camera_image_provider_returns_latest_frame():
    _application()
    provider = CameraImageProvider()
    frame = QImage(16, 9, QImage.Format.Format_RGB888)
    frame.fill(0xFF42D6BE)
    provider.set_image(frame)

    size = QSize()
    loaded = provider.requestImage("frame/1", size, QSize(8, 8))

    assert size == QSize(16, 9)
    assert loaded.size() == QSize(8, 4)

    provider.clear()
    assert provider.requestImage("frame/2", QSize(), QSize()).isNull()


def test_camera_stops_only_after_no_person_and_no_input_then_resumes(
    tmp_path, monkeypatch
):
    _application()
    provider = CameraImageProvider()
    user_idle_seconds = [0.5]
    controller = PoseCareController(
        SettingsStore(tmp_path / "settings.json"),
        AppSettings(),
        make_app_icon(),
        provider,
        history=PostureHistory(tmp_path / "history.sqlite3"),
        notifier=WindowsNotifier(toaster=object(), toast_factory=lambda fields: fields),
        idle_seconds_provider=lambda: user_idle_seconds[0],
    )
    controller._idle_camera_timeout_seconds = 300.0
    controller.camera_worker = object()
    stopped = []
    started = []

    class FakeWorker:
        def __init__(self):
            self.stop_requested = False
            self.deleted = False

        def request_stop(self):
            self.stop_requested = True

        def deleteLater(self):
            self.deleted = True

    def stop_camera(*, wait=False):
        stopped.append(True)
        controller.camera_worker = None

    def start_camera():
        started.append(True)
        controller.camera_worker = FakeWorker()

    monkeypatch.setattr(controller, "_stop_camera", stop_camera)
    monkeypatch.setattr(controller, "_start_camera", start_camera)
    monkeypatch.setattr("pose_care.ui.controller.time.monotonic", lambda: 401.0)

    # Fresh Windows input prevents release even when nobody has been detected.
    controller._last_person_seen_at = 100.0
    controller._check_camera_activity()
    assert not stopped
    assert not controller._camera_suspended_for_idle

    # Recent pose detection also prevents release when Windows has been idle.
    user_idle_seconds[0] = 301.0
    controller._last_person_seen_at = 400.0
    controller._check_camera_activity()
    assert not stopped
    assert not controller._camera_suspended_for_idle

    controller._last_person_seen_at = 100.0
    controller._check_camera_activity()
    assert stopped == [True]
    assert controller._camera_suspended_for_idle
    assert controller.stateKind == "idle"
    assert controller.cameraStatus == "無人・無操作のためカメラを停止しました"
    controller._on_pose(None, [])
    assert controller.stateKind == "idle"

    # Any fresh keyboard/mouse input resumes the camera without changing the
    # user's explicit monitoring setting. Give Windows Hello time to release
    # the camera before trying to reconnect.
    user_idle_seconds[0] = 0.5
    controller._check_camera_activity()
    assert started == []
    assert controller._camera_retry_timer.isActive()
    controller._retry_camera_after_idle()
    assert started == [True]
    assert not controller._camera_suspended_for_idle
    assert controller.stateKind == "starting"
    assert controller.monitoring

    # A transient failure while Windows Hello still owns the camera should
    # remain in the starting state and retry instead of showing CAMERA OFFLINE.
    controller._on_camera_error("camera still in use", True)
    assert controller.cameraErrorText == ""
    assert controller._camera_retry_timer.isActive()
    assert controller.stateKind == "starting"

    previous_worker = controller.camera_worker
    controller._retry_camera_after_idle()
    assert started == [True]
    assert previous_worker.stop_requested
    controller._on_camera_worker_finished(previous_worker)
    assert started == [True, True]
    assert previous_worker.deleted
    controller._on_camera_status("カメラ準備完了（共有モード）")
    assert not controller._camera_recovery_active
    assert not controller._camera_retry_timer.isActive()
    controller.shutdown()


def test_windows_lock_releases_camera_until_session_unlock(tmp_path, monkeypatch):
    _application()
    provider = CameraImageProvider()
    controller = PoseCareController(
        SettingsStore(tmp_path / "settings.json"),
        AppSettings(),
        make_app_icon(),
        provider,
        history=PostureHistory(tmp_path / "history.sqlite3"),
        notifier=WindowsNotifier(toaster=object(), toast_factory=lambda fields: fields),
        idle_seconds_provider=lambda: 0.0,
    )
    controller.camera_worker = object()
    stopped = []
    started = []

    def stop_camera(*, wait=False):
        stopped.append(wait)
        controller.camera_worker = None

    def start_camera():
        started.append(True)
        controller.camera_worker = object()

    monkeypatch.setattr(controller, "_stop_camera", stop_camera)
    monkeypatch.setattr(controller, "_start_camera", start_camera)

    controller.toggleMonitoring(False)
    controller.set_session_locked(True)

    assert stopped == [False]
    assert controller._session_locked
    assert controller.stateKind == "locked"
    assert controller.cameraStatus == "Windowsがロックされたためカメラを停止しました"
    assert not controller._camera_retry_timer.isActive()

    # Input on the lock screen must not reclaim the camera before Windows Hello.
    controller._check_camera_activity()
    controller._retry_camera_after_idle()
    assert started == []

    controller.set_session_locked(False)

    assert not controller._session_locked
    assert controller.stateKind == "starting"
    assert controller._camera_retry_timer.isActive()
    assert not controller.monitoring

    controller._retry_camera_after_idle()
    assert started == [True]
    controller._on_camera_status("カメラ準備完了（共有モード）")
    assert controller.stateKind == "paused"
    controller.shutdown()


def test_camera_does_not_start_when_app_begins_while_session_locked(tmp_path):
    _application()
    controller = PoseCareController(
        SettingsStore(tmp_path / "settings.json"),
        AppSettings(),
        make_app_icon(),
        CameraImageProvider(),
        history=PostureHistory(tmp_path / "history.sqlite3"),
        notifier=WindowsNotifier(toaster=object(), toast_factory=lambda fields: fields),
    )

    controller.set_session_locked(True)
    controller.start()

    assert controller.camera_worker is None
    assert controller.stateKind == "locked"
    controller.shutdown()


def test_camera_resume_reports_permanent_error_without_retry(tmp_path):
    _application()
    controller = PoseCareController(
        SettingsStore(tmp_path / "settings.json"),
        AppSettings(),
        make_app_icon(),
        CameraImageProvider(),
        history=PostureHistory(tmp_path / "history.sqlite3"),
        notifier=WindowsNotifier(toaster=object(), toast_factory=lambda fields: fields),
    )
    controller._camera_recovery_active = True
    controller._camera_recovery_attempts = 1

    controller._on_camera_error("model initialization failed", False)

    assert not controller._camera_recovery_active
    assert not controller._camera_retry_timer.isActive()
    assert controller.cameraErrorText.startswith("カメラを利用できません")
    controller.shutdown()


def test_camera_initial_transient_error_starts_recovery(tmp_path):
    _application()
    controller = PoseCareController(
        SettingsStore(tmp_path / "settings.json"),
        AppSettings(),
        make_app_icon(),
        CameraImageProvider(),
        history=PostureHistory(tmp_path / "history.sqlite3"),
        notifier=WindowsNotifier(toaster=object(), toast_factory=lambda fields: fields),
    )

    controller._on_camera_error("スリープ復帰後にカメラ接続が失われました", True)

    assert controller._camera_recovery_active
    assert controller._camera_retry_timer.isActive()
    assert controller._camera_retry_timer.interval() == 3_000
    assert controller.cameraErrorText == ""
    assert controller.stateKind == "starting"
    controller.shutdown()


def test_stale_camera_worker_error_does_not_restart_current_worker(tmp_path):
    _application()
    controller = PoseCareController(
        SettingsStore(tmp_path / "settings.json"),
        AppSettings(),
        make_app_icon(),
        CameraImageProvider(),
        history=PostureHistory(tmp_path / "history.sqlite3"),
        notifier=WindowsNotifier(toaster=object(), toast_factory=lambda fields: fields),
    )
    current_worker = object()
    stale_worker = object()
    controller.camera_worker = current_worker

    controller._on_camera_worker_error(stale_worker, "stale failure", True)

    assert not controller._camera_recovery_active
    assert not controller._camera_retry_timer.isActive()

    controller._camera_start_pending = True
    controller._on_camera_worker_error(current_worker, "replacement failure", True)

    assert not controller._camera_recovery_active
    assert not controller._camera_retry_timer.isActive()
    controller.camera_worker = None
    controller.shutdown()


def test_camera_shutdown_waits_before_deleting_slow_worker(tmp_path):
    _application()
    controller = PoseCareController(
        SettingsStore(tmp_path / "settings.json"),
        AppSettings(),
        make_app_icon(),
        CameraImageProvider(),
        history=PostureHistory(tmp_path / "history.sqlite3"),
        notifier=WindowsNotifier(toaster=object(), toast_factory=lambda fields: fields),
    )

    class SlowWorker:
        def __init__(self):
            self.stop_requested = False
            self.deleted = False
            self.wait_calls = []

        def request_stop(self):
            self.stop_requested = True

        def wait(self, timeout=None):
            self.wait_calls.append(timeout)
            return timeout is None

        def deleteLater(self):
            self.deleted = True

    worker = SlowWorker()
    controller.camera_worker = worker

    controller._stop_camera(wait=True)

    assert worker.stop_requested
    assert worker.wait_calls == [25_000, None]
    assert worker.deleted
    assert controller.camera_worker is None
    controller.shutdown()


def test_camera_resume_keeps_low_priority_retry_after_fast_attempts(
    tmp_path, monkeypatch
):
    _application()
    controller = PoseCareController(
        SettingsStore(tmp_path / "settings.json"),
        AppSettings(),
        make_app_icon(),
        CameraImageProvider(),
        history=PostureHistory(tmp_path / "history.sqlite3"),
        notifier=WindowsNotifier(toaster=object(), toast_factory=lambda fields: fields),
    )
    controller._camera_recovery_active = True
    controller._camera_recovery_attempts = 5

    controller._on_camera_error("camera still in use", True)

    assert controller._camera_recovery_active
    assert controller._camera_retry_timer.isActive()
    assert controller._camera_retry_timer.interval() == 60_000
    assert "1分後に再試行" in controller.cameraErrorText

    started = []
    monkeypatch.setattr(controller, "_start_camera", lambda: started.append(True))
    controller._retry_camera_after_idle()
    assert started == [True]
    controller._on_camera_status("カメラ準備完了（共有モード）")
    assert not controller._camera_recovery_active
    controller.shutdown()


def test_update_card_reflects_release_state():
    application = _application()
    controller = FakeUpdateController()
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("fakeUpdateController", controller)
    qml_dir = Path(__file__).parents[1] / "pose_care" / "ui" / "qml"
    component = QQmlComponent(engine)
    component.setData(
        b"""
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    width: 800
    height: 260

    QtObject {
        id: testTheme
        property color surface: "#101D2C"
        property color surfaceHigh: "#17283A"
        property color surfaceInset: "#0B1725"
        property color surfaceHover: "#1B3045"
        property color surfacePressed: "#0D1A29"
        property color line: "#263A4D"
        property color lineSoft: "#1C3042"
        property color text: "#EDF5F6"
        property color muted: "#91A6B8"
        property color signal: "#42D6BE"
        property color signalHover: "#68E2CF"
        property color signalPressed: "#2CBCA6"
        property color blue: "#62B8F5"
        property color danger: "#FF737A"
        property color inkOnAccent: "#05241F"
        property string displayFont: "Yu Gothic UI"
        property string bodyFont: "Yu Gothic UI"
        property string dataFont: "Cascadia Mono"
    }

    UpdateCard {
        anchors.fill: parent
        theme: testTheme
        updateController: fakeUpdateController
    }
}
""",
        QUrl.fromLocalFile(str(qml_dir / "UpdateCardHarness.qml")),
    )
    root = component.create()
    assert root is not None, "\n".join(error.toString() for error in component.errors())

    button = root.findChild(QObject, "updateActionButton")
    current_version = root.findChild(QObject, "currentVersionValue")
    latest_version = root.findChild(QObject, "latestVersionValue")
    status = root.findChild(QObject, "updateStatusText")
    progress = root.findChild(QObject, "updateProgressBar")

    assert button.property("text") == "更新を確認"
    assert button.property("enabled") is True
    assert current_version.property("text") == "v0.2.0"
    assert latest_version.property("text") == "未確認"
    assert progress.property("visible") is False
    button.clicked.emit()
    assert controller.check_calls == 1

    controller.set_update("checking")
    application.processEvents()
    assert button.property("text") == "確認中…"
    assert button.property("enabled") is False

    controller.set_update(
        "upToDate", latest_version="0.2.0", status="PoseCareは最新です"
    )
    application.processEvents()
    assert button.property("text") == "もう一度確認"
    assert status.property("text") == "PoseCareは最新です"

    controller.set_update("error", status="GitHubに接続できませんでした")
    application.processEvents()
    assert button.property("text") == "再確認"
    assert status.property("text") == "GitHubに接続できませんでした"
    button.clicked.emit()
    assert controller.check_calls == 2

    controller._app_version = "v0.2.0-build.122.1"
    controller.set_update(
        "available",
        latest_version="v0.2.0-build.123.1",
        status="新しいバージョンを利用できます",
    )
    application.processEvents()
    assert button.property("text") == "v0.2.0 · b123.1をダウンロード"
    assert button.property("accent") is True
    assert current_version.property("text") == "v0.2.0 · b122.1"
    assert latest_version.property("text") == "v0.2.0 · b123.1"
    assert status.property("text") == "新しいバージョンを利用できます"
    button.clicked.emit()
    assert controller.install_calls == 1

    controller.set_update(
        "downloading",
        latest_version="v0.2.0-build.123.1",
        status="更新ファイルをダウンロードしています",
        progress=0.42,
    )
    application.processEvents()
    assert button.property("text") == "ダウンロード中…"
    assert button.property("enabled") is False
    assert progress.property("visible") is True
    assert progress.property("value") == 0.42

    controller.set_update("ready", latest_version="v0.2.0-build.123.1")
    application.processEvents()
    assert button.property("text") == "再起動して更新"
    assert button.property("enabled") is True
    button.clicked.emit()
    assert controller.install_calls == 2

    root.deleteLater()


def test_main_qml_loads_with_controller(tmp_path):
    application = _application()
    provider = CameraImageProvider()
    history = PostureHistory(tmp_path / "history.sqlite3")
    controller = PoseCareController(
        SettingsStore(tmp_path / "settings.json"),
        AppSettings(),
        make_app_icon(),
        provider,
        history=history,
        notifier=WindowsNotifier(toaster=object(), toast_factory=lambda fields: fields),
        startup_registration=FakeStartupRegistration(),
    )
    engine = QQmlApplicationEngine()
    engine.addImageProvider("camera", provider)
    engine.rootContext().setContextProperty("controller", controller)
    qml_path = Path(__file__).parents[1] / "pose_care" / "ui" / "qml" / "Main.qml"

    engine.load(qml_path)
    application.processEvents()

    assert len(engine.rootObjects()) == 1
    window = engine.rootObjects()[0]
    assert window.property("currentPage") == 0
    assert window.findChild(QObject, "updateCard") is not None
    update_button = window.findChild(QObject, "updateActionButton")
    current_version = window.findChild(QObject, "currentVersionValue")
    assert update_button.property("text") == "更新を確認"
    assert current_version.property("text") == "v0.2.0"
    startup_toggle = window.findChild(QObject, "startupToggle")
    assert startup_toggle is not None
    assert startup_toggle.property("checked") is False
    controller.toggleMonitoring(False)
    assert not controller.monitoring
    controller.shutdown()


def test_registration_only_saves_after_three_stable_seconds(tmp_path, monkeypatch):
    _application()
    monkeypatch.setattr("pose_care.ui.controller.time.monotonic", lambda: 0.0)
    store = SettingsStore(tmp_path / "settings.json")
    controller = PoseCareController(
        store,
        AppSettings(),
        make_app_icon(),
        CameraImageProvider(),
        history=PostureHistory(tmp_path / "history.sqlite3"),
        notifier=WindowsNotifier(toaster=object(), toast_factory=lambda fields: fields),
        startup_registration=FakeStartupRegistration(),
    )
    controller.latest_feature = PoseFeature((0.0,) * 14, {})

    controller.beginRegistration("bad")
    controller.startRegistration("猫背")
    for index in range(1, 32):
        controller._update_registration(
            PoseFeature((0.002 * (index % 2),) * 14, {}),
            now=index * 0.1,
        )

    assert not controller.registrationCapturing
    assert controller.registrationPhase == "complete"
    assert controller.registrationProgress == 100
    assert controller.registrationSecondsRemaining == 0.0
    assert len(controller.settings.profiles) == 1
    assert controller.settings.profiles[0].name == "猫背"
    assert controller.settings.profiles[0].sample_count >= 15
    assert len(store.load().profiles) == 1
    controller.shutdown()


def test_registration_popup_exposes_live_stillness_ui_at_minimum_size(tmp_path):
    application = _application()
    provider = CameraImageProvider()
    controller = PoseCareController(
        SettingsStore(tmp_path / "settings.json"),
        AppSettings(),
        make_app_icon(),
        provider,
        history=PostureHistory(tmp_path / "history.sqlite3"),
        notifier=WindowsNotifier(toaster=object(), toast_factory=lambda fields: fields),
        startup_registration=FakeStartupRegistration(),
    )
    engine = QQmlApplicationEngine()
    engine.addImageProvider("camera", provider)
    engine.rootContext().setContextProperty("controller", controller)
    qml_path = Path(__file__).parents[1] / "pose_care" / "ui" / "qml" / "Main.qml"
    engine.load(qml_path)
    window = engine.rootObjects()[0]
    window.setWidth(960)
    window.setHeight(660)

    controller.beginRegistration("bad")
    application.processEvents()

    popup = window.findChild(QObject, "registrationPopup")
    preview = window.findChild(QObject, "registrationCameraPreview")
    status = window.findChild(QObject, "registrationStatusText")
    start_button = window.findChild(QObject, "registrationStartButton")
    assert popup is not None
    assert popup.property("visible") is True
    assert popup.property("width") <= 912
    assert popup.property("height") <= 624
    assert preview is not None
    assert status.property("text") == "準備できたら登録を開始してください"
    assert start_button.property("text") == "保持を始める"
    assert start_button.property("enabled") is True
    controller.shutdown()


def test_save_settings_updates_startup_registration(tmp_path):
    _application()
    startup = FakeStartupRegistration()
    controller = PoseCareController(
        SettingsStore(tmp_path / "settings.json"),
        AppSettings(),
        make_app_icon(),
        CameraImageProvider(),
        history=PostureHistory(tmp_path / "history.sqlite3"),
        notifier=WindowsNotifier(toaster=object(), toast_factory=lambda fields: fields),
        startup_registration=startup,
    )

    controller.saveSettings(55, 4.0, 5, True, 0, False, True)

    assert startup.enabled
    assert controller.startupEnabled
    assert controller.saveFeedback == "保存しました"
    assert not controller.saveFeedbackError
    controller.shutdown()


def test_startup_registration_error_resyncs_settings_and_feedback(tmp_path):
    application = _application()
    startup = FailingStartupRegistration()
    controller = PoseCareController(
        SettingsStore(tmp_path / "settings.json"),
        AppSettings(),
        make_app_icon(),
        CameraImageProvider(),
        history=PostureHistory(tmp_path / "history.sqlite3"),
        notifier=WindowsNotifier(toaster=object(), toast_factory=lambda fields: fields),
        startup_registration=startup,
    )
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("controller", controller)
    qml_path = Path(__file__).parents[1] / "pose_care" / "ui" / "qml" / "Main.qml"
    engine.load(qml_path)
    window = engine.rootObjects()[0]

    controller.saveSettings(55, 4.0, 5, True, 0, False, True)
    application.processEvents()

    assert not controller.startupEnabled
    assert controller.saveFeedbackError
    assert controller.saveFeedback == "スタートアップに登録できませんでした"
    feedback = window.findChild(QObject, "saveFeedbackText")
    assert feedback.property("text") == controller.saveFeedback
    assert feedback.property("color").name() == "#ff737a"
    controller.shutdown()


def test_hidden_qml_window_reopens_from_notification_and_tray(tmp_path):
    class FakeNotifier:
        def __init__(self):
            self.on_activated = None

        def send(self, title, message, on_activated=None):
            self.on_activated = on_activated
            return True

    application = _application()
    provider = CameraImageProvider()
    notifier = FakeNotifier()
    controller = PoseCareController(
        SettingsStore(tmp_path / "settings.json"),
        AppSettings(),
        make_app_icon(),
        provider,
        history=PostureHistory(tmp_path / "history.sqlite3"),
        notifier=notifier,
    )
    engine = QQmlApplicationEngine()
    engine.addImageProvider("camera", provider)
    engine.rootContext().setContextProperty("controller", controller)
    qml_path = Path(__file__).parents[1] / "pose_care" / "ui" / "qml" / "Main.qml"
    engine.load(qml_path)
    window = engine.rootObjects()[0]
    controller.attach_window(window)

    window.hide()
    controller._send_posture_notification("猫背")
    notifier.on_activated()
    application.processEvents()

    assert window.isVisible()

    window.hide()
    controller.tray.messageClicked.emit()
    application.processEvents()

    assert window.isVisible()

    window.hide()
    controller.tray_menu.actions()[0].trigger()
    application.processEvents()

    assert window.isVisible()
    controller.shutdown()
