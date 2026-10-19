"""
Tests for validated bulk completion by date.

Covers preparation, confirmation, cancellation, zero/one/multiple matches,
date-range handling, tool validation, database errors, and false-success
prevention. All databases are isolated temporary files.
"""

import json
from datetime import date, timedelta

import pytest

from src.assistant import Assistant
from src.database import DatabaseOperationError
from src.llm_client import BaseLLMClient, MockLLMClient
from src.task_service import TaskService
from src.tool_schemas import validate_tool_arguments


class FixedLLM(BaseLLMClient):
    """Return a single canned response regardless of the prompt."""

    def __init__(self, response):
        super().__init__()
        self.response = response

    def chat(self, messages, tools, tool_choice="auto"):
        return self.response

    def get_model_name(self):
        return "fixed"


def _tool_call(name: str, arguments: dict) -> dict:
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call_bulk",
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(arguments)},
            }
        ],
    }


def _pending_titles(task_service: TaskService) -> list:
    return [task.title for task in task_service._repo.get_pending_tasks()]


class TestPrepareBulkCompletion:
    """Preparing must never mutate tasks and must match dates exactly."""

    def test_zero_matches_is_reported(self, task_service):
        result = task_service.prepare_bulk_completion(date(2026, 10, 20))
        assert result.success is False
        assert result.status == "not_found"
        assert "2026-10-20" in result.message
        assert result.count == 0

    def test_one_match_returns_candidate_with_id(self, task_service):
        created = task_service.create_task("Solo", date(2026, 10, 20))

        result = task_service.prepare_bulk_completion(date(2026, 10, 20))

        assert result.success is True
        assert result.status == "confirmation_required"
        assert result.count == 1
        assert [task.id for task in result.tasks] == [created.task.id]
        # Nothing completed yet.
        assert _pending_titles(task_service) == ["Solo"]

    def test_multiple_matches_return_all_candidates(self, task_service):
        target = date(2026, 10, 20)
        task_service.create_task("Mock test", target)
        task_service.create_task("Date", target)
        task_service.create_task("Football match", target)
        task_service.create_task("Later", target + timedelta(days=1))

        result = task_service.prepare_bulk_completion(target)

        assert result.count == 3
        titles = [task.title for task in result.tasks]
        assert titles == ["Mock test", "Date", "Football match"]
        assert "Should I mark all 3" in result.message
        assert _pending_titles(task_service) == [
            "Mock test",
            "Date",
            "Football match",
            "Later",
        ]

    def test_exact_date_does_not_include_later_dates(self, task_service):
        """Regression: single-date bulk action must not complete future tasks."""
        target = date(2026, 10, 20)
        task_service.create_task("On date", target)
        task_service.create_task("Later", target + timedelta(days=1))
        task_service.create_task("Much later", target + timedelta(days=5))

        result = task_service.prepare_bulk_completion(target)

        assert result.count == 1
        assert result.tasks[0].title == "On date"

    def test_range_is_inclusive(self, task_service):
        start = date(2026, 10, 20)
        end = date(2026, 10, 22)
        for offset, title in enumerate(["Day one", "Day two", "Day three"]):
            task_service.create_task(title, start + timedelta(days=offset))
        task_service.create_task("Outside", end + timedelta(days=1))

        result = task_service.prepare_bulk_completion(start, end_date=end)

        assert result.count == 3
        assert "2026-10-20 to 2026-10-22" in result.message

    def test_end_before_start_rejected(self, task_service):
        result = task_service.prepare_bulk_completion(
            date(2026, 10, 22), end_date=date(2026, 10, 20)
        )
        assert result.success is False
        assert task_service.get_task_count() == 0


