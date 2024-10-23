import os
from aiogram import Bot, Dispatcher, types
from aiogram.types import InputMediaPhoto, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor
from config import TELEGRAM_TOKEN

SKINS_DIR = 'path/to/skins'
SKINS_PER_PAGE = 5

bot = Bot(TELEGRAM_TOKEN)
dp = Dispatcher(bot)

def get_skin_page(page_number):
    skins = os.listdir(SKINS_DIR)
    total_skins = len(skins)
    start = page_number * SKINS_PER_PAGE
    end = start + SKINS_PER_PAGE
    return skins[start:end], total_skins

@dp.message_handler(commands=['store'])
async def store_command(message: types.Message):
    page_number = int(message.get_args()) if message.get_args() else 0
    skins, total_skins = get_skin_page(page_number)
    total_pages = (total_skins + SKINS_PER_PAGE - 1) // SKINS_PER_PAGE

    media_group = []
    for skin in skins:
        skin_image_path = os.path.join(SKINS_DIR, skin)
        if os.path.exists(skin_image_path):
            media_group.append(InputMediaPhoto(open(skin_image_path, 'rb'), caption=skin))

    if media_group:
        await message.answer_media_group(media_group)

    keyboard = InlineKeyboardMarkup(row_width=2)
    for skin in skins:
        keyboard.add(InlineKeyboardButton(f"Buy {skin}", callback_data=f"buy_{skin}"))

    if page_number > 0:
        keyboard.add(InlineKeyboardButton("Previous", callback_data=f"store_{page_number - 1}"))
    if page_number < total_pages - 1:
        keyboard.add(InlineKeyboardButton("Next", callback_data=f"store_{page_number + 1}"))

    await message.answer("Choose an action:", reply_markup=keyboard)

@dp.callback_query_handler(lambda c: c.data and c.data.startswith('store_'))
async def process_store_callback(callback_query: types.CallbackQuery):
    page_number = int(callback_query.data.split('_')[1])
    await store_command(callback_query.message)

@dp.callback_query_handler(lambda c: c.data and c.data.startswith('buy_'))
async def process_buy_callback(callback_query: types.CallbackQuery):
    skin_name = callback_query.data.split('_')[1]
    await callback_query.message.answer(f"You have bought the skin: {skin_name}")

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)