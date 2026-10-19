"""
Assistant orchestration for AI-Personal Task Manager.

Connects the LLM client, task service, and tool execution into a complete assistant.
"""

import json
import re
from datetime import date
from typing import Any, Dict, List, Optional

from src.config import config
from src.date_utils import format_due
from src.llm_client import (
    DESTRUCTIVE_OPERATION_REFUSAL,
    BaseLLMClient,
    LLMError,
    LLMAPIError,
    LLMRetryExhaustedError,
    LLMTimeoutError,
    build_system_prompt,
    create_llm_client,
    execute_tool_call,
    get_tool_schemas,
    is_destructive_task_intent,
)
from src.models import OperationResult
from src.task_service import TaskService


class AssistantError(Exception):
    """Base exception for assistant errors."""
    pass


class Assistant:
    """
    Main assistant class that orchestrates LLM interaction and task operations.

    Handles:
    - User message processing
    - LLM communication with function calling
    - Tool execution and validation
    - Conversation state for clarification follow-ups
    """

    def __init__(
        self,
        task_service: Optional[TaskService] = None,
        llm_client: Optional[BaseLLMClient] = None,
        system_prompt: Optional[str] = None,
    ):
        self.task_service = task_service or TaskService()
        self.llm_client = llm_client or create_llm_client()
        self.system_prompt = system_prompt or build_system_prompt(
            timezone=config.TIMEZONE
        )
        self.tools = get_tool_schemas()

        # Conversation state for clarification and bulk-completion confirmation
        self._pending_clarification: Optional[Dict[str, Any]] = None
        self._pending_confirmation: Optional[Dict[str, Any]] = None

    # Affirmative and negative answers accepted for bulk confirmation.
    _AFFIRMATIVE = {
        "yes", "y", "yeah", "yep", "yup", "confirm", "confirmed", "ok",
        "okay", "sure", "proceed", "please",
    }
    _NEGATIVE = {
        "no", "n", "nope", "cancel", "stop", "abort", "nevermind",
    }

    def process_message(self, user_message: str) -> str:
        """
        Process a user message and return the assistant's response.

        Args:
            user_message: User's natural language input.

        Returns:
            Assistant's response string.
        """
        if not user_message or not user_message.strip():
            return "Please provide a message."

        # Check if this is a pending bulk-completion confirmation first.
        if self._pending_confirmation:
            return self._handle_confirmation(user_message.strip())

        # Check if this is a clarification response
        if self._pending_clarification:
            return self._handle_clarification(user_message.strip())

        # Hard safety guard: deleting/clearing tasks is never supported and
        # must never reach the provider or any tool.
        if is_destructive_task_intent(user_message):
            return DESTRUCTIVE_OPERATION_REFUSAL

        # Build messages for LLM
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_message.strip()},
        ]

        try:
            # Get LLM response
            response = self.llm_client.chat(messages, self.tools)

            # Handle tool calls if present
            if response.get("tool_calls"):
                return self._handle_tool_calls(response["tool_calls"], messages)

            # No tool calls - return LLM's direct response
            return response.get("content", "I'm not sure how to help with that.")

        except LLMRetryExhaustedError as e:
            # Friendly, pre-formatted message; no task changes were made.
            return str(e)
        except LLMAPIError as e:
            return f"LLM API error: {e}. Please try again."
        except LLMTimeoutError:
            return "The request timed out. Please try again."
        except LLMError as e:
            return f"LLM error: {e}"
        except Exception as e:
            return f"An unexpected error occurred: {e}"

    def _handle_tool_calls(
        self,
        tool_calls: List[Dict[str, Any]],
        messages: List[Dict[str, Any]],
    ) -> str:
        """
        Execute tool calls and return the result message.

        Args:
            tool_calls: List of tool calls from LLM.
            messages: Current conversation messages.

        Returns:
            Final response string.
        """
        # Add assistant message with tool calls to conversation
        messages.append({
            "role": "assistant",
            "content": None,
            "tool_calls": tool_calls,
        })

        last_result_data = None
        confirmation_message = None

        # Execute each tool call
        for tool_call in tool_calls:
            result = execute_tool_call(tool_call, self.task_service)
            messages.append(result)

            # Parse result for status checking
            try:
                result_data = json.loads(result["content"])
                last_result_data = result_data

                # Bulk completion candidates require explicit confirmation.
                if (
                    result_data.get("status") == "confirmation_required"
                    and result_data.get("tasks")
                ):
                    self._pending_confirmation = {
                        "tool_name": tool_call["function"]["name"],
                        "ids": [task["id"] for task in result_data["tasks"]],
                        "titles": [task["title"] for task in result_data["tasks"]],
                    }
                    confirmation_message = result_data.get("message")
                    continue

                # Check if this was a clarification request (ambiguous task)
                if result_data.get("status") == "ambiguous" and result_data.get("matches"):
                    # Store clarification state for follow-up (convert dicts to Task-like objects)
                    self._pending_clarification = {
                        "tool_name": tool_call["function"]["name"],
                        "original_query": tool_call["function"]["arguments"],
                        "matches": result_data["matches"],  # These are dicts from JSON
                    }
            except (json.JSONDecodeError, KeyError):
                pass

        # Bulk-completion prompts take precedence over the generic message.
        if confirmation_message:
            return confirmation_message

        # If we have a pending clarification, return the clarification message
        if self._pending_clarification:
            matches = self._pending_clarification["matches"]
            match_list = "\n".join(
                f"  {i+1}. {m['title']} "
                f"(due: {format_due(m['due_date'], m.get('due_time'), m.get('due_period'))}, "
                f"status: {m['status']})"
                for i, m in enumerate(matches)
            )
            return (
                f"I found multiple matching tasks:\n{match_list}\n\n"
                "Please specify which task you mean (e.g., 'the first one', 'task 2', or the full title)."
            )

        # For non-ambiguous results, return the tool's message directly.
        # Never fall back to a success-sounding message when the tool
        # returned an error or produced no usable result.
        if isinstance(last_result_data, dict):
            if last_result_data.get("message"):
                return last_result_data["message"]
            if last_result_data.get("error"):
                return f"Request failed: {last_result_data['error']}"
            if last_result_data.get("success") is True:
                return "Operation completed."

        return (
            "I couldn't process the tool result safely, so no task changes "
            "were reported. Please try again."
        )

    def _handle_clarification(self, user_response: str) -> str:
        """
        Handle user's response to an ambiguity clarification.

        Args:
            user_response: User's clarification response.

        Returns:
            Assistant's response after resolving clarification.
        """
        if not self._pending_clarification:
            return "No pending clarification."

        # A destructive request abandons the clarification and is refused.
        if is_destructive_task_intent(user_response):
            self._pending_clarification = None
            return DESTRUCTIVE_OPERATION_REFUSAL

        clarification = self._pending_clarification
        matches = clarification["matches"]
        tool_name = clarification["tool_name"]
        original_args = json.loads(clarification["original_query"])

        # Try to resolve user's response to a specific match
        selected_task = self._resolve_clarification(user_response, matches)

        if selected_task is None:
            # If the message looks like a brand-new command, abandon the old
            # clarification and process the new request instead of trapping
            # the user in the clarification loop.
            lowered = user_response.lower()
            new_intent_markers = (
                "add ", "create ", "new task", "show ", "list ", "pending",
                "complete ", "mark ", "finish ", "when ", "details", "due ",
            )
            if any(marker in lowered for marker in new_intent_markers):
                self._pending_clarification = None
                return self.process_message(user_response)
            return (
                "I couldn't understand which task you meant. "
                "Please specify the number (e.g., '1', '2') or the full task title."
            )

        # Clear clarification state
        self._pending_clarification = None

        # Execute the original tool call with the resolved task
        if tool_name == "complete_task":
            result = self.task_service.complete_task(selected_task["title"])
        elif tool_name == "get_task_details":
            result = self.task_service.get_task_details(selected_task["title"])
        else:
            return "Clarification not supported for this operation."

        return self._format_operation_result(result)

    def _resolve_clarification(self, user_response: str, matches: List[Dict]) -> Optional[Dict]:
        """
        Resolve user's clarification response to a specific task.

        Args:
            user_response: User's response.
            matches: List of matching task dicts.

        Returns:
            Selected task dict or None if unresolved.
        """
        response_lower = user_response.lower().strip()

        # Try numeric selection
        try:
            idx = int(response_lower) - 1
            if 0 <= idx < len(matches):
                return matches[idx]
        except ValueError:
            pass

        # Try exact title match
        for match in matches:
            if match["title"].lower() == response_lower:
                return match

        # Try partial title match
        for match in matches:
            if response_lower in match["title"].lower() or match["title"].lower() in response_lower:
                return match

        # Try ordinal words
        ordinals = {"first": 0, "second": 1, "third": 2, "last": -1}
        for word, idx in ordinals.items():
            if word in response_lower:
                if 0 <= idx < len(matches) or (idx == -1 and matches):
                    return matches[idx]

        return None

    def _handle_confirmation(self, user_response: str) -> str:
        """
        Handle a yes/no answer to a pending bulk-completion confirmation.

        Tasks are completed only after an explicit affirmative answer.
        """
        pending = self._pending_confirmation
        if not pending:
            return "No bulk completion is awaiting confirmation."

        # A destructive request always cancels the pending confirmation and is
        # refused; it must never be interpreted as an affirmative answer.
        if is_destructive_task_intent(user_response):
            self._pending_confirmation = None
            return DESTRUCTIVE_OPERATION_REFUSAL

        normalized = user_response.strip().lower().strip(" .,!?:;")
        first_word = ""
        if normalized:
            first_word = re.split(r"[^a-z0-9]+", normalized)[0]

        if normalized in self._AFFIRMATIVE or first_word in self._AFFIRMATIVE:
            task_ids = list(pending.get("ids", []))
            self._pending_confirmation = None
            result = self.task_service.complete_tasks_by_ids(task_ids)
            return result.message

        if normalized in self._NEGATIVE or first_word in self._NEGATIVE:
            self._pending_confirmation = None
            return "Bulk completion cancelled. No tasks were changed."

        # Abandon the confirmation if the user starts a new command instead.
        new_intent_markers = (
            "add ", "create ", "new task", "show ", "list ", "pending",
            "schedule", "next task", "complete ", "mark ", "finish ",
            "when ", "details", "due ",
        )
        if any(marker in normalized for marker in new_intent_markers):
            self._pending_confirmation = None
            return self.process_message(user_response)

        return (
            "Please answer 'yes' to confirm the bulk completion or 'no' to cancel."
        )

    def _format_operation_result(self, result: OperationResult) -> str:
        """Format an OperationResult as a user-friendly message."""
        if result.success:
            return result.message
        else:
            return result.message

    def reset_clarification(self) -> None:
        """Reset the clarification state."""
        self._pending_clarification = None

    def reset_confirmation(self) -> None:
        """Reset any pending bulk-completion confirmation."""
        self._pending_confirmation = None

    @property
    def has_pending_clarification(self) -> bool:
        """Check if there's a pending clarification."""
        return self._pending_clarification is not None

    @property
    def has_pending_confirmation(self) -> bool:
        """Check if a bulk-completion confirmation is pending."""
        return self._pending_confirmation is not None


def create_assistant(
    task_service: Optional[TaskService] = None,
    llm_provider: Optional[str] = None,
) -> Assistant:
    """
    Factory function to create a fully configured Assistant.

    Args:
        task_service: Optional TaskService instance.
        llm_provider: Optional LLM provider override.

    Returns:
        Configured Assistant instance.
    """
    if task_service is None:
        task_service = TaskService()

    if llm_provider:
        # Temporarily override config
        original_provider = config.LLM_PROVIDER
        config.LLM_PROVIDER = llm_provider
        llm_client = create_llm_client()
        config.LLM_PROVIDER = original_provider
    else:
        llm_client = create_llm_client()

    return Assistant(task_service=task_service, llm_client=llm_client)