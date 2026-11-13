import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

with open(ROOT / "config.yaml", encoding="utf-8") as f:
    CFG = yaml.safe_load(f)

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
CHANNEL_ID = os.getenv("CHANNEL_ID", "").strip()  # @username или -100...
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
PIXABAY_KEY = os.getenv("PIXABAY_KEY", "").strip()

TZ = ZoneInfo(CFG["timezone"])
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"


def now() -> datetime:
    return datetime.now(TZ)


def configured() -> bool:
    return bool(BOT_TOKEN and CHANNEL_ID)


def channel_link() -> str:
    return f"https://t.me/{CHANNEL_ID[1:]}" if CHANNEL_ID.startswith("@") else ""
