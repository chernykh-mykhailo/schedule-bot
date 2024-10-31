# -*- coding: utf-8 -*-
# from aiogram import types
from aiogram.filters import Command
from aiogram.types import Message

from . import router
from refactor_aiogram_bot.utils import update_schedules
from refactor_aiogram_bot.config import ADMIN_IDS

@router.message(Command("update"))
async def mechanical_update_schedules(message: Message):
    user_id = message.from_user.id

    if user_id not in ADMIN_IDS:
        await message.reply("У вас немає прав доступу до цієї команди.")
        return

    await message.reply("Графік змінено", update_schedules())
