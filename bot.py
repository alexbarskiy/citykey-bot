# bot.py
import os, sys, datetime, sqlite3, requests, bs4, telebot, re, time, threading, random, urllib.parse, traceback
from telebot import types

# --------------- 1. НАЛАШТУВАННЯ ТА ТОКЕН ---------------
TOKEN_RAW = os.getenv("FINAL_BOT_TOKEN") or os.getenv("BOT_TOKEN") or os.getenv("TOKEN") or ""
TOKEN = re.sub(r'[^a-zA-Z0-9:_\-]', '', TOKEN_RAW).strip()
DB_NAME = os.getenv("DB_PATH", "data/stats.db")
ADMIN_ID = 0          # ← свій Telegram-ID (число)

# VIP-посилання (без пробілів)
VIP_LINK_TEMPLATE = "https://www.citykey.com.ua/city-key-horoscope/index.html?name={name}&sign={sign}"

print(f"TOKEN length: {len(TOKEN) or 0}", flush=True)
if not TOKEN:
    print("❌ КРИТИЧНО: TOKEN не знайдено в Variables!", flush=True)
    sys.exit(1)

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

# --------------- 2. ДАНІ ---------------
SIGNS = {
    "aries": {"emoji": "♈", "ua": "Овен", "slug": "horoskop-oven"},
    "taurus": {"emoji": "♉", "ua": "Тілець", "slug": "horoskop-telec"},
    "gemini": {"emoji": "♊", "ua": "Близнюки", "slug": "horoskop-bliznyu"},
    "cancer": {"emoji": "♋", "ua": "Рак", "slug": "horoskop-rak"},
    "leo": {"emoji": "♌", "ua": "Лев", "slug": "horoskop-lev"},
    "virgo": {"emoji": "♍", "ua": "Діва", "slug": "horoskop-diva"},
    "libra": {"emoji": "♎", "ua": "Терези", "slug": "horoskop-terez"},
    "scorpio": {"emoji": "♏", "ua": "Скорпіон", "slug": "horoskop-skorpion"},
    "sagittarius": {"emoji": "♐", "ua": "Стрілець", "slug": "horoskop-strilec"},
    "capricorn": {"emoji": "♑", "ua": "Козеріг", "slug": "horoskop-kozerig"},
    "aquarius": {"emoji": "♒", "ua": "Водолій", "slug": "horoskop-vodoliy"},
    "pisces": {"emoji": "♓", "ua": "Риби", "slug": "horoskop-ryby"},
}
SIGNS_UA_LIST = [f'{v["emoji"]} {v["ua"]}' for v in SIGNS.values()]
UA_TO_KEY = {f'{v["emoji"]} {v["ua"]}': k for k, v in SIGNS.items()}

BTN_MY_SUBS = "🔔 Мої підписки"
BTN_VIP_STATUS = "💎 VIP Статус / Друзі"
BTN_UNSUB_ALL = "🔕 Відписатись від всього"

# --------------- 3. БАЗА ДАНИХ ---------------
def get_db():
    return sqlite3.connect(DB_NAME, timeout=30, check_same_thread=False)

def init_db():
    try:
        os.makedirs(os.path.dirname(DB_NAME), exist_ok=True)
        conn = get_db()
        c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, first_name TEXT, date TEXT, username TEXT, referrer_id INTEGER)")
        c.execute("CREATE TABLE IF NOT EXISTS subs (user_id INTEGER, sign TEXT, PRIMARY KEY (user_id, sign))")
        c.execute("CREATE TABLE IF NOT EXISTS deliveries (user_id INTEGER, sign TEXT, date TEXT, PRIMARY KEY (user_id, sign, date))")
        c.execute("CREATE TABLE IF NOT EXISTS feedback (user_id INTEGER, date TEXT, rate TEXT)")
        conn.commit(); conn.close()
        print("💾 База даних синхронізована.", flush=True)
    except Exception as e:
        print(f"❌ Помилка бази: {e}", flush=True); raise

# --------------- 4. КОНТЕНТ ---------------
def get_compatibility(sign_key):
    random.seed(int(datetime.date.today().strftime("%Y%m%d")) + len(sign_key))
    return f"💖 <b>Сумісність дня:</b> найкраще взаємодіяти з <b>{SIGNS[random.choice(list(SIGNS.keys()))]['ua']}</b>"

def fetch_horo(sign_key):
    url = f"https://www.citykey.com.ua/{SIGNS[sign_key]['slug']}/"
    try:
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        soup = bs4.BeautifulSoup(r.text, "html.parser")
        content = soup.select_one(".entry-content")
        if not content: return "Прогноз на сьогодні вже на нашому сайті!"
        paragraphs = content.find_all("p")
        txt = " ".join([p.get_text().strip() for p in paragraphs if len(p.get_text()) > 25][:2])
        return (txt[:550] + "...") if len(txt) > 550 else (txt or "Читати далі на сайті.")
    except Exception as e:
        print(f"Scraping error for {sign_key}: {e}", flush=True)
        return "Детальний прогноз на сьогодні вже опубліковано на сайті citykey.com.ua"

