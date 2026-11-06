import json
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot import extract_text, split_message
from config import Config
from memory import ChatMemory
from reminders import (
    TZ,
    ReminderStore,
    next_run_at,
    parse_remind_command,
)

passed = 0
failed: list[str] = []


def check(name: str, condition: bool) -> None:
    global passed
    if condition:
        passed += 1
    else:
        failed.append(name)


def test_extract_text() -> None:
    check("纯字符串", extract_text("你好") == "你好")
    segments = [
        {"type": "at", "data": {"qq": "123"}},
        {"type": "text", "data": {"text": " 你好"}},
        {"type": "face", "data": {"id": "1"}},
    ]
    check("分段消息", extract_text(segments) == "@123 你好")
    check("空消息", extract_text([]) == "")
    check("None 消息", extract_text(None) == "")


def test_split_message() -> None:
    check("短消息不切", split_message("你好") == ["你好"])
    check("空消息不切", split_message("   ") == [])
    long_text = "啊" * 2500
    chunks = split_message(long_text, limit=1200)
    check("长消息切分", len(chunks) == 3)
    check("切分不丢字符", "".join(chunks) == long_text)
    multiline = "第一行\n" + "第二行" * 500
    check("按行切分", all(len(c) <= 1200 for c in split_message(multiline)))


def test_parse_remind() -> None:
    check("正常提醒", parse_remind_command("08:30 开会") == ("08:30", "开会"))
    check("单位数小时", parse_remind_command("9:05 吃药") == ("09:05", "吃药"))
    check("缺内容", parse_remind_command("09:05") is None)
    check("时间越界", parse_remind_command("25:00 睡觉") is None)
    check("格式错误", parse_remind_command("明天 开会") is None)


def test_next_run_at() -> None:
    now = datetime(2026, 10, 31, 9, 0, tzinfo=TZ)
    same_day = next_run_at("10:00", now)
    check("当天未到", same_day == datetime(2026, 10, 31, 10, 0, tzinfo=TZ))
    next_day = next_run_at("08:00", now)
    check("已过则顺延", next_day == datetime(2026, 11, 1, 8, 0, tzinfo=TZ))


def test_memory() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "memory.json"
        mem = ChatMemory(path, max_turns=2)
        for i in range(4):
            mem.append(1, "user", f"u{i}")
            mem.append(1, "assistant", f"a{i}")
        history = mem.history(1)
        check("按轮数裁剪", len(history) == 4)
        check("保留最新内容", history[-1]["content"] == "a3")
        check("文件已落盘", path.exists())

        reloaded = ChatMemory(path, max_turns=2)
        check("重启后记忆仍在", reloaded.history(1) == history)

        messages = reloaded.build_messages(1, "系统提示", "新问题")
        check("消息顺序", messages[0]["role"] == "system" and messages[-1]["content"] == "新问题")
        check("历史带时间戳", messages[2]["content"].startswith("[") and "u2" in messages[2]["content"])
        check("提醒相对时间", any("明天" in m["content"] for m in messages if "方括号" in m["content"]))

        dropped = reloaded.drop_trailing(1, "assistant")
        check(
            "能删掉末尾同角色条目",
            dropped == 1 and reloaded.history(1)[-1]["role"] == "user",
        )

        reloaded.clear(1)
        check("清空记忆", reloaded.history(1) == [])


def test_reminders() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "reminders.json"
        store = ReminderStore(path)
        fire_at = datetime.now(TZ) + timedelta(hours=1)
        item = store.add(10001, fire_at, "喝水")
        check("新增提醒", len(store.pending()) == 1)
        check("提醒 id 递增", item.id == 1)

        reloaded = ReminderStore(path)
        check("重启后提醒仍在", len(reloaded.pending()) == 1)
        check("取消提醒", reloaded.remove(1) is True)
        check("重复取消返回 False", reloaded.remove(1) is False)

        old = loaded_id = None
        past = datetime.now(TZ) - timedelta(minutes=5)
        old = reloaded.add(10001, past, "过期事项")
        loaded_id = old.id
        expired = reloaded.expired()
        check("识别过期提醒", any(r.id == loaded_id for r in expired))
        reloaded.drop_expired()
        check("清理过期提醒", all(r.id != loaded_id for r in reloaded.pending()))


