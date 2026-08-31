from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from datetime import date, datetime, time as datetime_time, timedelta, tzinfo
from pathlib import Path


GOOD_STATES = frozenset({"good", "normal"})
BAD_STATES = frozenset({"warning", "bad"})
TRACKED_STATES = GOOD_STATES | BAD_STATES


@dataclass(frozen=True, slots=True)
class TimelineBucket:
    label: str
    good_seconds: float
    bad_seconds: float
    capacity_seconds: float
    started_at: float = 0.0
    ended_at: float = 0.0

    @property
    def monitored_seconds(self) -> float:
        return self.good_seconds + self.bad_seconds


@dataclass(frozen=True, slots=True)
class ProfileDuration:
    name: str
    seconds: float


@dataclass(frozen=True, slots=True)
class StatisticsSummary:
    period: str
    started_at: float
    ended_at: float
    good_seconds: float
    bad_seconds: float
    alert_count: int
    timeline: tuple[TimelineBucket, ...]
    bad_profiles: tuple[ProfileDuration, ...]

    @property
    def monitored_seconds(self) -> float:
        return self.good_seconds + self.bad_seconds

    @property
    def good_ratio(self) -> float | None:
        if self.monitored_seconds <= 0.0:
            return None
        return self.good_seconds / self.monitored_seconds


