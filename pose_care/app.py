from __future__ import annotations

import ctypes
import sys

from PySide6.QtCore import QLockFile
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from pose_care.config import SettingsStore, app_data_dir
from pose_care.ui.main_window import MainWindow
from pose_care.ui.style import APP_STYLE, configure_font, make_app_icon


def _configure_windows_identity() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("PoseCare.Desktop.0.1")
    except (AttributeError, OSError):
        pass


def main() -> int:
    _configure_windows_identity()
    application = QApplication(sys.argv)
    application.setApplicationName("PoseCare")
    application.setOrganizationName("PoseCare")
    application.setQuitOnLastWindowClosed(False)
    configure_font(application)
    application.setStyleSheet(APP_STYLE)
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
    window = MainWindow(store, settings, icon)
    if settings.start_minimized and settings.first_run_complete and QSystemTrayIcon.isSystemTrayAvailable():
        window.hide()
    else:
        window.show()
    exit_code = application.exec()
    lock.unlock()
    return exit_code
