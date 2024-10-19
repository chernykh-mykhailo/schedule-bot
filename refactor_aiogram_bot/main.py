import asyncio

from bot import MyBot

async def main():
    bot = MyBot()
    await bot.start_polling()

if __name__ == "__main__":
    asyncio.run(main())
