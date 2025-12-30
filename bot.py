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
app = Flask(__name__)

@app.route('/')
def home():
    return "City Key Bot is Online and Functional!", 200

def run_flask():
    # Render призначає порт автоматично
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- 2. НАЛАШТУВАННЯ ТА ТОКЕН ---
TOKEN_RAW = os.getenv("BOT_TOKEN") or os.getenv("TOKEN") or ""
TOKEN = re.sub(r'[^a-zA-Z0-9:_]', '', TOKEN_RAW).strip()
DB_NAME = "stats.db" 
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# Шаблон VIP-посилання
VIP_LINK_TEMPLATE = "https://www.citykey.com.ua/city-key-horoscope/index.html?u={name}&s={sign}"

if not TOKEN:
    print("❌ КРИТИЧНО: TOKEN не знайдено!", flush=True)
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

# Кнопки меню
BTN_MY_SUBS = "🔔 Мої підписки"
BTN_VIP_STATUS = "💎 VIP Статус / Друзі"
BTN_UNSUB_ALL = "🔕 Відписатись від всього"

# --- 4. БАЗА ДАНИХ ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, first_name TEXT, date TEXT, referrer_id INTEGER, username TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS subs (user_id INTEGER, sign TEXT, PRIMARY KEY (user_id, sign))")
    c.execute("CREATE TABLE IF NOT EXISTS deliveries (user_id INTEGER, sign TEXT, date TEXT, PRIMARY KEY (user_id, sign, date))")
    conn.commit()
    conn.close()

# --- 5. ЛОГІКА КОНТЕНТУ ---
def get_compatibility(sign_key):
    random.seed(int(datetime.date.today().strftime("%Y%m%d")) + len(sign_key))
    compat_key = random.choice(list(SIGNS.keys()))
    return f"💖 <b>Сумісність дня:</b> найкраще взаємодіяти з <b>{SIGNS[compat_key]['ua']}</b>"

def fetch_horo(sign_key):
    url = f'https://www.citykey.com.ua/{SIGNS[sign_key]["slug"]}/'
    try:
        r = requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
        soup = bs4.BeautifulSoup(r.text, "html.parser")
        content = soup.select_one(".entry-content")
        p = content.find_all("p") if content else []
        txt = " ".join([i.get_text().strip() for i in p if len(i.get_text()) > 25][:2])
        return (txt[:500] + "...") if len(txt) > 500 else (txt or "Прогноз уже на сайті.")
    except:
        return "Детальний прогноз уже на сайті citykey.com.ua"

# --- 6. КЛАВІАТУРИ ---
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
    
    conn = sqlite3.connect(DB_NAME)
    is_sub = conn.execute("SELECT 1 FROM subs WHERE user_id=? AND sign=?", (uid, sign_key)).fetchone()
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

# --- 7. ОБРОБНИКИ ---
@bot.message_handler(commands=['start'])
def start(m):
    user_id = m.from_user.id
    ref_id = None
    if len(m.text.split()) > 1:
        candidate = m.text.split()[1]
        if candidate.isdigit() and int(candidate) != user_id:
            ref_id = int(candidate)

    conn = sqlite3.connect(DB_NAME)
    conn.execute("INSERT OR IGNORE INTO users (user_id, first_name, date, referrer_id) VALUES (?,?,?,?)", 
                 (user_id, m.from_user.first_name, datetime.date.today().isoformat(), ref_id))
    conn.commit()
    conn.close()
    bot.send_message(m.chat.id, f"✨ <b>Вітаю, {m.from_user.first_name}!</b>\nОберіть свій знак зодіаку:", reply_markup=main_kb())

@bot.message_handler(func=lambda m: m.text in UA_TO_KEY)
def send_horo(m):
    key = UA_TO_KEY[m.text]
    bot.send_chat_action(m.chat.id, 'typing')
    txt = fetch_horo(key)
    compat = get_compatibility(key)
    bot.send_message(m.chat.id, f"✨ <b>{m.text}</b>\n\n{txt}\n\n{compat}", reply_markup=inline_kb(key, m.from_user.id, txt), disable_web_page_preview=True)

@bot.message_handler(func=lambda m: BTN_MY_SUBS in m.text or "підписки" in m.text.lower())
def my_subs(m):
    conn = sqlite3.connect(DB_NAME)
    rows = conn.execute("SELECT sign FROM subs WHERE user_id=?", (m.from_user.id,)).fetchall()
    conn.close()
    if not rows:
        bot.send_message(m.chat.id, "У вас немає активних підписок.")
    else:
        txt = "<b>Ваші підписки:</b>\n" + "\n".join([f"- {SIGNS[r[0]]['emoji']} {SIGNS[r[0]]['ua']}" for r in rows if r[0] in SIGNS])
        bot.send_message(m.chat.id, txt)

