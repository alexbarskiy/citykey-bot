#!/usr/bin/env python3
import sqlite3, requests, bs4, os, telebot

TOKEN   = os.getenv('TOKEN')          # змінна середовища Railway
DB_NAME = 'stats.db'
bot     = telebot.TeleBot(TOKEN)

SIGNS = {'aries': '♈', 'taurus': '♉', 'gemini': '♊', 'cancer': '♋',
         'leo': '♌', 'virgo': '♍', 'libra': '♎', 'scorpio': '♏',
         'sagittarius': '♐', 'capricorn': '♑', 'aquarius': '♒', 'pisces': '♓'}

def get_horoscope(sign: str) -> str:
    slug = {'aries': 'horoskop-oven', 'taurus': 'horoskop-telec', 'gemini': 'horoskop-bliznyu',
            'cancer': 'horoskop-rak', 'leo': 'horoskop-lev', 'virgo': 'horoskop-diva',
            'libra': 'horoskop-terez', 'scorpio': 'horoskop-skorpion', 'sagittarius': 'horoskop-strilec',
            'capricorn': 'horoskop-kozerig', 'aquarius': 'horoskop-vodoliy', 'pisces': 'horoskop-ryby'}.get(sign, 'horoskop-oven')
    url = f'https://www.citykey.com.ua/{slug}/'
    try:
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        soup = bs4.BeautifulSoup(r.text, 'html.parser')
        h3 = soup.find('h3')
        if h3:
            txt = ' '.join(p.get_text(strip=True) for p in h3.find_all_next('p')[:4])
            return txt[:1200]
    except:
        return 'Гороскоп оновлюється.'
    return 'Гороскоп оновлюється.'

def broadcast():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    subs = c.execute('SELECT user_id, sign FROM subs').fetchall()
    for user_id, sign in subs:
        emoji = SIGNS.get(sign, '♈')
        txt   = get_horoscope(sign)
        try:
            bot.send_message(user_id, f'{emoji} Гороскоп на сьогодні:\n\n{txt}\n\n🔔 Щоб відписатись – /unsubscribe')
        except Exception as e:
            print(f'Не вдалось надіслати {user_id}: {e}')
    conn.close()

if __name__ == '__main__':
    broadcast()
