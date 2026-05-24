"""
app/api_controller.py -- Controller for FastAPI backend (no Qt dependency).

Mirrors app/controller.py but replaces:
  - QObject/Signal  → plain callbacks
  - QThread         → threading.Thread
  - _features_ready Qt signal → queue.Queue (thread-safe marshaling)
"""

from __future__ import annotations

import json
import logging
import queue
import threading
from pathlib import Path
from typing import Callable

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

EventCallback = Callable[[str, dict], None]


def _normalize_subject_name(subject: str) -> str:
    return " ".join(subject.strip().split())


def _is_valid_subject_name(subject: str) -> bool:
    normalized = _normalize_subject_name(subject)
    if not normalized or normalized in {".", ".."}:
        return False
    return "/" not in normalized and "\\" not in normalized


class APIController:
    """
    Pure-Python controller (no Qt). Emits events via registered callbacks.

    Thread safety: a single RLock serializes all DB/classifier access.
    The watcher fires in its own thread; features are queued and processed
    by a dedicated processor thread to keep DB writes serialized.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._event_callbacks: list[EventCallback] = []

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
        legacy_model = model_dir / "course_predictor.pkl"
        self._subject_pred.load_model(
            subject_model if subject_model.exists() else legacy_model
        )
        self._refresh_subject_list()

        self._in_flight: set[str] = set()
        self._in_flight_lock = threading.Lock()
        self._undo_pending_paths: dict[int, str] = {}

        self._feature_queue: queue.Queue[dict | None] = queue.Queue()
        self._processor = threading.Thread(
            target=self._process_loop, daemon=True, name="feature-processor"
        )
        self._processor.start()

        self._watcher = FileWatcher(
            self._settings.effective_watch_folder,
            self._on_file_detected,
        )
        self._retrain_thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # Event subscription
    # ------------------------------------------------------------------

    def add_event_callback(self, cb: EventCallback) -> None:
        self._event_callbacks.append(cb)

    def remove_event_callback(self, cb: EventCallback) -> None:
        self._event_callbacks.discard(cb) if hasattr(self._event_callbacks, "discard") else None
        try:
            self._event_callbacks.remove(cb)
        except ValueError:
            pass

    def _emit(self, event_type: str, data: dict) -> None:
        for cb in list(self._event_callbacks):
            try:
                cb(event_type, data)
            except Exception as exc:
                logger.warning("Event callback error: %s", exc)

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
        with self._lock:
            self._settings.save(self._settings_repo)

    def get_history(self, limit: int = 200) -> list[dict]:
        with self._lock:
            return self._event_repo.get_all(limit)

    def get_pending(self) -> list[dict]:
        with self._lock:
            return self._event_repo.get_pending()

    def get_subject_names(self) -> list[str]:
        with self._lock:
            return self._subject_repo.get_subject_names()

    def scan_subject_folders(self, school_root: str) -> int:
        root = Path(school_root)
        if not root.exists():
            return 0
        with self._lock:
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

    def clear_training_samples(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM training_samples")
            self._conn.commit()

    def seed_from_folder(self, folder: str) -> int:
        root = Path(folder)
        if not root.is_dir():
            return 0
        count = 0
        with self._lock:
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
                    text = " ".join(t for t in [stem_tokens, parent_tokens, subject_name] if t)
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
        self, event_id: int, final_subject: str, action: str
    ) -> str | None:
        with self._lock:
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
                    return None
                if not _is_valid_subject_name(normalized_subject):
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

    def handle_mark_as_school(self, event_id: int, subject: str) -> str | None:
        with self._lock:
            event = self._event_repo.get_by_id(event_id)
            if not event or event.get("stage") != "not_school":
                return None
            normalized = _normalize_subject_name(subject)
            if not normalized or not _is_valid_subject_name(normalized):
                return None
            canonical = self._canonical_subject_name(normalized)
            school_root = self._settings.school_root
            dest_path = None

            if school_root:
                dest_dir = Path(school_root) / canonical
                try:
                    dest_dir.mkdir(parents=True, exist_ok=True)
                except OSError:
                    pass
                try:
                    dest_path = safe_move(event["original_path"], str(dest_dir))
                    self._event_repo.update(
                        event_id,
                        destination_path=dest_path,
                        stage="moved",
                        user_action="corrected_not_school",
                        final_course=canonical,
                    )
                except (FileNotFoundError, OSError) as exc:
                    self._event_repo.update(
                        event_id, stage="skipped",
                        user_action="corrected_not_school",
                        final_course=canonical,
                        notes=str(exc),
                    )
                self._register_subject_folder(canonical)
            else:
                self._event_repo.update(
                    event_id, stage="skipped",
                    user_action="corrected_not_school",
                    final_course=canonical,
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
        with self._lock:
            event = self._event_repo.get_by_id(event_id)
            if not event:
                return False
            dest = event.get("destination_path")
            original = event.get("original_path")
            if not dest or not original:
                return False

        with self._in_flight_lock:
            self._in_flight.add(original)

        success = undo_move(dest, original)
        with self._lock:
            if success:
                self._event_repo.update(event_id, stage="undone", user_action="undone")
                self._queue_as_pending_after_undo(event, original)
            else:
                with self._in_flight_lock:
                    self._in_flight.discard(original)
        return success

    def trigger_retrain(self) -> None:
        with self._lock:
            samples = self._sample_repo.get_all()
        if not samples:
            return
        if self._retrain_thread and self._retrain_thread.is_alive():
            return
        self._retrain_thread = threading.Thread(
            target=self._retrain_work,
            args=(samples,),
            daemon=True,
            name="retrain-worker",
        )
        self._retrain_thread.start()

    def get_warmup_status(self) -> tuple[int, int]:
        return self._settings.warmup_labeled_count, WARMUP_MIN_SCHOOL_LABELS

    def shutdown(self) -> None:
        self.stop_watching()
        self._feature_queue.put(None)
        self._conn.close()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _process_loop(self) -> None:
        while True:
            data = self._feature_queue.get()
            if data is None:
                break
            path = data.get("path", "")
            try:
                with self._lock:
                    self._run_pipeline(data)
            finally:
                with self._in_flight_lock:
                    self._in_flight.discard(path)

    def _on_file_detected(self, path: str) -> None:
        with self._in_flight_lock:
            if path in self._in_flight:
                return
            self._in_flight.add(path)

        emitted = False
        try:
            p = Path(path)
            if p.is_dir():
                if not wait_until_stable_dir(path):
                    return
                if not p.exists():
                    return
                features = extract_folder_features(path)
            else:
                if not wait_until_stable(path):
                    return
                if not p.exists():
                    return
                features = extract_features(path)
            self._feature_queue.put({
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
            self._emit("file_status", {
                "event_id": eid,
                "filename": features.filename,
                "stage": "not_school",
                "school_confidence": school_conf,
                "reason": school_reason,
            })
            return

        overall_conf = (
            min(c for c in [school_conf, subject_conf] if c is not None)
            if subject_conf > 0 else school_conf
        )
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
                self._emit("file_auto_moved", {
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
                self._emit("file_status", {
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
            self._emit("file_classified", {
                "event_id": eid,
                "filename": features.filename,
                "original_path": features.path,
                "subject": subject,
                "overall_confidence": overall_conf,
                "school_confidence": school_conf,
                "subject_confidence": subject_conf,
                "reason": reason,
            })

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
        self._emit("file_classified", {
            "event_id": eid,
            "filename": filename,
            "original_path": original_path,
            "subject": subject,
            "overall_confidence": overall,
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

    def _refresh_subject_list(self) -> None:
        self._subject_pred.set_known_subjects(self._subject_repo.get_subject_names())

    def _canonical_subject_name(self, subject_name: str) -> str:
        for existing in self._subject_repo.get_subject_names():
            if existing.casefold() == subject_name.casefold():
                return existing
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

    def _retrain_work(self, samples: list[dict]) -> None:
        logger.info("Background retrain started (%d samples)", len(samples))
        try:
            model_dir = get_models_dir()
            known_subjects = self.get_subject_names()
            school_det = SchoolDetector()
            subject_pred = SubjectPredictor()
            subject_pred.set_known_subjects(known_subjects)
            school_det.retrain(samples)
            school_det.save_model(model_dir / "school_detector.pkl")
            subject_pred.retrain(samples)
            subject_pred.save_model(model_dir / "subject_predictor.pkl")
            subject_pred.save_model(model_dir / "course_predictor.pkl")
            with self._lock:
                self._school_det.load_model(model_dir / "school_detector.pkl")
                subject_model = model_dir / "subject_predictor.pkl"
                self._subject_pred.load_model(subject_model)
            logger.info("Retrain complete, classifiers reloaded.")
            self._emit("retrain_done", {})
        except Exception as exc:
            logger.error("Retrain failed: %s", exc)
