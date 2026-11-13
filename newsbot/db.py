import sqlite3
import time

from .config import ROOT

(ROOT / "data").mkdir(exist_ok=True)
_con = sqlite3.connect(ROOT / "data" / "news.db")
_con.row_factory = sqlite3.Row
_con.executescript(
    """
CREATE TABLE IF NOT EXISTS items(
  id INTEGER PRIMARY KEY, url TEXT UNIQUE, source TEXT, region TEXT,
  title TEXT, summary TEXT, published REAL, fetched REAL,
  status TEXT DEFAULT 'new');          -- new | posted | skipped
CREATE TABLE IF NOT EXISTS posts(
  id INTEGER PRIMARY KEY, item_id INTEGER, ts REAL, day TEXT, region TEXT,
  headline TEXT, message_id INTEGER, image_id TEXT);
CREATE TABLE IF NOT EXISTS kv(key TEXT PRIMARY KEY, value TEXT);
"""
)


def add_items(items: list[dict]) -> int:
    n = 0
    for it in items:
        cur = _con.execute(
            "INSERT OR IGNORE INTO items(url,source,region,title,summary,published,fetched)"
            " VALUES(?,?,?,?,?,?,?)",
            (it["url"], it["source"], it["region"], it["title"], it["summary"],
             it["published"], time.time()),
        )
        n += cur.rowcount
    _con.commit()
    return n


def candidates(region: str, max_age_h: float, limit: int = 30) -> list[sqlite3.Row]:
    return _con.execute(
        "SELECT * FROM items WHERE status='new' AND region=? AND published>?"
        " ORDER BY published DESC LIMIT ?",
        (region, time.time() - max_age_h * 3600, limit),
    ).fetchall()


def set_status(item_id: int, status: str) -> None:
    _con.execute("UPDATE items SET status=? WHERE id=?", (status, item_id))
    _con.commit()


def add_post(item_id, day, region, headline, message_id, image_id) -> None:
    _con.execute(
        "INSERT INTO posts(item_id,ts,day,region,headline,message_id,image_id)"
        " VALUES(?,?,?,?,?,?,?)",
        (item_id, time.time(), day, region, headline, message_id, image_id),
    )
    _con.commit()


def last_post_ts() -> float:
    r = _con.execute("SELECT MAX(ts) FROM posts").fetchone()[0]
    return r or 0.0


def posts_of_day(day: str) -> list[sqlite3.Row]:
    return _con.execute("SELECT * FROM posts WHERE day=? ORDER BY ts", (day,)).fetchall()


def recent_posts(limit: int = 40) -> list[sqlite3.Row]:
    return _con.execute(
        "SELECT p.headline, i.title FROM posts p JOIN items i ON i.id=p.item_id"
        " ORDER BY p.ts DESC LIMIT ?", (limit,),
    ).fetchall()


def recent_image_ids(limit: int = 80) -> set[str]:
    rows = _con.execute(
        "SELECT image_id FROM posts WHERE image_id IS NOT NULL ORDER BY ts DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return {r[0] for r in rows}


def kv_get(key: str) -> str | None:
    r = _con.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
    return r[0] if r else None


def kv_set(key: str, value: str) -> None:
    _con.execute("INSERT OR REPLACE INTO kv(key,value) VALUES(?,?)", (key, value))
    _con.commit()


def prune(days: float = 4) -> None:
    """База не должна расти бесконечно: старые новости больше не нужны."""
    _con.execute("DELETE FROM items WHERE fetched<?", (time.time() - days * 86400,))
    _con.execute("DELETE FROM posts WHERE ts<?", (time.time() - 30 * 86400,))
    _con.commit()
