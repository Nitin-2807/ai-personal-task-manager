"""
LLM Client for AI-Personal Task Manager.

Provides a unified interface for LLM providers with function calling support.
Supports: Google Gemini and a mock provider for testing. The provider interface
(`BaseLLMClient`) is intentionally small so a new SDK adapter can be added later.
"""

import json
import os
import re
import time
from abc import ABC, abstractmethod
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from src.config import config
from src.date_utils import (
    TIME_PERIODS,
    format_time_12h,
    normalize_period_value,
    normalize_time_value,
    today_in_timezone,
)
from src.tool_schemas import (
    TOOL_HANDLER_MAP,
    get_tool_schemas,
    validate_tool_arguments,
)


class LLMError(Exception):
    """Base exception for LLM errors."""
    pass


class LLMAPIError(LLMError):
    """Raised when LLM API returns an error."""
    pass


class LLMTimeoutError(LLMError):
    """Raised when LLM request times out."""
    pass


class LLMResponseError(LLMError):
    """Raised when LLM response is invalid or malformed."""
    pass


class LLMRetryExhaustedError(LLMAPIError):
    """
    Raised when transient API errors (HTTP 429/503) persist after the
    configured number of bounded retries.
    """
    pass


# HTTP status codes worth retrying with exponential backoff.
RETRYABLE_STATUS_CODES = frozenset({429, 503})

# Text-only signals used when an exception carries no numeric status code.
_TRANSIENT_TEXT_RE = re.compile(
    r"(?i)\b(429|503|resource[_ ]?exhausted|service[_ ]?unavailable|"
    r"unavailable|overloaded|high demand|try again later)\b"
)


def is_retryable_api_error(exc: Exception) -> bool:
    """
    Return True when an exception looks like a transient 429/503 API error.

    The google-genai SDK exposes the HTTP status on ``exc.code``; provider
    wrappers and generic exceptions may only expose it in the message text.
    An explicit non-retryable status code is treated as authoritative.
    """
    for attribute in ("code", "status_code"):
        value = getattr(exc, attribute, None)
        if isinstance(value, int) and not isinstance(value, bool):
            return value in RETRYABLE_STATUS_CODES
    return bool(_TRANSIENT_TEXT_RE.search(str(exc)))


# ---------------------------------------------------------------------------
# Destructive-operation policy
# ---------------------------------------------------------------------------

# The assistant never deletes task records. Requests to clear/delete tasks
# are refused explicitly instead of being ignored or simulated.
DESTRUCTIVE_OPERATION_REFUSAL = (
    "I can't delete tasks. Bulk deletion is not supported, so nothing was "
    "deleted. Tasks can only be created, listed, updated to completed, or "
    "viewed. To finish tasks, say for example \"Mark all tomorrow's tasks as "
    "done\" (you will be asked to confirm) or \"Mark the report as completed\"."
)

_DESTRUCTIVE_VERBS = (
    "clear", "delete", "remove", "erase", "wipe", "purge", "drop",
)


def is_destructive_task_intent(message: str) -> bool:
    """
    Return True when a message asks to delete/clear task records.

    Matching is intentionally simple and conservative: a destructive verb
    followed within a few words by "task"/"tasks".
    """
    if not message:
        return False
    lowered = message.lower()
    verb_pattern = r"\b(?:" + "|".join(_DESTRUCTIVE_VERBS) + r")\b"
    if not re.search(verb_pattern, lowered):
        return False
    return bool(
        re.search(
            verb_pattern + r"(?:\s+\S+){0,3}?\s+tasks?\b",
            lowered,
        )
    )


class BaseLLMClient(ABC):
    """Abstract base class for LLM clients."""

    def __init__(self, system_prompt: str = ""):
        self.system_prompt = system_prompt

    @abstractmethod
    def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        tool_choice: str = "auto",
    ) -> Dict[str, Any]:
        """
        Send a chat request to the LLM.

        Args:
            messages: Conversation messages.
            tools: Available tool schemas.
            tool_choice: Tool choice strategy.

        Returns:
            LLM response with optional tool calls.
        """
        pass

    @abstractmethod
    def get_model_name(self) -> str:
        """Return the model name being used."""
        pass


# ---------------------------------------------------------------------------
# Deterministic helpers for the mock LLM client
# ---------------------------------------------------------------------------

_WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


def _tool_call(name: str, arguments: Dict[str, Any], call_number: int) -> Dict[str, Any]:
    """Build a standard assistant message containing one tool call."""
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [{
            "id": f"call_{call_number}",
            "type": "function",
            "function": {
                "name": name,
                "arguments": json.dumps(arguments),
            },
        }],
    }


def _is_create_intent(message: str) -> bool:
    return bool(re.search(r"\b(add|create|new)\b", message)) and "task" in message


