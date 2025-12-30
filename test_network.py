import os
import requests
import telebot
import socket
import sys

def run_test():
    # Отримуємо токен
    token = os.getenv("FINAL_BOT_TOKEN") or os.getenv("BOT_TOKEN") or os.getenv("TOKEN")
    
    print("--- ЗАПУСК ДІАГНОСТИКИ МЕРЕЖІ ---", flush=True)
    print(f"Python version: {sys.version}", flush=True)
    print(f"Токен знайдено: {'ТАК' if token else 'НІ'}", flush=True)

    # 1. Перевірка DNS (чи знає сервер, де знаходиться telegram)
    try:
        host = "api.telegram.org"
        ip = socket.gethostbyname(host)
        print(f"✅ DNS працює: {host} -> {ip}", flush=True)
    except Exception as e:
        print(f"❌ Помилка DNS (сервер не бачить адрес): {e}", flush=True)

    # 2. Перевірка загального виходу в інтернет
    try:
        r = requests.get("https://www.google.com", timeout=10)
        print(f"✅ Загальний інтернет: Google доступний ({r.status_code})", flush=True)
    except Exception as e:
        print(f"❌ КРИТИЧНО: Загальний інтернет недоступний (Errno 101): {e}", flush=True)

    # 3. Перевірка зв'язку з Telegram API через простий запит
    if token:
        try:
            url = f"https://api.telegram.org/bot{token}/getMe"
            r = requests.get(url, timeout=10)
            print(f"✅ Telegram API: Статус {r.status_code}", flush=True)
            print(f"Відповідь: {r.text}", flush=True)
        except Exception as e:
            print(f"❌ Помилка зв'язку з Telegram API: {e}", flush=True)

    # 4. Перевірка через бібліотеку telebot
    if token:
        try:
            bot = telebot.TeleBot(token)
            me = bot.get_me()
            print(f"✅ Бібліотека telebot: Авторизовано як @{me.username}", flush=True)
        except Exception as e:
            print(f"❌ Бібліотека telebot не може з'єднатися: {e}", flush=True)

if __name__ == "__main__":
    run_test()
