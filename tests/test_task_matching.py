"""
Task title matching tests.

These tests document the matching precedence used by the assistant:

1. exact case-insensitive title match;
2. partial (substring) match;
3. all-significant-word match with stop-word filtering.

Ambiguous matches must be reported as ambiguous and must never be resolved by
silently choosing one task.
"""

from datetime import date, timedelta

import pytest

from src.models import MatchResult, TaskStatus
from src.task_repository import TaskRepository
from src.task_service import TaskService


@pytest.fixture
def matching_service(temp_db_path):
    """Task service backed by an isolated temporary database."""
    return TaskService(temp_db_path)


def _add(service, title, days=1):
    result = service.create_task(title, date.today() + timedelta(days=days))
    assert result.success
    return result.task


class TestMatchingPrecedence:
    def test_exact_match_takes_priority_over_partial(self, matching_service):
        _add(matching_service, "Python")
        _add(matching_service, "Python assignment")

        result = matching_service.get_task_details("Python")

        assert result.success
        assert result.task.title == "Python"

    def test_exact_match_is_case_insensitive(self, matching_service):
        _add(matching_service, "Python Assignment")

        result = matching_service.get_task_details("python assignment")

        assert result.success
        assert result.task.title == "Python Assignment"

    def test_surrounding_whitespace_is_ignored(self, matching_service):
        _add(matching_service, "Whitespace task")

        result = matching_service.get_task_details("   whitespace task   ")

        assert result.success
        assert result.task.title == "Whitespace task"

    def test_partial_match_is_case_insensitive(self, matching_service):
        _add(matching_service, "Python assignment")

        result = matching_service.get_task_details("ASSIGN")

        assert result.success
        assert result.task.title == "Python assignment"


class TestWordBasedMatching:
    def test_all_significant_words_are_required(self, matching_service):
        _add(matching_service, "Prepare the GenAI assignment")
        _add(matching_service, "Python assignment")

        result = matching_service.get_task_details("GenAI assignment")

        assert result.success
        assert result.task.title == "Prepare the GenAI assignment"

    def test_missing_word_prevents_false_positive(self, matching_service):
        _add(matching_service, "Prepare the GenAI assignment")

        result = matching_service.get_task_details("Python assignment")

        assert result.success is False
        assert result.status == MatchResult.NOT_FOUND.value

    def test_stop_words_are_ignored(self, matching_service):
        _add(matching_service, "Python assignment")

        result = matching_service.get_task_details("the Python task")

        assert result.success
        assert result.task.title == "Python assignment"

    def test_generic_word_match_can_be_ambiguous(self, matching_service):
        _add(matching_service, "Python assignment")
        _add(matching_service, "Python project")

        result = matching_service.get_task_details("Python task")

        assert result.success is False
        assert result.status == MatchResult.AMBIGUOUS.value
        assert {task.title for task in result.matches} == {
            "Python assignment",
            "Python project",
        }

    def test_significant_word_without_any_match(self, matching_service):
        _add(matching_service, "Python assignment")

        result = matching_service.get_task_details("flight booking")

        assert result.status == MatchResult.NOT_FOUND.value


class TestMatchingRepositoryContract:
    def test_empty_query_returns_no_matches(self, temp_db_path):
        repository = TaskRepository(temp_db_path)

        assert repository.find_tasks_by_title("") == ()
        assert repository.find_tasks_by_title("   ") == ()

    def test_completed_tasks_remain_matchable(self, matching_service):
        _add(matching_service, "Completed but findable")
        matching_service.complete_task("Completed but findable")

        result = matching_service.get_task_details("Completed but findable")

        assert result.success
        assert result.task.status == TaskStatus.COMPLETED

    def test_duplicate_titles_are_ambiguous(self, matching_service):
        _add(matching_service, "Duplicate title")
        _add(matching_service, "Duplicate title")

        result = matching_service.get_task_details("Duplicate title")

        assert result.status == MatchResult.AMBIGUOUS.value
        assert len(result.matches) == 2
