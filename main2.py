from urllib import parse
from urllib.request import getproxies
import os
from pyrogram import Client
import asyncio

# 允许嵌套事件循环
task = [
    (820670338, "/checkin"),
    (745814644, "/checkin"),
    (6042960290, '/sign'),
    # (7780250809, '/sign'),
    # (871838903, '🎲'),
    # (6005833864, "/sign"),
]


def get_api_config():
    api_id = int(os.environ.get("TG_API_ID", 611335))
    api_hash = os.environ.get("TG_API_HASH", "d524b414d21f4d37f08684c1df41ac9c")
    return api_id, api_hash


async def main():
    api_id, api_hash = get_api_config()
    async with Client("my_account", api_id, api_hash) as app:
        async for chat in app.get_dialogs():
            print(chat.chat.id, chat.chat.first_name)
        for id, text in task:
            await app.send_message(id, text)
            print(f"Send {text} to {id}")
        await app.send_dice(871838903, emoji="🎲")


asyncio.run(main())
