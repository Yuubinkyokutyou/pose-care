from __future__ import annotations

import sqlite3
import threading
import time

from pose_care.history_service import HistoryService


def test_history_service_coalesces_brief_state_flicker(tmp_path):
    path = tmp_path / "history.sqlite3"
    service = HistoryService(path)
    started_at = time.time()

    service.observe("good", timestamp=started_at)
    for offset in (0.10, 0.30, 0.50):
        service.observe("no_pose", timestamp=started_at + offset)
        service.observe("good", timestamp=started_at + offset + 0.05)
    service.observe("good", timestamp=started_at + 2.0)
    service.close(timestamp=started_at + 2.0)

    assert service._closed.wait(2.0)
    with sqlite3.connect(path) as connection:
        rows = connection.execute(
            "SELECT state, COUNT(*) FROM posture_segments GROUP BY state"
        ).fetchall()

    assert rows == [("good", 1)]


def test_history_service_keeps_stable_state_changes(tmp_path):
    path = tmp_path / "history.sqlite3"
    service = HistoryService(path)
    started_at = time.time()

    service.observe("good", timestamp=started_at)
    for offset in (0.10, 0.50, 0.90):
        service.observe("no_pose", timestamp=started_at + offset)
    for offset in (1.00, 1.40, 1.80):
        service.observe("good", timestamp=started_at + offset)
    service.close(timestamp=started_at + 2.0)

    assert service._closed.wait(2.0)
    with sqlite3.connect(path) as connection:
        rows = connection.execute(
            "SELECT state, COUNT(*) FROM posture_segments GROUP BY state ORDER BY state"
        ).fetchall()

    assert rows == [("good", 2), ("no_pose", 1)]


def test_profile_flicker_does_not_hide_stable_warning_state(tmp_path):
    path = tmp_path / "history.sqlite3"
    service = HistoryService(path)
    started_at = time.time()

    service.observe("good", timestamp=started_at)
    for index in range(21):
        service.observe(
            "warning",
            "姿勢A" if index % 2 == 0 else "姿勢B",
            timestamp=started_at + 0.1 + (index * 0.4),
        )
    service.close(timestamp=started_at + 8.5)

    assert service._closed.wait(2.0)
    with sqlite3.connect(path) as connection:
        durations = dict(connection.execute(
            "SELECT state, SUM(ended_at - started_at) FROM posture_segments GROUP BY state"
        ).fetchall())

    assert durations["warning"] > 7.0
    assert durations["good"] < 1.0


def test_history_service_calls_never_wait_for_blocked_storage(tmp_path):
    entered = threading.Event()
    release = threading.Event()

    class BlockingHistory:
        def __init__(self, _path):
            pass

        def observe(self, _state, _profile_name=None, *, timestamp=None):
            del timestamp
            entered.set()
            release.wait(2.0)

        def record_alert(self, _profile_name, *, timestamp=None):
            del timestamp

        def summarize(self, _period, **_kwargs):
            raise AssertionError("summary should remain queued while storage is blocked")

        def close(self, *, timestamp=None):
            del timestamp

    service = HistoryService(
        tmp_path / "history.sqlite3",
        history_factory=BlockingHistory,
    )
    service.observe("good")
    assert entered.wait(1.0)

    started = time.perf_counter()
    service.observe("no_pose")
    service.record_alert("猫背")
    elapsed = time.perf_counter() - started

    assert elapsed < 0.1
    release.set()
    service.close()
    assert service._closed.wait(2.0)


def test_history_service_recovers_after_transient_storage_error(tmp_path):
    failed = threading.Event()
    stored = []
    alerts = []

    class FlakyHistory:
        should_fail = True

        def __init__(self, _path):
            pass

        def observe(self, state, profile_name=None, *, timestamp=None):
            if self.should_fail:
                type(self).should_fail = False
                failed.set()
                raise OSError("temporary storage failure")
            stored.append((state, profile_name, timestamp))

        def record_alert(self, profile_name, *, timestamp=None):
            alerts.append((profile_name, timestamp))

        def close(self, *, timestamp=None):
            del timestamp

    service = HistoryService(
        tmp_path / "history.sqlite3",
        history_factory=FlakyHistory,
    )
    service.observe("good", timestamp=1.0)
    assert failed.wait(1.0)
    service.observe("bad", "猫背", timestamp=2.0)
    service.observe("bad", "猫背", timestamp=3.0)
    service.record_alert("猫背", timestamp=3.0)
    service.close(timestamp=4.0)

    assert service._closed.wait(2.0)
    assert stored
    assert any(state == "bad" for state, _profile, _timestamp in stored)
    assert alerts == [("猫背", 3.0)]


def test_pending_observations_are_bounded_while_storage_is_blocked(tmp_path):
    entered = threading.Event()
    release = threading.Event()

    class BlockingHistory:
        def __init__(self, _path):
            pass

        def observe(self, _state, _profile_name=None, *, timestamp=None):
            del timestamp
            entered.set()
            release.wait(2.0)

        def close(self, *, timestamp=None):
            del timestamp

    service = HistoryService(
        tmp_path / "history.sqlite3",
        history_factory=BlockingHistory,
    )
    service.observe("good", timestamp=1.0)
    assert entered.wait(1.0)

    for index in range(100):
        service.observe("warning", timestamp=2.0 + (index * 0.1))
    with service._observation_lock:
        assert len(service._pending_observations) >= 30

    for index in range(5_000):
        service.observe(
            "warning" if index % 2 else "good",
            timestamp=2.0 + (index * 0.1),
        )

    with service._observation_lock:
        assert len(service._pending_observations) <= service.MAX_PENDING_OBSERVATIONS
    assert service._commands.qsize() <= 1

    release.set()
    service.close(timestamp=600.0)
    assert service._closed.wait(2.0)
