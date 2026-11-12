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
WEEKEND_SCHEDULE = [
    (1, 9, "在家睡觉", 8.0),
    (9, 11, "刚醒，赖在床上刷手机", 1.0),
    (11, 13, "在家吃早午饭", 3.0),
    (13, 18, "在家待着，看看剧或者收拾东西", -2.0),
    (18, 20, "在家吃晚饭", 3.0),
    (20, 24, "在家待着，刷手机或者追剧", -2.0),
]
OUTING_PLACES = (
    "在商场里逛",
    "在电影院",
    "和朋友在外面吃饭",
    "在书店待着",
    "在公园散步",
    "去逛超市了",
)
OUTING_CHANCE_WEEKDAY = 0.01
OUTING_CHANCE_WEEKEND = 0.05
VACATION_SCHEDULE = [
    (1, 10, "在睡觉", 8.0),
    (10, 12, "刚起，在家吃早午饭", 3.0),
    (12, 18, "在家待着，刷手机看剧", -2.0),
    (18, 20, "在吃晚饭", 3.0),
    (20, 24, "在家待着，刷手机或者追剧", -2.0),
]
# (开始, 结束, 名称)，按 月, 日 比较
VACATIONS = (
    ((1, 10), (2, 25), "寒假"),
    ((7, 1), (8, 31), "暑假"),
)
NIGHT_ACTIVITY = "在宿舍床上刷手机，准备睡了"
NIGHT_RATE = -1.0
WEEKDAYS = "一二三四五六日"
MOODS = ("爽", "烦", "累", "无语", "开心", "慌")


def vacation_on(day) -> str:
    """当天在假期里就返回假期名，否则返回空串。"""
    month_day = (day.month, day.day)
    for start, end, name in VACATIONS:
        if start <= month_day <= end:
            return name
    return ""


def home_override(now) -> str:
    """周五晚上回家、周日晚上回宿舍的过渡状态。"""
    if now.weekday() == 4 and 18 <= now.hour < 23:
        return "在家，周末回家了"
    if now.weekday() == 6 and 20 <= now.hour < 22:
        return "刚从家回到宿舍，收拾东西"
    return ""


def activity_for_hour(
    hour: int, weekend: bool = False, vacation: str = ""
) -> tuple[str, float]:
    if vacation:
        schedule = VACATION_SCHEDULE
    elif weekend:
        schedule = WEEKEND_SCHEDULE
    else:
        schedule = SCHEDULE
    for start, end, text, rate in schedule:
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
        self.outing_place = ""
        self.outing_until = ""
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
        self.outing_place = str(data.get("outing_place", ""))
        self.outing_until = str(data.get("outing_until", ""))

    def _save(self) -> None:
        data = {
            "activity": self.activity,
            "energy": round(self.energy, 1),
            "events": self.events[-20:],
            "updated_at": self.updated_at,
            "hold_text": self.hold_text,
            "hold_until": self.hold_until,
            "outing_place": self.outing_place,
            "outing_until": self.outing_until,
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
        vacation = vacation_on(now_aware.date())
        weekend = now_aware.weekday() >= 5
        activity, rate = activity_for_hour(now_aware.hour, weekend, vacation)
        self._update_outing(now_aware, weekend or bool(vacation))
        hold_until = self._parse(self.hold_until)
        if hold_until is not None and hold_until.tzinfo is None:
            hold_until = hold_until.astimezone()
        if self._outing_active(now_aware):
            self.activity = f"出门了，{self.outing_place}"
        elif hold_until is not None and now_aware < hold_until and self.hold_text:
            self.activity = self.hold_text
        else:
            self.hold_text = ""
            self.hold_until = ""
            target = home_override(now_aware) or activity
            if previous is None or target != self.activity:
                self.activity = target
        if hours > 0:
            self.energy = clamp(self.energy + rate * hours)
        self.updated_at = now_aware.isoformat()
        self._expire(now_aware)
        self._save()

    def _outing_active(self, now: datetime) -> bool:
        until = self._parse(self.outing_until)
        if until is None or not self.outing_place:
            return False
        if until.tzinfo is None:
            until = until.astimezone()
        return now < until

    def _update_outing(self, now: datetime, weekend: bool) -> None:
        until = self._parse(self.outing_until)
        if until is not None and until.tzinfo is None:
            until = until.astimezone()
        if until is not None and now >= until:
            if self.outing_place:
                self.add_event("刚到家 在外面走了一天腿都酸了", now, ttl_hours=8)
            self.outing_place = ""
            self.outing_until = ""
            return
        if until is not None:
            return
        if not 10 <= now.hour <= 20:
            return
        chance = OUTING_CHANCE_WEEKEND if weekend else OUTING_CHANCE_WEEKDAY
        if random.random() >= chance:
            return
        self.outing_place = random.choice(OUTING_PLACES)
        self.outing_until = (now + timedelta(hours=random.uniform(2, 4))).isoformat()
        self.add_event(f"出门了，{self.outing_place}", now, ttl_hours=6)

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

    def add_event(
        self, text: str, now: datetime, ttl_hours: float = 12, mood: str = ""
    ) -> bool:
        text = text.strip()
        if not text:
            return False
        for recent in self.recent_events(5):
            if difflib.SequenceMatcher(None, text, recent).ratio() > 0.7:
                logger.debug("生活小事太像最近的事件，跳过：%s", text)
                return False
        self.events.append(
            {
                "text": text[:60],
                "at": now.isoformat(),
                "ttl_hours": ttl_hours,
                "mood": mood[:6],
            }
        )
        self.events = self.events[-20:]
        self._save()
        return True

    def recent_events(self, limit: int = 3) -> list[str]:
        return [item["text"] for item in self.events[-limit:]]

    def latest_mood(self, now: datetime | None = None, hours: float = 6) -> str:
        now = now or datetime.now().astimezone()
        if now.tzinfo is None:
            now = now.astimezone()
        for item in reversed(self.events):
            mood = str(item.get("mood", "")).strip()
            if not mood:
                continue
            at = self._parse(item.get("at", ""))
            if at is None:
                continue
            if at.tzinfo is None:
                at = at.astimezone()
            if now - at <= timedelta(hours=hours):
                return mood
        return ""

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
        if activity.startswith("出门了"):
            return 30, 180, 0.10, True
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
        vacation = vacation_on(now.date())
        if vacation:
            day_note = f"，{vacation}，不用上课"
        elif now.weekday() >= 5:
            day_note = "，周末回家了"
        else:
            day_note = ""
        mood = self.latest_mood(now)
        mood_line = (
            f"最近那件小事让你有点{mood}，说话可以带一点这个情绪，但别直接把心情说出来。\n"
            if mood
            else ""
        )
        return (
            "# 你自己的生活（内部设定，不要机械复述，也不要每条消息都提）\n"
            f"现在是 {now:%m-%d %H:%M}（周{weekday}{day_note}）。你{self.activity}，精力大概 {self.energy:.0f}/100。\n"
            f"最近发生的事：{event_text}。\n"
            f"{mood_line}"
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
