#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import time
import logging
import xml.etree.ElementTree as ET
import requests

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHANNEL_ID = os.environ.get("CHANNEL_ID", "@c14newsflash")
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "60"))
STATE_FILE = os.path.join(os.environ.get("DATA_DIR", "."), "state_c14.json")
NEWS_URL = "https://www.c14.co.il/category/%D7%9E%D7%91%D7%96%D7%A7%D7%99%D7%9D/feed/"

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

    root = ET.fromstring(response.content)
    ns = {"content": "http://purl.org/rss/1.0/modules/content/"}
    items = []

    for item in root.findall(".//item"):
        title_el = item.find("title")
        link_el = item.find("link")
        guid_el = item.find("guid")

        title = title_el.text.strip() if title_el is not None and title_el.text else ""
        link = link_el.text.strip() if link_el is not None and link_el.text else ""
        post_id = guid_el.text.strip() if guid_el is not None and guid_el.text else link

        if not title:
            continue

        items.append({"id": post_id, "title": title, "link": link})

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

    if link:
        return f"📰 <b>{title}</b>\n\n🔗 <a href=\"{link}\">קרא עוד</a>"
    else:
        return f"📰 <b>{title}</b>"


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
        logger.info("ריצה ראשונה — מסמן כל הפריטים הקיימים, לא שולח")
        new_seen = seen | {item["id"] for item in items}
        save_state(new_seen)
        logger.info("אותחל. מהריצה הבאה ישלח רק חדשות חדשות")
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
