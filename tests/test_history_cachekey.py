from pop_translate.history import HistoryDB


def _make_db():
    db = HistoryDB.__new__(HistoryDB)
    return db


def test_cache_key_is_stable():
    db = _make_db()
    key1 = db._cache_key("hello", "model-a", "v1")
    key2 = db._cache_key("hello", "model-a", "v1")
    assert key1 == key2
    assert len(key1) == 64


def test_cache_key_differs_by_model():
    db = _make_db()
    key_a = db._cache_key("hello", "model-a", "v1")
    key_b = db._cache_key("hello", "model-b", "v1")
    assert key_a != key_b


def test_cache_key_differs_by_prompt_version():
    db = _make_db()
    key_v1 = db._cache_key("hello", "model-a", "v1")
    key_v2 = db._cache_key("hello", "model-a", "v2")
    assert key_v1 != key_v2


def test_cache_key_differs_by_source_text():
    db = _make_db()
    key_a = db._cache_key("hello", "model-a", "v1")
    key_b = db._cache_key("world", "model-a", "v1")
    assert key_a != key_b


def test_cache_key_treats_none_and_empty_consistently():
    db = _make_db()
    assert db._cache_key("text", None, None) == db._cache_key("text", "", "legacy")


def test_cache_key_handles_empty_source():
    db = _make_db()
    key = db._cache_key("", "model", "v1")
    assert len(key) == 64
