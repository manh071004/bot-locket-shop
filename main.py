import os
import sys
import io
import time
import asyncio
from datetime import datetime
from telethon import TelegramClient, events, Button
from telethon.tl.types import ReplyKeyboardMarkup, KeyboardButtonRow, KeyboardButton, ReplyKeyboardHide
from telethon.errors import MessageNotModifiedError, UserIsBlockedError

# Nạp cấu hình và cơ sở dữ liệu
from config import (
    API_ID,
    API_HASH,
    BOT_TOKEN,
    ADMIN_IDS,
    TIMEOUT_INPUT_SECONDS,
    TIMEOUT_PAYMENT_SECONDS,
    BACKUP_INTERVAL_HOURS,
    GROUP_ID,
    GROUP_INVITE_LINK,
    GROUP_USERNAME,
    logger
)
import database
from database import db, load_products, get_product_by_id
import payos_service

# Kiểm tra cấu hình Telegram bắt buộc
if not API_ID or not API_HASH or not BOT_TOKEN:
    logger.error("THIẾU THÔNG TIN TELEGRAM: API_ID, API_HASH hoặc BOT_TOKEN chưa được cài đặt trong .env!")
    sys.exit(1)

# Khởi tạo client Telethon
client = TelegramClient("shop_bot_session", API_ID, API_HASH)

# Link dịch vụ miễn phí
LOCKET_APP_LINK = "https://t.me/nghientrickshop_bot?startapp"
CANVA_INVITE_LINK = "https://www.canva.com/brand/join?token=FZjc3M_8p-wm7leu_d4VOA&brandingVariant=edu&referrer=team-invite"

# Bộ nhớ tạm lưu trữ trạng thái người dùng (Session State Machine)
# user_states[user_id] = {"step": ..., "product_id": ..., "expires_at": ...}
user_states = {}
active_payment_tasks = {} # order_id -> asyncio.Task

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

def format_money(amount: int) -> str:
    if amount == 0:
        return "MIỄN PHÍ (0đ)"
    return f"{amount:,.0f} VNĐ".replace(",", ".")

# ==================== GIAO DIỆN CHÍNH & HELPER ====================

# Biến tạm lưu danh sách user đang test như khách thường (kể cả admin)
test_regular_users = set()

async def check_user_in_group(user_id: int) -> bool:
    """Kiểm tra xem người dùng đã thực sự tham gia kênh/nhóm cộng đồng chưa"""
    # Nếu đang bật chế độ testadmin thì không miễn trừ admin, kiểm tra như khách mới
    if is_admin(user_id) and user_id not in test_regular_users:
        return True
    
    # 1. Kiểm tra nếu đã xác minh vào nhóm trong vòng 7 ngày qua
    if db.is_group_verified(user_id):
        return True

    # Nếu đang ở chế độ test (test_regular_users): KHÔNG tự động quét ngầm để bắt buộc phải hiển thị bảng xác minh & ấn nút
    if user_id in test_regular_users:
        return False

    # 2. Quét quyền trực tiếp từ Telegram qua ID hoặc Username kênh (@tooltrickfree)
    target = GROUP_ID if GROUP_ID else (GROUP_USERNAME if GROUP_USERNAME else None)
    if target:
        try:
            participant = await client.get_permissions(target, user_id)
            if participant and (participant.is_admin or participant.participant):
                db.set_group_verified(user_id)
                return True
            return False
        except Exception as e:
            logger.warning(f"Quét thành viên kênh/nhóm Telegram ({target}) lỗi: {e}")
            return False

    return False

def get_join_group_prompt(user_id: int):
    """Thông báo bắt buộc tham gia kênh cộng đồng kèm nút xác minh"""
    text = (
        "📢 **THÔNG BÁO TỪ HỆ THỐNG SHOP BẢN QUYỀN**\n\n"
        "Chào bạn! Để tiếp tục sử dụng bot và nhận các chương trình ưu đãi, giảm giá sốc, "
        "bạn vui lòng **tham gia Kênh cộng đồng chính thức** của chúng tôi nhé!\n\n"
        "👉 **Bước 1:** Bấm nút **'👉 Tham Gia Kênh Cộng Đồng'** bên dưới.\n"
        "👉 **Bước 2:** Bấm nút **'✅ Tôi Đã Vào Kênh'** để bot quét và mở khóa toàn bộ tính năng.\n\n"
        "_(Mỗi tuần hệ thống sẽ kiểm tra định kỳ 1 lần để đảm bảo bạn không bỏ lỡ các ưu đãi quà tặng mới nhất)_"
    )
    buttons = [
        [Button.url("👉 Tham Gia Kênh Cộng Đồng", GROUP_INVITE_LINK)],
        [Button.inline("✅ Tôi Đã Vào Kênh (Xác Minh)", b"verify_joined_group")]
    ]
    return text, buttons

# ==================== GIAO DIỆN CHÍNH & HELPER ====================

def get_main_menu_buttons(user_id: int):
    buttons = [
        # Nút chuyển tới luồng nhận Locket Gold Free (Yêu cầu mời bạn bè)
        [Button.inline("🎁 Nhận Locket Gold Free (0đ)", b"start_locket_free_flow")],
        # Nút chuyển tới luồng nhận Canva Pro Edu Free (Yêu cầu mời bạn bè)
        [Button.inline("🎨 Nhận Canva Pro Edu Free (0đ)", b"start_canva_free_flow")],
        [
            Button.inline("🛍️ Bảng Giá Sản Phẩm", b"menu_products"),
            Button.inline("📋 Đơn Hàng Của Tôi", b"my_orders")
        ],
        [
            Button.inline("💬 Hỗ Trợ Khách Hàng", b"contact_support"),
            Button.inline("📜 Hướng Dẫn Mua", b"guide")
        ]
    ]
    # CHỈ DUY NHẤT ADMIN THẬT (ID TRONG CONFIG) VÀ KHÔNG Ở CHẾ ĐỘ TEST MỚI NHÌN THẤY NÚT NÀY
    if is_admin(user_id) and user_id not in test_regular_users:
        buttons.append([Button.inline("👑 Quản Trị Viên (Admin Panel)", b"admin_panel")])
    return buttons

def get_products_menu_buttons():
    products = load_products()
    rows = []
    # Nút bấm riêng cho từng sản phẩm
    for p in products:
        price_text = "0đ" if p["price"] == 0 else f"{p['price'] // 1000}k"
        btn_text = f"{p['name']} • {price_text}"
        rows.append([Button.inline(btn_text, f"view_prod_{p['id']}".encode())])
    rows.append([Button.inline("⬅️ Quay Lại Menu Chính", b"menu_main")])
    return rows

def get_reply_keyboard(user_id: int):
    """Bàn phím dưới đáy 2 hàng gọn gàng, thanh lịch"""
    return [
        [
            Button.text("🎁 Locket Free", resize=True),
            Button.text("🎨 Canva Free", resize=True)
        ],
        [
            Button.text("🛍️ Bảng Giá", resize=True),
            Button.text("📋 Đơn Hàng", resize=True)
        ]
    ]

# ==================== CÁC SỰ KIỆN LỆNH TELEGRAM & NÚT BÀN PHÍM DƯỚI ====================

@client.on(events.NewMessage(pattern=r"(?i)^/start"))
async def start_handler(event):
    try:
        sender = await event.get_sender()
        user_id = sender.id if sender else event.sender_id
        username = (sender.username if sender else "") or ""
        first_name = (sender.first_name if sender else "Khách hàng") or "Khách hàng"

        # Lưu thông tin khách hàng
        curr_user = db.get_or_create_user(user_id, username, first_name)
        user_states.pop(user_id, None)

        # XỬ LÝ PHƯƠNG THỨC 1: BẠN BÈ VÀO BOT QUA LINK GIỚI THIỆU (/start <ref_code>)
        raw_msg = (event.raw_text or "").strip()
        parts = raw_msg.split()
        if len(parts) > 1:
            ref_param = parts[1].strip()
            referrer = db.find_user_by_ref_code(ref_param)
            if referrer and referrer["id"] != user_id:
                # Nếu tài khoản này chưa liên kết với ai, lưu người giới thiệu đang chờ xác minh
                if not db.is_user_already_linked(user_id) and not db.is_user_already_linked(referrer["id"]):
                    curr_user["pending_referrer_id"] = referrer["id"]
                    db.save()

        # 1. KIỂM TRA ĐIỀU KIỆN VÀO NHÓM/KÊNH CỘNG ĐỒNG (HẠN 7 NGÀY)
        is_exempt = is_admin(user_id) and (user_id not in test_regular_users)
        if not is_exempt and not db.is_group_verified(user_id):
            is_member = await check_user_in_group(user_id)
            if not is_member:
                prompt_text, buttons = get_join_group_prompt(user_id)
                await event.respond(prompt_text, buttons=buttons)
                return

        # Nếu đã ở trong kênh rồi và có pending_referrer_id, kích hoạt liên kết ngay
        pending_ref = curr_user.get("pending_referrer_id")
        if pending_ref and not db.is_user_already_linked(user_id):
            linked = db.link_referral_mutual(user_id, pending_ref)
            if linked:
                curr_user["pending_referrer_id"] = None
                db.save()
                try:
                    ref_text_notify = (
                        f"🎉 **BẠN BÈ ĐÃ KẾT NỐI THÀNH CÔNG!**\n\n"
                        f"✅ Người bạn của bạn (@{username or first_name}) đã tham gia Kênh và hoàn thành điều kiện.\n"
                        f"✨ Cả hai tài khoản đã được liên kết thành công! Bây giờ bạn đã mở khóa nhận CẢ HAI món quà:\n"
                        f"• 🎁 **Locket Gold Free 0đ**\n"
                        f"• 🎨 **Canva Pro Edu Free 0đ (Gia đình)**\n\n"
                        f"👇 Bấm các nút bên dưới để nhận ngay quà của bạn:"
                    )
                    ref_buttons = [
                        [Button.url("🚀 MỞ APP NHẬN LOCKET GOLD FREE", LOCKET_APP_LINK)],
                        [Button.url("🎨 THAM GIA GIA ĐÌNH CANVA PRO EDU", CANVA_INVITE_LINK)],
                        [Button.inline("⬅️ Về Menu Chính", b"menu_main")]
                    ]
                    await client.send_message(pending_ref, ref_text_notify, buttons=ref_buttons)
                except Exception:
                    pass

        welcome_text = (
            f"👋 **Chào mừng {first_name} đến với Shop Dịch Vụ Bản Quyền!**\n\n"
            f"🌟 **ƯU ĐÃI ĐẶC BIỆT HÔM NAY:**\n"
            f"🎁 Nhận ngay gói **Locket Gold Free 0đ** trải nghiệm đầy đủ tính năng!\n\n"
            f"💎 **DANH MỤC DỊCH VỤ NỔI BẬT:**\n"
            f"• 💛 **Locket Gold 2 Năm:** 80.000đ\n"
            f"• 🎨 **Canva Pro Edu 12 Tháng:** 40.000đ\n"
            f"• 👑 **Admin Canva Pro Edu 2 Năm:** 120.000đ\n"
            f"• 🤖 **Gemini Pro 18 Tháng:** 200.000đ\n\n"
            f"⚡ **Tất cả dịch vụ đều có bảo hành 1 đổi 1 & hỗ trợ 24/7!**\n"
            f"👇 _Chọn chức năng bên dưới để bắt đầu:_"
        )

        # Gộp thành DUY NHẤT 1 tin nhắn gửi tới khách hàng (kèm cả menu inline và bàn phím đáy)
        await event.respond(
            welcome_text,
            buttons=get_main_menu_buttons(user_id)
        )
    except Exception as e:
        logger.error(f"Lỗi khi xử lý lệnh /start: {e}", exc_info=True)
        try:
            await event.respond(f"⚠️ **Đang tải lại hệ thống ({e})**\nVui lòng thử lại sau giây lát!")
        except Exception:
            pass

@client.on(events.NewMessage(pattern=r"^(/products|🛍️ Bảng Giá Sản Phẩm|🛍️ Bảng Giá)$"))
async def products_command_handler(event):
    user_id = event.sender_id
    if not is_admin(user_id) and not db.is_group_verified(user_id):
        is_member = await check_user_in_group(user_id)
        if not is_member:
            prompt_text, buttons = get_join_group_prompt(user_id)
            await event.respond(prompt_text, buttons=buttons)
            return

    text = (
        "🛍️ **BẢNG GIÁ DỊCH VỤ BẢN QUYỀN CHÍNH HÃNG**\n\n"
        "1. 🎁 **Locket Gold Miễn Phí:** `0 VNĐ`\n"
        "2. 🎨 **Canva Pro Edu Miễn Phí:** `0 VNĐ`\n"
        "3. 💛 **Locket Gold 2 Năm:** `80.000 VNĐ`\n"
        "4. 🎨 **Canva Pro Edu 12 Tháng:** `40.000 VNĐ`\n"
        "5. 👑 **Admin Canva Pro Edu 2 Năm:** `120.000 VNĐ`\n"
        "6. 🤖 **Gemini Pro 18 Tháng:** `200.000 VNĐ`\n\n"
        "👇 Bấm vào từng sản phẩm dưới đây để xem chi tiết & đặt mua:"
    )
    await event.respond(text, buttons=get_products_menu_buttons())