def _looks_like_bare_create(message: str) -> bool:
    """Detect short imperative task phrases with a time and a date."""
    lowered = message.lower().strip()
    if lowered.endswith("?"):
        return False
    if any(
        marker in lowered
        for marker in (
            "show", "list", "pending", "schedule", "complete", "mark",
            "finish", "done", "when", "what", "details", "status",
        )
    ):
        return False
    has_time = bool(
        _TIME_12_RE.search(lowered)
        or _TIME_24_RE.search(lowered)
        or re.search(r"\b(morning|afternoon|evening|night)\b", lowered)
    )
    return has_time and bool(_find_date_expressions(lowered))


_DATE_RE = re.compile(
    r"\b(\d{4}-\d{2}-\d{2})\b"
    r"|\b(tomorrow|today|tonight|tmrw)\b"
    r"|\b(next\s+week)\b"
    r"|\b((?:next|this)\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday))\b"
    r"|\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b"
    r"|\b(in\s+\d{1,3}\s+days?)\b",
    re.IGNORECASE,
)

_TIME_12_RE = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*([ap])\.?m\.?\b", re.IGNORECASE)
_TIME_24_RE = re.compile(r"\b(\d{1,2}):(\d{2})\b")
_TIME_PERIOD_RE = re.compile(r"\b(morning|afternoon|evening|night)\b", re.IGNORECASE)
_AMBIGUOUS_AT_RE = re.compile(r"\bat\s+(\d{1,2})\b", re.IGNORECASE)


def _find_date_expressions(text: str) -> list[Tuple[str, int, int]]:
    """Return all date-expression phrases with their spans, in order."""
    return [
        (match.group(0), match.start(), match.end())
        for match in _DATE_RE.finditer(text)
    ]


def _extract_time_and_period(
    text: str,
) -> Tuple[Optional[str], Optional[str], str, Optional[str]]:
    """
    Extract an exact time or approximate period from ``text``.

    Returns ``(due_time, due_period, remaining_text, ambiguous_hour)``.
    ``ambiguous_hour`` is set for inputs like "at 3" where AM/PM is missing;
    the caller must ask for clarification instead of inventing a time.
    """
    due_time: Optional[str] = None
    due_period: Optional[str] = None
    ambiguous_hour: Optional[str] = None
    working = text

    match = _TIME_12_RE.search(working)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2) or 0)
        meridiem = match.group(3).upper() + "M"
        due_time = normalize_time_value(f"{hour}:{minute:02d} {meridiem}")
        working = (working[: match.start()] + " " + working[match.end():]).strip()
    else:
        match = _TIME_24_RE.search(working)
        if match:
            due_time = normalize_time_value(match.group(0))
            working = (working[: match.start()] + " " + working[match.end():]).strip()
        else:
            match = _AMBIGUOUS_AT_RE.search(working)
            if match:
                hour = int(match.group(1))
                if 13 <= hour <= 23:
                    due_time = f"{hour:02d}:00"
                    working = (working[: match.start()] + " " + working[match.end():]).strip()
                elif 1 <= hour <= 12:
                    ambiguous_hour = str(hour)

    if due_time is None and ambiguous_hour is None:
        match = _TIME_PERIOD_RE.search(working)
        if match:
            due_period = match.group(1).lower()
            working = (working[: match.start()] + " " + working[match.end():]).strip()

    working = re.sub(r"\s+", " ", working).strip()
    return due_time, due_period, working, ambiguous_hour


def _clean_title(value: str) -> str:
    value = value.strip().strip(" .,!?:;")
    value = re.sub(r"^(?:the|my|a|an)\s+", "", value, flags=re.IGNORECASE)
    # Drop dangling prepositions left behind after removing date/time phrases.
    value = re.sub(
        r"(?:\s+(?:at|on|by|for|to|due))+$", "", value, flags=re.IGNORECASE
    )
    return value.strip().strip(" .,!?:;")


