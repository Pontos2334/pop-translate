import json
import urllib.error
from io import BytesIO

from pop_translate.api import (
    _build_payload,
    _classify_error,
    _is_timeout_error,
    _sanitize_error,
    _stream_delta,
)
from pop_translate.i18n import ERROR_API, ERROR_API_KEY, ERROR_NETWORK, ERROR_TIMEOUT, ERROR_UNKNOWN


class _StubConfig:
    api_url = "https://example.test/v1/chat/completions"
    api_key = "sk-test"
    model = "stub-model"
    timeout = 60


def _http_error(code):
    return urllib.error.HTTPError(
        url="https://example.test",
        code=code,
        msg="error",
        hdrs=None,
        fp=BytesIO(b"{}"),
    )


def test_classify_error_unauthorized_maps_to_api_key():
    msg, retryable = _classify_error(_http_error(401))
    assert msg == ERROR_API_KEY
    assert retryable is False


def test_classify_error_forbidden_maps_to_api_key():
    msg, retryable = _classify_error(_http_error(403))
    assert msg == ERROR_API_KEY
    assert retryable is False


def test_classify_error_server_error_is_retryable():
    msg, retryable = _classify_error(_http_error(503))
    assert msg == ERROR_API.format(503)
    assert retryable is True


def test_classify_error_client_error_is_not_retryable():
    msg, retryable = _classify_error(_http_error(404))
    assert msg == ERROR_API.format(404)
    assert retryable is False


def test_classify_error_timeout_is_retryable():
    msg, retryable = _classify_error(TimeoutError("timed out"))
    assert msg == ERROR_TIMEOUT
    assert retryable is True


def test_classify_error_url_timeout_reason():
    err = urllib.error.URLError(reason=TimeoutError("operation timed out"))
    msg, retryable = _classify_error(err)
    assert msg == ERROR_TIMEOUT
    assert retryable is True


def test_classify_error_generic_network_is_retryable():
    err = urllib.error.URLError(reason="connection refused")
    msg, retryable = _classify_error(err)
    assert msg == ERROR_NETWORK
    assert retryable is True


def test_classify_error_unknown_falls_back():
    msg, retryable = _classify_error(RuntimeError("boom"))
    assert msg == ERROR_UNKNOWN
    assert retryable is False


def test_is_timeout_error_native():
    assert _is_timeout_error(TimeoutError()) is True


def test_is_timeout_error_url_with_timeout_reason():
    err = urllib.error.URLError(reason=TimeoutError())
    assert _is_timeout_error(err) is True


def test_is_timeout_error_url_with_string_reason():
    err = urllib.error.URLError(reason="operation timed out")
    assert _is_timeout_error(err) is True


def test_is_timeout_error_other_error():
    assert _is_timeout_error(ValueError("nope")) is False


def test_sanitize_error_redacts_bearer_token():
    raw = "Authorization: Bearer sk-abcdef123456"
    sanitized = _sanitize_error(raw)
    assert "abcdef123456" not in sanitized
    assert "sk-" in sanitized or "已隐藏" in sanitized


def test_sanitize_error_redacts_api_key_assignment():
    raw = "api_key=sk-abcdef123456 header"
    sanitized = _sanitize_error(raw)
    assert "abcdef123456" not in sanitized


def test_stream_delta_done_marker():
    _, _, _, done = _stream_delta("data: [DONE]")
    assert done is True


def test_stream_delta_content_chunk():
    line = 'data: {"choices":[{"delta":{"content":"hi"}}]}'
    content, reasoning, usage, done = _stream_delta(line)
    assert content == "hi"
    assert reasoning is None
    assert usage is None
    assert done is False


def test_stream_delta_reasoning_chunk():
    line = 'data: {"choices":[{"delta":{"reasoning_content":"thinking"}}]}'
    content, reasoning, usage, done = _stream_delta(line)
    assert content is None
    assert reasoning == "thinking"


def test_stream_delta_usage_only_chunk():
    line = 'data: {"usage":{"total_tokens":42}}'
    content, reasoning, usage, done = _stream_delta(line)
    assert content is None
    assert reasoning is None
    assert isinstance(usage, dict)
    assert usage["total_tokens"] == 42


def test_stream_delta_ignores_non_data_lines():
    assert _stream_delta(": keepalive") == (None, None, None, False)
    assert _stream_delta("event: ping") == (None, None, None, False)


def test_stream_delta_handles_malformed_json():
    content, reasoning, usage, done = _stream_delta("data: {not json")
    assert (content, reasoning, usage, done) == (None, None, None, False)


def test_build_payload_basic_request_shape():
    payload = _build_payload("sys", "user", _StubConfig())
    assert payload["model"] == "stub-model"
    assert payload["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "user"},
    ]
    assert payload["temperature"] == 0.3
    assert "stream" not in payload
    assert "thinking" not in payload


def test_build_payload_with_stream_and_usage():
    payload = _build_payload(
        "sys", "user", _StubConfig(), stream=True, include_usage=True
    )
    assert payload["stream"] is True
    assert payload["stream_options"] == {"include_usage": True}


def test_build_payload_with_thinking_enabled():
    payload = _build_payload(
        "sys", "user", _StubConfig(), thinking_enabled=True
    )
    assert payload["thinking"] == {"type": "enabled"}


def test_build_payload_uses_explicit_messages():
    messages = [{"role": "user", "content": "hi"}]
    payload = _build_payload(None, None, _StubConfig(), messages=messages)
    assert payload["messages"] == messages


def test_build_payload_model_override():
    payload = _build_payload("sys", "user", _StubConfig(), model="other-model")
    assert payload["model"] == "other-model"
