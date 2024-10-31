from apscheduler.schedulers.asyncio import AsyncIOScheduler
from utils import update_schedules

scheduler = AsyncIOScheduler()

def start_scheduler():
    scheduler.add_job(update_schedules, 'cron', hour=0, minute=0, timezone='Europe/Kiev')
    scheduler.start()
