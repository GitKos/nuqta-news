"""Новостной канал: автопостинг.

  python main.py tick      — рабочий цикл (его запускает Планировщик каждые 10 минут)
  python main.py preview   — сделать пост в папку preview/ без публикации
  python main.py rates     — превью поста с курсами (preview/rates.*)
  python main.py now       — опубликовать одну новость прямо сейчас
  python main.py check     — проверить токен и права бота в канале
"""
import logging
import os
import sys
import time
from logging.handlers import RotatingFileHandler

from newsbot.config import ROOT

(ROOT / "logs").mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s",
    handlers=[RotatingFileHandler(ROOT / "logs" / "bot.log", maxBytes=1_000_000,
                                  backupCount=3, encoding="utf-8"),
              logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("main")
LOCK = ROOT / "data" / "tick.lock"


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "tick"
    from newsbot import pipeline, telegram

    if cmd == "check":
        print(telegram.check())
        return 0
    if cmd == "rates":
        pipeline.post_rates(dry=True)
        return 0
    if cmd not in ("tick", "preview", "now"):
        print(__doc__)
        return 1

    if LOCK.exists() and time.time() - LOCK.stat().st_mtime < 15 * 60:
        log.info("предыдущий запуск ещё работает, выходим")
        return 0
    LOCK.write_text(str(os.getpid()))
    try:
        pipeline.tick(dry=cmd == "preview", force=cmd in ("preview", "now"))
    except Exception:
        log.exception("tick failed")
        return 1
    finally:
        LOCK.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
