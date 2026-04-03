import aiohttp
from config import MAX_BOT_TOKEN

class MaxAPIError(Exception):
    pass

class MaxClient:
    def __init__(self):
        self.token = MAX_BOT_TOKEN
        self.base = "https://platform-api.max.ru"
        self.headers = {
            "Authorization": self.token,
            "Content-Type": "application/json"
        }

    async def _request(self, method: str, endpoint: str, params: dict = None, data: dict = None):
        url = f"{self.base}{endpoint}"
        async with aiohttp.ClientSession() as session:
            async with session.request(method, url, headers=self.headers, params=params, json=data) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise MaxAPIError(f"HTTP {resp.status}: {text}")
                return await resp.json()

    async def send_message(self, user_id: int, text: str, keyboard=None, format=None):
        payload = {"text": text}
        if format:
            payload["format"] = format
        if keyboard:
            payload["attachments"] = [{
                "type": "inline_keyboard",
                "payload": {"buttons": keyboard}
            }]
        return await self._request("POST", "/messages", params={"user_id": user_id}, data=payload)

    async def send_action(self, chat_id: int, action: str):
        # action: typing_on, sending_photo, mark_seen и др.
        return await self._request("POST", f"/chats/{chat_id}/actions", data={"action": action})
