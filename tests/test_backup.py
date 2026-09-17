from __future__ import annotations

import json
import sqlite3
import threading
import time
import zipfile

import pytest
from PySide6.QtCore import Qt

from pose_care.backup import export_backup
from pose_care.config import SettingsStore
from pose_care.history import PostureHistory
from pose_care.history_service import HistoryService
from pose_care.models import AppSettings, PostureProfile


def test_backup_restores_all_settings_profiles_and_history(tmp_path):
    history = PostureHistory(tmp_path / "source.sqlite3")
    now = time.time()
    settings = AppSettings(
        camera_index=2, sensitivity=77, hold_seconds=8.5,
        cooldown_minutes=17, notifications_enabled=False,
        start_minimized=True, first_run_complete=True,
        profiles=[
            PostureProfile.create("猫背", [0.1] * 14, 30),
            PostureProfile.create("通常の姿勢", [0.2] * 14, 40, "normal"),
        ],
    )
    # Include records outside all of the UI's 1/7/30-day windows, and a
    # deleted profile's name which must remain in the historical database.
    for age in (350, 40, 7, 0):
        started = now - age * 86400 - 12
        history.observe("bad", "削除済みの姿勢", timestamp=started)
        history.observe("bad", "削除済みの姿勢", timestamp=started + 8)
        history.record_alert("削除済みの姿勢", timestamp=started + 5)
    destination = tmp_path / "移行 データ.zip"
    export_backup(history, json.dumps(settings.to_dict()), destination)
    restored_dir = tmp_path / "restored"
    with zipfile.ZipFile(destination) as archive:
        assert set(archive.namelist()) == {
            "settings.json", "posture_history.sqlite3", "manifest.json", "移行手順.txt",
        }
        assert archive.testzip() is None
        assert json.loads(archive.read("manifest.json"))["version"] == 1
        archive.extractall(restored_dir)
    assert SettingsStore(restored_dir / "settings.json").load() == settings
    with sqlite3.connect(restored_dir / "posture_history.sqlite3") as restored:
        assert restored.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert restored.execute("PRAGMA user_version").fetchone() == (1,)
        for table in ("posture_segments", "posture_alerts"):
            assert restored.execute(f"SELECT * FROM {table}").fetchall() == (
                history._connection.execute(f"SELECT * FROM {table}").fetchall()
            )
        assert restored.execute("SELECT COUNT(*) FROM posture_alerts").fetchone() == (4,)
    restored_history = PostureHistory(restored_dir / "posture_history.sqlite3")
    assert restored_history.summarize("month", now=now) == history.summarize("month", now=now)
    restored_history.close(timestamp=now)
    # Exporting must not end the source's active monitoring session.
    history.observe("good", timestamp=now)
    history.close(timestamp=now + 1)


def test_empty_backup_is_valid_without_existing_settings_file(tmp_path):
    history = PostureHistory(tmp_path / "history.sqlite3")
    destination = tmp_path / "empty.zip"
    export_backup(history, json.dumps(AppSettings().to_dict()), destination)
    with zipfile.ZipFile(destination) as archive:
        assert json.loads(archive.read("settings.json"))["profiles"] == []
        archive.extract("posture_history.sqlite3", tmp_path / "restored")
    with sqlite3.connect(tmp_path / "restored" / "posture_history.sqlite3") as restored:
        assert restored.execute("SELECT COUNT(*) FROM posture_segments").fetchone() == (0,)
    history.close()


@pytest.mark.parametrize("failure_stage", ["snapshot", "archive", "publish"])
def test_failure_preserves_existing_export_and_cleans_temporary_files(tmp_path, monkeypatch, failure_stage):
    history = PostureHistory(tmp_path / "history.sqlite3")
    destination = tmp_path / "existing.zip"
    destination.write_bytes(b"previous backup")

    def fail(*args, **kwargs):
        raise OSError("disk unavailable")

    if failure_stage == "snapshot":
        monkeypatch.setattr(history, "backup", fail)
    elif failure_stage == "archive":
        monkeypatch.setattr(zipfile.ZipFile, "write", fail)
    else:
        monkeypatch.setattr(type(destination), "replace", fail)
    with pytest.raises(OSError, match="disk unavailable"):
        export_backup(history, "{}", destination)
    assert destination.read_bytes() == b"previous backup"
    assert not list(tmp_path.glob(".posecare-export-*"))
    history.close()


def test_service_export_flushes_latest_observation_and_reports_failures(tmp_path):
    service = HistoryService(tmp_path / "history.sqlite3")
    finished = threading.Event()
    results = []

    def on_finished(path, error):
        results.append((path, error))
        finished.set()

    service.exportFinished.connect(on_finished, Qt.ConnectionType.DirectConnection)
    now = time.time()
    service.observe("bad", "猫背", timestamp=now - 8)
    service.observe("bad", "猫背", timestamp=now - 1)
    service.record_alert("猫背", timestamp=now - 2)
    destination = tmp_path / "backup.zip"
    service.request_export(destination, json.dumps(AppSettings().to_dict()))
    assert finished.wait(5)
    assert results == [(str(destination), "")]
    with zipfile.ZipFile(destination) as archive:
        archive.extract("posture_history.sqlite3", tmp_path / "restored")
    with sqlite3.connect(tmp_path / "restored" / "posture_history.sqlite3") as restored:
        row = restored.execute("SELECT started_at, ended_at FROM posture_segments").fetchone()
        assert row[0] == now - 8
        assert row[1] >= now - 1
        assert restored.execute("SELECT COUNT(*) FROM posture_alerts").fetchone() == (1,)
    finished.clear()
    service.request_export(tmp_path / "missing" / "backup.zip", "{}")
    assert finished.wait(5)
    assert results[-1][1]
    # The worker remains usable after a failed export.
    finished.clear()
    service.request_export(destination, "{}")
    assert finished.wait(5)
    assert results[-1][1] == ""
    service.close()
    assert service._closed.wait(5)


def test_export_request_does_not_wait_for_slow_storage(tmp_path, monkeypatch):
    entered = threading.Event()
    release = threading.Event()

    def slow_export(*args):
        entered.set()
        assert release.wait(5)

    monkeypatch.setattr("pose_care.history_service.export_backup", slow_export)
    service = HistoryService(tmp_path / "history.sqlite3")
    try:
        service.request_export(tmp_path / "backup.zip", "{}")
        assert entered.wait(2)
        service.observe("good")
        service.request_summary("day")
        assert not release.is_set()
    finally:
        release.set()
        service.close()
        assert service._closed.wait(5)
