"""
Handler /start và Menu Sản Phẩm:
1. Gợi ý lệnh duy nhất: /start
2. Bàn phím Menu dưới đáy màn hình (ReplyKeyboardMarkup):
   [🛍️ Bảng Giá Sản Phẩm]  [🛒 Giỏ Hàng]
   [📋 Đơn Hàng Của Tôi]   [💬 Hỗ Trợ]
3. Menu tương tác bấm chọn sản phẩm (Inline Keyboard)
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
from db_helper import get_store_by_slug, get_categories_by_store, get_products_by_store
from cart_store import set_user_store, get_user_store, get_cart_count
import urllib.parse

DASHBOARD_URL = "http://127.0.0.1:5174"
ADMIN_CONTACT = "manhkmhd2004"


def get_bottom_reply_keyboard():
    """Bàn phím menu dưới đáy chat tiện lợi cho khách bấm chọn ngay"""
    return ReplyKeyboardMarkup(
        [
            ["🛍️ Bảng Giá Sản Phẩm", "🛒 Giỏ Hàng"],
            ["📋 Đơn Hàng Của Tôi", "💬 Hỗ Trợ Khách Hàng"]
        ],
        resize_keyboard=True
    )


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args  # ["store_SLUG"] hoặc []

    # Xử lý deep link của shop con
    if args:
        arg = args[0]
        if arg.startswith("store_"):
            slug = arg[len("store_"):]
            store = await get_store_by_slug(slug)
            if store:
                set_user_store(user.id, slug)
                await show_store_home(update, context, store)
                return

    # Không có deep link → Hiển thị Menu chính với 2 gói tạo bot
    await show_service_intro(update)


async def show_service_intro(update: Update):
    """Trang chủ hiển thị Menu chọn gói sản phẩm."""
    user = update.effective_user
    text = (
        f"👋 <b>Xin chào {user.first_name or 'bạn'}!</b>\n\n"
        "Chào mừng bạn đến với <b>Hệ Thống Tạo Bot Bán Hàng Telegram</b>.\n"
        "Sau khi mua gói, bạn sẽ có ngay <b>Trang Web riêng</b> để tự cài đặt sản phẩm, giá tiền và link bot riêng để bán hàng tự động.\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🛍️ <b>MENU CÁC GÓI SẢN PHẨM:</b>\n\n"
        "⚡ <b>1. GÓI 1 THÁNG: 50.000 VNĐ</b>\n"
        "• Dùng 30 ngày đầy đủ mọi tính năng\n"
        "• Không giới hạn mặt hàng & đơn hàng\n"
        "• Tự động thanh toán chuyển khoản VietQR\n\n"
        "👑 <b>2. GÓI VĨNH VIỄN (LIFETIME): 250.000 VNĐ</b>\n"
        "• Sở hữu <b>TRỌN ĐỜI</b> - KHÔNG BAO GIỜ hết hạn!\n"
        "• Ưu tiên cập nhật tính năng mới mãi mãi\n"
        "• Tiết kiệm chi phí tối đa (Khuyên dùng 🔥)\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "👇 <b>Bấm vào gói bên dưới để xem chi tiết & nhận mã QR thanh toán:</b>"
    )

    keyboard = [
        [InlineKeyboardButton("⚡ [50.000đ] Gói 1 Tháng", callback_data="buy_plan_monthly")],
        [InlineKeyboardButton("👑 [250.000đ] Gói Vĩnh Viễn (Lifetime)", callback_data="buy_plan_lifetime")],
        [
            InlineKeyboardButton("🌐 Web Quản Trị", url=DASHBOARD_URL),
            InlineKeyboardButton("💬 Hỗ Trợ Admin", url=f"https://t.me/{ADMIN_CONTACT}"),
        ]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    # Nếu gửi từ tin nhắn gõ /start -> kèm theo bàn phím dưới đáy
    if update.message:
        await update.message.reply_text(
            "📱 Bàn phím Menu chức năng đã sẵn sàng bên dưới!",
            reply_markup=get_bottom_reply_keyboard()
        )
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, parse_mode="HTML", reply_markup=reply_markup)


async def plan_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý chọn sản phẩm / gói từ Menu"""
    query = update.callback_query
    await query.answer()
    data = query.data
    user = update.effective_user

    if data == "show_plans":
        await show_service_intro(update)
        return

    if data in ["buy_plan_monthly", "buy_plan_lifetime"]:
        is_lifetime = (data == "buy_plan_lifetime")
        plan_name = "VĨNH VIỄN (LIFETIME)" if is_lifetime else "1 THÁNG"
        price = 250000 if is_lifetime else 50000
        plan_code = "LIFETIME" if is_lifetime else "THANG"
        order_memo = f"BOT {plan_code} {user.id}"

        # VietQR chuẩn MB Bank
        bank_bin = "970422" # MB Bank
        bank_acc = "0865768828"
        bank_name = "MB BANK"
        bank_owner = "VO DUC MANH"
        qr_url = f"https://img.vietqr.io/image/{bank_bin}-{bank_acc}-compact2.png?amount={price}&addInfo={urllib.parse.quote(order_memo)}&accountName={urllib.parse.quote(bank_owner)}"

        text = (
            f"🛒 <b>CHI TIẾT ĐƠN HÀNG: {plan_name}</b>\n\n"
            f"• <b>Sản phẩm:</b> Tạo Bot Bán Hàng Telegram ({plan_name})\n"
            f"• <b>Giá thanh toán:</b> <code>{price:,}đ</code>\n"
            f"• <b>Hạn dùng:</b> {'Vĩnh viễn trọn đời' if is_lifetime else '30 ngày'}\n\n"
            "🏦 <b>THÔNG TIN CHUYỂN KHOẢN (Quét mã VietQR):</b>\n"
            f"• Ngân hàng: <b>{bank_name}</b>\n"
            f"• Số tài khoản: <code>{bank_acc}</code> (chạm để sao chép)\n"
            f"• Chủ tài khoản: <b>{bank_owner}</b>\n"
            f"• Nội dung CK: <code>{order_memo}</code>\n\n"
            "👉 <i>Sau khi quét mã thanh toán, bấm nút bên dưới để xác nhận:</i>"
        )

        keyboard = [
            [InlineKeyboardButton("✅ Tôi Đã Chuyển Khoản", callback_data=f"paid_check_{plan_code}_{user.id}")],
            [InlineKeyboardButton("💬 Hỗ Trợ Admin", url=f"https://t.me/{ADMIN_CONTACT}")],
            [InlineKeyboardButton("⬅️ Quay Lại Menu Sản Phẩm", callback_data="show_plans")],
        ]

        try:
            await query.message.reply_photo(
                photo=qr_url,
                caption=text,
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
        except Exception:
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if data.startswith("paid_check_"):
        await query.edit_message_caption(
            caption=(
                "⏳ <b>ĐÃ GHI NHẬN YÊU CẦU XÁC NHẬN!</b>\n\n"
                "Cảm ơn bạn đã thanh toán. Hệ thống đang đối soát và sẽ kích hoạt dịch vụ cho bạn trong ít phút.\n\n"
                f"👉 Đăng nhập web quản trị: <a href='{DASHBOARD_URL}'>{DASHBOARD_URL}</a>\n"
                f"👉 Hoặc nhắn tin Admin: @{ADMIN_CONTACT}"
            ),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🌐 Vào Web Quản Trị", url=DASHBOARD_URL)],
                [InlineKeyboardButton("💬 Nhắn Tin Admin", url=f"https://t.me/{ADMIN_CONTACT}")],
                [InlineKeyboardButton("⬅️ Về Menu Sản Phẩm", callback_data="show_plans")],
            ])
        )


