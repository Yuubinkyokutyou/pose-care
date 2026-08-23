from __future__ import annotations

import time

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QAction, QCloseEvent, QIcon
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from pose_care.camera import CameraWorker
from pose_care.config import SettingsStore, model_path
from pose_care.models import (
    POSTURE_FEATURE_VERSION,
    AppSettings,
    DetectionState,
    PoseFeature,
)
from pose_care.notifications import WindowsNotifier
from pose_care.posture import PostureDetector
from pose_care.ui.dialogs import RegistrationDialog
from pose_care.ui.style import COLORS
from pose_care.ui.widgets import MetricBlock, SpineCompass, VideoLabel


class ProfileRow(QFrame):
    delete_requested = Signal(str)

    def __init__(self, profile, parent=None) -> None:
        super().__init__(parent)
        self.profile_id = profile.id
        self.setStyleSheet(
            f"QFrame {{ background: #0D1726; border: 1px solid {COLORS['line']}; border-radius: 11px; }}"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 10, 10)
        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        name = QLabel(profile.name)
        name.setStyleSheet("font-weight: 650; background: transparent; border: none;")
        profile_label = "正常姿勢・通知から除外" if profile.posture_type == "normal" else "悪い姿勢・通知対象"
        if profile.feature_version == POSTURE_FEATURE_VERSION:
            detail_text = f"{profile_label}　上半身・{profile.sample_count}サンプルから登録"
        else:
            detail_text = f"{profile_label}　旧方式です。上半身方式で再登録してください"
        detail = QLabel(detail_text)
        detail.setObjectName("muted")
        detail.setStyleSheet(f"color: {COLORS['muted']}; background: transparent; border: none;")
        text_layout.addWidget(name)
        text_layout.addWidget(detail)
        remove = QPushButton("削除")
        remove.setObjectName("dangerButton")
        remove.setFixedWidth(68)
        remove.clicked.connect(lambda: self.delete_requested.emit(self.profile_id))
        layout.addLayout(text_layout, 1)
        layout.addWidget(remove)