class PostureHistory:
    """Persist compact posture intervals and build rolling local summaries."""

    CHECKPOINT_SECONDS = 30.0
    MAX_OBSERVATION_GAP_SECONDS = 10.0
    OBSERVATION_GRACE_SECONDS = 2.0
    RETENTION_DAYS = 400
    CLEANUP_INTERVAL_SECONDS = 24 * 60 * 60.0
    PERIOD_DAYS = {"day": 1, "week": 7, "month": 30}

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path)
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA synchronous=NORMAL")
        self._connection.execute("PRAGMA busy_timeout=3000")
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS posture_segments (
                id INTEGER PRIMARY KEY,
                started_at REAL NOT NULL,
                ended_at REAL NOT NULL,
                state TEXT NOT NULL,
                profile_name TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_posture_segments_time
                ON posture_segments(started_at, ended_at);
            CREATE TABLE IF NOT EXISTS posture_alerts (
                id INTEGER PRIMARY KEY,
                occurred_at REAL NOT NULL,
                profile_name TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_posture_alerts_time
                ON posture_alerts(occurred_at);
            PRAGMA user_version=1;
            """
        )
        self._connection.commit()
        self._active_state: str | None = None
        self._active_profile: str | None = None
        self._active_started_at = 0.0
        self._active_segment_id: int | None = None
        self._last_observed_at = 0.0
        self._last_checkpoint_at = 0.0
        self._closed = False
        initialized_at = time.time()
        self._delete_expired(initialized_at)
        self._last_cleanup_at = initialized_at

    def observe(
        self,
        state: str,
        profile_name: str | None = None,
        *,
        timestamp: float | None = None,
    ) -> None:
        if self._closed:
            return
        observed_at = time.time() if timestamp is None else float(timestamp)
        normalized_profile = profile_name if state in ("normal", "warning", "bad") else None
        if self._active_state is None:
            self._begin(state, normalized_profile, observed_at)
            return

        gap = observed_at - self._last_observed_at
        if gap < 0.0 or gap > self.MAX_OBSERVATION_GAP_SECONDS:
            self._finalize(min(
                max(self._active_started_at, self._last_observed_at + self.OBSERVATION_GRACE_SECONDS),
                observed_at,
            ))
            self._begin(state, normalized_profile, observed_at)
            return

        if state != self._active_state or normalized_profile != self._active_profile:
            self._finalize(observed_at)
            self._begin(state, normalized_profile, observed_at)
            return

        self._last_observed_at = observed_at
        if observed_at - self._last_checkpoint_at >= self.CHECKPOINT_SECONDS:
            self.checkpoint(timestamp=observed_at)

    def checkpoint(self, *, timestamp: float | None = None) -> None:
        if self._closed or self._active_state is None:
            return
        checkpoint_at = time.time() if timestamp is None else float(timestamp)
        safe_end = min(checkpoint_at, self._last_observed_at + self.OBSERVATION_GRACE_SECONDS)
        self._persist_active_end(safe_end)

    def record_alert(self, profile_name: str, *, timestamp: float | None = None) -> None:
        if self._closed:
            return
        occurred_at = time.time() if timestamp is None else float(timestamp)
        self._connection.execute(
            "INSERT INTO posture_alerts(occurred_at, profile_name) VALUES (?, ?)",
            (occurred_at, profile_name),
        )
        self._connection.commit()

    def summarize(
        self,
        period: str,
        *,
        now: float | None = None,
        timezone_info: tzinfo | None = None,
        anchor_date: date | None = None,
    ) -> StatisticsSummary:
        if period not in self.PERIOD_DAYS:
            raise ValueError(f"未対応の集計期間です: {period}")
        checkpoint_at = time.time() if now is None else float(now)
        self.checkpoint(timestamp=checkpoint_at)
        self._delete_expired_if_due(checkpoint_at)
        current = self._local_datetime(checkpoint_at, timezone_info)
        selected_date = self.clamp_anchor_date(
            period,
            current.date() if anchor_date is None else anchor_date,
            current.date(),
        )
        boundaries, labels = self._timeline_boundaries(
            period,
            checkpoint_at,
            timezone_info,
            anchor_date=selected_date,
        )
        started_at = boundaries[0]
        ended_at = min(checkpoint_at, boundaries[-1])

        rows = self._connection.execute(
            """
            SELECT started_at, ended_at, state, profile_name
            FROM posture_segments
            WHERE ended_at > ? AND started_at < ?
            ORDER BY started_at
            """,
            (started_at, ended_at),
        ).fetchall()

        good_by_bucket = [0.0] * (len(boundaries) - 1)
        bad_by_bucket = [0.0] * (len(boundaries) - 1)
        profile_totals: dict[str, float] = {}
        for segment_start, segment_end, state, profile_name in rows:
            clipped_start = max(float(segment_start), started_at)
            clipped_end = min(float(segment_end), ended_at)
            if clipped_end <= clipped_start or state not in TRACKED_STATES:
                continue
            for index, (bucket_start, bucket_end) in enumerate(zip(boundaries, boundaries[1:])):
                overlap = max(0.0, min(clipped_end, bucket_end) - max(clipped_start, bucket_start))
                if overlap <= 0.0:
                    continue
                if state in GOOD_STATES:
                    good_by_bucket[index] += overlap
                else:
                    bad_by_bucket[index] += overlap
                    name = profile_name or "登録姿勢"
                    profile_totals[name] = profile_totals.get(name, 0.0) + overlap

        alert_count = int(self._connection.execute(
            "SELECT COUNT(*) FROM posture_alerts WHERE occurred_at >= ? AND occurred_at < ?",
            (started_at, ended_at),
        ).fetchone()[0])
        timeline = tuple(
            TimelineBucket(
                label=labels[index],
                good_seconds=good_by_bucket[index],
                bad_seconds=bad_by_bucket[index],
                capacity_seconds=max(1.0, min(boundaries[index + 1], ended_at) - boundaries[index]),
                started_at=boundaries[index],
                ended_at=boundaries[index + 1],
            )
            for index in range(len(labels))
        )
        bad_profiles = tuple(
            ProfileDuration(name=name, seconds=seconds)
            for name, seconds in sorted(profile_totals.items(), key=lambda item: item[1], reverse=True)
        )
        return StatisticsSummary(
            period=period,
            started_at=started_at,
            ended_at=ended_at,
            good_seconds=sum(good_by_bucket),
            bad_seconds=sum(bad_by_bucket),
            alert_count=alert_count,
            timeline=timeline,
            bad_profiles=bad_profiles,
        )

    def close(self, *, timestamp: float | None = None) -> None:
        if self._closed:
            return
        self.checkpoint(timestamp=time.time() if timestamp is None else timestamp)
        self._connection.close()
        self._closed = True

    def _begin(self, state: str, profile_name: str | None, started_at: float) -> None:
        self._active_state = state
        self._active_profile = profile_name
        self._active_started_at = started_at
        self._last_observed_at = started_at
        self._last_checkpoint_at = started_at
        cursor = self._connection.execute(
            """
            INSERT INTO posture_segments(started_at, ended_at, state, profile_name)
            VALUES (?, ?, ?, ?)
            """,
            (started_at, started_at, state, profile_name),
        )
        self._active_segment_id = int(cursor.lastrowid)
        self._connection.commit()

    def _finalize(self, ended_at: float) -> None:
        if self._active_state is None:
            return
        if ended_at > self._active_started_at:
            self._persist_active_end(ended_at)
        elif self._active_segment_id is not None:
            self._connection.execute(
                "DELETE FROM posture_segments WHERE id = ?",
                (self._active_segment_id,),
            )
            self._connection.commit()
        self._active_state = None
        self._active_profile = None
        self._active_segment_id = None

    def _persist_active_end(self, ended_at: float) -> None:
        if self._active_segment_id is None or ended_at <= self._last_checkpoint_at:
            return
        self._connection.execute(
            "UPDATE posture_segments SET ended_at = ? WHERE id = ?",
            (ended_at, self._active_segment_id),
        )
        self._connection.commit()
        self._last_checkpoint_at = ended_at

    def _delete_expired(self, now: float) -> None:
        cutoff = now - (self.RETENTION_DAYS * 86400.0)
        self._connection.execute("DELETE FROM posture_segments WHERE ended_at < ?", (cutoff,))
        self._connection.execute("DELETE FROM posture_alerts WHERE occurred_at < ?", (cutoff,))
        self._connection.commit()

    def _delete_expired_if_due(self, now: float) -> None:
        if now - self._last_cleanup_at < self.CLEANUP_INTERVAL_SECONDS:
            return
        self._delete_expired(now)
        self._last_cleanup_at = now

    @staticmethod
    def _local_datetime(timestamp: float, timezone_info: tzinfo | None) -> datetime:
        if timezone_info is None:
            return datetime.fromtimestamp(timestamp).astimezone()
        return datetime.fromtimestamp(timestamp, tz=timezone_info)

    @classmethod
    def clamp_anchor_date(
        cls,
        period: str,
        anchor_date: date,
        current_date: date,
    ) -> date:
        if period not in cls.PERIOD_DAYS:
            raise ValueError(f"未対応の集計期間です: {period}")
        if isinstance(anchor_date, datetime):
            anchor_date = anchor_date.date()
        period_days = cls.PERIOD_DAYS[period]
        oldest_anchor = current_date - timedelta(
            days=cls.RETENTION_DAYS - period_days
        )
        return min(current_date, max(oldest_anchor, anchor_date))

    @staticmethod
    def _timeline_boundaries(
        period: str,
        now: float,
        timezone_info: tzinfo | None,
        *,
        anchor_date: date | None = None,
    ) -> tuple[list[float], list[str]]:
        current = PostureHistory._local_datetime(now, timezone_info)
        selected_date = current.date() if anchor_date is None else anchor_date
        # A naive local datetime delegates conversion to the operating system,
        # which preserves historical DST rules.  ``astimezone().tzinfo`` is a
        # fixed offset on Windows and would shift past winter/summer anchors.
        midnight = datetime.combine(
            selected_date,
            datetime_time.min,
            tzinfo=None if timezone_info is None else current.tzinfo,
        )
        if period == "day":
            starts = [midnight + timedelta(hours=index) for index in range(25)]
            labels = [f"{index:02d}" for index in range(24)]
        else:
            day_count = 7 if period == "week" else 30
            first_day = midnight - timedelta(days=day_count - 1)
            starts = [first_day + timedelta(days=index) for index in range(day_count + 1)]
            labels = [f"{item.month}/{item.day}" for item in starts[:-1]]
        return [item.timestamp() for item in starts], labels