def test_reply_formatting() -> None:
    from bot import BotApp

    check("去掉角色前缀", BotApp._clean_reply("对方.：在啊") == "在啊")
    bubbles = BotApp._split_bubbles("在啊\n干嘛\n[表情]")
    check("按行拆气泡", bubbles == ["在啊", "干嘛", "[表情]"])
    long_line = "今天真的超级无敌累" * 6
    parts = BotApp._split_bubbles(long_line, limit=20)
    check("长句会自动切", len(parts) > 1 and all(len(p) <= 24 for p in parts))
    check("最多四条", len(BotApp._split_bubbles("\n".join(["1"] * 10))) == 4)


def test_emoji_filter() -> None:
    try:
        from archive.fetch_emojis import allowed_name
    except ImportError:
        return  # 表情抓取模块未包含在开源版中

    check("普通表情名放行", allowed_name("猫和老鼠00093-疑问问号.jpg"))
    check("恋爱词被拦截", not allowed_name("亲亲抱抱.jpg"))
    check("英文恋爱词被拦截", not allowed_name("love-you.gif"))


def test_web_tools() -> None:
    import asyncio

    from webtools import TOOLS, WebTools, extract_text, is_safe_url

    check("拒绝 127.0.0.1", not is_safe_url("http://127.0.0.1/x"))
    check("拒绝 localhost", not is_safe_url("http://localhost/x"))
    check("拒绝非 http 协议", not is_safe_url("ftp://example.com/x"))
    check("拒绝私有网段", not is_safe_url("http://192.168.1.1/x"))
    html = "<html><script>bad()</script><body><article><p>正文内容</p></article></body></html>"
    check("提取正文并去脚本", extract_text(html) == "正文内容")
    check("工具数量", len(TOOLS) == 2)
    result = asyncio.run(WebTools(proxy="").execute("web_search", "{}"))
    check("缺参数有提示", "缺少" in result)


def test_idle_logic() -> None:
    from datetime import time

    from idle import StateStore, in_window, parse_window, should_idle_chat

    window = parse_window("09:00-23:00")
    check("窗口内", in_window(time(10, 0), window))
    check("窗口外", not in_window(time(8, 0), window))
    overnight = parse_window("20:00-02:00")
    check(
        "跨夜窗口",
        in_window(time(1, 0), overnight)
        and in_window(time(21, 0), overnight)
        and not in_window(time(10, 0), overnight),
    )

    now = datetime(2026, 10, 31, 12, 0, tzinfo=TZ)
    check(
        "静默不足不触发",
        not should_idle_chat(
            now, now - timedelta(hours=2), None, window, 4, 6, 1.0, rng=lambda: 0.0
        ),
    )
    check(
        "满足条件触发",
        should_idle_chat(
            now, now - timedelta(hours=5), None, window, 4, 6, 1.0, rng=lambda: 0.0
        ),
    )
    check(
        "概率未中不触发",
        not should_idle_chat(
            now, now - timedelta(hours=5), None, window, 4, 6, 0.0, rng=lambda: 0.9
        ),
    )
    check(
        "间隔不足不触发",
        not should_idle_chat(
            now,
            now - timedelta(hours=5),
            now - timedelta(hours=2),
            window,
            4,
            6,
            1.0,
            rng=lambda: 0.0,
        ),
    )

    with tempfile.TemporaryDirectory() as tmp:
        state = StateStore(Path(tmp) / "state.json")
        state.set("last_user_at", "2026-10-31T12:00:00+08:00")
        reloaded = StateStore(Path(tmp) / "state.json")
        check("状态持久化", reloaded.get("last_user_at").startswith("2026-10-31"))


