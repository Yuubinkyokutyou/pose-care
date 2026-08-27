from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import ModuleType


RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "PoseCare"


class StartupRegistrationError(RuntimeError):
    """Raised when the Windows startup registration cannot be changed."""


class StartupRegistration:
    """Manage PoseCare's per-user Windows startup registration."""

    def __init__(
        self,
        executable_path: Path | None = None,
        *,
        frozen: bool | None = None,
        platform: str | None = None,
        registry: ModuleType | None = None,
    ) -> None:
        self.executable_path = Path(executable_path or sys.executable).resolve()
        self.frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
        self.platform = sys.platform if platform is None else platform
        self._registry = registry

    @property
    def command(self) -> str:
        arguments = [str(self.executable_path)]
        if not self.frozen:
            arguments.extend(["-m", "pose_care"])
        return subprocess.list2cmdline(arguments)

    def is_enabled(self) -> bool:
        registry = self._windows_registry()
        try:
            with registry.OpenKey(
                registry.HKEY_CURRENT_USER,
                RUN_KEY,
                0,
                registry.KEY_QUERY_VALUE,
            ) as key:
                registry.QueryValueEx(key, VALUE_NAME)
        except FileNotFoundError:
            return False
        except OSError as error:
            raise StartupRegistrationError(
                "スタートアップ登録の状態を確認できませんでした"
            ) from error
        return True

    def set_enabled(self, enabled: bool) -> None:
        registry = self._windows_registry()
        if enabled:
            try:
                with registry.CreateKeyEx(
                    registry.HKEY_CURRENT_USER,
                    RUN_KEY,
                    0,
                    registry.KEY_SET_VALUE,
                ) as key:
                    registry.SetValueEx(
                        key,
                        VALUE_NAME,
                        0,
                        registry.REG_SZ,
                        self.command,
                    )
            except OSError as error:
                raise StartupRegistrationError(
                    "スタートアップに登録できませんでした"
                ) from error
            return

        try:
            with registry.OpenKey(
                registry.HKEY_CURRENT_USER,
                RUN_KEY,
                0,
                registry.KEY_SET_VALUE,
            ) as key:
                registry.DeleteValue(key, VALUE_NAME)
        except FileNotFoundError:
            return
        except OSError as error:
            raise StartupRegistrationError(
                "スタートアップ登録を解除できませんでした"
            ) from error

    def _windows_registry(self) -> ModuleType:
        if self.platform != "win32":
            raise StartupRegistrationError(
                "スタートアップ登録はWindowsでのみ利用できます"
            )
        if self._registry is None:
            import winreg

            self._registry = winreg
        return self._registry
