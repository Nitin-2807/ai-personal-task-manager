"""
End-to-end assistant tests for AI-Personal Task Manager.

These tests exercise the user-facing assistant (Phase 4) with a mocked LLM,
using isolated temporary databases.
"""

import json
from datetime import date, timedelta

from src.assistant import Assistant, create_assistant
from src.llm_client import BaseLLMClient, LLMAPIError, LLMTimeoutError
from src.models import TaskStatus
from src.task_service import TaskService


def _tool_call(name: str, arguments: dict) -> dict:
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [{
            "id": "call_test",
            "type": "function",
            "function": {"name": name, "arguments": json.dumps(arguments)},
        }],
    }


class FailingLLMClient(BaseLLMClient):
    """Always raises an API error."""

    def chat(self, messages, tools, tool_choice="auto"):
        raise LLMAPIError("simulated provider outage")

    def get_model_name(self):
        return "failing-llm"


class TimeoutLLMClient(BaseLLMClient):
    """Always raises a timeout."""

    def chat(self, messages, tools, tool_choice="auto"):
        raise LLMTimeoutError("simulated timeout")

    def get_model_name(self):
        return "timeout-llm"


class FixedResponseLLMClient(BaseLLMClient):
    """Returns a fixed response, useful for malformed/invalid output tests."""

    def __init__(self, response):
        super().__init__()
        self.response = response

    def chat(self, messages, tools, tool_choice="auto"):
        return self.response

    def get_model_name(self):
        return "fixed-llm"


class TestAssistantEndToEnd:
    """Required Phase 4 end-to-end scenarios."""

    def test_create_task(self, task_service):
        assistant = create_assistant(task_service=task_service, llm_provider="mock")
        response = assistant.process_message(
            "Add a task to prepare for the GenAI assignment by tomorrow."
        )

        assert "created" in response.lower()
        details = task_service.get_task_details("prepare for the GenAI assignment")
        assert details.success
        assert details.task.status == TaskStatus.PENDING
        assert details.task.due_date == date.today() + timedelta(days=1)

    def test_create_task_without_due_date_asks_for_it(self, task_service):
        assistant = create_assistant(task_service=task_service, llm_provider="mock")
        response = assistant.process_message("Add a task to revise Python.")

        assert "due date" in response.lower()
        assert task_service.get_task_count() == 0

    def test_list_pending_tasks(self, task_service):
        tomorrow = date.today() + timedelta(days=1)
        task_service.create_task("Pending A", tomorrow)
        task_service.create_task("Pending B", tomorrow)
        task_service.complete_task("Pending B")

        assistant = create_assistant(task_service=task_service, llm_provider="mock")
        response = assistant.process_message("Show me all my pending tasks.")

        assert "pending tasks (1)" in response.lower()
        assert "pending a" in response.lower()
        assert "pending b" not in response.lower()

    def test_complete_task(self, task_service):
        tomorrow = date.today() + timedelta(days=1)
        task_service.create_task("Python assignment", tomorrow)

        assistant = create_assistant(task_service=task_service, llm_provider="mock")
        response = assistant.process_message("Mark the Python assignment as completed.")

        assert "completed" in response.lower()
        assert task_service.get_task_details("Python assignment").task.status == TaskStatus.COMPLETED

    def test_get_task_details(self, task_service):
        tomorrow = date.today() + timedelta(days=1)
        task_service.create_task("GenAI assignment", tomorrow)

        assistant = create_assistant(task_service=task_service, llm_provider="mock")
        response = assistant.process_message("When is my GenAI assignment due?")

        assert "due" in response.lower()
        assert tomorrow.isoformat() in response
        assert "pending" in response.lower()

    def test_ambiguous_then_valid_selection(self, task_service):
        tomorrow = date.today() + timedelta(days=1)
        next_week = date.today() + timedelta(days=7)
        task_service.create_task("Python assignment", tomorrow)
        task_service.create_task("Python project", next_week)

        assistant = create_assistant(task_service=task_service, llm_provider="mock")
        response = assistant.process_message("Complete my Python task.")

        assert "multiple" in response.lower()
        assert assistant.has_pending_clarification
        # No mutation before clarification.
        assert task_service.get_task_count(TaskStatus.COMPLETED) == 0

        response = assistant.process_message("Python project")
        assert "completed" in response.lower()
        assert not assistant.has_pending_clarification

        # The project was explicitly chosen and must be the completed task.
        assert task_service.get_task_details("Python project").task.status == TaskStatus.COMPLETED
        assert task_service.get_task_details("Python assignment").task.status == TaskStatus.PENDING

    def test_not_found_response(self, task_service):
        assistant = create_assistant(task_service=task_service, llm_provider="mock")
        response = assistant.process_message("Show details for my nonexistent task.")

        assert "not found" in response.lower()
        assert task_service.get_task_count() == 0

    def test_unsupported_request(self, task_service):
        assistant = create_assistant(task_service=task_service, llm_provider="mock")
        response = assistant.process_message("Book me a flight to Delhi.")

        assert "task" in response.lower()
        assert task_service.get_task_count() == 0

    def test_persistence_across_assistant_interactions(self, task_service, temp_db_path):
        tomorrow = date.today() + timedelta(days=1)

        first = create_assistant(task_service=task_service, llm_provider="mock")
        first.process_message(f"Add a task to persistent demo by {tomorrow.isoformat()}")

        # New service and assistant, same database file.
        second_service = TaskService(temp_db_path)
        second = create_assistant(task_service=second_service, llm_provider="mock")
        response = second.process_message("Show me all my pending tasks.")

        assert "pending tasks (1)" in response.lower()
        assert "persistent demo" in response.lower()


