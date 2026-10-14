import os
import sys
import io
import time
import asyncio
from datetime import datetime
from telethon import TelegramClient, events, Button
from telethon.tl.types import ReplyKeyboardMarkup, KeyboardButtonRow, KeyboardButton
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

def get_main_menu_buttons(user_id: int):
    buttons = [
        # Nút WebApp mở trực tiếp cửa sổ Mini App Nghiện Trick trên Telegram
        [KeyboardButtonWebView("🎁 NHẬN LOCKET GOLD FREE (0Đ)", "https://nghientrick.com/privacy.html")],
        [
            Button.inline("🛍️ Bảng Giá Sản Phẩm", b"menu_products"),
            Button.inline("📋 Đơn Hàng Của Tôi", b"my_orders")
        ],
        [
            Button.inline("💬 Hỗ Trợ Khách Hàng", b"contact_support"),
            Button.inline("📜 Hướng Dẫn Mua", b"guide")
        ]
    ]
    if is_admin(user_id):
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
    """Bàn phím Menu cố định dưới thanh nhập tin nhắn được thu nhỏ gọn gàng (resize=True)"""
    kb_rows = [
        KeyboardButtonRow([
            KeyboardButton("🎁 Nhận Locket Free 0đ"),
            KeyboardButton("🛍️ Bảng Giá Sản Phẩm")
        ]),
        KeyboardButtonRow([
            KeyboardButton("📋 Đơn Hàng Của Tôi"),
            KeyboardButton("💬 Hỗ Trợ 24/7")
        ])
    ]
    if is_admin(user_id):
        kb_rows.append(KeyboardButtonRow([
            KeyboardButton("👑 Bảng Điều Khiển Admin")
        ]))
    return ReplyKeyboardMarkup(rows=kb_rows, resize=True)

# ==================== CÁC SỰ KIỆN LỆNH TELEGRAM & NÚT BÀN PHÍM DƯỚI ====================

@client.on(events.NewMessage(pattern=r"^/start"))
async def start_handler(event):
    sender = await event.get_sender()
    user_id = sender.id
    username = sender.username or ""
    first_name = sender.first_name or "Khách hàng"

    # Lưu thông tin khách hàng
    db.get_or_create_user(user_id, username, first_name)
    user_states.pop(user_id, None)

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
        f"👇 _Bạn có thể bấm vào Menu bên dưới hoặc các nút chọn nhanh:_"
    )

    # Gửi duy nhất 1 tin nhắn chào mừng kèm nút chọn nhanh
    await event.respond(welcome_text, buttons=get_main_menu_buttons(user_id))

@client.on(events.NewMessage(pattern=r"^(/products|🛍️ Bảng Giá Sản Phẩm)$"))
async def products_command_handler(event):
    text = (
        "🛍️ **BẢNG GIÁ DỊCH VỤ BẢN QUYỀN CHÍNH HÃNG**\n\n"
        "1. 🎁 **Locket Gold Miễn Phí:** `0 VNĐ`\n"
        "2. 💛 **Locket Gold 2 Năm:** `80.000 VNĐ`\n"
        "3. 🎨 **Canva Pro Edu 12 Tháng:** `40.000 VNĐ`\n"
        "4. 👑 **Admin Canva Pro Edu 2 Năm:** `120.000 VNĐ`\n"
        "5. 🤖 **Gemini Pro 18 Tháng:** `200.000 VNĐ`\n\n"
        "👇 Bấm vào từng sản phẩm dưới đây để xem chi tiết & đặt mua:"
    )
    await event.respond(text, buttons=get_products_menu_buttons())