@bot.message_handler(func=lambda m: BTN_VIP_STATUS in m.text or "vip" in m.text.lower())
def vip_status(m):
    uid = m.from_user.id
    conn = sqlite3.connect(DB_NAME)
    count = conn.execute("SELECT COUNT(*) FROM users WHERE referrer_id=?", (uid,)).fetchone()[0]
    sub = conn.execute("SELECT sign FROM subs WHERE user_id=? LIMIT 1", (uid,)).fetchone()
    conn.close()
    
    is_admin = (ADMIN_ID != 0 and uid == ADMIN_ID)
    if count >= 3 or is_admin:
        # ПРАВИЛЬНЕ ФОРМУВАННЯ ПОСИЛАННЯ (З АНГЛІЙСЬКИМ КЛЮЧЕМ)
        sign_key = sub[0] if sub else 'aries'
        encoded_name = urllib.parse.quote(m.from_user.first_name)
        encoded_sign = urllib.parse.quote(sign_key) 
        
        personal_link = VIP_LINK_TEMPLATE.format(name=encoded_name, sign=encoded_sign)
        
        bot.send_message(
            m.chat.id,
            f"🌟 <b>ВАШ СТАТУС: VIP</b>\n\nВи запросили {count} друзів! "
            f"Твій персональний VIP-прогноз тут:\n\n👉 <a href='{personal_link}'>ВІДКРИТИ ПРЕМІУМ</a>",
            disable_web_page_preview=True
        )
    else:
        ref_link = f"https://t.me/City_Key_Bot?start={uid}"
        bot.send_message(m.chat.id, f"💎 Запросіть ще {3-count} друзів для VIP!\n\n🔗 Твоє посилання:\n<code>{ref_link}</code>")

@bot.message_handler(func=lambda m: BTN_UNSUB_ALL in m.text or "відписатись" in m.text.lower())
def unsub_all(m):
    conn = sqlite3.connect(DB_NAME)
    conn.execute("DELETE FROM subs WHERE user_id=?", (m.from_user.id,))
    conn.commit()
    conn.close()
    bot.send_message(m.chat.id, "Ви відписалися від усіх розсилок.")

@bot.callback_query_handler(func=lambda c: True)
def callback_handler(c):
    uid = c.from_user.id
    if c.data.startswith(('sub:', 'unsub:')):
        act, key = c.data.split(':')
        conn = sqlite3.connect(DB_NAME)
        if act == "sub": conn.execute("INSERT OR IGNORE INTO subs VALUES (?,?)", (uid, key))
        else: conn.execute("DELETE FROM subs WHERE user_id=? AND sign=?", (uid, key))
        conn.commit()
        conn.close()
        bot.answer_callback_query(c.id, "Оновлено!")
        try: bot.edit_message_reply_markup(c.message.chat.id, c.message.message_id, reply_markup=inline_kb(key, uid, ""))
        except: pass

# --- 8. РОЗСИЛКА (Щодня о 09:00 за Києвом) ---
def newsletter_thread():
    while True:
        try:
            now = datetime.datetime.now()
            if now.hour == 7: # 07:00 UTC = 09:00 за Києвом
                is_sunday = now.weekday() == 6
                today = now.strftime("%Y-%m-%d")
                conn = sqlite3.connect(DB_NAME)
                to_send = conn.execute("""
                    SELECT s.user_id, s.sign FROM subs s 
                    LEFT JOIN deliveries d ON s.user_id = d.user_id AND s.sign = d.sign AND d.date = ?
                    WHERE d.user_id IS NULL
                """, (today,)).fetchall()
                if to_send:
                    for uid, skey in to_send:
                        try:
                            if is_sunday:
                                text = f"📅 <b>Час планувати тиждень!</b>\nПрогноз для {SIGNS[skey]['ua']} вже на сайті."
                                kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("📖 Читати", url="https://www.citykey.com.ua/weekly-horoscope/"))
                            else:
                                txt = fetch_horo(skey)
                                text = f"☀️ <b>Твій прогноз на сьогодні ({SIGNS[skey]['ua']}):</b>\n\n{txt}"
                                kb = inline_kb(skey, uid, txt)
                            bot.send_message(uid, text, reply_markup=kb, disable_web_page_preview=True)
                            conn.execute("INSERT INTO deliveries VALUES (?,?,?)", (uid, skey, today))
                            conn.commit()
                        except: pass
                conn.close()
            time.sleep(1800) # Перевірка кожні 30 хв
        except: time.sleep(60)

# --- 9. ЗАПУСК ---
if __name__ == "__main__":
    init_db()
    # Запуск веб-сервера (для Render)
    threading.Thread(target=run_flask, daemon=True).start()
    # Запуск розсилки
    threading.Thread(target=newsletter_thread, daemon=True).start()
    
    print("🚀 Бот City Key v4.1 (VIP Fix) запущений!", flush=True)
    while True:
        try:
            bot.polling(none_stop=True, timeout=60)
        except Exception as e:
            print(f"Polling error: {e}", flush=True)
            time.sleep(15)