class TestAssistantFailureRecovery:
    """LLM failure must never produce a fabricated success message."""

    def test_llm_api_error_does_not_mutate(self, task_service):
        assistant = Assistant(task_service=task_service, llm_client=FailingLLMClient())
        response = assistant.process_message("Add a task to test failure by tomorrow")

        assert "error" in response.lower()
        assert "created" not in response.lower()
        assert task_service.get_task_count() == 0

    def test_llm_timeout_does_not_mutate(self, task_service):
        assistant = Assistant(task_service=task_service, llm_client=TimeoutLLMClient())
        response = assistant.process_message("Add a task to test timeout by tomorrow")

        assert "timed out" in response.lower()
        assert task_service.get_task_count() == 0

    def test_invalid_tool_arguments_are_rejected(self, task_service):
        client = FixedResponseLLMClient(
            _tool_call("create_task", {"title": "", "due_date": "2026-10-20"})
        )
        assistant = Assistant(task_service=task_service, llm_client=client)
        response = assistant.process_message("Add an empty task")

        assert "failed" in response.lower() or "empty" in response.lower()
        assert task_service.get_task_count() == 0

    def test_invalid_date_is_rejected(self, task_service):
        client = FixedResponseLLMClient(
            _tool_call("create_task", {"title": "Bad date", "due_date": "2026-13-45"})
        )
        assistant = Assistant(task_service=task_service, llm_client=client)
        response = assistant.process_message("Add a task with a bad date")

        assert "failed" in response.lower() or "invalid" in response.lower()
        assert task_service.get_task_count() == 0

    def test_unknown_tool_is_rejected(self, task_service):
        client = FixedResponseLLMClient(_tool_call("delete_database", {}))
        assistant = Assistant(task_service=task_service, llm_client=client)
        response = assistant.process_message("Delete everything")

        assert "failed" in response.lower() or "unknown" in response.lower()
        assert task_service.get_task_count() == 0

    def test_malformed_json_arguments_are_rejected(self, task_service):
        client = FixedResponseLLMClient({
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": "call_bad",
                "type": "function",
                "function": {"name": "create_task", "arguments": "{not valid json"},
            }],
        })
        assistant = Assistant(task_service=task_service, llm_client=client)
        response = assistant.process_message("Add a malformed task")

        assert "failed" in response.lower() or "invalid" in response.lower()
        assert task_service.get_task_count() == 0