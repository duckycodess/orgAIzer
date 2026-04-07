"""
storage/db.py -- SQLite connection and schema initialization.

The database lives in %APPDATA%/OrgAIzer/orgaizer.db.
WAL journal mode is enabled so the UI thread can read while
the background watcher thread writes without blocking.
"""

import os
import sqlite3
from pathlib import Path


def get_db_path() -> Path:
    """Return the path to the SQLite database file, creating the directory if needed."""
    app_data = os.environ.get("APPDATA", Path.home())
    db_dir = Path(app_data) / "OrgAIzer"
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / "orgaizer.db"


def get_models_dir() -> Path:
    """Return the directory where trained model pickles are stored."""
    app_data = os.environ.get("APPDATA", Path.home())
    models_dir = Path(app_data) / "OrgAIzer" / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    return models_dir


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """
    Open a SQLite connection with WAL mode and foreign keys enabled.
    Each call returns a new connection — callers are responsible for closing it.
    For long-lived objects (e.g. Repository), store the connection as an attribute.
    """
    path = db_path or get_db_path()
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row          # rows accessible as dicts
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _add_column_if_missing(
    conn: sqlite3.Connection, table: str, column: str, col_type: str
) -> None:
    """Add a column to an existing table; silently no-ops if it already exists."""
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # column already exists


def init_schema(conn: sqlite3.Connection) -> None:
    """Create all tables if they don't already exist."""
    conn.executescript("""
        -- App configuration: thresholds, paths, warm-up counters
        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        -- Complete history of every file event the app has processed
        CREATE TABLE IF NOT EXISTS file_events (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp           TEXT NOT NULL,
            filename            TEXT NOT NULL,
            original_path       TEXT NOT NULL,
            destination_path    TEXT,
            stage               TEXT NOT NULL,
            school_confidence   REAL,
            course_predicted    TEXT,
            course_confidence   REAL,
            category_predicted  TEXT,
            category_confidence REAL,
            prediction_reason   TEXT,
            user_action         TEXT,
            final_course        TEXT,
            final_category      TEXT,
            notes               TEXT
        );

        -- Labeled samples used to retrain the ML models
        CREATE TABLE IF NOT EXISTS training_samples (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp       TEXT NOT NULL,
            filename        TEXT NOT NULL,
            text_features   TEXT,
            extension       TEXT,
            file_size       INTEGER,
            label_school    INTEGER,
            label_course    TEXT,
            label_category  TEXT,
            source          TEXT
        );

        -- Course folders discovered by scanning the School root directory
        CREATE TABLE IF NOT EXISTS course_folders (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            course_name  TEXT NOT NULL UNIQUE,
            folder_path  TEXT NOT NULL,
            subfolders   TEXT
        );
    """)
    conn.commit()

    # Migrate: add columns introduced after the initial schema.
    # ALTER TABLE ADD COLUMN is idempotent-safe via try/except.
    _add_column_if_missing(conn, "file_events", "feature_text", "TEXT")
    _add_column_if_missing(conn, "file_events", "file_size",    "INTEGER")

    # Insert default settings on first run (only if they don't exist yet)
    defaults = {
        "downloads_path": str(Path.home() / "Downloads"),
        "school_root": "",
        "watch_folder_override": "",   # empty = use downloads_path
        "threshold_high": "0.85",
        "threshold_medium": "0.55",
        "warmup_active": "1",          # 1 = warm-up mode ON
        "warmup_labeled_count": "0",   # total confirmed school labels so far
        "correction_counter": "0",     # triggers background retrain every 5
    }
    for key, value in defaults.items():
        conn.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            (key, value),
        )
    conn.commit()
