"""
Handler /start và Menu Sản Phẩm:
1. Gợi ý lệnh duy nhất: /start
2. Mã định danh 4 số ngẫu nhiên cho mỗi cửa hàng (store_code)
3. Chức năng tìm cửa hàng theo mã 4 số
4. Khách hàng gắn chết với cửa hàng (Lock-in) để chống cạnh tranh
5. Chế độ Admin test không cần trả tiền (0đ)
"""
import os
import json
import random
import string
import urllib.parse
import urllib.request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
from db_helper import (
    get_store_by_slug,
    get_store_by_code,
    get_categories_by_store,
    get_products_by_store,
    get_customer_lock,
    set_customer_lock,
    remove_customer_lock,
    get_store_by_owner_telegram_id,
    get_store_stats_for_owner,
    get_store_by_id,
    get_owner_telegram_id,
)
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
    if user.username and user.username.lower() in [ADMIN_CONTACT.lower(), "manhkmhd2004", "manh071004"]:
        return True
    # Kiểm tra đồng bộ từ database users table
    try:
        import sqlite3
        from db_helper import DB_FILE
        with sqlite3.connect(DB_FILE) as conn:
            cur = conn.cursor()
            row = cur.execute("SELECT id FROM users WHERE telegram_id = ? AND is_admin = 1", (user.id,)).fetchone()
            if row:
                return True
    except Exception:
        pass
    return False


def generate_local_code(plan: str, tg_id: int, tg_username: str = "") -> str:
    chars = string.ascii_uppercase + string.digits
    code = f"LINK-{''.join(random.choices(chars, k=6))}"
    
    # Gọi Backend API để lưu đồng bộ vào Database
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


def get_bottom_reply_keyboard(is_admin: bool = False, is_owner: bool = False):
    """Bàn phím menu dưới đáy chat tiện lợi cho khách, Chủ shop hoặc SuperAdmin"""
    if is_admin:
        return ReplyKeyboardMarkup(
            [
                ["🛍️ Bảng Giá Sản Phẩm", "🔍 Tìm Cửa Hàng (Mã 4 Số)"],
                ["👑 Quản Trị Cửa Hàng", "🛒 Giỏ Hàng"],
                ["💬 Hỗ Trợ Khách Hàng"]
            ],
            resize_keyboard=True
        )
    if is_owner:
        return ReplyKeyboardMarkup(
            [
                ["👑 Bảng Quản Trị Shop", "🛍️ Xem Shop Của Tôi"],
                ["📋 Đơn Hàng Của Shop", "🛒 Giỏ Hàng"],
                ["💬 Hỗ Trợ Khách Hàng"]
            ],
            resize_keyboard=True
        )
    return ReplyKeyboardMarkup(
        [
            ["🛍️ Bảng Giá Sản Phẩm", "🔍 Tìm Cửa Hàng (Mã 4 Số)"],
            ["🛒 Giỏ Hàng", "📋 Đơn Hàng Của Tôi"],
            ["💬 Hỗ Trợ Khách Hàng"]
        ],
        resize_keyboard=True
    )


