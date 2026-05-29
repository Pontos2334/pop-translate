import re
from .api import call_api
from .history import HistoryDB


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
        flags = re.IGNORECASE if any(x in pattern.lower() for x in ("error", "traceback", "failed", "warning")) else 0
        if re.search(pattern, text, flags):
            return True
            
    # Indentation heuristic for multiline code snippets
    lines = text.split("\n")
    if len(lines) > 2:
        indent_count = sum(1 for line in lines if line.startswith("    ") or line.startswith("\t"))
        if indent_count / len(lines) > 0.4:
            return True
            
    return False


def _translate_prompt(text):
    target_lang = "English" if _has_chinese(text) else "中文"
    return (
        f"You are a professional translator. Translate the following text to {target_lang}. "
        f"Only output the translation result, nothing else. "
        f"If the text is already in {target_lang}, just return it as is. "
        f"Keep the original formatting."
    )


_EXPLAIN_PROMPT = (
    "You are a knowledgeable assistant. The user has encountered something they don't understand. "
    "Explain it briefly in 中文: only the most important points in 3-5 sentences. "
    "Use plain language suitable for a learner. Output only the explanation. "
    "You may use markdown formatting (bold, inline code) to highlight key terms."
)

_EXPLAIN_DETAILED_PROMPT = (
    "You are a knowledgeable assistant. The user has encountered something they don't understand. "
    "Explain it clearly and thoroughly in 中文: what it is, what it means, why it matters, and any relevant background. "
    "Use plain language suitable for a learner. Output only the explanation. "
    "You may use markdown formatting (headings, bold, lists, code blocks) to structure your explanation."
)

_CHAT_SYSTEM_PROMPT = (
    "你是一个翻译助手。用户选中了一段文字，可能已经有译文或解释作为上下文。"
    "请基于已提供的上下文，用中文回答用户关于这段文字的问题，例如翻译细节、语法、用法等。"
    "你可以使用 markdown 格式来组织回复。"
)


def _is_error(result):
    prefixes = ("API", "网络", "翻译超时", "API Key", "发生未知错误")
    return any(result.startswith(p) for p in prefixes)


def translate(text, config, history_db, model=None, thinking_enabled=False, use_cache=True):
    if use_cache and not model and not thinking_enabled:
        cached = history_db.lookup(text)
        if cached:
            return cached
    result = call_api(
        _translate_prompt(text),
        text,
        config,
        model=model,
        thinking_enabled=thinking_enabled,
    )
    if use_cache and not model and not thinking_enabled and not _is_error(result):
        history_db.save(text, result)
    return result


_CODE_EXPLAIN_PROMPT = (
    "You are a Senior Software Engineer. The user has provided a snippet of code or an error message. "
    "Explain it briefly in 中文 in 3-5 sentences: what it does or why the error occurred. "
    "Output only the explanation. You may use inline code formatting."
)

_CODE_EXPLAIN_DETAILED_PROMPT = (
    "You are a Senior Software Engineer. The user has provided a snippet of code or an error message. "
    "Explain it clearly in 中文:\n"
    "1. For code snippet: explain what the code does, analyze its logic, and suggest any potential optimizations.\n"
    "2. For error message: analyze why the error occurred, explain the root cause, and provide a step-by-step fix with corrected code examples.\n"
    "Use clean structure. Output only the explanation. Use markdown code blocks for code examples."
)


def explain(text, config, model=None, thinking_enabled=False, detailed=False):
    if is_code_or_error(text):
        prompt = _CODE_EXPLAIN_DETAILED_PROMPT if detailed else _CODE_EXPLAIN_PROMPT
    else:
        prompt = _EXPLAIN_DETAILED_PROMPT if detailed else _EXPLAIN_PROMPT
    return call_api(
        prompt,
        text,
        config,
        model=model,
        thinking_enabled=thinking_enabled,
    )


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
    messages = [{"role": "system", "content": _CHAT_SYSTEM_PROMPT}]
    if include_context:
        context_parts = [f"原文：{text}"]
        if translated:
            context_parts.append(f"译文：{translated}")
        if explanation:
            context_parts.append(f"解释：{explanation}")
        messages.append({"role": "user", "content": "上下文信息如下：\n" + "\n".join(context_parts)})
        messages.append({"role": "assistant", "content": "好的，我已了解这段文字的上下文，请问你有什么问题？"})
    for msg in chat_messages:
        messages.append(msg)
    messages.append({"role": "user", "content": user_input})
    return call_api(
        None,
        None,
        config,
        messages=messages,
        model=model,
        thinking_enabled=thinking_enabled,
    )
