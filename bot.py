import os
import datetime
import sqlite3
import requests
import bs4
import telebot
import sys
import re
import time
import threading
import random
import urllib.parse
from flask import Flask
from telebot import types

# --- 1. ВЕБ-СЕРВЕР ДЛЯ RENDER (ОБОВ'ЯЗКОВО) ---
# Без цього блоку Render Free Tier видасть помилку "Port timeout"
app = Flask(__name__)

@app.route('/')
def home():
    return "City Key Bot is Online!", 200

@app.route('/health')
def health():
    return {"status": "alive"}, 200

def run_flask():
    # Render автоматично призначає порт у змінну PORT
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- 2. НАЛАШТУВАННЯ БОТА ---
# Використовуємо BOT_TOKEN (переконайтеся, що він є у Variables на Render)
TOKEN_RAW = os.getenv("BOT_TOKEN") or os.getenv("TOKEN") or ""
TOKEN = re.sub(r'[^a-zA-Z0-9:_]', '', TOKEN_RAW).strip()
DB_NAME = "stats.db" 
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# Шаблон VIP-посилання
VIP_LINK_TEMPLATE = "https://www.citykey.com.ua/city-key-horoscope/index.html?u={name}&s={sign}"

if not TOKEN:
    print("❌ КРИТИЧНО: TOKEN не знайдено у змінних оточення Render!", flush=True)
    sys.exit(1)

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

# --- 3. ДАНІ ТА СТРУКТУРИ ---
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

def init_db():
    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, first_name TEXT, date TEXT, referrer_id INTEGER, username TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS subs (user_id INTEGER, sign TEXT, PRIMARY KEY (user_id, sign))")
        c.execute("CREATE TABLE IF NOT EXISTS deliveries (user_id INTEGER, sign TEXT, date TEXT, PRIMARY KEY (user_id, sign, date))")
        conn.commit()
        conn.close()
        print("💾 База даних ініціалізована.", flush=True)
    except Exception as e:
        print(f"⚠️ Помилка БД: {e}", flush=True)

def fetch_horo(sign_key):
    url = f'https://www.citykey.com.ua/{SIGNS[sign_key]["slug"]}/'
    try:
        r = requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
        soup = bs4.BeautifulSoup(r.text, "html.parser")
        content = soup.select_one(".entry-content")
        p = content.find_all("p") if content else []
        txt = " ".join([i.get_text().strip() for i in p if len(i.get_text()) > 25][:2])
        return (txt[:500] + "...") if len(txt) > 500 else (txt or "Читати далі на сайті.")
    except:
        return "Детальний прогноз уже опубліковано на сайті citykey.com.ua"

def main_kb():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    markup.add(*[types.KeyboardButton(s) for s in SIGNS_UA_LIST])
    markup.row(types.KeyboardButton("💎 VIP Статус / Друзі"), types.KeyboardButton("🔔 Мої підписки"))
    return markup

# --- 4. ОБРОБНИКИ ---
@bot.message_handler(commands=['start'])
def start(m):
    user_id = m.from_user.id
    ref_id = None
    if len(m.text.split()) > 1:
        candidate = m.text.split()[1]
        if candidate.isdigit() and int(candidate) != user_id:
            ref_id = int(candidate)

    try:
        conn = sqlite3.connect(DB_NAME)
        conn.execute("INSERT OR IGNORE INTO users (user_id, first_name, date, referrer_id) VALUES (?,?,?,?)", 
                     (user_id, m.from_user.first_name, datetime.date.today().isoformat(), ref_id))
        conn.commit()
        conn.close()
    except: pass
    
    bot.send_message(m.chat.id, f"✨ <b>Вітаю, {m.from_user.first_name}!</b>\nОберіть свій знак зодіаку:", reply_markup=main_kb())

@bot.message_handler(func=lambda m: m.text in UA_TO_KEY)
def send_horo(m):
    key = UA_TO_KEY[m.text]
    txt = fetch_horo(key)
    bot.send_message(m.chat.id, f"✨ <b>{m.text}</b>\n\n{txt}\n\n📖 <a href='https://www.citykey.com.ua/{SIGNS[key]['slug']}/'>Читати повністю</a>", disable_web_page_preview=True)

@bot.message_handler(func=lambda m: "vip" in m.text.lower() or "статус" in m.text.lower() or "друзі" in m.text.lower())
def vip_status(m):
    uid = m.from_user.id
    try:
        conn = sqlite3.connect(DB_NAME)
        count = conn.execute("SELECT COUNT(*) FROM users WHERE referrer_id=?", (uid,)).fetchone()[0]
        conn.close()
    except: count = 0
    
    if count >= 3 or uid == ADMIN_ID:
        encoded_name = urllib.parse.quote(m.from_user.first_name)
        link = VIP_LINK_TEMPLATE.format(name=encoded_name, sign="Horoscope")
        bot.send_message(m.chat.id, f"🌟 <b>Ваш статус: VIP!</b>\n\n👉 <a href='{link}'>ВІДКРИТИ ПРЕМІУМ</a>")
    else:
        ref_link = f"https://t.me/City_Key_Bot?start={uid}"
        bot.send_message(m.chat.id, f"💎 Запросіть ще {3-count} друзів для VIP!\n\n🔗 Твоє посилання:\n<code>{ref_link}</code>")

# --- 5. ЗАПУСК ---
if __name__ == "__main__":
    init_db()
    # Запуск Flask у фоновому потоці для Render
    threading.Thread(target=run_flask, daemon=True).start()
    
    print("🚀 Бот City Key (Render Edition) запущений!", flush=True)
    while True:
        try:
            bot.polling(none_stop=True, timeout=60, long_polling_timeout=60)
        except Exception as e:
            print(f"⚠️ Помилка Polling: {e}", flush=True)
            time.sleep(15)
