def pick_missed(
    items: list[dict],
    last_ts: int,
    now_ts: int,
    hours: float = 2.0,
    limit: int = 3,
) -> list[dict]:
    """从历史消息里挑出机器人离线期间收到、还值得回的消息。"""
    cutoff = now_ts - int(hours * 3600)
    picked = [
        item
        for item in items
        if int(item.get("ts", 0)) > last_ts and int(item.get("ts", 0)) >= cutoff
    ]
    picked.sort(key=lambda item: int(item.get("ts", 0)))
    return picked[-limit:]
