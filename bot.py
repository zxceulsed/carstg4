import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta
from db import init_db,get_custom_link,set_custom_link
import pytz
import logging
from aiogram.exceptions import TelegramBadRequest
import requests


TOKEN = "8572062250:AAFLkHQQPPCP8AlSWq5UR5LWRR2aOWopUtg"
CHAT_ID = -1003156926197

bot = Bot(token=TOKEN)
dp = Dispatcher()

moscow_tz = pytz.timezone("Europe/Moscow")
scheduler = AsyncIOScheduler(timezone=moscow_tz)

time_send = ["10:00","13:00","15:00","18:00","21:00"]

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from parser import get_random_cars, parse_single_car

@dp.message(Command("start"))
async def start(message: types.Message):
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🚘 Опубликовать пост")]
        ],
        resize_keyboard=True
    )
    await message.answer("Привет! Нажми кнопку, чтобы опубликовать объявление.", reply_markup=keyboard)


@dp.message(lambda m: m.text == "🚘 Опубликовать пост")
async def ask_link(message: types.Message):
    await message.answer("Отправь ссылку на объявление вида:\nhttps://cars.av.by/opel/astra/119900734")

@dp.message(lambda m: m.text.startswith("https://cars.av.by/"))
async def handle_link(message: types.Message):

    car = parse_single_car(message.text)
    print("DEBUG CAR =", car)
    print("Type =", type(car))
    caption = format_post(car)

    if car["photos"]:
        media = []
        for idx, url in enumerate(car["photos"][:10]):
            if idx == 0:
                media.append(types.InputMediaPhoto(media=url, caption=caption.strip(), parse_mode="HTML"))
            else:
                media.append(types.InputMediaPhoto(media=url))
        await bot.send_media_group(chat_id=CHAT_ID, media=media)
        await message.answer('опубликовано')
    else:
        await bot.send_message(chat_id=CHAT_ID, text=caption.strip(), parse_mode="HTML")

@dp.message(Command("ping"))
async def set_link_command(message: types.Message):
    try:
        r = requests.get("https://av.by/", timeout=5)
        if r.status_code == 200:
            await message.answer("✅ av.by доступен")
        else:
            await message.answer(f"⚠️ Статус: {r.status_code}")
    except Exception:
        await message.answer("❌ av.by недоступен")

@dp.message(Command("setlink"))
async def set_link_command(message: types.Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].startswith("https://"):
        await message.answer("❌ Использование: /setlink <ссылка на av.by>")
        return

    link = parts[1].strip()
    await set_custom_link(link)
    await message.answer(f"✅ Ссылка успешно обновлена:\n{link}")


@dp.message(Command("next"))
async def next_time(message: types.Message):
    now = datetime.now(moscow_tz)
    today_times = []

    for t in time_send:
        h, m = map(int, t.split(":"))
        candidate = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if candidate < now:
            candidate += timedelta(days=1)  # перенос на завтра
        today_times.append(candidate)

    nearest = min(today_times)
    await message.answer(f"⏳ Следующая рассылка в {nearest.strftime('%d.%m %H:%M')} (МСК)")

async def send_ad():
    MAX_RETRIES = 3

    for attempt in range(MAX_RETRIES):
        try:
            custom_link = await get_custom_link()

            if custom_link:
                cars = await get_random_cars(count=1, base_url=custom_link)
            else:
                cars = await get_random_cars(count=1)

            if not cars:
                print("❌ Не удалось получить объявления")
                return

            car = cars[0]
            caption = car["message"] + f"<a href='{car['link']}'>Контакт продавца</a>"

            # Ограничиваем caption, если он слишком длинный (>1024 символа)
            if len(caption) > 1024:
                caption = caption[:1020] + "..." + f"<a href='{car['link']}'>Контакт продавца</a>"

            if car["photos"]:
                media = []
                for idx, url in enumerate(car["photos"][:10]):
                    if idx == 0:
                        media.append(
                            types.InputMediaPhoto(
                                media=url,
                                caption=caption.strip(),
                                parse_mode="HTML"
                            )
                        )
                    else:
                        media.append(types.InputMediaPhoto(media=url))
                await bot.send_media_group(chat_id=CHAT_ID, media=media)
            else:
                await bot.send_message(chat_id=CHAT_ID, text=caption.strip(), parse_mode="HTML")

            print("✅ Объявление успешно отправлено")
            return  # успех — выходим из цикла

        except TelegramBadRequest as e:
            # если ошибка caption слишком длинный — пробуем другое авто
            if "message caption is too long" in str(e):
                print(f"⚠️ Слишком длинный caption, пробую другое объявление ({attempt+1}/{MAX_RETRIES})...")
                await asyncio.sleep(1)
                continue
            else:
                print(f"⚠️ TelegramBadRequest: {e}")
                break

        except Exception as e:
            logging.exception(f"❌ Ошибка при отправке объявления (попытка {attempt+1}/{MAX_RETRIES}): {e}")
            await asyncio.sleep(2)
            continue

    print("❌ Не удалось отправить объявление после нескольких попыток.")

def format_post(car):
    return f"""
🚗 {car['title']}  📅 {car['year']}
🛣 {car['mileage']}  |⛽️ {car['engine_info']}
📦 {car['gearbox']} |⚙️ {car['drive']}
📍 {car['location']}
💰 {car['price']}

{car['description']}

<a href="{car['link']}">Контакт продавца</a>
""".strip()

async def main():
    for t in time_send:
        h, m = map(int, t.split(":"))
        scheduler.add_job(send_ad, "cron", hour=h, minute=m, name=f"Рассылка {t}", timezone=moscow_tz)

    await init_db()
    scheduler.start()
    print("✅ Планировщик запущен по московскому времени")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
