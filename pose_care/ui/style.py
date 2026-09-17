from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QFont, QIcon


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


def make_app_icon() -> QIcon:
    """Load the same multi-resolution artwork used by the Windows executable."""
    return QIcon(str(Path(__file__).parents[1] / "assets" / "pose-care.ico"))


def configure_font(application) -> None:
    font = QFont("Segoe UI Variable Text", 10)
    if not font.exactMatch():
        font = QFont("Segoe UI", 10)
    application.setFont(font)
