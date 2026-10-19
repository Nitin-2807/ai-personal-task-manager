"""
Tests for LLM failure handling, Gemini retry behaviour, cancellation, and
destructive-operation safety.

Covers:
- bounded exponential-backoff retries for transient Gemini 429/503 errors;
- friendly messages when retries are exhausted;
- guarantee that failed LLM requests never report task operations as success;
- explicit refusal of "clear/delete all tasks" requests with no mutation;
- rejection of model-invented destructive tool calls;
- cancellation of pending confirmations.

All Gemini checks stub the SDK call; no network request is made.
"""

import json
import time
from datetime import date, timedelta

import pytest

from src.assistant import Assistant
from src.llm_client import (
    DESTRUCTIVE_OPERATION_REFUSAL,
    BaseLLMClient,
    GeminiLLMClient,
    LLMAPIError,
    LLMRetryExhaustedError,
    LLMTimeoutError,
    MockLLMClient,
    execute_tool_call,
    is_destructive_task_intent,
    is_retryable_api_error,
)
from src.models import TaskStatus


class FakeAPIError(Exception):
    """Stand-in for provider SDK errors, with an optional HTTP status code."""

    def __init__(self, message: str = "api error", code=None):
        super().__init__(message)
        if code is not None:
            self.code = code


class StubModels:
    """Records calls and runs a behaviour function instead of a network call."""

    def __init__(self, behavior):
        self._behavior = behavior
        self.calls = 0

    def generate_content(self, **kwargs):
        self.calls += 1
        return self._behavior(self.calls)


class StubClient:
    """Minimal stand-in for the google-genai Client."""

    def __init__(self, behavior):
        self.models = StubModels(behavior)


def _raise_then_succeed(exc, failures: int):
    def behavior(call_number):
        if call_number <= failures:
            raise exc
        return "stub-response"

    return behavior


def _always_raise(exc):
    def behavior(_call_number):
        raise exc

    return behavior


class FixedLLM(BaseLLMClient):
    """Return a single canned response regardless of the prompt."""

    def __init__(self, response):
        super().__init__()
        self.response = response

    def chat(self, messages, tools, tool_choice="auto"):
        return self.response

    def get_model_name(self):
        return "fixed"


class ExplodingLLM(BaseLLMClient):
    """Raise a configured exception from chat()."""

    def __init__(self, exc: Exception):
        super().__init__()
        self.exc = exc
        self.calls = 0

    def chat(self, messages, tools, tool_choice="auto"):
        self.calls += 1
        raise self.exc

    def get_model_name(self):
        return "exploding"


class SpyLLM(BaseLLMClient):
    """Record chat() calls and return a benign message."""

    def __init__(self):
        super().__init__()
        self.calls = 0

    def chat(self, messages, tools, tool_choice="auto"):
        self.calls += 1
        return {"role": "assistant", "content": "ok", "tool_calls": None}

    def get_model_name(self):
        return "spy"


def _tool_call(name: str, arguments: dict) -> dict:
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call_test",
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(arguments)},
            }
        ],
    }


# ---------------------------------------------------------------------------
# Gemini retry behaviour
# ---------------------------------------------------------------------------


@pytest.fixture
def recorded_sleeps(monkeypatch):
    """Capture backoff delays without actually sleeping."""
    delays = []
    monkeypatch.setattr(time, "sleep", delays.append)
    return delays


@pytest.fixture
def gemini_client(monkeypatch, recorded_sleeps):
    pytest.importorskip("google.genai")
    client = GeminiLLMClient(
        system_prompt="",
        api_key="test-key-not-real",
        max_retries=2,
        retry_base_delay=0.25,
    )
    monkeypatch.setattr(
        client,
        "_parse_response",
        lambda response: {
            "role": "assistant",
            "content": response,
            "tool_calls": None,
        },
    )
    return client


