import asyncio
import json
import logging
import os
import aiohttp
import ssl
import certifi

from aiohttp import web

from config import (
    MAX_BOT_TOKEN,
    ADMIN_USER_ID,
    GOOGLE_CREDS_JSON,
    WEBHOOK_URL,
    WEBHOOK_PATH,
    PORT
)

from google_sheets import init_google_sheets

from handlers import (
    process_phone,
    sync_command,
    broadcast_command,
    normalize_phone,
    subscriptions_command
)

from max_api import MaxClient


logging.basicConfig(level=logging.INFO)


max_client = MaxClient()


print("=== STARTING BOT ===")
print(f"MAX_BOT_TOKEN set: {bool(MAX_BOT_TOKEN)}")
print(f"ADMIN_USER_ID: {ADMIN_USER_ID}")
print(f"MAIN_SHEET_ID: {os.getenv('MAIN_SHEET_ID')}")
print(f"WEBHOOK_URL: {WEBHOOK_URL}")
print(f"PORT: {PORT}")


async def handle_update(data):

    try:

        update_type = data.get('update_type')

        user_id = None


        if 'user' in data and data['user']:
            user_id = data['user'].get('user_id')

        elif 'message' in data and data['message'].get('sender'):
            user_id = data['message']['sender'].get('user_id')


        if not user_id:
            return


        if update_type == 'bot_started':

            keyboard = [[{
                "type": "request_contact",
                "text": "📱 Поделиться номером"
            }]]

            await max_client.send_message(
                user_id,
                "Привет! Нажмите кнопку ниже, чтобы поделиться номером телефона, или отправьте номер цифрами.",
                keyboard=keyboard
            )

            return


        if update_type == 'message_created':

            message = data.get('message', {})

            body = message.get('body', {})

            text = body.get('text', '')

            attachments = body.get('attachments', [])


            for att in attachments:

                if att.get('type') == 'contact':

                    phone_raw = att.get('payload', {}).get('phone_number', '')

                    phone_norm = normalize_phone(phone_raw)

                    if phone_norm:
                        await process_phone(
                            phone_norm,
                            user_id
                        )

                    else:
                        await max_client.send_message(
                            user_id,
                            "❌ Не удалось распознать номер."
                        )

                    return


            if text:

                if text == '/sync' and user_id == ADMIN_USER_ID:
                    await sync_command(user_id)
                    return


                if text == '/broadcast' and user_id == ADMIN_USER_ID:
                    await broadcast_command(user_id)
                    return


                if text == '/subscriptions' and user_id == ADMIN_USER_ID:
                    await subscriptions_command(user_id)
                    return


                phone_norm = normalize_phone(text)


                if phone_norm:

                    await max_client.send_message(
                        user_id,
                        "🔍 Проверяю номер..."
                    )

                    await process_phone(
                        phone_norm,
                        user_id
                    )

                else:

                    await max_client.send_message(
                        user_id,
                        "Пожалуйста, отправьте номер в правильном формате."
                    )


    except Exception:

        logging.exception("UPDATE ERROR")



async def webhook_handler(request):

    data = await request.json()

    logging.info(
        f"Received update: {json.dumps(data, indent=2)}"
    )


    asyncio.create_task(
        handle_update(data)
    )


    return web.Response(status=200)



async def set_webhook():

    url = f"{WEBHOOK_URL}{WEBHOOK_PATH}"


    headers = {
        "Authorization": MAX_BOT_TOKEN,
        "Content-Type": "application/json"
    }


    payload = {

        "url": url,

        "update_types": [
            "message_created",
            "bot_started"
        ]
    }


    ssl_context = ssl.create_default_context(
        cafile=certifi.where()
    )


    connector = aiohttp.TCPConnector(
        ssl=False
    )


    async with aiohttp.ClientSession(
        connector=connector
    ) as session:


        async with session.post(

            "https://platform-api2.max.ru/subscriptions",

            headers=headers,

            json=payload

        ) as resp:


            text = await resp.text()


            if resp.status == 200:

                logging.info(
                    f"Webhook successfully set: {url}"
                )

            else:

                logging.error(
                    f"Webhook error {resp.status}: {text}"
                )



async def main():

    init_google_sheets(
        GOOGLE_CREDS_JSON
    )


    await set_webhook()


    app = web.Application()


    app.router.add_post(
        WEBHOOK_PATH,
        webhook_handler
    )


    runner = web.AppRunner(app)

    await runner.setup()


    site = web.TCPSite(
        runner,
        host="0.0.0.0",
        port=PORT
    )


    await site.start()


    logging.info(
        "Bot started"
    )


    await asyncio.Event().wait()



if __name__ == "__main__":

    asyncio.run(main())
