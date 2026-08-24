from __future__ import annotations

import ctypes
import logging
import sys
import threading
import time
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import (
    Property,
    QCoreApplication,
    QElapsedTimer,
    QObject,
    QTimer,
    Qt,
    Signal,
    Slot,
)
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from pose_care.camera import CameraWorker
from pose_care.config import SettingsStore, history_path, model_path
from pose_care.history import PostureHistory
from pose_care.models import (
    POSTURE_FEATURE_VERSION,
    AppSettings,
    DetectionState,
    PoseFeature,
    PostureProfile,
)
from pose_care.notifications import WindowsNotifier
from pose_care.posture import PostureDetector, aggregate_features
from pose_care.ui.image_provider import CameraImageProvider
from pose_care.updater import (
    ApplicationUpdater,
    PreparedUpdate,
    UpdateCheck,
    UpdateError,
    UpdateProgress,
)


logger = logging.getLogger(__name__)


_UPDATE_PROGRESS_RANGES: dict[str, tuple[float, float]] = {
    "downloading_checksum": (0.0, 0.05),
    "downloading": (0.05, 0.82),
    "verifying": (0.82, 0.90),
    "extracting": (0.90, 1.0),
    "ready": (1.0, 1.0),
}


CAMERA_IDLE_TIMEOUT_SECONDS = 5 * 60.0
CAMERA_ACTIVITY_POLL_INTERVAL_MS = 1_000