def _extract_create_parts(
    message: str,
) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    Extract task title, due-date expression, time, and period from a create request.

    Returns ``(title, date_expression, due_time, due_period, ambiguous_hour)``.
    A missing date expression lets the assistant ask for a due date; an
    ambiguous hour lets it ask for AM/PM instead of guessing.
    """
    rest = message
    # Remove the leading "add/create [a] [new] task [to]" phrase.
    match = re.search(
        r"^(?:please\s+)?(?:add|create|new)\s+(?:a\s+)?(?:new\s+)?task\b\s*(?:to\s+|:)?\s*(.*)$",
        rest,
        flags=re.IGNORECASE,
    )
    if match:
        rest = match.group(1).strip()
    else:
        # Fallback for "add <thing>" phrasing.
        rest = re.sub(
            r"^(?:please\s+)?(?:add|create)\s+", "", rest, flags=re.IGNORECASE
        ).strip()

    if not rest:
        return "Mock task", None, None, None, None

    due_time, due_period, rest, ambiguous_hour = _extract_time_and_period(rest)
    if ambiguous_hour:
        return None, None, None, None, ambiguous_hour

    date_expression: Optional[str] = None
    date_matches = _find_date_expressions(rest)
    if not date_matches:
        # The time phrase may have carried the date; check the original text.
        date_matches = _find_date_expressions(message)
    for expression, start, end in reversed(date_matches):
        rest = (rest[:start] + " " + rest[end:]).strip()
        if date_expression is None:
            date_expression = expression

    title = _clean_title(rest)
    return title or "Mock task", date_expression, due_time, due_period, None


def _parse_relative_date(expression: Optional[str], today: date) -> Optional[date]:
    """Resolve common absolute/relative date expressions to a date."""
    if not expression:
        return None

    value = expression.lower().strip().strip(" .,!?:;")

    # ISO date, e.g. 2026-10-20
    iso_match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", value)
    if iso_match:
        try:
            return date.fromisoformat(iso_match.group(1))
        except ValueError:
            return None

    if value in {"today", "now", "tonight"}:
        return today
    if value in {"tomorrow", "tmrw"}:
        return today + timedelta(days=1)
    if value in {"next week", "in one week", "in a week"}:
        return today + timedelta(days=7)

    in_days = re.search(r"\bin\s+(\d{1,3})\s+days?\b", value)
    if in_days:
        return today + timedelta(days=int(in_days.group(1)))

    # "next monday", "this friday", or a bare weekday name.
    weekday_match = re.search(
        r"\b(?:(next|this)\s+)?(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
        value,
    )
    if weekday_match:
        qualifier = weekday_match.group(1)
        target = _WEEKDAYS[weekday_match.group(2)]
        delta = (target - today.weekday()) % 7
        if qualifier == "next":
            delta = delta or 7
        elif qualifier == "this":
            delta = delta  # today if same weekday
        else:
            delta = delta or 7
        return today + timedelta(days=delta)

    return None


def _is_bulk_complete_intent(message: str) -> bool:
    """Detect requests to complete a date's tasks rather than one task."""
    has_verb = bool(
        re.search(r"\b(complete|completed|mark|finish|done)\b", message)
    )
    has_group = bool(re.search(r"\b(all|every|both)\b", message)) or "tasks" in message
    return has_verb and has_group and "task" in message


def _is_list_intent(message: str) -> bool:
    """Detect schedule/list/next-task requests."""
    markers = (
        "pending",
        "list",
        "schedule",
        "what do i have",
        "next task",
        "upcoming",
        "my day",
        "show my tasks",
    )
    return any(marker in message for marker in markers)


