#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import time
import logging
import requests

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHANNEL_ID = os.environ.get("CHANNEL_ID", "@c14newsflash")
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "60"))
STATE_FILE = os.path.join(os.environ.get("DATA_DIR", "."), "state_c14.json")
RSS_FEED = "https://www.c14.co.il/category/%D7%9E%D7%91%D7%96%D7%A7%D7%99%D7%9D/feed/"
NEWS_URL = f"https://api.rss2json.com/v1/api.json?rss_url={RSS_FEED}&count=20"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger("c14-news-bot")


def load_state() -> set:
    if not os.path.exists(STATE_FILE):
        return set()
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return set(data.get("seen", []))
    except Exception:
        return set()


def save_state(seen: set):
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"seen": sorted(seen)}, f, ensure_ascii=False)
    os.replace(tmp, STATE_FILE)


def fetch_news() -> list:
    response = requests.get(NEWS_URL, timeout=30)
    response.raise_for_status()

    data = response.json()
    if data.get("status") != "ok":
        raise RuntimeError(f"rss2json error: {data.get('message', 'unknown')}")

    items = []
    for post in data.get("items", []):
        post_id = post.get("guid") or post.get("link", "")
        title = post.get("title", "").strip()
        link = post.get("link", "")
        desc_raw = post.get("description", "") or post.get("content", "")

        import re as _re
        desc = _re.sub(r"<[^>]+>", "", desc_raw).strip()
        desc = " ".join(desc.split())[:300]

        if not title:
            continue

        items.append({"id": post_id, "title": title, "link": link, "desc": desc})

    return items


def send_telegram(text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHANNEL_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    response = requests.post(url, json=payload, timeout=15)
    response.raise_for_status()
    return response.json()


def format_message(item: dict) -> str:
    title = item["title"]
    link = item.get("link", "")
    desc = item.get("desc", "")

    channel_line = "\n\n🇮🇱 <b>ביחד ננצח</b> | <a href=\"https://t.me/c14newsflash\">C14 חדשות</a>"
    desc_line = f"\n\n{desc}" if desc else ""

    if link:
        return f"📰 <b>{title}</b>{desc_line}\n\n🔗 <a href=\"{link}\">קרא עוד</a>{channel_line}"
    else:
        return f"📰 <b>{title}</b>{desc_line}{channel_line}"


def process_once(seen: set, initialized: bool) -> tuple[set, bool]:
    try:
        items = fetch_news()
    except Exception as e:
        logger.exception(f"שגיאה בקריאת האתר: {e}")
        return seen, initialized

    if not items:
        logger.warning("לא נמצאו פריטים באתר — ייתכן שהמבנה השתנה")
        return seen, initialized

    logger.info(f"נמצאו {len(items)} פריטים")

    if not initialized:
        logger.info("ריצה ראשונה — מסמן את כל הפריטים חוץ מ-5 האחרונים")
        new_seen = seen | {item["id"] for item in items[:-5]}
        save_state(new_seen)
        logger.info("אותחל. מעלה את 5 הפריטים האחרונים...")
        return new_seen, True

    new_items = [item for item in items if item["id"] not in seen]

    if not new_items:
        logger.info("אין חדשות חדשות")
        return seen, initialized

    logger.info(f"נמצאו {len(new_items)} פריטים חדשים — שולח לטלגרם")

    for item in reversed(new_items):
        try:
            msg = format_message(item)
            send_telegram(msg)
            seen.add(item["id"])
            save_state(seen)
            logger.info(f"נשלח: {item['title'][:60]}")
            time.sleep(1)
        except Exception as e:
            logger.exception(f"שגיאה בשליחה: {e}")

    return seen, initialized


def main():
    if not TELEGRAM_TOKEN:
        raise RuntimeError("לא נמצא TELEGRAM_TOKEN במשתני הסביבה")

    os.makedirs(os.environ.get("DATA_DIR", "."), exist_ok=True)

    logger.info("בוט חדשות C14 התחיל")
    logger.info(f"ערוץ: {CHANNEL_ID}")
    logger.info(f"בדיקה כל {CHECK_INTERVAL} שניות")

    seen = load_state()
    initialized = len(seen) > 0

    while True:
        seen, initialized = process_once(seen, initialized)
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
