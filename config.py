import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

DEFAULT_PERSONA = (
    "你是一个说话简洁、有点毒舌但可靠的私人助理。"
    "回答控制在三句话以内，除非对方明确要求详细展开。"
    "不要使用 Markdown 语法，因为对方在手机 QQ 上阅读。"
)


def _env_str(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        raise ValueError(f"环境变量 {name} 必须是整数，当前值: {raw!r}")


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        raise ValueError(f"环境变量 {name} 必须是数字，当前值: {raw!r}")


@dataclass
class Config:
    onebot_ws: str = field(default_factory=lambda: _env_str("ONEBOT_WS", "ws://127.0.0.1:3001"))
    onebot_token: str = field(default_factory=lambda: _env_str("ONEBOT_TOKEN"))
    owner_qq: int = field(default_factory=lambda: _env_int("OWNER_QQ", 0))
    api_key: str = field(default_factory=lambda: _env_str("DEEPSEEK_API_KEY"))
    api_base: str = field(default_factory=lambda: _env_str("DEEPSEEK_BASE", "https://api.deepseek.com").rstrip("/"))
    model: str = field(default_factory=lambda: _env_str("LLM_MODEL", "deepseek-chat"))
    persona: str = field(default_factory=lambda: _env_str("PERSONA", DEFAULT_PERSONA))
    morning_time: str = field(default_factory=lambda: _env_str("MORNING_TIME", "08:00"))
    night_time: str = field(default_factory=lambda: _env_str("NIGHT_TIME", "22:30"))
    night_dynamic: bool = field(
        default_factory=lambda: _env_str("NIGHT_DYNAMIC", "1") != "0"
    )
    night_earliest: str = field(
        default_factory=lambda: _env_str("NIGHT_EARLIEST", "22:20")
    )
    night_latest: str = field(
        default_factory=lambda: _env_str("NIGHT_LATEST", "00:40")
    )
    history_turns: int = field(default_factory=lambda: _env_int("HISTORY_TURNS", 12))
    data_dir: Path = field(default_factory=lambda: BASE_DIR / "data")
    archive_dir: Path = field(default_factory=lambda: BASE_DIR / "data" / "archive")
    use_persona_file: bool = field(
        default_factory=lambda: _env_str("USE_PERSONA_FILE", "1") != "0"
    )
    archive_enabled: bool = field(
        default_factory=lambda: _env_str("ARCHIVE_ENABLED", "1") != "0"
    )
    archive_top_k: int = field(default_factory=lambda: _env_int("ARCHIVE_TOP_K", 4))
    split_reply: bool = field(
        default_factory=lambda: _env_str("SPLIT_REPLY", "1") != "0"
    )
    emoji_enabled: bool = field(
        default_factory=lambda: _env_str("EMOJI_ENABLED", "1") != "0"
    )
    emoji_rate: float = field(default_factory=lambda: _env_float("EMOJI_RATE", 0.28))
    emoji_since: str = field(
        default_factory=lambda: _env_str("EMOJI_SINCE", "2024-07-01")
    )
    emoji_auto_fetch: bool = field(
        default_factory=lambda: _env_str("EMOJI_AUTO_FETCH", "1") != "0"
    )
    emoji_fetch_count: int = field(
        default_factory=lambda: _env_int("EMOJI_FETCH_COUNT", 6)
    )
    web_enabled: bool = field(
        default_factory=lambda: _env_str("WEB_ENABLED", "1") != "0"
    )
    web_proxy: str = field(
        default_factory=lambda: _env_str("WEB_PROXY", "http://127.0.0.1:7897")
    )
    serper_api_key: str = field(default_factory=lambda: _env_str("SERPER_API_KEY"))
    web_max_rounds: int = field(default_factory=lambda: _env_int("WEB_MAX_ROUNDS", 3))
    web_max_results: int = field(
        default_factory=lambda: _env_int("WEB_MAX_RESULTS", 5)
    )
    idle_enabled: bool = field(
        default_factory=lambda: _env_str("IDLE_CHAT_ENABLED", "1") != "0"
    )
    idle_hours: float = field(
        default_factory=lambda: _env_float("IDLE_HOURS", 4.0)
    )
    idle_check_minutes: int = field(
        default_factory=lambda: _env_int("IDLE_CHECK_MINUTES", 30)
    )
    idle_chance: float = field(
        default_factory=lambda: _env_float("IDLE_CHANCE", 0.35)
    )
    idle_window: str = field(
        default_factory=lambda: _env_str("IDLE_WINDOW", "09:00-23:00")
    )
    idle_min_gap_hours: float = field(
        default_factory=lambda: _env_float("IDLE_MIN_GAP_HOURS", 6.0)
    )
    idle_after_bot_hours: float = field(
        default_factory=lambda: _env_float("IDLE_AFTER_BOT_HOURS", 2.0)
    )
    disconnect_alert_minutes: int = field(
        default_factory=lambda: _env_int("DISCONNECT_ALERT_MINUTES", 10)
    )
    away_enabled: bool = field(
        default_factory=lambda: _env_str("AWAY_ENABLED", "1") != "0"
    )
    away_chance: float = field(
        default_factory=lambda: _env_float("AWAY_CHANCE", 0.06)
    )
    her_confess_chance: float = field(
        default_factory=lambda: _env_float("HER_CONFESS_CHANCE", 0.12)
    )
    school_name: str = field(default_factory=lambda: _env_str("SCHOOL_NAME", ""))
    major: str = field(default_factory=lambda: _env_str("MAJOR", ""))
    mood_enabled: bool = field(
        default_factory=lambda: _env_str("MOOD_ENABLED", "1") != "0"
    )
    mood_decay_hours: float = field(
        default_factory=lambda: _env_float("MOOD_DECAY_HOURS", 3.0)
    )
    vision_enabled: bool = field(
        default_factory=lambda: _env_str("VISION_ENABLED", "1") != "0"
    )
    vision_model: str = field(default_factory=lambda: _env_str("VISION_MODEL"))
    vision_api_base: str = field(default_factory=lambda: _env_str("VISION_API_BASE"))
    vision_api_key: str = field(default_factory=lambda: _env_str("VISION_API_KEY"))
    vision_max_images: int = field(
        default_factory=lambda: _env_int("VISION_MAX_IMAGES", 2)
    )
    longterm_enabled: bool = field(
        default_factory=lambda: _env_str("LONGTERM_ENABLED", "1") != "0"
    )
    longterm_summary_hour: int = field(
        default_factory=lambda: _env_int("LONGTERM_SUMMARY_HOUR", 23)
    )
    longterm_summary_minute: int = field(
        default_factory=lambda: _env_int("LONGTERM_SUMMARY_MINUTE", 40)
    )
    reply_debounce_seconds: float = field(
        default_factory=lambda: _env_float("REPLY_DEBOUNCE_SECONDS", 6.0)
    )
    reply_chance: float = field(
        default_factory=lambda: _env_float("REPLY_CHANCE", 0.9)
    )
    reply_delay_min: float = field(
        default_factory=lambda: _env_float("REPLY_DELAY_MIN", 1.5)
    )
    reply_delay_max: float = field(
        default_factory=lambda: _env_float("REPLY_DELAY_MAX", 4.0)
    )
    quiet_hours: float = field(
        default_factory=lambda: _env_float("QUIET_HOURS", 8.0)
    )
    topic_quiet_minutes: float = field(
        default_factory=lambda: _env_float("TOPIC_QUIET_MINUTES", 8.0)
    )
    topic_judge_enabled: bool = field(
        default_factory=lambda: _env_str("TOPIC_JUDGE_ENABLED", "1") != "0"
    )
    voice_enabled: bool = field(
        default_factory=lambda: _env_str("VOICE_ENABLED", "1") != "0"
    )
    tts_voice: str = field(
        default_factory=lambda: _env_str("TTS_VOICE", "zh-CN-XiaoyiNeural")
    )
    tts_rate: str = field(default_factory=lambda: _env_str("TTS_RATE", "+0%"))
    tts_pitch: str = field(default_factory=lambda: _env_str("TTS_PITCH", "+0Hz"))
    voice_max_chars: int = field(
        default_factory=lambda: _env_int("VOICE_MAX_CHARS", 100)
    )
    tts_backend: str = field(
        default_factory=lambda: _env_str("TTS_BACKEND", "edge")
    )
    cosyvoice_url: str = field(
        default_factory=lambda: _env_str("COSYVOICE_URL", "http://127.0.0.1:50001")
    )
    cosyvoice_speaker: str = field(
        default_factory=lambda: _env_str("COSYVOICE_SPEAKER", "xiaoyi")
    )
    cosyvoice_autostart: bool = field(
        default_factory=lambda: _env_str("COSYVOICE_AUTOSTART", "1") != "0"
    )
    cosyvoice_dir: Path = field(
        default_factory=lambda: Path(
            _env_str("COSYVOICE_DIR") or str(BASE_DIR.parent / "cosyvoice")
        )
    )
    cosyvoice_python: str = field(
        default_factory=lambda: _env_str("COSYVOICE_PYTHON")
    )
    cosyvoice_idle_minutes: int = field(
        default_factory=lambda: _env_int("COSYVOICE_IDLE_MINUTES", 15)
    )
    cosyvoice_start_timeout: int = field(
        default_factory=lambda: _env_int("COSYVOICE_START_TIMEOUT", 120)
    )
    relationship_enabled: bool = field(
        default_factory=lambda: _env_str("RELATIONSHIP_ENABLED", "1") != "0"
    )
    relationship_daily_cap: int = field(
        default_factory=lambda: _env_int("RELATIONSHIP_DAILY_CAP", 6)
    )
    relationship_decay_per_day: int = field(
        default_factory=lambda: _env_int("RELATIONSHIP_DECAY_PER_DAY", 4)
    )
    relationship_start_points: int = field(
        default_factory=lambda: _env_int("RELATIONSHIP_START_POINTS", 40)
    )
    life_enabled: bool = field(
        default_factory=lambda: _env_str("LIFE_ENABLED", "1") != "0"
    )
    life_tick_minutes: int = field(
        default_factory=lambda: _env_int("LIFE_TICK_MINUTES", 30)
    )
    life_event_chance: float = field(
        default_factory=lambda: _env_float("LIFE_EVENT_CHANCE", 0.18)
    )
    habits_enabled: bool = field(
        default_factory=lambda: _env_str("HABITS_ENABLED", "1") != "0"
    )
    habits_hour: int = field(
        default_factory=lambda: _env_int("HABITS_HOUR", 18)
    )
    habits_minute: int = field(
        default_factory=lambda: _env_int("HABITS_MINUTE", 0)
    )
    emoji_fetch_hour: int = field(
        default_factory=lambda: _env_int("EMOJI_FETCH_HOUR", 18)
    )
    emoji_fetch_minute: int = field(
        default_factory=lambda: _env_int("EMOJI_FETCH_MINUTE", 0)
    )
    recover_missed: bool = field(
        default_factory=lambda: _env_str("RECOVER_MISSED", "1") != "0"
    )
    recover_hours: float = field(
        default_factory=lambda: _env_float("RECOVER_HOURS", 2.0)
    )
    recover_max: int = field(
        default_factory=lambda: _env_int("RECOVER_MAX", 3)
    )
    commitments_enabled: bool = field(
        default_factory=lambda: _env_str("COMMITMENTS_ENABLED", "1") != "0"
    )
    commitment_check_minutes: int = field(
        default_factory=lambda: _env_int("COMMITMENT_CHECK_MINUTES", 1)
    )
    meet_hours: float = field(
        default_factory=lambda: _env_float("MEET_HOURS", 2.0)
    )
    weather_enabled: bool = field(
        default_factory=lambda: _env_str("WEATHER_ENABLED", "1") != "0"
    )
    weather_city: str = field(
        default_factory=lambda: _env_str("WEATHER_CITY", "上海")
    )
    weather_refresh_hours: float = field(
        default_factory=lambda: _env_float("WEATHER_REFRESH_HOURS", 3.0)
    )

    def validate(self) -> list[str]:
        problems = []
        if self.owner_qq <= 0:
            problems.append("OWNER_QQ 未设置：请填你自己的 QQ 号（接收主动消息的人）")
        if not self.api_key:
            problems.append("DEEPSEEK_API_KEY 未设置：可从 agent-lab/.env 复制")
        if not self.onebot_ws.startswith(("ws://", "wss://")):
            problems.append(f"ONEBOT_WS 必须以 ws:// 或 wss:// 开头，当前: {self.onebot_ws}")
        for name, value in (("MORNING_TIME", self.morning_time), ("NIGHT_TIME", self.night_time)):
            if value and not _valid_hhmm(value):
                problems.append(f"{name} 格式必须是 HH:MM，留空则关闭，当前: {value!r}")
        for name, value in (
            ("NIGHT_EARLIEST", self.night_earliest),
            ("NIGHT_LATEST", self.night_latest),
        ):
            if self.night_dynamic and not _valid_hhmm(value):
                problems.append(f"{name} 格式必须是 HH:MM，当前: {value!r}")
        if self.history_turns < 1:
            problems.append("HISTORY_TURNS 至少为 1")
        if self.idle_enabled:
            try:
                _parse_window(self.idle_window)
            except ValueError as exc:
                problems.append(str(exc))
            if not 0 <= self.idle_chance <= 1:
                problems.append("IDLE_CHANCE 必须在 0 到 1 之间")
            if self.idle_hours <= 0 or self.idle_min_gap_hours <= 0:
                problems.append("IDLE_HOURS 与 IDLE_MIN_GAP_HOURS 必须大于 0")
            if self.idle_check_minutes < 1:
                problems.append("IDLE_CHECK_MINUTES 至少为 1")
        if self.mood_enabled and self.mood_decay_hours <= 0:
            problems.append("MOOD_DECAY_HOURS 必须大于 0")
        if self.relationship_enabled:
            if self.relationship_daily_cap < 1:
                problems.append("RELATIONSHIP_DAILY_CAP 至少为 1")
            if self.relationship_decay_per_day < 0:
                problems.append("RELATIONSHIP_DECAY_PER_DAY 不能为负数")
            if not 0 <= self.relationship_start_points <= 100:
                problems.append("RELATIONSHIP_START_POINTS 必须在 0-100")
        if self.life_enabled:
            if self.life_tick_minutes < 5:
                problems.append("LIFE_TICK_MINUTES 至少为 5")
            if not 0 <= self.life_event_chance <= 1:
                problems.append("LIFE_EVENT_CHANCE 必须在 0 到 1 之间")
        if self.habits_enabled:
            if not (0 <= self.habits_hour <= 23):
                problems.append("HABITS_HOUR 必须在 0-23")
            if not (0 <= self.habits_minute <= 59):
                problems.append("HABITS_MINUTE 必须在 0-59")
        if self.emoji_auto_fetch:
            if not (0 <= self.emoji_fetch_hour <= 23):
                problems.append("EMOJI_FETCH_HOUR 必须在 0-23")
            if not (0 <= self.emoji_fetch_minute <= 59):
                problems.append("EMOJI_FETCH_MINUTE 必须在 0-59")
        if self.recover_missed:
            if self.recover_hours <= 0:
                problems.append("RECOVER_HOURS 必须大于 0")
            if self.recover_max < 1:
                problems.append("RECOVER_MAX 至少为 1")
        if self.commitments_enabled:
            if self.commitment_check_minutes < 1:
                problems.append("COMMITMENT_CHECK_MINUTES 至少为 1")
            if self.meet_hours <= 0:
                problems.append("MEET_HOURS 必须大于 0")
        if self.weather_enabled and self.weather_refresh_hours < 1:
            problems.append("WEATHER_REFRESH_HOURS 至少为 1")
        if self.vision_enabled and self.vision_max_images < 1:
            problems.append("VISION_MAX_IMAGES 至少为 1")
        if self.longterm_enabled:
            if not (0 <= self.longterm_summary_hour <= 23):
                problems.append("LONGTERM_SUMMARY_HOUR 必须在 0-23")
            if not (0 <= self.longterm_summary_minute <= 59):
                problems.append("LONGTERM_SUMMARY_MINUTE 必须在 0-59")
        if not 0 <= self.reply_chance <= 1:
            problems.append("REPLY_CHANCE 必须在 0 到 1 之间")
        if self.reply_debounce_seconds < 0 or self.reply_delay_min < 0:
            problems.append("回复延迟不能为负数")
        if self.reply_delay_max < self.reply_delay_min:
            problems.append("REPLY_DELAY_MAX 不能小于 REPLY_DELAY_MIN")
        if self.quiet_hours < 0:
            problems.append("QUIET_HOURS 不能为负数")
        if self.topic_quiet_minutes <= 0:
            problems.append("TOPIC_QUIET_MINUTES 必须大于 0")
        if self.voice_max_chars < 1:
            problems.append("VOICE_MAX_CHARS 至少为 1")
        if self.tts_backend not in ("edge", "cosyvoice"):
            problems.append("TTS_BACKEND 只能是 edge 或 cosyvoice")
        if self.tts_backend == "cosyvoice" and self.cosyvoice_autostart:
            if self.cosyvoice_idle_minutes < 1:
                problems.append("COSYVOICE_IDLE_MINUTES 至少为 1")
            if self.cosyvoice_start_timeout < 10:
                problems.append("COSYVOICE_START_TIMEOUT 至少为 10 秒")
            if not (self.cosyvoice_dir / "server.py").exists():
                problems.append(
                    f"COSYVOICE_DIR 下找不到 server.py：{self.cosyvoice_dir}"
                )
        return problems


def _valid_hhmm(value: str) -> bool:
    try:
        hour, minute = value.split(":")
        return 0 <= int(hour) <= 23 and 0 <= int(minute) <= 59
    except (ValueError, AttributeError):
        return False


def _parse_window(value: str):
    try:
        start_text, end_text = value.split("-")
        from datetime import time

        return time.fromisoformat(start_text.strip()), time.fromisoformat(
            end_text.strip()
        )
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"IDLE_WINDOW 格式应为 HH:MM-HH:MM，当前: {value!r}") from exc
