"""
Checkout handler: Xử lý thanh toán, tạo đơn hàng, gửi QR VietQR.
Callback patterns:
  checkout_start_{slug}
  pay_bank_{slug}
  pay_momo_{slug}
  pay_done_{order_code}
"""
import random, string, json, os, urllib.parse
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from db_helper import (
    get_store_by_slug,
    get_store_by_id,
    create_order,
    get_owner_telegram_id,
    get_order_by_code,
    update_order_status,
)
from cart_store import get_cart, get_cart_total, get_cart_count, clear_cart
from config import BOT_TOKEN, API_BASE_URL, DASHBOARD_URL
from handlers.admin import is_admin_user
import httpx


BANK_NAME_TO_BIN = {
    "MB": "970422",
    "MBBANK": "970422",
    "MB BANK": "970422",
    "VCB": "970436",
    "VIETCOMBANK": "970436",
    "TCB": "970407",
    "TECHCOMBANK": "970407",
    "VPB": "970432",
    "VPBANK": "970432",
    "ACB": "970416",
    "BIDV": "970418",
    "VIETINBANK": "970415",
    "CTG": "970415",
    "TPB": "970423",
    "TPBANK": "970423",
    "STB": "970403",
    "SACOMBANK": "970403",
    "HDB": "970437",
    "HDBANK": "970437",
    "MSB": "970426",
    "VIB": "970441",
    "SHB": "970443",
    "OCB": "970448",
    "LPB": "970449",
    "LIENVIETPOSTBANK": "970449",
    "LPBANK": "970449",
    "SEABANK": "970440",
    "CAKE": "546034",
    "TIMO": "963388"
}

def resolve_bank_bin(bank_bin: str, bank_name: str) -> str:
    """Tự động suy ra mã BIN ngân hàng chuẩn từ bin hoặc tên ngân hàng."""
    if bank_bin and str(bank_bin).strip().isdigit() and len(str(bank_bin).strip()) >= 6:
        return str(bank_bin).strip()
    clean_name = (bank_name or "").upper().replace(" ", "").replace("-", "")
    for k, v in BANK_NAME_TO_BIN.items():
        if k.replace(" ", "") in clean_name:
            return v
    return "970422"  # Mặc định MB Bank nếu không xác định được

def format_price(price: int) -> str:
    return f"{price:,}đ".replace(",", ".")


def generate_order_code() -> str:
    chars = string.ascii_uppercase + string.digits
    return "BOT-" + "".join(random.choices(chars, k=7))


