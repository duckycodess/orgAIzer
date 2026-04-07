"""
ui/history_widget.py -- History tab: table of all file events with undo.

Columns: Time | Filename | Course | Category | Confidence | Action | Undo
Color coding: green >= HIGH_THRESHOLD, yellow >= MEDIUM_THRESHOLD, red below.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
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
    "skipped": "Skipped",
    "undone": "Undone",
    "not_school": "Not school",
    "pending": "Pending",
    "error": "Error",
}

_CONF_HIGH = 0.85
_CONF_MED = 0.55


def _conf_color(conf: float | None) -> QColor:
    if conf is None:
        return QColor("#888888")
    if conf >= _CONF_HIGH:
        return QColor("#2ecc71")   # green
    if conf >= _CONF_MED:
        return QColor("#f39c12")   # amber
    return QColor("#e74c3c")       # red


def _conf_label(conf: float | None) -> str:
    if conf is None:
        return "—"
    return f"{conf:.0%}"


class HistoryWidget(QWidget):
    """Shows the full event log with undo buttons on moved rows."""

    undo_requested = Signal(int)   # event_id

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # Header row
        header = QHBoxLayout()
        title = QLabel("File History")
        font = QFont()
        font.setPointSize(12)
        font.setBold(True)
        title.setFont(font)
        header.addWidget(title)
        header.addStretch()
        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.setFixedWidth(80)
        header.addWidget(self._refresh_btn)
        layout.addLayout(header)

        # Table
        self._table = QTableWidget(0, 7)
        self._table.setHorizontalHeaderLabels([
            "Time", "Filename", "Course", "Category", "Confidence", "Action", "Undo"
        ])
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        layout.addWidget(self._table)

        self._refresh_btn.clicked.connect(self.refresh_requested)

    def refresh_requested(self) -> None:
        """Signal parent to reload events from DB."""
        self.load_events([])  # caller should call populate_events instead

    def populate_events(self, events: list[dict]) -> None:
        """Fill the table with a list of event dicts from FileEventRepo."""
        self._table.setRowCount(0)
        for evt in events:
            self._add_row(evt)

    def prepend_event(self, evt: dict) -> None:
        """Add a single new event at the top of the table."""
        self._table.insertRow(0)
        self._fill_row(0, evt)

    def _add_row(self, evt: dict) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._fill_row(row, evt)

    def _fill_row(self, row: int, evt: dict) -> None:
        event_id = evt.get("id")

        # Timestamp (shorten to HH:MM:SS date part)
        ts = str(evt.get("timestamp", ""))
        if "T" in ts:
            date, time_ = ts.split("T", 1)
            display_ts = f"{date}\n{time_}"
        else:
            display_ts = ts

        overall_conf = evt.get("school_confidence")
        if evt.get("course_confidence") is not None:
            all_confs = [
                c for c in [
                    evt.get("school_confidence"),
                    evt.get("course_confidence"),
                    evt.get("category_confidence"),
                ] if c is not None
            ]
            if all_confs:
                overall_conf = min(all_confs)

        action = evt.get("user_action") or evt.get("stage") or "—"
        action_label = _ACTION_LABELS.get(action, action)

        course = evt.get("final_course") or evt.get("course_predicted") or "—"
        category = evt.get("final_category") or evt.get("category_predicted") or "—"

        cells = [
            display_ts,
            evt.get("filename", ""),
            course,
            category,
            _conf_label(overall_conf),
            action_label,
        ]
        for col, text in enumerate(cells):
            item = QTableWidgetItem(str(text))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if col == 1:  # filename left-aligned
                item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            if col == 4:  # confidence — color it
                item.setForeground(_conf_color(overall_conf))
                font = QFont()
                font.setBold(True)
                item.setFont(font)
            self._table.setItem(row, col, item)

        # Undo button — only for moved events that haven't been undone
        stage = evt.get("stage", "")
        if stage == "moved" and action != "undone":
            btn = QPushButton("Undo")
            btn.setFixedWidth(60)
            btn.setProperty("event_id", event_id)
            btn.clicked.connect(lambda checked=False, eid=event_id: self.undo_requested.emit(eid))
            self._table.setCellWidget(row, 6, btn)
        else:
            self._table.setItem(row, 6, QTableWidgetItem(""))

    def mark_undone(self, event_id: int) -> None:
        """Update a row's action and remove its Undo button after successful undo."""
        for row in range(self._table.rowCount()):
            btn = self._table.cellWidget(row, 6)
            if btn and btn.property("event_id") == event_id:
                self._table.setItem(row, 5, QTableWidgetItem("Undone"))
                self._table.removeCellWidget(row, 6)
                break
