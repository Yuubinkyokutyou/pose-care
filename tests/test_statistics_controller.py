from __future__ import annotations

import os
from datetime import datetime, time as datetime_time, timedelta

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")

from PySide6.QtWidgets import QApplication

from pose_care.config import SettingsStore
from pose_care.history import PostureHistory
from pose_care.models import AppSettings
from pose_care.notifications import WindowsNotifier
from pose_care.ui.controller import PoseCareController
from pose_care.ui.image_provider import CameraImageProvider
from pose_care.ui.style import make_app_icon


class FakeStartupRegistration:
    def is_enabled(self) -> bool:
        return False

    def set_enabled(self, enabled: bool) -> None:
        pass


def application() -> QApplication:
    return QApplication.instance() or QApplication([])


def create_controller(tmp_path, history: PostureHistory) -> PoseCareController:
    application()
    return PoseCareController(
        SettingsStore(tmp_path / "settings.json"),
        AppSettings(),
        make_app_icon(),
        CameraImageProvider(),
        history=history,
        notifier=WindowsNotifier(toaster=object(), toast_factory=lambda fields: fields),
        startup_registration=FakeStartupRegistration(),
    )


def observe_span(
    history: PostureHistory,
    state: str,
    started_at: float,
    ended_at: float,
    profile_name: str | None = None,
) -> None:
    timestamp = started_at
    while timestamp < ended_at:
        history.observe(state, profile_name, timestamp=timestamp)
        timestamp += 5


def test_statistics_date_navigation_and_bounds(tmp_path, monkeypatch):
    local_timezone = datetime.now().astimezone().tzinfo
    fixed_now = datetime(2026, 8, 31, 12, tzinfo=local_timezone).timestamp()
    monkeypatch.setattr("pose_care.ui.controller.time.time", lambda: fixed_now)
    controller = create_controller(
        tmp_path,
        PostureHistory(tmp_path / "history.sqlite3"),
    )
    today = controller._local_date_at(fixed_now)

    assert controller.statisticsAnchorDate == today.isoformat()
    assert controller.statisticsRangeLabel == (
        f"{today.year}年{today.month}月{today.day}日"
    )
    assert controller.statisticsCanGoPrevious
    assert not controller.statisticsCanGoNext

    selected = today - timedelta(days=21)
    controller.setStatisticsDate(selected.isoformat())
    assert controller.statisticsAnchorDate == selected.isoformat()
    assert controller.statisticsCanGoNext

    controller.setStatisticsPeriod("week")
    controller.showNextStatistics()
    selected += timedelta(days=7)
    assert controller.statisticsAnchorDate == selected.isoformat()
    controller.showPreviousStatistics()
    selected -= timedelta(days=7)
    assert controller.statisticsAnchorDate == selected.isoformat()

    unchanged = controller.statisticsAnchorDate
    controller.setStatisticsDate("not-an-iso-date")
    assert controller.statisticsAnchorDate == unchanged

    controller.setStatisticsPeriod("day")
    controller.setStatisticsDate((today + timedelta(days=20)).isoformat())
    assert controller.statisticsAnchorDate == today.isoformat()
    assert not controller.statisticsCanGoNext

    controller.setStatisticsDate((today - timedelta(days=800)).isoformat())
    oldest_day = today - timedelta(days=PostureHistory.RETENTION_DAYS - 1)
    assert controller.statisticsAnchorDate == oldest_day.isoformat()
    assert not controller.statisticsCanGoPrevious

    controller.setStatisticsPeriod("month")
    oldest_month_anchor = today - timedelta(
        days=PostureHistory.RETENTION_DAYS - PostureHistory.PERIOD_DAYS["month"]
    )
    assert controller.statisticsAnchorDate == oldest_month_anchor.isoformat()
    assert not controller.statisticsCanGoPrevious
    assert controller.statisticsRangeLabel.startswith(
        f"{oldest_day.year}年{oldest_day.month}月{oldest_day.day}日"
    )
    controller.showNextStatistics()
    regular_month_anchor = today - timedelta(
        days=(
            (today - oldest_month_anchor).days
            - ((today - oldest_month_anchor).days % PostureHistory.PERIOD_DAYS["month"])
        )
    )
    assert controller.statisticsAnchorDate == regular_month_anchor.isoformat()
    controller.showPreviousStatistics()
    assert controller.statisticsAnchorDate == oldest_month_anchor.isoformat()

    controller.showTodayStatistics()
    assert controller.statisticsAnchorDate == today.isoformat()
    assert not controller.statisticsCanGoNext
    controller.shutdown()


def test_timeline_payload_contains_formatted_tooltip_values(tmp_path, monkeypatch):
    history = PostureHistory(tmp_path / "history.sqlite3")
    local_timezone = datetime.now().astimezone().tzinfo
    fixed_now = datetime(2026, 8, 31, 12, tzinfo=local_timezone).timestamp()
    monkeypatch.setattr("pose_care.ui.controller.time.time", lambda: fixed_now)
    anchor_date = datetime.fromtimestamp(fixed_now).date() - timedelta(days=2)
    bucket_start = datetime.combine(
        anchor_date,
        datetime_time(hour=9),
        tzinfo=local_timezone,
    ).timestamp()
    observe_span(history, "good", bucket_start, bucket_start + 120)
    observe_span(history, "bad", bucket_start + 120, bucket_start + 180, "猫背")
    history.observe("paused", timestamp=bucket_start + 180)
    controller = create_controller(tmp_path, history)

    controller.setStatisticsDate(anchor_date.isoformat())

    bucket = controller.timeline[9]
    assert bucket["detailLabel"] == (
        f"{anchor_date.year}年{anchor_date.month}月{anchor_date.day}日 "
        "09:00–10:00"
    )
    assert bucket["good"] == pytest.approx(120.0)
    assert bucket["bad"] == pytest.approx(60.0)
    assert bucket["monitored"] == pytest.approx(180.0)
    assert bucket["goodRatio"] == pytest.approx(2 / 3)
    assert bucket["hasData"] is True
    assert bucket["goodText"] == "2分"
    assert bucket["badText"] == "1分"
    assert bucket["monitoredText"] == "3分"
    assert bucket["ratioText"] == "67%"
    assert controller.timeline[0]["ratioText"] == "—"
    assert controller.timeline[0]["hasData"] is False
    controller.shutdown()