def _extract_complete_query(message: str) -> Optional[str]:
    # Remove an explicit "as completed" / "as done" suffix first, otherwise
    # the optional regex group can be skipped by the non-greedy title match.
    cleaned = re.sub(
        r"\s+as\s+(?:completed|complete|done)[.!?]*\s*$",
        "",
        message,
        flags=re.IGNORECASE,
    )
    match = re.search(
        r"(?:complete|mark|finish)\s+(.+)$",
        cleaned,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    query = _clean_title(match.group(1))
    # Remove a leading "task" only when more words remain.
    query = re.sub(r"^task\s+", "", query, flags=re.IGNORECASE).strip()
    return query or None


def _extract_detail_query(message: str) -> Optional[str]:
    patterns = [
        r"when\s+is\s+(.+?)\s+due\b",
        r"when(?:'s|\s+is)\s+(.+?)\s+due\b",
        r"(?:details?|status)\s+(?:of|for)\s+(.+)",
        r"due\s+date\s+(?:of|for)\s+(.+)",
        r"when\s+is\s+(.+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, message, flags=re.IGNORECASE)
        if match:
            query = _clean_title(match.group(1))
            query = re.sub(r"\s+due\s*\??$", "", query, flags=re.IGNORECASE).strip()
            if query:
                return query
    return None


class MockLLMClient(BaseLLMClient):
    """
    Mock LLM client for testing without API keys.

    Returns predefined responses based on keywords in user messages.
    """

    def __init__(self, system_prompt: str = ""):
        super().__init__(system_prompt)
        self.call_count = 0

    def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        tool_choice: str = "auto",
    ) -> Dict[str, Any]:
        self.call_count += 1

        # Check if the last message is a tool result - if so, return a final response
        if messages and messages[-1].get("role") == "tool":
            return {
                "role": "assistant",
                "content": "Operation completed successfully.",
                "tool_calls": None,
            }

        # Get the last user message (preserve original case for extraction)
        raw_user_msg = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                raw_user_msg = msg.get("content", "").strip()
                break
        user_msg = raw_user_msg.lower()

        # Destructive requests are refused explicitly; the mock never even
        # considers a delete/clear operation.
        if is_destructive_task_intent(raw_user_msg):
            return {
                "role": "assistant",
                "content": DESTRUCTIVE_OPERATION_REFUSAL,
                "tool_calls": None,
            }

        today = today_in_timezone(config.TIMEZONE)

        # --- Detail intent (check before list, because "show details ..." contains "show") ---
        if "detail" in user_msg or "when" in user_msg or "due date" in user_msg or "status" in user_msg:
            task_query = _extract_detail_query(raw_user_msg)
            if task_query:
                return _tool_call("get_task_details", {"task_query": task_query}, self.call_count)

        # --- Bulk complete by date (checked before single complete) ---
        if _is_bulk_complete_intent(user_msg):
            date_matches = _find_date_expressions(raw_user_msg)
            if not date_matches:
                return {
                    "role": "assistant",
                    "content": (
                        "Which date's tasks should I mark as completed? "
                        "Please provide a date (for example 'tomorrow' or "
                        "'2026-10-20')."
                    ),
                    "tool_calls": None,
                }
            due_date = _parse_relative_date(date_matches[0][0], today)
            if due_date is None:
                return {
                    "role": "assistant",
                    "content": (
                        f"I couldn't understand the date '{date_matches[0][0]}'. "
                        "Please use a concrete date such as 2026-10-20."
                    ),
                    "tool_calls": None,
                }
            bulk_args: Dict[str, Any] = {"due_date": due_date.isoformat()}
            if len(date_matches) > 1:
                end_date = _parse_relative_date(date_matches[1][0], today)
                if end_date and end_date >= due_date:
                    bulk_args["end_date"] = end_date.isoformat()
            return _tool_call("complete_tasks_by_date", bulk_args, self.call_count)

        # --- List / schedule / next-task intent ---
        if _is_list_intent(user_msg):
            due_time, due_period, _, ambiguous_hour = _extract_time_and_period(raw_user_msg)
            if ambiguous_hour:
                return {
                    "role": "assistant",
                    "content": (
                        f"Did you mean {ambiguous_hour} AM or {ambiguous_hour} PM? "
                        "Please provide an exact time such as '3 PM' or '15:00'."
                    ),
                    "tool_calls": None,
                }
            list_args: Dict[str, Any] = {}
            date_matches = _find_date_expressions(raw_user_msg)
            if date_matches:
                parsed_date = _parse_relative_date(date_matches[0][0], today)
                if parsed_date is None:
                    return {
                        "role": "assistant",
                        "content": (
                            f"I couldn't understand the date '{date_matches[0][0]}'. "
                            "Please use a concrete date such as 2026-10-20."
                        ),
                        "tool_calls": None,
                    }
                list_args["due_date"] = parsed_date.isoformat()
            if due_time:
                list_args["due_time"] = due_time
            elif due_period:
                list_args["due_period"] = due_period
            if "next task" in user_msg:
                list_args["limit"] = 1
            return _tool_call("list_pending_tasks", list_args, self.call_count)

        # --- Create intent ---
        if _is_create_intent(user_msg) or _looks_like_bare_create(raw_user_msg):
            title, date_expression, due_time, due_period, ambiguous_hour = _extract_create_parts(raw_user_msg)
            if ambiguous_hour:
                return {
                    "role": "assistant",
                    "content": (
                        f"Did you mean {ambiguous_hour} AM or {ambiguous_hour} PM? "
                        "Please provide an exact time such as '3 PM' or '15:00'."
                    ),
                    "tool_calls": None,
                }
            due_date = _parse_relative_date(date_expression, today)
            if due_date is None:
                return {
                    "role": "assistant",
                    "content": (
                        f"What due date should I use for '{title}'? "
                        "Please provide a date (YYYY-MM-DD) or say 'tomorrow'."
                    ),
                    "tool_calls": None,
                }
            create_args: Dict[str, Any] = {
                "title": title or "Mock task",
                "due_date": due_date.isoformat(),
            }
            if due_time:
                create_args["due_time"] = due_time
            elif due_period:
                create_args["due_period"] = due_period
            return _tool_call("create_task", create_args, self.call_count)

        # --- Single complete intent ---
        if "complete" in user_msg or "mark" in user_msg or "finish" in user_msg:
            task_query = _extract_complete_query(raw_user_msg)
            if task_query:
                return _tool_call("complete_task", {"task_query": task_query}, self.call_count)

        # Default: respond without tool call
        return {
            "role": "assistant",
            "content": (
                "I can help you manage tasks. Try asking me to create a task, "
                "list pending tasks, complete a task, or get task details."
            ),
            "tool_calls": None,
        }

    def get_model_name(self) -> str:
        return "mock-llm"


class GeminiLLMClient(BaseLLMClient):
    """Google Gemini LLM client using the current google-genai SDK."""

    _TYPE_MAP = {
        "string": "STRING",
        "number": "NUMBER",
        "integer": "INTEGER",
        "boolean": "BOOLEAN",
        "array": "ARRAY",
        "object": "OBJECT",
        "null": "NULL",
    }

    def __init__(
        self,
        system_prompt: str = "",
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        max_retries: Optional[int] = None,
        retry_base_delay: Optional[float] = None,
    ):
        super().__init__(system_prompt)
        self.api_key = api_key or config.GOOGLE_API_KEY
        self.model = model or config.GEMINI_MODEL
        self.max_retries = max(
            0,
            int(
                config.GEMINI_MAX_RETRIES
                if max_retries is None
                else max_retries
            ),
        )
        self.retry_base_delay = max(
            0.0,
            float(
                config.GEMINI_RETRY_BASE_DELAY
                if retry_base_delay is None
                else retry_base_delay
            ),
        )

        if not self.api_key:
            raise ValueError("Google API key required for Gemini client")

        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise LLMError(
                "google-genai package not installed. Run: pip install google-genai"
            ) from exc

        self._genai = genai
        self._types = types
        self._client = genai.Client(api_key=self.api_key)

        # Build once to fail fast if our tool schemas are malformed.
        self._default_tools = self._build_tools(get_tool_schemas())

    def _redact(self, value: Any) -> str:
        """Remove the API key from SDK error text before exposing it."""
        text = str(value)
        if self.api_key:
            text = text.replace(self.api_key, "[REDACTED]")
        return re.sub(
            r"(?i)(api[_-]?key=)[^&\s]+",
            r"\1[REDACTED]",
            text,
        )

    def _to_gemini_schema(self, schema: Dict[str, Any]) -> Any:
        """Convert a JSON-schema fragment to a google-genai Schema."""
        types = self._types
        schema_type = str(schema.get("type", "string")).lower()
        kwargs: Dict[str, Any] = {}

        if schema.get("description"):
            kwargs["description"] = schema["description"]
        if schema.get("enum"):
            kwargs["enum"] = [str(item) for item in schema["enum"]]

        if schema_type == "object":
            properties = schema.get("properties", {}) or {}
            kwargs["type"] = types.Type.OBJECT
            if properties:
                kwargs["properties"] = {
                    name: self._to_gemini_schema(child)
                    for name, child in properties.items()
                }
            if schema.get("required"):
                kwargs["required"] = list(schema["required"])
        elif schema_type == "array":
            kwargs["type"] = types.Type.ARRAY
            if schema.get("items"):
                kwargs["items"] = self._to_gemini_schema(schema["items"])
        else:
            type_name = self._TYPE_MAP.get(schema_type, "STRING")
            kwargs["type"] = getattr(types.Type, type_name)

        return types.Schema(**kwargs)

    def _build_tools(self, schemas: List[Dict[str, Any]]) -> List[Any]:
        """Convert the project's tool schemas to google-genai Tool objects."""
        types = self._types
        declarations = []
        for schema in schemas:
            function = schema.get("function", schema)
            declarations.append(
                types.FunctionDeclaration(
                    name=function["name"],
                    description=function.get("description", ""),
                    parameters=self._to_gemini_schema(
                        function.get(
                            "parameters",
                            {"type": "object", "properties": {}},
                        )
                    ),
                )
            )
        return [types.Tool(function_declarations=declarations)]

    def _build_contents(
        self, messages: List[Dict[str, Any]]
    ) -> tuple[List[Any], Optional[str]]:
        """Convert shared-format messages into Gemini Content objects."""
        types = self._types
        contents = []
        system_instruction = self.system_prompt or None

        for message in messages:
            role = message.get("role", "user")
            content = message.get("content") or ""

            if role == "system":
                # Gemini requires the system prompt via system_instruction,
                # not as a Content with role="system".
                system_instruction = content or system_instruction
                continue

            if role == "assistant" and message.get("tool_calls"):
                parts = []
                if content:
                    parts.append(types.Part(text=content))
                for tool_call in message["tool_calls"]:
                    function = tool_call.get("function", {})
                    try:
                        arguments = json.loads(function.get("arguments", "{}"))
                    except (json.JSONDecodeError, TypeError):
                        arguments = {}
                    parts.append(
                        types.Part(
                            function_call=types.FunctionCall(
                                id=tool_call.get("id"),
                                name=function.get("name", ""),
                                args=arguments,
                            )
                        )
                    )
                contents.append(types.Content(role="model", parts=parts))
                continue

            if role == "tool":
                try:
                    response_data = json.loads(content)
                except (json.JSONDecodeError, TypeError):
                    response_data = {"result": content}
                contents.append(
                    types.Content(
                        role="user",
                        parts=[
                            types.Part(
                                function_response=types.FunctionResponse(
                                    id=message.get("tool_call_id"),
                                    name=message.get("name", ""),
                                    response=response_data,
                                )
                            )
                        ],
                    )
                )
                continue

            if content:
                contents.append(
                    types.Content(
                        role="model" if role == "assistant" else "user",
                        parts=[types.Part(text=content)],
                    )
                )

        if not contents:
            contents.append(
                types.Content(role="user", parts=[types.Part(text="")])
            )

        return contents, system_instruction

    def _parse_response(self, response: Any) -> Dict[str, Any]:
        """Convert a Gemini GenerateContentResponse to the shared format."""
        candidates = getattr(response, "candidates", None)
        if not candidates:
            feedback = getattr(response, "prompt_feedback", None)
            raise LLMResponseError(
                f"Gemini returned no candidates. Prompt feedback: {feedback}"
            )

        content = getattr(candidates[0], "content", None)
        parts = getattr(content, "parts", None) or []

        text_chunks = []
        tool_calls = []

        for index, part in enumerate(parts):
            if getattr(part, "thought", False):
                continue

            function_call = getattr(part, "function_call", None)
            if function_call is not None:
                arguments = (
                    dict(function_call.args)
                    if getattr(function_call, "args", None)
                    else {}
                )
                tool_calls.append(
                    {
                        "id": getattr(function_call, "id", None)
                        or f"call_{index + 1}",
                        "type": "function",
                        "function": {
                            "name": function_call.name,
                            "arguments": json.dumps(arguments),
                        },
                    }
                )
            elif getattr(part, "text", None):
                text_chunks.append(part.text)

        if not tool_calls and not text_chunks:
            raise LLMResponseError("Gemini returned an empty response")

        return {
            "role": "assistant",
            "content": "".join(text_chunks) or None,
            "tool_calls": tool_calls or None,
        }

    def _generate_with_retries(self, contents: Any, generation_config: Any) -> Any:
        """
        Call generate_content with bounded retries for transient 429/503 errors.

        Delays use exponential backoff: base_delay * 2**attempt. When the
        retries are exhausted, ``LLMRetryExhaustedError`` carries a friendly,
        redacted message. Non-transient errors are re-raised unchanged.
        """
        attempt = 0
        while True:
            try:
                return self._client.models.generate_content(
                    model=self.model,
                    contents=contents,
                    config=generation_config,
                )
            except LLMError:
                raise
            except Exception as exc:
                if not is_retryable_api_error(exc):
                    raise
                if attempt >= self.max_retries:
                    raise LLMRetryExhaustedError(
                        f"Gemini is temporarily unavailable. I retried "
                        f"{self.max_retries} time(s) with exponential backoff "
                        "without success. No task changes were made. Please "
                        "wait a moment and try again."
                    ) from exc
                delay = self.retry_base_delay * (2 ** attempt)
                time.sleep(delay)
                attempt += 1

    def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        tool_choice: str = "auto",
    ) -> Dict[str, Any]:
        try:
            contents, system_instruction = self._build_contents(messages)
            gemini_tools = (
                self._build_tools(tools) if tools else self._default_tools
            )
            generation_config = self._types.GenerateContentConfig(
                system_instruction=system_instruction,
                tools=gemini_tools,
            )

            response = self._generate_with_retries(contents, generation_config)
            return self._parse_response(response)

        except LLMError:
            raise
        except Exception as exc:
            message = self._redact(exc)
            if (
                "timeout" in type(exc).__name__.lower()
                or "timed out" in message.lower()
            ):
                raise LLMTimeoutError(
                    f"Gemini request timed out: {message}"
                ) from exc
            raise LLMAPIError(f"Gemini API error: {message}") from exc

    def get_model_name(self) -> str:
        return self.model


