import asyncio
import logging
import os
import random
import subprocess
import time
from pathlib import Path

import edge_tts
import httpx

logger = logging.getLogger(__name__)

CURATED_VOICES = [
    ("zh-CN-XiaoyiNeural", "晓伊", "活泼年轻女声，适合她的人设"),
    ("zh-CN-XiaoxiaoNeural", "晓晓", "自然温柔女声，最常用"),
    ("zh-CN-XiaobeiNeural", "晓北", "东北口音女声，有烟火气"),
    ("zh-CN-XiaoniNeural", "晓妮", "中原口音女声，接地气"),
    ("zh-CN-liaoning-XiaobeiNeural", "晓北(辽宁)", "东北话"),
    ("zh-CN-XiaohanNeural", "晓涵", "成熟女声"),
    ("zh-CN-XiaomoNeural", "晓墨", "沉稳女声"),
    ("zh-CN-XiaoxuanNeural", "晓萱", "知性女声"),
    ("zh-CN-XiaoruiNeural", "晓睿", "温柔女声"),
    ("zh-CN-XiaoshuangNeural", "晓双", "童声女声"),
    ("zh-CN-XiaoyanNeural", "晓颜", "亲和女声"),
    ("zh-CN-YunxiNeural", "云希", "年轻男声"),
    ("zh-CN-YunjianNeural", "云健", "浑厚男声"),
]


class TTSError(RuntimeError):
    pass


def pick_voice_style(
    mood_level: int, stage: int, rng=random.random
) -> tuple[str, float]:
    """CosyVoice2 的 instruct2 在这套参考音上只改语速、情绪几乎不变，
    所以先只用零样本合成，配一点点语速抖动，保持第 1 条那种自然度。"""
    return "", 0.97 + rng() * 0.06


