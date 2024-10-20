import random
import emoji
import sys
import re
import asyncio
import copy
import json
import logging
import os
import threading
import time
import signal
from datetime import datetime, timedelta

import pytz
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.error import BadRequest
from apscheduler.schedulers.background import BackgroundScheduler

from responses import responses_easy, responses_username

# Додаємо шлях до секретного файлу у Python шлях (для хостингу)
sys.path.append('/etc/secrets')

from config import TELEGRAM_TOKEN  # Імпорт токену з конфігураційного файлу
from config import ADMIN_IDS  # Імпорт списку з айдішками адмінів

LOCK_FILE = 'bot.lock'


def create_lock():
    if os.path.exists(LOCK_FILE):
        print("Bot is already running.")
        sys.exit()
    else:
        with open(LOCK_FILE, 'w') as f:
            f.write(str(os.getpid()))


def remove_lock():
    if os.path.exists(LOCK_FILE):
        os.remove(LOCK_FILE)


def signal_handler(sig, frame):
    remove_lock()
    sys.exit(0)


def keep_alive():
    while True:
        print("Bot is still running...")
        time.sleep(1800)  # 1800 секунд = 30 хвилин


def remove_emoji(text):
    return emoji.replace_emoji(text, replace='')


def format_name(name):
    first_emoji = ''
    for c in name:
        if emoji.is_emoji(c):
            first_emoji = c
            break

    clean_name = remove_emoji(name).strip()

    if '(' in clean_name:
        match = re.search(r'[^()]*\)', clean_name)
        if match:
            clean_name = clean_name[:match.end()].strip()
    else:
        match = re.search(r'([^ ]+)', clean_name)
        if match:
            clean_name = match.group(1).strip()

    return f"{first_emoji}{clean_name}".strip() if first_emoji else clean_name.strip()


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# Імена файлів для графіків
SCHEDULES_DIR = "schedules"
if not os.path.exists(SCHEDULES_DIR):
    os.makedirs(SCHEDULES_DIR)


def get_schedule_file_name(chat_id, schedule_type):
    return os.path.join(SCHEDULES_DIR, f"{chat_id}_{schedule_type}.json")


def load_schedule(chat_id, schedule_type, weekday_default, weekend_default):
    file_name = get_schedule_file_name(chat_id, schedule_type)
    if os.path.exists(file_name):
        with open(file_name, 'r', encoding='utf-8') as f:
            return json.load(f)
    else:
        kyiv_tz = pytz.timezone('Europe/Kiev')
        today = datetime.now(kyiv_tz).weekday()
        if today < 5:
            schedule = weekday_default
        else:
            schedule = weekend_default

        with open(file_name, 'w', encoding='utf-8') as f:
            json.dump(schedule, f, ensure_ascii=False, indent=4)
        return schedule


def save_schedule(chat_id, schedule_type, schedule):
    file_name = get_schedule_file_name(chat_id, schedule_type)
    try:
        with open(file_name, 'w', encoding='utf-8') as f:
            json.dump(schedule, f, ensure_ascii=False, indent=4)
        logging.info(f"Schedule saved successfully: {file_name}")
    except Exception as e:
        logging.error(f"Failed to save schedule: {file_name}, Error: {e}")


empty_weekday = {
    "15:00 - 16:00": [],
    "16:00 - 17:00": [],
    "17:00 - 18:00": [],
    "18:00 - 19:00": [],
    "19:00 - 20:00": [],
    "20:00 - 21:00": [],
    "21:00 - 22:00": [],
    "22:00 - 23:00": [],
    "23:00 - 00:00": [],
    "00:00 - 01:00": []
}

empty_weekend = {
    "09:00 - 10:00": [],
    "10:00 - 11:00": [],
    "11:00 - 12:00": [],
    "12:00 - 13:00": [],
    "13:00 - 14:00": [],
    "14:00 - 15:00": [],
    "15:00 - 16:00": [],
    "16:00 - 17:00": [],
    "17:00 - 18:00": [],
    "18:00 - 19:00": [],
    "19:00 - 20:00": [],
    "20:00 - 21:00": [],
    "21:00 - 22:00": [],
    "22:00 - 23:00": [],
    "23:00 - 00:00": [],
    "00:00 - 01:00": []
}


