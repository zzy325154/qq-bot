from datetime import date

FIXED = {
    (1, 1): "元旦",
    (2, 14): "情人节",
    (3, 8): "妇女节",
    (5, 1): "劳动节",
    (6, 1): "儿童节",
    (10, 1): "国庆节",
    (12, 24): "平安夜",
    (12, 25): "圣诞节",
}

LUNAR = {
    (1, 1): "春节",
    (1, 15): "元宵节",
    (5, 5): "端午节",
    (8, 15): "中秋节",
    (9, 9): "重阳节",
}


def today_holiday(day: date | None = None) -> str | None:
    day = day or date.today()
    fixed = FIXED.get((day.month, day.day))
    if fixed:
        return fixed
    try:
        from lunardate import LunarDate
    except ImportError:
        return None
    try:
        lunar = LunarDate.from_solar_date(day.year, day.month, day.day)
    except Exception:
        return None
    return LUNAR.get((lunar.month, lunar.day))
