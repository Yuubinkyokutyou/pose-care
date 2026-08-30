from __future__ import annotations

import ctypes
import logging
import sys
from collections.abc import Callable
from ctypes import wintypes
from typing import Any

from PySide6.QtCore import QAbstractNativeEventFilter, QCoreApplication, QTimer


logger = logging.getLogger(__name__)


WM_WTSSESSION_CHANGE = 0x02B1
WM_DESTROY = 0x0002
WTS_SESSION_LOCK = 0x7
WTS_SESSION_UNLOCK = 0x8
NOTIFY_FOR_THIS_SESSION = 0
WTS_CURRENT_SESSION = 0xFFFFFFFF
WTS_SESSION_INFO_EX = 25
WTS_SESSIONSTATE_LOCK = 0
WTS_SESSIONSTATE_UNLOCK = 1
RPC_S_INVALID_BINDING = 1702
SESSION_REGISTRATION_RETRY_MS = 2_000


class _WTSInfoExLevel1(ctypes.Structure):
    _fields_ = (
        ("session_id", wintypes.ULONG),
        ("session_state", ctypes.c_int),
        ("session_flags", wintypes.LONG),
        ("win_station_name", wintypes.WCHAR * 33),
        ("user_name", wintypes.WCHAR * 21),
        ("domain_name", wintypes.WCHAR * 18),
        ("logon_time", ctypes.c_longlong),
        ("connect_time", ctypes.c_longlong),
        ("disconnect_time", ctypes.c_longlong),
        ("last_input_time", ctypes.c_longlong),
        ("current_time", ctypes.c_longlong),
        ("incoming_bytes", wintypes.DWORD),
        ("outgoing_bytes", wintypes.DWORD),
        ("incoming_frames", wintypes.DWORD),
        ("outgoing_frames", wintypes.DWORD),
        ("incoming_compressed_bytes", wintypes.DWORD),
        ("outgoing_compressed_bytes", wintypes.DWORD),
    )


class _WTSInfoExLevel(ctypes.Union):
    _fields_ = (("level1", _WTSInfoExLevel1),)


class _WTSInfoEx(ctypes.Structure):
    _fields_ = (
        ("level", wintypes.DWORD),
        ("data", _WTSInfoExLevel),
    )


def _windows_dll(name: str) -> Any:
    return ctypes.WinDLL(name, use_last_error=True)


def _register_session_notifications(window_handle: int) -> tuple[bool, int]:
    register = _windows_dll("wtsapi32").WTSRegisterSessionNotification
    register.argtypes = (wintypes.HWND, wintypes.DWORD)
    register.restype = wintypes.BOOL
    ctypes.set_last_error(0)
    succeeded = bool(
        register(wintypes.HWND(window_handle), NOTIFY_FOR_THIS_SESSION)
    )
    return succeeded, 0 if succeeded else ctypes.get_last_error()


def _unregister_session_notifications(window_handle: int) -> tuple[bool, int]:
    unregister = _windows_dll("wtsapi32").WTSUnRegisterSessionNotification
    unregister.argtypes = (wintypes.HWND,)
    unregister.restype = wintypes.BOOL
    ctypes.set_last_error(0)
    succeeded = bool(unregister(wintypes.HWND(window_handle)))
    return succeeded, 0 if succeeded else ctypes.get_last_error()


def _query_current_session_locked() -> bool | None:
    wtsapi32 = _windows_dll("wtsapi32")
    query = wtsapi32.WTSQuerySessionInformationW
    query.argtypes = (
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.c_int,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(wintypes.DWORD),
    )
    query.restype = wintypes.BOOL
    free_memory = wtsapi32.WTSFreeMemory
    free_memory.argtypes = (ctypes.c_void_p,)
    free_memory.restype = None

    buffer = ctypes.c_void_p()
    byte_count = wintypes.DWORD()
    ctypes.set_last_error(0)
    if not query(
        None,
        WTS_CURRENT_SESSION,
        WTS_SESSION_INFO_EX,
        ctypes.byref(buffer),
        ctypes.byref(byte_count),
    ):
        error_code = ctypes.get_last_error()
        logger.warning("Failed to query Windows session state (error %s)", error_code)
        return None
    try:
        if not buffer.value or byte_count.value < ctypes.sizeof(_WTSInfoEx):
            logger.warning("Windows returned incomplete session state information")
            return None
        information = ctypes.cast(
            buffer,
            ctypes.POINTER(_WTSInfoEx),
        ).contents
        if information.level != 1:
            logger.warning("Windows returned unsupported session state level")
            return None
        session_flags = int(information.data.level1.session_flags)
        if session_flags == WTS_SESSIONSTATE_LOCK:
            return True
        if session_flags == WTS_SESSIONSTATE_UNLOCK:
            return False
        logger.warning("Windows returned unknown session flags: %s", session_flags)
        return None
    finally:
        free_memory(buffer)


