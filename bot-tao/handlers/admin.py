"""
Admin Handler: Bảng điều khiển quản trị tối cao dành cho Admin Võ Đức Mạnh (@manhkmhd2004).
Kiểm soát toàn quyền mọi cửa hàng, mã định danh 4 số, mở khóa khách hàng, và test 0đ.
"""
import os
import json
import random
import string
import urllib.request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from db_helper import (
    get_all_stores_for_admin,
    toggle_store_active_db,
    unlock_all_store_customers_db,
    regenerate_store_code_db,
    get_store_by_slug,
    get_store_by_code,
    is_admin_telegram_id,
    remove_customer_lock,
    get_store_by_owner_telegram_id,
)
from cart_store import set_user_store

DASHBOARD_URL = os.getenv("DASHBOARD_URL", "http://127.0.0.1:5174")
API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8088")
BOT_USERNAME = os.getenv("BOT_TAO_USERNAME", "Shoppretool_bot")
ADMIN_CONTACT = "manhkmhd2004"
ADMIN_TELEGRAM_IDS = [8337687095]
ADMIN_SECRET_PASS = "Vomanh321"


def is_admin_user(user) -> bool:
    if not user:
        return False
    if user.id in ADMIN_TELEGRAM_IDS:
        return True
    if user.username and user.username.lower() in [ADMIN_CONTACT.lower(), "manhkmhd2004", "manh071004"]:
        return True
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


async def admin_auth_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lệnh /admin_auth <secret>: Cấp quyền SuperAdmin ngay lập tức cho tài khoản Telegram này"""
    user = update.effective_user
    args = context.args
    if not args or args[0] != ADMIN_SECRET_PASS:
        await update.message.reply_text("❌ Sai mật khẩu quản trị! Vui lòng thử lại.")
        return

    if user.id not in ADMIN_TELEGRAM_IDS:
        ADMIN_TELEGRAM_IDS.append(user.id)

    # Cập nhật telegram_id vào database
    try:
        import sqlite3
        from db_helper import DB_FILE
        with sqlite3.connect(DB_FILE) as conn:
            cur = conn.cursor()
            cur.execute("UPDATE users SET telegram_id = ? WHERE email = 'manhkmhd2004@gmail.com'", (user.id,))
            conn.commit()
    except Exception:
        pass

    await update.message.reply_text(
        f"👑 <b>XÁC THỰC QUẢN TRỊ VIÊN THÀNH CÔNG!</b>\n\n"
        f"Xin chào Sếp <b>Võ Đức Mạnh</b>!\n"
        f"ID Telegram: <code>{user.id}</code> đã được cấp quyền SuperAdmin tối cao.\n"
        f"Bạn được miễn trừ khóa vĩnh viễn và có toàn quyền kiểm soát mọi shop.\n\n"
        "👉 Gõ /start hoặc /admin để mở bảng điều khiển quản trị!",
        parse_mode="HTML"
    )


async def admin_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lệnh /admin hoặc /admin_stores: Mở bảng điều khiển cho SuperAdmin hoặc Chủ shop"""
    user = update.effective_user
    if is_admin_user(user):
        await show_admin_stores_list(update)
        return

    # Kiểm tra nếu là Chủ cửa hàng
    owner_store = await get_store_by_owner_telegram_id(user.id)
    if owner_store:
        from handlers.start import show_store_owner_home
        await show_store_owner_home(update, context, owner_store)
        return

    await update.message.reply_text(
        f"⛔ <b>Bạn chưa liên kết tài khoản Quản trị viên cửa hàng.</b>\n\n"
        f"👉 Nếu bạn là chủ shop, vui lòng vào Web Quản Trị > mục <b>Link Bot</b> để bấm <b>Liên Kết 1 Chạm</b> với Telegram này!\n\n"
        f"💬 Hoặc liên hệ hỗ trợ: @{ADMIN_CONTACT}",
        parse_mode="HTML"
    )


