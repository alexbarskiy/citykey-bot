import os
import datetime
import sqlite3
import requests
import bs4
import telebot
import sys
import re
from telebot import types

# --- 1. НАЛАШТУВАННЯ ТА ТОКЕН ---
# Використовуємо BOT_TOKEN, який ми успішно налаштували
TOKEN_RAW = os.getenv("BOT_TOKEN") or os.getenv("TOKEN") or ""
TOKEN = re.sub(r'[^a-zA-Z0-9:_]', '', TOKEN_RAW).strip()

# Шлях до бази даних (Railway Volume)
# Якщо DB_PATH не вказано, створить у поточній папці
DB_NAME = os.getenv("DB_PATH", "data/stats.db")

if not TOKEN:
    print("❌ КРИТИЧНО: TOKEN не знайдено!", flush=True)
    sys.exit(1)

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

# --- 2. СТРУКТУРА ДАНИХ ---
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
def get_db():
    return sqlite3.connect(DB_NAME, timeout=20)

def init_db():
    try:
        # Створення папки для бази (якщо це /app/data/...)
        db_dir = os.path.dirname(DB_NAME)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
            print(f"✅ Створено директорію для бази: {db_dir}", flush=True)
        
        conn = get_db()
        c = conn.cursor()
        # Користувачі
        c.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, first_name TEXT, date TEXT)")
        # Підписки
        c.execute("CREATE TABLE IF NOT EXISTS subs (user_id INTEGER, sign TEXT, PRIMARY KEY (user_id, sign))")
        # Історія відправок
        c.execute("CREATE TABLE IF NOT EXISTS deliveries (user_id INTEGER, sign TEXT, date TEXT, PRIMARY KEY (user_id, sign, date))")
        conn.commit()
        conn.close()
        print(f"💾 База даних ініціалізована за шляхом: {DB_NAME}", flush=True)
    except Exception as e:
        print(f"❌ Помилка ініціалізації бази: {e}", flush=True)

def register_user(user_id, name):
    try:
        conn = get_db()
        conn.execute("INSERT OR IGNORE INTO users VALUES (?,?,?)", (user_id, name, datetime.date.today().isoformat()))
        conn.commit()
        conn.close()
    except: pass

# --- 4. ПАРСИНГ ТА КЛАВІАТУРИ ---
def fetch_horoscope(sign_key):
    """Отримання тексту гороскопу з сайту citykey.com.ua"""
    url = f'https://www.citykey.com.ua/{SIGNS[sign_key]["slug"]}/'
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        r = requests.get(url, timeout=15, headers=headers)
        r.raise_for_status()
        soup = bs4.BeautifulSoup(r.text, "html.parser")
        
        # Шукаємо контент гороскопу
        content = soup.select_one(".entry-content")
        if not content:
            return "Сьогоднішній прогноз уже доступний на нашому сайті!"
        
        paragraphs = content.find_all("p")
        # Фільтруємо занадто короткі або службові абзаци
        text_parts = [p.get_text().strip() for p in paragraphs if len(p.get_text()) > 30]
        full_text = " ".join(text_parts[:2]).strip()
        
        if len(full_text) > 600:
            return full_text[:600] + "..."
        return full_text or "Прогноз уже на сайті!"
    except Exception as e:
        print(f"Помилка парсингу для {sign_key}: {e}", flush=True)
        return "Детальний прогноз на сьогодні вже опубліковано на нашому сайті."

def main_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    btns = [types.KeyboardButton(text) for text in SIGNS_UA_LIST]
    markup.add(*btns)
    markup.row(types.KeyboardButton("🔔 Мої підписки"), types.KeyboardButton("🔕 Відписатись від всього"))
    return markup

