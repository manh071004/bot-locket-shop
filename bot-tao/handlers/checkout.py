"""
Checkout handler: Xử lý thanh toán, tạo đơn hàng, gửi QR VietQR.
Callback patterns:
  checkout_start_{slug}
  pay_bank_{slug}
  pay_momo_{slug}
  pay_done_{order_code}
"""
import random, string
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from db_helper import get_store_by_slug, create_order, get_owner_telegram_id
from cart_store import get_cart, get_cart_total, get_cart_count, clear_cart
from config import BOT_TOKEN
import httpx


def format_price(price: int) -> str:
    return f"{price:,}đ".replace(",", ".")


def generate_order_code() -> str:
    chars = string.ascii_uppercase + string.digits
    return "BOT-" + "".join(random.choices(chars, k=7))


def vietqr_url(bank_bin: str, account: str, amount: int, content: str) -> str:
    """Tạo URL QR VietQR."""
    return (
        f"https://img.vietqr.io/image/{bank_bin}-{account}-qr_only.png"
        f"?amount={amount}&addInfo={content}&accountName="
    )


async def checkout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bắt đầu checkout: hiển thị chọn phương thức thanh toán."""
    query = update.callback_query
    await query.answer()

    # checkout_start_{slug}
    slug = query.data.replace("checkout_start_", "")
    user = update.effective_user

    cart = get_cart(user.id, slug)
    items = cart.get("items", {})
    if not items:
        await query.answer("Giỏ hàng trống!", show_alert=True)
        return

    total = get_cart_total(user.id, slug)
    store = await get_store_by_slug(slug)
    if not store:
        return

    # Xây text tóm tắt đơn
    text = f"💳 <b>Xác nhận đơn hàng - {store['store_name']}</b>\n\n"
    for item in items.values():
        text += f"• {item['name']} × {item['qty']} = {format_price(item['price'] * item['qty'])}\n"
    text += f"\n💰 <b>Tổng: {format_price(total)}</b>\n\n"
    text += "Chọn phương thức thanh toán:"

    keyboard = []
    if store.get("bank_account") and store.get("bank_bin"):
        keyboard.append([InlineKeyboardButton(
            f"🏦 Chuyển khoản ngân hàng",
            callback_data=f"pay_bank_{slug}"
        )])
    if store.get("momo_phone"):
        keyboard.append([InlineKeyboardButton(
            f"📱 Thanh toán MoMo",
            callback_data=f"pay_momo_{slug}"
        )])
    if not keyboard:
        keyboard.append([InlineKeyboardButton(
            "⚠️ Liên hệ chủ cửa hàng",
            callback_data=f"noop"
        )])

    keyboard.append([InlineKeyboardButton("◀️ Quay lại giỏ", callback_data=f"cart_view_{slug}")])

    await query.edit_message_text(
        text, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def checkout_action_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý chọn phương thức thanh toán, tạo đơn hàng."""
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    data = query.data  # pay_bank_{slug} | pay_momo_{slug}

    if data.startswith("pay_bank_"):
        slug = data[len("pay_bank_"):]
        payment_method = "bank"
    elif data.startswith("pay_momo_"):
        slug = data[len("pay_momo_"):]
        payment_method = "momo"
    else:
        return

    cart = get_cart(user.id, slug)
    items = cart.get("items", {})
    if not items:
        await query.answer("Giỏ hàng trống!", show_alert=True)
        return

    total = get_cart_total(user.id, slug)
    store = await get_store_by_slug(slug)
    if not store:
        return

    # Tạo đơn hàng trong DB
    order_code = generate_order_code()
    # Đảm bảo unique
    items_list = [
        {
            "product_id": v["product_id"],
            "name": v["name"],
            "price": v["price"],
            "qty": v["qty"],
        }
        for v in items.values()
    ]

    customer_name = user.full_name or user.first_name or "Khách"
    customer_username = user.username or ""

    order = await create_order(
        store_id=store["id"],
        order_code=order_code,
        customer_tg_id=user.id,
        customer_name=customer_name,
        customer_username=customer_username,
        items=items_list,
        total_amount=total,
    )

    # Xóa giỏ hàng sau khi đặt
    clear_cart(user.id, slug)

    # Gửi thông tin thanh toán
    if payment_method == "bank":
        await send_bank_payment_info(query, store, order_code, total, customer_name)
    elif payment_method == "momo":
        await send_momo_payment_info(query, store, order_code, total)

    # Notify chủ cửa hàng
    await notify_owner_new_order(store, order_code, customer_name, customer_username, total, items_list)


