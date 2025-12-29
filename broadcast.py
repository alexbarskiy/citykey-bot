import os
import sqlite3
import datetime
import time
import requests
import bs4
import telebot
from telebot.apihelper import ApiTelegramException

# Шлях до бази має збігатися з bot.py
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

def get_db_connection():
    return sqlite3.connect(DB_NAME, timeout=20)

def init_db():
    """Додано ініціалізацію, щоб скрипт не падав, якщо бази ще немає"""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS subs (user_id INTEGER, sign TEXT, PRIMARY KEY (user_id, sign))")
    c.execute("CREATE TABLE IF NOT EXISTS deliveries (user_id INTEGER, sign TEXT, date TEXT, PRIMARY KEY (user_id, sign, date))")
    conn.commit()
    conn.close()

def remove_blocked_user(user_id: int):
    """Видаляємо користувача, який заблокував бота"""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM subs WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
    print(f"User {user_id} removed (blocked bot)")

def broadcast():
    init_db()
    today = datetime.date.today().isoformat()

    conn = get_db_connection()
    c = conn.cursor()
    rows = c.execute("SELECT user_id, sign FROM subs").fetchall()
    conn.close()

    print(f"Starting broadcast for {len(rows)} subscriptions...")

    for user_id, sign in rows:
        if sign not in SIGNS: continue
        
        # Перевірка чи вже відправляли сьогодні
        conn = get_db_connection()
        sent = conn.execute("SELECT 1 FROM deliveries WHERE user_id=? AND sign=? AND date=?", (user_id, sign, today)).fetchone()
        conn.close()
        
        if sent: continue

        info = SIGNS[sign]
        # Тут можна додати виклик get_preview, як у твоєму коді
        text = f'{info["emoji"]} <b>{info["ua"]}. Гороскоп на сьогодні вже доступний!</b>'
        url = f'https://www.citykey.com.ua/{info["slug"]}/'
        
        kb = telebot.types.InlineKeyboardMarkup()
        kb.add(telebot.types.InlineKeyboardButton("Читати прогноз", url=url))

        try:
            bot.send_message(user_id, text, reply_markup=kb)
            
            # Помітка про успішну доставку
            conn = get_db_connection()
            conn.execute("INSERT OR IGNORE INTO deliveries (user_id, sign, date) VALUES (?,?,?)", (user_id, sign, today))
            conn.commit()
            conn.close()
            
            time.sleep(0.05) # Затримка для обходу лімітів Telegram
            
        except ApiTelegramException as e:
            if e.error_code == 403:
                remove_blocked_user(user_id)
            else:
                print(f"Telegram error for {user_id}: {e}")
        except Exception as e:
            print(f"General error for {user_id}: {e}")

if __name__ == "__main__":
    broadcast()
