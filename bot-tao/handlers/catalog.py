"""
Catalog handler: Hiển thị danh mục và sản phẩm.
Callback pattern: cat_{store_id}_{category_id}
                  prod_{store_id}_{product_id}
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from db_helper import get_products_by_store, get_product_by_id, get_store_by_slug, get_categories_by_store
from cart_store import add_to_cart, get_user_store


def format_price(price: int) -> str:
    return f"{price:,}đ".replace(",", ".")


async def catalog_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Hiển thị danh sách sản phẩm theo danh mục."""
    query = update.callback_query
    await query.answer()

    # Pattern: cat_{store_id}_{category_id}
    parts = query.data.split("_")
    store_id = int(parts[1])
    category_id = int(parts[2]) if parts[2] != "0" else None

    products = await get_products_by_store(store_id, category_id)

    if not products:
        await query.edit_message_text(
            "😕 Danh mục này chưa có sản phẩm nào!",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🏠 Về trang chủ", callback_data="home")
            ]])
        )
        return

    # Build inline keyboard: 2 sản phẩm / hàng
    keyboard = []
    row = []
    for i, prod in enumerate(products):
        price_text = format_price(prod["price"])
        btn_text = f"{prod['name']} - {price_text}"
        if len(btn_text) > 35:
            btn_text = btn_text[:32] + "..."
        row.append(InlineKeyboardButton(
            btn_text,
            callback_data=f"prod_{store_id}_{prod['id']}"
        ))
        if len(row) == 1 or i == len(products) - 1:
            keyboard.append(row)
            row = []

    keyboard.append([InlineKeyboardButton("🏠 Về trang chủ", callback_data="home")])

    # Lấy tên danh mục
    categories = await get_categories_by_store(store_id)
    cat_name = "Tất cả sản phẩm"
    if category_id:
        for cat in categories:
            if cat["id"] == category_id:
                cat_name = f"{cat['emoji'] or ''} {cat['name']}"
                break

    text = f"📦 <b>{cat_name}</b>\n\n"
    text += f"Có <b>{len(products)}</b> sản phẩm. Chọn sản phẩm để xem chi tiết:"

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def product_detail_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Hiển thị chi tiết sản phẩm với ảnh và nút thêm giỏ."""
    query = update.callback_query
    await query.answer()

    # Pattern: prod_{store_id}_{product_id}
    parts = query.data.split("_")
    store_id = int(parts[1])
    product_id = int(parts[2])

    product = await get_product_by_id(product_id, store_id)
    if not product:
        await query.edit_message_text("❌ Sản phẩm không còn tồn tại!")
        return

    # Xác định nút thêm giỏ
    user = update.effective_user
    slug = get_user_store(user.id)

    stock_text = ""
    if product["stock"] == 0:
        stock_text = "\n⚠️ <b>Hết hàng</b>"
    elif product["stock"] > 0:
        stock_text = f"\n📦 Còn <b>{product['stock']}</b> sản phẩm"

    text = (
        f"🏷️ <b>{product['name']}</b>\n\n"
        f"💰 Giá: <b>{format_price(product['price'])}</b>{stock_text}\n\n"
    )
    if product.get("description"):
        text += f"📝 {product['description']}\n\n"

    keyboard = []
    if product["stock"] != 0:  # Còn hàng
        keyboard.append([
            InlineKeyboardButton("➕ Thêm vào giỏ", callback_data=f"cart_add_{store_id}_{product_id}_{slug}"),
        ])
        keyboard.append([
            InlineKeyboardButton("⚡ Mua ngay", callback_data=f"cart_buynow_{store_id}_{product_id}_{slug}"),
        ])

    keyboard.append([
        InlineKeyboardButton("◀️ Quay lại", callback_data="home"),
        InlineKeyboardButton("🛒 Giỏ hàng", callback_data=f"cart_view_{slug}"),
    ])

    reply_markup = InlineKeyboardMarkup(keyboard)

    # Nếu có ảnh, gửi ảnh + caption
    if product.get("image_url"):
        try:
            await query.message.reply_photo(
                photo=product["image_url"],
                caption=text,
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
            await query.delete_message()
            return
        except Exception:
            pass

    await query.edit_message_text(text, parse_mode="HTML", reply_markup=reply_markup)