def test_mood_tiers() -> None:
    from idle import mood_for_silence

    check("3h 平静", mood_for_silence(3)[0] == "平静")
    check("7h 有点在意", mood_for_silence(7)[0] == "有点在意")
    check("14h 不高兴", mood_for_silence(14)[0] == "不高兴")
    check("30h 明显生气", mood_for_silence(30)[0] == "明显生气")
    check("50h 赌气冷淡", mood_for_silence(50)[0] == "赌气冷淡")
    check("越久越有提示", bool(mood_for_silence(30)[1]))


def test_longterm() -> None:
    from longterm import ChatLog, NoteStore, format_notes, parse_notes

    check("解析 JSON 记忆", parse_notes('["他下周考试","她喜欢猫"]') == ["他下周考试", "她喜欢猫"])
    check("解析行式记忆", parse_notes("- 第一条\n- 第二条") == ["第一条", "第二条"])
    check(
        "记忆带日期",
        format_notes([{"created_at": "2026-11-05T21:45", "text": "一起打王者"}])
        == "[11-05] 一起打王者",
    )

    with tempfile.TemporaryDirectory() as tmp:
        log = ChatLog(Path(tmp) / "chat.jsonl")
        log.append("user", "你好")
        log.append("assistant", "在")
        records = log.since(None)
        check("对话日志追加", len(records) == 2)
        check("对话日志按时间过滤", len(log.since(records[0]["ts"])) == 1)

        store = NoteStore(Path(tmp) / "notes.json")
        added = store.add_many(["他下周要考试", "她喜欢猫"], "a", "b")
        check("记忆新增", added == 2)
        check("记忆检索", any("考试" in n["text"] for n in store.search("考试")))
        reloaded = NoteStore(Path(tmp) / "notes.json")
        check("记忆持久化", len(reloaded.notes) == 2)
        note_id = reloaded.notes[0]["id"]
        check("记忆删除", reloaded.remove(note_id) and len(reloaded.notes) == 1)


def test_mood_continuity() -> None:
    from idle import decay_mood, level_for_silence, mood_by_level

    check("7h 等级 1", level_for_silence(7) == 1)
    check("13h 等级 2", level_for_silence(13) == 2)
    check("25h 等级 3", level_for_silence(25) == 3)
    check("50h 等级 4", level_for_silence(50) == 4)
    now = datetime(2026, 10, 31, 12, 0, tzinfo=TZ)
    check("7 小时后衰减两级", decay_mood(4, now - timedelta(hours=7), now, 3) == 2)
    check("衰减到底", decay_mood(1, now - timedelta(hours=10), now, 3) == 0)
    check("等级文案", mood_by_level(3)[0] == "明显生气")


def test_extract_images() -> None:
    from bot import extract_images

    segments = [
        {"type": "image", "data": {"file": "a.jpg"}},
        {"type": "text", "data": {"text": "hi"}},
    ]
    check("提取图片段", extract_images(segments) == [{"file": "a.jpg"}])
    check("没有图片返回空", extract_images("纯文本") == [])


def test_summarize_pipeline() -> None:
    import asyncio

    from idle import StateStore
    from longterm import ChatLog, NoteStore, summarize_pending

    class FakeLLM:
        async def chat(self, messages, temperature=0.0):
            return '["他下周要考试","她最近在准备面试"]'

    with tempfile.TemporaryDirectory() as tmp:
        log = ChatLog(Path(tmp) / "chat.jsonl")
        for index in range(6):
            log.append("user" if index % 2 == 0 else "assistant", f"消息{index}")
        notes = NoteStore(Path(tmp) / "notes.json")
        state = StateStore(Path(tmp) / "state.json")
        added = asyncio.run(summarize_pending(FakeLLM(), log, notes, state))
        check("摘要新增条数", added == 2)
        check("摘要写入记忆", len(notes.notes) == 2)
        check("摘要游标更新", bool(state.get("last_summary_ts")))
        again = asyncio.run(summarize_pending(FakeLLM(), log, notes, state))
        check("无新消息不重复摘要", again == 0)


