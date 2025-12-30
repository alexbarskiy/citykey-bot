import os
import sqlite3
import datetime
import requests
import bs4
import telebot
import time
import sys
import re
from telebot.apihelper import ApiTelegramException

# --- 1. ПРИМУСОВА ДІАГНОСТИКА ТОКЕНА (як у bot.py) ---
raw_token = os.getenv("FINAL_BOT_TOKEN") or os.getenv("BOT_TOKEN") or os.getenv("TOKEN") or ""
TOKEN = re.sub(r'[^a-zA-Z0-9:_]', '', raw_token).strip()

# Шлях до бази даних
DB_NAME = os.getenv("DB_PATH", "data/stats.db")

if not TOKEN:
    print("--- КРИТИЧНА ПОМИЛКА: TOKEN не знайдено у змінних оточення! ---", flush=True)
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

def get_preview(sign: str) -> str:
    """Отримання короткого тексту гороскопу з сайту"""
    info = SIGNS.get(sign)
    url = f'https://www.citykey.com.ua/{info["slug"]}/'
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        soup = bs4.BeautifulSoup(r.text, "html.parser")
        container = soup.select_one(".entry-content")
        if not container: return "Прогноз уже на сайті!"
        paragraphs = container.find_all("p")
        text_parts = [p.get_text().strip() for p in paragraphs if len(p.get_text()) > 30]
        txt = " ".join(text_parts[:2]).strip()
        return (txt[:400] + "...") if len(txt) > 400 else (txt or "Читати далі на сайті.")
    except Exception as e:
        return "Сьогоднішній прогноз уже опубліковано на сайті!"

def broadcast(force_send=False):
    today = datetime.date.today().isoformat()
    
    print(f"--- ЗАПУСК РУЧНОЇ РОЗСИЛКИ ---", flush=True)
    print(f"Використовується база: {DB_NAME}", flush=True)
    
    if not os.path.exists(DB_NAME):
        print(f"❌ ПОМИЛКА: Базу {DB_NAME} не знайдено!", flush=True)
        return

    try:
        conn = sqlite3.connect(DB_NAME, timeout=20)
        c = conn.cursor()
        rows = c.execute("SELECT user_id, sign FROM subs").fetchall()
        conn.close()
    except Exception as e:
        print(f"❌ ПОМИЛКА БАЗИ ДАНИХ: {e}", flush=True)
        return

    print(f"Знайдено підписок: {len(rows)}", flush=True)
    
    if len(rows) == 0:
        print("Розсилка скасована: база підписок порожня.", flush=True)
        return

    for user_id, sign in rows:
        if sign not in SIGNS: continue
        
        # Перевірка дублікатів (якщо це не тестовий запуск)
        if not force_send:
            try:
                conn = sqlite3.connect(DB_NAME, timeout=20)
                sent = conn.execute("SELECT 1 FROM deliveries WHERE user_id=? AND sign=? AND date=?", (user_id, sign, today)).fetchone()
                conn.close()
                if sent:
                    print(f"⏩ Користувач {user_id} вже отримав прогноз сьогодні.", flush=True)
                    continue
            except: pass

        info = SIGNS[sign]
        preview = get_preview(sign)
        
        text = f'☀️ <b>{info["ua"]}. Гороскоп на сьогодні</b>\n\n{preview}'
        url = f'https://www.citykey.com.ua/{info["slug"]}/'
        
        kb = telebot.types.InlineKeyboardMarkup()
        kb.add(telebot.types.InlineKeyboardButton("Читати повний прогноз", url=url))

        try:
            bot.send_message(user_id, text, reply_markup=kb, disable_web_page_preview=True)
            
            # Помітка про доставку
            conn = sqlite3.connect(DB_NAME, timeout=20)
            conn.execute("INSERT OR IGNORE INTO deliveries (user_id, sign, date) VALUES (?,?,?)", (user_id, sign, today))
            conn.commit()
            conn.close()
            print(f"✅ УСПІШНО надіслано користувачу {user_id}", flush=True)
            time.sleep(0.1)
            
        except ApiTelegramException as e:
            if e.error_code == 409:
                print("❌ КОНФЛІКТ 409: Основний бот все ще запущений!", flush=True)
                return
            print(f"Помилка для {user_id}: {e.description}", flush=True)
        except Exception as e:
            print(f"Загальна помилка для {user_id}: {e}", flush=True)

    print(f"--- РОЗСИЛКА ЗАВЕРШЕНА ---", flush=True)

if __name__ == "__main__":
    is_test = len(sys.argv) > 1 and sys.argv[1] == "test"
    broadcast(force_send=is_test)
