from __future__ import annotations

import logging
import queue
import threading
import time
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
        self._commands.put_nowait(("observe", state, profile_name, observed_at))

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
        history: PostureHistory | None = None
        persisted_key: tuple[str, str | None] | None = None
        pending_key: tuple[str, str | None] | None = None
        pending_since = 0.0
        last_observed_at = 0.0
        try:
            history = self._history_factory(self.path)
            while True:
                command = self._commands.get()
                operation = command[0]
                if operation == "observe":
                    _, state, profile_name, observed_at = command
                    key = (state, profile_name)
                    last_observed_at = observed_at
                    if persisted_key is None:
                        history.observe(state, profile_name, timestamp=observed_at)
                        persisted_key = key
                        continue
                    if key == persisted_key:
                        pending_key = None
                        history.observe(state, profile_name, timestamp=observed_at)
                        continue
                    if key != pending_key:
                        pending_key = key
                        pending_since = observed_at
                        continue
                    if observed_at - pending_since < self.STATE_STABILITY_SECONDS:
                        continue
                    history.observe(
                        pending_key[0],
                        pending_key[1],
                        timestamp=pending_since,
                    )
                    history.observe(state, profile_name, timestamp=observed_at)
                    persisted_key = pending_key
                    pending_key = None
                elif operation == "alert":
                    _, profile_name, occurred_at = command
                    history.record_alert(profile_name, timestamp=occurred_at)
                elif operation == "summary":
                    (
                        _,
                        request_id,
                        period,
                        requested_at,
                        timezone_info,
                        anchor_date,
                    ) = command
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
                elif operation == "close":
                    _, closed_at = command
                    persisted_key, pending_key = self._flush_pending(
                        history,
                        persisted_key,
                        pending_key,
                        pending_since,
                        last_observed_at,
                    )
                    history.close(timestamp=closed_at)
                    history = None
                    return
        except Exception as error:
            logger.exception("History worker failed")
            if not self._closing.is_set():
                self.historyError.emit(str(error))
        finally:
            if history is not None:
                try:
                    history.close()
                except Exception:
                    logger.exception("Could not close history after worker failure")
            self._closing.set()
            self._closed.set()

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
