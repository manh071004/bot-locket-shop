"""
Bot Engine - Telegram Bot SaaS
Chạy 1 bot trung tâm, phục vụ nhiều cửa hàng qua Deep Link.
"""
import asyncio
import logging
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from config import BOT_TOKEN
from handlers.start import (
    start_handler, main_menu_handler, plan_callback_handler, bottom_menu_handler
)
from handlers.catalog import catalog_handler, product_detail_handler
from handlers.cart import cart_handler, cart_action_handler
from handlers.checkout import (
    checkout_handler, checkout_action_handler,
    customer_paid_handler, approve_order_handler, reject_order_handler
)
from handlers.admin import admin_handler, admin_command_handler, admin_auth_handler

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def create_application() -> Application:
    app = Application.builder().token(BOT_TOKEN).build()

    # Lệnh khởi động & Quản trị
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("menu", start_handler))
    app.add_handler(CommandHandler("admin", admin_command_handler))
    app.add_handler(CommandHandler("admin_stores", admin_command_handler))
    app.add_handler(CommandHandler("admin_auth", admin_auth_handler))

    # Callback query handlers (chọn gói, chọn sản phẩm, giỏ hàng, thanh toán, duyệt đơn)
    app.add_handler(CallbackQueryHandler(plan_callback_handler, pattern=r"^(buy_plan_|paid_check_|show_plans|owner_|support_store_|reply_cust_|btn_|link_admin_acc_|admin_test_|admin_quick_link)"))
    app.add_handler(CallbackQueryHandler(catalog_handler, pattern=r"^cat_"))
    app.add_handler(CallbackQueryHandler(product_detail_handler, pattern=r"^prod_"))
    app.add_handler(CallbackQueryHandler(cart_action_handler, pattern=r"^cart_"))
    app.add_handler(CallbackQueryHandler(checkout_handler, pattern=r"^checkout_"))
    app.add_handler(CallbackQueryHandler(checkout_action_handler, pattern=r"^pay_"))
    app.add_handler(CallbackQueryHandler(customer_paid_handler, pattern=r"^order_paid_"))
    app.add_handler(CallbackQueryHandler(approve_order_handler, pattern=r"^approve_order_"))
    app.add_handler(CallbackQueryHandler(reject_order_handler, pattern=r"^reject_order_"))
    app.add_handler(CallbackQueryHandler(admin_handler, pattern=r"^admin_"))
    app.add_handler(CallbackQueryHandler(main_menu_handler, pattern=r"^home$"))


    # Bắt sự kiện bấm nút bàn phím Menu dưới đáy màn hình
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bottom_menu_handler))

    return app


def main():
    logger.info("🤖 Starting Bot Engine...")
    application = create_application()
    application.run_polling(drop_pending_updates=True)
    logger.info("✅ Bot is running!")


if __name__ == "__main__":
    main()
