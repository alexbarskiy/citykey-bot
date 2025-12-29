import os
import sqlite3
import datetime
import telebot
import time

# Використовуємо ту саму змінну DB_PATH
DB_NAME = os.getenv("DB_PATH", "stats.db")
TOKEN = os.getenv("TOKEN", "").strip()

if not TOKEN:
    raise RuntimeError("TOKEN is missing.")

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

SIGNS = {
    "aries":       {"emoji": "♈", "ua": "Овен",      "slug": "horoskop-oven"},
    "taurus":      {"emoji": "♉", "ua": "Тілець",    "slug": "horoskop-telec"},
    "gemini":      {"emoji": "♊", "ua": "Близнюки",  "slug": "horoskop-bliznyu"},
    "cancer":      {"emoji": "♋", "ua": "Рак",       "slug": "horoskop-rak"},
    "leo":         {"emoji": "♌", "ua": "Лев",       "slug": "horoskop-lev"},
    "virgo":      {"emoji": "♍", "ua": "Діва",      "slug": "horoskop-diva"},
    "libra":       {"emoji": "♎", "ua": "Терези",    "slug": "horoskop-terez"},
    "scorpio":     {"emoji": "♏", "ua": "Скорпіон",  "slug": "horoskop-skorpion"},
    "sagittarius": {"emoji": "♐", "ua": "Стрілець",  "slug": "horoskop-strilec"},
    "capricorn":   {"emoji": "♑", "ua": "Козеріг",   "slug": "horoskop-kozerig"},
    "aquarius":    {"emoji": "♒", "ua": "Водолій",   "slug": "horoskop-vodoliy"},
    "pisces":      {"emoji": "♓", "ua": "Риби",      "slug": "horoskop-ryby"},
}

def broadcast():
    today = datetime.date.today().isoformat()
    if not os.path.exists(DB_NAME):
        print("База даних не знайдена. Скасовую.")
        return

    conn = sqlite3.connect(DB_NAME, timeout=20)
    c = conn.cursor()
    rows = c.execute("SELECT user_id, sign FROM subs").fetchall()
    conn.close()

    print(f"Початок розсилки для {len(rows)} записів...")

    for user_id, sign in rows:
        # Перевірка чи вже відправляли
        conn = sqlite3.connect(DB_NAME, timeout=20)
        sent = conn.execute("SELECT 1 FROM deliveries WHERE user_id=? AND sign=? AND date=?", (user_id, sign, today)).fetchone()
        conn.close()
        
        if sent: continue

        info = SIGNS.get(sign)
        if not info: continue

        text = f'{info["emoji"]} <b>{info["ua"]}. Оновлення гороскопу!</b>\n\nСьогоднішній прогноз уже на сайті.'
        url = f'https://www.citykey.com.ua/{info["slug"]}/'
        
        kb = telebot.types.InlineKeyboardMarkup()
        kb.add(telebot.types.InlineKeyboardButton("Читати", url=url))

        try:
            bot.send_message(user_id, text, reply_markup=kb)
            conn = sqlite3.connect(DB_NAME, timeout=20)
            conn.execute("INSERT OR IGNORE INTO deliveries (user_id, sign, date) VALUES (?,?,?)", (user_id, sign, today))
            conn.commit()
            conn.close()
            time.sleep(0.05) # Пауза для Telegram
        except Exception as e:
            print(f"Помилка для {user_id}: {e}")

if __name__ == "__main__":
    broadcast()