class WindowsSessionMonitor(QAbstractNativeEventFilter):
    """Report Windows lock transitions delivered to a registered Qt window."""

    def __init__(self, on_locked_changed: Callable[[bool], None]) -> None:
        super().__init__()
        self._on_locked_changed = on_locked_changed
        self._application: QCoreApplication | None = None
        self._window_handle: int | None = None
        self._locked: bool | None = None
        self._registered = False
        self._filter_installed = False
        self._registration_retry_timer: QTimer | None = None

    def start(self, window: Any) -> bool:
        if sys.platform != "win32":
            return False
        if self._window_handle is not None:
            return self._registered
        application = QCoreApplication.instance()
        if application is None:
            return False
        try:
            window_handle = int(window.winId())
            if not window_handle:
                return False
        except (AttributeError, OSError, TypeError, ValueError):
            logger.exception("Failed to obtain a window for session notifications")
            return False

        application.installNativeEventFilter(self)
        self._application = application
        self._window_handle = window_handle
        self._filter_installed = True
        self._refresh_current_state()
        self._try_register()
        return self._registered

    def close(self) -> None:
        application, self._application = self._application, None
        retry_timer, self._registration_retry_timer = (
            self._registration_retry_timer,
            None,
        )
        if retry_timer is not None:
            retry_timer.stop()
        self._unregister()
        self._window_handle = None
        if application is not None and self._filter_installed:
            application.removeNativeEventFilter(self)
        self._filter_installed = False

    def _try_register(self) -> None:
        if self._registered or self._window_handle is None:
            return
        try:
            succeeded, error_code = _register_session_notifications(
                self._window_handle
            )
        except (AttributeError, OSError, TypeError, ValueError):
            logger.exception("Failed to register for Windows session notifications")
            return
        if succeeded:
            self._registered = True
            if self._registration_retry_timer is not None:
                self._registration_retry_timer.stop()
            self._refresh_current_state()
            return
        logger.warning(
            "Failed to register for Windows session notifications (error %s)",
            error_code,
        )
        if error_code == RPC_S_INVALID_BINDING:
            self._schedule_registration_retry()

    def _schedule_registration_retry(self) -> None:
        if self._registration_retry_timer is None:
            timer = QTimer()
            timer.setSingleShot(True)
            timer.setInterval(SESSION_REGISTRATION_RETRY_MS)
            timer.timeout.connect(self._try_register)
            self._registration_retry_timer = timer
        self._registration_retry_timer.start()

    def _unregister(self) -> None:
        if not self._registered or self._window_handle is None:
            return
        window_handle = self._window_handle
        self._registered = False
        try:
            succeeded, error_code = _unregister_session_notifications(window_handle)
            if not succeeded:
                logger.warning(
                    "Failed to unregister Windows session notifications (error %s)",
                    error_code,
                )
        except (AttributeError, OSError, TypeError, ValueError):
            logger.exception("Failed to unregister Windows session notifications")

    def _refresh_current_state(self) -> None:
        try:
            current_state = _query_current_session_locked()
        except (AttributeError, OSError, TypeError, ValueError):
            logger.exception("Failed to query the current Windows session state")
            return
        if current_state is not None:
            self._report_locked(current_state)

    def _handle_window_destroyed(self) -> None:
        self._unregister()
        if self._registration_retry_timer is not None:
            self._registration_retry_timer.stop()
        self._window_handle = None

    def nativeEventFilter(self, _event_type: Any, message: int) -> bool:
        if sys.platform != "win32":
            return False
        try:
            native_message = wintypes.MSG.from_address(int(message))
            if (
                int(native_message.message) == WM_DESTROY
                and int(native_message.hWnd or 0) == self._window_handle
            ):
                self._handle_window_destroyed()
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
        self._report_locked(locked)
        return True

    def _report_locked(self, locked: bool) -> None:
        if self._locked == locked:
            return
        self._locked = locked
        try:
            self._on_locked_changed(locked)
        except Exception:
            logger.exception("Failed to handle a Windows session transition")
