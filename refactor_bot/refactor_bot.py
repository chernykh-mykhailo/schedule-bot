# refactor_bot.py
import logging
import os
import signal
import sys
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram import Router
from config import TELEGRAM_TOKEN, LOCK_FILE
from handlers import register_handlers

logging.basicConfig(level=logging.INFO)

class BotApp:
    def __init__(self):
        self.bot = Bot(token=TELEGRAM_TOKEN)
        self.storage = MemoryStorage()
        self.dp = Dispatcher(storage=self.storage)
        self.router = Router()
        register_handlers(self.router)
        self.dp.include_router(self.router)

    def create_lock(self):
        if os.path.exists(LOCK_FILE):
            print("Bot is already running. Removing the lock file and restarting.")
            os.remove(LOCK_FILE)
        with open(LOCK_FILE, 'w') as f:
            f.write(str(os.getpid()))

    def remove_lock(self):
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)

    def signal_handler(self, sig, frame):
        self.remove_lock()
        sys.exit(0)

    async def run(self):
        signal.signal(signal.SIGINT, self.signal_handler)
        self.create_lock()
        await self.dp.start_polling(self.bot)
        self.remove_lock()

if __name__ == "__main__":
    app = BotApp()
    asyncio.run(app.run())
