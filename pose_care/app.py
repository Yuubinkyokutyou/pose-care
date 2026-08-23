from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path

from PySide6.QtCore import QLockFile
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtWidgets import QApplication, QMessageBox

from pose_care.config import SettingsStore, app_data_dir
from pose_care.ui.controller import PoseCareController
from pose_care.ui.image_provider import CameraImageProvider
from pose_care.ui.style import configure_font, make_app_icon


def _configure_windows_identity() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("PoseCare.Desktop.0.2")
    except (AttributeError, OSError):
        pass


def main() -> int:
    _configure_windows_identity()
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    application = QApplication(sys.argv)
    application.setApplicationName("PoseCare")
    application.setOrganizationName("PoseCare")
    application.setQuitOnLastWindowClosed(False)
    configure_font(application)
    icon = make_app_icon()
    application.setWindowIcon(icon)

    data_directory = app_data_dir()
    data_directory.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(data_directory / "pose-care.lock"))
    lock.setStaleLockTime(10_000)
    if not lock.tryLock(100):
        QMessageBox.information(None, "PoseCare", "PoseCareはすでに起動しています。タスクトレイを確認してください。")
        return 0

    store = SettingsStore()
    settings = store.load()
    image_provider = CameraImageProvider()
    controller = PoseCareController(store, settings, icon, image_provider)
    engine = QQmlApplicationEngine()
    engine.addImageProvider("camera", image_provider)
    engine.rootContext().setContextProperty("controller", controller)
    qml_path = Path(__file__).parent / "ui" / "qml" / "Main.qml"
    engine.load(qml_path)
    if not engine.rootObjects():
        controller.shutdown()
        lock.unlock()
        return 1

    window = engine.rootObjects()[0]
    controller.attach_window(window)
    application.aboutToQuit.connect(controller.shutdown)
    controller.start()
    controller.show_initial_window()
    exit_code = application.exec()
    lock.unlock()
    return exit_code
