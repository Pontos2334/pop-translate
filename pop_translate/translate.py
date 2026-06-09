import re
from .api import StreamEvent, call_api, stream_api

TRANSLATE_PROMPT_VERSION = "translate:v2"
EXPLAIN_PROMPT_VERSION = "explain:v2"
EXPLAIN_DETAILED_PROMPT_VERSION = "explain-detailed:v2"
CODE_EXPLAIN_PROMPT_VERSION = "code-explain:v2"
CODE_EXPLAIN_DETAILED_PROMPT_VERSION = "code-explain-detailed:v2"


def _has_chinese(text):
    return any("\u4e00" <= c <= "\u9fff" for c in text)


def _english_ratio(text):
    ascii_letters = sum(1 for c in text if c.isascii() and c.isalpha())
    total = sum(1 for c in text if c.isalpha())
    return ascii_letters / total if total > 0 else 0


def should_translate(text):
    return _english_ratio(text) > 0.5


_CODE_PATTERNS = [
    r"\bdef\s+\w+\b",
    r"\bclass\s+\w+\b",
    r"\bimport\s+\w+\b",
    r"\bfrom\s+\w+\s+import\b",
    r"\bpublic\s+static\s+void\b",
    r"\bconst\s+\w+\s*=",
    r"\blet\s+\w+\s*=",
    r"\bvar\s+\w+\s*=",
    r"\bstruct\s+\w+\b",
    r"\bfn\s+\w+\b",
    r"#include\s+<\w+>",
    r"\busing\s+namespace\s+\w+",
    r"\bconsole\.log\b",
    r"\bprint\s*\(",
    r"\bprintf\s*\(",
    r"^[ \t]*{",
    r"^[ \t]*}",
    r"\bSyntaxError\b",
    r"\bTypeError\b",
    r"\bValueError\b",
    r"\bIndexError\b",
    r"\bKeyError\b",
    r"\bAttributeError\b",
    r"\bException\b",
    r"\bTraceback\s*\(most\s+recent\s+call\s+last\)",
    r"\bNullPointerException\b",
    r"\bWarning\b",
    r"failed\s+to\s+load",
    r"\bCRITICAL\b",
    r"\bFATAL\b",
]


def is_code_or_error(text):
    if not text:
        return False
    for pattern in _CODE_PATTERNS:
        # Ignore case for error/warning/traceback/failed related queries
        flags = (
            re.IGNORECASE
            if any(
                x in pattern.lower()
                for x in ("error", "traceback", "failed", "warning")
            )
            else 0
        )
        if re.search(pattern, text, flags):
            return True

    # Indentation heuristic for multiline code snippets
    lines = text.split("\n")
    if len(lines) > 2:
        indent_count = sum(
            1 for line in lines if line.startswith("    ") or line.startswith("\t")
        )
        if indent_count / len(lines) > 0.4:
            return True

    return False


def _translate_prompt(text):
    target_lang = "英文" if _has_chinese(text) else "中文"
    return (
        f"你是一名专业翻译。请将用户提供的文本翻译成{target_lang}。"
        f"只输出翻译结果，不要输出解释或其他内容。"
        f"如果文本已经是{target_lang}，请原样返回。"
        f"保留原始格式。"
    )


_EXPLAIN_PROMPT = (
    "你是一名知识丰富的助理。用户遇到了一段不理解的内容。"
    "请用中文简要解释：只说明最重要的要点。"
    "使用适合学习者的通俗语言。只输出解释本身。"
    "可以使用 markdown 格式（加粗、行内代码）突出关键词。"
)

_EXPLAIN_DETAILED_PROMPT = (
    "你是一名知识丰富的助理。用户遇到了一段不理解的内容。"
    "请用中文清晰、详细地解释：它是什么、是什么意思、为什么重要，以及相关背景。"
    "使用适合学习者的通俗语言。只输出解释本身。"
    "可以使用 markdown 格式（标题、加粗、列表、代码块）组织内容。"
)

_CHAT_SYSTEM_PROMPT = (
    "你是一个翻译助手。用户选中了一段文字，可能已经有译文或解释作为上下文。"
    "请基于已提供的上下文，用中文回答用户关于这段文字的问题，例如翻译细节、语法、用法等。"
    "你可以使用 markdown 格式来组织回复。"
)


