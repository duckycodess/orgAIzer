"""
ui/theme.py -- Glassmorphism theme constants, stylesheet loader, and shared helpers.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QColor, QLinearGradient, QPainter
from PySide6.QtWidgets import QWidget

# -- Background gradient --
BG_DEEP   = "#06041a"
BG_MID    = "#120d30"
BG_LIGHT  = "#1a1245"

# -- Accent colors --
ACCENT_VIOLET = "#9d7dff"
ACCENT_CYAN   = "#00e5ff"

# -- Confidence colors --
CONF_HIGH = "#00e5ff"  # cyan
CONF_MED  = "#ffb347"  # amber
CONF_LOW  = "#ff6b9d"  # rose

# -- Text --
TEXT_PRIMARY   = "#ede9ff"
TEXT_SECONDARY = "#a89ec9"
TEXT_MUTED     = "#4e4875"

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
