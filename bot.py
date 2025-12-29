import os
import datetime
import sqlite3
import requests
import bs4
import telebot
import sys
from telebot import types

# 1. КОНФІГУРАЦІЯ ТА ДІАГНОСТИКА
# Отримуємо токен та шлях до бази з перемінних Railway
TOKEN = os.getenv("TOKEN", "").strip().replace('"', '').replace("'", "")
DB_NAME = os.getenv("DB_PATH", "stats.db")

print("--- ДІАГНОСТИКА СИСТЕМИ ---", flush=True)
print(f"Довжина токена: {len(TOKEN)} символів", flush=True)
if len(TOKEN) > 10:
    print(f"Токен починається на: {TOKEN[:6]}...", flush=True)
else:
    print("УВАГА: Токен порожній або надто короткий!", flush=True)

if not TOKEN:
    print("КРИТИЧНА ПОМИЛКА: TOKEN не знайдено у Variables на Railway!", flush=True)
    sys.exit(1)

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

# 2. ДАНІ ЗНАКІВ ЗОДІАКУ
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

# Списки для швидкого пошуку в кнопках
SIGNS_UA_LIST = [f'{v["emoji"]} {v["ua"]}' for v in SIGNS.values()]
UA_TO_KEY = {f'{v["emoji"]} {v["ua"]}': k for k, v in SIGNS.items()}

# 3. ФУНКЦІЇ БАЗИ ДАНИХ
def get_db():
    # Використовуємо timeout для уникнення блокувань на Railway
    return sqlite3.connect(DB_NAME, timeout=15)

def init_db():
    try:
        # Створюємо папку для бази, якщо вона вказана (наприклад, /data/)
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
        print("База даних готова до роботи.", flush=True)
    except Exception as e:
        print(f"Помилка ініціалізації бази: {e}", flush=True)

def ensure_user(uid, name):
    conn = get_db()
    conn.execute("INSERT OR IGNORE INTO users VALUES (?,?,?)", (uid, name, datetime.date.today().isoformat()))
    conn.commit()
    conn.close()

def db_action(action, uid, sign=None):
    conn = get_db()
    res = None
    if action == "sub":
        conn.execute("INSERT OR IGNORE INTO subs VALUES (?,?)", (uid, sign))
    elif action == "unsub":
        conn.execute("DELETE FROM subs WHERE user_id=? AND sign=?", (uid, sign))
    elif action == "unsub_all":
        conn.execute("DELETE FROM subs WHERE user_id=?", (uid,))
    elif action == "check":
        res = conn.execute("SELECT 1 FROM subs WHERE user_id=? AND sign=?", (uid, sign)).fetchone()
    elif action == "get_my":
        res = conn.execute("SELECT sign FROM subs WHERE user_id=?", (uid,)).fetchall()
    conn.commit()
    conn.close()
    return res

# 4. ПАРСИНГ ТА КЛАВІАТУРИ
def get_preview(sign_key):
    info = SIGNS[sign_key]
    url = f'https://www.citykey.com.ua/{info["slug"]}/'
    try:
        r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        soup = bs4.BeautifulSoup(r.text, "html.parser")
        p = soup.select_one(".entry-content p")
        txt = p.get_text().strip() if p else ""
        return (txt[:500] + "...") if len(txt) > 500 else (txt or "Прогноз уже на сайті!")
    except:
        return "Сьогоднішній прогноз уже доступний на нашому сайті."

def main_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    btns = [types.KeyboardButton(s) for s in SIGNS_UA_LIST]
    kb.add(*btns)
    kb.row(types.KeyboardButton("🔔 Мої підписки"), types.KeyboardButton("🔕 Відписатись від всього"))
    return kb

def inline_kb(sign_key, uid):
    kb = types.InlineKeyboardMarkup(row_width=1)
    url = f'https://www.citykey.com.ua/{SIGNS[sign_key]["slug"]}/'
    kb.add(types.InlineKeyboardButton("Читати повний прогноз", url=url))
    
    if db_action("check", uid, sign_key):
        kb.add(types.InlineKeyboardButton("🔕 Відписатися від оновлень", callback_data=f"un:{sign_key}"))
    else:
        kb.add(types.InlineKeyboardButton("🔔 Отримувати щодня", callback_data=f"sub:{sign_key}"))
    return kb

# 5. ОБРОБНИКИ КОМАНД
@bot.message_handler(commands=['start'])
def cmd_start(m):
    ensure_user(m.from_user.id, m.from_user.first_name)
    bot.send_message(m.chat.id, "✨ Привіт! Я твій зірковий провідник.\nОбери свій знак зодіаку, щоб отримати прогноз:", reply_markup=main_kb())

@bot.message_handler(func=lambda m: m.text in UA_TO_KEY)
def send_horo(m):
    ensure_user(m.from_user.id, m.from_user.first_name)
    key = UA_TO_KEY[m.text]
    txt = get_preview(key)
    bot.send_message(m.chat.id, f"<b>{m.text}</b>\n\n{txt}", reply_markup=inline_kb(key, m.from_user.id))

@bot.callback_query_handler(func=lambda c: c.data.startswith(('sub:', 'un:')))
def handle_callback(c):
    act, key = c.data.split(':')
    if act == "sub":
        db_action("sub", c.from_user.id, key)
        bot.answer_callback_query(c.id, "Підписку оформлено! Чекайте прогноз завтра зранку.")
    else:
        db_action("unsub", c.from_user.id, key)
        bot.answer_callback_query(c.id, "Ви відписалися.")
    
    try:
        bot.edit_message_reply_markup(c.message.chat.id, c.message.message_id, reply_markup=inline_kb(key, c.from_user.id))
    except: pass

@bot.message_handler(func=lambda m: m.text == "🔔 Мої підписки")
def show_subs(m):
    rows = db_action("get_my", m.from_user.id)
    if not rows:
        bot.send_message(m.chat.id, "У вас поки немає активних підписок.")
        return
    
    res = "<b>Ваші підписки:</b>\n"
    for (key,) in rows:
        if key in SIGNS:
            res += f"- {SIGNS[key]['emoji']} {SIGNS[key]['ua']}\n"
    bot.send_message(m.chat.id, res)

@bot.message_handler(func=lambda m: m.text == "🔕 Відписатись від всього")
def unsub_all(m):
    db_action("unsub_all", m.from_user.id)
    bot.send_message(m.chat.id, "Ви відписані від усіх розсилок.")

@bot.message_handler(func=lambda m: True)
def default_msg(m):
    bot.send_message(m.chat.id, "Будь ласка, скористайтеся меню нижче для вибору знака зодіаку.", reply_markup=main_kb())

# 6. ЗАПУСК
if __name__ == "__main__":
    init_db()
    print("Бот запускається...", flush=True)
    try:
        bot.infinity_polling(skip_pending=True)
    except Exception as e:
        print(f"Критична помилка: {e}", flush=True)
