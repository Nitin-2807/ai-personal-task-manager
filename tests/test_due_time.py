"""
Tests for structured due times and approximate periods.

Covers service creation rules, repository filtering/ordering, NULL storage,
12-hour display, mock natural-language parsing, and relative-date boundaries.
"""

from datetime import date, timedelta

import sqlite3

import pytest

from src.assistant import Assistant
from src.config import config
from src.date_utils import today_in_timezone
from src.llm_client import MockLLMClient, _parse_relative_date
from src.task_service import TaskService


def _today() -> date:
    return today_in_timezone(config.TIMEZONE)


def _next_weekday(today: date, target: int) -> date:
    """Resolve a weekday name: same day means next week (mock convention)."""
    delta = (target - today.weekday()) % 7
    return today + timedelta(days=delta or 7)


@pytest.fixture
def assistant(task_service: TaskService) -> Assistant:
    return Assistant(task_service=task_service, llm_client=MockLLMClient())


class TestCreateWithStructuredTime:
    """create_task must store exact times and periods separately."""

    def test_create_with_exact_time(self, task_service):
        result = task_service.create_task(
            "Train", _today(), due_time="15:00"
        )
        assert result.success is True
        assert result.task.due_time == "15:00"
        assert result.task.due_period is None
        assert "3:00 PM" in result.message

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("3 PM", "15:00"),
            ("3:30 PM", "15:30"),
            ("15:00", "15:00"),
            ("10 AM", "10:00"),
        ],
    )
    def test_common_time_formats_are_normalized(self, task_service, raw, expected):
        result = task_service.create_task("Standup", _today(), due_time=raw)
        assert result.success is True
        assert result.task.due_time == expected

    def test_create_with_approximate_period(self, task_service):
        result = task_service.create_task(
            "Call mom", _today(), due_period="morning"
        )
        assert result.success is True
        assert result.task.due_time is None
        assert result.task.due_period == "morning"
        assert "(morning)" in result.message

    def test_missing_time_is_null(self, task_service):
        result = task_service.create_task("Revision", _today())
        assert result.success is True
        assert result.task.due_time is None
        assert result.task.due_period is None

        stored = task_service._repo.get_pending_tasks()[0]
        assert stored.due_time is None
        assert stored.due_period is None
        assert stored.to_dict()["due_time"] is None
        assert stored.to_dict()["due_period"] is None

    def test_both_time_and_period_rejected(self, task_service):
        result = task_service.create_task(
            "Conflicting", _today(), due_time="15:00", due_period="evening"
        )
        assert result.success is False
        assert task_service.get_task_count() == 0

    def test_invalid_time_rejected_without_creating(self, task_service):
        result = task_service.create_task("Bad time", _today(), due_time="25:00")
        assert result.success is False
        assert task_service.get_task_count() == 0

    def test_invalid_period_rejected_without_creating(self, task_service):
        result = task_service.create_task("Bad period", _today(), due_period="dawn")
        assert result.success is False
        assert task_service.get_task_count() == 0

    def test_details_and_list_display_structured_fields(self, task_service):
        task_service.create_task("Train", _today(), due_time="15:00")
        task_service.create_task("Call mom", _today(), due_period="evening")

        details = task_service.get_task_details("Train")
        assert "3:00 PM" in details.message

        listing = task_service.list_pending_tasks()
        assert "3:00 PM" in listing.message
        assert "(evening)" in listing.message

    def test_repository_stores_null_for_missing_time(self, temp_db_path):
        service = TaskService(temp_db_path)
        service.create_task("No time", _today())

        conn = sqlite3.connect(temp_db_path)
        row = conn.execute(
            "SELECT due_time, due_period FROM tasks WHERE title = 'No time'"
        ).fetchone()
        conn.close()
        assert row == (None, None)


