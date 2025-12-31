import os
import datetime
import psycopg2  # Бібліотека для зв'язку з Postgres
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

# --- 1. ВЕБ-СЕРВЕР ДЛЯ RENDER (KEEP-ALIVE) ---
app = Flask(__name__)

@app.route('/')
def home():
    return "City Key Bot is Online with Persistent Database! 🛡️", 200

@app.route('/ping')
def ping():
    return "PONG", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- 2. НАЛАШТУВАННЯ ТА БАЗА ДАНИХ ---
TOKEN_RAW = os.getenv("BOT_TOKEN") or ""
TOKEN = re.sub(r'[^a-zA-Z0-9:_]', '', TOKEN_RAW).strip()
DATABASE_URL = os.getenv("DATABASE_URL") 
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

VIP_LINK_TEMPLATE = "https://www.citykey.com.ua/city-key-horoscope/index.html?u={name}&s={sign}"

if not TOKEN or not DATABASE_URL:
    print("❌ КРИТИЧНО: BOT_TOKEN або DATABASE_URL не знайдено в Environment!", flush=True)
    sys.exit(1)

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

# --- 3. ФУНКЦІЇ БАЗИ ДАНИХ (Supabase / Postgres) ---
def get_db_connection():
    # Підключення до хмарної бази даних
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    return conn

def init_db():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        # Таблиця користувачів
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY, 
                first_name TEXT, 
                date TEXT, 
                referrer_id BIGINT, 
                username TEXT
            )
        """)
        # Таблиця підписок
        cur.execute("""
            CREATE TABLE IF NOT EXISTS subs (
                user_id BIGINT, 
                sign TEXT, 
                PRIMARY KEY (user_id, sign)
            )
        """)
        # Таблиця доставок (для розсилки)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS deliveries (
                user_id BIGINT, 
                sign TEXT, 
                date TEXT, 
                PRIMARY KEY (user_id, sign, date)
            )
        """)
        conn.commit()
        cur.close()
        conn.close()
        print("🐘 База даних Supabase (Postgres) успішно ініціалізована!", flush=True)
    except Exception as e:
        print(f"❌ Помилка ініціалізації БД: {e}", flush=True)

# --- 4. ДАНІ ТА СТРУКТУРИ ---
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

# Кнопки меню
BTN_MY_SUBS = "🔔 Мої підписки"
BTN_VIP_STATUS = "💎 VIP Статус / Друзі"
BTN_UNSUB_ALL = "🔕 Відписатись від всього"

# --- 5. ЛОГІКА ТА ПАРСИНГ ---
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
        return "Детальний прогноз уже на сайті citykey.com.ua!"

def main_kb():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    markup.add(*[types.KeyboardButton(s) for s in SIGNS_UA_LIST])
    markup.row(types.KeyboardButton(BTN_VIP_STATUS), types.KeyboardButton(BTN_MY_SUBS))
    markup.row(types.KeyboardButton(BTN_UNSUB_ALL))
    return markup

def inline_kb(sign_key, uid, text_share):
    markup = types.InlineKeyboardMarkup(row_width=2)
    url = f'https://www.citykey.com.ua/{SIGNS[sign_key]["slug"]}/'
    markup.add(types.InlineKeyboardButton("📖 Читати повністю", url=url))
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM subs WHERE user_id=%s AND sign=%s", (uid, sign_key))
    is_sub = cur.fetchone()
    cur.close()
    conn.close()
    
    sub_text = "🔕 Відписатися" if is_sub else "🔔 Отримувати щодня"
    sub_data = f"unsub:{sign_key}" if is_sub else f"sub:{sign_key}"
    
    ref_link = f"https://t.me/City_Key_Bot?start={uid}"
    share_msg = f"Мій гороскоп ({SIGNS[sign_key]['ua']}):\n\n{text_share}\n\nДізнайся свій тут 👇"
    share_url = f"https://t.me/share/url?url={urllib.parse.quote(ref_link)}&text={urllib.parse.quote(share_msg)}"
    
    markup.add(
        types.InlineKeyboardButton(sub_text, callback_data=sub_data),
        types.InlineKeyboardButton("🚀 Поділитися", url=share_url)
    )
    return markup

# --- 6. ХЕНДЛЕРИ ---
@bot.message_handler(commands=['start'])
def start(m):
    user_id = m.from_user.id
    ref_id = None
    if len(m.text.split()) > 1:
        candidate = m.text.split()[1]
        if candidate.isdigit() and int(candidate) != user_id:
            ref_id = int(candidate)

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO users (user_id, first_name, date, referrer_id) VALUES (%s,%s,%s,%s) ON CONFLICT (user_id) DO NOTHING", 
                 (user_id, m.from_user.first_name, datetime.date.today().isoformat(), ref_id))
    conn.commit()
    cur.close()
    conn.close()
    bot.send_message(m.chat.id, f"✨ <b>Вітаю, {m.from_user.first_name}!</b>\nЯ твій астрологічний бот City Key.", reply_markup=main_kb())

