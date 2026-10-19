"""
Database migration tests for structured due times.

Verifies that pre-existing databases gain the ``due_time``/``due_period``
columns safely, without data loss, and that the migrated schema supports the
new behaviour.
"""

import sqlite3
from datetime import date

import pytest

from src.database import initialize_database, verify_database
from src.task_repository import TaskRepository
from src.task_service import TaskService

LEGACY_SCHEMA = """
CREATE TABLE tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    due_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'completed')),
    created_at TEXT NOT NULL
);
CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_tasks_due_date ON tasks(due_date);
"""


def _create_legacy_db(path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(LEGACY_SCHEMA)
    conn.execute(
        "INSERT INTO tasks (title, due_date, status, created_at) VALUES (?, ?, ?, ?)",
        ("Legacy pending", "2026-10-20", "pending", "2026-10-01T09:00:00"),
    )
    conn.execute(
        "INSERT INTO tasks (title, due_date, status, created_at) VALUES (?, ?, ?, ?)",
        ("Legacy done", "2026-10-18", "completed", "2026-10-01T10:00:00"),
    )
    conn.commit()
    conn.close()


def _column_names(path) -> set:
    conn = sqlite3.connect(path)
    columns = {
        row[1] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()
    }
    conn.close()
    return columns


def _index_names(path) -> set:
    conn = sqlite3.connect(path)
    indexes = {
        row[1]
        for row in conn.execute("PRAGMA index_list(tasks)").fetchall()
    }
    conn.close()
    return indexes


class TestMigration:
    """initialize_database must upgrade old databases in place."""

    def test_columns_added_and_rows_preserved(self, temp_db_path):
        _create_legacy_db(temp_db_path)

        initialize_database(temp_db_path)

        columns = _column_names(temp_db_path)
        assert {"due_time", "due_period"} <= columns
        assert verify_database(temp_db_path) is True

        conn = sqlite3.connect(temp_db_path)
        rows = conn.execute(
            "SELECT title, status, due_time, due_period FROM tasks ORDER BY id"
        ).fetchall()
        conn.close()
        assert rows == [
            ("Legacy pending", "pending", None, None),
            ("Legacy done", "completed", None, None),
        ]

    def test_migration_is_idempotent(self, temp_db_path):
        _create_legacy_db(temp_db_path)
        initialize_database(temp_db_path)
        initialize_database(temp_db_path)
        initialize_database(temp_db_path)

        assert verify_database(temp_db_path) is True
        conn = sqlite3.connect(temp_db_path)
        count = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        conn.close()
        assert count == 2

    def test_new_database_has_time_columns_and_index(self, temp_db_path):
        initialize_database(temp_db_path)

        assert {"due_time", "due_period"} <= _column_names(temp_db_path)
        assert "idx_tasks_due_datetime" in _index_names(temp_db_path)
        assert "idx_tasks_due_date" in _index_names(temp_db_path)

    def test_unmigrated_legacy_database_fails_verification(self, temp_db_path):
        _create_legacy_db(temp_db_path)
        assert verify_database(temp_db_path) is False

    def test_migrated_database_supports_service_operations(self, temp_db_path):
        _create_legacy_db(temp_db_path)
        initialize_database(temp_db_path)

        service = TaskService(temp_db_path)
        created = service.create_task(
            "New timed task", date(2026, 10, 20), due_time="10:00"
        )
        assert created.success is True

        listing = service._repo.get_pending_tasks()
        titles = [task.title for task in listing]
        # Legacy untimed task sorts before the timed task on the same date.
        assert titles == ["Legacy pending", "New timed task"]
        assert listing[0].due_time is None
        assert listing[1].due_time == "10:00"

        details = service.get_task_details("Legacy pending")
        assert details.success is True
        assert "2026-10-20" in details.message

    def test_completion_of_legacy_task_still_works(self, temp_db_path):
        _create_legacy_db(temp_db_path)
        initialize_database(temp_db_path)

        service = TaskService(temp_db_path)
        result = service.complete_task("Legacy pending")

        assert result.success is True
        remaining = [t.title for t in service._repo.get_pending_tasks()]
        assert remaining == []


class TestSchemaConstraints:
    """The migrated schema must reject invalid periods at the database level."""

    def test_invalid_period_rejected_by_check_constraint(self, temp_db_path):
        initialize_database(temp_db_path)
        conn = sqlite3.connect(temp_db_path)

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO tasks (title, due_date, due_period, status, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                ("Bad period", "2026-10-20", "dawn", "pending", "2026-10-01T09:00:00"),
            )
        conn.close()

    def test_repository_rejects_invalid_period(self, temp_db_path):
        repo = TaskRepository(temp_db_path)
        initialize_database(temp_db_path)

        with pytest.raises(ValueError):
            repo.create_task("Bad period", date(2026, 10, 20), due_period="dawn")

    def test_repository_accepts_nullable_period_after_migration(self, temp_db_path):
        _create_legacy_db(temp_db_path)
        initialize_database(temp_db_path)

        repo = TaskRepository(temp_db_path)
        task = repo.create_task(
            "Evening task", date(2026, 10, 20), due_period="evening"
        )
        assert task.due_period == "evening"
        assert task.due_time is None
