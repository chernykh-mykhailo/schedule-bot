# handlers.py
from aiogram import Router, types
from aiogram.filters import Command
from utils import format_name, get_schedule_text, load_schedule
from datetime import datetime, timedelta
import pytz

schedule_manager = load_schedule()

async def start_command(message: types.Message):
    await message.reply("Вітаємо! Використовуйте команди /today для сьогоднішнього графіка, /tomorrow для завтрашнього, та /default для стандартного графіка.")

async def show_today_schedule(message: types.Message):
    chat_id = message.chat.id
    today_schedule = schedule_manager.load_schedule(chat_id, "today")
    kyiv_tz = pytz.timezone('Europe/Kiev')
    today_date = datetime.now(kyiv_tz).strftime("%d-%m-%Y")
    text = await get_schedule_text(today_schedule, f"сьогодні ({today_date})", message.bot)
    await message.reply(text)

async def show_tomorrow_schedule(message: types.Message):
    chat_id = message.chat.id
    tomorrow_schedule = schedule_manager.load_schedule(chat_id, "tomorrow")
    kyiv_tz = pytz.timezone('Europe/Kiev')
    tomorrow_date = (datetime.now(kyiv_tz) + timedelta(days=1)).strftime("%d-%m-%Y")
    text = await get_schedule_text(tomorrow_schedule, f"завтра ({tomorrow_date})", message.bot)
    await message.reply(text)

async def show_default_schedule(message: types.Message):
    chat_id = message.chat.id
    today = datetime.now(pytz.timezone('Europe/Kiev')).weekday()
    if today < 5:
        schedule = schedule_manager.load_schedule(chat_id, "weekday_default")
        text = await get_schedule_text(schedule, "стандартний графік (будній день)", message.bot)
    else:
        schedule = schedule_manager.load_schedule(chat_id, "weekend_default")
        text = await get_schedule_text(schedule, "стандартний графік (вихідний день)", message.bot)
    await message.reply(text)

def register_handlers(router: Router):
    router.message.register(start_command, Command(commands=["start"]))
    router.message.register(show_today_schedule, Command(commands=["today"]))
    router.message.register(show_tomorrow_schedule, Command(commands=["tomorrow"]))
    router.message.register(show_default_schedule, Command(commands=["default"]))
