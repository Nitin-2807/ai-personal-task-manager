"""
Database module for AI-Powered Personal Task Manager.

Provides SQLite connection management, schema initialization,
and transaction handling using Python's built-in sqlite3 module.
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional

from src.config import config


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    due_date TEXT NOT NULL,
    due_time TEXT,
    due_period TEXT CHECK (due_period IS NULL OR due_period IN ('morning', 'afternoon', 'evening', 'night')),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'completed')),
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_due_date ON tasks(due_date);
"""


class DatabaseError(Exception):
    """Base exception for database errors."""
    pass


class DatabaseConnectionError(DatabaseError):
    """Raised when database connection fails."""
    pass


class DatabaseOperationError(DatabaseError):
    """Raised when a database operation fails."""
    pass


def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """
    Create a new SQLite connection with proper configuration.

    Args:
        db_path: Optional path to database file. Uses config default if not provided.

    Returns:
        Configured sqlite3.Connection with row_factory set to sqlite3.Row.

    Raises:
        DatabaseConnectionError: If connection cannot be established.
    """
    path = db_path or config.get_db_path()
    try:
        conn = sqlite3.connect(str(path), detect_types=sqlite3.PARSE_DECLTYPES)
        conn.row_factory = sqlite3.Row
        # Enable foreign keys and WAL mode for better concurrency
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn
    except sqlite3.Error as e:
        raise DatabaseConnectionError(f"Failed to connect to database at {path}: {e}") from e


@contextmanager
def transaction(db_path: Optional[Path] = None) -> Generator[sqlite3.Connection, None, None]:
    """
    Context manager for database transactions.

    Commits on success, rolls back on exception.
    Ensures connection is closed in all cases.

    Args:
        db_path: Optional path to database file.

    Yields:
        sqlite3.Connection within a transaction.

    Raises:
        DatabaseOperationError: If transaction fails.
    """
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except sqlite3.Error as e:
        conn.rollback()
        raise DatabaseOperationError(f"Database transaction failed: {e}") from e
    finally:
        conn.close()


def _migrate_schema(conn: sqlite3.Connection) -> None:
    """
    Add structured due-time columns to pre-existing databases safely.

    Existing tasks are preserved; new columns are NULL for old rows.
    """
    columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()
    }
    if "due_time" not in columns:
        conn.execute("ALTER TABLE tasks ADD COLUMN due_time TEXT")
    if "due_period" not in columns:
        conn.execute(
            "ALTER TABLE tasks ADD COLUMN due_period TEXT "
            "CHECK (due_period IS NULL OR "
            "due_period IN ('morning', 'afternoon', 'evening', 'night'))"
        )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_tasks_due_datetime "
        "ON tasks(due_date, due_time)"
    )


def initialize_database(db_path: Optional[Path] = None) -> None:
    """
    Initialize the database schema and run safe in-place migrations.

    Creates the tasks table and indexes if they don't exist, then adds
    structured due-time columns to older databases. Safe to call multiple
    times - preserves existing data.

    Args:
        db_path: Optional path to database file.

    Raises:
        DatabaseOperationError: If schema creation fails.
    """
    try:
        with transaction(db_path) as conn:
            conn.executescript(SCHEMA_SQL)
            _migrate_schema(conn)
    except DatabaseOperationError:
        raise
    except Exception as e:
        raise DatabaseOperationError(f"Failed to initialize database: {e}") from e


def verify_database(db_path: Optional[Path] = None) -> bool:
    """
    Verify that the database schema exists and is correct.

    Args:
        db_path: Optional path to database file.

    Returns:
        True if schema is valid, False otherwise.
    """
    try:
        with get_connection(db_path) as conn:
            # Check tasks table exists with correct columns
            cursor = conn.execute("""
                SELECT sql FROM sqlite_master
                WHERE type='table' AND name='tasks'
            """)
            row = cursor.fetchone()
            if not row:
                return False

            # Verify required columns exist
            cursor = conn.execute("PRAGMA table_info(tasks)")
            columns = {row["name"]: row for row in cursor.fetchall()}
            required = {
                "id",
                "title",
                "due_date",
                "due_time",
                "due_period",
                "status",
                "created_at",
            }
            if not required.issubset(columns.keys()):
                return False

            # Verify status constraint
            if columns["status"]["notnull"] != 1:
                return False

            return True
    except Exception:
        return False