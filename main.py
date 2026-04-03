import asyncio
import json
import logging
from aiohttp import web

from config import MAX_BOT_TOKEN, ADMIN_USER_ID, GOOGLE_CREDS_JSON, WEBHOOK_URL, WEBHOOK_PATH, PORT
from google_sheets import init_google_sheets
from handlers import process_phone, sync_command, broadcast_command, normalize_phone
from max_api import MaxClient

logging.basicConfig(level=logging.INFO)

max_client = MaxClient()

# ---------- Обработка входящего обновления от MAX ----------
async def webhook_handler(request):
    try:
        data = await request.json()
        logging.info(f"Received update: {json.dumps(data, indent=2)}")

        update_type = data.get('update_type')
        # Определяем user_id (может быть в data['user'] или data['message']['sender'])
        user_id = None
        if 'user' in data and data['user']:
            user_id = data['user'].get('user_id')
        elif 'message' in data and data['message'].get('sender'):
            user_id = data['message']['sender'].get('user_id')

        if not user_id:
            return web.Response(status=200)  # игнорируем

        # Обработка команды /start (бот запущен)
        if update_type == 'bot_started':
            # Отправляем приветствие с кнопкой запроса контакта
            keyboard = [[{
                "type": "request_contact",
                "text": "📱 Поделиться номером"
            }]]
            await max_client.send_message(
                user_id,
                "Привет! Нажмите кнопку ниже, чтобы поделиться номером телефона, или отправьте номер цифрами.",
                keyboard=keyboard
            )
            return web.Response(status=200)

        # Обработка нового сообщения
        if update_type == 'message_created':
            message = data.get('message', {})
            body = message.get('body', {})
            text = body.get('text', '')
            attachments = body.get('attachments', [])

            # Проверка, есть ли вложение contact
            for att in attachments:
                if att.get('type') == 'contact':
                    contact_payload = att.get('payload', {})
                    phone_raw = contact_payload.get('phone_number', '')
                    phone_norm = normalize_phone(phone_raw)
                    if phone_norm:
                        await process_phone(phone_norm, user_id)
                    else:
                        await max_client.send_message(user_id, "❌ Не удалось распознать номер.")
                    return web.Response(status=200)

            # Если это текст
            if text:
                # Команды для админа
                if text == '/sync' and user_id == ADMIN_USER_ID:
                    await sync_command(user_id)
                    return web.Response(status=200)
                if text == '/broadcast' and user_id == ADMIN_USER_ID:
                    await broadcast_command(user_id)
                    return web.Response(status=200)

                # Иначе пробуем как номер телефона
                phone_norm = normalize_phone(text)
                if phone_norm:
                    await max_client.send_message(user_id, "🔍 Проверяю номер...")
                    await process_phone(phone_norm, user_id)
                else:
                    await max_client.send_message(user_id, "Пожалуйста, отправьте номер в правильном формате (только цифры).")
                return web.Response(status=200)

        return web.Response(status=200)
    except Exception as e:
        logging.exception("Error in webhook")
        return web.Response(status=500)

# ---------- Установка вебхука на MAX ----------
async def set_webhook():
    url = f"{WEBHOOK_URL}{WEBHOOK_PATH}"
    # Отправляем POST /subscriptions для настройки вебхука
    async with aiohttp.ClientSession() as session:
        headers = {"Authorization": MAX_BOT_TOKEN, "Content-Type": "application/json"}
        payload = {
            "url": url,
            "update_types": ["message_created", "bot_started"]
        }
        async with session.post("https://platform-api.max.ru/subscriptions", headers=headers, json=payload) as resp:
            if resp.status == 200:
                logging.info(f"Webhook successfully set to {url}")
            else:
                text = await resp.text()
                logging.error(f"Failed to set webhook: {resp.status} {text}")

# ---------- Запуск сервера ----------
async def main():
    # Инициализируем Google Sheets
    init_google_sheets(GOOGLE_CREDS_JSON)
    # Устанавливаем вебхук (при старте)
    await set_webhook()
    # Запускаем aiohttp сервер
    app = web.Application()
    app.router.add_post(WEBHOOK_PATH, webhook_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host='0.0.0.0', port=PORT)
    await site.start()
    logging.info(f"Server started on port {PORT}, webhook path {WEBHOOK_PATH}")
    # Бесконечное ожидание
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
