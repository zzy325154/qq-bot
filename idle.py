import json
import os
import random
from datetime import datetime, time, timedelta
from pathlib import Path


MOOD_LEVELS = [
    (0, "平静", ""),
    (
        1,
        "有点在意",
        "你有点在意对方不回消息，会轻轻抱怨一句，但语气还是软的，愿意给台阶。",
    ),
    (
        2,
        "不高兴",
        "你有点不高兴，会阴阳怪气、说反话，比如「你还知道回啊」「忙完了？」，但还愿意继续聊。",
    ),
    (
        3,
        "明显生气",
        "你现在很生气。语气冷，常用「哦」「行吧」「随你」这类短句，不主动找话题。",
    ),
    (
        4,
        "赌气冷淡",
        "你已经很久没被理了。装作无所谓，但话里带刺，回得很短，不主动示弱，也不解释自己为什么不高兴。",
    ),
]

MOOD_TIERS = [
    (48, MOOD_LEVELS[4][1], MOOD_LEVELS[4][2]),
    (24, MOOD_LEVELS[3][1], MOOD_LEVELS[3][2]),
    (12, MOOD_LEVELS[2][1], MOOD_LEVELS[2][2]),
    (6, MOOD_LEVELS[1][1], MOOD_LEVELS[1][2]),
]


def level_for_silence(hours: float) -> int:
    if hours >= 48:
        return 4
    if hours >= 24:
        return 3
    if hours >= 12:
        return 2
    if hours >= 6:
        return 1
    return 0


def mood_by_level(level: int) -> tuple[str, str]:
    level = max(0, min(4, int(level)))
    return MOOD_LEVELS[level][1], MOOD_LEVELS[level][2]


def decay_mood(
    level: int,
    updated_at: datetime | None,
    now: datetime,
    decay_hours: float,
) -> int:
    if level <= 0 or updated_at is None or decay_hours <= 0:
        return max(0, level)
    hours = (now - updated_at).total_seconds() / 3600
    steps = int(hours // decay_hours)
    return max(0, int(level) - steps)


def mood_for_silence(hours: float) -> tuple[str, str]:
    return mood_by_level(level_for_silence(hours))


def parse_window(value: str) -> tuple[time, time]:
    try:
        start_text, end_text = value.split("-")
        start = time.fromisoformat(start_text.strip())
        end = time.fromisoformat(end_text.strip())
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"时间窗口格式应为 HH:MM-HH:MM，当前: {value!r}") from exc
    return start, end


def in_window(now: time, window: tuple[time, time]) -> bool:
    start, end = window
    if start <= end:
        return start <= now < end
    return now >= start or now < end


def should_idle_chat(
    now: datetime,
    last_user_at: datetime | None,
    last_idle_at: datetime | None,
    window: tuple[time, time],
    idle_hours: float,
    min_gap_hours: float,
    chance: float,
    rng=random.random,
) -> bool:
    if last_user_at is None:
        return False
    if not in_window(now.timetz().replace(tzinfo=None), window):
        return False
    if now - last_user_at < timedelta(hours=idle_hours):
        return False
    if last_idle_at is not None and now - last_idle_at < timedelta(hours=min_gap_hours):
        return False
    return rng() < chance


class StateStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._data: dict = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                self._data = raw
        except (OSError, json.JSONDecodeError):
            self._data = {}

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def set(self, key: str, value) -> None:
        self._data[key] = value
        self._save()

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(tmp, self.path)
