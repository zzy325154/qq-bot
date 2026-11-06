import json
import logging
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Awaitable, Callable
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

TZ = ZoneInfo("Asia/Shanghai")
REMIND_RE = re.compile(r"^(\d{1,2}):(\d{2})\s+(.+)$", re.S)


@dataclass
class Reminder:
    id: int
    user_id: int
    run_at: str
    text: str


def next_run_at(hhmm: str, now: datetime | None = None) -> datetime:
    now = now or datetime.now(TZ)
    hour, minute = (int(x) for x in hhmm.split(":"))
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target


class ReminderStore:
    """提醒的持久化存储，重启后仍保留。"""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._items: list[Reminder] = []
        self._next_id = 1
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self._items = [Reminder(**item) for item in raw]
            if self._items:
                self._next_id = max(item.id for item in self._items) + 1
        except (json.JSONDecodeError, TypeError, OSError) as exc:
            logger.warning("读取提醒文件失败: %s", exc)
            self._items = []

    def _save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps([asdict(i) for i in self._items], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(tmp, self.path)

    def add(self, user_id: int, run_at: datetime, text: str) -> Reminder:
        item = Reminder(self._next_id, user_id, run_at.isoformat(), text)
        self._next_id += 1
        self._items.append(item)
        self._save()
        return item

    def remove(self, reminder_id: int) -> bool:
        before = len(self._items)
        self._items = [i for i in self._items if i.id != reminder_id]
        if len(self._items) != before:
            self._save()
            return True
        return False

    def pending(self) -> list[Reminder]:
        return sorted(self._items, key=lambda i: i.run_at)

    def expired(self, now: datetime | None = None) -> list[Reminder]:
        now = now or datetime.now(TZ)
        return [i for i in self._items if datetime.fromisoformat(i.run_at) <= now]

    def drop_expired(self) -> None:
        self._items = [i for i in self._items if i not in self.expired()]
        self._save()


def parse_remind_command(text: str) -> tuple[str, str] | None:
    """把 '/remind 08:30 开会' 解析成 ('08:30', '开会')。"""
    match = REMIND_RE.match(text.strip())
    if not match:
        return None
    hour, minute, content = match.groups()
    if not (0 <= int(hour) <= 23 and 0 <= int(minute) <= 59):
        return None
    if not content.strip():
        return None
    return f"{int(hour):02d}:{minute}", content.strip()
