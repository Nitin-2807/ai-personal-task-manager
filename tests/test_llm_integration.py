"""
LLM Integration tests for AI-Personal Task Manager.

Tests tool schemas, mock LLM client, assistant orchestration, and error handling.
"""

import json
from datetime import date, timedelta

import pytest

from src.assistant import Assistant, create_assistant
from src.llm_client import (
    MockLLMClient,
    build_system_prompt,
    create_llm_client,
    execute_tool_call,
    get_tool_schemas,
    validate_tool_arguments,
)
from src.models import TaskStatus
from src.task_service import TaskService
from src.tool_schemas import TOOL_HANDLER_MAP


class TestToolSchemas:
    """Tests for tool schema definitions."""

    def test_get_tool_schemas_returns_five_tools(self):
        """Test that we have exactly 5 tool schemas."""
        schemas = get_tool_schemas()
        assert len(schemas) == 5
        tool_names = {s["function"]["name"] for s in schemas}
        assert tool_names == {
            "create_task",
            "list_pending_tasks",
            "complete_task",
            "get_task_details",
            "complete_tasks_by_date",
        }

    def test_create_task_schema(self):
        """Test create_task schema structure."""
        schemas = get_tool_schemas()
        create_schema = next(s for s in schemas if s["function"]["name"] == "create_task")
        fn = create_schema["function"]
        assert fn["name"] == "create_task"
        assert "title" in fn["parameters"]["properties"]
        assert "due_date" in fn["parameters"]["properties"]
        assert "due_time" in fn["parameters"]["properties"]
        assert "due_period" in fn["parameters"]["properties"]
        assert fn["parameters"]["required"] == ["title", "due_date"]

    def test_list_pending_tasks_schema(self):
        """Test list_pending_tasks schema exposes optional filters."""
        schemas = get_tool_schemas()
        list_schema = next(s for s in schemas if s["function"]["name"] == "list_pending_tasks")
        properties = list_schema["function"]["parameters"]["properties"]
        assert set(properties) == {
            "due_date",
            "end_date",
            "due_time",
            "due_period",
            "limit",
        }
        assert "required" not in list_schema["function"]["parameters"]

    def test_complete_tasks_by_date_schema(self):
        """Test complete_tasks_by_date schema requires a concrete date."""
        schemas = get_tool_schemas()
        bulk_schema = next(
            s for s in schemas if s["function"]["name"] == "complete_tasks_by_date"
        )
        fn = bulk_schema["function"]
        assert "due_date" in fn["parameters"]["properties"]
        assert "end_date" in fn["parameters"]["properties"]
        assert fn["parameters"]["required"] == ["due_date"]

    def test_complete_task_schema(self):
        """Test complete_task schema."""
        schemas = get_tool_schemas()
        complete_schema = next(s for s in schemas if s["function"]["name"] == "complete_task")
        fn = complete_schema["function"]
        assert "task_query" in fn["parameters"]["properties"]
        assert fn["parameters"]["required"] == ["task_query"]

    def test_get_task_details_schema(self):
        """Test get_task_details schema."""
        schemas = get_tool_schemas()
        details_schema = next(s for s in schemas if s["function"]["name"] == "get_task_details")
        fn = details_schema["function"]
        assert "task_query" in fn["parameters"]["properties"]
        assert fn["parameters"]["required"] == ["task_query"]


