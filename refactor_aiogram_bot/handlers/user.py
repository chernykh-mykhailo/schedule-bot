import random

from aiogram import types
from aiogram.filters import Command
from aiogram.types import Message
import logging
from . import router
from refactor_aiogram_bot.responses import responses_easy, responses_username


@router.message(Command("start"))
async def start(message: Message):
    user = message.from_user
    logging.info(f"Starting conversation with user: {user.first_name}")
    await message.reply(
        "Вітаємо! Використовуйте команди /today для сьогоднішнього графіка, "
        "/tomorrow для завтрашнього, та /default для стандартного графіка.")


@router.message(Command("leave"))
async def leave(message: Message):
    response = random.choice(responses_easy)
    await message.reply(response)


@router.message(Command("leavethisgroup"))
async def leave_username(message: Message):
    username = message.from_user.username
    response = random.choice(responses_username).format(username=username)
    await message.reply(response)