def test_pacing() -> None:
    import pacing

    check("低内容识别", pacing.is_low_content("嗯") and pacing.is_low_content("？"))
    check("正常内容放行", not pacing.is_low_content("今天考试好难"))
    check("晚安识别", pacing.is_goodnight("睡了，晚安"))
    check("唤醒词识别", pacing.is_wake("在吗"))
    check("好的啊不算收尾", not pacing.is_topic_end("好的啊") and pacing.is_ack("好的啊"))
    check("知道了算收尾", pacing.is_topic_end("知道了"))
    check(
        "概率不回",
        pacing.should_skip("随便聊聊", 0, 0.9, rng=lambda: 0.95),
    )
    check(
        "概率回复",
        not pacing.should_skip("随便聊聊", 0, 0.9, rng=lambda: 0.5),
    )
    check(
        "生气更容易不回",
        pacing.should_skip("随便聊聊", 3, 0.9, rng=lambda: 0.4),
    )
    check(
        "低内容更容易不回",
        pacing.should_skip("嗯", 0, 0.9, rng=lambda: 0.3),
    )
    check("延迟随情绪增加", pacing.reply_delay(3, 1, 2, rng=lambda a, b: a) >= 3)
    check("收尾识别-好的", pacing.is_topic_end("好的"))
    check("收尾识别-知道了", pacing.is_topic_end("知道了"))
    check("带问题不算收尾", not pacing.is_topic_end("好的，明天去哪"))
    check("正常话题不算收尾", not pacing.is_topic_end("今天天气怎么样"))
    check("新话题识别", pacing.starts_new_topic("对了，问你个事"))
    check("收尾不是新话题", not pacing.starts_new_topic("好的"))


def test_voice() -> None:
    from bot import BotApp
    from voice import CURATED_VOICES

    check("音色数量", len(CURATED_VOICES) >= 10)
    check(
        "解析音色全名",
        BotApp._resolve_voice("zh-CN-XiaoxiaoNeural") == "zh-CN-XiaoxiaoNeural",
    )
    check("解析音色中文名", BotApp._resolve_voice("晓伊") == "zh-CN-XiaoyiNeural")
    check("无效音色返回空", BotApp._resolve_voice("不存在") is None)


def test_greeting_variety() -> None:
    from bot import NIGHT_FALLBACKS, is_flat_night_reply

    check("裸晚安算敷衍", is_flat_night_reply("晚安"))
    check("带标点晚安算敷衍", is_flat_night_reply("晚安。"))
    check("带表情晚安算敷衍", is_flat_night_reply("晚安[表情]"))
    check("睡了算敷衍", is_flat_night_reply("睡了"))
    check("没有睡前意思算敷衍", is_flat_night_reply("番茄炸鸡饭别忘了"))
    check("有内容的晚安不算", not is_flat_night_reply("眼睛都睁不开了 你也早点睡"))
    check("兜底文案都不敷衍", all(not is_flat_night_reply(t) for t in NIGHT_FALLBACKS))


def test_cosyvoice_lazy() -> None:
    import asyncio

    from voice import TTSError, TTSClient

    cfg = Config()
    check("CosyVoice 默认按需启动", cfg.cosyvoice_autostart)
    check("闲置默认 15 分钟", cfg.cosyvoice_idle_minutes == 15)

    tmp = Path(tempfile.mkdtemp())
    client = TTSClient(
        backend="cosyvoice",
        autostart=True,
        cosyvoice_dir=cfg.cosyvoice_dir,
        idle_seconds=600,
        out_dir=tmp,
    )
    check("能找到启动命令", client._spawn_command() is not None)
    check("闲置时间会传给子进程", client.idle_seconds == 600)

    client.cosyvoice_url = "http://127.0.0.1:59999"
    check("服务未启动时探测为假", asyncio.run(client._probe(0.3)) is False)

    off = TTSClient(backend="cosyvoice", autostart=False, out_dir=tmp)
    off.cosyvoice_url = "http://127.0.0.1:59999"
    try:
        asyncio.run(off.ensure_service())
    except TTSError:
        check("关闭自动启动时会报错", True)
    else:
        check("关闭自动启动时会报错", False)