def create_llm_client(provider: Optional[str] = None, system_prompt: str = "") -> BaseLLMClient:
    """
    Factory function to create an LLM client based on configuration.

    Args:
        provider: LLM provider ("gemini" or "mock").
                  Uses config.LLM_PROVIDER if not specified.
        system_prompt: System prompt to use.

    Returns:
        Configured LLM client instance.

    Raises:
        ValueError: If provider is unknown or API key missing.
    """
    provider = (provider or config.LLM_PROVIDER).lower()

    if provider == "mock":
        return MockLLMClient(system_prompt)
    elif provider == "gemini":
        return GeminiLLMClient(system_prompt)
    else:
        raise ValueError(
            f"Unknown LLM provider: {provider}. Supported providers: gemini, mock"
        )


def build_system_prompt(current_date: Optional[date] = None, timezone: str = "UTC") -> str:
    """
    Build the system prompt for the LLM with current date and instructions.

    Args:
        current_date: Current date for relative date resolution. Defaults to
            the configured timezone's current date.
        timezone: Timezone for date interpretation.

    Returns:
        Complete system prompt string.
    """
    if current_date is None:
        current_date = today_in_timezone(timezone)

    tomorrow = current_date + timedelta(days=1)

    return f"""You are an AI-powered personal task management assistant. Your role is to help users manage their tasks using natural language.

CURRENT DATE: {current_date.isoformat()}
TIMEZONE: {timezone}

STORED FIELDS:
- due_date: required ISO date YYYY-MM-DD
- due_time: optional exact time in 24-hour HH:MM (for example 15:00); stored as NULL when unknown
- due_period: optional approximate period, one of morning, afternoon, evening, night; stored as NULL when unknown
Never convert an approximate period into an exact time, and never provide both due_time and due_period.

AVAILABLE OPERATIONS:
1. create_task - Create a task with title, due_date, and optional due_time or due_period
2. list_pending_tasks - List pending tasks chronologically; optional due_date, end_date, due_time, due_period, limit filters
3. complete_task - Mark one task completed by title query
4. get_task_details - Get one task's due date, time or period, and status by title query
5. complete_tasks_by_date - Find pending tasks for a concrete date or date range and ask for confirmation; it never completes anything by itself

RULES:
- ALWAYS use the provided tools for task operations. Never claim to have performed an operation without calling the tool.
- Keep the task title independent of date and time. "Train at 3 PM on Saturday" becomes title "Train", the resolved Saturday due_date, and due_time "15:00".
- For create_task: due_date MUST be YYYY-MM-DD. Resolve relative dates such as "tomorrow", "next Saturday", and "in 3 days" from CURRENT DATE in the TIMEZONE above. If no due date is given, ask for it - DO NOT guess.
- If no time is given, omit due_time and due_period so the task is stored without a time. If the user gives an exact time such as "3 PM", "3:30 PM", "10 AM", or "15:00", normalize it to HH:MM.
- If the user gives only an approximate period such as "tomorrow morning" or "tomorrow evening", set due_period and omit due_time.
- If a time is ambiguous (for example "at 3" without AM/PM), ask the user to clarify instead of inventing a time.
- For complete_task and get_task_details: use task_query with the user's reference. The system handles exact, partial, and ambiguous matching; ask the user to clarify ambiguous references.
- Use complete_tasks_by_date only when a concrete date or date range is known. Never call it without a date, and never mark every task completed because the date is unclear.
- After complete_tasks_by_date returns candidate tasks, ask the user to confirm. Only explicit confirmation authorizes completing the confirmed task IDs; the application completes them after the user says yes.
- If a tool reports not_found, already_completed, or a database error, report that accurately and do not claim success.
- Never make up task information. Always rely on tool results.
- Deleting or clearing tasks is NOT supported. The available tools cannot delete task records. If the user asks to clear, delete, or remove tasks, explain that deletion is not available, state that nothing was deleted, and suggest marking tasks as completed instead (for example "mark all tomorrow's tasks as done"). NEVER claim that tasks were deleted or cleared.
- If a transient API error occurs (for example HTTP 503 or 429), the client retries automatically with exponential backoff. If it still fails, explain that the assistant is temporarily unavailable and that no task changes were made.
- For schedule questions use list_pending_tasks with due_date (for example "What do I have tomorrow at 10 AM?" or "Show my schedule for Saturday"); use limit=1 for "What is my next task?".
- Times are displayed in a readable 12-hour format even though they are stored as 24-hour HH:MM.

EXAMPLES:
User: "Add a task to prepare for the GenAI assignment by tomorrow"
→ Call create_task with title="prepare for the GenAI assignment", due_date="{tomorrow:%Y-%m-%d}"

User: "Train at 3 PM on Saturday"
→ Call create_task with title="Train", the resolved Saturday due_date, due_time="15:00"

User: "Add a task to call mom tomorrow morning"
→ Call create_task with title="call mom", due_date="{tomorrow:%Y-%m-%d}", due_period="morning"

User: "Show me all my pending tasks"
→ Call list_pending_tasks with no arguments

User: "What do I have tomorrow at 10 AM?"
→ Call list_pending_tasks with due_date="{tomorrow:%Y-%m-%d}", due_time="10:00"

User: "What is my next task?"
→ Call list_pending_tasks with limit=1

User: "Mark the Python assignment as completed"
→ Call complete_task with task_query="Python assignment"

User: "Mark all tomorrow's tasks as done"
→ Call complete_tasks_by_date with due_date="{tomorrow:%Y-%m-%d}", then ask the user to confirm

User: "When is my GenAI assignment due?"
→ Call get_task_details with task_query="GenAI assignment"

User: "Clear all my tasks"
→ Do not call any tool. Explain that deletion is not supported and that nothing was deleted, then suggest marking tasks as completed instead.

UNSUPPORTED REQUESTS:
If the user asks for something outside task management (e.g., "Book a flight"), explain that you only support task management operations.
Deletion is outside the supported scope: never delete records, never claim to have deleted them, and never mark tasks completed as a substitute for deletion unless the user explicitly asks to complete them.
"""


