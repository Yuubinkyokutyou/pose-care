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
        lambda handle: registered.append(handle) or True,
    )
    monkeypatch.setattr(
        "pose_care.windows_session._unregister_session_notifications",
        lambda handle: unregistered.append(handle) or True,
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