def test_voice_styles() -> None:
    from voice import pick_voice_style

    instructs = {
        pick_voice_style(mood, stage, rng=lambda r=r: r)[0]
        for mood in range(5)
        for stage in range(5)
        for r in (0.0, 0.5, 0.99)
    }
    check("暂不使用语气指令", instructs == {""})
    speeds = [pick_voice_style(0, 2, rng=lambda r=r: r)[1] for r in (0.0, 0.5, 0.99)]
    check("语速抖动在合理范围", all(0.95 <= s <= 1.05 for s in speeds))


def test_emoji_cute() -> None:
    try:
        from archive.fetch_emojis import tone_score
    except ImportError:
        return  # 表情抓取模块未包含在开源版中

    check("可爱词加分", tone_score("超可爱猫咪") > tone_score("离谱沙雕"))
    check("丑图减分", tone_score("丑糊裂开") < tone_score("软萌小猫"))


def test_weather_holiday() -> None:
    from datetime import date

    from holidays import today_holiday
    from weather import describe, describe_code, format_weather

    check("元旦能识别", today_holiday(date(2026, 1, 1)) == "元旦")
    check("春节能识别（农历）", today_holiday(date(2026, 2, 17)) == "春节")
    check("中秋能识别（农历）", today_holiday(date(2026, 9, 25)) == "中秋节")
    check("普通日子没有节日", today_holiday(date(2026, 11, 2)) is None)

    data = {
        "current_condition": [
            {"temp_C": "15", "weatherDesc": [{"value": "Smoky haze"}]}
        ],
        "weather": [{"mintempC": "15", "maxtempC": "21"}],
    }
    text = format_weather(data, "上海")
    check("天气文案", bool(text) and "上海" in text and "霾" in text and "15" in text)
    check("天气描述兜底", describe("") == "未知")
    check("天气代码映射", describe_code(0) == "晴" and describe_code(61) == "小雨")


def test_humanness() -> None:
    import random

    from humanness import make_typo

    rng = random.Random(1)
    typo = make_typo("在干嘛呢", rng=rng)
    check("会打错字", typo is not None and typo != "在干嘛呢" and len(typo) == 4)
    check("太短不改", make_typo("嗯") is None)


def test_commitments() -> None:
    from datetime import datetime, timedelta, timezone

    from commitments import CommitmentStore, parse_commitments, parse_due

    tz = timezone(timedelta(hours=8))
    now = datetime(2026, 11, 2, 20, 0, tzinfo=tz)
    store = CommitmentStore(Path(tempfile.mkdtemp()) / "c.json")
    item = store.add("明天6点去接你", now + timedelta(hours=22), now)
    check("记录约定", item is not None)
    check(
        "重复约定不重复记",
        store.add("明天6点去接你", now + timedelta(hours=22), now) is None,
    )
    check("过去的约定不收", store.add("昨天的事", now - timedelta(hours=1), now) is None)
    check("超过七天不收", store.add("下周再说", now + timedelta(days=8), now) is None)

    due = store.due(now + timedelta(hours=23))
    check("到点能取出来", len(due) == 1)
    store.mark(item["id"], "met")
    check("状态会更新", store.latest_active()["status"] == "met")

    raw = '```json\n[{"text": "接你", "due_at": "2026-11-03T18:00:00+08:00"}]\n```'
    parsed = parse_commitments(raw)
    check("解析约定 JSON", bool(parsed) and parsed[0]["text"] == "接你")
    check("解析时间", parse_due(parsed[0]["due_at"]) is not None)
    check("无效时间返回空", parse_due("明天六点") is None)


def test_recover() -> None:
    from recover import pick_missed

    now = 1_000_000
    items = [
        {"ts": now - 5 * 3600, "text": "太旧"},
        {"ts": now - 3600, "text": "一小时前"},
        {"ts": now - 600, "text": "十分钟前"},
        {"ts": now - 60, "text": "一分钟前"},
    ]
    picked = pick_missed(items, now - 7200, now, hours=2, limit=3)
    check("只补最近的", [p["text"] for p in picked] == ["一小时前", "十分钟前", "一分钟前"])
    check("按上限截断", len(pick_missed(items, 0, now, hours=2, limit=1)) == 1)
    check("没有新消息返回空", pick_missed(items, now, now, hours=2, limit=3) == [])


