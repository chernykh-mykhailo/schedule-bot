# schedules.py
import os
import json
from datetime import datetime, timedelta
import pytz
from config import SCHEDULES_DIR

class ScheduleManager:
    def __init__(self):
        if not os.path.exists(SCHEDULES_DIR):
            os.makedirs(SCHEDULES_DIR)
        self.empty_weekday = {
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
        self.empty_weekend = {
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

    def get_schedule_file_name(self, chat_id, schedule_type):
        return os.path.join(SCHEDULES_DIR, f"{chat_id}_{schedule_type}.json")

    def load_schedule(self, chat_id, schedule_type):
        file_name = self.get_schedule_file_name(chat_id, schedule_type)
        if os.path.exists(file_name):
            with open(file_name, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            return self._get_default_schedule(schedule_type)

    def save_schedule(self, chat_id, schedule_type, schedule):
        file_name = self.get_schedule_file_name(chat_id, schedule_type)
        with open(file_name, 'w', encoding='utf-8') as f:
            json.dump(schedule, f, ensure_ascii=False, indent=4)

    def _get_default_schedule(self, schedule_type):
        if schedule_type == "weekday_default":
            return self.empty_weekday
        elif schedule_type == "weekend_default":
            return self.empty_weekend
        else:
            kyiv_tz = pytz.timezone('Europe/Kiev')
            today = datetime.now(kyiv_tz).weekday()
            if schedule_type == "today":
                return self.empty_weekday if today < 5 else self.empty_weekend
            elif schedule_type == "tomorrow":
                tomorrow = (datetime.now(kyiv_tz) + timedelta(days=1)).weekday()
                return self.empty_weekday if tomorrow < 5 else self.empty_weekend
            else:
                return self.empty_weekday if today < 5 else self.empty_weekend
