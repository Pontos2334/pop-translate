import base64

from pop_translate.config import Config
from pop_translate.translate import _chat_messages
from pop_translate.vision import (
    encode_image_data_url,
    vision_chat_messages,
    vision_messages,
    vision_prompt,
)


class _StubVisionConfig:
    api_url = "https://example.test/chat/completions"
    api_key = "sk-test"
    model = "stub-model"
    vision_model = "deepseek-flash"
    timeout = 60


def test_encode_image_data_url_embeds_png_bytes(tmp_path):
    png = tmp_path / "shot.png"
    raw = b"\x89PNG\r\n\x1a\nfake-image-data"
    png.write_bytes(raw)

    data_url = encode_image_data_url(str(png))

    assert data_url.startswith("data:image/png;base64,")
    encoded = data_url.split(",", 1)[1]
    assert base64.b64decode(encoded) == raw


def test_encode_image_data_url_defaults_to_png_mime(tmp_path):
    img = tmp_path / "shot.bin"
    img.write_bytes(b"not-a-known-extension")
    assert encode_image_data_url(str(img)).startswith("data:image/png;base64,")


def test_vision_messages_builds_multimodal_content():
    messages = vision_messages("data:image/png;base64,QUJD", detailed=False)

    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == vision_prompt(detailed=False)

    user = messages[1]
    assert user["role"] == "user"
    assert isinstance(user["content"], list)
    parts = {part["type"]: part for part in user["content"]}
    assert parts["text"]["text"]
    assert parts["image_url"]["image_url"]["url"] == "data:image/png;base64,QUJD"


def test_vision_prompt_detailed_differs_from_short():
    assert vision_prompt(detailed=True) != vision_prompt(detailed=False)


def test_config_vision_model_default_and_env(monkeypatch):
    config = Config()
    assert config.vision_model == "deepseek-flash"

    monkeypatch.setenv("POP_TRANSLATE_VISION_MODEL", "my-custom-vision-model")
    config = Config()
    config._apply_env()
    assert config.vision_model == "my-custom-vision-model"


def test_chat_messages_include_vision_context():
    messages = _chat_messages(
        "hello",
        "你好",
        "greeting",
        [],
        "它还有什么用法？",
        include_context=True,
        vision_result="截图中是终端报错",
    )
    context = messages[1]["content"]
    assert "识图结果：截图中是终端报错" in context
    assert messages[-1]["content"] == "它还有什么用法？"


def test_chat_messages_vision_only_context():
    messages = _chat_messages(
        "",
        "",
        "",
        [],
        "图里报错怎么修？",
        include_context=True,
        vision_result="TypeError: ...",
    )
    context = messages[1]["content"]
    assert "识图结果：TypeError: ..." in context
    assert "原文：" not in context


def test_vision_chat_messages_include_image_context():
    history = [
        {"role": "user", "content": "请分析这张截图。"},
        {"role": "assistant", "content": "图中是一只猫"},
    ]
    messages = vision_chat_messages(
        "data:image/png;base64,QUJD",
        history,
        "猫在做什么？",
        include_context=True,
    )

    assert messages[0]["role"] == "system"
    ctx = messages[1]
    assert ctx["role"] == "user"
    parts = {p["type"]: p for p in ctx["content"]}
    assert parts["image_url"]["image_url"]["url"] == "data:image/png;base64,QUJD"
    assert messages[2]["role"] == "assistant"  # 确认回复
    assert messages[3] == history[0]
    assert messages[4] == history[1]
    assert messages[-1] == {"role": "user", "content": "猫在做什么？"}


def test_vision_chat_messages_exclude_context_omits_image():
    messages = vision_chat_messages(
        "data:image/png;base64,QUJD",
        [],
        "你好",
        include_context=False,
    )
    assert len(messages) == 2  # system + user input only
    assert messages[-1]["content"] == "你好"
    for msg in messages:
        assert not isinstance(msg["content"], list)
