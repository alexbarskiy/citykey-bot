import os
import sqlite3
import datetime
import requests
import bs4
import telebot
import time
import sys
from telebot.apihelper import ApiTelegramException

# ВАЖЛИВО: Обидва файли (bot.py та broadcast.py) мають використовувати однаковий шлях
DB_NAME = os.getenv("DB_PATH", "stats.db")
TOKEN = os.getenv("TOKEN", "").strip()

if not TOKEN:
    raise RuntimeError("TOKEN is missing.")

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

def _fetch_html(url: str) -> str:
    session = requests.Session()
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    try:
        r = session.get(url, headers=headers, timeout=(5, 14))
        r.raise_for_status()
        return r.text
    except Exception: return ""

def get_preview(sign: str) -> str:
    """Отримуємо текст прогнозу для розсилки"""
    info = SIGNS.get(sign)
    url = f'https://www.citykey.com.ua/{info["slug"]}/'
    try:
        html = _fetch_html(url)
        if not html: return "Сьогоднішній прогноз уже доступний на сайті!"
        soup = bs4.BeautifulSoup(html, "html.parser")
        container = soup.select_one(".entry-content") or soup.body
        parts = [p.get_text(strip=True) for p in container.find_all("p", limit=3) if len(p.get_text()) > 20]
        txt = " ".join(parts).strip()
        return (txt[:400] + "...") if len(txt) > 400 else txt
    except Exception:
        return "Сьогоднішній прогноз уже доступний на сайті!"

def remove_user_subscription(user_id: int):
    """Видаляємо користувача, якщо він заблокував бота"""
    try:
        conn = sqlite3.connect(DB_NAME, timeout=10)
        c = conn.cursor()
        c.execute("DELETE FROM subs WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
        print(f"Користувач {user_id} видалений (бот заблокований)")
    except Exception as e:
        print(f"Помилка видалення користувача: {e}")

def broadcast(force_send=False):
    today = datetime.date.today().isoformat()
    
    if not os.path.exists(DB_NAME):
        print(f"База даних {DB_NAME} не знайдена. Перевірте DB_PATH.")
        return

    # Отримуємо список підписок
    try:
        conn = sqlite3.connect(DB_NAME, timeout=10)
        c = conn.cursor()
        rows = c.execute("SELECT user_id, sign FROM subs").fetchall()
        conn.close()
    except Exception as e:
        print(f"Помилка читання бази: {e}")
        return

    print(f"Початок розсилки для {len(rows)} записів... (Примусово: {force_send})")

    for user_id, sign in rows:
        if sign not in SIGNS: continue
        
        # Якщо НЕ тестовий запуск, перевіряємо чи вже відправляли сьогодні
        if not force_send:
            conn = sqlite3.connect(DB_NAME, timeout=10)
            sent = conn.execute("SELECT 1 FROM deliveries WHERE user_id=? AND sign=? AND date=?", (user_id, sign, today)).fetchone()
            conn.close()
            if sent: 
                print(f"Користувач {user_id} ({sign}) вже отримав сьогодні. Пропускаю.")
                continue

        info = SIGNS[sign]
        preview_text = get_preview(sign)
        
        text = f'{info["emoji"]} <b>{info["ua"]}. Гороскоп на сьогодні</b>\n\n{preview_text}'
        url = f'https://www.citykey.com.ua/{info["slug"]}/?utm_source=telegram'
        
        kb = telebot.types.InlineKeyboardMarkup()
        kb.add(telebot.types.InlineKeyboardButton("Читати повністю на сайті", url=url))

        try:
            bot.send_message(user_id, text, reply_markup=kb, disable_web_page_preview=True)
            
            # Помітка про успішну доставку
            conn = sqlite3.connect(DB_NAME, timeout=10)
            conn.execute("INSERT OR IGNORE INTO deliveries (user_id, sign, date) VALUES (?,?,?)", (user_id, sign, today))
            conn.commit()
            conn.close()
            print(f"Надіслано для {user_id} ({sign})")
            
            time.sleep(0.2) # Затримка
            
        except ApiTelegramException as e:
            if e.error_code == 403:
                remove_user_subscription(user_id)
            else:
                print(f"Помилка Telegram для {user_id}: {e}")
        except Exception as e:
            print(f"Загальна помилка для {user_id}: {e}")

if __name__ == "__main__":
    # Перевіряємо чи запущено з аргументом 'test'
    is_test = len(sys.argv) > 1 and sys.argv[1] == "test"
    broadcast(force_send=is_test)