class MainWindow(QMainWindow):
    def __init__(self, store: SettingsStore, settings: AppSettings, icon: QIcon) -> None:
        super().__init__()
        self.store = store
        self.settings = settings
        self.icon = icon
        self.detector = PostureDetector()
        self.camera_worker: CameraWorker | None = None
        self.latest_feature: PoseFeature | None = None
        self.latest_landmarks = []
        self.monitoring = True
        self._quitting = False
        self._first_run_prompted = False
        self._tray_hint_shown = False
        self._last_state = DetectionState(kind="starting")

        self.setWindowTitle("PoseCare")
        self.setWindowIcon(icon)
        self.resize(1180, 760)
        self.setMinimumSize(980, 650)
        self._build_ui()
        self._build_tray()
        self.notifier = WindowsNotifier()
        self._load_settings_into_controls()
        self._render_profiles()
        self._set_detection_state(self._last_state)
        self._start_camera()

    def _build_ui(self) -> None:
        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        nav = QFrame()
        nav.setObjectName("navRail")
        nav.setFixedWidth(208)
        nav_layout = QVBoxLayout(nav)
        nav_layout.setContentsMargins(20, 24, 20, 20)
        nav_layout.setSpacing(10)

        brand_row = QHBoxLayout()
        brand_mark = QLabel("│")
        brand_mark.setStyleSheet(f"color: {COLORS['signal']}; font-size: 27px; font-weight: 800;")
        brand = QLabel("PoseCare")
        brand.setObjectName("appName")
        brand_row.addWidget(brand_mark)
        brand_row.addWidget(brand)
        brand_row.addStretch(1)
        nav_layout.addLayout(brand_row)
        nav_layout.addSpacing(26)

        self.monitor_nav = QPushButton("  姿勢モニター")
        self.monitor_nav.setObjectName("navButton")
        self.monitor_nav.setCheckable(True)
        self.monitor_nav.setChecked(True)
        self.monitor_nav.clicked.connect(lambda: self._switch_page(0))
        self.settings_nav = QPushButton("  設定")
        self.settings_nav.setObjectName("navButton")
        self.settings_nav.setCheckable(True)
        self.settings_nav.clicked.connect(lambda: self._switch_page(1))
        nav_layout.addWidget(self.monitor_nav)
        nav_layout.addWidget(self.settings_nav)
        nav_layout.addStretch(1)

        privacy = QLabel("映像は保存・送信されません\nすべてこのPC内で処理します")
        privacy.setObjectName("muted")
        privacy.setWordWrap(True)
        privacy.setStyleSheet(f"color: {COLORS['muted']}; font-size: 10px; line-height: 1.4;")
        nav_layout.addWidget(privacy)

        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_monitor_page())
        self.pages.addWidget(self._build_settings_page())
        root_layout.addWidget(nav)
        root_layout.addWidget(self.pages, 1)
        self.setCentralWidget(root)

    def _build_monitor_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 25, 30, 28)
        layout.setSpacing(20)

        header = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(3)
        eyebrow = QLabel("LIVE POSTURE")
        eyebrow.setObjectName("eyebrow")
        title = QLabel("姿勢モニター")
        title.setObjectName("pageTitle")
        self.camera_status = QLabel("起動しています")
        self.camera_status.setObjectName("muted")
        title_col.addWidget(eyebrow)
        title_col.addWidget(title)
        title_col.addWidget(self.camera_status)
        header.addLayout(title_col)
        header.addStretch(1)
        self.monitor_toggle = QCheckBox("監視を開始")
        self.monitor_toggle.setChecked(True)
        self.monitor_toggle.toggled.connect(self._toggle_monitoring)
        header.addWidget(self.monitor_toggle)
        layout.addLayout(header)

        content = QHBoxLayout()
        content.setSpacing(18)
        video_frame = QFrame()
        video_frame.setObjectName("videoFrame")
        video_layout = QVBoxLayout(video_frame)
        video_layout.setContentsMargins(8, 8, 8, 8)
        self.video = VideoLabel()
        video_layout.addWidget(self.video)
        content.addWidget(video_frame, 7)

        right = QVBoxLayout()
        right.setSpacing(14)
        state_card = QFrame()
        state_card.setObjectName("card")
        state_layout = QVBoxLayout(state_card)
        state_layout.setContentsMargins(22, 20, 22, 20)
        state_layout.setSpacing(10)
        self.compass = SpineCompass()
        compass_row = QHBoxLayout()
        compass_row.addStretch(1)
        compass_row.addWidget(self.compass)
        compass_row.addStretch(1)
        self.state_title = QLabel("準備しています")
        self.state_title.setObjectName("sectionTitle")
        self.state_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.state_detail = QLabel("カメラとモデルを起動しています")
        self.state_detail.setObjectName("muted")
        self.state_detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.state_detail.setWordWrap(True)
        state_layout.addLayout(compass_row)
        state_layout.addWidget(self.state_title)
        state_layout.addWidget(self.state_detail)
        right.addWidget(state_card)

        telemetry_card = QFrame()
        telemetry_card.setObjectName("card")
        telemetry_layout = QVBoxLayout(telemetry_card)
        telemetry_layout.setContentsMargins(20, 18, 20, 18)
        telemetry_layout.setSpacing(14)
        telemetry_title = QLabel("内部の位置")
        telemetry_title.setObjectName("sectionTitle")
        telemetry_note = QLabel("頭と両肩から算出した相対値")
        telemetry_note.setObjectName("muted")
        telemetry_layout.addWidget(telemetry_title)
        telemetry_layout.addWidget(telemetry_note)
        metrics_grid = QGridLayout()
        metrics_grid.setHorizontalSpacing(20)
        metrics_grid.setVerticalSpacing(16)
        self.head_metric = MetricBlock("頭の横ずれ", "")
        self.shoulder_metric = MetricBlock("肩の傾き")
        self.shoulder_depth_metric = MetricBlock("肩の前後差", "")
        self.depth_metric = MetricBlock("頭の前後", "")
        metrics_grid.addWidget(self.head_metric, 0, 0)
        metrics_grid.addWidget(self.shoulder_metric, 0, 1)
        metrics_grid.addWidget(self.shoulder_depth_metric, 1, 0)
        metrics_grid.addWidget(self.depth_metric, 1, 1)
        telemetry_layout.addLayout(metrics_grid)
        telemetry_layout.addStretch(1)
        self.fps_label = QLabel("解析 — fps")
        self.fps_label.setObjectName("muted")
        telemetry_layout.addWidget(self.fps_label)
        right.addWidget(telemetry_card, 1)
        content.addLayout(right, 3)
        layout.addLayout(content, 1)
        return page

    def _build_settings_page(self) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(30, 25, 22, 24)
        page_layout.setSpacing(14)
        eyebrow = QLabel("PREFERENCES")
        eyebrow.setObjectName("eyebrow")
        title = QLabel("設定")
        title.setObjectName("pageTitle")
        page_layout.addWidget(eyebrow)
        page_layout.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 4, 10, 4)
        content_layout.setSpacing(16)

        bad_profile_card = QFrame()
        bad_profile_card.setObjectName("settingsCard")
        bad_profile_layout = QVBoxLayout(bad_profile_card)
        bad_profile_layout.setContentsMargins(22, 20, 22, 20)
        bad_profile_layout.setSpacing(12)
        bad_profile_head = QHBoxLayout()
        bad_profile_title_col = QVBoxLayout()
        bad_profile_title = QLabel("通知したい悪い姿勢")
        bad_profile_title.setObjectName("sectionTitle")
        bad_profile_desc = QLabel("似た姿勢が続くと通知します。複数登録できます。")
        bad_profile_desc.setObjectName("muted")
        bad_profile_title_col.addWidget(bad_profile_title)
        bad_profile_title_col.addWidget(bad_profile_desc)
        add_bad_button = QPushButton("＋ 悪い姿勢")
        add_bad_button.setObjectName("primaryButton")
        add_bad_button.clicked.connect(lambda checked=False: self._open_registration("bad"))
        bad_profile_head.addLayout(bad_profile_title_col, 1)
        bad_profile_head.addWidget(add_bad_button)
        bad_profile_layout.addLayout(bad_profile_head)
        self.bad_profile_list = QVBoxLayout()
        self.bad_profile_list.setSpacing(8)
        bad_profile_layout.addLayout(self.bad_profile_list)
        content_layout.addWidget(bad_profile_card)

        normal_profile_card = QFrame()
        normal_profile_card.setObjectName("settingsCard")
        normal_profile_layout = QVBoxLayout(normal_profile_card)
        normal_profile_layout.setContentsMargins(22, 20, 22, 20)
        normal_profile_layout.setSpacing(12)
        normal_profile_head = QHBoxLayout()
        normal_profile_title_col = QVBoxLayout()
        normal_profile_title = QLabel("通知から除外する正常姿勢")
        normal_profile_title.setObjectName("sectionTitle")
        normal_profile_desc = QLabel("この姿勢に近い場合は、悪い姿勢と少し似ていても通知しません。")
        normal_profile_desc.setObjectName("muted")
        normal_profile_title_col.addWidget(normal_profile_title)
        normal_profile_title_col.addWidget(normal_profile_desc)
        add_normal_button = QPushButton("＋ 正常姿勢")
        add_normal_button.setObjectName("primaryButton")
        add_normal_button.clicked.connect(lambda checked=False: self._open_registration("normal"))
        normal_profile_head.addLayout(normal_profile_title_col, 1)
        normal_profile_head.addWidget(add_normal_button)
        normal_profile_layout.addLayout(normal_profile_head)
        self.normal_profile_list = QVBoxLayout()
        self.normal_profile_list.setSpacing(8)
        normal_profile_layout.addLayout(self.normal_profile_list)
        content_layout.addWidget(normal_profile_card)

        detection_card = QFrame()
        detection_card.setObjectName("settingsCard")
        detection_layout = QGridLayout(detection_card)
        detection_layout.setContentsMargins(22, 20, 22, 20)
        detection_layout.setHorizontalSpacing(24)
        detection_layout.setVerticalSpacing(15)
        detection_title = QLabel("検知と通知")
        detection_title.setObjectName("sectionTitle")
        detection_layout.addWidget(detection_title, 0, 0, 1, 3)
        detection_layout.addWidget(QLabel("検知感度"), 1, 0)
        self.sensitivity_slider = QSlider(Qt.Orientation.Horizontal)
        self.sensitivity_slider.setRange(0, 100)
        self.sensitivity_value = QLabel()
        self.sensitivity_value.setMinimumWidth(46)
        self.sensitivity_value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.sensitivity_slider.valueChanged.connect(
            lambda value: self.sensitivity_value.setText(f"{value}%")
        )
        detection_layout.addWidget(self.sensitivity_slider, 1, 1)
        detection_layout.addWidget(self.sensitivity_value, 1, 2)
        detection_layout.addWidget(QLabel("通知までの時間"), 2, 0)
        self.hold_spin = QDoubleSpinBox()
        self.hold_spin.setRange(1.0, 30.0)
        self.hold_spin.setSingleStep(0.5)
        self.hold_spin.setSuffix(" 秒")
        detection_layout.addWidget(self.hold_spin, 2, 1, 1, 2)
        detection_layout.addWidget(QLabel("通知の間隔"), 3, 0)
        self.cooldown_spin = QSpinBox()
        self.cooldown_spin.setRange(1, 120)
        self.cooldown_spin.setSuffix(" 分")
        detection_layout.addWidget(self.cooldown_spin, 3, 1, 1, 2)
        self.notifications_check = QCheckBox("Windows通知を有効にする")
        detection_layout.addWidget(self.notifications_check, 4, 0, 1, 2)
        self.test_notification_button = QPushButton("テスト通知")
        self.test_notification_button.clicked.connect(self._send_test_notification)
        detection_layout.addWidget(self.test_notification_button, 4, 2)
        self.notification_feedback = QLabel("")
        self.notification_feedback.setObjectName("muted")
        detection_layout.addWidget(self.notification_feedback, 5, 0, 1, 3)
        content_layout.addWidget(detection_card)

        app_card = QFrame()
        app_card.setObjectName("settingsCard")
        app_layout = QGridLayout(app_card)
        app_layout.setContentsMargins(22, 20, 22, 20)
        app_layout.setHorizontalSpacing(24)
        app_layout.setVerticalSpacing(15)
        app_title = QLabel("アプリとカメラ")
        app_title.setObjectName("sectionTitle")
        app_layout.addWidget(app_title, 0, 0, 1, 2)
        app_layout.addWidget(QLabel("カメラ番号"), 1, 0)
        self.camera_spin = QSpinBox()
        self.camera_spin.setRange(0, 9)
        app_layout.addWidget(self.camera_spin, 1, 1)
        self.start_minimized_check = QCheckBox("次回からタスクトレイで起動する")
        app_layout.addWidget(self.start_minimized_check, 2, 0, 1, 2)
        content_layout.addWidget(app_card)
        content_layout.addStretch(1)
        scroll.setWidget(content)
        page_layout.addWidget(scroll, 1)

        save_row = QHBoxLayout()
        self.save_feedback = QLabel("")
        self.save_feedback.setObjectName("muted")
        save_button = QPushButton("設定を保存")
        save_button.setObjectName("primaryButton")
        save_button.clicked.connect(self._save_controls)
        save_row.addWidget(self.save_feedback)
        save_row.addStretch(1)
        save_row.addWidget(save_button)
        page_layout.addLayout(save_row)
        return page

    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(self.icon, self)
        self.tray.setToolTip("PoseCare — 姿勢を監視中")
        menu = QMenu(self)
        open_action = QAction("PoseCareを開く", menu)
        open_action.triggered.connect(self.show_from_tray)
        self.pause_action = QAction("監視を一時停止", menu)
        self.pause_action.triggered.connect(self._toggle_from_tray)
        test_notification_action = QAction("テスト通知", menu)
        test_notification_action.triggered.connect(self._send_test_notification)
        quit_action = QAction("終了", menu)
        quit_action.triggered.connect(self.quit_application)
        menu.addAction(open_action)
        menu.addAction(self.pause_action)
        menu.addAction(test_notification_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()

    def _switch_page(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        self.monitor_nav.setChecked(index == 0)
        self.settings_nav.setChecked(index == 1)

    def _toggle_monitoring(self, checked: bool) -> None:
        self.monitoring = checked
        self.pause_action.setText("監視を一時停止" if checked else "監視を再開")
        self.detector.reset(clear_alerts=checked)
        if not checked:
            self._set_detection_state(DetectionState(kind="paused"))

    def _toggle_from_tray(self) -> None:
        self.monitor_toggle.setChecked(not self.monitor_toggle.isChecked())

    def _load_settings_into_controls(self) -> None:
        self.sensitivity_slider.setValue(self.settings.sensitivity)
        self.hold_spin.setValue(self.settings.hold_seconds)
        self.cooldown_spin.setValue(self.settings.cooldown_minutes)
        self.notifications_check.setChecked(self.settings.notifications_enabled)
        self.camera_spin.setValue(self.settings.camera_index)
        self.start_minimized_check.setChecked(self.settings.start_minimized)

    def _save_controls(self) -> None:
        old_camera_index = self.settings.camera_index
        self.settings.sensitivity = self.sensitivity_slider.value()
        self.settings.hold_seconds = self.hold_spin.value()
        self.settings.cooldown_minutes = self.cooldown_spin.value()
        self.settings.notifications_enabled = self.notifications_check.isChecked()
        self.settings.camera_index = self.camera_spin.value()
        self.settings.start_minimized = self.start_minimized_check.isChecked()
        self.store.save(self.settings)
        self.detector.reset(clear_alerts=True)
        self.save_feedback.setText("保存しました")
        QTimer.singleShot(2400, lambda: self.save_feedback.setText(""))
        if old_camera_index != self.settings.camera_index:
            self._restart_camera()

    def _render_profiles(self) -> None:
        self._render_profile_group(self.bad_profile_list, "bad")
        self._render_profile_group(self.normal_profile_list, "normal")

    def _render_profile_group(self, layout: QVBoxLayout, posture_type: str) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        profiles = [
            profile for profile in self.settings.profiles
            if profile.posture_type == posture_type
        ]
        if not profiles:
            empty_text = (
                "未登録です。必要に応じて正常姿勢を追加できます。"
                if posture_type == "normal"
                else "まだ登録されていません。まず1つ登録してください。"
            )
            empty = QLabel(empty_text)
            empty.setObjectName("muted")
            empty.setStyleSheet(
                f"color: {COLORS['muted']}; border: 1px dashed {COLORS['line']}; "
                "border-radius: 10px; padding: 14px;"
            )
            layout.addWidget(empty)
            return
        for profile in profiles:
            row = ProfileRow(profile)
            row.delete_requested.connect(self._delete_profile)
            layout.addWidget(row)

    def _open_registration(self, posture_type: str = "bad", first_run: bool = False) -> None:
        dialog = RegistrationDialog(
            lambda: self.latest_feature,
            posture_type=posture_type,
            first_run=first_run,
            parent=self,
        )
        if dialog.exec() and dialog.profile is not None:
            self.settings.profiles.append(dialog.profile)
            self.settings.first_run_complete = True
            self.store.save(self.settings)
            self._render_profiles()
            self.detector.reset(clear_alerts=True)
            self._switch_page(0)

    def _delete_profile(self, profile_id: str) -> None:
        profile = next((item for item in self.settings.profiles if item.id == profile_id), None)
        if profile is None:
            return
        answer = QMessageBox.question(
            self,
            "姿勢を削除",
            f"「{profile.name}」を削除しますか？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.settings.profiles = [item for item in self.settings.profiles if item.id != profile_id]
        self.store.save(self.settings)
        self.detector.reset(clear_alerts=True)
        self._render_profiles()

    def _start_camera(self) -> None:
        self.latest_feature = None
        self.camera_worker = CameraWorker(self.settings.camera_index, model_path(), self)
        self.camera_worker.frame_ready.connect(self._on_frame)
        self.camera_worker.pose_ready.connect(self._on_pose)
        self.camera_worker.status_changed.connect(self._on_camera_status)
        self.camera_worker.model_progress.connect(self._on_model_progress)
        self.camera_worker.camera_error.connect(self._on_camera_error)
        self.camera_worker.fps_changed.connect(lambda fps: self.fps_label.setText(f"解析 {fps:.0f} fps"))
        self.camera_worker.start()

    def _restart_camera(self) -> None:
        self.camera_status.setText("カメラを切り替えています")
        self._stop_camera()
        self._start_camera()

    def _stop_camera(self) -> None:
        if self.camera_worker is None:
            return
        self.camera_worker.request_stop()
        # The initial HTTPS model request cannot be interrupted mid-connect.
        # Keep the thread alive until that bounded request or a camera read finishes.
        self.camera_worker.wait(25_000)
        self.camera_worker.deleteLater()
        self.camera_worker = None

    def _on_frame(self, image) -> None:
        if self.isVisible() and not self.isMinimized():
            self.video.set_image(image)

    def _on_pose(self, feature: PoseFeature | None, landmarks) -> None:
        self.latest_feature = feature
        self.latest_landmarks = landmarks
        if feature is None:
            self.head_metric.set_value(None)
            self.shoulder_metric.set_value(None)
            self.shoulder_depth_metric.set_value(None)
            self.depth_metric.set_value(None)
        else:
            self.head_metric.set_value(feature.metrics["head_side"])
            self.shoulder_metric.set_value(feature.metrics["shoulder_tilt"])
            self.shoulder_depth_metric.set_value(feature.metrics["shoulder_depth"])
            self.depth_metric.set_value(feature.metrics["head_forward"])
        if not self.monitoring:
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
        self.camera_status.setText(status)
        has_compatible_profile = any(
            profile.feature_version == POSTURE_FEATURE_VERSION
            and profile.posture_type == "bad"
            for profile in self.settings.profiles
        )
        if status == "カメラ準備完了" and not has_compatible_profile and not self._first_run_prompted:
            self._first_run_prompted = True
            self.show_from_tray()
            QTimer.singleShot(
                550,
                lambda: self._open_registration(posture_type="bad", first_run=True),
            )

    def _on_model_progress(self, value: int) -> None:
        self.camera_status.setText(f"姿勢モデルをダウンロードしています… {value}%")

    def _on_camera_error(self, message: str) -> None:
        self.camera_status.setText(message)
        self.video.setText("カメラを利用できません\n設定でカメラ番号を確認してください")
        self._set_detection_state(DetectionState(kind="no_pose"))
        if self.tray.isVisible():
            self.tray.showMessage("PoseCare — カメラエラー", message, QSystemTrayIcon.MessageIcon.Warning, 5000)

    def _set_detection_state(self, state: DetectionState) -> None:
        self._last_state = state
        self.compass.set_state(state)
        if state.kind == "normal":
            title = "登録した正常姿勢です"
            detail = f"「{state.profile_name}」と {state.similarity * 100:.0f}% 一致・通知対象外"
            tooltip = f"PoseCare — 正常姿勢（{state.profile_name}）"
        elif state.kind == "good":
            title = "姿勢は安定しています"
            detail = f"悪い姿勢との最高一致度 {state.similarity * 100:.0f}%"
            tooltip = "PoseCare — 姿勢は安定しています"
        elif state.kind == "warning":
            remaining = max(0.0, self.settings.hold_seconds * (1.0 - state.progress))
            title = "姿勢を確認しています"
            detail = (
                f"「{state.profile_name}」と {state.similarity * 100:.0f}% 一致　"
                f"あと {remaining:.1f} 秒"
            )
            tooltip = f"PoseCare — {state.profile_name}を確認中"
        elif state.kind == "bad":
            title = "姿勢を戻しましょう"
            if state.cooldown_remaining > 0.0:
                minutes, seconds = divmod(int(state.cooldown_remaining + 0.5), 60)
                detail = (
                    f"通知済み　次回まで {minutes}:{seconds:02d}　"
                    f"一致度 {state.similarity * 100:.0f}%"
                )
                tooltip = f"PoseCare — 通知済み（次回まで {minutes}:{seconds:02d}）"
            else:
                detail = f"「{state.profile_name}」と {state.similarity * 100:.0f}% 一致しています"
                tooltip = f"PoseCare — {state.profile_name}を検知"
        elif state.kind == "no_pose":
            title = "姿勢が見つかりません"
            detail = "頭と両肩が映る位置に座ってください"
            tooltip = "PoseCare — 姿勢を探しています"
        elif state.kind == "unconfigured":
            title = "悪い姿勢を登録してください"
            detail = "上半身向けに、通知したい姿勢を登録してください"
            tooltip = "PoseCare — 初期設定が必要です"
        elif state.kind == "paused":
            title = "監視を一時停止中"
            detail = "再開するとカメラの姿勢判定が戻ります"
            tooltip = "PoseCare — 一時停止中"
        else:
            title = "準備しています"
            detail = "カメラと姿勢モデルを起動しています"
            tooltip = "PoseCare — 起動中"
        self.state_title.setText(title)
        self.state_detail.setText(detail)
        self.tray.setToolTip(tooltip)

    def _send_posture_notification(self, profile_name: str) -> None:
        title = "姿勢を戻しましょう"
        message = f"「{profile_name}」に近い状態が続いています。肩の力を抜いて座り直しましょう。"
        if not self.notifier.send(title, message) and self.tray.isVisible():
            self.tray.showMessage(
                title,
                message,
                QSystemTrayIcon.MessageIcon.Warning,
                6500,
            )

    def _send_test_notification(self) -> None:
        title = "PoseCare テスト通知"
        message = "通知は正常です。悪い姿勢が続いたときも、この形式でお知らせします。"
        if self.notifier.send(title, message):
            self.notification_feedback.setText("ネイティブWindows通知を送信しました")
        elif self.tray.isVisible():
            self.tray.showMessage(
                title,
                message,
                QSystemTrayIcon.MessageIcon.Information,
                6000,
            )
            self.notification_feedback.setText("タスクトレイ通知へ切り替えて送信しました")
        else:
            self.notification_feedback.setText("通知を送信できませんでした")
        QTimer.singleShot(4000, lambda: self.notification_feedback.setText(""))

    def _tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.show_from_tray()

    def show_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._quitting or not self.tray.isVisible():
            self._stop_camera()
            event.accept()
            return
        event.ignore()
        # Treat entering background monitoring as a fresh monitoring session.
        # This prevents an alert shown while the window was open from silencing
        # the first meaningful background alert for the full cooldown period.
        self.detector.reset(clear_alerts=True)
        self.hide()
        if not self._tray_hint_shown:
            self._tray_hint_shown = True
            title = "バックグラウンド監視を開始しました"
            message = (
                f"悪い姿勢が{self.settings.hold_seconds:g}秒続くと通知します。"
                "開く・一時停止・終了はタスクトレイから操作できます。"
            )
            if self.settings.notifications_enabled and self.notifier.send(title, message):
                return
            self.tray.showMessage(
                title,
                message,
                QSystemTrayIcon.MessageIcon.Information,
                4500,
            )

    def quit_application(self) -> None:
        self._quitting = True
        self.tray.hide()
        self._stop_camera()
        from PySide6.QtWidgets import QApplication

        QApplication.instance().quit()
