"""
Test configuration and fixtures for AI-Personal Task Manager.

Provides isolated test databases and common fixtures.
"""

import tempfile
from pathlib import Path
from typing import Generator

import pytest

from src.task_service import TaskService


@pytest.fixture(scope="function")
def temp_db_path() -> Generator[Path, None, None]:
    """Create a temporary database file for each test."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    try:
        yield db_path
    finally:
        # Cleanup
        try:
            db_path.unlink(missing_ok=True)
        except Exception:
            pass


@pytest.fixture(scope="function")
def task_service(temp_db_path: Path) -> TaskService:
    """Create a TaskService with isolated test database."""
    return TaskService(temp_db_path)


@pytest.fixture(scope="function")
def sample_tasks(task_service: TaskService) -> list:
    """Create sample tasks for testing."""
    from datetime import date, timedelta

    today = date.today()
    tomorrow = today + timedelta(days=1)
    next_week = today + timedelta(days=7)

    tasks = [
        task_service.create_task("Python assignment", tomorrow),
        task_service.create_task("GenAI interview prep", next_week),
        task_service.create_task("Write documentation", today),
    ]
    return tasks