async def bottom_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bắt các sự kiện khi khách bấm nút ở bàn phím dưới đáy màn hình"""
    text = (update.message.text or "").strip()

    if "Bảng Giá" in text or "Sản Phẩm" in text:
        await show_service_intro(update)
    elif "Giỏ Hàng" in text:
        await update.message.reply_text(
            "🛒 <b>Giỏ Hàng Của Bạn</b>\n\n"
            "Bạn chưa chọn sản phẩm nào vào giỏ. Hãy bấm vào <b>'🛍️ Bảng Giá Sản Phẩm'</b> để chọn gói dịch vụ!",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🛍️ Xem Bảng Giá Sản Phẩm", callback_data="show_plans")]
            ])
        )
    elif "Đơn Hàng" in text:
        await update.message.reply_text(
            "📋 <b>Lịch Sử Đơn Hàng</b>\n\n"
            "Đăng nhập trang quản trị để xem chi tiết toàn bộ đơn hàng của bạn: "
            f"<a href='{DASHBOARD_URL}'>{DASHBOARD_URL}</a>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🌐 Vào Web Quản Trị", url=DASHBOARD_URL)]
            ])
        )
    elif "Hỗ Trợ" in text:
        await update.message.reply_text(
            "💬 <b>HỖ TRỢ KHÁCH HÀNG 24/7</b>\n\n"
            f"Mọi thắc mắc về cài đặt bot hoặc thanh toán, vui lòng liên hệ Admin:\n"
            f"👉 @{ADMIN_CONTACT}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📩 Nhắn Tin Cho Admin", url=f"https://t.me/{ADMIN_CONTACT}")]
            ])
        )
    else:
        await show_service_intro(update)


# ─── Deep link cho Shop con ────────────────────────────────────────

async def main_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    slug = get_user_store(user.id)
    if not slug:
        await show_service_intro(update)
        return

    store = await get_store_by_slug(slug)
    if not store:
        await show_service_intro(update)
        return

    if update.callback_query:
        await update.callback_query.answer()
        await show_store_home_edit(update, context, store)
    else:
        await show_store_home(update, context, store)


async def show_store_home(update: Update, context: ContextTypes.DEFAULT_TYPE, store: dict):
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
            "💬 Liên hệ hỗ trợ shop",
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
            "💬 Liên hệ hỗ trợ shop",
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