class TestConfirmationFlow:
    """Bulk completion happens only after explicit confirmation."""

    def _seed_tomorrow(self, task_service: TaskService) -> date:
        tomorrow = date.today() + timedelta(days=1)
        task_service.create_task("Mock test", tomorrow)
        task_service.create_task("Date", tomorrow)
        task_service.create_task("Football match", tomorrow)
        task_service.create_task("Later", tomorrow + timedelta(days=1))
        return tomorrow

    def test_candidates_shown_before_confirmation(self, task_service):
        self._seed_tomorrow(task_service)
        assistant = Assistant(task_service=task_service, llm_client=MockLLMClient())

        response = assistant.process_message("Mark all tomorrow's tasks as done.")

        assert "Mock test" in response
        assert "Date" in response
        assert "Football match" in response
        assert "[id " in response
        assert assistant.has_pending_confirmation is True
        assert len(_pending_titles(task_service)) == 4

    def test_yes_completes_only_confirmed_ids(self, task_service):
        self._seed_tomorrow(task_service)
        assistant = Assistant(task_service=task_service, llm_client=MockLLMClient())

        assistant.process_message("Mark all tomorrow's tasks as done.")
        response = assistant.process_message("Yes.")

        assert "Completed 3" in response
        assert "Mock test" in response
        assert "Football match" in response
        assert assistant.has_pending_confirmation is False
        assert _pending_titles(task_service) == ["Later"]

    @pytest.mark.parametrize("confirmation", ["yes", "Yes!", "confirm", "ok", "sure, go ahead"])
    def test_affirmative_variants(self, task_service, confirmation):
        self._seed_tomorrow(task_service)
        assistant = Assistant(task_service=task_service, llm_client=MockLLMClient())

        assistant.process_message("Mark all tomorrow's tasks as done.")
        response = assistant.process_message(confirmation)

        assert "Completed 3" in response
        assert _pending_titles(task_service) == ["Later"]

    @pytest.mark.parametrize("cancellation", ["No.", "no", "No, cancel", "stop"])
    def test_cancellation_leaves_tasks_pending(self, task_service, cancellation):
        self._seed_tomorrow(task_service)
        assistant = Assistant(task_service=task_service, llm_client=MockLLMClient())

        assistant.process_message("Mark all tomorrow's tasks as done.")
        response = assistant.process_message(cancellation)

        assert "cancelled" in response.lower()
        assert assistant.has_pending_confirmation is False
        assert len(_pending_titles(task_service)) == 4

    def test_unrecognized_reply_keeps_confirmation_pending(self, task_service):
        self._seed_tomorrow(task_service)
        assistant = Assistant(task_service=task_service, llm_client=MockLLMClient())

        assistant.process_message("Mark all tomorrow's tasks as done.")
        response = assistant.process_message("banana")

        assert "yes" in response.lower() and "no" in response.lower()
        assert assistant.has_pending_confirmation is True
        assert len(_pending_titles(task_service)) == 4

    def test_new_command_abandons_confirmation_without_completing(self, task_service):
        self._seed_tomorrow(task_service)
        assistant = Assistant(task_service=task_service, llm_client=MockLLMClient())

        assistant.process_message("Mark all tomorrow's tasks as done.")
        response = assistant.process_message("Show all pending tasks")

        assert "Pending tasks (4)" in response
        assert assistant.has_pending_confirmation is False
        assert len(_pending_titles(task_service)) == 4

    def test_unclear_date_asks_and_never_completes(self, task_service):
        self._seed_tomorrow(task_service)
        assistant = Assistant(task_service=task_service, llm_client=MockLLMClient())

        response = assistant.process_message("Mark all tasks as done.")

        assert "which date" in response.lower()
        assert assistant.has_pending_confirmation is False
        assert len(_pending_titles(task_service)) == 4

    def test_zero_matching_date_reports_accurately(self, task_service):
        assistant = Assistant(task_service=task_service, llm_client=MockLLMClient())

        response = assistant.process_message(
            "Mark all tasks on 2030-01-01 as done."
        )

        assert "No pending tasks found" in response
        assert assistant.has_pending_confirmation is False

    def test_complete_tasks_are_skipped_by_prepare(self, task_service):
        target = date.today() + timedelta(days=1)
        task_service.create_task("Alpha", target)
        task_service.create_task("Beta", target)
        task_service.complete_task("Alpha")

        result = task_service.prepare_bulk_completion(target)

        assert result.count == 1
        assert [task.title for task in result.tasks] == ["Beta"]

    def test_single_task_completion_still_works(self, task_service):
        tomorrow = date.today() + timedelta(days=1)
        task_service.create_task("Alpha", tomorrow)
        task_service.create_task("Beta", tomorrow)

        result = task_service.complete_task("Alpha")

        assert result.success is True
        assert result.status == "completed"
        assert _pending_titles(task_service) == ["Beta"]


