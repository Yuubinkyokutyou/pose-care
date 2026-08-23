from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Any


class WindowsNotifier:
    """Send native Windows toasts, while keeping construction failure non-fatal."""

    def __init__(
        self,
        toaster: Any | None = None,
        toast_factory: Callable[[list[str]], Any] | None = None,
    ) -> None:
        self._toaster = toaster
        self._toast_factory = toast_factory
        self.last_error = ""
        if toaster is not None and toast_factory is not None:
            return
        if sys.platform != "win32":
            self.last_error = "Windows以外ではネイティブ通知を利用できません"
            return
        try:
            from windows_toasts import Toast, WindowsToaster

            self._toaster = WindowsToaster("PoseCare")
            self._toast_factory = Toast
        except Exception as error:
            self.last_error = str(error)
            self._toaster = None
            self._toast_factory = None

    @property
    def available(self) -> bool:
        return self._toaster is not None and self._toast_factory is not None

    def send(
        self,
        title: str,
        message: str,
        on_activated: Callable[[], None] | None = None,
    ) -> bool:
        if not self.available:
            return False
        try:
            toast = self._toast_factory([title, message])
            if on_activated is not None:
                toast.on_activated = lambda _: on_activated()
            self._toaster.show_toast(toast)
            self.last_error = ""
            return True
        except Exception as error:
            self.last_error = str(error)
            return False
