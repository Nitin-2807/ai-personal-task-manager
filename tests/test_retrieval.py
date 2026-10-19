"""
Retrieval and output tests for the assistant.

Covers schedule questions, exact-time lookups, next-task queries, full
pending lists, and preserved ambiguity handling.
"""

from datetime import date, timedelta

import pytest

from src.assistant import Assistant
from src.config import config
from src.date_utils import today_in_timezone
from src.llm_client import MockLLMClient
from src.task_service import TaskService


def _today() -> date:
    return today_in_timezone(config.TIMEZONE)


def _next_weekday(today: date, target: int) -> date:
    delta = (target - today.weekday()) % 7
    return today + timedelta(days=delta or 7)


@pytest.fixture
def assistant(task_service: TaskService) -> Assistant:
    return Assistant(task_service=task_service, llm_client=MockLLMClient())


class TestRetrieval:
    """Requests like 'When is my train?' must resolve through tools."""

    def test_when_is_my_train(self, assistant, task_service):
        saturday = _next_weekday(_today(), 5)
        task_service.create_task("Train", saturday, due_time="15:00")

        response = assistant.process_message("When is my train?")

        assert "Train" in response
        assert saturday.isoformat() in response
        assert "3:00 PM" in response
        assert "pending" in response

    def test_tomorrow_at_10am_exact_time_lookup(self, assistant, task_service):
        tomorrow = _today() + timedelta(days=1)
        task_service.create_task("Standup", tomorrow, due_time="10:00")
        task_service.create_task("Lunch", tomorrow, due_time="12:00")
        task_service.create_task("Untimed", tomorrow)

        response = assistant.process_message("What do I have tomorrow at 10 AM?")

        assert "Standup" in response
        assert "Lunch" not in response
        assert "Untimed" not in response

    def test_tomorrow_morning_period_lookup(self, assistant, task_service):
        tomorrow = _today() + timedelta(days=1)
        task_service.create_task("Call mom", tomorrow, due_period="morning")
        task_service.create_task("Call dad", tomorrow, due_period="evening")

        response = assistant.process_message("What do I have tomorrow morning?")

        assert "Call mom" in response
        assert "Call dad" not in response
        assert "morning" in response

    def test_schedule_for_saturday(self, assistant, task_service):
        saturday = _next_weekday(_today(), 5)
        sunday = saturday + timedelta(days=1)
        task_service.create_task("Football match", saturday, due_time="09:00")
        task_service.create_task("Rest", sunday)

        response = assistant.process_message("Show my schedule for Saturday.")

        assert "Football match" in response
        assert "9:00 AM" in response
        assert "Rest" not in response

    def test_next_task_returns_only_first(self, assistant, task_service):
        today = _today()
        task_service.create_task("Later", today + timedelta(days=2))
        task_service.create_task("Sooner", today + timedelta(days=1))

        response = assistant.process_message("What is my next task?")

        assert "Sooner" in response
        assert "Later" not in response

    def test_show_all_pending(self, assistant, task_service):
        today = _today()
        task_service.create_task("Alpha", today)
        task_service.create_task("Beta", today + timedelta(days=1))

        response = assistant.process_message("Show all pending tasks")

        assert "Pending tasks (2)" in response
        assert "Alpha" in response
        assert "Beta" in response

    def test_no_pending_tasks_message(self, assistant):
        response = assistant.process_message("Show all pending tasks")
        assert "No pending tasks found" in response

    def test_nonexistent_task_reported(self, assistant):
        response = assistant.process_message("When is my unicorn?")
        assert "not found" in response.lower()

    def test_ambiguous_task_name_still_handled(self, assistant, task_service):
        today = _today()
        task_service.create_task("Party planning", today)
        task_service.create_task("Party shopping", today + timedelta(days=1))

        response = assistant.process_message("When is my Party?")

        assert "multiple matching tasks" in response.lower()
        assert assistant.has_pending_clarification is True

        resolved = assistant.process_message("Party planning")
        assert "Party planning" in resolved
        assert assistant.has_pending_clarification is False

    def test_retrieval_does_not_create_tasks(self, assistant, task_service):
        tomorrow = _today() + timedelta(days=1)
        task_service.create_task("Only task", tomorrow)

        assistant.process_message("What do I have tomorrow?")
        assistant.process_message("Show my schedule for Saturday.")
        assistant.process_message("What is my next task?")

        assert task_service.get_task_count() == 1
