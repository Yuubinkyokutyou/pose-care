from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

from pose_care.models import DetectionState
from pose_care.ui.style import COLORS


class VideoLabel(QLabel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._source: QPixmap | None = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(520, 340)
        self.setText("カメラを準備しています…")
        self.setStyleSheet(f"color: {COLORS['muted']}; background: #060B12; border-radius: 18px;")

    def set_image(self, image) -> None:
        self._source = QPixmap.fromImage(image)
        self._refresh()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._refresh()

    def _refresh(self) -> None:
        if self._source is None or self._source.isNull():
            return
        self.setPixmap(
            self._source.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )


class SpineCompass(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(142, 142)
        self._kind = "starting"
        self._progress = 0.0

    def set_state(self, state: DetectionState) -> None:
        self._kind = state.kind
        self._progress = state.progress
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(9, 9, -9, -9)
        color_name = {
            "normal": "signal",
            "good": "signal",
            "warning": "amber",
            "bad": "danger",
            "no_pose": "muted",
            "unconfigured": "blue",
            "paused": "muted",
        }.get(self._kind, "blue")
        color = QColor(COLORS[color_name])
        painter.setPen(QPen(QColor(COLORS["line"]), 8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawArc(rect, 0, 360 * 16)
        span = 360.0 if self._kind in ("normal", "good", "bad") else max(32.0, 360.0 * self._progress)
        if self._kind in ("no_pose", "unconfigured", "paused", "starting"):
            span = 82.0
        painter.setPen(QPen(color, 8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawArc(rect, 90 * 16, int(-span * 16))

        center_x = self.width() / 2
        painter.setPen(QPen(QColor(COLORS["text"]), 5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(QPointF(center_x, 45), QPointF(center_x, 96))
        painter.setBrush(QColor(COLORS["text"]))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(center_x, 34), 7, 7)
        painter.setPen(QPen(color, 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(QPointF(47, 59), QPointF(center_x, 63))
        painter.drawLine(QPointF(center_x, 63), QPointF(95, 59))
        painter.end()


class MetricBlock(QWidget):
    def __init__(self, label: str, suffix: str = "°", parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        caption = QLabel(label)
        caption.setObjectName("muted")
        self.value_label = QLabel(f"—{suffix}")
        self.value_label.setObjectName("metricValue")
        layout.addWidget(caption)
        layout.addWidget(self.value_label)
        self.suffix = suffix

    def set_value(self, value: float | None) -> None:
        self.value_label.setText("—" if value is None else f"{value:+.1f}{self.suffix}")
