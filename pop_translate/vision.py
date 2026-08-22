"""AI 识图：把截图发给视觉模型（OpenAI 兼容 image_url 格式）并流式返回分析。"""
import base64
import mimetypes
import os
import threading
from typing import Iterator, Optional, Union

from .api import StreamEvent, stream_api
from .config import Config

StreamChunk = Union[str, StreamEvent]

VISION_PROMPT_VERSION = "vision:v1"
VISION_DETAILED_PROMPT_VERSION = "vision-detailed:v1"

_VISION_PROMPT = (
    "你是一名高效的桌面助手。用户提供了一张屏幕截图。请用中文分析它：\n"
    "1. 如果截图包含文字，先准确转录其中的文字并保留原有排版；外文内容请附上中文翻译。\n"
    "2. 如果是代码或报错信息，解释它在做什么或错误为什么发生，并给出简要修复建议。\n"
    "3. 如果是图表、界面或其他内容，简要说明它展示的信息。\n"
    "只输出与截图相关的内容，使用 markdown 组织，尽量精炼。"
)

_VISION_DETAILED_PROMPT = (
    "你是一名高效且细致的桌面助手。用户提供了一张屏幕截图。请用中文详细分析它：\n"
    "1. 完整转录截图中的所有文字并保留排版结构，外文内容附上中文翻译。\n"
    "2. 逐项解释截图内容：界面元素、数据、图表含义或代码逻辑。\n"
    "3. 如果有报错或异常，分析根因并给出分步骤修复建议。\n"
    "使用 markdown（标题、列表、代码块）组织内容。"
)

_VISION_CHAT_SYSTEM_PROMPT = (
    "你是一个桌面截图助手。用户截取了一张屏幕截图，围绕它与你对话。"
    "请基于截图和已有对话历史，用中文回答用户的追问，"
    "例如图中细节、文字含义、代码或报错的进一步解释、翻译等。"
    "你可以使用 markdown 格式来组织回复。"
)


def encode_image_data_url(path: str) -> str:
    mime, _ = mimetypes.guess_type(path)
    if mime not in ("image/png", "image/jpeg", "image/gif", "image/webp"):
        mime = "image/png"
    with open(path, "rb") as f:
        data = base64.b64encode(f.read()).decode("ascii")
    return f"data:{mime};base64,{data}"


def vision_prompt(detailed: bool = False) -> str:
    return _VISION_DETAILED_PROMPT if detailed else _VISION_PROMPT


def vision_messages(image_data_url: str, detailed: bool = False) -> list[dict]:
    return [
        {"role": "system", "content": vision_prompt(detailed)},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "请分析这张截图。"},
                {"type": "image_url", "image_url": {"url": image_data_url}},
            ],
        },
    ]


def vision_stream(
    image_path: str,
    config: Config,
    model: Optional[str] = None,
    detailed: bool = False,
    cancel_event: Optional[threading.Event] = None,
) -> Iterator[StreamChunk]:
    if cancel_event is not None and cancel_event.is_set():
        return
    if not image_path or not os.path.exists(image_path):
        yield "未找到截图文件，请重新截图"
        return
    messages = vision_messages(encode_image_data_url(image_path), detailed=detailed)
    timeout = max(config.timeout, 240 if detailed else 120)
    yield from stream_api(
        None,
        None,
        config,
        messages=messages,
        model=model or config.vision_model,
        thinking_enabled=False,
        timeout=timeout,
        cancel_event=cancel_event,
    )


def vision_chat_messages(
    image_data_url: Optional[str],
    chat_messages: list[dict],
    user_input: str,
    include_context: bool = True,
) -> list[dict]:
    messages: list[dict] = [
        {"role": "system", "content": _VISION_CHAT_SYSTEM_PROMPT}
    ]
    if include_context and image_data_url:
        messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "以下是用户截取的屏幕截图，后续对话都围绕它进行：",
                    },
                    {"type": "image_url", "image_url": {"url": image_data_url}},
                ],
            }
        )
        messages.append(
            {"role": "assistant", "content": "好的，我已看到这张截图，请问有什么问题？"}
        )
    for msg in chat_messages:
        messages.append(msg)
    messages.append({"role": "user", "content": user_input})
    return messages


def vision_chat_stream(
    image_path: str,
    chat_messages: list[dict],
    user_input: str,
    config: Config,
    model: Optional[str] = None,
    include_context: bool = True,
    cancel_event: Optional[threading.Event] = None,
) -> Iterator[StreamChunk]:
    if cancel_event is not None and cancel_event.is_set():
        return
    if not image_path or not os.path.exists(image_path):
        yield "未找到截图文件，请重新截图"
        return
    image_data_url = encode_image_data_url(image_path) if include_context else None
    messages = vision_chat_messages(
        image_data_url, chat_messages, user_input, include_context=include_context
    )
    yield from stream_api(
        None,
        None,
        config,
        messages=messages,
        model=model or config.vision_model,
        thinking_enabled=False,
        timeout=max(config.timeout, 120),
        cancel_event=cancel_event,
    )
