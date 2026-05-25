from .api import call_api
from .history import HistoryDB


def _has_chinese(text):
    return any("\u4e00" <= c <= "\u9fff" for c in text)


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