class TestGeminiRetry:
    """Transient 429/503 errors are retried with exponential backoff."""

    def test_503_is_retried_then_succeeds(self, gemini_client, recorded_sleeps):
        from google.genai import errors

        transient = errors.APIError(
            code=503, response_json={"error": {"message": "high demand"}}
        )
        gemini_client._client = StubClient(_raise_then_succeed(transient, 2))

        result = gemini_client.chat([{"role": "user", "content": "hi"}], [])

        assert result["content"] == "stub-response"
        assert gemini_client._client.models.calls == 3
        assert recorded_sleeps == [0.25, 0.5]

    def test_429_is_retried(self, gemini_client, recorded_sleeps):
        from google.genai import errors

        transient = errors.APIError(
            code=429, response_json={"error": {"message": "rate limited"}}
        )
        gemini_client._client = StubClient(_raise_then_succeed(transient, 1))

        result = gemini_client.chat([{"role": "user", "content": "hi"}], [])

        assert result["content"] == "stub-response"
        assert gemini_client._client.models.calls == 2
        assert recorded_sleeps == [0.25]

    def test_delays_follow_exponential_backoff(self, gemini_client, recorded_sleeps):
        transient = FakeAPIError("503 UNAVAILABLE", code=503)
        gemini_client._client = StubClient(_always_raise(transient))

        with pytest.raises(LLMRetryExhaustedError):
            gemini_client.chat([{"role": "user", "content": "hi"}], [])

        # max_retries=2 -> two retries: base, then 2x base.
        assert recorded_sleeps == [0.25, 0.5]
        assert gemini_client._client.models.calls == 3

    def test_exhausted_retries_raise_friendly_message(
        self, gemini_client, recorded_sleeps
    ):
        transient = FakeAPIError("503 UNAVAILABLE: high demand", code=503)
        gemini_client._client = StubClient(_always_raise(transient))

        with pytest.raises(LLMRetryExhaustedError) as excinfo:
            gemini_client.chat([{"role": "user", "content": "hi"}], [])

        message = str(excinfo.value)
        assert "temporarily unavailable" in message.lower()
        assert "retried 2 time(s)" in message.lower()
        assert "no task changes were made" in message.lower()
        assert "try again" in message.lower()
        # The API key must never appear in an error message.
        assert "test-key-not-real" not in message

    def test_non_retryable_error_is_not_retried(self, gemini_client, recorded_sleeps):
        from google.genai import errors

        bad_request = errors.APIError(
            code=400, response_json={"error": {"message": "bad request"}}
        )
        gemini_client._client = StubClient(_always_raise(bad_request))

        with pytest.raises(LLMAPIError) as excinfo:
            gemini_client.chat([{"role": "user", "content": "hi"}], [])

        assert not isinstance(excinfo.value, LLMRetryExhaustedError)
        assert gemini_client._client.models.calls == 1
        assert recorded_sleeps == []

    def test_text_only_transient_error_is_recognized(self, gemini_client, recorded_sleeps):
        text_only = FakeAPIError("RESOURCE_EXHAUSTED: quota exceeded")
        gemini_client._client = StubClient(_raise_then_succeed(text_only, 1))

        result = gemini_client.chat([{"role": "user", "content": "hi"}], [])

        assert result["content"] == "stub-response"
        assert recorded_sleeps == [0.25]

    def test_timeout_is_not_retried(self, gemini_client, recorded_sleeps):
        timed_out = FakeAPIError("request timed out after 30s")
        gemini_client._client = StubClient(_always_raise(timed_out))

        with pytest.raises(LLMTimeoutError):
            gemini_client.chat([{"role": "user", "content": "hi"}], [])

        assert gemini_client._client.models.calls == 1
        assert recorded_sleeps == []

    def test_zero_retries_attempts_once(self, monkeypatch, recorded_sleeps):
        pytest.importorskip("google.genai")
        client = GeminiLLMClient(
            system_prompt="",
            api_key="test-key-not-real",
            max_retries=0,
            retry_base_delay=0.25,
        )
        client._client = StubClient(_always_raise(FakeAPIError("503 UNAVAILABLE")))

        with pytest.raises(LLMRetryExhaustedError):
            client.chat([{"role": "user", "content": "hi"}], [])

        assert client._client.models.calls == 1
        assert recorded_sleeps == []

    def test_explicit_status_code_overrides_text(self):
        assert is_retryable_api_error(FakeAPIError("503 mentioned", code=400)) is False
        assert is_retryable_api_error(FakeAPIError("boom", code=503)) is True
        assert is_retryable_api_error(FakeAPIError("boom", code=429)) is True
        assert is_retryable_api_error(FakeAPIError("503 UNAVAILABLE")) is True
        assert is_retryable_api_error(FakeAPIError("invalid argument")) is False


# ---------------------------------------------------------------------------
# Failed LLM requests must never report success
# ---------------------------------------------------------------------------


