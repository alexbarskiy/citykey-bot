#!/usr/bin/env python3
import os
import sqlite3
import requests
import bs4
import telebot
from telebot import types

TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise RuntimeError("ENV TOKEN is missing. Add TOKEN in Railway Variables.")

bot = telebot.TeleBot(TOKEN)
DB_PATH = os.getenv("DB_PATH", "stats.db")

SIGN_TO_SLUG = {
    "aries": "horoskop-oven",
    "taurus": "horoskop-telec",
    "gemini": "horoskop-bliznyu",
    "cancer": "horoskop-rak",
    "leo": "horoskop-lev",
    "virgo": "horoskop-diva",
    "libra": "horoskop-terez",
    "scorpio": "horoskop-skorpion",
    "sagittarius": "horoskop-strilec",
    "capricorn": "horoskop-kozerig",
    "aquarius": "horoskop-vodoliy",
    "pisces": "horoskop-ryby",
}

SIGNS = {
    "aries": "♈", "taurus": "♉", "gemini": "♊", "cancer": "♋",
    "leo": "♌", "virgo": "♍", "libra": "♎", "scorpio": "♏",
    "sagittarius": "♐", "capricorn": "♑", "aquarius": "♒", "pisces": "♓",
}

def build_readmore_url(sign: str) -> str:
    slug = SIGN_TO_SLUG.get(sign, "horoskop-oven")
    base = f"https://www.citykey.com.ua/{slug}/"
    utm = f"?utm_source=telegram&utm_medium=bot&utm_campaign=horoscope&utm_content={sign}"
    return base + utm

def inline_readmore(sign: str):
    ik = types.InlineKeyboardMarkup()
    ik.add(types.InlineKeyboardButton("Читати далі на сайті", url=build_readmore_url(sign)))
    return ik

def fetch_horoscope_excerpt(sign: str, max_chars: int = 520) -> str:
    slug = SIGN_TO_SLUG.get(sign, "horoskop-oven")
    url = f"https://www.citykey.com.ua/{slug}/"
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        r.raise_for_status()
        soup = bs4.BeautifulSoup(r.text, "html.parser")
        h3 = soup.find("h3")
        if not h3:
            return "Гороскоп оновлюється."

        parts = []
        for p in h3.find_all_next("p", limit=6):
            t = p.get_text(" ", strip=True)
            if t:
                parts.append(t)

        text = " ".join(parts).strip()
        if not text:
            return "Гороскоп оновлюється."

        if len(text) > max_chars:
            text = text[:max_chars].rstrip() + "…"
        return text
    except Exception:
        return "Гороскоп оновлюється."

def broadcast():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    subs = c.execute("SELECT user_id, sign FROM subs").fetchall()
    conn.close()

    for user_id, sign in subs:
        emoji = SIGNS.get(sign, "♈")
        txt = fetch_horoscope_excerpt(sign)
        try:
            bot.send_message(user_id, f"{emoji} Гороскоп на сьогодні\n\n{txt}", reply_markup=inline_readmore(sign))
        except Exception as e:
            print(f"Send failed {user_id}: {e}")

if __name__ == "__main__":
    broadcast()
