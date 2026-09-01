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

from pose_care.history import PostureHistory


logger = logging.getLogger(__name__)


class HistoryService(QObject):
    """Run SQLite history work away from Qt's GUI thread."""

    summaryReady = Signal(int, object)
    historyError = Signal(str)

    STATE_STABILITY_SECONDS = 0.75
    OBSERVATION_SAMPLE_SECONDS = 0.25
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
            maxlen=self.MAX_PENDING_OBSERVATIONS
        )
        self._observation_command_queued = False
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
        observation = (state, normalized_profile, observed_at)
        with self._observation_lock:
            if self._closing.is_set():
                return
            if (
                self._pending_observations
                and self._pending_observations[-1][:2] == observation[:2]
                and observed_at - self._pending_observations[-1][2]
                < self.OBSERVATION_SAMPLE_SECONDS
            ):
                return
            else:
                self._pending_observations.append(observation)
            if not self._observation_command_queued:
                self._observation_command_queued = True
                self._commands.put_nowait(("observations",))

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
        self._commands.put_nowait(("close", closed_at))
        # Give normal shutdown a brief chance to flush, but never let storage
        # or a Windows volume operation make the GUI appear hung.
        self._closed.wait(self.CLOSE_WAIT_SECONDS)

    def _run(self) -> None:
        history = self._open_history()
        persisted_key: tuple[str, str | None] | None = None
        pending_key: tuple[str, str | None] | None = None
        pending_since = 0.0
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
                                break
                            try:
                                (
                                    persisted_key,
                                    pending_key,
                                    pending_since,
                                    last_observed_at,
                                ) = self._apply_observation(
                                    history,
                                    persisted_key,
                                    pending_key,
                                    pending_since,
                                    state,
                                    profile_name,
                                    observed_at,
                                )
                                break
                            except Exception as error:
                                self._report_error("Could not store posture history", error)
                                history = self._reopen_history(history)
                                persisted_key = None
                                pending_key = None
                                pending_since = 0.0
                                last_observed_at = 0.0
                                if attempt == 1:
                                    break
                elif operation == "alert":
                    _, profile_name, occurred_at = command
                    if history is None:
                        history = self._open_history()
                    if history is None:
                        continue
                    try:
                        history.record_alert(profile_name, timestamp=occurred_at)
                    except Exception as error:
                        self._report_error("Could not store posture alert", error)
                        history = self._reopen_history(history)
                        persisted_key = None
                        pending_key = None
                elif operation == "summary":
                    (
                        _,
                        request_id,
                        period,
                        requested_at,
                        timezone_info,
                        anchor_date,
                    ) = command
                    if history is None:
                        history = self._open_history()
                    if history is None:
                        continue
                    try:
                        persisted_key, pending_key = self._flush_pending(
                            history,
                            persisted_key,
                            pending_key,
                            pending_since,
                            last_observed_at,
                        )
                        summary = history.summarize(
                            period,
                            now=requested_at,
                            timezone_info=timezone_info,
                            anchor_date=anchor_date,
                        )
                        if not self._closing.is_set():
                            self.summaryReady.emit(request_id, summary)
                    except Exception as error:
                        self._report_error("Could not summarize posture history", error)
                        history = self._reopen_history(history)
                        persisted_key = None
                        pending_key = None
                elif operation == "close":
                    _, closed_at = command
                    if history is not None:
                        try:
                            self._flush_pending(
                                history,
                                persisted_key,
                                pending_key,
                                pending_since,
                                last_observed_at,
                            )
                            history.close(timestamp=closed_at)
                        except Exception as error:
                            self._report_error("Could not close posture history", error)
                    history = None
                    return
        except Exception as error:
            self._report_error("History worker stopped unexpectedly", error)
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
        return observations

    def _apply_observation(
        self,
        history: PostureHistory,
        persisted_key: tuple[str, str | None] | None,
        pending_key: tuple[str, str | None] | None,
        pending_since: float,
        state: str,
        profile_name: str | None,
        observed_at: float,
    ) -> tuple[
        tuple[str, str | None] | None,
        tuple[str, str | None] | None,
        float,
        float,
    ]:
        key = (state, profile_name)
        if persisted_key is None:
            history.observe(state, profile_name, timestamp=observed_at)
            return key, None, 0.0, observed_at
        if key == persisted_key:
            history.observe(state, profile_name, timestamp=observed_at)
            return persisted_key, None, 0.0, observed_at

        if state == persisted_key[0]:
            if key != pending_key:
                pending_key = key
                pending_since = observed_at
            if observed_at - pending_since >= self.STATE_STABILITY_SECONDS:
                # The posture category is unchanged, so keep it current while
                # only the best-matching profile settles. Attribute the short
                # debounce interval to the previous profile.
                history.observe(state, profile_name, timestamp=observed_at)
                return key, None, 0.0, observed_at
            history.observe(
                persisted_key[0],
                persisted_key[1],
                timestamp=observed_at,
            )
            return persisted_key, pending_key, pending_since, observed_at

        if pending_key is None or state != pending_key[0]:
            pending_since = observed_at
        pending_key = key
        if observed_at - pending_since < self.STATE_STABILITY_SECONDS:
            return persisted_key, pending_key, pending_since, observed_at
        history.observe(state, profile_name, timestamp=pending_since)
        history.observe(state, profile_name, timestamp=observed_at)
        return key, None, 0.0, observed_at

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
            self._report_error("Could not open posture history", error)
        return None

    def _reopen_history(self, history: PostureHistory) -> PostureHistory | None:
        try:
            history.close()
        except Exception:
            logger.exception("Could not close failed posture history connection")
        return self._open_history()

    def _report_error(self, context: str, error: Exception) -> None:
        logger.error(
            "%s: %s",
            context,
            error,
            exc_info=(type(error), error, error.__traceback__),
        )
        if not self._closing.is_set():
            self.historyError.emit(str(error))

    def _flush_pending(
        self,
        history: PostureHistory,
        persisted_key: tuple[str, str | None] | None,
        pending_key: tuple[str, str | None] | None,
        pending_since: float,
        last_observed_at: float,
    ) -> tuple[tuple[str, str | None] | None, tuple[str, str | None] | None]:
        if persisted_key is None or last_observed_at <= 0.0:
            return persisted_key, pending_key
        if (
            pending_key is not None
            and pending_key[0] != persisted_key[0]
            and last_observed_at - pending_since >= self.STATE_STABILITY_SECONDS
        ):
            history.observe(
                pending_key[0],
                pending_key[1],
                timestamp=pending_since,
            )
            history.observe(
                pending_key[0],
                pending_key[1],
                timestamp=last_observed_at,
            )
            return pending_key, None
        history.observe(
            persisted_key[0],
            persisted_key[1],
            timestamp=last_observed_at,
        )
        return persisted_key, pending_key
