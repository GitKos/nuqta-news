"""RSS-ленты и извлечение текста статьи. Без внешних парсеров."""
import html
import logging
import re
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from email.utils import parsedate_to_datetime
from datetime import datetime

import requests

from .config import CFG, UA

log = logging.getLogger("sources")
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def clean(text: str | None) -> str:
    return _WS.sub(" ", html.unescape(_TAG.sub(" ", text or ""))).strip()


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _parse_date(s: str | None) -> float:
    if not s:
        return time.time()
    try:
        return parsedate_to_datetime(s).timestamp()
    except Exception:
        try:
            return datetime.fromisoformat(s.strip().replace("Z", "+00:00")).timestamp()
        except Exception:
            return time.time()


def fetch_feed(feed: dict) -> list[dict]:
    root = None
    for ua in (UA, "Mozilla/5.0 (compatible; NewsReader/1.0)"):  # часть сайтов не любит один из UA
        try:
            r = requests.get(feed["url"], headers={"User-Agent": ua}, timeout=20)
            r.raise_for_status()
            root = ET.fromstring(r.content)
            break
        except Exception as e:
            err = str(e)[:120]
    if root is None:
        log.warning("feed %s failed: %s", feed["name"], err)
        return []
    out = []
    for node in root.iter():
        if _local(node.tag) not in ("item", "entry"):
            continue
        f = {}
        for ch in node:
            name = _local(ch.tag)
            if name == "link":
                f.setdefault("link", (ch.text or "").strip() or ch.get("href", ""))
            elif name in ("title", "description", "summary", "pubdate", "updated", "published"):
                f.setdefault(name, ch.text or "")
        title, url = clean(f.get("title")), (f.get("link") or "").strip()
        if not title or not url.startswith("http"):
            continue
        out.append({
            "url": url, "source": feed["name"], "region": feed["region"], "title": title,
            "summary": clean(f.get("description") or f.get("summary"))[:1500],
            "published": min(time.time(), _parse_date(
                f.get("pubdate") or f.get("published") or f.get("updated"))),
        })
    return out


def fetch_all() -> list[dict]:
    with ThreadPoolExecutor(8) as ex:
        lists = list(ex.map(fetch_feed, CFG["feeds"]))
    return [it for lst in lists for it in lst]


def article_text(url: str, limit: int = 5000) -> str:
    """Грубое, но надёжное извлечение: содержимое абзацев <p>."""
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=20)
        r.raise_for_status()
        page = r.text
    except Exception as e:
        log.warning("article fetch failed %s: %s", url, str(e)[:100])
        return ""
    page = re.sub(r"(?is)<(script|style|nav|footer|aside|form)[^>]*>.*?</\1>", " ", page)
    paras = [clean(p) for p in re.findall(r"(?is)<p[^>]*>(.*?)</p>", page)]
    paras = [p for p in paras if len(p) > 60]
    return "\n".join(paras)[:limit]
