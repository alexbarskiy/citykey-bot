import os
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
    "aries": {"emoji": "♈", "ua": "Овен", "slug": "horoskop-oven"},
    "taurus": {"emoji": "♉", "ua": "Тілець", "slug": "horoskop-telec"},
    "gemini": {"emoji": "♊", "ua": "Близнюки", "slug": "horoskop-bliznyu"},
    "cancer": {"emoji": "♋", "ua": "Рак", "slug": "horoskop-rak"},
    "leo": {"emoji": "♌", "ua": "Лев", "slug": "horoskop-lev"},
    "virgo": {"emoji": "♍", "ua": "Діва", "slug": "horoskop-diva"},
    "libra": {"emoji": "♎", "ua": "Терези", "slug": "horoskop-terez"},
    "scorpio": {"emoji": "♏", "ua": "Скорпіон", "slug": "horoskop-skorpion"},
    "sagittarius": {"emoji": "♐", "ua": "Стрілець", "slug": "horoskop-strilec"},
    "capricorn": {"emoji": "♑", "ua": "Козеріг", "slug": "horoskop-kozerig"},
    "aquarius": {"emoji": "♒", "ua": "Водолій", "slug": "horoskop-vodoliy"},
    "pisces": {"emoji": "♓", "ua": "Риби", "slug": "horoskop-ryby"},
}

def get_preview(sign):
    info = SIGNS.get(sign, SIGNS["aries"])
    url = "https://www.citykey.com.ua/" + info["slug"] + "/"
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=12)
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

def daily_inline_kb(sign):
    info = SIGNS.get(sign, SIGNS["aries"])
    url = "https://www.citykey.com.ua/" + info["slug"] + "/?utm_source=telegram&utm_medium=bot&utm_campaign=horoscope_daily&utm_content=" + sign
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton("Читати далі на сайті", url=url))
    kb.add(types.InlineKeyboardButton("🔕 Відписатись від цього знака", callback_data="unsub:" + sign))
    return kb

def remove_all_user_subs(user_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM subs WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def broadcast():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    rows = c.execute("SELECT user_id, sign FROM subs").fetchall()
    conn.close()

    for user_id, sign in rows:
        info = SIGNS.get(sign, SIGNS["aries"])
        preview = get_preview(sign)
        text = info["emoji"] + " <b>" + info["ua"] + ". Гороскоп на сьогодні</b>\n\n" + preview
        try:
            bot.send_message(user_id, text, reply_markup=daily_inline_kb(sign), disable_web_page_preview=True)
        except Exception as e:
            s = str(e)
            print("Send failed to " + str(user_id) + ": " + s)
            if "403" in s or "blocked" in s or "bot was blocked" in s:
                remove_all_user_subs(user_id)

if __name__ == "__main__":
    broadcast()
