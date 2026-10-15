"""
Handler /start: Nhận deep link, load cửa hàng, hiển thị menu chính.
Deep link format: t.me/BOT?start=store_SLUG
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from db_helper import get_store_by_slug, get_categories_by_store, get_products_by_store
from cart_store import set_user_store, get_user_store, get_cart_count
import asyncio


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args  # ["store_SLUG"] hoặc []

    # Xử lý deep link
    if args:
        arg = args[0]
        if arg.startswith("store_"):
            slug = arg[len("store_"):]
            store = await get_store_by_slug(slug)
            if store:
                set_user_store(user.id, slug)
                await show_store_home(update, context, store)
                return

    # Không có deep link → hiển thị trang giới thiệu dịch vụ
    await show_service_intro(update)


async def main_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Quay về menu chính của store đang dùng."""
    user = update.effective_user
    slug = get_user_store(user.id)
    if not slug:
        await update.effective_message.reply_text(
            "❌ Vui lòng dùng link cửa hàng để vào mua sắm!"
        )
        return

    store = await get_store_by_slug(slug)
    if not store:
        await update.effective_message.reply_text("❌ Cửa hàng không tìm thấy!")
        return

    if update.callback_query:
        await update.callback_query.answer()
        await show_store_home_edit(update, context, store)
    else:
        await show_store_home(update, context, store)


async def show_store_home(update: Update, context: ContextTypes.DEFAULT_TYPE, store: dict):
    """Hiển thị trang chủ cửa hàng."""
    user = update.effective_user
    categories = await get_categories_by_store(store["id"])
    cart_count = get_cart_count(user.id, store["store_slug"])

    keyboard = []
    # Các nút danh mục
    for cat in categories:
        keyboard.append([InlineKeyboardButton(
            f"{cat['emoji'] or '🛍️'} {cat['name']}",
            callback_data=f"cat_{store['id']}_{cat['id']}"
        )])

    # Nút xem tất cả nếu không có danh mục
    if not categories:
        keyboard.append([InlineKeyboardButton(
            "🛍️ Xem tất cả sản phẩm",
            callback_data=f"cat_{store['id']}_0"
        )])

    # Nút giỏ hàng và đơn hàng
    bottom_row = []
    cart_text = f"🛒 Giỏ hàng ({cart_count})" if cart_count > 0 else "🛒 Giỏ hàng"
    bottom_row.append(InlineKeyboardButton(cart_text, callback_data=f"cart_view_{store['store_slug']}"))
    bottom_row.append(InlineKeyboardButton("📋 Đơn hàng", callback_data=f"cart_orders_{store['store_slug']}"))
    keyboard.append(bottom_row)

    if store.get("support_contact"):
        keyboard.append([InlineKeyboardButton(
            "💬 Liên hệ hỗ trợ",
            url=f"https://t.me/{store['support_contact'].lstrip('@')}"
        )])

    reply_markup = InlineKeyboardMarkup(keyboard)
    welcome = store.get("welcome_message") or f"👋 Chào mừng đến {store['store_name']}!"

    text = (
        f"🏪 <b>{store['store_name']}</b>\n\n"
        f"{welcome}\n\n"
        f"📦 Chọn danh mục để xem sản phẩm:"
    )

    if store.get("logo_url"):
        try:
            await update.message.reply_photo(
                photo=store["logo_url"],
                caption=text,
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
            return
        except Exception:
            pass

    await update.message.reply_text(text, parse_mode="HTML", reply_markup=reply_markup)


async def show_store_home_edit(update: Update, context: ContextTypes.DEFAULT_TYPE, store: dict):
    """Edit message về trang chủ cửa hàng (dùng khi nhấn Back)."""
    user = update.effective_user
    categories = await get_categories_by_store(store["id"])
    cart_count = get_cart_count(user.id, store["store_slug"])

    keyboard = []
    for cat in categories:
        keyboard.append([InlineKeyboardButton(
            f"{cat['emoji'] or '🛍️'} {cat['name']}",
            callback_data=f"cat_{store['id']}_{cat['id']}"
        )])

    if not categories:
        keyboard.append([InlineKeyboardButton(
            "🛍️ Xem tất cả sản phẩm",
            callback_data=f"cat_{store['id']}_0"
        )])

    bottom_row = []
    cart_text = f"🛒 Giỏ hàng ({cart_count})" if cart_count > 0 else "🛒 Giỏ hàng"
    bottom_row.append(InlineKeyboardButton(cart_text, callback_data=f"cart_view_{store['store_slug']}"))
    bottom_row.append(InlineKeyboardButton("📋 Đơn hàng", callback_data=f"cart_orders_{store['store_slug']}"))
    keyboard.append(bottom_row)

    if store.get("support_contact"):
        keyboard.append([InlineKeyboardButton(
            "💬 Liên hệ hỗ trợ",
            url=f"https://t.me/{store['support_contact'].lstrip('@')}"
        )])

    reply_markup = InlineKeyboardMarkup(keyboard)
    welcome = store.get("welcome_message") or f"👋 Chào mừng đến {store['store_name']}!"

    text = (
        f"🏪 <b>{store['store_name']}</b>\n\n"
        f"{welcome}\n\n"
        f"📦 Chọn danh mục để xem sản phẩm:"
    )

    await update.callback_query.edit_message_text(
        text, parse_mode="HTML", reply_markup=reply_markup
    )


async def show_service_intro(update: Update):
    """Trang giới thiệu dịch vụ tạo bot bán hàng."""
    text = (
        "🤖 <b>Bot Bán Hàng Telegram</b>\n\n"
        "Tạo bot bán hàng Telegram của riêng bạn trong vài phút!\n\n"
        "✅ Quản lý sản phẩm dễ dàng\n"
        "✅ Thanh toán QR tự động\n"
        "✅ Nhận thông báo đơn hàng ngay lập tức\n"
        "✅ Link bot riêng cho cửa hàng của bạn\n\n"
        "💎 <b>Đăng ký ngay để nhận link bot miễn phí!</b>"
    )
    keyboard = [[
        InlineKeyboardButton("🚀 Tạo bot ngay", url="https://your-dashboard.com/register"),
        InlineKeyboardButton("📖 Hướng dẫn", url="https://your-dashboard.com/guide"),
    ]]
    await update.message.reply_text(
        text, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
