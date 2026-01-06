import os
import datetime
import psycopg2
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

# --- 1. ВЕБ-СЕРВЕР ДЛЯ KEEP-ALIVE (RENDER) ---
app = Flask(__name__)

@app.route('/')
def home():
    return "City Key Bot is Online (Supabase v5.3) 🛡️", 200

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
ADMIN_ID = int(os.getenv("ADMIN_ID", "564858074"))

VIP_LINK_TEMPLATE = "https://www.citykey.com.ua/city-key-horoscope/index.html?u={name}&s={sign}"

if not TOKEN or not DATABASE_URL:
    print("❌ КРИТИЧНО: BOT_TOKEN або DATABASE_URL не знайдено!", flush=True)
    sys.exit(1)

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

# --- 3. ФУНКЦІЇ POSTGRESQL (SUPABASE) ---
def get_db_connection():
    conn_str = DATABASE_URL
    if "sslmode" not in conn_str:
        conn_str += "?sslmode=require"
    return psycopg2.connect(conn_str)

def init_db():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY, 
                first_name TEXT, 
                date TEXT, 
                referrer_id BIGINT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS subs (
                user_id BIGINT, 
                sign TEXT, 
                PRIMARY KEY (user_id, sign)
            )
        """)
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
        print("🐘 База Supabase (Postgres) готова та синхронізована.", flush=True)
    except Exception as e:
        print(f"❌ Помилка ініціалізації БД: {e}", flush=True)

# --- 4. ДАНІ ---
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

UA_TO_KEY = {f'{v["emoji"]} {v["ua"]}': k for k, v in SIGNS.items()}

# --- 5. КОНТЕНТ ТА ПАРСИНГ ---
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
        return "Детальний прогноз уже на сайті citykey.com.ua"

def get_compatibility(sign_key):
    # Генерація сумісності на основі дати (однакова для всіх на один день)
    random.seed(int(datetime.date.today().strftime("%Y%m%d")) + len(sign_key))
    compat_key = random.choice(list(SIGNS.keys()))
    return f"💖 <b>Сумісність дня:</b> найкраще взаємодіяти з <b>{SIGNS[compat_key]['ua']}</b>"

# --- 6. КЛАВІАТУРИ ---
def main_kb():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    markup.add(*[types.KeyboardButton(f'{v["emoji"]} {v["ua"]}') for v in SIGNS.values()])
    markup.row(types.KeyboardButton("💎 VIP Кімната"), types.KeyboardButton("🔔 Мої підписки"))
    markup.row(types.KeyboardButton("🔕 Відписатись від всього"))
    return markup

def inline_kb(sign_key, uid, text_share=""):
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
    
    # Кнопка поділитися
    ref_link = f"https://t.me/City_Key_Bot?start={uid}"
    share_msg = f"Мій гороскоп ({SIGNS[sign_key]['ua']}):\n\n{text_share}\n\nДізнайся свій тут 👇"
    share_url = f"https://t.me/share/url?url={urllib.parse.quote(ref_link)}&text={urllib.parse.quote(share_msg)}"
    
    markup.add(
        types.InlineKeyboardButton(sub_text, callback_data=f"toggle:{sign_key}"),
        types.InlineKeyboardButton("🚀 Поділитися", url=share_url)
    )
    return markup

# --- 7. ОБРОБНИКИ ПОВІДОМЛЕНЬ ---
@bot.message_handler(commands=['start'])
def start(m):
    uid = m.from_user.id
    ref_id = int(m.text.split()[1]) if len(m.text.split()) > 1 and m.text.split()[1].isdigit() else None
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO users (user_id, first_name, date, referrer_id) VALUES (%s,%s,%s,%s) ON CONFLICT (user_id) DO NOTHING", 
                (uid, m.from_user.first_name, datetime.date.today().isoformat(), ref_id))
    conn.commit()
    cur.close()
    conn.close()
    bot.send_message(m.chat.id, f"✨ <b>Вітаю, {m.from_user.first_name}!</b>\nЯ твій астрологічний бот City Key.", reply_markup=main_kb())

@bot.message_handler(commands=['stats'])
def admin_stats(m):
    if m.from_user.id != ADMIN_ID:
        bot.send_message(m.chat.id, f"🚫 Доступ лише для адміна. Ваш ID: {m.from_user.id}")
        return
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    u_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM subs")
    s_count = cur.fetchone()[0]
    cur.close()
    conn.close()
    bot.send_message(m.chat.id, f"📊 <b>Статистика (Supabase):</b>\n\nЮзерів: {u_count}\nАктивних підписок: {s_count}")

def _get_all_sub_users():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT user_id FROM subs")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [r[0] for r in rows]

@bot.message_handler(commands=['post'])
def admin_post(m):
    if m.from_user.id != ADMIN_ID:
        bot.send_message(m.chat.id, f"🚫 Доступ лише для адміна. Ваш ID: {m.from_user.id}")
        return

    raw = m.text or ""
    text = raw.replace("/post", "", 1).strip()

    if not text:
        bot.send_message(m.chat.id, "Напиши так: /post твій текст")
        return

    users = _get_all_sub_users()
    sent = 0

    for uid in users:
        try:
            bot.send_message(uid, text, disable_web_page_preview=True)
            sent += 1
        except:
            pass

    bot.send_message(m.chat.id, f"Готово. Відправлено: {sent}")

@bot.message_handler(commands=['post_compat'])
def admin_post_compat(m):
    if m.from_user.id != ADMIN_ID:
        bot.send_message(m.chat.id, f"🚫 Доступ лише для адміна. Ваш ID: {m.from_user.id}")
        return

    url = "https://www.citykey.com.ua/test-na-sumisnist-znakiv-zodiaku/"
    hook_list = [
    "Іноді в середині дня стає зрозуміло, з ким легко, а з ким виникає напруга буквально з дрібниць. "
    "У такі моменти цікаво подивитись не на слова, а на поєднання характерів. "
    "Я сьогодні заглянув у тест на сумісність і він несподівано добре пояснює такі речі.",
    "Обідня перерва — цікавий момент для невеликого експерименту. Дві хвилини уваги можуть дати несподіваний інсайт про взаємодію з людьми.",
    "Іноді хочеться чесного натяку на вашу динаміку без зайвих слів. У таких випадках цікаво просто подивитись, як сходяться знаки у парі."
]

    text = random.choice(hook_list)

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("Перевірити сумісність", url=url))

    users = _get_all_sub_users()
    sent = 0

    for uid in users:
        try:
            bot.send_message(uid, text, reply_markup=kb, disable_web_page_preview=True)
            sent += 1
        except:
            pass

    bot.send_message(m.chat.id, f"Готово. Відправлено: {sent}")


@bot.message_handler(func=lambda m: m.text in UA_TO_KEY)
def send_horo(m):
    key = UA_TO_KEY[m.text]
    txt = fetch_horo(key)
    compat = get_compatibility(key)
    bot.send_message(m.chat.id, f"✨ <b>{m.text}</b>\n\n{txt}\n\n{compat}", reply_markup=inline_kb(key, m.from_user.id, txt), disable_web_page_preview=True)

@bot.message_handler(func=lambda m: "підписки" in m.text.lower())
def list_subs(m):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT sign FROM subs WHERE user_id=%s", (m.from_user.id,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    
    if not rows:
        bot.send_message(m.chat.id, "У вас поки немає активних підписок.")
    else:
        text = "<b>Ваші підписки:</b>\n"
        for r in rows:
            sign = SIGNS.get(r[0])
            if sign: text += f"- {sign['emoji']} {sign['ua']}\n"
        bot.send_message(m.chat.id, text)

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
        name = urllib.parse.quote(m.from_user.first_name)
        link = VIP_LINK_TEMPLATE.format(name=name, sign=sign_key)
        bot.send_message(m.chat.id, f"🌟 <b>ВАШ СТАТУС: VIP!</b>\n\n👉 <a href='{link}'>ВІДКРИТИ ПРЕМІУМ</a>", disable_web_page_preview=True)
    else:
        ref_link = f"https://t.me/City_Key_Bot?start={uid}"
        bot.send_message(m.chat.id, f"💎 Запросіть ще {3-count} друзів для VIP!\n\n🔗 Твоє посилання:\n<code>{ref_link}</code>")

@bot.message_handler(func=lambda m: "відписатись" in m.text.lower())
def unsub_all(m):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM subs WHERE user_id=%s", (m.from_user.id,))
    conn.commit()
    cur.close()
    conn.close()
    bot.send_message(m.chat.id, "Ви відписалися від усіх розсилок.")

@bot.callback_query_handler(func=lambda c: c.data.startswith('toggle:'))
def callback_handler(c):
    uid = c.from_user.id
    key = c.data.split(':')[1]
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM subs WHERE user_id=%s AND sign=%s", (uid, key))
    if cur.fetchone():
        cur.execute("DELETE FROM subs WHERE user_id=%s AND sign=%s", (uid, key))
    else:
        cur.execute("INSERT INTO subs (user_id, sign) VALUES (%s,%s) ON CONFLICT DO NOTHING", (uid, key))
    conn.commit()
    cur.close()
    conn.close()
    bot.answer_callback_query(c.id, "Оновлено!")
    try:
        bot.edit_message_reply_markup(c.message.chat.id, c.message.message_id, reply_markup=inline_kb(key, uid, ""))
    except:
        pass

# --- 8. РОЗСИЛКА (Щодня о 09:00 за Києвом) ---
def newsletter_thread():
    while True:
        try:
            now = datetime.datetime.now()
            # 07:00 UTC = 09:00 за Києвом
            if now.hour == 7:
                today = now.strftime("%Y-%m-%d")
                conn = get_db_connection()
                cur = conn.cursor()
                # Знайти всі підписки, по яких ще не було відправки сьогодні
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
                    except:
                        pass
                cur.close()
                conn.close()
            time.sleep(3000) # Перевірка кожні 50 хв
        except Exception as e:
            print(f"Помилка розсилки: {e}")
            time.sleep(60)

# --- 9. ЗАПУСК ---
if __name__ == "__main__":
    init_db()
    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=newsletter_thread, daemon=True).start()
    
    print("🚀 City Key v5.3 Full persistent online!", flush=True)

try:
    bot.remove_webhook()
except Exception:
    pass

while True:
    try:
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
    except Exception as e:
        print(f"❌ Polling error: {e}", flush=True)
        time.sleep(5)




