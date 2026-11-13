import logging
import time

import requests

from .config import BOT_TOKEN, CHANNEL_ID

log = logging.getLogger("telegram")


def _call(method: str, data: dict, files: dict | None = None) -> dict:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    for _ in range(3):
        r = requests.post(url, data=data, files=files, timeout=60)
        j = r.json()
        if j.get("ok"):
            return j["result"]
        if r.status_code == 429:
            time.sleep(j.get("parameters", {}).get("retry_after", 5) + 1)
            continue
        raise RuntimeError(f"Telegram {method}: {j.get('description')}")
    raise RuntimeError(f"Telegram {method}: rate limited")


def send_photo(photo: bytes, caption: str) -> int:
    res = _call("sendPhoto", {"chat_id": CHANNEL_ID, "caption": caption, "parse_mode": "HTML"},
                {"photo": ("card.jpg", photo, "image/jpeg")})
    return res["message_id"]


def send_message(text: str) -> int:
    res = _call("sendMessage", {"chat_id": CHANNEL_ID, "text": text, "parse_mode": "HTML",
                                "disable_web_page_preview": "true"})
    return res["message_id"]


def check() -> str:
    me = _call("getMe", {})
    chat = _call("getChat", {"chat_id": CHANNEL_ID})
    member = _call("getChatMember", {"chat_id": CHANNEL_ID, "user_id": me["id"]})
    ok = member.get("status") == "administrator" and member.get("can_post_messages", False)
    return (f"бот @{me['username']}, канал «{chat.get('title')}», "
            f"право публикации: {'есть' if ok else 'НЕТ — добавьте бота админом канала'}")