def vietqr_url(bank_bin: str, account: str, amount: int, content: str, account_name: str = "") -> str:
    """Tạo URL QR VietQR mẫu compact2 đầy đủ logo và tên."""
    encoded_name = urllib.parse.quote(account_name) if account_name else ""
    return (
        f"https://img.vietqr.io/image/{bank_bin}-{account}-compact2.png"
        f"?amount={amount}&addInfo={content}&accountName={encoded_name}"
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
    await notify_owner_new_order(store, order_code, user.id, customer_name, customer_username, total, items_list)


async def send_bank_payment_info(query, store: dict, order_code: str, total: int, customer_name: str):
    """Gửi QR (ảnh shop tải lên hoặc VietQR tự sinh) và thông tin chuyển khoản kèm nút 'Tôi Đã Thanh Toán'."""
    bank_bin = resolve_bank_bin(store.get("bank_bin", ""), store.get("bank_name", ""))
    bank_account = store.get("bank_account", "")
    bank_name = store.get("bank_name", "Ngân hàng")
    bank_owner = store.get("bank_owner", "")
    qr_code_url_setting = (store.get("qr_code_url") or "").strip()

    text = (
        f"🏦 <b>Thông tin chuyển khoản</b>\n\n"
        f"📦 Đơn hàng: <b>{order_code}</b>\n"
        f"💰 Số tiền: <b>{format_price(total)}</b>\n\n"
        f"🏦 Ngân hàng: <b>{bank_name}</b>\n"
        f"👤 Chủ TK: <b>{bank_owner}</b>\n"
        f"🔢 Số TK: <code>{bank_account}</code>\n"
        f"📝 Nội dung CK: <code>{order_code}</code>\n\n"
        f"⚠️ <b>QUAN TRỌNG:</b> Quét mã QR hoặc chuyển đúng số tài khoản & ghi đúng nội dung <code>{order_code}</code> để shop nhận diện đơn!\n\n"
        f"👉 <b>Sau khi chuyển khoản xong, vui lòng bấm nút [✅ Tôi Đã Thanh Toán] bên dưới để bot báo ngay cho chủ shop duyệt đơn!</b>"
    )

    keyboard = [
        [InlineKeyboardButton("✅ Tôi Đã Thanh Toán", callback_data=f"order_paid_{order_code}")],
        [
            InlineKeyboardButton("📋 Đơn hàng", callback_data=f"cart_orders_{store['store_slug']}"),
            InlineKeyboardButton("🏠 Về trang chủ", callback_data="home"),
        ]
    ]

    # 1. Thử gửi ảnh QR riêng của shop nếu shop có tải lên
    if qr_code_url_setting:
        clean_rel = qr_code_url_setting.replace("/uploads/", "").lstrip("/").replace("\\", "/")
        candidates = [
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend", "uploads", clean_rel)),
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend", qr_code_url_setting.lstrip("/\\"))),
            os.path.abspath(os.path.join(os.getcwd(), "backend", "uploads", clean_rel)),
            os.path.abspath(os.path.join(os.getcwd(), "backend", qr_code_url_setting.lstrip("/\\"))),
        ]
        local_qr_path = next((c for c in candidates if os.path.isfile(c)), None)

        if local_qr_path:
            try:
                with open(local_qr_path, "rb") as photo_f:
                    await query.message.reply_photo(
                        photo=photo_f,
                        caption=text,
                        parse_mode="HTML",
                        reply_markup=InlineKeyboardMarkup(keyboard),
                    )
                await query.delete_message()
                return
            except Exception as e:
                print(f"[!] Lỗi gửi ảnh QR riêng local: {e}")
        elif qr_code_url_setting.startswith("http://") or qr_code_url_setting.startswith("https://"):
            if not ("127.0.0.1" in qr_code_url_setting or "localhost" in qr_code_url_setting):
                try:
                    await query.message.reply_photo(
                        photo=qr_code_url_setting,
                        caption=text,
                        parse_mode="HTML",
                        reply_markup=InlineKeyboardMarkup(keyboard),
                    )
                    await query.delete_message()
                    return
                except Exception as e:
                    print(f"[!] Lỗi gửi ảnh QR riêng remote: {e}")

    # 2. Nếu không có ảnh QR riêng (hoặc gửi lỗi), tự động tạo VietQR
    if bank_account:
        qr_url = vietqr_url(bank_bin, bank_account, total, order_code, bank_owner)
        try:
            await query.message.reply_photo(
                photo=qr_url,
                caption=text,
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
            await query.delete_message()
            return
        except Exception as e:
            print(f"[!] Lỗi gửi mã VietQR tự sinh: {e}")

    # 3. Fallback gửi dạng tin nhắn văn bản
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))


async def send_momo_payment_info(query, store: dict, order_code: str, total: int):
    """Gửi thông tin thanh toán MoMo kèm nút 'Tôi Đã Thanh Toán'."""
    momo_phone = store.get("momo_phone", "")
    text = (
        f"📱 <b>Thanh toán MoMo</b>\n\n"
        f"📦 Đơn hàng: <b>{order_code}</b>\n"
        f"💰 Số tiền: <b>{format_price(total)}</b>\n\n"
        f"📱 Số MoMo: <code>{momo_phone}</code>\n"
        f"📝 Nội dung: <code>{order_code}</code>\n\n"
        f"👉 <b>Sau khi chuyển tiền xong, vui lòng bấm nút [✅ Tôi Đã Thanh Toán] bên dưới để shop duyệt đơn!</b>"
    )

    deep_link = f"https://nhantien.momo.vn/{momo_phone}/{total}/{order_code}"
    keyboard = [
        [InlineKeyboardButton("💜 Mở MoMo", url=deep_link)],
        [InlineKeyboardButton("✅ Tôi Đã Thanh Toán", callback_data=f"order_paid_{order_code}")],
        [
            InlineKeyboardButton("📋 Đơn hàng", callback_data=f"cart_orders_{store['store_slug']}"),
            InlineKeyboardButton("🏠 Về trang chủ", callback_data="home"),
        ]
    ]

    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))


