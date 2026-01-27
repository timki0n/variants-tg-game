import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import TELEGRAM_BOT_TOKEN
from database import init_db
from handlers import setup_routers


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def main() -> None:
    """Головна функція запуску бота."""
    # Ініціалізуємо базу даних
    await init_db()
    logger.info("Database initialized")
    
    # Створюємо бота
    bot = Bot(
        token=TELEGRAM_BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    
    # Створюємо диспетчер та підключаємо роутери
    dp = Dispatcher()
    dp.include_router(setup_routers())
    
    # Запускаємо polling
    logger.info("Starting bot...")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