def test_habits() -> None:
    from habits import HabitStore, parse_candidates

    raw = """1. “行吧”
    2. 你少来
    - 又开始了
    4. 这条句子特别特别长已经超过了四十个字的限制所以应该被直接过滤掉不要出现在结果里面啦"""
    items = parse_candidates(raw)
    check("解析习惯候选", items == ["行吧", "你少来", "又开始了"])

    store = HabitStore(Path(tempfile.mkdtemp()) / "habits.json")
    check("添加习惯", store.add_many(["行吧", "你少来"]) == 2)
    check("习惯去重", store.add_many(["行吧"]) == 0)
    check("习惯会注入", "行吧" in store.text())
    check("删除习惯", store.remove(1) and "行吧" not in store.text())
    check("越界删除返回假", not store.remove(99))


def test_avatar() -> None:
    import io

    from PIL import Image

    from avatar import parse_image_urls, save_square

    payload = {
        "data": [
            {"middleURL": "https://img/a.jpg"},
            {"thumbURL": "https://img/b.jpg"},
            {"middleURL": "", "thumbURL": ""},
            {"x": 1},
        ]
    }
    check("解析图片链接", parse_image_urls(payload) == ["https://img/a.jpg", "https://img/b.jpg"])

    buffer = io.BytesIO()
    Image.new("RGB", (800, 600), (120, 30, 30)).save(buffer, "PNG")
    out = Path(tempfile.mkdtemp()) / "a.jpg"
    save_square(buffer.getvalue(), out)
    with Image.open(out) as image:
        check("头像裁成方形", image.size == (640, 640))


def test_life() -> None:
    from datetime import datetime, timedelta, timezone

    from life import LifeState, activity_for_hour

    check("凌晨在睡觉", "睡" in activity_for_hour(3)[0])
    check("中午在吃午饭", "午饭" in activity_for_hour(13)[0])
    check("晚上在追剧", "追剧" in activity_for_hour(21)[0])

    tmp = Path(tempfile.mkdtemp()) / "life.json"
    life = LifeState(tmp)
    life.energy = 50
    start = datetime(2026, 11, 1, 9, 0)
    life.tick(start)
    check("上午在忙事情", "上课" in life.activity)
    life.tick(start + timedelta(hours=1))
    check("精力会随活动下降", life.energy < 50)

    life.add_event("路上踩到一滩水", start)
    check("事件能记下", "踩到一滩水" in life.prompt(start))
    later = start + timedelta(hours=13)
    life.tick(later)
    check("事件会过期", "踩到一滩水" not in life.prompt(later))
    check("状态文本可读", "她现在的状态" in life.status_text())
    check("提示包含日期时间", "11-01 09:00" in life.prompt(start))

    dup = LifeState(Path(tempfile.mkdtemp()) / "life.json")
    first = dup.add_event("外卖到了懒得下楼", start)
    second = dup.add_event("外卖到了我懒得下楼拿", start)
    check("重复的小事会被跳过", first and not second)

    labeled = LifeState(Path(tempfile.mkdtemp()) / "life.json")
    labeled.add_event("和他一起打了两把王者荣耀", start, ttl_hours=48)
    check("新发生的事标成刚刚", "刚刚：和他一起打了两把王者荣耀" in labeled.prompt(start))
    check(
        "隔天的事标成昨天",
        "昨天：和他一起打了两把王者荣耀" in labeled.prompt(start + timedelta(hours=20)),
    )

    aware = LifeState(Path(tempfile.mkdtemp()) / "life.json")
    aware.add_event("时区测试", start.replace(tzinfo=timezone.utc))
    check(
        "带时区事件不报错",
        "时区测试" in aware.prompt(start),
    )

    profile = LifeState(Path(tempfile.mkdtemp()) / "life.json")
    profile.activity = "在睡觉"
    check("睡觉时不该回", profile.reply_profile()[3] is False)
    profile.activity = "在上课或者忙事情"
    busy = profile.reply_profile()
    check("上课会拖很久", busy[0] >= 60 and busy[2] > 0 and busy[3])
    profile.activity = "在宿舍待着，刷手机或者追剧"
    free = profile.reply_profile()
    check("空闲时正常", free[0] == 0 and free[2] == 0 and free[3])