async def notify_owner_new_order(
    store: dict, order_code: str, customer_tg_id: int, customer_name: str,
    customer_username: str, total: int, items: list
):
    """Gửi thông báo đơn mới cho chủ cửa hàng kèm nút hỗ trợ khách."""
    owner_tg_id = await get_owner_telegram_id(store["id"])
    if not owner_tg_id or not BOT_TOKEN:
        return

    items_text = "\n".join([f"• {i['name']} × {i['qty']} = {format_price(i['price'] * i['qty'])}" for i in items])
    username_text = f"@{customer_username}" if customer_username else "Ẩn danh"

    text = (
        f"🔔 <b>THÔNG BÁO ĐƠN HÀNG MỚI!</b>\n\n"
        f"🏪 Cửa hàng: <b>{store['store_name']}</b>\n"
        f"📦 Mã đơn: <b>{order_code}</b>\n"
        f"👤 Khách: <b>{customer_name}</b> ({username_text})\n"
        f"🆔 Telegram ID: <code>{customer_tg_id}</code>\n"
        f"💰 Tổng: <b>{format_price(total)}</b>\n\n"
        f"<b>Chi tiết sản phẩm:</b>\n{items_text}\n\n"
        f"👉 Bấm nút bên dưới để nhắn tin hỗ trợ khách hàng ngay:"
    )

    inline_keyboard = []
    if customer_username:
        inline_keyboard.append([{"text": f"💬 Chat với @{customer_username}", "url": f"https://t.me/{customer_username}"}])
    inline_keyboard.append([
        {"text": "↩️ Trả Lời Khách Qua Bot", "callback_data": f"reply_cust_{customer_tg_id}_{store['id']}"},
        {"text": "🌐 Mở Web Đơn Hàng", "url": f"{DASHBOARD_URL}/dashboard/orders"},
    ])

    async with httpx.AsyncClient() as client:
        try:
            await client.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": owner_tg_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "reply_markup": {"inline_keyboard": inline_keyboard},
                },
                timeout=10,
            )
        except Exception as e:
            print(f"[!] Lỗi gửi thông báo cho chủ shop: {e}")


