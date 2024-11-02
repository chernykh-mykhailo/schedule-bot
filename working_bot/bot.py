# -*- coding: utf-8 -*-
import random
import emoji
import sys
import re
import copy
import json
import logging
import os
import threading
import time
import signal
from datetime import datetime, timedelta

import pytz
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, \
    CallbackQueryHandler, CallbackContext
from telegram.error import BadRequest, NetworkError
from apscheduler.schedulers.background import BackgroundScheduler

from responses import responses_easy, responses_username

# Додаємо шлях до секретного файлу у Python шлях (для хостингу)
sys.path.append('/etc/secrets')

from config import TELEGRAM_TOKEN  # Імпорт токену з конфігураційного файлу
from config import ADMIN_IDS  # Імпорт списку з айдішками адмінів
from config import MISTRAL_API_KEY
from config import MISTRAL_API_URL

LOCK_FILE = 'bot.lock'

SKINS_DIR = "skins"
PROFILE_SKINS_DIR = "skins/profile_skins"
KISS_SKINS_DIR = "skins/kiss_skins"
HUG_SKINS_DIR = "skins/hug_skins"
DANCE_SKINS_DIR = "skins/dance_skins"

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


chat_states = {}

async def start_chatbot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    chat_states[chat_id] = True
    await update.message.reply_text("Чат-бот активовано.")

async def stop_chatbot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    chat_states[chat_id] = False
    await update.message.reply_text("Чат-бот деактивовано.")

async def get_mistral_response(message: str) -> str:
    headers = {
        "Authorization": f"Bearer {MISTRAL_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "open-mistral-nemo",
        "messages": [{"role": "user", "content": message}]
    }
    try:
        response = requests.post(MISTRAL_API_URL, headers=headers, json=data)
        response.raise_for_status()
        response_data = response.json()
        return response_data.get("choices", [{}])[0].get("message", {}).get("content", "")
    except requests.exceptions.RequestException as e:
        logging.error(f"Error occurred during Mistral API request: {e}")
        return ""


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if update.message.reply_to_message and chat_states.get(chat_id, False):
        response = await get_mistral_response(update.message.text)
        logging.info(f"Mistral response: {response}")
        if response:
            await update.message.reply_text(response)
        else:
            logging.warning("Empty response from Mistral.ai API")



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


def get_user_name(stats, user):
    # Check if the name is set in the statistics
    if "name" in stats:
        return stats["name"]

    # Check if the first name is longer than 3 characters
    if user.first_name and len(user.first_name) > 3:
        return format_name(user.first_name)

    # Use the username if available
    if user.username:
        return user.username

    # Fallback to user ID
    return str(user.id)


logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

logger = logging.getLogger(__name__)


async def error_handler(update: Update, context: CallbackContext) -> None:
    logging.error(msg="Exception while handling an update:", exc_info=context.error)
    if isinstance(context.error, NetworkError):
        await update.message.reply_text("Network error occurred. Please try again later.")



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


def load_statistics_for_period(chat_id, start_date, end_date):
    stats = {}
    current_date = start_date
    while current_date <= end_date:
        file_name = os.path.join(STATS_DIR, f"{chat_id}_{current_date.strftime('%Y-%m-%d')}.json")
        if os.path.exists(file_name):
            try:
                with open(file_name, 'r', encoding='utf-8') as f:
                    daily_stats = json.load(f)
                    for user_id, user_stats in daily_stats.items():
                        if user_id not in stats:
                            stats[user_id] = user_stats
                        else:
                            stats[user_id]['total'] += user_stats.get('total', 0)
                            stats[user_id]['currency'] += user_stats.get('currency', 0)
                            for day, hours in user_stats.get('daily', {}).items():
                                if day not in stats[user_id]['daily']:
                                    stats[user_id]['daily'][day] = hours
                                else:
                                    stats[user_id]['daily'][day] += hours
            except Exception as e:
                logging.error(f"Error loading statistics from {file_name}: {e}")
        current_date += timedelta(days=1)
    return stats


def load_user_stats(chat_id, user_id):
    file_name = os.path.join(STATS_DIR, f"{chat_id}.json")
    if os.path.exists(file_name):
        with open(file_name, 'r', encoding='utf-8') as f:
            stats = json.load(f)
            return stats.get(str(user_id), {})
    return {}

def save_user_stats(chat_id, user_id, user_stats):
    file_name = os.path.join(STATS_DIR, f"{chat_id}.json")
    if os.path.exists(file_name):
        with open(file_name, 'r', encoding='utf-8') as f:
            stats = json.load(f)
    else:
        stats = {}
    stats[str(user_id)] = user_stats
    with open(file_name, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=4)


def has_earned_today(user_stats):
    last_earn_date = datetime.strptime(user_stats.get('last_earn', '1970-01-01 00:00:00'), "%Y-%m-%d %H:%M:%S")
    return last_earn_date.date() == datetime.now(kyiv_tz).date()


