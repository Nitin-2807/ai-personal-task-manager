"""
Error-handling tests for AI-Personal Task Manager.

Covers validation failures, database errors, ambiguous references,
already-completed tasks, and false-success prevention.
"""

import json
from datetime import date, timedelta

from src.assistant import Assistant
from src.database import DatabaseOperationError
from src.llm_client import BaseLLMClient
from src.models import TaskStatus


class FixedLLM(BaseLLMClient):
    def __init__(self, response):
        super().__init__()
        self.response = response

    def chat(self, messages, tools, tool_choice="auto"):
        return self.response

    def get_model_name(self):
        return "fixed"


class TestValidationErrors:
    """Input validation must fail safely without mutating data."""

    def test_empty_title_rejected(self, task_service):
        result = task_service.create_task("", date.today() + timedelta(days=1))
        assert result.success is False
        assert task_service.get_task_count() == 0

    def test_whitespace_title_rejected(self, task_service):
        result = task_service.create_task("   ", date.today() + timedelta(days=1))
        assert result.success is False
        assert task_service.get_task_count() == 0

    def test_invalid_due_date_type_rejected(self, task_service):
        result = task_service.create_task("Test", "not-a-date")
        assert result.success is False
        assert task_service.get_task_count() == 0

    def test_empty_complete_query_rejected(self, task_service):
        result = task_service.complete_task("")
        assert result.success is False
        assert result.status == "error"

    def test_empty_details_query_rejected(self, task_service):
        result = task_service.get_task_details("  ")
        assert result.success is False
        assert result.status == "error"


class TestNoFalseSuccess:
    """Operations must report actual failures instead of fake success."""

    def test_database_error_on_create(self, task_service, monkeypatch):
        def boom(*args, **kwargs):
            raise DatabaseOperationError("simulated write failure")

        monkeypatch.setattr(task_service._repo, "create_task", boom)
        result = task_service.create_task("DB failure", date.today() + timedelta(days=1))

        assert result.success is False
        assert result.status == "error"
        assert "failed" in result.message.lower()

    def test_database_error_on_complete(self, task_service, monkeypatch):
        tomorrow = date.today() + timedelta(days=1)
        task_service.create_task("Will fail", tomorrow)

        def boom(*args, **kwargs):
            raise DatabaseOperationError("simulated update failure")

        monkeypatch.setattr(task_service._repo, "complete_task", boom)
        result = task_service.complete_task("Will fail")

        assert result.success is False
        assert result.status == "error"
        assert "failed" in result.message.lower()

    def test_database_error_on_list(self, task_service, monkeypatch):
        def boom(*args, **kwargs):
            raise DatabaseOperationError("simulated read failure")

        monkeypatch.setattr(task_service._repo, "get_pending_tasks", boom)
        result = task_service.list_pending_tasks()

        assert result.success is False
        assert result.status == "error"

    def test_database_error_on_details(self, task_service, monkeypatch):
        def boom(*args, **kwargs):
            raise DatabaseOperationError("simulated read failure")

        monkeypatch.setattr(task_service._repo, "match_task", boom)
        result = task_service.get_task_details("anything")

        assert result.success is False
        assert result.status == "error"

    def test_assistant_db_error_not_reported_as_success(self, task_service, monkeypatch):
        tomorrow = date.today() + timedelta(days=1)
        task_service.create_task("Complete me", tomorrow)

        def boom(*args, **kwargs):
            raise DatabaseOperationError("simulated update failure")

        monkeypatch.setattr(task_service._repo, "complete_task", boom)

        client = FixedLLM({
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": "call_db",
                "type": "function",
                "function": {"name": "complete_task", "arguments": json.dumps({"task_query": "Complete me"})},
            }],
        })
        assistant = Assistant(task_service=task_service, llm_client=client)
        response = assistant.process_message("Complete Complete me")

        assert "failed" in response.lower()
        assert "marked complete" not in response.lower()
        # The task must remain pending.
        assert task_service.get_task_details("Complete me").task.status == TaskStatus.PENDING


class TestAmbiguityAndNonexistence:
    """Ambiguous or missing tasks must never be modified."""

    def test_ambiguous_completion_does_not_mutate(self, task_service):
        tomorrow = date.today() + timedelta(days=1)
        task_service.create_task("Python assignment", tomorrow)
        task_service.create_task("Python project", tomorrow)

        result = task_service.complete_task("Python")

        assert result.success is False
        assert result.status == "ambiguous"
        assert len(result.matches) == 2
        assert task_service.get_task_count(TaskStatus.COMPLETED) == 0

    def test_nonexistent_completion_does_not_insert(self, task_service):
        before = task_service.get_task_count()
        result = task_service.complete_task("Flight booking")

        assert result.success is False
        assert result.status == "not_found"
        assert task_service.get_task_count() == before

    def test_nonexistent_details_does_not_insert(self, task_service):
        result = task_service.get_task_details("Flight booking")

        assert result.success is False
        assert result.status == "not_found"
        assert task_service.get_task_count() == 0

    def test_duplicate_completion_is_informative(self, task_service):
        tomorrow = date.today() + timedelta(days=1)
        created = task_service.create_task("Already done", tomorrow)
        task_service.complete_task("Already done")

        result = task_service.complete_task("Already done")

        assert result.success is False
        assert result.status == "already_completed"
        assert result.task.id == created.task.id
        assert result.task.status == TaskStatus.COMPLETED

    def test_duplicate_completion_preserves_created_at(self, task_service):
        tomorrow = date.today() + timedelta(days=1)
        created = task_service.create_task("Stable", tomorrow)
        task_service.complete_task("Stable")

        task_service.complete_task("Stable")
        refreshed = task_service.get_task_details("Stable").task

        assert refreshed.created_at == created.task.created_at


class TestLLMFailureSafety:
    """Invalid model output must not execute unintended actions."""

    def test_non_tool_response_is_safe(self, task_service):
        client = FixedLLM({
            "role": "assistant",
            "content": "I can only help with task management.",
            "tool_calls": None,
        })
        assistant = Assistant(task_service=task_service, llm_client=client)
        response = assistant.process_message("Book a flight")

        assert "task management" in response.lower()
        assert task_service.get_task_count() == 0

    def test_error_response_contains_no_traceback(self, task_service):
        client = FixedLLM({
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": "call_bad",
                "type": "function",
                "function": {"name": "create_task", "arguments": "{bad json"},
            }],
        })
        assistant = Assistant(task_service=task_service, llm_client=client)
        response = assistant.process_message("Add malformed")

        assert "traceback" not in response.lower()
        assert "simulated" not in response.lower()
        assert task_service.get_task_count() == 0

    def test_sql_injection_is_not_executed(self, task_service):
        tomorrow = date.today() + timedelta(days=1)
        malicious = "Robert'); DROP TABLE tasks;--"
        result = task_service.create_task(malicious, tomorrow)

        assert result.success is True
        # Table still exists and the malicious text is stored only as data.
        assert task_service.get_task_count() == 1
        assert task_service.get_task_details(malicious).success is True