"""
tests/conftest.py — Shared pytest fixtures.
"""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from storage.db import get_connection, init_schema


@pytest.fixture
def tmp_dir(tmp_path: Path) -> Path:
    """A fresh temporary directory for each test."""
    return tmp_path


@pytest.fixture
def db_conn() -> sqlite3.Connection:
    """In-memory SQLite database with schema initialized."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    init_schema(conn)
    yield conn
    conn.close()