class TestValidateToolArguments:
    """Tests for tool argument validation."""

    def test_validate_create_task_valid(self):
        """Test valid create_task arguments."""
        valid, msg = validate_tool_arguments("create_task", {"title": "Test", "due_date": "2026-10-20"})
        assert valid is True
        assert msg == ""

    def test_validate_create_task_missing_title(self):
        """Test missing title."""
        valid, msg = validate_tool_arguments("create_task", {"due_date": "2026-10-20"})
        assert valid is False
        assert "title" in msg.lower()

    def test_validate_create_task_empty_title(self):
        """Test empty title."""
        valid, msg = validate_tool_arguments("create_task", {"title": "", "due_date": "2026-10-20"})
        assert valid is False
        assert "empty" in msg.lower()

    def test_validate_create_task_missing_due_date(self):
        """Test missing due_date."""
        valid, msg = validate_tool_arguments("create_task", {"title": "Test"})
        assert valid is False
        assert "due_date" in msg.lower()

    def test_validate_create_task_invalid_date_format(self):
        """Test invalid date format."""
        valid, msg = validate_tool_arguments("create_task", {"title": "Test", "due_date": "20-10-2026"})
        assert valid is False
        assert "invalid" in msg.lower()

    def test_validate_create_task_invalid_date(self):
        """Test invalid calendar date."""
        valid, msg = validate_tool_arguments("create_task", {"title": "Test", "due_date": "2026-13-45"})
        assert valid is False
        assert "invalid" in msg.lower()

    def test_validate_list_pending_tasks(self):
        """Test list_pending_tasks validation (no args needed)."""
        valid, msg = validate_tool_arguments("list_pending_tasks", {})
        assert valid is True

    def test_validate_complete_task_valid(self):
        """Test valid complete_task arguments."""
        valid, msg = validate_tool_arguments("complete_task", {"task_query": "test task"})
        assert valid is True

    def test_validate_complete_task_empty_query(self):
        """Test empty task_query."""
        valid, msg = validate_tool_arguments("complete_task", {"task_query": ""})
        assert valid is False

    def test_validate_get_task_details_valid(self):
        """Test valid get_task_details arguments."""
        valid, msg = validate_tool_arguments("get_task_details", {"task_query": "test task"})
        assert valid is True

    def test_validate_unknown_tool(self):
        """Test unknown tool name."""
        valid, msg = validate_tool_arguments("unknown_tool", {})
        assert valid is False
        assert "unknown" in msg.lower()


class TestMockLLMClient:
    """Tests for MockLLMClient."""

    def test_mock_client_creation(self):
        """Test mock client creation."""
        client = MockLLMClient("test prompt")
        assert client.get_model_name() == "mock-llm"
        assert client.system_prompt == "test prompt"

    def test_mock_create_task_intent(self):
        """Test mock client routes create intent."""
        client = MockLLMClient()
        messages = [{"role": "user", "content": "Add a task to test by 2026-10-20"}]
        response = client.chat(messages, get_tool_schemas())

        assert response["role"] == "assistant"
        assert response["tool_calls"] is not None
        assert len(response["tool_calls"]) == 1
        assert response["tool_calls"][0]["function"]["name"] == "create_task"

    def test_mock_list_pending_intent(self):
        """Test mock client routes list intent."""
        client = MockLLMClient()
        messages = [{"role": "user", "content": "Show me pending tasks"}]
        response = client.chat(messages, get_tool_schemas())

        assert response["tool_calls"][0]["function"]["name"] == "list_pending_tasks"

    def test_mock_complete_task_intent(self):
        """Test mock client routes complete intent."""
        client = MockLLMClient()
        messages = [{"role": "user", "content": "Complete the test task"}]
        response = client.chat(messages, get_tool_schemas())

        assert response["tool_calls"][0]["function"]["name"] == "complete_task"

    def test_mock_get_details_intent(self):
        """Test mock client routes details intent."""
        client = MockLLMClient()
        messages = [{"role": "user", "content": "When is the test task due?"}]
        response = client.chat(messages, get_tool_schemas())

        assert response["tool_calls"][0]["function"]["name"] == "get_task_details"


