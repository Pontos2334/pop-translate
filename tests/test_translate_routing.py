from pop_translate.translate import (
    CODE_EXPLAIN_DETAILED_PROMPT_VERSION,
    CODE_EXPLAIN_PROMPT_VERSION,
    EXPLAIN_DETAILED_PROMPT_VERSION,
    EXPLAIN_PROMPT_VERSION,
    _english_ratio,
    _explain_prompt_and_version,
    _has_chinese,
    is_code_or_error,
    should_translate,
)


def test_has_chinese_detects_cjk():
    assert _has_chinese("hello 你好") is True
    assert _has_chinese("hello world") is False
    assert _has_chinese("") is False


def test_english_ratio_basic():
    assert _english_ratio("hello world") == 1.0
    assert _english_ratio("你好") == 0.0
    assert 0 < _english_ratio("hello 你好") < 1


def test_english_ratio_empty_does_not_divide_by_zero():
    assert _english_ratio("") == 0
    assert _english_ratio("!?,. ") == 0


def test_should_translate_routes_english_to_translate():
    assert should_translate("hello world") is True


def test_should_translate_keeps_chinese_out():
    assert should_translate("你好世界") is False


def test_should_translate_empty_string_safe():
    assert should_translate("") is False


def test_is_code_or_error_detects_python():
    assert is_code_or_error("def foo():\n    return 1") is True
    assert is_code_or_error("import os") is True


def test_is_code_or_error_detects_traceback():
    assert is_code_or_error("Traceback (most recent call last):") is True
    assert is_code_or_error("ValueError: invalid input") is True


def test_is_code_or_error_rejects_plain_text():
    assert is_code_or_error("The quick brown fox jumps over the lazy dog.") is False
    assert is_code_or_error("你好，世界") is False


def test_is_code_or_error_empty():
    assert is_code_or_error("") is False


def test_is_code_or_error_indentation_heuristic():
    indented = "\n".join(["line {}".format(i) if i % 3 == 0 else "    {}".format(i) for i in range(10)])
    assert is_code_or_error(indented) is True


def test_explain_prompt_version_non_code_default():
    _, version = _explain_prompt_and_version("Hello world", detailed=False)
    assert version == EXPLAIN_PROMPT_VERSION


def test_explain_prompt_version_non_code_detailed():
    _, version = _explain_prompt_and_version("Hello world", detailed=True)
    assert version == EXPLAIN_DETAILED_PROMPT_VERSION


def test_explain_prompt_version_code_default():
    _, version = _explain_prompt_and_version("def foo(): pass", detailed=False)
    assert version == CODE_EXPLAIN_PROMPT_VERSION


def test_explain_prompt_version_code_detailed():
    _, version = _explain_prompt_and_version("def foo(): pass", detailed=True)
    assert version == CODE_EXPLAIN_DETAILED_PROMPT_VERSION