async def show_admin_stores_list(update: Update):
    """Hiển thị danh sách tất cả các cửa hàng kèm các nút điều khiển trực tiếp"""
    stores = await get_all_stores_for_admin()
    total = len(stores)
    active_count = sum(1 for s in stores if s.get("is_active"))

    text = (
        f"👑 <b>BẢNG QUẢN TRỊ TOÀN BỘ CỬA HÀNG (SUPERADMIN)</b>\n\n"
        f"📊 <b>Thống kê:</b> Tổng <b>{total}</b> shop | 🟢 <b>{active_count}</b> đang chạy\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<i>Tài khoản Admin KHÔNG bị khóa vào bất kỳ shop nào. Bạn có thể tự do test hoặc đổi shop tùy thích.</i>\n\n"
        "👇 <b>Danh sách cửa hàng trên hệ thống:</b>\n\n"
    )

    keyboard = []
    for s in stores:
        is_act = "🟢" if s.get("is_active") else "🔴"
        code = s.get("store_code") or "N/A"
        prods = s.get("product_count", 0)
        locks = s.get("locked_customers_count", 0)

        text += (
            f"{is_act} <b>{s['store_name']}</b> (#{code})\n"
            f"   • Slug: <code>{s['store_slug']}</code>\n"
            f"   • Chủ: <i>{s.get('owner_email') or 'Chưa rõ'}</i>\n"
            f"   • SP: <b>{prods}</b> | 🔒 Khách gắn chết: <b>{locks}</b>\n\n"
        )

        keyboard.append([
            InlineKeyboardButton(
                f"{is_act} #{code} - {s['store_name'][:18]}",
                callback_data=f"admin_detail_{s['id']}"
            )
        ])

    keyboard.append([
        InlineKeyboardButton("🌐 Mở Web Quản Trị Chi Tiết", url=f"{DASHBOARD_URL}/dashboard/admin-stores"),
        InlineKeyboardButton("⬅️ Menu Admin", callback_data="show_plans")
    ])

    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.message:
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode="HTML", reply_markup=reply_markup)


async def show_admin_store_detail(update: Update, store_id: int):
    """Hiển thị chi tiết 1 shop và các nút điều khiển: Bật/Tắt, Mở khóa, Sinh mã mới, Vào test"""
    query = update.callback_query
    stores = await get_all_stores_for_admin()
    store = next((s for s in stores if s["id"] == store_id), None)

    if not store:
        await query.answer("Không tìm thấy cửa hàng!", show_alert=True)
        return

    is_act = "🟢 Đang hoạt động" if store.get("is_active") else "🔴 Đang tạm dừng"
    code = store.get("store_code") or "Chưa có"
    prods = store.get("product_count", 0)
    locks = store.get("locked_customers_count", 0)
    slug = store["store_slug"]

    bot_link = f"https://t.me/{BOT_USERNAME}?start=store_{slug}"
    code_link = f"https://t.me/{BOT_USERNAME}?start={code}"

    text = (
        f"🏪 <b>QUẢN LÝ SHOP: {store['store_name']}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"• <b>Mã định danh 4 số:</b> <code>#{code}</code>\n"
        f"• <b>Trạng thái:</b> {is_act}\n"
        f"• <b>Slug định danh:</b> <code>{slug}</code>\n"
        f"• <b>Chủ cửa hàng:</b> {store.get('owner_email') or 'N/A'}\n"
        f"• <b>Gói dịch vụ:</b> {store.get('owner_plan') or 'free'}\n"
        f"• <b>Sản phẩm đang bán:</b> <b>{prods}</b> SP\n"
        f"• <b>Khách hàng bị khóa chặt:</b> <b>{locks}</b> tài khoản\n\n"
        f"🔗 <b>Link Bot:</b> {bot_link}\n"
        f"🔢 <b>Link Mã 4 Số:</b> {code_link}\n\n"
        "👇 <b>Chọn hành động quản trị:</b>"
    )

    toggle_btn_text = "🔴 Tắt Cửa Hàng (Giải phóng khách)" if store.get("is_active") else "🟢 Bật Hoạt Động Cửa Hàng"

    keyboard = [
        [InlineKeyboardButton(toggle_btn_text, callback_data=f"admin_toggle_{store_id}")],
        [
            InlineKeyboardButton(f"🔓 Mở Khóa {locks} Khách", callback_data=f"admin_unlock_{store_id}"),
            InlineKeyboardButton("🎲 Cấp Lại Mã 4 Số", callback_data=f"admin_regen_{store_id}"),
        ],
        [InlineKeyboardButton("🛒 [ADMIN] Vào Test Mua Hàng Shop Này 0đ", callback_data=f"admin_enter_{slug}")],
        [InlineKeyboardButton("⬅️ Quay Lại Danh Sách Shop", callback_data="admin_list_stores")],
    ]

    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))


