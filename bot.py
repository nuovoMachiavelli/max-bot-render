import asyncio
import json
import os
from aiohttp import web
import socket

from maxapi import Bot, Dispatcher, types
import gspread
from google.oauth2.service_account import Credentials

# ================= НАСТРОЙКИ =================
MAX_TOKEN = os.getenv("MAX_TOKEN")
BASE_WEBHOOK_URL = os.getenv("BASE_WEBHOOK_URL")
GOOGLE_CREDS = json.loads(os.getenv("GOOGLE_CREDS") or "{}")

WEBHOOK_PATH = "/webhook"
WEBAPP_HOST = "0.0.0.0"
WEBAPP_PORT = int(os.getenv("PORT", 10000))  # важно для Render

bot = Bot(MAX_TOKEN)
dp = Dispatcher()
gc = None

# ================= ПРОВЕРКИ =================
print("🚀 STARTING BOT...")
print("TOKEN:", str(MAX_TOKEN)[:10])
print("WEBHOOK URL:", BASE_WEBHOOK_URL)
print("PORT:", WEBAPP_PORT)

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

# ================= ОБРАБОТКА СООБЩЕНИЙ =================
@dp.message_created()
async def handle_all_messages(event: types.MessageCreated):
    print("🔥 EVENT:", event)

    try:
        text = event.message.text.strip()
    except:
        text = ""

    if text.lower() == "/start":
        await event.message.answer("Привет! Бот работает ✅")
    else:
        await event.message.answer(f"Ты написал: {text}")

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
    # 👉 ВАЖНО: просто вызываем руками
    await on_startup()

    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_post(WEBHOOK_PATH, webhook_handler)

    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, host=WEBAPP_HOST, port=WEBAPP_PORT)
    await site.start()

    print(f"✅ SERVER RUNNING ON PORT {WEBAPP_PORT}")
    print("👉 Render должен увидеть этот порт")
    print("HOSTNAME:", socket.gethostname())

    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