def test_together() -> None:
    from datetime import timedelta

    import together
    from life import LifeState
    from memory import strip_stamp

    check(
        "答应陪玩会记下",
        together.detect("来陪我打王者", "行吧 上号") == (
            "和主人一起打王者荣耀",
            "和他一起打了两把王者荣耀",
        ),
    )
    check("推辞就不算", together.detect("来陪我打王者", "这个点了还打啊") is None)
    check("拒绝不算", together.detect("来陪我打王者", "不打 明天吧") is None)
    check("没邀请不算", together.detect("今天好累", "那早点睡") is None)
    delayed = together.detect(
        "来陪我打王者 这个点了还打啊 现在才几点", "那我陪你打两把 打完就睡"
    )
    check("隔一轮才答应也算", delayed is not None)
    check("时间戳会被去掉", strip_stamp("[11-05 21:41] 那我陪你打两把") == "那我陪你打两把")

    tmp = Path(tempfile.mkdtemp()) / "life.json"
    life = LifeState(tmp)
    start = datetime(2026, 11, 5, 21, 0)
    life.tick(start)
    life.set_activity("和主人一起打王者荣耀", start, hold_hours=2)
    life.tick(start + timedelta(minutes=30))
    check("一起玩的状态会保持", "打王者" in life.activity)
    life.tick(start + timedelta(hours=3))
    check("两小时后回到作息", "打王者" not in life.activity)


def test_bedtime() -> None:
    from datetime import datetime, timedelta, timezone

    import bedtime

    tz = timezone(timedelta(hours=8))
    evening = datetime(2026, 11, 5, 20, 0, tzinfo=tz)
    start, target, end = bedtime.plan(evening, 20, rng=lambda a, b: 0)
    check("精力低就早睡", target == start and target.hour == 22)
    check("窗口跨午夜", end.date() > start.date())

    _, late, _ = bedtime.plan(evening, 95, rng=lambda a, b: 0)
    check("精力足就往后拖", late.hour == 0 and late.date().day == 6)

    just_after_midnight = datetime(2026, 11, 6, 0, 10, tzinfo=tz)
    s2, _, e2 = bedtime.plan(just_after_midnight, 50, rng=lambda a, b: 0)
    check("凌晨仍算前一天的窗口", s2.date().day == 5 and e2.date().day == 6)

    _, _, e3 = bedtime.plan(datetime(2026, 11, 6, 3, 0, tzinfo=tz), 50)
    check("凌晨三点窗口已结束", datetime(2026, 11, 6, 3, 0, tzinfo=tz) > e3)


