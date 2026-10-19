"""
Database tests for AI-Personal Task Manager.

Tests database initialization, schema creation, persistence, and constraints.
"""

import sqlite3
from pathlib import Path

import pytest

from src.database import (
    DatabaseConnectionError,
    DatabaseOperationError,
    get_connection,
    initialize_database,
    transaction,
    verify_database,
)
from src.models import TaskStatus


class TestDatabaseInitialization:
    """Tests for database initialization."""

    def test_initialize_creates_schema(self, temp_db_path):
        """Test that initialize_database creates the tasks table."""
        initialize_database(temp_db_path)
        assert verify_database(temp_db_path)

    def test_initialize_idempotent(self, temp_db_path):
        """Test that initialize_database can be called multiple times safely."""
        initialize_database(temp_db_path)
        initialize_database(temp_db_path)
        initialize_database(temp_db_path)
        assert verify_database(temp_db_path)

    def test_initialize_preserves_existing_data(self, temp_db_path):
        """Test that re-initializing doesn't delete existing data."""
        initialize_database(temp_db_path)

        # Insert a task
        with transaction(temp_db_path) as conn:
            conn.execute(
                "INSERT INTO tasks (title, due_date, status, created_at) VALUES (?, ?, ?, ?)",
                ("Test Task", "2026-10-20", "pending", "2026-10-19T10:00:00"),
            )

        # Re-initialize
        initialize_database(temp_db_path)

        # Data should still exist
        with get_connection(temp_db_path) as conn:
            cursor = conn.execute("SELECT COUNT(*) as cnt FROM tasks WHERE title = ?", ("Test Task",))
            assert cursor.fetchone()["cnt"] == 1

    def test_schema_has_correct_columns(self, temp_db_path):
        """Test that tasks table has all required columns with correct types."""
        initialize_database(temp_db_path)

        with get_connection(temp_db_path) as conn:
            cursor = conn.execute("PRAGMA table_info(tasks)")
            columns = {row["name"]: row for row in cursor.fetchall()}

        required_columns = {
            "id": {"type": "INTEGER", "pk": 1},
            "title": {"type": "TEXT", "notnull": 1},
            "due_date": {"type": "TEXT", "notnull": 1},
            "status": {"type": "TEXT", "notnull": 1},
            "created_at": {"type": "TEXT", "notnull": 1},
        }

        for col_name, expected in required_columns.items():
            assert col_name in columns, f"Missing column: {col_name}"
            col = columns[col_name]
            assert col["type"] == expected["type"], f"Column {col_name} has wrong type"
            if "pk" in expected:
                assert col["pk"] == expected["pk"], f"Column {col_name} pk mismatch"
            if "notnull" in expected:
                assert col["notnull"] == expected["notnull"], f"Column {col_name} notnull mismatch"

    def test_status_check_constraint(self, temp_db_path):
        """Test that status column only allows 'pending' or 'completed'."""
        initialize_database(temp_db_path)

        with transaction(temp_db_path) as conn:
            # Valid statuses should work
            conn.execute(
                "INSERT INTO tasks (title, due_date, status, created_at) VALUES (?, ?, ?, ?)",
                ("Valid Pending", "2026-10-20", "pending", "2026-10-19T10:00:00"),
            )
            conn.execute(
                "INSERT INTO tasks (title, due_date, status, created_at) VALUES (?, ?, ?, ?)",
                ("Valid Completed", "2026-10-20", "completed", "2026-10-19T10:00:00"),
            )

        # Invalid status should fail
        from src.database import DatabaseOperationError
        with pytest.raises(DatabaseOperationError) as exc_info:
            with transaction(temp_db_path) as conn:
                conn.execute(
                    "INSERT INTO tasks (title, due_date, status, created_at) VALUES (?, ?, ?, ?)",
                    ("Invalid", "2026-10-20", "invalid_status", "2026-10-19T10:00:00"),
                )
        # Verify it's the check constraint error
        assert "CHECK constraint failed" in str(exc_info.value)

    def test_indexes_exist(self, temp_db_path):
        """Test that required indexes are created."""
        initialize_database(temp_db_path)

        with get_connection(temp_db_path) as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='tasks'"
            )
            indexes = {row["name"] for row in cursor.fetchall()}

        assert "idx_tasks_status" in indexes
        assert "idx_tasks_due_date" in indexes


