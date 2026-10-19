"""
Tool schemas for AI-Personal Task Manager.

Defines the function calling schemas exposed to the LLM.
These schemas must match the function signatures in task_service.py.
"""

from datetime import date
from typing import Any, Dict, List

from src.date_utils import (
    TIME_PERIODS,
    normalize_period_value,
    normalize_time_value,
)


# Tool definitions for function calling
TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "create_task",
            "description": (
                "Create a new task with a title and due date. Use this when the "
                "user wants to add a task. Include an exact due_time or an "
                "approximate due_period when the user gives one; omit both when "
                "they do not. Never invent a time."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": (
                            "The task title, without date or time words. "
                            "Must not be empty."
                        ),
                    },
                    "due_date": {
                        "type": "string",
                        "description": "The due date in ISO format (YYYY-MM-DD). Must be a valid calendar date.",
                    },
                    "due_time": {
                        "type": "string",
                        "description": (
                            "Exact due time in 24-hour HH:MM (for example "
                            "'15:00' or '10:00'). Omit when only an approximate "
                            "period is known."
                        ),
                    },
                    "due_period": {
                        "type": "string",
                        "enum": list(TIME_PERIODS),
                        "description": (
                            "Approximate time period: morning, afternoon, "
                            "evening, or night. Omit when an exact due_time is "
                            "given."
                        ),
                    },
                },
                "required": ["title", "due_date"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_pending_tasks",
            "description": (
                "List pending tasks in chronological order. Use with no "
                "arguments for all pending tasks. Filter by due_date for a "
                "schedule, end_date for a date range, due_time/due_period for a "
                "time of day, and limit=1 for the next task."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "due_date": {
                        "type": "string",
                        "description": "Inclusive due date filter in YYYY-MM-DD.",
                    },
                    "end_date": {
                        "type": "string",
                        "description": "Inclusive end date for a range in YYYY-MM-DD.",
                    },
                    "due_time": {
                        "type": "string",
                        "description": "Exact 24-hour time filter in HH:MM.",
                    },
                    "due_period": {
                        "type": "string",
                        "enum": list(TIME_PERIODS),
                        "description": "Approximate period filter.",
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "description": "Maximum number of tasks to return.",
                    },
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "complete_task",
            "description": (
                "Mark one task as completed by title query. Use this for a "
                "single task, not for a date or a group of tasks."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task_query": {
                        "type": "string",
                        "description": "The task title or partial title to match. Will find exact or partial matches.",
                    },
                },
                "required": ["task_query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_task_details",
            "description": (
                "Get a specific task's due date, time or period, and status by "
                "title query. Use this for questions like 'When is my train?'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task_query": {
                        "type": "string",
                        "description": "The task title or partial title to match.",
                    },
                },
                "required": ["task_query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "complete_tasks_by_date",
            "description": (
                "Find all pending tasks due on a specific date or inclusive "
                "date range and ask the user to confirm before any are "
                "completed. This tool never completes tasks by itself. Never "
                "call it without a concrete date."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "due_date": {
                        "type": "string",
                        "description": "Requested due date in YYYY-MM-DD. Required.",
                    },
                    "end_date": {
                        "type": "string",
                        "description": "Optional inclusive end date for a date range in YYYY-MM-DD.",
                    },
                },
                "required": ["due_date"],
                "additionalProperties": False,
            },
        },
    },
]


# Mapping from tool name to handler function name in TaskService
TOOL_HANDLER_MAP = {
    "create_task": "create_task",
    "list_pending_tasks": "list_pending_tasks",
    "complete_task": "complete_task",
    "get_task_details": "get_task_details",
    "complete_tasks_by_date": "prepare_bulk_completion",
}


def get_tool_schemas() -> List[Dict[str, Any]]:
    """Return the list of tool schemas for the LLM."""
    return TOOLS


def get_handler_name(tool_name: str) -> str:
    """Get the TaskService handler method name for a tool."""
    return TOOL_HANDLER_MAP.get(tool_name, tool_name)


