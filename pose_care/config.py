from __future__ import annotations

import json
import os
from pathlib import Path

from pose_care.models import AppSettings


APP_NAME = "PoseCare"


def app_data_dir() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / APP_NAME
    return Path.home() / "AppData" / "Local" / APP_NAME


class SettingsStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or app_data_dir() / "settings.json"

    def load(self) -> AppSettings:
        if not self.path.exists():
            return AppSettings()
        try:
            with self.path.open("r", encoding="utf-8") as stream:
                payload = json.load(stream)
            return AppSettings.from_dict(payload)
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            backup_path = self.path.with_suffix(".invalid.json")
            try:
                self.path.replace(backup_path)
            except OSError:
                pass
            return AppSettings()

    def save(self, settings: AppSettings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.path.with_suffix(".tmp")
        with temporary_path.open("w", encoding="utf-8") as stream:
            json.dump(settings.to_dict(), stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        temporary_path.replace(self.path)


def model_path() -> Path:
    return app_data_dir() / "models" / "pose_landmarker_lite.task"
