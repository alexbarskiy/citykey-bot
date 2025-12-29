import os
import datetime
import sqlite3
import requests
import bs4
import telebot
from telebot import types

# Читаємо шлях до бази з налаштувань Railway. 
# Якщо змінної DB_PATH немає, використовуємо локальний файл stats.db.
DB_NAME = os.getenv("DB_PATH", "stats.db")
TOKEN = os.getenv("TOKEN", "").strip()

if not TOKEN:
    raise RuntimeError("TOKEN env var is missing. Додайте TOKEN у Variables на Railway.")

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

# Словник з даними знаків (slug для сайту, емодзі та назва)
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

# Допоміжні списки для кнопок
SIGNS_UA_BUTTONS = [f'{v["emoji"]} {v["ua"]}' for v in SIGNS.values()]
UA_TO_SIGN = {f'{v["emoji"]} {v["ua"]}': k for k, v in SIGNS.items()}

# --- Робота з Базою Даних (SQLite) ---

def get_db_connection():
    # timeout 10 допомагає уникнути помилки "database is locked" на Railway
    return sqlite3.connect(DB_NAME, timeout=10)

def init_db() -> None:
    # Створюємо папку для бази (якщо використовуємо Volume)
    db_dir = os.path.dirname(DB_NAME)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)

    conn = get_db_connection()
    c = conn.cursor()
    # Таблиця користувачів
    c.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, first_name TEXT, date TEXT)")
    # Таблиця підписок
    c.execute("CREATE TABLE IF NOT EXISTS subs (user_id INTEGER, sign TEXT, PRIMARY KEY (user_id, sign))")
    # Таблиця відправлених повідомлень
    c.execute("CREATE TABLE IF NOT EXISTS deliveries (user_id INTEGER, sign TEXT, date TEXT, PRIMARY KEY (user_id, sign, date))")
    conn.commit()
    conn.close()

def ensure_user(user_id: int, first_name: str) -> None:
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, first_name, date) VALUES (?,?,?)",
              (user_id, first_name, datetime.date.today().isoformat()))
    conn.commit()
    conn.close()

def is_subscribed(user_id: int, sign: str) -> bool:
    conn = get_db_connection()
    c = conn.cursor()
    row = c.execute("SELECT 1 FROM subs WHERE user_id = ? AND sign = ? LIMIT 1", (user_id, sign)).fetchone()
    conn.close()
    return bool(row)

def subscribe_user(user_id: int, sign: str) -> None:
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO subs (user_id, sign) VALUES (?, ?)", (user_id, sign))
    conn.commit()
    conn.close()

def unsubscribe_user(user_id: int, sign: str) -> None:
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM subs WHERE user_id = ? AND sign = ?", (user_id, sign))
    conn.commit()
    conn.close()

# --- Парсинг сайту ---

def _fetch_html(url: str) -> str:
    session = requests.Session()
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    try:
        r = session.get(url, headers=headers, timeout=(5, 14))
        r.raise_for_status()
        return r.text
    except Exception: return ""

def get_horoscope_preview(sign: str) -> str:
    info = SIGNS.get(sign, SIGNS["aries"])
    url = f'https://www.citykey.com.ua/{info["slug"]}/'
    try:
        html = _fetch_html(url)
        if not html: return "Сьогоднішній прогноз уже доступний на сайті! Натисніть кнопку нижче, щоб прочитати."
        soup = bs4.BeautifulSoup(html, "html.parser")
        container = soup.select_one(".entry-content") or soup.body
        parts = [p.get_text(strip=True) for p in container.find_all("p", limit=5) if len(p.get_text()) > 20]
        txt = " ".join(parts).strip()
        if not txt:
            return "Сьогоднішній прогноз чекає на вас на сайті."
        return (txt[:600] + "...") if len(txt) > 600 else txt
    except Exception: 
        return "Детальний прогноз на сьогодні вже опубліковано на сайті."

# --- Кнопки (Клавіатури) ---

def sign_keyboard():
    mk = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    # Додаємо всі знаки зодіаку
    mk.add(*[types.KeyboardButton(x) for x in SIGNS_UA_BUTTONS])
    # Додаємо системні кнопки
    mk.row(types.KeyboardButton("🔔 Мої підписки"), types.KeyboardButton("🔕 Відписатись від всього"))
    return mk

