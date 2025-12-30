# bot.py
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

# ---------------- 1. НАЛАШТУВАННЯ ТА ТОКЕН ----------------
# Пріоритет на FINAL_BOT_TOKEN для уникнення проблем з кешем Railway
TOKEN_RAW = os.getenv("FINAL_BOT_TOKEN") or os.getenv("BOT_TOKEN") or os.getenv("TOKEN") or ""
TOKEN = re.sub(r'[^a-zA-Z0-9:_]', '', TOKEN_RAW).strip()
DB_NAME = os.getenv("DB_PATH", "data/stats.db")

# ВСТАВТЕ СВІЙ ID ТУТ (отримайте у @userinfobot)
ADMIN_ID = 564858074

# Шаблон персоналізованого VIP-посилання (БЕЗ ПРОБІЛІВ!)
VIP_LINK_TEMPLATE = "https://www.citykey.com.ua/city-key-horoscope/index.html?name={name}&sign={sign}"

if not TOKEN:
    print("❌ КРИТИЧНО: TOKEN не знайдено в Variables!", flush=True)
    sys.exit(1)

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

# ---------------- 2. ДАНІ ТА СТРУКТУРИ ----------------
SIGNS = {
    "aries":       {"emoji": "♈", "ua": "Овен",      "slug": "horoskop-oven"},
    "taurus":      {"emoji": "♉", "ua": "Тілець",    "slug": "horoskop-telec"},
    "gemini":      {"emoji": "♊", "ua": "Близнюки",  "slug": "horoskop-bliznyu"},
    "cancer":      {"emoji": "♋", "ua": "Рак",       "slug": "horoskop-rak"},
    "leo":         {"emoji": "♌", "ua": "Лев",       "slug": "horoskop-lev"},
    "virgo":       {"emoji": "♍", "ua": "Діва",      "slug": "horoskop-diva"},
    "libra":       {"emoji": "♎", "ua": "Терези",    "slug": "horoskop-terez"},
    "scorpio":     {"emoji": "♏", "ua": "Скорпіон",  "slug": "horoskop-skorpion"},
    "sagittarius": {"emoji": "♐", "ua": "Стрілець",  "slug": "horoskop-strilec"},
    "capricorn":   {"emoji": "♑", "ua": "Козеріг",   "slug": "horoskop-kozerig"},
    "aquarius":    {"emoji": "♒", "ua": "Водолій",   "slug": "horoskop-vodoliy"},
    "pisces":      {"emoji": "♓", "ua": "Риби",      "slug": "horoskop-ryby"},
}

SIGNS_UA_LIST = [f'{v["emoji"]} {v["ua"]}' for v in SIGNS.values()]
UA_TO_KEY = {f'{v["emoji"]} {v["ua"]}': k for k, v in SIGNS.items()}

BTN_MY_SUBS = "🔔 Мої підписки"
BTN_VIP_STATUS = "💎 VIP Статус / Друзі"
BTN_UNSUB_ALL = "🔕 Відписатись від всього"

# ---------------- 3. РОБОТА З БАЗОЮ ДАНИХ ----------------
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
        c.execute("CREATE TABLE IF NOT EXISTS feedback (user_id INTEGER, date TEXT, rate TEXT)")

        cols = [info[1] for info in c.execute("PRAGMA table_info(users)").fetchall()]
        if 'referrer_id' not in cols:
            c.execute("ALTER TABLE users ADD COLUMN referrer_id INTEGER")
        if 'username' not in cols:
            c.execute("ALTER TABLE users ADD COLUMN username TEXT")
        conn.commit()
        conn.close()
        print("💾 База даних синхронізована.", flush=True)
    except Exception as e:
        print(f"❌ Помилка бази: {e}", flush=True)

# ---------------- 4. ЛОГІКА КОНТЕНТУ ----------------
def get_compatibility(sign_key):
    random.seed(int(datetime.date.today().strftime("%Y%m%d")) + len(sign_key))
    compat_key = random.choice(list(SIGNS.keys()))
    return f"💖 <b>Сумісність дня:</b> найкраще взаємодіяти з <b>{SIGNS[compat_key]['ua']}</b>"

