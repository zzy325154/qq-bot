import logging

import httpx

logger = logging.getLogger(__name__)

CONDITIONS = [
    (("thunder", "thundery"), "雷阵雨"),
    (("blizzard", "snow", "sleet", "ice"), "雪"),
    (("torrential", "heavy rain"), "大雨"),
    (("rain", "shower", "drizzle"), "雨"),
    (("fog", "mist"), "雾"),
    (("haze", "smoke", "smoky"), "霾"),
    (("overcast",), "阴"),
    (("cloud",), "多云"),
    (("sunny", "clear"), "晴"),
]


def describe(desc: str) -> str:
    lower = (desc or "").lower()
    for words, cn in CONDITIONS:
        if any(word in lower for word in words):
            return cn
    return desc or "未知"


def _num(value) -> str:
    try:
        return str(round(float(value)))
    except (TypeError, ValueError):
        return str(value)


def format_weather(data: dict, city: str = "") -> str | None:
    try:
        current = data["current_condition"][0]
        today = data["weather"][0]
    except (KeyError, IndexError, TypeError):
        return None
    desc = describe(current["weatherDesc"][0]["value"])
    low = today.get("mintempC", "?")
    high = today.get("maxtempC", "?")
    now = current.get("temp_C", "?")
    name = city or "你那边"
    return f"{name}今天{desc}，{_num(low)}–{_num(high)}℃，现在 {_num(now)}℃"


WMO = {
    0: "晴",
    1: "晴间多云",
    2: "多云",
    3: "阴",
    45: "雾",
    48: "雾",
    51: "毛毛雨",
    53: "毛毛雨",
    55: "毛毛雨",
    56: "冻雨",
    57: "冻雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    66: "冻雨",
    67: "冻雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    77: "雪粒",
    80: "阵雨",
    81: "强阵雨",
    82: "暴雨",
    85: "阵雪",
    86: "强阵雪",
    95: "雷阵雨",
    96: "雷暴冰雹",
    99: "雷暴冰雹",
}


def describe_code(code) -> str:
    try:
        return WMO.get(int(code), "未知")
    except (TypeError, ValueError):
        return "未知"


async def fetch_weather(city: str) -> str | None:
    try:
        text = await _fetch_wttr(city)
        if text:
            return text
    except Exception as exc:
        logger.warning("wttr 天气源失败，改用备用源: %s", exc)
    return await _fetch_open_meteo(city)


async def _fetch_wttr(city: str) -> str | None:
    url = f"https://wttr.in/{city or ''}"
    params = {"format": "j1", "lang": "zh"}
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(15.0, connect=8.0),
        trust_env=False,
        headers={"User-Agent": "Mozilla/5.0"},
    ) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        data = response.json()
    return format_weather(data, city)


async def _fetch_open_meteo(city: str) -> str | None:
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(20.0, connect=8.0),
        trust_env=False,
        headers={"User-Agent": "Mozilla/5.0"},
    ) as client:
        geo = await client.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city or "上海", "count": 1, "language": "zh"},
        )
        geo.raise_for_status()
        results = geo.json().get("results") or []
        if not results:
            return None
        place = results[0]
        forecast = await client.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": place["latitude"],
                "longitude": place["longitude"],
                "daily": "weather_code,temperature_2m_max,temperature_2m_min",
                "current": "temperature_2m,weather_code",
                "timezone": "Asia/Shanghai",
            },
        )
        forecast.raise_for_status()
        data = forecast.json()
    current = data.get("current") or {}
    daily = data.get("daily") or {}
    codes = daily.get("weather_code") or []
    desc = describe_code(codes[0] if codes else current.get("weather_code"))
    low = (daily.get("temperature_2m_min") or ["?"])[0]
    high = (daily.get("temperature_2m_max") or ["?"])[0]
    now = current.get("temperature_2m", "?")
    return f"{city or place.get('name', '你那边')}今天{desc}，{_num(low)}–{_num(high)}℃，现在 {_num(now)}℃"

