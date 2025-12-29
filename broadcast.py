import os
import datetime
import sqlite3
import requests
import bs4
import telebot
from telebot import types

TOKEN = os.getenv("TOKEN", "").strip()
if not TOKEN:
    raise RuntimeError("TOKEN env var is missing. Add TOKEN in Railway Variables.")

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
DB_NAME = "stats.db"

SIGNS = {
    "aries":       {"emoji": "♈", "ua": "Овен",      "slug": "horoskop-oven"},
    "taurus":      {"emoji": "♉", "ua": "Тілець",    "slug": "horoskop-telec"},
    "gemini":      {"emoji": "♊", "ua": "Близнюки",  "slug": "horoskop-bliznyu"},
    "cancer":      {"emoji": "♋", "ua": "Рак",       "slug": "horoskop-rak"},
    "leo":         {"emoji": "♌", "ua": "Лев",       "slug": "horoskop-lev"},
    "virgo":       {"emoji": "♍", "ua": "Діва",      "slug": "horoskop-diva"},
    "libra":       {"emoji": "♎", "ua": "Терези",    "slug": "horoskop-terez"},
    "scorpio":     {"emoji": "♏", "ua": "Скорпіон",  "slug": "horoskop-skorpion"},
    "sagittarius": {"emoji": "♐", "ua": "Стрілець",  "slug": "horoskop-strilec"},
    "capricorn":   {"emoji": "♑", "ua": "Козеріг",   "slug": "horoskop-kozerig"},
    "aquarius":    {"emoji": "♒", "ua": "Водолій",   "slug": "horoskop-vodoliy"},
    "pisces":      {"emoji": "♓", "ua": "Риби",      "slug": "horoskop-ryby"},
}

def init_db() -> None:
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute(
        """CREATE TABLE IF NOT EXISTS deliveries (
            user_id INTEGER,
            sign TEXT,
            date TEXT,
            PRIMARY KEY (user_id, sign, date)
        )"""
    )
    conn.commit()
    conn.close()

def already_sent(user_id: int, sign: str, d: str) -> bool:
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    row = c.execute(
        "SELECT 1 FROM deliveries WHERE user_id = ? AND sign = ? AND date = ? LIMIT 1",
        (user_id, sign, d),
    ).fetchone()
    conn.close()
    return bool(row)

def mark_sent(user_id: int, sign: str, d: str) -> None:
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute(
        "INSERT OR IGNORE INTO deliveries (user_id, sign, date) VALUES (?, ?, ?)",
        (user_id, sign, d),
    )
    conn.commit()
    conn.close()

def drop_user(user_id: int) -> None:
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM subs WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def get_preview(sign: str) -> str:
    info = SIGNS.get(sign, SIGNS["aries"])
    url = f'https://www.citykey.com.ua/{info["slug"]}/'
    try:
        r = requests.get(url, timeout=12)
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
        txt = " ".join(parts).strip()
        if not txt:
            return "Гороскоп оновлюється."

        if len(txt) > 600:
            txt = txt[:600].rsplit(" ", 1)[0] + "…"
        return txt
    except Exception:
        return "Гороскоп оновлюється."

def daily_kb(sign: str):
    info = SIGNS.get(sign, SIGNS["aries"])
    url = f'https://www.citykey.com.ua/{info["slug"]}/?utm_source=telegram&utm_medium=bot&utm_campaign=horoscope_daily&utm_content={sign}'
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton("Читати далі на сайті", url=url))
    kb.add(types.InlineKeyboardButton("🔕 Відписатись від цього знака", callback_data=f"unsub:{sign}"))
    return kb

def broadcast():
    init_db()
    today = datetime.date.today().isoformat()

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    rows = c.execute("SELECT user_id, sign FROM subs").fetchall()
    conn.close()

    for user_id, sign in rows:
        if sign not in SIGNS:
            continue

        if already_sent(user_id, sign, today):
            continue

        info = SIGNS[sign]
        preview = get_preview(sign)

        text = f'{info["emoji"]} <b>{info["ua"]}. Гороскоп на сьогодні</b>\n\n{preview}'
        kb = daily_kb(sign)

        try:
            bot.send_message(user_id, text, reply_markup=kb, disable_web_page_preview=True)
            mark_sent(user_id, sign, today)
        except Exception as e:
            msg = str(e).lower()
            if "forbidden" in msg or "blocked" in msg or "chat not found" in msg:
                drop_user(user_id)
            print(f"Send failed to {user_id}: {e}")

if __name__ == "__main__":
    broadcast()