def fetch_horo(sign_key):
    url = f'https://www.citykey.com.ua/{SIGNS[sign_key]["slug"]}/'   # ← ПРОБІЛ ПРИБРАНО
    try:
        r = requests.get(url, timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
        soup = bs4.BeautifulSoup(r.text, "html.parser")
        content = soup.select_one(".entry-content")
        if not content:
            return "Прогноз на сьогодні вже на нашому сайті!"
        paragraphs = content.find_all("p")
        txt = " ".join([p.get_text().strip() for p in paragraphs if len(p.get_text()) > 25][:2])
        return (txt[:550] + "...") if len(txt) > 550 else (txt or "Читати далі на сайті.")
    except Exception as e:
        print(f"Scraping error for {sign_key}: {e}", flush=True)
        return "Детальний прогноз на сьогодні вже опубліковано на сайті citykey.com.ua"

# ---------------- 5. КЛАВІАТУРИ ----------------
def main_kb():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    markup.add(*[types.KeyboardButton(s) for s in SIGNS_UA_LIST])
    markup.row(types.KeyboardButton(BTN_VIP_STATUS), types.KeyboardButton(BTN_MY_SUBS))
    markup.row(types.KeyboardButton(BTN_UNSUB_ALL))
    return markup

def inline_kb(sign_key, uid, text_to_share):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton("📖 Читати повністю", url=f'https://www.citykey.com.ua/{SIGNS[sign_key]["slug"]}/'))

    conn = get_db()
    is_sub = conn.execute("SELECT 1 FROM subs WHERE user_id=? AND sign=?", (uid, sign_key)).fetchone()
    conn.close()

    sub_text = "🔕 Відписатися" if is_sub else "🔔 Отримувати щодня"
    sub_data = f"unsub:{sign_key}" if is_sub else f"sub:{sign_key}"

    ref_link = f"https://t.me/City_Key_Bot?start={uid}"                       # ← ПРОБІЛ ПРИБРАНО
    share_msg = f"Мій гороскоп ({SIGNS[sign_key]['ua']}):\n\n{text_to_share}\n\nДізнайся свій тут 👇"
    share_url = f"https://t.me/share/url?url={urllib.parse.quote(ref_link)}&text={urllib.parse.quote(share_msg)}"

    markup.add(
        types.InlineKeyboardButton(sub_text, callback_data=sub_data),
        types.InlineKeyboardButton("🚀 Поділитися", url=share_url)
    )
    markup.row(types.InlineKeyboardButton("👍 Лайк", callback_data="rate:up"),
               types.InlineKeyboardButton("👎 Дизлайк", callback_data="rate:down"))
    return markup

# ---------------- 6. ОБРОБНИКИ ----------------
@bot.message_handler(commands=['start'])
def cmd_start(m):
    user_id = m.from_user.id
    name = m.from_user.first_name or "друг"
    username = m.from_user.username
    referrer_id = None

    if len(m.text.split()) > 1:
        ref_candidate = m.text.split()[1]
        if ref_candidate.isdigit() and int(ref_candidate) != user_id:
            referrer_id = int(ref_candidate)

    conn = get_db()
    user_exists = conn.execute("SELECT 1 FROM users WHERE user_id=?", (user_id,)).fetchone()
    if not user_exists:
        conn.execute(
            "INSERT INTO users (user_id, first_name, username, date, referrer_id) VALUES (?,?,?,?,?)",
            (user_id, name, username, datetime.date.today().isoformat(), referrer_id)
        )
        conn.commit()
        if referrer_id:
            try:
                bot.send_message(referrer_id, f"🎉 Вітаємо! Новий користувач приєднався за вашим посиланням. Це зараховано для VIP!")
            except:
                pass
    else:
        conn.execute("UPDATE users SET username=?, first_name=? WHERE user_id=?", (username, name, user_id))
        conn.commit()
    conn.close()
    bot.send_message(m.chat.id, f"✨ <b>Вітаю, {name}!</b> Оберіть свій знак зодіаку:", reply_markup=main_kb())

@bot.message_handler(commands=['stats'])
def cmd_stats(m):
    if ADMIN_ID != 0 and m.from_user.id != ADMIN_ID:
        return
    conn = get_db()
    u = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    s = conn.execute("SELECT COUNT(*) FROM subs").fetchone()[0]
    conn.close()
    bot.send_message(m.chat.id, f"📊 <b>АДМІН-СТАТИСТИКА:</b>\n👥 Користувачів: {u}\n🔔 Підписок: {s}")

@bot.message_handler(func=lambda m: True)
def central_handler(m):
    text = m.text.strip()
    uid = m.from_user.id

    if text in UA_TO_KEY:
        key = UA_TO_KEY[text]
        bot.send_chat_action(m.chat.id, 'typing')
        txt = fetch_horo(key)
        compat = get_compatibility(key)
        bot.send_message(m.chat.id, f"✨ <b>{text}</b>\n\n{txt}\n\n{compat}",
                         reply_markup=inline_kb(key, uid, txt), disable_web_page_preview=True)
        return

    if "підписки" in text.lower() or "подписки" in text.lower():
        conn = get_db()
        rows = conn.execute("SELECT sign FROM subs WHERE user_id=?", (uid,)).fetchall()
        conn.close()
        if not rows:
            bot.send_message(m.chat.id, "У вас немає активних підписок. Оберіть знак і натисніть «Отримувати щодня».")
        else:
            txt = "<b>Ваші активні підписки:</b>\n" + \
                  "\n".join([f"- {SIGNS[r[0]]['emoji']} {SIGNS[r[0]]['ua']}" for r in rows if r[0] in SIGNS])
            bot.send_message(m.chat.id, txt)
        return

    if "vip" in text.lower() or "статус" in text.lower() or "друзі" in text.lower():
        conn = get_db()
        count = conn.execute("SELECT COUNT(*) FROM users WHERE referrer_id=?", (uid,)).fetchone()[0]
        sub = conn.execute("SELECT sign FROM subs WHERE user_id=? LIMIT 1", (uid,)).fetchone()
        conn.close()

        sign_ua = SIGNS[sub[0]]["ua"] if sub else "Гороскоп"
        ref_link = f"https://t.me/City_Key_Bot?start={uid}"                    # ← ПРОБІЛ ПРИБРАНО
        is_admin = (ADMIN_ID != 0 and uid == ADMIN_ID)

        if count >= 3 or is_admin:
            encoded_name = urllib.parse.quote(m.from_user.first_name)
            encoded_sign = urllib.parse.quote(sign_ua)
            personal_link = VIP_LINK_TEMPLATE.format(name=encoded_name, sign=encoded_sign)
            bot.send_message(m.chat.id,
                             f"🌟 <b>ВАШ СТАТУС: VIP</b>\n\nВи запросили {count} друзів! "
                             f"Твій персональний VIP-прогноз тут:\n\n👉 <a href='{personal_link}'>ВІДКРИТИ ПРЕМІУМ</a>",
                             disable_web_page_preview=True)
        else:
            bot.send_message(m.chat.id,
                             f"💎 Запросіть ще {3 - count} друзів для VIP-статусу!\n\n"
                             f"🔗 Твоє посилання для запрошення:\n<code>{ref_link}</code>")
        return

    if "відписатись" in text.lower() or "отписаться" in text.lower():
        conn = get_db()
        conn.execute("DELETE FROM subs WHERE user_id=?", (uid,))
        conn.commit()
        conn.close()
        bot.send_message(m.chat.id, "Ви відписалися від усіх розсилок.")

