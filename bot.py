import emoji
import re
import asyncio
import copy
import json
import logging
import os
import threading
import time
from datetime import datetime, timedelta

import pytz  # Додати для роботи з часовими поясами
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.error import BadRequest

from config import TELEGRAM_TOKEN  # Імпорт токену з конфігураційного файлу


def keep_alive():
    while True:
        print("Bot is still running...")
        time.sleep(1800)  # 1800 секунд = 30 хвилин


# Функція для видалення емодзі
def remove_emoji(text):
    return emoji.replace_emoji(text, replace='')


def format_name(name):
    # Зберігаємо перший емодзі
    first_emoji = ''
    for c in name:
        if emoji.is_emoji(c):
            first_emoji = c  # Зберігаємо перший емодзі
            break  # Зупиняємося, як тільки знайшли перший емодзі

    # Видаляємо всі емодзі з імені
    clean_name = remove_emoji(name).strip()

    # Перевіряємо наявність дужок
    if '(' in clean_name:
        # Обрізаємо до закритої дужки
        match = re.search(r'[^()]*\)', clean_name)
        if match:
            clean_name = clean_name[:match.end()].strip()  # Обрізаємо до закритої дужки
    else:
        # Обрізаємо на першому пробілі, якщо дужок немає
        match = re.search(r'([^ ]+)', clean_name)
        if match:
            clean_name = match.group(1).strip()  # Обрізаємо на першому пробілі

    # Повертаємо ім'я з першим емодзі без пробілів
    return f"{first_emoji}{clean_name}".strip() if first_emoji else clean_name.strip()
# Приклад використання
example_name_1 = "🌙Мишко яке найдовше ім'я можна собі придумати, га? Трішки більше"
example_name_2 = "Аарон(а хулі нє)?"

formatted_name_1 = format_name(example_name_1)
formatted_name_2 = format_name(example_name_2)

print(formatted_name_1)  # Виведе: "🌙Мишко"
print(formatted_name_2)  # Виведе: "Аарон(а хулі нє)?"




# Налаштування логування
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

logger = logging.getLogger(__name__)

# Імена файлів для графіків
TODAY_SCHEDULE_FILE = "today_schedule.json"
TOMORROW_SCHEDULE_FILE = "tomorrow_schedule.json"
DEFAULT_SCHEDULE_FILE = "default_schedule.json"


# Завантажити графік з файлів або ініціалізувати їх
def load_schedule(file_name, default_schedule=None):
    if os.path.exists(file_name):
        with open(file_name, 'r', encoding='utf-8') as f:
            return json.load(f)
    return default_schedule if default_schedule else {}


# Зберегти графік у файл
def save_schedule(file_name, schedule):
    with open(file_name, 'w', encoding='utf-8') as f:
        json.dump(schedule, f, ensure_ascii=False, indent=4)


# Ініціалізація стандартного графіку
empty_schedule = {
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
    "00:00 - 01:00": [],
}

# Завантажити графіки на сьогодні і завтра
today_schedule = copy.deepcopy(load_schedule(TODAY_SCHEDULE_FILE, empty_schedule))
tomorrow_schedule = copy.deepcopy(load_schedule(TOMORROW_SCHEDULE_FILE, empty_schedule))
default_schedule = copy.deepcopy(load_schedule(DEFAULT_SCHEDULE_FILE, empty_schedule))


# Функція для оновлення графіків на новий день
def update_schedules():
    global today_schedule, tomorrow_schedule
    # Графік на сьогодні стає графіком на завтра
    today_schedule = copy.deepcopy(tomorrow_schedule)
    # Новий графік на завтра - це стандартний графік
    tomorrow_schedule = copy.deepcopy(default_schedule)

    # Зберегти оновлені графіки
    save_schedule(TODAY_SCHEDULE_FILE, today_schedule)
    save_schedule(TOMORROW_SCHEDULE_FILE, tomorrow_schedule)


def process_hours(input_range):
    hours = input_range.split('-')

    # Переконайтеся, що у вас два значення
    if len(hours) != 2:
        return "Будь ласка, введіть правильний час (формат: x-y)."

    try:
        start_hour = int(hours[0]) % 24  # Перетворюємо на 24-годинний формат
        end_hour = int(hours[1]) % 24
    except ValueError:
        return "Будь ласка, введіть правильний час (тільки числа)."

    time_slots = []

    # Обробка переходу через північ
    if start_hour <= end_hour:
        for hour in range(start_hour, end_hour + 1):
            next_hour = (hour + 1) % 24
            time_slot = f"{hour:02d}:00 - {next_hour:02d}:00"
            time_slots.append(time_slot)
    else:
        # Обробка часових слотів при переході через північ
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