async def send_locket_free_referral_flow(event, user_id: int):
    """Xử lý hiển thị luồng nhận Locket Gold Free theo điều kiện giới thiệu bạn bè (Hỗ trợ 2 phương thức: Link & Mã 8 ký tự)"""
    user_data = db.get_or_create_user(user_id)
    friend_id = user_data.get("referred_friend_id")

    # ADMIN (khi không ở chế độ test) hoặc người đã xác minh giới thiệu bạn bè: hiển thị trực tiếp nút mở app
    is_exempt = is_admin(user_id) and (user_id not in test_regular_users)
    if is_exempt or friend_id:
        text_success = (
            "🎉 **CHÚC MỪNG BẠN ĐÃ ĐỦ ĐIỀU KIỆN!**\n\n"
            "✅ Bạn đã hoàn thành nhiệm vụ giới thiệu bạn bè và tham gia kênh cộng đồng.\n"
            "👇 Bấm nút bên dưới để mở ứng dụng nhận Locket Gold Free ngay lập tức:"
        )
        buttons = [
            [Button.url("🚀 MỞ APP NHẬN LOCKET GOLD FREE", "https://t.me/nghientrickshop_bot?startapp")],
            [Button.inline("⬅️ Về Menu Chính", b"menu_main")]
        ]
        await event.respond(text_success, buttons=buttons)
        return

    # Lấy mã ref_code 8 ký tự ngẫu nhiên của khách
    ref_code = db.get_user_ref_code(user_id)
    bot_info = await client.get_me()
    bot_user = bot_info.username or "locketfreeshop_bot"
    ref_link = f"https://t.me/{bot_user}?start={ref_code}"
    cmd_code = f"/{ref_code}"

    ref_text = (
        "🎁 **ĐIỀU KIỆN NHẬN LOCKET GOLD FREE (0Đ)**\n\n"
        "Để nhận link mở ứng dụng Locket Gold Free, bạn chỉ cần **kết nối với 1 người bạn** (hoặc 1 nick phụ/clone của bạn) qua **1 trong 2 cách sau**:\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🔗 **CÁCH 1: GỬI LINK GIỚI THIỆU TRỰC TIẾP**\n"
        f"• Link của bạn: `{ref_link}`\n"
        "👉 Gửi link này cho bạn bè bấm vào. Khi bạn bè bấm **/start** và **tham gia Kênh cộng đồng**, hệ thống sẽ tự động liên kết 2 tài khoản ngay lập tức!\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🔑 **CÁCH 2: SAO CHÉP MÃ LỆNH 8 KÝ TỰ**\n"
        f"• Mã kết nối của bạn: `{cmd_code}`\n"
        "👉 Bạn của bạn chỉ cần vào bot, vượt qua bước tham gia Kênh, sau đó **nhắn tin đúng mã trên** vào bot là 2 tài khoản tự động liên kết thành công!\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "💡 **Mẹo:** Bạn có thể tự tạo 1 tài khoản Telegram clone rồi tự gửi link/mã để hoàn thành ngay trong 1 phút!\n"
        "⚠️ _Lưu ý: Hai tài khoản sau khi liên kết với nhau sẽ được tính hoàn thành và không thể liên kết thêm với ai khác nữa._"
    )

    buttons = [
        [Button.inline("🔗 Sao Chép Link Giới Thiệu", f"copy_link_{ref_code}".encode())],
        [Button.inline(f"📋 Sao Chép Mã ({cmd_code})", f"copy_code_{ref_code}".encode())],
        [Button.inline("⬅️ Quay Lại Menu Chính", b"menu_main")]
    ]
    await event.respond(ref_text, buttons=buttons)

@client.on(events.NewMessage(pattern=r"^(/free|🎁 Nhận Locket Free 0đ|🎁 Locket Free)$"))
async def free_command_handler(event):
    user_id = event.sender_id
    if not is_admin(user_id) and not db.is_group_verified(user_id):
        is_member = await check_user_in_group(user_id)
        if not is_member:
            prompt_text, buttons = get_join_group_prompt(user_id)
            await event.respond(prompt_text, buttons=buttons)
            return

    await send_locket_free_referral_flow(event, user_id)

async def send_canva_free_referral_flow(event, user_id: int):
    """Gửi trực tiếp liên kết mời tham gia nhóm gia đình Canva Pro Edu Free 0đ (Không cần giới thiệu bạn bè)"""
    text = (
        "🎉 **QUÀ TẶNG CANVA PRO EDU FREE (0Đ) TỪ SHOP!**\n\n"
        "✨ Dưới đây là liên kết mời tham gia nhóm gia đình **Canva Pro Edu Miễn Phí (0đ)** của shop:\n\n"
        f"🔗 **Link mời tham gia:**\n`{CANVA_INVITE_LINK}`\n\n"
        "👉 **Hướng dẫn:** Bạn chỉ cần bấm vào link trên (hoặc bấm nút bên dưới), đăng nhập tài khoản Canva của bạn là sẽ được tự động tham gia nhóm Canva Pro Edu với đầy đủ tính năng Premium!\n\n"
        "👇 Bấm nút bên dưới để tham gia nhóm ngay lập tức:"
    )
    buttons = [
        [Button.url("🎨 THAM GIA GIA ĐÌNH CANVA PRO EDU", CANVA_INVITE_LINK)],
        [Button.inline("⬅️ Về Menu Chính", b"menu_main")]
    ]
    await event.respond(text, buttons=buttons)

@client.on(events.NewMessage(pattern=r"(?i)^(/canva|/canva_free|🎨 Nhận Canva Free 0đ|🎨 Canva Free|Canva Free)$"))
async def canva_free_command_handler(event):
    user_id = event.sender_id
    if not is_admin(user_id) and not db.is_group_verified(user_id):
        is_member = await check_user_in_group(user_id)
        if not is_member:
            prompt_text, buttons = get_join_group_prompt(user_id)
            await event.respond(prompt_text, buttons=buttons)
            return

    await send_canva_free_referral_flow(event, user_id)

@client.on(events.NewMessage(pattern=r"^(/orders|📋 Đơn Hàng Của Tôi)$"))
async def orders_command_handler(event):
    user_id = event.sender_id
    orders = db.get_user_orders(user_id, limit=5)
    if not orders:
        msg = "📋 **Bạn chưa có đơn hàng nào trong lịch sử!**\nHãy chọn một sản phẩm để trải nghiệm nhé."
    else:
        msg = "📋 **DANH SÁCH ĐƠN HÀNG GẦN ĐÂY CỦA BẠN:**\n\n"
        for o in orders:
            st = o.get("status")
            st_icon = "✅ Đã Hoàn Tất" if st in ["COMPLETED"] else ("💳 Đã Thanh Toán - Chờ Bàn Giao" if st == "PAID" else ("⏳ Chờ Thanh Toán" if st == "PENDING" else "❌ Đã Hủy"))
            msg += (
                f"📦 **Đơn hàng:** `#{o['order_id']}`\n"
                f"• Dịch vụ: **{o['product_name']}**\n"
                f"• Giá: `{format_money(o['amount'])}`\n"
                f"• Trạng thái: {st_icon}\n"
                f"• Ngày đặt: {o['created_at']}\n"
                f"────────────────────\n"
            )
    buttons = [
        [Button.inline("🛍️ Xem Bảng Giá Mua Thêm", b"menu_products")],
        [Button.inline("⬅️ Quay Lại", b"menu_main")]
    ]
    await event.respond(msg, buttons=buttons)

async def start_customer_support_flow(event, user_id: int, is_callback: bool = False):
    """Mở giao diện để khách nhắn tin gửi câu hỏi trực tiếp cho Admin qua bot"""
    user_states[user_id] = {
        "step": "waiting_customer_support",
        "expires_at": time.time() + 600
    }
    text = (
        "💬 **TRUNG TÂM HỖ TRỢ KHÁCH HÀNG 24/7**\n\n"
        "Bạn đang cần tư vấn gói dịch vụ, hỗ trợ thanh toán hoặc bảo hành tài khoản?\n\n"
        "👉 **Vui lòng nhập câu hỏi hoặc vấn đề của bạn gửi trực tiếp vào đây:**\n"
        "_(Hệ thống sẽ chuyển tiếp tin nhắn của bạn ngay tới Admin để phản hồi sớm nhất!)_"
    )
    buttons = [
        [Button.inline("❌ Hủy Thao Tác", b"cancel_support")],
        [Button.inline("⬅️ Về Menu Chính", b"menu_main")]
    ]
    if is_callback:
        try:
            await event.edit(text, buttons=buttons)
        except Exception:
            await event.respond(text, buttons=buttons)
        await event.answer()
    else:
        await event.respond(text, buttons=buttons)

@client.on(events.NewMessage(pattern=r"(?i)^(/support(@\w+)?|💬 Hỗ Trợ 24/7|/help(@\w+)?)$"))
async def support_command_handler(event):
    await start_customer_support_flow(event, event.sender_id, is_callback=False)

@client.on(events.NewMessage(pattern=r"(?i)^/admin(@\w+)?$|^👑 Bảng Điều Khiển Admin$"))
async def admin_command_handler(event):
    user_id = event.sender_id
    if not is_admin(user_id):
        await event.respond(f"⛔ Bạn không có quyền truy cập bảng quản trị! (ID: `{user_id}` chưa được thêm vào ADMIN_ID)")
        return
    await show_admin_panel(event, is_callback=False)

@client.on(events.NewMessage(pattern=r"(?i)^/backup(@\w+)?$"))
async def backup_command_handler(event):
    user_id = event.sender_id
    if not is_admin(user_id):
        await event.respond(f"⛔ Bạn không có quyền gọi lệnh backup! (ID: `{user_id}`)")
        return
    await perform_backup_to_chat(event.chat_id)

# ==================== LỆNH BÍ MẬT TEST DÀNH CHO TẤT CẢ TÀI KHOẢN (/testadmin, /test) ====================
# Bất kỳ tài khoản nào cũng có thể gọi lệnh này để xóa trắng dữ liệu và test quy trình từ đầu
@client.on(events.NewMessage(pattern=r"(?i)^/(testadmin|test|testkhach)(@\w+)?$"))
async def test_admin_handler(event):
    user_id = event.sender_id

    # 1. Xóa hoàn toàn toàn bộ dữ liệu tài khoản này trong cơ sở dữ liệu
    db.reset_user_completely(user_id)
    user_states.pop(user_id, None)

    # 2. Đưa tài khoản vào danh sách test như khách mới (bỏ qua mọi đặc quyền admin nếu có)
    test_regular_users.add(user_id)

    # Đảm bảo reset trạng thái xác minh kênh về 0
    curr_user = db.get_or_create_user(user_id)
    curr_user["group_verified_at"] = 0
    db.save()

    # 3. Gửi lại thông báo bắt buộc xác minh tham gia Kênh cộng đồng
    prompt_text, buttons = get_join_group_prompt(user_id)
    intro = (
        "🧪 **[CHẾ ĐỘ TEST KHÁCH MỚI ĐÃ BẬT]**\n\n"
        f"• Đã xóa sạch dữ liệu tài khoản (`{user_id}`) trong database.\n"
        f"• Bạn đang trải nghiệm giao diện như một khách hàng mới lần đầu vào bot.\n"
        f"• Gõ `/untest` bất kỳ lúc nào để thoát chế độ test.\n\n"
        "────────────────────\n\n"
    )
    await event.respond(intro + prompt_text, buttons=buttons)

@client.on(events.NewMessage(pattern=r"(?i)^/(untest|endtest)(@\w+)?$"))
async def untest_handler(event):
    user_id = event.sender_id
    test_regular_users.discard(user_id)
    if is_admin(user_id):
        await event.respond("👑 **Đã thoát chế độ test!** Tài khoản của bạn đã được khôi phục đầy đủ đặc quyền Quản trị viên.")
    else:
        await event.respond("✅ **Đã thoát chế độ test!** Tài khoản của bạn đã trở về trạng thái bình thường.")

