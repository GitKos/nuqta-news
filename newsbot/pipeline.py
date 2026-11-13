"""Один «тик»: ежедневные рубрики + одна новость, если подошло время."""
import html
import logging
import re
import time

import requests

from . import card, db, llm, sources, telegram
from .config import CFG, ROOT, UA, channel_link, configured, now

log = logging.getLogger("pipeline")
MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",
          "сентября", "октября", "ноября", "декабря"]
WMO = {0: "ясно", 1: "малооблачно", 2: "переменная облачность", 3: "пасмурно", 45: "туман",
       48: "туман", 51: "морось", 53: "морось", 55: "морось", 61: "небольшой дождь",
       63: "дождь", 65: "сильный дождь", 71: "небольшой снег", 73: "снег", 75: "сильный снег",
       80: "ливни", 81: "ливни", 82: "сильные ливни", 95: "гроза", 96: "гроза", 99: "гроза"}


def footer() -> str:
    link = channel_link()
    title = html.escape(CFG["channel_title"])
    return f'<a href="{link}">{title} — подписаться</a>' if link else title


def publish(photo: bytes | None, text: str, dry: bool, name: str) -> int:
    if dry:
        out = ROOT / "preview"
        out.mkdir(exist_ok=True)
        if photo:
            (out / f"{name}.jpg").write_bytes(photo)
        (out / f"{name}.txt").write_text(text, encoding="utf-8")
        log.info("preview saved: preview/%s", name)
        return 0
    return telegram.send_photo(photo, text) if photo else telegram.send_message(text)


# ── Новость ────────────────────────────────────────────────────────────────
def _tokens(s: str) -> set[str]:
    return {w for w in re.findall(r"\w{4,}", s.lower())}


def _similar(a: str, b: str) -> bool:
    ta, tb = _tokens(a), _tokens(b)
    return bool(ta and tb) and len(ta & tb) / len(ta | tb) > 0.6


def _due_region(day: str) -> str:
    posts = db.posts_of_day(day)
    world = sum(1 for p in posts if p["region"] == "world")
    return "world" if posts and world / len(posts) < CFG["world_share"] else "uz"


def build_caption(art: dict, item) -> str:
    head = f"<b>{html.escape(art['emoji'])} {html.escape(art['headline'])}</b>"
    src = f'Источник: <a href="{html.escape(item["url"])}">{html.escape(item["source"])}</a>'
    body = art["body"].strip()
    while True:
        text = f"{head}\n\n{html.escape(body)}\n\n{src}\n{footer()}"
        visible = len(re.sub(r"<[^>]+>", "", text))
        if visible <= 1000 or "." not in body[:-1]:
            return text
        body = body[: body[:-1].rfind(".") + 1]  # убираем последнее предложение


def post_news(dry: bool) -> bool:
    day = now().strftime("%Y-%m-%d")
    first = _due_region(day)
    for region in (first, "world" if first == "uz" else "uz"):
        for _ in range(3):
            recent = db.recent_posts()
            cands = []
            for c in db.candidates(region, CFG["max_item_age_hours"]):
                if any(_similar(c["title"], r["title"]) for r in recent) or \
                        any(_similar(c["title"], k["title"]) for k in cands):
                    db.set_status(c["id"], "skipped")
                else:
                    cands.append(c)
            if not cands:
                break
            sel = llm.select(cands, recent, region)
            for i in sel.get("duplicates") or []:
                if isinstance(i, int) and 0 <= i < len(cands) and i != sel.get("pick"):
                    db.set_status(cands[i]["id"], "skipped")
            pick = sel.get("pick")
            if not isinstance(pick, int) or not 0 <= pick < len(cands):
                break
            item = cands[pick]
            text = sources.article_text(item["url"])
            if len(text) < 300:
                text = f"{item['summary']}\n{text}"
            if len(text) < 200:
                db.set_status(item["id"], "skipped")
                continue
            art = llm.rewrite(item, text)
            if art.get("skip") or not art.get("headline") or not art.get("body"):
                db.set_status(item["id"], "skipped")
                continue
            art.setdefault("emoji", "📰")
            photo, image_id = card.news_card(art["headline"], region, art.get("image_query", ""))
            mid = publish(photo, build_caption(art, item), dry, f"news_{item['id']}")
            if not dry:
                db.set_status(item["id"], "posted")
                db.add_post(item["id"], day, region, art["headline"], mid, image_id)
            log.info("posted [%s] %s", region, art["headline"])
            return True
    log.info("nothing to post")
    return False