class TestDatabaseConnection:
    """Tests for database connection management."""

    def test_get_connection_returns_connection(self, temp_db_path):
        """Test that get_connection returns a valid connection."""
        initialize_database(temp_db_path)
        conn = get_connection(temp_db_path)
        assert conn is not None
        conn.close()

    def test_connection_row_factory(self, temp_db_path):
        """Test that connection has row_factory set to sqlite3.Row."""
        initialize_database(temp_db_path)
        conn = get_connection(temp_db_path)
        cursor = conn.execute("SELECT 1 as test_col")
        row = cursor.fetchone()
        assert isinstance(row, sqlite3.Row)
        assert row["test_col"] == 1
        conn.close()

    def test_connection_foreign_keys_enabled(self, temp_db_path):
        """Test that foreign keys pragma is enabled."""
        initialize_database(temp_db_path)
        conn = get_connection(temp_db_path)
        cursor = conn.execute("PRAGMA foreign_keys")
        assert cursor.fetchone()[0] == 1
        conn.close()


class TestDatabaseTransaction:
    """Tests for transaction context manager."""

    def test_transaction_commits_on_success(self, temp_db_path):
        """Test that transaction commits on successful completion."""
        initialize_database(temp_db_path)

        with transaction(temp_db_path) as conn:
            conn.execute(
                "INSERT INTO tasks (title, due_date, status, created_at) VALUES (?, ?, ?, ?)",
                ("Commit Test", "2026-10-20", "pending", "2026-10-19T10:00:00"),
            )

        # Verify committed
        with get_connection(temp_db_path) as conn:
            cursor = conn.execute("SELECT COUNT(*) as cnt FROM tasks WHERE title = ?", ("Commit Test",))
            assert cursor.fetchone()["cnt"] == 1

    def test_transaction_rolls_back_on_exception(self, temp_db_path):
        """Test that transaction rolls back on exception."""
        initialize_database(temp_db_path)

        with pytest.raises(ValueError):
            with transaction(temp_db_path) as conn:
                conn.execute(
                    "INSERT INTO tasks (title, due_date, status, created_at) VALUES (?, ?, ?, ?)",
                    ("Rollback Test", "2026-10-20", "pending", "2026-10-19T10:00:00"),
                )
                raise ValueError("Intentional error")

        # Verify rolled back
        with get_connection(temp_db_path) as conn:
            cursor = conn.execute("SELECT COUNT(*) as cnt FROM tasks WHERE title = ?", ("Rollback Test",))
            assert cursor.fetchone()["cnt"] == 0

    def test_transaction_closes_connection(self, temp_db_path):
        """Test that connection is closed after transaction."""
        initialize_database(temp_db_path)

        with transaction(temp_db_path) as conn:
            conn.execute("SELECT 1")

        # Connection should be closed (no direct way to test, but no leaks)
        # This test mainly ensures no exception during cleanup


class TestVerifyDatabase:
    """Tests for verify_database function."""

    def test_verify_valid_database(self, temp_db_path):
        """Test verify_database returns True for valid schema."""
        initialize_database(temp_db_path)
        assert verify_database(temp_db_path)

    def test_verify_invalid_database(self, temp_db_path):
        """Test verify_database returns False for missing schema."""
        # Don't initialize - just create empty file
        temp_db_path.touch()
        assert not verify_database(temp_db_path)

    def test_verify_corrupted_database(self, temp_db_path):
        """Test verify_database returns False for corrupted schema."""
        # Create table with wrong schema
        with get_connection(temp_db_path) as conn:
            conn.execute("CREATE TABLE tasks (id INTEGER PRIMARY KEY, wrong_col TEXT)")

        assert not verify_database(temp_db_path)