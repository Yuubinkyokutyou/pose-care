from __future__ import annotations

from pathlib import Path

import pytest

from pose_care.startup import (
    RUN_KEY,
    VALUE_NAME,
    StartupRegistration,
    StartupRegistrationError,
)


class FakeKey:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False


class FakeRegistry:
    HKEY_CURRENT_USER = object()
    KEY_QUERY_VALUE = 1
    KEY_SET_VALUE = 2
    REG_SZ = 1

    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.opened_paths: list[str] = []

    def OpenKey(self, root, path, reserved, access):
        self.opened_paths.append(path)
        if VALUE_NAME not in self.values:
            raise FileNotFoundError
        return FakeKey()

    def CreateKeyEx(self, root, path, reserved, access):
        self.opened_paths.append(path)
        return FakeKey()

    def QueryValueEx(self, key, name):
        if name not in self.values:
            raise FileNotFoundError
        return self.values[name], self.REG_SZ

    def SetValueEx(self, key, name, reserved, value_type, value):
        self.values[name] = value

    def DeleteValue(self, key, name):
        if name not in self.values:
            raise FileNotFoundError
        del self.values[name]


def test_startup_registration_round_trip_for_frozen_app():
    registry = FakeRegistry()
    startup = StartupRegistration(
        Path(r"C:\Users\test\AppData\Local\Programs\PoseCare\PoseCare.exe"),
        frozen=True,
        platform="win32",
        registry=registry,
    )

    assert not startup.is_enabled()
    startup.set_enabled(True)

    assert startup.is_enabled()
    assert registry.values[VALUE_NAME] == (
        r"C:\Users\test\AppData\Local\Programs\PoseCare\PoseCare.exe"
    )
    assert registry.opened_paths == [RUN_KEY, RUN_KEY, RUN_KEY]

    startup.set_enabled(False)
    assert not startup.is_enabled()


def test_source_startup_command_uses_pose_care_module():
    startup = StartupRegistration(
        Path(r"C:\Python312\pythonw.exe"),
        frozen=False,
        platform="win32",
        registry=FakeRegistry(),
    )

    assert startup.command == r"C:\Python312\pythonw.exe -m pose_care"


def test_stale_startup_command_is_not_reported_as_enabled():
    registry = FakeRegistry()
    registry.values[VALUE_NAME] = r'"C:\Old Folder\PoseCare.exe"'
    startup = StartupRegistration(
        Path(r"C:\Apps\PoseCare\PoseCare.exe"),
        frozen=True,
        platform="win32",
        registry=registry,
    )

    assert not startup.is_enabled()

    startup.set_enabled(True)
    assert startup.is_enabled()
    assert registry.values[VALUE_NAME] == r"C:\Apps\PoseCare\PoseCare.exe"


def test_registry_write_error_is_reported():
    class FailingRegistry(FakeRegistry):
        def SetValueEx(self, key, name, reserved, value_type, value):
            raise PermissionError("access denied")

    startup = StartupRegistration(
        Path(r"C:\Apps\PoseCare\PoseCare.exe"),
        frozen=True,
        platform="win32",
        registry=FailingRegistry(),
    )

    with pytest.raises(StartupRegistrationError, match="登録できません"):
        startup.set_enabled(True)


def test_startup_registration_is_windows_only():
    startup = StartupRegistration(platform="linux", registry=FakeRegistry())

    with pytest.raises(StartupRegistrationError, match="Windows"):
        startup.set_enabled(True)