async def send_bank_payment_info(query, store: dict, order_code: str, total: int, customer_name: str):
    """Gửi QR VietQR và thông tin chuyển khoản."""
    bank_bin = store.get("bank_bin", "")
    bank_account = store.get("bank_account", "")
    bank_name = store.get("bank_name", "Ngân hàng")
    bank_owner = store.get("bank_owner", "")

    text = (
        f"🏦 <b>Thông tin chuyển khoản</b>\n\n"
        f"📦 Đơn hàng: <b>{order_code}</b>\n"
        f"💰 Số tiền: <b>{format_price(total)}</b>\n\n"
        f"🏦 Ngân hàng: <b>{bank_name}</b>\n"
        f"👤 Chủ TK: <b>{bank_owner}</b>\n"
        f"🔢 Số TK: <code>{bank_account}</code>\n"
        f"📝 Nội dung CK: <code>{order_code}</code>\n\n"
        f"⚠️ <b>QUAN TRỌNG:</b> Ghi đúng nội dung <code>{order_code}</code> để tự động xác nhận đơn!\n\n"
        f"✅ Sau khi chuyển khoản, đơn sẽ được xác nhận tự động trong vài phút."
    )

    keyboard = [[
        InlineKeyboardButton("🏠 Về trang chủ", callback_data="home"),
        InlineKeyboardButton("📋 Đơn hàng", callback_data=f"cart_orders_{store['store_slug']}"),
    ]]

    # Gửi QR nếu có đủ thông tin
    if bank_bin and bank_account:
        qr_url = vietqr_url(bank_bin, bank_account, total, order_code)
        try:
            await query.message.reply_photo(
                photo=qr_url,
                caption=text,
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
            await query.delete_message()
            return
        except Exception:
            pass

    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))


async def send_momo_payment_info(query, store: dict, order_code: str, total: int):
    """Gửi thông tin thanh toán MoMo."""
    momo_phone = store.get("momo_phone", "")
    text = (
        f"📱 <b>Thanh toán MoMo</b>\n\n"
        f"📦 Đơn hàng: <b>{order_code}</b>\n"
        f"💰 Số tiền: <b>{format_price(total)}</b>\n\n"
        f"📱 Số MoMo: <code>{momo_phone}</code>\n"
        f"📝 Nội dung: <code>{order_code}</code>\n\n"
        f"⚠️ Ghi đúng nội dung để xác nhận tự động!"
    )

    deep_link = f"https://nhantien.momo.vn/{momo_phone}/{total}/{order_code}"
    keyboard = [[
        InlineKeyboardButton("💜 Mở MoMo", url=deep_link),
        InlineKeyboardButton("📋 Đơn hàng", callback_data=f"cart_orders_{store['store_slug']}"),
    ]]

    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))


async def notify_owner_new_order(
    store: dict, order_code: str, customer_name: str,
    customer_username: str, total: int, items: list
):
    """Gửi thông báo đơn mới cho chủ cửa hàng."""
    owner_tg_id = await get_owner_telegram_id(store["id"])
    if not owner_tg_id or not BOT_TOKEN:
        return

    items_text = "\n".join([f"• {i['name']} × {i['qty']} = {format_price(i['price'] * i['qty'])}" for i in items])
    username_text = f"@{customer_username}" if customer_username else "Ẩn danh"

    text = (
        f"🔔 <b>ĐƠN HÀNG MỚI!</b>\n\n"
        f"📦 Mã đơn: <b>{order_code}</b>\n"
        f"👤 Khách: {customer_name} ({username_text})\n"
        f"💰 Tổng: <b>{format_price(total)}</b>\n\n"
        f"<b>Chi tiết:</b>\n{items_text}"
    )

    async with httpx.AsyncClient() as client:
        try:
            await client.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={"chat_id": owner_tg_id, "text": text, "parse_mode": "HTML"},
                timeout=10,
            )
        except Exception:
            pass
