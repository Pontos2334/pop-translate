import json
import re
import time
import urllib.error
import urllib.request

from .i18n import ERROR_API, ERROR_API_KEY, ERROR_NETWORK, ERROR_TIMEOUT, ERROR_UNKNOWN

MAX_RETRIES = 2
MAX_TIMEOUT_RETRIES = 1


def _sanitize_error(error):
    msg = str(error)
    msg = re.sub(r"[Aa]uthorization.?\s*[Bb]earer\s+\S+", "[已隐藏]", msg)
    msg = re.sub(r"(api[_-]?key\s*[:=]\s*)\S+", r"\1***", msg, flags=re.IGNORECASE)
    msg = re.sub(r"(sk-)[a-zA-Z0-9]{4}[a-zA-Z0-9]*", r"\1****", msg)
    return msg


def _is_timeout_error(error):
    if isinstance(error, TimeoutError):
        return True
    if isinstance(error, urllib.error.URLError):
        reason = getattr(error, "reason", None)
        return isinstance(reason, TimeoutError) or "timed out" in str(reason).lower()
    return "timed out" in str(error).lower()


def _classify_error(error):
    if isinstance(error, urllib.error.HTTPError):
        code = error.code
        if code == 401 or code == 403:
            return ERROR_API_KEY, False
        if 500 <= code < 600:
            return ERROR_API.format(code), True
        return ERROR_API.format(code), False
    if _is_timeout_error(error):
        return ERROR_TIMEOUT, True
    if isinstance(error, (urllib.error.URLError, OSError)):
        return ERROR_NETWORK, True
    return ERROR_UNKNOWN, False


def _build_payload(system_prompt, user_text, config, messages=None, model=None, thinking_enabled=False, stream=False):
    if messages is not None:
        payload_messages = messages
    else:
        payload_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ]

    payload = {
        "model": model or config.model,
        "messages": payload_messages,
        "temperature": 0.3,
        "max_tokens": 2048,
    }
    if thinking_enabled:
        payload["thinking"] = {"type": "enabled"}
    if stream:
        payload["stream"] = True
    return payload


def _build_request(payload, config):
    data = json.dumps(payload).encode("utf-8")
    return urllib.request.Request(
        config.api_url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.api_key}",
        },
    )


def _stream_delta(line):
    if not line.startswith("data:"):
        return None, False

    data = line[5:].strip()
    if not data:
        return None, False
    if data == "[DONE]":
        return None, True

    try:
        chunk = json.loads(data)
        choice = chunk["choices"][0]
    except (json.JSONDecodeError, KeyError, TypeError, IndexError):
        return None, False

    delta = choice.get("delta") or {}
    content = delta.get("content")
    if content is None:
        return None, False
    return content, False


def call_api(
    system_prompt,
    user_text,
    config,
    messages=None,
    model=None,
    thinking_enabled=False,
    timeout=None,
):
    req = _build_request(
        _build_payload(system_prompt, user_text, config, messages, model, thinking_enabled),
        config,
    )

    for attempt in range(MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout or config.timeout) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                try:
                    return result["choices"][0]["message"]["content"].strip()
                except (KeyError, TypeError, IndexError):
                    return ERROR_UNKNOWN
        except Exception as e:
            msg, retryable = _classify_error(e)
            max_retries = MAX_TIMEOUT_RETRIES if _is_timeout_error(e) else MAX_RETRIES
            if not retryable or attempt == max_retries:
                return _sanitize_error(msg) if retryable else msg
            time.sleep(2 ** attempt)

    return ERROR_UNKNOWN


def stream_api(
    system_prompt,
    user_text,
    config,
    messages=None,
    model=None,
    thinking_enabled=False,
    timeout=None,
    cancel_event=None,
):
    req = _build_request(
        _build_payload(system_prompt, user_text, config, messages, model, thinking_enabled, stream=True),
        config,
    )
    yielded_any = False

    for attempt in range(MAX_RETRIES + 1):
        if cancel_event is not None and cancel_event.is_set():
            return
        try:
            with urllib.request.urlopen(req, timeout=timeout or config.timeout) as resp:
                for raw_line in resp:
                    if cancel_event is not None and cancel_event.is_set():
                        return
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    delta, done = _stream_delta(line)
                    if done:
                        return
                    if delta:
                        yielded_any = True
                        yield delta
                return
        except Exception as e:
            msg, retryable = _classify_error(e)
            max_retries = MAX_TIMEOUT_RETRIES if _is_timeout_error(e) else MAX_RETRIES
            if yielded_any or not retryable or attempt == max_retries:
                yield _sanitize_error(msg) if retryable else msg
                return
            if cancel_event is not None and cancel_event.is_set():
                return
            time.sleep(2 ** attempt)

    yield ERROR_UNKNOWN
