"""
ui/theme.py -- Glassmorphism theme constants, stylesheet loader, and shared helpers.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QColor, QLinearGradient, QPainter
from PySide6.QtWidgets import QWidget

# -- Background gradient --
BG_DEEP   = "#0f0c29"
BG_MID    = "#302b63"
BG_LIGHT  = "#24243e"

# -- Accent colors --
ACCENT_VIOLET = "#8a65ff"
ACCENT_CYAN   = "#00d4ff"

# -- Confidence colors --
CONF_HIGH = "#00ffc6"  # teal
CONF_MED  = "#ffb347"  # amber
CONF_LOW  = "#ff6b8a"  # rose

# -- Text --
TEXT_PRIMARY   = "#f0eeff"
TEXT_SECONDARY = "#a89ec9"
TEXT_MUTED     = "#6b6490"

_CONF_HIGH_THRESH = 0.85
_CONF_MED_THRESH  = 0.55


def load_stylesheet() -> str:
    return (Path(__file__).parent / "theme.qss").read_text(encoding="utf-8")


def conf_qcolor(conf: float | None) -> QColor:
    if conf is None:
        return QColor(TEXT_MUTED)
    if conf >= _CONF_HIGH_THRESH:
        return QColor(CONF_HIGH)
    if conf >= _CONF_MED_THRESH:
        return QColor(CONF_MED)
    return QColor(CONF_LOW)


def conf_hex(conf: float) -> str:
    if conf >= _CONF_HIGH_THRESH:
        return CONF_HIGH
    if conf >= _CONF_MED_THRESH:
        return CONF_MED
    return CONF_LOW


class GlassContainer(QWidget):
    """Central widget that paints the deep-to-purple gradient background."""

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        gradient = QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0.0, QColor(BG_DEEP))
        gradient.setColorAt(0.5, QColor(BG_MID))
        gradient.setColorAt(1.0, QColor(BG_LIGHT))
        painter.fillRect(self.rect(), gradient)
