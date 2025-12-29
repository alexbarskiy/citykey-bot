import os
import datetime
import sqlite3
import requests
import bs4
import telebot
import sys
import re
import time
from telebot import types

# --- 1. СУВОРА КОНФІГУРАЦІЯ ТА ДЕБАГ ТОКЕНА ---

# Отримуємо сире значення з системи
raw_token = os.getenv("TOKEN", "")

# Очищуємо від лапок, пробілів та невидимих символів
TOKEN = re.sub(r'[\s\t\n\r\'"]+', '', raw_token).strip()

def extreme_debug_token(t):
    print("--- СУПЕР-ДІАГНОСТИКА ТОКЕНА ---", flush=True)
    if not t:
        print("❌ ТОКЕН ПУСТИЙ! Перевірте назву змінної (має бути TOKEN).", flush=True)
        return False
    
    print(f"Довжина: {len(t)} символів", flush=True)
    print(f"Перші 5 символів: {t[:5]}", flush=True)
    print(f"Останні 5 символів: {t[-5:]}", flush=True)
    
    # Перевіряємо на наявність не-ASCII символів або пробілів всередині
    has_space = " " in t
    print(f"Чи є пробіл всередині: {has_space}", flush=True)
    
    try:
        # Прямий запит до API Telegram
        test_url = f"https://api.telegram.org/bot{t}/getMe"
        r = requests.get(test_url, timeout=10)
        res = r.json()
        if res.get("ok"):
            print(f"✅ УСПІХ! Telegram впізнав бота: @{res['result']['username']}", flush=True)
            return True
        else:
            print(f"❌ ВІДМОВА! Telegram каже: {res.get('description')}", flush=True)
            print(f"Відповідь сервера: {r.text}", flush=True)
            return False
    except Exception as e:
        print(f"⚠️ Помилка зв'язку: {e}", flush=True)
        return False

# Запускаємо перевірку перед усім іншим
is_valid = extreme_debug_token(TOKEN)

# Ініціалізація об'єкта бота
bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

# --- 2. ДАНІ ЗНАКІВ ЗОДІАКУ (ПОВНИЙ СПИСОК) ---

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

SIGNS_UA_LIST = [f'{v["emoji"]} {v["ua"]}' for v in SIGNS.values()]
UA_TO_KEY = {f'{v["emoji"]} {v["ua"]}': k for k, v in SIGNS.items()}

DB_NAME = os.getenv("DB_PATH", "stats.db")

# --- 3. РОБОТА З БАЗОЮ ДАНИХ ---

def get_db():
    return sqlite3.connect(DB_NAME, timeout=20)

def init_db():
    try:
        db_dir = os.path.dirname(DB_NAME)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
        conn = get_db()
        c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, first_name TEXT, date TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS subs (user_id INTEGER, sign TEXT, PRIMARY KEY (user_id, sign))")
        c.execute("CREATE TABLE IF NOT EXISTS deliveries (user_id INTEGER, sign TEXT, date TEXT, PRIMARY KEY (user_id, sign, date))")
        conn.commit()
        conn.close()
        print("💾 База даних ініціалізована.", flush=True)
    except Exception as e:
        print(f"❌ Помилка бази: {e}", flush=True)

def reg_user(uid, name):
    try:
        conn = get_db()
        conn.execute("INSERT OR IGNORE INTO users VALUES (?,?,?)", (uid, name, datetime.date.today().isoformat()))
        conn.commit()
        conn.close()
    except: pass

# --- 4. ПАРСИНГ ТА КЛАВІАТУРИ ---

