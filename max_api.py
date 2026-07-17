import aiohttp
import ssl
import certifi

from config import MAX_BOT_TOKEN


class MaxAPIError(Exception):
    pass


class MaxClient:
    def __init__(self):
        self.token = MAX_BOT_TOKEN
        self.base = "https://platform-api2.max.ru"

        self.headers = {
            "Authorization": self.token,
            "Content-Type": "application/json"
        }

        self.ssl_context = ssl.create_default_context(
            cafile=certifi.where()
        )


    async def _request(
        self,
        method: str,
        endpoint: str,
        params: dict = None,
        data: dict = None
    ):
        url = f"{self.base}{endpoint}"

        connector = aiohttp.TCPConnector(
            ssl=self.ssl_context
        )

        async with aiohttp.ClientSession(
            connector=connector
        ) as session:

            async with session.request(
                method,
                url,
                headers=self.headers,
                params=params,
                json=data
            ) as resp:

                if resp.status != 200:
                    text = await resp.text()
                    raise MaxAPIError(
                        f"HTTP {resp.status}: {text}"
                    )

                return await resp.json()


    async def send_message(
        self,
        user_id: int,
        text: str,
        keyboard=None,
        format=None
    ):
        payload = {
            "text": text
        }

        if format:
            payload["format"] = format

        if keyboard:
            payload["attachments"] = [{
                "type": "inline_keyboard",
                "payload": {
                    "buttons": keyboard
                }
            }]

        return await self._request(
            "POST",
            "/messages",
            params={
                "user_id": user_id
            },
            data=payload
        )


    async def send_action(
        self,
        chat_id: int,
        action: str
    ):
        return await self._request(
            "POST",
            f"/chats/{chat_id}/actions",
            data={
                "action": action
            }
        )


    async def get_subscriptions(self):
        return await self._request(
            "GET",
            "/subscriptions"
        )


    async def delete_subscription(
        self,
        url: str
    ):
        return await self._request(
            "DELETE",
            "/subscriptions",
            params={
                "url": url
            }
        )
