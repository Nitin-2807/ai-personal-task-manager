"""
Response formatter for AI-Personal Task Manager.

Converts operation results into user-friendly messages.
"""

from src.date_utils import format_due
from src.models import OperationResult, Task


def format_operation_result(result: OperationResult) -> str:
    """
    Format an OperationResult as a user-friendly message.

    Args:
        result: OperationResult from TaskService.

    Returns:
        Formatted message string.
    """
    if result.success:
        return result.message
    else:
        return result.message


def format_task_list(tasks: tuple[Task, ...], title: str = "Tasks") -> str:
    """
    Format a list of tasks for display.

    Args:
        tasks: Tuple of Task objects.
        title: Title for the list.

    Returns:
        Formatted string.
    """
    if not tasks:
        return f"No {title.lower()} found."

    lines = [f"{title} ({len(tasks)}):"]
    for i, task in enumerate(tasks, 1):
        status_icon = "✓" if task.is_completed else "○"
        lines.append(
            f"  {i}. {status_icon} {task.title} — Due: {task.due_display} — Status: {task.status.value}"
        )
    return "\n".join(lines)


def format_task_details(task: Task) -> str:
    """
    Format a single task's details.

    Args:
        task: Task object.

    Returns:
        Formatted string.
    """
    status_icon = "✓ Completed" if task.is_completed else "○ Pending"
    return (
        f"Task Details:\n"
        f"  Title: {task.title}\n"
        f"  Due: {format_due(task.due_date, task.due_time, task.due_period)}\n"
        f"  Status: {status_icon}\n"
        f"  Created: {task.created_at.strftime('%Y-%m-%d %H:%M')}\n"
        f"  ID: {task.id}"
    )


def format_clarification(matches: tuple[Task, ...], query: str) -> str:
    """
    Format an ambiguous match clarification request.

    Args:
        matches: Tuple of matching Task objects.
        query: Original query that caused ambiguity.

    Returns:
        Formatted clarification message.
    """
    if not matches:
        return f"No tasks found matching '{query}'."

    lines = [f"Multiple tasks match '{query}':"]
    for i, task in enumerate(matches, 1):
        status_icon = "✓" if task.is_completed else "○"
        lines.append(
            f"  {i}. {status_icon} {task.title} — Due: {task.due_display} — Status: {task.status.value}"
        )
    lines.append("\nPlease specify which task you mean (e.g., '1', 'the first one', or the full title).")
    return "\n".join(lines)


def format_error(message: str) -> str:
    """Format an error message."""
    return f"Error: {message}"


def format_welcome() -> str:
    """Format welcome message."""
    return (
        "Welcome to your AI-Powered Personal Task Manager!\n\n"
        "I can help you:\n"
        "  • Create tasks: \"Add a task to finish the report by tomorrow\"\n"
        "  • Add times: \"Train at 3 PM on Saturday\" or \"Call mom tomorrow evening\"\n"
        "  • See your schedule: \"Show my schedule for Saturday\"\n"
        "  • List pending tasks: \"Show me my pending tasks\"\n"
        "  • Complete tasks: \"Mark the report as completed\"\n"
        "  • Bulk complete: \"Mark all tomorrow's tasks as done\"\n"
        "  • Get task details: \"When is the report due?\"\n\n"
        "What would you like to do?"
    )


def format_goodbye() -> str:
    """Format goodbye message."""
    return "Goodbye! Your tasks have been saved."