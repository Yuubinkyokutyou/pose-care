from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import sqlite3

import pytest

from pose_care.history import PostureHistory


def utc_timestamp(year: int, month: int, day: int, hour: int = 0) -> float:
    return datetime(year, month, day, hour, tzinfo=timezone.utc).timestamp()


def observe_span(history, state, started_at, ended_at, profile_name=None):
    timestamp = started_at
    while timestamp < ended_at:
        history.observe(state, profile_name, timestamp=timestamp)
        timestamp += 5


def test_summary_calculates_good_bad_profiles_and_alerts(tmp_path):
    history = PostureHistory(tmp_path / "history.sqlite3")
    started_at = utc_timestamp(2026, 8, 23)
    observe_span(history, "good", started_at, started_at + 600)
    observe_span(history, "warning", started_at + 600, started_at + 720, "猫背")
    observe_span(history, "bad", started_at + 720, started_at + 900, "猫背")
    history.record_alert("猫背", timestamp=started_at + 721)
    history.record_alert("猫背", timestamp=started_at + 721)
    observe_span(history, "normal", started_at + 900, started_at + 1200, "普段の姿勢")
    history.observe("paused", timestamp=started_at + 1200)

    summary = history.summarize(
        "day",
        now=started_at + 3600,
        timezone_info=timezone.utc,
    )

    assert summary.good_seconds == pytest.approx(900.0)
    assert summary.bad_seconds == pytest.approx(300.0)
    assert summary.good_ratio == pytest.approx(0.75)
    assert summary.alert_count == 1
    assert summary.bad_profiles[0].name == "猫背"
    assert summary.bad_profiles[0].seconds == pytest.approx(300.0)
    assert summary.timeline[0].good_seconds == pytest.approx(900.0)
    assert summary.timeline[0].bad_seconds == pytest.approx(300.0)
    history.close(timestamp=started_at + 3600)


def test_week_and_month_use_daily_buckets(tmp_path):
    history = PostureHistory(tmp_path / "history.sqlite3")
    now = utc_timestamp(2026, 8, 23, 12)
    first = utc_timestamp(2026, 8, 21, 9)
    observe_span(history, "good", first, first + 3600)
    history.observe("paused", timestamp=first + 3600)
    second = utc_timestamp(2026, 8, 23, 10)
    observe_span(history, "bad", second, second + 1800, "前のめり")
    history.observe("paused", timestamp=second + 1800)

    week = history.summarize("week", now=now, timezone_info=timezone.utc)
    month = history.summarize("month", now=now, timezone_info=timezone.utc)

    assert len(week.timeline) == 7
    assert len(month.timeline) == 30
    assert week.timeline[-3].good_seconds == pytest.approx(3600.0)
    assert week.timeline[-1].bad_seconds == pytest.approx(1800.0)
    assert month.good_seconds == pytest.approx(3600.0)
    assert month.bad_seconds == pytest.approx(1800.0)
    history.close(timestamp=now)


def test_past_anchor_uses_selected_window_but_checkpoints_at_now(tmp_path):
    history = PostureHistory(tmp_path / "history.sqlite3")
    selected_date = date(2026, 8, 20)
    selected_start = utc_timestamp(2026, 8, 20)
    monitored_start = selected_start + (10 * 3600)
    observe_span(history, "good", monitored_start, monitored_start + 300)
    history.observe("paused", timestamp=monitored_start + 300)

    now = utc_timestamp(2026, 8, 31, 12)
    history.observe("good", timestamp=now - 5)
    history.observe("good", timestamp=now)

    summary = history.summarize(
        "day",
        now=now,
        timezone_info=timezone.utc,
        anchor_date=selected_date,
    )
    week = history.summarize(
        "week",
        now=now,
        timezone_info=timezone.utc,
        anchor_date=selected_date,
    )

    assert summary.started_at == selected_start
    assert summary.ended_at == selected_start + 86400
    assert summary.good_seconds == pytest.approx(300.0)
    assert summary.timeline[10].started_at == monitored_start
    assert summary.timeline[10].ended_at == monitored_start + 3600
    assert datetime.fromtimestamp(week.started_at, tz=timezone.utc).date() == (
        selected_date - timedelta(days=6)
    )
    assert datetime.fromtimestamp(week.ended_at, tz=timezone.utc).date() == (
        selected_date + timedelta(days=1)
    )
    active_ended_at = history._connection.execute(
        "SELECT ended_at FROM posture_segments WHERE started_at = ?",
        (now - 5,),
    ).fetchone()[0]
    assert active_ended_at == now
    history.close(timestamp=now)


