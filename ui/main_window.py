"""
ui/main_window.py -- Main application window.

Layout: QTabWidget with 3 tabs:
  1. Pending Decisions  (shown first so users see actionable items immediately)
  2. History
  3. Settings

Features:
  - System tray icon (app keeps running when window is closed)
  - Status bar: watch folder path + warm-up progress indicator
  - Connects all Controller signals to UI updates
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QCloseEvent, QIcon, QPixmap, QColor
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QMessageBox,
    QStatusBar,
    QSystemTrayIcon,
    QTabWidget,
    QMenu,
    QWidget,
)

from app.controller import Controller
from ui.history_widget import HistoryWidget
from ui.pending_widget import PendingWidget
from ui.settings_widget import SettingsWidget


def _make_tray_icon() -> QIcon:
    """Create a simple colored square as a tray icon (no external asset needed)."""
    pixmap = QPixmap(16, 16)
    pixmap.fill(QColor("#2980b9"))
    return QIcon(pixmap)


class MainWindow(QMainWindow):
    """
    The top-level window for OrgAIzer.
    Owns the Controller and wires all signals to the UI.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("OrgAIzer — AI School File Sorter")
        self.setMinimumSize(780, 560)
        self.resize(960, 680)

        # Controller (backend)
        self._controller = Controller()

        # Build UI
        self._build_tabs()
        self._build_status_bar()
        self._build_tray()

        # Wire controller signals
        self._wire_signals()

        # Initial data load
        self._refresh_history()
        self._refresh_pending()
        self._update_status_bar()

        # Sync course names to PendingWidget
        course_names = self._controller._course_repo.get_course_names()
        self._pending.set_course_names(course_names)

        # Start watching
        self._controller.start_watching()

        # Status bar refresh timer (updates warm-up counter every 5s)
        self._status_timer = QTimer(self)
        self._status_timer.setInterval(5000)
        self._status_timer.timeout.connect(self._update_status_bar)
        self._status_timer.start()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_tabs(self) -> None:
        tabs = QTabWidget()
        tabs.setTabPosition(QTabWidget.TabPosition.North)

        self._pending = PendingWidget()
        self._history = HistoryWidget()
        self._settings_widget = SettingsWidget(self._controller.settings)

        tabs.addTab(self._pending, "Pending Decisions")
        tabs.addTab(self._history, "History")
        tabs.addTab(self._settings_widget, "Settings")

        self.setCentralWidget(tabs)
        self._tabs = tabs

    def _build_status_bar(self) -> None:
        bar = QStatusBar()
        self._watch_label = QLabel()
        self._warmup_label = QLabel()
        self._warmup_label.setStyleSheet("color: #f39c12; font-weight: bold;")
        bar.addWidget(self._watch_label)
        bar.addPermanentWidget(self._warmup_label)
        self.setStatusBar(bar)

    def _build_tray(self) -> None:
        self._tray = QSystemTrayIcon(_make_tray_icon(), self)
        self._tray.setToolTip("OrgAIzer — AI School File Sorter")

        menu = QMenu()
        show_action = QAction("Show", self)
        quit_action = QAction("Quit", self)
        show_action.triggered.connect(self._show_window)
        quit_action.triggered.connect(self._quit_app)
        menu.addAction(show_action)
        menu.addSeparator()
        menu.addAction(quit_action)

        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------

    def _wire_signals(self) -> None:
        c = self._controller

        # New files from controller
        c.file_classified.connect(self._on_file_classified)
        c.file_auto_moved.connect(self._on_file_auto_moved)
        c.file_status.connect(self._on_file_status)
        c.retrain_done.connect(self._on_retrain_done)

        # User decisions from PendingWidget
        self._pending.decision_made.connect(self._on_decision_made)

        # History undo
        self._history.undo_requested.connect(self._on_undo_requested)

        # Settings tab
        self._settings_widget.settings_changed.connect(self._on_settings_changed)
        self._settings_widget.rescan_requested.connect(self._on_rescan_requested)
        self._settings_widget.retrain_requested.connect(self._on_retrain_requested)

        # History tab refresh button
        self._history._refresh_btn.clicked.connect(self._refresh_history)

    # ------------------------------------------------------------------
    # Controller signal handlers
    # ------------------------------------------------------------------

    def _on_file_classified(self, event: dict) -> None:
        """New pending file arrived — add card and switch to Pending tab."""
        self._pending.add_pending(event)
        self._tabs.setCurrentWidget(self._pending)
        # Also show tray notification
        self._tray.showMessage(
            "New file to sort",
            f"{event.get('filename', '')} — {event.get('overall_confidence', 0):.0%} confidence",
            QSystemTrayIcon.MessageIcon.Information,
            3000,
        )
        self._refresh_history()

    def _on_file_auto_moved(self, event: dict) -> None:
        """File was auto-moved — update history tab."""
        self._refresh_history()
        self._tray.showMessage(
            "Auto-sorted",
            f"{event.get('filename', '')} → {event.get('course')}/{event.get('category')}",
            QSystemTrayIcon.MessageIcon.Information,
            2000,
        )

    def _on_file_status(self, event: dict) -> None:
        """Non-school file or other status update."""
        self._refresh_history()

    def _on_retrain_done(self) -> None:
        self._settings_widget.on_retrain_done()
        self._update_status_bar()

    # ------------------------------------------------------------------
    # User action handlers
    # ------------------------------------------------------------------

    def _on_decision_made(
        self, event_id: int, course: str, category: str, action: str
    ) -> None:
        self._controller.handle_user_decision(event_id, course, category, action)
        self._refresh_history()
        self._update_status_bar()
        self._settings_widget.update_warmup_display()

    def _on_undo_requested(self, event_id: int) -> None:
        success = self._controller.undo_move(event_id)
        if success:
            self._history.mark_undone(event_id)
            self._tray.showMessage(
                "Undo successful",
                "File returned to Downloads.",
                QSystemTrayIcon.MessageIcon.Information,
                2000,
            )
        else:
            QMessageBox.warning(
                self,
                "Undo Failed",
                "Could not undo: the file may have been moved or deleted already.",
            )

    def _on_settings_changed(self) -> None:
        self._controller.save_settings()
        # Restart watcher with potentially new folder
        self._controller.stop_watching()
        self._controller.start_watching()
        self._update_status_bar()

    def _on_rescan_requested(self, school_root: str) -> None:
        count = self._controller.scan_course_folders(school_root)
        self._settings_widget.on_rescan_done(count)
        # Update course names in pending widget
        course_names = self._controller._course_repo.get_course_names()
        self._pending.set_course_names(course_names)

    def _on_retrain_requested(self) -> None:
        self._controller.trigger_retrain()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _refresh_history(self) -> None:
        events = self._controller.get_history()
        self._history.populate_events(events)

    def _refresh_pending(self) -> None:
        pending = self._controller.get_pending()
        self._pending.load_pending(pending)

    def _update_status_bar(self) -> None:
        folder = self._controller.settings.effective_watch_folder
        self._watch_label.setText(f"Watching: {folder}")

        labeled, required = self._controller.get_warmup_status()
        if self._controller.settings.warmup_active:
            self._warmup_label.setText(
                f"Warm-up: {labeled}/{required} labeled"
            )
        else:
            self._warmup_label.setText("Auto-move: ON")
            self._warmup_label.setStyleSheet("color: #2ecc71; font-weight: bold;")

    # ------------------------------------------------------------------
    # Window lifecycle
    # ------------------------------------------------------------------

    def closeEvent(self, event: QCloseEvent) -> None:
        """Minimize to tray instead of quitting."""
        event.ignore()
        self.hide()
        self._tray.showMessage(
            "OrgAIzer",
            "Still running in the background. Right-click the tray icon to quit.",
            QSystemTrayIcon.MessageIcon.Information,
            2000,
        )

    def _show_window(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()

    def _quit_app(self) -> None:
        self._controller.shutdown()
        self._tray.hide()
        QApplication.quit()

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._show_window()
