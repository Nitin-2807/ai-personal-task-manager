"""
Interactive terminal REPL for the AI-Powered Personal Task Manager.

Run from the project root with:

    .venv/bin/python -m src.cli

The CLI intentionally refuses to start unless the configured provider is
``gemini``.  It never falls back to the offline mock provider.
"""

from __future__ import annotations

import sys
from typing import Optional

from src.assistant import Assistant, create_assistant
from src.config import config
from src.response_formatter import format_goodbye, format_welcome
from src.task_service import TaskService


def _redact(text: object) -> str:
    """Remove the configured API key from text before displaying it."""
    value = str(text)
    if config.GOOGLE_API_KEY:
        value = value.replace(config.GOOGLE_API_KEY, "[REDACTED]")
    return value


def _start_assistant() -> Optional[Assistant]:
    """Validate configuration and construct the real Gemini assistant."""
    if config.LLM_PROVIDER != "gemini":
        print(
            "Refusing to start: LLM_PROVIDER must be 'gemini'. "
            f"Current value: {config.LLM_PROVIDER!r}. "
            "Mock mode is never used implicitly.",
            file=sys.stderr,
        )
        return None

    try:
        config.validate()
    except ValueError as exc:
        print(f"Configuration error: {_redact(exc)}", file=sys.stderr)
        return None

    try:
        task_service = TaskService(config.get_db_path())
        return create_assistant(task_service=task_service)
    except Exception as exc:  # startup failure, not a per-message failure
        print(f"Unable to start assistant: {_redact(exc)}", file=sys.stderr)
        return None


def main() -> int:
    """Run the interactive assistant until the user exits."""
    assistant = _start_assistant()
    if assistant is None:
        return 2

    print(f"Provider: {config.LLM_PROVIDER}")
    print(f"Model: {assistant.llm_client.get_model_name()}")
    print(f"Database: {config.get_db_path()}")
    print()
    print(format_welcome())
    print("Type 'exit' or 'quit' to leave.")

    while True:
        try:
            message = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{format_goodbye()}")
            return 0

        if not message:
            continue
        if message.lower() in {"exit", "quit"}:
            print(format_goodbye())
            return 0
        if message.lower() in {"help", "/help"}:
            print(format_welcome())
            continue

        try:
            response = assistant.process_message(message)
        except Exception as exc:  # defensive: never expose the API key
            response = f"Unexpected error: {_redact(exc)}"

        print(f"\nAssistant: {response}")


if __name__ == "__main__":
    raise SystemExit(main())