def _is_error(result):
    prefixes = ("API", "网络", "翻译超时", "API Key", "发生未知错误")
    return any(result.startswith(p) for p in prefixes)


def _request_timeout(
    config, thinking_enabled=False, detailed=False, chat_request=False
):
    timeout = config.timeout
    if chat_request:
        return max(timeout, 240 if thinking_enabled else 90)
    if thinking_enabled or detailed:
        return max(timeout, 240 if thinking_enabled else 90)
    return timeout


def translate(
    text, config, history_db, model=None, thinking_enabled=False, use_cache=True
):
    cache_model = model or config.model
    if use_cache and not thinking_enabled:
        cached = history_db.lookup(
            text, model=cache_model, prompt_version=TRANSLATE_PROMPT_VERSION
        )
        if cached:
            return cached
    result = call_api(
        _translate_prompt(text),
        text,
        config,
        model=model,
        thinking_enabled=thinking_enabled,
        timeout=_request_timeout(config, thinking_enabled=thinking_enabled),
    )
    if use_cache and not thinking_enabled and not _is_error(result):
        history_db.save(
            text, result, model=cache_model, prompt_version=TRANSLATE_PROMPT_VERSION
        )
    return result


def translate_stream(
    text,
    config,
    history_db,
    model=None,
    thinking_enabled=False,
    use_cache=True,
    cancel_event=None,
):
    cache_model = model or config.model
    if cancel_event is not None and cancel_event.is_set():
        return
    if use_cache and not thinking_enabled:
        cached = history_db.lookup(
            text, model=cache_model, prompt_version=TRANSLATE_PROMPT_VERSION
        )
        if cached:
            yield StreamEvent("cached")
            yield cached
            return

    chunks = []
    has_error = False
    for chunk in stream_api(
        _translate_prompt(text),
        text,
        config,
        model=model,
        thinking_enabled=thinking_enabled,
        timeout=_request_timeout(config, thinking_enabled=thinking_enabled),
        cancel_event=cancel_event,
    ):
        if cancel_event is not None and cancel_event.is_set():
            return
        if isinstance(chunk, StreamEvent):
            if chunk.kind == "usage":
                yield chunk
            continue
        if _is_error(chunk):
            has_error = True
        chunks.append(chunk)
        yield chunk

    result = "".join(chunks).strip()
    if (
        use_cache
        and not thinking_enabled
        and result
        and not has_error
        and not _is_error(result)
    ):
        history_db.save(
            text, result, model=cache_model, prompt_version=TRANSLATE_PROMPT_VERSION
        )


_CODE_EXPLAIN_PROMPT = (
    "你是一名资深软件工程师。用户提供了一段代码或错误信息。"
    "请用中文在 3-5 句话内简要解释：这段代码做了什么，或这个错误为什么发生。"
    "只输出解释本身。可以使用行内代码格式。"
)

_CODE_EXPLAIN_DETAILED_PROMPT = (
    "你是一名资深软件工程师。用户提供了一段代码或错误信息。"
    "请用中文清晰解释：\n"
    "1. 如果是代码片段：说明代码做了什么，分析它的逻辑，并指出可能的优化点。\n"
    "2. 如果是错误信息：分析错误为什么发生，解释根因，并给出分步骤修复方法和修正后的代码示例。\n"
    "使用清晰的结构。只输出解释本身。代码示例请使用 markdown 代码块。"
)


def _explain_prompt_and_version(text, detailed=False):
    is_code = is_code_or_error(text)
    if is_code:
        prompt = _CODE_EXPLAIN_DETAILED_PROMPT if detailed else _CODE_EXPLAIN_PROMPT
        prompt_version = (
            CODE_EXPLAIN_DETAILED_PROMPT_VERSION
            if detailed
            else CODE_EXPLAIN_PROMPT_VERSION
        )
    else:
        prompt = _EXPLAIN_DETAILED_PROMPT if detailed else _EXPLAIN_PROMPT
        prompt_version = (
            EXPLAIN_DETAILED_PROMPT_VERSION if detailed else EXPLAIN_PROMPT_VERSION
        )
    return prompt, prompt_version


