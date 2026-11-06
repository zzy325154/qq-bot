import random
import re

LOW_CONTENT = {
    "嗯", "哦", "噢", "好", "行", "在", "啊", "哈", "嘿", "呵", "额", "呃",
    "？", "?", "。", "...", "…", "6", "草",
}
GOODNIGHT_WORDS = ("晚安", "睡了", "不聊了", "拜拜", "再见", "先这样", "我去睡", "下了")
WAKE_WORDS = ("在吗", "在么", "在不在", "醒了吗", "起床", "理我", "出来", "别装死")
TOPIC_END_PHRASES = {
    "好", "好的", "好滴", "行", "行吧", "嗯", "嗯嗯", "哦", "噢", "知道了",
    "明白了", "可以", "没事了", "就这样", "先这样", "谢谢", "收到", "ok",
}
NEW_TOPIC_MARKERS = (
    "？", "?", "对了", "还有", "顺便", "问你", "帮我", "那个", "在吗", "我想",
    "能不能", "怎么样", "为什么", "怎么",
)
TOPIC_END_LONG = ("先这样", "就这样", "没事了", "知道了", "明白了", "谢谢")
ACK_ONLY = {"好的啊", "好啊", "好呀", "行啊", "可以啊", "好吧", "好滴", "嗯嗯", "哦哦"}


def is_low_content(text: str) -> bool:
    compact = re.sub(r"[\s\W_]+", "", text)
    return len(compact) <= 2 or compact in LOW_CONTENT


def contains_any(text: str, words: tuple[str, ...]) -> bool:
    return any(word in text for word in words)


def is_goodnight(text: str) -> bool:
    return len(text) <= 30 and contains_any(text, GOODNIGHT_WORDS)


def is_wake(text: str) -> bool:
    return contains_any(text, WAKE_WORDS)


def starts_new_topic(text: str) -> bool:
    return contains_any(text, NEW_TOPIC_MARKERS)


def is_topic_end(text: str) -> bool:
    if len(text) > 16 or "?" in text or "？" in text:
        return False
    compact = re.sub(r"[\s\W_]+", "", text)
    if compact in ACK_ONLY:
        return False
    if compact in TOPIC_END_PHRASES:
        return True
    return contains_any(text, TOPIC_END_LONG)


def is_ack(text: str) -> bool:
    compact = re.sub(r"[\s\W_]+", "", text)
    return compact in ACK_ONLY


def should_skip(
    text: str,
    mood_level: int,
    reply_chance: float,
    rng=random.random,
) -> bool:
    if is_low_content(text):
        return rng() < 0.6
    if mood_level >= 3:
        return rng() < 0.5
    if mood_level == 2:
        return rng() < 0.25
    return rng() > reply_chance


def reply_delay(
    mood_level: int,
    delay_min: float,
    delay_max: float,
    rng=random.uniform,
) -> float:
    return min(15.0, rng(delay_min, delay_max) + mood_level * 0.8)
