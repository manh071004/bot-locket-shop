"""
Handler /start, /muagoi, /taobot, /web, /hotro
Phục vụ 2 chức năng:
1. Giới thiệu & Bán 2 gói tạo bot (50k/tháng & 250k vĩnh viễn) kèm thanh toán VietQR
2. Nhận deep link của shop con: t.me/BOT?start=store_SLUG
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from db_helper import get_store_by_slug, get_categories_by_store, get_products_by_store
from cart_store import set_user_store, get_user_store, get_cart_count
import urllib.parse

DASHBOARD_URL = "http://localhost:5174"
ADMIN_CONTACT = "manhkmhd2004"


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

    # Không có deep link → hiển thị trang Bảng giá 2 gói dịch vụ tạo bot
    await show_service_intro(update)


async def muagoi_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lệnh /muagoi: Hiển thị 2 gói tạo bot"""
    await show_service_intro(update)


async def taobot_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lệnh /taobot: Hướng dẫn tạo bot bán hàng riêng"""
    text = (
        "🤖 <b>HƯỚNG DẪN TẠO BOT BÁN HÀNG TELEGRAM RIÊNG</b>\n\n"
        "Chỉ với 3 bước đơn giản:\n\n"
        "1️⃣ <b>Bước 1:</b> Mua một trong 2 gói dịch vụ:\n"
        "   • ⚡ Gói Tháng: <b>50.000đ</b>\n"
        "   • 👑 Gói Vĩnh Viễn: <b>250.000đ</b> (Trọn đời)\n\n"
        "2️⃣ <b>Bước 2:</b> Đăng nhập vào trang web quản trị của bạn:\n"
        f"   👉 <a href='{DASHBOARD_URL}'>{DASHBOARD_URL}</a>\n"
        "   • Đặt tên shop, số tài khoản ngân hàng nhận tiền\n"
        "   • Đăng tải sản phẩm và giá bán\n\n"
        "3️⃣ <b>Bước 3:</b> Nhận <b>Link Bot Riêng</b> & Mã QR của shop bạn để gửi cho khách hàng mua hàng!\n"
    )
    keyboard = [
        [InlineKeyboardButton("💎 Mua Gói Ngay", callback_data="show_plans")],
        [InlineKeyboardButton("🌐 Vào Web Quản Trị", url=DASHBOARD_URL)],
    ]
    await update.effective_message.reply_text(
        text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def web_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lệnh /web: Link đăng nhập trang quản trị"""
    text = (
        "🌐 <b>TRANG WEB QUẢN TRỊ CỬA HÀNG (DASHBOARD)</b>\n\n"
        f"Truy cập: <a href='{DASHBOARD_URL}'>{DASHBOARD_URL}</a>\n\n"
        "Tại đây bạn có thể:\n"
        "• Thêm / sửa / xóa mặt hàng & giá bán\n"
        "• Cài đặt số tài khoản ngân hàng nhận tiền chuyển khoản\n"
        "• Theo dõi đơn hàng và doanh thu thời gian thực\n"
        "• Lấy Link Bot riêng và mã QR chia sẻ cho khách hàng"
    )
    keyboard = [[InlineKeyboardButton("🚀 Mở Trang Quản Trị Web", url=DASHBOARD_URL)]]
    await update.effective_message.reply_text(
        text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def hotro_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lệnh /hotro: Hỗ trợ kỹ thuật"""
    text = (
        "💬 <b>HỖ TRỢ KỸ THUẬT & TƯ VẤN 24/7</b>\n\n"
        f"• Admin hỗ trợ: @{ADMIN_CONTACT}\n"
        "• Hỗ trợ kích hoạt bot, kết nối thanh toán PayOS và giải đáp mọi thắc mắc."
    )
    keyboard = [[InlineKeyboardButton("📩 Nhắn Tin Admin Ngay", url=f"https://t.me/{ADMIN_CONTACT}")]]
    await update.effective_message.reply_text(
        text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def show_service_intro(update: Update):
    """Trang giới thiệu 2 gói dịch vụ tạo bot bán hàng."""
    text = (
        "🤖 <b>NỀN TẢNG TẠO BOT BÁN HÀNG TELEGRAM TỰ ĐỘNG</b>\n\n"
        "Chào mừng bạn đến với hệ thống tạo bot bán hàng chuyên nghiệp!\n"
        "Khi mua gói, bạn sẽ được cấp <b>Web cài đặt riêng</b> để tự do đăng mặt hàng, giá tiền, số tài khoản ngân hàng. Bot sẽ tự cập nhật và nhả <b>Link bot riêng</b> cho khách của bạn!\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "💎 <b>BẢNG GIÁ 2 GÓI DỊCH VỤ:</b>\n\n"
        "⚡ <b>1. GÓI 1 THÁNG: 50.000 VNĐ</b>\n"
        "• Thời hạn: 30 ngày sử dụng\n"
        "• Đăng sản phẩm & đơn hàng không giới hạn\n"
        "• Tự động thanh toán chuyển khoản VietQR\n"
        "• Báo đơn tức thì về Telegram của bạn\n\n"
        "👑 <b>2. GÓI VĨNH VIỄN (LIFETIME): 250.000 VNĐ</b>\n"
        "• Sở hữu <b>TRỌN ĐỜI</b> - KHÔNG BAO GIỜ hết hạn!\n"
        "• Mọi tính năng cao cấp nhất\n"
        "• Cập nhật tính năng mới miễn phí mãi mãi\n"
        "• Tiết kiệm chi phí tối đa (Khuyên dùng 🔥)\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "👇 <b>Bấm chọn gói bạn muốn mua bên dưới:</b>"
    )
    keyboard = [
        [InlineKeyboardButton("⚡ Mua Gói Tháng (50.000đ)", callback_data="buy_plan_monthly")],
        [InlineKeyboardButton("👑 Mua Gói Vĩnh Viễn (250.000đ)", callback_data="buy_plan_lifetime")],
        [
            InlineKeyboardButton("🌐 Web Quản Trị", url=DASHBOARD_URL),
            InlineKeyboardButton("💬 Hỗ Trợ", url=f"https://t.me/{ADMIN_CONTACT}"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, parse_mode="HTML", reply_markup=reply_markup)
    else:
        await update.effective_message.reply_text(text, parse_mode="HTML", reply_markup=reply_markup)


async def plan_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý bấm nút mua gói tạo bot trên Telegram"""
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

        # Tạo link VietQR chuẩn
        bank_bin = "970422" # MB Bank
        bank_acc = "0865768828" # STK mẫu / MB
        bank_name = "MB BANK"
        bank_owner = "VO DUC MANH"
        qr_url = f"https://img.vietqr.io/image/{bank_bin}-{bank_acc}-compact2.png?amount={price}&addInfo={urllib.parse.quote(order_memo)}&accountName={urllib.parse.quote(bank_owner)}"

        text = (
            f"💳 <b>THANH TOÁN GÓI {plan_name}</b>\n\n"
            f"• <b>Giá thanh toán:</b> <code>{price:,}đ</code>\n"
            f"• <b>Thời hạn:</b> {'Vĩnh viễn (Trọn đời)' if is_lifetime else '30 ngày'}\n\n"
            "🏦 <b>THÔNG TIN CHUYỂN KHOẢN (VietQR):</b>\n"
            f"• Ngân hàng: <b>{bank_name}</b>\n"
            f"• Số tài khoản: <code>{bank_acc}</code> (chạm để copy)\n"
            f"• Chủ tài khoản: <b>{bank_owner}</b>\n"
            f"• Nội dung chuyển khoản: <code>{order_memo}</code>\n\n"
            "⚠️ <i>Lưu ý: Vui lòng ghi đúng nội dung để hệ thống tự động nhận diện và kích hoạt bot cho bạn!</i>"
        )

        keyboard = [
            [InlineKeyboardButton("✅ Tôi Đã Chuyển Khoản", callback_data=f"paid_check_{plan_code}_{user.id}")],
            [InlineKeyboardButton("💬 Hỗ Trợ Trực Tiếp", url=f"https://t.me/{ADMIN_CONTACT}")],
            [InlineKeyboardButton("⬅️ Quay Lại Bảng Giá", callback_data="show_plans")],
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
                "⏳ <b>HỆ THỐNG ĐANG XÁC NHẬN GIAO DỊCH...</b>\n\n"
                "Cảm ơn bạn đã thanh toán! Hệ thống đang kiểm tra tiền vào tài khoản và sẽ kích hoạt dịch vụ cho bạn trong ít phút.\n\n"
                f"👉 Trong lúc chờ, bạn có thể truy cập Web quản trị để làm quen trước: <a href='{DASHBOARD_URL}'>{DASHBOARD_URL}</a>\n"
                f"👉 Hoặc nhắn tin trực tiếp cho Admin nếu cần gấp: @{ADMIN_CONTACT}"
            ),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🌐 Vào Web Quản Trị", url=DASHBOARD_URL)],
                [InlineKeyboardButton("💬 Nhắn Tin Admin", url=f"https://t.me/{ADMIN_CONTACT}")],
                [InlineKeyboardButton("⬅️ Về Trang Chủ", callback_data="show_plans")],
            ])
        )


# ─── Phần xử lý Deep Link cho Shop Con ─────────────────────────────

async def main_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Quay về menu chính của store đang dùng."""
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
    """Hiển thị trang chủ cửa hàng của khách hàng theo deep link."""
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
    """Edit message về trang chủ cửa hàng."""
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