def _validate_iso_date(value: Any, field_name: str) -> tuple[bool, str]:
    """Validate an ISO date string and return (is_valid, error_message)."""
    if not isinstance(value, str):
        return False, f"{field_name} must be a string in YYYY-MM-DD format"
    try:
        date.fromisoformat(value)
    except ValueError:
        return False, f"Invalid {field_name} format: {value}. Must be YYYY-MM-DD"
    return True, ""


def _validate_optional_time(value: Any) -> tuple[bool, str]:
    """Validate an optional due_time value using the shared normalizer."""
    if value is None or value == "":
        return True, ""
    try:
        normalize_time_value(value)
    except ValueError as exc:
        return False, str(exc)
    return True, ""


def _validate_optional_period(value: Any) -> tuple[bool, str]:
    """Validate an optional due_period value using the shared normalizer."""
    if value is None or value == "":
        return True, ""
    try:
        normalize_period_value(value)
    except ValueError as exc:
        return False, str(exc)
    return True, ""


def validate_tool_arguments(tool_name: str, arguments: Dict[str, Any]) -> tuple[bool, str]:
    """
    Validate tool arguments before execution.

    Args:
        tool_name: Name of the tool being called.
        arguments: Arguments dict from the LLM.

    Returns:
        Tuple of (is_valid, error_message).
    """
    if tool_name == "create_task":
        if "title" not in arguments:
            return False, "Missing required argument: title"
        if not arguments["title"] or not str(arguments["title"]).strip():
            return False, "Title cannot be empty"
        if "due_date" not in arguments:
            return False, "Missing required argument: due_date"
        is_valid, message = _validate_iso_date(arguments["due_date"], "due_date")
        if not is_valid:
            return False, message

        is_valid, message = _validate_optional_time(arguments.get("due_time"))
        if not is_valid:
            return False, message
        is_valid, message = _validate_optional_period(arguments.get("due_period"))
        if not is_valid:
            return False, message

        has_time = bool(str(arguments.get("due_time") or "").strip())
        has_period = bool(str(arguments.get("due_period") or "").strip())
        if has_time and has_period:
            return False, "Provide either due_time or due_period, not both"
        return True, ""

    elif tool_name == "list_pending_tasks":
        for field_name in ("due_date", "end_date"):
            value = arguments.get(field_name)
            if value in (None, ""):
                continue
            is_valid, message = _validate_iso_date(value, field_name)
            if not is_valid:
                return False, message

        is_valid, message = _validate_optional_time(arguments.get("due_time"))
        if not is_valid:
            return False, message
        is_valid, message = _validate_optional_period(arguments.get("due_period"))
        if not is_valid:
            return False, message

        if arguments.get("due_time") and arguments.get("due_period"):
            return False, "Provide either due_time or due_period, not both"

        limit = arguments.get("limit")
        if limit is not None:
            if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
                return False, "limit must be a positive integer"

        due_date = arguments.get("due_date")
        end_date = arguments.get("end_date")
        if due_date and end_date and end_date < due_date:
            return False, "end_date cannot be earlier than due_date"
        return True, ""

    elif tool_name == "complete_task":
        if "task_query" not in arguments:
            return False, "Missing required argument: task_query"
        if not arguments["task_query"] or not str(arguments["task_query"]).strip():
            return False, "Task query cannot be empty"
        return True, ""

    elif tool_name == "get_task_details":
        if "task_query" not in arguments:
            return False, "Missing required argument: task_query"
        if not arguments["task_query"] or not str(arguments["task_query"]).strip():
            return False, "Task query cannot be empty"
        return True, ""

    elif tool_name == "complete_tasks_by_date":
        if "due_date" not in arguments:
            return False, "Missing required argument: due_date"
        is_valid, message = _validate_iso_date(arguments["due_date"], "due_date")
        if not is_valid:
            return False, message

        end_date = arguments.get("end_date")
        if end_date not in (None, ""):
            is_valid, message = _validate_iso_date(end_date, "end_date")
            if not is_valid:
                return False, message
            if end_date < arguments["due_date"]:
                return False, "end_date cannot be earlier than due_date"
        return True, ""

    else:
        return False, f"Unknown tool: {tool_name}"
