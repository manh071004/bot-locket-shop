"""
Bot Engine - Telegram Bot SaaS
Chạy 1 bot trung tâm, phục vụ nhiều cửa hàng qua Deep Link.
"""
import asyncio
import logging
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from config import BOT_TOKEN
from handlers.start import start_handler, main_menu_handler
from handlers.catalog import catalog_handler, product_detail_handler
from handlers.cart import cart_handler, cart_action_handler
from handlers.checkout import checkout_handler, checkout_action_handler
from handlers.admin import admin_handler

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def create_application() -> Application:
    app = Application.builder().token(BOT_TOKEN).build()

    # Handlers
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("menu", main_menu_handler))

    # Callback query handlers (inline keyboard buttons)
    app.add_handler(CallbackQueryHandler(catalog_handler, pattern=r"^cat_"))
    app.add_handler(CallbackQueryHandler(product_detail_handler, pattern=r"^prod_"))
    app.add_handler(CallbackQueryHandler(cart_action_handler, pattern=r"^cart_"))
    app.add_handler(CallbackQueryHandler(checkout_handler, pattern=r"^checkout_"))
    app.add_handler(CallbackQueryHandler(checkout_action_handler, pattern=r"^pay_"))
    app.add_handler(CallbackQueryHandler(admin_handler, pattern=r"^admin_"))
    app.add_handler(CallbackQueryHandler(main_menu_handler, pattern=r"^home$"))

    # Text message handler (fallback)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, main_menu_handler))

    return app


def main():
    logger.info("🤖 Starting Bot Engine...")
    application = create_application()
    application.run_polling(drop_pending_updates=True)
    logger.info("✅ Bot is running!")


if __name__ == "__main__":
    main()
