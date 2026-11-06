import asyncio
import ipaddress
import json
import logging
import re
import socket
from dataclasses import dataclass
from urllib.parse import parse_qs, unquote, urlparse

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
MAX_BYTES = 2_000_000
MAX_TEXT = 4000

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "搜索互联网，返回若干条标题、链接和摘要。用于查询实时信息、新闻、事实。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                    "count": {
                        "type": "integer",
                        "description": "返回条数，1-8",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": "读取一个网页的正文内容。只在需要查看搜索结果详情时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "完整的 http/https 网址"}
                },
                "required": ["url"],
            },
        },
    },
]


class WebError(RuntimeError):
    pass


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str


def is_safe_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return False
    host = parsed.hostname.lower()
    if host in ("localhost",) or host.endswith(".local"):
        return False
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
        ):
            return False
    return True


def extract_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(
        ["script", "style", "noscript", "nav", "header", "footer", "aside", "form", "svg"]
    ):
        tag.decompose()
    root = soup.find("article") or soup.find("main") or soup.body or soup
    text = root.get_text("\n", strip=True)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


class WebTools:
    def __init__(
        self,
        proxy: str = "",
        max_results: int = 5,
        serper_key: str = "",
    ):
        self.proxy = proxy.strip()
        self.max_results = max_results
        self.serper_key = serper_key.strip()
        self._proxy_ok: bool | None = None
        self.calls = 0

    async def _usable_proxy(self) -> str | None:
        if not self.proxy:
            return None
        if self._proxy_ok is None:
            parsed = urlparse(self.proxy)
            host = parsed.hostname or "127.0.0.1"
            port = parsed.port or 80
            try:
                _, writer = await asyncio.wait_for(
                    asyncio.open_connection(host, port), timeout=0.8
                )
                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:
                    pass
                self._proxy_ok = True
            except Exception:
                self._proxy_ok = False
                logger.warning("代理 %s 不可用，将尝试直连", self.proxy)
        return self.proxy if self._proxy_ok else None

    async def _client(self, timeout: float = 20.0) -> httpx.AsyncClient:
        proxy = await self._usable_proxy()
        return httpx.AsyncClient(
            proxy=proxy,
            timeout=timeout,
            follow_redirects=True,
            trust_env=False,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "zh-CN,zh;q=0.9"},
        )

    async def search(self, query: str, count: int | None = None) -> list[SearchResult]:
        limit = min(max(count or self.max_results, 1), 8)
        for backend in (self._serper, self._baidu, self._bing, self._duckduckgo):
            try:
                results = await backend(query, limit)
                if results:
                    logger.info("搜索命中 %s 条（%s）", len(results), backend.__name__)
                    return results
            except Exception as exc:
                logger.warning("%s 搜索失败: %s", backend.__name__, exc)
        return []

    async def _baidu(self, query: str, limit: int) -> list[SearchResult]:
        async with await self._client() as client:
            response = await client.get(
                "https://www.baidu.com/s", params={"wd": query, "ie": "utf-8"}
            )
            response.raise_for_status()
        soup = BeautifulSoup(response.text, "lxml")
        results = []
        for block in soup.select("div.result, div.c-container"):
            link = block.select_one("h3 a")
            if not link:
                continue
            title = link.get_text(" ", strip=True)
            href = link.get("href", "")
            if not title or not href.startswith("http"):
                continue
            if "广告" in block.get_text(" ", strip=True)[:30]:
                continue
            snippet_node = (
                block.select_one('[class*="content-right"]')
                or block.select_one(".c-abstract")
                or block.select_one('[class*="abstract"]')
            )
            snippet = (
                snippet_node.get_text(" ", strip=True) if snippet_node else ""
            )
            results.append(SearchResult(title, href, snippet[:200]))
            if len(results) >= limit:
                break
        return results

    async def _serper(self, query: str, limit: int) -> list[SearchResult]:
        if not self.serper_key:
            return []
        async with await self._client() as client:
            response = await client.post(
                "https://google.serper.dev/search",
                headers={"X-API-KEY": self.serper_key},
                json={"q": query, "num": limit, "hl": "zh-cn"},
            )
            response.raise_for_status()
        return [
            SearchResult(
                item.get("title", ""),
                item.get("link", ""),
                item.get("snippet", ""),
            )
            for item in response.json().get("organic", [])[:limit]
        ]

    async def _duckduckgo(self, query: str, limit: int) -> list[SearchResult]:
        async with await self._client() as client:
            response = await client.get(
                "https://html.duckduckgo.com/html/", params={"q": query}
            )
            response.raise_for_status()
        soup = BeautifulSoup(response.text, "lxml")
        results = []
        for block in soup.select(".result")[:limit]:
            link = block.select_one(".result__a")
            snippet = block.select_one(".result__snippet")
            if not link:
                continue
            href = link.get("href", "")
            if "uddg=" in href:
                href = unquote(parse_qs(urlparse(href).query).get("uddg", [href])[0])
            results.append(
                SearchResult(
                    link.get_text(strip=True),
                    href,
                    snippet.get_text(" ", strip=True) if snippet else "",
                )
            )
        return results

    async def _bing(self, query: str, limit: int) -> list[SearchResult]:
        async with await self._client() as client:
            response = await client.get(
                "https://www.bing.com/search",
                params={"q": query, "setlang": "zh-hans"},
            )
            response.raise_for_status()
        soup = BeautifulSoup(response.text, "lxml")
        results = []
        for block in soup.select("li.b_algo")[:limit]:
            link = block.select_one("h2 a")
            caption = block.select_one(".b_caption p")
            if not link:
                continue
            results.append(
                SearchResult(
                    link.get_text(strip=True),
                    link.get("href", ""),
                    caption.get_text(" ", strip=True) if caption else "",
                )
            )
        return results

    async def fetch(self, url: str) -> str:
        if not await asyncio.to_thread(is_safe_url, url):
            raise WebError("这个网址不允许访问")
        async with await self._client(timeout=25.0) as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                content_type = response.headers.get("content-type", "")
                if "html" not in content_type and "text" not in content_type:
                    raise WebError(f"不是网页内容（{content_type}）")
                data = b""
                async for chunk in response.aiter_bytes():
                    data += chunk
                    if len(data) >= MAX_BYTES:
                        break
                encoding = response.encoding or "utf-8"
        text = extract_text(data.decode(encoding, errors="ignore"))
        if not text:
            raise WebError("网页没有可读正文")
        return text[:MAX_TEXT]

    async def execute(self, name: str, arguments: str) -> str:
        self.calls += 1
        try:
            args = json.loads(arguments or "{}")
        except json.JSONDecodeError:
            return "错误：工具参数不是合法 JSON"

        if name == "web_search":
            query = str(args.get("query", "")).strip()[:200]
            if not query:
                return "错误：缺少搜索关键词"
            try:
                results = await self.search(query, args.get("count"))
            except Exception as exc:
                return f"搜索失败：{exc}"
            if not results:
                return "没有找到相关结果。"
            return "\n\n".join(
                f"[{index}] {item.title}\n{item.url}\n{item.snippet[:200]}"
                for index, item in enumerate(results, 1)
            )

        if name == "fetch_url":
            url = str(args.get("url", "")).strip()
            if not url:
                return "错误：缺少网址"
            try:
                return await self.fetch(url)
            except Exception as exc:
                return f"抓取失败：{exc}"

        return f"错误：未知工具 {name}"
