import os
import sqlite3
import requests
import bs4
import telebot

TOKEN = os.getenv("TOKEN", "").strip()
if not TOKEN:
    raise RuntimeError("TOKEN env var is missing. Add TOKEN in Railway Variables.")

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
DB_NAME = "stats.db"

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


def get_preview(sign: str) -> str:
    info = SIGNS.get(sign, SIGNS["aries"])
    url = f'https://www.citykey.com.ua/{info["slug"]}/'
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=12)
        r.raise_for_status()
        soup = bs4.BeautifulSoup(r.text, "html.parser")

        h3 = soup.find("h3")
        if not h3:
            return "Гороскоп оновлюється."

        parts = []
        for p in h3.find_all_next("p", limit=6):
            t = p.get_text(" ", strip=True)
            if t:
                parts.append(t)

        txt = " ".join(parts).strip()
        if not txt:
            return "Гороскоп оновлюється."

        if len(txt) > 260:
            txt = txt[:260].rsplit(" ", 1)[0] + "…"
        return txt
    except Exception:
        return "Гороскоп оновлюється."


def build_daily_keyboard(user_signs: list[str]):
    from telebot import types

    kb = types.InlineKeyboardMarkup(row_width=1)
    for sign in user_signs:
        info = SIGNS.get(sign)
        if not info:
            continue
        url = (
            f'https://www.citykey.com.ua/{info["slug"]}/'
            f'?utm_source=telegram&utm_medium=bot&utm_campaign=horoscope_daily&utm_content={sign}'
        )
        kb.add(types.InlineKeyboardButton(f'{info["emoji"]} {info["ua"]} читати повністю', url=url))

    kb.add(types.InlineKeyboardButton("🔕 Відписатись від всього", callback_data="unsub_all"))
    return kb


def broadcast():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    rows = c.execute("SELECT user_id, sign FROM subs ORDER BY user_id").fetchall()
    conn.close()

    if not rows:
        print("No subscriptions found")
        return

    by_user: dict[int, list[str]] = {}
    for user_id, sign in rows:
        if sign not in SIGNS:
            continue
        by_user.setdefault(int(user_id), []).append(sign)

    for user_id, signs in by_user.items():
        seen = set()
        uniq_signs = []
        for s in signs:
            if s not in seen:
                seen.add(s)
                uniq_signs.append(s)

        blocks = []
        for s in uniq_signs:
            info = SIGNS[s]
            preview = get_preview(s)
            blocks.append(f'{info["emoji"]} <b>{info["ua"]}</b>\n{preview}')

        text = "<b>Твої гороскопи на сьогодні</b>\n\n" + "\n\n".join(blocks)
        kb = build_daily_keyboard(uniq_signs)

        try:
            bot.send_message(user_id, text, reply_markup=kb, disable_web_page_preview=True)
        except Exception as e:
            print(f"Send failed to {user_id}: {e}")


if __name__ == "__main__":
    broadcast()
