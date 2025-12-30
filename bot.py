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

# --- 1. ПРИМУСОВА ДІАГНОСТИКА (БЕЗ КЕШУ) ---
# Ми спеціально шукаємо тільки одну змінну, щоб не було плутанини
# РЕКОМЕНДАЦІЯ: На Railway створіть змінну FINAL_BOT_TOKEN
TOKEN_RAW = os.getenv("FINAL_BOT_TOKEN") or os.getenv("BOT_TOKEN") or os.getenv("TOKEN") or ""
TOKEN = re.sub(r'[^a-zA-Z0-9:_]', '', TOKEN_RAW).strip()

def verify_and_start():
    print("--- ГЛИБОКА ДІАГНОСТИКА СИСТЕМИ ---", flush=True)
    env_keys = list(os.environ.keys())
    print(f"Доступні ключі в системі: {[k for k in env_keys if 'TOKEN' in k]}", flush=True)
    
    if not TOKEN:
        print("❌ КРИТИЧНО: Жодної змінної з токеном не знайдено!", flush=True)
        return False
        
    print(f"Зчитано токен довжиною: {len(TOKEN)}")
    print(f"Відбиток (перші 10): {TOKEN[:10]}... (останні 5): ...{TOKEN[-5:]}", flush=True)
    
    try:
        r = requests.get(f"https://api.telegram.org/bot{TOKEN}/getMe", timeout=15)
        res = r.json()
        if res.get("ok"):
            print(f"✅ УСПІХ! Telegram підтвердив: @{res['result']['username']}", flush=True)
            return True
        else:
            print(f"❌ ТЕЛЕГРАМ ВІДХИЛИВ ТОКЕН (401): {res.get('description')}", flush=True)
            return False
    except Exception as e:
        print(f"⚠️ Помилка мережі при перевірці: {e}", flush=True)
        return False

# Спроба перевірки
is_ready = verify_and_start()
bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

# --- 2. БАЗА ДАНИХ ТА КОНСТАНТИ ---
DB_NAME = os.getenv("DB_PATH", "data/stats.db")
ADMIN_ID = 564858074  # ВСТАВТЕ ВАШ ID ТУТ

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

def get_db():
    return sqlite3.connect(DB_NAME, timeout=30)

def init_db():
    try:
        db_dir = os.path.dirname(DB_NAME)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
        conn = get_db()
        conn.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, first_name TEXT, date TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS subs (user_id INTEGER, sign TEXT, PRIMARY KEY (user_id, sign))")
        conn.execute("CREATE TABLE IF NOT EXISTS deliveries (user_id INTEGER, sign TEXT, date TEXT, PRIMARY KEY (user_id, sign, date))")
        conn.commit()
        conn.close()
        print(f"💾 База даних готова: {DB_NAME}", flush=True)
    except Exception as e:
        print(f"❌ Помилка бази: {e}", flush=True)

# --- 3. РОЗСИЛКА ТА ПАРСИНГ ---
def fetch_horo(sign_key):
    url = f'https://www.citykey.com.ua/{SIGNS[sign_key]["slug"]}/'
    try:
        r = requests.get(url, timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
        soup = bs4.BeautifulSoup(r.text, "html.parser")
        content = soup.select_one(".entry-content")
        if not content: return "Прогноз на сьогодні вже на нашому сайті!"
        p = content.find_all("p")
        txt = " ".join([item.get_text().strip() for item in p if len(item.get_text()) > 25][:2])
        return (txt[:580] + "...") if len(txt) > 600 else (txt or "Читати на сайті.")
    except:
        return "Детальний прогноз на сьогодні вже опубліковано на нашому сайті."

def daily_newsletter():
    """Фоновий потік розсилки"""
    print("⏰ Планувальник розсилки активовано.", flush=True)
    while True:
        try:
            now = datetime.datetime.now()
            # 07:00 UTC ≈ 09:00 за Києвом
            if now.hour == 7:
                today = now.strftime("%Y-%m-%d")
                conn = get_db()
                to_send = conn.execute("""
                    SELECT s.user_id, s.sign FROM subs s 
                    LEFT JOIN deliveries d ON s.user_id = d.user_id AND s.sign = d.sign AND d.date = ?
                    WHERE d.user_id IS NULL
                """, (today,)).fetchall()
                
                if to_send:
                    print(f"📤 Відправка {len(to_send)} повідомлень...", flush=True)
                    for uid, skey in to_send:
                        try:
                            txt = fetch_horo(skey)
                            bot.send_message(uid, f"☀️ <b>Добрий ранок! Твій прогноз:</b>\n\n✨ <b>{SIGNS[skey]['ua']}</b>\n\n{txt}", disable_web_page_preview=True)
                            conn.execute("INSERT INTO deliveries VALUES (?,?,?)", (uid, skey, today))
                            conn.commit()
                            time.sleep(0.1)
                        except: pass
                conn.close()
            time.sleep(1800)
        except Exception as e:
            print(f"Помилка в потоці розсилки: {e}", flush=True)
            time.sleep(60)

# --- 4. КЛАВІАТУРИ ТА ОБРОБНИКИ ---
def main_kb():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    markup.add(*[types.KeyboardButton(s) for s in SIGNS_UA_LIST])
    markup.row(types.KeyboardButton("🔔 Мої підписки"), types.KeyboardButton("🔕 Відписатись від всього"))
    return markup

def inline_kb(sign_key, uid):
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("Повний прогноз", url=f'https://www.citykey.com.ua/{SIGNS[sign_key]["slug"]}/'))
    conn = get_db()
    is_sub = conn.execute("SELECT 1 FROM subs WHERE user_id=? AND sign=?", (uid, sign_key)).fetchone()
    conn.close()
    text = "🔕 Відписатися" if is_sub else "🔔 Отримувати щодня"
    data = f"unsub:{sign_key}" if is_sub else f"sub:{sign_key}"
    markup.add(types.InlineKeyboardButton(text, callback_data=data))
    return markup

