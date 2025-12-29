# bot.py
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

SIGNS_UA_BUTTONS = [f'{v["emoji"]} {v["ua"]}' for v in SIGNS.values()]
UA_TO_SIGN = {f'{v["emoji"]} {v["ua"]}': k for k, v in SIGNS.items()}


def init_db() -> None:
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute(
        """CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            first_name TEXT,
            date TEXT
        )"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS subs (
            user_id INTEGER,
            sign TEXT,
            PRIMARY KEY (user_id, sign)
        )"""
    )
    conn.commit()
    conn.close()


def is_subscribed(user_id: int, sign: str) -> bool:
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    row = c.execute(
        "SELECT 1 FROM subs WHERE user_id = ? AND sign = ? LIMIT 1",
        (user_id, sign),
    ).fetchone()
    conn.close()
    return bool(row)


def subscribe_user(user_id: int, sign: str) -> None:
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO subs (user_id, sign) VALUES (?, ?)", (user_id, sign))
    conn.commit()
    conn.close()


def unsubscribe_user(user_id: int, sign: str) -> None:
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM subs WHERE user_id = ? AND sign = ?", (user_id, sign))
    conn.commit()
    conn.close()


def count_stats():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    starters = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    subs = c.execute("SELECT COUNT(*) FROM subs").fetchone()[0]
    conn.close()
    return starters, subs


def get_horoscope_preview(sign: str) -> str:
    info = SIGNS.get(sign, SIGNS["aries"])
    url = f'https://www.citykey.com.ua/{info["slug"]}/'
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


def sign_keyboard():
    mk = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    mk.add(*[types.KeyboardButton(x) for x in SIGNS_UA_BUTTONS])
    mk.add(types.KeyboardButton("🔔 Мої підписки"), types.KeyboardButton("🔕 Відписатись від всього"))
    return mk


def horo_inline_kb(sign: str, user_id: int):
    info = SIGNS.get(sign, SIGNS["aries"])
    url = f'https://www.citykey.com.ua/{info["slug"]}/?utm_source=telegram&utm_medium=bot&utm_campaign=horoscope&utm_content={sign}'

    kb = types.InlineKeyboardMarkup(row_width=2)

    kb.add(types.InlineKeyboardButton("Читати далі на сайті", url=url))

    if is_subscribed(user_id, sign):
        kb.add(types.InlineKeyboardButton("🔕 Відписатись від цього знака", callback_data=f"unsub:{sign}"))
    else:
        kb.add(types.InlineKeyboardButton("🔔 Підписатись на цей знак", callback_data=f"sub:{sign}"))

    kb.add(
        types.InlineKeyboardButton("♻️ Інший знак", callback_data="pick_sign")
    )
    return kb


@bot.message_handler(commands=["start"])
def start(m):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute(
        "INSERT OR IGNORE INTO users (user_id, first_name, date) VALUES (?,?,?)",
        (m.from_user.id, m.from_user.first_name, datetime.date.today().isoformat()),
    )
    conn.commit()
    conn.close()

    bot.send_message(
        m.chat.id,
        "👋 Привіт. Обери свій знак і я дам короткий прогноз. Під самим прогнозом буде кнопка підписки на щоденні оновлення.",
        reply_markup=sign_keyboard(),
    )


@bot.message_handler(func=lambda m: m.text in UA_TO_SIGN)
def show_horo(m):
    sign = UA_TO_SIGN.get(m.text, "aries")
    info = SIGNS.get(sign, SIGNS["aries"])
    txt = get_horoscope_preview(sign)

    header = f'{info["emoji"]} <b>{info["ua"]}</b>\n\n'
    bot.send_message(
        m.chat.id,
        header + txt,
        reply_markup=horo_inline_kb(sign, m.from_user.id),
        disable_web_page_preview=True,
    )


@bot.callback_query_handler(func=lambda c: c.data in ["pick_sign"])
def cb_pick_sign(c):
    try:
        bot.answer_callback_query(c.id)
    except Exception:
        pass

    bot.send_message(
        c.message.chat.id,
        "Обери знак з клавіатури нижче.",
        reply_markup=sign_keyboard(),
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("sub:") or c.data.startswith("unsub:"))
def cb_subscribe(c):
    data = c.data
    action, sign = data.split(":", 1)

    if sign not in SIGNS:
        try:
            bot.answer_callback_query(c.id, "Невідомий знак.")
        except Exception:
            pass
        return

    if action == "sub":
        subscribe_user(c.from_user.id, sign)
        msg = "Готово. Підписка активна. Щоденні розсилки підуть з Railway cron."
    else:
        unsubscribe_user(c.from_user.id, sign)
        msg = "Ок. Відписав від цього знака."

    try:
        bot.answer_callback_query(c.id, msg, show_alert=False)
    except Exception:
        pass

    info = SIGNS[sign]
    new_kb = horo_inline_kb(sign, c.from_user.id)
    try:
        bot.edit_message_reply_markup(
            chat_id=c.message.chat.id,
            message_id=c.message.message_id,
            reply_markup=new_kb,
        )
    except Exception:
        pass


@bot.message_handler(func=lambda m: m.text == "🔔 Мої підписки")
def my_subs(m):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    rows = c.execute("SELECT sign FROM subs WHERE user_id = ?", (m.from_user.id,)).fetchall()
    conn.close()

    if not rows:
        bot.send_message(m.chat.id, "Поки що підписок немає. Відкрий гороскоп свого знака і натисни кнопку підписки.")
        return

    names = []
    for (s,) in rows:
        if s in SIGNS:
            names.append(f'{SIGNS[s]["emoji"]} {SIGNS[s]["ua"]}')
    bot.send_message(m.chat.id, "Твої підписки:\n" + "\n".join(names))


@bot.message_handler(func=lambda m: m.text == "🔕 Відписатись від всього")
def unsub_all(m):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM subs WHERE user_id = ?", (m.from_user.id,))
    conn.commit()
    conn.close()
    bot.send_message(m.chat.id, "Готово. Відписав від усіх знаків.")


@bot.message_handler(commands=["stat"])
def stat(m):
    starters, subs = count_stats()
    bot.send_message(m.chat.id, f"📊 Користувачів: {starters}\n🔔 Підписок: {subs}")


if __name__ == "__main__":
    init_db()
    print("Bot started")
    bot.infinity_polling(skip_pending=True)