async def show_store_owner_home(update: Update, context: ContextTypes.DEFAULT_TYPE, store: dict):
    """Trang điều khiển dành riêng cho Chủ cửa hàng khi liên kết Telegram với Web."""
    stats = await get_store_stats_for_owner(store["id"])
    store_code = store.get("store_code") or "8868"
    bot_link = f"https://t.me/{BOT_USERNAME}?start=store_{store['store_slug']}"

    text = (
        f"👑 <b>CHÀO MỪNG QUẢN TRỊ VIÊN CỬA HÀNG!</b>\n\n"
        f"🏪 Cửa hàng: <b>{store['store_name']}</b>\n"
        f"🔢 Mã định danh 4 số: <code>#{store_code}</code>\n"
        f"👤 Tài khoản Web: <code>{store.get('owner_email') or 'Chính chủ'}</code>\n"
        f"💎 Gói dịch vụ: <b>{str(store.get('owner_plan', 'free')).upper()}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📊 <b>THỐNG KÊ KINH DOANH CỦA SHOP:</b>\n"
        f"• 💰 Doanh thu thực tế: <b>{stats['total_revenue']:,} VNĐ</b>\n"
        f"• 📦 Sản phẩm đang bán: <b>{stats['products_count']}</b> món\n"
        f"• 🛒 Tổng đơn hàng: <b>{stats['orders_count']}</b> đơn\n"
        f"• 🔒 Khách hàng gắn chết: <b>{stats['locked_customers_count']}</b> người\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "✨ <i>Mỗi khi có đơn hàng mới hoặc khách bấm nút 'Hỗ trợ', Bot sẽ tự động gửi tin nhắn trực tiếp vào đây để bạn hỗ trợ khách ngay lập tức!</i>\n\n"
        "👇 <b>Chọn chức năng quản lý:</b>"
    )

    keyboard = [
        [InlineKeyboardButton("🛍️ Mở Cửa Hàng Của Tôi (Góc Nhìn Khách)", callback_data=f"owner_view_shop_{store['store_slug']}")],
        [InlineKeyboardButton("📋 Danh Sách Đơn Hàng Của Shop", callback_data=f"owner_orders_{store['id']}")],
        [InlineKeyboardButton("🔗 Lấy Link Bot & Mã Định Danh 4 Số", callback_data=f"owner_share_link_{store['id']}")],
        [InlineKeyboardButton("💬 Hướng Dẫn Hỗ Trợ Khách Hàng", callback_data=f"owner_support_info_{store['id']}")],
        [
            InlineKeyboardButton("🌐 Web Quản Trị Cửa Hàng", url=f"{DASHBOARD_URL}/dashboard"),
            InlineKeyboardButton("💬 Hỗ Trợ Admin Tối Cao", url=f"https://t.me/{ADMIN_CONTACT}"),
        ]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)
    bottom_kb = get_bottom_reply_keyboard(is_admin=False, is_owner=True)
    if update.message:
        await update.message.reply_text(
            f"👑 Xin chào Chủ cửa hàng <b>{store['store_name']}</b>!",
            parse_mode="HTML",
            reply_markup=bottom_kb
        )
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, parse_mode="HTML", reply_markup=reply_markup)


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args  # ["store_SLUG"] hoặc ["code_1234"] hoặc ["1234"] hoặc ["claim_..."]
    is_admin = is_admin_user(user)

    # ══════════════════════════════════════════════════════════════════════════
    # 0. ƯU TIÊN SỐ 1: LIÊN KẾT QUYỀN ADMIN CỬA HÀNG QUA LINK (claim_ / admin_)
    # ══════════════════════════════════════════════════════════════════════════
    # Dù tài khoản Telegram này trước đó từng bị khóa vào shop khác làm khách hàng,
    # việc liên kết làm Admin cửa hàng luôn được ƯU TIÊN TUYỆT ĐỐI và tự động gỡ khóa khách hàng!
    if args:
        arg = args[0].strip()
        if arg.startswith("admin_") or arg.startswith("claim_"):
            target_key = arg.replace("admin_", "").replace("claim_", "").strip()
            from db_helper import link_owner_telegram_by_code
            result = await link_owner_telegram_by_code(target_key, user.id)
            status = result.get("status")
            store = result.get("store")

            if status == "success":
                # Đã liên kết Admin thành công -> Gỡ bỏ hoàn toàn khóa khách hàng cũ
                await remove_customer_lock(user.id)
                set_user_store(user.id, store["store_slug"])
                username_str = f"@{user.username}" if user.username else f"ID: {user.id}"
                if update.message:
                    await update.message.reply_text(
                        f"🎉 <b>LIÊN KẾT CHỦ CỬA HÀNG THÀNH CÔNG! (1 LẦN DUY NHẤT)</b>\n\n"
                        f"👑 Tài khoản Telegram: <b>{username_str}</b>\n"
                        f"🏪 Cửa hàng: <b>{store['store_name']}</b> (Mã #{store.get('store_code') or 'Shop'})\n\n"
                        f"🔒 <b>Lưu ý bảo mật:</b> Link liên kết này <b>đã hết hiệu lực ngay lập tức</b>. Hệ thống không cho phép bất kỳ tài khoản Telegram nào khác gắn vào cửa hàng này nữa.\n\n"
                        f"✅ <b>Quyền hạn đã kích hoạt:</b>\n"
                        f"• Nhận thông báo tức thì khi có khách đặt hàng.\n"
                        f"• Nhận thông báo kèm nút <b>[✅ Duyệt Đơn Này]</b> khi khách chuyển khoản.\n"
                        f"• Nhận tin nhắn hỗ trợ từ khách và chat trực tiếp với khách.\n\n"
                        f"👇 Bấm nút bên dưới để mở Bảng điều khiển cửa hàng:",
                        parse_mode="HTML"
                    )
                await show_store_owner_home(update, context, store)
                return

            elif status == "already_self":
                await remove_customer_lock(user.id)
                set_user_store(user.id, store["store_slug"])
                if update.message:
                    await update.message.reply_text(
                        f"👑 <b>BẠN ĐÃ LÀ ADMIN CỦA CỬA HÀNG NÀY RỒI!</b>\n\n"
                        f"🏪 Cửa hàng: <b>{store['store_name']}</b>\n"
                        f"Tài khoản Telegram của bạn đã được gắn cố định với cửa hàng.",
                        parse_mode="HTML"
                    )
                await show_store_owner_home(update, context, store)
                return

            elif status == "already_claimed":
                if update.message:
                    await update.message.reply_text(
                        "⛔ <b>LINK LIÊN KẾT ĐÃ HẾT HIỆU LỰC!</b>\n\n"
                        "Cửa hàng này <b>đã được liên kết với một tài khoản Telegram Admin khác trước đó</b>. Hệ thống chỉ cho phép liên kết 1 lần duy nhất và đã khóa quyền gắn tài khoản để chống chiếm đoạt quyền quản trị.\n\n"
                        "👉 Nếu bạn là chủ sở hữu hợp pháp và muốn đổi nick Telegram, vui lòng đăng nhập vào Web Quản Trị bằng Email & Mật khẩu để tạo lại link mới.",
                        parse_mode="HTML"
                    )
                return

            else:
                if update.message:
                    await update.message.reply_text(
                        "⚠️ <b>Link liên kết không hợp lệ hoặc đã hết hạn!</b>\n"
                        "Vui lòng đăng nhập vào trang quản trị Web để lấy link mới nhất.",
                        parse_mode="HTML"
                    )
                return

    # ══════════════════════════════════════════════════════════════════════════
    # 1. KIỂM TRA NGƯỜI DÙNG CÓ PHẢI CHỦ CỬA HÀNG KHÔNG (STORE OWNER)
    # ══════════════════════════════════════════════════════════════════════════
    owner_store = await get_store_by_owner_telegram_id(user.id)
    if owner_store:
        # Nếu đã là Admin/Chủ shop, tự động xóa mọi customer_lock cũ
        await remove_customer_lock(user.id)
        if not args:
            set_user_store(user.id, owner_store["store_slug"])
            await show_store_owner_home(update, context, owner_store)
            return

    # ══════════════════════════════════════════════════════════════════════════
    # 2. KIỂM TRA KHÁCH HÀNG ĐÃ BỊ GẮN CHẾT VỚI CỬA HÀNG NÀO CHƯA (STICKY CUSTOMER LOCK)
    # ══════════════════════════════════════════════════════════════════════════
    # (Chỉ áp dụng với khách thông thường, KHÔNG áp dụng với SuperAdmin hoặc Chủ shop)
    if not is_admin and not owner_store:
        lock = await get_customer_lock(user.id)
        if lock:
            store = await get_store_by_slug(lock["store_slug"])
            if store:
                set_user_store(user.id, store["store_slug"])
                # Nếu khách cố tình bấm vào link của shop khác
                if args and args[0] not in [f"store_{store['store_slug']}", store.get("store_code"), f"code_{store.get('store_code')}"]:
                    if update.message:
                        await update.message.reply_text(
                            f"🔒 <b>BẠN ĐÃ ĐƯỢC LIÊN KẾT CỐ ĐỊNH VỚI SHOP:</b>\n"
                            f"🏪 <b>{lock['store_name']}</b> (Mã #{lock.get('store_code') or 'Shop'})\n\n"
                            "Để bảo vệ quyền lợi bảo hành và giao dịch an toàn, tài khoản của bạn được gắn cố định với cửa hàng này, không thể chuyển sang cửa hàng khác.\n\n"
                            f"👇 Tiếp tục mua sắm tại <b>{lock['store_name']}</b>:",
                            parse_mode="HTML"
                        )
                await show_store_home(update, context, store)
                return
            else:
                # Cửa hàng đã hết hạn hoặc bị xóa khỏi hệ thống -> Gỡ khóa ngay để khách tự do!
                await remove_customer_lock(user.id)
                if update.message:
                    await update.message.reply_text(
                        "ℹ️ <b>THÔNG BÁO HỆ THỐNG:</b>\n"
                        "Cửa hàng trước đây bạn từng liên kết hiện đã <b>tạm dừng hoạt động hoặc đã bị đóng cửa</b>.\n\n"
                        "✅ Tài khoản của bạn đã được <b>mở khóa tự do</b>. Bạn có thể sử dụng các dịch vụ chính hoặc liên kết mua sắm tại bất kỳ cửa hàng nào khác!",
                        parse_mode="HTML"
                    )

    # ══════════════════════════════════════════════════════════════════════════
    # 3. KHÁCH MỚI / CHỦ SHOP VÀO QUA DEEP LINK HOẶC MÃ ĐỊNH DANH 4 SỐ
    # ══════════════════════════════════════════════════════════════════════════
    if args:
        arg = args[0].strip()

        # Deep link theo slug: store_<slug>
        if arg.startswith("store_"):
            slug = arg[len("store_"):]
            store = await get_store_by_slug(slug)
            if store:
                if not is_admin:
                    await set_customer_lock(user.id, store["id"], store["store_slug"])
                set_user_store(user.id, slug)
                if is_admin and update.message:
                    await update.message.reply_text(
                        f"👑 <b>[ADMIN TEST MODE]</b>\n"
                        f"Đang xem cửa hàng: <b>{store['store_name']}</b> (Mã #{store.get('store_code') or 'N/A'})\n"
                        f"<i>Tài khoản Admin không bị khóa, bạn có thể tự do test hoặc đổi sang shop khác bất cứ lúc nào!</i>",
                        parse_mode="HTML"
                    )
                await show_store_home(update, context, store)
                return
            else:
                if update.message:
                    await update.message.reply_text(
                        "⚠️ <b>Cửa hàng này hiện đang tạm dừng hoạt động hoặc không tồn tại!</b>\n"
                        "Vui lòng liên hệ chủ cửa hàng để kiểm tra hoặc trải nghiệm các dịch vụ khác của BotStore.",
                        parse_mode="HTML"
                    )

        # Deep link theo mã 4 số: code_<4digits> hoặc <4digits>
        code_candidate = arg.replace("code_", "")
        if code_candidate.isdigit() and len(code_candidate) == 4:
            store = await get_store_by_code(code_candidate)
            if store:
                if not is_admin:
                    await set_customer_lock(user.id, store["id"], store["store_slug"])
                set_user_store(user.id, store["store_slug"])
                if is_admin and update.message:
                    await update.message.reply_text(
                        f"👑 <b>[ADMIN TEST MODE]</b>\n"
                        f"Đang xem cửa hàng: <b>{store['store_name']}</b> (Mã #{code_candidate})\n"
                        f"<i>Tài khoản Admin không bị khóa, bạn có thể tự do test hoặc đổi sang shop khác bất cứ lúc nào!</i>",
                        parse_mode="HTML"
                    )
                await show_store_home(update, context, store)
                return
            else:
                if update.message:
                    await update.message.reply_text(
                        f"⚠️ <b>Không tìm thấy cửa hàng với mã #{code_candidate} hoặc cửa hàng đã hết hạn dịch vụ!</b>",
                        parse_mode="HTML"
                    )

    # 3. KHÁCH CHƯA CÓ SHOP VÀO BOT TRỰC TIẾP
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
            "⚡ <b>QUYỀN LỢI & CÔNG CỤ TEST CỦA BẠN:</b>\n"
            "• Bạn <b>KHÔNG BỊ KHÓA</b> vào bất kỳ cửa hàng nào.\n"
            "• Quản trị & kiểm soát toàn bộ cửa hàng trên hệ thống.\n"
            "• Bật/Tắt shop, mở khóa khách hàng, sinh lại mã 4 số.\n"
            "• Test mua hàng 0đ cho cả Gói 1 Tháng & Gói Vĩnh Viễn.\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "👇 <b>Chọn chức năng Admin muốn điều khiển:</b>"
        )
        keyboard = [
            [InlineKeyboardButton("👑 [ADMIN] Quản Trị Toàn Bộ Cửa Hàng", callback_data="admin_list_stores")],
            [InlineKeyboardButton("⚡ [ADMIN TEST 0đ] Lấy Mã Gói 1 Tháng", callback_data="admin_test_monthly")],
            [InlineKeyboardButton("👑 [ADMIN TEST 0đ] Lấy Mã Gói Vĩnh Viễn", callback_data="admin_test_lifetime")],
            [InlineKeyboardButton("🔗 [ADMIN] Lấy Ngay Link Bot & Mã 4 Số", callback_data="admin_quick_link")],
            [
                InlineKeyboardButton("🌐 Web Quản Trị Shop", url=f"{DASHBOARD_URL}/dashboard/admin-stores"),
                InlineKeyboardButton("💬 Nhắn Tin Admin", url=f"https://t.me/{ADMIN_CONTACT}"),
            ]
        ]
    else:
        text = (
            f"👋 <b>Xin chào {user.first_name or 'bạn'}!</b>\n\n"
            "Chào mừng bạn đến với <b>Hệ Thống Tạo Bot Bán Hàng Telegram</b>.\n\n"
            "📌 <b>BẠN MUỐN LÀM GÌ HÔM NAY?</b>\n\n"
            "1️⃣ <b>Bạn là Khách Mua Hàng:</b>\n"
            "👉 Bấm <b>'🔍 Tìm Cửa Hàng (Mã 4 Số)'</b> bên dưới và nhập mã định danh do chủ shop cung cấp để vào mua sắm!\n\n"
            "2️⃣ <b>Bạn Muốn Tạo Bot Bán Hàng Riêng:</b>\n"
            "👉 Chọn một trong 2 gói dịch vụ bên dưới để sở hữu ngay hệ thống bot + web bán hàng riêng biệt!\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "🛍️ <b>BẢNG GIÁ GÓI TẠO BOT:</b>\n\n"
            "⚡ <b>1. GÓI 1 THÁNG: 50.000 VNĐ</b>\n"
            "• Dùng 30 ngày đầy đủ mọi tính năng\n"
            "• Cấp Mã Định Danh 4 số riêng biệt\n"
            "• Gắn chết khách hàng với shop chống cạnh tranh\n\n"
            "👑 <b>2. GÓI VĨNH VIỄN (LIFETIME): 250.000 VNĐ</b>\n"
            "• Sở hữu <b>TRỌN ĐỜI</b> - KHÔNG BAO GIỜ hết hạn!\n"
            "• Tiết kiệm chi phí tối đa (Khuyên dùng 🔥)\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "👇 <b>Chọn chức năng bên dưới để tiếp tục:</b>"
        )
        keyboard = [
            [InlineKeyboardButton("🔍 Tìm Cửa Hàng (Nhập Mã 4 Số)", callback_data="btn_search_store")],
            [InlineKeyboardButton("⚡ [50.000đ] Mua Gói 1 Tháng", callback_data="buy_plan_monthly")],
            [InlineKeyboardButton("👑 [250.000đ] Mua Gói Vĩnh Viễn", callback_data="buy_plan_lifetime")],
            [
                InlineKeyboardButton("🌐 Web Quản Trị", url=f"{DASHBOARD_URL}/settings"),
                InlineKeyboardButton("💬 Hỗ Trợ Admin", url=f"https://t.me/{ADMIN_CONTACT}"),
            ]
        ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.message:
        await update.message.reply_text(
            "📱 Bàn phím Menu chức năng đã sẵn sàng bên dưới!",
            reply_markup=get_bottom_reply_keyboard(is_admin)
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

    # ─── CALLBACKS DÀNH CHO CHỦ CỬA HÀNG ───
    if data == "owner_home":
        owner_store = await get_store_by_owner_telegram_id(user.id)
        if owner_store:
            await show_store_owner_home(update, context, owner_store)
        else:
            await show_service_intro(update)
        return

    if data.startswith("owner_view_shop_"):
        slug = data.replace("owner_view_shop_", "")
        store = await get_store_by_slug(slug)
        if store:
            set_user_store(user.id, store["store_slug"])
            await show_store_home(update, context, store)
        return

    if data.startswith("owner_orders_"):
        store_id = int(data.replace("owner_orders_", ""))
        store = await get_store_by_id(store_id)
        import sqlite3
        from db_helper import DB_FILE
        rows = []
        try:
            with sqlite3.connect(DB_FILE) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.cursor().execute(
                    "SELECT * FROM orders WHERE store_id = ? ORDER BY id DESC LIMIT 10", (store_id,)
                ).fetchall()
        except Exception:
            pass

        if not rows:
            text = (
                f"📋 <b>ĐƠN HÀNG CỦA CỬA HÀNG: {store['store_name'] if store else ''}</b>\n\n"
                "Hiện tại shop của bạn chưa có đơn hàng nào phát sinh.\n"
                "Hãy chia sẻ link bot hoặc mã 4 số để đón những khách hàng đầu tiên!"
            )
        else:
            text = f"📋 <b>10 ĐƠN HÀNG GẦN NHẤT - {store['store_name'] if store else ''}:</b>\n\n"
            for r in rows:
                st_emoji = "✅" if r["status"] in ["paid", "completed"] else "⏳"
                text += f"{st_emoji} <b>{r['order_code']}</b>: {r['total_amount']:,}đ\n"
                text += f"   • Khách: {r['customer_name'] or 'Khách'} (ID: <code>{r['customer_tg_id']}</code>)\n"
                text += f"   • Trạng thái: <b>{r['status'].upper()}</b>\n\n"

        keyboard = [
            [InlineKeyboardButton("⬅️ Về Bảng Quản Trị", callback_data="owner_home")],
            [InlineKeyboardButton("🌐 Quản Trị Đơn Chi Tiết Trên Web", url=f"{DASHBOARD_URL}/dashboard/orders")]
        ]
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if data.startswith("owner_share_link_"):
        store_id = int(data.replace("owner_share_link_", ""))
        store = await get_store_by_id(store_id)
        if store:
            store_code = store.get("store_code") or "8868"
            bot_link = f"https://t.me/{BOT_USERNAME}?start=store_{store['store_slug']}"
            text = (
                f"🔗 <b>LINK BOT & MÃ ĐỊNH DANH 4 SỐ CỦA SHOP BẠN:</b>\n\n"
                f"🏪 Cửa hàng: <b>{store['store_name']}</b>\n\n"
                f"🔢 <b>MÃ 4 SỐ ĐỊNH DANH DUY NHẤT:</b>\n"
                f"👉 <code>{store_code}</code> 👈 <i>(Khách chỉ cần gõ {store_code} vào bot là vào shop!)</i>\n\n"
                f"📎 <b>LINK BOT BÁN HÀNG:</b>\n"
                f"👉 <code>{bot_link}</code> 👈\n\n"
                f"🔒 <b>Cơ chế Khóa Khách Hàng (Lock-in):</b>\n"
                "Khi khách hàng dùng link hoặc nhập mã này, tài khoản của khách sẽ được <b>gắn chết vĩnh viễn với shop của bạn</b> để chống cạnh tranh!"
            )
            keyboard = [
                [InlineKeyboardButton("🚀 Mở Thử Shop Của Tôi", url=bot_link)],
                [InlineKeyboardButton("⬅️ Về Bảng Quản Trị", callback_data="owner_home")]
            ]
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if data.startswith("owner_support_info_"):
        store_id = int(data.replace("owner_support_info_", ""))
        store = await get_store_by_id(store_id)
        text = (
            f"💬 <b>HỆ THỐNG HỖ TRỢ KHÁCH HÀNG TỰ ĐỘNG - {store['store_name'] if store else ''}</b>\n\n"
            "⚡ <b>Cơ chế hỗ trợ khách hàng:</b>\n"
            "1️⃣ Tất cả khách hàng trong shop của bạn đều có nút <b>'💬 Hỗ Trợ Khách Hàng'</b>.\n"
            "2️⃣ Khi khách bấm nút và gửi tin nhắn, <b>Bot sẽ gửi ngay tin nhắn của khách vào đây cho bạn</b>!\n"
            "3️⃣ Bạn chỉ cần bấm nút <b>'↩️ Trả Lời Khách Hàng'</b>, Bot sẽ chuyển câu trả lời của bạn tới khách hàng ngay lập tức!\n"
            "4️⃣ Khi có đơn hàng mới phát sinh, Bot cũng gửi thông tin chi tiết đơn hàng cho bạn kèm nút chat với khách."
        )
        keyboard = [
            [InlineKeyboardButton("⬅️ Về Bảng Quản Trị", callback_data="owner_home")]
        ]
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # ─── NÚT HỖ TRỢ DÀNH CHO KHÁCH HÀNG ───
    if data.startswith("support_store_"):
        store_id = int(data.replace("support_store_", ""))
        store = await get_store_by_id(store_id)
        store_name = store["store_name"] if store else "Cửa hàng"
        context.user_data["awaiting_support_store_id"] = store_id

        text = (
            f"💬 <b>HỖ TRỢ KHÁCH HÀNG - {store_name}</b>\n\n"
            "Bạn đang cần Chủ cửa hàng tư vấn, giải đáp thắc mắc hoặc hỗ trợ đơn hàng?\n\n"
            "👉 <b>Hãy nhập nội dung câu hỏi/tin nhắn của bạn vào khung chat bên dưới và gửi đi.</b>\n"
            "Bot sẽ chuyển trực tiếp tin nhắn của bạn cho Chủ cửa hàng để phản hồi sớm nhất có thể!"
        )
        keyboard = [
            [InlineKeyboardButton("⬅️ Quay Lại Mua Sắm", callback_data=f"owner_view_shop_{store['store_slug']}")] if store else [InlineKeyboardButton("⬅️ Quay Lại", callback_data="show_plans")]
        ]
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # ─── NÚT TRẢ LỜI KHÁCH HÀNG DÀNH CHO CHỦ SHOP ───
    if data.startswith("reply_cust_"):
        parts = data.split("_")
        customer_id = int(parts[2])
        store_id = int(parts[3])
        store = await get_store_by_id(store_id)
        context.user_data["replying_to_customer"] = {
            "customer_id": customer_id,
            "store_id": store_id,
        }
        text = (
            f"✏️ <b>TRẢ LỜI TIN NHẮN KHÁCH HÀNG (ID: <code>{customer_id}</code>)</b>\n\n"
            f"Cửa hàng: <b>{store['store_name'] if store else ''}</b>\n\n"
            "👉 <b>Hãy nhập nội dung câu trả lời của bạn vào khung chat bên dưới và gửi đi.</b>\n"
            "Bot sẽ gửi trực tiếp câu trả lời của bạn tới khách hàng ngay lập tức!"
        )
        keyboard = [
            [InlineKeyboardButton("❌ Hủy Bỏ", callback_data="owner_home")]
        ]
        await query.message.reply_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # NÚT BẤM TÌM CỬA HÀNG
    if data == "btn_search_store":
        text = (
            "🔍 <b>TÌM KIẾM CỬA HÀNG BẰNG MÃ ĐỊNH DANH 4 SỐ</b>\n\n"
            "Mỗi cửa hàng trên hệ thống đều có 1 <b>Mã Định Danh gồm 4 chữ số</b> (Ví dụ: <code>8868</code>).\n\n"
            "👉 Hãy <b>nhập ngay 4 số đó</b> vào khung chat và gửi đi, bot sẽ đưa bạn tới thẳng cửa hàng đó!\n\n"
            "<i>(Lưu ý: Sau khi vào, bạn sẽ được gắn cố định với cửa hàng đó để hưởng chế độ bảo hành đơn hàng).</i>"
        )
        keyboard = [
            [InlineKeyboardButton("⬅️ Quay Lại", callback_data="show_plans")]
        ]
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
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
            "2️⃣ <b>Cách 2:</b> Bấm ngay nút <b>'🔗 Kích Hoạt Thẳng Vào Web'</b> bên dưới để nhận ngay Link Bot & Mã Định Danh 4 Số!"
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
        bot_link = res.get("bot_link", f"https://t.me/{BOT_USERNAME}?start=store_admin-manh")
        store_code = res.get("store_code", "8868")

        text = (
            "🚀 <b>[ADMIN] THÔNG TIN CỬA HÀNG RIÊNG CỦA BẠN:</b>\n\n"
            f"👤 Tài khoản Web: <code>manhkmhd2004@gmail.com</code>\n"
            f"👑 Gói dịch vụ: <b>VĨNH VIỄN (LIFETIME)</b>\n\n"
            f"🔢 <b>MÃ ĐỊNH DANH 4 SỐ (Duy nhất):</b>\n"
            f"👉 <code>{store_code}</code> 👈 <i>(Khách chỉ cần gõ {store_code} là vào thẳng shop!)</i>\n\n"
            f"🔗 <b>Link Bot Bán Hàng Riêng:</b>\n"
            f"👉 <code>{bot_link}</code> 👈\n\n"
            "🔒 <b>Cơ chế Sticky:</b> Khi khách dùng link này hoặc nhập mã <b>#{store_code}</b>, khách sẽ bị <b>gắn chết vĩnh viễn với shop của bạn</b>!"
        )
        keyboard = [
            [InlineKeyboardButton("🚀 Mở Thử Cửa Hàng Riêng", url=bot_link)],
            [InlineKeyboardButton("🌐 Vào Web Quản Lý Sản Phẩm", url=DASHBOARD_URL)],
            [InlineKeyboardButton("⬅️ Quay Lại Menu", callback_data="show_plans")],
        ]
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if data.startswith("link_admin_acc_"):
        code = data.replace("link_admin_acc_", "")
        res = link_email_via_api("manhkmhd2004@gmail.com", code, user.id, user.username or "")
        bot_link = res.get("bot_link", f"https://t.me/{BOT_USERNAME}?start=store_admin-manh")
        store_code = res.get("store_code", "8868")

        text = (
            "🎉 <b>LIÊN KẾT TÀI KHOẢN THÀNH CÔNG!</b>\n\n"
            f"👤 Tài khoản Web: <code>manhkmhd2004@gmail.com</code>\n"
            f"👑 Gói dịch vụ: <b>VĨNH VIỄN (LIFETIME)</b>\n\n"
            f"🔢 <b>MÃ ĐỊNH DANH 4 SỐ CỦA BẠN:</b> <code>{store_code}</code>\n"
            f"🔗 <b>LINK BOT BÁN HÀNG RIÊNG:</b>\n"
            f"👉 <code>{bot_link}</code> 👈\n\n"
            "🔒 Khách hàng dùng mã hoặc link này sẽ bị gắn chết với shop của bạn!"
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

        bank_bin = "970422" # MB Bank
        bank_acc = "0865768828"
        bank_name = "MB BANK"
        bank_owner = "VO DUC MANH"
        qr_url = f"https://img.vietqr.io/image/{bank_bin}-{bank_acc}-compact2.png?amount={price}&addInfo={urllib.parse.quote(order_memo)}&accountName={urllib.parse.quote(bank_owner)}"

        text = (
            f"🛒 <b>CHI TIẾT ĐƠN HÀNG: GÓI {plan_name}</b>\n\n"
            f"• <b>Sản phẩm:</b> Tạo Bot Bán Hàng Telegram ({plan_name})\n"
            f"• <b>Giá thanh toán:</b> <code>{price:,} VNĐ</code>\n"
            f"• <b>Quyền lợi:</b> Nhận Link Bot riêng + Mã Định Danh 4 số riêng + Gắn chết khách hàng\n\n"
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
            "📌 <b>BƯỚC TIẾP THEO:</b>\n"
            f"1️⃣ Truy cập Web Quản Trị: <a href='{DASHBOARD_URL}/settings'>{DASHBOARD_URL}/settings</a>\n"
            f"2️⃣ Dán mã <code>{code}</code> vào ô <b>'Kích Hoạt Bằng Mã Liên Kết'</b>.\n"
            "3️⃣ Hệ thống sẽ cấp <b>LINK BOT RIÊNG & MÃ ĐỊNH DANH 4 SỐ</b> cho bạn để kinh doanh ngay!"
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
    """Bắt các sự kiện khi khách bấm nút hoặc gõ tin nhắn"""
    user = update.effective_user
    text = (update.message.text or "").strip()
    is_admin = is_admin_user(user)

    # ─── 0. XỬ LÝ KHÁCH HÀNG GỬI YÊU CẦU HỖ TRỢ CHO CHỦ CỬA HÀNG ───
    if context.user_data.get("awaiting_support_store_id"):
        store_id = context.user_data.pop("awaiting_support_store_id")
        store = await get_store_by_id(store_id)
        owner_tg_id = await get_owner_telegram_id(store_id)
        store_name = store["store_name"] if store else "Cửa hàng"

        # 1. Báo xác nhận cho khách hàng
        await update.message.reply_text(
            f"✅ <b>Yêu cầu hỗ trợ của bạn đã được gửi thành công!</b>\n\n"
            f"Chủ cửa hàng <b>{store_name}</b> đã nhận được tin nhắn và sẽ trả lời bạn sớm nhất có thể.\n\n"
            f"📝 <b>Nội dung đã gửi:</b> <i>\"{text}\"</i>",
            parse_mode="HTML"
        )

        # 2. Chuyển tiếp tin nhắn cho Chủ cửa hàng
        if owner_tg_id:
            customer_name = user.full_name or user.first_name or "Khách hàng"
            customer_uname = f"@{user.username}" if user.username else "Không có username"
            owner_msg = (
                f"📩 <b>YÊU CẦU HỖ TRỢ TỪ KHÁCH HÀNG!</b>\n\n"
                f"🏪 Cửa hàng: <b>{store_name}</b>\n"
                f"👤 Khách hàng: <b>{customer_name}</b> ({customer_uname})\n"
                f"🆔 Telegram ID: <code>{user.id}</code>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"💬 <b>Nội dung tin nhắn khách gửi:</b>\n"
                f"<i>\"{text}\"</i>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"👉 Bấm nút <b>'↩️ Trả Lời Khách Hàng'</b> bên dưới để trả lời lại ngay qua Bot:"
            )
            buttons = [
                [InlineKeyboardButton("↩️ Trả Lời Khách Hàng", callback_data=f"reply_cust_{user.id}_{store_id}")]
            ]
            if user.username:
                buttons.append([InlineKeyboardButton("💬 Chat Telegram Trực Tiếp", url=f"https://t.me/{user.username}")])

            import httpx
            from config import BOT_TOKEN
            async with httpx.AsyncClient() as client:
                try:
                    await client.post(
                        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                        json={
                            "chat_id": owner_tg_id,
                            "text": owner_msg,
                            "parse_mode": "HTML",
                            "reply_markup": {"inline_keyboard": [[b.to_dict() for b in row] for row in buttons]},
                        },
                        timeout=10,
                    )
                except Exception as e:
                    print(f"[!] Lỗi chuyển tin nhắn cho chủ shop: {e}")
        return

    # ─── 0.1 XỬ LÝ CHỦ CỬA HÀNG TRẢ LỜI LẠI KHÁCH HÀNG ───
    if context.user_data.get("replying_to_customer"):
        target = context.user_data.pop("replying_to_customer")
        customer_id = target["customer_id"]
        store_id = target["store_id"]
        store = await get_store_by_id(store_id)
        store_name = store["store_name"] if store else "Cửa hàng"

        # Báo cho chủ shop
        await update.message.reply_text(
            f"✅ <b>Đã gửi phản hồi thành công tới khách hàng!</b>\n\n"
            f"Nội dung phản hồi: <i>\"{text}\"</i>",
            parse_mode="HTML"
        )

        # Gửi vào Telegram của khách hàng
        cust_msg = (
            f"📩 <b>PHẢN HỒI TỪ CHỦ CỬA HÀNG {store_name}!</b>\n\n"
            f"💬 <i>\"{text}\"</i>\n\n"
            f"👉 Nếu bạn cần hỏi thêm, hãy bấm nút <b>'💬 Tiếp Tục Hỗ Trợ'</b> bên dưới:"
        )
        buttons = [
            [InlineKeyboardButton("💬 Tiếp Tục Hỗ Trợ", callback_data=f"support_store_{store_id}")]
        ]
        if store:
            buttons.append([InlineKeyboardButton("🛍️ Xem Cửa Hàng", callback_data=f"owner_view_shop_{store['store_slug']}")])

        import httpx
        from config import BOT_TOKEN
        async with httpx.AsyncClient() as client:
            try:
                await client.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                    json={
                        "chat_id": customer_id,
                        "text": cust_msg,
                        "parse_mode": "HTML",
                        "reply_markup": {"inline_keyboard": [[b.to_dict() for b in row] for row in buttons]},
                    },
                    timeout=10,
                )
            except Exception as e:
                print(f"[!] Lỗi gửi phản hồi tới khách hàng: {e}")
        return

    # 1. KHÁCH GÕ MÃ ĐỊNH DANH 4 CHỮ SỐ (VD: 8868)
    if text.isdigit() and len(text) == 4:
        # Kiểm tra khách có bị gắn chết với shop khác không
        if not is_admin:
            lock = await get_customer_lock(user.id)
            if lock:
                curr_store = await get_store_by_slug(lock["store_slug"])
                await update.message.reply_text(
                    f"🔒 <b>BẠN ĐÃ ĐƯỢC LIÊN KẾT CỐ ĐỊNH VỚI SHOP:</b>\n"
                    f"🏪 <b>{lock['store_name']}</b> (Mã #{lock.get('store_code') or 'Shop'})\n\n"
                    "Để bảo vệ quyền lợi bảo hành, bạn không thể chuyển sang cửa hàng khác.\n\n"
                    f"👇 Tiếp tục mua sắm tại <b>{lock['store_name']}</b>:",
                    parse_mode="HTML"
                )
                if curr_store:
                    await show_store_home(update, context, curr_store)
                return

        # Khách chưa bị khóa -> Tìm cửa hàng theo mã 4 số
        store = await get_store_by_code(text)
        if store:
            if not is_admin:
                await set_customer_lock(user.id, store["id"], store["store_slug"])
            set_user_store(user.id, store["store_slug"])
            if is_admin:
                await update.message.reply_text(
                    f"👑 <b>[ADMIN TEST MODE]</b>\n\n"
                    f"🏪 Cửa hàng: <b>{store['store_name']}</b>\n"
                    f"🔢 Mã định danh: <code>#{text}</code>\n\n"
                    "<i>Tài khoản Admin không bị gắn chết với shop, có thể tự do test hoặc đổi sang shop khác bất cứ lúc nào!</i>",
                    parse_mode="HTML"
                )
            else:
                await update.message.reply_text(
                    f"🎉 <b>ĐÃ TÌM THẤY & LIÊN KẾT THÀNH CÔNG!</b>\n\n"
                    f"🏪 Cửa hàng: <b>{store['store_name']}</b>\n"
                    f"🔢 Mã định danh: <code>#{text}</code>\n\n"
                    "🔒 <i>Tài khoản của bạn đã được gắn cố định với cửa hàng này để đảm bảo quyền lợi bảo hành đơn hàng!</i>",
                    parse_mode="HTML"
                )
            await show_store_home(update, context, store)
            return
        else:
            await update.message.reply_text(
                f"❌ <b>KHÔNG TÌM THẤY CỬA HÀNG!</b>\n\n"
                f"Không có cửa hàng nào trên hệ thống sử dụng mã <b>#{text}</b>.\n"
                "Vui lòng kiểm tra lại mã 4 số do chủ cửa hàng cung cấp!",
                parse_mode="HTML"
            )
            return

    # 2. CÁC NÚT BÀN PHÍM ĐÁY MÀN HÌNH
    if "Quản Trị" in text or text.lower() in ["/admin", "/owner"]:
        if is_admin:
            from handlers.admin import show_admin_stores_list
            await show_admin_stores_list(update)
            return
        owner_store = await get_store_by_owner_telegram_id(user.id)
        if owner_store:
            await show_store_owner_home(update, context, owner_store)
            return

    if "Xem Shop" in text:
        owner_store = await get_store_by_owner_telegram_id(user.id)
        if owner_store:
            set_user_store(user.id, owner_store["store_slug"])
            await show_store_home(update, context, owner_store)
            return

    if "Tìm Cửa Hàng" in text:
        # Nếu khách đã bị khóa
        if not is_admin:
            lock = await get_customer_lock(user.id)
            if lock:
                curr_store = await get_store_by_slug(lock["store_slug"])
                await update.message.reply_text(
                    f"🔒 Bạn hiện đang là khách hàng thân thiết của <b>{lock['store_name']}</b> (Mã #{lock.get('store_code') or 'Shop'}).\n"
                    "Mọi đơn hàng của bạn đều được lưu giữ tại đây!",
                    parse_mode="HTML"
                )
                if curr_store:
                    await show_store_home(update, context, curr_store)
                return

        await update.message.reply_text(
            "🔍 <b>TÌM KIẾM CỬA HÀNG BẰNG MÃ 4 SỐ</b>\n\n"
            "Vui lòng <b>gõ mã 4 số</b> (Ví dụ: <code>8868</code>) vào khung chat và gửi đi để bot đưa bạn tới cửa hàng đó!",
            parse_mode="HTML"
        )
    elif "Bảng Giá" in text or "Sản Phẩm" in text:
        # Nếu khách đã bị gắn chết với 1 shop -> Mở danh mục sản phẩm của shop đó!
        if not is_admin:
            lock = await get_customer_lock(user.id)
            if lock:
                store = await get_store_by_slug(lock["store_slug"])
                if store:
                    await show_store_home(update, context, store)
                    return
        await show_service_intro(update)
    elif "Giỏ Hàng" in text:
        slug = get_user_store(user.id)
        if slug:
            await update.message.reply_text(
                "🛒 <b>Giỏ Hàng Của Bạn</b>\n\n"
                "Bấm nút bên dưới để xem giỏ hàng:",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🛒 Mở Giỏ Hàng", callback_data=f"cart_view_{slug}")]
                ])
            )
        else:
            await update.message.reply_text(
                "🛒 <b>Giỏ Hàng Của Bạn Trống</b>\n\nVui lòng vào cửa hàng để chọn sản phẩm trước!",
                parse_mode="HTML"
            )
    elif "Đơn Hàng" in text:
        owner_store = await get_store_by_owner_telegram_id(user.id)
        if owner_store and "Shop" in text:
            # Chủ shop muốn xem đơn của shop mình
            import sqlite3
            from db_helper import DB_FILE
            rows = []
            try:
                with sqlite3.connect(DB_FILE) as conn:
                    conn.row_factory = sqlite3.Row
                    rows = conn.cursor().execute(
                        "SELECT * FROM orders WHERE store_id = ? ORDER BY id DESC LIMIT 10", (owner_store["id"],)
                    ).fetchall()
            except Exception:
                pass
            if not rows:
                await update.message.reply_text(
                    f"📋 Cửa hàng <b>{owner_store['store_name']}</b> hiện chưa có đơn hàng nào.",
                    parse_mode="HTML"
                )
            else:
                msg = f"📋 <b>10 ĐƠN HÀNG GẦN NHẤT - {owner_store['store_name']}:</b>\n\n"
                for r in rows:
                    st_emoji = "✅" if r["status"] in ["paid", "completed"] else "⏳"
                    msg += f"{st_emoji} <b>{r['order_code']}</b>: {r['total_amount']:,}đ\n"
                    msg += f"   • Khách: {r['customer_name'] or 'Khách'} (ID: <code>{r['customer_tg_id']}</code>)\n"
                    msg += f"   • Trạng thái: <b>{r['status'].upper()}</b>\n\n"
                await update.message.reply_text(
                    msg,
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🌐 Quản Trị Đơn Hàng Trên Web", url=f"{DASHBOARD_URL}/dashboard/orders")]
                    ])
                )
            return

        await update.message.reply_text(
            "📋 <b>Tra Cứu Đơn Hàng</b>\n\n"
            f"Mọi đơn hàng của bạn được lưu trữ tự động. Nếu cần hỗ trợ đơn hàng, hãy liên hệ Admin hoặc bấm nút 'Hỗ Trợ' bên dưới!",
            parse_mode="HTML"
        )
    elif "Hỗ Trợ" in text:
        # Kiểm tra xem khách có đang trong 1 shop hoặc gắn kết với shop nào không
        curr_store = None
        slug = get_user_store(user.id)
        if slug:
            curr_store = await get_store_by_slug(slug)
        if not curr_store and not is_admin:
            lock = await get_customer_lock(user.id)
            if lock:
                curr_store = await get_store_by_slug(lock["store_slug"])

        if curr_store:
            context.user_data["awaiting_support_store_id"] = curr_store["id"]
            await update.message.reply_text(
                f"💬 <b>HỖ TRỢ KHÁCH HÀNG - {curr_store['store_name']}</b>\n\n"
                "Bạn đang cần Chủ cửa hàng tư vấn, giải đáp thắc mắc hoặc hỗ trợ đơn hàng?\n\n"
                "👉 <b>Hãy nhập nội dung câu hỏi/tin nhắn của bạn vào khung chat bên dưới và gửi đi:</b>\n"
                "Bot sẽ chuyển trực tiếp tin nhắn của bạn cho Chủ cửa hàng để phản hồi ngay!",
                parse_mode="HTML"
            )
            return

        await update.message.reply_text(
            "💬 <b>HỖ TRỢ KHÁCH HÀNG 24/7</b>\n\n"
            f"Mọi thắc mắc hoặc cần tư vấn, vui lòng liên hệ Admin:\n"
            f"👉 @{ADMIN_CONTACT}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📩 Nhắn Tin Cho Admin", url=f"https://t.me/{ADMIN_CONTACT}")]
            ])
        )

    else:
        # Kiểm tra khách có gắn với shop nào không
        if not is_admin:
            lock = await get_customer_lock(user.id)
            if lock:
                store = await get_store_by_slug(lock["store_slug"])
                if store:
                    await show_store_home(update, context, store)
                    return
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
    store_code_str = f"#{store.get('store_code')}" if store.get("store_code") else ""
    text = (
        f"🏪 <b>{store['store_name']}</b> {store_code_str}\n\n"
        f"{welcome}\n\n"
        "🛍️ <b>Hãy chọn danh mục bên dưới để bắt đầu mua hàng:</b>"
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
    keyboard.append([
        InlineKeyboardButton("🛒 Xem Giỏ hàng", callback_data=f"cart_view_{store['store_slug']}"),
        InlineKeyboardButton("💬 Hỗ Trợ Khách Hàng", callback_data=f"support_store_{store['id']}")
    ])

    user = update.effective_user
    owner_store = await get_store_by_owner_telegram_id(user.id)
    if owner_store and owner_store["id"] == store["id"]:
        keyboard.append([
            InlineKeyboardButton("👑 [CHỦ SHOP] Về Bảng Quản Trị", callback_data="owner_home")
        ])
    elif is_admin_user(user):
        keyboard.append([
            InlineKeyboardButton("👑 [ADMIN] Thoát Khỏi Shop Này", callback_data="show_plans"),
            InlineKeyboardButton("👑 Quản Trị Cửa Hàng", callback_data="admin_list_stores"),
        ])

    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.message:
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode="HTML", reply_markup=reply_markup)


async def show_store_home_edit(update: Update, context: ContextTypes.DEFAULT_TYPE, store: dict):
    await show_store_home(update, context, store)
