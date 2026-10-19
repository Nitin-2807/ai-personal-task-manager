"""
Task Repository for AI-Powered Personal Task Manager.

Handles all database operations for tasks: CRUD, queries, and matching.
"""

import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Optional, Sequence

from src.database import (
    DatabaseOperationError,
    get_connection,
    transaction,
)
from src.date_utils import TIME_PERIODS
from src.models import (
    MatchResult,
    Task,
    TaskMatch,
    TaskStatus,
)


class TaskRepository:
    """Data access layer for tasks."""

    def __init__(self, db_path: Optional[Path] = None):
        self._db_path = db_path

    def create_task(
        self,
        title: str,
        due_date: date,
        due_time: Optional[str] = None,
        due_period: Optional[str] = None,
    ) -> Task:
        """
        Insert a new task into the database.

        Args:
            title: Task title (non-empty)
            due_date: Due date
            due_time: Optional normalized time in HH:MM
            due_period: Optional approximate period (morning/afternoon/evening/night)

        Returns:
            The created Task with assigned ID.

        Raises:
            DatabaseOperationError: If insertion fails.
            ValueError: If title, date, time, or period is invalid.
        """
        if not title or not title.strip():
            raise ValueError("Task title cannot be empty")
        if not isinstance(due_date, date):
            raise ValueError("due_date must be a date object")
        if due_time is not None and not isinstance(due_time, str):
            raise ValueError("due_time must be a string in HH:MM format")
        if due_period is not None and due_period not in TIME_PERIODS:
            raise ValueError(f"due_period must be one of: {', '.join(TIME_PERIODS)}")

        now = datetime.now().isoformat()
        due_str = due_date.isoformat()

        try:
            with transaction(self._db_path) as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO tasks
                        (title, due_date, due_time, due_period, status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        title.strip(),
                        due_str,
                        due_time,
                        due_period,
                        TaskStatus.PENDING.value,
                        now,
                    ),
                )
                task_id = cursor.lastrowid
                if task_id is None:
                    raise DatabaseOperationError("Failed to get inserted task ID")
                return Task(
                    id=task_id,
                    title=title.strip(),
                    due_date=due_date,
                    due_time=due_time,
                    due_period=due_period,
                    status=TaskStatus.PENDING,
                    created_at=datetime.fromisoformat(now),
                )
        except sqlite3.Error as e:
            raise DatabaseOperationError(f"Failed to create task: {e}") from e

    def get_pending_tasks(self) -> tuple[Task, ...]:
        """Retrieve all pending tasks in chronological order."""
        return self.get_pending_tasks_filtered()

    def get_pending_tasks_filtered(
        self,
        due_date: Optional[date] = None,
        end_date: Optional[date] = None,
        due_time: Optional[str] = None,
        due_period: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> tuple[Task, ...]:
        """
        Retrieve pending tasks with optional validated filters.

        Filter semantics:
            due_date alone: exact due-date match.
            due_date + end_date: inclusive date range.
            end_date alone: all pending tasks due on or before end_date.

        Ordering is chronological: due date first, then exact times (earlier
        first), then untimed tasks for that date, then creation time.

        Args:
            due_date: Exact due date, or inclusive range start with end_date.
            end_date: Inclusive range end or upper bound.
            due_time: Exact normalized time filter (HH:MM).
            due_period: Approximate period filter.
            limit: Optional maximum number of tasks.

        Returns:
            Tuple of matching pending Task objects.
        """
        conditions = ["status = ?"]
        params: list = [TaskStatus.PENDING.value]

        if due_date is not None and end_date is not None:
            conditions.append("due_date >= ?")
            params.append(due_date.isoformat())
            conditions.append("due_date <= ?")
            params.append(end_date.isoformat())
        elif due_date is not None:
            conditions.append("due_date = ?")
            params.append(due_date.isoformat())
        elif end_date is not None:
            conditions.append("due_date <= ?")
            params.append(end_date.isoformat())
        if due_time is not None:
            conditions.append("due_time = ?")
            params.append(due_time)
        if due_period is not None:
            conditions.append("due_period = ?")
            params.append(due_period)

        if limit is not None:
            params.append(int(limit))

        limit_clause = "LIMIT ?" if limit is not None else ""
        sql = f"""
            SELECT id, title, due_date, due_time, due_period, status, created_at
            FROM tasks
            WHERE {' AND '.join(conditions)}
            ORDER BY due_date ASC,
                     CASE WHEN due_time IS NULL THEN 0 ELSE 1 END ASC,
                     due_time ASC,
                     created_at ASC,
                     id ASC
            {limit_clause}
        """

        try:
            with get_connection(self._db_path) as conn:
                cursor = conn.execute(sql, params)
                return tuple(Task.from_row(row) for row in cursor.fetchall())
        except sqlite3.Error as e:
            raise DatabaseOperationError(f"Failed to get pending tasks: {e}") from e

    def get_all_tasks(self) -> tuple[Task, ...]:
        """
        Retrieve all tasks ordered by creation date (newest first).

        Returns:
            Tuple of all Task objects.
        """
        try:
            with get_connection(self._db_path) as conn:
                cursor = conn.execute(
                    """
                    SELECT id, title, due_date, due_time, due_period, status, created_at
                    FROM tasks
                    ORDER BY created_at DESC
                    """,
                )
                return tuple(Task.from_row(row) for row in cursor.fetchall())
        except sqlite3.Error as e:
            raise DatabaseOperationError(f"Failed to get all tasks: {e}") from e

    def find_task_by_id(self, task_id: int) -> Optional[Task]:
        """
        Find a task by its ID.

        Args:
            task_id: Task ID to search for.

        Returns:
            Task if found, None otherwise.
        """
        try:
            with get_connection(self._db_path) as conn:
                cursor = conn.execute(
                    """
                    SELECT id, title, due_date, due_time, due_period, status, created_at
                    FROM tasks
                    WHERE id = ?
                    """,
                    (task_id,),
                )
                row = cursor.fetchone()
                return Task.from_row(row) if row else None
        except sqlite3.Error as e:
            raise DatabaseOperationError(f"Failed to find task by ID: {e}") from e

    def find_tasks_by_title(self, query: str) -> tuple[Task, ...]:
        """
        Find tasks matching a title query.

        Matching strategy (in order):
        1. Exact case-insensitive match
        2. Partial match (case-insensitive LIKE)
        3. Word-based match (all significant query words must appear)

        Args:
            query: Search query string.

        Returns:
            Tuple of matching Task objects.
        """
        if not query or not query.strip():
            return ()

        query = query.strip()

        try:
            with get_connection(self._db_path) as conn:
                # 1. Exact case-insensitive match
                cursor = conn.execute(
                    """
                    SELECT id, title, due_date, due_time, due_period, status, created_at
                    FROM tasks
                    WHERE LOWER(title) = LOWER(?)
                    ORDER BY created_at DESC
                    """,
                    (query,),
                )
                exact_matches = tuple(Task.from_row(row) for row in cursor.fetchall())
                if exact_matches:
                    return exact_matches

                # 2. Partial match (query as substring)
                cursor = conn.execute(
                    """
                    SELECT id, title, due_date, due_time, due_period, status, created_at
                    FROM tasks
                    WHERE LOWER(title) LIKE LOWER(?)
                    ORDER BY created_at DESC
                    """,
                    (f"%{query}%",),
                )
                partial_matches = tuple(Task.from_row(row) for row in cursor.fetchall())
                if partial_matches:
                    return partial_matches

                # 3. Word-based match: split query into words and match any significant word
                # Filter out common stop words
                stop_words = {"the", "a", "an", "my", "task", "to", "for", "of", "in", "on", "at", "by", "with", "and", "or"}
                words = [w for w in query.lower().split() if w not in stop_words and len(w) > 2]
                
                if words:
                    # Require all significant query words to appear in the title.
                    # This is stricter than a single-word OR match, avoiding
                    # false positives when only a generic word (e.g. "assignment")
                    # overlaps with an unrelated task.
                    conditions = " AND ".join(["LOWER(title) LIKE ?"] * len(words))
                    params = [f"%{word}%" for word in words]
                    cursor = conn.execute(
                        f"""
                        SELECT id, title, due_date, due_time, due_period, status, created_at
                        FROM tasks
                        WHERE {conditions}
                        GROUP BY id
                        ORDER BY created_at DESC
                        """,
                        params,
                    )
                    word_matches = tuple(Task.from_row(row) for row in cursor.fetchall())
                    if word_matches:
                        return word_matches

                return ()
        except sqlite3.Error as e:
            raise DatabaseOperationError(f"Failed to find tasks by title: {e}") from e

    def match_task(self, query: str) -> TaskMatch:
        """
        Match a task query to a unique task or return ambiguity info.

        Args:
            query: Task title or partial title to match.

        Returns:
            TaskMatch with result type and task/matches.
        """
        matches = self.find_tasks_by_title(query)

        if not matches:
            return TaskMatch.not_found(query)
        if len(matches) == 1:
            return TaskMatch.exact(matches[0])
        return TaskMatch.ambiguous(matches)

    def complete_task(self, task_id: int) -> Task:
        """
        Mark a task as completed.

        Args:
            task_id: ID of task to complete.

        Returns:
            Updated Task object.

        Raises:
            DatabaseOperationError: If update fails.
            ValueError: If task not found or already completed.
        """
        try:
            with transaction(self._db_path) as conn:
                # First check current status
                cursor = conn.execute(
                    "SELECT status FROM tasks WHERE id = ?",
                    (task_id,),
                )
                row = cursor.fetchone()
                if not row:
                    raise ValueError(f"Task with ID {task_id} not found")
                if row["status"] == TaskStatus.COMPLETED.value:
                    raise ValueError(f"Task {task_id} is already completed")

                # Update status
                conn.execute(
                    "UPDATE tasks SET status = ? WHERE id = ?",
                    (TaskStatus.COMPLETED.value, task_id),
                )

                # Return updated task
                cursor = conn.execute(
                    """
                    SELECT id, title, due_date, due_time, due_period, status, created_at
                    FROM tasks WHERE id = ?
                    """,
                    (task_id,),
                )
                row = cursor.fetchone()
                if not row:
                    raise DatabaseOperationError("Task disappeared after update")
                return Task.from_row(row)
        except sqlite3.Error as e:
            raise DatabaseOperationError(f"Failed to complete task: {e}") from e

    def get_tasks_by_ids(self, task_ids: Sequence[int]) -> tuple[Task, ...]:
        """
        Fetch tasks by a sequence of IDs, in chronological order.

        Args:
            task_ids: Task IDs to fetch.

        Returns:
            Tuple of found Task objects (missing IDs are simply absent).
        """
        ids = [int(task_id) for task_id in task_ids]
        if not ids:
            return ()

        placeholders = ", ".join("?" for _ in ids)
        try:
            with get_connection(self._db_path) as conn:
                cursor = conn.execute(
                    f"""
                    SELECT id, title, due_date, due_time, due_period, status, created_at
                    FROM tasks
                    WHERE id IN ({placeholders})
                    ORDER BY due_date ASC,
                             CASE WHEN due_time IS NULL THEN 0 ELSE 1 END ASC,
                             due_time ASC,
                             id ASC
                    """,
                    ids,
                )
                return tuple(Task.from_row(row) for row in cursor.fetchall())
        except sqlite3.Error as e:
            raise DatabaseOperationError(f"Failed to get tasks by IDs: {e}") from e

    def complete_tasks_by_ids(self, task_ids: Sequence[int]) -> tuple[Task, ...]:
        """
        Complete all pending tasks among the supplied IDs in one transaction.

        Only pending tasks are changed. IDs that are missing or already
        completed are ignored and reported by the caller.

        Args:
            task_ids: Confirmed task IDs to complete.

        Returns:
            Tuple of the tasks actually completed.

        Raises:
            ValueError: If no IDs are supplied.
            DatabaseOperationError: If the update fails.
        """
        ids = [int(task_id) for task_id in task_ids]
        if not ids:
            raise ValueError("At least one task ID is required")

        placeholders = ", ".join("?" for _ in ids)
        try:
            with transaction(self._db_path) as conn:
                # Find which of the requested IDs are still pending.
                cursor = conn.execute(
                    f"""
                    SELECT id FROM tasks
                    WHERE id IN ({placeholders}) AND status = ?
                    """,
                    [*ids, TaskStatus.PENDING.value],
                )
                pending_ids = [row["id"] for row in cursor.fetchall()]
                if not pending_ids:
                    return ()

                pending_placeholders = ", ".join("?" for _ in pending_ids)
                conn.execute(
                    f"""
                    UPDATE tasks
                    SET status = ?
                    WHERE id IN ({pending_placeholders}) AND status = ?
                    """,
                    [
                        TaskStatus.COMPLETED.value,
                        *pending_ids,
                        TaskStatus.PENDING.value,
                    ],
                )
                cursor = conn.execute(
                    f"""
                    SELECT id, title, due_date, due_time, due_period, status, created_at
                    FROM tasks
                    WHERE id IN ({pending_placeholders}) AND status = ?
                    ORDER BY due_date ASC,
                             CASE WHEN due_time IS NULL THEN 0 ELSE 1 END ASC,
                             due_time ASC,
                             id ASC
                    """,
                    [*pending_ids, TaskStatus.COMPLETED.value],
                )
                return tuple(Task.from_row(row) for row in cursor.fetchall())
        except sqlite3.Error as e:
            raise DatabaseOperationError(f"Failed to complete tasks in bulk: {e}") from e

    def get_task_details(self, task_id: int) -> Optional[Task]:
        """
        Get full details of a task by ID.

        Args:
            task_id: Task ID.

        Returns:
            Task if found, None otherwise.
        """
        return self.find_task_by_id(task_id)

    def count_tasks(self, status: Optional[TaskStatus] = None) -> int:
        """
        Count tasks, optionally filtered by status.

        Args:
            status: Optional status filter.

        Returns:
            Count of tasks.
        """
        try:
            with get_connection(self._db_path) as conn:
                if status:
                    cursor = conn.execute(
                        "SELECT COUNT(*) as cnt FROM tasks WHERE status = ?",
                        (status.value,),
                    )
                else:
                    cursor = conn.execute("SELECT COUNT(*) as cnt FROM tasks")
                row = cursor.fetchone()
                return row["cnt"] if row else 0
        except sqlite3.Error as e:
            raise DatabaseOperationError(f"Failed to count tasks: {e}") from e