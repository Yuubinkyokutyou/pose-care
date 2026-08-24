from __future__ import annotations

import json
import os

from pose_care.app import (
    _UPDATE_EXPECTED_TAG_ENV,
    _UPDATE_READY_FILE_ENV,
    _UPDATE_READY_TOKEN_ENV,
    _signal_update_ready,
)


def _set_handshake_environment(monkeypatch, ready_path, *, expected_tag: str) -> None:
    monkeypatch.setenv(_UPDATE_READY_FILE_ENV, str(ready_path))
    monkeypatch.setenv(_UPDATE_READY_TOKEN_ENV, "test-ready-token")
    monkeypatch.setenv(_UPDATE_EXPECTED_TAG_ENV, expected_tag)


def test_signal_update_ready_writes_atomic_handshake_inside_updates(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    workspace = tmp_path / "PoseCare" / "updates" / "posecare-update-test"
    workspace.mkdir(parents=True)
    ready_path = workspace / "update-ready.json"
    tag = "v0.2.0-build.42.1"
    _set_handshake_environment(monkeypatch, ready_path, expected_tag=tag)

    assert _signal_update_ready(tag)

    payload = json.loads(ready_path.read_text(encoding="utf-8"))
    assert payload == {
        "schema_version": 1,
        "token": "test-ready-token",
        "tag": tag,
        "pid": os.getpid(),
    }
    assert _UPDATE_READY_FILE_ENV not in os.environ
    assert _UPDATE_READY_TOKEN_ENV not in os.environ
    assert _UPDATE_EXPECTED_TAG_ENV not in os.environ
    assert list(workspace.glob("*.tmp")) == []


def test_signal_update_ready_rejects_wrong_tag(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    workspace = tmp_path / "PoseCare" / "updates" / "posecare-update-test"
    workspace.mkdir(parents=True)
    ready_path = workspace / "update-ready.json"
    _set_handshake_environment(
        monkeypatch,
        ready_path,
        expected_tag="v0.2.0-build.42.1",
    )

    assert not _signal_update_ready("v0.2.0-build.41.1")
    assert not ready_path.exists()


def test_signal_update_ready_rejects_path_outside_updates(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local-app-data"))
    outside = tmp_path / "outside"
    outside.mkdir()
    ready_path = outside / "update-ready.json"
    tag = "v0.2.0-build.42.1"
    _set_handshake_environment(monkeypatch, ready_path, expected_tag=tag)

    assert not _signal_update_ready(tag)
    assert not ready_path.exists()