# ── Курсы и погода ─────────────────────────────────────────────────────────
def _weather() -> tuple[str, str]:
    """(короткая строка для картинки, строка для текста)"""
    try:
        w = CFG["weather"]
        d = requests.get("https://api.open-meteo.com/v1/forecast", timeout=20, params={
            "latitude": w["lat"], "longitude": w["lon"], "timezone": CFG["timezone"],
            "forecast_days": 1,
            "daily": "temperature_2m_max,temperature_2m_min,weather_code",
        }).json()["daily"]
        hi, lo = round(d["temperature_2m_max"][0]), round(d["temperature_2m_min"][0])
        sky = WMO.get(d["weather_code"][0], "")
        line = f"В {w['city']} днём {hi:+d}°, ночью {lo:+d}°" + (f", {sky}" if sky else "")
        return line, f"🌤 <b>Погода.</b> {line}."
    except Exception as e:
        log.warning("weather failed: %s", str(e)[:100])
        return "", ""


def post_rates(dry: bool) -> None:
    data = requests.get("https://cbu.uz/ru/arkhiv-kursov-valyut/json/", timeout=30,
                        headers={"User-Agent": UA}).json()
    by = {r["Ccy"]: r for r in data}
    flags = {"USD": "🇺🇸", "EUR": "🇪🇺", "RUB": "🇷🇺", "KZT": "🇰🇿", "CNY": "🇨🇳"}
    rows, lines = [], []
    for code in flags:
        r = by.get(code)
        if not r:
            continue
        rate, diff = float(r["Rate"]), float(r["Diff"])
        pretty = f"{rate:,.2f}".replace(",", " ").replace(".", ",")
        rows.append({"code": code, "rate": pretty, "diff": diff})
        lines.append(f"{flags[code]} {code} — <b>{pretty}</b> сум "
                     f"({'▲' if diff >= 0 else '▼'} {abs(diff):.2f})".replace(".", ","))
    if not rows:
        raise RuntimeError("ЦБ не вернул курсы")
    dd, mm, yy = by["USD"]["Date"].split(".")
    date_str = f"{int(dd)} {MONTHS[int(mm) - 1]} {yy}"
    w_short, w_text = _weather()
    text = (f"<b>💱 Курсы валют на {date_str}</b>\n\n" + "\n".join(lines)
            + (f"\n\n{w_text}" if w_text else "") + f"\n\nДанные: Центральный банк Узбекистана\n{footer()}")
    publish(card.rates_card(date_str, rows, w_short), text, dry, "rates")


def post_digest(dry: bool) -> None:
    n = now()
    posts = db.posts_of_day(n.strftime("%Y-%m-%d"))
    if len(posts) < 3:
        return
    link = channel_link()
    lines = []
    for p in posts[-10:]:
        h = html.escape(p["headline"])
        lines.append(f'▪️ <a href="{link}/{p["message_id"]}">{h}</a>'
                     if link and p["message_id"] else f"▪️ {h}")
    text = (f"<b>🗞 Главное за {n.day} {MONTHS[n.month - 1]}</b>\n\n" + "\n\n".join(lines)
            + f"\n\n{footer()}")
    publish(None, text, dry, "digest")


# ── Тик ────────────────────────────────────────────────────────────────────
def _daily(key: str, hour: int, fn, dry: bool) -> None:
    n = now()
    today = n.strftime("%Y-%m-%d")
    if n.hour >= hour and db.kv_get(key) != today:
        try:
            fn(dry)
        except Exception:
            log.exception("%s failed", key)
            return  # повторим на следующем тике
        if not dry:
            db.kv_set(key, today)


def tick(dry: bool = False, force: bool = False) -> None:
    if not dry and not configured():
        log.info("BOT_TOKEN / CHANNEL_ID не заданы в .env — публикация выключена")
        return
    lo, hi = CFG["active_hours"]
    if not force and not lo <= now().hour < hi:
        return
    db.prune()
    added = db.add_items(sources.fetch_all())
    log.info("fetched, %d new items", added)
    if not force:
        _daily("rates_day", CFG["rates_post_hour"], post_rates, dry)
        _daily("digest_day", CFG["digest_post_hour"], post_digest, dry)
        if time.time() - db.last_post_ts() < CFG["post_interval_min"] * 60:
            return
    post_news(dry)
