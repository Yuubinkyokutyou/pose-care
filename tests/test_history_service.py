from __future__ import annotations

import sqlite3
import threading
import time

from PySide6.QtCore import Qt

from pose_care.history import PostureHistory
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


def test_profile_change_keeps_its_duration_during_storage_stall(tmp_path):
    path = tmp_path / "history.sqlite3"
    entered = threading.Event()
    release = threading.Event()

    class BlockingOnceHistory(PostureHistory):
        should_block = True

        def observe(self, *args, **kwargs):
            if self.should_block:
                type(self).should_block = False
                entered.set()
                release.wait(2.0)
            super().observe(*args, **kwargs)

    service = HistoryService(path, history_factory=BlockingOnceHistory)
    started_at = time.time()
    service.observe("warning", "姿勢A", timestamp=started_at)
    assert entered.wait(1.0)
    for index in range(1, 61):
        service.observe(
            "warning",
            "姿勢B",
            timestamp=started_at + (index * 0.1),
        )
    release.set()
    service.close(timestamp=started_at + 6.0)

    assert service._closed.wait(3.0)
    with sqlite3.connect(path) as connection:
        durations = dict(connection.execute(
            "SELECT profile_name, SUM(ended_at - started_at) "
            "FROM posture_segments GROUP BY profile_name"
        ).fetchall())

    assert durations["姿勢A"] < 1.0
    assert durations["姿勢B"] > 5.0


def test_state_flicker_within_good_category_does_not_hide_detection(tmp_path):
    path = tmp_path / "history.sqlite3"
    service = HistoryService(path)
    started_at = time.time()

    service.observe("no_pose", timestamp=started_at)
    for index in range(21):
        service.observe(
            "good" if index % 2 == 0 else "normal",
            "デスク姿勢" if index % 2 else None,
            timestamp=started_at + 0.1 + (index * 0.4),
        )
    service.close(timestamp=started_at + 8.5)

    assert service._closed.wait(2.0)
    with sqlite3.connect(path) as connection:
        durations = dict(connection.execute(
            "SELECT state, SUM(ended_at - started_at) FROM posture_segments GROUP BY state"
        ).fetchall())

    detected_seconds = durations.get("good", 0.0) + durations.get("normal", 0.0)
    assert detected_seconds > 7.0
    assert durations["no_pose"] < 1.0


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


def test_recovery_does_not_overlap_old_and_queued_intervals(tmp_path):
    path = tmp_path / "history.sqlite3"
    observed = threading.Event()
    alert_entered = threading.Event()
    release = threading.Event()

    class AlertFailureHistory(PostureHistory):
        should_fail = True

        def observe(self, *args, **kwargs):
            super().observe(*args, **kwargs)
            observed.set()

        def record_alert(self, *args, **kwargs):
            if self.should_fail:
                type(self).should_fail = False
                alert_entered.set()
                release.wait(2.0)
                raise OSError("temporary alert failure")
            super().record_alert(*args, **kwargs)

    service = HistoryService(path, history_factory=AlertFailureHistory)
    started_at = time.time()
    service.observe("good", timestamp=started_at)
    assert observed.wait(1.0)
    service.record_alert("猫背", timestamp=started_at + 0.05)
    assert alert_entered.wait(1.0)
    for index in range(1, 7):
        service.observe("good", timestamp=started_at + (index * 0.1))
    release.set()
    service.close(timestamp=started_at + 0.6)

    assert service._closed.wait(2.0)
    with sqlite3.connect(path) as connection:
        stored_seconds = connection.execute(
            "SELECT SUM(ended_at - started_at) FROM posture_segments WHERE state = 'good'"
        ).fetchone()[0]
        alert_count = connection.execute(
            "SELECT COUNT(*) FROM posture_alerts"
        ).fetchone()[0]

    assert stored_seconds <= 0.61
    assert alert_count == 1


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
        assert len(service._pending_observations) >= 2

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


def test_long_storage_stall_preserves_compacted_continuous_time(tmp_path):
    path = tmp_path / "history.sqlite3"
    entered = threading.Event()
    release = threading.Event()

    class BlockingOnceHistory(PostureHistory):
        should_block = True

        def observe(self, *args, **kwargs):
            if self.should_block:
                type(self).should_block = False
                entered.set()
                release.wait(2.0)
            super().observe(*args, **kwargs)

    service = HistoryService(path, history_factory=BlockingOnceHistory)
    started_at = time.time()
    service.observe("good", timestamp=started_at)
    assert entered.wait(1.0)

    for index in range(5_000):
        service.observe(
            "warning" if index % 2 else "good",
            timestamp=started_at + 1.0 + (index * 0.1),
        )

    release.set()
    service.close(timestamp=started_at + 501.0)
    assert service._closed.wait(3.0)
    with sqlite3.connect(path) as connection:
        good_seconds = connection.execute(
            "SELECT SUM(ended_at - started_at) FROM posture_segments WHERE state = 'good'"
        ).fetchone()[0]

    assert good_seconds > 495.0


def test_close_flushes_latest_compacted_observation(tmp_path):
    path = tmp_path / "history.sqlite3"
    entered = threading.Event()
    release = threading.Event()

    class BlockingOnceHistory(PostureHistory):
        should_block = True

        def observe(self, *args, **kwargs):
            if self.should_block:
                type(self).should_block = False
                entered.set()
                release.wait(2.0)
            super().observe(*args, **kwargs)

    service = HistoryService(path, history_factory=BlockingOnceHistory)
    started_at = time.time()
    service.observe("good", timestamp=started_at)
    assert entered.wait(1.0)
    for index in range(1, 50):
        service.observe("good", timestamp=started_at + (index * 0.1))
    release.set()
    service.close(timestamp=started_at + 4.9)

    assert service._closed.wait(3.0)
    with sqlite3.connect(path) as connection:
        good_seconds = connection.execute(
            "SELECT SUM(ended_at - started_at) FROM posture_segments WHERE state = 'good'"
        ).fetchone()[0]

    assert good_seconds > 4.8


def test_persistent_storage_failure_emits_each_error_kind_once(tmp_path):
    errors = []

    class UnavailableHistory:
        def __init__(self, _path):
            raise OSError("database unavailable")

    service = HistoryService(
        tmp_path / "history.sqlite3",
        history_factory=UnavailableHistory,
    )
    service.historyError.connect(
        lambda message, data_lost: errors.append((message, data_lost)),
        Qt.ConnectionType.DirectConnection,
    )

    for index in range(100):
        service.observe("good", timestamp=time.time() + (index * 0.1))
        time.sleep(0.002)
    deadline = time.monotonic() + 2.0
    while not errors and time.monotonic() < deadline:
        time.sleep(0.01)
    service.close()

    data_loss_errors = [item for item in errors if item[1] is True]
    assert len(data_loss_errors) == 1


def test_summary_open_failure_is_reported_without_claiming_data_loss(tmp_path):
    errors = []

    class UnavailableHistory:
        def __init__(self, _path):
            raise OSError("database unavailable")

    service = HistoryService(
        tmp_path / "history.sqlite3",
        history_factory=UnavailableHistory,
    )
    service.historyError.connect(
        lambda message, data_lost: errors.append((message, data_lost)),
        Qt.ConnectionType.DirectConnection,
    )
    service.request_summary("day")

    deadline = time.monotonic() + 2.0
    while not errors and time.monotonic() < deadline:
        time.sleep(0.01)
    service.close()

    assert errors == [("履歴データベースを開けませんでした", False)]
