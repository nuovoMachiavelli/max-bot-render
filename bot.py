import asyncio
import os
from maxapi import Bot, Dispatcher
from maxapi.types import Command, MessageCreated

MAX_TOKEN = os.getenv("MAX_TOKEN")
BASE_WEBHOOK_URL = os.getenv("BASE_WEBHOOK_URL").rstrip('/') if os.getenv("BASE_WEBHOOK_URL") else None
PORT = int(os.getenv("PORT", 8080))
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "/webhook")

bot = Bot(MAX_TOKEN)
dp = Dispatcher()


@dp.message_created(Command("start"))
async def start_cmd(event: MessageCreated):
    await event.message.answer("✅ Бот живой! /start работает.")


@dp.message_created()
async def echo(event: MessageCreated):
    if event.message and event.message.text:
        text = event.message.text.strip()
        print(f"📨 Получено сообщение: '{text}' от {event.sender_id}")
        await event.message.answer(f"Я получил: {text}\n\nБот работает! 🎉")


async def on_startup():
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
    print(f"🚀 Тестовый бот запущен на порту {PORT}")

    await dp.handle_webhook(
        bot=bot,
        host="0.0.0.0",
        port=PORT,
        path=WEBHOOK_PATH
    )


if __name__ == "__main__":
    asyncio.run(main())
