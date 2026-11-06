import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    pass


class LLMClient:
    def __init__(self, api_key: str, api_base: str, model: str):
        self.api_key = api_key
        self.api_base = api_base.rstrip("/")
        self.model = model
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(90.0, connect=15.0))

    async def chat_message(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
    ) -> dict[str, Any]:
        if not self.api_key:
            raise LLMError("DEEPSEEK_API_KEY 为空")
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        try:
            resp = await self._client.post(
                f"{self.api_base}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
            )
        except httpx.HTTPError as exc:
            raise LLMError(f"请求失败: {exc}") from exc

        if resp.status_code != 200:
            body = resp.text[:300].replace("\n", " ")
            raise LLMError(f"HTTP {resp.status_code}: {body}")

        try:
            data = resp.json()
            return data["choices"][0]["message"]
        except (KeyError, IndexError, ValueError) as exc:
            raise LLMError(f"响应结构异常: {resp.text[:300]}") from exc

    async def chat(self, messages: list[dict[str, str]], temperature: float = 0.7) -> str:
        message = await self.chat_message(messages, temperature=temperature)
        text = (message.get("content") or "").strip()
        if not text:
            raise LLMError("模型返回了空内容")
        return text

    async def aclose(self) -> None:
        await self._client.aclose()