def test_relationship() -> None:
    from datetime import date, timedelta

    from relationship import Relationship

    tmp = Path(tempfile.mkdtemp()) / "relationship.json"
    day = date(2026, 10, 1)
    rel = Relationship(tmp, daily_cap=6, decay_per_day=2, start_points=0)
    check("起点 0 是普通朋友", rel.stage == 0)
    check("提示词包含阶段", "普通朋友" in rel.prompt())
    check("默认起点是亲近", Relationship(tmp.parent / "b.json").stage == 2)
    off = Relationship(tmp.parent / "c.json", enabled=False)
    check("关闭时状态显示已关闭", "已关闭" in off.status_text())
    check("关闭时不注入", off.prompt() == "")

    plain = Relationship(Path(tempfile.mkdtemp()) / "r.json")
    plain.observe("在吗", day)
    flirt = Relationship(Path(tempfile.mkdtemp()) / "r.json")
    flirt.observe("想你了", day)
    check("暧昧加分更多", flirt.points > plain.points)

    for _ in range(20):
        plain.observe("随便说说", day)
    check("每日加分有上限", plain.today_gain <= 6)

    rel.points = 25
    rel.stage = 0
    rel._recompute()
    check("够分升到熟人", rel.stage == 1)
    rel.points = 15
    rel._recompute()
    check("小幅下降不立刻掉级", rel.stage == 1)
    rel.points = 8
    rel._recompute()
    check("跌破阈值才掉级", rel.stage == 0)

    decay = Relationship(Path(tempfile.mkdtemp()) / "r.json", decay_per_day=2)
    decay.points = 50
    decay.last_message_date = day - timedelta(days=3)
    decay.refresh(day)
    check("久不聊会掉好感", decay.points == 46)

    streak = Relationship(Path(tempfile.mkdtemp()) / "r.json")
    for offset in range(3):
        streak.observe("早", day + timedelta(days=offset))
    check("连续聊会累积天数", streak.streak == 3)

    streak.reset()
    check("重置回到初始", streak.points == 0 and streak.stage == 0)

    cold = Relationship(Path(tempfile.mkdtemp()) / "r.json", start_points=40)
    cold.last_message_date = day
    cold.gain_date = day.isoformat()
    cold.observe("烦不烦", day)
    check("冷话扣 6 分", cold.points == 34)

    proactive = Relationship(Path(tempfile.mkdtemp()) / "r.json", start_points=40)
    check("主动消息加一点", proactive.observe_proactive(day) == 1)
    check("主动加分每天一次", proactive.observe_proactive(day) == 0)
    check("主动加分生效", proactive.points == 41)
    check(
        "普通朋友主动概率更低",
        Relationship(Path(tempfile.mkdtemp()) / "l.json", start_points=0).idle_chance_factor()
        < 1,
    )
    check(
        "情侣主动概率更高",
        Relationship(Path(tempfile.mkdtemp()) / "c.json", start_points=100).idle_chance_factor()
        > 1,
    )
    tmp_dir = tempfile.mkdtemp()
    check(
        "普通朋友等更久才主动",
        Relationship(Path(tmp_dir) / "g0.json", start_points=0).idle_gap_factor() > 1,
    )
    check(
        "情侣更快主动",
        Relationship(Path(tmp_dir) / "g4.json", start_points=100).idle_gap_factor() < 1,
    )
    check(
        "亲近按原间隔",
        Relationship(Path(tmp_dir) / "g2.json", start_points=40).idle_gap_factor() == 1.0,
    )


def test_config_validation() -> None:
    cfg = Config()
    cfg.owner_qq = 0
    cfg.api_key = ""
    problems = cfg.validate()
    check("空配置能报错", any("OWNER_QQ" in p for p in problems))
    check("Key 为空能报错", any("DEEPSEEK_API_KEY" in p for p in problems))

    cfg.owner_qq = 123456
    cfg.api_key = "sk-test"
    cfg.morning_time = "25:00"
    check("时间格式能被拦截", any("MORNING_TIME" in p for p in cfg.validate()))

    cfg.morning_time = ""
    cfg.night_time = "00:00"
    check("问候时间留空不报错", not any("MORNING_TIME" in p for p in cfg.validate()))


def main() -> int:
    test_extract_text()
    test_split_message()
    test_parse_remind()
    test_next_run_at()
    test_memory()
    test_reminders()
    test_reply_formatting()
    test_emoji_filter()
    test_web_tools()
    test_idle_logic()
    test_mood_tiers()
    test_longterm()
    test_mood_continuity()
    test_extract_images()
    test_summarize_pipeline()
    test_pacing()
    test_voice()
    test_greeting_variety()
    test_voice_styles()
    test_emoji_cute()
    test_recover()
    test_weather_holiday()
    test_humanness()
    test_commitments()
    test_habits()
    test_avatar()
    test_life()
    test_together()
    test_bedtime()
    test_relationship()
    test_cosyvoice_lazy()
    test_config_validation()

    print(f"通过 {passed} 项，失败 {len(failed)} 项")
    for name in failed:
        print(f"  失败: {name}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