async def admin_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bắt và xử lý mọi callback query bắt đầu bằng admin_"""
    query = update.callback_query
    await query.answer()
    data = query.data
    user = update.effective_user

    if not is_admin_user(user):
        await query.answer("⛔ Bạn không có quyền Admin!", show_alert=True)
        return

    # 1. QUẢN LÝ TOÀN BỘ CỬA HÀNG
    if data == "admin_list_stores":
        await show_admin_stores_list(update)
        return

    # 2. XEM CHI TIẾT 1 SHOP
    if data.startswith("admin_detail_"):
        store_id = int(data[len("admin_detail_"):])
        await show_admin_store_detail(update, store_id)
        return

    # 3. BẬT / TẮT SHOP (NẾU TẮT -> GIẢI PHÓNG TOÀN BỘ KHÁCH HÀNG BỊ KHÓA)
    if data.startswith("admin_toggle_"):
        store_id = int(data[len("admin_toggle_"):])
        res = await toggle_store_active_db(store_id)
        if res:
            status_text = "🟢 Đang hoạt động" if res["is_active"] else "🔴 Đã tạm dừng"
            freed_msg = f"\nĐã tự động giải phóng {res['freed_locks']} khách hàng!" if res["freed_locks"] > 0 else ""
            await query.answer(f"Shop '{res['store_name']}' hiện {status_text}!{freed_msg}", show_alert=True)
        await show_admin_store_detail(update, store_id)
        return

    # 4. MỞ KHÓA TOÀN BỘ KHÁCH CỦA SHOP
    if data.startswith("admin_unlock_"):
        store_id = int(data[len("admin_unlock_"):])
        freed = await unlock_all_store_customers_db(store_id)
        await query.answer(f"Đã mở khóa thành công cho {freed} khách hàng!", show_alert=True)
        await show_admin_store_detail(update, store_id)
        return

    # 5. SINH LẠI MÃ 4 SỐ NGẪU NHIÊN
    if data.startswith("admin_regen_"):
        store_id = int(data[len("admin_regen_"):])
        new_code = await regenerate_store_code_db(store_id)
        if new_code:
            await query.answer(f"Đã đổi sang mã 4 số mới: #{new_code}", show_alert=True)
        await show_admin_store_detail(update, store_id)
        return

    # 6. ADMIN VÀO TEST MUA HÀNG TẠI SHOP NÀY (0đ, KHÔNG BỊ KHÓA)
    if data.startswith("admin_enter_"):
        slug = data[len("admin_enter_"):]
        store = await get_store_by_slug(slug)
        if store:
            set_user_store(user.id, slug)
            from handlers.start import show_store_home
            await query.message.reply_text(
                f"👑 <b>[ADMIN TEST MODE]</b>\n\n"
                f"Đã chuyển vào cửa hàng: <b>{store['store_name']}</b> (Mã #{store.get('store_code') or 'N/A'})\n"
                f"<i>Tài khoản Admin hoàn toàn tự do, không bị khóa, có thể mua test 0đ!</i>",
                parse_mode="HTML"
            )
            await show_store_home(update, context, store)
        else:
            await query.answer("Cửa hàng không tồn tại hoặc đã bị tắt!", show_alert=True)
        return

    # 7. ADMIN TEST GÓI 1 THÁNG HOẶC VĨNH VIỄN 0đ
    if data in ["admin_test_monthly", "admin_test_lifetime"]:
        is_lifetime = (data == "admin_test_lifetime")
        plan_code = "lifetime" if is_lifetime else "monthly"
        plan_name = "VĨNH VIỄN (LIFETIME)" if is_lifetime else "1 THÁNG (30 NGÀY)"

        code = generate_local_code(plan_code, user.id, user.username or "")

        caption = (
            f"👑 <b>[ADMIN TEST] CẤP MÃ LIÊN KẾT 0đ THÀNH CÔNG!</b>\n\n"
            f"Gói dịch vụ test: <b>{plan_name}</b>\n\n"
            f"🔑 <b>MÃ LIÊN KẾT CỦA BẠN:</b>\n"
            f"👉 <code>{code}</code> 👈 <i>(chạm để sao chép)</i>\n\n"
            "📌 <b>BƯỚC KÍCH HOẠT NHANH:</b>\n"
            f"1️⃣ Truy cập Web Quản Trị: <a href='{DASHBOARD_URL}/settings'>{DASHBOARD_URL}/settings</a>\n"
            f"2️⃣ Dán mã <code>{code}</code> vào ô <b>'Kích Hoạt Bằng Mã Liên Kết'</b>.\n"
            "3️⃣ Hệ thống sẽ tự động kích hoạt gói và tạo <b>Mã Định Danh 4 Số + Link Bot</b> cho bạn ngay!"
        )

        keyboard = [
            [InlineKeyboardButton("🌐 Vào Web Quản Trị Nhập Mã", url=f"{DASHBOARD_URL}/settings")],
            [InlineKeyboardButton("👑 Quản Trị Toàn Bộ Cửa Hàng", callback_data="admin_list_stores")],
            [InlineKeyboardButton("⬅️ Menu Admin", callback_data="show_plans")],
        ]

        await query.edit_message_text(caption, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # 8. ADMIN LẤY LINK BOT VÀ MÃ 4 SỐ CỦA SHOP ADMIN
    if data == "admin_quick_link":
        stores = await get_all_stores_for_admin()
        my_store = stores[0] if stores else None
        if not my_store:
            await query.answer("Chưa có cửa hàng nào trên hệ thống!", show_alert=True)
            return

        code = my_store.get("store_code") or "8868"
        slug = my_store.get("store_slug") or "admin-manh"
        bot_link = f"https://t.me/{BOT_USERNAME}?start=store_{slug}"
        code_link = f"https://t.me/{BOT_USERNAME}?start={code}"

        text = (
            f"👑 <b>THÔNG TIN KẾT NỐI BOT CỦA SẾP</b>\n\n"
            f"🏪 Cửa hàng: <b>{my_store['store_name']}</b>\n"
            f"🔢 <b>Mã Định Danh 4 Số:</b> <code>#{code}</code>\n\n"
            f"🔗 <b>Link Bot Trực Tiếp:</b>\n{bot_link}\n\n"
            f"🔢 <b>Link Theo Mã 4 Số:</b>\n{code_link}\n\n"
            "💡 <i>Gửi link hoặc mã 4 số này cho khách, khách vào bot sẽ tự động đưa tới shop này và bị khóa cố định!</i>"
        )
        keyboard = [
            [InlineKeyboardButton("🛒 Vào Test Shop Này", callback_data=f"admin_enter_{slug}")],
            [InlineKeyboardButton("👑 Quản Trị Toàn Bộ Cửa Hàng", callback_data="admin_list_stores")],
            [InlineKeyboardButton("⬅️ Menu Admin", callback_data="show_plans")],
        ]
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
        return