def explain(
    text,
    config,
    history_db=None,
    model=None,
    thinking_enabled=False,
    detailed=False,
    use_cache=True,
):
    cache_model = model or config.model
    prompt, prompt_version = _explain_prompt_and_version(text, detailed=detailed)
    if history_db is not None and use_cache and not thinking_enabled:
        cached = history_db.lookup(
            text, model=cache_model, prompt_version=prompt_version
        )
        if cached:
            return cached
    return call_api(
        prompt,
        text,
        config,
        model=model,
        thinking_enabled=thinking_enabled,
        timeout=_request_timeout(
            config, thinking_enabled=thinking_enabled, detailed=detailed
        ),
    )


def explain_stream(
    text,
    config,
    history_db=None,
    model=None,
    thinking_enabled=False,
    detailed=False,
    use_cache=True,
    cancel_event=None,
):
    cache_model = model or config.model
    if cancel_event is not None and cancel_event.is_set():
        return
    prompt, prompt_version = _explain_prompt_and_version(text, detailed=detailed)
    if history_db is not None and use_cache and not thinking_enabled:
        cached = history_db.lookup(
            text, model=cache_model, prompt_version=prompt_version
        )
        if cached:
            yield StreamEvent("cached")
            yield cached
            return

    chunks = []
    has_error = False
    for chunk in stream_api(
        prompt,
        text,
        config,
        model=model,
        thinking_enabled=thinking_enabled,
        timeout=_request_timeout(
            config, thinking_enabled=thinking_enabled, detailed=detailed
        ),
        cancel_event=cancel_event,
    ):
        if cancel_event is not None and cancel_event.is_set():
            return
        if isinstance(chunk, StreamEvent):
            if chunk.kind == "usage":
                yield chunk
            elif thinking_enabled:
                yield chunk
            continue
        if _is_error(chunk):
            has_error = True
        chunks.append(chunk)
        yield chunk

    result = "".join(chunks).strip()
    if (
        history_db is not None
        and use_cache
        and not thinking_enabled
        and result
        and not has_error
        and not _is_error(result)
    ):
        history_db.save(text, result, model=cache_model, prompt_version=prompt_version)


def _chat_messages(
    text, translated, explanation, chat_messages, user_input, include_context=True
):
    messages = [{"role": "system", "content": _CHAT_SYSTEM_PROMPT}]
    if include_context:
        context_parts = [f"原文：{text}"]
        if translated:
            context_parts.append(f"译文：{translated}")
        if explanation:
            context_parts.append(f"解释：{explanation}")
        messages.append(
            {"role": "user", "content": "上下文信息如下：\n" + "\n".join(context_parts)}
        )
        messages.append(
            {
                "role": "assistant",
                "content": "好的，我已了解这段文字的上下文，请问你有什么问题？",
            }
        )
    for msg in chat_messages:
        messages.append(msg)
    messages.append({"role": "user", "content": user_input})
    return messages


def chat(
    text,
    translated,
    explanation,
    chat_messages,
    user_input,
    config,
    model=None,
    thinking_enabled=False,
    include_context=True,
):
    return call_api(
        None,
        None,
        config,
        messages=_chat_messages(
            text, translated, explanation, chat_messages, user_input, include_context
        ),
        model=model,
        thinking_enabled=thinking_enabled,
        timeout=_request_timeout(
            config, thinking_enabled=thinking_enabled, chat_request=True
        ),
    )


def chat_stream(
    text,
    translated,
    explanation,
    chat_messages,
    user_input,
    config,
    model=None,
    thinking_enabled=False,
    include_context=True,
    cancel_event=None,
):
    if cancel_event is not None and cancel_event.is_set():
        return
    yield from stream_api(
        None,
        None,
        config,
        messages=_chat_messages(
            text, translated, explanation, chat_messages, user_input, include_context
        ),
        model=model,
        thinking_enabled=thinking_enabled,
        timeout=_request_timeout(
            config, thinking_enabled=thinking_enabled, chat_request=True
        ),
        cancel_event=cancel_event,
    )
