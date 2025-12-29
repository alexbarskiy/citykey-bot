import os
import sqlite3
import datetime
import requests
import bs4
import telebot

TOKEN = os.getenv("TOKEN", "").strip()
if not TOKEN:
    raise RuntimeError("TOKEN env var is missing. Add TOKEN in Railway Variables.")

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
DB_NAME = "stats.db"

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

    headers1 = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "uk-UA,uk;q=0.9,en-US;q=0.8,en;q=0.7",
        "Connection": "keep-alive",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Referer": "https://www.google.com/",
    }

    r = session.get(url, headers=headers1, timeout=(5, 14), allow_redirects=True)
    if r.status_code in (403, 429) or not r.text:
        headers2 = dict(headers1)
        headers2["User-Agent"] = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
        r = session.get(url, headers=headers2, timeout=(5, 14), allow_redirects=True)

    r.raise_for_status()
    return r.text

def get_preview(sign: str) -> str:
    info = SIGNS.get(sign, SIGNS["aries"])
    url = f'https://www.citykey.com.ua/{info["slug"]}/'

    try:
        html = _fetch_html(url)
        soup = bs4.BeautifulSoup(html, "html.parser")

        container = (
            soup.select_one(".entry-content")
            or soup.select_one("article")
            or soup.select_one("main")
            or soup.body
        )

        if not container:
            return "Прогноз уже на сайті. Натисни кнопку нижче, щоб прочитати повністю."

        parts = []
        h3 = container.find("h3")
        if h3:
            for p in h3.find_all_next("p", limit=10):
                t = p.get_text(" ", strip=True)
                if t:
                    parts.append(t)

        if not parts:
            for p in container.find_all("p", limit=10):
                t = p.get_text(" ", strip=True)
                if t and len(t) > 20:
                    parts.append(t)

        txt = " ".join(parts).strip()
        if not txt:
            return "Прогноз уже на сайті. Натисни кнопку нижче, щоб прочитати повністю."

        if len(txt) > 600:
            txt = txt[:600].rsplit(" ", 1)[0] + "…"

        return txt
    except Exception:
        return "Прогноз уже на сайті. Натисни кнопку нижче, щоб прочитати повністю."

def already_sent_today(user_id: int, sign: str, today: str) -> bool:
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    row = c.execute(
        "SELECT 1 FROM deliveries WHERE user_id = ? AND sign = ? AND date = ? LIMIT 1",
        (user_id, sign, today),
    ).fetchone()
    conn.close()
    return bool(row)

def mark_sent_today(user_id: int, sign: str, today: str) -> None:
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute(
        "INSERT OR IGNORE INTO deliveries (user_id, sign, date) VALUES (?,?,?)",
        (user_id, sign, today),
    )
    conn.commit()
    conn.close()

def broadcast():
    today = datetime.date.today().isoformat()

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    rows = c.execute("SELECT user_id, sign FROM subs").fetchall()
    conn.close()

    for user_id, sign in rows:
        if sign not in SIGNS:
            continue
        if already_sent_today(user_id, sign, today):
            continue

        info = SIGNS[sign]
        preview = get_preview(sign)
        url = f'https://www.citykey.com.ua/{info["slug"]}/?utm_source=telegram&utm_medium=bot&utm_campaign=horoscope_daily&utm_content={sign}'

        text = f'{info["emoji"]} <b>{info["ua"]}. Гороскоп на сьогодні</b>\n\n{preview}'
        kb = telebot.types.InlineKeyboardMarkup()
        kb.add(telebot.types.InlineKeyboardButton("Читати далі на сайті", url=url))

        try:
            bot.send_message(user_id, text, reply_markup=kb, disable_web_page_preview=True)
            mark_sent_today(user_id, sign, today)
        except Exception as e:
            print(f"Send failed to {user_id}: {e}")

if __name__ == "__main__":
    broadcast()