class TestBulkToolValidation:
    """Tool arguments for bulk completion must be strictly validated."""

    def test_missing_due_date_rejected(self):
        valid, message = validate_tool_arguments("complete_tasks_by_date", {})
        assert valid is False
        assert "due_date" in message.lower()

    def test_invalid_date_rejected(self):
        valid, message = validate_tool_arguments(
            "complete_tasks_by_date", {"due_date": "20-10-2026"}
        )
        assert valid is False
        assert "invalid" in message.lower()

    def test_end_before_start_rejected(self):
        valid, message = validate_tool_arguments(
            "complete_tasks_by_date",
            {"due_date": "2026-10-22", "end_date": "2026-10-20"},
        )
        assert valid is False
        assert "earlier" in message.lower()

    def test_valid_range_accepted(self):
        valid, message = validate_tool_arguments(
            "complete_tasks_by_date",
            {"due_date": "2026-10-20", "end_date": "2026-10-22"},
        )
        assert valid is True
        assert message == ""

    def test_list_validation_rejects_bad_limit(self):
        valid, message = validate_tool_arguments("list_pending_tasks", {"limit": 0})
        assert valid is False
        assert "limit" in message.lower()

    def test_list_validation_rejects_bad_date(self):
        valid, message = validate_tool_arguments(
            "list_pending_tasks", {"due_date": "not-a-date"}
        )
        assert valid is False
        assert "invalid" in message.lower()

    def test_list_validation_rejects_time_and_period_together(self):
        valid, message = validate_tool_arguments(
            "list_pending_tasks", {"due_time": "10:00", "due_period": "morning"}
        )
        assert valid is False

    def test_create_validation_rejects_time_and_period_together(self):
        valid, message = validate_tool_arguments(
            "create_task",
            {"title": "X", "due_date": "2026-10-20", "due_time": "10:00", "due_period": "morning"},
        )
        assert valid is False

    def test_create_validation_rejects_bad_time(self):
        valid, _ = validate_tool_arguments(
            "create_task",
            {"title": "X", "due_date": "2026-10-20", "due_time": "25:00"},
        )
        assert valid is False

    def test_create_validation_rejects_bad_period(self):
        valid, _ = validate_tool_arguments(
            "create_task",
            {"title": "X", "due_date": "2026-10-20", "due_period": "dawn"},
        )
        assert valid is False


class TestBulkErrorsAndFalseSuccess:
    """Failures must be reported and must not complete anything."""

    def test_missing_date_tool_call_is_rejected(self, task_service):
        tomorrow = date.today() + timedelta(days=1)
        task_service.create_task("Keep me", tomorrow)
        assistant = Assistant(
            task_service=task_service,
            llm_client=FixedLLM(_tool_call("complete_tasks_by_date", {})),
        )

        response = assistant.process_message("Mark all tasks done")

        assert "failed" in response.lower() or "missing" in response.lower()
        assert "Completed" not in response
        assert _pending_titles(task_service) == ["Keep me"]

    def test_database_error_while_finding_is_reported(self, task_service, monkeypatch):
        tomorrow = date.today() + timedelta(days=1)
        task_service.create_task("Keep me", tomorrow)

        def boom(*args, **kwargs):
            raise DatabaseOperationError("simulated read failure")

        monkeypatch.setattr(task_service._repo, "get_pending_tasks_filtered", boom)
        assistant = Assistant(
            task_service=task_service,
            llm_client=FixedLLM(_tool_call("complete_tasks_by_date", {"due_date": tomorrow.isoformat()})),
        )

        response = assistant.process_message("Mark all tomorrow's tasks done")

        assert "failed" in response.lower()
        assert "Completed" not in response
        assert assistant.has_pending_confirmation is False

    def test_database_error_while_completing_is_reported(self, task_service, monkeypatch):
        tomorrow = date.today() + timedelta(days=1)
        task_service.create_task("Keep me", tomorrow)
        assistant = Assistant(task_service=task_service, llm_client=MockLLMClient())

        assistant.process_message("Mark all tomorrow's tasks as done.")

        def boom(*args, **kwargs):
            raise DatabaseOperationError("simulated write failure")

        monkeypatch.setattr(task_service._repo, "complete_tasks_by_ids", boom)
        response = assistant.process_message("yes")

        assert "failed" in response.lower()
        assert "Completed" not in response
        assert _pending_titles(task_service) == ["Keep me"]

    def test_no_pending_ids_reports_error(self, task_service):
        created = task_service.create_task("Done already", date(2026, 10, 20))
        task_service.complete_task("Done already")

        result = task_service.complete_tasks_by_ids([created.task.id])

        assert result.success is False
        assert "No pending tasks" in result.message

    def test_empty_ids_rejected(self, task_service):
        result = task_service.complete_tasks_by_ids([])
        assert result.success is False

    def test_non_integer_ids_rejected(self, task_service):
        result = task_service.complete_tasks_by_ids(["abc"])
        assert result.success is False
