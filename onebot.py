import asyncio
import base64
import json
import logging
import uuid
from pathlib import Path
from typing import Any, Awaitable, Callable

import websockets
from websockets.exceptions import ConnectionClosed

logger = logging.getLogger(__name__)


class OneBotError(RuntimeError):
    pass


class NotConnected(OneBotError):
    pass


class OneBotClient:
    """OneBot 11 的 WebSocket 客户端：收事件、调 API。"""

    def __init__(self, ws_url: str, token: str = ""):
        self.ws_url = ws_url
        self.token = token
        self._ws: Any = None
        self._pending: dict[str, asyncio.Future] = {}
        self._stop = False
        self._on_event: Callable[[dict], Awaitable[None]] | None = None
        self._connected = asyncio.Event()

    @property
    def connected(self) -> bool:
        return self._connected.is_set()

    def on_event(self, handler: Callable[[dict], Awaitable[None]]) -> None:
        self._on_event = handler

    async def run(self) -> None:
        backoff = 1.0
        while not self._stop:
            headers = {"Authorization": f"Bearer {self.token}"} if self.token else None
            try:
                async with websockets.connect(
                    self.ws_url,
                    additional_headers=headers,
                    ping_interval=30,
                    ping_timeout=20,
                    max_size=8 * 1024 * 1024,
                ) as ws:
                    self._ws = ws
                    self._connected.set()
                    backoff = 1.0
                    logger.info("已连接 OneBot: %s", self.ws_url)
                    await self._read_loop(ws)
            except asyncio.CancelledError:
                raise
            except ConnectionClosed as exc:
                logger.warning("连接已关闭: %s", exc)
            except OSError as exc:
                logger.warning("连接失败: %s", exc)
            except Exception as exc:  # 鉴权失败、协议异常等
                logger.warning("连接异常: %s: %s", type(exc).__name__, exc)
            finally:
                self._connected.clear()
                self._ws = None
                self._fail_pending("连接已断开")
            if self._stop:
                break
            logger.info("%.0f 秒后重连", backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30.0)

    async def _read_loop(self, ws: Any) -> None:
        async for raw in ws:
            try:
                data = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                logger.debug("忽略非 JSON 帧: %r", raw[:200])
                continue

            echo = data.get("echo")
            if echo is not None and echo in self._pending:
                future = self._pending.pop(echo)
                if not future.done():
                    future.set_result(data)
                continue

            if data.get("post_type") and self._on_event is not None:
                task = asyncio.create_task(self._on_event(data))
                task.add_done_callback(self._log_event_error)

    def _log_event_error(self, task: asyncio.Task) -> None:
        if task.cancelled():
            return
        error = task.exception()
        if error is not None:
            logger.error("处理事件失败: %s: %s", type(error).__name__, error)

    def _fail_pending(self, reason: str) -> None:
        for future in self._pending.values():
            if not future.done():
                future.set_exception(NotConnected(reason))
        self._pending.clear()

    async def call(self, action: str, params: dict[str, Any], timeout: float = 30.0) -> dict:
        if self._ws is None:
            raise NotConnected("尚未连接 OneBot")
        echo = uuid.uuid4().hex
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[echo] = future
        try:
            await self._ws.send(json.dumps({"action": action, "params": params, "echo": echo}))
            resp = await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending.pop(echo, None)
            raise OneBotError(f"{action} 超时（{timeout}s）") from None
        finally:
            self._pending.pop(echo, None)

        if resp.get("retcode") not in (0, None):
            raise OneBotError(
                f"{action} 失败 retcode={resp.get('retcode')}: {resp.get('message') or resp.get('wording')}"
            )
        return resp.get("data") or {}

    async def friend_history(self, user_id: int, count: int = 30) -> list[dict]:
        data = await self.call(
            "get_friend_msg_history",
            {"user_id": user_id, "count": count},
            timeout=30.0,
        )
        return data.get("messages", []) if isinstance(data, dict) else []

    async def send_private(
        self, user_id: int, text: str, reply_to: int | None = None
    ) -> int | None:
        message = []
        if reply_to:
            message.append({"type": "reply", "data": {"id": str(reply_to)}})
        message.append({"type": "text", "data": {"text": text}})
        data = await self.call("send_private_msg", {"user_id": user_id, "message": message})
        message_id = data.get("message_id") if isinstance(data, dict) else None
        return message_id if isinstance(message_id, int) else None

    async def delete_msg(self, message_id: int) -> None:
        await self.call("delete_msg", {"message_id": message_id}, timeout=30.0)

    async def set_typing(self, user_id: int, typing: bool = True) -> None:
        await self.call(
            "set_input_status",
            {"user_id": user_id, "event_type": 1 if typing else 2},
            timeout=10.0,
        )

    async def send_private_image(self, user_id: int, path: Path) -> None:
        path = Path(path).resolve()
        try:
            await self.call(
                "send_private_msg",
                {
                    "user_id": user_id,
                    "message": [{"type": "image", "data": {"file": path.as_uri()}}],
                },
                timeout=60.0,
            )
        except OneBotError:
            payload = base64.b64encode(path.read_bytes()).decode()
            await self.call(
                "send_private_msg",
                {
                    "user_id": user_id,
                    "message": [
                        {"type": "image", "data": {"file": f"base64://{payload}"}}
                    ],
                },
                timeout=60.0,
            )

    async def set_avatar(self, path: Path) -> None:
        path = Path(path).resolve()
        try:
            await self.call("set_qq_avatar", {"file": path.as_uri()}, timeout=60.0)
        except OneBotError:
            payload = base64.b64encode(path.read_bytes()).decode()
            await self.call(
                "set_qq_avatar", {"file": f"base64://{payload}"}, timeout=60.0
            )

    async def send_private_record(self, user_id: int, path: Path) -> None:
        path = Path(path).resolve()
        try:
            await self.call(
                "send_private_msg",
                {
                    "user_id": user_id,
                    "message": [{"type": "record", "data": {"file": path.as_uri()}}],
                },
                timeout=60.0,
            )
        except OneBotError:
            payload = base64.b64encode(path.read_bytes()).decode()
            await self.call(
                "send_private_msg",
                {
                    "user_id": user_id,
                    "message": [
                        {"type": "record", "data": {"file": f"base64://{payload}"}}
                    ],
                },
                timeout=60.0,
            )

    async def stop(self) -> None:
        self._stop = True
        if self._ws is not None:
            await self._ws.close()
