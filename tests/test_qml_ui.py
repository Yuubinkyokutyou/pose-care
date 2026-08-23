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
