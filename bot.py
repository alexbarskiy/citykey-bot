# bot.py – телеграм-бот @City_Key_Bot
import telebot, requests, bs4, datetime, sqlite3, os
from telebot import types

TOKEN = '8180365248:AAF3M70ndMKw6zMWEIDcOHmaqupgmEx8Uwk'
bot = telebot.TeleBot(TOKEN)
DB_NAME = 'stats.db'

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY, first_name TEXT, date TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS subs
                 (user_id INTEGER, sign TEXT, PRIMARY KEY (user_id, sign))''')
    conn.commit()
    conn.close()

def count_users():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    starters = c.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    subs = c.execute('SELECT COUNT(DISTINCT user_id) FROM subs').fetchone()[0]
    conn.close()
    return starters, subs

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
        pass
    return 'Гороскоп оновлюється.'

SIGNS_UA = ['♈ Овен', '♉ Тілець', '♊ Близнюки', '♋ Рак', '♌ Лев', '♍ Діва',
            '♎ Терези', '♏ Скорпіон', '♐ Стрілець', '♑ Козеріг', '♒ Водолій', '♓ Риби']

def kb():
    mk = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    mk.add(*[telebot.types.KeyboardButton(s) for s in SIGNS_UA])
    return mk

@bot.message_handler(commands=['start'])
def start(m):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('INSERT OR IGNORE INTO users (user_id, first_name, date) VALUES (?,?,?)',
              (m.from_user.id, m.from_user.first_name, datetime.date.today().isoformat()))
    conn.commit()
    conn.close()
    bot.send_message(m.chat.id,
                     '👋 Привіт! Обери свій знак Зодіаку й отримуй гороскоп.\n\n'
                     '🔔 Хочеш отримувати прогноз щоранку? Натисни /subscribe',
                     reply_markup=kb())

@bot.message_handler(commands=['subscribe'])
def subscribe(m):
    signs = ['♈ Овен', '♉ Тілець', '♊ Близнюки', '♋ Рак', '♌ Лев', '♍ Діва',
             '♎ Терези', '♏ Скорпіон', '♐ Стрілець', '♑ Козеріг', '♒ Водолій', '♓ Риби']
    mk = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=4)
    mk.add(*[telebot.types.KeyboardButton(f'{s} Підписатись') for s in signs])
    bot.send_message(m.chat.id, 'Обери знак, на який хочеш підписатись:', reply_markup=mk)

@bot.message_handler(func=lambda m: m.text.endswith('Підписатись'))
def sub_save(m):
    sign = {'♈': 'aries', '♉': 'taurus', '♊': 'gemini', '♋': 'cancer',
            '♌': 'leo', '♍': 'virgo', '♎': 'libra', '♏': 'scorpio',
            '♐': 'sagittarius', '♑': 'capricorn', '♒': 'aquarius', '♓': 'pisces'}.get(m.text[0])
    if sign:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute('INSERT OR IGNORE INTO subs (user_id, sign) VALUES (?,?)', (m.from_user.id, sign))
        conn.commit()
        conn.close()
        bot.send_message(m.chat.id, f'🔔 Підписку на {m.text[:2]} активовано! Щоранку о 08:00 отримаєш гороскоп.', reply_markup=kb())

@bot.message_handler(commands=['unsubscribe'])
def unsub(m):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('DELETE FROM subs WHERE user_id = ?', (m.from_user.id,))
    conn.commit()
    conn.close()
    bot.send_message(m.chat.id, '🔕 Ви відписались від усіх сповіщень. Натисніть /subscribe, щоб підписатись знову.', reply_markup=kb())

@bot.message_handler(func=lambda m: m.text in SIGNS_UA)
def show_horo(m):
    sign = {'♈ Овен': 'aries', '♉ Тілець': 'taurus', '♊ Близнюки': 'gemini',
            '♋ Рак': 'cancer', '♌ Лев': 'leo', '♍ Діва': 'virgo',
            '♎ Терези': 'libra', '♏ Скорпіон': 'scorpio', '♐ Стрілець': 'sagittarius',
            '♑ Козеріг': 'capricorn', '♒ Водолій': 'aquarius', '♓ Риби': 'pisces'}.get(m.text, 'aries')
    txt = get_horoscope(sign)
    bot.send_message(m.chat.id, f'{m.text}\n\n{txt}', reply_markup=kb())

@bot.message_handler(commands=['stat'])
def stat(m):
    starters, subs = count_users()
    bot.send_message(m.chat.id, f'📊 Унікальних користувачів: {starters}\n🔔 Активних підписок: {subs}')

# ---------- запуск ----------
if __name__ == '__main__':
    init_db()
    print('Bot started')
    bot.infinity_polling()
