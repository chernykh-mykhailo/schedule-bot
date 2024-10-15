# utils.py
import emoji
import re
import os
import json
from aiogram import Bot
from datetime import datetime
from config import SCHEDULES_DIR

class ScheduleManager:
    def __init__(self, schedules_dir=SCHEDULES_DIR):
        self.schedules_dir = schedules_dir

    def load_schedule(self, chat_id, schedule_type):
        file_path = os.path.join(self.schedules_dir, f"{chat_id}_{schedule_type}.json")
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

def load_schedule():
    return ScheduleManager()

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

async def get_schedule_text(schedule, date_label, bot: Bot):
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