# --------------- 5. КЛАВІАТУРИ ---------------
def main_kb():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    markup.add(*[types.KeyboardButton(s) for s in SIGNS_UA_LIST])
    markup.row(types.KeyboardButton(BTN_VIP_STATUS), types.KeyboardButton(BTN_MY_SUBS))
    markup.row(types.KeyboardButton(BTN_UNSUB_ALL))
    return markup

def inline_kb(sign_key, uid, text_to_share):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton("📖 Читати повністю", url=f"https://www.citykey.com.ua/{SIGNS[sign_key]['slug']}/"))
    conn = get_db()
    is_sub = conn.execute("SELECT 1 FROM subs WHERE user_id=? AND sign=?", (uid, sign_key)).fetchone()
    conn.close()
    sub_text, sub_data = (("🔕 Відписатися", f"unsub:{sign_key}") if is_sub else ("🔔 Отримувати щодня", f"sub:{sign_key}"))
    ref_link = f"https://t.me/City_Key_Bot?start={uid}"
    share_msg = f"Мій гороскоп ({SIGNS[sign_key]['ua']}):\n\n{text_to_share}\n\nДізнайся свій тут 👇"
    share_url = f"https://t.me/share/url?url={urllib.parse.quote(ref_link)}&text={urllib.parse.quote(share_msg)}"
    markup.add(types.InlineKeyboardButton(sub_text, callback_data=sub_data), types.InlineKeyboardButton("🚀 Поділитися", url=share_url))
    markup.row(types.InlineKeyboardButton("👍 Лайк", callback_data="rate:up"), types.InlineKeyboardButton("👎 Дизлайк", callback_data="rate:down"))
    return markup

# --------------- 6. ХЕНДЛЕРИ ---------------
@bot.message_handler(commands=["start"])
def cmd_start(m):
    uid, name, uname = m.from_user.id, m.from_user.first_name or "друг", m.from_user.username
    ref = None
    if len(m.text.split()) > 1:
        rc = m.text.split()[1]
        if rc.isdigit() and int(rc) != uid: ref = int(rc)
    conn = get_db()
    if not conn.execute("SELECT 1 FROM users WHERE user_id=?", (uid,)).fetchone():
        conn.execute("INSERT INTO users(user_id,first_name,username,date,referrer_id) VALUES(?,?,?,?,?)",
                     (uid, name, uname, datetime.date.today().isoformat(), ref))
        conn.commit()
        if ref:
            try: bot.send_message(ref, "🎉 Новий користувач приєднався за вашим посиланням!")
            except: pass
    else:
        conn.execute("UPDATE users SET first_name=?, username=? WHERE user_id=?", (name, uname, uid))
        conn.commit()
    conn.close()
    bot.send_message(m.chat.id, f"✨ <b>Вітаю, {name}!</b> Оберіть свій знак:", reply_markup=main_kb())

@bot.message_handler(commands=["stats"])
def cmd_stats(m):
    if ADMIN_ID and m.from_user.id != ADMIN_ID: return
    conn = get_db()
    u, s = [conn.execute("SELECT COUNT(*) FROM "+t).fetchone()[0] for t in ("users","subs")]
    conn.close()
    bot.send_message(m.chat.id, f"📊 <b>АДМІН-СТАТИСТИКА:</b>\n👥 Користувачів: {u}\n🔔 Підписок: {s}")