class TestExecuteToolCall:
    """Tests for execute_tool_call function."""

    def test_execute_create_task(self, task_service):
        """Test executing create_task tool call."""
        tool_call = {
            "id": "call_1",
            "type": "function",
            "function": {
                "name": "create_task",
                "arguments": json.dumps({"title": "Test task", "due_date": "2026-10-20"}),
            },
        }

        result = execute_tool_call(tool_call, task_service)

        assert result["role"] == "tool"
        assert result["name"] == "create_task"
        content = json.loads(result["content"])
        assert content["success"] is True
        assert content["status"] == "created"
        assert "task" in content

    def test_execute_list_pending_tasks(self, task_service):
        """Test executing list_pending_tasks tool call."""
        # Create a task first
        tomorrow = date.today() + timedelta(days=1)
        task_service.create_task("Pending task", tomorrow)

        tool_call = {
            "id": "call_2",
            "type": "function",
            "function": {"name": "list_pending_tasks", "arguments": "{}"},
        }

        result = execute_tool_call(tool_call, task_service)

        assert result["role"] == "tool"
        content = json.loads(result["content"])
        assert content["success"] is True
        assert content["status"] == "listed"
        assert content["count"] == 1

    def test_execute_complete_task(self, task_service):
        """Test executing complete_task tool call."""
        tomorrow = date.today() + timedelta(days=1)
        task_service.create_task("Task to complete", tomorrow)

        tool_call = {
            "id": "call_3",
            "type": "function",
            "function": {"name": "complete_task", "arguments": json.dumps({"task_query": "Task to complete"})},
        }

        result = execute_tool_call(tool_call, task_service)

        assert result["role"] == "tool"
        content = json.loads(result["content"])
        assert content["success"] is True
        assert content["status"] == "completed"

    def test_execute_get_task_details(self, task_service):
        """Test executing get_task_details tool call."""
        tomorrow = date.today() + timedelta(days=1)
        task_service.create_task("Detail task", tomorrow)

        tool_call = {
            "id": "call_4",
            "type": "function",
            "function": {"name": "get_task_details", "arguments": json.dumps({"task_query": "Detail task"})},
        }

        result = execute_tool_call(tool_call, task_service)

        assert result["role"] == "tool"
        content = json.loads(result["content"])
        assert content["success"] is True
        assert content["status"] == "retrieved"

    def test_execute_invalid_tool(self, task_service):
        """Test executing unknown tool."""
        tool_call = {
            "id": "call_5",
            "type": "function",
            "function": {"name": "unknown_tool", "arguments": "{}"},
        }

        result = execute_tool_call(tool_call, task_service)

        content = json.loads(result["content"])
        assert content["success"] is False
        assert "unknown" in content["error"].lower()

    def test_execute_invalid_arguments(self, task_service):
        """Test executing with invalid arguments."""
        tool_call = {
            "id": "call_6",
            "type": "function",
            "function": {"name": "create_task", "arguments": json.dumps({"title": ""})},
        }

        result = execute_tool_call(tool_call, task_service)

        content = json.loads(result["content"])
        assert content["success"] is False
        assert "error" in content


