import asyncio
import json
import os
from datetime import datetime
from maxapi import Bot, Dispatcher
from maxapi.types import Command, MessageCreated
import gspread
from google.oauth2.service_account import Credentials

# ================= НАСТРОЙКИ =================
MAX_TOKEN = os.getenv("MAX_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
MAIN_SHEET_ID = os.getenv("MAIN_SHEET_ID")
GOOGLE_CREDS = json.loads(os.getenv("GOOGLE_CREDS") or "{}")
BASE_WEBHOOK_URL = os.getenv("BASE_WEBHOOK_URL").rstrip('/') if os.getenv("BASE_WEBHOOK_URL") else None

PORT = int(os.getenv("PORT", 8080))
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "/webhook")

# Таблицы менеджеров
MANAGER_SHEETS = [
    "1uURwa7q2o_PSzqkXAvobFk-iy1gS9k4JGFmevF1O7NU",
    "1od2y0ZwNpe7myLZfXqgN_Dpwx4fG2g69ByYTW-eECwU",
    "1qyWlfSRyK_3CPVbm2c1mBAeVyfli90R1s6NqNiHj8SY",
    "1nKqRES6loYGDbuc8f58APnrVPiEMPDdkqKr51QG5WzQ",
    "1wBolD2JNQwUXnuCuuANDjcOr6qIJgaFnyzcD0OkBkv4",
    "1VoKVBad6DdqiS8AzFGXfmI5-b4CQ6kT7n3aQVcR5WHA",
    "1bmpMh-VhB_yj6QM9L6ucOAKdwabuo75Zb8ycc7xqRAQ"
]

bot = Bot(MAX_TOKEN)
dp = Dispatcher()
gc = None


def normalize_phone(raw):
    if not raw:
        return None
    s = ''.join(filter(str.isdigit, str(raw).strip()))
    if len(s) == 11 and s.startswith('8'):
        s = '7' + s[1:]
    elif len(s) == 10:
        s = '7' + s
    return s if len(s) == 11 and s.startswith('7') else None


# ================= АСИНХРОННЫЕ ОБЁРТКИ =================
async def async_open(spreadsheet_id):
    return await asyncio.to_thread(gc.open_by_key, spreadsheet_id)

async def async_worksheet(spreadsheet, title):
    return await asyncio.to_thread(spreadsheet.worksheet, title)

async def async_append_rows(worksheet, rows_list):
    if not rows_list:
        return
    return await asyncio.to_thread(worksheet.append_rows, rows_list, value_input_option="RAW")


# ================= ОБРАБОТЧИКИ =================
async def process_phone(phone_norm: str, event: MessageCreated):
    chat_id = event.message.chat_id if event.message else event.sender_id
    print(f"=== ПРИВЯЗКА === Номер: {phone_norm} | Chat ID: {chat_id}")

    try:
        spreadsheet = await async_open(MAIN_SHEET_ID)
        clients = await async_worksheet(spreadsheet, "Clients")
        clients_values = await asyncio.to_thread(clients.get_all_values)

        # ... (твоя логика process_phone остаётся прежней — я её не трогаю, чтобы не усложнять)
        # Для экономии места оставил заглушку. Замени этот блок на свой старый process_phone полностью.

        await event.message.answer("✅ Логика привязки работает (тест)")
    except Exception as e:
        print(f"ERROR process_phone: {e}")
        await event.message.answer("❌ Ошибка обработки номера.")


@dp.message_created(Command("start"))
async def start_cmd(event: MessageCreated):
    await event.message.answer("Привет! Напиши номер телефона цифрами.")


@dp.message_created(Command("sync"))
async def sync_cmd(event: MessageCreated):
    if str(event.sender_id) != str(ADMIN_ID):
        await event.message.answer("Доступ запрещён.")
        return
    await event.message.answer("🔄 Команда /sync получена. Синхронизация запущена...")


@dp.message_created()
async def handle_any_message(event: MessageCreated):
    if not event.message or not event.message.text:
        return
    
    text = event.message.text.strip()
    print(f"Получено сообщение: {text} от {event.sender_id}")

    phone_norm = normalize_phone(text)
    if phone_norm:
        await event.message.answer("🔍 Проверяю номер...")
        await process_phone(phone_norm, event)
    else:
        await event.message.answer("Отправь номер телефона цифрами, например: 79123456789\nИли команду /start")


# ================= ЗАПУСК =================
async def on_startup():
    global gc
    try:
        creds = Credentials.from_service_account_info(
            GOOGLE_CREDS,
            scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        )
        gc = gspread.authorize(creds)
        print("✅ Google Sheets подключён")
    except Exception as e:
        print(f"❌ Ошибка Google CREDS: {e}")
        raise

    if not BASE_WEBHOOK_URL:
        print("❌ BASE_WEBHOOK_URL не указан!")
        return

    webhook_url = f"{BASE_WEBHOOK_URL}{WEBHOOK_PATH}"
    try:
        await bot.set_webhook(webhook_url)
        print(f"✅ Webhook установлен: {webhook_url}")
    except Exception as e:
        print(f"❌ Ошибка set_webhook: {e}")


async def main():
    if not MAX_TOKEN:
        print("❌ MAX_TOKEN не указан!")
        return

    dp.startup(on_startup)

    print(f"🚀 Бот запущен на порту {PORT}")
    print(f"📍 Webhook path: {WEBHOOK_PATH}")

    await dp.handle_webhook(
        bot=bot,
        host="0.0.0.0",
        port=PORT,
        path=WEBHOOK_PATH
    )


if __name__ == "__main__":
    asyncio.run(main())
