import base64
import io
import json
import logging
from pathlib import Path

import httpx
from PIL import Image

logger = logging.getLogger(__name__)

VISION_CONFIG = Path(r"C:\Users\30540\vision-mcp\Vision-MCP\config.json")
DEFAULT_PROMPT = "用 1-3 句话描述这张图片：主体、画面里的文字、情绪或梗。只描述，不评价。"


class VisionError(RuntimeError):
    pass


class VisionClient:
    def __init__(
        self,
        api_key: str = "",
        api_base: str = "",
        model: str = "",
        max_bytes: int = 10 * 1024 * 1024,
    ):
        config = self._load_config()
        self.api_key = api_key or str(config.get("vision_api_key", ""))
        self.api_base = (
            api_base or str(config.get("vision_api_base", "https://api.deepseek.com"))
        ).rstrip("/")
        self.model = model or str(
            config.get("vision_model", "deepseek-v4-flash-vision-exp")
        )
        self.max_bytes = max_bytes

    @staticmethod
    def _load_config() -> dict:
        if not VISION_CONFIG.exists():
            return {}
        try:
            data = json.loads(VISION_CONFIG.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _prepare(self, data: bytes) -> bytes:
        if len(data) > self.max_bytes:
            raise VisionError(f"图片太大（{len(data) // 1024} KB）")
        try:
            with Image.open(io.BytesIO(data)) as image:
                image.seek(0)
                if image.mode in ("RGBA", "LA", "P"):
                    background = Image.new("RGB", image.size, "white")
                    background.paste(image.convert("RGBA"), mask=image.convert("RGBA"))
                    image = background
                else:
                    image = image.convert("RGB")
                image.thumbnail((1280, 1280))
                buffer = io.BytesIO()
                image.save(buffer, format="JPEG", quality=85)
                return buffer.getvalue()
        except VisionError:
            raise
        except Exception as exc:
            raise VisionError(f"图片无法解析: {exc}") from exc

    async def describe(self, data: bytes, prompt: str = DEFAULT_PROMPT) -> str:
        if not self.api_key:
            raise VisionError("视觉模型 API Key 未配置")
        prepared = self._prepare(data)
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": "data:image/jpeg;base64,"
                                + base64.b64encode(prepared).decode()
                            },
                        },
                    ],
                }
            ],
            "temperature": 0.2,
            "stream": False,
        }
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(90.0, connect=15.0), trust_env=False
            ) as client:
                response = await client.post(
                    f"{self.api_base}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=payload,
                )
        except httpx.HTTPError as exc:
            raise VisionError(f"请求失败: {exc}") from exc

        if response.status_code != 200:
            raise VisionError(
                f"HTTP {response.status_code}: {response.text[:200]}"
            )
        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as exc:
            raise VisionError("响应结构异常") from exc
        text = (content or "").strip()
        if not text:
            raise VisionError("模型没有返回描述")
        return text