def fetch_horo(key):
    url = f'https://www.citykey.com.ua/{SIGNS[key]["slug"]}/'
    try:
        r = requests.get(url, timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
        soup = bs4.BeautifulSoup(r.text, "html.parser")
        p = soup.select_one(".entry-content p")
        txt = p.get_text().strip() if p else ""
        return (txt[:550] + "...") if len(txt) > 550 else (txt or "Прогноз на сьогодні вже на сайті!")
    except:
        return "Детальний прогноз уже опубліковано на нашому сайті."

def main_kb():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    markup.add(*[types.KeyboardButton(s) for s in SIGNS_UA_LIST])
    markup.row(types.KeyboardButton("🔔 Мої підписки"), types.KeyboardButton("🔕 Відписатись від всього"))
    return markup

def inline_kb(key, uid):
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton("Читати повний прогноз", url=f'https://www.citykey.com.ua/{SIGNS[key]["slug"]}/'))
    
    conn = get_db()
    sub = conn.execute("SELECT 1 FROM subs WHERE user_id=? AND sign=?", (uid, key)).fetchone()
    conn.close()
    
    if sub:
        kb.add(types.InlineKeyboardButton("🔕 Відписатися", callback_data=f"un:{key}"))
    else:
        kb.add(types.InlineKeyboardButton("🔔 Отримувати щодня", callback_data=f"sub:{key}"))
    return kb

# --- 5. ОБРОБНИКИ ПОВІДОМЛЕНЬ ---

@bot.message_handler(commands=['start'])
def start(m):
    reg_user(m.from_user.id, m.from_user.first_name)
    bot.send_message(m.chat.id, "✨ Вітаю! Оберіть свій знак зодіаку:", reply_markup=main_kb())

@bot.message_handler(func=lambda m: m.text in UA_TO_KEY)
def horo_msg(m):
    reg_user(m.from_user.id, m.from_user.first_name)
    key = UA_TO_KEY[m.text]
    txt = fetch_horo(key)
    bot.send_message(m.chat.id, f"✨ <b>{m.text}</b>\n\n{txt}", reply_markup=inline_kb(key, m.from_user.id))

@bot.callback_query_handler(func=lambda c: c.data.startswith(('sub:', 'un:')))
def cb(c):
    act, key = c.data.split(':')
    conn = get_db()
    if act == "sub":
        conn.execute("INSERT OR IGNORE INTO subs VALUES (?,?)", (c.from_user.id, key))
        bot.answer_callback_query(c.id, "Підписку оформлено!")
    else:
        conn.execute("DELETE FROM subs WHERE user_id=? AND sign=?", (c.from_user.id, key))
        bot.answer_callback_query(c.id, "Ви відписалися.")
    conn.commit()
    conn.close()
    try: bot.edit_message_reply_markup(c.message.chat.id, c.message.message_id, reply_markup=inline_kb(key, c.from_user.id))
    except: pass

@bot.message_handler(func=lambda m: m.text == "🔔 Мої підписки")
def my_subs(m):
    conn = get_db()
    rows = conn.execute("SELECT sign FROM subs WHERE user_id=?", (m.from_user.id,)).fetchall()
    conn.close()
    if not rows:
        bot.send_message(m.chat.id, "У вас немає активних підписок.")
        return
    res = "<b>Ваші підписки:</b>\n" + "\n".join([f"- {SIGNS[r[0]]['emoji']} {SIGNS[r[0]]['ua']}" for r in rows if r[0] in SIGNS])
    bot.send_message(m.chat.id, res)

@bot.message_handler(func=lambda m: m.text == "🔕 Відписатись від всього")
def unsub_all(m):
    conn = get_db()
    conn.execute("DELETE FROM subs WHERE user_id=?", (m.from_user.id,))
    conn.commit()
    conn.close()
    bot.send_message(m.chat.id, "Всі підписки видалено.")

# --- 6. ЗАПУСК ---

if __name__ == "__main__":
    init_db()
    if not is_valid:
        print("🛑 ЗАПУСК ЗУПИНЕНО: Токен не пройшов перевірку Telegram API.", flush=True)
        sys.exit(1)
        
    print("🚀 Бот запускається в режимі розсилки та відповідей...", flush=True)
    try:
        bot.infinity_polling(skip_pending=True)
    except Exception as e:
        print(f"🛑 Критична помилка: {e}", flush=True)
