"""
Task Service for AI-Powered Personal Task Manager.

Contains business logic for task operations, validation, and coordination
between the repository and higher layers. Independent of LLM provider.
"""

from datetime import date, datetime
from pathlib import Path
from typing import Optional

from src.config import config
from src.database import initialize_database, verify_database
from src.date_utils import normalize_period_value, normalize_time_value
from src.models import (
    MatchResult,
    OperationResult,
    Task,
    TaskMatch,
    TaskStatus,
)
from src.task_repository import TaskRepository


class TaskService:
    """
    Business logic layer for task management.

    Provides validated operations for creating, listing, completing,
    and retrieving tasks. All operations return structured results.
    """

    def __init__(self, db_path: Optional[Path] = None):
        self._repo = TaskRepository(db_path)
        self._db_path = db_path
        # Ensure database is initialized
        initialize_database(db_path)

    def create_task(
        self,
        title: str,
        due_date: date,
        due_time: Optional[str] = None,
        due_period: Optional[str] = None,
    ) -> OperationResult:
        """
        Create a new task with validation.

        Args:
            title: Task title (required, non-empty)
            due_date: Due date (required, valid date)
            due_time: Optional exact time in HH:MM (or a common format to normalize)
            due_period: Optional approximate period (morning/afternoon/evening/night)

        Returns:
            OperationResult with created task or error.
        """
        # Validate title
        if not title or not title.strip():
            return OperationResult.error("Task title cannot be empty")

        # Validate due_date
        if not isinstance(due_date, date):
            return OperationResult.error("Due date must be a valid date")

        try:
            normalized_time = normalize_time_value(due_time)
            normalized_period = normalize_period_value(due_period)
        except ValueError as e:
            return OperationResult.error(str(e))

        if normalized_time and normalized_period:
            return OperationResult.error(
                "Specify either an exact time or an approximate period, not both"
            )

        try:
            task = self._repo.create_task(
                title.strip(),
                due_date,
                due_time=normalized_time,
                due_period=normalized_period,
            )
            return OperationResult.created(task)
        except Exception as e:
            return OperationResult.error(f"Failed to create task: {e}")

    def list_pending_tasks(
        self,
        due_date: Optional[date] = None,
        end_date: Optional[date] = None,
        due_time: Optional[str] = None,
        due_period: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> OperationResult:
        """
        List pending tasks with optional date/time filters.

        Args:
            due_date: Inclusive earliest due date.
            end_date: Inclusive latest due date.
            due_time: Exact normalized time filter (HH:MM).
            due_period: Approximate period filter.
            limit: Maximum number of results (used for "next task" requests).

        Returns:
            OperationResult with matching pending tasks or error.
        """
        if due_date is not None and not isinstance(due_date, date):
            return OperationResult.error("due_date must be a valid date")
        if end_date is not None and not isinstance(end_date, date):
            return OperationResult.error("end_date must be a valid date")
        if due_date is not None and end_date is not None and end_date < due_date:
            return OperationResult.error("end_date cannot be earlier than due_date")

        try:
            normalized_time = normalize_time_value(due_time)
            normalized_period = normalize_period_value(due_period)
        except ValueError as e:
            return OperationResult.error(str(e))

        if normalized_time and normalized_period:
            return OperationResult.error(
                "Specify either an exact time or an approximate period, not both"
            )

        if limit is not None:
            try:
                limit = int(limit)
            except (TypeError, ValueError):
                return OperationResult.error("limit must be a positive integer")
            if limit < 1:
                return OperationResult.error("limit must be a positive integer")

        try:
            if (
                due_date is None
                and end_date is None
                and normalized_time is None
                and normalized_period is None
                and limit is None
            ):
                # Preserve the original no-filter call path.
                tasks = self._repo.get_pending_tasks()
            else:
                tasks = self._repo.get_pending_tasks_filtered(
                    due_date=due_date,
                    end_date=end_date,
                    due_time=normalized_time,
                    due_period=normalized_period,
                    limit=limit,
                )
            return OperationResult.listed(tasks)
        except Exception as e:
            return OperationResult.error(f"Failed to list pending tasks: {e}")

    def complete_task(self, task_query: str) -> OperationResult:
        """
        Complete a task by title query.

        Args:
            task_query: Task title or partial title to match.

        Returns:
            OperationResult with completion status or clarification request.
        """
        if not task_query or not task_query.strip():
            return OperationResult.error("Task query cannot be empty")

        try:
            match = self._repo.match_task(task_query.strip())
        except Exception as e:
            return OperationResult.error(f"Failed to search tasks: {e}")

        if match.result == MatchResult.NOT_FOUND:
            return OperationResult.not_found(task_query)

        if match.result == MatchResult.AMBIGUOUS:
            return OperationResult.ambiguous(match.matches)

        # Unique match - proceed to complete
        task = match.task
        assert task is not None

        if task.is_completed:
            return OperationResult.already_completed(task)

        try:
            completed_task = self._repo.complete_task(task.id)
            return OperationResult.completed(completed_task)
        except ValueError as e:
            return OperationResult.error(str(e))
        except Exception as e:
            return OperationResult.error(f"Failed to complete task: {e}")

    def get_task_details(self, task_query: str) -> OperationResult:
        """
        Get details of a task by title query.

        Args:
            task_query: Task title or partial title to match.

        Returns:
            OperationResult with task details or clarification request.
        """
        if not task_query or not task_query.strip():
            return OperationResult.error("Task query cannot be empty")

        try:
            match = self._repo.match_task(task_query.strip())
        except Exception as e:
            return OperationResult.error(f"Failed to search tasks: {e}")

        if match.result == MatchResult.NOT_FOUND:
            return OperationResult.not_found(task_query)

        if match.result == MatchResult.AMBIGUOUS:
            return OperationResult.ambiguous(match.matches)

        # Unique match - return details
        task = match.task
        assert task is not None
        return OperationResult.retrieved(task)

    def prepare_bulk_completion(
        self,
        due_date: date,
        end_date: Optional[date] = None,
    ) -> OperationResult:
        """
        Find pending tasks for a date or date range without changing them.

        The assistant must show these candidates and obtain explicit user
        confirmation before calling complete_tasks_by_ids.

        Args:
            due_date: Requested due date (required).
            end_date: Optional inclusive end date for a range.

        Returns:
            OperationResult with confirmation_required status and candidates,
            a not_found result when nothing matches, or an error.
        """
        if not isinstance(due_date, date):
            return OperationResult.error("due_date must be a valid date")
        if end_date is not None and not isinstance(end_date, date):
            return OperationResult.error("end_date must be a valid date")
        if end_date is not None and end_date < due_date:
            return OperationResult.error("end_date cannot be earlier than due_date")

        label = due_date.isoformat()
        if end_date is not None:
            label = f"{due_date.isoformat()} to {end_date.isoformat()}"

        try:
            tasks = self._repo.get_pending_tasks_filtered(
                due_date=due_date,
                end_date=end_date,
            )
        except Exception as e:
            return OperationResult.error(f"Failed to find matching tasks: {e}")

        if not tasks:
            return OperationResult.no_tasks_for_date(label)

        return OperationResult.awaiting_confirmation(tasks, date_label=label)

    def complete_tasks_by_ids(self, task_ids: list[int]) -> OperationResult:
        """
        Complete only the confirmed task IDs.

        Args:
            task_ids: Task IDs the user explicitly confirmed.

        Returns:
            OperationResult reporting the tasks actually completed.
        """
        if not task_ids:
            return OperationResult.error("No task IDs were confirmed")

        try:
            ids = [int(task_id) for task_id in task_ids]
        except (TypeError, ValueError):
            return OperationResult.error("Task IDs must be integers")

        try:
            completed = self._repo.complete_tasks_by_ids(ids)
        except Exception as e:
            return OperationResult.error(f"Failed to complete tasks: {e}")

        if not completed:
            return OperationResult.error(
                "No pending tasks were completed; they may already be done."
            )

        return OperationResult.bulk_completed(completed)

    def verify_database(self) -> bool:
        """Verify database schema is valid."""
        return verify_database(self._db_path)

    def get_task_count(self, status: Optional[TaskStatus] = None) -> int:
        """Get count of tasks, optionally filtered by status."""
        return self._repo.count_tasks(status)