def execute_tool_call(
    tool_call: Dict[str, Any],
    task_service,
) -> Dict[str, Any]:
    """
    Execute a validated tool call against the TaskService.

    Args:
        tool_call: Tool call dict with id, type, function (name, arguments).
        task_service: TaskService instance.

    Returns:
        Tool result dict for returning to LLM.
    """
    function = tool_call.get("function", {})
    tool_name = function.get("name", "")
    arguments_str = function.get("arguments", "{}")

    try:
        arguments = json.loads(arguments_str)
    except json.JSONDecodeError as e:
        return {
            "tool_call_id": tool_call.get("id", ""),
            "role": "tool",
            "name": tool_name,
            "content": json.dumps({"success": False, "error": f"Invalid JSON in arguments: {e}"}),
        }

    # Validate arguments
    is_valid, error_msg = validate_tool_arguments(tool_name, arguments)
    if not is_valid:
        return {
            "tool_call_id": tool_call.get("id", ""),
            "role": "tool",
            "name": tool_name,
            "content": json.dumps({"success": False, "error": error_msg}),
        }

    # Route to handler
    handler_name = TOOL_HANDLER_MAP.get(tool_name)
    if not handler_name:
        return {
            "tool_call_id": tool_call.get("id", ""),
            "role": "tool",
            "name": tool_name,
            "content": json.dumps({"success": False, "error": f"Unknown tool: {tool_name}"}),
        }

    handler = getattr(task_service, handler_name, None)
    if not handler:
        return {
            "tool_call_id": tool_call.get("id", ""),
            "role": "tool",
            "name": tool_name,
            "content": json.dumps({"success": False, "error": f"Handler not found: {handler_name}"}),
        }

    try:
        # Execute handler
        if tool_name == "create_task":
            due_date = date.fromisoformat(arguments["due_date"])
            due_time = str(arguments.get("due_time") or "").strip() or None
            due_period = str(arguments.get("due_period") or "").strip() or None
            result = handler(
                arguments["title"],
                due_date,
                due_time=due_time,
                due_period=due_period,
            )
        elif tool_name == "list_pending_tasks":
            list_kwargs = {}
            if arguments.get("due_date"):
                list_kwargs["due_date"] = date.fromisoformat(arguments["due_date"])
            if arguments.get("end_date"):
                list_kwargs["end_date"] = date.fromisoformat(arguments["end_date"])
            if arguments.get("due_time"):
                list_kwargs["due_time"] = arguments["due_time"]
            if arguments.get("due_period"):
                list_kwargs["due_period"] = arguments["due_period"]
            if arguments.get("limit") is not None:
                list_kwargs["limit"] = int(arguments["limit"])
            result = handler(**list_kwargs)
        elif tool_name == "complete_tasks_by_date":
            due_date = date.fromisoformat(arguments["due_date"])
            end_date = (
                date.fromisoformat(arguments["end_date"])
                if arguments.get("end_date")
                else None
            )
            result = handler(due_date, end_date=end_date)
        elif tool_name in ("complete_task", "get_task_details"):
            result = handler(arguments["task_query"])
        else:
            result = handler(**arguments)

        # Convert OperationResult to dict
        result_dict = {
            "success": result.success,
            "status": result.status,
            "message": result.message,
            "count": result.count,
        }
        if result.task:
            result_dict["task"] = result.task.to_dict()
        if result.matches:
            result_dict["matches"] = [t.to_dict() for t in result.matches]
        if result.tasks:
            result_dict["tasks"] = [t.to_dict() for t in result.tasks]

        return {
            "tool_call_id": tool_call.get("id", ""),
            "role": "tool",
            "name": tool_name,
            "content": json.dumps(result_dict),
        }

    except Exception as e:
        return {
            "tool_call_id": tool_call.get("id", ""),
            "role": "tool",
            "name": tool_name,
            "content": json.dumps({"success": False, "error": f"Execution error: {e}"}),
        }