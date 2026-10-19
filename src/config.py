"""
Configuration module for AI-Powered Personal Task Manager.

Loads settings from environment variables with sensible defaults.
Uses python-dotenv if available, otherwise falls back to os.environ.
"""

import os
from pathlib import Path
from typing import Optional

from src.date_utils import timezone_object


def _env_int(name: str, default: int) -> int:
    """Read an integer environment variable, falling back to a default."""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    """Read a float environment variable, falling back to a default."""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def load_dotenv_if_available() -> None:
    """Load .env file if python-dotenv is installed."""
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        # python-dotenv not installed; rely on system environment
        pass


# Load .env on module import
load_dotenv_if_available()


class Config:
    """Application configuration loaded from environment variables."""

    # Database
    DATABASE_PATH: str = os.getenv("DATABASE_PATH", "./tasks.db")

    # LLM Provider (one of: "gemini", "mock")
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "mock")

    # LLM API Keys
    GOOGLE_API_KEY: Optional[str] = os.getenv("GOOGLE_API_KEY")

    # LLM Model Names
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")

    # Gemini retry behaviour for transient API errors (HTTP 429 / 503).
    # Delays follow exponential backoff: base_delay * 2**attempt.
    GEMINI_MAX_RETRIES: int = _env_int("GEMINI_MAX_RETRIES", 3)
    GEMINI_RETRY_BASE_DELAY: float = _env_float("GEMINI_RETRY_BASE_DELAY", 0.5)

    # Timezone for date interpretation
    TIMEZONE: str = os.getenv("TIMEZONE", "UTC")

    # Application
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    @classmethod
    def validate(cls) -> None:
        """Validate configuration and raise if critical settings are missing."""
        if cls.LLM_PROVIDER not in ("gemini", "mock"):
            raise ValueError(
                f"Invalid LLM_PROVIDER: {cls.LLM_PROVIDER}. "
                "Must be one of: gemini, mock"
            )

        if cls.LLM_PROVIDER == "gemini" and not cls.GOOGLE_API_KEY:
            raise ValueError("GOOGLE_API_KEY required when LLM_PROVIDER=gemini")

        # Fail fast on an unusable timezone instead of silently assuming UTC.
        timezone_object(cls.TIMEZONE)

        if cls.GEMINI_MAX_RETRIES < 0:
            raise ValueError("GEMINI_MAX_RETRIES must be zero or greater")
        if cls.GEMINI_RETRY_BASE_DELAY < 0:
            raise ValueError("GEMINI_RETRY_BASE_DELAY must be zero or greater")

    @classmethod
    def get_db_path(cls) -> Path:
        """Return database path as a Path object."""
        return Path(cls.DATABASE_PATH).expanduser().resolve()


# Global config instance
config = Config()