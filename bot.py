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

# --- 1. ПРИМУСОВА ДІАГНОСТИКА ТА ОБХІД КЕШУ ---
now = datetime.datetime.now().strftime("%H:%M:%S")

# Спробуємо знайти всі можливі варіанти токена в системі
env_vars = os.environ
potential_tokens = {k: v for k, v in env_vars.items() if "TOKEN" in k.upper()}

print(f"--- АНАЛІЗ СЕРЕДОВИЩА RAILWAY [{now}] ---", flush=True)
print(f"Знайдено змінних, що містять 'TOKEN': {list(potential_tokens.keys())}", flush=True)

# ПРІОРИТЕТ: використовуємо тільки BOT_TOKEN, якщо він є
TOKEN_RAW = os.getenv("BOT_TOKEN") or ""
USED_VAR = "BOT_TOKEN"

if not TOKEN_RAW:
    print("⚠️ Попередження: BOT_TOKEN не знайдено. Перевіряємо застарілу змінну TOKEN...", flush=True)
    TOKEN_RAW = os.getenv("TOKEN") or ""
    USED_VAR = "TOKEN"

# Жорстка чистка токена
TOKEN = re.sub(r'[^a-zA-Z0-9:_]', '', TOKEN_RAW).strip()

def verify_token_identity(t, name):
    if not t:
        print(f"❌ КРИТИЧНО: Жодна змінна токена не знайдена!", flush=True)
        return False
    
    print(f"Використовується: {name}", flush=True)
    print(f"Відбиток: {t[:6]}...{t[-5:]}", flush=True)
    
    try:
        # Пряма перевірка через API Telegram
        r = requests.get(f"https://api.telegram.org/bot{t}/getMe", timeout=10)
        res = r.json()
        if res.get("ok"):
            print(f"✅ УСПІХ! Бот впізнаний: @{res['result']['username']}", flush=True)
            return True
        else:
            print(f"❌ ВІДМОВА: Telegram каже {res.get('description')} (код {res.get('error_code')})", flush=True)
            return False
    except Exception as e:
        print(f"⚠️ Помилка зв'язку: {e}", flush=True)
        return False

# Перевірка перед запуском
token_ok = verify_token_identity(TOKEN, USED_VAR)
bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

# --- 2. ДАНІ ТА СТРУКТУРА ---
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

# --- 3. БАЗА ДАНИХ ---
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
        print("💾 База даних готова.", flush=True)
    except Exception as e:
        print(f"❌ База: {e}")

def save_user(uid, name):
    try:
        conn = get_db()
        conn.execute("INSERT OR IGNORE INTO users VALUES (?,?,?)", (uid, name, datetime.date.today().isoformat()))
        conn.commit()
        conn.close()
    except: pass

# --- 4. ЛОГІКА ТА КЛАВІАТУРИ ---
def fetch_horo(key):
    url = f'https://www.citykey.com.ua/{SIGNS[key]["slug"]}/'
    try:
        r = requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
        soup = bs4.BeautifulSoup(r.text, "html.parser")
        p = soup.select_one(".entry-content p")
        txt = p.get_text().strip() if p else ""
        return (txt[:550] + "...") if len(txt) > 550 else (txt or "Прогноз уже на сайті!")
    except:
        return "Детальний прогноз на сайті."

def get_main_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    kb.add(*[types.KeyboardButton(s) for s in SIGNS_UA_LIST])
    kb.row(types.KeyboardButton("🔔 Мої підписки"), types.KeyboardButton("🔕 Відписатись від всього"))
    return kb

def get_inline_kb(key, uid):
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

# --- 5. ОБРОБНИКИ ---
@bot.message_handler(commands=['start'])
def welcome(m):
    save_user(m.from_user.id, m.from_user.first_name)
    bot.send_message(m.chat.id, "👋 Привіт! Оберіть свій знак зодіаку:", reply_markup=get_main_kb())

@bot.message_handler(func=lambda m: m.text in UA_TO_KEY)
def show_horo(m):
    save_user(m.from_user.id, m.from_user.first_name)
    key = UA_TO_KEY[m.text]
    txt = fetch_horo(key)
    bot.send_message(m.chat.id, f"✨ <b>{m.text}</b>\n\n{txt}", reply_markup=get_inline_kb(key, m.from_user.id))

@bot.callback_query_handler(func=lambda c: c.data.startswith(('sub:', 'un:')))
def callback_handler(c):
    act, key = c.data.split(':')
    conn = get_db()
    if act == "sub":
        conn.execute("INSERT OR IGNORE INTO subs VALUES (?,?)", (c.from_user.id, key))
        bot.answer_callback_query(c.id, "Підписано!")
    else:
        conn.execute("DELETE FROM subs WHERE user_id=? AND sign=?", (c.from_user.id, key))
        bot.answer_callback_query(c.id, "Відписано.")
    conn.commit()
    conn.close()
    try: bot.edit_message_reply_markup(c.message.chat.id, c.message.message_id, reply_markup=get_inline_kb(key, c.from_user.id))
    except: pass

@bot.message_handler(func=lambda m: m.text == "🔔 Мої підписки")
def my_subscriptions(m):
    conn = get_db()
    rows = conn.execute("SELECT sign FROM subs WHERE user_id=?", (m.from_user.id,)).fetchall()
    conn.close()
    if not rows:
        bot.send_message(m.chat.id, "У вас немає активних підписок.")
        return
    text = "<b>Ваші підписки:</b>\n" + "\n".join([f"- {SIGNS[r[0]]['emoji']} {SIGNS[r[0]]['ua']}" for r in rows if r[0] in SIGNS])
    bot.send_message(m.chat.id, text)

@bot.message_handler(func=lambda m: m.text == "🔕 Відписатись від всього")
def unsub_all_handler(m):
    conn = get_db()
    conn.execute("DELETE FROM subs WHERE user_id=?", (m.from_user.id,))
    conn.commit()
    conn.close()
    bot.send_message(m.chat.id, "Всі підписки видалено.")

# --- 6. ЗАПУСК ---
if __name__ == "__main__":
    init_db()
    if not token_ok:
        print(f"🛑 ЗАПУСК ПЕРЕРВАНО: Railway не оновив токен. Зараз у системі: {TOKEN[:5]}...{TOKEN[-5:]}", flush=True)
        sys.exit(1)
        
    print("🚀 Бот запущений успішно!", flush=True)
    try:
        bot.infinity_polling(skip_pending=True)
    except Exception as e:
        print(f"🛑 Помилка: {e}", flush=True)
