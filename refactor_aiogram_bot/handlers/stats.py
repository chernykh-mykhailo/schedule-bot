from aiogram import types
from aiogram.filters import Command
from aiogram.types import Message

from . import router
from refactor_aiogram_bot.utils import load_statistics

@router.message(Command("stat"))
async def stat(message: Message):
    chat_id = message.chat.id
    chat_stats = load_statistics(chat_id)

    text = "Статистика чату:\n"
    for user_id, stats in chat_stats.items():
        try:
            chat = await message.bot.get_chat(user_id)
            user_name = chat.first_name or "unknown"
        except Exception:
            user_name = "unknown"

        text += f"{user_name}: {stats.get('total', 0)} годин\n"

    await message.reply(text)

@router.message(Command("mystat"))
async def mystat(message: Message):
    chat_id = message.chat.id
    user_id = str(message.from_user.id)
    chat_stats = load_statistics(chat_id)

    if user_id not in chat_stats:
        await message.reply("У вас немає статистики.")
        return

    user_stats = chat_stats[user_id]
    total_hours = user_stats.get('total', 0)
    daily_stats = user_stats.get('daily', {})

    text = f"Ваша статистика:\nЗагалом: {total_hours} годин\n\n"
    text += "Статистика по дням тижня:\n"

    days = ["Понеділок", "Вівторок", "Середа", "Четвер", "П'ятниця", "Субота", "Неділя"]
    for i, day in enumerate(days):
        text += f"{day}: {daily_stats.get(str(i), 0)} годин\n"

    await message.reply(text)
