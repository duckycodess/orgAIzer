"""
app/settings.py — Typed settings object backed by the SQLite settings table.

AppSettings is a simple dataclass. Call load() to populate it from DB,
call save() to persist changes back. The controller holds one instance.
"""

from dataclasses import dataclass, field
from pathlib import Path

from storage.repository import SettingsRepo


# Fixed category labels — never extend this set automatically in v1.
CATEGORY_LABELS = [
    "Lectures",
    "Labs",
    "Exercises",
    "Assignments",
    "References",
    "Others",
]

# Minimum warm-up thresholds before auto-move is allowed.
WARMUP_MIN_SCHOOL_LABELS = 25
WARMUP_MIN_COURSE_LABELS = 5

# Retrain background worker fires after this many new corrections.
RETRAIN_EVERY_N = 5


@dataclass
class AppSettings:
    # Folder paths
    downloads_path: str = str(Path.home() / "Downloads")
    school_root: str = ""
    watch_folder_override: str = ""   # if non-empty, watch this folder instead of downloads_path

    # Confidence thresholds
    threshold_high: float = 0.85
    threshold_medium: float = 0.55

    # Warm-up state
    warmup_active: bool = True
    warmup_labeled_count: int = 0

    # Internal counter for background retraining
    correction_counter: int = 0

    @property
    def effective_watch_folder(self) -> str:
        """The actual folder being monitored (dev override or real Downloads)."""
        return self.watch_folder_override or self.downloads_path

    def load(self, repo: SettingsRepo) -> None:
        """Populate fields from the settings table."""
        self.downloads_path = repo.get("downloads_path", self.downloads_path)
        self.school_root = repo.get("school_root", self.school_root)
        self.watch_folder_override = repo.get("watch_folder_override", "")
        self.threshold_high = repo.get_float("threshold_high", 0.85)
        self.threshold_medium = repo.get_float("threshold_medium", 0.55)
        self.warmup_active = repo.get_bool("warmup_active", True)
        self.warmup_labeled_count = repo.get_int("warmup_labeled_count", 0)
        self.correction_counter = repo.get_int("correction_counter", 0)

    def save(self, repo: SettingsRepo) -> None:
        """Persist all fields back to the settings table."""
        repo.set("downloads_path", self.downloads_path)
        repo.set("school_root", self.school_root)
        repo.set("watch_folder_override", self.watch_folder_override)
        repo.set("threshold_high", str(self.threshold_high))
        repo.set("threshold_medium", str(self.threshold_medium))
        repo.set("warmup_active", "1" if self.warmup_active else "0")
        repo.set("warmup_labeled_count", str(self.warmup_labeled_count))
        repo.set("correction_counter", str(self.correction_counter))