class TestLLMFailureNeverSucceeds:
    """Provider failures must surface as errors and mutate nothing."""

    def test_api_error_is_reported(self, task_service):
        client = ExplodingLLM(LLMAPIError("provider down"))
        assistant = Assistant(task_service=task_service, llm_client=client)

        response = assistant.process_message("Add a task to test by tomorrow")

        assert "error" in response.lower()
        assert "created" not in response.lower()
        assert task_service.get_task_count() == 0

    def test_retry_exhausted_shows_friendly_message(self, task_service):
        friendly = LLMRetryExhaustedError(
            "Gemini is temporarily unavailable. I retried 3 time(s) with "
            "exponential backoff without success. No task changes were made. "
            "Please wait a moment and try again."
        )
        client = ExplodingLLM(friendly)
        assistant = Assistant(task_service=task_service, llm_client=client)

        response = assistant.process_message("Add a task to test by tomorrow")

        assert response == str(friendly)
        assert "temporarily unavailable" in response.lower()
        assert "no task changes" in response.lower()
        assert "created" not in response.lower()
        assert task_service.get_task_count() == 0

    def test_timeout_is_reported(self, task_service):
        client = ExplodingLLM(LLMTimeoutError("deadline exceeded"))
        assistant = Assistant(task_service=task_service, llm_client=client)

        response = assistant.process_message("Show all pending tasks")

        assert "timed out" in response.lower()
        assert task_service.get_task_count() == 0

    def test_unexpected_exception_is_reported(self, task_service):
        client = ExplodingLLM(RuntimeError("boom"))
        assistant = Assistant(task_service=task_service, llm_client=client)

        response = assistant.process_message("Show all pending tasks")

        assert "unexpected error" in response.lower()
        assert "traceback" not in response.lower()
        assert task_service.get_task_count() == 0

    def test_failed_llm_never_executes_a_tool(self, task_service, monkeypatch):
        executed = []
        monkeypatch.setattr(
            "src.assistant.execute_tool_call",
            lambda *args, **kwargs: executed.append(args),
        )
        client = ExplodingLLM(LLMAPIError("provider down"))
        assistant = Assistant(task_service=task_service, llm_client=client)

        assistant.process_message("Add a task to test by tomorrow")

        assert executed == []
        assert task_service.get_task_count() == 0

    def test_unparseable_tool_result_is_not_reported_as_success(
        self, task_service, monkeypatch
    ):
        monkeypatch.setattr(
            "src.assistant.execute_tool_call",
            lambda tool_call, service: {
                "role": "tool",
                "tool_call_id": "call_test",
                "name": "create_task",
                "content": "not-json",
            },
        )
        client = FixedLLM(
            _tool_call("create_task", {"title": "X", "due_date": "2026-10-20"})
        )
        assistant = Assistant(task_service=task_service, llm_client=client)

        response = assistant.process_message("Add a task X by 2026-10-20")

        assert "operation completed" not in response.lower()
        assert "created" not in response.lower()
        assert "couldn't process" in response.lower()
        assert task_service.get_task_count() == 0

    def test_tool_result_without_message_is_not_reported_as_success(
        self, task_service, monkeypatch
    ):
        monkeypatch.setattr(
            "src.assistant.execute_tool_call",
            lambda tool_call, service: {
                "role": "tool",
                "tool_call_id": "call_test",
                "name": "create_task",
                "content": json.dumps({}),
            },
        )
        client = FixedLLM(
            _tool_call("create_task", {"title": "X", "due_date": "2026-10-20"})
        )
        assistant = Assistant(task_service=task_service, llm_client=client)

        response = assistant.process_message("Add a task X by 2026-10-20")

        assert "operation completed" not in response.lower()
        assert task_service.get_task_count() == 0


# ---------------------------------------------------------------------------
# Destructive-operation safety
# ---------------------------------------------------------------------------


class TestDestructiveIntentDetection:
    """The destructive-intent detector must be precise enough to be useful."""

    @pytest.mark.parametrize(
        "message",
        [
            "clear all tasks",
            "Clear my tasks.",
            "delete all my tasks",
            "Remove every task",
            "wipe my task list",
            "purge tasks",
        ],
    )
    def test_destructive_messages_detected(self, message):
        assert is_destructive_task_intent(message) is True

    @pytest.mark.parametrize(
        "message",
        [
            "complete all tasks",
            "mark all tomorrow's tasks as done",
            "clear the kitchen",
            "delete the date from my task note",
            "when is my task due?",
            "",
        ],
    )
    def test_non_destructive_messages_not_detected(self, message):
        assert is_destructive_task_intent(message) is False


