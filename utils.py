import asyncio
from aiogram.types import Message


async def delete_after(
    messages: Message | list[Message],
    delay: float
):
    async def delete():
        await asyncio.sleep(delay)

        if isinstance(messages, Message):
            messages_to_delete = [messages]
        else:
            messages_to_delete = messages

        for message in messages_to_delete:
            try:
                await message.delete()
            except Exception:
                pass

    asyncio.create_task(delete())
