"""Token-usage capture for both OpenAI SDK calls and Docling VLM API calls."""

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


_usage_lock = threading.Lock()
_usage = TokenUsage()


def reset_usage() -> None:
    global _usage
    with _usage_lock:
        _usage = TokenUsage()


def get_usage() -> TokenUsage:
    return _usage


def _accumulate_from_response(response_payload: dict | None) -> None:
    """Extract token usage from an OpenAI-compatible API response and add to _usage."""
    if not response_payload:
        return
    usage = response_payload.get("usage")
    if not usage:
        return
    with _usage_lock:
        _usage.prompt_tokens += usage.get("prompt_tokens", 0) or 0
        _usage.completion_tokens += usage.get("completion_tokens", 0) or 0
        _usage.total_tokens += usage.get("total_tokens", 0) or 0
        _usage.api_calls += 1


# --- Monkey-patches -----------------------------------------------------------

_original_create: object = None  # ponytail: lazy to avoid import-time side effects
_original_api_image_request: object = None


def install_token_capture() -> None:
    """Patch OpenAI SDK and Docling VLM to capture token usage."""
    global _original_create, _original_api_image_request

    # Patch OpenAI SDK
    if _original_create is None:
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

    # Patch Docling's api_image_request (uses requests.post, not OpenAI SDK)
    if _original_api_image_request is None:
        from docling.utils.api_image_request import api_image_request as _orig

        _original_api_image_request = _orig

        def _patched_api_image_request(*args, **kwargs):
            result = _original_api_image_request(*args, **kwargs)
            # Result has .usage which is the raw usage dict from the API response
            if hasattr(result, "usage") and result.usage:
                _accumulate_from_response({"usage": result.usage})
            return result

        import docling.utils.api_image_request as _mod
        _mod.api_image_request = _patched_api_image_request


def uninstall_token_capture() -> None:
    """Restore original functions."""
    global _original_create, _original_api_image_request
    if _original_create is not None:
        from openai.resources.chat.completions import Completions
        Completions.create = _original_create
        _original_create = None
    if _original_api_image_request is not None:
        import docling.utils.api_image_request as _mod
        _mod.api_image_request = _original_api_image_request
        _original_api_image_request = None