async def earn(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    user_id = str(update.effective_user.id)
    chat_stats = load_statistics(chat_id)
    user_stats = load_user_stats(chat_id, user_id)

    if user_id == 1087968824:
        await update.message.reply_text("Анонімні адміністратори не можуть використовувати цю команду.")
        return

    if user_id not in chat_stats:
        chat_stats[user_id] = {"total": 0, "daily": {}, "currency": 0, "name": "", "last_earn": None}

    if has_earned_today(user_stats):
        now = datetime.now(kyiv_tz)
        next_earn_time = datetime.combine(now.date() + timedelta(days=1), datetime.min.time(), kyiv_tz)
        remaining_time = next_earn_time - now
        hours, remainder = divmod(remaining_time.seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        await update.message.reply_text(
            f"Ви вже заробили сяйво✨ сьогодні. Спробуйте знову через {hours} годин і {minutes} хвилин.")
        return

    last_earn = chat_stats[user_id].get("last_earn")
    now = datetime.now(kyiv_tz)

    # Calculate the total hours worked yesterday
    hours_worked_yesterday = chat_stats[user_id].get("yesterday", 0)

    # Introduce randomness in the currency awarded
    random_multiplier = random.uniform(0.7, 1.5)
    earned_currency = int(hours_worked_yesterday * 10 * random_multiplier)
    chat_stats[user_id]["currency"] += earned_currency
    chat_stats[user_id]["last_earn"] = now.strftime("%Y-%m-%d %H:%M:%S")

    save_statistics(chat_id, chat_stats)
    await update.message.reply_text(f"Ви заробили {earned_currency} сяйва✨ з"
                                    f"а {hours_worked_yesterday} годин роботи вчора. Загальний баланс: {chat_stats[user_id]['currency']} сяйва✨.")


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


def list_skins(directory):
    skins = []
    try:
        for file_name in os.listdir(directory):
            if file_name.endswith(('.png', '.jpg', '.jpeg')):
                skins.append(file_name)
        logger.info(f"Found skins in {directory}: {skins}")
    except Exception as e:
        logger.error(f"Error loading skins from {directory}: {e}")
    return skins


def get_skin_page(category, page_number):
    if category == "profile":
        skins = list_skins(PROFILE_SKINS_DIR)
    elif category == "kiss":
        skins = list_skins(KISS_SKINS_DIR)
    elif category == "hug":
        skins = list_skins(HUG_SKINS_DIR)
    elif category == "dance":
        skins = list_skins(DANCE_SKINS_DIR)
    else:
        skins = []

    start_index = page_number * SKINS_PER_PAGE
    end_index = start_index + SKINS_PER_PAGE
    return skins[start_index:end_index], len(skins)


# python
async def shop_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        text = "Please choose a category:\n"
        text += "`/shop profile` - Skins for profiles\n"
        text += "`/shop kiss` - Skins for kisses\n"
        text += "`/shop hug` - Skins for hugs\n"
        text += "`/shop dance` - Skins for dances\n"
        await update.message.reply_text(text, parse_mode='Markdown')
        return

    category = context.args[0].lower()
    if category not in ["profile", "kiss", "hug", "dance"]:
        await update.message.reply_text("Invalid category. Please choose from profile, kiss, hug, or dance.")
        return

    page_number = int(context.args[1]) if len(context.args) > 1 else 0
    skins, total_skins = get_skin_page(category, page_number)
    total_pages = (total_skins + SKINS_PER_PAGE - 1) // SKINS_PER_PAGE

    text = f"Available skins for {category}:\n"
    for skin in skins:
        text += f"`{skin}` - 100 сяйва \n"

    text += "\nUse `/buy_skin `*skin_name* to purchase a skin.\n"
    text += "Use `/preview_skin `*skin_name* to preview.\n"

    if page_number > 0:
        text += f"`/shop {category} {page_number - 1}` - Previous\n"
    if page_number < total_pages - 1:
        text += f"`/shop {category} {page_number + 1}` - Next\n"

    await update.message.reply_text(text, parse_mode='Markdown')


async def buy_skin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    user_id = str(update.effective_user.id)
    chat_stats = load_statistics(chat_id)

    if user_id not in chat_stats:
        await update.message.reply_text("У вас немає статистики.")
        return

    if len(context.args) != 1:
        await update.message.reply_text("Будь ласка, використовуйте формат: /buy_skin <назва_скіна>")
        return

    skin_name = context.args[0]
    skin_found = False
    skin_category = None

    # Check all skin categories
    for category in ["profile_skins", "kiss_skins", "hug_skins", "dance_skins"]:
        available_skins = list_skins(os.path.join(SKINS_DIR, category))
        if skin_name in available_skins:
            skin_found = True
            skin_category = category
            break

    if not skin_found:
        await update.message.reply_text("Скін не знайдено.")
        return

    user_stats = chat_stats[user_id]
    balance = user_stats.get('currency', 0)

    skin_cost = 100
    if balance < skin_cost:
        await update.message.reply_text("Недостатньо сяйва✨ для покупки цього скіна.")
        return

    user_stats['currency'] -= skin_cost
    if 'purchased_skins' not in user_stats:
        user_stats['purchased_skins'] = {}
    if skin_category not in user_stats['purchased_skins']:
        user_stats['purchased_skins'][skin_category] = []
    user_stats['purchased_skins'][skin_category].append(skin_name)
    user_stats[f'{skin_category[:-1]}_skin'] = skin_name  # Set the last purchased skin as active
    save_statistics(chat_id, chat_stats)

    await update.message.reply_text(f"Ви успішно придбали скіна {skin_name} з категорії {skin_category}.")

async def preview_skin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) < 1:
        await update.message.reply_text("Please specify the skin name.")
        return

    skin_name = context.args[0]
    skin_found = False
    skin_path = ""

    # Check all skin categories
    for root, dirs, files in os.walk(SKINS_DIR):
        if skin_name in files:
            skin_found = True
            skin_path = os.path.join(root, skin_name)
            break

    if not skin_found:
        await update.message.reply_text("Skin not found. Please choose another skin.")
        return

    await update.message.reply_photo(photo=open(skin_path, 'rb'))

async def set_skin_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    # Check if the user is an admin
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("У вас немає прав доступу до цієї команди.")
        return

    # Check if the correct number of arguments is provided
    if len(context.args) != 3:
        await update.message.reply_text("Будь ласка, використовуйте формат: /set_skin @username <category> <skin_name>")
        return

    target_username = context.args[0].lstrip('@')
    category = context.args[1].lower()
    skin_name = context.args[2]

    available_skins = list_skins(os.path.join(SKINS_DIR, f"{category}_skins"))
    if skin_name not in available_skins:
        await update.message.reply_text("Скін не знайдено. Будь ласка, виберіть інший скін.")
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

    if category == "profile_skins":
        chat_stats[target_user_id]["skin"] = skin_name
    else:
        chat_stats[target_user_id][f"{category}_skin"] = skin_name

    save_statistics(chat_id, chat_stats)

    await update.message.reply_text(f"Користувачу @{target_username} було встановлено скин: {skin_name} для категорії {category}.")


async def change_skin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    user_id = str(update.effective_user.id)
    chat_stats = load_statistics(chat_id)

    if user_id not in chat_stats:
        await update.message.reply_text("У вас немає статистики.")
        return

    if len(context.args) != 1:
        await update.message.reply_text("Будь ласка, використовуйте формат: /change_skin <назва_скіна>")
        return

    skin_name = context.args[0]
    category = None

    # Determine the category of the skin
    for cat in ["profile_skins", "kiss_skins", "hug_skins", "dance_skins"]:
        if skin_name in list_skins(os.path.join(SKINS_DIR, cat)):
            category = cat
            break

    if not category:
        await update.message.reply_text("Скін не знайдено. Будь ласка, виберіть інший скін.")
        return

    user_stats = chat_stats[user_id]
    if ('purchased_skins' not in user_stats or category not in user_stats['purchased_skins']
            or skin_name not in user_stats['purchased_skins'][category]):
        await update.message.reply_text("У вас немає придбаних скінів у цій категорії.")
        return

    purchased_skins = user_stats['purchased_skins'][category]

    skin = skin_name
    user_stats[f'{category[:-1]}_skin'] = skin  # Set the selected skin as active
    save_statistics(chat_id, chat_stats)

    await update.message.reply_text(f"Ви успішно змінили активний скін на {skin} з категорії {category}.")


def save_statistics(chat_id, stats, date=None):
    if date is None:
        date = datetime.now(kyiv_tz).strftime("%Y-%m-%d")
    file_name = os.path.join(STATS_DIR, f"{chat_id}_{date}.json")
    try:
        with open(file_name, 'w', encoding='utf-8') as f:
            json.dump(stats, f, ensure_ascii=False, indent=4)
        logging.info(f"Statistics saved successfully: {file_name}")
    except Exception as e:
        logging.error(f"Failed to save statistics: {file_name}, Error: {e}")


async def get_user_stats_text(user_stats, user_name):
    profile_skin = user_stats.get('profile_skin_skin', None)
    profile_skin_path = os.path.join(PROFILE_SKINS_DIR, profile_skin) if profile_skin else None

    text = f"Статистика користувача {user_name}:\n"
    if user_stats.get("total", 0) > 0:
        text += f"Загалом: {user_stats['total']} годин\n"
    if user_stats.get("yesterday", 0) > 0:
        text += f"Вчора: {user_stats['yesterday']} годин\n"
    if user_stats.get("currency", 0) > 0:
        text += f"Баланс: {user_stats['currency']} сяйва✨\n"
    if user_stats.get("gender", "не встановлено") != "не встановлено":
        text += f"Стать: {user_stats['gender']}\n"
    if user_stats.get("hugs", 0) > 0:
        text += f"Обійми: {user_stats['hugs']}\n"
    if user_stats.get("kisses", 0) > 0:
        text += f"Поцілунки: {user_stats['kisses']}\n"

    text += "\nСтатистика по дням тижня:\n"
    days_of_week = ["Понеділок", "Вівторок", "Середа", "Четвер", "П'ятниця", "Субота", "Неділя"]
    for day, hours in user_stats.get("daily", {}).items():
        if hours > 0:
            text += f"{days_of_week[int(day)]}: {hours} годин\n"

    text += "\nПридбані скіни:\n"
    for category, skins in user_stats.get("purchased_skins", {}).items():
        if skins:
            text += f"{category.capitalize()}: {', '.join(skins)}\n"

    return text, profile_skin_path


async def my_stat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    user_id = str(update.effective_user.id)
    chat_stats = load_statistics(chat_id)

    if user_id not in chat_stats:
        await update.message.reply_text("Ваша статистика не знайдена.")
        return

    user_stats = chat_stats[user_id]
    user_name = get_user_name(user_stats, update.effective_user)
    text, profile_skin_path = await get_user_stats_text(user_stats, user_name)

    if profile_skin_path and os.path.exists(profile_skin_path):
        await update.message.reply_photo(photo=open(profile_skin_path, 'rb'), caption=text)
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
    text, profile_skin_path = await get_user_stats_text(user_stats, f"@{username}")

    if profile_skin_path and os.path.exists(profile_skin_path):
        await update.message.reply_photo(photo=open(profile_skin_path, 'rb'), caption=text)
    else:
        await update.message.reply_text(text)


async def remove_user_from_all_schedules(chat_id, user_id, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if user_id is None:
        logging.error("User ID is None. Cannot remove user from schedules.")
        return

    for schedule_type in ['today', 'tomorrow', 'default', 'weekday_default', 'weekend_default']:
        schedule = load_schedule(chat_id, schedule_type, empty_weekday, empty_weekend)
        user_removed = False
        for time_slot, users in schedule.items():
            if user_id in users:
                users.remove(user_id)
                user_removed = True
                logging.info(f"Removed user {user_id} from {time_slot} in {schedule_type} schedule.")
        if user_removed:
            save_schedule(chat_id, schedule_type, schedule)
            await update.message.reply_text(
                f"{user_id} видалено з усіх графіків.")

        else:
            logging.info(f"User {user_id} not found in {schedule_type} schedule.")


async def reset_stat_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    # Check if the user is an admin
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("У вас немає прав доступу до цієї команди.")
        return

    # Check if context.args is None or does not have exactly one argument
    if context.args is None or len(context.args) != 1:
        await update.message.reply_text("Будь ласка, використовуйте формат: /reset_stat @username або /reset_stat user_id")
        return

    target_identifier = context.args[0].lstrip('@')
    chat_id = update.effective_chat.id

    # Store the target identifier in user_data for later use
    context.user_data['reset_stat_target'] = target_identifier
    await update.message.reply_text(f"Ви впевнені, що хочете скинути статистику для {target_identifier}? Напишіть 'так' або 'ні'.")


async def confirm_reset_stat_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_response = update.message.text.lower()
    if 'reset_stat_target' not in context.user_data:
        return

    target_identifier = context.user_data.pop('reset_stat_target')
    chat_id = update.effective_chat.id
    chat_stats = load_statistics(chat_id)

    if user_response == 'так':
        # Determine if the identifier is a user ID or username
        if target_identifier.isdigit():
            target_user_id = int(target_identifier)
        else:
            target_user_id = None
            for user in chat_stats:
                try:
                    chat = await context.bot.get_chat(user)
                    if chat.username == target_identifier:
                        target_user_id = user
                        break
                except BadRequest:
                    continue
        # Remove user from all schedules
        await remove_user_from_all_schedules(chat_id, target_user_id, update, context)

        if not target_user_id or target_user_id not in chat_stats:
            await update.message.reply_text(f"Статистика користувача з ідентифікатором {target_identifier} не знайдена.")
            return

        # Remove user from statistics
        del chat_stats[target_user_id]
        save_statistics(chat_id, chat_stats)

        await update.message.reply_text(f"Статистика користувача з ідентифікатором {target_identifier} була скинута.")
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
        user_name = get_user_name(stats, chat)
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
        user_name = get_user_name(stats, chat)
        total_hours = stats.get('total', 0)
        text += f"{user_name}: {total_hours} годин\n"

    await update.message.reply_text(text)


async def top_yesterday(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    chat_stats = load_statistics(chat_id)

    top_users = []
    for user_id, stats in chat_stats.items():
        total_day_hours = stats.get('yesterday', 0)
        try:
            chat = await context.bot.get_chat(user_id)
            top_users.append((user_id, total_day_hours))
        except BadRequest as e:
            logging.error(f"Failed to get chat for user_id {user_id}: {e}")

    top_users = sorted(top_users, key=lambda x: x[1], reverse=True)[:10]
    text = "Топ користувачів за кількістю годин за вчорашній день:\n"
    for user_id, total_day_hours in top_users:
        try:
            user_name = get_user_name(chat_stats[user_id], await context.bot.get_chat(user_id))
            text += f"{user_name}: {total_day_hours} годин\n"
        except BadRequest as e:
            logging.error(f"Failed to get chat for user_id {user_id}: {e}")

    await update.message.reply_text(text)


async def top_week(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    end_date = datetime.now(kyiv_tz)
    start_date = end_date - timedelta(days=7)
    weekly_stats = load_statistics_for_period(chat_id, start_date, end_date)
    await display_top_users(update, weekly_stats, "за цей тиждень")


async def top_last_week(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    end_date = datetime.now(kyiv_tz) - timedelta(days=7)
    start_date = end_date - timedelta(days=7)
    last_week_stats = load_statistics_for_period(chat_id, start_date, end_date)
    await display_top_users(update, last_week_stats, "за минулий тиждень")


async def top_month(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    end_date = datetime.now(kyiv_tz)
    start_date = end_date - timedelta(days=30)
    monthly_stats = load_statistics_for_period(chat_id, start_date, end_date)
    await display_top_users(update, monthly_stats, "за цей місяць")


async def top_last_month(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    end_date = datetime.now(kyiv_tz) - timedelta(days=30)
    start_date = end_date - timedelta(days=30)
    last_month_stats = load_statistics_for_period(chat_id, start_date, end_date)
    await display_top_users(update, last_month_stats, "за минулий місяць")


async def top_custom_period(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if len(context.args) != 2:
        await update.message.reply_text("Будь ласка, введіть дві дати у форматі YYYY-MM-DD.")
        return
    try:
        start_date = datetime.strptime(context.args[0], "%Y-%m-%d")
        end_date = datetime.strptime(context.args[1], "%Y-%m-%d")
    except ValueError:
        await update.message.reply_text("Неправильний формат дати. Використовуйте YYYY-MM-DD.")
        return
    custom_period_stats = load_statistics_for_period(chat_id, start_date, end_date)
    await display_top_users(update, custom_period_stats, f"з {start_date.strftime('%Y-%m-%d')} по {end_date.strftime('%Y-%m-%d')}")


async def display_top_users(update: Update, stats, period_label):
    top_users = sorted(stats.items(), key=lambda x: x[1].get('total', 0), reverse=True)[:10]
    text = f"Топ користувачів {period_label}:\n"
    for user_id, user_stats in top_users:
        user_name = get_user_name(user_stats, update.effective_user)
        total_hours = user_stats.get("total", 0)
        text += f"{user_name}: {total_hours} годин\n"
    await update.message.reply_text(text)


async def all_stat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    chat_stats = load_statistics(chat_id)

    user_stats_summary = {}

    for user_id, stats in chat_stats.items():
        try:
            chat = await context.bot.get_chat(user_id)
            user_name = get_user_name(chat_stats[user_id], await context.bot.get_chat(user_id))
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



async def top_workers_weekly(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    chat_stats = load_statistics(chat_id)

    if not chat_stats:
        await update.message.reply_text("Немає статистики для цього чату.")
        return

    # Calculate weekly hours for all users
    weekly_stats = {}
    for user_id, stats in chat_stats.items():
        weekly_hours = sum(stats.get('daily', {}).values())
        weekly_stats[user_id] = weekly_hours

    # Sort users by weekly hours
    top_users = sorted(weekly_stats.items(), key=lambda x: x[1], reverse=True)[:5]

    text = "*Топ користувачів за тиждень:*\n"
    for rank, (user_id, hours) in enumerate(top_users, 1):
        user_name = chat_stats[user_id].get('name', f"User {user_id}")
        text += f"{rank}. {user_name}: *{hours}* годин\n"

    await update.message.reply_text(text, parse_mode='Markdown')


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

            # Reset yesterday's hours for all users
            for user_id in chat_stats:
                chat_stats[user_id]['yesterday'] = 0

            # Update total hours worked for each user
            for user_id, hours in today_stats.items():
                # Initialize user statistics if not already present
                if user_id not in chat_stats:
                    chat_stats[user_id] = {"total": 0, "daily": {}, "yesterday": 0}

                chat_stats[user_id]["total"] += hours

                # Update daily statistics for the user
                weekday = previos_date.weekday()  # Це індекс дня тижня (0 для Понеділка і т.д.)
                daily_stats = chat_stats[user_id].get('daily', {})
                if str(weekday) not in daily_stats:
                    daily_stats[str(weekday)] = hours
                else:
                    daily_stats[str(weekday)] += hours
                chat_stats[user_id]['daily'] = daily_stats

                # Update yesterday's hours
                chat_stats[user_id]['yesterday'] = hours

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
    text = await get_schedule_text(today_schedule, datetime.now(kyiv_tz).strftime("%d.%m.%Y"), context, update)
    await update.message.reply_text(text)


async def show_tomorrow_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    tomorrow_schedule = load_schedule(chat_id, "tomorrow", empty_weekday, empty_weekend)
    text = await get_schedule_text(tomorrow_schedule, (datetime.now(kyiv_tz) + timedelta(days=1)).strftime("%d.%m.%Y"), context, update)
    await update.message.reply_text(text)


async def show_default_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    current_day = datetime.now(kyiv_tz).weekday()
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

    if not update.message:
        return

    user_id = update.effective_user.id
    chat_stats = load_statistics(chat_id)
    user_name = get_user_name(chat_stats.get(str(user_id), {}), update.effective_user)

    if not update.message.reply_to_message:
        return

    reply_text = update.message.reply_to_message.text
    schedule_type = None

    if "стандартний графік (будній день)" in reply_text:
        schedule_type = "weekday_default"
    elif "стандартний графік (вихідний день)" in reply_text:
        schedule_type = "weekend_default"
    elif "Графік роботи Адміністраторів на " in reply_text:
        schedule_date = reply_text.split('на ')[1].strip().split()[0]
        current_date = datetime.now(kyiv_tz).strftime("%d.%m.%Y")
        tomorrow_date = (datetime.now(kyiv_tz) + timedelta(days=1)).strftime("%d.%m.%Y")
        if schedule_date == current_date:
            schedule_type = "today"
        elif schedule_date == tomorrow_date:
            schedule_type = "tomorrow"

    if not schedule_type:
        return

    schedule = load_schedule(chat_id, schedule_type, empty_weekday, empty_weekend)
    operations = message.split(',')
    updated_hours = []
    invalid_hours = []
    op_type = None  # Initialize op_type

    for operation in operations:
        operation = operation.strip()
        if not (operation.startswith('+') or operation.startswith('-')):
            continue

        op_type = 'remove' if operation[0] == '-' else 'add'
        hours_range = operation[1:].strip().rstrip('!')
        add_hours = operation.endswith('!') and op_type == 'add'
        remove_hours = operation.endswith('!') and op_type == 'remove' and user_id in ADMIN_IDS

        try:
            if '-' in hours_range:
                start_time, end_time = hours_range.split('-')
                start_hour = int(start_time.split(':')[0])
                end_hour = int(end_time.split(':')[0])
                if start_hour < 0 or end_hour > 24 or start_hour >= end_hour:
                    raise ValueError
                for hour in range(start_hour, end_hour):
                    time_slot = f"{hour % 24:02d}:00 - {(hour + 1) % 24:02d}:00"
                    if op_type == 'add':
                        if add_hours and time_slot not in schedule:
                            schedule[time_slot] = []
                        if user_id not in schedule[time_slot]:
                            schedule[time_slot].append(user_id)
                            updated_hours.append(time_slot)
                    elif op_type == 'remove':
                        if remove_hours and time_slot in schedule:
                            del schedule[time_slot]
                        if time_slot in schedule and user_id in schedule[time_slot]:
                            schedule[time_slot].remove(user_id)
                            updated_hours.append(time_slot)
            else:
                hour = int(hours_range.split(':')[0])
                if hour < 0 or hour > 24:
                    raise ValueError
                time_slot = f"{hour % 24:02d}:00 - {(hour + 1) % 24:02d}:00"
                if op_type == 'add':
                    if add_hours and time_slot not in schedule:
                        schedule[time_slot] = []
                    if user_id not in schedule[time_slot]:
                        schedule[time_slot].append(user_id)
                        updated_hours.append(time_slot)
                elif op_type == 'remove':
                    if remove_hours and time_slot in schedule:
                        del schedule[time_slot]
                    if time_slot in schedule and user_id in schedule[time_slot]:
                        schedule[time_slot].remove(user_id)
                        updated_hours.append(time_slot)
        except ValueError:
            invalid_hours.append(operation)
        except KeyError:
            await update.message.reply_text(
                f"Будь ласка, введіть правильний час(від 0 до 24). "
                f"Для {'додавання' if op_type == 'add' else 'видалення'} неіснуючої години використовуйте ! "
                f"в кінці, наприклад: {'+' if op_type == 'add' else '-'}{hours_range}!"
            )
            return

    save_schedule(chat_id, schedule_type, schedule)

    if updated_hours:
        start_time = updated_hours[0].split('-')[0]
        end_time = updated_hours[-1].split('-')[1]
        response_message = f"{user_name} було {'додано до' if op_type == 'add' else 'видалено з'} графіка на {start_time} - {end_time}."
    else:
        response_message = f"Не вдалося {'додати години' if op_type == 'add' else 'видалити години'}."

    if invalid_hours:
        await update.message.reply_text(
            f"Будь ласка, введіть правильний час(від 0 до 24). "
        )
    date_label = {
        "today": datetime.now(kyiv_tz).strftime("%d.%m.%Y"),
        "tomorrow": (datetime.now(kyiv_tz) + timedelta(days=1)).strftime("%d.%m.%Y"),
        "weekday_default": "стандартний графік (будній день)",
        "weekend_default": "стандартний графік (вихідний день)"
    }.get(schedule_type, "незнайомий графік")

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


async def hug_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    chat_stats = load_statistics(chat_id)

    command_text = update.message.text.lower()
    target_username = command_text.split(" ", 1)[1].lstrip('@') if " " in command_text else None

    if target_username:
        target_user_id = next((user_id for user_id, stats in chat_stats.items() if stats.get("name") == target_username), None)
    elif update.message.reply_to_message:
        target_user_id = str(update.message.reply_to_message.from_user.id)
    else:
        await update.message.reply_text("Будь ласка, вкажіть користувача для обіймів.")
        return

    if not target_user_id:
        await update.message.reply_text("Користувача не знайдено.")
        return

    source_user_id = str(update.effective_user.id)
    source_user_name = chat_stats.get(source_user_id, {}).get("name") or update.effective_user.first_name or update.effective_user.username
    target_user_name = chat_stats.get(target_user_id, {}).get("name") or update.message.reply_to_message.from_user.first_name or update.message.reply_to_message.from_user.username

    source_user_link = f"[{source_user_name}](tg://user?id={source_user_id})"
    target_user_link = f"[{target_user_name}](tg://user?id={target_user_id})"

    source_gender = chat_stats.get(source_user_id, {}).get("gender", None)
    if source_gender == "чоловік":
        response_message = f"{source_user_link} обійняв {target_user_link} 😘"
    elif source_gender == "жінка":
        response_message = f"{source_user_link} обійняла {target_user_link} 😘"
    else:
        response_message = f"{source_user_link} обійня(ла/в) {target_user_link} 😘"

    if source_user_id in chat_stats and "hug_skin" in chat_stats[source_user_id]:
        skin = chat_stats[source_user_id]["hug_skin"]
        await update.message.reply_photo(photo=open(os.path.join(HUG_SKINS_DIR, skin), 'rb'), caption=response_message, parse_mode='Markdown')
    else:
        await update.message.reply_text(response_message, parse_mode='Markdown')



async def kiss_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    user_id = str(update.effective_user.id)
    logger.info(f"kiss_command called by user_id: {user_id} in chat_id: {chat_id}")

    chat_stats = load_statistics(chat_id)
    if user_id not in chat_stats:
        await update.message.reply_text("У вас немає статистики.")
        logger.warning(f"No statistics found for user_id: {user_id}")
        return

    command_text = update.message.text.lower()
    target_username = command_text.split(" ", 1)[1].lstrip('@') if " " in command_text else None
    logger.info(f"Target username: {target_username}")

    if target_username:
        target_user_id = next((user_id for user_id, stats in chat_stats.items() if stats.get("name") == target_username), None)
    elif update.message.reply_to_message:
        target_user_id = str(update.message.reply_to_message.from_user.id)
    else:
        await update.message.reply_text("Будь ласка, вкажіть користувача для поцілунку.")
        logger.warning("No target user specified.")
        return

    if not target_user_id:
        await update.message.reply_text("Користувача не знайдено.")
        logger.warning(f"Target user not found: {target_username}")
        return

    source_user_name = chat_stats.get(user_id, {}).get("name") or update.effective_user.first_name or update.effective_user.username
    target_user_name = chat_stats.get(target_user_id, {}).get("name") or update.message.reply_to_message.from_user.first_name or update.message.reply_to_message.from_user.username

    source_user_link = f"[{source_user_name}](tg://user?id={user_id})"
    target_user_link = f"[{target_user_name}](tg://user?id={target_user_id})"

    source_gender = chat_stats.get(user_id, {}).get("gender", None)
    if source_gender == "чоловік":
        response_message = f"{source_user_link} поцілував {target_user_link} 😘"
    elif source_gender == "жінка":
        response_message = f"{source_user_link} поцілувала {target_user_link} 😘"
    else:
        response_message = f"{source_user_link} поцілува(ла/в) {target_user_link} 😘"

    logger.info(f"Response message: {response_message}")

    if user_id in chat_stats and "kiss_skin_skin" in chat_stats[user_id]:
        kiss_skin = chat_stats[user_id]["kiss_skin_skin"]
        kiss_skin_path = os.path.join(KISS_SKINS_DIR, kiss_skin)
        logger.info(f"Kiss skin path: {kiss_skin_path}")

        if os.path.exists(kiss_skin_path):
            logger.info(f"Sending photo from path: {kiss_skin_path}")
            await update.message.reply_photo(photo=open(kiss_skin_path, 'rb'), caption=response_message, parse_mode='Markdown')
        else:
            logger.warning(f"Kiss skin path does not exist: {kiss_skin_path}")
            await update.message.reply_text(response_message, parse_mode='Markdown')
    else:
        logger.info("No kiss skin found, sending text response.")
        await update.message.reply_text(response_message, parse_mode='Markdown')
async def set_gender(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    user_id = str(update.effective_user.id)
    chat_stats = load_statistics(chat_id)

    if user_id not in chat_stats:
        await update.message.reply_text("У вас немає статистики.")
        return

    if len(context.args) != 1:
        await update.message.reply_text("Будь ласка, використовуйте формат: /set_gender <чоловік/жінка>")
        return

    gender = context.args[0].lower()
    if gender not in ["чоловік", "жінка"]:
        await update.message.reply_text("Невірний вибір статі. Доступні варіанти: чоловік, жінка.")
        return

    user_stats = chat_stats[user_id]
    if 'gender' in user_stats:
        balance = user_stats.get('currency', 0)
        if balance < 100:
            await update.message.reply_text("Недостатньо сяйва для зміни статі.")
            return
        user_stats['currency'] -= 100
    user_stats['gender'] = gender
    save_statistics(chat_id, chat_stats)

    await update.message.reply_text(f"Ваша стать була встановлена на {gender}.")


async def pin_message_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    # Check if the user is an admin
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("You do not have permission to use this command.")
        return

    # Check if the message is a reply to another message
    if not update.message.reply_to_message:
        await update.message.reply_text("Please use this command in reply to the message you want to pin.")
        return

    try:
        await context.bot.pin_chat_message(chat_id=update.effective_chat.id, message_id=update.message.reply_to_message.message_id)
        await update.message.reply_text("Message pinned successfully.")
    except Exception as e:
        await update.message.reply_text(f"Failed to pin message: {e}")


def command_filter(command):
    class CustomFilter(filters.MessageFilter):
        def filter(self, message):
            return message.text and message.text.lower().startswith(command)

    return CustomFilter()


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "Доступні команди:\n"
        "+година-година - у ВІДПОВІДЬ на графік. Додати себе до графіка на години від x до y, наприклад: +9-12 або -9-12\n"
        "+година - у ВІДПОВІДЬ на графік. Додати себе до графіка на вказану годину, наприклад: +9 або -9\n"
        "+година! - у ВІДПОВІДЬ на графік (зі ЗНАКОМ ОКЛИКУ в кінці. Додати годину до графіку та себе себе до графіка "
        "на вказані години, наприклад: +9! або -9! або +9-12!\n"
        "/today - Показати сьогоднішній графік\n"
        "/tomorrow - Показати завтрашній графік\n"
        "/default - Показати стандартний графік\n"
        "/weekday - Показати стандартний графік на будній день\n"
        "/weekend - Показати стандартний графік на вихідний день\n"
        "\n"
        "/stat - Показати статистику чату\n"
        "/my_stat - Показати вашу статистику\n"
        "/earn - Заробити сяйво✨ за вчорашню роботу\n"
        "/set_name - Встановити ваше ім'я\n"
        "/top_earners - Показати топ користувачів за кількістю сяйва✨\n"
        "/top_workers - Показати топ користувачів за кількістю годин\n"
        "/top_yesterday - Показати топ користувачів за кількістю годин за вчорашній день\n"
        "/shop - Показати магазин скинів\n"
        "/buy_skin назва_скину - Придбати скин\n"
        "/preview_skin назва_скину- Переглянути скин\n"
        "\n"
        "Для адмінів\n"
        "/reset_stat - Скинути статистику користувача\n"
        "/your_stat - Показати статистику іншого користувача\n"
        "/add_money - Додати сяйво✨ іншому користувачу\n"
        "/set_money - Встановити кількість сяйва✨ для користувача\n"
        "/set_skin - Встановити скин для користувача\n"
    )
    await update.message.reply_text(text)


def add_handlers(app):
    app.add_handler(CommandHandler("help", help_command))
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
    app.add_handler(CommandHandler("hug", hug_command))
    app.add_handler(CommandHandler("kiss", kiss_command))
    app.add_handler(CommandHandler("my_stat", my_stat))
    app.add_handler(CommandHandler("your_stat", your_stat))
    app.add_handler(CommandHandler("earn", earn))
    app.add_handler(CommandHandler("set_name", set_name))
    app.add_handler(CommandHandler("add_money", add_money_admin))
    app.add_handler(CommandHandler("set_money", set_money_admin))

    app.add_handler(CommandHandler("top_earners", top_earners))
    app.add_handler(CommandHandler("top_workers", top_workers))
    app.add_handler(CommandHandler("top", top_workers))
    app.add_handler(CommandHandler("top_yesterday", top_yesterday))
    app.add_handler(CommandHandler("top_workers_weekly", top_workers_weekly))
    app.add_handler(CommandHandler("top_week", top_week))
    app.add_handler(CommandHandler("top_last_week", top_last_week))
    app.add_handler(CommandHandler("top_month", top_month))
    app.add_handler(CommandHandler("top_last_month", top_last_month))
    app.add_handler(CommandHandler("top_custom_period", top_custom_period))

    app.add_handler(CommandHandler("shop", shop_command))
    app.add_handler(CommandHandler("buy_skin", buy_skin_command))
    app.add_handler(CommandHandler("preview_skin", preview_skin_command))
    app.add_handler(CommandHandler("set_skin", set_skin_admin))
    app.add_handler(CommandHandler("reset_stat", reset_stat_admin))
    app.add_handler(CommandHandler("change_skin", change_skin_command))
    app.add_handler(CommandHandler("set_gender", set_gender))

    app.add_handler(CommandHandler("pin", pin_message_admin))

    app.add_handler(MessageHandler(command_filter("стата"), all_stat))
    app.add_handler(MessageHandler(command_filter("обійняти"), hug_command))
    app.add_handler(MessageHandler(command_filter("цьом"), kiss_command))
    app.add_handler(MessageHandler(command_filter("моя стата"), my_stat))
    app.add_handler(MessageHandler(command_filter("твоя стата"), your_stat))
    app.add_handler(MessageHandler(command_filter("зп"), earn))
    app.add_handler(MessageHandler(command_filter("топ сяйва"), top_earners))
    app.add_handler(MessageHandler(command_filter("топ годин"), top_workers))
    app.add_handler(MessageHandler(command_filter("топ тиждень"), top_workers_weekly))
    app.add_handler(MessageHandler(command_filter("топ вчора"), top_yesterday))

    app.add_handler(MessageHandler(command_filter("магазин") | command_filter("шоп"), shop_command))
    app.add_handler(CallbackQueryHandler(shop_command, pattern=r'^shop\s\d+'))

    app.add_handler(MessageHandler(filters.Regex(r'^(так|ні)$') & ~filters.COMMAND, confirm_reset_stat_text))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r'^[+-]'), edit_schedule))

    app.add_handler(CommandHandler("start_gpt", start_chatbot))
    app.add_handler(CommandHandler("stop_gpt", stop_chatbot))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))


def main() -> None:
    signal.signal(signal.SIGINT, signal_handler)  # Handle signal
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    add_handlers(app)

    # Create scheduler
    scheduler = BackgroundScheduler()
    scheduler.add_job(update_schedules, 'cron', hour=0, minute=0, timezone=kyiv_tz)
    scheduler.start()
    # Run keep_alive in a separate thread
    threading.Thread(target=keep_alive, daemon=True).start()
    app.run_polling(poll_interval=1)


if __name__ == "__main__":
    main()
