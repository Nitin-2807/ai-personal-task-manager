"""
Data models for AI-Powered Personal Task Manager.

Defines the Task model and related data structures.
"""

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Optional

from src.date_utils import format_due


class TaskStatus(str, Enum):
    """Task status enumeration."""
    PENDING = "pending"
    COMPLETED = "completed"


class MatchResult(str, Enum):
    """Task matching result types."""
    EXACT = "exact"
    PARTIAL = "partial"
    AMBIGUOUS = "ambiguous"
    NOT_FOUND = "not_found"


@dataclass(frozen=True)
class Task:
    """Represents a task in the system."""
    id: int
    title: str
    due_date: date
    status: TaskStatus
    created_at: datetime
    due_time: Optional[str] = None
    due_period: Optional[str] = None

    @property
    def is_completed(self) -> bool:
        return self.status == TaskStatus.COMPLETED

    @property
    def is_pending(self) -> bool:
        return self.status == TaskStatus.PENDING

    @property
    def due_display(self) -> str:
        """User-facing due date plus time or approximate period."""
        return format_due(self.due_date, self.due_time, self.due_period)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "title": self.title,
            "due_date": self.due_date.isoformat(),
            "due_time": self.due_time,
            "due_period": self.due_period,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_row(cls, row: "sqlite3.Row") -> "Task":
        """Create Task from sqlite3.Row."""
        columns = row.keys()
        return cls(
            id=row["id"],
            title=row["title"],
            due_date=date.fromisoformat(row["due_date"]),
            status=TaskStatus(row["status"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            due_time=row["due_time"] if "due_time" in columns else None,
            due_period=row["due_period"] if "due_period" in columns else None,
        )


@dataclass(frozen=True)
class TaskMatch:
    """Result of a task matching operation."""
    result: MatchResult
    task: Optional[Task] = None
    matches: tuple[Task, ...] = ()
    message: str = ""

    @classmethod
    def exact(cls, task: Task) -> "TaskMatch":
        return cls(result=MatchResult.EXACT, task=task, message=f"Found task: {task.title}")

    @classmethod
    def partial(cls, task: Task) -> "TaskMatch":
        return cls(result=MatchResult.PARTIAL, task=task, message=f"Found task: {task.title}")

    @classmethod
    def ambiguous(cls, matches: tuple[Task, ...]) -> "TaskMatch":
        titles = ", ".join(f'"{t.title}"' for t in matches)
        return cls(
            result=MatchResult.AMBIGUOUS,
            matches=matches,
            message=f"Multiple tasks match: {titles}. Please specify which one.",
        )

    @classmethod
    def not_found(cls, query: str) -> "TaskMatch":
        return cls(
            result=MatchResult.NOT_FOUND,
            message=f"No task found matching: {query}",
        )


@dataclass(frozen=True)
class OperationResult:
    """Result of a task operation (create, complete, etc.)."""
    success: bool
    status: str
    message: str
    task: Optional[Task] = None
    matches: tuple[Task, ...] = ()
    tasks: tuple[Task, ...] = ()
    count: int = 0

    @classmethod
    def created(cls, task: Task) -> "OperationResult":
        return cls(
            success=True,
            status="created",
            message=(
                f"Task created: {task.title} "
                f"(due: {task.due_display}, status: {task.status.value})"
            ),
            task=task,
        )

    @classmethod
    def completed(cls, task: Task) -> "OperationResult":
        return cls(
            success=True,
            status="completed",
            message=f"Task marked completed: {task.title}",
            task=task,
        )

    @classmethod
    def already_completed(cls, task: Task) -> "OperationResult":
        return cls(
            success=False,
            status="already_completed",
            message=f"Task already completed: {task.title}",
            task=task,
        )

    @classmethod
    def not_found(cls, query: str) -> "OperationResult":
        return cls(
            success=False,
            status="not_found",
            message=f"Task not found: {query}",
        )

    @classmethod
    def ambiguous(cls, matches: tuple[Task, ...]) -> "OperationResult":
        titles = ", ".join(f'"{t.title}"' for t in matches)
        return cls(
            success=False,
            status="ambiguous",
            message=f"Multiple tasks match: {titles}. Please specify.",
            matches=matches,
        )

    @classmethod
    def listed(cls, tasks: tuple[Task, ...]) -> "OperationResult":
        if not tasks:
            return cls(
                success=True,
                status="listed",
                message="No pending tasks found.",
                tasks=(),
                count=0,
            )

        lines = [f"Pending tasks ({len(tasks)}):"]
        for task in tasks:
            lines.append(
                f"  [{task.id}] {task.title} — due: {task.due_display} "
                f"— status: {task.status.value}"
            )
        return cls(
            success=True,
            status="listed",
            message="\n".join(lines),
            tasks=tasks,
            count=len(tasks),
        )

    @classmethod
    def retrieved(cls, task: Task) -> "OperationResult":
        return cls(
            success=True,
            status="retrieved",
            message=(
                f"Task details: {task.title} "
                f"(id: {task.id}, due: {task.due_display}, status: {task.status.value})"
            ),
            task=task,
        )

    @classmethod
    def awaiting_confirmation(
        cls, tasks: tuple[Task, ...], date_label: str = ""
    ) -> "OperationResult":
        """Return matching tasks and ask for explicit confirmation."""
        scope = f" for {date_label}" if date_label else ""
        lines = [f"I found {len(tasks)} pending task(s){scope}:"]
        for index, task in enumerate(tasks, 1):
            lines.append(
                f"  {index}. [id {task.id}] {task.title} "
                f"— due: {task.due_display}"
            )
        lines.append(
            f"Should I mark all {len(tasks)} as completed? (yes/no)"
        )
        return cls(
            success=True,
            status="confirmation_required",
            message="\n".join(lines),
            tasks=tasks,
            count=len(tasks),
        )

    @classmethod
    def bulk_completed(cls, tasks: tuple[Task, ...]) -> "OperationResult":
        """Report a confirmed bulk completion with titles."""
        titles = ", ".join(task.title for task in tasks)
        return cls(
            success=True,
            status="completed",
            message=f"Completed {len(tasks)} task(s): {titles}.",
            tasks=tasks,
            count=len(tasks),
        )

    @classmethod
    def no_tasks_for_date(cls, date_label: str) -> "OperationResult":
        """Report accurately when a date selection matches nothing."""
        return cls(
            success=False,
            status="not_found",
            message=f"No pending tasks found for {date_label}.",
        )

    @classmethod
    def error(cls, message: str) -> "OperationResult":
        return cls(
            success=False,
            status="error",
            message=message,
        )