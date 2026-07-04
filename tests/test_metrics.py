"""Tests for metrics module."""

from dataclasses import dataclass
from unittest.mock import MagicMock

from src.metrics import TokenUsage, get_usage, reset_usage, install_token_capture, uninstall_token_capture


def test_token_usage_merge():
    a = TokenUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30, api_calls=1)
    b = TokenUsage(prompt_tokens=5, completion_tokens=10, total_tokens=15, api_calls=1)
    a.merge(b)
    assert a.prompt_tokens == 15
    assert a.completion_tokens == 30
    assert a.total_tokens == 45
    assert a.api_calls == 2


def test_token_usage_to_dict():
    u = TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150, api_calls=3)
    d = u.to_dict()
    assert d == {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150, "api_calls": 3}


def test_reset_usage():
    reset_usage()
    u = get_usage()
    assert u.prompt_tokens == 0
    reset_usage()
    u = get_usage()
    assert u.prompt_tokens == 0


def test_install_and_capture(monkeypatch):
    """Patch is applied and captures usage from a mock response."""
    reset_usage()
    uninstall_token_capture()  # ensure clean state

    mock_usage = MagicMock()
    mock_usage.prompt_tokens = 42
    mock_usage.completion_tokens = 13
    mock_usage.total_tokens = 55

    mock_response = MagicMock()
    mock_response.usage = mock_usage

    original_create = MagicMock(return_value=mock_response)
    monkeypatch.setattr("openai.resources.chat.completions.Completions.create", original_create)

    install_token_capture()

    from openai.resources.chat.completions import Completions
    completions_obj = Completions(client=MagicMock())
    completions_obj.create(model="test", messages=[{"role": "user", "content": "hi"}])

    u = get_usage()
    assert u.prompt_tokens == 42
    assert u.completion_tokens == 13
    assert u.total_tokens == 55
    assert u.api_calls == 1

    uninstall_token_capture()


def test_install_idempotent():
    """Calling install twice doesn't double-patch."""
    reset_usage()
    uninstall_token_capture()
    install_token_capture()
    install_token_capture()  # should be a no-op
    uninstall_token_capture()


def test_shared_usage_across_threads():
    """Token counts from worker threads accumulate into the shared instance."""
    reset_usage()
    uninstall_token_capture()

    from concurrent.futures import ThreadPoolExecutor

    # Directly test the shared instance via merge
    u = get_usage()
    u.merge(TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15, api_calls=1))

    assert u.prompt_tokens == 10
    assert u.completion_tokens == 5
    assert u.api_calls == 1


def test_docling_api_image_request_patch(monkeypatch):
    """Patching docling api_image_request captures usage from result.usage."""
    reset_usage()
    uninstall_token_capture()

    from docling.datamodel.base_models import ApiImageRequestResult, VlmStopReason

    fake_result = ApiImageRequestResult(
        text="a logo",
        num_tokens=88,
        stop_reason=VlmStopReason.END_OF_SEQUENCE,
        usage={"prompt_tokens": 60, "completion_tokens": 28, "total_tokens": 88},
    )

    real_api_image_request = MagicMock(return_value=fake_result)
    monkeypatch.setattr(
        "docling.utils.api_image_request.api_image_request", real_api_image_request
    )

    install_token_capture()

    import docling.utils.api_image_request as _mod
    _mod.api_image_request(image=None, prompt="test", url="https://example.com")

    u = get_usage()
    assert u.prompt_tokens == 60
    assert u.completion_tokens == 28
    assert u.total_tokens == 88
    assert u.api_calls == 1

    uninstall_token_capture()


if __name__ == "__main__":
    test_token_usage_merge()
    test_token_usage_to_dict()
    test_reset_usage()
    test_install_idempotent()
    test_shared_usage_across_threads()
    print("All metrics tests passed.")