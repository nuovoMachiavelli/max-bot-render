import asyncio
import json
import logging
import os
import aiohttp
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


# ================= СТАРЫЕ ПОДПИСКИ =================

OLD_SUBSCRIPTIONS = [
    "https://max-bot-render.onrender.com/webhook",
    "https://bot-1784280894-5382-machiavelli.bothost.tech/webhook/webhook",
    "https://bot-1784281727-9973-machiavelli.bothost.tech/webhook",
    "https://max-bot-render.onrender.com"
]


# ================= ПРОВЕРКА ПОДПИСОК =================

async def get_max_subscriptions():

    timeout = aiohttp.ClientTimeout(total=25)

    async with aiohttp.ClientSession(timeout=timeout) as session:

        async with session.get(
            "https://platform-api2.max.ru/subscriptions",
            headers={"Authorization": MAX_BOT_TOKEN}
        ) as response:

            body = await response.text()

            if response.status != 200:
                raise Exception(
                    f"Ошибка получения подписок: HTTP {response.status}: {body}"
                )

            return json.loads(body).get("subscriptions", [])


# ================= ОЧИСТКА ПОДПИСОК =================

async def cleanup_subscriptions_command(user_id, confirm=False):

    try:

        subscriptions = await get_max_subscriptions()

        current_urls = [
            item.get("url")
            for item in subscriptions
        ]

        # Защита текущего адреса бота и Bitrix
        protected_urls = {
            WEBHOOK_URL,
            "https://im-ru.bitrix.info/imwebhook/eh/1d8a1778d2f80af613758e1538ea27841774864307/"
        }

        targets = [
            url for url in OLD_SUBSCRIPTIONS
            if url in current_urls and url not in protected_urls
        ]

        if not confirm:

            if not targets:

                await max_client.send_message(
                    user_id,
                    "✅ Старых подписок для удаления не найдено."
                )

                return

            message = (
                "🔎 Найдены старые подписки:\n\n"
                + "\n".join(targets)
                + "\n\nBitrix и текущий Bothost останутся нетронутыми."
                + "\n\nДля подтверждения отправь:\n"
                + "/cleanup_subscriptions_confirm"
            )

            await max_client.send_message(user_id, message)

            return

        if not targets:

            await max_client.send_message(
                user_id,
                "✅ Старых подписок для удаления не найдено."
            )

            return

        results = []

        timeout = aiohttp.ClientTimeout(total=25)

        async with aiohttp.ClientSession(timeout=timeout) as session:

            for url in targets:

                # Повторная защита перед удалением
                if url == WEBHOOK_URL or url in protected_urls:

                    continue

                async with session.delete(
                    "https://platform-api2.max.ru/subscriptions",
                    params={"url": url},
                    headers={"Authorization": MAX_BOT_TOKEN}
                ) as response:

                    body = await response.text()

                    try:
                        result = json.loads(body) if body else {}
                    except Exception:
                        result = {}

                    if response.status == 200 and result.get("success") is True:

                        results.append(
                            "✅ Удалена:\n" + url
                        )

                    else:

                        results.append(
                            "❌ Ошибка удаления:\n"
                            + url
                            + "\nHTTP: "
                            + str(response.status)
                            + "\nОтвет: "
                            + body
                        )

                        break

        # Повторная проверка
        remaining = await get_max_subscriptions()

        remaining_urls = [
            item.get("url")
            for item in remaining
        ]

        message = (
            "РЕЗУЛЬТАТ ОЧИСТКИ\n\n"
            + "\n\n".join(results)
            + "\n\nОСТАВШИЕСЯ ПОДПИСКИ:\n"
            + "\n".join(remaining_urls)
        )

        await max_client.send_message(user_id, message)

    except Exception as e:

        logging.exception("SUBSCRIPTION CLEANUP ERROR")

        await max_client.send_message(
            user_id,
            "❌ Ошибка очистки подписок:\n" + str(e)
        )


# ================= ЗАПУСК =================

