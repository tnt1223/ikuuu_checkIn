from urllib import parse
from urllib.request import getproxies
import os
from pyrogram import Client 
import asyncio
# 允许嵌套事件循环

task = [(820670338,'/checkin'),
        ]


def get_api_config():
    api_id = int(os.environ.get("TG_API_ID", 611335))
    api_hash = os.environ.get("TG_API_HASH", "d524b414d21f4d37f08684c1df41ac9c")
    return api_id, api_hash

async def main():
    api_id, api_hash = get_api_config()
    async with Client("my_account", api_id, api_hash) as app:
        for id,text in task:
            await app.send_message(id, text)
            print(f"Send {text} to {id}")
        



asyncio.run(main())
