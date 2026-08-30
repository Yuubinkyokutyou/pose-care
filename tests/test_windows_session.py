from __future__ import annotations

import ctypes
from ctypes import wintypes
from types import SimpleNamespace

from pose_care.windows_session import (
    WM_WTSSESSION_CHANGE,
    WTS_SESSION_LOCK,
    WTS_SESSION_UNLOCK,
    WindowsSessionMonitor,
)


def test_session_monitor_reports_lock_transitions_once():
    transitions = []
    monitor = WindowsSessionMonitor(transitions.append)

    assert not monitor.handle_message(0x1234, WTS_SESSION_LOCK)
    assert monitor.handle_message(WM_WTSSESSION_CHANGE, WTS_SESSION_LOCK)
    assert monitor.handle_message(WM_WTSSESSION_CHANGE, WTS_SESSION_LOCK)
    assert monitor.handle_message(WM_WTSSESSION_CHANGE, WTS_SESSION_UNLOCK)
    assert not monitor.handle_message(WM_WTSSESSION_CHANGE, 0x99)

    assert transitions == [True, False]


def test_native_event_filter_decodes_windows_message():
    transitions = []
    monitor = WindowsSessionMonitor(transitions.append)
    message = wintypes.MSG()
    message.message = WM_WTSSESSION_CHANGE
    message.wParam = WTS_SESSION_LOCK

    assert monitor.nativeEventFilter(
        b"windows_generic_MSG",
        ctypes.addressof(message),
    ) is False
    assert transitions == [True]


def test_session_monitor_registers_and_unregisters_window(monkeypatch):
    installed = []
    removed = []
    registered = []
    unregistered = []
    application = SimpleNamespace(
        installNativeEventFilter=installed.append,
        removeNativeEventFilter=removed.append,
    )
    monkeypatch.setattr(
        "pose_care.windows_session.QCoreApplication.instance",
        lambda: application,
    )
    monkeypatch.setattr(
        "pose_care.windows_session._register_session_notifications",
        lambda handle: (registered.append(handle) or True, 0),
    )
    monkeypatch.setattr(
        "pose_care.windows_session._unregister_session_notifications",
        lambda handle: (unregistered.append(handle) or True, 0),
    )
    monkeypatch.setattr(
        "pose_care.windows_session._query_current_session_locked",
        lambda: False,
    )

    monitor = WindowsSessionMonitor(lambda _locked: None)
    window = SimpleNamespace(winId=lambda: 12345)

    assert monitor.start(window)
    assert monitor.start(window)
    monitor.close()
    monitor.close()

    assert registered == [12345]
    assert installed == [monitor]
    assert removed == [monitor]
    assert unregistered == [12345]


def test_session_monitor_retries_when_terminal_services_is_not_ready(monkeypatch):
    registration_results = [(False, 1702), (True, 0)]

    class FakeSignal:
        def connect(self, callback):
            self.callback = callback

    class FakeTimer:
        def __init__(self):
            self.timeout = FakeSignal()
            self.active = False

        def setSingleShot(self, _single_shot):
            pass

        def setInterval(self, _interval):
            pass

        def start(self):
            self.active = True

        def stop(self):
            self.active = False

        def isActive(self):
            return self.active

    application = SimpleNamespace(
        installNativeEventFilter=lambda _monitor: None,
        removeNativeEventFilter=lambda _monitor: None,
    )
    monkeypatch.setattr(
        "pose_care.windows_session.QCoreApplication.instance",
        lambda: application,
    )
    monkeypatch.setattr(
        "pose_care.windows_session._register_session_notifications",
        lambda _handle: registration_results.pop(0),
    )
    monkeypatch.setattr(
        "pose_care.windows_session._unregister_session_notifications",
        lambda _handle: (True, 0),
    )
    monkeypatch.setattr(
        "pose_care.windows_session._query_current_session_locked",
        lambda: True,
    )
    monkeypatch.setattr("pose_care.windows_session.QTimer", FakeTimer)

    transitions = []
    monitor = WindowsSessionMonitor(transitions.append)

    assert not monitor.start(SimpleNamespace(winId=lambda: 12345))
    assert monitor._registration_retry_timer is not None
    assert monitor._registration_retry_timer.isActive()
    monitor._try_register()

    assert monitor._registered
    assert not monitor._registration_retry_timer.isActive()
    assert transitions == [True]
    monitor.close()


def test_session_monitor_unregisters_before_registered_window_is_destroyed(
    monkeypatch,
):
    unregistered = []
    monitor = WindowsSessionMonitor(lambda _locked: None)
    monitor._window_handle = 12345
    monitor._registered = True
    monkeypatch.setattr(
        "pose_care.windows_session._unregister_session_notifications",
        lambda handle: (unregistered.append(handle) or True, 0),
    )
    message = wintypes.MSG()
    message.hWnd = 12345
    message.message = 0x0002

    monitor.nativeEventFilter(b"windows_generic_MSG", ctypes.addressof(message))

    assert unregistered == [12345]
    assert not monitor._registered
    assert monitor._window_handle is None
