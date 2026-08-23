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
from pose_care.models import AppSettings
from pose_care.notifications import WindowsNotifier
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
