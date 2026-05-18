"""
ui/main_window.py -- Main application window.

Layout:
  1. Pending Decisions
  2. History
  3. Settings
"""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtGui import QAction, QCloseEvent, QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QStatusBar,
    QSystemTrayIcon,
    QTabWidget,
)

from app.controller import Controller
from ui.history_widget import HistoryWidget
from ui.pending_widget import PendingWidget
from ui.settings_widget import SettingsWidget


def _make_tray_icon() -> QIcon:
    pixmap = QPixmap(16, 16)
    pixmap.fill(QColor("#2980b9"))
    return QIcon(pixmap)


class MainWindow(QMainWindow):
    """Top-level window for OrgAIzer."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("OrgAIzer -- AI School Subject Sorter")
        self.setMinimumSize(780, 560)
        self.resize(960, 680)

        self._controller = Controller()

        self._build_tabs()
        self._build_status_bar()
        self._build_tray()
        self._wire_signals()

        self._refresh_history()
        self._refresh_pending()
        self._update_status_bar()
        subject_names = self._controller.get_subject_names()
        self._pending.set_subject_names(subject_names)
        self._history.set_subject_names(subject_names)

        self._controller.start_watching()

        self._status_timer = QTimer(self)
        self._status_timer.setInterval(5000)
        self._status_timer.timeout.connect(self._update_status_bar)
        self._status_timer.start()

    def _build_tabs(self) -> None:
        self._tabs = QTabWidget()
        self._pending = PendingWidget()
        self._history = HistoryWidget()
        self._settings_widget = SettingsWidget(self._controller.settings)

        self._tabs.addTab(self._pending, "Pending Decisions")
        self._tabs.addTab(self._history, "History")
        self._tabs.addTab(self._settings_widget, "Settings")
        self.setCentralWidget(self._tabs)

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
        self._tray.setToolTip("OrgAIzer -- AI School Subject Sorter")

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

    def _wire_signals(self) -> None:
        controller = self._controller
        controller.file_classified.connect(self._on_file_classified)
        controller.file_auto_moved.connect(self._on_file_auto_moved)
        controller.file_status.connect(self._on_file_status)
        controller.retrain_done.connect(self._on_retrain_done)

        self._pending.decision_made.connect(self._on_decision_made)
        self._history.undo_requested.connect(self._on_undo_requested)
        self._history.mark_as_school_requested.connect(self._on_mark_as_school)
        self._settings_widget.settings_changed.connect(self._on_settings_changed)
        self._settings_widget.rescan_requested.connect(self._on_rescan_requested)
        self._settings_widget.retrain_requested.connect(self._on_retrain_requested)
        self._history._refresh_btn.clicked.connect(self._refresh_history)

    def _on_file_classified(self, event: dict) -> None:
        self._pending.add_pending(event)
        self._tabs.setCurrentWidget(self._pending)
        self._tray.showMessage(
            "New file to sort",
            f"{event.get('filename', '')} -- {event.get('overall_confidence', 0):.0%} confidence",
            QSystemTrayIcon.MessageIcon.Information,
            3000,
        )
        self._refresh_history()

    def _on_file_auto_moved(self, event: dict) -> None:
        self._refresh_history()
        self._tray.showMessage(
            "Auto-sorted",
            f"{event.get('filename', '')} -> {event.get('subject')}",
            QSystemTrayIcon.MessageIcon.Information,
            2000,
        )

    def _on_file_status(self, event: dict) -> None:
        self._refresh_history()

    def _on_retrain_done(self) -> None:
        self._settings_widget.on_retrain_done()
        self._update_status_bar()

    def _on_decision_made(self, event_id: int, subject: str, action: str) -> None:
        dest_path = self._controller.handle_user_decision(event_id, subject, action)
        if action != "skipped" and dest_path is None:
            QMessageBox.warning(
                self,
                "Could Not Sort File",
                "The file could not be moved. Check that the School root is set and the subject name is valid.",
            )
        self._refresh_history()
        subject_names = self._controller.get_subject_names()
        self._pending.set_subject_names(subject_names)
        self._history.set_subject_names(subject_names)
        self._refresh_pending()
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
            return

        QMessageBox.warning(
            self,
            "Undo Failed",
            "Could not undo: the file may have been moved or deleted already.",
        )

    def _on_mark_as_school(self, event_id: int, subject: str) -> None:
        dest_path = self._controller.handle_mark_as_school(event_id, subject)
        if dest_path is None:
            QMessageBox.information(
                self,
                "Marked as School",
                "Training sample recorded. File could not be moved (missing or no School root set).",
            )
        self._refresh_history()
        subject_names = self._controller.get_subject_names()
        self._pending.set_subject_names(subject_names)
        self._history.set_subject_names(subject_names)
        self._update_status_bar()
        self._settings_widget.update_warmup_display()

    def _on_settings_changed(self) -> None:
        self._controller.save_settings()
        self._controller.stop_watching()
        self._controller.start_watching()
        self._update_status_bar()

    def _on_rescan_requested(self, school_root: str) -> None:
        count = self._controller.scan_subject_folders(school_root)
        self._settings_widget.on_rescan_done(count)
        subject_names = self._controller.get_subject_names()
        self._pending.set_subject_names(subject_names)
        self._history.set_subject_names(subject_names)
        self._refresh_pending()

    def _on_retrain_requested(self) -> None:
        self._controller.trigger_retrain()

    def _refresh_history(self) -> None:
        self._history.populate_events(self._controller.get_history())

    def _refresh_pending(self) -> None:
        self._pending.load_pending(self._controller.get_pending())

    def _update_status_bar(self) -> None:
        folder = self._controller.settings.effective_watch_folder
        self._watch_label.setText(f"Watching: {folder}")

        labeled, required = self._controller.get_warmup_status()
        if self._controller.settings.warmup_active:
            self._warmup_label.setText(f"Warm-up: {labeled}/{required} labeled")
        else:
            self._warmup_label.setText("Auto-move: ON")
            self._warmup_label.setStyleSheet("color: #2ecc71; font-weight: bold;")

    def closeEvent(self, event: QCloseEvent) -> None:
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
