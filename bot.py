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

# --- 1. СУВОРА КОНФІГУРАЦІЯ ТОКЕНА ---

# Отримуємо токен. Використовуємо rstrip/lstrip та регулярні вирази для видалення ВСЬОГО зайвого
raw_token = os.getenv("TOKEN", "").strip()
# Видаляємо пробіли, лапки, невидимі символи \n або \r
TOKEN = re.sub(r'[\s\t\n\r\'"]+', '', raw_token)

DB_NAME = os.getenv("DB_PATH", "stats.db")

print("--- СИСТЕМНА ДІАГНОСТИКА ---", flush=True)
print(f"Довжина токена: {len(TOKEN)} символів", flush=True)

if not TOKEN:
    print("КРИТИЧНА ПОМИЛКА: Змінна TOKEN порожня у Variables!", flush=True)
    sys.exit(1)

# Перевірка токена прямим запитом до Telegram API перед запуском
def test_token_validity(t):
    try:
        url = f"https://api.telegram.org/bot{t}/getMe"
        r = requests.get(url, timeout=10)
        data = r.json()
        if data.get("ok"):
            print(f"✅ Токен ПІДТВЕРДЖЕНО: @{data['result']['username']}", flush=True)
            return True
        else:
            print(f"❌ Telegram відхилив токен: {data.get('description')}", flush=True)
            return False
    except Exception as e:
        print(f"⚠️ Помилка мережі при перевірці токена: {e}", flush=True)
        return False

token_ok = test_token_validity(TOKEN)

# Ініціалізація бота
bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

# --- 2. ДАНІ ЗНАКІВ ЗОДІАКУ ---

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

# --- 3. РОБОТА З БАЗОЮ ДАНИХ ---

def get_db_connection():
    return sqlite3.connect(DB_NAME, timeout=20)

def init_db():
    try:
        db_dir = os.path.dirname(DB_NAME)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
        
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, first_name TEXT, date TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS subs (user_id INTEGER, sign TEXT, PRIMARY KEY (user_id, sign))")
        c.execute("CREATE TABLE IF NOT EXISTS deliveries (user_id INTEGER, sign TEXT, date TEXT, PRIMARY KEY (user_id, sign, date))")
        conn.commit()
        conn.close()
        print("База даних ініціалізована успішно.", flush=True)
    except Exception as e:
        print(f"Помилка бази даних: {e}", flush=True)

def register_user(user_id, name):
    try:
        conn = get_db_connection()
        conn.execute("INSERT OR IGNORE INTO users (user_id, first_name, date) VALUES (?,?,?)", 
                     (user_id, name, datetime.date.today().isoformat()))
        conn.commit()
        conn.close()
    except: pass

# --- 4. ПАРСИНГ ТА ЛОГІКА ---

def fetch_horoscope(sign_key):
    info = SIGNS[sign_key]
    url = f'https://www.citykey.com.ua/{info["slug"]}/'
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        r = requests.get(url, timeout=15, headers=headers)
        r.raise_for_status()
        soup = bs4.BeautifulSoup(r.text, "html.parser")
        content = soup.select_one(".entry-content")
        if not content: return "Сьогоднішній прогноз уже доступний на сайті!"
        
        paragraphs = content.find_all("p")
        text_parts = [p.get_text().strip() for p in paragraphs if len(p.get_text()) > 20]
        full_text = " ".join(text_parts[:3]).strip()
        return (full_text[:600] + "...") if len(full_text) > 600 else (full_text or "Прогноз уже на сайті!")
    except Exception as e:
        return "Детальний прогноз на сьогодні вже опубліковано на нашому сайті."

# --- 5. КЛАВІАТУРИ ---

def get_main_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    markup.add(*[types.KeyboardButton(text) for text in SIGNS_UA_LIST])
    markup.row(types.KeyboardButton("🔔 Мої підписки"), types.KeyboardButton("🔕 Відписатись від всього"))
    return markup

