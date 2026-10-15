"""
Handler /start và Menu Sản Phẩm:
1. Gợi ý lệnh duy nhất: /start
2. Chế độ Admin: Admin test không cần trả tiền (0đ)
3. Quy trình mua: Thanh toán -> Trả Mã Liên Kết (Code) -> Nhập Web -> Nhả Link Bot Cửa Hàng Riêng
4. Bàn phím Menu dưới đáy màn hình (ReplyKeyboardMarkup)
"""
import os
import json
import random
import string
import urllib.parse
import urllib.request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
from db_helper import get_store_by_slug, get_categories_by_store, get_products_by_store
from cart_store import set_user_store, get_user_store, get_cart_count

DASHBOARD_URL = os.getenv("DASHBOARD_URL", "http://127.0.0.1:5174")
API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8088")
BOT_USERNAME = os.getenv("BOT_TAO_USERNAME", "Shoppretool_bot")
ADMIN_CONTACT = "manhkmhd2004"
ADMIN_TELEGRAM_IDS = [8337687095]

LINK_CODES_FILE = "link_codes.json"


def is_admin_user(user) -> bool:
    if not user:
        return False
    if user.id in ADMIN_TELEGRAM_IDS:
        return True
    if user.username and user.username.lower() == ADMIN_CONTACT.lower():
        return True
    return False


