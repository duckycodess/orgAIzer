"""
app/controller.py -- Central orchestrator.

Threading model (IMPORTANT):
  - The SQLite connection and all DB repos are owned by the main Qt thread.
  - The file watcher dispatches callbacks in background daemon threads.
  - Background threads do ONLY: stability check + feature extraction.
  - They then emit `_features_ready` (a class-level Qt Signal).
  - Qt automatically uses a QueuedConnection for cross-thread signals,
    so `_process_features` always runs in the main thread.
  - This makes all DB writes, classifier calls, and UI signal emissions
    main-thread-only — no shared-connection issues.

Fix summary (v1.1):
  1. SQLite thread safety via signal-based handoff to main thread.
  2. Store full features.all_text[:4000] in pending events for quality retraining.
  3. Do NOT auto-move into non-existing category folders (force to pending).
  4. In-flight set prevents duplicate processing of the same path.
  5. Retraining uses fresh classifier instances; live instances swapped in
     main thread after worker finishes (never mutates live models mid-use).
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal

from app.settings import AppSettings, RETRAIN_EVERY_N, WARMUP_MIN_SCHOOL_LABELS, WARMUP_MIN_COURSE_LABELS
from classifiers.category_predictor import CategoryPredictor
from classifiers.course_predictor import CoursePredictor
from classifiers.school_detector import SchoolDetector
from core.extractor import extract_features, FileFeatures
from core.mover import safe_move, undo_move
from core.stability import wait_until_stable
from core.watcher import FileWatcher
from storage.db import get_connection, get_models_dir, init_schema
from storage.repository import (
    CourseFolderRepo,
    FileEventRepo,
    SettingsRepo,
    TrainingSampleRepo,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Background retraining worker  (Fix #5)
# ---------------------------------------------------------------------------

class _RetrainWorker(QThread):
    """
    Trains FRESH classifier instances in a background thread, saves them to
    disk, then signals the main thread to reload.  Never mutates the live
    classifier objects that may be in use for prediction.
    """
    done = Signal()

    def __init__(
        self,
        samples: list[dict],
        known_courses: list[str],
        model_dir: Path,
    ) -> None:
        super().__init__()
        self._samples = samples
        self._known_courses = known_courses
        self._model_dir = model_dir

    def run(self) -> None:
        logger.info("Background retrain started (%d samples)", len(self._samples))
        try:
            # Create completely fresh instances — never touch the live ones.
            school_det = SchoolDetector()
            course_pred = CoursePredictor()
            course_pred.set_known_courses(self._known_courses)
            cat_pred = CategoryPredictor()

            school_det.retrain(self._samples)
            school_det.save_model(self._model_dir / "school_detector.pkl")

            course_pred.retrain(self._samples)
            course_pred.save_model(self._model_dir / "course_predictor.pkl")

            cat_pred.retrain(self._samples)
            cat_pred.save_model(self._model_dir / "category_predictor.pkl")

            logger.info("Background retrain completed")
        except Exception as e:
            logger.error("Retrain failed: %s", e)
        finally:
            self.done.emit()


# ---------------------------------------------------------------------------
# Main controller
# ---------------------------------------------------------------------------

class Controller(QObject):
    """
    Owns: DB connection, classifier instances, file watcher, settings.
    All DB and classifier access happens in the main Qt thread.
    """

    # Public signals consumed by the UI
    file_classified = Signal(dict)   # school file needing user review
    file_auto_moved = Signal(dict)   # file was auto-moved
    file_status     = Signal(dict)   # non-school / error / info
    retrain_done    = Signal()       # background retrain finished

    # Internal signal for handing off extracted features from background thread
    # to the main thread (Fix #1). QueuedConnection is automatic for cross-thread.
    _features_ready = Signal(object)

    def __init__(self) -> None:
        super().__init__()

        # Database — only ever accessed from the main thread.
        self._conn = get_connection()
        init_schema(self._conn)

        # Repositories
        self._settings_repo = SettingsRepo(self._conn)
        self._event_repo    = FileEventRepo(self._conn)
        self._sample_repo   = TrainingSampleRepo(self._conn)
        self._course_repo   = CourseFolderRepo(self._conn)

        # Settings
        self._settings = AppSettings()
        self._settings.load(self._settings_repo)

        # Classifiers (main thread only)
        model_dir = get_models_dir()
        self._school_det = SchoolDetector()
        self._course_pred = CoursePredictor()
        self._cat_pred    = CategoryPredictor()
        self._school_det.load_model(model_dir / "school_detector.pkl")
        self._course_pred.load_model(model_dir / "course_predictor.pkl")
        self._cat_pred.load_model(model_dir / "category_predictor.pkl")
        self._refresh_course_list()

        # In-flight protection (Fix #4): tracks paths currently being processed.
        # Accessed from background threads, so guarded by a lock.
        self._in_flight: set[str] = set()
        self._in_flight_lock = threading.Lock()

        # File watcher
        self._watcher = FileWatcher(
            self._settings.effective_watch_folder,
            self._on_file_detected,
        )

        # Retrain worker reference (kept to prevent GC)
        self._retrain_worker: _RetrainWorker | None = None

        # Connect internal handoff signal (Fix #1)
        self._features_ready.connect(self._process_features)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start_watching(self) -> None:
        folder = self._settings.effective_watch_folder
        if not folder or not Path(folder).exists():
            logger.warning("Watch folder not configured or missing: %s", folder)
            return
        self._watcher.change_folder(folder)
        self._watcher.start()

    def stop_watching(self) -> None:
        self._watcher.stop()

    def is_watching(self) -> bool:
        return self._watcher.is_running()

    @property
    def settings(self) -> AppSettings:
        return self._settings

    def save_settings(self) -> None:
        self._settings.save(self._settings_repo)

    def get_history(self, limit: int = 200) -> list[dict]:
        return self._event_repo.get_all(limit)

    def get_pending(self) -> list[dict]:
        return self._event_repo.get_pending()

    def scan_course_folders(self, school_root: str) -> int:
        """Discover course folders under school_root and persist to DB."""
        root = Path(school_root)
        if not root.exists():
            return 0
        self._course_repo.clear()
        count = 0
        for entry in root.iterdir():
            if entry.is_dir():
                subfolders = [s.name for s in entry.iterdir() if s.is_dir()]
                self._course_repo.upsert(entry.name, str(entry), subfolders)
                count += 1
        self._refresh_course_list()
        return count

    def handle_user_decision(
        self,
        event_id: int,
        final_course: str,
        final_category: str,
        action: str,   # 'accepted' | 'corrected' | 'skipped'
    ) -> str | None:
        """
        Process user's decision on a pending file.
        Returns the final destination path, or None on skip/failure.
        """
        event = self._event_repo.get_by_id(event_id)
        if not event:
            return None

        dest_path = None

        if action in ("accepted", "corrected"):
            school_root = self._settings.school_root
            if not school_root:
                logger.warning("School root not configured; cannot move file")
                return None
            dest_dir = str(Path(school_root) / final_course / final_category)
            try:
                dest_path = safe_move(event["original_path"], dest_dir)
                self._event_repo.update(
                    event_id,
                    destination_path=dest_path,
                    stage="moved",
                    user_action=action,
                    final_course=final_course,
                    final_category=final_category,
                )
            except (FileNotFoundError, OSError) as e:
                logger.error("Move failed for event %d: %s", event_id, e)
                self._event_repo.update(event_id, stage="error", notes=str(e))
                return None
        else:
            self._event_repo.update(event_id, stage="skipped", user_action="skipped")

        # Log training sample using the stored feature_text (Fix #2 + Fix #3).
        # feature_text holds the full extracted document text from detection time.
        # file_size was also stored at detection time so we don't need the file to exist.
        stored_text = event.get("feature_text") or ""
        stored_size = event.get("file_size") or 0
        self._sample_repo.insert(
            filename=event["filename"],
            text_features=json.dumps(stored_text),
            extension=Path(event["filename"]).suffix.lower(),
            file_size=stored_size,
            label_school=1 if action != "skipped" else 0,
            label_course=final_course if action != "skipped" else None,
            label_category=final_category if action != "skipped" else None,
            source=f"user_{action}",
        )

        if action in ("accepted", "corrected"):
            self._settings.warmup_labeled_count += 1
            self._check_warmup_exit(final_course)
            self._settings.correction_counter += 1
            self._settings.save(self._settings_repo)
            if self._settings.correction_counter % RETRAIN_EVERY_N == 0:
                self.trigger_retrain()

        return dest_path

    def undo_move(self, event_id: int) -> bool:
        """Return a moved file to its original Downloads location."""
        event = self._event_repo.get_by_id(event_id)
        if not event:
            return False
        dest = event.get("destination_path")
        original = event.get("original_path")
        if not dest or not original:
            return False
        success = undo_move(dest, original)
        if success:
            self._event_repo.update(event_id, stage="undone", user_action="undone")
        return success

    def trigger_retrain(self) -> None:
        """Launch background retraining (Fix #5: uses fresh instances)."""
        samples = self._sample_repo.get_all()
        if not samples:
            return
        if self._retrain_worker and self._retrain_worker.isRunning():
            return  # already running

        known_courses = self._course_repo.get_course_names()
        self._retrain_worker = _RetrainWorker(
            samples=samples,
            known_courses=known_courses,
            model_dir=get_models_dir(),
        )
        self._retrain_worker.done.connect(self._on_retrain_done)
        self._retrain_worker.start()

    def get_warmup_status(self) -> tuple[int, int]:
        return self._settings.warmup_labeled_count, WARMUP_MIN_SCHOOL_LABELS

    # ------------------------------------------------------------------
    # Background thread: stability + extraction only (Fix #1)
    # ------------------------------------------------------------------

    def _on_file_detected(self, path: str) -> None:
        """
        Called from a background daemon thread by the file watcher.
        ONLY does blocking I/O work: stability check + feature extraction.
        All DB writes and classifier calls happen in _process_features()
        which runs in the main thread via the _features_ready queued signal.

        Fix #4 (improved): path stays in-flight until _process_features()
        finishes in the main thread, not just until this background thread ends.
        On failure (timeout / file gone), we release immediately here.
        """
        with self._in_flight_lock:
            if path in self._in_flight:
                logger.debug("Skipping duplicate in-flight path: %s", path)
                return
            self._in_flight.add(path)

        emitted = False
        try:
            logger.info("Processing file: %s", path)

            if not wait_until_stable(path):
                logger.warning("Stability timeout: %s", path)
                return

            if not Path(path).exists():
                return  # disappeared before we could read it

            features = extract_features(path)

            # Hand off to main thread via queued signal.
            self._features_ready.emit({
                "path":        features.path,
                "filename":    features.filename,
                "stem":        features.stem,
                "ext":         features.ext,
                "size_bytes":  features.size_bytes,
                "text":        features.text,
                "zip_members": features.zip_members,
            })
            emitted = True
        finally:
            # Release in-flight only if we did NOT successfully emit the signal.
            # If we did emit, _process_features() will release it in the main thread.
            if not emitted:
                with self._in_flight_lock:
                    self._in_flight.discard(path)

    # ------------------------------------------------------------------
    # Main thread: classification + DB + UI signals (Fix #1)
    # ------------------------------------------------------------------

    def _process_features(self, data: dict) -> None:
        """
        Runs in the main Qt thread (connected via QueuedConnection).
        Performs all classification, DB writes, and UI signal emissions.
        Releases the in-flight lock when done (Fix #4).
        """
        path = data.get("path", "")
        try:
            self._run_pipeline(data)
        finally:
            with self._in_flight_lock:
                self._in_flight.discard(path)

    def _run_pipeline(self, data: dict) -> None:
        """Core classification + DB + signal logic, called from _process_features."""
        features = FileFeatures(
            path=data["path"],
            filename=data["filename"],
            stem=data["stem"],
            ext=data["ext"],
            size_bytes=data["size_bytes"],
            text=data["text"],
            zip_members=data["zip_members"],
        )
        feature_text = features.all_text[:4000]   # stored for quality retraining (Fix #2)

        # Stage 1: school-related?
        is_school, school_conf, school_reason = self._school_det.predict(features)

        if not is_school:
            eid = self._event_repo.insert(
                filename=features.filename,
                original_path=features.path,
                stage="not_school",
                school_confidence=school_conf,
                prediction_reason=school_reason,
                feature_text=feature_text,
                file_size=features.size_bytes,
            )
            self.file_status.emit({
                "event_id": eid,
                "filename": features.filename,
                "stage": "not_school",
                "school_confidence": school_conf,
                "reason": school_reason,
            })
            return

        # Stage 2 & 3
        course,   course_conf, course_reason = self._course_pred.predict(features)
        category, cat_conf,    cat_reason    = self._cat_pred.predict(features)

        overall_conf = min(school_conf, course_conf, cat_conf)
        reason = f"{school_reason} | {course_reason} | {cat_reason}"

        # Decide auto-move eligibility
        known_courses = self._course_repo.get_course_names()
        can_auto = (
            not self._settings.warmup_active
            and overall_conf >= self._settings.threshold_high
            and course in known_courses
        )

        # Fix #3: only auto-move into an EXISTING category folder.
        if can_auto:
            dest_candidate = Path(self._settings.school_root) / course / category
            if not dest_candidate.is_dir():
                can_auto = False
                logger.info(
                    "Destination %s does not exist; sending to pending review.",
                    dest_candidate,
                )

        if can_auto:
            dest_dir = str(Path(self._settings.school_root) / course / category)
            try:
                dest_path = safe_move(features.path, dest_dir)
                eid = self._event_repo.insert(
                    filename=features.filename,
                    original_path=features.path,
                    destination_path=dest_path,
                    stage="moved",
                    school_confidence=school_conf,
                    course_predicted=course,
                    course_confidence=course_conf,
                    category_predicted=category,
                    category_confidence=cat_conf,
                    prediction_reason=reason,
                    user_action="auto",
                    final_course=course,
                    final_category=category,
                    feature_text=feature_text,      # Fix #2
                    file_size=features.size_bytes,  # Fix #3
                )
                # Fix #1: do NOT add auto-moved files to training_samples.
                # Only user-confirmed decisions are trusted training data.
                self.file_auto_moved.emit({
                    "event_id": eid,
                    "filename": features.filename,
                    "original_path": features.path,
                    "destination_path": dest_path,
                    "course": course,
                    "category": category,
                    "overall_confidence": overall_conf,
                    "reason": reason,
                })
            except (FileNotFoundError, OSError) as e:
                logger.error("Auto-move failed for %s: %s", features.path, e)
                self._event_repo.insert(
                    filename=features.filename,
                    original_path=features.path,
                    stage="error",
                    notes=str(e),
                    feature_text=feature_text,
                    file_size=features.size_bytes,
                )
                self.file_status.emit({
                    "event_id": None,
                    "filename": features.filename,
                    "stage": "error",
                    "reason": str(e),
                })
        else:
            # Pending: store feature_text separately from notes (Fix #2).
            eid = self._event_repo.insert(
                filename=features.filename,
                original_path=features.path,
                stage="pending",
                school_confidence=school_conf,
                course_predicted=course,
                course_confidence=course_conf,
                category_predicted=category,
                category_confidence=cat_conf,
                prediction_reason=reason,
                feature_text=feature_text,      # Fix #2: clean separation
                file_size=features.size_bytes,  # Fix #3
            )
            self.file_classified.emit({
                "event_id": eid,
                "filename": features.filename,
                "original_path": features.path,
                "course": course,
                "category": category,
                "overall_confidence": overall_conf,
                "school_confidence": school_conf,
                "course_confidence": course_conf,
                "category_confidence": cat_conf,
                "reason": reason,
            })

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _check_warmup_exit(self, predicted_course: str) -> None:
        if not self._settings.warmup_active:
            return
        total_ok = self._settings.warmup_labeled_count >= WARMUP_MIN_SCHOOL_LABELS
        course_ok = self._sample_repo.count_for_course(predicted_course) >= WARMUP_MIN_COURSE_LABELS
        if total_ok and course_ok:
            self._settings.warmup_active = False
            logger.info("Warm-up mode exited. Auto-move is now enabled.")

    def _refresh_course_list(self) -> None:
        names = self._course_repo.get_course_names()
        self._course_pred.set_known_courses(names)

    def _on_retrain_done(self) -> None:
        """
        Runs in main thread after worker finishes.
        Reloads freshly saved models into the live classifiers (Fix #5).
        """
        model_dir = get_models_dir()
        self._school_det.load_model(model_dir / "school_detector.pkl")
        self._course_pred.load_model(model_dir / "course_predictor.pkl")
        self._cat_pred.load_model(model_dir / "category_predictor.pkl")
        logger.info("Live classifiers updated from retrained models.")
        self.retrain_done.emit()

    def shutdown(self) -> None:
        self.stop_watching()
        self._conn.close()
