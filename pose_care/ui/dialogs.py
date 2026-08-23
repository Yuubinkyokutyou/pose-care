from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QElapsedTimer, QTimer, Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from pose_care.models import PoseFeature, PostureProfile
from pose_care.posture import aggregate_features
from pose_care.ui.style import COLORS


class RegistrationDialog(QDialog):
    def __init__(
        self,
        feature_provider: Callable[[], PoseFeature | None],
        posture_type: str = "bad",
        first_run: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.feature_provider = feature_provider
        self.posture_type = "normal" if posture_type == "normal" else "bad"
        self.profile: PostureProfile | None = None
        self.samples: list[PoseFeature] = []
        self._last_sample: PoseFeature | None = None
        self._capturing = False
        self._elapsed = QElapsedTimer()
        self._timer = QTimer(self)
        self._timer.setInterval(70)
        self._timer.timeout.connect(self._tick)

        is_normal = self.posture_type == "normal"
        self.setWindowTitle("正常姿勢を登録" if is_normal else "悪い姿勢を登録")
        self.setModal(True)
        self.setMinimumWidth(510)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)

        eyebrow = QLabel("FIRST SETUP" if first_run else "POSTURE PROFILE")
        eyebrow.setObjectName("eyebrow")
        title = QLabel("基準にする正常姿勢を覚えさせる" if is_normal else "よくしてしまう姿勢を覚えさせる")
        title.setObjectName("pageTitle")
        if is_normal:
            intro_text = (
                "頭・両肩・胸元をカメラに入れ、通知から除外したい正常姿勢を3秒間保ちます。\n"
                "普段のカメラ位置・椅子の高さで登録すると安定します。"
            )
        else:
            intro_text = (
                "頭・両肩・胸元をカメラに入れ、通知してほしい悪い姿勢を3秒間保ちます。\n"
                "普段のカメラ位置・椅子の高さで登録すると安定します。"
            )
        intro = QLabel(intro_text)
        intro.setObjectName("muted")
        intro.setWordWrap(True)
        layout.addWidget(eyebrow)
        layout.addWidget(title)
        layout.addWidget(intro)

        name_label = QLabel("姿勢の名前")
        self.name_input = QLineEdit("いつもの正常姿勢" if is_normal else "猫背")
        self.name_input.setMaxLength(30)
        self.name_input.selectAll()
        layout.addWidget(name_label)
        layout.addWidget(self.name_input)

        pose_label = "正常姿勢をとる" if is_normal else "悪い姿勢をとる"
        guide = QLabel(f"●  {pose_label}  →  ●  3秒保つ  →  ●  登録完了")
        guide.setStyleSheet(
            f"background: {COLORS['surface']}; border: 1px solid {COLORS['line']}; "
            "border-radius: 12px; padding: 14px;"
        )
        layout.addWidget(guide)

        self.status_label = QLabel("準備できたら登録を開始してください")
        self.status_label.setObjectName("muted")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        layout.addWidget(self.status_label)
        layout.addWidget(self.progress)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.cancel_button = QPushButton("あとで")
        self.cancel_button.clicked.connect(self.reject)
        self.capture_button = QPushButton("3秒間登録する")
        self.capture_button.setObjectName("primaryButton")
        self.capture_button.clicked.connect(self._start_capture)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.capture_button)
        layout.addLayout(buttons)

    def _start_capture(self) -> None:
        if not self.name_input.text().strip():
            self.status_label.setText("姿勢の名前を入力してください")
            self.name_input.setFocus()
            return
        if self.feature_provider() is None:
            self.status_label.setText("姿勢を認識できません。頭と両肩をカメラに入れてください")
            return
        self.samples.clear()
        self._last_sample = None
        self._capturing = True
        self._elapsed.start()
        self.capture_button.setEnabled(False)
        self.name_input.setEnabled(False)
        self.status_label.setText("その姿勢のまま、動かずに保ってください")
        self._timer.start()

    def _tick(self) -> None:
        elapsed_ms = self._elapsed.elapsed()
        self.progress.setValue(min(100, int(elapsed_ms / 30)))
        feature = self.feature_provider()
        if feature is not None and feature is not self._last_sample:
            self.samples.append(feature)
            self._last_sample = feature
        if elapsed_ms < 3000:
            return
        self._timer.stop()
        self._capturing = False
        if len(self.samples) < 15:
            self.status_label.setText("十分に認識できませんでした。姿勢と明るさを整えて再試行してください")
            self.progress.setValue(0)
            self.capture_button.setEnabled(True)
            self.name_input.setEnabled(True)
            return
        aggregate = aggregate_features(self.samples)
        self.profile = PostureProfile.create(
            self.name_input.text(),
            list(aggregate),
            len(self.samples),
            posture_type=self.posture_type,
        )
        self.status_label.setText(f"「{self.profile.name}」を登録しました")
        self.progress.setValue(100)
        QTimer.singleShot(450, self.accept)

    def reject(self) -> None:
        self._timer.stop()
        super().reject()