def get_inline_keyboard(sign_key, user_id):
    markup = types.InlineKeyboardMarkup(row_width=1)
    url = f'https://www.citykey.com.ua/{SIGNS[sign_key]["slug"]}/'
    markup.add(types.InlineKeyboardButton("Читати повний прогноз на сайті", url=url))
    
    conn = get_db_connection()
    is_sub = conn.execute("SELECT 1 FROM subs WHERE user_id=? AND sign=?", (user_id, sign_key)).fetchone()
    conn.close()

    if is_sub:
        markup.add(types.InlineKeyboardButton("🔕 Відписатися від оновлень", callback_data=f"unsub:{sign_key}"))
    else:
        markup.add(types.InlineKeyboardButton("🔔 Отримувати щодня", callback_data=f"sub:{sign_key}"))
    return markup

# --- 6. ОБРОБНИКИ ПОВІДОМЛЕНЬ ---

@bot.message_handler(commands=['start'])
def welcome(m):
    register_user(m.from_user.id, m.from_user.first_name)
    bot.send_message(m.chat.id, "<b>Вітаю!</b> ✨ Обери свій знак зодіаку:", reply_markup=get_main_keyboard())

@bot.message_handler(func=lambda m: m.text in UA_TO_KEY)
def send_sign_horo(m):
    register_user(m.from_user.id, m.from_user.first_name)
    sign_key = UA_TO_KEY[m.text]
    bot.send_chat_action(m.chat.id, 'typing')
    text = fetch_horoscope(sign_key)
    bot.send_message(m.chat.id, f"✨ <b>{m.text}</b>\n\n{text}", reply_markup=get_inline_keyboard(sign_key, m.from_user.id), disable_web_page_preview=True)

@bot.callback_query_handler(func=lambda c: c.data.startswith(('sub:', 'unsub:')))
def handle_subs(c):
    action, sign_key = c.data.split(':')
    conn = get_db_connection()
    if action == "sub":
        conn.execute("INSERT OR IGNORE INTO subs (user_id, sign) VALUES (?,?)", (c.from_user.id, sign_key))
        bot.answer_callback_query(c.id, "Ви підписалися!")
    else:
        conn.execute("DELETE FROM subs WHERE user_id=? AND sign=?", (c.from_user.id, sign_key))
        bot.answer_callback_query(c.id, "Ви відписалися.")
    conn.commit()
    conn.close()
    try: bot.edit_message_reply_markup(c.message.chat.id, c.message.message_id, reply_markup=get_inline_keyboard(sign_key, c.from_user.id))
    except: pass

@bot.message_handler(func=lambda m: m.text == "🔔 Мої підписки")
def list_my_subs(m):
    conn = get_db_connection()
    rows = conn.execute("SELECT sign FROM subs WHERE user_id=?", (m.from_user.id,)).fetchall()
    conn.close()
    if not rows:
        bot.send_message(m.chat.id, "У вас поки немає підписок.")
        return
    text = "<b>Ваші підписки:</b>\n"
    for (s_key,) in rows:
        if s_key in SIGNS: text += f"\n- {SIGNS[s_key]['emoji']} {SIGNS[s_key]['ua']}"
    bot.send_message(m.chat.id, text)

@bot.message_handler(func=lambda m: m.text == "🔕 Відписатись від всього")
def delete_all_subs(m):
    conn = get_db_connection()
    conn.execute("DELETE FROM subs WHERE user_id=?", (m.from_user.id,))
    conn.commit()
    conn.close()
    bot.send_message(m.chat.id, "Всі підписки видалено.")

# --- 7. ЗАПУСК ---

if __name__ == "__main__":
    init_db()
    if not token_ok:
        print("🛑 Бот не може бути запущений через недійсний токен.", flush=True)
        sys.exit(1)
        
    print("Бот запускається...", flush=True)
    try:
        bot.infinity_polling(skip_pending=True)
    except Exception as e:
        print(f"Критична помилка виконання: {e}", flush=True)
