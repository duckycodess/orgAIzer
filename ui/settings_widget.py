"""
ui/settings_widget.py -- Settings tab.

Controls:
  - Downloads folder path picker
  - Dev/test watch folder override (separate from real Downloads)
  - School root folder picker
  - "Rescan Subject Folders" button
  - Confidence threshold sliders (HIGH and MEDIUM)
  - Warm-up mode toggle
  - "Refresh Model" button (manual retrain trigger)
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
    QFrame,
)

from app.settings import AppSettings


class SettingsWidget(QWidget):
    """Settings tab that reads/writes an AppSettings object."""

    # Emitted when any setting changes so the controller can save and apply.
    settings_changed = Signal()
    # Emitted when user clicks Rescan.
    rescan_requested = Signal(str)  # school_root path
    # Emitted when user clicks Refresh Model.
    retrain_requested = Signal()
    # Emitted when user clicks Import Training Data.
    seed_requested = Signal(str)  # school_root path

    def __init__(self, settings: AppSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._setup_ui()
        self._load_from_settings()

    def _setup_ui(self) -> None:
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(16)
        layout.setContentsMargins(16, 16, 16, 16)

        # Title
        title = QLabel("Settings")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        # --- Folder Settings ---
        folder_group = QGroupBox("Folder Configuration")
        folder_form = QFormLayout(folder_group)
        folder_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)

        self._downloads_edit = QLineEdit()
        self._downloads_btn = QPushButton("Browse…")
        self._downloads_btn.setFixedWidth(90)
        dl_row = QHBoxLayout()
        dl_row.addWidget(self._downloads_edit)
        dl_row.addWidget(self._downloads_btn)
        folder_form.addRow("Downloads folder:", dl_row)

        self._watch_override_edit = QLineEdit()
        self._watch_override_edit.setPlaceholderText("Leave empty to use Downloads folder")
        self._watch_btn = QPushButton("Browse…")
        self._watch_btn.setFixedWidth(90)
        wo_row = QHBoxLayout()
        wo_row.addWidget(self._watch_override_edit)
        wo_row.addWidget(self._watch_btn)
        folder_form.addRow("Dev/test watch folder:", wo_row)

        hint = QLabel("Set a dev folder to test without touching real Downloads.")
        hint.setObjectName("HintLabel")
        folder_form.addRow("", hint)

        self._school_root_edit = QLineEdit()
        self._school_root_btn = QPushButton("Browse…")
        self._school_root_btn.setFixedWidth(90)
        sr_row = QHBoxLayout()
        sr_row.addWidget(self._school_root_edit)
        sr_row.addWidget(self._school_root_btn)
        folder_form.addRow("School root folder:", sr_row)

        self._rescan_btn = QPushButton("Rescan Subject Folders")
        self._rescan_btn.setProperty("role", "change")
        self._rescan_status = QLabel("")
        self._rescan_status.setObjectName("StatusActive")
        rescan_row = QHBoxLayout()
        rescan_row.addWidget(self._rescan_btn)
        rescan_row.addWidget(self._rescan_status)
        rescan_row.addStretch()
        folder_form.addRow("", rescan_row)

        layout.addWidget(folder_group)

        # --- Confidence Thresholds ---
        thresh_group = QGroupBox("Confidence Thresholds")
        thresh_layout = QVBoxLayout(thresh_group)

        thresh_layout.addWidget(QLabel("Auto-move threshold (HIGH):"))
        self._high_slider = _PercentSlider(default=85)
        thresh_layout.addWidget(self._high_slider)

        thresh_layout.addWidget(QLabel("Recommend threshold (MEDIUM):"))
        self._med_slider = _PercentSlider(default=55)
        thresh_layout.addWidget(self._med_slider)

        layout.addWidget(thresh_group)

        # --- Warm-up Mode ---
        warmup_group = QGroupBox("Warm-up Mode")
        warmup_layout = QVBoxLayout(warmup_group)

        self._warmup_check = QCheckBox("Enable warm-up mode (never auto-move; always ask)")
        warmup_layout.addWidget(self._warmup_check)

        self._warmup_status = QLabel("")
        self._warmup_status.setObjectName("StatusLabel")
        warmup_layout.addWidget(self._warmup_status)

        layout.addWidget(warmup_group)

        # --- Model ---
        model_group = QGroupBox("AI Model")
        model_layout = QVBoxLayout(model_group)

        self._import_btn = QPushButton("Import Training Data")
        self._import_btn.setProperty("role", "change")
        self._import_status = QLabel("")
        self._import_status.setObjectName("StatusLabel")
        import_row = QHBoxLayout()
        import_row.addWidget(self._import_btn)
        import_row.addWidget(self._import_status)
        import_row.addStretch()
        model_layout.addWidget(QLabel("Bootstrap model from existing school root folder:"))
        model_layout.addLayout(import_row)

        self._retrain_btn = QPushButton("Refresh Model")
        self._retrain_btn.setProperty("role", "primary")
        self._retrain_status = QLabel("")
        self._retrain_status.setObjectName("StatusLabel")
        retrain_row = QHBoxLayout()
        retrain_row.addWidget(self._retrain_btn)
        retrain_row.addWidget(self._retrain_status)
        retrain_row.addStretch()
        model_layout.addWidget(QLabel("Manually retrain the AI model on all saved corrections:"))
        model_layout.addLayout(retrain_row)

        layout.addWidget(model_group)

        # --- Save button ---
        save_row = QHBoxLayout()
        save_row.addStretch()
        self._save_btn = QPushButton("Save Settings")
        self._save_btn.setProperty("role", "primary")
        save_row.addWidget(self._save_btn)
        layout.addLayout(save_row)
        layout.addStretch()

        scroll.setWidget(container)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        # Connect signals
        self._downloads_btn.clicked.connect(
            lambda: self._pick_folder(self._downloads_edit, "Select Downloads folder")
        )
        self._watch_btn.clicked.connect(
            lambda: self._pick_folder(self._watch_override_edit, "Select dev/test watch folder")
        )
        self._school_root_btn.clicked.connect(
            lambda: self._pick_folder(self._school_root_edit, "Select School root folder")
        )
        self._rescan_btn.clicked.connect(self._on_rescan)
        self._import_btn.clicked.connect(self._on_import)
        self._retrain_btn.clicked.connect(self._on_retrain)
        self._save_btn.clicked.connect(self._on_save)

    def _pick_folder(self, edit: QLineEdit, caption: str) -> None:
        folder = QFileDialog.getExistingDirectory(self, caption, edit.text())
        if folder:
            edit.setText(folder)

    def _load_from_settings(self) -> None:
        s = self._settings
        self._downloads_edit.setText(s.downloads_path)
        self._watch_override_edit.setText(s.watch_folder_override)
        self._school_root_edit.setText(s.school_root)
        self._high_slider.set_value(int(s.threshold_high * 100))
        self._med_slider.set_value(int(s.threshold_medium * 100))
        self._warmup_check.setChecked(s.warmup_active)
        self._update_warmup_status()

    def _update_warmup_status(self) -> None:
        count = self._settings.warmup_labeled_count
        from app.settings import WARMUP_MIN_SCHOOL_LABELS
        if self._settings.warmup_active:
            self._warmup_status.setText(
                f"Progress: {count} / {WARMUP_MIN_SCHOOL_LABELS} labeled school files"
            )
            self._warmup_status.setObjectName("StatusLabel")
        else:
            self._warmup_status.setText("Auto-move is ENABLED")
            self._warmup_status.setObjectName("StatusActive")
        self._warmup_status.style().unpolish(self._warmup_status)
        self._warmup_status.style().polish(self._warmup_status)

    def _on_save(self) -> None:
        s = self._settings
        s.downloads_path = self._downloads_edit.text().strip()
        s.watch_folder_override = self._watch_override_edit.text().strip()
        s.school_root = self._school_root_edit.text().strip()
        s.threshold_high = self._high_slider.value() / 100.0
        s.threshold_medium = self._med_slider.value() / 100.0
        s.warmup_active = self._warmup_check.isChecked()
        self.settings_changed.emit()

    def _on_rescan(self) -> None:
        path = self._school_root_edit.text().strip()
        if path:
            self._rescan_status.setText("Scanning…")
            self.rescan_requested.emit(path)

    def on_rescan_done(self, count: int) -> None:
        self._rescan_status.setText(f"Found {count} subject folder(s)")

    def _on_import(self) -> None:
        path = self._school_root_edit.text().strip()
        if not path:
            self._import_status.setText("Set school root first.")
            return
        self._import_status.setText("Importing…")
        self._import_btn.setEnabled(False)
        self.seed_requested.emit(path)

    def on_import_done(self, count: int) -> None:
        self._import_status.setText(f"{count} samples imported. Retraining…")
        self._import_btn.setEnabled(True)

    def _on_retrain(self) -> None:
        self._retrain_status.setText("Retraining in background…")
        self.retrain_requested.emit()

    def on_retrain_done(self) -> None:
        self._retrain_status.setText("Model updated!")

    def update_warmup_display(self) -> None:
        self._warmup_check.setChecked(self._settings.warmup_active)
        self._update_warmup_status()


class _PercentSlider(QWidget):
    """A labeled horizontal slider showing a percentage value."""

    def __init__(self, default: int = 85, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(10, 99)
        self._slider.setValue(default)

        self._label = QLabel(f"{default}%")
        self._label.setFixedWidth(40)

        self._slider.valueChanged.connect(lambda v: self._label.setText(f"{v}%"))

        layout.addWidget(self._slider)
        layout.addWidget(self._label)

    def value(self) -> int:
        return self._slider.value()

    def set_value(self, v: int) -> None:
        self._slider.setValue(v)