class TestRepositoryFiltering:
    """Filters and ordering must be exact, inclusive, and stable."""

    def test_exact_date_filter_does_not_leak_later_dates(self, task_service):
        """Regression: a single date filter must not behave like 'from date on'."""
        target = date(2026, 10, 20)
        task_service.create_task("On date", target)
        task_service.create_task("Later", target + timedelta(days=1))

        matches = task_service._repo.get_pending_tasks_filtered(due_date=target)
        assert [task.title for task in matches] == ["On date"]

    def test_date_range_is_inclusive(self, task_service):
        start = date(2026, 10, 20)
        end = date(2026, 10, 22)
        for offset, title in enumerate(["Day one", "Day two", "Day three"]):
            task_service.create_task(title, start + timedelta(days=offset))
        task_service.create_task("Outside", end + timedelta(days=1))

        matches = task_service._repo.get_pending_tasks_filtered(
            due_date=start, end_date=end
        )
        assert [task.title for task in matches] == [
            "Day one",
            "Day two",
            "Day three",
        ]

    def test_exact_time_filter(self, task_service):
        target = date(2026, 10, 20)
        task_service.create_task("Ten AM", target, due_time="10:00")
        task_service.create_task("Three PM", target, due_time="15:00")
        task_service.create_task("Morning", target, due_period="morning")

        matches = task_service._repo.get_pending_tasks_filtered(
            due_date=target, due_time="10:00"
        )
        assert [task.title for task in matches] == ["Ten AM"]

    def test_period_filter(self, task_service):
        target = date(2026, 10, 20)
        task_service.create_task("Morning", target, due_period="morning")
        task_service.create_task("Evening", target, due_period="evening")
        task_service.create_task("Ten AM", target, due_time="10:00")

        matches = task_service._repo.get_pending_tasks_filtered(
            due_date=target, due_period="morning"
        )
        assert [task.title for task in matches] == ["Morning"]

    def test_limit_returns_next_task(self, task_service):
        today = _today()
        task_service.create_task("Second", today + timedelta(days=2))
        task_service.create_task("First", today + timedelta(days=1))

        matches = task_service._repo.get_pending_tasks_filtered(limit=1)
        assert [task.title for task in matches] == ["First"]

    def test_chronological_order_with_times_and_no_times(self, task_service):
        target = date(2026, 10, 20)
        task_service.create_task("Afternoon", target, due_time="15:00")
        task_service.create_task("Untimed", target)
        task_service.create_task("Morning", target, due_time="09:30")
        task_service.create_task("Earlier date", target - timedelta(days=1))

        titles = [task.title for task in task_service._repo.get_pending_tasks()]
        assert titles == ["Earlier date", "Untimed", "Morning", "Afternoon"]

    def test_due_display_uses_twelve_hour_and_period(self, task_service):
        target = date(2026, 10, 20)
        task_service.create_task("Timed", target, due_time="15:00")
        task_service.create_task("Period", target, due_period="evening")
        task_service.create_task("Plain", target)

        displays = {t.title: t.due_display for t in task_service._repo.get_pending_tasks()}
        assert displays["Timed"] == "2026-10-20 at 3:00 PM"
        assert displays["Period"] == "2026-10-20 (evening)"
        assert displays["Plain"] == "2026-10-20"

    def test_service_listing_with_filters(self, task_service):
        target = date(2026, 10, 20)
        task_service.create_task("Ten AM", target, due_time="10:00")
        task_service.create_task("Other", target + timedelta(days=1))

        result = task_service.list_pending_tasks(due_date=target, due_time="10:00")
        assert result.success is True
        assert result.count == 1
        assert "Ten AM" in result.message

    def test_service_listing_rejects_end_before_start(self, task_service):
        result = task_service.list_pending_tasks(
            due_date=date(2026, 10, 22), end_date=date(2026, 10, 20)
        )
        assert result.success is False


class TestMockTimeParsing:
    """Natural-language input must produce structured fields and clean titles."""

    def test_train_at_3pm_on_saturday(self, assistant, task_service):
        response = assistant.process_message("Train at 3 PM on Saturday")

        assert "Task created" in response
        tasks = task_service._repo.get_pending_tasks()
        assert len(tasks) == 1
        assert tasks[0].title == "Train"
        assert tasks[0].due_time == "15:00"
        assert tasks[0].due_date == _next_weekday(_today(), 5)

    def test_add_phrase_with_time_and_weekday(self, assistant, task_service):
        assistant.process_message("Add a task to train at 3:30 PM on Saturday")
        task = task_service._repo.get_pending_tasks()[0]
        assert task.title == "train"
        assert task.due_time == "15:30"

    def test_tomorrow_morning_period(self, assistant, task_service):
        assistant.process_message("Add a task to call mom tomorrow morning")
        task = task_service._repo.get_pending_tasks()[0]
        assert task.title == "call mom"
        assert task.due_date == _today() + timedelta(days=1)
        assert task.due_period == "morning"
        assert task.due_time is None

    def test_tomorrow_evening_period(self, assistant, task_service):
        assistant.process_message("Add a task to relax tomorrow evening")
        task = task_service._repo.get_pending_tasks()[0]
        assert task.title == "relax"
        assert task.due_period == "evening"

    def test_24_hour_time(self, assistant, task_service):
        assistant.process_message("Add a task to run at 15:00 tomorrow")
        task = task_service._repo.get_pending_tasks()[0]
        assert task.due_time == "15:00"

    def test_10am(self, assistant, task_service):
        assistant.process_message("Add a task to join the standup tomorrow at 10 AM")
        task = task_service._repo.get_pending_tasks()[0]
        assert task.title == "join the standup"
        assert task.due_time == "10:00"

    def test_ambiguous_time_asks_instead_of_inventing(self, assistant, task_service):
        response = assistant.process_message("Add a task to train at 3 tomorrow")

        assert "3 AM" in response and "3 PM" in response
        assert task_service.get_task_count() == 0

    def test_missing_date_asks_and_does_not_create(self, assistant, task_service):
        response = assistant.process_message("Add a task to train at 3 PM")
        assert "date" in response.lower()
        assert task_service.get_task_count() == 0


class TestRelativeDateBoundaries:
    """Relative dates must behave around day, week, and month boundaries."""

    @pytest.mark.parametrize(
        ("expression", "today", "expected"),
        [
            ("tomorrow", date(2026, 10, 31), date(2026, 11, 1)),
            ("tomorrow", date(2026, 12, 31), date(2027, 1, 1)),
            ("next week", date(2026, 10, 28), date(2026, 11, 4)),
            ("in 3 days", date(2026, 1, 30), date(2026, 2, 2)),
            ("in 5 days", date(2026, 12, 29), date(2027, 1, 3)),
            ("next saturday", date(2026, 10, 24), date(2026, 10, 31)),
            ("saturday", date(2026, 10, 24), date(2026, 10, 31)),
            ("this saturday", date(2026, 10, 24), date(2026, 10, 24)),
            ("2026-11-01", date(2026, 10, 31), date(2026, 11, 1)),
        ],
    )
    def test_boundary_resolution(self, expression, today, expected):
        assert _parse_relative_date(expression, today) == expected
