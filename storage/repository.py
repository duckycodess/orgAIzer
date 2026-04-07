"""
storage/repository.py — CRUD operations for all database tables.

Each repository class takes a sqlite3.Connection so it can participate
in transactions without owning the connection lifecycle.
"""

import json
import sqlite3
from datetime import datetime
from typing import Any


# ---------------------------------------------------------------------------
# SettingsRepo
# ---------------------------------------------------------------------------

class SettingsRepo:
    """Read and write key-value settings."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get(self, key: str, default: str = "") -> str:
        row = self._conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else default

    def set(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?)"
            " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self._conn.commit()

    def get_float(self, key: str, default: float = 0.0) -> float:
        try:
            return float(self.get(key, str(default)))
        except ValueError:
            return default

    def get_int(self, key: str, default: int = 0) -> int:
        try:
            return int(self.get(key, str(default)))
        except ValueError:
            return default

    def get_bool(self, key: str, default: bool = False) -> bool:
        return self.get(key, "1" if default else "0") == "1"


# ---------------------------------------------------------------------------
# FileEventRepo
# ---------------------------------------------------------------------------

class FileEventRepo:
    """Log and query file processing events."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert(
        self,
        filename: str,
        original_path: str,
        stage: str,
        destination_path: str | None = None,
        school_confidence: float | None = None,
        course_predicted: str | None = None,
        course_confidence: float | None = None,
        category_predicted: str | None = None,
        category_confidence: float | None = None,
        prediction_reason: str | None = None,
        user_action: str | None = None,
        final_course: str | None = None,
        final_category: str | None = None,
        notes: str | None = None,
        feature_text: str | None = None,   # extracted document text for retraining
        file_size: int | None = None,       # bytes at time of detection
    ) -> int:
        """Insert a new event and return its id."""
        cursor = self._conn.execute(
            """
            INSERT INTO file_events (
                timestamp, filename, original_path, destination_path,
                stage, school_confidence, course_predicted, course_confidence,
                category_predicted, category_confidence, prediction_reason,
                user_action, final_course, final_category, notes,
                feature_text, file_size
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now().isoformat(timespec="seconds"),
                filename, original_path, destination_path,
                stage, school_confidence, course_predicted, course_confidence,
                category_predicted, category_confidence, prediction_reason,
                user_action, final_course, final_category, notes,
                feature_text, file_size,
            ),
        )
        self._conn.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    def update(self, event_id: int, **fields: Any) -> None:
        """Update arbitrary columns on an existing event."""
        if not fields:
            return
        set_clause = ", ".join(f"{col} = ?" for col in fields)
        values = list(fields.values()) + [event_id]
        self._conn.execute(
            f"UPDATE file_events SET {set_clause} WHERE id = ?", values
        )
        self._conn.commit()

    def get_all(self, limit: int = 200) -> list[dict]:
        """Return recent events newest-first."""
        rows = self._conn.execute(
            "SELECT * FROM file_events ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_by_id(self, event_id: int) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM file_events WHERE id = ?", (event_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_pending(self) -> list[dict]:
        """Return events that are waiting for user action."""
        rows = self._conn.execute(
            "SELECT * FROM file_events WHERE stage = 'pending' ORDER BY id DESC"
        ).fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# TrainingSampleRepo
# ---------------------------------------------------------------------------

class TrainingSampleRepo:
    """Store and retrieve labeled training samples for model retraining."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert(
        self,
        filename: str,
        text_features: str,   # JSON-encoded text (up to 4000 chars)
        extension: str,
        file_size: int,
        label_school: int,    # 0 or 1
        label_course: str | None,
        label_category: str | None,
        source: str,          # 'user_correction', 'user_accept', 'bootstrap'
    ) -> int:
        cursor = self._conn.execute(
            """
            INSERT INTO training_samples (
                timestamp, filename, text_features, extension,
                file_size, label_school, label_course, label_category, source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now().isoformat(timespec="seconds"),
                filename, text_features, extension,
                file_size, label_school, label_course, label_category, source,
            ),
        )
        self._conn.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    def get_all(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM training_samples ORDER BY id ASC"
        ).fetchall()
        return [dict(r) for r in rows]

    def count(self) -> int:
        return self._conn.execute(
            "SELECT COUNT(*) FROM training_samples"
        ).fetchone()[0]

    def count_school(self) -> int:
        """Count samples labeled as school-related (label_school=1)."""
        return self._conn.execute(
            "SELECT COUNT(*) FROM training_samples WHERE label_school = 1"
        ).fetchone()[0]

    def count_for_course(self, course: str) -> int:
        """Count school samples for a specific course."""
        return self._conn.execute(
            "SELECT COUNT(*) FROM training_samples"
            " WHERE label_school = 1 AND label_course = ?",
            (course,),
        ).fetchone()[0]


# ---------------------------------------------------------------------------
# CourseFolderRepo
# ---------------------------------------------------------------------------

class CourseFolderRepo:
    """Manage discovered course folders from the School root directory."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def upsert(self, course_name: str, folder_path: str, subfolders: list[str]) -> None:
        """Insert or replace a course folder record."""
        self._conn.execute(
            """
            INSERT INTO course_folders (course_name, folder_path, subfolders)
            VALUES (?, ?, ?)
            ON CONFLICT(course_name) DO UPDATE SET
                folder_path = excluded.folder_path,
                subfolders  = excluded.subfolders
            """,
            (course_name, folder_path, json.dumps(subfolders)),
        )
        self._conn.commit()

    def get_all(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM course_folders ORDER BY course_name ASC"
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["subfolders"] = json.loads(d["subfolders"] or "[]")
            result.append(d)
        return result

    def get_course_names(self) -> list[str]:
        rows = self._conn.execute(
            "SELECT course_name FROM course_folders ORDER BY course_name ASC"
        ).fetchall()
        return [r["course_name"] for r in rows]

    def clear(self) -> None:
        self._conn.execute("DELETE FROM course_folders")
        self._conn.commit()