def is_weekend(date):
    return date.weekday() in (5, 6)


STATS_DIR = "stats"
SCHEDULES_DIR = "schedules"

# Create directory for statistics if not exists
if not os.path.exists(STATS_DIR):
    os.makedirs(STATS_DIR)


def get_stats_file_name(chat_id):
    return os.path.join(STATS_DIR, f"{chat_id}.json")


def load_statistics(chat_id):
    file_name = get_stats_file_name(chat_id)
    if os.path.exists(file_name):
        try:
            with open(file_name, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Error loading statistics from {file_name}: {e}")
            return {}
    else:
        return {}


def save_statistics(chat_id, stats):
    file_name = get_stats_file_name(chat_id)
    try:
        with open(file_name, 'w', encoding='utf-8') as f:
            json.dump(stats, f, ensure_ascii=False, indent=4)
        logging.info(f"Statistics saved successfully: {file_name}")
    except Exception as e:
        logging.error(f"Failed to save statistics: {file_name}, Error: {e}")


async def stat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    chat_stats = load_statistics(chat_id)

    text = "Статистика чату:\n"
    for user_id, stats in chat_stats.items():
        try:
            chat = await context.bot.get_chat(user_id)
            user_name = chat.first_name or "unknown"
        except BadRequest:
            user_name = "unknown"

        text += f"{user_name}: {stats.get('total', 0)} годин\n"

    await update.message.reply_text(text)


async def mystat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    user_id = str(update.effective_user.id)  # Ensure user_id is string
    chat_stats = load_statistics(chat_id)

    if user_id not in chat_stats:
        await update.message.reply_text("У вас немає статистики.")
        return

    user_stats = chat_stats[user_id]
    total_hours = user_stats.get('total', 0)
    daily_stats = user_stats.get('daily', {})

    text = f"Ваша статистика:\nЗагалом: {total_hours} годин\n\n"
    text += "Статистика по дням тижня:\n"

    # Якщо для дня немає даних, повертається 0 годин
    days = ["Понеділок", "Вівторок", "Середа", "Четвер", "П'ятниця", "Субота", "Неділя"]
    for i, day in enumerate(days):
        # Використовуємо get для отримання значення або 0, якщо не знайдено
        text += f"{day}: {daily_stats.get(str(i), 0)} годин\n"

    await update.message.reply_text(text)


async def your_stat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args
    if not args:
        await stat(update, context)
        return
    user_id = update.effective_user.id

    if user_id not in ADMIN_IDS:
        await update.message.reply_text("У вас немає прав доступу до цієї команди.")
        return

    username = args[0].lstrip('@')
    chat_id = update.effective_chat.id
    chat_stats = load_statistics(chat_id)

    user_id = None
    for user in chat_stats:
        try:
            chat = await context.bot.get_chat(user)
            if chat.username == username:
                user_id = str(user)
                break
        except BadRequest:
            continue

    if not user_id or user_id not in chat_stats:
        await update.message.reply_text(f"У користувача @{username} немає статистики.")
        return

    user_stats = chat_stats[user_id]
    total_hours = user_stats.get('total', 0)
    daily_stats = user_stats.get('daily', {})

    text = f"Статистика користувача @{username}:\nЗагалом: {total_hours} годин\n\n"
    text += "Статистика по дням тижня:\n"

    days = ["Понеділок", "Вівторок", "Середа", "Четвер", "П'ятниця", "Субота", "Неділя"]
    for i, day in enumerate(days):
        text += f"{day}: {daily_stats.get(str(i), 0)} годин\n"

    await update.message.reply_text(text)


def update_schedules():
    kyiv_tz = pytz.timezone('Europe/Kiev')
    today_date = datetime.now(kyiv_tz)
    tomorrow_date = today_date + timedelta(days=1)
    previos_date = today_date - timedelta(days=1)

    for file_name in os.listdir(SCHEDULES_DIR):
        if file_name.endswith("_today.json"):
            chat_id = file_name.split("_")[0]
            today_schedule = load_schedule(chat_id, "today", empty_weekday, empty_weekend)
            tomorrow_schedule = load_schedule(chat_id, "tomorrow", empty_weekday, empty_weekend)

            # Calculate statistics for today's schedule
            today_stats = {}
            for time_slot, user_ids in today_schedule.items():
                for user_id in user_ids:
                    user_id = str(user_id)  # Ensure user_id is string
                    if user_id not in today_stats:
                        today_stats[user_id] = 1
                    else:
                        today_stats[user_id] += 1

            # Load previous statistics for the chat
            chat_stats = load_statistics(chat_id)

            # Update total hours worked for each user
            for user_id, hours in today_stats.items():
                # Initialize user statistics if not already present
                if user_id not in chat_stats:
                    chat_stats[user_id] = {"total": 0, "daily": {}}

                chat_stats[user_id]["total"] += hours

                # Update daily statistics for the user
                weekday = previos_date.weekday()  # Це індекс дня тижня (0 для Понеділка і т.д.)
                daily_stats = chat_stats[user_id].get('daily', {})
                if str(weekday) not in daily_stats:
                    daily_stats[str(weekday)] = hours
                else:
                    daily_stats[str(weekday)] += hours
                chat_stats[user_id]['daily'] = daily_stats

            # Save updated statistics for the chat
            save_statistics(chat_id, chat_stats)

            # Update schedules for today and tomorrow
            today_schedule = copy.deepcopy(tomorrow_schedule)
            if is_weekend(tomorrow_date):
                default_for_tomorrow = load_schedule(chat_id, "weekend_default", empty_weekday, empty_weekend)
            else:
                default_for_tomorrow = load_schedule(chat_id, "weekday_default", empty_weekday, empty_weekend)
            tomorrow_schedule = copy.deepcopy(default_for_tomorrow)

            save_schedule(chat_id, "today", today_schedule)
            save_schedule(chat_id, "tomorrow", tomorrow_schedule)


def process_hours(input_range):
    hours = input_range.split('-')

    if len(hours) != 2:
        return "Будь ласка, введіть правильний час (формат: x-y)."

    try:
        start_hour = int(hours[0]) % 24
        end_hour = int(hours[1]) % 24
    except ValueError:
        return "Будь ласка, введіть правильний час (тільки числа)."

    time_slots = []

    if start_hour <= end_hour:
        for hour in range(start_hour, end_hour + 1):
            next_hour = (hour + 1) % 24
            time_slot = f"{hour:02d}:00 - {next_hour:02d}:00"
            time_slots.append(time_slot)
    else:
        for hour in range(start_hour, 24):
            next_hour = (hour + 1) % 24
            time_slot = f"{hour:02d}:00 - {next_hour:02d}:00"
            time_slots.append(time_slot)
        for hour in range(0, end_hour + 1):
            next_hour = (hour + 1) % 24
            time_slot = f"{hour:02d}:00 - {next_hour:02d}:00"
            time_slots.append(time_slot)

    return time_slots


async def get_schedule_text(schedule, date_label, context):
    text = f"Графік роботи Адміністраторів на {date_label}\n\n"

    for time_slot, user_ids in schedule.items():
        admins = []
        for user_id in user_ids:
            try:
                chat = await context.bot.get_chat(user_id)
                if chat.first_name:
                    admins.append(format_name(chat.first_name))
                else:
                    admins.append("–")
            except BadRequest:
                admins.append("unknown")

        admins_str = ' – '.join(admins) if admins else "–"
        text += f"{time_slot} – {admins_str}\n"

    return text


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    logging.info(f"Starting conversation with user: {user.first_name}")
    await update.message.reply_text(
        "Вітаємо! Використовуйте команди /today для сьогоднішнього графіка, "
        "/tomorrow для завтрашнього, та /default для стандартного графіка.")


async def mechanical_update_schedules(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    if user_id not in ADMIN_IDS:
        await update.message.reply_text("У вас немає прав доступу до цієї команди.")
        return

    await update.message.reply_text("Графік змінено", update_schedules())


async def mechanical_track(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    if user_id not in ADMIN_IDS:
        await update.message.reply_text("У вас немає прав доступу до цієї команди.")
        return

    await update.message.reply_text("Перевірка присутності увімкнена")
    await track_user_presence(context)


async def show_today_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    today_schedule = load_schedule(chat_id, "today", empty_weekday, empty_weekend)
    text = await get_schedule_text(today_schedule, datetime.now(pytz.timezone('Europe/Kiev')).strftime("%d.%m.%Y"),
                                   context)
    await update.message.reply_text(text)


async def show_tomorrow_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    tomorrow_schedule = load_schedule(chat_id, "tomorrow", empty_weekday, empty_weekend)
    text = await get_schedule_text(tomorrow_schedule,
                                   (datetime.now(pytz.timezone('Europe/Kiev')) + timedelta(days=1)).strftime(
                                       "%d.%m.%Y"), context)
    await update.message.reply_text(text)


async def show_default_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    current_day = datetime.now(pytz.timezone('Europe/Kiev')).weekday()
    if current_day < 5:
        schedule = load_schedule(chat_id, "weekday_default", empty_weekday, empty_weekend)
        text = await get_schedule_text(schedule, "стандартний графік (будній день)", context)
    else:
        schedule = load_schedule(chat_id, "weekend_default", empty_weekday, empty_weekend)
        text = await get_schedule_text(schedule, "стандартний графік (вихідний день)", context)
    await update.message.reply_text(text)


async def edit_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message.text.strip()
    chat_id = update.effective_chat.id

    if not (message.startswith('+') or message.startswith('-')):
        return
    if not update.message:
        # If there is no message, return early
        return

    user_id = update.effective_user.id
    user_name = update.effective_user.first_name or update.effective_user.username

    if update.message.reply_to_message:
        reply_text = update.message.reply_to_message.text

        if "Графік роботи Адміністраторів на стандартний графік (будній день)" in reply_text:
            schedule = load_schedule(chat_id, "weekday_default", empty_weekday, empty_weekend)
            schedule_type = "weekday_default"
        elif "Графік роботи Адміністраторів на стандартний графік (вихідний день)" in reply_text:
            schedule = load_schedule(chat_id, "weekend_default", empty_weekday, empty_weekend)
            schedule_type = "weekend_default"
        elif "Графік роботи Адміністраторів на " in reply_text:
            schedule_date = update.message.reply_to_message.text.split('на ')[1].strip().split()[0]
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
    else:
        return

    operation = 'remove' if message[0] == '-' else 'add'
    hours_range = message[1:].strip()

    updated_hours = []
    if '-' in hours_range:
        try:
            start_hour, end_hour = map(int, hours_range.split('-'))

            if start_hour < 0:
                start_hour += 24
            if end_hour < 0:
                end_hour += 24

            if start_hour < 0 or end_hour > 24 or start_hour >= end_hour:
                await update.message.reply_text("Будь ласка, введіть правильний час (9-24).\n ")
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
            await update.message.reply_text("Будь ласка, введіть правильний час (9-24).")
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
            await update.message.reply_text("Будь ласка, введіть правильний час (9-24).")
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

        user_name_tasks = [context.bot.get_chat_member(chat_id=update.effective_chat.id, user_id=user) for user in
                           users]

        user_names_results = await asyncio.gather(*user_name_tasks)

        user_names = ' – '.join([format_name(member.user.first_name) for member in user_names_results]) or "–"
        updated_schedule_message += f"{time_slot}: {user_names}\n"

    try:
        await update.message.reply_to_message.edit_text(updated_schedule_message + '\n' + response_message)
    except Exception as e:
        await update.message.reply_text("Не вдалося редагувати повідомлення. Спробуйте ще раз.")
        print(e)


async def show_weekday_default_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    schedule = load_schedule(chat_id, "weekday_default", empty_weekday, empty_weekday)
    text = await get_schedule_text(schedule, "стандартний графік (будній день)", context)
    await update.message.reply_text(text)


async def show_weekend_default_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    schedule = load_schedule(chat_id, "weekend_default", empty_weekend, empty_weekend)
    text = await get_schedule_text(schedule, "стандартний графік (вихідний день)", context)
    await update.message.reply_text(text)


async def leave(update: Update, context):
    response = random.choice(responses_easy)
    await update.message.reply_text(response)


async def leave_username(update: Update, context):
    username = update.message.from_user.username
    response = random.choice(responses_username).format(username=username)
    await update.message.reply_text(response)


async def find_schedule_message_id(context, chat_id, date_str):
    async for message in context.bot.get_chat_history(chat_id, limit=100):
        if date_str in message.text:
            return message.message_id
    return None


async def track_user_presence(context: ContextTypes.DEFAULT_TYPE):
    kyiv_tz = pytz.timezone('Europe/Kiev')
    today_date = datetime.now(kyiv_tz)
    schedule_files = [f for f in os.listdir(SCHEDULES_DIR) if f.endswith("_today.json")]

    for file_name in schedule_files:
        chat_id = file_name.split("_")[0]
        schedule = load_schedule(chat_id, "today", empty_weekday, empty_weekend)
        schedule_message_id = await find_schedule_message_id(context, chat_id, today_date.strftime("%d.%m.%Y"))

        if not schedule_message_id:
            # Логіка, якщо не знайдено повідомлення
            print("Не знайдено повідомлення з графіком для сьогоднішньої дати")
            return

        now = datetime.now(pytz.timezone('Europe/Kyiv'))
        current_hour = now.strftime('%H:00')

        if current_hour in schedule and schedule[current_hour]:
            scheduled_users = schedule[current_hour]  # Users scheduled for the current hour
            remaining_users = scheduled_users.copy()  # Copy the list of users
            absent_users = []  # List of absent users

            # Get the schedule message for today
            today_schedule_message = await context.bot.get_message(chat_id, schedule_message_id)

            # Check for "here" messages within the first 10 minutes of the hour
            end_time = datetime.now() + timedelta(minutes=10)
            while datetime.now() < end_time:
                for scheduled_user in scheduled_users:
                    def message_filter(message):
                        return message.text.lower() == "тут" and message.from_user.username == scheduled_user

                    try:
                        # Wait for "here" from each user for 1 minute
                        message = await context.bot.wait_for_message(filters=message_filter, timeout=60)
                        if message:
                            # If the user is present, update the schedule
                            updated_text = f"{today_schedule_message.text}\n{scheduled_user} присутній ✅"
                            await context.bot.edit_message_text(
                                chat_id=chat_id,
                                message_id=schedule_message_id,
                                text=updated_text
                            )
                            remaining_users.remove(scheduled_user)
                    except asyncio.TimeoutError:
                        continue

            # Mark absent users
            absent_users = remaining_users
            if absent_users:
                updated_text = f"{today_schedule_message.text}\n" + "\n".join([f"{user} відсутній ❌" for user in absent_users])
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=schedule_message_id,
                    text=updated_text
                )

            # Update the schedule for the current hour
            schedule[current_hour] = remaining_users
            save_schedule(chat_id, "today", schedule)


def main() -> None:
    signal.signal(signal.SIGINT, signal_handler)  # Handle signal
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("today", show_today_schedule))
    app.add_handler(CommandHandler("tomorrow", show_tomorrow_schedule))
    app.add_handler(CommandHandler("default", show_default_schedule))
    app.add_handler(CommandHandler("weekday", show_weekday_default_schedule))
    app.add_handler(CommandHandler("weekend", show_weekend_default_schedule))
    app.add_handler(CommandHandler("update", mechanical_update_schedules))
    app.add_handler(CommandHandler("track", mechanical_track))
    app.add_handler(CommandHandler("leavethisgroup", leave_username))
    app.add_handler(CommandHandler("leave", leave))
    app.add_handler(CommandHandler("stat", stat))
    app.add_handler(CommandHandler("mystat", mystat))
    app.add_handler(CommandHandler("your_stat", your_stat))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, edit_schedule))

    # Create scheduler
    scheduler = BackgroundScheduler()
    kyiv_tz = pytz.timezone('Europe/Kiev')
    scheduler.add_job(update_schedules, 'cron', hour=0, minute=0, timezone=kyiv_tz)
    scheduler.add_job(track_user_presence, 'interval', hours=1, timezone=kyiv_tz, args=[app]) # Track user presence every hour
    scheduler.start()

    # Run keep_alive in a separate thread
    threading.Thread(target=keep_alive, daemon=True).start()

    app.run_polling(poll_interval=1)

if __name__ == "__main__":
    main()