@bot.message_handler(commands=['stats'])
def admin_stats(m):
    if m.from_user.id != ADMIN_ID:
        bot.send_message(m.chat.id, f"🚫 Доступ лише для адміна. Ваш ID: <code>{m.from_user.id}</code>")
        return
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    u_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM subs")
    s_count = cur.fetchone()[0]
    cur.close()
    conn.close()
    bot.send_message(m.chat.id, f"📊 <b>Статистика (Supabase):</b>\n\nЮзерів: {u_count}\nПідписок: {s_count}")

@bot.message_handler(func=lambda m: m.text in UA_TO_KEY)
def send_horo(m):
    key = UA_TO_KEY[m.text]
    txt = fetch_horo(key)
    bot.send_message(m.chat.id, f"✨ <b>{m.text}</b>\n\n{txt}", reply_markup=inline_kb(key, m.from_user.id, txt), disable_web_page_preview=True)

@bot.message_handler(func=lambda m: "vip" in m.text.lower() or "друзі" in m.text.lower())
def vip_status(m):
    uid = m.from_user.id
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users WHERE referrer_id=%s", (uid,))
    count = cur.fetchone()[0]
    cur.execute("SELECT sign FROM subs WHERE user_id=%s LIMIT 1", (uid,))
    sub = cur.fetchone()
    cur.close()
    conn.close()
    
    if count >= 3 or uid == ADMIN_ID:
        sign_key = sub[0] if sub else 'aries'
        encoded_name = urllib.parse.quote(m.from_user.first_name)
        encoded_sign = urllib.parse.quote(sign_key)
        link = VIP_LINK_TEMPLATE.format(name=encoded_name, sign=encoded_sign)
        bot.send_message(m.chat.id, f"🌟 <b>ВАШ СТАТУС: VIP!</b>\n\n👉 <a href='{link}'>ВІДКРИТИ ПРЕМІУМ</a>", disable_web_page_preview=True)
    else:
        ref_link = f"https://t.me/City_Key_Bot?start={uid}"
        bot.send_message(m.chat.id, f"💎 Запросіть ще {3-count} друзів для VIP!\n\n🔗 Твоє посилання:\n<code>{ref_link}</code>")

@bot.callback_query_handler(func=lambda c: True)
def callback_handler(c):
    uid = c.from_user.id
    if c.data.startswith(('sub:', 'unsub:')):
        act, key = c.data.split(':')
        conn = get_db_connection()
        cur = conn.cursor()
        if act == "sub": cur.execute("INSERT INTO subs (user_id, sign) VALUES (%s,%s) ON CONFLICT DO NOTHING", (uid, key))
        else: cur.execute("DELETE FROM subs WHERE user_id=%s AND sign=%s", (uid, key))
        conn.commit()
        cur.close()
        conn.close()
        bot.answer_callback_query(c.id, "Оновлено!")
        try: bot.edit_message_reply_markup(c.message.chat.id, c.message.message_id, reply_markup=inline_kb(key, uid, ""))
        except: pass

# --- 7. РОЗСИЛКА ---
def newsletter_thread():
    while True:
        try:
            now = datetime.datetime.now()
            if now.hour == 7: # 09:00 за Києвом
                today = now.strftime("%Y-%m-%d")
                conn = get_db_connection()
                cur = conn.cursor()
                cur.execute("""
                    SELECT s.user_id, s.sign FROM subs s 
                    LEFT JOIN deliveries d ON s.user_id = d.user_id AND s.sign = d.sign AND d.date = %s
                    WHERE d.user_id IS NULL
                """, (today,))
                to_send = cur.fetchall()
                
                for uid, skey in to_send:
                    try:
                        txt = fetch_horo(skey)
                        bot.send_message(uid, f"☀️ <b>Твій прогноз на сьогодні ({SIGNS[skey]['ua']}):</b>\n\n{txt}", reply_markup=inline_kb(skey, uid, txt))
                        cur.execute("INSERT INTO deliveries (user_id, sign, date) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING", (uid, skey, today))
                        conn.commit()
                    except: pass
                cur.close()
                conn.close()
            time.sleep(3600)
        except: time.sleep(60)

# --- 8. ЗАПУСК ---
if __name__ == "__main__":
    init_db()
    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=newsletter_thread, daemon=True).start()
    
    print("🚀 City Key v5.0 (Supabase/Postgres) Online!", flush=True)
    while True:
        try:
            bot.polling(none_stop=True, timeout=60)
        except Exception as e:
            print(f"Polling error: {e}", flush=True)
            time.sleep(15)