async def start_admin_deliver_flow(event, order_id: str, admin_id: int, is_callback: bool = False):
    """Quy trình bàn giao đơn hàng chuyên biệt cho từng dịch vụ:
       - Canva: Hoàn tất ngay lập tức & báo khách kiểm tra email/app.
       - Locket (có phí): Yêu cầu Admin gửi file DNS (.mobileconfig / .dns) + kèm toàn bộ hướng dẫn cài đặt 4 bước cho khách.
       - Gemini: Yêu cầu Admin gửi link ưu đãi 18 tháng + kèm bài hướng dẫn kích hoạt 5 bước chuẩn của shop.
    """
    order = db.get_order(order_id)
    if not order:
        if is_callback:
            await event.answer("⚠️ Đơn hàng không tồn tại!", alert=True)
        else:
            await event.respond(f"⚠️ Đơn hàng {order_id} không tồn tại!")
        return

    prod_id = order.get("product_id", "")
    prod_name_lower = order.get("product_name", "").lower()

    # 1. CANVA: GIAO THÀNH CÔNG NGAY LẬP TỨC
    if "canva" in prod_id or "canva" in prod_name_lower:
        db.update_order_status(order_id, "COMPLETED")
        msg_admin = (
            f"✅ **ĐƠN HÀNG CANVA #{order_id} ĐÃ BÀN GIAO THÀNH CÔNG!**\n\n"
            f"• **Khách hàng:** @{order.get('username') or order.get('user_id')} (`{order['user_id']}`)\n"
            f"• **Dịch vụ:** {order.get('product_name')}\n"
            f"• **Email Canva:** `{order.get('customer_info')}`\n"
            f"• **Thời gian bàn giao:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        if is_callback:
            try:
                await event.edit(msg_admin)
            except Exception:
                await event.respond(msg_admin)
            await event.answer("✅ Đã bàn giao Canva thành công!", alert=True)
        else:
            await event.respond(msg_admin)

        try:
            cust_text = (
                f"🎉 **DỊCH VỤ CANVA CỦA BẠN ĐÃ ĐƯỢC KÍCH HOẠT THÀNH CÔNG!**\n\n"
                f"• **Mã đơn hàng:** `#{order_id}`\n"
                f"• **Dịch vụ:** **{order.get('product_name')}**\n"
                f"• **Email nhận:** `{order.get('customer_info')}`\n\n"
                f"✅ Admin đã hoàn tất thêm tài khoản Email của bạn vào nhóm Canva Pro Edu bản quyền!\n"
                f"👉 Bạn vui lòng kiểm tra hộp thư Email (hoặc mở trực tiếp ứng dụng / web Canva) để vào nhóm và trải nghiệm trọn bộ tính năng Pro nhé!\n\n"
                f"🛡️ **Bảo hành:** Gói dịch vụ được bảo hành chính hãng 1 đổi 1 suốt thời gian sử dụng. Cảm ơn bạn đã tin tưởng ủng hộ shop! ❤️"
            )
            await client.send_message(order["user_id"], cust_text)
        except Exception as e:
            logger.error(f"Lỗi gửi tin nhắn bàn giao Canva cho khách {order['user_id']}: {e}")
        return

    # 2. LOCKET GOLD 2 NĂM: CHUYỂN SANG BƯỚC CHỜ ADMIN GỬI FILE CẤU HÌNH DNS
    if "locket" in prod_id or "locket" in prod_name_lower:
        user_states[admin_id] = {
            "step": "admin_waiting_locket_dns",
            "order_id": order_id
        }
        prompt_text = (
            f"📦 **BÀN GIAO ĐƠN HÀNG LOCKET #{order_id}:**\n\n"
            f"• **Khách:** @{order.get('username') or order.get('user_id')} (`{order['user_id']}`)\n"
            f"• **Tài khoản Locket (Username/Link):** `{order.get('customer_info')}`\n"
            f"• **Dịch vụ:** {order.get('product_name')}\n\n"
            f"👉 **Admin vui lòng gửi FILE CẤU HÌNH DNS (.mobileconfig / .dns / file bất kỳ) vào đây:**\n"
            f"_(Bot sẽ tự động gửi kèm File DNS này cùng toàn bộ Hướng Dẫn Cài Đặt DNS Locket chuẩn cho khách)_\n\n"
            f"*(Hoặc nếu muốn hoàn tất không gửi file, gõ: `/skip_{order_id}`)*"
        )
        buttons = [[Button.inline("❌ Hủy Thao Tác", b"admin_cancel_deliver")]]
        if is_callback:
            try:
                await event.edit(prompt_text, buttons=buttons)
            except Exception:
                await event.respond(prompt_text, buttons=buttons)
            await event.answer()
        else:
            await event.respond(prompt_text, buttons=buttons)
        return

    # 3. GEMINI PRO 18 THÁNG: CHUYỂN SANG BƯỚC CHỜ ADMIN GỬI LINK ƯU ĐÃI
    if "gemini" in prod_id or "gemini" in prod_name_lower:
        user_states[admin_id] = {
            "step": "admin_waiting_gemini_link",
            "order_id": order_id
        }
        prompt_text = (
            f"📦 **BÀN GIAO ĐƠN HÀNG GEMINI PRO 18 THÁNG #{order_id}:**\n\n"
            f"• **Khách:** @{order.get('username') or order.get('user_id')} (`{order['user_id']}`)\n"
            f"• **Email Google:** `{order.get('customer_info')}`\n"
            f"• **Dịch vụ:** {order.get('product_name')}\n\n"
            f"👉 **Admin vui lòng GỬI LINK ƯU ĐÃI GEMINI 18 THÁNG vào đây:**\n"
            f"_(Bot sẽ tự động lồng Link này vào bài Hướng Dẫn Kích Hoạt chuẩn và gửi cho khách)_"
        )
        buttons = [[Button.inline("❌ Hủy Thao Tác", b"admin_cancel_deliver")]]
        if is_callback:
            try:
                await event.edit(prompt_text, buttons=buttons)
            except Exception:
                await event.respond(prompt_text, buttons=buttons)
            await event.answer()
        else:
            await event.respond(prompt_text, buttons=buttons)
        return

    # MẶC ĐỊNH CHO CÁC SẢN PHẨM KHÁC
    db.update_order_status(order_id, "COMPLETED")
    msg_admin = f"✅ Đã xác nhận bàn giao đơn hàng #{order_id} thành công!"
    if is_callback:
        try:
            await event.edit(msg_admin)
        except Exception:
            await event.respond(msg_admin)
        await event.answer("✅ Đã bàn giao thành công!", alert=True)
    else:
        await event.respond(msg_admin)

    try:
        cust_text = (
            f"🎉 **DỊCH VỤ CỦA BẠN ĐÃ ĐƯỢC KÍCH HOẠT THÀNH CÔNG!**\n\n"
            f"• **Mã đơn hàng:** `#{order_id}`\n"
            f"• **Dịch vụ:** **{order.get('product_name')}**\n"
            f"• **Thông tin:** `{order.get('customer_info')}`\n\n"
            f"✨ Chúc bạn có trải nghiệm tuyệt vời cùng dịch vụ của chúng tôi! ❤️"
        )
        await client.send_message(order["user_id"], cust_text)
    except Exception:
        pass

# ==================== XỬ LÝ CALLBACK QUERIES (NÚT BẤM) ====================

@client.on(events.CallbackQuery)
async def callback_handler(event):
    user_id = event.sender_id
    data = event.data.decode("utf-8")
    sender = await event.get_sender()
    username = sender.username or ""
    first_name = sender.first_name or "Khách hàng"
    db.get_or_create_user(user_id, username, first_name)

    # 1. Quay về Menu chính
    if data == "menu_main":
        user_states.pop(user_id, None)
        welcome_text = (
            f"👋 **Menu Chính Shop Dịch Vụ**\n\n"
            f"Vui lòng chọn dịch vụ hoặc tính năng bạn muốn thao tác:"
        )
        try:
            await event.edit(welcome_text, buttons=get_main_menu_buttons(user_id))
        except MessageNotModifiedError:
            pass
        await event.answer()
        return

    # 2. Danh mục sản phẩm
    if data == "menu_products":
        text = (
            "🛍️ **BẢNG GIÁ DỊCH VỤ BẢN QUYỀN CHÍNH HÃNG**\n\n"
            "1. 🎁 **Locket Gold Miễn Phí:** `0 VNĐ`\n"
            "2. 🎨 **Canva Pro Edu Miễn Phí:** `0 VNĐ`\n"
            "3. 💛 **Locket Gold 2 Năm:** `80.000 VNĐ`\n"
            "4. 🎨 **Canva Pro Edu 12 Tháng:** `40.000 VNĐ`\n"
            "5. 👑 **Admin Canva Pro Edu 2 Năm:** `120.000 VNĐ`\n"
            "6. 🤖 **Gemini Pro 18 Tháng:** `200.000 VNĐ`\n\n"
            "👇 Bấm vào từng sản phẩm dưới đây để xem chi tiết & đặt mua:"
        )
        try:
            await event.edit(text, buttons=get_products_menu_buttons())
        except MessageNotModifiedError:
            pass
        await event.answer()
        return

    # 3. Xem chi tiết sản phẩm
    if data.startswith("view_prod_"):
        prod_id = data.replace("view_prod_", "")
        prod = get_product_by_id(prod_id)
        if not prod:
            await event.answer("⚠️ Sản phẩm không tồn tại!", alert=True)
            return

        detail_text = (
            f"✨ **{prod['name']}**\n\n"
            f"🏷️ **Giá niêm yết:** `{format_money(prod['price'])}`\n"
            f"💎 **Thời hạn/Gói:** {prod.get('badge', '')}\n\n"
            f"📝 **Mô Tả & Quyền Lợi:**\n{prod['description']}\n\n"
            f"🛡️ **Cam kết:** Kích hoạt nhanh chóng, bảo hành 1 đổi 1 suốt thời gian sử dụng."
        )

        if prod["price"] == 0:
            if prod["id"] == "canva_free":
                action_btn = Button.inline("🎨 Bấm Để Nhận Miễn Phí (0đ)", b"start_canva_free_flow")
            else:
                action_btn = Button.inline("🎁 Bấm Để Nhận Miễn Phí (0đ)", b"start_locket_free_flow")
        else:
            action_btn = Button.inline(f"🛒 Mua Ngay ({format_money(prod['price'])})", f"order_{prod['id']}".encode())

        buttons = [
            [action_btn],
            [Button.inline("⬅️ Quay Lại Bảng Giá", b"menu_products")]
        ]
        try:
            await event.edit(detail_text, buttons=buttons)
        except MessageNotModifiedError:
            pass
        await event.answer()
        return

    # XÁC MINH VÀO NHÓM CỘNG ĐỒNG
    if data == "verify_joined_group":
        target = GROUP_ID if GROUP_ID else (GROUP_USERNAME if GROUP_USERNAME else None)
        if not target:
            await event.answer("⚠️ Hệ thống đang cập nhật kênh, vui lòng thử lại sau!", alert=True)
            return

        is_member = False
        try:
            participant = await client.get_permissions(target, user_id)
            is_member = bool(participant and (participant.is_admin or participant.participant))
        except Exception as e:
            logger.warning(f"Quét kênh/nhóm khi bấm nút ({target}) lỗi: {e}")
            is_member = False

        if is_member:
            db.set_group_verified(user_id)
            await event.answer("🎉 Tuyệt vời! Bạn đã xác minh vào kênh thành công.", alert=True)

            # Tự động kích hoạt liên kết nếu người này vào qua link của bạn bè
            curr_user = db.get_or_create_user(user_id)
            pending_ref = curr_user.get("pending_referrer_id")
            if pending_ref and not db.is_user_already_linked(user_id):
                linked = db.link_referral_mutual(user_id, pending_ref)
                if linked:
                    curr_user["pending_referrer_id"] = None
                    db.save()
                    try:
                        await client.send_message(
                            pending_ref,
                            f"🎉 **BẠN BÈ ĐÃ KẾT NỐI THÀNH CÔNG!**\n\n"
                            f"✅ Người bạn của bạn (@{sender.username or sender.first_name}) đã tham gia Kênh và hoàn thành điều kiện.\n"
                            f"✨ Hai tài khoản đã được liên kết thành công! Bây giờ bạn có thể bấm **🎁 Nhận Locket Gold Free** để lấy link mở ứng dụng ngay lập tức!"
                        )
                    except Exception:
                        pass

            welcome_text = (
                f"🎉 **XÁC MINH THÀNH CÔNG!**\n\n"
                f"Cảm ơn bạn đã tham gia kênh cộng đồng. Mọi chức năng và ưu đãi của bot đã được mở khóa!\n"
                f"👇 _Chọn chức năng bên dưới để tiếp tục:_"
            )
            try:
                await event.edit(welcome_text, buttons=get_main_menu_buttons(user_id))
            except Exception:
                await event.respond(welcome_text, buttons=get_main_menu_buttons(user_id))
        else:
            await event.answer("⚠️ Bot kiểm tra bạn VẪN CHƯA tham gia kênh! Vui lòng bấm '👉 Tham Gia Kênh Cộng Đồng' trước rồi thử lại nhé.", alert=True)
        return

    # LUỒNG NHẬN LOCKET GOLD FREE: YÊU CẦU GIỚI THIỆU BẠN BÈ
    if data == "start_locket_free_flow":
        # Kiểm tra nếu là Admin hoặc user này đã hoàn thành giới thiệu bạn bè chưa
        user_data = db.get_or_create_user(user_id)
        friend_id = user_data.get("referred_friend_id")

        is_exempt = is_admin(user_id) and (user_id not in test_regular_users)
        if is_exempt or friend_id:
            # ĐÃ ĐỦ ĐIỀU KIỆN HOẶC LÀ ADMIN: HIỂN THỊ TRỰC TIẾP NÚT CHUYỂN ĐẾN APP
            text_success = (
                "🎉 **CHÚC MỪNG BẠN ĐÃ ĐỦ ĐIỀU KIỆN!**\n\n"
                "✅ Bạn đã hoàn thành nhiệm vụ giới thiệu bạn bè và tham gia nhóm cộng đồng.\n"
                "👇 Bấm nút bên dưới để mở ứng dụng nhận Locket Gold Free ngay lập tức:"
            )
            buttons = [
                [Button.url("🚀 MỞ APP NHẬN LOCKET GOLD FREE", "https://t.me/nghientrickshop_bot?startapp")],
                [Button.inline("⬅️ Về Menu Chính", b"menu_main")]
            ]
            try:
                await event.edit(text_success, buttons=buttons)
            except Exception:
                await event.respond(text_success, buttons=buttons)
            await event.answer()
            return

        # CHƯA ĐỦ ĐIỀU KIỆN: ĐƯA RA NHIỆM VỤ GIỚI THIỆU BẠN BÈ VỚI 2 PHƯƠNG THỨC
        ref_code = db.get_user_ref_code(user_id)
        bot_info = await client.get_me()
        bot_user = bot_info.username or "locketfreeshop_bot"
        ref_link = f"https://t.me/{bot_user}?start={ref_code}"
        cmd_code = f"/{ref_code}"

        ref_text = (
            "🎁 **ĐIỀU KIỆN NHẬN LOCKET GOLD FREE (0Đ)**\n\n"
            "Để nhận link mở ứng dụng Locket Gold Free, bạn chỉ cần **kết nối với 1 người bạn** (hoặc 1 nick phụ/clone của bạn) qua **1 trong 2 cách sau**:\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "🔗 **CÁCH 1: GỬI LINK GIỚI THIỆU TRỰC TIẾP**\n"
            f"• Link của bạn: `{ref_link}`\n"
            "👉 Gửi link này cho bạn bè bấm vào. Khi bạn bè bấm **/start** và **tham gia Kênh cộng đồng**, hệ thống sẽ tự động liên kết 2 tài khoản ngay lập tức!\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "🔑 **CÁCH 2: SAO CHÉP MÃ LỆNH 8 KÝ TỰ**\n"
            f"• Mã kết nối của bạn: `{cmd_code}`\n"
            "👉 Bạn của bạn chỉ cần vào bot, vượt qua bước tham gia Kênh, sau đó **nhắn tin đúng mã trên** vào bot là 2 tài khoản tự động liên kết thành công!\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "💡 **Mẹo:** Bạn có thể tự tạo 1 tài khoản Telegram clone rồi tự gửi link/mã để hoàn thành ngay trong 1 phút!\n"
            "⚠️ _Lưu ý: Hai tài khoản sau khi liên kết với nhau sẽ được tính hoàn thành và không thể liên kết thêm với ai khác nữa._"
        )
        buttons = [
            [Button.inline("🔗 Sao Chép Link Giới Thiệu", f"copy_link_{ref_code}".encode())],
            [Button.inline(f"📋 Sao Chép Mã ({cmd_code})", f"copy_code_{ref_code}".encode())],
            [Button.inline("⬅️ Quay Lại Menu", b"menu_main")]
        ]
        try:
            await event.edit(ref_text, buttons=buttons)
        except Exception:
            await event.respond(ref_text, buttons=buttons)
        await event.answer()
        return

    # LUỒNG NHẬN CANVA PRO EDU FREE: GỬI LINK TRỰC TIẾP KHÔNG CẦN GIỚI THIỆU
    if data == "start_canva_free_flow":
        text = (
            "🎉 **QUÀ TẶNG CANVA PRO EDU FREE (0Đ) TỪ SHOP!**\n\n"
            "✨ Dưới đây là liên kết mời tham gia nhóm gia đình **Canva Pro Edu Miễn Phí (0đ)** của shop:\n\n"
            f"🔗 **Link mời tham gia:**\n`{CANVA_INVITE_LINK}`\n\n"
            "👉 **Hướng dẫn:** Bạn chỉ cần bấm vào link trên (hoặc bấm nút bên dưới), đăng nhập tài khoản Canva của bạn là sẽ được tự động tham gia nhóm Canva Pro Edu với đầy đủ tính năng Premium!\n\n"
            "👇 Bấm nút bên dưới để tham gia nhóm ngay lập tức:"
        )
        buttons = [
            [Button.url("🎨 THAM GIA GIA ĐÌNH CANVA PRO EDU", CANVA_INVITE_LINK)],
            [Button.inline("⬅️ Về Menu Chính", b"menu_main")]
        ]
        try:
            await event.edit(text, buttons=buttons)
        except Exception:
            await event.respond(text, buttons=buttons)
        await event.answer()
        return

    # NÚT BẤM SAO CHÉP LINK GIỚI THIỆU
    if data.startswith("copy_link_"):
        code = data.replace("copy_link_", "").strip()
        bot_info = await client.get_me()
        bot_user = bot_info.username or "locketfreeshop_bot"
        ref_link = f"https://t.me/{bot_user}?start={code}"
        await event.answer()
        await event.respond(ref_link)
        return

    # NÚT BẤM SAO CHÉP MÃ LIÊN KẾT 8 KÝ TỰ
    if data.startswith("copy_code_"):
        code = data.replace("copy_code_", "").strip()
        cmd = f"/{code}"
        await event.answer()
        await event.respond(cmd)
        return

    # BẮT ĐẦU NHẬP USERNAME BẠN BÈ
    if data == "enter_referral_friend":
        user_states[user_id] = {
            "step": "waiting_referral_username",
            "expires_at": time.time() + TIMEOUT_INPUT_SECONDS
        }
        prompt = (
            "✍️ **NHẬP THÔNG TIN NGƯỜI BẠN BẠN ĐÃ MỜI**\n\n"
            "Vui lòng gửi **@username** (hoặc ID Telegram) của người bạn đã mời vào tin nhắn này:\n\n"
            "_(Ví dụ: `@manh0710` hoặc `manh0710`)_\n"
            "⏱️ _Thời gian thao tác: 3 phút._"
        )
        await event.respond(prompt, buttons=[[Button.inline("❌ Hủy Bỏ", b"cancel_order")]])
        await event.answer()
        return

    # 4. Đặt mua sản phẩm (Bắt đầu bước nhập thông tin)
    if data.startswith("order_"):
        prod_id = data.replace("order_", "")
        prod = get_product_by_id(prod_id)
        if not prod:
            await event.answer("⚠️ Sản phẩm không tồn tại!", alert=True)
            return

        # Kiểm tra nếu là gói free và user đã nhận rồi
        if prod["price"] == 0 and db.has_claimed_free(user_id, prod["id"]):
            await event.answer(
                "⚠️ Bạn đã nhận gói Locket Gold Miễn Phí rồi!\nMỗi tài khoản chỉ được nhận 1 lần. Bạn có thể tham khảo gói 2 Năm nhé!",
                alert=True
            )
            return

        # Lưu trạng thái chờ người dùng nhập thông tin
        user_states[user_id] = {
            "step": "waiting_input",
            "product_id": prod_id,
            "expires_at": time.time() + TIMEOUT_INPUT_SECONDS
        }

        prompt_text = (
            f"📝 **BƯỚC ĐẶT HÀNG: {prod['name']}**\n\n"
            f"💰 **Giá thanh toán:** `{format_money(prod['price'])}`\n"
            f"👉 **Yêu cầu:** {prod.get('input_prompt', 'Vui lòng nhập Email hoặc Tài khoản nhận dịch vụ:')}\n\n"
            f"💡 _{prod.get('input_placeholder', '')}_\n\n"
            f"⏱️ _Thời gian thao tác: {TIMEOUT_INPUT_SECONDS // 60} phút. Vui lòng gửi tin nhắn trả lời trực tiếp bên dưới!_"
        )

        buttons = [[Button.inline("❌ Hủy Bỏ", b"cancel_order")]]
        await event.respond(prompt_text, buttons=buttons)
        await event.answer()
        return

    # 5. Hủy đơn hàng / hủy thao tác
    if data == "cancel_order":
        user_states.pop(user_id, None)
        await event.edit("❌ **Đã hủy thao tác đặt hàng.**", buttons=[[Button.inline("⬅️ Về Menu Chính", b"menu_main")]])
        await event.answer("Đã hủy")
        return

    # 6. Đơn hàng của tôi
    if data == "my_orders":
        orders = db.get_user_orders(user_id, limit=5)
        if not orders:
            msg = "📋 **Bạn chưa có đơn hàng nào trong lịch sử!**\nHãy chọn một sản phẩm để trải nghiệm nhé."
        else:
            msg = "📋 **DANH SÁCH ĐƠN HÀNG GẦN ĐÂY CỦA BẠN:**\n\n"
            for o in orders:
                st = o.get("status")
                st_icon = "✅ Đã Hoàn Tất" if st in ["COMPLETED"] else ("💳 Đã Thanh Toán - Chờ Bàn Giao" if st == "PAID" else ("⏳ Chờ Thanh Toán" if st == "PENDING" else "❌ Đã Hủy"))
                msg += (
                    f"📦 **Đơn hàng:** `#{o['order_id']}`\n"
                    f"• Dịch vụ: **{o['product_name']}**\n"
                    f"• Giá: `{format_money(o['amount'])}`\n"
                    f"• Trạng thái: {st_icon}\n"
                    f"• Ngày đặt: {o['created_at']}\n"
                    f"────────────────────\n"
                )
        buttons = [
            [Button.inline("🛍️ Xem Bảng Giá Mua Thêm", b"menu_products")],
            [Button.inline("⬅️ Quay Lại", b"menu_main")]
        ]
        try:
            await event.edit(msg, buttons=buttons)
        except MessageNotModifiedError:
            pass
        await event.answer()
        return

    # 7. Hỗ trợ khách hàng
    if data == "contact_support":
        await start_customer_support_flow(event, user_id, is_callback=True)
        return

    # Hủy yêu cầu hỗ trợ
    if data == "cancel_support":
        user_states.pop(user_id, None)
        try:
            await event.edit("❌ **Đã hủy gửi tin nhắn hỗ trợ.**", buttons=[[Button.inline("⬅️ Về Menu Chính", b"menu_main")]])
        except Exception:
            await event.respond("❌ **Đã hủy gửi tin nhắn hỗ trợ.**", buttons=[[Button.inline("⬅️ Về Menu Chính", b"menu_main")]])
        await event.answer("Đã hủy")
        return

    # 8. Hướng dẫn mua
    if data == "guide":
        text = (
            "📜 **HƯỚNG DẪN MUA HÀNG VÀ KÍCH HOẠT DỊCH VỤ**\n\n"
            "• **Gói Free 0đ:** Bạn chỉ cần chọn gói, nhập Email/Username Locket, bot sẽ ghi nhận và gửi Admin kích hoạt.\n"
            "• **Gói Trả Phí:** Bạn nhập thông tin, hệ thống sẽ tạo mã QR thanh toán VietQR tự động qua PayOS. Quét mã xong tiền vào tài khoản là hệ thống tự động xác nhận ngay lập tức!\n"
            "• **Bảo hành:** Cam kết bảo hành 1 đổi 1 suốt thời gian sử dụng."
        )
        buttons = [[Button.inline("⬅️ Quay Lại", b"menu_main")]]
        try:
            await event.edit(text, buttons=buttons)
        except MessageNotModifiedError:
            pass
        await event.answer()
        return

    # 9. Kiểm tra thanh toán thủ công (Nút Kiểm Tra)
    if data.startswith("check_pay_"):
        parts = data.split("_")
        if len(parts) >= 4:
            order_id = parts[2]
            order_code = int(parts[3])
            status = payos_service.check_payment_status(order_code)
            if status == "PAID":
                db.update_order_status(order_id, "PAID")
                await event.answer("🎉 Thanh toán đã được xác nhận thành công!", alert=True)
                await handle_paid_order(user_id, order_id)
            elif status == "PENDING":
                await event.answer("⏳ Hệ thống chưa nhận được giao dịch. Bạn vui lòng kiểm tra lại tiền đã trừ trong app ngân hàng chưa nhé!", alert=True)
            elif status in ["CANCELLED", "EXPIRED"]:
                db.update_order_status(order_id, "CANCELLED")
                await event.answer("❌ Đơn hàng này đã bị hủy hoặc hết hạn!", alert=True)
            else:
                await event.answer("Đang kiểm tra...", alert=False)
        return

    # 10. Admin: Bàn giao dịch vụ cho khách (Deliver)
    if data.startswith("admin_deliver_"):
        if not is_admin(user_id):
            await event.answer("⛔ Bạn không phải admin!", alert=True)
            return
        order_id = data.replace("admin_deliver_", "")
        await start_admin_deliver_flow(event, order_id, user_id, is_callback=True)
        return

    # Hủy thao tác bàn giao đơn hàng
    if data == "admin_cancel_deliver":
        user_states.pop(user_id, None)
        try:
            await event.edit("❌ **Đã hủy thao tác bàn giao đơn hàng.**")
        except Exception:
            await event.respond("❌ **Đã hủy thao tác bàn giao đơn hàng.**")
        await event.answer("Đã hủy")
        return

    # 11. Admin Panel
    if data == "admin_panel":
        if not is_admin(user_id):
            await event.answer("⛔ Không có quyền!", alert=True)
            return
        await show_admin_panel(event, is_callback=True)
        await event.answer()
        return

    # 11.1 Admin Xem danh sách hỗ trợ khách hàng
    if data == "admin_support_list":
        if not is_admin(user_id):
            await event.answer("⛔ Không có quyền!", alert=True)
            return
        tickets = db.get_pending_support_tickets()
        if not tickets:
            await event.edit(
                "✅ **Hiện tại không có yêu cầu hỗ trợ nào đang chờ xử lý!**\n"
                "Tất cả câu hỏi của khách hàng đã được phản hồi.",
                buttons=[[Button.inline("⬅️ Quay Lại Admin", b"admin_panel")]]
            )
        else:
            msg = f"📋 **DANH SÁCH {len(tickets)} KHÁCH HÀNG ĐANG CHỜ HỖ TRỢ:**\n\n"
            buttons = []
            for t in tickets[:8]:
                uname = f"@{t['username']}" if t.get('username') else f"ID: {t['user_id']}"
                msg += (
                    f"👤 **{uname}** (`{t['user_id']}`) - #{t['ticket_id']}\n"
                    f"• Tên: {t.get('first_name', '')}\n"
                    f"• Thời gian: {t['created_at']}\n"
                    f"• Câu hỏi: \"{t['message'][:120]}\"\n"
                    f"────────────────────\n"
                )
                buttons.append([Button.inline(f"💬 Trả Lời #{t['ticket_id']} ({uname})", f"admin_reply_ticket_{t['ticket_id']}".encode())])
            buttons.append([Button.inline("🔄 Làm Mới", b"admin_support_list")])
            buttons.append([Button.inline("⬅️ Quay Lại Admin", b"admin_panel")])
            await event.edit(msg, buttons=buttons)
        await event.answer()
        return

    # 11.2 Admin Bấm Trả lời ticket hỗ trợ
    if data.startswith("admin_reply_ticket_"):
        if not is_admin(user_id):
            await event.answer("⛔ Bạn không phải admin!", alert=True)
            return
        ticket_id = data.replace("admin_reply_ticket_", "").strip()
        ticket = db.get_support_ticket(ticket_id)
        if not ticket:
            await event.answer("⚠️ Yêu cầu hỗ trợ không tồn tại hoặc đã được xử lý!", alert=True)
            return
        user_states[user_id] = {
            "step": "admin_replying_support",
            "ticket_id": ticket_id
        }
        prompt = (
            f"💬 **TRẢ LỜI YÊU CẦU HỖ TRỢ #{ticket_id}:**\n\n"
            f"• **Khách hàng:** @{ticket.get('username') or ticket['user_id']} (`{ticket['user_id']}`)\n"
            f"• **Tên:** {ticket.get('first_name', '')}\n"
            f"• **Thời gian gửi:** {ticket.get('created_at', '')}\n\n"
            f"❓ **Nội dung câu hỏi của khách:**\n"
            f"\"{ticket.get('message')}\"\n\n"
            f"👉 **Admin vui lòng soạn nội dung phản hồi gửi vào đây:**\n"
            f"_(Bot sẽ chuyển tiếp tin nhắn trả lời này trực tiếp cho khách hàng)_"
        )
        buttons = [[Button.inline("❌ Hủy Trả Lời", b"admin_cancel_reply")]]
        await event.respond(prompt, buttons=buttons)
        await event.answer()
        return

    # 11.3 Admin Hủy trả lời
    if data == "admin_cancel_reply":
        user_states.pop(user_id, None)
        try:
            await event.edit("❌ **Đã hủy thao tác trả lời khách hàng.**")
        except Exception:
            await event.respond("❌ **Đã hủy thao tác trả lời khách hàng.**")
        await event.answer("Đã hủy")
        return

    # 12. Admin Backup Trigger
    if data == "admin_backup":
        if not is_admin(user_id):
            await event.answer("⛔ Không có quyền!", alert=True)
            return
        await event.answer("Đang xuất dữ liệu backup...")
        await perform_backup_to_chat(event.chat_id)
        return

    # 13. Admin Broadcast Trigger
    if data == "admin_broadcast":
        if not is_admin(user_id):
            await event.answer("⛔ Không có quyền!", alert=True)
            return
        user_states[user_id] = {
            "step": "waiting_broadcast",
            "expires_at": time.time() + 300
        }
        await event.respond(
            "📢 **GỬI THÔNG BÁO TỚI TOÀN BỘ NGƯỜI DÙNG**\n\n"
            "Vui lòng soạn tin nhắn bạn muốn gửi (hỗ trợ văn bản, hình ảnh, link):\n"
            "_(Gõ /cancel hoặc bấm nút bên dưới để hủy)_",
            buttons=[[Button.inline("❌ Hủy Thông Báo", b"cancel_order")]]
        )
        await event.answer()
        return

    # 14. Admin Xem đơn chờ bàn giao
    if data == "admin_pending_orders":
        if not is_admin(user_id):
            await event.answer("⛔ Không có quyền!", alert=True)
            return
        pending = db.get_pending_delivery_orders()
        if not pending:
            await event.edit(
                "✅ **Hiện tại không có đơn hàng nào cần bàn giao!**",
                buttons=[[Button.inline("⬅️ Quay Lại Admin", b"admin_panel")]]
            )
        else:
            msg = f"📋 **DANH SÁCH {len(pending)} ĐƠN HÀNG CẦN BÀN GIAO:**\n\n"
            for o in pending[:8]:
                msg += (
                    f"📦 **#{o['order_id']}** - {o['product_name']}\n"
                    f"• Khách: @{o.get('username') or o.get('user_id')} (`{o['user_id']}`)\n"
                    f"• Tiền: `{format_money(o['amount'])}`\n"
                    f"• Thông tin: `{o.get('customer_info')}`\n"
                    f"• Thời gian: {o['created_at']}\n"
                    f"👉 Bàn giao: /deliver_{o['order_id']}\n"
                    f"────────────────────\n"
                )
            buttons = [
                [Button.inline("🔄 Làm Mới", b"admin_pending_orders")],
                [Button.inline("⬅️ Quay Lại Admin", b"admin_panel")]
            ]
            await event.edit(msg, buttons=buttons)
        await event.answer()
        return

# ==================== XỬ LÝ TIN NHẮN VĂN BẢN (USER INPUT / TEXT) ====================

@client.on(events.NewMessage)
async def message_input_handler(event):
    raw_text = (event.raw_text or "").strip()

    # Lệnh nhanh bàn giao: /deliver_DH12345678
    if raw_text.startswith("/deliver_") and is_admin(event.sender_id):
        order_id = raw_text.replace("/deliver_", "").strip()
        await start_admin_deliver_flow(event, order_id, event.sender_id, is_callback=False)
        return

    # Lệnh bỏ qua gửi file/link: /skip_DH12345678
    if raw_text.startswith("/skip_") and is_admin(event.sender_id):
        order_id = raw_text.replace("/skip_", "").strip()
        order = db.get_order(order_id)
        if order:
            db.update_order_status(order_id, "COMPLETED")
            user_states.pop(event.sender_id, None)
            await event.respond(f"✅ Đã xác nhận bàn giao đơn hàng #{order_id} thành công (bỏ qua file/link)!")
            try:
                cust_text = (
                    f"🎉 **DỊCH VỤ CỦA BẠN ĐÃ ĐƯỢC KÍCH HOẠT THÀNH CÔNG!**\n\n"
                    f"• **Mã đơn hàng:** `#{order_id}`\n"
                    f"• **Dịch vụ:** **{order.get('product_name')}**\n"
                    f"• **Thông tin:** `{order.get('customer_info')}`\n\n"
                    f"✨ Cảm ơn bạn đã tin tưởng sử dụng dịch vụ của shop! ❤️"
                )
                await client.send_message(order["user_id"], cust_text)
            except Exception:
                pass
        else:
            await event.respond(f"⚠️ Không tìm thấy đơn hàng {order_id}!")
        return

    # KIỂM TRA TRẠNG THÁI ADMIN BÀN GIAO ĐƠN HÀNG (GEMINI / LOCKET)
    admin_state = user_states.get(event.sender_id, {})
    admin_step = admin_state.get("step")

    # 1. ADMIN GỬI LINK KÍCH HOẠT GEMINI 18 THÁNG
    if admin_step == "admin_waiting_gemini_link" and is_admin(event.sender_id):
        order_id = admin_state.get("order_id")
        gemini_link = raw_text.strip()
        order = db.get_order(order_id)
        if not order:
            user_states.pop(event.sender_id, None)
            await event.respond("⚠️ Đơn hàng không tồn tại hoặc đã bị hủy!")
            return

        db.update_order_status(order_id, "COMPLETED")
        user_states.pop(event.sender_id, None)

        gemini_guide = (
            f"🎉 **DỊCH VỤ GEMINI PRO 18 THÁNG CỦA BẠN ĐÃ SẴN SÀNG!**\n\n"
            f"• **Mã đơn hàng:** `#{order_id}`\n"
            f"• **Dịch vụ:** **{order.get('product_name')}**\n"
            f"• **Email nhận:** `{order.get('customer_info')}`\n\n"
            f"🔗 **Link ưu đãi 18 tháng của bạn:**\n"
            f"`{gemini_link}`\n\n"
            f"📖 **HƯỚNG DẪN KÍCH HOẠT (BẠN LÀM THEO HƯỚNG DẪN SAU):**\n"
            f"👉 **Đầu tiên:** Bạn đăng nhập tài khoản của bạn trên thiết bị của bạn.\n"
            f"👉 **Sau đó:** Bạn dán link ưu đãi 18 tháng bên dưới vào trình duyệt đó.\n"
            f"👉 **Sau khi dán bạn kiểm tra các thông tin sau:**\n"
            f"   1️⃣ Chọn đúng tài khoản, nếu chưa đúng bạn đổi lại nhé.\n"
            f"   2️⃣ Miễn phí 18 tháng gói GG AI Pro.\n"
            f"   3️⃣ Bạn kéo xuống dưới sẽ có hạn kết thúc gói chuẩn 18 tháng.\n"
            f"👉 **Đúng thông tin bạn ấn kích hoạt là xong.**\n"
            f"👉 **Sau đó:** Bạn vào GG One hoặc Gemini để kiểm tra xem lên Pro chưa ạ!\n\n"
            f"🛡️ **Bảo hành:** Gói dịch vụ bảo hành 1 đổi 1 suốt 18 tháng sử dụng. Cảm ơn bạn đã tin tưởng ủng hộ shop! ❤️"
        )
        buttons = [[Button.url("🚀 MỞ LINK KÍCH HOẠT GEMINI", gemini_link)]]
        try:
            await client.send_message(order["user_id"], gemini_guide, buttons=buttons)
            await event.respond(f"✅ Đã gửi link ưu đãi và hướng dẫn kích hoạt Gemini 18 tháng cho khách `#{order_id}` thành công!")
        except Exception as e:
            await event.respond(f"⚠️ Đã đánh dấu hoàn tất đơn nhưng không gửi được tin nhắn cho khách: {e}")
        return

    # 2. ADMIN GỬI FILE CẤU HÌNH DNS LOCKET
    if admin_step == "admin_waiting_locket_dns" and is_admin(event.sender_id):
        order_id = admin_state.get("order_id")
        order = db.get_order(order_id)
        if not order:
            user_states.pop(event.sender_id, None)
            await event.respond("⚠️ Đơn hàng không tồn tại hoặc đã bị hủy!")
            return

        db.update_order_status(order_id, "COMPLETED")
        user_states.pop(event.sender_id, None)

        locket_guide = (
            f"🎉 **GÓI LOCKET GOLD CỦA BẠN ĐÃ ĐƯỢC BÀN GIAO THÀNH CÔNG!**\n\n"
            f"• **Mã đơn hàng:** `#{order_id}`\n"
            f"• **Dịch vụ:** **{order.get('product_name')}**\n"
            f"• **Tài khoản Locket:** `{order.get('customer_info')}`\n\n"
            f"📁 **FILE CẤU HÌNH DNS LOCKET ĐÍNH KÈM Ở TRÊN**\n\n"
            f"📖 **HƯỚNG DẪN CÀI ĐẶT & SỬ DỤNG DNS LOCKET:**\n"
            f"1️⃣ **Bước 1:** Bấm vào file cấu hình DNS đính kèm ở trên để tải về điện thoại.\n"
            f"2️⃣ **Bước 2 (Dành cho iOS/iPhone):**\n"
            f"   • Vào **Cài đặt** trên điện thoại ➡️ Chọn mục **Đã tải về hồ sơ** ở trên cùng.\n"
            f"   • Bấm **Cài đặt** ở góc trên cùng bên phải ➡️ Nhập mật khẩu máy để xác nhận.\n"
            f"3️⃣ **Bước 3:**\n"
            f"   • Vào **Cài đặt** ➡️ **Cài đặt chung** ➡️ **Quản lý VPN & Thiết bị** ➡️ Mục **DNS**.\n"
            f"   • Tích chọn vào cấu hình DNS Locket vừa cài đặt.\n"
            f"4️⃣ **Bước 4:** Mở ứng dụng Locket và trải nghiệm trọn bộ tính năng VIP Gold vĩnh viễn!\n\n"
            f"🛡️ **Bảo hành:** Gói dịch vụ bảo hành chính hãng 1 đổi 1 suốt 2 năm (24 tháng). Chúc bạn có trải nghiệm tuyệt vời! ❤️"
        )
        try:
            if event.message.media:
                await client.send_file(order["user_id"], event.message.media, caption=locket_guide)
            else:
                extra_note = f"\n\n📝 **Ghi chú của Admin:**\n{raw_text}" if raw_text else ""
                await client.send_message(order["user_id"], locket_guide + extra_note)
            await event.respond(f"✅ Đã bàn giao File DNS và toàn bộ hướng dẫn cài đặt Locket cho khách `#{order_id}` thành công!")
        except Exception as e:
            await event.respond(f"⚠️ Đã đánh dấu hoàn tất đơn nhưng không gửi được file/tin nhắn cho khách: {e}")
        return

    # 3. ADMIN TRẢ LỜI YÊU CẦU HỖ TRỢ CỦA KHÁCH HÀNG
    if admin_step == "admin_replying_support" and is_admin(event.sender_id):
        ticket_id = admin_state.get("ticket_id")
        ticket = db.get_support_ticket(ticket_id)
        reply_text = raw_text.strip()
        user_states.pop(event.sender_id, None)

        if not ticket:
            await event.respond("⚠️ Yêu cầu hỗ trợ không tồn tại hoặc đã được xử lý!")
            return

        db.resolve_support_ticket(ticket_id, reply_text)

        msg_cust = (
            f"💬 **PHẢN HỒI TỪ ADMIN SHOP**\n\n"
            f"• **Mã yêu cầu:** `#{ticket_id}`\n"
            f"• **Câu hỏi của bạn:** \"{ticket.get('message')}\"\n\n"
            f"📝 **Nội dung trả lời từ Admin:**\n"
            f"{reply_text}\n\n"
            f"────────────────────\n"
            f"✨ Cảm ơn bạn đã liên hệ! Nếu vẫn còn thắc mắc, bạn hãy bấm vào mục **💬 Hỗ Trợ Khách Hàng** để tiếp tục gửi câu hỏi nhé! ❤️"
        )
        try:
            await client.send_message(ticket["user_id"], msg_cust)
            await event.respond(f"✅ Đã gửi phản hồi thành công tới khách hàng @{ticket.get('username') or ticket['user_id']} (`#{ticket_id}`)!")
        except Exception as e:
            await event.respond(f"⚠️ Đã lưu phản hồi nhưng không gửi được tới khách: {e}")
        return

    # XỬ LÝ KHÁCH HÀNG GỬI YÊU CẦU HỖ TRỢ CHO ADMIN
    if user_states.get(event.sender_id, {}).get("step") == "waiting_customer_support":
        customer_msg = (event.raw_text or "").strip()
        if len(customer_msg) < 2:
            await event.respond("⚠️ Câu hỏi của bạn quá ngắn. Vui lòng nhập nội dung chi tiết để Admin hỗ trợ nhé:")
            return

        cust_user_id = event.sender_id
        user_states.pop(cust_user_id, None)
        sender = await event.get_sender()
        username = (sender.username or "") if sender else ""
        first_name = (sender.first_name or "Khách hàng") if sender else "Khách hàng"

        # Tạo ticket trong DB
        ticket = db.create_support_ticket(cust_user_id, username, first_name, customer_msg)

        # Phản hồi cho khách
        await event.respond(
            f"✅ **YÊU CẦU HỖ TRỢ ĐÃ ĐƯỢC GỬI THÀNH CÔNG!**\n\n"
            f"• **Mã yêu cầu:** `#{ticket['ticket_id']}`\n"
            f"• **Nội dung:** \"{customer_msg}\"\n\n"
            f"⚡ Tin nhắn của bạn đã được chuyển tới Admin. Admin sẽ phản hồi trực tiếp qua bot trong thời gian sớm nhất! ❤️",
            buttons=[[Button.inline("⬅️ Về Menu Chính", b"menu_main")]]
        )

        # Thông báo cho toàn bộ Admin
        admin_alert = (
            f"📩 **YÊU CẦU HỖ TRỢ MỚI TỪ KHÁCH HÀNG!**\n\n"
            f"• **Khách hàng:** @{username or cust_user_id} (`{cust_user_id}`)\n"
            f"• **Tên:** {first_name}\n"
            f"• **Mã hỗ trợ:** `#{ticket['ticket_id']}`\n"
            f"• **Thời gian:** {ticket['created_at']}\n\n"
            f"❓ **Nội dung câu hỏi:**\n"
            f"\"{customer_msg}\""
        )
        buttons_admin = [
            [Button.inline(f"💬 Trả Lời Khách #{ticket['ticket_id']}", f"admin_reply_ticket_{ticket['ticket_id']}".encode())],
            [Button.url("👤 Nhắn Tin Riêng Cho Khách", f"tg://user?id={cust_user_id}")]
        ]
        for aid in ADMIN_IDS:
            try:
                await client.send_message(aid, admin_alert, buttons=buttons_admin)
            except Exception as e:
                logger.error(f"Lỗi gửi thông báo hỗ trợ cho admin {aid}: {e}")
        return

    # XỬ LÝ PHƯƠNG THỨC 2: NHẬP MÃ GIỚI THIỆU 8 KÝ TỰ (dạng /abcsf... hoặc abcsf...)
    raw_text = (event.raw_text or "").strip()
    # Loại bỏ @bot_username nếu người dùng bấm hoặc gửi dạng /code@bot
    clean_code = raw_text.split("@")[0].strip().lstrip("/").strip().lower()
    if len(clean_code) == 8 and clean_code.isalnum() and not raw_text.startswith("/deliver_"):
        referrer = db.find_user_by_ref_code(clean_code)
        if referrer:
            user_id = event.sender_id
            sender = await event.get_sender()
            sender_name = (sender.username if sender and sender.username else (sender.first_name if sender else "Bạn")) or "Bạn"

            # 1. Không được tự nhập mã của chính mình
            if referrer["id"] == user_id:
                await event.respond(
                    "❌ **Không thể tự kết nối:** Đây là mã kết nối của chính bạn!\n"
                    "👉 Hãy gửi mã này cho một người bạn khác (hoặc tài khoản clone) để hoàn thành nhé."
                )
                return

            # 2. Kiểm tra xem người gửi mã đã tham gia kênh cộng đồng chưa
            is_member = await check_user_in_group(user_id)
            if not is_member:
                prompt_text, buttons = get_join_group_prompt(user_id)
                await event.respond(
                    "⚠️ **BẠN CẦN THAM GIA KÊNH CỘNG ĐỒNG TRƯỚC!**\n\n"
                    "Để nhập mã kết nối bạn bè, bạn vui lòng tham gia kênh cộng đồng của shop trước nhé:\n\n" + prompt_text,
                    buttons=buttons
                )
                return

            # 3. Kiểm tra xem tài khoản này hoặc tài khoản bạn bè đã liên kết với ai trước đó chưa
            if db.is_user_already_linked(user_id):
                user_data = db.get_or_create_user(user_id)
                await event.respond(
                    "⚠️ **Tài khoản của bạn đã được liên kết giới thiệu trước đó rồi!**\n\n"
                    "Mỗi tài khoản chỉ được kết nối với 1 người bạn duy nhất. "
                    "Bạn đã đủ điều kiện nhận quà, hãy bấm các nút bên dưới để nhận ngay quà của bạn:",
                    buttons=[
                        [Button.url("🚀 MỞ APP NHẬN LOCKET GOLD FREE", LOCKET_APP_LINK)],
                        [Button.url("🎨 THAM GIA GIA ĐÌNH CANVA PRO EDU", CANVA_INVITE_LINK)],
                        [Button.inline("⬅️ Về Menu Chính", b"menu_main")]
                    ]
                )
                return

            if db.is_user_already_linked(referrer["id"]):
                await event.respond(
                    "⚠️ **Mã kết nối này đã được một người khác sử dụng trước đó!**\n\n"
                    "Mỗi mã chỉ có hiệu lực ghép nối 1-1 cho 2 tài khoản duy nhất. "
                    "Vui lòng xin mã của một người bạn khác hoặc dùng tài khoản clone khác nhé!"
                )
                return

            # 4. Đảm bảo tài khoản người nhập mã đã có trong DB trước khi liên kết
            db.get_or_create_user(user_id, getattr(sender, 'username', None), getattr(sender, 'first_name', None))

            # 5. Thực hiện liên kết 2 chiều
            linked = db.link_referral_mutual(user_id, referrer["id"])
            if linked:
                # Gửi thông báo thành công cho người nhập mã kèm cả 2 nút nhận quà
                success_text_sender = (
                    "🎉 **KẾT NỐI BẠN BÈ THÀNH CÔNG RỰC RỠ!**\n\n"
                    f"✅ Hệ thống đã tự động liên kết tài khoản của bạn với người bạn (`Mã: {clean_code}`).\n"
                    f"✨ Cả 2 bạn đều đã hoàn thành nhiệm vụ và đủ điều kiện nhận CẢ HAI món quà:\n"
                    f"• 🎁 **Locket Gold Free 0đ**\n"
                    f"• 🎨 **Canva Pro Edu Free 0đ (Gia đình)**\n\n"
                    f"👇 Bấm các nút bên dưới để nhận ngay quà của bạn:"
                )
                sender_buttons = [
                    [Button.url("🚀 MỞ APP NHẬN LOCKET GOLD FREE", LOCKET_APP_LINK)],
                    [Button.url("🎨 THAM GIA GIA ĐÌNH CANVA PRO EDU", CANVA_INVITE_LINK)],
                    [Button.inline("⬅️ Về Menu Chính", b"menu_main")]
                ]
                await event.respond(success_text_sender, buttons=sender_buttons)

                # Gửi thông báo trực tiếp cho người chủ mã kèm cả 2 nút nhận quà
                try:
                    ref_text_notify = (
                        "🎉 **BẠN BÈ ĐÃ KẾT NỐI THÀNH CÔNG!**\n\n"
                        f"✅ Người bạn của bạn (@{sender_name}) vừa nhập mã kết nối của bạn và hoàn thành điều kiện.\n"
                        f"✨ Cả hai tài khoản đã được liên kết thành công! Bây giờ bạn có thể nhận ngay quà tặng:\n"
                        f"• 🎁 **Locket Gold Free 0đ**\n"
                        f"• 🎨 **Canva Pro Edu Free 0đ (Gia đình)**\n\n"
                        f"👇 Bấm các nút bên dưới để nhận quà ngay lập tức:"
                    )
                    ref_buttons = [
                        [Button.url("🚀 MỞ APP NHẬN LOCKET GOLD FREE", LOCKET_APP_LINK)],
                        [Button.url("🎨 THAM GIA GIA ĐÌNH CANVA PRO EDU", CANVA_INVITE_LINK)],
                        [Button.inline("⬅️ Về Menu Chính", b"menu_main")]
                    ]
                    await client.send_message(referrer["id"], ref_text_notify, buttons=ref_buttons)
                except Exception as e:
                    logger.warning(f"Không thể gửi tin nhắn thông báo kết nối tới {referrer['id']}: {e}")

                # Báo cho Admin biết
                for aid in ADMIN_IDS:
                    try:
                        await client.send_message(
                            aid,
                            f"🎁 **KẾT NỐI GIỚI THIỆU THÀNH CÔNG (MÃ 8 KÝ TỰ):**\n"
                            f"• Người nhập mã: @{sender_name} (`{user_id}`)\n"
                            f"• Chủ mã: @{referrer.get('username') or referrer.get('first_name')} (`{referrer['id']}`)\n"
                            f"• Mã: `{clean_code}`\n"
                            f"• Thời gian: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                        )
                    except Exception:
                        pass
                return
            else:
                # Trường hợp hiếm: đã pass hết check ở trên nhưng vẫn fail (race condition...)
                await event.respond(
                    "⚠️ **Liên kết thất bại!**\n\n"
                    "Có lỗi xảy ra trong quá trình liên kết tài khoản. "
                    "Vui lòng thử lại hoặc liên hệ Admin để được hỗ trợ."
                )
                return
        else:
            await event.respond(
                f"⚠️ **Không tìm thấy mã kết nối `{clean_code}` trong hệ thống!**\n\n"
                "👉 Vui lòng kiểm tra lại chính xác 8 ký tự mã được bạn bè gửi nhé."
            )
            return

    if event.raw_text.startswith("/"):
        return

    user_id = event.sender_id
    state = user_states.get(user_id)
    if not state:
        return

    # Kiểm tra hết hạn timeout nhập liệu (3 phút)
    if time.time() > state.get("expires_at", 0):
        user_states.pop(user_id, None)
        await event.respond("⏰ Đã hết thời gian thao tác (3 phút). Vui lòng chọn lại dịch vụ để bắt đầu lại nhé!")
        return

    step = state.get("step")

    # XỬ LÝ NHẬP USERNAME / ID BẠN BÈ ĐỂ NHẬN LOCKET GOLD FREE
    if step == "waiting_referral_username":
        referral_query = event.raw_text.strip()
        user_states.pop(user_id, None)

        # 1. Không được tự nhập username/ID của chính mình
        sender = await event.get_sender()
        my_username = (sender.username or "").lower()
        clean_input = referral_query.lstrip("@").lower()

        if clean_input == str(user_id) or (my_username and clean_input == my_username):
            await event.respond(
                "❌ **Không hợp lệ:** Bạn không thể tự nhập tài khoản của chính mình!\n"
                "👉 Hãy nhờ bạn bè hoặc dùng 1 tài khoản clone khác để mời nhé.",
                buttons=[[Button.inline("🔄 Thử Lại", b"enter_referral_friend")], [Button.inline("⬅️ Về Menu", b"menu_main")]]
            )
            return

        # 2. Tìm người bạn này trong hệ thống bot (họ phải bấm /start bot trước)
        friend = db.find_user_by_username_or_id(referral_query)
        if not friend:
            await event.respond(
                f"⚠️ **Không tìm thấy tài khoản `{referral_query}` trong hệ thống bot!**\n\n"
                "📌 **Nguyên nhân:** Người bạn này chưa từng bấm `/start` tương tác với bot.\n"
                "👉 **Cách giải quyết:** Hãy gửi link bot cho bạn bè (hoặc tài khoản clone) của bạn, bấm `/start` rồi vào đây nhập lại nhé!",
                buttons=[[Button.inline("🔄 Thử Lại", b"enter_referral_friend")], [Button.inline("⬅️ Về Menu", b"menu_main")]]
            )
            return

        friend_id = friend["id"]
        friend_name = friend.get("username") or friend.get("first_name") or str(friend_id)

        # 3. Kiểm tra xem người bạn này đã từng được ai điền trước đó chưa (Chống gian lận 1 người dùng cho nhiều nick)
        if db.is_friend_already_used_as_referral(friend_id):
            await event.respond(
                f"❌ **Tài khoản @{friend_name} đã được người khác sử dụng để nhận thưởng trước đó!**\n\n"
                "⚠️ Hệ thống quy định mỗi tài khoản giới thiệu chỉ được tính điểm cho 1 người duy nhất để đảm bảo công bằng.\n"
                "👉 Vui lòng giới thiệu một người bạn khác hoặc dùng tài khoản clone khác.",
                buttons=[[Button.inline("🔄 Thử Tài Khoản Khác", b"enter_referral_friend")], [Button.inline("⬅️ Về Menu", b"menu_main")]]
            )
            return

        # 4. Kiểm tra xem người bạn này đã tham gia nhóm cộng đồng chưa
        friend_in_group = await check_user_in_group(friend_id)
        if not friend_in_group:
            await event.respond(
                f"⚠️ **Tài khoản @{friend_name} CHƯA tham gia nhóm cộng đồng của shop!**\n\n"
                "👉 Hãy nhắc người bạn đó bấm vào link nhóm cộng đồng và tham gia nhóm, sau đó bạn quay lại đây quét lại nhé!",
                buttons=[
                    [Button.url("👉 Link Nhóm Cộng Đồng", GROUP_INVITE_LINK)],
                    [Button.inline("🔄 Thử Lại", b"enter_referral_friend")],
                    [Button.inline("⬅️ Về Menu", b"menu_main")]
                ]
            )
            return

        # 5. Tất cả điều kiện ĐÃ THỎA MÃN -> Lưu vào cơ sở dữ liệu vĩnh viễn
        db.set_user_referral_success(user_id, friend_id)

        # Thông báo thành công và hiển thị nút mở app
        congrat_text = (
            "🎉 **XÁC MINH GIỚI THIỆU THÀNH CÔNG RỰC RỠ!**\n\n"
            f"✅ Hệ thống đã xác nhận tài khoản bạn bè: **@{friend_name}** (`ID: {friend_id}`).\n"
            "✨ Bạn đã đủ 100% điều kiện để nhận CẢ HAI món quà:\n"
            "• 🎁 **Locket Gold Free 0đ**\n"
            "• 🎨 **Canva Pro Edu Free 0đ (Gia đình)**\n\n"
            "👇 Bấm các nút bên dưới để nhận ngay quà của bạn:"
        )
        buttons = [
            [Button.url("🚀 MỞ APP NHẬN LOCKET GOLD FREE", LOCKET_APP_LINK)],
            [Button.url("🎨 THAM GIA GIA ĐÌNH CANVA PRO EDU", CANVA_INVITE_LINK)],
            [Button.inline("⬅️ Quay Lại Menu Chính", b"menu_main")]
        ]
        await event.respond(congrat_text, buttons=buttons)

        # Gửi thông báo cho Admin biết có lượt giới thiệu mới hợp lệ
        for aid in ADMIN_IDS:
            try:
                await client.send_message(
                    aid,
                    f"🎁 **THÀNH VIÊN HOÀN THÀNH MỜI BẠN BÈ (LOCKET FREE):**\n"
                    f"• Người nhận: @{sender.username or ''} (`{user_id}`)\n"
                    f"• Người được mời: @{friend_name} (`{friend_id}`)\n"
                    f"• Thời gian: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                )
            except Exception:
                pass
        return

    # Xử lý nhập thông tin khách hàng cho đơn hàng
    if step == "waiting_input":
        customer_info = event.raw_text.strip()
        if len(customer_info) < 2:
            await event.respond("⚠️ Thông tin bạn nhập quá ngắn. Vui lòng nhập đúng Email hoặc Username nhận dịch vụ:")
            return

        prod_id = state.get("product_id")
        prod = get_product_by_id(prod_id)
        user_states.pop(user_id, None)

        if not prod:
            await event.respond("⚠️ Sản phẩm không tồn tại, vui lòng thử lại!")
            return

        sender = await event.get_sender()
        username = sender.username or ""

        # TRƯỜNG HỢP 1: SẢN PHẨM MIỄN PHÍ 0Đ (LOCKET GOLD FREE)
        if prod["price"] == 0:
            order = db.create_order(
                user_id=user_id,
                username=username,
                product=prod,
                customer_info=customer_info,
                payment_type="free"
            )

            # Thông báo cho khách hàng
            success_msg = (
                f"🎉 **ĐĂNG KÝ NHẬN LOCKET GOLD FREE THÀNH CÔNG!**\n\n"
                f"• **Mã đơn:** `#{order['order_id']}`\n"
                f"• **Dịch vụ:** **{prod['name']}**\n"
                f"• **Thông tin nhận:** `{customer_info}`\n"
                f"• **Chi phí:** `0 VNĐ (MIỄN PHÍ)`\n\n"
                f"⚡ Thông tin của bạn đã được chuyển tới Admin để kích hoạt.\n"
                f"Bạn sẽ nhận được tin nhắn thông báo ngay sau khi hoàn tất!"
            )
            await event.respond(success_msg, buttons=get_main_menu_buttons(user_id))

            # Thông báo ngay cho toàn bộ Admin
            admin_alert = (
                f"🎁 **[ĐƠN HÀNG 0Đ] KHÁCH NHẬN LOCKET GOLD FREE!**\n\n"
                f"• **Khách hàng:** @{username} (ID: `{user_id}`)\n"
                f"• **Mã đơn:** `#{order['order_id']}`\n"
                f"• **Dịch vụ:** {prod['name']}\n"
                f"• **Thông tin khách:** `{customer_info}`\n"
                f"• **Thời gian:** {order['created_at']}\n\n"
                f"👉 Bấm nút bên dưới sau khi bạn đã kích hoạt xong cho khách:"
            )
            deliver_btn = [[Button.inline("✅ Đã Bàn Giao Quà", f"admin_deliver_{order['order_id']}".encode())]]
            for aid in ADMIN_IDS:
                try:
                    await client.send_message(aid, admin_alert, buttons=deliver_btn)
                except Exception as e:
                    logger.error(f"Lỗi gửi thông báo admin {aid}: {e}")
            return

        # TRƯỜNG HỢP 2: SẢN PHẨM CÓ PHÍ (LOCKET 80K, CANVA 40K, ADMIN CANVA 120K, GEMINI 200K)
        pay_order_code = payos_service.generate_order_code()
        desc = f"DH{pay_order_code}"

        # Tạo yêu cầu thanh toán qua PayOS (hoặc VietQR dự phòng)
        payment_res = payos_service.create_payment_request(
            order_code=pay_order_code,
            amount=prod["price"],
            description=desc,
            buyer_name=username or f"user_{user_id}"
        )

        order = db.create_order(
            user_id=user_id,
            username=username,
            product=prod,
            customer_info=customer_info,
            payos_order_code=pay_order_code,
            payment_type=payment_res["type"]
        )

        # Tạo ảnh QR VietQR
        qr_buf = payos_service.generate_qr_image_bytes(
            qr_payload=payment_res.get("qr_code"),
            bank_bin=payment_res.get("bin"),
            account_no=payment_res.get("account_number"),
            amount=prod["price"],
            description=desc
        )

        bill_caption = (
            f"💳 **HOÁ ĐƠN THANH TOÁN ĐƠN HÀNG #{order['order_id']}**\n\n"
            f"📦 **Sản phẩm:** {prod['name']}\n"
            f"💰 **Số tiền cần thanh toán:** `{format_money(prod['price'])}`\n"
            f"📝 **Thông tin nhận:** `{customer_info}`\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🏦 **THÔNG TIN CHUYỂN KHOẢN:**\n"
            f"• **Ngân hàng:** `{payment_res.get('bin', 'MB')}`\n"
            f"• **Số tài khoản:** `{payment_res.get('account_number')}`\n"
            f"• **Chủ tài khoản:** `{payment_res.get('account_name')}`\n"
            f"• **Số tiền chính xác:** `{format_money(prod['price'])}`\n"
            f"• **Nội dung chuyển khoản:** `{desc}`\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"⏳ _Mã QR VietQR tự động xác nhận trong 10 phút. Ngay khi chuyển khoản thành công hệ thống sẽ ghi nhận tức thì!_"
        )

        pay_buttons = []
        if payment_res.get("checkout_url"):
            pay_buttons.append([Button.url("🌐 Mở Trang Thanh Toán PayOS", payment_res["checkout_url"])])
        pay_buttons.append([
            Button.inline("🔄 Kiểm Tra Thanh Toán", f"check_pay_{order['order_id']}_{pay_order_code}".encode()),
            Button.inline("❌ Hủy Đơn Hàng", b"cancel_order")
        ])

        sent_msg = await client.send_file(
            user_id,
            file=qr_buf,
            caption=bill_caption,
            buttons=pay_buttons
        )

        # Chạy tác vụ nền tự động kiểm tra giao dịch PayOS
        task = asyncio.create_task(
            poll_payos_payment(
                user_id=user_id,
                order_id=order["order_id"],
                order_code=pay_order_code,
                product_name=prod["name"],
                amount=prod["price"],
                customer_info=customer_info,
                username=username,
                message_id=sent_msg.id
            )
        )
        active_payment_tasks[order["order_id"]] = task
        return

    # Xử lý Admin gửi thông báo toàn hệ thống (Broadcast)
    if step == "waiting_broadcast" and is_admin(user_id):
        user_states.pop(user_id, None)
        broadcast_text = event.raw_text.strip()
        all_user_ids = db.get_all_user_ids()
        
        status_msg = await event.respond(f"⏳ Đang gửi thông báo tới {len(all_user_ids)} người dùng...")
        success_count = 0
        fail_count = 0

        for uid in all_user_ids:
            try:
                await client.send_message(uid, f"📢 **THÔNG BÁO TỪ SHOP:**\n\n{broadcast_text}")
                success_count += 1
                await asyncio.sleep(0.05) # Giãn cách nhẹ tránh spam rate-limit
            except Exception:
                fail_count += 1

        await status_msg.edit(
            f"✅ **KẾT QUẢ GỬI THÔNG BÁO:**\n\n"
            f"• Thành công: `{success_count}` người\n"
            f"• Thất bại: `{fail_count}` người\n"
            f"• Tổng số: `{len(all_user_ids)}` người"
        )
        return

# ==================== TÁC VỤ NỀN KIỂM TRA THANH TOÁN (POLLING) ====================

async def poll_payos_payment(user_id: int, order_id: str, order_code: int, product_name: str, amount: int, customer_info: str, username: str, message_id: int):
    """Lặp kiểm tra trạng thái thanh toán từ PayOS mỗi 5 giây trong 10 phút"""
    start_time = time.time()
    logger.info(f"Bắt đầu theo dõi thanh toán cho đơn {order_id} (PayOS: {order_code})...")

    while time.time() - start_time < TIMEOUT_PAYMENT_SECONDS:
        await asyncio.sleep(5)
        
        # Kiểm tra xem đơn có bị hủy bởi người dùng hay không
        order = db.get_order(order_id)
        if not order or order.get("status") in ["CANCELLED", "PAID", "COMPLETED"]:
            return

        status = payos_service.check_payment_status(order_code)
        if status == "PAID":
            logger.info(f"Đơn hàng {order_id} đã thanh toán thành công qua PayOS!")
            db.update_order_status(order_id, "PAID")
            await handle_paid_order(user_id, order_id)
            return
        elif status in ["CANCELLED", "EXPIRED"]:
            logger.info(f"Đơn hàng {order_id} bị hủy trên PayOS ({status})")
            db.update_order_status(order_id, "CANCELLED")
            try:
                await client.send_message(user_id, f"❌ Đơn hàng `#{order_id}` đã bị hủy hoặc hết hạn.")
            except Exception:
                pass
            return

    # Quá thời gian 10 phút
    order = db.get_order(order_id)
    if order and order.get("status") == "PENDING":
        db.update_order_status(order_id, "EXPIRED")
        payos_service.cancel_payment(order_code, "Timeout 10m")
        try:
            await client.send_message(
                user_id,
                f"⏰ **ĐƠN HÀNG HẾT HẠN:**\n"
                f"Đơn hàng `#{order_id}` ({product_name}) đã hết hạn thanh toán (10 phút).\n"
                f"Nếu bạn vẫn có nhu cầu, vui lòng tạo đơn mới nhé!"
            )
        except Exception:
            pass

async def handle_paid_order(user_id: int, order_id: str):
    """Xử lý sau khi đơn hàng được thanh toán thành công"""
    order = db.get_order(order_id)
    if not order:
        return

    # 1. Báo khách hàng
    success_msg = (
        f"🎉 **XÁC NHẬN THANH TOÁN THÀNH CÔNG!**\n\n"
        f"• **Mã đơn hàng:** `#{order['order_id']}`\n"
        f"• **Dịch vụ:** **{order['product_name']}**\n"
        f"• **Số tiền:** `{format_money(order['amount'])}`\n"
        f"• **Thông tin kích hoạt:** `{order.get('customer_info')}`\n\n"
        f"⚡ Hệ thống đã nhận được tiền của bạn! Admin đang tiến hành kích hoạt và sẽ bàn giao cho bạn trong ít phút."
    )
    try:
        await client.send_message(user_id, success_msg, buttons=get_main_menu_buttons(user_id))
    except Exception as e:
        logger.error(f"Lỗi gửi tin nhắn cho khách {user_id}: {e}")

    # 2. Báo Admin
    admin_alert = (
        f"💰 **[ĐƠN HÀNG ĐÃ THANH TOÁN THÀNH CÔNG]**\n\n"
        f"• **Khách hàng:** @{order.get('username') or order['user_id']} (ID: `{user_id}`)\n"
        f"• **Mã đơn:** `#{order['order_id']}`\n"
        f"• **Mã PayOS:** `{order.get('payos_order_code')}`\n"
        f"• **Dịch vụ:** **{order['product_name']}**\n"
        f"• **Số tiền:** `{format_money(order['amount'])}`\n"
        f"• **Thông tin khách:** `{order.get('customer_info')}`\n"
        f"• **Thời gian thanh toán:** {order.get('paid_at')}\n\n"
        f"👉 Bấm nút bên dưới để bàn giao dịch vụ cho khách:"
    )
    deliver_btn = [
        [Button.inline("✅ Đã Bàn Giao Dịch Vụ", f"admin_deliver_{order['order_id']}".encode())],
        [Button.url("📩 Nhắn Tin Cho Khách", f"tg://user?id={user_id}")]
    ]
    for aid in ADMIN_IDS:
        try:
            await client.send_message(aid, admin_alert, buttons=deliver_btn)
        except Exception as e:
            logger.error(f"Lỗi gửi thông báo admin {aid}: {e}")

# ==================== ADMIN PANEL & SAO LƯU DỮ LIỆU (BACKUP) ====================

async def show_admin_panel(event, is_callback=False):
    stats = db.get_statistics()
    pending_orders = db.get_pending_delivery_orders()
    pending_support = db.count_pending_support_tickets()

    text = (
        f"👑 **BẢNG ĐIỀU KHIỂN QUẢN TRỊ VIÊN (ADMIN)**\n\n"
        f"📊 **BÁO CÁO DOANH THU & ĐƠN HÀNG:**\n"
        f"• Doanh thu tổng: `{format_money(stats['total_revenue'])}`\n"
        f"• Doanh thu hôm nay: `{format_money(stats['today_revenue'])}`\n"
        f"• Tổng số đơn hàng: `{stats['total_orders']}` (Đã thanh toán: `{stats['paid_orders_count']}`)\n"
        f"• Đơn hàng hôm nay: `{stats['today_orders_count']}` đơn\n"
        f"• Tổng khách hàng: `{stats['total_users']}` người\n"
        f"• ⏳ **Đơn đang chờ bàn giao:** `{len(pending_orders)}` đơn\n"
        f"• 💬 **Khách đang chờ hỗ trợ:** `{pending_support}` người\n\n"
        f"Chọn chức năng quản trị bên dưới:"
    )

    buttons = [
        [Button.inline(f"💬 Yêu Cầu Hỗ Trợ ({pending_support} chờ duyệt)", b"admin_support_list")],
        [Button.inline(f"📋 Xem Đơn Chờ Bàn Giao ({len(pending_orders)})", b"admin_pending_orders")],
        [
            Button.inline("💾 Sao Lưu Dữ Liệu (/backup)", b"admin_backup"),
            Button.inline("📢 Gửi Thông Báo (Broadcast)", b"admin_broadcast")
        ],
        [Button.inline("🔄 Làm Mới Thống Kê", b"admin_panel")]
    ]

    if is_callback:
        try:
            await event.edit(text, buttons=buttons)
        except MessageNotModifiedError:
            pass
    else:
        await event.respond(text, buttons=buttons)

async def perform_backup_to_chat(chat_id: int):
    """Gửi trực tiếp file db.json về chat theo yêu cầu bảo toàn dữ liệu"""
    if not os.path.exists("db.json"):
        await client.send_message(chat_id, "⚠️ Không tìm thấy file db.json để sao lưu!")
        return

    try:
        file_size = os.path.getsize("db.json")
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        stats = db.get_statistics()
        
        caption = (
            f"💾 **BẢN SAO LƯU DỮ LIỆU TỰ ĐỘNG (BACKUP)**\n\n"
            f"• **Thời gian:** `{now_str}`\n"
            f"• **Dung lượng file:** `{file_size} bytes` (~{file_size/1024:.2f} KB)\n"
            f"• **Tổng người dùng:** `{stats['total_users']}`\n"
            f"• **Tổng đơn hàng:** `{stats['total_orders']}`\n"
            f"• **Doanh thu tích lũy:** `{format_money(stats['total_revenue'])}`\n\n"
            f"🛡️ Dữ liệu được lưu trữ an toàn chống mất mát khi VPS gặp sự cố."
        )
        await client.send_file(chat_id, file="db.json", caption=caption)
        logger.info(f"Đã gửi file backup thành công tới chat {chat_id}")
    except Exception as e:
        logger.error(f"Lỗi khi gửi backup: {e}")
        await client.send_message(chat_id, f"❌ Lỗi khi gửi file backup: {e}")

async def auto_backup_task():
    """Tác vụ chạy ngầm tự động gửi backup mỗi 12 tiếng tới tất cả Admin"""
    logger.info(f"Tác vụ tự động sao lưu định kỳ đã kích hoạt (chu kỳ {BACKUP_INTERVAL_HOURS} tiếng)!")
    while True:
        try:
            await asyncio.sleep(BACKUP_INTERVAL_HOURS * 3600)
            logger.info("Bắt đầu chu kỳ tự động sao lưu dữ liệu...")
            for aid in ADMIN_IDS:
                await perform_backup_to_chat(aid)
        except Exception as e:
            logger.error(f"Lỗi trong auto_backup_task: {e}")
            await asyncio.sleep(60)

# ==================== WEB HEALTH CHECK CHO RENDER (0 ĐỒNG / THÁNG) ====================

async def start_web_server():
    """Server HTTP siêu nhẹ để Render nhận diện Web Service và nhận ping giữ bot không ngủ"""
    port = int(os.getenv("PORT", 8080))
    async def handle_client(reader, writer):
        data = await reader.read(1024)
        response = (
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: text/plain; charset=utf-8\r\n"
            "Connection: close\r\n\r\n"
            "Shop Bot Telegram is running 24/7!"
        )
        writer.write(response.encode("utf-8"))
        await writer.drain()
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass

    server = await asyncio.start_server(handle_client, "0.0.0.0", port)
    logger.info(f"Đã mở Web Server sức khoẻ tại port {port} (Sẵn sàng chạy Render Free 0$)")
    return server

# ==================== ĐIỂM BẮT ĐẦU CHƯƠNG TRÌNH ====================

async def main():
    logger.info("Đang khởi động Telegram Shop Bot...")
    # Chạy Web Server cho Render song song với Bot Telegram
    await start_web_server()

    await client.start(bot_token=BOT_TOKEN)
    me = await client.get_me()
    logger.info(f"Bot đã online thành công: @{me.username} ({me.first_name})")

    # Kích hoạt background auto backup
    asyncio.create_task(auto_backup_task())

    # Chạy giữ bot online
    await client.run_until_disconnected()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot đã dừng bởi người dùng.")
    except Exception as e:
        logger.error(f"Lỗi dừng bot đột ngột: {e}")

