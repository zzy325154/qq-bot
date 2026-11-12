"""情侣之间的冷战：怎么触发、持续多久、期间怎么说话。"""

from datetime import timedelta

APOLOGY_WORDS = (
    "对不起",
    "我错了",
    "抱歉",
    "别生气",
    "哄你",
    "原谅",
    "理理我",
    "别不理我",
)
COLD_LEVELS = {1: timedelta(hours=3), 2: timedelta(hours=6)}

COLD_PROMPT = (
    "# 你们在冷战（内部设定）\n"
    "你还在生他的气，但也不是真想断。回复要短（一般 2–8 个字），"
    "语气冷、不带表情、不撒娇、不主动找话题，也别先道歉。"
    "他要是一直哄你，可以稍微松一点口，但别马上就没事了。"
)

SOFT_PROMPT = (
    "# 他刚哄你了（内部设定）\n"
    "你气消了一点，但嘴上还要别扭，可以带一句抱怨，别立刻变得很甜。"
)

END_LINES = ("算了 不跟你计较", "气消了 下不为例", "懒得跟你生气")


def is_apology(text: str) -> bool:
    return any(word in (text or "") for word in APOLOGY_WORDS)
