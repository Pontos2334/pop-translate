import json
import re
import time
import urllib.error
import urllib.request
from typing import Generator, Dict, Any

from .i18n import ERROR_API, ERROR_API_KEY, ERROR_NETWORK, ERROR_TIMEOUT, ERROR_UNKNOWN
from .sse_parser import SSEParser

MAX_RETRIES = 2


def _sanitize_error(error):
    msg = str(error)
    msg = re.sub(r"[Aa]uthorization.?\s*[Bb]earer\s+\S+", "[已隐藏]", msg)
    msg = re.sub(r"(api[_-]?key\s*[:=]\s*)\S+", r"\1***", msg, flags=re.IGNORECASE)
    msg = re.sub(r"(sk-)[a-zA-Z0-9]{4}[a-zA-Z0-9]*", r"\1****", msg)
    return msg


def _classify_error(error):
    if isinstance(error, urllib.error.HTTPError):
        code = error.code
        if code == 401 or code == 403:
            return ERROR_API_KEY, False
        if 500 <= code < 600:
            return ERROR_API.format(code), True
        return ERROR_API.format(code), False
    if isinstance(error, (TimeoutError,)):
        return ERROR_TIMEOUT, True
    if isinstance(error, (urllib.error.URLError, OSError)):
        return ERROR_NETWORK, True
    return ERROR_UNKNOWN, False


def call_api(system_prompt, user_text, config, messages=None, model=None, thinking_enabled=False):
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
        "thinking": {"type": "enabled" if thinking_enabled else "disabled"},
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        config.api_url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.api_key}",
        },
    )

    last_error = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=config.timeout) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                return result["choices"][0]["message"]["content"].strip()
        except Exception as e:
            last_error = e
            msg, retryable = _classify_error(e)
            if not retryable or attempt == MAX_RETRIES:
                return _sanitize_error(msg) if retryable else msg
            time.sleep(2 ** attempt)

    return ERROR_UNKNOWN


def call_api_stream(system_prompt, user_text, config, messages=None, model=None, thinking_enabled=False) -> Generator[Dict[str, Any], None, None]:
    """流式调用 API，返回增量内容的生成器。

    Args:
        system_prompt: 系统提示词
        user_text: 用户输入文本
        config: 配置对象
        messages: 自定义消息列表（可选）
        model: 模型名称（可选）
        thinking_enabled: 是否启用思考模式

    Yields:
        字典包含:
        - content: 增量内容
        - thinking: 增量思考内容
        - done: 是否完成
    """
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
        "thinking": {"type": "enabled" if thinking_enabled else "disabled"},
        "stream": True,
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        config.api_url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.api_key}",
        },
    )

    last_error = None
    for attempt in range(MAX_RETRIES + 1):
        resp = None
        try:
            resp = urllib.request.urlopen(req, timeout=config.timeout)
            parser = SSEParser()
            yield from parser.parse_stream(resp)
            return
        except Exception as e:
            last_error = e
            msg, retryable = _classify_error(e)
            if not retryable or attempt == MAX_RETRIES:
                error_msg = _sanitize_error(msg) if retryable else msg
                yield {"content": error_msg, "thinking": "", "done": True}
                return
            time.sleep(2 ** attempt)
        finally:
            if resp is not None:
                try:
                    resp.close()
                except Exception:
                    pass

    yield {"content": ERROR_UNKNOWN, "thinking": "", "done": True}