@bot.message_handler(commands=['start'])
def start(m):
    conn = get_db()
    conn.execute("INSERT OR IGNORE INTO users VALUES (?,?,?)", (m.from_user.id, m.from_user.first_name, datetime.date.today().isoformat()))
    conn.commit()
    conn.close()
    bot.send_message(m.chat.id, "✨ <b>Вітаю!</b> Оберіть знак зодіаку:", reply_markup=main_kb())

@bot.message_handler(commands=['stats'])
def stats(m):
    if ADMIN_ID != 0 and m.from_user.id != ADMIN_ID: return
    conn = get_db()
    u = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    s = conn.execute("SELECT COUNT(*) FROM subs").fetchone()[0]
    conn.close()
    bot.send_message(m.chat.id, f"📊 <b>Статистика:</b>\nКористувачів: {u}\nПідписок: {s}")

@bot.message_handler(func=lambda m: m.text in UA_TO_KEY)
def sign_handler(m):
    key = UA_TO_KEY[m.text]
    txt = fetch_horo(key)
    bot.send_message(m.chat.id, f"✨ <b>{m.text}</b>\n\n{txt}", reply_markup=inline_kb(key, m.from_user.id), disable_web_page_preview=True)

@bot.callback_query_handler(func=lambda c: c.data.startswith(('sub:', 'unsub:')))
def callback_query(c):
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
def my_subscriptions(m):
    conn = get_db()
    rows = conn.execute("SELECT sign FROM subs WHERE user_id=?", (m.from_user.id,)).fetchall()
    conn.close()
    if not rows:
        bot.send_message(m.chat.id, "У вас немає активних підписок.")
        return
    txt = "<b>Ваші підписки:</b>\n" + "\n".join([f"- {SIGNS[r[0]]['emoji']} {SIGNS[r[0]]['ua']}" for r in rows if r[0] in SIGNS])
    bot.send_message(m.chat.id, txt)

@bot.message_handler(func=lambda m: m.text == "🔕 Відписатись від всього")
def unsubscribe_all(m):
    conn = get_db()
    conn.execute("DELETE FROM subs WHERE user_id=?", (m.from_user.id,))
    conn.commit()
    conn.close()
    bot.send_message(m.chat.id, "Всі ваші підписки успішно видалено.")

# --- 5. ЗАПУСК ---
if __name__ == "__main__":
    init_db()
    if not is_ready:
        print("🛑 СТОП: Токен не пройшов перевірку. Перевірте Variables на Railway.", flush=True)
        sys.exit(1)
        
    threading.Thread(target=daily_newsletter, daemon=True).start()
    print("🚀 Бот увімкнений та готовий до роботи!", flush=True)
    
    while True:
        try:
            bot.infinity_polling(skip_pending=True, timeout=60)
        except Exception as e:
            if "409" in str(e):
                print("⚠️ Конфлікт (409): Інший бот працює. Чекаємо 15 сек...", flush=True)
                time.sleep(15)
            else:
                time.sleep(5)

