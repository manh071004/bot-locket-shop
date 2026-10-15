"""
DB Helper cho Bot:
Truy vấn dữ liệu thời gian thực từ Database (SQLite botstore.db hoặc PostgreSQL).
Tự động đồng bộ ngay lập tức khi người dùng thêm/sửa sản phẩm, giá bán trên Web Dashboard!
"""
import os
import json
import sqlite3
from typing import Optional, List, Dict, Any

# Tìm đường dẫn botstore.db
def find_sqlite_db_path() -> str:
    candidates = [
        os.getenv("DATABASE_PATH", ""),
        "botstore.db",
        os.path.join(os.path.dirname(__file__), "botstore.db"),
        os.path.join(os.path.dirname(__file__), "..", "backend", "botstore.db"),
        os.path.join(os.path.dirname(__file__), "..", "..", "bot tao bot ban hang", "backend", "botstore.db"),
        "c:/Users/Admin/OneDrive - HUCE/Desktop/Web của Mạnh/server 7 đô render ( 5-2027)/bot tao bot ban hang/backend/botstore.db",
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return os.path.abspath(c)
    return "botstore.db"


DB_FILE = find_sqlite_db_path()


def get_sqlite_conn():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


async def get_store_by_slug(slug: str) -> Optional[Dict[str, Any]]:
    """Lấy thông tin cửa hàng theo slug (deep link key)."""
    try:
        with get_sqlite_conn() as conn:
            cur = conn.cursor()
            row = cur.execute(
                "SELECT * FROM store_configs WHERE store_slug = ? AND is_active = 1",
                (slug,)
            ).fetchone()
            return dict(row) if row else None
    except Exception as e:
        print(f"[!] get_store_by_slug error: {e}")
        return None


async def get_products_by_store(store_id: int, category_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Lấy danh sách sản phẩm theo store_id và danh mục (real-time từ web)."""
    try:
        with get_sqlite_conn() as conn:
            cur = conn.cursor()
            if category_id:
                rows = cur.execute(
                    """SELECT * FROM products
                       WHERE store_id = ? AND category_id = ? AND is_available = 1
                       ORDER BY sort_order, id""",
                    (store_id, category_id)
                ).fetchall()
            else:
                rows = cur.execute(
                    """SELECT * FROM products
                       WHERE store_id = ? AND is_available = 1
                       ORDER BY sort_order, id""",
                    (store_id,)
                ).fetchall()
            return [dict(r) for r in rows]
    except Exception as e:
        print(f"[!] get_products_by_store error: {e}")
        return []


async def get_product_by_id(product_id: int, store_id: int) -> Optional[Dict[str, Any]]:
    """Lấy chi tiết 1 sản phẩm theo ID."""
    try:
        with get_sqlite_conn() as conn:
            cur = conn.cursor()
            row = cur.execute(
                "SELECT * FROM products WHERE id = ? AND store_id = ? AND is_available = 1",
                (product_id, store_id)
            ).fetchone()
            return dict(row) if row else None
    except Exception as e:
        print(f"[!] get_product_by_id error: {e}")
        return None


async def get_categories_by_store(store_id: int) -> List[Dict[str, Any]]:
    """Lấy danh mục sản phẩm của cửa hàng."""
    try:
        with get_sqlite_conn() as conn:
            cur = conn.cursor()
            rows = cur.execute(
                "SELECT * FROM categories WHERE store_id = ? AND is_active = 1 ORDER BY sort_order, id",
                (store_id,)
            ).fetchall()
            return [dict(r) for r in rows]
    except Exception as e:
        print(f"[!] get_categories_by_store error: {e}")
        return []


async def create_order(
    store_id: int,
    order_code: str,
    customer_tg_id: int,
    customer_name: str,
    customer_username: str,
    items: list,
    total_amount: int,
) -> Optional[Dict[str, Any]]:
    """Tạo đơn hàng mới."""
    try:
        with get_sqlite_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO orders
                   (store_id, order_code, customer_tg_id, customer_name, customer_username, items, total_amount, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')""",
                (store_id, order_code, customer_tg_id, customer_name, customer_username, json.dumps(items), total_amount)
            )
            conn.commit()
            row = cur.execute("SELECT * FROM orders WHERE order_code = ?", (order_code,)).fetchone()
            return dict(row) if row else None
    except Exception as e:
        print(f"[!] create_order error: {e}")
        return None


async def get_orders_by_customer(customer_tg_id: int, store_id: int, limit: int = 5) -> List[Dict[str, Any]]:
    """Lấy danh sách đơn hàng của khách."""
    try:
        with get_sqlite_conn() as conn:
            cur = conn.cursor()
            rows = cur.execute(
                """SELECT * FROM orders
                   WHERE customer_tg_id = ? AND store_id = ?
                   ORDER BY created_at DESC LIMIT ?""",
                (customer_tg_id, store_id, limit)
            )
            return [dict(r) for r in rows]
    except Exception as e:
        print(f"[!] get_orders_by_customer error: {e}")
        return []


async def get_owner_telegram_id(store_id: int) -> Optional[int]:
    """Lấy telegram_id của chủ cửa hàng để gửi thông báo."""
    try:
        with get_sqlite_conn() as conn:
            cur = conn.cursor()
            row = cur.execute(
                """SELECT u.telegram_id FROM users u
                   JOIN store_configs s ON s.user_id = u.id
                   WHERE s.id = ?""",
                (store_id,)
            ).fetchone()
            return row["telegram_id"] if row and row["telegram_id"] else None
    except Exception:
        return None
