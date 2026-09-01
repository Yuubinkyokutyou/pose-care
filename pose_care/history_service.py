from __future__ import annotations

import logging
import queue
import threading
import time
from collections import deque
from collections.abc import Callable
from datetime import date, tzinfo
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Signal

from pose_care.history import BAD_STATES, GOOD_STATES, PostureHistory


logger = logging.getLogger(__name__)


class HistoryService(QObject):
    """Run SQLite history work away from Qt's GUI thread."""

    summaryReady = Signal(int, object)
    historyError = Signal(str, bool)

    STATE_STABILITY_SECONDS = 0.75
    OBSERVATION_SAMPLE_SECONDS = 5.0
    MAX_PENDING_OBSERVATIONS = 256
    CLOSE_WAIT_SECONDS = 0.25

    def __init__(
        self,
        path: Path,
        parent: QObject | None = None,
        *,
        history_factory: Callable[[Path], PostureHistory] = PostureHistory,
    ) -> None:
        super().__init__(parent)
        self.path = path
        self._history_factory = history_factory
        self._commands: queue.Queue[tuple[Any, ...]] = queue.Queue()
        self._observation_lock = threading.Lock()
        self._pending_observations: deque[tuple[str, str | None, float]] = deque(
        )
        self._observation_command_queued = False
        self._producer_key: tuple[str, str | None] | None = None
        self._producer_pending_key: tuple[str, str | None] | None = None
        self._producer_pending_since = 0.0
        self._producer_profile_key: tuple[str, str | None] | None = None
        self._producer_profile_since = 0.0
        self._producer_latest_observed_at = 0.0
        self._observation_overflow_reported = False
        self._closing = threading.Event()
        self._closed = threading.Event()
        self._request_lock = threading.Lock()
        self._next_request_id = 0
        self._thread = threading.Thread(
            target=self._run,
            name="PoseCare history",
            daemon=True,
        )
        self._thread.start()

    def observe(
        self,
        state: str,
        profile_name: str | None = None,
        *,
        timestamp: float | None = None,
    ) -> None:
        if self._closing.is_set():
            return
        observed_at = time.time() if timestamp is None else float(timestamp)
        normalized_profile = (
            profile_name if state in ("normal", "warning", "bad") else None
        )
        key = (state, normalized_profile)
        overflowed = False
        with self._observation_lock:
            if self._closing.is_set():
                return
            self._producer_latest_observed_at = observed_at
            if self._producer_key is None:
                self._producer_key = key
                overflowed = self._buffer_observation(key, observed_at, force=True)
            elif self._state_category(state) != self._state_category(
                self._producer_key[0]
            ):
                category = self._state_category(state)
                if (
                    self._producer_pending_key is None
                    or self._state_category(self._producer_pending_key[0]) != category
                ):
                    self._producer_pending_since = observed_at
                self._producer_pending_key = key
                self._producer_profile_key = None
                if (
                    observed_at - self._producer_pending_since
                    >= self.STATE_STABILITY_SECONDS
                ):
                    self._producer_key = key
                    overflowed = self._buffer_observation(
                        key,
                        self._producer_pending_since,
                        force=True,
                    )
                    overflowed = self._buffer_observation(
                        key,
                        observed_at,
                        force=True,
                    ) or overflowed
                    self._producer_pending_key = None
                    self._producer_pending_since = 0.0
                else:
                    overflowed = self._buffer_observation(
                        self._producer_key,
                        observed_at,
                    )
            else:
                self._producer_pending_key = None
                self._producer_pending_since = 0.0
                if key == self._producer_key:
                    self._producer_profile_key = None
                    self._producer_profile_since = 0.0
                else:
                    if key != self._producer_profile_key:
                        self._producer_profile_key = key
                        self._producer_profile_since = observed_at
                    elif (
                        observed_at - self._producer_profile_since
                        >= self.STATE_STABILITY_SECONDS
                    ):
                        profile_started_at = self._producer_profile_since
                        self._producer_key = key
                        self._producer_profile_key = None
                        self._producer_profile_since = 0.0
                        overflowed = self._buffer_observation(
                            key,
                            profile_started_at,
                            force=True,
                        )
                        overflowed = self._buffer_observation(
                            key,
                            observed_at,
                            force=True,
                        ) or overflowed
                overflowed = self._buffer_observation(
                    self._producer_key,
                    observed_at,
                ) or overflowed
        if overflowed:
            self._report_error(
                "History observation buffer overflowed",
                RuntimeError("一部の姿勢履歴を保存できませんでした"),
                data_lost=True,
            )

    def record_alert(
        self,
        profile_name: str,
        *,
        timestamp: float | None = None,
    ) -> None:
        if self._closing.is_set():
            return
        occurred_at = time.time() if timestamp is None else float(timestamp)
        self._commands.put_nowait(("alert", profile_name, occurred_at))

    def request_summary(
        self,
        period: str,
        *,
        now: float | None = None,
        timezone_info: tzinfo | None = None,
        anchor_date: date | None = None,
    ) -> int:
        with self._request_lock:
            self._next_request_id += 1
            request_id = self._next_request_id
        if self._closing.is_set():
            return request_id
        requested_at = time.time() if now is None else float(now)
        overflowed = self._force_latest_observation()
        if overflowed:
            self._report_error(
                "History observation buffer overflowed",
                RuntimeError("一部の姿勢履歴を保存できませんでした"),
                data_lost=True,
            )
        self._commands.put_nowait(
            (
                "summary",
                request_id,
                period,
                requested_at,
                timezone_info,
                anchor_date,
            )
        )
        return request_id

    def close(self, *, timestamp: float | None = None) -> None:
        if self._closing.is_set():
            return
        self._closing.set()
        closed_at = time.time() if timestamp is None else float(timestamp)
        overflowed = self._force_latest_observation()
        if overflowed:
            self._report_error(
                "History observation buffer overflowed",
                RuntimeError("一部の姿勢履歴を保存できませんでした"),
                data_lost=True,
            )
        self._commands.put_nowait(("close", closed_at))
        # Give normal shutdown a brief chance to flush, but never let storage
        # or a Windows volume operation make the GUI appear hung.
        self._closed.wait(self.CLOSE_WAIT_SECONDS)

    def _run(self) -> None:
        history = self._open_history()
        last_observed_at = 0.0
        try:
            while True:
                command = self._commands.get()
                operation = command[0]
                if operation == "observations":
                    for state, profile_name, observed_at in self._take_observations():
                        for attempt in range(2):
                            if history is None:
                                history = self._open_history()
                            if history is None:
                                if attempt == 1:
                                    self._report_error(
                                        "Could not store posture history",
                                        RuntimeError("履歴データベースを開けませんでした"),
                                        data_lost=True,
                                    )
                                continue
                            try:
                                history.observe(
                                    state,
                                    profile_name,
                                    timestamp=observed_at,
                                )
                                last_observed_at = observed_at
                                break
                            except Exception as error:
                                self._log_error("Could not store posture history", error)
                                history = self._reopen_history(
                                    history,
                                    last_observed_at,
                                )
                                if attempt == 1:
                                    self._report_error(
                                        "Posture history observation was lost",
                                        error,
                                        data_lost=True,
                                    )
                elif operation == "alert":
                    _, profile_name, occurred_at = command
                    for attempt in range(2):
                        if history is None:
                            history = self._open_history()
                        if history is None:
                            if attempt == 1:
                                self._report_error(
                                    "Posture alert was lost",
                                    RuntimeError("履歴データベースを開けませんでした"),
                                    data_lost=True,
                                )
                            continue
                        try:
                            history.record_alert(profile_name, timestamp=occurred_at)
                            break
                        except Exception as error:
                            self._log_error("Could not store posture alert", error)
                            history = self._reopen_history(history, last_observed_at)
                            if attempt == 1:
                                self._report_error(
                                    "Posture alert was lost",
                                    error,
                                    data_lost=True,
                                )
                elif operation == "summary":
                    (
                        _,
                        request_id,
                        period,
                        requested_at,
                        timezone_info,
                        anchor_date,
                    ) = command
                    for attempt in range(2):
                        if history is None:
                            history = self._open_history()
                        if history is None:
                            continue
                        try:
                            summary = history.summarize(
                                period,
                                now=requested_at,
                                timezone_info=timezone_info,
                                anchor_date=anchor_date,
                            )
                            if not self._closing.is_set():
                                self.summaryReady.emit(request_id, summary)
                            break
                        except Exception as error:
                            self._log_error("Could not summarize posture history", error)
                            history = self._reopen_history(history, last_observed_at)
                            if attempt == 1:
                                self._report_error(
                                    "Could not summarize posture history",
                                    error,
                                    data_lost=False,
                                )
                elif operation == "close":
                    _, closed_at = command
                    if history is not None:
                        try:
                            history.close(timestamp=closed_at)
                        except Exception as error:
                            self._report_error(
                                "Could not close posture history",
                                error,
                                data_lost=True,
                            )
                    history = None
                    return
        except Exception as error:
            self._report_error(
                "History worker stopped unexpectedly",
                error,
                data_lost=True,
            )
        finally:
            if history is not None:
                try:
                    history.close()
                except Exception:
                    logger.exception("Could not close history after worker failure")
            self._closing.set()
            self._closed.set()

    def _take_observations(self) -> list[tuple[str, str | None, float]]:
        with self._observation_lock:
            observations = list(self._pending_observations)
            self._pending_observations.clear()
            self._observation_command_queued = False
            self._observation_overflow_reported = False
        return observations

    def _force_latest_observation(self) -> bool:
        with self._observation_lock:
            if self._producer_key is None or self._producer_latest_observed_at <= 0.0:
                return False
            return self._buffer_observation(
                self._producer_key,
                self._producer_latest_observed_at,
                force=True,
            )

    def _buffer_observation(
        self,
        key: tuple[str, str | None],
        observed_at: float,
        *,
        force: bool = False,
    ) -> bool:
        if (
            not force
            and self._pending_observations
            and self._pending_observations[-1][:2] == key
            and observed_at - self._pending_observations[-1][2]
            < self.OBSERVATION_SAMPLE_SECONDS
        ):
            return False
        overflowed = False
        if len(self._pending_observations) >= self.MAX_PENDING_OBSERVATIONS:
            self._pending_observations.popleft()
            if not self._observation_overflow_reported:
                self._observation_overflow_reported = True
                overflowed = True
        self._pending_observations.append((key[0], key[1], observed_at))
        if not self._observation_command_queued:
            self._observation_command_queued = True
            self._commands.put_nowait(("observations",))
        return overflowed

    @staticmethod
    def _state_category(state: str) -> str:
        if state in GOOD_STATES:
            return "good"
        if state in BAD_STATES:
            return "bad"
        return state

    def _open_history(self) -> PostureHistory | None:
        error: Exception | None = None
        for delay in (0.0, 0.1):
            if delay:
                time.sleep(delay)
            try:
                return self._history_factory(self.path)
            except Exception as current_error:
                error = current_error
        if error is not None:
            self._log_error("Could not open posture history", error)
        return None

    def _reopen_history(
        self,
        history: PostureHistory,
        last_observed_at: float,
    ) -> PostureHistory | None:
        try:
            if last_observed_at > 0.0:
                history.close(timestamp=last_observed_at)
            else:
                history.close()
        except Exception:
            logger.exception("Could not close failed posture history connection")
        return self._open_history()

    @staticmethod
    def _log_error(context: str, error: Exception) -> None:
        logger.error(
            "%s: %s",
            context,
            error,
            exc_info=(type(error), error, error.__traceback__),
        )

    def _report_error(
        self,
        context: str,
        error: Exception,
        *,
        data_lost: bool,
    ) -> None:
        self._log_error(context, error)
        if not self._closing.is_set() or data_lost:
            self.historyError.emit(str(error), data_lost)
