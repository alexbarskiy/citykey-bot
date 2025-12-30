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
from telebot import types

# --- 1. НАЛАШТУВАННЯ ---
TOKEN_RAW = os.getenv("FINAL_BOT_TOKEN") or os.getenv("BOT_TOKEN") or os.getenv("TOKEN") or ""
TOKEN = re.sub(r'[^a-zA-Z0-9:_]', '', TOKEN_RAW).strip()
DB_NAME = os.getenv("DB_PATH", "data/stats.db")
ADMIN_ID = 0  # <--- ВСТАВТЕ ВАШ ID ТУТ!

# Шаблон VIP-посилання з параметрами
VIP_LINK_TEMPLATE = "https://www.citykey.com.ua/city-key-horoscope/index.html?u={name}&s={sign}"

if not TOKEN:
    print("❌ КРИТИЧНО: TOKEN не знайдено!", flush=True)
    sys.exit(1)

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

SIGNS_UA_LIST = [f'{v["emoji"]} {v["ua"]}' for v in SIGNS.values()]
UA_TO_KEY = {f'{v["emoji"]} {v["ua"]}': k for k, v in SIGNS.items()}

# --- 2. БАЗА ДАНИХ (ПІДТРИМКА 5 КОЛОНОК) ---
def get_db():
    return sqlite3.connect(DB_NAME, timeout=30)

def init_db():
    try:
        db_dir = os.path.dirname(DB_NAME)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
        
        conn = get_db()
        c = conn.cursor()
        
        # Початкове створення (базова структура)
        c.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, first_name TEXT, date TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS subs (user_id INTEGER, sign TEXT, PRIMARY KEY (user_id, sign))")
        c.execute("CREATE TABLE IF NOT EXISTS deliveries (user_id INTEGER, sign TEXT, date TEXT, PRIMARY KEY (user_id, sign, date))")
        c.execute("CREATE TABLE IF NOT EXISTS feedback (user_id INTEGER, date TEXT, rate TEXT)")
        
        # --- МІГРАЦІЯ СТРУКТУРИ ---
        c.execute("PRAGMA table_info(users)")
        columns = [info[1] for info in c.fetchall()]
        
        # Додаємо 4-ту колонку (referrer_id)
        if 'referrer_id' not in columns:
            print("🔧 База: додавання referrer_id", flush=True)
            c.execute("ALTER TABLE users ADD COLUMN referrer_id INTEGER")
            conn.commit()
            
        # Додаємо 5-ту колонку (username)
        if 'username' not in columns:
            print("🔧 База: додавання username", flush=True)
            c.execute("ALTER TABLE users ADD COLUMN username TEXT")
            conn.commit()
            
        conn.close()
        print(f"💾 База даних синхронізована (5 колонок): {DB_NAME}", flush=True)
    except Exception as e:
        print(f"❌ Помилка ініціалізації бази: {e}", flush=True)

# --- 3. ЛОГІКА ТРАФІКУ ---
def get_compatibility(sign_key):
    random.seed(int(datetime.date.today().strftime("%Y%m%d")) + len(sign_key))
    compat_key = random.choice(list(SIGNS.keys()))
    return f"💖 <b>Сумісність дня:</b> найкраще взаємодіяти з <b>{SIGNS[compat_key]['ua']}</b>"

