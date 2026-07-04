"""Token-usage capture via monkey-patch of the OpenAI chat completions endpoint."""

from __future__ import annotations

import threading
from dataclasses import dataclass


@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    api_calls: int = 0

    def to_dict(self) -> dict:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "api_calls": self.api_calls,
        }

    def merge(self, other: TokenUsage) -> None:
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens
        self.total_tokens += other.total_tokens
        self.api_calls += other.api_calls


# Shared instance with lock, so ThreadPoolExecutor workers in LangExtract
# all accumulate into the same counter.
_usage_lock = threading.Lock()
_usage = TokenUsage()


def reset_usage() -> None:
    global _usage
    with _usage_lock:
        _usage = TokenUsage()


def get_usage() -> TokenUsage:
    return _usage


# --- Monkey-patch -----------------------------------------------------------

_original_create: object = None  # ponytail: set lazily to avoid import-time side effects


def install_token_capture() -> None:
    """Patch openai.resources.chat.completions.Completions.create to capture usage."""
    global _original_create
    if _original_create is not None:
        return  # already patched

    from openai.resources.chat.completions import Completions

    _original_create = Completions.create

    def _patched_create(self, *args, **kwargs):
        response = _original_create(self, *args, **kwargs)
        if hasattr(response, "usage") and response.usage is not None:
            with _usage_lock:
                _usage.prompt_tokens += getattr(response.usage, "prompt_tokens", 0) or 0
                _usage.completion_tokens += getattr(response.usage, "completion_tokens", 0) or 0
                _usage.total_tokens += getattr(response.usage, "total_tokens", 0) or 0
                _usage.api_calls += 1
        return response

    Completions.create = _patched_create


def uninstall_token_capture() -> None:
    """Restore the original create method."""
    global _original_create
    if _original_create is None:
        return
    from openai.resources.chat.completions import Completions
    Completions.create = _original_create
    _original_create = None