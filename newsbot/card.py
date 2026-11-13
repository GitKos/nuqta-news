"""Картинки к постам: стоковое фото (Pixabay) + заголовок и бренд канала."""
import io
import logging
import random
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps

from . import db
from .config import CFG, PIXABAY_KEY

log = logging.getLogger("card")
W, H, PAD = 1280, 800, 64
_WIN = Path("C:/Windows/Fonts")
_DEJAVU = Path("/usr/share/fonts/truetype/dejavu")  # Linux / GitHub Actions
ACCENT = {"uz": (25, 194, 160), "world": (255, 176, 32), "rates": (25, 194, 160)}
TAG = {"uz": "УЗБЕКИСТАН", "world": "МИР"}
GRAD = {"uz": ((8, 40, 66), (14, 96, 104)), "world": ((24, 22, 48), (78, 44, 104)),
        "rates": ((8, 34, 58), (12, 84, 96))}


def font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    if _WIN.exists():
        return ImageFont.truetype(str(_WIN / ("segoeuib.ttf" if bold else "segoeui.ttf")), size)
    return ImageFont.truetype(
        str(_DEJAVU / ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf")), int(size * 0.92))


def gradient(kind: str) -> Image.Image:
    a, b = GRAD[kind]
    strip = Image.new("RGB", (1, H))
    for y in range(H):
        t = y / (H - 1)
        strip.putpixel((0, y), tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3)))
    return strip.resize((W, H))


def stock_photo(query: str) -> tuple[Image.Image | None, str | None]:
    if not PIXABAY_KEY or not query:
        return None, None
    try:
        r = requests.get("https://pixabay.com/api/", timeout=20, params={
            "key": PIXABAY_KEY, "q": query[:90], "image_type": "photo",
            "orientation": "horizontal", "safesearch": "true", "per_page": 20,
        }, headers={"User-Agent": "news-card-maker/1.0"})
        hits = r.json().get("hits", [])
        used = db.recent_image_ids()
        hits = [h for h in hits if str(h["id"]) not in used][:8]
        if not hits:
            return None, None
        hit = random.choice(hits)
        raw = requests.get(hit["largeImageURL"], timeout=30,
                           headers={"User-Agent": "news-card-maker/1.0"}).content
        return Image.open(io.BytesIO(raw)).convert("RGB"), str(hit["id"])
    except Exception as e:
        log.warning("pixabay failed for %r: %s", query, str(e)[:120])
        return None, None


def wrap(draw, text: str, fnt, max_w: int) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        test = f"{cur} {word}".strip()
        if draw.textlength(test, font=fnt) <= max_w or not cur:
            cur = test
        else:
            lines.append(cur)
            cur = word
    return lines + [cur] if cur else lines


def brand(draw, kind: str) -> None:
    draw.rectangle([PAD, H - 62, PAD + 44, H - 56], fill=ACCENT[kind])
    draw.text((PAD + 60, H - 80), CFG["channel_title"].upper(), font=font(26),
              fill=(255, 255, 255, 235))


def to_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=90)
    return buf.getvalue()


def news_card(headline: str, region: str, query: str,
              urgent: bool = False) -> tuple[bytes, str | None]:
    photo, image_id = stock_photo(query)
    base = ImageOps.fit(photo, (W, H), Image.LANCZOS, centering=(0.5, 0.4)) if photo \
        else gradient(region)
    img = base.convert("RGBA")
    shade = Image.new("L", (1, H))
    for y in range(H):
        t = max(0.0, (y / H - 0.12) / 0.88)
        shade.putpixel((0, y), int(70 + 175 * t ** 1.3))
    black = Image.new("RGBA", (W, H), (6, 10, 18, 255))
    black.putalpha(shade.resize((W, H)))
    img = Image.alpha_composite(img, black)
    d = ImageDraw.Draw(img)

    for size in range(68, 38, -4):
        fnt = font(size)
        lines = wrap(d, headline, fnt, W - 2 * PAD)
        if len(lines) <= 4:
            break
    lh = int(size * 1.18)
    y = H - 118 - lh * len(lines)
    tag_f = font(24)
    tag, tag_bg, tag_fg = ("СРОЧНО", (226, 48, 48), "white") if urgent else         (TAG[region], ACCENT[region], (10, 20, 30))
    tw = d.textlength(tag, font=tag_f)
    d.rounded_rectangle([PAD, y - 62, PAD + tw + 36, y - 18], 8, fill=tag_bg)
    d.text((PAD + 18, y - 58), tag, font=tag_f, fill=tag_fg)
    for line in lines:
        d.text((PAD, y), line, font=fnt, fill="white")
        y += lh
    brand(d, region)
    return to_bytes(img), image_id


def rates_card(date_str: str, rows: list[dict], weather: str) -> bytes:
    """rows: [{code, rate, diff}]"""
    img = gradient("rates").convert("RGBA")
    top, step, rh = 196, 92, 78
    panels = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    pd = ImageDraw.Draw(panels)
    for i in range(len(rows)):
        pd.rounded_rectangle([PAD, top + i * step, W - PAD, top + i * step + rh], 16,
                             fill=(255, 255, 255, 26))
    img = Image.alpha_composite(img, panels)
    d = ImageDraw.Draw(img)
    d.text((PAD, 44), "КУРСЫ ВАЛЮТ", font=font(64), fill="white")
    d.text((PAD, 126), f"Центробанк Узбекистана · {date_str}", font=font(28, False),
           fill=(200, 225, 230))
    y = top
    for r in rows:
        d.text((PAD + 28, y + 12), r["code"], font=font(40), fill=ACCENT["rates"])
        d.text((PAD + 210, y + 12), r["rate"], font=font(40), fill="white")
        up = r["diff"] >= 0
        diff = f"{'▲' if up else '▼'} {abs(r['diff']):.2f}".replace(".", ",")
        dw = d.textlength(diff, font=font(32))
        d.text((W - PAD - 28 - dw, y + 18), diff, font=font(32),
               fill=(92, 220, 140) if up else (255, 120, 110))
        y += step
    if weather:
        d.text((PAD, y + 4), weather, font=font(30, False), fill=(225, 240, 242))
    brand(d, "rates")
    return to_bytes(img)
