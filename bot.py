import asyncio
import json
import os
from datetime import datetime
from aiohttp import web

from maxapi import Bot, Dispatcher, types, filters
import gspread
from google.oauth2.service_account import Credentials

# ================= НАСТРОЙКИ =================
MAX_TOKEN = os.getenv("MAX_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
MAIN_SHEET_ID = os.getenv("MAIN_SHEET_ID")
GOOGLE_CREDS = json.loads(os.getenv("GOOGLE_CREDS") or "{}")

BASE_WEBHOOK_URL = os.getenv("BASE_WEBHOOK_URL")
WEBHOOK_PATH = "/webhook"

WEBAPP_HOST = "0.0.0.0"
WEBAPP_PORT = int(os.getenv("PORT", 8080))

bot = Bot(MAX_TOKEN)
dp = Dispatcher()
gc = None

# ================= DEBUG =================
print("🚀 STARTING BOT...")
print("TOKEN:", str(MAX_TOKEN)[:10])
print("WEBHOOK URL:", BASE_WEBHOOK_URL)

if not MAX_TOKEN:
    raise ValueError("❌ MAX_TOKEN не задан")

if not BASE_WEBHOOK_URL:
    raise ValueError("❌ BASE_WEBHOOK_URL не задан")

if not GOOGLE_CREDS:
    raise ValueError("❌ GOOGLE_CREDS пустой")

# ================= HEALTH =================
async def health(request):
    return web.Response(text="OK")

# ================= WEBHOOK =================
async def webhook_handler(request):
    print("📩 WEBHOOK HIT")

    try:
        data = await request.json()
        print("📦 RAW UPDATE:", data)

        update = types.Update(**data)
        await dp.feed_update(bot, update)

        return web.Response(text="ok")
    except Exception as e:
        print("❌ WEBHOOK ERROR:", e)
        return web.Response(status=500)

# ================= ОБРАБОТЧИКИ =================
@dp.message_created()
async def debug_all(event: types.MessageCreated):
    print("🔥 EVENT:", event)

@dp.message_created(filters.Command("start"))
async def start(event: types.MessageCreated):
    await event.message.answer("Привет! Бот работает ✅")

# ================= STARTUP =================
async def on_startup():
    global gc

    print("🔧 Инициализация Google...")
    creds = Credentials.from_service_account_info(
        GOOGLE_CREDS,
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ],
    )
    gc = gspread.authorize(creds)

    webhook_url = f"{BASE_WEBHOOK_URL.rstrip('/')}{WEBHOOK_PATH}"

    print("🔗 Устанавливаю webhook:", webhook_url)
    res = await bot.set_webhook(webhook_url)
    print("✅ RESULT:", res)

# ================= MAIN =================
async def main():
    dp.startup.register(on_startup)

    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_post(WEBHOOK_PATH, webhook_handler)

    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, host=WEBAPP_HOST, port=WEBAPP_PORT)
    await site.start()

    print(f"🌐 SERVER STARTED: {WEBAPP_PORT}")

    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
