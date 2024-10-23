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
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, \
    CallbackQueryHandler, CallbackContext
from telegram.error import BadRequest
from apscheduler.schedulers.background import BackgroundScheduler

from responses import responses_easy, responses_username

# Додаємо шлях до секретного файлу у Python шлях (для хостингу)
sys.path.append('/etc/secrets')

from config import TELEGRAM_TOKEN  # Імпорт токену з конфігураційного файлу
from config import ADMIN_IDS  # Імпорт списку з айдішками адмінів

LOCK_FILE = 'bot.lock'

SKINS_DIR = "skins"
SKINS_PER_PAGE = 5

kyiv_tz = pytz.timezone('Europe/Kiev')



# Імена файлів для графіків
SCHEDULES_DIR = "schedules"
if not os.path.exists(SCHEDULES_DIR):
    os.makedirs(SCHEDULES_DIR)

STATS_DIR = "stats"
# Create directory for statistics if not exists
if not os.path.exists(STATS_DIR):
    os.makedirs(STATS_DIR)


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


def get_user_name(stats, chat, user_id):
    return stats.get("name", format_name(chat.first_name) or format_name(chat.last_name) or chat.username)


logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

logger = logging.getLogger(__name__)


def get_schedule_file_name(chat_id, schedule_type):
    return os.path.join(SCHEDULES_DIR, f"{chat_id}_{schedule_type}.json")


def load_schedule(chat_id, schedule_type, weekday_default, weekend_default):
    file_name = get_schedule_file_name(chat_id, schedule_type)
    if os.path.exists(file_name):
        with open(file_name, 'r', encoding='utf-8') as f:
            return json.load(f)
    else:
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
    sorted_schedule = dict(sorted(schedule.items(), key=lambda x: (x[0] == '00:00 - 01:00', x[0])))
    try:
        with open(file_name, 'w', encoding='utf-8') as f:
            json.dump(sorted_schedule, f, ensure_ascii=False, indent=4)
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


def get_stats_file_name(chat_id):
    return os.path.join(STATS_DIR, f"{chat_id}.json")


def load_statistics(chat_id):
    file_name = get_stats_file_name(chat_id)
    if os.path.exists(file_name):
        try:
            with open(file_name, 'r', encoding='utf-8') as f:
                stats = json.load(f)
                # Ensure each user has a currency field
                for user_id, user_stats in stats.items():
                    if 'currency' not in user_stats:
                        user_stats['currency'] = 0
                return stats
        except Exception as e:
            logging.error(f"Error loading statistics from {file_name}: {e}")
            return {}
    else:
        return {}


