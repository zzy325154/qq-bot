import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


class HabitStore:
    """从真实对话里确认下来的说话习惯，叠加在人设之后。"""

    def __init__(self, path: Path, limit: int = 12):
        self.path = Path(path)
        self.limit = limit
        self.habits: list[str] = []
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("读取说话习惯失败: %s", exc)
            return
        if isinstance(data, list):
            self.habits = [str(item) for item in data if str(item).strip()]

    def _save(self) -> None:
        try:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(self.habits, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            tmp.replace(self.path)
        except OSError as exc:
            logger.warning("保存说话习惯失败: %s", exc)

    def all(self) -> list[str]:
        return list(self.habits)

    def add_many(self, items: list[str]) -> int:
        added = 0
        for item in items:
            text = item.strip()
            if not text or text in self.habits:
                continue
            self.habits.append(text)
            added += 1
        self.habits = self.habits[-self.limit :]
        if added:
            self._save()
        return added

    def remove(self, index: int) -> bool:
        if 1 <= index <= len(self.habits):
            self.habits.pop(index - 1)
            self._save()
            return True
        return False

    def text(self) -> str:
        if not self.habits:
            return ""
        lines = "\n".join(f"- {item}" for item in self.habits)
        return "# 你最近养成的说话习惯（自然带入，不要刻意重复）\n" + lines


def parse_candidates(raw: str, max_items: int = 3) -> list[str]:
    items: list[str] = []
    for line in raw.splitlines():
        text = re.sub(r"^\s*(?:\d+[.、)）]|[-*•])\s*", "", line).strip()
        text = text.strip("「」\"'“”‘’（）() ")
        if not text or len(text) > 40:
            continue
        if text not in items:
            items.append(text)
    return items[:max_items]
