"""
Cart handler: Quản lý giỏ hàng.
Callback patterns:
  cart_add_{store_id}_{product_id}_{slug}
  cart_buynow_{store_id}_{product_id}_{slug}
  cart_view_{slug}
  cart_remove_{product_id}_{slug}
  cart_plus_{product_id}_{slug}
  cart_minus_{product_id}_{slug}
  cart_orders_{slug}
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from db_helper import get_product_by_id, get_orders_by_customer
from cart_store import (
    add_to_cart, remove_from_cart, update_qty,
    get_cart, get_cart_total, get_cart_count, get_user_store
)


def format_price(price: int) -> str:
    return f"{price:,}đ".replace(",", ".")


async def cart_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Dispatcher cho các cart_view và cart_orders actions."""
    query = update.callback_query
    await query.answer()
    data = query.data

    user = update.effective_user

    if data.startswith("cart_view_"):
        slug = data[len("cart_view_"):]
        await show_cart(query, user.id, slug)
    elif data.startswith("cart_orders_"):
        slug = data[len("cart_orders_"):]
        await show_orders(query, user.id, slug)


async def cart_action_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Dispatcher cho add/remove/plus/minus."""
    query = update.callback_query
    await query.answer()
    data = query.data
    user = update.effective_user

    if data.startswith("cart_add_"):
        # cart_add_{store_id}_{product_id}_{slug}
        parts = data.split("_")
        store_id = int(parts[2])
        product_id = int(parts[3])
        slug = "_".join(parts[4:])
        product = await get_product_by_id(product_id, store_id)
        if product:
            add_to_cart(user.id, slug, store_id, product, 1)
            count = get_cart_count(user.id, slug)
            await query.answer(f"✅ Đã thêm! Giỏ hàng: {count} sản phẩm", show_alert=False)
        return

    elif data.startswith("cart_buynow_"):
        # cart_buynow_{store_id}_{product_id}_{slug}
        parts = data.split("_")
        store_id = int(parts[2])
        product_id = int(parts[3])
        slug = "_".join(parts[4:])
        product = await get_product_by_id(product_id, store_id)
        if product:
            add_to_cart(user.id, slug, store_id, product, 1)
            await show_cart(query, user.id, slug)
        return

    elif data.startswith("cart_remove_"):
        # cart_remove_{product_id}_{slug}
        parts = data.split("_")
        product_id = int(parts[2])
        slug = "_".join(parts[3:])
        remove_from_cart(user.id, slug, product_id)
        await show_cart(query, user.id, slug)

    elif data.startswith("cart_plus_"):
        # cart_plus_{product_id}_{slug}
        parts = data.split("_")
        product_id = int(parts[2])
        slug = "_".join(parts[3:])
        cart = get_cart(user.id, slug)
        pid = str(product_id)
        current_qty = cart.get("items", {}).get(pid, {}).get("qty", 0)
        update_qty(user.id, slug, product_id, current_qty + 1)
        await show_cart(query, user.id, slug)

    elif data.startswith("cart_minus_"):
        parts = data.split("_")
        product_id = int(parts[2])
        slug = "_".join(parts[3:])
        cart = get_cart(user.id, slug)
        pid = str(product_id)
        current_qty = cart.get("items", {}).get(pid, {}).get("qty", 0)
        update_qty(user.id, slug, product_id, current_qty - 1)
        await show_cart(query, user.id, slug)


async def show_cart(query, tg_id: int, slug: str):
    """Hiển thị giỏ hàng."""
    cart = get_cart(tg_id, slug)
    items = cart.get("items", {})

    if not items:
        await query.edit_message_text(
            "🛒 <b>Giỏ hàng trống!</b>\n\nHãy chọn sản phẩm để thêm vào giỏ.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🛍️ Tiếp tục mua sắm", callback_data="home")
            ]])
        )
        return

    text = "🛒 <b>Giỏ hàng của bạn</b>\n\n"
    keyboard = []

    for pid, item in items.items():
        subtotal = item["price"] * item["qty"]
        text += f"• <b>{item['name']}</b>\n"
        text += f"  {format_price(item['price'])} × {item['qty']} = <b>{format_price(subtotal)}</b>\n\n"

        # Nút +/- và xóa cho mỗi sản phẩm
        keyboard.append([
            InlineKeyboardButton(f"➖", callback_data=f"cart_minus_{pid}_{slug}"),
            InlineKeyboardButton(f"{item['qty']}", callback_data=f"noop"),
            InlineKeyboardButton(f"➕", callback_data=f"cart_plus_{pid}_{slug}"),
            InlineKeyboardButton(f"🗑️", callback_data=f"cart_remove_{pid}_{slug}"),
        ])

    total = get_cart_total(tg_id, slug)
    text += f"─────────────────\n"
    text += f"💰 <b>Tổng cộng: {format_price(total)}</b>"

    keyboard.append([
        InlineKeyboardButton("◀️ Tiếp tục mua", callback_data="home"),
        InlineKeyboardButton("💳 Thanh toán", callback_data=f"checkout_start_{slug}"),
    ])

    await query.edit_message_text(
        text, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def show_orders(query, tg_id: int, slug: str):
    """Hiển thị lịch sử đơn hàng của khách."""
    from db_helper import get_store_by_slug
    store = await get_store_by_slug(slug)
    if not store:
        return

    orders = await get_orders_by_customer(tg_id, store["id"])

    if not orders:
        await query.edit_message_text(
            "📋 <b>Lịch sử đơn hàng</b>\n\nBạn chưa có đơn hàng nào.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🛍️ Mua sắm ngay", callback_data="home")
            ]])
        )
        return

    status_emoji = {"pending": "⏳", "paid": "✅", "completed": "🎉", "cancelled": "❌"}
    text = "📋 <b>Lịch sử đơn hàng</b>\n\n"

    for order in orders:
        emoji = status_emoji.get(order["status"], "📦")
        text += (
            f"{emoji} <b>{order['order_code']}</b> - {format_price(order['total_amount'])}\n"
            f"   Trạng thái: {order['status'].upper()}\n"
            f"   Ngày: {order['created_at'].strftime('%d/%m/%Y %H:%M')}\n\n"
        )

    await query.edit_message_text(
        text, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🏠 Trang chủ", callback_data="home")
        ]])
    )
