from __future__ import annotations

from types import SimpleNamespace

from pose_care import app


class _WindowsFunction:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def __call__(self, *args):
        self.calls.append(args)
        return self.result


def test_windows_dpi_awareness_prefers_per_monitor_v2(monkeypatch):
    set_context = _WindowsFunction(True)
    legacy = _WindowsFunction(True)
    windll = SimpleNamespace(
        user32=SimpleNamespace(
            SetProcessDpiAwarenessContext=set_context,
            SetProcessDPIAware=legacy,
        )
    )
    monkeypatch.setattr(app.sys, "platform", "win32")
    monkeypatch.setattr(app.ctypes, "windll", windll, raising=False)

    assert app._configure_windows_dpi_awareness()
    assert len(set_context.calls) == 1
    assert set_context.calls[0][0].value == app.ctypes.c_void_p(-4).value
    assert legacy.calls == []


def test_windows_dpi_awareness_falls_back_for_older_windows(monkeypatch):
    set_context = _WindowsFunction(False)
    set_per_monitor = _WindowsFunction(0)
    legacy = _WindowsFunction(True)
    windll = SimpleNamespace(
        user32=SimpleNamespace(
            SetProcessDpiAwarenessContext=set_context,
            SetProcessDPIAware=legacy,
        ),
        shcore=SimpleNamespace(SetProcessDpiAwareness=set_per_monitor),
    )
    monkeypatch.setattr(app.sys, "platform", "win32")
    monkeypatch.setattr(app.ctypes, "windll", windll, raising=False)

    assert app._configure_windows_dpi_awareness()
    assert set_per_monitor.calls == [(2,)]
    assert legacy.calls == []


def test_windows_dpi_awareness_is_skipped_on_other_platforms(monkeypatch):
    monkeypatch.setattr(app.sys, "platform", "linux")

    assert not app._configure_windows_dpi_awareness()
