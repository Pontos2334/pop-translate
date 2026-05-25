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


def _translate_prompt(text):
    target_lang = "English" if _has_chinese(text) else "中文"
    return (
        f"You are a professional translator. Translate the following text to {target_lang}. "
        f"Only output the translation result, nothing else. "
        f"If the text is already in {target_lang}, just return it as is. "
        f"Keep the original formatting. Do NOT use markdown formatting."
    )


_EXPLAIN_PROMPT = (
    "You are a knowledgeable assistant. The user has encountered something they don't understand. "
    "Explain it clearly in 中文: what it is, what it means, why it matters, and any relevant background. "
    "Use plain language suitable for a learner. Output only the explanation. Do NOT use markdown formatting."
)

_CHAT_SYSTEM_PROMPT = (
    "你是一个翻译助手。用户选中了一段文字并已获得翻译结果。"
    "请用中文回答用户关于这段文字的问题，例如翻译细节、语法、用法等。"
    "不要使用 markdown 格式。"
)


def _is_error(result):
    prefixes = ("API", "网络", "翻译超时", "API Key", "发生未知错误")
    return any(result.startswith(p) for p in prefixes)


def translate(text, config, history_db):
    cached = history_db.lookup(text)
    if cached:
        return cached
    result = call_api(_translate_prompt(text), text, config)
    if not _is_error(result):
        history_db.save(text, result)
    return result


def explain(text, config):
    return call_api(_EXPLAIN_PROMPT, text, config)


def chat(text, translated, explanation, chat_messages, user_input, config):
    messages = [{"role": "system", "content": _CHAT_SYSTEM_PROMPT}]
    context_parts = [f"原文：{text}"]
    if translated:
        context_parts.append(f"译文：{translated}")
    if explanation:
        context_parts.append(f"解释：{explanation}")
    messages.append({"role": "user", "content": "上下文信息如下：\n" + "\n".join(context_parts)})
    messages.append({"role": "assistant", "content": "好的，我已了解这段文字的翻译和解释，请问你有什么问题？"})
    for msg in chat_messages:
        messages.append(msg)
    messages.append({"role": "user", "content": user_input})
    return call_api(None, None, config, messages=messages)
