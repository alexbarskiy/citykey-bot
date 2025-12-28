# bot.py – телеграм-бот @City_Key_Bot
import telebot
import requests
import bs4
import datetime

TOKEN = '8180365248:AAF3M70ndMKw6zMWEIDcOHmaqupgmEx8Uwk'
bot = telebot.TeleBot(TOKEN)

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

# --- запуск ---
if __name__ == '__main__':
    print('Bot started')

    bot.infinity_polling()
