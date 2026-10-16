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


def get_bottom_reply_keyboard(is_admin: bool = False):
    """Bàn phím menu dưới đáy chat tiện lợi cho khách hoặc Admin"""
    if is_admin:
        return ReplyKeyboardMarkup(
            [
                ["🛍️ Bảng Giá Sản Phẩm", "🔍 Tìm Cửa Hàng (Mã 4 Số)"],
                ["👑 Quản Trị Cửa Hàng", "🛒 Giỏ Hàng"],
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


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args  # ["store_SLUG"] hoặc ["code_1234"] hoặc ["1234"] hoặc []
    is_admin = is_admin_user(user)

    # 1. KIỂM TRA KHÁCH HÀNG ĐÃ BỊ GẮN CHẾT VỚI CỬA HÀNG NÀO CHƯA (STICKY CUSTOMER LOCK)
    # (Trừ Admin tối cao để admin test tự do)
    if not is_admin:
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

    # 2. KHÁCH MỚI / ADMIN VÀO QUA DEEP LINK HOẶC MÃ ĐỊNH DANH 4 SỐ
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
    if "Quản Trị" in text or text.lower() == "/admin":
        if is_admin:
            from handlers.admin import show_admin_stores_list
            await show_admin_stores_list(update)
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
        await update.message.reply_text(
            "📋 <b>Tra Cứu Đơn Hàng</b>\n\n"
            f"Mọi đơn hàng của bạn được lưu trữ tự động. Nếu cần hỗ trợ đơn hàng, hãy liên hệ Admin: @{ADMIN_CONTACT}",
            parse_mode="HTML"
        )
    elif "Hỗ Trợ" in text:
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
    keyboard.append([InlineKeyboardButton("🛒 Xem Giỏ hàng", callback_data=f"cart_view_{store['store_slug']}")])

    user = update.effective_user
    if is_admin_user(user):
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