async def earn(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    user_id = str(update.effective_user.id)
    chat_stats = load_statistics(chat_id)

    if user_id == 1087968824:
        await update.message.reply_text("Анонімні адміністратори не можуть використовувати цю команду.")
        return

    if user_id not in chat_stats:
        chat_stats[user_id] = {"total": 0, "daily": {}, "currency": 0, "name": "", "last_earn": None}

    last_earn = chat_stats[user_id].get("last_earn")
    now = datetime.now(kyiv_tz)

    if last_earn:
        last_earn_date = datetime.strptime(last_earn, "%Y-%m-%d %H:%M:%S").astimezone(kyiv_tz).date()
        if last_earn_date == now.date():
            next_earn_time = datetime.combine(now.date() + timedelta(days=1), datetime.min.time(), kyiv_tz)
            remaining_time = next_earn_time - now
            hours, remainder = divmod(remaining_time.seconds, 3600)
            minutes, _ = divmod(remainder, 60)
            await update.message.reply_text(f"Ви вже заробили сяйво✨ сьогодні. Спробуйте знову через {hours} годин і {minutes} хвилин.")
            return


    # Calculate the total hours worked yesterday
    yesterday = (now - timedelta(days=1)).weekday()
    hours_worked_yesterday = chat_stats[user_id]["daily"].get(str(yesterday), 0)

    # Introduce randomness in the currency awarded
    random_multiplier = random.uniform(0.7, 1.5)
    earned_currency = int(hours_worked_yesterday * 10 * random_multiplier)
    chat_stats[user_id]["currency"] += earned_currency
    chat_stats[user_id]["last_earn"] = now.strftime("%Y-%m-%d %H:%M:%S")

    save_statistics(chat_id, chat_stats)
    await update.message.reply_text(f"Ви заробили {earned_currency} сяйва✨ за {hours_worked_yesterday} годин роботи вчора. Загальний баланс: {chat_stats[user_id]['currency']} сяйва✨.")


async def add_money_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    # Check if the user is an admin
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("У вас немає прав доступу до цієї команди.")
        return

    # Check if the correct number of arguments is provided
    if len(context.args) != 2:
        await update.message.reply_text("Будь ласка, використовуйте формат: /add_money @username <amount>")
        return

    target_username = context.args[0].lstrip('@')
    try:
        amount = int(context.args[1])
    except ValueError:
        await update.message.reply_text("Будь ласка, введіть правильну кількість сяйва✨.")
        return

    chat_id = update.effective_chat.id
    chat_stats = load_statistics(chat_id)

    # Find the target user ID by username
    target_user_id = None
    for user in chat_stats:
        try:
            chat = await context.bot.get_chat(user)
            if chat.username == target_username:
                target_user_id = user
                break
        except BadRequest:
            continue

    if not target_user_id:
        await update.message.reply_text(f"Користувача з ім'ям @{target_username} не знайдено.")
        return

    if target_user_id not in chat_stats:
        chat_stats[target_user_id] = {"total": 0, "daily": {}, "currency": 0, "name": "", "last_earn": None}

    chat_stats[target_user_id]["currency"] += amount
    save_statistics(chat_id, chat_stats)

    await update.message.reply_text(f"Користувачу @{target_username} було додано {amount} сяйва✨. Новий баланс: {chat_stats[target_user_id]['currency']} сяйва✨.")


async def set_money_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    # Check if the user is an admin
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("У вас немає прав доступу до цієї команди.")
        return

    # Check if the correct number of arguments is provided
    if len(context.args) != 2:
        await update.message.reply_text("Будь ласка, використовуйте формат: /setmoney @username <amount>")
        return

    target_username = context.args[0].lstrip('@')
    try:
        amount = int(context.args[1])
    except ValueError:
        await update.message.reply_text("Будь ласка, введіть правильну кількість сяйва✨.")
        return

    chat_id = update.effective_chat.id
    chat_stats = load_statistics(chat_id)

    # Find the target user ID by username
    target_user_id = None
    for user in chat_stats:
        try:
            chat = await context.bot.get_chat(user)
            if chat.username == target_username:
                target_user_id = user
                break
        except BadRequest:
            continue

    if not target_user_id:
        await update.message.reply_text(f"Користувача з ім'ям @{target_username} не знайдено.")
        return

    if target_user_id not in chat_stats:
        chat_stats[target_user_id] = {"total": 0, "daily": {}, "currency": 0, "name": "", "last_earn": None}

    chat_stats[target_user_id]["currency"] = amount
    save_statistics(chat_id, chat_stats)

    await update.message.reply_text(f"Користувачу @{target_username} було встановлено {amount} сяйва✨. Новий баланс: {chat_stats[target_user_id]['currency']} сяйва✨.")


async def set_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    user_id = str(update.effective_user.id)
    chat_stats = load_statistics(chat_id)

    if user_id not in chat_stats:
        chat_stats[user_id] = {"total": 0, "daily": {}, "currency": 0, "name": ""}

    if context.args:
        custom_name = ' '.join(context.args)

        # Check if the name is not longer than 20 characters
        if len(custom_name) > 20:
            await update.message.reply_text("Ім'я не повинно бути довше за 20 символів.")
            return

        if len(custom_name) < 3:
            await update.message.reply_text("Ім'я не повинно бути меншим за 3 символи.")
            return

        # Check if the name does not contain spaces
        if ' ' in custom_name:
            await update.message.reply_text("Ім'я не повинно містити пробілів.")
            return

        # Check if the name is unique
        for user_stats in chat_stats.values():
            if user_stats.get("name") == custom_name:
                await update.message.reply_text("Це ім'я вже використовується іншим користувачем.")
                return

        # Check if the user has enough currency
        if chat_stats[user_id]["currency"] < 100:
            await update.message.reply_text(f"Недостатньо грошей, ваш баланс: {chat_stats[user_id]['currency']} сяйва✨.")
            return

        # Deduct 100 currency units
        chat_stats[user_id]["currency"] -= 100
        chat_stats[user_id]["name"] = custom_name
        save_statistics(chat_id, chat_stats)
        await update.message.reply_text(f"Ваше ім'я було змінено на {custom_name}. Ваш новий баланс: {chat_stats[user_id]['currency']} сяйва✨.")
    else:
        await update.message.reply_text("Будь ласка, введіть ім'я після команди /setname.")


def list_skins():
    skins = []
    try:
        for file_name in os.listdir(SKINS_DIR):
            if file_name.endswith(('.png', '.jpg', '.jpeg')):
                skins.append(file_name)
        logger.info(f"Знайдено скіни: {skins}")
    except Exception as e:
        logger.error(f"Помилка при завантаженні скінів: {e}")
    return skins


def get_skin_page(page_number):
    skins = list_skins()
    start_index = page_number * SKINS_PER_PAGE
    end_index = start_index + SKINS_PER_PAGE
    return skins[start_index:end_index], len(skins)


async def shop_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    page_number = int(context.args[0]) if context.args else 0
    skins, total_skins = get_skin_page(page_number)
    total_pages = (total_skins + SKINS_PER_PAGE - 1) // SKINS_PER_PAGE

    text = "Available skins:\n"
    for skin in skins:
        text += f"`{skin}` - 100 сяйва \n"

    text += "\nUse `/buy_skin ` *<skin_name>* to purchase a skin.\n"
    text += "\nUse `/preview_skin ` *<skin_name>* to preview.\n"

    if page_number > 0:
        text += f"`/shop {page_number - 1}` - Previous\n"
    if page_number < total_pages - 1:
        text += f"`/shop {page_number + 1}` - Next\n"

    await update.message.reply_text(text, parse_mode='Markdown')


async def buy_skin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    user_id = str(update.effective_user.id)
    chat_stats = load_statistics(chat_id)
    skin_name = context.args[0] if context.args else None

    if not skin_name:
        await update.message.reply_text("Будь ласка, вкажіть назву скіна.")
        return

    if user_id not in chat_stats:
        await update.message.reply_text("Ваша статистика не знайдена.")
        return

    available_skins = list_skins()
    if skin_name not in available_skins:
        await update.message.reply_text("Скін не знайдено. Будь ласка, виберіть інший скін.")
        return

        # Deduct currency and assign the new skin
        # Check if the user has enough currency
    if chat_stats[user_id]["currency"] < 100:
        await update.message.reply_text(f"Недостатньо грошей, ваш баланс: {chat_stats[user_id]['currency']} сяйва✨.")
        return

        # Deduct 100 currency units
    user_stats = chat_stats[user_id]
    if "skin" in user_stats and user_stats["skin"] == skin_name:
        await update.message.reply_text("У вас вже є цей скин.")
        return
    # Add logic to handle the purchase of the skin
    # For example, deduct currency and assign the new skin
    user_stats["currency"] -= 100
    user_stats["skin"] = skin_name
    save_statistics(chat_id, chat_stats)

    await update.message.reply_text(f"Ви успішно придбали скин: {skin_name}. Ваш новий баланс: {chat_stats[user_id]['currency']} сяйва✨.")

async def preview_skin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Use `/preview_skin ` *<skin_name>* for preview")
        return

    skin_name = ' '.join(context.args)
    skin_image_path = os.path.join(SKINS_DIR, f"{skin_name}")

    if os.path.exists(skin_image_path):
        await update.message.reply_photo(photo=open(skin_image_path, 'rb'), caption=f"Прев'ю скіна: {skin_name}")
    else:
        await update.message.reply_text(f"Скін з назвою `{skin_name}` не знайдено.", parse_mode='Markdown')

async def set_skin_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    # Check if the user is an admin
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("У вас немає прав доступу до цієї команди.")
        return

    # Check if the correct number of arguments is provided
    if len(context.args) != 1:
        await update.message.reply_text("Будь ласка, використовуйте формат: /set_skin @username <skin_name>")
        return

    skin_name = context.args[0]
    available_skins = list_skins()
    if skin_name not in available_skins:
        await update.message.reply_text("Скін не знайдено. Будь ласка, виберіть інший скін.")
        return
    target_username = None

    # Determine the target user
    if context.args[0].startswith('@'):
        target_username = context.args[0].lstrip('@')
        target_user_id = None
        chat_id = update.effective_chat.id
        chat_stats = load_statistics(chat_id)

        for user in chat_stats:
            try:
                chat = await context.bot.get_chat(user)
                if chat.username == target_username:
                    target_user_id = user
                    break
            except BadRequest:
                continue

        if not target_user_id:
            await update.message.reply_text(f"Користувача з ім'ям @{target_username} не знайдено.")
            return
    elif update.message.reply_to_message:
        target_user_id = str(update.message.reply_to_message.from_user.id)
        target_username = update.message.reply_to_message.from_user.username
    else:
        await update.message.reply_text("Будь ласка, вкажіть ім'я користувача або відповідайте на повідомлення користувача.")
        return

    chat_id = update.effective_chat.id
    chat_stats = load_statistics(chat_id)

    if target_user_id not in chat_stats:
        chat_stats[target_user_id] = {"total": 0, "daily": {}, "currency": 0, "name": "", "last_earn": None}

    chat_stats[target_user_id]["skin"] = skin_name
    save_statistics(chat_id, chat_stats)

    await update.message.reply_text(f"Користувачу @{target_username} було встановлено скин: {skin_name}.")


def save_statistics(chat_id, stats):
    file_name = get_stats_file_name(chat_id)
    try:
        with open(file_name, 'w', encoding='utf-8') as f:
            json.dump(stats, f, ensure_ascii=False, indent=4)
        logging.info(f"Statistics saved successfully: {file_name}")
    except Exception as e:
        logging.error(f"Failed to save statistics: {file_name}, Error: {e}")


async def all_stat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    chat_stats = load_statistics(chat_id)

    user_stats_summary = {}

    for user_id, stats in chat_stats.items():
        try:
            chat = await context.bot.get_chat(user_id)
            user_name = get_user_name(stats, chat, user_id)
            # Update the name in the statistics if it has changed
        except BadRequest:
            user_name = f"unknown: {user_id}"

        if user_name not in user_stats_summary:
            user_stats_summary[user_name] = 0
        user_stats_summary[user_name] += stats.get('total', 0)

    text = "Статистика чату:\n"
    for user_name, total_hours in user_stats_summary.items():
        text += f"{user_name}: {total_hours} годин\n"

    await update.message.reply_text(text)


async def my_stat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    user_id = str(update.effective_user.id)
    chat_stats = load_statistics(chat_id)

    if user_id not in chat_stats:
        await update.message.reply_text("У вас немає статистики.")
        return

    user_stats = chat_stats[user_id]
    total_hours = user_stats.get('total', 0)
    daily_stats = user_stats.get('daily', {})
    balance = user_stats.get('currency', 0)
    skin = user_stats.get('skin', None)

    text = f"Ваша статистика:\nЗагалом: {total_hours} годин\nБаланс: {balance} сяйва✨\n\n"
    text += "Статистика по дням тижня:\n"

    days = ["Понеділок", "Вівторок", "Середа", "Четвер", "П'ятниця", "Субота", "Неділя"]
    for i, day in enumerate(days):
        hours = daily_stats.get(str(i), 0)
        if hours > 0:
            text += f"{day}: {hours} годин\n"

    if skin:
        skin_path = os.path.join(SKINS_DIR, skin)
        await update.message.reply_photo(photo=open(skin_path, 'rb'), caption=text)
    else:
        await update.message.reply_text(text)


async def your_stat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args
    user_id = update.effective_user.id

    if user_id not in ADMIN_IDS:
        await update.message.reply_text("У вас немає прав доступу до цієї команди.")
        return

    if args:
        username = args[0].lstrip('@')
    elif update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
        username = target_user.username
    else:
        await update.message.reply_text("Будь ласка, вкажіть @username або відповідайте на повідомлення користувача.")
        return

    chat_id = update.effective_chat.id
    chat_stats = load_statistics(chat_id)

    target_user_id = None
    for user in chat_stats:
        try:
            chat = await context.bot.get_chat(user)
            if chat.username == username:
                target_user_id = user
                break
        except BadRequest:
            continue

    if not target_user_id or target_user_id not in chat_stats:
        await update.message.reply_text(f"У користувача @{username} немає статистики.")
        return

    user_stats = chat_stats[target_user_id]
    total_hours = user_stats.get('total', 0)
    daily_stats = user_stats.get('daily', {})
    balance = user_stats.get('currency', 0)
    skin = user_stats.get('skin', None)

    text = f"Статистика користувача @{username}:\nЗагалом: {total_hours} годин\nБаланс: {balance} сяйва✨\n\n"
    text += "Статистика по дням тижня:\n"

    days = ["Понеділок", "Вівторок", "Середа", "Четвер", "П'ятниця", "Субота", "Неділя"]
    for i, day in enumerate(days):
        hours = daily_stats.get(str(i), 0)
        if hours > 0:
            text += f"{day}: {hours} годин\n"

    if skin:
        skin_path = os.path.join(SKINS_DIR, skin)
        with open(skin_path, 'rb') as photo:
            await update.message.reply_photo(photo=photo, caption=text)
    else:
        await update.message.reply_text(text)


async def reset_stat_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    if user_id not in ADMIN_IDS:
        await update.message.reply_text("У вас немає прав доступу до цієї команди.")
        return

    chat_id = update.effective_chat.id
    chat_stats = load_statistics(chat_id)

    target_user_id = None
    if context.args:
        target_username = context.args[0].lstrip('@')
        target_user_id = None
        for user in chat_stats:
            try:
                chat = await context.bot.get_chat(user)
                if chat.username == target_username:
                    target_user_id = user
                    break
            except BadRequest:
                continue
    elif update.message.reply_to_message:
        target_user_id = str(update.message.reply_to_message.from_user.id)

    if target_user_id and target_user_id in chat_stats:
        context.user_data['reset_stat_target'] = target_user_id
        await update.message.reply_text(f"Ви впевнені, що хочете скинути статистику користувача {target_user_id}? Відповідайте 'так' або 'ні'.")
    else:
        await update.message.reply_text("Користувача не знайдено. Будь ласка, вкажіть @username, ID користувача або відповідайте на повідомлення користувача.")


async def confirm_reset_stat_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_response = update.message.text.lower()
    if 'reset_stat_target' not in context.user_data:
        return

    if user_response == 'так':
        target_user_id = context.user_data.pop('reset_stat_target')
        chat_id = update.effective_chat.id
        chat_stats = load_statistics(chat_id)
        if target_user_id in chat_stats:
            chat_stats[target_user_id] = {"total": 0, "daily": {}, "currency": 0, "name": "", "last_earn": None}
            save_statistics(chat_id, chat_stats)
            await update.message.reply_text(f"Статистика користувача з ID {target_user_id} була скинута.")
        else:
            await update.message.reply_text("Користувача не знайдено.")
    else:
        context.user_data.pop('reset_stat_target')
        await update.message.reply_text("Скидання статистики скасовано.")


async def top_earners(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    chat_stats = load_statistics(chat_id)

    top_users = sorted(chat_stats.items(), key=lambda x: x[1].get('currency', 0), reverse=True)[:10]
    text = "Топ користувачів за кількістю сяйва✨:\n"
    for user_id, stats in top_users:
        chat = await context.bot.get_chat(user_id)
        user_name = get_user_name(stats, chat, user_id)
        currency = stats.get('currency', 0)
        text += f"{user_name}: {currency} сяйва✨\n"

    await update.message.reply_text(text)


async def top_workers(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    chat_stats = load_statistics(chat_id)

    top_users = sorted(chat_stats.items(), key=lambda x: x[1].get('total', 0), reverse=True)[:10]
    text = "Топ користувачів за загальною кількістю годин:\n"
    for user_id, stats in top_users:
        chat = await context.bot.get_chat(user_id)
        user_name = get_user_name(stats, chat, user_id)
        total_hours = stats.get('total', 0)
        text += f"{user_name}: {total_hours} годин\n"

    await update.message.reply_text(text)


async def top_workers_day(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    chat_stats = load_statistics(chat_id)

    now = datetime.now(kyiv_tz)
    yesterday = (now - timedelta(days=1)).weekday()

    top_users = []
    for user_id, stats in chat_stats.items():
        total_day_hours = stats.get('daily', {}).get(str(yesterday), 0)
        chat = await context.bot.get_chat(user_id)
        user_name = get_user_name(stats, chat, user_id)
        top_users.append((user_id, total_day_hours))

    top_users = sorted(top_users, key=lambda x: x[1], reverse=True)[:10]
    text = "Топ користувачів за кількістю годин за вчорашній день:\n"
    for user_id, total_day_hours in top_users:
        user_name = chat_stats[user_id].get("name") or get_user_name(chat_stats[user_id], await context.bot.get_chat(user_id), user_id)
        text += f"{user_name}: {total_day_hours} годин\n"

    await update.message.reply_text(text)


def update_schedules():
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


# def process_hours(input_range):
#     hours = input_range.split('-')
#
#     if len(hours) != 2:
#         return "Будь ласка, введіть правильний час (формат: x-y)."
#
#     try:
#         start_hour = int(hours[0]) % 24
#         end_hour = int(hours[1]) % 24
#     except ValueError:
#         return "Будь ласка, введіть правильний час (тільки числа)."
#
#     time_slots = []
#
#     if start_hour <= end_hour:
#         for hour in range(start_hour, end_hour + 1):
#             next_hour = (hour + 1) % 24
#             time_slot = f"{hour:02d}:00 - {next_hour:02d}:00"
#             time_slots.append(time_slot)
#     else:
#         for hour in range(start_hour, 24):
#             next_hour = (hour + 1) % 24
#             time_slot = f"{hour:02d}:00 - {next_hour:02d}:00"
#             time_slots.append(time_slot)
#         for hour in range(0, end_hour + 1):
#             next_hour = (hour + 1) % 24
#             time_slot = f"{hour:02d}:00 - {next_hour:02d}:00"
#             time_slots.append(time_slot)
#
#     return time_slots


async def get_schedule_text(schedule, date_label, context, update):
    text = f"Графік роботи Адміністраторів на {date_label}\n\n"

    for time_slot, user_ids in schedule.items():
        admins = []
        for user_id in user_ids:
            user_id = str(user_id)
            chat_stats = load_statistics(update.effective_chat.id)
            if user_id in chat_stats and chat_stats[user_id].get("name"):
                admins.append(chat_stats[user_id]["name"])
            else:
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
        "/tomorrow для завтрашнього, та /default для стандартного графіка."
        "Для додаткової інформації використовуйте команду /help.")


async def mechanical_update_schedules_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    if user_id not in ADMIN_IDS:
        await update.message.reply_text("У вас немає прав доступу до цієї команди.")
        return

    await update.message.reply_text("Графік змінено", update_schedules())


async def show_today_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    today_schedule = load_schedule(chat_id, "today", empty_weekday, empty_weekend)
    text = await get_schedule_text(today_schedule, datetime.now(pytz.timezone('Europe/Kiev')).strftime("%d.%m.%Y"), context, update)
    await update.message.reply_text(text)


async def show_tomorrow_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    tomorrow_schedule = load_schedule(chat_id, "tomorrow", empty_weekday, empty_weekend)
    text = await get_schedule_text(tomorrow_schedule, (datetime.now(pytz.timezone('Europe/Kiev')) + timedelta(days=1)).strftime("%d.%m.%Y"), context, update)
    await update.message.reply_text(text)


async def show_default_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    current_day = datetime.now(pytz.timezone('Europe/Kiev')).weekday()
    if current_day < 5:
        schedule = load_schedule(chat_id, "weekday_default", empty_weekday, empty_weekend)
        text = await get_schedule_text(schedule, "стандартний графік (будній день)", context, update)
    else:
        schedule = load_schedule(chat_id, "weekend_default", empty_weekday, empty_weekend)
        text = await get_schedule_text(schedule, "стандартний графік (вихідний день)", context, update)
    await update.message.reply_text(text)


async def show_weekday_default_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    schedule = load_schedule(chat_id, "weekday_default", empty_weekday, empty_weekday)
    text = await get_schedule_text(schedule, "стандартний графік (будній день)", context, update)
    await update.message.reply_text(text)


async def show_weekend_default_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    schedule = load_schedule(chat_id, "weekend_default", empty_weekend, empty_weekend)
    text = await get_schedule_text(schedule, "стандартний графік (вихідний день)", context, update)
    await update.message.reply_text(text)


async def edit_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message.text.strip()
    chat_id = update.effective_chat.id

    if not (message.startswith('+') or message.startswith('-')):
        return
    if not update.message:
        return

    user_id = update.effective_user.id
    chat_stats = load_statistics(chat_id)
    user_name = chat_stats.get(user_id, {}).get("name", update.effective_user.first_name or update.effective_user.username)

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

    add_hours = hours_range.endswith('!') and operation == 'add'
    remove_hours = hours_range.endswith('!') and operation == 'remove' and user_id in ADMIN_IDS

    if add_hours or remove_hours:
        hours_range = hours_range[:-1].strip()

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
                    if add_hours and time_slot not in schedule:
                        schedule[time_slot] = []
                    if user_id not in schedule[time_slot]:
                        schedule[time_slot].append(user_id)
                        updated_hours.append(time_slot)

                elif operation == 'remove':
                    if remove_hours and time_slot in schedule:
                        del schedule[time_slot]
                    if time_slot in schedule and user_id in schedule[time_slot]:
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

            if add_hours and time_slot not in schedule:
                schedule[time_slot] = []

            if operation == 'add':
                if user_id not in schedule[time_slot]:
                    schedule[time_slot].append(user_id)
                    updated_hours.append(time_slot)
            elif operation == 'remove':
                if remove_hours and time_slot in schedule:
                    del schedule[time_slot]
                if time_slot in schedule and user_id in schedule[time_slot]:
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

    # Sort the schedule by time slots, keeping '00:00 - 01:00' at the end
    sorted_schedule = sorted(schedule.items(), key=lambda x: (x[0] == '00:00 - 01:00', x[0]))

    updated_schedule_message = f"Графік роботи Адміністраторів на {date_label}\n\n"
    for time_slot, users in sorted_schedule:
        user_names = []
        for user_id in users:
            user_id = str(user_id)
            chat_stats = load_statistics(update.effective_chat.id)
            if user_id in chat_stats and chat_stats[user_id].get("name"):
                user_names.append(chat_stats[user_id]["name"])
            else:
                try:
                    chat = await context.bot.get_chat(user_id)
                    if chat.first_name:
                        user_names.append(format_name(chat.first_name))
                    else:
                        user_names.append("–")
                except BadRequest:
                    user_names.append("unknown")

        user_names_str = ' – '.join(user_names) if user_names else "–"
        updated_schedule_message += f"{time_slot}: {user_names_str}\n"

    try:
        await update.message.reply_to_message.edit_text(updated_schedule_message + '\n' + response_message)
    except Exception as e:
        await update.message.reply_text("Не вдалося редагувати повідомлення. Спробуйте ще раз.")
        print(e)

async def leave(update: Update, context):
    response = random.choice(responses_easy)
    await update.message.reply_text(response)


async def leave_username(update: Update, context):
    username = update.message.from_user.username
    response = random.choice(responses_username).format(username=username)
    await update.message.reply_text(response)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "Доступні команди:\n"
        "+h-h - у ВІДПОВІДЬ на графік. Додати себе до графіка на години від x до y, наприклад: +9-12 або -9-12\n"
        "/today - Показати сьогоднішній графік\n"
        "/tomorrow - Показати завтрашній графік\n"
        "/default - Показати стандартний графік\n"
        "/stat - Показати статистику чату\n"
        "/my_stat - Показати вашу статистику\n"
        "/earn - Заробити сяйво✨ за вчорашню роботу\n"
        "/set_name - Встановити ваше ім'я\n"
        "/top_earners - Показати топ користувачів за кількістю сяйва✨\n"
        "/top_workers - Показати топ користувачів за кількістю годин\n"
        "/top_workers_day - Показати топ користувачів за кількістю годин за вчорашній день\n"
        "/shop - Показати магазин скинів\n"
        "/buy_skin - Придбати скин\n"
        "/help - Показати це повідомлення\n"
        "\n"
        "Для адмінів\n"
        "/reset_stat - Скинути статистику користувача\n"
        "/your_stat - Показати статистику іншого користувача\n"
        "/add_money - Додати сяйво✨ іншому користувачу\n"
        "/set_money - Встановити кількість сяйва✨ для користувача\n"
        "/set_skin - Встановити скин для користувача\n"
    )
    await update.message.reply_text(text)


def main() -> None:
    signal.signal(signal.SIGINT, signal_handler)  # Handle signal
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("today", show_today_schedule))
    app.add_handler(CommandHandler("tomorrow", show_tomorrow_schedule))
    app.add_handler(CommandHandler("default", show_default_schedule))
    app.add_handler(CommandHandler("weekday", show_weekday_default_schedule))
    app.add_handler(CommandHandler("weekend", show_weekend_default_schedule))
    app.add_handler(CommandHandler("update", mechanical_update_schedules_admin))
    app.add_handler(CommandHandler("leavethisgroup", leave_username))
    app.add_handler(CommandHandler("leave", leave))
    app.add_handler(CommandHandler("stat", all_stat))
    app.add_handler(CommandHandler("my_stat", my_stat))
    app.add_handler(CommandHandler("your_stat", your_stat))
    app.add_handler(CommandHandler("earn", earn))
    app.add_handler(CommandHandler("set_name", set_name))
    app.add_handler(CommandHandler("add_money", add_money_admin))
    app.add_handler(CommandHandler("set_money", set_money_admin))
    app.add_handler(CommandHandler("top_earners", top_earners))
    app.add_handler(CommandHandler("top_workers", top_workers))
    app.add_handler(CommandHandler("top_workers_day", top_workers_day))
    app.add_handler(CommandHandler("shop", shop_command))
    app.add_handler(CommandHandler("buy_skin", buy_skin_command))
    app.add_handler(CommandHandler("preview_skin", preview_skin_command))
    app.add_handler(CommandHandler("set_skin", set_skin_admin))
    app.add_handler(CommandHandler("reset_stat", reset_stat_admin))
    app.add_handler(MessageHandler(filters.Regex(r'^(так|ні)$') & ~filters.COMMAND, confirm_reset_stat_text))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r'^[+-]'), edit_schedule))
    app.add_handler(CallbackQueryHandler(shop_command, pattern=r'^shop\s\d+'))
    # Create scheduler
    scheduler = BackgroundScheduler()
    scheduler.add_job(update_schedules, 'cron', hour=0, minute=0, timezone=kyiv_tz)
    scheduler.start()

    # Run keep_alive in a separate thread
    threading.Thread(target=keep_alive, daemon=True).start()

    app.run_polling(poll_interval=1)


if __name__ == "__main__":
    main()
