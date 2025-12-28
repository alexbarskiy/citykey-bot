# bot.py – телеграм-бот @City_Key_Bot
import telebot
import requests
import bs4
import datetime
import sqlite3
import os

TOKEN = '8180365248:AAF3M70ndMKw6zMWEIDcOHmaqupgmEx8Uwk'
bot = telebot.TeleBot(TOKEN)

# --- база даних ---
DB_NAME = 'stats.db'

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY, first_name TEXT, date TEXT)''')
    conn.commit()
    conn.close()

def count_users():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM users')
    total = c.fetchone()[0]
    conn.close()
    return total

# --- гороскоп ---
def get_horoscope(sign: str) -> str:
    slug = {
        'aries': 'horoskop-oven', 'taurus': 'horoskop-telec', 'gemini': 'horoskop-bliznyu',
        'cancer': 'horoskop-rak', 'leo': 'horoskop-lev', 'virgo': 'horoskop-diva',
        'libra': 'horoskop-terez', 'scorpio': 'horoskop-skorpion', 'sagittarius': 'horoskop-strilec',
        'capricorn': 'horoskop-kozerig', 'aquarius': 'horoskop-vodoliy', 'pisces': 'horoskop-ryby'
    }.get(sign, 'horoskop-oven')

    url = f'https://www.citykey.com.ua/{slug}/'
    try:
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        soup = bs4.BeautifulSoup(r.text, 'html.parser')
        h3 = soup.find('h3')
        if h3:
            txt = ' '.join(p.get_text(strip=True) for p in h3.find_all_next('p')[:4])
            return txt[:1200]
    except:
        pass
    return 'Гороскоп оновлюється.'

# --- клавіатура знаків ---
SIGNS_UA = ['♈ Овен', '♉ Тілець', '♊ Близнюки', '♋ Рак', '♌ Лев', '♍ Діва',
            '♎ Терези', '♏ Скорпіон', '♐ Стрілець', '♑ Козеріг', '♒ Водолій', '♓ Риби']

def kb():
    mk = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    mk.add(*[telebot.types.KeyboardButton(s) for s in SIGNS_UA])
    return mk

# --- handlers ---
@bot.message_handler(commands=['start'])
def start(m):
    # записуємо користувача
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('INSERT OR IGNORE INTO users (user_id, first_name, date) VALUES (?,?,?)',
              (m.from_user.id, m.from_user.first_name, datetime.date.today().isoformat()))
    conn.commit()
    conn.close()

    bot.send_message(m.chat.id, 'Обери свій знак Зодіаку:', reply_markup=kb())

@bot.message_handler(func=lambda m: m.text in SIGNS_UA)
def show_horo(m):
    sign = {
        '♈ Овен': 'aries', '♉ Тілець': 'taurus', '♊ Близнюки': 'gemini',
        '♋ Рак': 'cancer', '♌ Лев': 'leo', '♍ Діва': 'virgo',
        '♎ Терези': 'libra', '♏ Скорпіон': 'scorpio', '♐ Стрілець': 'sagittarius',
        '♑ Козеріг': 'capricorn', '♒ Водолій': 'aquarius', '♓ Риби': 'pisces'
    }.get(m.text, 'aries')

    txt = get_horoscope(sign)
    bot.send_message(m.chat.id, f'{m.text}\n\n{txt}', reply_markup=kb())

# --- команда статистики (тільки для тебе) ---
@bot.message_handler(commands=['stat'])
def stat(m):
    # дозволяємо тільки собі (заміни на свій Telegram-ID)
    ADMIN_ID = 564858074   # ← твій ID (дізнатись: @userinfobot)
    if m.from_user.id == ADMIN_ID:
        total = count_users()
        bot.send_message(m.chat.id, f'📊 Усього підписались: {total}')
    else:
        bot.send_message(m.chat.id, 'Ця команда тільки для адміна.')

# --- запуск ---
if __name__ == '__main__':
    init_db()                       # створюємо таблицю
    print('Bot started')
    bot.infinity_polling()