@client.on(events.NewMessage(pattern=r"^(/free|🎁 Nhận Locket Free 0đ)$"))
async def free_command_handler(event):
    sender = await event.get_sender()
    user_id = sender.id
    prod = get_product_by_id("locket_free")
    if not prod:
        await event.respond("⚠️ Gói khuyến mãi tạm thời chưa sẵn sàng.")
        return

    if db.has_claimed_free(user_id, prod["id"]):
        await event.respond(
            "⚠️ **Bạn đã nhận gói Locket Gold Miễn Phí rồi!**\n"
            "Mỗi khách hàng chỉ được nhận 1 lần. Bạn có thể tham khảo gói Locket Gold 2 Năm chính chủ nhé!",
            buttons=get_products_menu_buttons()
        )
        return

    user_states[user_id] = {
        "step": "waiting_input",
        "product_id": "locket_free",
        "expires_at": time.time() + TIMEOUT_INPUT_SECONDS
    }

    prompt_text = (
        f"📝 **BƯỚC ĐẶT HÀNG: {prod['name']}**\n\n"
        f"💰 **Giá thanh toán:** `0 VNĐ (MIỄN PHÍ)`\n"
        f"👉 **Yêu cầu:** {prod.get('input_prompt', 'Vui lòng nhập Email hoặc Username Locket của bạn:')}\n\n"
        f"⏱️ _Thời gian thao tác: {TIMEOUT_INPUT_SECONDS // 60} phút. Vui lòng gửi tin nhắn trả lời trực tiếp bên dưới!_"
    )
    await event.respond(prompt_text, buttons=[[Button.inline("❌ Hủy Bỏ", b"cancel_order")]])

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

@client.on(events.NewMessage(pattern=r"^(/support|💬 Hỗ Trợ 24/7|/help)$"))
async def support_command_handler(event):
    text = (
        "💬 **HỖ TRỢ KHÁCH HÀNG 24/7**\n\n"
        "Nếu bạn cần tư vấn, gặp sự cố thanh toán hoặc bảo hành dịch vụ, xin vui lòng:\n\n"
        f"• **Nhắn tin trực tiếp với Admin:** [Liên Hệ Admin](tg://user?id={ADMIN_IDS[0] if ADMIN_IDS else ''})\n"
        f"• **Telegram ID Admin:** `{ADMIN_IDS[0] if ADMIN_IDS else ''}`\n\n"
        "Đội ngũ hỗ trợ sẽ phản hồi bạn trong thời gian sớm nhất!"
    )
    buttons = [[Button.inline("⬅️ Quay Lại", b"menu_main")]]
    await event.respond(text, buttons=buttons)

@client.on(events.NewMessage(pattern=r"^(/admin|👑 Bảng Điều Khiển Admin)$"))
async def admin_command_handler(event):
    user_id = event.sender_id
    if not is_admin(user_id):
        await event.respond("⛔ Bạn không có quyền truy cập bảng quản trị!")
        return
    await show_admin_panel(event, is_callback=False)

