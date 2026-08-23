from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap


COLORS = {
    "canvas": "#0B1220",
    "surface": "#121D2E",
    "surface_high": "#18263A",
    "line": "#27384F",
    "text": "#EDF4F5",
    "muted": "#92A3B8",
    "signal": "#35D0BA",
    "amber": "#F4B860",
    "danger": "#FF6B6B",
    "blue": "#60B8F4",
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


APP_STYLE = f"""
* {{
    color: {COLORS['text']};
    font-family: "Segoe UI Variable Text", "Segoe UI";
    outline: none;
}}
QWidget {{
    background: {COLORS['canvas']};
}}
QLabel {{
    background: transparent;
}}
QToolTip {{
    background: {COLORS['surface_high']};
    border: 1px solid {COLORS['line']};
    color: {COLORS['text']};
    padding: 6px;
}}
QFrame#navRail {{
    background: #09111E;
    border-right: 1px solid {COLORS['line']};
}}
QFrame#card, QFrame#settingsCard {{
    background: {COLORS['surface']};
    border: 1px solid {COLORS['line']};
    border-radius: 18px;
}}
QWidget#statisticsCard {{
    background: {COLORS['surface']};
    border: 1px solid {COLORS['line']};
    border-radius: 15px;
}}
QFrame#videoFrame {{
    background: #060B12;
    border: 1px solid {COLORS['line']};
    border-radius: 20px;
}}
QLabel#appName {{
    font-family: "Segoe UI Variable Display", "Segoe UI";
    font-size: 21px;
    font-weight: 700;
    letter-spacing: 1px;
}}
QLabel#pageTitle {{
    font-family: "Segoe UI Variable Display", "Segoe UI";
    font-size: 28px;
    font-weight: 700;
}}
QLabel#sectionTitle {{
    font-family: "Segoe UI Variable Display", "Segoe UI";
    font-size: 17px;
    font-weight: 650;
}}
QLabel#muted, QLabel.muted {{
    color: {COLORS['muted']};
}}
QLabel#eyebrow {{
    color: {COLORS['signal']};
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 2px;
}}
QLabel#metricValue {{
    font-family: "Cascadia Mono", "Consolas";
    font-size: 17px;
    font-weight: 600;
}}
QLabel#statisticsValue {{
    font-family: "Cascadia Mono", "Consolas";
    font-size: 25px;
    font-weight: 700;
}}
QPushButton {{
    background: {COLORS['surface_high']};
    border: 1px solid {COLORS['line']};
    border-radius: 10px;
    padding: 9px 15px;
    font-weight: 600;
}}
QPushButton:hover {{
    background: #20324A;
    border-color: #3A526F;
}}
QPushButton:pressed {{
    background: #152237;
}}
QPushButton:focus {{
    border-color: {COLORS['signal']};
}}
QPushButton#primaryButton {{
    background: {COLORS['signal']};
    border-color: {COLORS['signal']};
    color: #06221E;
}}
QPushButton#primaryButton:hover {{
    background: #5ADCC9;
}}
QPushButton#dangerButton {{
    color: {COLORS['danger']};
}}
QPushButton#navButton {{
    background: transparent;
    border: none;
    border-radius: 10px;
    color: {COLORS['muted']};
    padding: 11px 13px;
    text-align: left;
}}
QPushButton#navButton:hover {{
    background: {COLORS['surface']};
    color: {COLORS['text']};
}}
QPushButton#navButton:checked {{
    background: {COLORS['surface_high']};
    color: {COLORS['signal']};
    border-left: 3px solid {COLORS['signal']};
}}
QPushButton#periodButton {{
    background: transparent;
    color: {COLORS['muted']};
    border-radius: 8px;
    border: none;
    padding: 7px 14px;
}}
QPushButton#periodButton:checked {{
    background: {COLORS['surface_high']};
    color: {COLORS['signal']};
}}
QCheckBox {{
    spacing: 10px;
}}
QCheckBox::indicator {{
    width: 38px;
    height: 20px;
    border-radius: 10px;
    background: #29384C;
    border: 1px solid #3A4D65;
}}
QCheckBox::indicator:checked {{
    background: {COLORS['signal']};
    border-color: {COLORS['signal']};
}}
QLineEdit, QSpinBox, QDoubleSpinBox {{
    background: #0C1625;
    border: 1px solid {COLORS['line']};
    border-radius: 9px;
    padding: 8px 10px;
    selection-background-color: {COLORS['signal']};
    selection-color: #061B18;
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {COLORS['signal']};
}}
QSlider::groove:horizontal {{
    height: 4px;
    background: #2B3A4E;
    border-radius: 2px;
}}
QSlider::sub-page:horizontal {{
    background: {COLORS['signal']};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {COLORS['text']};
    border: 2px solid {COLORS['signal']};
    width: 16px;
    height: 16px;
    margin: -7px 0;
    border-radius: 9px;
}}
QProgressBar {{
    background: #27364A;
    border: none;
    border-radius: 4px;
    height: 8px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{
    background: {COLORS['signal']};
    border-radius: 4px;
}}
QScrollArea {{
    border: none;
    background: transparent;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: #34465E;
    border-radius: 4px;
    min-height: 28px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QDialog {{
    background: {COLORS['canvas']};
}}
"""
