"""
ui/pending_widget.py -- Pending decisions tab.

Each pending file shows as a card with:
  - filename
  - predicted course + category
  - overall confidence bar + color
  - short AI reason ("Matched course code CS180 in filename")
  - Accept / Change / Skip buttons

"Change" opens a dialog with course and category dropdowns.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.settings import CATEGORY_LABELS

_CONF_HIGH = 0.85
_CONF_MED = 0.55


def _conf_color_hex(conf: float) -> str:
    if conf >= _CONF_HIGH:
        return "#2ecc71"
    if conf >= _CONF_MED:
        return "#f39c12"
    return "#e74c3c"


def _conf_label(conf: float) -> str:
    if conf >= _CONF_HIGH:
        return f"High confidence ({conf:.0%})"
    if conf >= _CONF_MED:
        return f"Medium confidence ({conf:.0%}) — please review"
    return f"Low confidence ({conf:.0%}) — please choose"


class _ChangeDialog(QDialog):
    """Dialog that lets the user pick a different course and category."""

    def __init__(
        self,
        course_names: list[str],
        current_course: str,
        current_category: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Change Destination")
        self.setMinimumWidth(320)

        layout = QFormLayout(self)

        self._course_combo = QComboBox()
        self._course_combo.addItems(course_names)
        idx = self._course_combo.findText(current_course)
        if idx >= 0:
            self._course_combo.setCurrentIndex(idx)
        layout.addRow("Course:", self._course_combo)

        self._cat_combo = QComboBox()
        self._cat_combo.addItems(CATEGORY_LABELS)
        cidx = self._cat_combo.findText(current_category)
        if cidx >= 0:
            self._cat_combo.setCurrentIndex(cidx)
        layout.addRow("Category:", self._cat_combo)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def selected_course(self) -> str:
        return self._course_combo.currentText()

    def selected_category(self) -> str:
        return self._cat_combo.currentText()


class _PendingCard(QFrame):
    """A single card representing one pending file decision."""

    accepted = Signal(int, str, str)   # event_id, course, category
    changed = Signal(int, str, str)    # event_id, new_course, new_category
    skipped = Signal(int)              # event_id

    def __init__(
        self,
        event: dict,
        course_names: list[str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._event = event
        self._course_names = course_names
        self._event_id = event["event_id"]
        self._course = event.get("course", "Unknown")
        self._category = event.get("category", "Others")
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Raised)
        self.setStyleSheet("""
            _PendingCard, QFrame {
                background: #2b2b2b;
                border-radius: 6px;
                border: 1px solid #444;
            }
        """)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        main = QVBoxLayout(self)
        main.setSpacing(6)

        # --- Filename ---
        filename = self._event.get("filename", "unknown")
        name_label = QLabel(filename)
        name_font = QFont()
        name_font.setPointSize(11)
        name_font.setBold(True)
        name_label.setFont(name_font)
        name_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        main.addWidget(name_label)

        # --- Prediction line ---
        conf = self._event.get("overall_confidence", 0.0)
        color = _conf_color_hex(conf)
        dest_text = f"→  <b>{self._course}</b> / <b>{self._category}</b>"
        dest_label = QLabel(dest_text)
        dest_label.setTextFormat(Qt.TextFormat.RichText)
        main.addWidget(dest_label)

        # --- Confidence bar ---
        conf_row = QHBoxLayout()
        conf_bar = QProgressBar()
        conf_bar.setRange(0, 100)
        conf_bar.setValue(int(conf * 100))
        conf_bar.setFixedHeight(12)
        conf_bar.setTextVisible(False)
        conf_bar.setStyleSheet(f"""
            QProgressBar {{ border-radius: 4px; background: #555; }}
            QProgressBar::chunk {{ background: {color}; border-radius: 4px; }}
        """)
        conf_row.addWidget(conf_bar, stretch=3)
        conf_row.addWidget(QLabel(_conf_label(conf)), stretch=5)
        main.addLayout(conf_row)

        # --- AI reason ---
        reason = self._event.get("reason", "")
        if reason:
            # Show only the most relevant part (first pipe-separated segment)
            short_reason = reason.split("|")[1].strip() if "|" in reason else reason
            reason_label = QLabel(f'<i style="color:#aaa">{short_reason}</i>')
            reason_label.setTextFormat(Qt.TextFormat.RichText)
            reason_label.setWordWrap(True)
            main.addWidget(reason_label)

        # --- Buttons ---
        btn_row = QHBoxLayout()
        accept_btn = QPushButton("Accept")
        accept_btn.setStyleSheet("QPushButton { background: #27ae60; color: white; border-radius: 4px; padding: 4px 12px; }")
        change_btn = QPushButton("Change")
        change_btn.setStyleSheet("QPushButton { background: #2980b9; color: white; border-radius: 4px; padding: 4px 12px; }")
        skip_btn = QPushButton("Skip")
        skip_btn.setStyleSheet("QPushButton { background: #7f8c8d; color: white; border-radius: 4px; padding: 4px 12px; }")

        accept_btn.clicked.connect(self._on_accept)
        change_btn.clicked.connect(self._on_change)
        skip_btn.clicked.connect(self._on_skip)

        btn_row.addWidget(accept_btn)
        btn_row.addWidget(change_btn)
        btn_row.addWidget(skip_btn)
        btn_row.addStretch()
        main.addLayout(btn_row)

    def _on_accept(self) -> None:
        self.accepted.emit(self._event_id, self._course, self._category)
        self.deleteLater()

    def _on_change(self) -> None:
        dlg = _ChangeDialog(
            self._course_names,
            self._course,
            self._category,
            parent=self,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_course = dlg.selected_course()
            new_cat = dlg.selected_category()
            self.changed.emit(self._event_id, new_course, new_cat)
            self.deleteLater()

    def _on_skip(self) -> None:
        self.skipped.emit(self._event_id)
        self.deleteLater()


class PendingWidget(QWidget):
    """
    Scrollable list of pending file decision cards.
    Emits signals with (event_id, final_course, final_category) for accepted/changed,
    and (event_id,) for skipped.
    """

    decision_made = Signal(int, str, str, str)  # event_id, course, category, action

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._course_names: list[str] = []
        self._setup_ui()

    def _setup_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)

        title = QLabel("Pending Decisions")
        font = QFont()
        font.setPointSize(12)
        font.setBold(True)
        title.setFont(font)
        outer.addWidget(title)

        self._empty_label = QLabel("No pending files — everything is sorted!")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet("color: #888; font-style: italic;")
        outer.addWidget(self._empty_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        container = QWidget()
        self._cards_layout = QVBoxLayout(container)
        self._cards_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._cards_layout.setSpacing(8)
        scroll.setWidget(container)
        outer.addWidget(scroll)

    def set_course_names(self, names: list[str]) -> None:
        self._course_names = names

    def add_pending(self, event: dict) -> None:
        """Add a new pending card to the top of the list."""
        self._empty_label.hide()
        card = _PendingCard(event, self._course_names, parent=self)
        card.accepted.connect(
            lambda eid, c, cat: self.decision_made.emit(eid, c, cat, "accepted")
        )
        card.changed.connect(
            lambda eid, c, cat: self.decision_made.emit(eid, c, cat, "corrected")
        )
        card.skipped.connect(
            lambda eid: self.decision_made.emit(eid, "", "", "skipped")
        )
        self._cards_layout.insertWidget(0, card)

    def load_pending(self, events: list[dict]) -> None:
        """Replace all pending cards from a list of event dicts."""
        # Clear existing cards
        while self._cards_layout.count():
            item = self._cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not events:
            self._empty_label.show()
            return

        self._empty_label.hide()
        for evt in events:
            # Adapt DB event dict to the card's expected format
            card_event = {
                "event_id": evt["id"],
                "filename": evt.get("filename", ""),
                "original_path": evt.get("original_path", ""),
                "course": evt.get("course_predicted", "Unknown"),
                "category": evt.get("category_predicted", "Others"),
                "overall_confidence": min(filter(
                    lambda x: x is not None,
                    [
                        evt.get("school_confidence"),
                        evt.get("course_confidence"),
                        evt.get("category_confidence"),
                    ],
                ), default=0.0),
                "reason": evt.get("prediction_reason", ""),
            }
            card = _PendingCard(card_event, self._course_names, parent=self)
            card.accepted.connect(
                lambda eid, c, cat: self.decision_made.emit(eid, c, cat, "accepted")
            )
            card.changed.connect(
                lambda eid, c, cat: self.decision_made.emit(eid, c, cat, "corrected")
            )
            card.skipped.connect(
                lambda eid: self.decision_made.emit(eid, "", "", "skipped")
            )
            self._cards_layout.addWidget(card)