@client.on(events.NewMessage(pattern=r"^/backup"))
async def backup_command_handler(event):
    user_id = event.sender_id
    if not is_admin(user_id):
        await event.respond("⛔ Bạn không có quyền gọi lệnh backup!")
        return
    await perform_backup_to_chat(event.chat_id)

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
            "2. 💛 **Locket Gold 2 Năm:** `80.000 VNĐ`\n"
            "3. 🎨 **Canva Pro Edu 12 Tháng:** `40.000 VNĐ`\n"
            "4. 👑 **Admin Canva Pro Edu 2 Năm:** `120.000 VNĐ`\n"
            "5. 🤖 **Gemini Pro 18 Tháng:** `200.000 VNĐ`\n\n"
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
            action_btn = KeyboardButtonWebView("🎁 Mở App Nhận Locket Gold Miễn Phí (0đ)", "https://nghientrick.com/privacy.html")
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
        admin_contact = f"@{ADMIN_IDS[0]}" if ADMIN_IDS else "Admin"
        text = (
            "💬 **HỖ TRỢ KHÁCH HÀNG 24/7**\n\n"
            "Nếu bạn cần tư vấn, gặp sự cố thanh toán hoặc bảo hành dịch vụ, xin vui lòng:\n\n"
            f"• **Nhắn tin trực tiếp với Admin:** [Liên Hệ Admin](tg://user?id={ADMIN_IDS[0] if ADMIN_IDS else ''})\n"
            f"• **Telegram ID:** `{ADMIN_IDS[0] if ADMIN_IDS else ''}`\n\n"
            "Đội ngũ hỗ trợ sẽ phản hồi bạn trong thời gian sớm nhất!"
        )
        buttons = [[Button.inline("⬅️ Quay Lại", b"menu_main")]]
        try:
            await event.edit(text, buttons=buttons)
        except MessageNotModifiedError:
            pass
        await event.answer()
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
        order = db.get_order(order_id)
        if not order:
            await event.answer("Đơn hàng không tồn tại!", alert=True)
            return

        db.update_order_status(order_id, "COMPLETED")
        await event.answer("✅ Đã cập nhật trạng thái bàn giao!", alert=True)
        
        # Báo cho Admin biết
        try:
            await event.edit(
                f"✅ **ĐƠN HÀNG #{order_id} ĐÃ BÀN GIAO THÀNH CÔNG!**\n"
                f"• Khách: {order.get('username') or order.get('user_id')}\n"
                f"• Dịch vụ: {order.get('product_name')}\n"
                f"• Thông tin: `{order.get('customer_info')}`\n"
                f"• Thời gian bàn giao: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
        except Exception:
            pass

        # Gửi tin nhắn kích hoạt thành công tới khách hàng
        try:
            cust_text = (
                f"🎉 **DỊCH VỤ CỦA BẠN ĐÃ ĐƯỢC KÍCH HOẠT THÀNH CÔNG!**\n\n"
                f"• **Mã đơn hàng:** `#{order_id}`\n"
                f"• **Dịch vụ:** **{order.get('product_name')}**\n"
                f"• **Thông tin kích hoạt:** `{order.get('customer_info')}`\n\n"
                f"✨ Cảm ơn bạn đã tin tưởng sử dụng dịch vụ của shop! Nếu có bất kỳ thắc mắc hoặc cần bảo hành, hãy liên hệ ngay với shop nhé! ❤️"
            )
            await client.send_message(order["user_id"], cust_text)
        except Exception as e:
            logger.error(f"Không thể gửi tin nhắn cho khách {order['user_id']}: {e}")
        return

    # 11. Admin Panel
    if data == "admin_panel":
        if not is_admin(user_id):
            await event.answer("⛔ Không có quyền!", alert=True)
            return
        await show_admin_panel(event, is_callback=True)
        await event.answer()
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
    if event.raw_text.startswith("/"):
        # Lệnh nhanh bàn giao: /deliver_DH12345678
        if event.raw_text.startswith("/deliver_") and is_admin(event.sender_id):
            order_id = event.raw_text.replace("/deliver_", "").strip()
            order = db.get_order(order_id)
            if order:
                db.update_order_status(order_id, "COMPLETED")
                await event.respond(f"✅ Đã xác nhận bàn giao đơn hàng #{order_id} thành công!")
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
            else:
                await event.respond(f"⚠️ Không tìm thấy đơn hàng {order_id}!")
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
    pending = db.get_pending_delivery_orders()

    text = (
        f"👑 **BẢNG ĐIỀU KHIỂN QUẢN TRỊ VIÊN (ADMIN)**\n\n"
        f"📊 **BÁO CÁO DOANH THU & ĐƠN HÀNG:**\n"
        f"• Doanh thu tổng: `{format_money(stats['total_revenue'])}`\n"
        f"• Doanh thu hôm nay: `{format_money(stats['today_revenue'])}`\n"
        f"• Tổng số đơn hàng: `{stats['total_orders']}` (Đã thanh toán: `{stats['paid_orders_count']}`)\n"
        f"• Đơn hàng hôm nay: `{stats['today_orders_count']}` đơn\n"
        f"• Tổng khách hàng: `{stats['total_users']}` người\n"
        f"• ⏳ **Đơn đang chờ bàn giao:** `{len(pending)}` đơn\n\n"
        f"Chọn chức năng quản trị bên dưới:"
    )

    buttons = [
        [Button.inline("📋 Xem Đơn Chờ Bàn Giao", b"admin_pending_orders")],
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

