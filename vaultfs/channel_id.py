from telethon import TelegramClient

api_id = 38873532
api_hash = "37b6d9f4256b70377d9438a8418b16c1"

client = TelegramClient("vault_session", api_id, api_hash)


async def main():
    async for dialog in client.iter_dialogs():
        if dialog.is_channel:
            print(dialog.name, dialog.id)


with client:
    client.loop.run_until_complete(main())