class _LastInputInfo(ctypes.Structure):
    _fields_ = (("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint))


def _seconds_since_last_user_input() -> float:
    """Return the Windows-wide keyboard/mouse idle time."""
    if sys.platform != "win32":
        return 0.0
    try:
        info = _LastInputInfo()
        info.cbSize = ctypes.sizeof(info)
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
            return 0.0
        current_tick = ctypes.c_uint32(ctypes.windll.kernel32.GetTickCount()).value
        elapsed_ms = (current_tick - info.dwTime) & 0xFFFFFFFF
        return elapsed_ms / 1_000.0
    except (AttributeError, OSError, TypeError, ValueError):
        # Keep the camera running when the OS activity state cannot be read.
        return 0.0


def _restore_native_window(window: Any) -> None:
    if sys.platform != "win32":
        return
    try:
        handle = int(window.winId())
        ctypes.windll.user32.ShowWindow(handle, 9)  # SW_RESTORE
        ctypes.windll.user32.SetForegroundWindow(handle)
    except (AttributeError, OSError, TypeError, ValueError):
        pass


class PoseCareController(QObject):
    """Application state and commands exposed to the Qt Quick view."""

    uiChanged = Signal()
    frameChanged = Signal()
    profilesChanged = Signal()
    settingsChanged = Signal()
    statisticsChanged = Signal()
    registrationChanged = Signal()
    feedbackChanged = Signal()
    updateChanged = Signal()
    navigateRequested = Signal(int)
    notificationActivated = Signal()
    _updateTaskFinished = Signal(str, object)
    _updateTaskFailed = Signal(str, str)
    _updateProgressReported = Signal(object)

    def __init__(
        self,
        store: SettingsStore,
        settings: AppSettings,
        icon: QIcon,
        image_provider: CameraImageProvider,
        parent: QObject | None = None,
        *,
        history: PostureHistory | None = None,
        notifier: WindowsNotifier | None = None,
        idle_seconds_provider: Callable[[], float] | None = None,
        updater: ApplicationUpdater | None = None,
    ) -> None:
        super().__init__(parent)
        self.store = store
        self.settings = settings
        self.icon = icon
        self.image_provider = image_provider
        self.notificationActivated.connect(self.show_from_tray)
        self.detector = PostureDetector()
        self.notifier = notifier or WindowsNotifier()
        self._idle_seconds_provider = idle_seconds_provider or _seconds_since_last_user_input
        self.history = history or PostureHistory(history_path())
        self.updater = updater or ApplicationUpdater()
        self.camera_worker: CameraWorker | None = None
        self.latest_feature: PoseFeature | None = None
        self.latest_landmarks: list[Any] = []
        self._window: Any | None = None
        self._monitoring = True
        self._camera_suspended_for_idle = False
        self._last_person_seen_at = time.monotonic()
        self._idle_camera_timeout_seconds = CAMERA_IDLE_TIMEOUT_SECONDS
        self._quitting = False
        self._history_closed = False
        self._first_run_prompted = False
        self._tray_hint_shown = False
        self._frame_serial = 0
        self._camera_status = "起動しています"
        self._camera_error_text = ""
        self._fps_text = "解析 — fps"
        self._state_kind = "starting"
        self._state_title = "準備しています"
        self._state_detail = "カメラと姿勢モデルを起動しています"
        self._state_progress = 0.0
        self._metrics = self._empty_metrics()
        self._statistics_period = "day"
        self._statistics_cards: list[dict[str, str]] = []
        self._timeline: list[dict[str, Any]] = []
        self._breakdown: list[dict[str, Any]] = []
        self._statistics_note = "時間ごとの監視結果"
        self._statistics_updated = "判定結果をこのPC内で集計します"
        self._save_feedback = ""
        self._notification_feedback = ""
        self._latest_version = ""
        self._update_state = "idle"
        self._update_status = ""
        self._update_progress = 0.0
        self._update_check: UpdateCheck | None = None
        self._prepared_update: PreparedUpdate | None = None
        self._update_thread: threading.Thread | None = None
        self._update_shutdown = threading.Event()
        self._registration_open = False
        self._registration_type = "bad"
        self._registration_first_run = False
        self._registration_capturing = False
        self._registration_progress = 0
        self._registration_status = "準備できたら登録を開始してください"
        self._registration_name = ""
        self._registration_samples: list[PoseFeature] = []
        self._registration_last_sample: PoseFeature | None = None
        self._registration_elapsed = QElapsedTimer()
        self._registration_timer = QTimer(self)
        self._registration_timer.setInterval(70)
        self._registration_timer.timeout.connect(self._registration_tick)

        self._updateTaskFinished.connect(self._on_update_task_finished)
        self._updateTaskFailed.connect(self._on_update_task_failed)
        self._updateProgressReported.connect(self._on_update_progress)

        self._statistics_timer = QTimer(self)
        self._statistics_timer.setInterval(60_000)
        self._statistics_timer.timeout.connect(self.refreshStatistics)
        self._statistics_timer.start()
        self._camera_activity_timer = QTimer(self)
        self._camera_activity_timer.setInterval(CAMERA_ACTIVITY_POLL_INTERVAL_MS)
        self._camera_activity_timer.timeout.connect(self._check_camera_activity)
        self._build_tray()
        self._refresh_statistics()

    def start(self) -> None:
        self._last_person_seen_at = time.monotonic()
        self._camera_activity_timer.start()
        self._start_camera()

    def attach_window(self, window: Any) -> None:
        self._window = window

    def show_initial_window(self) -> None:
        if self._window is None:
            return
        if (
            self.settings.start_minimized
            and self.settings.first_run_complete
            and self.tray.isVisible()
        ):
            self._window.hide()
        else:
            self.show_from_tray()

    @staticmethod
    def _empty_metrics() -> dict[str, str]:
        return {
            "headSide": "—",
            "shoulderTilt": "—",
            "shoulderDepth": "—",
            "headForward": "—",
        }

    @staticmethod
    def _format_metric(value: float | None, suffix: str = "") -> str:
        return "—" if value is None else f"{value:+.1f}{suffix}"

    @staticmethod
    def _format_duration(seconds: float) -> str:
        total_minutes = int(seconds / 60.0)
        if total_minutes >= 60:
            hours, minutes = divmod(total_minutes, 60)
            return f"{hours}時間{minutes:02d}分"
        if total_minutes >= 1:
            return f"{total_minutes}分"
        return f"{int(seconds)}秒"

    def _get_camera_frame_source(self) -> str:
        return f"image://camera/frame/{self._frame_serial}"

    cameraFrameSource = Property(str, _get_camera_frame_source, notify=frameChanged)

    def _get_camera_status(self) -> str:
        return self._camera_status

    cameraStatus = Property(str, _get_camera_status, notify=uiChanged)

    def _get_camera_error_text(self) -> str:
        return self._camera_error_text

    cameraErrorText = Property(str, _get_camera_error_text, notify=uiChanged)

    def _get_fps_text(self) -> str:
        return self._fps_text

    fpsText = Property(str, _get_fps_text, notify=uiChanged)

    def _get_monitoring(self) -> bool:
        return self._monitoring

    monitoring = Property(bool, _get_monitoring, notify=uiChanged)

    def _get_state_kind(self) -> str:
        return self._state_kind

    stateKind = Property(str, _get_state_kind, notify=uiChanged)

    def _get_state_title(self) -> str:
        return self._state_title

    stateTitle = Property(str, _get_state_title, notify=uiChanged)

    def _get_state_detail(self) -> str:
        return self._state_detail

    stateDetail = Property(str, _get_state_detail, notify=uiChanged)

    def _get_state_progress(self) -> float:
        return self._state_progress

    stateProgress = Property(float, _get_state_progress, notify=uiChanged)

    def _get_metrics(self) -> dict[str, str]:
        return self._metrics

    metrics = Property("QVariantMap", _get_metrics, notify=uiChanged)

    def _get_bad_profiles(self) -> list[dict[str, str]]:
        return self._profiles_for("bad")

    badProfiles = Property("QVariantList", _get_bad_profiles, notify=profilesChanged)

    def _get_normal_profiles(self) -> list[dict[str, str]]:
        return self._profiles_for("normal")

    normalProfiles = Property("QVariantList", _get_normal_profiles, notify=profilesChanged)

    def _profiles_for(self, posture_type: str) -> list[dict[str, str]]:
        profiles: list[dict[str, str]] = []
        for profile in self.settings.profiles:
            if profile.posture_type != posture_type:
                continue
            label = "正常姿勢・通知から除外" if posture_type == "normal" else "悪い姿勢・通知対象"
            if profile.feature_version == POSTURE_FEATURE_VERSION:
                detail = f"{label}　上半身・{profile.sample_count}サンプルから登録"
            else:
                detail = f"{label}　旧方式です。上半身方式で再登録してください"
            profiles.append({"id": profile.id, "name": profile.name, "detail": detail})
        return profiles

    def _get_sensitivity(self) -> int:
        return self.settings.sensitivity

    sensitivity = Property(int, _get_sensitivity, notify=settingsChanged)

    def _get_hold_seconds(self) -> float:
        return self.settings.hold_seconds

    holdSeconds = Property(float, _get_hold_seconds, notify=settingsChanged)

    def _get_cooldown_minutes(self) -> int:
        return self.settings.cooldown_minutes

    cooldownMinutes = Property(int, _get_cooldown_minutes, notify=settingsChanged)

    def _get_notifications_enabled(self) -> bool:
        return self.settings.notifications_enabled

    notificationsEnabled = Property(bool, _get_notifications_enabled, notify=settingsChanged)

    def _get_camera_index(self) -> int:
        return self.settings.camera_index

    cameraIndex = Property(int, _get_camera_index, notify=settingsChanged)

    def _get_start_minimized(self) -> bool:
        return self.settings.start_minimized

    startMinimized = Property(bool, _get_start_minimized, notify=settingsChanged)

    def _get_statistics_period(self) -> str:
        return self._statistics_period

    statisticsPeriod = Property(str, _get_statistics_period, notify=statisticsChanged)

    def _get_statistics_cards(self) -> list[dict[str, str]]:
        return self._statistics_cards

    statisticsCards = Property("QVariantList", _get_statistics_cards, notify=statisticsChanged)

    def _get_timeline(self) -> list[dict[str, Any]]:
        return self._timeline

    timeline = Property("QVariantList", _get_timeline, notify=statisticsChanged)

    def _get_breakdown(self) -> list[dict[str, Any]]:
        return self._breakdown

    breakdown = Property("QVariantList", _get_breakdown, notify=statisticsChanged)

    def _get_statistics_note(self) -> str:
        return self._statistics_note

    statisticsNote = Property(str, _get_statistics_note, notify=statisticsChanged)

    def _get_statistics_updated(self) -> str:
        return self._statistics_updated

    statisticsUpdated = Property(str, _get_statistics_updated, notify=statisticsChanged)

    def _get_save_feedback(self) -> str:
        return self._save_feedback

    saveFeedback = Property(str, _get_save_feedback, notify=feedbackChanged)

    def _get_notification_feedback(self) -> str:
        return self._notification_feedback

    notificationFeedback = Property(str, _get_notification_feedback, notify=feedbackChanged)

    def _get_app_version(self) -> str:
        return self.updater.current_build.tag

    appVersion = Property(str, _get_app_version, notify=updateChanged)

    def _get_latest_version(self) -> str:
        return self._latest_version

    latestVersion = Property(str, _get_latest_version, notify=updateChanged)

    def _get_update_state(self) -> str:
        return self._update_state

    updateState = Property(str, _get_update_state, notify=updateChanged)

    def _get_update_status(self) -> str:
        return self._update_status

    updateStatus = Property(str, _get_update_status, notify=updateChanged)

    def _get_update_progress(self) -> float:
        return self._update_progress

    updateProgress = Property(float, _get_update_progress, notify=updateChanged)

    def _get_registration_open(self) -> bool:
        return self._registration_open

    registrationOpen = Property(bool, _get_registration_open, notify=registrationChanged)

    def _get_registration_type(self) -> str:
        return self._registration_type

    registrationType = Property(str, _get_registration_type, notify=registrationChanged)

    def _get_registration_first_run(self) -> bool:
        return self._registration_first_run

    registrationFirstRun = Property(bool, _get_registration_first_run, notify=registrationChanged)

    def _get_registration_capturing(self) -> bool:
        return self._registration_capturing

    registrationCapturing = Property(bool, _get_registration_capturing, notify=registrationChanged)

    def _get_registration_progress(self) -> int:
        return self._registration_progress

    registrationProgress = Property(int, _get_registration_progress, notify=registrationChanged)

    def _get_registration_status(self) -> str:
        return self._registration_status

    registrationStatus = Property(str, _get_registration_status, notify=registrationChanged)

    @Slot(bool)
    def toggleMonitoring(self, enabled: bool) -> None:
        self._monitoring = enabled
        self.pause_action.setText("監視を一時停止" if enabled else "監視を再開")
        self.detector.reset(clear_alerts=enabled)
        if not enabled:
            self._set_detection_state(DetectionState(kind="paused"))
        else:
            self.uiChanged.emit()

    @Slot(str)
    def setStatisticsPeriod(self, period: str) -> None:
        if period not in {"day", "week", "month"}:
            return
        self._statistics_period = period
        self._refresh_statistics()

    @Slot()
    def refreshStatistics(self) -> None:
        self._refresh_statistics()

    def _refresh_statistics(self) -> None:
        summary = self.history.summarize(self._statistics_period)
        ratio = "—" if summary.good_ratio is None else f"{summary.good_ratio * 100:.0f}%"
        self._statistics_cards = [
            {
                "label": "良好率",
                "value": ratio,
                "detail": f"良好 {self._format_duration(summary.good_seconds)}",
                "tone": "signal",
            },
            {
                "label": "監視できた時間",
                "value": self._format_duration(summary.monitored_seconds),
                "detail": "姿勢を判定できた時間",
                "tone": "blue",
            },
            {
                "label": "悪い姿勢",
                "value": self._format_duration(summary.bad_seconds),
                "detail": "確認中の時間も含みます",
                "tone": "danger",
            },
            {
                "label": "姿勢通知",
                "value": f"{summary.alert_count}回",
                "detail": "実際に送った姿勢通知",
                "tone": "amber",
            },
        ]
        self._timeline = [
            {
                "label": bucket.label,
                "good": bucket.good_seconds,
                "bad": bucket.bad_seconds,
                "capacity": bucket.capacity_seconds,
            }
            for bucket in summary.timeline
        ]
        maximum = max((item.seconds for item in summary.bad_profiles[:5]), default=1.0)
        self._breakdown = [
            {
                "name": item.name,
                "value": self._format_duration(item.seconds),
                "ratio": item.seconds / maximum,
            }
            for item in summary.bad_profiles[:5]
        ]
        self._statistics_note = (
            "時間ごとの監視結果" if summary.period == "day" else "日ごとの監視結果"
        )
        self._statistics_updated = (
            f"最終更新 {time.strftime('%H:%M')}　映像・骨格は保存しません"
        )
        self.statisticsChanged.emit()

    @Slot(int, float, int, bool, int, bool)
    def saveSettings(
        self,
        sensitivity: int,
        hold_seconds: float,
        cooldown_minutes: int,
        notifications_enabled: bool,
        camera_index: int,
        start_minimized: bool,
    ) -> None:
        old_camera_index = self.settings.camera_index
        self.settings.sensitivity = max(0, min(100, int(sensitivity)))
        self.settings.hold_seconds = max(1.0, min(30.0, float(hold_seconds)))
        self.settings.cooldown_minutes = max(1, min(120, int(cooldown_minutes)))
        self.settings.notifications_enabled = bool(notifications_enabled)
        self.settings.camera_index = max(0, min(9, int(camera_index)))
        self.settings.start_minimized = bool(start_minimized)
        self.store.save(self.settings)
        self.detector.reset(clear_alerts=True)
        self._save_feedback = "保存しました"
        self.settingsChanged.emit()
        self.feedbackChanged.emit()
        QTimer.singleShot(2400, self._clear_save_feedback)
        if old_camera_index != self.settings.camera_index:
            self._restart_camera()

    def _clear_save_feedback(self) -> None:
        self._save_feedback = ""
        self.feedbackChanged.emit()

    @Slot(str, bool)
    def beginRegistration(self, posture_type: str, first_run: bool = False) -> None:
        self._registration_type = "normal" if posture_type == "normal" else "bad"
        self._registration_first_run = bool(first_run)
        self._registration_open = True
        self._registration_capturing = False
        self._registration_progress = 0
        self._registration_status = "準備できたら登録を開始してください"
        self._registration_samples.clear()
        self.registrationChanged.emit()

    @Slot(str)
    def startRegistration(self, name: str) -> None:
        normalized_name = name.strip()
        if not normalized_name:
            self._registration_status = "姿勢の名前を入力してください"
            self.registrationChanged.emit()
            return
        if self.latest_feature is None:
            self._registration_status = "姿勢を認識できません。頭と両肩をカメラに入れてください"
            self.registrationChanged.emit()
            return
        self._registration_name = normalized_name[:30]
        self._registration_samples.clear()
        self._registration_last_sample = None
        self._registration_capturing = True
        self._registration_progress = 0
        self._registration_status = "その姿勢のまま、動かずに保ってください"
        self._registration_elapsed.start()
        self._registration_timer.start()
        self.registrationChanged.emit()

    @Slot()
    def cancelRegistration(self) -> None:
        self._registration_timer.stop()
        self._registration_open = False
        self._registration_capturing = False
        self.registrationChanged.emit()

    def _registration_tick(self) -> None:
        elapsed_ms = self._registration_elapsed.elapsed()
        self._registration_progress = min(100, int(elapsed_ms / 30))
        feature = self.latest_feature
        if feature is not None and feature is not self._registration_last_sample:
            self._registration_samples.append(feature)
            self._registration_last_sample = feature
        if elapsed_ms < 3000:
            self.registrationChanged.emit()
            return
        self._registration_timer.stop()
        self._registration_capturing = False
        if len(self._registration_samples) < 15:
            self._registration_status = (
                "十分に認識できませんでした。姿勢と明るさを整えて再試行してください"
            )
            self._registration_progress = 0
            self.registrationChanged.emit()
            return
        aggregate = aggregate_features(self._registration_samples)
        profile = PostureProfile.create(
            self._registration_name,
            list(aggregate),
            len(self._registration_samples),
            posture_type=self._registration_type,
        )
        self.settings.profiles.append(profile)
        self.settings.first_run_complete = True
        self.store.save(self.settings)
        self.detector.reset(clear_alerts=True)
        self._registration_status = f"「{profile.name}」を登録しました"
        self._registration_progress = 100
        self.profilesChanged.emit()
        self.settingsChanged.emit()
        self.registrationChanged.emit()
        QTimer.singleShot(450, self._finish_registration)

    def _finish_registration(self) -> None:
        self._registration_open = False
        self.registrationChanged.emit()
        self.navigateRequested.emit(0)

    @Slot(str)
    def deleteProfile(self, profile_id: str) -> None:
        original_count = len(self.settings.profiles)
        self.settings.profiles = [
            profile for profile in self.settings.profiles if profile.id != profile_id
        ]
        if len(self.settings.profiles) == original_count:
            return
        self.store.save(self.settings)
        self.detector.reset(clear_alerts=True)
        self.profilesChanged.emit()

    @Slot()
    def sendTestNotification(self) -> None:
        title = "PoseCare テスト通知"
        message = "通知は正常です。悪い姿勢が続いたときも、この形式でお知らせします。"
        if self.notifier.send(title, message):
            self._notification_feedback = "ネイティブWindows通知を送信しました"
        elif self.tray.isVisible():
            self.tray.showMessage(
                title,
                message,
                QSystemTrayIcon.MessageIcon.Information,
                6000,
            )
            self._notification_feedback = "タスクトレイ通知へ切り替えて送信しました"
        else:
            self._notification_feedback = "通知を送信できませんでした"
        self.feedbackChanged.emit()
        QTimer.singleShot(4000, self._clear_notification_feedback)

    def _clear_notification_feedback(self) -> None:
        self._notification_feedback = ""
        self.feedbackChanged.emit()

    @Slot()
    def checkForUpdates(self) -> None:
        if self._update_task_is_running():
            return
        self._discard_prepared_update()
        self._update_check = None
        self._latest_version = ""
        self._update_state = "checking"
        self._update_status = "GitHub Releasesを確認しています"
        self._update_progress = 0.0
        self.updateChanged.emit()
        self._start_update_task(
            "check",
            lambda progress: self.updater.check_for_update(progress),
        )

    @Slot()
    def installUpdate(self) -> None:
        if self._update_task_is_running():
            return
        if self._update_state == "available" and self._update_check is not None:
            if not self.updater.can_apply_update:
                self._update_state = "error"
                self._update_status = (
                    "自動更新はWindows向けにビルドされたPoseCare.exeでのみ実行できます"
                )
                self.updateChanged.emit()
                return
            release = self._update_check.latest
            self._update_state = "downloading"
            self._update_status = "更新ファイルをダウンロードしています"
            self._update_progress = 0.0
            self.updateChanged.emit()
            self._start_update_task(
                "prepare",
                lambda progress: self.updater.prepare_update(release, progress),
            )
            return
        if self._update_state != "ready" or self._prepared_update is None:
            self.checkForUpdates()
            return

        try:
            self.updater.launch_update(
                self._prepared_update,
                self._on_update_progress,
            )
        except UpdateError as error:
            self._update_state = "error"
            self._update_status = str(error)
            self.updateChanged.emit()
            return
        except Exception:
            logger.exception("Unexpected failure while launching the update helper")
            self._update_state = "error"
            self._update_status = "更新プログラムを起動できませんでした"
            self.updateChanged.emit()
            return

        # Ownership of the workspace has moved to the detached helper.  The
        # normal shutdown path must not remove it while the helper is waiting.
        self._prepared_update = None
        self._update_status = "PoseCareを終了して更新を適用します"
        self.updateChanged.emit()
        self.quitApplication()

    def _update_task_is_running(self) -> bool:
        return self._update_thread is not None and self._update_thread.is_alive()

    def _start_update_task(
        self,
        operation: str,
        task: Callable[[Callable[[UpdateProgress], None]], Any],
    ) -> None:
        if self._update_task_is_running():
            return

        def run() -> None:
            try:
                result = task(self._updateProgressReported.emit)
            except UpdateError as error:
                if not self._update_shutdown.is_set():
                    self._updateTaskFailed.emit(operation, str(error))
                return
            except Exception:
                logger.exception("Unexpected failure in update operation %s", operation)
                if not self._update_shutdown.is_set():
                    self._updateTaskFailed.emit(
                        operation,
                        "更新処理で予期しないエラーが発生しました",
                    )
                return

            if self._update_shutdown.is_set():
                if isinstance(result, PreparedUpdate):
                    result.cleanup()
                return
            self._updateTaskFinished.emit(operation, result)

        self._update_thread = threading.Thread(
            target=run,
            name=f"PoseCare-update-{operation}",
            daemon=True,
        )
        self._update_thread.start()

    @Slot(object)
    def _on_update_progress(self, progress: UpdateProgress) -> None:
        if self._update_shutdown.is_set() or not isinstance(progress, UpdateProgress):
            return
        self._update_status = progress.message
        if self._update_state == "checking":
            self._update_progress = progress.percent / 100.0
        elif self._update_state == "downloading":
            start, end = _UPDATE_PROGRESS_RANGES.get(progress.stage, (0.0, 1.0))
            self._update_progress = start + (end - start) * progress.percent / 100.0
        self.updateChanged.emit()

    @Slot(str, object)
    def _on_update_task_finished(self, operation: str, result: object) -> None:
        self._update_thread = None
        if self._update_shutdown.is_set():
            if isinstance(result, PreparedUpdate):
                result.cleanup()
            return
        if operation == "check" and isinstance(result, UpdateCheck):
            self._update_check = result
            self._latest_version = result.latest.tag
            self._update_progress = 1.0
            if result.update_available:
                self._update_state = "available"
                self._update_status = f"{result.latest.tag} を利用できます"
            else:
                self._update_state = "upToDate"
                self._update_status = "PoseCareは最新です"
            self.updateChanged.emit()
            return
        if operation == "prepare" and isinstance(result, PreparedUpdate):
            self._discard_prepared_update()
            self._prepared_update = result
            self._update_state = "ready"
            self._update_status = "ダウンロード完了。再起動すると更新されます"
            self._update_progress = 1.0
            self.updateChanged.emit()
            return
        self._on_update_task_failed(operation, "更新処理の結果を読み取れませんでした")

    @Slot(str, str)
    def _on_update_task_failed(self, operation: str, message: str) -> None:
        del operation
        self._update_thread = None
        if self._update_shutdown.is_set():
            return
        self._update_state = "error"
        self._update_status = message
        self._update_progress = 0.0
        self.updateChanged.emit()

    def _discard_prepared_update(self) -> None:
        if self._prepared_update is None:
            return
        self._prepared_update.cleanup()
        self._prepared_update = None

    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(self.icon, self)
        self.tray.setToolTip("PoseCare — 姿勢を監視中")
        self.tray_menu = QMenu()
        menu = self.tray_menu
        open_action = QAction("PoseCareを開く", menu)
        open_action.triggered.connect(self.show_from_tray)
        self.pause_action = QAction("監視を一時停止", menu)
        self.pause_action.triggered.connect(
            lambda: self.toggleMonitoring(not self._monitoring)
        )
        test_notification_action = QAction("テスト通知", menu)
        test_notification_action.triggered.connect(self.sendTestNotification)
        quit_action = QAction("終了", menu)
        quit_action.triggered.connect(self.quitApplication)
        menu.addAction(open_action)
        menu.addAction(self.pause_action)
        menu.addAction(test_notification_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.messageClicked.connect(self.notificationActivated.emit)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()

    def _tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.show_from_tray()

    @Slot()
    def show_from_tray(self) -> None:
        if self._window is None:
            return
        state = self._window.windowState()
        if state & Qt.WindowState.WindowMinimized:
            self._window.setWindowState(state & ~Qt.WindowState.WindowMinimized)
        self._window.show()
        self._window.showNormal()
        self._activate_window()
        QTimer.singleShot(0, self._activate_window)

    def _activate_window(self) -> None:
        if self._window is None or not self._window.isVisible():
            return
        _restore_native_window(self._window)
        self._window.raise_()
        self._window.requestActivate()

    @Slot(result=bool)
    def requestClose(self) -> bool:
        if self._quitting or not self.tray.isVisible():
            self.shutdown()
            QTimer.singleShot(0, QCoreApplication.instance().quit)
            return True
        self.detector.reset(clear_alerts=True)
        if self._window is not None:
            self._window.hide()
        if not self._tray_hint_shown:
            self._tray_hint_shown = True
            title = "バックグラウンド監視を開始しました"
            message = (
                f"悪い姿勢が{self.settings.hold_seconds:g}秒続くと通知します。"
                "開く・一時停止・終了はタスクトレイから操作できます。"
            )
            if not (
                self.settings.notifications_enabled
                and self.notifier.send(title, message)
            ):
                self.tray.showMessage(
                    title,
                    message,
                    QSystemTrayIcon.MessageIcon.Information,
                    4500,
                )
        return False

    @Slot()
    def quitApplication(self) -> None:
        self._quitting = True
        self.tray.hide()
        self.shutdown()
        QCoreApplication.instance().quit()

    @Slot()
    def shutdown(self) -> None:
        self._update_shutdown.set()
        self._discard_prepared_update()
        self._registration_timer.stop()
        self._statistics_timer.stop()
        self._camera_activity_timer.stop()
        self._stop_camera()
        if not self._history_closed:
            self.history.close()
            self._history_closed = True

    def _start_camera(self) -> None:
        if self.camera_worker is not None or self._quitting:
            return
        self.latest_feature = None
        self.latest_landmarks = []
        self._camera_error_text = ""
        self.camera_worker = CameraWorker(self.settings.camera_index, model_path(), self)
        self.camera_worker.frame_ready.connect(self._on_frame)
        self.camera_worker.pose_ready.connect(self._on_pose)
        self.camera_worker.status_changed.connect(self._on_camera_status)
        self.camera_worker.model_progress.connect(self._on_model_progress)
        self.camera_worker.camera_error.connect(self._on_camera_error)
        self.camera_worker.fps_changed.connect(self._on_fps)
        self.camera_worker.start()

    def _restart_camera(self) -> None:
        self._camera_suspended_for_idle = False
        self._last_person_seen_at = time.monotonic()
        self._camera_status = "カメラを切り替えています"
        self.uiChanged.emit()
        self._stop_camera()
        self._start_camera()

    def _stop_camera(self) -> None:
        if self.camera_worker is None:
            return
        self.camera_worker.request_stop()
        self.camera_worker.wait(25_000)
        self.camera_worker.deleteLater()
        self.camera_worker = None

    def _check_camera_activity(self) -> None:
        if self._quitting:
            return
        try:
            user_idle_seconds = max(0.0, float(self._idle_seconds_provider()))
        except (OSError, TypeError, ValueError):
            return

        if self._camera_suspended_for_idle:
            if user_idle_seconds < self._idle_camera_timeout_seconds:
                self._resume_camera_after_idle()
            return

        if self.camera_worker is None or self._camera_error_text:
            return
        person_absent_seconds = max(0.0, time.monotonic() - self._last_person_seen_at)
        if (
            person_absent_seconds >= self._idle_camera_timeout_seconds
            and user_idle_seconds >= self._idle_camera_timeout_seconds
        ):
            self._suspend_camera_for_idle()

    def _suspend_camera_for_idle(self) -> None:
        self._camera_suspended_for_idle = True
        self.detector.reset()
        self.latest_feature = None
        self.latest_landmarks = []
        self._metrics = self._empty_metrics()
        self._stop_camera()
        self.image_provider.clear()
        self._frame_serial += 1
        self.frameChanged.emit()
        self._camera_status = "無人・無操作のためカメラを停止しました"
        self._fps_text = "カメラ停止中"
        self._set_detection_state(DetectionState(kind="idle"))

    def _resume_camera_after_idle(self) -> None:
        self._camera_suspended_for_idle = False
        self._last_person_seen_at = time.monotonic()
        self._camera_status = "操作を検知したためカメラを再開しています"
        self._fps_text = "解析 — fps"
        self._set_detection_state(DetectionState(kind="starting"))
        self._start_camera()

    def _on_frame(self, image: Any) -> None:
        if self._camera_suspended_for_idle:
            return
        if self._window is None or not self._window.isVisible():
            return
        self.image_provider.set_image(image)
        self._frame_serial += 1
        self.frameChanged.emit()

    def _on_pose(self, feature: PoseFeature | None, landmarks: Any) -> None:
        if self._camera_suspended_for_idle:
            return
        self.latest_feature = feature
        self.latest_landmarks = landmarks
        if landmarks:
            self._last_person_seen_at = time.monotonic()
        if feature is None:
            self._metrics = self._empty_metrics()
        else:
            self._metrics = {
                "headSide": self._format_metric(feature.metrics["head_side"]),
                "shoulderTilt": self._format_metric(feature.metrics["shoulder_tilt"], "°"),
                "shoulderDepth": self._format_metric(feature.metrics["shoulder_depth"]),
                "headForward": self._format_metric(feature.metrics["head_forward"]),
            }
        if not self._monitoring:
            self.uiChanged.emit()
            return
        state = self.detector.process(
            feature=feature,
            profiles=self.settings.profiles,
            sensitivity=self.settings.sensitivity,
            hold_seconds=self.settings.hold_seconds,
            cooldown_minutes=self.settings.cooldown_minutes,
            now=time.monotonic(),
        )
        self._set_detection_state(state)
        if state.should_notify and self.settings.notifications_enabled:
            self._send_posture_notification(state.profile_name or "登録した姿勢")

    def _on_camera_status(self, status: str) -> None:
        if self._camera_suspended_for_idle:
            return
        self._camera_status = status
        self.uiChanged.emit()
        has_compatible_profile = any(
            profile.feature_version == POSTURE_FEATURE_VERSION
            and profile.posture_type == "bad"
            for profile in self.settings.profiles
        )
        if (
            status.startswith("カメラ準備完了")
            and not has_compatible_profile
            and not self._first_run_prompted
        ):
            self._first_run_prompted = True
            self.show_from_tray()
            QTimer.singleShot(550, lambda: self.beginRegistration("bad", True))

    def _on_model_progress(self, value: int) -> None:
        if self._camera_suspended_for_idle:
            return
        self._camera_status = f"姿勢モデルをダウンロードしています… {value}%"
        self.uiChanged.emit()

    def _on_camera_error(self, message: str) -> None:
        if self._camera_suspended_for_idle:
            return
        self._camera_status = message
        self._camera_error_text = "カメラを利用できません\n設定でカメラ番号を確認してください"
        self._set_detection_state(DetectionState(kind="no_pose"))
        if self.tray.isVisible():
            self.tray.showMessage(
                "PoseCare — カメラエラー",
                message,
                QSystemTrayIcon.MessageIcon.Warning,
                5000,
            )

    def _on_fps(self, fps: float) -> None:
        if self._camera_suspended_for_idle:
            return
        self._fps_text = f"解析 {fps:.0f} fps"
        self.uiChanged.emit()

    def _set_detection_state(self, state: DetectionState) -> None:
        self._state_kind = state.kind
        self._state_progress = state.progress
        self.history.observe(state.kind, state.profile_name)
        if state.kind == "normal":
            self._state_title = "登録した正常姿勢です"
            self._state_detail = (
                f"「{state.profile_name}」と {state.similarity * 100:.0f}% 一致・通知対象外"
            )
            tooltip = f"PoseCare — 正常姿勢（{state.profile_name}）"
        elif state.kind == "good":
            self._state_title = "姿勢は安定しています"
            self._state_detail = f"悪い姿勢との最高一致度 {state.similarity * 100:.0f}%"
            tooltip = "PoseCare — 姿勢は安定しています"
        elif state.kind == "warning":
            remaining = max(0.0, self.settings.hold_seconds * (1.0 - state.progress))
            self._state_title = "姿勢を確認しています"
            self._state_detail = (
                f"「{state.profile_name}」と {state.similarity * 100:.0f}% 一致　"
                f"あと {remaining:.1f} 秒"
            )
            tooltip = f"PoseCare — {state.profile_name}を確認中"
        elif state.kind == "bad":
            self._state_title = "姿勢を戻しましょう"
            if state.cooldown_remaining > 0.0:
                minutes, seconds = divmod(int(state.cooldown_remaining + 0.5), 60)
                self._state_detail = (
                    f"通知済み　次回まで {minutes}:{seconds:02d}　"
                    f"一致度 {state.similarity * 100:.0f}%"
                )
                tooltip = f"PoseCare — 通知済み（次回まで {minutes}:{seconds:02d}）"
            else:
                self._state_detail = (
                    f"「{state.profile_name}」と {state.similarity * 100:.0f}% 一致しています"
                )
                tooltip = f"PoseCare — {state.profile_name}を検知"
        elif state.kind == "no_pose":
            self._state_title = "姿勢が見つかりません"
            self._state_detail = "頭と両肩が映る位置に座ってください"
            tooltip = "PoseCare — 姿勢を探しています"
        elif state.kind == "unconfigured":
            self._state_title = "悪い姿勢を登録してください"
            self._state_detail = "上半身向けに、通知したい姿勢を登録してください"
            tooltip = "PoseCare — 初期設定が必要です"
        elif state.kind == "paused":
            self._state_title = "監視を一時停止中"
            self._state_detail = "再開するとカメラの姿勢判定が戻ります"
            tooltip = "PoseCare — 一時停止中"
        elif state.kind == "idle":
            self._state_title = "カメラを自動停止中"
            self._state_detail = "キーボードやマウスを操作すると自動で再開します"
            tooltip = "PoseCare — 無人・無操作のためカメラ停止中"
        else:
            self._state_title = "準備しています"
            self._state_detail = "カメラと姿勢モデルを起動しています"
            tooltip = "PoseCare — 起動中"
        self.tray.setToolTip(tooltip)
        self.uiChanged.emit()

    def _send_posture_notification(self, profile_name: str) -> None:
        title = "姿勢を戻しましょう"
        message = (
            f"「{profile_name}」に近い状態が続いています。"
            "肩の力を抜いて座り直しましょう。"
        )
        self.history.record_alert(profile_name)
        if not self.notifier.send(
            title,
            message,
            self.notificationActivated.emit,
        ) and self.tray.isVisible():
            self.tray.showMessage(
                title,
                message,
                QSystemTrayIcon.MessageIcon.Warning,
                6500,
            )
