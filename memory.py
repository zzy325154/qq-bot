import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

MAX_CHARS = 6000

TIME_HINT = (
    "最近聊天记录每条前面的方括号是当时的时间（月-日 时:分）。"
    "里面的「今天」「明天」「后天」都是那会儿说的相对时间，不是说现在，"
    "已经过去的事不要当成今天的安排，也不要再拿昨天说过的话当新消息。"
    "这些方括号只是给你看时间的标记，你回复的时候绝对不要写时间，也不要照抄这种格式。"
)

STAMP_RE = re.compile(r"(?m)^\s*\[\d{1,2}-\d{1,2}\s+\d{1,2}:\d{2}\]\s*")


def strip_stamp(text: str) -> str:
    return STAMP_RE.sub("", text or "").strip()


def _stamp(entry: dict) -> str:
    raw = str(entry.get("ts", "") or "")
    try:
        return datetime.fromisoformat(raw).strftime("%m-%d %H:%M")
    except ValueError:
        return ""


def annotate(entry: dict) -> str:
    content = str(entry.get("content", ""))
    stamp = _stamp(entry)
    return f"[{stamp}] {content}" if stamp else content


class ChatMemory:
    """按 QQ 号保存的多轮对话历史，落盘为 JSON。"""

    def __init__(self, path: Path, max_turns: int = 12):
        self.path = Path(path)
        self.max_turns = max_turns
        self._data: dict[str, list[dict[str, str]]] = {}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                self._data = {
                    str(k): v for k, v in raw.items() if isinstance(v, list)
                }
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("读取记忆文件失败，已从空记忆开始: %s", exc)
            self._data = {}

    def _save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        try:
            tmp.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(tmp, self.path)
        except OSError as exc:
            logger.error("保存记忆失败: %s", exc)

    def history(self, user_id: int) -> list[dict[str, str]]:
        return list(self._data.get(str(user_id), []))

    def append(self, user_id: int, role: str, content: str, ts: str = "") -> None:
        key = str(user_id)
        turns = self._data.setdefault(key, [])
        turns.append(
            {
                "role": role,
                "content": content,
                "ts": ts or datetime.now().astimezone().isoformat(timespec="seconds"),
            }
        )
        self._trim(turns)
        self._save()

    def _trim(self, turns: list[dict[str, str]]) -> None:
        limit = self.max_turns * 2
        if len(turns) > limit:
            del turns[: len(turns) - limit]
        while turns and sum(len(t["content"]) for t in turns) > MAX_CHARS:
            turns.pop(0)
            if turns and turns[0]["role"] == "assistant":
                turns.pop(0)

    def clear(self, user_id: int) -> None:
        self._data.pop(str(user_id), None)
        self._save()

    def drop_trailing(self, user_id: int, role: str) -> int:
        turns = self._data.get(str(user_id), [])
        count = 0
        while turns and turns[-1]["role"] == role:
            turns.pop()
            count += 1
        if count:
            self._save()
        return count

    def build_messages(
        self, user_id: int, system_prompt: str, user_text: str
    ) -> list[dict[str, str]]:
        history = self.history(user_id)
        messages = [{"role": "system", "content": system_prompt}]
        if any(entry.get("ts") for entry in history):
            messages.append({"role": "system", "content": TIME_HINT})
        messages.extend(
            {"role": entry["role"], "content": annotate(entry)} for entry in history
        )
        messages.append({"role": "user", "content": user_text})
        return messages