def horo_inline_kb(sign: str, user_id: int):
    info = SIGNS.get(sign)
    url = f'https://www.citykey.com.ua/{info["slug"]}/?utm_source=telegram'
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton("Читати повний прогноз", url=url))
    
    if is_subscribed(user_id, sign):
        kb.add(types.InlineKeyboardButton("🔕 Відписатись від оновлень", callback_data=f"unsub:{sign}"))
    else:
        kb.add(types.InlineKeyboardButton("🔔 Отримувати оновлення щодня", callback_data=f"sub:{sign}"))
    return kb

# --- Обробники повідомлень ---

@bot.message_handler(commands=["start"])
def start(m):
    ensure_user(m.from_user.id, m.from_user.first_name or "")
    bot.send_message(
        m.chat.id, 
        "👋 Привіт! Я твій особистий астролог.\n\nОбери свій знак зодіаку, щоб отримати прогноз на сьогодні або підписатися на щоденні оновлення:", 
        reply_markup=sign_keyboard()
    )

@bot.message_handler(func=lambda m: m.text in UA_TO_SIGN)
def show_horo(m):
    ensure_user(m.from_user.id, m.from_user.first_name or "")
    sign = UA_TO_SIGN[m.text]
    txt = get_horoscope_preview(sign)
    bot.send_message(
        m.chat.id, 
        f"<b>{m.text}</b>\n\n{txt}", 
        reply_markup=horo_inline_kb(sign, m.from_user.id), 
        disable_web_page_preview=True
    )

@bot.callback_query_handler(func=lambda c: c.data.startswith(("sub:", "unsub:")))
def cb_handler(c):
    action, sign = c.data.split(":")
    if action == "sub":
        subscribe_user(c.from_user.id, sign)
        bot.answer_callback_query(c.id, "Ви підписалися! Я надішлю прогноз завтра зранку.")
    else:
        unsubscribe_user(c.from_user.id, sign)
        bot.answer_callback_query(c.id, "Ви відписалися від цього знака.")
    
    # Оновлюємо кнопки під повідомленням
    try:
        bot.edit_message_reply_markup(
            c.message.chat.id, 
            c.message.message_id, 
            reply_markup=horo_inline_kb(sign, c.from_user.id)
        )
    except Exception:
        pass

@bot.message_handler(func=lambda m: m.text == "🔔 Мої підписки")
def my_subs(m):
    ensure_user(m.from_user.id, m.from_user.first_name or "")
    conn = get_db_connection()
    rows = conn.execute("SELECT sign FROM subs WHERE user_id = ?", (m.from_user.id,)).fetchall()
    conn.close()

    if not rows:
        bot.send_message(m.chat.id, "У вас поки що немає активних підписок.")
        return

    names = []
    for (s,) in rows:
        if s in SIGNS:
            names.append(f'{SIGNS[s]["emoji"]} {SIGNS[s]["ua"]}')
    
    bot.send_message(m.chat.id, "<b>Ваші активні підписки:</b>\n\n" + "\n".join(names))

@bot.message_handler(func=lambda m: m.text == "🔕 Відписатись від всього")
def unsub_all(m):
    ensure_user(m.from_user.id, m.from_user.first_name or "")
    conn = get_db_connection()
    conn.execute("DELETE FROM subs WHERE user_id = ?", (m.from_user.id,))
    conn.commit()
    conn.close()
    bot.send_message(m.chat.id, "Ви успішно відписані від усіх розсилок.")

@bot.message_handler(commands=["stat"])
def stat(m):
    # Команда для перевірки кількості користувачів (тільки для вас)
    conn = get_db_connection()
    u_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    s_count = conn.execute("SELECT COUNT(*) FROM subs").fetchone()[0]
    conn.close()
    bot.send_message(m.chat.id, f"📊 Статистика:\n- Всього користувачів: {u_count}\n- Активних підписок: {s_count}")

if __name__ == "__main__":
    init_db()
    print("Бот запущений...")
    # skip_pending=True допомагає не відповідати на старі повідомлення після перезапуску
    bot.infinity_polling(skip_pending=True)