class TestAssistant:
    """Tests for Assistant orchestration."""

    def test_assistant_creation(self, task_service):
        """Test assistant creation with mock LLM."""
        assistant = create_assistant(task_service=task_service, llm_provider="mock")
        assert assistant is not None
        assert assistant.task_service == task_service
        assert isinstance(assistant.llm_client, MockLLMClient)

    def test_assistant_create_task(self, task_service):
        """Test assistant creates task via mock LLM."""
        assistant = create_assistant(task_service=task_service, llm_provider="mock")
        response = assistant.process_message("Add a task to test by 2026-10-20")

        # Should contain success message
        assert "created" in response.lower() or "test" in response.lower()

    def test_assistant_list_pending(self, task_service):
        """Test assistant lists pending tasks."""
        tomorrow = date.today() + timedelta(days=1)
        task_service.create_task("Pending task", tomorrow)

        assistant = create_assistant(task_service=task_service, llm_provider="mock")
        response = assistant.process_message("Show me pending tasks")

        assert "pending" in response.lower()

    def test_assistant_complete_task(self, task_service):
        """Test assistant completes task."""
        tomorrow = date.today() + timedelta(days=1)
        task_service.create_task("Task to complete", tomorrow)

        assistant = create_assistant(task_service=task_service, llm_provider="mock")
        response = assistant.process_message("Complete the task to complete")

        assert "complete" in response.lower()

    def test_assistant_get_details(self, task_service):
        """Test assistant gets task details."""
        tomorrow = date.today() + timedelta(days=1)
        task_service.create_task("Detail task", tomorrow)

        assistant = create_assistant(task_service=task_service, llm_provider="mock")
        response = assistant.process_message("When is the detail task due?")

        assert "detail" in response.lower() or "due" in response.lower()

    def test_assistant_ambiguous_task_clarification(self, task_service):
        """Test assistant handles ambiguous task."""
        tomorrow = date.today() + timedelta(days=1)
        task_service.create_task("Python assignment", tomorrow)
        task_service.create_task("Python project", tomorrow)

        assistant = create_assistant(task_service=task_service, llm_provider="mock")
        response = assistant.process_message("Complete the Python task")

        # Should ask for clarification
        assert "multiple" in response.lower() or "ambiguous" in response.lower() or "specify" in response.lower()
        assert assistant.has_pending_clarification

    def test_assistant_clarification_followup(self, task_service):
        """Test assistant handles clarification follow-up."""
        tomorrow = date.today() + timedelta(days=1)
        task_service.create_task("Python assignment", tomorrow)
        task_service.create_task("Python project", tomorrow)

        assistant = create_assistant(task_service=task_service, llm_provider="mock")
        # First request - ambiguous
        assistant.process_message("Complete the Python task")
        assert assistant.has_pending_clarification

        # Follow-up - select first
        response = assistant.process_message("1")

        # Should complete the first task
        assert "complete" in response.lower()
        assert not assistant.has_pending_clarification

    def test_assistant_nonexistent_task(self, task_service):
        """Test assistant handles nonexistent task."""
        assistant = create_assistant(task_service=task_service, llm_provider="mock")
        response = assistant.process_message("Complete the nonexistent task")

        assert "not found" in response.lower() or "found" in response.lower()

    def test_assistant_already_completed(self, task_service):
        """Test assistant handles already completed task."""
        tomorrow = date.today() + timedelta(days=1)
        task_service.create_task("Done task", tomorrow)
        task_service.complete_task("Done task")

        assistant = create_assistant(task_service=task_service, llm_provider="mock")
        response = assistant.process_message("Complete the done task")

        assert "already" in response.lower() or "completed" in response.lower()

    def test_assistant_unsupported_request(self, task_service):
        """Test assistant handles unsupported request."""
        assistant = create_assistant(task_service=task_service, llm_provider="mock")
        response = assistant.process_message("Book me a flight to Delhi")

        # Should respond without tool call, explaining limitations
        assert "task" in response.lower() or "support" in response.lower()

    def test_assistant_empty_message(self, task_service):
        """Test assistant handles empty message."""
        assistant = create_assistant(task_service=task_service, llm_provider="mock")
        response = assistant.process_message("")
        assert "please" in response.lower() or "message" in response.lower()


class TestBuildSystemPrompt:
    """Tests for system prompt building."""

    def test_build_system_prompt_contains_date(self):
        """Test system prompt contains current date."""
        prompt = build_system_prompt(date(2026, 10, 19))
        assert "2026-10-19" in prompt

    def test_build_system_prompt_contains_operations(self):
        """Test system prompt lists all operations."""
        prompt = build_system_prompt()
        assert "create_task" in prompt
        assert "list_pending_tasks" in prompt
        assert "complete_task" in prompt
        assert "get_task_details" in prompt

    def test_build_system_prompt_contains_rules(self):
        """Test system prompt contains key rules."""
        prompt = build_system_prompt()
        assert "YYYY-MM-DD" in prompt
        assert "tomorrow" in prompt.lower()
        assert "ambiguous" in prompt.lower()
        assert "not_found" in prompt.lower() or "not found" in prompt.lower()


class TestCreateLLMClient:
    """Tests for LLM client factory."""

    def test_create_mock_client(self):
        """Test creating mock client."""
        client = create_llm_client("mock")
        assert isinstance(client, MockLLMClient)

    def test_create_mock_client_case_insensitive(self):
        """Test provider name case insensitivity."""
        client = create_llm_client("MOCK")
        assert isinstance(client, MockLLMClient)

    def test_create_unknown_provider_fails(self):
        """Test unknown provider raises error."""
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            create_llm_client("unknown_provider")