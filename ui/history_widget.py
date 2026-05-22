"""
ui/history_widget.py -- History tab with undo support.

Columns: Time | Filename | Subject | Confidence | Action | Undo
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont

from ui.theme import ACCENT_VIOLET, CONF_LOW, conf_qcolor
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

_ACTION_LABELS = {
    "auto": "Auto-moved",
    "accepted": "Accepted",
    "corrected": "Corrected",
    "corrected_not_school": "Corrected (was Not School)",
    "skipped": "Skipped",
    "undone": "Undone",
    "not_school": "Not school",
    "pending": "Pending",
    "error": "Error",
}

def _conf_label(conf: float | None) -> str:
    if conf is None:
        return "-"
    return f"{conf:.0%}"


def _normalize_subject_input(subject: str) -> str:
    return " ".join(subject.strip().split())


def _is_valid_subject_input(subject: str) -> bool:
    if not subject:
        return False
    if subject in (".", ".."):
        return False
    if "/" in subject or "\\" in subject:
        return False
    return True


class _SubjectPickerDialog(QDialog):
    """Dialog to pick or type a subject name."""

    def __init__(self, subject_names: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Choose Subject")
        self.setModal(True)
        self.setMinimumWidth(400)

        layout = QFormLayout(self)
        self._combo = QComboBox()
        self._combo.setEditable(True)
        self._combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._combo.addItems(sorted(subject_names))
        self._combo.setEditText("")
        self._combo.lineEdit().setPlaceholderText("Choose an existing subject or type a new one")

        layout.addRow("Subject:", self._combo)

        hint = QLabel("New subject names are allowed.")
        hint.setObjectName("HintLabel")
        layout.addRow("", hint)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

        self._update_ok_state()
        self._combo.lineEdit().textChanged.connect(self._update_ok_state)

    def _update_ok_state(self) -> None:
        text = self._combo.lineEdit().text()
        normalized = _normalize_subject_input(text)
        ok_btn = self.findChild(QPushButton)
        if ok_btn is None:
            for btn in self.findChildren(QPushButton):
                if btn.text() == "OK":
                    ok_btn = btn
                    break
        if ok_btn:
            ok_btn.setEnabled(_is_valid_subject_input(normalized))

    def selected_subject(self) -> str:
        return _normalize_subject_input(self._combo.lineEdit().text())


class HistoryWidget(QWidget):
    """Shows the full event log with undo buttons on moved rows."""

    undo_requested = Signal(int)
    mark_as_school_requested = Signal(int, str)  # (event_id, subject)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._subject_names: list[str] = []
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        header = QHBoxLayout()
        title = QLabel("File History")
        title.setObjectName("SectionTitle")
        header.addWidget(title)
        header.addStretch()
        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.setFixedWidth(80)
        self._refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(138, 101, 255, 0.25);
                border: 1px solid {ACCENT_VIOLET};
                border-radius: 12px;
                color: #c4b0ff;
                font-weight: 600;
                padding: 4px 12px;
            }}
            QPushButton:hover {{ background: rgba(138, 101, 255, 0.45); }}
        """)
        header.addWidget(self._refresh_btn)
        layout.addLayout(header)

        self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels([
            "Time", "Filename", "Subject", "Confidence", "Action", "Actions"
        ])
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(5, 150)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(36)
        layout.addWidget(self._table)

        self._refresh_btn.clicked.connect(self.refresh_requested)

    def refresh_requested(self) -> None:
        self.populate_events([])

    def set_subject_names(self, names: list[str]) -> None:
        self._subject_names = list(names)

    def populate_events(self, events: list[dict]) -> None:
        self._table.setRowCount(0)
        for evt in events:
            self._add_row(evt)

    def _add_row(self, evt: dict) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._fill_row(row, evt)

    def _fill_row(self, row: int, evt: dict) -> None:
        event_id = evt.get("id")
        ts = str(evt.get("timestamp", ""))
        if "T" in ts:
            date, time_ = ts.split("T", 1)
            display_ts = f"{date}\n{time_}"
        else:
            display_ts = ts

        conf_values = [
            value for value in [
                evt.get("school_confidence"),
                evt.get("course_confidence"),
            ] if value is not None
        ]
        overall_conf = min(conf_values) if conf_values else evt.get("school_confidence")

        action = evt.get("user_action") or evt.get("stage") or "-"
        action_label = _ACTION_LABELS.get(action, action)
        subject = evt.get("final_course") or evt.get("course_predicted") or "-"

        cells = [
            display_ts,
            evt.get("filename", ""),
            subject,
            _conf_label(overall_conf),
            action_label,
        ]
        for col, text in enumerate(cells):
            item = QTableWidgetItem(str(text))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if col == 1:
                item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            if col == 3:
                item.setForeground(conf_qcolor(overall_conf))
                font = QFont()
                font.setBold(True)
                item.setFont(font)
            self._table.setItem(row, col, item)

        stage = evt.get("stage", "")
        if stage == "moved" and action != "undone":
            btn = QPushButton("Undo")
            btn.setFixedWidth(80)
            btn.setProperty("event_id", event_id)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: rgba(255, 107, 138, 0.30);
                    border: 1px solid {CONF_LOW};
                    border-radius: 8px;
                    color: {CONF_LOW};
                    font-weight: 600;
                    padding: 3px 6px;
                }}
                QPushButton:hover {{
                    background: rgba(255, 107, 138, 0.50);
                }}
            """)
            btn.clicked.connect(
                lambda checked=False, eid=event_id: self.undo_requested.emit(eid)
            )
            self._table.setCellWidget(row, 5, btn)
        elif stage == "not_school" and evt.get("user_action") is None:
            btn = QPushButton("Mark as School")
            btn.setFixedWidth(140)
            btn.setProperty("event_id", event_id)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: rgba(138, 101, 255, 0.30);
                    border: 1px solid {ACCENT_VIOLET};
                    border-radius: 8px;
                    color: #c4b0ff;
                    font-weight: 600;
                    padding: 3px 6px;
                    font-size: 11px;
                }}
                QPushButton:hover {{
                    background: rgba(138, 101, 255, 0.50);
                }}
            """)
            btn.clicked.connect(
                lambda checked=False, eid=event_id: self._on_mark_as_school_clicked(eid)
            )
            self._table.setCellWidget(row, 5, btn)
        else:
            self._table.setItem(row, 5, QTableWidgetItem(""))

    def mark_undone(self, event_id: int) -> None:
        for row in range(self._table.rowCount()):
            btn = self._table.cellWidget(row, 5)
            if btn and btn.property("event_id") == event_id:
                self._table.setItem(row, 4, QTableWidgetItem("Undone"))
                self._table.removeCellWidget(row, 5)
                break

    def _on_mark_as_school_clicked(self, event_id: int) -> None:
        dlg = _SubjectPickerDialog(self._subject_names, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.mark_as_school_requested.emit(event_id, dlg.selected_subject())
