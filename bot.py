import os
import datetime
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

SIGNS_UA = [
    "♈ Овен", "♉ Тілець", "♊ Близнюки", "♋ Рак",
    "♌ Лев", "♍ Діва", "♎ Терези", "♏ Скорпіон",
    "♐ Стрілець", "♑ Козеріг", "♒ Водолій", "♓ Риби",
]

UA_TO_SIGN = {
    "♈ Овен": "aries",
    "♉ Тілець": "taurus",
    "♊ Близнюки": "gemini",
    "♋ Рак": "cancer",
    "♌ Лев": "leo",
    "♍ Діва": "virgo",
    "♎ Терези": "libra",
    "♏ Скорпіон": "scorpio",
    "♐ Стрілець": "sagittarius",
    "♑ Козеріг": "capricorn",
    "♒ Водолій": "aquarius",
    "♓ Риби": "pisces",
}

EMOJI_BY_SIGN = {
    "aries": "♈", "taurus": "♉", "gemini": "♊", "cancer": "♋",
    "leo": "♌", "virgo": "♍", "libra": "♎", "scorpio": "♏",
    "sagittarius": "♐", "capricorn": "♑", "aquarius": "♒", "pisces": "♓",
}

def db_conn():
    return sqlite3.connect(DB_PATH)

def init_db():
    conn = db_conn()
    c = conn.cursor()
    c.execute(
        """CREATE TABLE IF NOT EXISTS users
           (user_id INTEGER PRIMARY KEY, first_name TEXT, date TEXT)"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS subs
           (user_id INTEGER, sign TEXT, PRIMARY KEY (user_id, sign))"""
    )
    conn.commit()
    conn.close()

def count_users():
    conn = db_conn()
    c = conn.cursor()
    starters = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    subs = c.execute("SELECT COUNT(DISTINCT user_id) FROM subs").fetchone()[0]
    conn.close()
    return starters, subs

def build_readmore_url(sign: str) -> str:
    slug = SIGN_TO_SLUG.get(sign, "horoskop-oven")
    base = f"https://www.citykey.com.ua/{slug}/"
    utm = f"?utm_source=telegram&utm_medium=bot&utm_campaign=horoscope&utm_content={sign}"
    return base + utm

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

def reply_kb():
    mk = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    mk.add(*[types.KeyboardButton(s) for s in SIGNS_UA])
    return mk

def inline_readmore(sign: str):
    url = build_readmore_url(sign)
    ik = types.InlineKeyboardMarkup()
    ik.add(types.InlineKeyboardButton("Читати далі на сайті", url=url))
    return ik

@bot.message_handler(commands=["start"])
def start(m):
    conn = db_conn()
    c = conn.cursor()
    c.execute(
        "INSERT OR IGNORE INTO users (user_id, first_name, date) VALUES (?,?,?)",
        (m.from_user.id, m.from_user.first_name, datetime.date.today().isoformat()),
    )
    conn.commit()
    conn.close()

    bot.send_message(
        m.chat.id,
        "Привіт. Обери знак, і я надішлю короткий гороскоп з кнопкою читати далі.",
        reply_markup=reply_kb(),
    )

@bot.message_handler(func=lambda m: m.text in SIGNS_UA)
def show_horo(m):
    sign = UA_TO_SIGN.get(m.text, "aries")
    emoji = EMOJI_BY_SIGN.get(sign, "♈")
    excerpt = fetch_horoscope_excerpt(sign)
    bot.send_message(
        m.chat.id,
        f"{emoji} {m.text}\n\n{excerpt}",
        reply_markup=reply_kb(),
    )
    bot.send_message(
        m.chat.id,
        "Якщо хочеш повну версію, тисни кнопку нижче.",
        reply_markup=inline_readmore(sign),
    )

@bot.message_handler(commands=["subscribe"])
def subscribe(m):
    mk = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    mk.add(*[types.KeyboardButton(f"{s} Підписатись") for s in SIGNS_UA])
    bot.send_message(m.chat.id, "Обери знак для підписки на ранковий прогноз.", reply_markup=mk)

@bot.message_handler(func=lambda m: isinstance(m.text, str) and m.text.endswith("Підписатись"))
def sub_save(m):
    sign = None
    for ua, code in UA_TO_SIGN.items():
        if m.text.startswith(ua):
            sign = code
            break

    if not sign:
        bot.send_message(m.chat.id, "Не зрозумів знак. Спробуй ще раз.", reply_markup=reply_kb())
        return

    conn = db_conn()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO subs (user_id, sign) VALUES (?,?)", (m.from_user.id, sign))
    conn.commit()
    conn.close()

    bot.send_message(
        m.chat.id,
        f"Підписку активовано для {EMOJI_BY_SIGN.get(sign,'♈')}.",
        reply_markup=reply_kb(),
    )

@bot.message_handler(commands=["unsubscribe"])
def unsub(m):
    conn = db_conn()
    c = conn.cursor()
    c.execute("DELETE FROM subs WHERE user_id = ?", (m.from_user.id,))
    conn.commit()
    conn.close()
    bot.send_message(m.chat.id, "Відписав. Якщо захочеш знову, команда /subscribe.", reply_markup=reply_kb())

@bot.message_handler(commands=["stat"])
def stat(m):
    starters, subs = count_users()
    bot.send_message(m.chat.id, f"Користувачів: {starters}\nПідписок: {subs}")

if __name__ == "__main__":
    init_db()
    bot.infinity_polling(timeout=20, long_polling_timeout=20)
