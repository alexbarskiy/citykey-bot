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

# --- 1. НАЛАШТУВАННЯ ТА ТОКЕН ---
TOKEN_RAW = os.getenv("BOT_TOKEN") or os.getenv("TOKEN") or ""
TOKEN = re.sub(r'[^a-zA-Z0-9:_]', '', TOKEN_RAW).strip()

# Шлях до бази даних (Railway Volume)
DB_NAME = os.getenv("DB_PATH", "data/stats.db")

# ВАЖЛИВО: Вставте сюди свій Telegram ID (числовий), щоб тільки ви бачили статистику
# Дізнатися свій ID можна у бота @userinfobot
ADMIN_ID = 564858074  # Замініть на ваш ID, наприклад: 123456789

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
        db_dir = os.path.dirname(DB_NAME)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
            print(f"✅ Створено директорію для бази: {db_dir}", flush=True)
        
        conn = get_db()
        c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, first_name TEXT, date TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS subs (user_id INTEGER, sign TEXT, PRIMARY KEY (user_id, sign))")
        c.execute("CREATE TABLE IF NOT EXISTS deliveries (user_id INTEGER, sign TEXT, date TEXT, PRIMARY KEY (user_id, sign, date))")
        conn.commit()
        conn.close()
        print(f"💾 База даних ініціалізована: {DB_NAME}", flush=True)
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
    url = f'https://www.citykey.com.ua/{SIGNS[sign_key]["slug"]}/'
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, timeout=15, headers=headers)
        r.raise_for_status()
        soup = bs4.BeautifulSoup(r.text, "html.parser")
        content = soup.select_one(".entry-content")
        if not content: return "Прогноз уже на нашому сайті!"
        
        paragraphs = content.find_all("p")
        text_parts = [p.get_text().strip() for p in paragraphs if len(p.get_text()) > 30]
        full_text = " ".join(text_parts[:2]).strip()
        return (full_text[:600] + "...") if len(full_text) > 600 else (full_text or "Прогноз уже на сайті!")
    except Exception as e:
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
        f"✨ <b>Вітаю, {m.from_user.first_name}!</b>\n\nОберіть свій знак зодіаку:", 
        reply_markup=main_keyboard()
    )

# НОВА КОМАНДА СТАТИСТИКИ
@bot.message_handler(commands=['stats'])
def cmd_stats(m):
    # Перевірка, чи це адмін (якщо ви вказали ADMIN_ID вище)
    if ADMIN_ID != 0 and m.from_user.id != ADMIN_ID:
        return # Ігноруємо команду від сторонніх

    try:
        conn = get_db()
        # Загальна кількість людей, які хоч раз натиснули /start
        total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        # Кількість активних підписок (одна людина може мати кілька)
        total_subs = conn.execute("SELECT COUNT(*) FROM subs").fetchone()[0]
        # Кількість унікальних підписників
        unique_subscribers = conn.execute("SELECT COUNT(DISTINCT user_id) FROM subs").fetchone()[0]
        conn.close()

        text = (
            "📊 <b>Статистика бота:</b>\n\n"
            f"👥 Всього користувачів (база): {total_users}\n"
            f"🔔 Унікальних підписників: {unique_subscribers}\n"
            f"📈 Всього активних підписок: {total_subs}"
        )
        bot.send_message(m.chat.id, text)
    except Exception as e:
        bot.send_message(m.chat.id, f"Помилка при отриманні статистики: {e}")

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
        bot.answer_callback_query(c.id, "Ви підписалися!")
    else:
        conn.execute("DELETE FROM subs WHERE user_id=? AND sign=?", (c.from_user.id, sign_key))
        bot.answer_callback_query(c.id, "Відписано.")
    conn.commit()
    conn.close()
    try:
        bot.edit_message_reply_markup(c.message.chat.id, c.message.message_id, reply_markup=inline_keyboard(sign_key, c.from_user.id))
    except: pass

@bot.message_handler(func=lambda m: m.text == "🔔 Мої підписки")
def cmd_my_subs(m):
    conn = get_db()
    rows = conn.execute("SELECT sign FROM subs WHERE user_id=?", (m.from_user.id,)).fetchall()
    conn.close()
    if not rows:
        bot.send_message(m.chat.id, "У вас немає активних підписок.")
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
    bot.send_message(m.chat.id, "Всі ваші підписки видалено.")

# --- 6. ЗАПУСК З ОБРОБКОЮ КОНФЛІКТУ ---
if __name__ == "__main__":
    init_db()
    print("🚀 Запуск бота... Очікування з'єднання.", flush=True)
    
    while True:
        try:
            bot.infinity_polling(skip_pending=True, timeout=60, logger_level=5)
        except requests.exceptions.ReadTimeout:
            time.sleep(2)
        except telebot.apihelper.ApiTelegramException as e:
            if e.error_code == 409:
                print("⚠️ Конфлікт (409): Інший примірник бота ще працює. Спробуємо через 10 сек...", flush=True)
                time.sleep(10)
            else:
                print(f"❌ Помилка Telegram API: {e}", flush=True)
                time.sleep(5)
        except Exception as e:
            print(f"❌ Критична помилка: {e}", flush=True)
            time.sleep(5)
