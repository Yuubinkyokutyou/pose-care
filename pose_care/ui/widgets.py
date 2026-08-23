from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

from pose_care.models import DetectionState
from pose_care.history import ProfileDuration, TimelineBucket
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


class StatisticsCard(QWidget):
    def __init__(self, label: str, accent: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("statisticsCard")
        self.setMinimumHeight(112)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(3)
        caption = QLabel(label)
        caption.setObjectName("muted")
        self.value_label = QLabel("—")
        self.value_label.setObjectName("statisticsValue")
        self.detail_label = QLabel("データを集計中")
        self.detail_label.setObjectName("muted")
        self.accent = accent
        self.value_label.setStyleSheet(f"color: {accent};")
        layout.addWidget(caption)
        layout.addWidget(self.value_label)
        layout.addWidget(self.detail_label)

    def set_value(self, value: str, detail: str) -> None:
        self.value_label.setText(value)
        self.detail_label.setText(detail)


class TimelineChart(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(235)
        self._buckets: tuple[TimelineBucket, ...] = ()

    def set_buckets(self, buckets: tuple[TimelineBucket, ...]) -> None:
        self._buckets = buckets
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        if not self._buckets or sum(item.monitored_seconds for item in self._buckets) <= 0.0:
            painter.setPen(QColor(COLORS["muted"]))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "表示できる統計はまだありません")
            painter.end()
            return

        left, right, top, bottom = 8.0, 8.0, 15.0, 34.0
        chart = QRectF(left, top, max(1.0, self.width() - left - right), max(1.0, self.height() - top - bottom))
        guide_pen = QPen(QColor(COLORS["line"]), 1)
        guide_pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(guide_pen)
        for fraction in (0.0, 0.5, 1.0):
            y = chart.bottom() - (chart.height() * fraction)
            painter.drawLine(QPointF(chart.left(), y), QPointF(chart.right(), y))

        slot = chart.width() / len(self._buckets)
        bar_width = max(4.0, min(18.0, slot * 0.62))
        for index, bucket in enumerate(self._buckets):
            x = chart.left() + (index * slot) + ((slot - bar_width) / 2.0)
            coverage = min(1.0, bucket.monitored_seconds / max(1.0, bucket.capacity_seconds))
            total_height = chart.height() * coverage
            good_height = 0.0
            if bucket.monitored_seconds > 0.0:
                good_height = total_height * (bucket.good_seconds / bucket.monitored_seconds)
            bad_height = max(0.0, total_height - good_height)
            if good_height > 0.5:
                painter.setBrush(QColor(COLORS["signal"]))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRoundedRect(
                    QRectF(x, chart.bottom() - good_height, bar_width, good_height),
                    min(3.0, bar_width / 2.0),
                    min(3.0, bar_width / 2.0),
                )
            if bad_height > 0.5:
                painter.setBrush(QColor(COLORS["danger"]))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRoundedRect(
                    QRectF(x, chart.bottom() - total_height, bar_width, bad_height),
                    min(3.0, bar_width / 2.0),
                    min(3.0, bar_width / 2.0),
                )

            show_every = 4 if len(self._buckets) == 24 else (5 if len(self._buckets) > 10 else 1)
            if index % show_every == 0 or index == len(self._buckets) - 1:
                painter.setPen(QColor(COLORS["muted"]))
                label_rect = QRectF(chart.left() + (index * slot) - (slot * 0.35), chart.bottom() + 8, slot * 1.7, 20)
                painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, bucket.label)
        painter.end()


class ProfileBreakdownChart(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(180)
        self._profiles: tuple[ProfileDuration, ...] = ()

    def set_profiles(self, profiles: tuple[ProfileDuration, ...]) -> None:
        self._profiles = profiles[:5]
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        if not self._profiles:
            painter.setPen(QColor(COLORS["muted"]))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "この期間に悪い姿勢は記録されていません",
            )
            painter.end()
            return

        maximum = max(item.seconds for item in self._profiles)
        row_height = min(38.0, max(28.0, self.height() / max(1, len(self._profiles))))
        name_width = min(145.0, self.width() * 0.38)
        value_width = 58.0
        bar_left = name_width + 10.0
        bar_width = max(20.0, self.width() - bar_left - value_width - 8.0)
        for index, profile in enumerate(self._profiles):
            y = 8.0 + (index * row_height)
            painter.setPen(QColor(COLORS["text"]))
            painter.drawText(QRectF(0, y, name_width, 20), Qt.AlignmentFlag.AlignVCenter, profile.name)
            painter.setBrush(QColor(COLORS["line"]))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(QRectF(bar_left, y + 6, bar_width, 8), 4, 4)
            filled = bar_width * (profile.seconds / max(1.0, maximum))
            painter.setBrush(QColor(COLORS["danger"]))
            painter.drawRoundedRect(QRectF(bar_left, y + 6, filled, 8), 4, 4)
            painter.setPen(QColor(COLORS["muted"]))
            minutes = profile.seconds / 60.0
            value = f"{minutes:.0f}分" if minutes >= 1.0 else f"{profile.seconds:.0f}秒"
            painter.drawText(
                QRectF(bar_left + bar_width + 8, y, value_width, 20),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                value,
            )
        painter.end()
