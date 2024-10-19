To diagnose why only the schedule-related commands and `/update` are working, let's ensure the following:

1. **Command Registration**: Ensure all commands are registered in the `set_commands` method.
2. **Handler Registration**: Ensure handlers for all commands are added to the dispatcher.
3. **Command Logic**: Verify the logic inside the command functions.

### Step 1: Ensure Command Registration
Make sure all commands are included in the `set_commands` method in `alfa_bot/bot.py`.

```python
async def set_commands(self):
    commands = [
        BotCommand(command="start", description="Start the bot"),
        BotCommand(command="help", description="Get help"),
        BotCommand(command="today", description="Show today's schedule"),
        BotCommand(command="tomorrow", description="Show tomorrow's schedule"),
        BotCommand(command="default", description="Show default schedule"),
        BotCommand(command="weekday", description="Show weekday default schedule"),
        BotCommand(command="weekend", description="Show weekend default schedule"),
        BotCommand(command="update", description="Update schedules"),
        BotCommand(command="leavethisgroup", description="Leave this group"),
        BotCommand(command="leave", description="Leave"),
        BotCommand(command="stat", description="Show chat statistics"),
        BotCommand(command="mystat", description="Show my statistics"),
        BotCommand(command="edit_schedule", description="Edit schedule"),
    ]
    await self.bot.set_my_commands(commands)
```

### Step 2: Ensure Handler Registration
Make sure the handlers for all commands are added to the dispatcher in `alfa_bot/main.py`.

```python
def main() -> None:
    signal.signal(signal.SIGINT, signal_handler)  # Handle signal
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("today", show_today_schedule))
    app.add_handler(CommandHandler("tomorrow", show_tomorrow_schedule))
    app.add_handler(CommandHandler("default", show_default_schedule))
    app.add_handler(CommandHandler("weekday", show_weekday_default_schedule))
    app.add_handler(CommandHandler("weekend", show_weekend_default_schedule))
    app.add_handler(CommandHandler("update", mechanical_update_schedules))
    app.add_handler(CommandHandler("leavethisgroup", leave_username))
    app.add_handler(CommandHandler("leave", leave))
    app.add_handler(CommandHandler("stat", stat))
    app.add_handler(CommandHandler("mystat", mystat))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, edit_schedule))

    # Create scheduler
    scheduler = BackgroundScheduler()
    kyiv_tz = pytz.timezone('Europe/Kiev')
    scheduler.add_job(update_schedules, 'cron', hour=0, minute=0, timezone=kyiv_tz)
    scheduler.start()

    # Run keep_alive in a separate thread
    threading.Thread(target=keep_alive, daemon=True).start()

    app.run_polling(poll_interval=1)
```

### Step 3: Verify Command Logic
Ensure the logic inside the command functions is correct. Here are the simplified versions of the functions:

```python
@router.message(Command("start"))
async def start(message: Message):
    user = message.from_user
    logging.info(f"Starting conversation with user: {user.first_name}")
    await message.reply(
        "Вітаємо! Використовуйте команди /today для сьогоднішнього графіка, "
        "/tomorrow для завтрашнього, та /default для стандартного графіка.")

@router.message(Command("help"))
async def help_command(message: Message):
    help_text = (
        "/start - Start the bot\n"
        "/help - Get help\n"
        "/today - Show today's schedule\n"
        "/tomorrow - Show tomorrow's schedule\n"
        "/default - Show default schedule\n"
        "/weekday - Show weekday default schedule\n"
        "/weekend - Show weekend default schedule\n"
        "/update - Update schedules\n"
        "/leavethisgroup - Leave this group\n"
        "/leave - Leave\n"
        "/stat - Show chat statistics\n"
        "/mystat - Show my statistics\n"
        "/edit_schedule - Edit schedule"
    )
    await message.reply(help_text)

@router.message(Command("stat"))
async def stat(message: Message):
    chat_id = message.chat.id
    stats = load_statistics(chat_id)
    stats_text = json.dumps(stats, indent=4, ensure_ascii=False)
    await message.reply(f"Chat statistics:\n{stats_text}")

@router.message(Command("mystat"))
async def mystat(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    stats = load_statistics(chat_id)
    user_stats = stats.get(str(user_id), {})
    user_stats_text = json.dumps(user_stats, indent=4, ensure_ascii=False)
    await message.reply(f"Your statistics:\n{user_stats_text}")
```

By ensuring these steps, all commands should work as expected.