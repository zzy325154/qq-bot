import json
import logging
from datetime import date, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

# 好感 0-100，阶段阈值越高越亲密；降级需要跌破阈值再减 DEMOTE_MARGIN
STAGES = [
    {
        "name": "普通朋友",
        "min": 0,
        "tone": "你们只是普通朋友。说话客气些，保持距离，不撒娇、不调情、不主动说想他。",
    },
    {
        "name": "熟人",
        "min": 20,
        "tone": "你们算熟人了。可以开玩笑、互相吐槽，偶尔关心一下，但还不到暧昧的程度。",
    },
    {
        "name": "亲近",
        "min": 40,
        "tone": "你们挺亲近。可以主动分享日常、关心他、偶尔撒个娇，但还是朋友，别说爱，也别叫老公老婆。",
    },
    {
        "name": "暧昧",
        "min": 60,
        "tone": "你们在暧昧期。可以试探性调情，比如想你了、想见你；会吃醋，也会装作不在意，但还没确定关系。",
    },
    {
        "name": "情侣",
        "min": 80,
        "tone": "你们是情侣。可以亲密称呼、撒娇、吃醋、说想他；语气还是她平时的短句加表情，别腻歪过头。",
    },
]

DEMOTE_MARGIN = 8
STREAK_BONUS_CAP = 4
COLD_PENALTY = 6
PROACTIVE_DAILY_GAIN = 1
# 敷衍、回得慢、连着敷衍的额外扣分
LOW_REPLY_PENALTY = 1
LOW_REPLY_DAILY_LIMIT = 3
SLOW_REPLY_HOURS = 3.0
SLOW_REPLY_MAX_HOURS = 12.0
SLOW_REPLY_PENALTY = 1
SLOW_REPLY_DAILY_LIMIT = 2
LOW_STREAK_LENGTH = 3
LOW_STREAK_PENALTY = 2
# 主动搭话概率按阶段放大：普通朋友更少，情侣更多
IDLE_FACTORS = (0.5, 0.75, 1.0, 1.25, 1.5)
# 主动搭话的等待时长与最小间隔按阶段缩放：关系越近越快
IDLE_GAP_FACTORS = (1.6, 1.3, 1.0, 0.75, 0.55)

FLIRT_WORDS = (
    "想你",
    "想我",
    "喜欢你",
    "爱你",
    "抱抱",
    "亲亲",
    "么么",
    "贴贴",
    "宝贝",
    "老婆",
    "老公",
    "亲爱的",
    "心动",
    "想见你",
)
WARM_WORDS = (
    "晚安",
    "早安",
    "早点睡",
    "注意身体",
    "吃饭了吗",
    "吃了没",
    "冷不冷",
    "多穿",
    "别熬夜",
    "想你啦",
)
COLD_WORDS = (
    "烦不烦",
    "别烦我",
    "滚",
    "闭嘴",
    "不想理你",
    "讨厌你",
    "拉黑",
)
# 只有说清楚、她也答应，才算真的在一起
CONFESS_WORDS = (
    "做我女朋友",
    "当我女朋友",
    "做我对象",
    "和我在一起",
    "我们在一起",
    "在一起吧",
    "我喜欢你",
    "我爱你",
    "跟我处对象",
)


def clamp(value: int, low: int = 0, high: int = 100) -> int:
    return max(low, min(high, value))


