import emoji
import re
import json
import os
import pytz
from datetime import datetime, timedelta
import logging
import copy

LOCK_FILE = 'bot.lock'
SCHEDULES_DIR = "schedules"
STATS_DIR = "stats"

if not os.path.exists(SCHEDULES_DIR):
    os.makedirs(SCHEDULES_DIR)

if not os.path.exists(STATS_DIR):
    os.makedirs(STATS_DIR)


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

def is_weekend(date):
    return date.weekday() in (5, 6)

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

def update_schedules():
    kyiv_tz = pytz.timezone('Europe/Kiev')
    today_date = datetime.now(kyiv_tz)
    tomorrow_date = today_date + timedelta(days=1)

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
                weekday = today_date.weekday()  # Це індекс дня тижня (0 для Понеділка і т.д.)
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


async def get_schedule_text(schedule, date_label, bot):
    text = f"Графік роботи Адміністраторів на {date_label}\n\n"

    for time_slot, user_ids in schedule.items():
        admins = []
        for user_id in user_ids:
            try:
                chat = await bot.get_chat(user_id)
                if chat.first_name:
                    admins.append(format_name(chat.first_name))
                else:
                    admins.append("–")
            except Exception:
                admins.append("unknown")

        admins_str = ' – '.join(admins) if admins else "–"
        text += f"{time_slot} – {admins_str}\n"

    return text