async def customer_paid_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý khi khách bấm '✅ Tôi Đã Thanh Toán' -> Bắn thông báo đến chủ shop kèm nút Duyệt Đơn."""
    query = update.callback_query
    order_code = query.data.replace("order_paid_", "").strip()
    user = update.effective_user

    order = await get_order_by_code(order_code)
    if not order:
        await query.answer("❌ Không tìm thấy thông tin đơn hàng này!", show_alert=True)
        return

    if order.get("status") in ["paid", "completed"]:
        await query.answer("✅ Đơn hàng này đã được xác nhận thanh toán rồi!", show_alert=True)
        return

    store = await get_store_by_id(order["store_id"])
    if not store:
        await query.answer("❌ Cửa hàng không tồn tại hoặc đã ngừng hoạt động!", show_alert=True)
        return

    # Thông báo pop-up cho khách
    await query.answer("✅ Đã gửi thông báo đến chủ shop! Vui lòng chờ shop kiểm tra và duyệt đơn.", show_alert=True)

    # Cập nhật giao diện tin nhắn của khách
    updated_text = (
        f"⏳ <b>ĐANG CHỜ CHỦ SHOP KIỂM TRA & DUYỆT ĐƠN...</b>\n\n"
        f"📦 Mã đơn hàng: <b>{order_code}</b>\n"
        f"💰 Tổng số tiền: <b>{format_price(order['total_amount'])}</b>\n"
        f"🏪 Cửa hàng: <b>{store['store_name']}</b>\n\n"
        f"✅ <i>Bạn đã báo [Tôi Đã Thanh Toán]. Bot đã gửi thông báo khẩn cấp đến Telegram của Chủ shop để đối soát biến động số dư và duyệt đơn cho bạn!</i>\n\n"
        f"⚡ Ngay khi chủ shop bấm [Duyệt Đơn], bot sẽ tự động gửi sản phẩm / nội dung bàn giao trực tiếp tại đây."
    )

    cust_keyboard = [
        [InlineKeyboardButton("🔄 Kiểm tra trạng thái đơn", callback_data=f"cart_orders_{store['store_slug']}")],
        [InlineKeyboardButton("🏠 Về trang chủ", callback_data="home")]
    ]

    try:
        if query.message.caption:
            await query.edit_message_caption(
                caption=updated_text,
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(cust_keyboard)
            )
        else:
            await query.edit_message_text(
                text=updated_text,
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(cust_keyboard)
            )
    except Exception:
        pass

    # Gửi thông báo đến chủ shop kèm nút duyệt đơn
    await notify_owner_customer_paid(store, order)


async def notify_owner_customer_paid(store: dict, order: dict):
    """Gửi thông báo khẩn đến Telegram chủ shop để duyệt đơn hàng."""
    owner_tg_id = await get_owner_telegram_id(store["id"])
    if not owner_tg_id or not BOT_TOKEN:
        return

    order_code = order["order_code"]
    total = order["total_amount"]
    customer_name = order.get("customer_name") or "Khách hàng"
    customer_username = order.get("customer_username") or ""
    customer_tg_id = order.get("customer_tg_id")

    items = order.get("items")
    if isinstance(items, str):
        try:
            items = json.loads(items)
        except Exception:
            items = []
    items_text = "\n".join([f"• {i.get('name')} × {i.get('qty', 1)} = {format_price(i.get('price', 0) * i.get('qty', 1))}" for i in (items or [])])
    username_text = f"@{customer_username}" if customer_username else "Không có"

    text = (
        f"🔔 <b>KHÁCH HÀNG BÁO ĐÃ THANH TOÁN! (CHỜ DUYỆT ĐƠN)</b>\n\n"
        f"🏪 Cửa hàng: <b>{store['store_name']}</b>\n"
        f"📦 Mã đơn hàng: <code>{order_code}</code>\n"
        f"💰 Số tiền: <b>{format_price(total)}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Khách hàng:</b>\n"
        f"• Tên: <b>{customer_name}</b> ({username_text})\n"
        f"• Telegram ID: <code>{customer_tg_id}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🛍️ <b>Sản phẩm đặt mua:</b>\n{items_text}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👉 <b>Hành động:</b> Khách vừa nhấn nút <i>'Tôi Đã Thanh Toán'</i>. Hãy kiểm tra biến động số dư tài khoản ngân hàng / MoMo của bạn. Nếu đã nhận đủ <b>{format_price(total)}</b>, hãy bấm <b>[✅ Duyệt Đơn Này]</b> bên dưới để bàn giao hàng cho khách:"
    )

    inline_keyboard = [
        [{"text": "✅ Duyệt Đơn Này (Giao Hàng Ngay)", "callback_data": f"approve_order_{order_code}"}],
        [
            {"text": "❌ Chưa Nhận Được Tiền", "callback_data": f"reject_order_{order_code}"},
            {"text": f"💬 Chat với @{customer_username}" if customer_username else "↩️ Trả Lời Khách", "url": f"https://t.me/{customer_username}" if customer_username else f"reply_cust_{customer_tg_id}_{store['id']}"}
        ],
        [{"text": "🌐 Mở Web Quản Trị Đơn", "url": f"{DASHBOARD_URL}/dashboard/orders"}]
    ]

    # Sửa nút reply_cust nếu không có URL
    fixed_kb = []
    for row in inline_keyboard:
        new_row = []
        for btn in row:
            if "url" in btn and not btn["url"].startswith("http"):
                new_row.append({"text": btn["text"], "callback_data": btn["url"]})
            elif "url" in btn:
                new_row.append({"text": btn["text"], "url": btn["url"]})
            else:
                new_row.append({"text": btn["text"], "callback_data": btn["callback_data"]})
        fixed_kb.append(new_row)

    async with httpx.AsyncClient() as client:
        try:
            await client.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": owner_tg_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "reply_markup": {"inline_keyboard": fixed_kb},
                },
                timeout=10,
            )
        except Exception as e:
            print(f"[!] Lỗi gửi thông báo duyệt đơn cho chủ shop: {e}")


async def approve_order_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Chủ cửa hàng hoặc SuperAdmin bấm [✅ Duyệt Đơn Này] -> Tự động bàn giao hàng."""
    query = update.callback_query
    user = update.effective_user
    order_code = query.data.replace("approve_order_", "").strip()

    order = await get_order_by_code(order_code)
    if not order:
        await query.answer("❌ Không tìm thấy đơn hàng!", show_alert=True)
        return

    store = await get_store_by_id(order["store_id"])
    owner_tg_id = await get_owner_telegram_id(order["store_id"])

    # Kiểm tra quyền: phải là chủ shop hoặc superadmin
    if user.id != owner_tg_id and not is_admin_user(user):
        await query.answer("⛔ Bạn không phải chủ cửa hàng này để duyệt đơn!", show_alert=True)
        return

    if order.get("status") in ["paid", "completed"]:
        await query.answer("Đơn hàng này đã được duyệt trước đó rồi!", show_alert=True)
        return

    # Gọi Backend API để xử lý trừ kho và bàn giao hàng tự động
    approved = False
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            res = await client.post(
                f"{API_BASE_URL}/api/orders/bot-confirm",
                json={
                    "order_code": order_code,
                    "actor_telegram_id": user.id,
                    "action": "approve"
                }
            )
            if res.status_code == 200:
                approved = True
    except Exception as e:
        print(f"[!] Lỗi gọi bot-confirm backend: {e}")

    # Fallback cập nhật DB nếu backend offline
    if not approved:
        await update_order_status(order_code, "completed")
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                    json={
                        "chat_id": order["customer_tg_id"],
                        "text": f"🎉 <b>ĐƠN HÀNG {order_code} ĐÃ ĐƯỢC DUYỆT!</b>\n\nChủ cửa hàng <b>{store['store_name']}</b> đã xác nhận thanh toán thành công! Cảm ơn bạn đã mua hàng. Chúc bạn một ngày tốt lành! 🙏",
                        "parse_mode": "HTML"
                    }
                )
        except Exception:
            pass

    await query.answer("✅ Đã duyệt đơn thành công! Bot đã giao hàng cho khách.", show_alert=True)
    try:
        await query.edit_message_text(
            f"✅ <b>ĐÃ DUYỆT ĐƠN HÀNG: {order_code}</b>\n\n"
            f"🏪 Cửa hàng: <b>{store['store_name']}</b>\n"
            f"💰 Số tiền: <b>{format_price(order['total_amount'])}</b>\n"
            f"👤 Khách hàng: <b>{order['customer_name']}</b> (ID: <code>{order['customer_tg_id']}</code>)\n\n"
            f"👉 <i>Đã xác nhận thanh toán thành công và kích hoạt gửi sản phẩm bàn giao cho khách qua Bot.</i>",
            parse_mode="HTML"
        )
    except Exception:
        pass


