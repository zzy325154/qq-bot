import asyncio
import json
import sys
import tempfile
from pathlib import Path

import websockets

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot import BotApp, HELP_TEXT
from config import Config

OWNER = 10001


async def mock_onebot(ws, replies: asyncio.Queue, received: asyncio.Event):
    await asyncio.sleep(0.2)
    await ws.send(json.dumps({
        "post_type": "message",
        "message_type": "private",
        "sub_type": "friend",
        "message_id": 1,
        "user_id": OWNER,
        "message": [{"type": "text", "data": {"text": "/help"}}],
    }))
    async for raw in ws:
        data = json.loads(raw)
        if data.get("action") == "send_private_msg":
            await replies.put(data["params"])
            await ws.send(json.dumps({"status": "ok", "retcode": 0, "data": {}, "echo": data.get("echo")}))
            received.set()


async def run() -> int:
    replies: asyncio.Queue = asyncio.Queue()
    received = asyncio.Event()

    server = await websockets.serve(
        lambda ws: mock_onebot(ws, replies, received), "127.0.0.1", 0
    )
    port = server.sockets[0].getsockname()[1]

    with tempfile.TemporaryDirectory() as tmp:
        cfg = Config()
        cfg.owner_qq = OWNER
        cfg.api_key = "sk-test"
        cfg.onebot_ws = f"ws://127.0.0.1:{port}"
        cfg.data_dir = Path(tmp)
        cfg.archive_enabled = False

        app = BotApp(cfg)
        await app.start()
        client_task = asyncio.create_task(app.client.run())
        try:
            await asyncio.wait_for(received.wait(), timeout=10)
            params = await replies.get()
            text = params.get("message", "")
            if isinstance(text, list):
                text = " | ".join(
                    seg.get("data", {}).get("text", "") if isinstance(seg, dict) else str(seg)
                    for seg in text
                )
            await asyncio.sleep(0.5)
            pending = len(app.client._pending)
            ok = (
                params.get("user_id") == OWNER
                and "可用指令" in text
                and pending == 0
            )
            if pending:
                print(f"告警：仍有 {pending} 个请求在等待回执（读取循环可能被阻塞）")
            print("收到回复：" + text.replace("\n", " | "))
            print("端到端测试：" + ("通过" if ok else "失败"))
            return 0 if ok else 1
        finally:
            await app.shutdown()
            server.close()
            await server.wait_closed()
            client_task.cancel()
            await asyncio.gather(client_task, return_exceptions=True)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
