"""
app/controller.py -- Central orchestrator for subject-based school sorting.

Threading model:
  - SQLite access and classifier use stay in the main Qt thread.
  - Watcher callbacks do only stability checks and feature extraction.
  - Extracted feature payloads are handed back through a queued Qt signal.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal

from app.settings import (
    AppSettings,
    RETRAIN_EVERY_N,
    WARMUP_MIN_SCHOOL_LABELS,
    WARMUP_MIN_SUBJECT_LABELS,
)
from classifiers.school_detector import SchoolDetector
from classifiers.subject_predictor import SubjectPredictor
from core.extractor import FileFeatures, extract_features, extract_folder_features
from core.mover import safe_move, undo_move
from core.stability import wait_until_stable, wait_until_stable_dir
from core.watcher import FileWatcher
from storage.db import get_connection, get_models_dir, init_schema
from storage.repository import (
    FileEventRepo,
    SettingsRepo,
    SubjectFolderRepo,
    TrainingSampleRepo,
)

logger = logging.getLogger(__name__)

STRONG_SUBJECT_OVERRIDE = 0.82

_SEED_EXTENSIONS = {".pdf", ".docx", ".txt", ".pptx", ".zip"}


def _normalize_subject_name(subject: str) -> str:
    return " ".join(subject.strip().split())


def _is_valid_subject_name(subject: str) -> bool:
    normalized = _normalize_subject_name(subject)
    if not normalized:
        return False
    if normalized in {".", ".."}:
        return False
    return "/" not in normalized and "\\" not in normalized


class _RetrainWorker(QThread):
    """Train fresh models in the background, then notify the main thread."""

    done = Signal()

    def __init__(
        self,
        samples: list[dict],
        known_subjects: list[str],
        model_dir: Path,
    ) -> None:
        super().__init__()
        self._samples = samples
        self._known_subjects = known_subjects
        self._model_dir = model_dir

    def run(self) -> None:
        logger.info("Background retrain started (%d samples)", len(self._samples))
        try:
            school_det = SchoolDetector()
            subject_pred = SubjectPredictor()
            subject_pred.set_known_subjects(self._known_subjects)

            school_det.retrain(self._samples)
            school_det.save_model(self._model_dir / "school_detector.pkl")

            subject_pred.retrain(self._samples)
            subject_pred.save_model(self._model_dir / "subject_predictor.pkl")
            subject_pred.save_model(self._model_dir / "course_predictor.pkl")

            logger.info("Background retrain completed")
        except Exception as exc:
            logger.error("Retrain failed: %s", exc)
        finally:
            self.done.emit()


class Controller(QObject):
    """
    Owns the DB connection, classifiers, settings, and file watcher.
    All classifier calls and DB writes happen in the main Qt thread.
    """

    file_classified = Signal(dict)
    file_auto_moved = Signal(dict)
    file_status = Signal(dict)
    retrain_done = Signal()

    _features_ready = Signal(object)

    def __init__(self) -> None:
        super().__init__()

        self._conn = get_connection()
        init_schema(self._conn)

        self._settings_repo = SettingsRepo(self._conn)
        self._event_repo = FileEventRepo(self._conn)
        self._sample_repo = TrainingSampleRepo(self._conn)
        self._subject_repo = SubjectFolderRepo(self._conn)

        self._settings = AppSettings()
        self._settings.load(self._settings_repo)

        model_dir = get_models_dir()
        self._school_det = SchoolDetector()
        self._subject_pred = SubjectPredictor()
        self._school_det.load_model(model_dir / "school_detector.pkl")
        subject_model = model_dir / "subject_predictor.pkl"
        legacy_subject_model = model_dir / "course_predictor.pkl"
        self._subject_pred.load_model(
            subject_model if subject_model.exists() else legacy_subject_model
        )
        self._refresh_subject_list()

        self._in_flight: set[str] = set()
        self._in_flight_lock = threading.Lock()
        self._undo_pending_paths: dict[int, str] = {}  # event_id -> original_path

        self._watcher = FileWatcher(
            self._settings.effective_watch_folder,
            self._on_file_detected,
        )
        self._retrain_worker: _RetrainWorker | None = None
        self._features_ready.connect(self._process_features)

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

    def get_subject_names(self) -> list[str]:
        return self._subject_repo.get_subject_names()

    def scan_subject_folders(self, school_root: str) -> int:
        """Discover subject folders under `school_root` and persist them."""
        root = Path(school_root)
        if not root.exists():
            return 0

        self._subject_repo.clear()
        count = 0
        for entry in sorted(root.iterdir()):
            if not entry.is_dir():
                continue
            subfolders = [s.name for s in sorted(entry.iterdir()) if s.is_dir()]
            self._subject_repo.upsert(entry.name, str(entry), subfolders)
            count += 1

        self._refresh_subject_list()
        return count

    def scan_course_folders(self, school_root: str) -> int:
        return self.scan_subject_folders(school_root)

    def clear_training_samples(self) -> None:
        """Delete all training samples from the database."""
        self._conn.execute("DELETE FROM training_samples")
        self._conn.commit()

    def seed_from_folder(self, folder: str) -> int:
        """Read an organized training folder and insert bootstrap training samples.

        A subfolder named NOT_SCHOOL (case-insensitive) produces label_school=0
        samples. All other subfolders produce label_school=1 samples.
        """
        root = Path(folder)
        if not root.is_dir():
            return 0
        count = 0
        for subject_dir in sorted(root.iterdir()):
            if not subject_dir.is_dir():
                continue
            subject_name = subject_dir.name
            is_not_school = subject_name.upper() == "NOT_SCHOOL"
            for file_path in sorted(subject_dir.rglob("*")):
                if not file_path.is_file():
                    continue
                if file_path.suffix.lower() not in _SEED_EXTENSIONS:
                    continue
                stem_tokens = file_path.stem.replace("_", " ").replace("-", " ")
                parent_tokens = " ".join(
                    file_path.parent.relative_to(subject_dir).parts
                )
                text = " ".join(
                    t for t in [stem_tokens, parent_tokens, subject_name] if t
                )
                self._sample_repo.insert(
                    filename=file_path.name,
                    text_features=json.dumps(text),
                    extension=file_path.suffix.lower(),
                    file_size=0,
                    label_school=0 if is_not_school else 1,
                    label_subject=None if is_not_school else subject_name,
                    source="bootstrap",
                )
                count += 1
        return count

    def handle_user_decision(
        self,
        event_id: int,
        final_subject: str,
        action: str,   # accepted | corrected | skipped
    ) -> str | None:
        # Release undo suppression for this event regardless of outcome.
        undo_path = self._undo_pending_paths.pop(event_id, None)
        if undo_path:
            with self._in_flight_lock:
                self._in_flight.discard(undo_path)
        event = self._event_repo.get_by_id(event_id)
        if not event:
            return None

        dest_path = None
        if action in ("accepted", "corrected"):
            school_root = self._settings.school_root
            normalized_subject = _normalize_subject_name(final_subject)
            if not school_root or not normalized_subject:
                logger.warning("School root or subject missing; cannot move file")
                return None
            if not _is_valid_subject_name(normalized_subject):
                logger.warning("Invalid subject name: %s", final_subject)
                return None
            canonical_subject = self._canonical_subject_name(normalized_subject)

            dest_dir = str(Path(school_root) / canonical_subject)
            try:
                dest_path = safe_move(event["original_path"], dest_dir)
                self._register_subject_folder(canonical_subject)
                self._event_repo.update(
                    event_id,
                    destination_path=dest_path,
                    stage="moved",
                    user_action=action,
                    final_course=canonical_subject,
                    final_category=None,
                )
            except (FileNotFoundError, OSError) as exc:
                logger.error("Move failed for event %d: %s", event_id, exc)
                self._event_repo.update(event_id, stage="error", notes=str(exc))
                return None
            final_subject = canonical_subject
        else:
            self._event_repo.update(event_id, stage="skipped", user_action="skipped")

        stored_text = event.get("feature_text") or ""
        stored_size = event.get("file_size") or 0
        self._sample_repo.insert(
            filename=event["filename"],
            text_features=json.dumps(stored_text),
            extension=Path(event["filename"]).suffix.lower(),
            file_size=stored_size,
            label_school=1 if action != "skipped" else 0,
            label_subject=final_subject if action != "skipped" else None,
            label_category=None,
            source=f"user_{action}",
        )

        if action in ("accepted", "corrected"):
            self._settings.warmup_labeled_count += 1
            self._check_warmup_exit(final_subject)
            self._settings.correction_counter += 1
            self._settings.save(self._settings_repo)
            if self._settings.correction_counter % RETRAIN_EVERY_N == 0:
                self.trigger_retrain()

        return dest_path

    def handle_mark_as_school(
        self,
        event_id: int,
        subject: str,
    ) -> str | None:
        """Correct a not_school false negative. Returns dest_path or None."""
        event = self._event_repo.get_by_id(event_id)
        if not event:
            return None
        if event.get("stage") != "not_school":
            logger.warning("Event %d is not a not_school event; ignoring", event_id)
            return None

        normalized = _normalize_subject_name(subject)
        if not normalized or not _is_valid_subject_name(normalized):
            logger.warning("Invalid subject name for mark_as_school: %s", subject)
            return None

        canonical = self._canonical_subject_name(normalized)
        school_root = self._settings.school_root
        dest_path = None

        if school_root:
            dest_dir = Path(school_root) / canonical
            try:
                dest_dir.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                logger.warning("Could not create subject folder %s: %s", dest_dir, exc)

            try:
                dest_path = safe_move(event["original_path"], str(dest_dir))
                self._event_repo.update(
                    event_id,
                    destination_path=dest_path,
                    stage="moved",
                    user_action="corrected_not_school",
                    final_course=canonical,
                )
            except FileNotFoundError:
                self._event_repo.update(
                    event_id,
                    stage="skipped",
                    user_action="corrected_not_school",
                    final_course=canonical,
                    notes="File not found; training sample created from stored features",
                )
            except OSError as exc:
                logger.error("Move failed for event %d: %s", event_id, exc)
                self._event_repo.update(
                    event_id,
                    stage="skipped",
                    user_action="corrected_not_school",
                    final_course=canonical,
                    notes=str(exc),
                )

            self._register_subject_folder(canonical)
        else:
            self._event_repo.update(
                event_id,
                stage="skipped",
                user_action="corrected_not_school",
                final_course=canonical,
                notes="No school root set; training sample created from stored features",
            )

        stored_text = event.get("feature_text") or ""
        stored_size = event.get("file_size") or 0
        self._sample_repo.insert(
            filename=event["filename"],
            text_features=json.dumps(stored_text),
            extension=Path(event["filename"]).suffix.lower(),
            file_size=stored_size,
            label_school=1,
            label_subject=canonical,
            source="user_mark_school",
        )

        self._settings.warmup_labeled_count += 1
        self._check_warmup_exit(canonical)
        self._settings.correction_counter += 1
        self._settings.save(self._settings_repo)
        if self._settings.correction_counter % RETRAIN_EVERY_N == 0:
            self.trigger_retrain()

        return dest_path

    def undo_move(self, event_id: int) -> bool:
        event = self._event_repo.get_by_id(event_id)
        if not event:
            return False
        dest = event.get("destination_path")
        original = event.get("original_path")
        if not dest or not original:
            return False
        # Suppress BEFORE the move so watchdog can't fire in the gap.
        with self._in_flight_lock:
            self._in_flight.add(original)
        success = undo_move(dest, original)
        if success:
            self._event_repo.update(event_id, stage="undone", user_action="undone")
            # Re-queue as pending so the user can correct the subject.
            # Suppression stays active until handle_user_decision is called.
            self._queue_as_pending_after_undo(event, original)
        else:
            with self._in_flight_lock:
                self._in_flight.discard(original)
        return success

    def _queue_as_pending_after_undo(self, original_event: dict, original_path: str) -> None:
        feature_text = original_event.get("feature_text") or ""
        filename = original_event.get("filename") or Path(original_path).name
        school_conf = float(original_event.get("school_confidence") or 0.0)
        subject = original_event.get("course_predicted") or "Unknown"
        subject_conf = float(original_event.get("course_confidence") or 0.0)
        reason = f"[After undo] {original_event.get('prediction_reason') or ''}"

        eid = self._event_repo.insert(
            filename=filename,
            original_path=original_path,
            stage="pending",
            school_confidence=school_conf,
            subject_predicted=subject,
            subject_confidence=subject_conf,
            prediction_reason=reason,
            feature_text=feature_text,
            file_size=original_event.get("file_size") or 0,
        )
        self._undo_pending_paths[eid] = original_path
        overall = min(school_conf, subject_conf) if subject_conf > 0 else school_conf
        self.file_classified.emit({
            "event_id": eid,
            "filename": filename,
            "original_path": original_path,
            "subject": subject,
            "overall_confidence": overall,
            "school_confidence": school_conf,
            "subject_confidence": subject_conf,
            "reason": reason,
        })

    def trigger_retrain(self) -> None:
        samples = self._sample_repo.get_all()
        if not samples:
            return
        if self._retrain_worker and self._retrain_worker.isRunning():
            return

        self._retrain_worker = _RetrainWorker(
            samples=samples,
            known_subjects=self._subject_repo.get_subject_names(),
            model_dir=get_models_dir(),
        )
        self._retrain_worker.done.connect(self._on_retrain_done)
        self._retrain_worker.start()

    def get_warmup_status(self) -> tuple[int, int]:
        return self._settings.warmup_labeled_count, WARMUP_MIN_SCHOOL_LABELS

    def _on_file_detected(self, path: str) -> None:
        with self._in_flight_lock:
            if path in self._in_flight:
                logger.debug("Skipping duplicate in-flight path: %s", path)
                return
            self._in_flight.add(path)

        emitted = False
        try:
            p = Path(path)
            if p.is_dir():
                logger.info("Processing folder: %s", path)
                if not wait_until_stable_dir(path):
                    logger.warning("Folder stability timeout: %s", path)
                    return
                if not p.exists():
                    return
                features = extract_folder_features(path)
            else:
                logger.info("Processing file: %s", path)
                if not wait_until_stable(path):
                    logger.warning("Stability timeout: %s", path)
                    return
                if not p.exists():
                    return
                features = extract_features(path)
            self._features_ready.emit({
                "path": features.path,
                "filename": features.filename,
                "stem": features.stem,
                "ext": features.ext,
                "size_bytes": features.size_bytes,
                "text": features.text,
                "zip_members": features.zip_members,
            })
            emitted = True
        finally:
            if not emitted:
                with self._in_flight_lock:
                    self._in_flight.discard(path)

    def _process_features(self, data: dict) -> None:
        path = data.get("path", "")
        try:
            self._run_pipeline(data)
        finally:
            with self._in_flight_lock:
                self._in_flight.discard(path)

    def _run_pipeline(self, data: dict) -> None:
        features = FileFeatures(
            path=data["path"],
            filename=data["filename"],
            stem=data["stem"],
            ext=data["ext"],
            size_bytes=data["size_bytes"],
            text=data["text"],
            zip_members=data["zip_members"],
        )
        feature_text = features.all_text[:4000]

        subject, subject_conf, subject_reason = self._subject_pred.predict(features)
        is_school, school_conf, school_reason = self._school_det.predict(features)

        if (
            not is_school
            and subject != "Unknown"
            and subject_conf >= STRONG_SUBJECT_OVERRIDE
        ):
            is_school = True
            school_conf = max(school_conf, min(subject_conf, 0.90))
            school_reason = f"Strong subject signal: {subject_reason}"

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

        overall_conf = min(
            conf for conf in [school_conf, subject_conf] if conf is not None
        ) if subject_conf > 0 else school_conf
        reason = f"{school_reason} | {subject_reason}"

        known_subjects = self._subject_repo.get_subject_names()
        can_auto = (
            subject in known_subjects
            and not self._settings.warmup_active
            and overall_conf >= self._settings.threshold_high
        )

        if can_auto:
            dest_candidate = Path(self._settings.school_root) / subject
            if not dest_candidate.is_dir():
                can_auto = False
                logger.info(
                    "Destination %s does not exist; sending to pending review.",
                    dest_candidate,
                )

        if can_auto:
            dest_dir = str(Path(self._settings.school_root) / subject)
            try:
                dest_path = safe_move(features.path, dest_dir)
                eid = self._event_repo.insert(
                    filename=features.filename,
                    original_path=features.path,
                    destination_path=dest_path,
                    stage="moved",
                    school_confidence=school_conf,
                    subject_predicted=subject,
                    subject_confidence=subject_conf,
                    prediction_reason=reason,
                    user_action="auto",
                    final_subject=subject,
                    feature_text=feature_text,
                    file_size=features.size_bytes,
                )
                self.file_auto_moved.emit({
                    "event_id": eid,
                    "filename": features.filename,
                    "original_path": features.path,
                    "destination_path": dest_path,
                    "subject": subject,
                    "overall_confidence": overall_conf,
                    "reason": reason,
                })
            except (FileNotFoundError, OSError) as exc:
                logger.error("Auto-move failed for %s: %s", features.path, exc)
                self._event_repo.insert(
                    filename=features.filename,
                    original_path=features.path,
                    stage="error",
                    notes=str(exc),
                    feature_text=feature_text,
                    file_size=features.size_bytes,
                )
                self.file_status.emit({
                    "event_id": None,
                    "filename": features.filename,
                    "stage": "error",
                    "reason": str(exc),
                })
        else:
            eid = self._event_repo.insert(
                filename=features.filename,
                original_path=features.path,
                stage="pending",
                school_confidence=school_conf,
                subject_predicted=subject,
                subject_confidence=subject_conf,
                prediction_reason=reason,
                feature_text=feature_text,
                file_size=features.size_bytes,
            )
            self.file_classified.emit({
                "event_id": eid,
                "filename": features.filename,
                "original_path": features.path,
                "subject": subject,
                "overall_confidence": overall_conf,
                "school_confidence": school_conf,
                "subject_confidence": subject_conf,
                "reason": reason,
            })

    def _check_warmup_exit(self, predicted_subject: str) -> None:
        if not self._settings.warmup_active:
            return
        total_ok = self._settings.warmup_labeled_count >= WARMUP_MIN_SCHOOL_LABELS
        subject_ok = (
            self._sample_repo.count_for_subject(predicted_subject)
            >= WARMUP_MIN_SUBJECT_LABELS
        )
        if total_ok and subject_ok:
            self._settings.warmup_active = False
            logger.info("Warm-up mode exited. Auto-move is now enabled.")

    def _refresh_subject_list(self) -> None:
        self._subject_pred.set_known_subjects(self._subject_repo.get_subject_names())

    def _canonical_subject_name(self, subject_name: str) -> str:
        for existing_subject in self._subject_repo.get_subject_names():
            if existing_subject.casefold() == subject_name.casefold():
                return existing_subject
        return subject_name

    def _register_subject_folder(self, subject_name: str) -> None:
        root = self._settings.school_root
        if not root:
            return
        subject_dir = Path(root) / subject_name
        if not subject_dir.exists():
            return
        subfolders = [item.name for item in sorted(subject_dir.iterdir()) if item.is_dir()]
        self._subject_repo.upsert(subject_name, str(subject_dir), subfolders)
        self._refresh_subject_list()

    def _on_retrain_done(self) -> None:
        model_dir = get_models_dir()
        self._school_det.load_model(model_dir / "school_detector.pkl")
        subject_model = model_dir / "subject_predictor.pkl"
        legacy_subject_model = model_dir / "course_predictor.pkl"
        self._subject_pred.load_model(
            subject_model if subject_model.exists() else legacy_subject_model
        )
        logger.info("Live classifiers updated from retrained models.")
        self.retrain_done.emit()

    def shutdown(self) -> None:
        self.stop_watching()
        self._conn.close()