async def reject_order_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Chủ cửa hàng từ chối đơn hàng (chưa nhận được tiền)."""
    query = update.callback_query
    user = update.effective_user
    order_code = query.data.replace("reject_order_", "").strip()

    order = await get_order_by_code(order_code)
    if not order:
        await query.answer("❌ Không tìm thấy đơn hàng!", show_alert=True)
        return

    store = await get_store_by_id(order["store_id"])
    owner_tg_id = await get_owner_telegram_id(order["store_id"])

    if user.id != owner_tg_id and not is_admin_user(user):
        await query.answer("⛔ Bạn không có quyền thao tác đơn này!", show_alert=True)
        return

    # Cập nhật backend hủy đơn
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            await client.post(
                f"{API_BASE_URL}/api/orders/bot-confirm",
                json={
                    "order_code": order_code,
                    "actor_telegram_id": user.id,
                    "action": "reject"
                }
            )
    except Exception:
        await update_order_status(order_code, "cancelled")

    # Thông báo cho khách hàng
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": order["customer_tg_id"],
                    "text": (
                        f"❌ <b>ĐƠN HÀNG {order_code} CHƯA ĐƯỢC DUYỆT</b>\n\n"
                        f"Chủ cửa hàng <b>{store['store_name']}</b> chưa nhận được số tiền chuyển khoản tương ứng.\n"
                        f"Nếu bạn đã chuyển khoản, vui lòng chụp lại biên lai giao dịch và liên hệ chủ shop: @{store.get('support_contact') or 'admin'} để được kiểm tra lại."
                    ),
                    "parse_mode": "HTML"
                }
            )
    except Exception:
        pass

    await query.answer("❌ Đã từ chối đơn hàng.", show_alert=True)
    try:
        await query.edit_message_text(
            f"❌ <b>ĐÃ TỪ CHỐI ĐƠN HÀNG: {order_code}</b>\n\n"
            f"Trạng thái: <b>ĐÃ HỦY (Chưa nhận được tiền)</b>\n"
            f"Bot đã gửi thông báo phản hồi đến khách hàng.",
            parse_mode="HTML"
        )
    except Exception:
        pass


