import io
import logging
from pathlib import Path

import httpx
from PIL import Image

logger = logging.getLogger(__name__)

IMAGE_API = "https://image.baidu.com/search/acjson"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}


def parse_image_urls(payload: dict, limit: int = 20) -> list[str]:
    urls = []
    for item in payload.get("data", []):
        if not isinstance(item, dict):
            continue
        url = item.get("middleURL") or item.get("thumbURL") or item.get("hoverURL")
        if url and url.startswith("http"):
            urls.append(url)
        if len(urls) >= limit:
            break
    return urls


async def search_image_urls(query: str, limit: int = 20) -> list[str]:
    params = {
        "tn": "resultjson_com",
        "ipn": "rj",
        "word": query,
        "pn": 0,
        "rn": max(limit, 10),
    }
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(20.0, connect=10.0), trust_env=False, headers=HEADERS
    ) as client:
        response = await client.get(IMAGE_API, params=params)
        response.raise_for_status()
        payload = response.json()
    return parse_image_urls(payload, limit)


async def download(url: str, timeout: float = 20.0) -> bytes:
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(timeout, connect=10.0), trust_env=False, headers=HEADERS
    ) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.content


def save_square(content: bytes, out_path: Path, size: int = 640) -> Path:
    image = Image.open(io.BytesIO(content)).convert("RGB")
    width, height = image.size
    if width < 160 or height < 160:
        raise ValueError(f"图片太小：{width}x{height}")
    side = min(width, height)
    left = (width - side) // 2
    top = (height - side) // 2
    image = image.crop((left, top, left + side, top + side))
    image = image.resize((size, size), Image.LANCZOS)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(out_path, "JPEG", quality=90)
    return out_path


async def fetch_avatar(query: str, out_path: Path, tries: int = 6) -> Path:
    urls = await search_image_urls(query, limit=20)
    if not urls:
        raise ValueError("没搜到图片")
    for url in urls[:tries]:
        try:
            content = await download(url)
            return save_square(content, out_path)
        except Exception as exc:
            logger.warning("头像候选下载失败（%s）：%s", url[:60], exc)
    raise ValueError("候选图片都下载失败")