class TestClearAllTasksRefusal:
    """'Clear all tasks' must be refused explicitly and never mutate."""

    @pytest.mark.parametrize(
        "message",
        [
            "Clear all my tasks.",
            "Delete all tasks",
            "Remove every task",
            "wipe all tasks",
        ],
    )
    def test_refused_without_mutation(self, task_service, message):
        tomorrow = date.today() + timedelta(days=1)
        task_service.create_task("Alpha", tomorrow)
        task_service.create_task("Beta", tomorrow)
        assistant = Assistant(task_service=task_service, llm_client=MockLLMClient())

        response = assistant.process_message(message)

        assert "can't delete tasks" in response.lower()
        assert "nothing was deleted" in response.lower()
        assert task_service.get_task_count() == 2
        pending = [t.title for t in task_service._repo.get_pending_tasks()]
        assert pending == ["Alpha", "Beta"]

    def test_refusal_does_not_call_the_llm(self, task_service):
        tomorrow = date.today() + timedelta(days=1)
        task_service.create_task("Alpha", tomorrow)
        client = SpyLLM()
        assistant = Assistant(task_service=task_service, llm_client=client)

        response = assistant.process_message("Clear all tasks")

        assert client.calls == 0
        assert response == DESTRUCTIVE_OPERATION_REFUSAL
        assert task_service.get_task_count() == 1

    def test_mock_client_refuses_destructive_request_directly(self):
        client = MockLLMClient()
        response = client.chat(
            [{"role": "user", "content": "clear all tasks"}], []
        )
        assert response["tool_calls"] is None
        assert "nothing was deleted" in response["content"].lower()

    def test_clear_during_pending_confirmation_is_refused_and_cancelled(
        self, task_service
    ):
        tomorrow = date.today() + timedelta(days=1)
        task_service.create_task("Alpha", tomorrow)
        task_service.create_task("Beta", tomorrow)
        assistant = Assistant(task_service=task_service, llm_client=MockLLMClient())

        assistant.process_message("Mark all tomorrow's tasks as done.")
        assert assistant.has_pending_confirmation is True

        response = assistant.process_message("clear all tasks")

        assert "nothing was deleted" in response.lower()
        assert assistant.has_pending_confirmation is False
        assert [
            t.title for t in task_service._repo.get_pending_tasks()
        ] == ["Alpha", "Beta"]

    def test_clear_during_pending_clarification_is_refused(self, task_service):
        tomorrow = date.today() + timedelta(days=1)
        task_service.create_task("Party planning", tomorrow)
        task_service.create_task("Party shopping", tomorrow)
        assistant = Assistant(task_service=task_service, llm_client=MockLLMClient())

        assistant.process_message("When is my Party?")
        assert assistant.has_pending_clarification is True

        response = assistant.process_message("delete all tasks")

        assert "nothing was deleted" in response.lower()
        assert assistant.has_pending_clarification is False
        assert task_service.get_task_count() == 2
        assert task_service.get_task_count(TaskStatus.COMPLETED) == 0

    @pytest.mark.parametrize(
        "tool_name", ["clear_all_tasks", "delete_all_tasks", "drop_tasks"]
    )
    def test_model_invented_deletion_tool_is_rejected(
        self, task_service, tool_name
    ):
        tomorrow = date.today() + timedelta(days=1)
        task_service.create_task("Keep me", tomorrow)
        assistant = Assistant(
            task_service=task_service,
            llm_client=FixedLLM(_tool_call(tool_name, {})),
        )

        # Neutral message: the destructive tool call comes from the model,
        # not from the user, so it must be rejected by the tool allowlist.
        response = assistant.process_message("Do something with my tasks")

        assert "unknown tool" in response.lower()
        assert "deleted" not in response.lower()
        assert task_service.get_task_count() == 1
        assert task_service.get_task_details("Keep me").task.status == TaskStatus.PENDING

    def test_execute_tool_call_rejects_deletion_directly(self, task_service):
        tomorrow = date.today() + timedelta(days=1)
        task_service.create_task("Keep me", tomorrow)

        tool_call = _tool_call("delete_all_tasks", {})["tool_calls"][0]
        result = execute_tool_call(tool_call, task_service)
        payload = json.loads(result["content"])

        assert payload["success"] is False
        assert "unknown tool" in payload["error"].lower()
        assert task_service.get_task_count() == 1


class TestCancellation:
    """Cancelling a pending confirmation must change nothing."""

    def test_cancel_bulk_completion_changes_nothing(self, task_service):
        tomorrow = date.today() + timedelta(days=1)
        task_service.create_task("Alpha", tomorrow)
        task_service.create_task("Beta", tomorrow)
        assistant = Assistant(task_service=task_service, llm_client=MockLLMClient())

        assistant.process_message("Mark all tomorrow's tasks as done.")
        response = assistant.process_message("No.")

        assert "cancelled" in response.lower()
        assert assistant.has_pending_confirmation is False
        assert task_service.get_task_count(TaskStatus.COMPLETED) == 0
        assert [
            t.title for t in task_service._repo.get_pending_tasks()
        ] == ["Alpha", "Beta"]

    def test_cancel_then_confirm_nothing_remains_armed(self, task_service):
        tomorrow = date.today() + timedelta(days=1)
        task_service.create_task("Alpha", tomorrow)
        assistant = Assistant(task_service=task_service, llm_client=MockLLMClient())

        assistant.process_message("Mark all tomorrow's tasks as done.")
        assistant.process_message("cancel")

        # A bare "yes" after cancellation must not complete anything.
        assistant.process_message("yes")

        assert assistant.has_pending_confirmation is False
        assert task_service.get_task_count(TaskStatus.COMPLETED) == 0
