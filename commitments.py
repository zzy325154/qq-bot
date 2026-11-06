import json
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

ACTIVE_STATUS = {"scheduled", "arrived", "met"}


def _as_aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.astimezone()


def parse_commitments(raw: str) -> list[dict]:
    text = raw.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    match = re.search(r"\[[\s\S]*\]", text)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    return [item for item in data if isinstance(item, dict) and item.get("text")]


def parse_due(value) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.strip())
    except ValueError:
        return None


class CommitmentStore:
    """她明确答应、且带具体时间的约定。"""

    def __init__(self, path: Path, limit: int = 5):
        self.path = Path(path)
        self.limit = limit
        self.items: list[dict] = []
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("读取约定失败: %s", exc)
            return
        if isinstance(data, list):
            self.items = [item for item in data if isinstance(item, dict) and item.get("due_at")]

    def _save(self) -> None:
        try:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.items, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.path)
        except OSError as exc:
            logger.warning("保存约定失败: %s", exc)

    def add(self, text: str, due_at: datetime, now: datetime | None = None) -> dict | None:
        text = " ".join(str(text).split())[:60]
        if not text:
            return None
        now = _as_aware(now or datetime.now().astimezone())
        due = _as_aware(due_at)
        if not (now < due <= now + timedelta(days=7)):
            return None
        for item in self.items:
            if item.get("status") in ACTIVE_STATUS and item.get("text") == text:
                return None
        next_id = max((int(item.get("id", 0)) for item in self.items), default=0) + 1
        item = {
            "id": next_id,
            "text": text,
            "due_at": due.isoformat(),
            "status": "scheduled",
            "created_at": now.isoformat(),
        }
        self.items.append(item)
        self.items = self.items[-self.limit :]
        self._save()
        logger.info("记录约定：%s @ %s", text, due.strftime("%m-%d %H:%M"))
        return item

    def due(self, now: datetime) -> list[dict]:
        now = _as_aware(now)
        out = []
        for item in self.items:
            if item.get("status") != "scheduled":
                continue
            try:
                due = datetime.fromisoformat(item["due_at"])
            except (KeyError, ValueError):
                continue
            if _as_aware(due) <= now:
                out.append(item)
        return out

    def mark(self, item_id: int, status: str) -> None:
        for item in self.items:
            if int(item.get("id", 0)) == int(item_id):
                item["status"] = status
                self._save()
                return

    def latest_active(self) -> dict | None:
        active = [item for item in self.items if item.get("status") in ACTIVE_STATUS]
        return active[-1] if active else None

    def remove(self, index: int) -> bool:
        active = [item for item in self.items if item.get("status") in ACTIVE_STATUS]
        if not (1 <= index <= len(active)):
            return False
        target = active[index - 1]
        self.items = [item for item in self.items if item is not target]
        self._save()
        return True

    def status_text(self, now: datetime) -> str:
        active = [
            item for item in self.items if item.get("status") in ACTIVE_STATUS
        ]
        if not active:
            return "现在没有约定。"
        lines = []
        for item in active:
            try:
                due = datetime.fromisoformat(item["due_at"])
            except ValueError:
                continue
            state = {"scheduled": "还没到", "arrived": "已到点", "met": "已见面"}.get(
                item.get("status"), item.get("status")
            )
            lines.append(f"{item['id']}. {due:%m-%d %H:%M} {item['text']}（{state}）")
        return "约定：\n" + "\n".join(lines) if lines else "现在没有约定。"
