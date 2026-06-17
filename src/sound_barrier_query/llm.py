from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from .config import LLMConfig

logger = logging.getLogger("sound_barrier_query.llm")


class LLMError(RuntimeError):
    """调用大模型接口失败。"""


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str


# 调用者必须返回形如 (status, headers_dict, body_bytes) 的三元组，
# 或者直接抛出 urllib.error.HTTPError/URLError 等异常。
HTTPPoster = Callable[[str, Mapping[str, str], bytes], tuple[int, dict[str, str], bytes]]


def chat_completions(
    config: LLMConfig,
    messages: Iterable[ChatMessage],
    *,
    timeout: float = 60.0,
    poster: HTTPPoster | None = None,
) -> str:
    if not config.is_complete():
        raise LLMError("AI接口未配置完整，请检查 .env 中 BASE_URL/API_KEY/MODEL。")

    payload = {
        "model": config.model,
        "messages": [
            {"role": message.role, "content": message.content}
            for message in messages
        ],
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    url = _join_chat_url(config.base_url)
    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
    }

    if poster is None:
        poster = _default_poster(timeout)

    logger.debug("LLM request: url=%s model=%s msgs=%d", url, config.model, len(messages))
    try:
        status, _, raw = poster(url, headers, body)
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="ignore")
        raise LLMError(f"AI助手返回错误：HTTP {error.code} {detail}".strip()) from error
    except urllib.error.URLError as error:
        raise LLMError(f"AI助手暂时无法回答，请稍后重试：{error.reason}") from error

    if status >= 400:
        raise LLMError(f"AI助手返回错误：HTTP {status} {raw.decode('utf-8', errors='ignore')}".strip())
    return _extract_content(raw)


def _default_poster(timeout: float) -> HTTPPoster:
    def poster(url: str, headers: Mapping[str, str], body: bytes) -> tuple[int, dict[str, str], bytes]:
        request = urllib.request.Request(url, data=body, headers=dict(headers), method="POST")
        with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec - URL from .env
            return response.status, dict(response.headers), response.read()

    return poster


def _join_chat_url(base_url: str) -> str:
    trimmed = base_url.rstrip("/")
    if trimmed.endswith("/chat/completions"):
        return trimmed
    return f"{trimmed}/chat/completions"


def _extract_content(body: bytes) -> str:
    text = body.decode("utf-8", errors="ignore")
    try:
        data: Any = json.loads(text)
    except json.JSONDecodeError as error:
        raise LLMError(f"AI助手返回结果无法解析：{error.msg}") from error
    try:
        return str(data["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError) as error:
        raise LLMError("AI助手返回结果缺少 choices[0].message.content。") from error