print("=== STARTING BOT ===")
print(f"MAX_BOT_TOKEN set: {bool(MAX_BOT_TOKEN)}")
print(f"ADMIN_USER_ID: {ADMIN_USER_ID}")
print(f"WEBHOOK_URL: {WEBHOOK_URL}")
print(f"PORT: {PORT}")


# ================= ОБРАБОТКА СОБЫТИЙ =================

async def handle_update(data):

    try:

        update_type = data.get("update_type")

        user_id = None

        if "user" in data and data["user"]:
            user_id = data["user"].get("user_id")

        elif "message" in data and data["message"].get("sender"):
            user_id = data["message"]["sender"].get("user_id")

        if not user_id:
            return

        if update_type == "bot_started":

            keyboard = [[
                {
                    "type": "request_contact",
                    "text": "📱 Поделиться номером"
                }
            ]]

            await max_client.send_message(
                user_id,
                "Привет! Нажмите кнопку ниже, чтобы поделиться номером телефона, или отправьте номер цифрами.",
                keyboard=keyboard
            )

            return

        if update_type == "message_created":

            message = data.get("message", {})
            body = message.get("body", {})
            text = body.get("text", "")
            attachments = body.get("attachments", [])

            for att in attachments:

                if att.get("type") == "contact":

                    phone_raw = att.get("payload", {}).get(
                        "phone_number",
                        ""
                    )

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

                if user_id != ADMIN_USER_ID and text.startswith("/"):
                    return

                if text == "/sync" and user_id == ADMIN_USER_ID:

                    await sync_command(user_id)
                    return

                if text == "/broadcast" and user_id == ADMIN_USER_ID:

                    await broadcast_command(user_id)
                    return

                if text == "/subscriptions" and user_id == ADMIN_USER_ID:

                    await subscriptions_command(user_id)
                    return

                if text == "/cleanup_subscriptions" and user_id == ADMIN_USER_ID:

                    await cleanup_subscriptions_command(user_id)
                    return

                if text == "/cleanup_subscriptions_confirm" and user_id == ADMIN_USER_ID:

                    await cleanup_subscriptions_command(
                        user_id,
                        confirm=True
                    )

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
                        "Пожалуйста, отправьте номер телефона."
                    )

    except Exception:

        logging.exception("HANDLE UPDATE ERROR")


# ================= WEBHOOK =================

async def webhook_handler(request):

    data = await request.json()

    logging.info(
        f"Received update: {json.dumps(data, ensure_ascii=False)}"
    )

    asyncio.create_task(
        handle_update(data)
    )

    return web.Response(status=200)


# ================= УСТАНОВКА WEBHOOK =================

async def set_webhook():

    if not WEBHOOK_URL:

        logging.error(
            "WEBHOOK_URL пустой! Проверь переменные BotHost"
        )

        return

    headers = {
        "Authorization": MAX_BOT_TOKEN,
        "Content-Type": "application/json"
    }

    payload = {
        "url": WEBHOOK_URL,
        "update_types": [
            "message_created",
            "bot_started"
        ]
    }

    logging.info(f"SETTING WEBHOOK: {WEBHOOK_URL}")

    connector = aiohttp.TCPConnector(ssl=False)

    async with aiohttp.ClientSession(
        connector=connector
    ) as session:

        async with session.post(
            "https://platform-api2.max.ru/subscriptions",
            headers=headers,
            json=payload
        ) as resp:

            response_text = await resp.text()

            if resp.status == 200:

                logging.info("Webhook successfully set")

            else:

                logging.error(
                    f"Webhook error {resp.status}: {response_text}"
                )


# ================= MAIN =================

async def main():

    if not GOOGLE_CREDS_JSON:

        raise Exception("GOOGLE_CREDS пустой")

    init_google_sheets(GOOGLE_CREDS_JSON)

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

    logging.info("BOT STARTED")

    await asyncio.Event().wait()


if __name__ == "__main__":

    asyncio.run(main())

