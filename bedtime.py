"""按当天的精力挑一个道晚安的时间，让她的作息跟着生活状态走。"""

import random
from datetime import datetime, time, timedelta

DEFAULT_EARLIEST = "22:20"
DEFAULT_LATEST = "00:40"


def _minutes(hhmm: str) -> int:
    hour, minute = (int(x) for x in hhmm.split(":"))
    return hour * 60 + minute


def plan(
    now: datetime,
    energy: float,
    earliest: str = DEFAULT_EARLIEST,
    latest: str = DEFAULT_LATEST,
    rng=random.uniform,
) -> tuple[datetime, datetime, datetime]:
    """返回 (窗口开始, 今晚的目标时间, 窗口结束)。

    精力越低越早说晚安，精力足就往后拖；窗口可以跨过午夜。
    """
    anchor = now.date() if now.hour >= 12 else (now - timedelta(days=1)).date()
    start_min = _minutes(earliest)
    end_min = _minutes(latest)
    if end_min <= start_min:
        end_min += 24 * 60
    midnight = datetime.combine(anchor, time.min, tzinfo=now.tzinfo)
    start = midnight + timedelta(minutes=start_min)
    end = midnight + timedelta(minutes=end_min)
    ratio = min(1.0, max(0.0, (float(energy) - 20.0) / 70.0))
    span = end_min - start_min
    offset = span * ratio + rng(-20.0, 20.0)
    offset = min(span, max(0.0, offset))
    return start, start + timedelta(minutes=offset), end
