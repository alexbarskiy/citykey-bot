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
from telebot import types

# --- 1. НАЛАШТУВАННЯ ---
TOKEN_RAW = os.getenv("BOT_TOKEN") or os.getenv("TOKEN") or ""
TOKEN = re.sub(r'[^a-zA-Z0-9:_]', '', TOKEN_RAW).strip()
DB_NAME = os.getenv("DB_PATH", "data/stats.db")
ADMIN_ID = 0  # Вставте свій ID

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

# --- 2. БАЗА ДАНИХ ---
def get_db():
    return sqlite3.connect(DB_NAME, timeout=30)

def init_db():
    try:
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
    except Exception as e:
        print(f"❌ Помилка бази: {e}", flush=True)

def fetch_horoscope(sign_key):
    url = f'https://www.citykey.com.ua/{SIGNS[sign_key]["slug"]}/'
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, timeout=15, headers=headers)
        soup = bs4.BeautifulSoup(r.text, "html.parser")
        content = soup.select_one(".entry-content")
        if not content: return "Прогноз на сайті!"
        paragraphs = content.find_all("p")
        text_parts = [p.get_text().strip() for p in paragraphs if len(p.get_text()) > 30]
        full_text = " ".join(text_parts[:2]).strip()
        return (full_text[:580] + "...") if len(full_text) > 600 else (full_text or "Прогноз уже на сайті!")
    except:
        return "Детальний прогноз на сьогодні вже опубліковано на сайті."

# --- 3. ФУНКЦІЯ РОЗСИЛКИ ---
def run_newsletter():
    """Фонова функція для щоденної розсилки"""
    print("⏰ Планувальник розсилки запущено.", flush=True)
    while True:
        try:
            now = datetime.datetime.now()
            # Налаштуйте годину розсилки (наприклад, 8 ранку)
            if now.hour == 6:
                today_str = now.strftime("%Y-%m-%d")
                conn = get_db()
                # Беремо всіх, кому ще не відправляли сьогодні
                to_send = conn.execute("""
                    SELECT s.user_id, s.sign 
                    FROM subs s 
                    LEFT JOIN deliveries d ON s.user_id = d.user_id AND s.sign = d.sign AND d.date = ?
                    WHERE d.user_id IS NULL
                """, (today_str,)).fetchall()
                
                if to_send:
                    print(f"📤 Починаю розсилку для {len(to_send)} підписок...", flush=True)
                    for uid, sign_key in to_send:
                        try:
                            text = fetch_horoscope(sign_key)
                            bot.send_message(
                                uid, 
                                f"☀️ <b>Доброго ранку! Твій прогноз на сьогодні:</b>\n\n✨ <b>{SIGNS[sign_key]['emoji']} {SIGNS[sign_key]['ua']}</b>\n\n{text}",
                                disable_web_page_preview=True
                            )
                            # Фіксуємо успішну відправку
                            conn.execute("INSERT INTO deliveries VALUES (?,?,?)", (uid, sign_key, today_str))
                            conn.commit()
                            time.sleep(0.1) # Захист від спам-фільтра Telegram
                        except Exception as e:
                            print(f"⚠️ Не вдалося відправити {uid}: {e}")
                conn.close()
            
            # Чекаємо 30 хвилин до наступної перевірки
            time.sleep(1800)
        except Exception as e:
            print(f"❌ Помилка у фоновій розсилці: {e}", flush=True)
            time.sleep(60)

# --- 4. КЛАВІАТУРИ ТА ОБРОБНИКИ ---
def main_kb():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    markup.add(*[types.KeyboardButton(s) for s in SIGNS_UA_LIST])
    markup.row(types.KeyboardButton("🔔 Мої підписки"), types.KeyboardButton("🔕 Відписатись від всього"))
    return markup

def inline_kb(sign_key, uid):
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("Повний прогноз на сайті", url=f'https://www.citykey.com.ua/{SIGNS[sign_key]["slug"]}/'))
    conn = get_db()
    is_sub = conn.execute("SELECT 1 FROM subs WHERE user_id=? AND sign=?", (uid, sign_key)).fetchone()
    conn.close()
    btn_text = "🔕 Відписатися" if is_sub else "🔔 Отримувати щодня"
    btn_data = f"unsub:{sign_key}" if is_sub else f"sub:{sign_key}"
    markup.add(types.InlineKeyboardButton(btn_text, callback_data=btn_data))
    return markup

@bot.message_handler(commands=['start'])
def start(m):
    conn = get_db()
    conn.execute("INSERT OR IGNORE INTO users VALUES (?,?,?)", (m.from_user.id, m.from_user.first_name, datetime.date.today().isoformat()))
    conn.commit()
    conn.close()
    bot.send_message(m.chat.id, "✨ <b>Вітаю!</b> Оберіть свій знак зодіаку:", reply_markup=main_kb())

@bot.message_handler(commands=['stats'])
def stats(m):
    if ADMIN_ID != 0 and m.from_user.id != ADMIN_ID: return
    conn = get_db()
    u = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    s = conn.execute("SELECT COUNT(*) FROM subs").fetchone()[0]
    conn.close()
    bot.send_message(m.chat.id, f"📊 <b>Статистика:</b>\nКористувачів: {u}\nПідписок: {s}")

@bot.message_handler(func=lambda m: m.text in UA_TO_KEY)
def send_horo(m):
    key = UA_TO_KEY[m.text]
    txt = fetch_horoscope(key)
    bot.send_message(m.chat.id, f"✨ <b>{m.text}</b>\n\n{txt}", reply_markup=inline_kb(key, m.from_user.id), disable_web_page_preview=True)

@bot.callback_query_handler(func=lambda c: c.data.startswith(('sub:', 'unsub:')))
def callback(c):
    act, key = c.data.split(':')
    conn = get_db()
    if act == "sub":
        conn.execute("INSERT OR IGNORE INTO subs VALUES (?,?)", (c.from_user.id, key))
        bot.answer_callback_query(c.id, "Підписано!")
    else:
        conn.execute("DELETE FROM subs WHERE user_id=? AND sign=?", (c.from_user.id, key))
        bot.answer_callback_query(c.id, "Відписано.")
    conn.commit()
    conn.close()
    try: bot.edit_message_reply_markup(c.message.chat.id, c.message.message_id, reply_markup=inline_kb(key, c.from_user.id))
    except: pass

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

# --- 5. ЗАПУСК ---
if __name__ == "__main__":
    init_db()
    # Запуск розсилки в окремому потоці, щоб не заважати боту відповідати
    threading.Thread(target=run_newsletter, daemon=True).start()
    
    print("🚀 Бот увімкнений.", flush=True)
    while True:
        try:
            bot.infinity_polling(skip_pending=True, timeout=60)
        except Exception as e:
            if "409" in str(e):
                print("⚠️ Конфлікт токенів. Спроба через 10 сек...", flush=True)
                time.sleep(10)
            else:
                time.sleep(5)
