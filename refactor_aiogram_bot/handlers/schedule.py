import asyncio

from aiogram import types
from aiogram.filters import Command
from aiogram.types import Message

from . import router
from refactor_aiogram_bot.utils import load_schedule, get_schedule_text, empty_weekday, empty_weekend, pytz, timedelta, datetime, format_name

from refactor_aiogram_bot.utils import save_schedule


@router.message(Command("today"))
async def show_today_schedule(message: Message):
    chat_id = message.chat.id
    today_schedule = load_schedule(chat_id, "today", empty_weekday, empty_weekend)
    text = await get_schedule_text(today_schedule, datetime.now(pytz.timezone('Europe/Kiev')).strftime("%d.%m.%Y"), message.bot)
    await message.reply(text)

@router.message(Command("tomorrow"))
async def show_tomorrow_schedule(message: Message):
    chat_id = message.chat.id
    tomorrow_schedule = load_schedule(chat_id, "tomorrow", empty_weekday, empty_weekend)
    text = await get_schedule_text(tomorrow_schedule, (datetime.now(pytz.timezone('Europe/Kiev')) + timedelta(days=1)).strftime("%d.%m.%Y"), message.bot)
    await message.reply(text)

@router.message(Command("default"))
async def show_default_schedule(message: Message):
    chat_id = message.chat.id
    current_day = datetime.now(pytz.timezone('Europe/Kiev')).weekday()
    if current_day < 5:
        schedule = load_schedule(chat_id, "weekday_default", empty_weekday, empty_weekend)
        text = await get_schedule_text(schedule, "стандартний графік (будній день)", message.bot)
    else:
        schedule = load_schedule(chat_id, "weekend_default", empty_weekday, empty_weekend)
        text = await get_schedule_text(schedule, "стандартний графік (вихідний день)", message.bot)
    await message.reply(text)

@router.message(Command("weekday"))
async def show_weekday_default_schedule(message: Message):
    chat_id = message.chat.id
    schedule = load_schedule(chat_id, "weekday_default", empty_weekday, empty_weekend)
    text = await get_schedule_text(schedule, "стандартний графік (будній день)", message.bot)
    await message.reply(text)

@router.message(Command("weekend"))
async def show_weekend_default_schedule(message: Message):
    chat_id = message.chat.id
    schedule = load_schedule(chat_id, "weekend_default", empty_weekend, empty_weekend)
    text = await get_schedule_text(schedule, "стандартний графік (вихідний день)", message.bot)
    await message.reply(text)

