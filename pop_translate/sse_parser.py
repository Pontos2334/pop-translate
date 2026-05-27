"""SSE (Server-Sent Events) 解析器，用于解析 OpenAI 兼容的流式响应。"""

import json
from typing import Generator, Dict, Any, Optional


class SSEParser:
    """解析 OpenAI SSE 格式的流式响应。

    SSE 格式示例:
    data: {"id":"...","object":"chat.completion.chunk","choices":[{"delta":{"content":"Hello"}}]}

    data: [DONE]
    """

    def __init__(self):
        self._buffer = ""

    def parse_line(self, line: str) -> Optional[Dict[str, Any]]:
        """解析单行 SSE 数据。

        Args:
            line: SSE 格式的单行数据

        Returns:
            解析结果字典:
            - content: 增量内容
            - thinking: 增量思考内容
            - done: 是否完成
            返回 None 表示需要更多数据
        """
        line = line.strip()

        # 跳过空行
        if not line:
            return None

        # 检查是否是结束标记
        if line == "data: [DONE]":
            return {"content": "", "thinking": "", "done": True}

        # 检查是否是数据行
        if not line.startswith("data: "):
            return None

        # 提取 JSON 数据
        json_str = line[6:]  # 去掉 "data: " 前缀

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            return None

        # 提取增量内容
        result = {"content": "", "thinking": "", "done": False}

        choices = data.get("choices", [])
        if not choices:
            return result

        delta = choices[0].get("delta", {})

        # 提取普通内容
        if "content" in delta:
            result["content"] = delta["content"] or ""

        # 提取思考内容 (DeepSeek 等模型)
        if "reasoning_content" in delta:
            result["thinking"] = delta["reasoning_content"] or ""

        # 检查是否完成
        finish_reason = choices[0].get("finish_reason")
        if finish_reason:
            result["done"] = True

        return result

    def parse_stream(self, response_stream) -> Generator[Dict[str, Any], None, None]:
        """解析流式响应。

        Args:
            response_stream: HTTP 响应流

        Yields:
            解析后的增量数据
        """
        for line in response_stream:
            line = line.decode("utf-8", errors="replace").strip()

            # 跳过空行和注释
            if not line or line.startswith(":"):
                continue

            result = self.parse_line(line)
            if result is not None:
                yield result

                # 如果完成，停止解析
                if result.get("done"):
                    break
