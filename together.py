"""识别「她答应了和你一起做某事」，把它记成共同经历。"""

GAME_WORDS = (
    "王者", "游戏", "吃鸡", "排位", "开黑", "双排", "第五人格", "原神", "金铲铲",
)
INVITE_WORDS = ("陪我", "一起", "上号", "来打", "开黑", "双排", "带我")
REFUSE_WORDS = (
    "不玩", "不打", "不陪", "不去", "算了", "改天", "明天", "太晚", "困",
    "睡了", "没空", "不了", "下次",
)
AGREE_WORDS = ("行", "好", "来", "可以", "上号", "打吧", "陪你", "走吧")


def detect(context: str, reply: str) -> tuple[str, str] | None:
    """context 是最近几轮对话（邀请可能在前一轮），reply 是她刚回的这句。"""
    context = context or ""
    reply = reply or ""
    game = next((word for word in GAME_WORDS if word in context), "")
    if not game:
        return None
    if not any(word in context for word in INVITE_WORDS):
        return None
    if any(word in reply for word in REFUSE_WORDS):
        return None
    if not any(word in reply for word in AGREE_WORDS):
        return None
    label = "王者荣耀" if game == "王者" else game
    return f"和浅井昭星一起打{label}", f"和他一起打了两把{label}"
