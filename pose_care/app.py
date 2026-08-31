from __future__ import annotations

import ctypes
import json
import os
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QLockFile, Qt, QTimer
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtWidgets import QApplication, QMessageBox

from pose_care.config import SettingsStore, app_data_dir
from pose_care.ui.controller import PoseCareController
from pose_care.ui.image_provider import CameraImageProvider
from pose_care.ui.style import configure_font, make_app_icon
from pose_care.windows_session import WindowsSessionMonitor


_UPDATE_READY_FILE_ENV = "POSE_CARE_UPDATE_READY_FILE"
_UPDATE_READY_TOKEN_ENV = "POSE_CARE_UPDATE_READY_TOKEN"
_UPDATE_EXPECTED_TAG_ENV = "POSE_CARE_UPDATE_EXPECTED_TAG"


def _configure_windows_dpi_awareness() -> bool:
    """Keep Qt's logical size and the native Windows window size in sync."""

    if sys.platform != "win32":
        return False

    # DPI awareness must be selected before QApplication creates the first HWND.
    # Prefer Per-Monitor V2 so Qt receives a resize when the window moves between
    # monitors with different scale factors. The older APIs keep the app usable on
    # Windows versions where the newest entry point is unavailable.
    try:
        per_monitor_v2 = ctypes.c_void_p(-4)
        if ctypes.windll.user32.SetProcessDpiAwarenessContext(per_monitor_v2):
            return True
    except (AttributeError, OSError):
        pass

    try:
        if ctypes.windll.shcore.SetProcessDpiAwareness(2) == 0:
            return True
    except (AttributeError, OSError):
        pass

    try:
        return bool(ctypes.windll.user32.SetProcessDPIAware())
    except (AttributeError, OSError):
        return False


def _configure_windows_identity() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("PoseCare.Desktop.0.2")
    except (AttributeError, OSError):
        pass


def _signal_update_ready(release_tag: str) -> bool:
    """Complete the updater handshake after QML and the controller have started."""

    ready_file_value = os.environ.pop(_UPDATE_READY_FILE_ENV, "")
    token = os.environ.pop(_UPDATE_READY_TOKEN_ENV, "")
    expected_tag = os.environ.pop(_UPDATE_EXPECTED_TAG_ENV, "")
    if not ready_file_value or not token or expected_tag != release_tag:
        return False
    if len(token) > 256 or any(character.isspace() for character in token):
        return False

    ready_path = Path(ready_file_value).resolve()
    updates_root = (app_data_dir() / "updates").resolve()
    if ready_path != updates_root and not ready_path.is_relative_to(updates_root):
        return False
    if ready_path.name != "update-ready.json" or not ready_path.parent.is_dir():
        return False
    if ready_path.parent.is_symlink() or (
        hasattr(ready_path.parent, "is_junction") and ready_path.parent.is_junction()
    ):
        return False

    payload = {
        "schema_version": 1,
        "token": token,
        "tag": release_tag,
        "pid": os.getpid(),
    }
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=ready_path.parent,
            prefix="update-ready-",
            suffix=".tmp",
            delete=False,
        ) as stream:
            json.dump(payload, stream, ensure_ascii=False, separators=(",", ":"))
            stream.write("\n")
            temporary_path = Path(stream.name)
        temporary_path.replace(ready_path)
    except OSError:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
        return False
    return True


def main() -> int:
    _configure_windows_dpi_awareness()
    _configure_windows_identity()
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
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
    session_monitor = WindowsSessionMonitor(controller.set_session_locked)
    session_monitor.start(window)
    application.aboutToQuit.connect(session_monitor.close)
    application.aboutToQuit.connect(controller.shutdown)
    controller.start()
    controller.show_initial_window()
    QTimer.singleShot(0, lambda: _signal_update_ready(controller.appVersion))
    exit_code = application.exec()
    lock.unlock()
    return exit_code
