"""
ui/pending_widget.py -- Pending decisions tab.

Each pending file shows:
  - filename
  - predicted subject
  - overall confidence
  - short AI reason
  - Accept / Change / Skip actions
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont

from ui.theme import TEXT_SECONDARY, conf_hex
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

_CONF_HIGH = 0.85
_CONF_MED = 0.55


def _normalize_subject_input(subject: str) -> str:
    return " ".join(subject.strip().split())


def _is_valid_subject_input(subject: str) -> bool:
    normalized = _normalize_subject_input(subject)
    if not normalized:
        return False
    if normalized in {".", ".."}:
        return False
    return "/" not in normalized and "\\" not in normalized


def _conf_label(conf: float) -> str:
    if conf >= _CONF_HIGH:
        return f"High confidence ({conf:.0%})"
    if conf >= _CONF_MED:
        return f"Medium confidence ({conf:.0%}), please review"
    return f"Low confidence ({conf:.0%}), please choose"


class _ChangeDialog(QDialog):
    """Dialog that lets the user pick or type a different subject."""

    def __init__(
        self,
        subject_names: list[str],
        current_subject: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Change Destination")
        self.setMinimumWidth(320)

        layout = QFormLayout(self)

        self._subject_combo = QComboBox()
        self._subject_combo.setEditable(True)
        self._subject_combo.addItems(subject_names)
        self._subject_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        initial_subject = (
            ""
            if _normalize_subject_input(current_subject) in {"", "Unknown"}
            else _normalize_subject_input(current_subject)
        )
        self._subject_combo.setEditText(initial_subject)
        self._subject_combo.lineEdit().setPlaceholderText(
            "Choose an existing subject or type a new one"
        )
        layout.addRow("Subject:", self._subject_combo)

        hint = QLabel("New subject names are allowed. Example: STS or Discrete Math")
        hint.setObjectName("HintLabel")
        hint.setWordWrap(True)
        layout.addRow("", hint)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

        self._subject_combo.lineEdit().textChanged.connect(self._update_ok_state)
        self._update_ok_state()

    def _update_ok_state(self) -> None:
        self._ok_button.setEnabled(
            _is_valid_subject_input(self._subject_combo.currentText())
        )

    def selected_subject(self) -> str:
        return _normalize_subject_input(self._subject_combo.currentText())


class _PendingCard(QFrame):
    """A single card representing one pending file decision."""

    accepted = Signal(int, str)
    changed = Signal(int, str)
    skipped = Signal(int)

    def __init__(
        self,
        event: dict,
        subject_names: list[str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._event = event
        self._subject_names = subject_names
        self._event_id = event["event_id"]
        self._subject = event.get("subject", "Unknown")
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Raised)
        self.setObjectName("PendingCard")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        main = QVBoxLayout(self)
        main.setSpacing(6)

        filename = self._event.get("filename", "unknown")
        name_label = QLabel(filename)
        name_font = QFont()
        name_font.setPointSize(11)
        name_font.setBold(True)
        name_label.setFont(name_font)
        name_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        main.addWidget(name_label)

        conf = self._event.get("overall_confidence", 0.0)
        subject_label = QLabel(f"->  <b>{self._subject}</b>")
        subject_label.setTextFormat(Qt.TextFormat.RichText)
        main.addWidget(subject_label)

        conf_row = QHBoxLayout()
        color = conf_hex(conf)
        conf_bar = QProgressBar()
        conf_bar.setRange(0, 100)
        conf_bar.setValue(int(conf * 100))
        conf_bar.setFixedHeight(10)
        conf_bar.setTextVisible(False)
        conf_bar.setStyleSheet(
            f"QProgressBar::chunk {{ background: {color}; border-radius: 6px; }}"
        )
        conf_row.addWidget(conf_bar, stretch=3)
        conf_row.addWidget(QLabel(_conf_label(conf)), stretch=5)
        main.addLayout(conf_row)

        reason = self._event.get("reason", "")
        if reason:
            short_reason = reason.split("|")[-1].strip()
            reason_label = QLabel(f'<i style="color:{TEXT_SECONDARY}">{short_reason}</i>')
            reason_label.setTextFormat(Qt.TextFormat.RichText)
            reason_label.setWordWrap(True)
            main.addWidget(reason_label)

        btn_row = QHBoxLayout()
        accept_btn = QPushButton("Accept")
        accept_btn.setProperty("role", "accept")
        change_btn = QPushButton("Change")
        change_btn.setProperty("role", "change")
        skip_btn = QPushButton("Skip")
        skip_btn.setProperty("role", "skip")

        valid_subject = bool(self._subject and self._subject != "Unknown")
        accept_btn.setEnabled(valid_subject)
        accept_btn.clicked.connect(self._on_accept)
        change_btn.clicked.connect(self._on_change)
        skip_btn.clicked.connect(self._on_skip)

        btn_row.addWidget(accept_btn)
        btn_row.addWidget(change_btn)
        btn_row.addWidget(skip_btn)
        btn_row.addStretch()
        main.addLayout(btn_row)

    def _on_accept(self) -> None:
        self.accepted.emit(self._event_id, self._subject)
        self.deleteLater()

    def _on_change(self) -> None:
        dlg = _ChangeDialog(self._subject_names, self._subject, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.changed.emit(self._event_id, dlg.selected_subject())
            self.deleteLater()

    def _on_skip(self) -> None:
        self.skipped.emit(self._event_id)
        self.deleteLater()


class PendingWidget(QWidget):
    """Scrollable list of pending file decisions."""

    decision_made = Signal(int, str, str)  # event_id, subject, action

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._subject_names: list[str] = []
        self._setup_ui()

    def _setup_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)

        title = QLabel("Pending Decisions")
        title.setObjectName("SectionTitle")
        outer.addWidget(title)

        self._empty_label = QLabel("No pending files. Everything is sorted!")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setObjectName("HintLabel")
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

    def set_subject_names(self, names: list[str]) -> None:
        self._subject_names = names

    def add_pending(self, event: dict) -> None:
        self._empty_label.hide()
        card = _PendingCard(event, self._subject_names, parent=self)
        card.accepted.connect(
            lambda eid, subject: self.decision_made.emit(eid, subject, "accepted")
        )
        card.changed.connect(
            lambda eid, subject: self.decision_made.emit(eid, subject, "corrected")
        )
        card.skipped.connect(
            lambda eid: self.decision_made.emit(eid, "", "skipped")
        )
        self._cards_layout.insertWidget(0, card)

    def load_pending(self, events: list[dict]) -> None:
        while self._cards_layout.count():
            item = self._cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not events:
            self._empty_label.show()
            return

        self._empty_label.hide()
        for evt in events:
            conf_values = [
                value for value in [
                    evt.get("school_confidence"),
                    evt.get("course_confidence"),
                ] if value is not None
            ]
            card_event = {
                "event_id": evt["id"],
                "filename": evt.get("filename", ""),
                "original_path": evt.get("original_path", ""),
                "subject": evt.get("course_predicted", "Unknown"),
                "overall_confidence": min(conf_values) if conf_values else 0.0,
                "reason": evt.get("prediction_reason", ""),
            }
            card = _PendingCard(card_event, self._subject_names, parent=self)
            card.accepted.connect(
                lambda eid, subject: self.decision_made.emit(eid, subject, "accepted")
            )
            card.changed.connect(
                lambda eid, subject: self.decision_made.emit(eid, subject, "corrected")
            )
            card.skipped.connect(
                lambda eid: self.decision_made.emit(eid, "", "skipped")
            )
            self._cards_layout.addWidget(card)
