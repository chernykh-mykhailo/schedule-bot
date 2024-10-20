Тут код:


```python'
async def track_user_presence(context: ContextTypes.DEFAULT_TYPE):
    kyiv_tz = pytz.timezone('Europe/Kiev')
    today_date = datetime.now(kyiv_tz)
    schedule_files = [f for f in os.listdir(SCHEDULES_DIR) if f.endswith("_today.json")]

    for file_name in schedule_files:
        chat_id = file_name.split("_")[0]
        schedule = load_schedule(chat_id, "today", empty_weekday, empty_weekend)
        schedule_message_id = await find_schedule_message_id(context, chat_id, today_date.strftime("%d.%m.%Y"))

        now = datetime.now(pytz.timezone('Europe/Kyiv'))
        current_hour = now.strftime('%H:00')

        if current_hour in schedule and schedule[current_hour]:
            scheduled_users = schedule[current_hour]  # Users scheduled for the current hour
            remaining_users = scheduled_users.copy()  # Copy the list of users
            absent_users = []  # List of absent users

            # Get the schedule message for today
            today_schedule_message = await context.bot.get_message(chat_id, schedule_message_id)

            # Check for "here" messages within the first 10 minutes of the hour
            while now.minute >= 0 and now.minute <= 10:
                for scheduled_user in scheduled_users:
                    def message_filter(message):
                        return message.text.lower() == "тут" and message.from_user.username == scheduled_user

                    try:
                        # Wait for "here" from each user for 1 minute
                        message = await context.bot.wait_for_message(filters=message_filter, timeout=60)
                        if message:
                            # If the user is present, update the schedule
                            updated_text = f"{today_schedule_message.text}\n{scheduled_user} присутній ?"
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
                updated_text = f"{today_schedule_message.text}\n" + "\n".join([f"{user} відсутній ?" for user in absent_users])
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=schedule_message_id,
                    text=updated_text
                )

            # Update the schedule for the current hour
            schedule[current_hour] = remaining_users
            save_schedule(chat_id, "today", schedule)
```