from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import QSize
from PySide6.QtGui import QImage
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtWidgets import QApplication

from pose_care.config import SettingsStore
from pose_care.history import PostureHistory
from pose_care.models import AppSettings
from pose_care.notifications import WindowsNotifier
from pose_care.ui.controller import PoseCareController
from pose_care.ui.image_provider import CameraImageProvider
from pose_care.ui.style import make_app_icon


def _application() -> QApplication:
    return QApplication.instance() or QApplication([])


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

    def stop_camera():
        stopped.append(True)
        controller.camera_worker = None

    def start_camera():
        started.append(True)
        controller.camera_worker = object()

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
    # user's explicit monitoring setting.
    user_idle_seconds[0] = 0.5
    controller._check_camera_activity()
    assert started == [True]
    assert not controller._camera_suspended_for_idle
    assert controller.stateKind == "starting"
    assert controller.monitoring
    controller.shutdown()


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
    )
    engine = QQmlApplicationEngine()
    engine.addImageProvider("camera", provider)
    engine.rootContext().setContextProperty("controller", controller)
    qml_path = Path(__file__).parents[1] / "pose_care" / "ui" / "qml" / "Main.qml"

    engine.load(qml_path)
    application.processEvents()

    assert len(engine.rootObjects()) == 1
    assert engine.rootObjects()[0].property("currentPage") == 0
    controller.toggleMonitoring(False)
    assert not controller.monitoring
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