def fetch_horo(sign_key):
    url = f'https://www.citykey.com.ua/{SIGNS[sign_key]["slug"]}/'
    try:
        r = requests.get(url, timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
        soup = bs4.BeautifulSoup(r.text, "html.parser")
        content = soup.select_one(".entry-content")
        if not content: return "Прогноз на сьогодні вже на нашому сайті!"
        p = content.find_all("p")
        txt = " ".join([item.get_text().strip() for item in p if len(item.get_text()) > 25][:2])
        return (txt[:550] + "...") if len(txt) > 550 else (txt or "Читати далі на сайті.")
    except:
        return "Детальний прогноз уже опубліковано на нашому сайті."

# --- 4. КЛАВІАТУРИ ---
def main_kb():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    markup.add(*[types.KeyboardButton(s) for s in SIGNS_UA_LIST])
    markup.row(types.KeyboardButton("💎 VIP Статус / Друзі"), types.KeyboardButton("🔔 Мої подписки"))
    markup.row(types.KeyboardButton("🔕 Відписатись від всього"))
    return markup

def inline_kb(sign_key, uid, full_text_for_share):
    markup = types.InlineKeyboardMarkup(row_width=2)
    url = f'https://www.citykey.com.ua/{SIGNS[sign_key]["slug"]}/'
    markup.add(types.InlineKeyboardButton("📖 Читати повністю", url=url))
    
    conn = get_db()
    is_sub = conn.execute("SELECT 1 FROM subs WHERE user_id=? AND sign=?", (uid, sign_key)).fetchone()
    conn.close()
    sub_text = "🔕 Відписатися" if is_sub else "🔔 Отримувати щодня"
    sub_data = f"unsub:{sign_key}" if is_sub else f"sub:{sign_key}"
    
    share_text = f"Мій гороскоп ({SIGNS[sign_key]['ua']}):\n\n{full_text_for_share}\n\nДізнайся свій тут 👇"
    share_url = f"https://t.me/share/url?url=https://t.me/City_Key_Bot&text={urllib.parse.quote(share_text)}"
    
    markup.add(
        types.InlineKeyboardButton(sub_text, callback_data=sub_data),
        types.InlineKeyboardButton("🚀 Поділитися", url=share_url)
    )
    markup.row(types.InlineKeyboardButton("👍", callback_data="rate:up"), types.InlineKeyboardButton("👎", callback_data="rate:down"))
    return markup

# --- 5. ХЕНДЛЕРИ ---
@bot.message_handler(commands=['start'])
def start(m):
    user_id = m.from_user.id
    name = m.from_user.first_name
    username = m.from_user.username
    referrer_id = None
    
    if len(m.text.split()) > 1:
        ref_candidate = m.text.split()[1]
        if ref_candidate.isdigit() and int(ref_candidate) != user_id:
            referrer_id = int(ref_candidate)

    conn = get_db()
    user_exists = conn.execute("SELECT 1 FROM users WHERE user_id=?", (user_id,)).fetchone()
    if not user_exists:
        # Вказуємо конкретні назви колонок для 5 значень
        conn.execute(
            "INSERT INTO users (user_id, first_name, username, date, referrer_id) VALUES (?,?,?,?,?)", 
            (user_id, name, username, datetime.date.today().isoformat(), referrer_id)
        )
        conn.commit()
        if referrer_id:
            try: bot.send_message(referrer_id, f"🎉 У вас новий реферал! {name} (@{username if username else 'без імені'}) приєднався.")
            except: pass
    else:
        # Оновлюємо username, якщо він змінився
        conn.execute("UPDATE users SET username=? WHERE user_id=?", (username, user_id))
        conn.commit()
    conn.close()
    bot.send_message(m.chat.id, f"✨ <b>Вітаю, {name}!</b> Оберіть свій знак зодіаку:", reply_markup=main_kb())

@bot.message_handler(func=lambda m: m.text == "💎 VIP Статус / Друзі")
def vip_status(m):
    user_id = m.from_user.id
    conn = get_db()
    count = conn.execute("SELECT COUNT(*) FROM users WHERE referrer_id=?", (user_id,)).fetchone()[0]
    sub = conn.execute("SELECT sign FROM subs WHERE user_id=? LIMIT 1", (user_id,)).fetchone()
    conn.close()
    
    sign_ua = SIGNS[sub[0]]["ua"] if sub else "Гороскоп"
    ref_link = f"https://t.me/City_Key_Bot?start={user_id}"
    
    if count >= 3:
        encoded_name = urllib.parse.quote(m.from_user.first_name)
        encoded_sign = urllib.parse.quote(sign_ua)
        personal_vip_link = VIP_LINK_TEMPLATE.format(name=encoded_name, sign=encoded_sign)
        status_text = f"🌟 <b>Ваш статус: VIP</b>\n\nВи запросили {count} друзів! Твій персональний VIP-прогноз тут:\n\n👉 <a href='{personal_vip_link}'>ВІДКРИТИ ПРЕМІУМ</a>"
    else:
        status_text = f"💎 <b>Ваш статус: Користувач</b>\n\nЗапросіть ще {3 - count} друзів для <b>VIP-статусу</b>!\n\n🔗 Твоє посилання:\n<code>{ref_link}</code>"
    
    bot.send_message(m.chat.id, status_text, disable_web_page_preview=True)

@bot.message_handler(func=lambda m: m.text in UA_TO_KEY)
def sign_handler(m):
    key = UA_TO_KEY[m.text]
    txt = fetch_horo(key)
    compat = get_compatibility(key)
    bot.send_message(m.chat.id, f"✨ <b>{m.text}</b>\n\n{txt}\n\n{compat}", reply_markup=inline_kb(key, m.from_user.id, txt), disable_web_page_preview=True)

@bot.callback_query_handler(func=lambda c: c.data.startswith('rate:'))
def handle_rate(c):
    rate = "UP" if "up" in c.data else "DOWN"
    conn = get_db()
    conn.execute("INSERT INTO feedback VALUES (?,?,?)", (c.from_user.id, datetime.date.today().isoformat(), rate))
    conn.commit()
    conn.close()
    bot.answer_callback_query(c.id, "Дякуємо за відгук!")

@bot.callback_query_handler(func=lambda c: c.data.startswith(('sub:', 'unsub:')))
def handle_sub(c):
    act, key = c.data.split(':')
    conn = get_db()
    if act == "sub":
        conn.execute("INSERT OR IGNORE INTO subs VALUES (?,?)", (c.from_user.id, key))
        bot.answer_callback_query(c.id, "Ви підписалися!")
    else:
        conn.execute("DELETE FROM subs WHERE user_id=? AND sign=?", (c.from_user.id, key))
        bot.answer_callback_query(c.id, "Відписано.")
    conn.commit()
    conn.close()
    try: bot.edit_message_reply_markup(c.message.chat.id, c.message.message_id, reply_markup=inline_kb(key, c.from_user.id, ""))
    except: pass

@bot.message_handler(commands=['stats'])
def stats(m):
    if ADMIN_ID != 0 and m.from_user.id != ADMIN_ID: return
    conn = get_db()
    u = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    s = conn.execute("SELECT COUNT(*) FROM subs").fetchone()[0]
    conn.close()
    bot.send_message(m.chat.id, f"📊 <b>АДМІН-ПАНЕЛЬ:</b>\n👥 Користувачів: {u}\n🔔 Підписок: {s}")

@bot.message_handler(func=lambda m: m.text == "🔔 Мої підписки")
def my_subs(m):
    conn = get_db()
    rows = conn.execute("SELECT sign FROM subs WHERE user_id=?", (m.from_user.id,)).fetchall()
    conn.close()
    if not rows:
        bot.send_message(m.chat.id, "У вас немає підписок.")
        return
    txt = "<b>Ваші підписки:</b>\n" + "\n".join([f"- {SIGNS[r[0]]['emoji']} {SIGNS[r[0]]['ua']}" for r in rows if r[0] in SIGNS])
    bot.send_message(m.chat.id, txt)

@bot.message_handler(func=lambda m: m.text == "🔕 Відписатись від всього")
def unsub_all(m):
    conn = get_db()
    conn.execute("DELETE FROM subs WHERE user_id=?", (m.from_user.id,))
    conn.commit()
    conn.close()
    bot.send_message(m.chat.id, "Всі підписки видалено.")

# --- 6. РОЗСИЛКА ---
def newsletter_thread():
    while True:
        try:
            now = datetime.datetime.now()
            if now.hour == 7: # 09:00 за Києвом
                is_sunday = now.weekday() == 6
                today = now.strftime("%Y-%m-%d")
                conn = get_db()
                to_send = conn.execute("""
                    SELECT s.user_id, s.sign FROM subs s 
                    LEFT JOIN deliveries d ON s.user_id = d.user_id AND s.sign = d.sign AND d.date = ?
                    WHERE d.user_id IS NULL
                """, (today,)).fetchall()
                if to_send:
                    for uid, skey in to_send:
                        try:
                            if is_sunday:
                                text = f"📅 <b>ПЛАНУЙ ТИЖДЕНЬ!</b>\n\nВеликий прогноз для знака {SIGNS[skey]['ua']} вже на нашому сайті."
                                kb = types.InlineKeyboardMarkup()
                                kb.add(types.InlineKeyboardButton("✨ Читати", url="https://www.citykey.com.ua/weekly-horoscope/"))
                            else:
                                txt = fetch_horo(skey)
                                compat = get_compatibility(skey)
                                text = f"☀️ <b>Добрий ранок! Прогноз для {SIGNS[skey]['ua']}:</b>\n\n{txt}\n\n{compat}"
                                kb = inline_kb(skey, uid, txt)
                            bot.send_message(uid, text, reply_markup=kb, disable_web_page_preview=True)
                            conn.execute("INSERT INTO deliveries VALUES (?,?,?)", (uid, skey, today))
                            conn.commit()
                            time.sleep(0.1)
                        except: pass
                conn.close()
            time.sleep(1800)
        except: time.sleep(60)

if __name__ == "__main__":
    init_db()
    threading.Thread(target=newsletter_thread, daemon=True).start()
    print("🚀 Бот City Key v2.3 (5 Columns Support) запущений!", flush=True)
    bot.infinity_polling(skip_pending=True)
