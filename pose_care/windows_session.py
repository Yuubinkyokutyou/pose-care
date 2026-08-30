from __future__ import annotations

import ctypes
import logging
import sys
from collections.abc import Callable
from ctypes import wintypes
from typing import Any

from PySide6.QtCore import QAbstractNativeEventFilter, QCoreApplication


logger = logging.getLogger(__name__)


WM_WTSSESSION_CHANGE = 0x02B1
WTS_SESSION_LOCK = 0x7
WTS_SESSION_UNLOCK = 0x8
NOTIFY_FOR_THIS_SESSION = 0


def _register_session_notifications(window_handle: int) -> bool:
    register = ctypes.windll.wtsapi32.WTSRegisterSessionNotification
    register.argtypes = (wintypes.HWND, wintypes.DWORD)
    register.restype = wintypes.BOOL
    return bool(register(wintypes.HWND(window_handle), NOTIFY_FOR_THIS_SESSION))


def _unregister_session_notifications(window_handle: int) -> bool:
    unregister = ctypes.windll.wtsapi32.WTSUnRegisterSessionNotification
    unregister.argtypes = (wintypes.HWND,)
    unregister.restype = wintypes.BOOL
    return bool(unregister(wintypes.HWND(window_handle)))


class WindowsSessionMonitor(QAbstractNativeEventFilter):
    """Report Windows lock transitions delivered to a registered Qt window."""

    def __init__(self, on_locked_changed: Callable[[bool], None]) -> None:
        super().__init__()
        self._on_locked_changed = on_locked_changed
        self._application: QCoreApplication | None = None
        self._window_handle: int | None = None
        self._locked: bool | None = None

    def start(self, window: Any) -> bool:
        if sys.platform != "win32":
            return False
        if self._window_handle is not None:
            return True
        application = QCoreApplication.instance()
        if application is None:
            return False
        try:
            window_handle = int(window.winId())
            if not window_handle or not _register_session_notifications(window_handle):
                logger.warning("Failed to register for Windows session notifications")
                return False
        except (AttributeError, OSError, TypeError, ValueError):
            logger.exception("Failed to register for Windows session notifications")
            return False

        application.installNativeEventFilter(self)
        self._application = application
        self._window_handle = window_handle
        return True

    def close(self) -> None:
        application, self._application = self._application, None
        window_handle, self._window_handle = self._window_handle, None
        if application is not None:
            application.removeNativeEventFilter(self)
        if window_handle is None:
            return
        try:
            if not _unregister_session_notifications(window_handle):
                logger.warning("Failed to unregister Windows session notifications")
        except (AttributeError, OSError, TypeError, ValueError):
            logger.exception("Failed to unregister Windows session notifications")

    def nativeEventFilter(self, _event_type: Any, message: int) -> bool:
        if sys.platform != "win32":
            return False
        try:
            native_message = wintypes.MSG.from_address(int(message))
            self.handle_message(
                int(native_message.message),
                int(native_message.wParam),
            )
        except (AttributeError, TypeError, ValueError):
            logger.exception("Failed to read a Windows session notification")
        return False

    def handle_message(self, message: int, event: int) -> bool:
        if message != WM_WTSSESSION_CHANGE:
            return False
        if event == WTS_SESSION_LOCK:
            locked = True
        elif event == WTS_SESSION_UNLOCK:
            locked = False
        else:
            return False
        if self._locked == locked:
            return True
        self._locked = locked
        try:
            self._on_locked_changed(locked)
        except Exception:
            logger.exception("Failed to handle a Windows session transition")
        return True
