from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from config import TELEGRAM_TOKEN
from handlers import router
from scheduler import start_scheduler


class MyBot:
    def __init__(self):
        self.bot = Bot(token=TELEGRAM_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        self.dp = Dispatcher()
        self.dp.include_router(router)

    async def set_commands(self):
        commands = [
            BotCommand(command="start", description="Start the bot"),
            BotCommand(command="help", description="Get help"),
            BotCommand(command="today", description="Show today's schedule"),
            BotCommand(command="tomorrow", description="Show tomorrow's schedule"),
            BotCommand(command="default", description="Show default schedule"),
            BotCommand(command="weekday", description="Show weekday default schedule"),
            BotCommand(command="weekend", description="Show weekend default schedule"),
            BotCommand(command="update", description="Update schedules"),
            BotCommand(command="leavethisgroup", description="Leave this group"),
            BotCommand(command="leave", description="Leave"),
            BotCommand(command="stat", description="Show chat statistics"),
            BotCommand(command="mystat", description="Show my statistics"),
        ]
        await self.bot.set_my_commands(commands)

    async def start_polling(self):
        await self.set_commands()
        start_scheduler()
        await self.dp.start_polling(self.bot)