def test_anchor_is_clamped_to_today_and_full_retention_windows(tmp_path):
    history = PostureHistory(tmp_path / "history.sqlite3")
    current_date = date(2026, 8, 31)
    now = utc_timestamp(2026, 8, 31, 12)

    future = history.summarize(
        "day",
        now=now,
        timezone_info=timezone.utc,
        anchor_date=current_date + timedelta(days=20),
    )
    oldest_day = history.summarize(
        "day",
        now=now,
        timezone_info=timezone.utc,
        anchor_date=current_date - timedelta(days=800),
    )
    oldest_month = history.summarize(
        "month",
        now=now,
        timezone_info=timezone.utc,
        anchor_date=current_date - timedelta(days=800),
    )

    expected_oldest = current_date - timedelta(days=history.RETENTION_DAYS - 1)
    assert future.started_at == utc_timestamp(2026, 8, 31)
    assert future.ended_at == now
    assert datetime.fromtimestamp(oldest_day.started_at, tz=timezone.utc).date() == expected_oldest
    assert datetime.fromtimestamp(oldest_month.started_at, tz=timezone.utc).date() == expected_oldest
    assert len(oldest_month.timeline) == 30
    history.close(timestamp=now)


def test_long_running_history_prunes_expired_rows_during_summary(
    tmp_path,
    monkeypatch,
):
    initialized_at = utc_timestamp(2025, 1, 1)
    monkeypatch.setattr("pose_care.history.time.time", lambda: initialized_at)
    history = PostureHistory(tmp_path / "history.sqlite3")
    history._connection.execute(
        """
        INSERT INTO posture_segments(started_at, ended_at, state, profile_name)
        VALUES (?, ?, 'bad', '猫背')
        """,
        (initialized_at, initialized_at + 60),
    )
    history._connection.execute(
        "INSERT INTO posture_alerts(occurred_at, profile_name) VALUES (?, '猫背')",
        (initialized_at,),
    )
    history._connection.commit()

    later = initialized_at + (401 * 86400)
    history.summarize("day", now=later, timezone_info=timezone.utc)

    segment_count = history._connection.execute(
        "SELECT COUNT(*) FROM posture_segments"
    ).fetchone()[0]
    alert_count = history._connection.execute(
        "SELECT COUNT(*) FROM posture_alerts"
    ).fetchone()[0]
    assert segment_count == 0
    assert alert_count == 0
    history.close(timestamp=later)


def test_long_observation_gap_is_not_counted_as_monitoring(tmp_path):
    history = PostureHistory(tmp_path / "history.sqlite3")
    started_at = utc_timestamp(2026, 8, 23)
    history.observe("good", timestamp=started_at)
    history.observe("good", timestamp=started_at + 5)
    history.observe("good", timestamp=started_at + 100)
    history.observe("paused", timestamp=started_at + 105)

    summary = history.summarize(
        "day",
        now=started_at + 200,
        timezone_info=timezone.utc,
    )

    assert summary.good_seconds == pytest.approx(12.0)
    history.close(timestamp=started_at + 200)


def test_history_survives_reopening_database(tmp_path):
    path = tmp_path / "history.sqlite3"
    started_at = utc_timestamp(2026, 8, 23)
    first = PostureHistory(path)
    observe_span(first, "bad", started_at, started_at + 60, "猫背")
    first.observe("paused", timestamp=started_at + 60)
    first.close(timestamp=started_at + 60)

    reopened = PostureHistory(path)
    summary = reopened.summarize(
        "day",
        now=started_at + 120,
        timezone_info=timezone.utc,
    )

    assert summary.bad_seconds == pytest.approx(60.0)
    assert summary.bad_profiles[0].name == "猫背"
    reopened.close(timestamp=started_at + 120)


def test_checkpoints_update_one_segment_instead_of_fragmenting_it(tmp_path):
    path = tmp_path / "history.sqlite3"
    started_at = utc_timestamp(2026, 8, 23)
    history = PostureHistory(path)
    observe_span(history, "good", started_at, started_at + 600)
    history.observe("paused", timestamp=started_at + 600)
    history.close(timestamp=started_at + 600)

    with sqlite3.connect(path) as connection:
        good_segments = connection.execute(
            "SELECT COUNT(*) FROM posture_segments WHERE state = 'good'"
        ).fetchone()[0]

    assert good_segments == 1


def test_unknown_period_is_rejected(tmp_path):
    history = PostureHistory(tmp_path / "history.sqlite3")
    with pytest.raises(ValueError, match="未対応"):
        history.summarize("year")
    history.close()
