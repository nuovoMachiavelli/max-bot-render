import asyncio
import json
import os
from datetime import datetime
from maxapi import Bot, Dispatcher
from maxapi.types import MessageCreated
import gspread
from google.oauth2.service_account import Credentials

# ================= НАСТРОЙКИ =================
MAX_TOKEN = os.getenv("MAX_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
MAIN_SHEET_ID = os.getenv("MAIN_SHEET_ID")
GOOGLE_CREDS = json.loads(os.getenv("GOOGLE_CREDS") or "{}")

BASE_WEBHOOK_URL = os.getenv("BASE_WEBHOOK_URL")
if BASE_WEBHOOK_URL:
    BASE_WEBHOOK_URL = BASE_WEBHOOK_URL.rstrip('/')

PORT = int(os.getenv("PORT", 8080))
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "/webhook")

bot = Bot(MAX_TOKEN)
dp = Dispatcher()
gc = None


# ================= УТИЛИТЫ =================
def normalize_phone(raw):
    if not raw:
        return None
    s = ''.join(filter(str.isdigit, str(raw).strip()))
    if len(s) == 11 and s.startswith('8'):
        s = '7' + s[1:]
    elif len(s) == 10:
        s = '7' + s
    return s if len(s) == 11 and s.startswith('7') else None


# ================= DEBUG =================
@dp.message_created()
async def debug_all(event: MessageCreated):
    print("📩 EVENT ПРИШЁЛ:", event)


# ================= ОСНОВНОЙ ОБРАБОТЧИК =================
@dp.message_created()
async def handle_text(event: MessageCreated):
    if not event.message or not event.message.text:
        return

    text = event.message.text.strip().lower()
    print("💬 TEXT:", text)

    # === /start ===
    if text == "/start":
        await event.message.answer("Привет! Напиши номер телефона цифрами.")
        return

    # === /sync ===
    if text == "/sync":
        if str(event.sender_id) != str(ADMIN_ID):
            await event.message.answer("Доступ запрещён.")
            return
        await event.message.answer("🔄 Команда sync получена")
        return

    # === /broadcast ===
    if text == "/broadcast":
        if str(event.sender_id) != str(ADMIN_ID):
            await event.message.answer("Доступ запрещён.")
            return
        await event.message.answer("🚀 Команда broadcast получена")
        return

    # === номер телефона ===
    phone_norm = normalize_phone(text)
    if phone_norm:
        await event.message.answer(f"🔍 Номер принят: {phone_norm}")
    else:
        await event.message.answer("❌ Номер не распознан. Отправь номер цифрами.")


# ================= ЗАПУСК =================
async def on_startup():
    global gc

    print("🚀 Запуск бота...")

    try:
        creds = Credentials.from_service_account_info(
            GOOGLE_CREDS,
            scopes=[
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive"
            ]
        )
        gc = gspread.authorize(creds)
        print("✅ Google подключен")
    except Exception as e:
        print("❌ Ошибка Google:", e)

    webhook_url = f"{BASE_WEBHOOK_URL}{WEBHOOK_PATH}"

    try:
        res = await bot.set_webhook(webhook_url)
        print("✅ Webhook установлен:", webhook_url)
        print("RESULT:", res)
    except Exception as e:
        print("❌ Ошибка webhook:", e)


async def main():
    if not MAX_TOKEN:
        print("❌ MAX_TOKEN не указан")
        return

    await on_startup()

    print(f"🌐 Сервер на порту {PORT}")

    await dp.handle_webhook(
        bot=bot,
        host="0.0.0.0",
        port=PORT,
        path=WEBHOOK_PATH
    )


if __name__ == "__main__":
    asyncio.run(main())