class TTSClient:
    def __init__(
        self,
        voice: str = "zh-CN-XiaoyiNeural",
        rate: str = "+0%",
        pitch: str = "+0Hz",
        volume: str = "+0%",
        max_chars: int = 120,
        out_dir: Path | None = None,
        backend: str = "edge",
        cosyvoice_url: str = "http://127.0.0.1:50001",
        autostart: bool = False,
        cosyvoice_dir: Path | None = None,
        cosyvoice_python: str = "",
        idle_seconds: int = 900,
        start_timeout: float = 120.0,
    ):
        self.voice = voice
        self.rate = rate
        self.pitch = pitch
        self.volume = volume
        self.max_chars = max_chars
        self.backend = backend
        self.cosyvoice_url = cosyvoice_url.rstrip("/")
        self.autostart = autostart
        self.cosyvoice_dir = Path(cosyvoice_dir) if cosyvoice_dir else None
        self.cosyvoice_python = cosyvoice_python
        self.idle_seconds = idle_seconds
        self.start_timeout = start_timeout
        self.out_dir = Path(out_dir) if out_dir else Path("data/tts")
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self._proc: subprocess.Popen | None = None
        self._start_lock = asyncio.Lock()
        self._voices_cache: list[tuple[str, str, str]] | None = None
        self._cleanup()

    def _cleanup(self) -> None:
        files = sorted(self.out_dir.glob("*.mp3"), key=lambda p: p.stat().st_mtime)
        for old in files[:-20]:
            try:
                old.unlink()
            except OSError:
                pass

    async def synthesize(self, text: str, instruct: str = "", speed: float = 1.0) -> Path:
        text = text.strip()[: self.max_chars]
        if not text:
            raise TTSError("没有可朗读的文字")
        if self.backend == "cosyvoice":
            return await self._synthesize_cosyvoice(text, instruct, speed)
        return await self._synthesize_edge(text)

    async def _synthesize_edge(self, text: str) -> Path:
        target = self.out_dir / f"{int(time.time() * 1000)}.mp3"
        try:
            communicate = edge_tts.Communicate(
                text,
                self.voice,
                rate=self.rate,
                pitch=self.pitch,
                volume=self.volume,
            )
            await communicate.save(str(target))
        except Exception as exc:
            raise TTSError(f"语音合成失败: {exc}") from exc
        if not target.exists() or target.stat().st_size < 1000:
            raise TTSError("语音文件异常")
        return target

    async def _probe(self, timeout: float = 1.5) -> bool:
        try:
            async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
                response = await client.get(f"{self.cosyvoice_url}/health")
            return response.status_code == 200
        except Exception:
            return False

    def _spawn_command(self) -> list[str] | None:
        if self.cosyvoice_dir is None:
            return None
        server = self.cosyvoice_dir / "server.py"
        if not server.exists():
            return None
        if self.cosyvoice_python:
            python = Path(self.cosyvoice_python)
        else:
            python = self.cosyvoice_dir / ".venv" / "Scripts" / "python.exe"
            if not python.exists():
                python = self.cosyvoice_dir / ".venv" / "bin" / "python"
        if not python.exists():
            return None
        return [str(python), str(server)]

    def _spawn(self, command: list[str]) -> None:
        log_path = self.out_dir / "cosyvoice-server.log"
        try:
            if log_path.exists() and log_path.stat().st_size > 2 * 1024 * 1024:
                log_path.unlink()
        except OSError:
            pass
        env = os.environ.copy()
        env["COSYVOICE_IDLE_SECONDS"] = str(max(0, self.idle_seconds))
        env["PYTHONUNBUFFERED"] = "1"
        env.setdefault("PYTHONIOENCODING", "utf-8")
        flags = 0
        if os.name == "nt":
            flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
        log = open(log_path, "ab", buffering=0)
        self._proc = subprocess.Popen(
            command,
            cwd=str(self.cosyvoice_dir),
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=flags,
            close_fds=True,
        )
        logger.info("已拉起 CosyVoice（pid=%s，闲置 %ss 退出）", self._proc.pid, self.idle_seconds)

    async def ensure_service(self) -> None:
        if await self._probe():
            return
        if not self.autostart:
            raise TTSError("CosyVoice 服务没启动（COSYVOICE_AUTOSTART=0）")
        async with self._start_lock:
            if await self._probe():
                return
            command = self._spawn_command()
            if command is None:
                raise TTSError("找不到 CosyVoice 的 server.py 或 Python，检查 COSYVOICE_DIR")
            await asyncio.to_thread(self._spawn, command)
            deadline = time.monotonic() + self.start_timeout
            while time.monotonic() < deadline:
                await asyncio.sleep(1.0)
                if await self._probe():
                    logger.info("CosyVoice 就绪")
                    return
                if self._proc is not None and self._proc.poll() is not None:
                    raise TTSError(
                        f"CosyVoice 启动失败（退出码 {self._proc.returncode}），"
                        f"日志见 {self.out_dir / 'cosyvoice-server.log'}"
                    )
            raise TTSError("CosyVoice 启动超时")

    async def _synthesize_cosyvoice(
        self, text: str, instruct: str = "", speed: float = 1.0
    ) -> Path:
        target = self.out_dir / f"{int(time.time() * 1000)}.wav"
        await self.ensure_service()
        payload = {"text": text, "speaker": self.voice, "speed": speed}
        if instruct:
            payload["instruct"] = instruct
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(180.0, connect=10.0), trust_env=False
            ) as client:
                response = await client.post(
                    f"{self.cosyvoice_url}/tts",
                    json=payload,
                )
        except httpx.HTTPError as exc:
            raise TTSError(f"CosyVoice 请求失败: {exc}") from exc
        if response.status_code != 200:
            raise TTSError(
                f"CosyVoice HTTP {response.status_code}: {response.text[:200]}"
            )
        target.write_bytes(response.content)
        if target.stat().st_size < 1000:
            raise TTSError("CosyVoice 返回的音频异常")
        return target

    async def list_voices(self) -> list[tuple[str, str, str]]:
        if self.backend != "cosyvoice":
            return CURATED_VOICES
        if self._voices_cache is not None:
            return self._voices_cache
        try:
            await self.ensure_service()
            async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
                response = await client.get(f"{self.cosyvoice_url}/speakers")
                response.raise_for_status()
            self._voices_cache = [
                (item["id"], item.get("label", item["id"]), "")
                for item in response.json()
            ]
            return self._voices_cache
        except Exception as exc:
            logger.warning("读取 CosyVoice 音色失败: %s", exc)
            return []