@bot.message_handler(func=lambda m: True)
def central(m):
    txt, uid = m.text.strip(), m.from_user.id
    if txt in UA_TO_KEY:
        key = UA_TO_KEY[txt]
        bot.send_chat_action(m.chat.id, "typing")
        h = fetch_horo(key); c = get_compatibility(key)
        bot.send_message(m.chat.id, f"✨ <b>{txt}</b>\n\n{h}\n\n{c}", reply_markup=inline_kb(key, uid, h), disable_web_page_preview=True)
        return
    if "підписки" in txt.lower() or "подписки" in txt.lower():
        conn = get_db()
        rows = conn.execute("SELECT sign FROM subs WHERE user_id=?", (uid,)).fetchall()
        conn.close()
        if not rows:
            bot.send_message(m.chat.id, "У вас немає активних підписок.")
        else:
            bot.send_message(m.chat.id, "<b>Ваші активні підписки:</b>\n" +
                              "\n".join([f"- {SIGNS[r[0]]['emoji']} {SIGNS[r[0]]['ua']}" for r in rows if r[0] in SIGNS]))
        return
    if "vip" in txt.lower() or "статус" in txt.lower() or "друзі" in txt.lower():
        conn = get_db()
        cnt = conn.execute("SELECT COUNT(*) FROM users WHERE referrer_id=?", (uid,)).fetchone()[0]
        sub = conn.execute("SELECT sign FROM subs WHERE user_id=? LIMIT 1", (uid,)).fetchone()
        conn.close()
        sign_ua = SIGNS[sub[0]]["ua"] if sub else "Гороскоп"
        ref_link = f"https://t.me/City_Key_Bot?start={uid}"
        is_admin = (ADMIN_ID and uid == ADMIN_ID)
        if cnt >= 3 or is_admin:
            personal = VIP_LINK_TEMPLATE.format(name=urllib.parse.quote(m.from_user.first_name),
                                                sign=urllib.parse.quote(sign_ua))
            bot.send_message(m.chat.id, f"🌟 <b>ВАШ СТАТУС: VIP</b>\n\nЗапросили {cnt} друзів!\n👉 <a href='{personal}'>ВІДКРИТИ ПРЕМІУМ</a>",
                             disable_web_page_preview=True)
        else:
            bot.send_message(m.chat.id, f"💎 Запросіть ще {3-cnt} друзів!\n🔗 Посилання:\n<code>{ref_link}</code>")
        return
    if "відписатись" in txt.lower() or "отписаться" in txt.lower():
        conn = get_db()
        conn.execute("DELETE FROM subs WHERE user_id=?", (uid,)); conn.commit(); conn.close()
        bot.send_message(m.chat.id, "Ви відписалися від усіх розсилок.")

# --------------- 7. CALLBACK ---------------
@bot.callback_query_handler(func=lambda c: True)
def inline_handler(c):
    uid = c.from_user.id
    if c.data.startswith("rate:"):
        bot.answer_callback_query(c.id, "Дякуємо за відгук!"); return
    if c.data.startswith(("sub:", "unsub:")):
        act, key = c.data.split(":")
        conn = get_db()
        if act == "sub": conn.execute("INSERT OR IGNORE INTO subs VALUES(?,?)", (uid, key))
        else: conn.execute("DELETE FROM subs WHERE user_id=? AND sign=?", (uid, key))
        conn.commit(); conn.close()
        bot.answer_callback_query(c.id, "Оновлено!")
        try: bot.edit_message_reply_markup(c.message.chat.id, c.message.message_id, reply_markup=inline_kb(key, uid, c.message.text or ""))
        except: pass

# --------------- 8. РОЗСИЛКА (07:00 UTC) ---------------
def newsletter():
    while True:
        try:
            now = datetime.datetime.now()
            if now.hour == 7:
                today, is_sun = now.strftime("%Y-%m-%d"), now.weekday()==6
                conn = get_db()
                rows = conn.execute("SELECT s.user_id, s.sign FROM subs s LEFT JOIN deliveries d ON s.user_id=d.user_id AND s.sign=d.sign AND d.date=? WHERE d.user_id IS NULL", (today,)).fetchall()
                for uid, skey in rows:
                    try:
                        if is_sun:
                            txt = f"📅 <b>ЧАС ПЛАНУВАТИ ТИЖДЕНЬ!</b>\nВеликий прогноз для {SIGNS[skey]['ua']} вже на сайті."
                            kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("✨ Дивитись", url="https://www.citykey.com.ua/weekly-horoscope/"))
                        else:
                            h = fetch_horo(skey); c = get_compatibility(skey)
                            txt = f"☀️ <b>Добрий ранок! Твій прогноз для {SIGNS[skey]['ua']}:</b>\n\n{h}\n\n{c}"
                            kb = inline_kb(skey, uid, h)
                        bot.send_message(uid, txt, reply_markup=kb, disable_web_page_preview=True)
                        conn.execute("INSERT INTO deliveries VALUES(?,?,?)", (uid, skey, today)); conn.commit()
                        time.sleep(.1)
                    except: pass
                conn.close()
            time.sleep(1800)
        except: time.sleep(60)

# --------------- 9. СТАРТ + ЗАХИСТ ВІД КРАШІВ ---------------
if __name__ == "__main__":
    try:
        print("⏳ Очікування стабілізації Railway (20 сек)...", flush=True); time.sleep(20)
        init_db()
        print("🚀 Бот намагається підключитися до Telegram...", flush=True)
        threading.Thread(target=newsletter, daemon=True).start()
        me = bot.get_me()
        print(f"✅ УСПІХ! Бот @{me.username} онлайн.", flush=True)
        bot.polling(none_stop=True, timeout=90, long_polling_timeout=90)
    except Exception as e:
        print(f"!!! Критична помилка: {e}", flush=True)
        traceback.print_exc()
        time.sleep(15)