@router.message()
async def edit_schedule(message: Message):
    message_text = message.text.strip()
    chat_id = message.chat.id

    if not (message_text.startswith('+') or message_text.startswith('-')):
        return
    if not message.reply_to_message:
        return

    user_id = message.from_user.id
    user_name = message.from_user.first_name or message.from_user.username

    reply_text = message.reply_to_message.text

    if "Графік роботи Адміністраторів на стандартний графік (будній день)" in reply_text:
        schedule = load_schedule(chat_id, "weekday_default", empty_weekday, empty_weekend)
        schedule_type = "weekday_default"
    elif "Графік роботи Адміністраторів на стандартний графік (вихідний день)" in reply_text:
        schedule = load_schedule(chat_id, "weekend_default", empty_weekday, empty_weekend)
        schedule_type = "weekend_default"
    elif "Графік роботи Адміністраторів на " in reply_text:
        schedule_date = message.reply_to_message.text.split('на ')[1].strip().split()[0]
        current_date = datetime.now(pytz.timezone('Europe/Kiev')).strftime("%d.%m.%Y")
        tomorrow_date = (datetime.now(pytz.timezone('Europe/Kiev')) + timedelta(days=1)).strftime("%d.%m.%Y")

        if schedule_date == current_date:
            schedule = load_schedule(chat_id, "today", empty_weekday, empty_weekend)
            schedule_type = "today"
        elif schedule_date == tomorrow_date:
            schedule = load_schedule(chat_id, "tomorrow", empty_weekday, empty_weekend)
            schedule_type = "tomorrow"
        else:
            return
    else:
        return

    operation = 'remove' if message_text[0] == '-' else 'add'
    hours_range = message_text[1:].strip()

    updated_hours = []
    if '-' in hours_range:
        try:
            start_hour, end_hour = map(int, hours_range.split('-'))

            if start_hour < 0:
                start_hour += 24
            if end_hour < 0:
                end_hour += 24

            if start_hour < 0 or end_hour > 24 or start_hour >= end_hour:
                await message.reply("Будь ласка, введіть правильний час (9-24).\n ")
                return

            for hour in range(start_hour, end_hour):
                if hour == 23:
                    time_slot = f"{hour:02d}:00 - 00:00"
                else:
                    time_slot = f"{hour:02d}:00 - {hour + 1:02d}:00"

                if operation == 'add':
                    if user_id not in schedule[time_slot]:
                        schedule[time_slot].append(user_id)
                        updated_hours.append(time_slot)
                elif operation == 'remove':
                    if user_id in schedule[time_slot]:
                        schedule[time_slot].remove(user_id)
                        updated_hours.append(time_slot)
        except ValueError:
            await message.reply("Будь ласка, введіть правильний час (9-24).")
            return
    else:
        try:
            hour = int(hours_range)

            if hour < 0:
                hour += 24

            if hour == 24:
                hour = 0

            time_slot = f"{hour:02d}:00 - {hour + 1:02d}:00"

            if hour == 23:
                time_slot = f"{hour:02d}:00 - 00:00"

            if operation == 'add':
                if user_id not in schedule[time_slot]:
                    schedule[time_slot].append(user_id)
                    updated_hours.append(time_slot)
            elif operation == 'remove':
                if user_id in schedule[time_slot]:
                    schedule[time_slot].remove(user_id)
                    updated_hours.append(time_slot)
        except ValueError:
            await message.reply("Будь ласка, введіть правильний час (9-24).")
            return

    save_schedule(chat_id, schedule_type, schedule)

    if operation == 'add':
        if updated_hours:
            start_time = updated_hours[0].split('-')[0]
            end_time = updated_hours[-1].split('-')[1]
            response_message = f"{user_name} було додано до графіка на {start_time} - {end_time}."
        else:
            response_message = "Не вдалося додати години."
    else:
        if updated_hours:
            start_time = updated_hours[0].split('-')[0]
            end_time = updated_hours[-1].split('-')[1]
            response_message = f"{user_name} було видалено з графіка на {start_time} - {end_time}."
        else:
            response_message = "Не вдалося видалити години."

    # Set the correct date label
    if schedule_type == "today":
        date_label = datetime.now(pytz.timezone('Europe/Kiev')).strftime("%d.%m.%Y")
    elif schedule_type == "tomorrow":
        date_label = (datetime.now(pytz.timezone('Europe/Kiev')) + timedelta(days=1)).strftime("%d.%m.%Y")
    elif schedule_type == "weekday_default":
        date_label = "стандартний графік (будній день)"
    elif schedule_type == "weekend_default":
        date_label = "стандартний графік (вихідний день)"
    else:
        date_label = "незнайомий графік"

    updated_schedule_message = f"Графік роботи Адміністраторів на {date_label}\n\n"
    for time_slot in schedule:
        users = schedule[time_slot]

        user_name_tasks = [message.bot.get_chat_member(chat_id=message.chat.id, user_id=user) for user in users]

        user_names_results = await asyncio.gather(*user_name_tasks)

        user_names = ' – '.join([format_name(member.user.first_name) for member in user_names_results]) or "–"
        updated_schedule_message += f"{time_slot}: {user_names}\n"

    try:
        await message.reply_to_message.edit_text(updated_schedule_message + '\n' + response_message)
    except Exception as e:
        await message.reply("Не вдалося редагувати повідомлення. Спробуйте ще раз.")
        print(e)