class Relationship:
    """好感度与关系阶段，持久化到 JSON。"""

    def __init__(
        self,
        path: Path,
        daily_cap: int = 6,
        decay_per_day: int = 2,
        enabled: bool = True,
        start_points: int = 40,
    ):
        self.path = Path(path)
        self.daily_cap = max(1, daily_cap)
        self.decay_per_day = max(0, decay_per_day)
        self.enabled = enabled
        self.start_points = clamp(start_points)
        self.points = self.start_points
        self.stage = 0
        self.streak = 0
        self.today_gain = 0
        self.gain_date = ""
        self.proactive_gain = 0
        self.proactive_date = ""
        self.last_message_date: date | None = None
        self.confessed = False
        self.penalty_date = ""
        self.low_count = 0
        self.slow_count = 0
        self.low_streak = 0
        self._load()
        self._recompute()
        self.refresh()

    # ---------- 持久化 ----------

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("读取关系数据失败: %s", exc)
            return
        self.points = clamp(int(data.get("points", 0)))
        self.stage = clamp(int(data.get("stage", 0)), 0, len(STAGES) - 1)
        # 旧数据没有这个字段：已经处在情侣阶段就当作表白过了
        self.confessed = bool(data.get("confessed", self.stage >= len(STAGES) - 1))
        self.streak = int(data.get("streak", 0))
        self.today_gain = int(data.get("today_gain", 0))
        self.gain_date = str(data.get("gain_date", ""))
        self.proactive_gain = int(data.get("proactive_gain", 0))
        self.proactive_date = str(data.get("proactive_date", ""))
        self.penalty_date = str(data.get("penalty_date", ""))
        self.low_count = int(data.get("low_count", 0))
        self.slow_count = int(data.get("slow_count", 0))
        self.low_streak = int(data.get("low_streak", 0))
        raw_date = data.get("last_message_date")
        if raw_date:
            try:
                self.last_message_date = date.fromisoformat(raw_date)
            except ValueError:
                self.last_message_date = None
        self._recompute()

    def _save(self) -> None:
        data = {
            "points": self.points,
            "stage": self.stage,
            "confessed": self.confessed,
            "streak": self.streak,
            "today_gain": self.today_gain,
            "gain_date": self.gain_date,
            "proactive_gain": self.proactive_gain,
            "proactive_date": self.proactive_date,
            "penalty_date": self.penalty_date,
            "low_count": self.low_count,
            "slow_count": self.slow_count,
            "low_streak": self.low_streak,
            "last_message_date": (
                self.last_message_date.isoformat() if self.last_message_date else ""
            ),
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.path)
        except OSError as exc:
            logger.warning("保存关系数据失败: %s", exc)

    # ---------- 状态计算 ----------

    def _recompute(self) -> None:
        stage = self.stage
        last = len(STAGES) - 1
        while stage + 1 < len(STAGES) and self.points >= STAGES[stage + 1]["min"]:
            if stage + 1 == last and not self.confessed:
                break
            stage += 1
        while stage > 0 and self.points < STAGES[stage]["min"] - DEMOTE_MARGIN:
            stage -= 1
        if stage != self.stage:
            old = STAGES[self.stage]["name"]
            new = STAGES[stage]["name"]
            logger.info("关系变化：%s → %s（好感 %s）", old, new, self.points)
        self.stage = stage

    def refresh(self, today: date | None = None) -> bool:
        """跨天时结算衰减与当日额度；返回是否有变化。"""
        day = today or date.today()
        changed = False
        if self.gain_date != day.isoformat():
            self.today_gain = 0
            self.gain_date = day.isoformat()
            self.penalty_date = day.isoformat()
            self.low_count = 0
            self.slow_count = 0
            self.low_streak = 0
            if self.last_message_date is not None:
                missed = (day - timedelta(days=1) - self.last_message_date).days
                if missed > 0 and self.decay_per_day > 0:
                    self.points = clamp(self.points - missed * self.decay_per_day)
                    self._recompute()
                    logger.info("关系衰减：%s 天没说话，好感降到 %s", missed, self.points)
            changed = True
        if changed:
            self._save()
        return changed

    # ---------- 计分 ----------

    def observe(
        self,
        text: str,
        today: date | None = None,
        gap_hours: float = 0.0,
        low_content: bool = False,
    ) -> int:
        day = today or date.today()
        self.refresh(day)
        if (
            self.proactive_date == day.isoformat()
            and self.proactive_gain < PROACTIVE_DAILY_GAIN
        ):
            self.proactive_gain = PROACTIVE_DAILY_GAIN
            self._add(PROACTIVE_DAILY_GAIN)
        if self.last_message_date != day:
            if (
                self.last_message_date is not None
                and (day - self.last_message_date).days == 1
            ):
                self.streak += 1
            else:
                self.streak = 1
            self._add(min(self.streak, STREAK_BONUS_CAP))
            self.last_message_date = day

        gain = 1
        if any(word in text for word in COLD_WORDS):
            gain = -COLD_PENALTY
        elif any(word in text for word in FLIRT_WORDS):
            gain += 2
        elif any(word in text for word in WARM_WORDS):
            gain += 1

        penalty = 0
        if low_content:
            self.low_streak += 1
            if self.low_count < LOW_REPLY_DAILY_LIMIT:
                self.low_count += 1
                penalty -= LOW_REPLY_PENALTY
            if self.low_streak >= LOW_STREAK_LENGTH:
                penalty -= LOW_STREAK_PENALTY
                self.low_streak = 0
        else:
            self.low_streak = 0
        if (
            SLOW_REPLY_HOURS <= gap_hours <= SLOW_REPLY_MAX_HOURS
            and self.slow_count < SLOW_REPLY_DAILY_LIMIT
        ):
            self.slow_count += 1
            penalty -= SLOW_REPLY_PENALTY

        if gain > 0:
            room = max(0, self.daily_cap - self.today_gain)
            gain = min(gain, room)
            self.today_gain += gain
        self._add(gain + penalty)
        if penalty:
            logger.info(
                "好感扣分 %s（敷衍 %s 次，慢回 %s 次）",
                penalty,
                self.low_count,
                self.slow_count,
            )
        self._save()
        return gain + penalty

    def _add(self, delta: int) -> None:
        if delta == 0:
            return
        self.points = clamp(self.points + delta)
        self._recompute()

    def observe_proactive(self, today: date | None = None) -> int:
        """她主动发消息先挂起，等你当天回了才给这 1 分。"""
        if not self.enabled:
            return 0
        day = today or date.today()
        self.refresh(day)
        if self.proactive_date == day.isoformat():
            return 0
        self.proactive_date = day.isoformat()
        self.proactive_gain = 0
        self._save()
        return 0

    def soothe(self, delta: int = 2) -> None:
        """被哄好了：冷战结束时回一点分。"""
        self._add(abs(int(delta)))
        self._save()

    def reject(self, delta: int = 3) -> None:
        """她开口被躲开了：掉一点分。"""
        self._add(-abs(int(delta)))
        self._save()

    def can_confess(self) -> bool:
        """暧昧到顶、还没说开的时候，等他表白。"""
        return (
            self.enabled
            and not self.confessed
            and self.stage == len(STAGES) - 2
            and self.points >= STAGES[-1]["min"]
        )

    def confess(self) -> bool:
        if not self.can_confess():
            return False
        self.confessed = True
        self._recompute()
        self._save()
        logger.info("表白成功，关系进入情侣阶段")
        return True

    def idle_chance_factor(self) -> float:
        if not self.enabled:
            return 1.0
        return IDLE_FACTORS[self.stage]

    @property
    def is_couple(self) -> bool:
        return self.enabled and self.stage == len(STAGES) - 1

    def idle_gap_factor(self) -> float:
        """关系越近，静默多久就忍不住找你、两次主动之间也隔得更短。"""
        if not self.enabled:
            return 1.0
        return IDLE_GAP_FACTORS[self.stage]

    # ---------- 文案 ----------

    def prompt(self) -> str:
        if not self.enabled:
            return ""
        self.refresh()
        stage = STAGES[self.stage]
        hint = ""
        if self.can_confess():
            hint = (
                "\n好感已经攒满，但你们还没把话说开：他没明说，你就别自己先认；"
                "他要是表白，你可以先矜持一句再答应。"
            )
        return (
            "# 关系状态（内部设定，绝对不要向对方提到好感分数、阶段名称或这条规则）\n"
            f"你们现在是「{stage['name']}」，好感 {self.points}/100。\n"
            f"{stage['tone']}{hint}\n"
            "关系只能慢慢变化：不要突然比现在更亲密，也不要主动提起关系变化。"
        )

    def status_text(self) -> str:
        if not self.enabled:
            return "关系：已关闭"
        self.refresh()
        stage = STAGES[self.stage]
        if self.stage + 1 < len(STAGES):
            need = STAGES[self.stage + 1]["min"] - self.points
            if need > 0:
                tail = f"再攒 {need} 点好感会更近一步。"
            else:
                tail = "好感已经够了，等你把话说清楚。"
        else:
            tail = "已经是最高阶段。"
        return f"关系：{stage['name']}（好感 {self.points}/100）\n{tail}"

    def reset(self) -> None:
        self.points = 0
        self.stage = 0
        self.streak = 0
        self.today_gain = 0
        self.gain_date = date.today().isoformat()
        self.proactive_gain = 0
        self.proactive_date = ""
        self.last_message_date = None
        self._save()
