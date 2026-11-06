import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path

import jieba

logger = logging.getLogger(__name__)

STOPWORDS = {
    "的", "了", "是", "我", "你", "他", "她", "就", "都", "也", "还", "在",
    "有", "和", "不", "吗", "呢", "吧", "啊", "呀", "哦", "嗯", "这", "那",
}


def format_notes(notes: list[dict], limit_chars: int = 50) -> str:
    """把记忆条目拼成带日期的文本，避免旧事被当成刚发生。"""
    parts = []
    for note in notes:
        stamp = str(note.get("created_at", ""))[:10]
        label = f"[{stamp[5:]}] " if len(stamp) == 10 else ""
        parts.append(label + str(note.get("text", ""))[:limit_chars])
    return "；".join(parts)


class ChatLog:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, role: str, content: str) -> None:
        record = {
            "ts": datetime.now().astimezone().isoformat(),
            "role": role,
            "content": content,
        }
        try:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError as exc:
            logger.warning("写入对话日志失败: %s", exc)

    def since(self, iso_time: str | None) -> list[dict]:
        if not self.path.exists():
            return []
        records = []
        try:
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if iso_time and record.get("ts", "") <= iso_time:
                    continue
                records.append(record)
        except OSError as exc:
            logger.warning("读取对话日志失败: %s", exc)
        return records


class NoteStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.notes: list[dict] = []
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                self.notes = [item for item in raw if isinstance(item, dict)]
        except (OSError, json.JSONDecodeError):
            self.notes = []

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(self.notes, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(tmp, self.path)

    def add_many(self, texts: list[str], period_start: str, period_end: str) -> int:
        next_id = max((int(n.get("id", 0)) for n in self.notes), default=0) + 1
        added = 0
        for text in texts:
            text = text.strip()
            if not text or len(text) > 200:
                continue
            self.notes.append(
                {
                    "id": next_id,
                    "text": text,
                    "created_at": datetime.now().astimezone().isoformat(),
                    "period_start": period_start,
                    "period_end": period_end,
                }
            )
            next_id += 1
            added += 1
        if added:
            self._save()
        return added

    def recent(self, limit: int = 5) -> list[dict]:
        return sorted(
            self.notes, key=lambda n: n.get("created_at", ""), reverse=True
        )[:limit]

    def search(self, query: str, limit: int = 3) -> list[dict]:
        query_tokens = {
            token
            for token in jieba.cut(query)
            if token.strip() and token not in STOPWORDS
        }
        if not query_tokens:
            return self.recent(limit)
        scored = []
        for note in self.notes:
            tokens = set(jieba.cut(note.get("text", "")))
            score = len(query_tokens & tokens)
            if score:
                scored.append((score, note.get("created_at", ""), note))
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [item[2] for item in scored[:limit]]

    def remove(self, note_id: int) -> bool:
        before = len(self.notes)
        self.notes = [n for n in self.notes if int(n.get("id", 0)) != note_id]
        if len(self.notes) != before:
            self._save()
            return True
        return False


def parse_notes(text: str) -> list[str]:
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            if isinstance(data, list):
                return [str(item).strip() for item in data if str(item).strip()]
        except json.JSONDecodeError:
            pass
    notes = []
    for line in text.splitlines():
        line = re.sub(r"^[\s\-\*\d\.、]+", "", line).strip()
        if line and not line.startswith("```"):
            notes.append(line)
    return notes


async def summarize_pending(
    llm,
    chat_log: ChatLog,
    notes: NoteStore,
    state,
    max_messages: int = 120,
) -> int:
    since = state.get("last_summary_ts")
    messages = chat_log.since(since)[-max_messages:]
    if len(messages) < 6:
        return 0

    lines = [
        f"{item.get('ts', '')[0:16]} {('她' if item.get('role') == 'assistant' else '主人')}: {item.get('content', '')[:200]}"
        for item in messages
    ]
    prompt = f"""以下是「对方.」和「主人」最近的一段对话。请提取值得长期记住的信息，供以后聊天时回忆。

只提取这些类型：
- 主人的近况、计划、偏好、重要日期
- 两人的约定、承诺、共同事件
- 关系状态的变化
- 她自己的近况或情绪（如果明确说了）

要求：
- 每条一句话，不超过 60 字
- 只写对话里明确出现的内容，不推测、不编造
- 最多 8 条
- 输出 JSON 数组，例如 ["...","..."]

对话：
{chr(10).join(lines)}"""
    try:
        reply = await llm.chat(
            [{"role": "user", "content": prompt}], temperature=0.2
        )
    except Exception as exc:
        logger.warning("长期记忆摘要失败: %s", exc)
        return 0

    items = parse_notes(reply)
    added = notes.add_many(
        items,
        period_start=messages[0].get("ts", ""),
        period_end=messages[-1].get("ts", ""),
    )
    state.set("last_summary_ts", messages[-1].get("ts", ""))
    logger.info("长期记忆新增 %s 条（处理 %s 条消息）", added, len(messages))
    return added