def generate_local_code(plan: str, tg_id: int, tg_username: str = "") -> str:
    chars = string.ascii_uppercase + string.digits
    code = f"LINK-{''.join(random.choices(chars, k=6))}"
    
    # Lưu vào file JSON cục bộ
    data = {}
    if os.path.exists(LINK_CODES_FILE):
        try:
            with open(LINK_CODES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}

    data[code] = {
        "code": code,
        "plan": plan,
        "telegram_id": tg_id,
        "telegram_username": tg_username,
        "is_used": False,
    }

    try:
        with open(LINK_CODES_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    # Gọi Backend API để lưu đồng bộ vào Database nếu backend đang chạy
    try:
        req = urllib.request.Request(
            f"{API_BASE_URL}/api/subscription/generate-code",
            data=json.dumps({
                "plan": plan,
                "telegram_id": tg_id,
                "telegram_username": tg_username,
            }).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=3) as res:
            res_data = json.loads(res.read().decode())
            if res_data.get("code"):
                return res_data["code"]
    except Exception:
        pass

    return code


def link_email_via_api(email: str, code: str, tg_id: int, tg_username: str = ""):
    """Gọi backend liên kết tài khoản web với telegram và trả về link bot riêng"""
    try:
        req = urllib.request.Request(
            f"{API_BASE_URL}/api/subscription/link-by-email",
            data=json.dumps({
                "email": email,
                "code": code,
                "telegram_id": tg_id,
                "telegram_username": tg_username,
            }).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=4) as res:
            return json.loads(res.read().decode())
    except Exception as e:
        return {"error": str(e)}


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

    # Không có deep link → Hiển thị Menu chính
    await show_service_intro(update)


async def show_service_intro(update: Update):
    """Trang chủ hiển thị Menu chọn gói sản phẩm."""
    user = update.effective_user
    is_admin = is_admin_user(user)

    if is_admin:
        text = (
            f"👑 <b>CHẾ ĐỘ QUẢN TRỊ VIÊN (ADMIN TEST MODE)</b>\n\n"
            f"Xin chào Sếp <b>Võ Đức Mạnh</b> (@{ADMIN_CONTACT})!\n"
            "Hệ thống nhận diện bạn là <b>Admin tối cao</b>.\n\n"
            "⚡ <b>QUYỀN LỢI TEST CỦA BẠN:</b>\n"
            "• Bạn <b>KHÔNG CẦN CHUYỂN KHOẢN</b> bất kỳ khoản tiền nào.\n"
            "• Nhận Mã Liên Kết test 0đ cho cả Gói 1 Tháng & Gói Vĩnh Viễn.\n"
            "• Kích hoạt thẳng vào tài khoản <code>manhkmhd2004@gmail.com</code> và nhận Link Bot cửa hàng riêng ngay lập tức!\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "👇 <b>Chọn chức năng Admin muốn test bên dưới:</b>"
        )
        keyboard = [
            [InlineKeyboardButton("⚡ [ADMIN TEST 0đ] Lấy Mã Gói 1 Tháng", callback_data="admin_test_monthly")],
            [InlineKeyboardButton("👑 [ADMIN TEST 0đ] Lấy Mã Gói Vĩnh Viễn", callback_data="admin_test_lifetime")],
            [InlineKeyboardButton("🔗 [ADMIN] Lấy Ngay Link Bot Cửa Hàng Riêng", callback_data="admin_quick_link")],
            [
                InlineKeyboardButton("🌐 Mở Web Quản Trị", url=DASHBOARD_URL),
                InlineKeyboardButton("💬 Nhắn Tin Admin", url=f"https://t.me/{ADMIN_CONTACT}"),
            ]
        ]
    else:
        text = (
            f"👋 <b>Xin chào {user.first_name or 'bạn'}!</b>\n\n"
            "Chào mừng bạn đến với <b>Hệ Thống Tạo Bot Bán Hàng Telegram</b>.\n\n"
            "📌 <b>QUY TRÌNH MUA & KÍCH HOẠT DỄ DÀNG:</b>\n"
            "1️⃣ Bạn chọn gói bên dưới & thanh toán quét mã VietQR tự động.\n"
            "2️⃣ Bot sẽ gửi ngay <b>MÃ LIÊN KẾT (Code)</b> cho bạn.\n"
            "3️⃣ Nhập mã lên Web quản trị để nhận <b>LINK BOT BÁN HÀNG RIÊNG</b> của bạn!\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "🛍️ <b>BẢNG GIÁ CÁC GÓI TẠO BOT:</b>\n\n"
            "⚡ <b>1. GÓI 1 THÁNG: 50.000 VNĐ</b>\n"
            "• Dùng 30 ngày đầy đủ mọi tính năng\n"
            "• Không giới hạn mặt hàng & đơn hàng\n"
            "• Tự động quét mã QR VietQR\n\n"
            "👑 <b>2. GÓI VĨNH VIỄN (LIFETIME): 250.000 VNĐ</b>\n"
            "• Sở hữu <b>TRỌN ĐỜI</b> - KHÔNG BAO GIỜ hết hạn!\n"
            "• Tiết kiệm chi phí tối đa (Khuyên dùng 🔥)\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "👇 <b>Bấm vào gói bạn muốn mua bên dưới:</b>"
        )
        keyboard = [
            [InlineKeyboardButton("⚡ [50.000đ] Gói 1 Tháng", callback_data="buy_plan_monthly")],
            [InlineKeyboardButton("👑 [250.000đ] Gói Vĩnh Viễn (Lifetime)", callback_data="buy_plan_lifetime")],
            [
                InlineKeyboardButton("🌐 Web Quản Trị", url=f"{DASHBOARD_URL}/settings"),
                InlineKeyboardButton("💬 Hỗ Trợ Admin", url=f"https://t.me/{ADMIN_CONTACT}"),
            ]
        ]

    reply_markup = InlineKeyboardMarkup(keyboard)

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
    is_admin = is_admin_user(user)

    if data == "show_plans":
        await show_service_intro(update)
        return

    # XỬ LÝ CHO ADMIN TEST (0đ KHÔNG CẦN CHUYỂN KHOẢN)
    if data in ["admin_test_monthly", "admin_test_lifetime"]:
        is_lifetime = (data == "admin_test_lifetime")
        plan_code = "lifetime" if is_lifetime else "monthly"
        plan_name = "VĨNH VIỄN (LIFETIME)" if is_lifetime else "1 THÁNG (30 NGÀY)"

        code = generate_local_code(plan_code, user.id, user.username or "")

        text = (
            f"🎉 <b>[ADMIN TEST 0đ] ĐÃ SINH MÃ LIÊN KẾT THÀNH CÔNG!</b>\n\n"
            f"👑 <b>Gói dịch vụ:</b> {plan_name}\n"
            f"💰 <b>Giá:</b> <code>0 VNĐ (Admin Test Miễn Phí)</code>\n\n"
            f"🔑 <b>MÃ LIÊN KẾT CỦA BẠN:</b>\n"
            f"👉 <code>{code}</code> 👈 <i>(chạm để sao chép)</i>\n\n"
            "📌 <b>BẠN CÓ THỂ THỰC HIỆN 1 TRONG 2 CÁCH:</b>\n"
            f"1️⃣ <b>Cách 1:</b> Mở Web <a href='{DASHBOARD_URL}/settings'>{DASHBOARD_URL}/settings</a>, dán mã <code>{code}</code> vào ô <b>'Kích Hoạt Bằng Mã Liên Kết'</b>.\n"
            "2️⃣ <b>Cách 2:</b> Bấm ngay nút <b>'🔗 Kích Hoạt Thẳng Vào Web'</b> bên dưới để liên kết ngay tài khoản <code>manhkmhd2004@gmail.com</code> và nhận Link Bot bán hàng ngay!"
        )

        keyboard = [
            [InlineKeyboardButton("🔗 Kích Hoạt Thẳng Vào manhkmhd2004@gmail.com", callback_data=f"link_admin_acc_{code}")],
            [InlineKeyboardButton("🌐 Mở Web Quản Trị", url=f"{DASHBOARD_URL}/settings")],
            [InlineKeyboardButton("⬅️ Quay Lại Menu", callback_data="show_plans")],
        ]
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # ADMIN BẤM LẤY NGAY LINK BOT SHOP
    if data == "admin_quick_link":
        code = generate_local_code("lifetime", user.id, user.username or "")
        res = link_email_via_api("manhkmhd2004@gmail.com", code, user.id, user.username or "")
        bot_link = res.get("bot_link", f"https://t.me/{BOT_USERNAME}?start=store_manhshop")

        text = (
            "🚀 <b>[ADMIN] LINK BOT CỬA HÀNG RIÊNG CỦA BẠN:</b>\n\n"
            f"👤 Tài khoản Web: <code>manhkmhd2004@gmail.com</code>\n"
            f"👑 Gói dịch vụ: <b>VĨNH VIỄN (LIFETIME)</b>\n\n"
            f"🔗 <b>Link Bot Bán Hàng Riêng:</b>\n"
            f"👉 <code>{bot_link}</code> 👈 <i>(chạm để sao chép)</i>\n\n"
            "💡 <i>Gửi link này cho khách hàng của bạn, họ bấm vào sẽ vào thẳng cửa hàng riêng của bạn để mua hàng!</i>"
        )
        keyboard = [
            [InlineKeyboardButton("🚀 Mở Thử Link Bot Cửa Hàng", url=bot_link)],
            [InlineKeyboardButton("🌐 Vào Web Quản Lý Sản Phẩm", url=DASHBOARD_URL)],
            [InlineKeyboardButton("⬅️ Quay Lại Menu", callback_data="show_plans")],
        ]
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if data.startswith("link_admin_acc_"):
        code = data.replace("link_admin_acc_", "")
        res = link_email_via_api("manhkmhd2004@gmail.com", code, user.id, user.username or "")
        bot_link = res.get("bot_link", f"https://t.me/{BOT_USERNAME}?start=store_manhshop")

        text = (
            "🎉 <b>LIÊN KẾT TÀI KHOẢN THÀNH CÔNG!</b>\n\n"
            f"👤 Tài khoản Web: <code>manhkmhd2004@gmail.com</code>\n"
            f"🔑 Mã liên kết đã dùng: <code>{code}</code>\n"
            f"👑 Gói dịch vụ: <b>VĨNH VIỄN (LIFETIME)</b>\n\n"
            f"🔗 <b>LINK BOT BÁN HÀNG RIÊNG CỦA BẠN ĐÃ ĐƯỢC NHẢ:</b>\n"
            f"👉 <code>{bot_link}</code> 👈\n\n"
            "✅ Hệ thống đã cập nhật trên Web Quản Trị!"
        )
        keyboard = [
            [InlineKeyboardButton("🚀 Bấm Mở Link Bot Bán Hàng", url=bot_link)],
            [InlineKeyboardButton("🌐 Vào Web Quản Trị", url=DASHBOARD_URL)],
            [InlineKeyboardButton("⬅️ Về Menu Chính", callback_data="show_plans")],
        ]
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # KHÁCH HÀNG THƯỜNG MUA GÓI
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
            f"🛒 <b>CHI TIẾT ĐƠN HÀNG: GÓI {plan_name}</b>\n\n"
            f"• <b>Sản phẩm:</b> Tạo Bot Bán Hàng Telegram ({plan_name})\n"
            f"• <b>Giá thanh toán:</b> <code>{price:,} VNĐ</code>\n"
            f"• <b>Hạn dùng:</b> {'Vĩnh viễn trọn đời' if is_lifetime else '30 ngày'}\n\n"
            "🏦 <b>THÔNG TIN CHUYỂN KHOẢN (Quét mã VietQR):</b>\n"
            f"• Ngân hàng: <b>{bank_name}</b>\n"
            f"• Số tài khoản: <code>{bank_acc}</code> <i>(chạm để sao chép)</i>\n"
            f"• Chủ tài khoản: <b>{bank_owner}</b>\n"
            f"• Nội dung CK: <code>{order_memo}</code>\n\n"
            "⚡ <i>Sau khi chuyển khoản xong, bấm nút bên dưới để nhận Mã Liên Kết ngay:</i>"
        )

        keyboard = [
            [InlineKeyboardButton("✅ Tôi Đã Chuyển Khoản (Nhận Mã)", callback_data=f"paid_check_{plan_code}_{user.id}")],
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

    # KHÁCH HÀNG BẤM TÔI ĐÃ CHUYỂN KHOẢN
    if data.startswith("paid_check_"):
        plan_type = "lifetime" if "LIFETIME" in data else "monthly"
        plan_name = "VĨNH VIỄN (LIFETIME)" if plan_type == "lifetime" else "1 THÁNG"
        code = generate_local_code(plan_type, user.id, user.username or "")

        caption = (
            "🎉 <b>XÁC NHẬN THANH TOÁN THÀNH CÔNG!</b>\n\n"
            f"Cảm ơn bạn đã đăng ký <b>Gói Tạo Bot {plan_name}</b>!\n\n"
            f"🔑 <b>MÃ LIÊN KẾT CỦA BẠN:</b>\n"
            f"👉 <code>{code}</code> 👈 <i>(chạm để sao chép)</i>\n\n"
            "📌 <b>BƯỚC TIẾP THEO ĐỂ NHẬN LINK BOT BÁN HÀNG:</b>\n"
            f"1️⃣ Truy cập Web Quản Trị: <a href='{DASHBOARD_URL}/settings'>{DASHBOARD_URL}/settings</a>\n"
            f"2️⃣ Đăng nhập tài khoản của bạn.\n"
            f"3️⃣ Dán mã <code>{code}</code> vào ô <b>'Kích Hoạt Bằng Mã Liên Kết'</b>.\n"
            "4️⃣ Hệ thống sẽ tự động kích hoạt gói và cấp <b>LINK BOT BÁN HÀNG RIÊNG</b> cho bạn ngay lập tức!"
        )

        keyboard = [
            [InlineKeyboardButton("🌐 Vào Web Quản Trị Nhập Mã", url=f"{DASHBOARD_URL}/settings")],
            [InlineKeyboardButton("💬 Nhắn Tin Hỗ Trợ Admin", url=f"https://t.me/{ADMIN_CONTACT}")],
            [InlineKeyboardButton("⬅️ Về Menu Chính", callback_data="show_plans")],
        ]

        try:
            await query.edit_message_caption(
                caption=caption,
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception:
            await query.message.reply_text(
                caption,
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(keyboard)
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
            f"Mọi thắc mắc về cài đặt bot hoặc kích hoạt gói, vui lòng liên hệ Admin:\n"
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


async def show_store_home(update: Update, context: ContextTypes.DEFAULT_TYPE, store: dict):
    welcome = store.get("welcome_message") or f"👋 Chào mừng đến với {store['store_name']}!"
    text = (
        f"🏪 <b>{store['store_name']}</b>\n\n"
        f"{welcome}\n\n"
        "🛍️ Hãy chọn danh mục bên dưới để bắt đầu mua hàng:"
    )

    categories = await get_categories_by_store(store["id"])
    keyboard = []
    for cat in categories:
        emoji = cat.get("emoji") or "🛍️"
        keyboard.append([InlineKeyboardButton(
            f"{emoji} {cat['name']}",
            callback_data=f"cat_{store['id']}_{cat['id']}"
        )])

    keyboard.append([InlineKeyboardButton("📦 Tất cả sản phẩm", callback_data=f"cat_{store['id']}_0")])
    keyboard.append([InlineKeyboardButton("🛒 Xem Giỏ hàng", callback_data=f"cart_view_{store['store_slug']}")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.message:
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode="HTML", reply_markup=reply_markup)


async def show_store_home_edit(update: Update, context: ContextTypes.DEFAULT_TYPE, store: dict):
    await show_store_home(update, context, store)