# ---------------- 7. CALLBACKS ----------------
@bot.callback_query_handler(func=lambda c: True)
def callback_handler(c):
    uid = c.from_user.id
    if c.data.startswith('rate:'):
        bot.answer_callback_query(c.id, "Дякуємо за відгук!")
        return

    if c.data.startswith(('sub:', 'unsub:')):
        act, key = c.data.split(':')
        conn = get_db()
        if act == "sub":
            conn.execute("INSERT OR IGNORE INTO subs VALUES (?,?)", (uid, key))
        else:
            conn.execute("DELETE FROM subs WHERE user_id=? AND sign=?", (uid, key))
        conn.commit()
        conn.close()
        bot.answer_callback_query(c.id, "Оновлено!")
        try:
            # перевантажуємо клавіатуру, щоб кнопка змінила підпис
            bot.edit_message_reply_markup(c.message.chat.id, c.message.message_id,
                                          reply_markup=inline_kb(key, uid, c.message.text or ""))
        except:
            pass

# ---------------- 8. ЩОДЕННА РОЗСИЛКА (07:00 UTC = 09:00 Київ) ----------------
def newsletter_thread():
    while True:
        try:
            now = datetime.datetime.now()
            if now.hour == 7:                       # 07:00 UTC
                is_sunday = now.weekday() == 6
                today = now.strftime("%Y-%m-%d")
                conn = get_db()
                to_send = conn.execute("""
                    SELECT s.user_id, s.sign FROM subs s
                    LEFT JOIN deliveries d ON s.user_id = d.user_id AND s.sign = d.sign AND d.date = ?
                    WHERE d.user_id IS NULL
                """, (today,)).fetchall()
                for uid, skey in to_send:
                    try:
                        if is_sunday:
                            text = f"📅 <b>ЧАС ПЛАНУВАТИ ТИЖДЕНЬ!</b>\n\n" \
                                   f"Великий прогноз для знака {SIGNS[skey]['ua']} вже доступний на нашому сайті."
                            kb = types.InlineKeyboardMarkup()
                            kb.add(types.InlineKeyboardButton("✨ Дивитись прогноз",
                                                              url="https://www.citykey.com.ua/weekly-horoscope/"))
                        else:
                            txt = fetch_horo(skey)
                            compat = get_compatibility(skey)
                            text = f"☀️ <b>Добрий ранок! Твій прогноз для {SIGNS[skey]['ua']}:</b>\n\n{txt}\n\n{compat}"
                            kb = inline_kb(skey, uid, txt)
                        bot.send_message(uid, text, reply_markup=kb, disable_web_page_preview=True)
                        conn.execute("INSERT INTO deliveries VALUES (?,?,?)", (uid, skey, today))
                        conn.commit()
                        time.sleep(0.1)
                    except:
                        pass
                conn.close()
            time.sleep(1800)        # 30 хв
        except:
            time.sleep(60)

# ---------------- 9. ЗАПУСК ----------------
if __name__ == "__main__":
    print("⏳ Очікування стабілізації Railway (20 сек)...", flush=True)
    time.sleep(20)
    init_db()
    print("🚀 Бот City Key намагається підключитися до Telegram...", flush=True)
    threading.Thread(target=newsletter_thread, daemon=True).start()
    while True:
        try:
            me = bot.get_me()
            print(f"✅ УСПІХ! Бот @{me.username} онлайн.", flush=True)
            bot.polling(none_stop=True, timeout=90, long_polling_timeout=90)
        except Exception as e:
            print(f"⚠️ Помилка з'єднання: {e}. Перезапуск через 15 сек...", flush=True)
            time.sleep(15)
