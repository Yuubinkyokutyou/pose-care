from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap


COLORS = {
    "canvas": "#EFF4F0",
    "surface": "#FBFDFC",
    "surface_high": "#EDF4EF",
    "line": "#C9D7CE",
    "text": "#17241C",
    "muted": "#5F6F66",
    "signal": "#1F7355",
    "amber": "#9A6729",
    "danger": "#B94D49",
    "blue": "#3D7088",
}


def make_app_icon(size: int = 64) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(COLORS["surface_high"]))
    painter.setPen(QPen(QColor(COLORS["signal"]), max(2, size // 18)))
    painter.drawRoundedRect(4, 4, size - 8, size - 8, size * 0.25, size * 0.25)
    painter.setPen(QPen(QColor(COLORS["text"]), max(2, size // 16), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    center = size // 2
    painter.drawLine(center, int(size * 0.26), center, int(size * 0.70))
    painter.drawEllipse(center - size // 14, int(size * 0.18), size // 7, size // 7)
    painter.setPen(QPen(QColor(COLORS["signal"]), max(2, size // 18), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    path = QPainterPath()
    path.moveTo(size * 0.27, size * 0.43)
    path.cubicTo(size * 0.39, size * 0.36, size * 0.42, size * 0.49, center, size * 0.47)
    path.cubicTo(size * 0.58, size * 0.45, size * 0.63, size * 0.36, size * 0.74, size * 0.43)
    painter.drawPath(path)
    painter.end()
    return QIcon(pixmap)


def configure_font(application) -> None:
    font = QFont("Segoe UI Variable Text", 10)
    if not font.exactMatch():
        font = QFont("Segoe UI", 10)
    application.setFont(font)