# Функція для початку розмови
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    logging.info(f"Starting conversation with user: {user.first_name}")
    await update.message.reply_text(
        "Вітаємо! Використовуйте команди /today для сьогоднішнього графіка, /tomorrow для завтрашнього, та /default для стандартного графіка.")


async def mechanical_update_shcedules(update: Update, contextcontest: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Графік змінено", update_schedules())


# Функція для показу сьогоднішнього графіку
async def show_today_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = await get_schedule_text(today_schedule, datetime.now(pytz.timezone('Europe/Kiev')).strftime("%d.%m.%Y"),
                                   context)
    await update.message.reply_text(text)


# Функція для показу завтрашнього графіку
async def show_tomorrow_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = await get_schedule_text(tomorrow_schedule,
                                   (datetime.now(pytz.timezone('Europe/Kiev')) + timedelta(days=1)).strftime(
                                       "%d.%m.%Y"), context)
    await update.message.reply_text(text)


# Функція для показу стандартного графіку
async def show_default_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = await get_schedule_text(default_schedule, "стандартний графік", context)
    await update.message.reply_text(text)


# Функція для редагування графіків
async def edit_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message.text.strip()

    # Перевірка на формат +цифри чи -цифри
    if not (message.startswith('+') or message.startswith('-')):
        return  # Якщо повідомлення не містить + або -, ігноруємо його

    user_id = update.effective_user.id
    user_name = update.effective_user.first_name or update.effective_user.username
    message = update.message.text.strip()

    # Витягуємо графік
    if update.message.reply_to_message:
        reply_text = update.message.reply_to_message.text

        # Перевірка стандартного графіка
        if "Графік роботи Адміністраторів на стандартний графік" in reply_text:
            schedule = default_schedule  # Якщо це стандартний графік
        elif "Графік роботи Адміністраторів на " in reply_text:
            schedule_date = update.message.reply_to_message.text.split('на ')[1].strip().split()[0]
            current_date = datetime.now(pytz.timezone('Europe/Kiev')).strftime("%d.%m.%Y")
            tomorrow_date = (datetime.now(pytz.timezone('Europe/Kiev')) + timedelta(days=1)).strftime("%d.%m.%Y")

            # Перевіряємо, який саме графік змінюємо
            if schedule_date == current_date:
                schedule = today_schedule  # Зміна лише сьогоднішнього графіка
            elif schedule_date == tomorrow_date:
                schedule = tomorrow_schedule  # Зміна лише завтрашнього графіка
            else:
                #                await update.message.reply_text("Це не графік. Спробуйте ще раз.")
                return
        else:
            #            await update.message.reply_text("Ви повинні відповісти на повідомлення про графік.")
            return
    else:
        #        await update.message.reply_text("Ви повинні відповісти на повідомлення про графік.")
        return

    # Витягуємо дії з команди
    operation = 'remove' if message[0] == '-' else 'add'
    hours_range = message[1:].strip()  # Отримуємо години без знака

    updated_hours = []
    if '+' in hours_range:  # Додаємо обробку символа +
        hour = int(hours_range[1:])
        time_slot = f"{hour:02d}:00 - {hour + 1:02d}:00" if hour < 23 else "23:00 - 00:00"
        if operation == 'add':
            if user_id not in schedule[time_slot]:
                schedule[time_slot].append(user_id)
                updated_hours.append(time_slot)
        elif operation == 'remove':
            if user_id in schedule[time_slot]:
                schedule[time_slot].remove(user_id)
                updated_hours.append(time_slot)

        # Логіка для обробки діапазону годин
    if '-' in hours_range:
        # Handle the range input
        try:
            start_hour, end_hour = map(int, hours_range.split('-'))

            # Adjust for negative inputs (e.g., -22 means from 22:00 to 00:00)
            if start_hour < 0:
                start_hour += 24
            if end_hour < 0:
                end_hour += 24

            if start_hour < 0 or end_hour > 24 or start_hour >= end_hour:
                await update.message.reply_text("Будь ласка, введіть правильний час (9-24).\n ")
                return

            for hour in range(start_hour, end_hour):
                # Обробка години 24
                if hour == 23:
                    time_slot = f"{hour:02d}:00 - 00:00"
                else:
                    time_slot = f"{hour:02d}:00 - {hour + 1:02d}:00"

                if operation == 'add':
                    if user_id not in schedule[time_slot]:
                        schedule[time_slot].append(user_id)
                        updated_hours.append(time_slot)  # Зберігаємо оновлені години
                elif operation == 'remove':
                    if user_id in schedule[time_slot]:
                        schedule[time_slot].remove(user_id)
                        updated_hours.append(time_slot)  # Зберігаємо оновлену годину
        except ValueError:
            await update.message.reply_text("Будь ласка, введіть правильний час (9-24).")
            return
    else:
        # Логіка для обробки одного часу
        try:
            hour = int(hours_range)

            # Adjust for negative inputs (e.g., -22 means 22:00 to 00:00)
            if hour < 0:
                hour += 24

            # Заміна +24 на 00
            if hour == 24:
                hour = 0

            time_slot = f"{hour:02d}:00 - {hour + 1:02d}:00"

            # Обробка години 24
            if hour == 23:
                time_slot = f"{hour:02d}:00 - 00:00"

            if operation == 'add':
                if user_id not in schedule[time_slot]:
                    schedule[time_slot].append(user_id)
                    updated_hours.append(time_slot)  # Зберігаємо оновлену годину
            elif operation == 'remove':
                if user_id in schedule[time_slot]:
                    schedule[time_slot].remove(user_id)
                    updated_hours.append(time_slot)  # Зберігаємо оновлену годину
        except ValueError:
            await update.message.reply_text("Будь ласка, введіть правильний час (9-24).")
            return

    # Оновлення графіка у файлі
    if schedule is today_schedule:
        save_schedule(TODAY_SCHEDULE_FILE, today_schedule)
    elif schedule is tomorrow_schedule:
        save_schedule(TOMORROW_SCHEDULE_FILE, tomorrow_schedule)
    elif schedule is default_schedule:
        save_schedule(DEFAULT_SCHEDULE_FILE, default_schedule)

    # Формування повідомлення
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

    # Формування оновленого графіка
    if schedule is today_schedule:
        date_label = datetime.now(pytz.timezone('Europe/Kiev')).strftime("%d.%m.%Y")
    elif schedule is tomorrow_schedule:
        date_label = (datetime.now(pytz.timezone('Europe/Kiev')) + timedelta(days=1)).strftime("%d.%m.%Y")
    else:
        date_label = "стандартний графік"

    updated_schedule_message = f"Графік роботи Адміністраторів на {date_label}\n\n"
    for time_slot in schedule:
        users = schedule[time_slot]

        # Список асинхронних завдань для отримання імен користувачів
        user_name_tasks = [context.bot.get_chat_member(chat_id=update.effective_chat.id, user_id=user) for user in
                           users]

        # Очікуємо результати
        user_names_results = await asyncio.gather(*user_name_tasks)

        # Отримуємо імена користувачів
        user_names = ' – '.join([format_name(member.user.first_name) for member in user_names_results]) or "–"
        updated_schedule_message += f"{time_slot}: {user_names}\n"

    # Редагуємо старе повідомлення
    try:
        await update.message.reply_to_message.edit_text(updated_schedule_message + '\n' + response_message)
    except Exception as e:
        await update.message.reply_text("Не вдалося редагувати повідомлення. Спробуйте ще раз.")
        print(e)


# Командні обробники
def main() -> None:
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Оновити графіки в 00:00
    # if datetime.now(pytz.timezone('Europe/Kiev')).hour == 0:
    # update_schedules()

    # Запуск функції keep_alive в окремому потоці

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("today", show_today_schedule))
    app.add_handler(CommandHandler("tomorrow", show_tomorrow_schedule))
    app.add_handler(CommandHandler("default", show_default_schedule))  # Додаємо команду для стандартного графіку
    app.add_handler(CommandHandler("update", mechanical_update_shcedules))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, edit_schedule))

    threading.Thread(target=keep_alive, daemon=True).start()

    app.run_polling()


if __name__ == '__main__':
    main()
