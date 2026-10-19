"""
Task Service tests for AI-Personal Task Manager.

Tests task creation, listing, completion, retrieval, and error handling.
"""

from datetime import date, timedelta

import pytest

from src.models import TaskStatus, OperationResult
from src.task_service import TaskService


class TestTaskCreation:
    """Tests for task creation."""

    def test_create_task_success(self, task_service):
        """Test successful task creation."""
        tomorrow = date.today() + timedelta(days=1)
        result = task_service.create_task("Test task", tomorrow)

        assert result.success is True
        assert result.status == "created"
        assert result.task is not None
        assert result.task.title == "Test task"
        assert result.task.due_date == tomorrow
        assert result.task.status == TaskStatus.PENDING

    def test_create_task_empty_title_fails(self, task_service):
        """Test that empty title is rejected."""
        tomorrow = date.today() + timedelta(days=1)
        result = task_service.create_task("", tomorrow)

        assert result.success is False
        assert result.status == "error"
        assert "empty" in result.message.lower()

    def test_create_task_whitespace_title_fails(self, task_service):
        """Test that whitespace-only title is rejected."""
        tomorrow = date.today() + timedelta(days=1)
        result = task_service.create_task("   ", tomorrow)

        assert result.success is False
        assert result.status == "error"

    def test_create_task_invalid_date_fails(self, task_service):
        """Test that invalid date is rejected."""
        result = task_service.create_task("Test task", "not a date")

        assert result.success is False
        assert result.status == "error"

    def test_create_task_persists_in_database(self, task_service):
        """Test that created task persists and can be retrieved."""
        tomorrow = date.today() + timedelta(days=1)
        result = task_service.create_task("Persistent task", tomorrow)

        assert result.success is True
        task_id = result.task.id

        # Retrieve via service
        detail_result = task_service.get_task_details("Persistent task")
        assert detail_result.success is True
        assert detail_result.task.id == task_id


class TestListPendingTasks:
    """Tests for listing pending tasks."""

    def test_list_pending_empty(self, task_service):
        """Test listing pending tasks when none exist."""
        result = task_service.list_pending_tasks()

        assert result.success is True
        assert result.status == "listed"
        assert result.count == 0

    def test_list_pending_only_returns_pending(self, task_service):
        """Test that only pending tasks are returned."""
        today = date.today()
        tomorrow = today + timedelta(days=1)

        task_service.create_task("Pending task 1", tomorrow)
        task_service.create_task("Pending task 2", tomorrow)

        # Complete one
        task_service.complete_task("Pending task 1")

        result = task_service.list_pending_tasks()

        assert result.success is True
        assert result.count == 1
        assert result.task is None  # listed result doesn't have single task
        # The message should indicate 1 task

    def test_list_pending_excludes_completed(self, task_service):
        """Test that completed tasks are not in pending list."""
        tomorrow = date.today() + timedelta(days=1)

        task_service.create_task("Will complete", tomorrow)
        task_service.complete_task("Will complete")

        result = task_service.list_pending_tasks()

        assert result.success is True
        assert result.count == 0


class TestTaskCompletion:
    """Tests for task completion."""

    def test_complete_task_success(self, task_service):
        """Test successful task completion."""
        tomorrow = date.today() + timedelta(days=1)
        task_service.create_task("Task to complete", tomorrow)

        result = task_service.complete_task("Task to complete")

        assert result.success is True
        assert result.status == "completed"
        assert result.task is not None
        assert result.task.status == TaskStatus.COMPLETED

    def test_complete_nonexistent_task_fails(self, task_service):
        """Test completing a task that doesn't exist."""
        result = task_service.complete_task("Nonexistent task")

        assert result.success is False
        assert result.status == "not_found"

    def test_complete_ambiguous_task_returns_clarification(self, task_service):
        """Test that ambiguous task query returns clarification."""
        tomorrow = date.today() + timedelta(days=1)
        task_service.create_task("Python assignment", tomorrow)
        task_service.create_task("Python interview prep", tomorrow)

        result = task_service.complete_task("Python")

        assert result.success is False
        assert result.status == "ambiguous"
        assert len(result.matches) == 2

    def test_complete_already_completed_task(self, task_service):
        """Test completing an already completed task."""
        tomorrow = date.today() + timedelta(days=1)
        task_service.create_task("Already done", tomorrow)
        task_service.complete_task("Already done")

        result = task_service.complete_task("Already done")

        assert result.success is False
        assert result.status == "already_completed"

    def test_complete_empty_query_fails(self, task_service):
        """Test that empty query is rejected."""
        result = task_service.complete_task("")

        assert result.success is False
        assert result.status == "error"


class TestTaskDetails:
    """Tests for retrieving task details."""

    def test_get_details_success(self, task_service):
        """Test successful task detail retrieval."""
        tomorrow = date.today() + timedelta(days=1)
        task_service.create_task("Detail task", tomorrow)

        result = task_service.get_task_details("Detail task")

        assert result.success is True
        assert result.status == "retrieved"
        assert result.task is not None
        assert result.task.title == "Detail task"

    def test_get_details_nonexistent(self, task_service):
        """Test retrieving details for nonexistent task."""
        result = task_service.get_task_details("Does not exist")

        assert result.success is False
        assert result.status == "not_found"

    def test_get_details_ambiguous(self, task_service):
        """Test retrieving details for ambiguous query."""
        tomorrow = date.today() + timedelta(days=1)
        task_service.create_task("Python task 1", tomorrow)
        task_service.create_task("Python task 2", tomorrow)

        result = task_service.get_task_details("Python")

        assert result.success is False
        assert result.status == "ambiguous"
        assert len(result.matches) == 2


class TestTaskMatching:
    """Tests for task matching logic."""

    def test_exact_match(self, task_service):
        """Test exact case-insensitive title match."""
        tomorrow = date.today() + timedelta(days=1)
        task_service.create_task("Exact Match Task", tomorrow)

        result = task_service.get_task_details("exact match task")
        assert result.success is True
        assert result.task.title == "Exact Match Task"

    def test_partial_match(self, task_service):
        """Test partial title match when no exact match."""
        tomorrow = date.today() + timedelta(days=1)
        task_service.create_task("Unique Task Title", tomorrow)

        result = task_service.get_task_details("Unique Task")
        assert result.success is True
        assert result.task.title == "Unique Task Title"

    def test_multiple_partial_matches_ambiguous(self, task_service):
        """Test multiple partial matches returns ambiguous."""
        tomorrow = date.today() + timedelta(days=1)
        task_service.create_task("Python homework", tomorrow)
        task_service.create_task("Python project", tomorrow)

        result = task_service.get_task_details("Python")
        assert result.success is False
        assert result.status == "ambiguous"
        assert len(result.matches) == 2

    def test_no_match(self, task_service):
        """Test no match returns not_found."""
        result = task_service.get_task_details("Completely different")
        assert result.success is False
        assert result.status == "not_found"


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_persistence_across_service_instances(self, temp_db_path):
        """Test that tasks persist across TaskService instances."""
        tomorrow = date.today() + timedelta(days=1)

        service1 = TaskService(temp_db_path)
        service1.create_task("Persistent task", tomorrow)

        service2 = TaskService(temp_db_path)
        result = service2.get_task_details("Persistent task")

        assert result.success is True
        assert result.task.title == "Persistent task"

    def test_verify_database(self, task_service):
        """Test database verification."""
        assert task_service.verify_database() is True