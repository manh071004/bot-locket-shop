"""
Admin handler: Các lệnh dành cho chủ cửa hàng.
Callback pattern: admin_{action}
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from db_helper import get_orders_by_customer


async def admin_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Tính năng đang phát triển...")
