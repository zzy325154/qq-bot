import difflib
import json
import logging
import random
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

# 时间段 → (在干嘛, 每小时精力变化)
SCHEDULE = [
    (1, 7, "在睡觉", 8.0),
    (7, 9, "刚醒，在洗漱收拾", 0.0),
    (9, 12, "在上课或者忙事情", -6.0),
    (12, 14, "在吃午饭，顺便歇一会儿", 3.0),
    (14, 18, "在上课或者忙事情", -6.0),
    (18, 20, "在吃晚饭", 3.0),
    (20, 23, "在宿舍待着，刷手机或者追剧", -2.0),
]
NIGHT_ACTIVITY = "躺在床上刷手机，准备睡了"
NIGHT_RATE = -1.0
WEEKDAYS = "一二三四五六日"


def activity_for_hour(hour: int) -> tuple[str, float]:
    for start, end, text, rate in SCHEDULE:
        if start <= hour < end:
            return text, rate
    return NIGHT_ACTIVITY, NIGHT_RATE


def clamp(value: float, low: float = 0, high: float = 100) -> float:
    return max(low, min(high, value))


class LifeState:
    """她自己的时间线：此刻在干嘛、精力、最近发生的小事。"""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.activity = NIGHT_ACTIVITY
        self.energy = 70.0
        self.events: list[dict] = []
        self.updated_at = ""
        self.hold_text = ""
        self.hold_until = ""
        self._load()

    # ---------- 持久化 ----------

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("读取生活状态失败: %s", exc)
            return
        self.activity = str(data.get("activity", NIGHT_ACTIVITY))
        self.energy = clamp(float(data.get("energy", 70)))
        self.events = [
            item
            for item in data.get("events", [])
            if isinstance(item, dict) and item.get("text")
        ]
        self.updated_at = str(data.get("updated_at", ""))
        self.hold_text = str(data.get("hold_text", ""))
        self.hold_until = str(data.get("hold_until", ""))

    def _save(self) -> None:
        data = {
            "activity": self.activity,
            "energy": round(self.energy, 1),
            "events": self.events[-20:],
            "updated_at": self.updated_at,
            "hold_text": self.hold_text,
            "hold_until": self.hold_until,
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.path)
        except OSError as exc:
            logger.warning("保存生活状态失败: %s", exc)

    # ---------- 推进 ----------

    def tick(self, now: datetime) -> None:
        now_aware = now if now.tzinfo is not None else now.astimezone()
        previous = self._parse(self.updated_at)
        if previous is not None and previous.tzinfo is None:
            previous = previous.astimezone()
        if previous is not None:
            hours = min(3.0, max(0.0, (now_aware - previous).total_seconds() / 3600))
        else:
            hours = 0.0
        activity, rate = activity_for_hour(now.hour)
        hold_until = self._parse(self.hold_until)
        if hold_until is not None and hold_until.tzinfo is None:
            hold_until = hold_until.astimezone()
        if hold_until is not None and now_aware < hold_until and self.hold_text:
            self.activity = self.hold_text
        else:
            self.hold_text = ""
            self.hold_until = ""
            if previous is None or activity != self.activity:
                self.activity = activity
        if hours > 0:
            self.energy = clamp(self.energy + rate * hours)
        self.updated_at = now_aware.isoformat()
        self._expire(now_aware)
        self._save()

    def _expire(self, now: datetime) -> None:
        now_aware = now if now.tzinfo is not None else now.astimezone()
        kept = []
        for item in self.events:
            at = self._parse(item.get("at", ""))
            ttl = float(item.get("ttl_hours", 12))
            if at is not None and at.tzinfo is None:
                at = at.astimezone()
            if at is None or now_aware - at <= timedelta(hours=ttl):
                kept.append(item)
        self.events = kept

    @staticmethod
    def _parse(value: str) -> datetime | None:
        try:
            return datetime.fromisoformat(value) if value else None
        except ValueError:
            return None

    # ---------- 事件 ----------

    def set_activity(
        self, text: str, now: datetime | None = None, hold_hours: float = 0.0
    ) -> None:
        now = now or datetime.now().astimezone()
        self.activity = text
        self.updated_at = now.isoformat()
        if hold_hours > 0:
            self.hold_text = text
            self.hold_until = (now + timedelta(hours=hold_hours)).isoformat()
        else:
            self.hold_text = ""
            self.hold_until = ""
        self._save()

    def add_event(self, text: str, now: datetime, ttl_hours: float = 12) -> bool:
        text = text.strip()
        if not text:
            return False
        for recent in self.recent_events(5):
            if difflib.SequenceMatcher(None, text, recent).ratio() > 0.7:
                logger.debug("生活小事太像最近的事件，跳过：%s", text)
                return False
        self.events.append(
            {"text": text[:60], "at": now.isoformat(), "ttl_hours": ttl_hours}
        )
        self.events = self.events[-20:]
        self._save()
        return True

    def recent_events(self, limit: int = 3) -> list[str]:
        return [item["text"] for item in self.events[-limit:]]

    def _ago(self, at: datetime, now: datetime) -> str:
        if at.tzinfo is None:
            at = at.astimezone()
        if now.tzinfo is None:
            now = now.astimezone()
        delta = now - at
        if delta < timedelta(minutes=45):
            return "刚刚"
        if delta < timedelta(hours=6):
            return f"{int(delta.total_seconds() // 3600)} 小时前"
        if at.date() == now.date():
            return "今天早些时候"
        if (now.date() - at.date()).days == 1:
            return "昨天"
        return "前几天"

    def events_with_time(self, now: datetime, limit: int = 3) -> list[tuple[str, str]]:
        out = []
        for item in self.events[-limit:]:
            at = self._parse(item.get("at", ""))
            if at is None:
                continue
            if at.tzinfo is None:
                at = at.astimezone()
            out.append((self._ago(at, now), item["text"]))
        return out

    # ---------- 文案 ----------

    def reply_profile(self) -> tuple[float, float, float, bool]:
        """按当前活动给出 (额外延迟下限秒, 上限秒, 不回概率增量, 是否醒着)。"""
        activity = self.activity
        if "睡觉" in activity and "准备睡" not in activity:
            return 0, 0, 0, False
        if "上课" in activity or "忙事情" in activity:
            return 60, 450, 0.15, True
        if "午饭" in activity or "晚饭" in activity:
            return 10, 60, 0.05, True
        if "洗漱" in activity:
            return 20, 120, 0.05, True
        if "准备睡" in activity:
            return 5, 30, 0.10, True
        return 0, 0, 0.0, True

    def prompt(self, now: datetime | None = None) -> str:
        now = now or datetime.now().astimezone()
        self._expire(now)
        events = self.events_with_time(now, 3)
        event_text = (
            "；".join(f"{when}：{text}" for when, text in events)
            if events
            else "最近没什么特别的"
        )
        weekday = WEEKDAYS[now.weekday()]
        return (
            "# 你自己的生活（内部设定，不要机械复述，也不要每条消息都提）\n"
            f"现在是 {now:%m-%d %H:%M}（周{weekday}）。你{self.activity}，精力大概 {self.energy:.0f}/100。\n"
            f"最近发生的事：{event_text}。\n"
            "前面标了时间的事都已经过去了，不要说成刚刚发生，也不要拿它当今天的新鲜事。\n"
            "聊天时可以自然带到这些，但不要和这些状态冲突，也不要编共同经历。"
        )

    def status_text(self) -> str:
        now = datetime.now().astimezone()
        events = self.events_with_time(now, 3)
        tail = "\n".join(f"- {when}：{text}" for when, text in events) or "- 最近没什么特别的"
        return (
            f"她现在的状态：{self.activity}（精力 {self.energy:.0f}/100）\n"
            f"最近发生的事：\n{tail}"
        )
