"""Gemini: выбор новости и рерайт. Ответ всегда JSON."""
import json
import logging
import time

import requests

from .config import CFG, GEMINI_API_KEY

log = logging.getLogger("llm")
URL = "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent"


class LLMError(RuntimeError):
    pass


def ask_json(prompt: str, temperature: float = 0.3):
    if not GEMINI_API_KEY:
        raise LLMError("GEMINI_API_KEY не задан")
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": temperature},
    }
    last = ""
    for round_ in range(2):  # два прохода по списку моделей
        for model in CFG["gemini_models"]:
            try:
                r = requests.post(URL.format(model), json=body, timeout=45,
                                  headers={"x-goog-api-key": GEMINI_API_KEY})
            except requests.RequestException as e:
                last = f"{model}: {str(e)[:120]}"
                log.warning("model failed: %s", last)
                continue
            if r.status_code == 200:
                try:
                    parts = r.json()["candidates"][0]["content"]["parts"]
                    text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
                    data = json.loads(text)
                    if isinstance(data, dict):
                        return data
                    last = f"{model}: not a JSON object"
                except Exception as e:
                    last = f"{model}: bad response {e}"
            else:
                last = f"{model}: HTTP {r.status_code} {r.text[:120]}"
            log.warning("model failed: %s", " ".join(last.split()))
        time.sleep(5)
    raise LLMError(last)


def select(cands: list, recent: list, region: str) -> dict:
    lines = "\n".join(f"{i}. [{c['source']}] {c['title']}" for i, c in enumerate(cands))
    posted = "\n".join(f"- {r['headline']} / {r['title']}" for r in recent) or "(пока ничего)"
    scope = ("новости Узбекистана" if region == "uz"
             else "мировые новости, важные или интересные жителям Узбекистана")
    return ask_json(f"""Ты выпускающий редактор новостного Telegram-канала для жителей Узбекистана.
Рубрика сейчас: {scope}.

УЖЕ ОПУБЛИКОВАНО (не повторять эти события):
{posted}

КАНДИДАТЫ:
{lines}

Выбери ОДНУ новость, которую читатели скорее всего прочитают и перешлют: то, что касается
денег, цен, законов, транспорта, погоды, безопасности, крупных событий, либо громкие мировые события.
Не выбирай: рекламу и пресс-релизы компаний, гороскопы, мелкий криминал, анонсы без сути,
новости о событиях, которые уже опубликованы.

Ответь JSON: {{"pick": <номер или null, если ничего достойного>,
"duplicates": [<номера кандидатов о событиях, которые уже опубликованы>]}}""", 0.2)


def rewrite(item, text: str) -> dict:
    return ask_json(f"""Ты редактор новостного Telegram-канала для жителей Узбекистана. Язык канала: {CFG['language']}.
Перепиши новость своими словами для поста в канале.

ИСТОЧНИК: {item['source']}
ЗАГОЛОВОК: {item['title']}
ТЕКСТ:
{text}

ПРАВИЛА:
- Только факты из текста выше. Ничего не добавляй, не домысливай, не оценивай. Цифры, имена, даты, должности переноси точно.
- Не копируй фразы источника дословно, пиши заново простым живым языком, без канцелярита и без кликбейта.
- Тон нейтральный. Никаких мнений о политиках, странах, народах и религиях.
- headline: до 85 символов, суть события, без точки в конце.
- body: 2–3 коротких абзаца, вместе 350–650 символов, абзацы разделяй \\n\\n. Первый абзац отвечает на «что случилось». Без эмодзи, без хэштегов, без ссылок.
- emoji: один эмодзи по теме.
- image_query: 1–3 английских слова для поиска нейтрального стокового фото по теме (предмет или место, не имена людей), например "tashkent city", "money", "airplane".
- Если в тексте нет внятной новости (реклама, обрывок, анонс без фактов), верни {{"skip": true}}.

Ответь JSON: {{"skip": false, "headline": "...", "body": "...", "emoji": "...", "image_query": "..."}}""", 0.5)