def inline_keyboard(sign_key, user_id):
    markup = types.InlineKeyboardMarkup(row_width=1)
    url = f'https://www.citykey.com.ua/{SIGNS[sign_key]["slug"]}/'
    markup.add(types.InlineKeyboardButton("Читати повний прогноз на сайті", url=url))
    
    # Перевірка статусу підписки
    conn = get_db()
    is_sub = conn.execute("SELECT 1 FROM subs WHERE user_id=? AND sign=?", (user_id, sign_key)).fetchone()
    conn.close()

    if is_sub:
        markup.add(types.InlineKeyboardButton("🔕 Відписатися від оновлень", callback_data=f"unsub:{sign_key}"))
    else:
        markup.add(types.InlineKeyboardButton("🔔 Отримувати цей знак щодня", callback_data=f"sub:{sign_key}"))
    return markup

# --- 5. ОБРОБНИКИ ПОВІДОМЛЕНЬ ---
@bot.message_handler(commands=['start'])
def cmd_start(m):
    register_user(m.from_user.id, m.from_user.first_name)
    bot.send_message(
        m.chat.id, 
        f"✨ <b>Вітаю, {m.from_user.first_name}!</b>\n\nЯ твій персональний астролог. Оберіть свій знак зодіаку, щоб отримати прогноз або підписатися на щоденну розсилку:", 
        reply_markup=main_keyboard()
    )

@bot.message_handler(func=lambda m: m.text in UA_TO_KEY)
def handle_sign(m):
    register_user(m.from_user.id, m.from_user.first_name)
    sign_key = UA_TO_KEY[m.text]
    
    bot.send_chat_action(m.chat.id, 'typing')
    text = fetch_horoscope(sign_key)
    
    bot.send_message(
        m.chat.id, 
        f"✨ <b>{m.text}</b>\n\n{text}", 
        reply_markup=inline_keyboard(sign_key, m.from_user.id),
        disable_web_page_preview=True
    )

@bot.callback_query_handler(func=lambda c: c.data.startswith(('sub:', 'unsub:')))
def handle_callback(c):
    action, sign_key = c.data.split(':')
    conn = get_db()
    
    if action == "sub":
        conn.execute("INSERT OR IGNORE INTO subs (user_id, sign) VALUES (?,?)", (c.from_user.id, sign_key))
        bot.answer_callback_query(c.id, "Ви підписалися! Прогноз надходитиме щоранку.")
    else:
        conn.execute("DELETE FROM subs WHERE user_id=? AND sign=?", (c.from_user.id, sign_key))
        bot.answer_callback_query(c.id, "Ви відписалися від цього знака.")
    
    conn.commit()
    conn.close()
    
    # Оновлення кнопок під повідомленням
    try:
        bot.edit_message_reply_markup(c.message.chat.id, c.message.message_id, reply_markup=inline_keyboard(sign_key, c.from_user.id))
    except: pass

@bot.message_handler(func=lambda m: m.text == "🔔 Мої підписки")
def cmd_my_subs(m):
    conn = get_db()
    rows = conn.execute("SELECT sign FROM subs WHERE user_id=?", (m.from_user.id,)).fetchall()
    conn.close()
    
    if not rows:
        bot.send_message(m.chat.id, "У вас поки немає активних підписок. Оберіть знак зодіаку та натисніть кнопку підписки під прогнозом.")
        return
    
    text = "<b>Ваші активні підписки:</b>\n"
    for (s_key,) in rows:
        if s_key in SIGNS:
            text += f"\n- {SIGNS[s_key]['emoji']} {SIGNS[s_key]['ua']}"
    
    bot.send_message(m.chat.id, text)

@bot.message_handler(func=lambda m: m.text == "🔕 Відписатись від всього")
def cmd_unsub_all(m):
    conn = get_db()
    conn.execute("DELETE FROM subs WHERE user_id=?", (m.from_user.id,))
    conn.commit()
    conn.close()
    bot.send_message(m.chat.id, "Всі ваші підписки успішно видалено.")

# --- 6. ЗАПУСК ---
if __name__ == "__main__":
    init_db()
    print("--- Бот запускає опитування (polling)... ---", flush=True)
    try:
        bot.infinity_polling(skip_pending=True, timeout=60)
    except Exception as e:
        print(f"Критична помилка: {e}", flush=True)
