import random


def make_typo(text: str, rng=random) -> str | None:
    """把相邻两个字交换，模拟手滑打错。"""
    text = text.strip()
    if len(text) < 4:
        return None
    index = rng.randint(1, len(text) - 2)
    typo = text[:index] + text[index + 1] + text[index] + text[index + 2 :]
    return typo if typo != text else None
