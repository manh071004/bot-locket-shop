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


async def get_store_by_code(code: str) -> Optional[Dict[str, Any]]:
    """Lấy thông tin cửa hàng theo Mã Định Danh 4 số ngẫu nhiên."""
    clean_code = (code or "").strip()
    try:
        with get_sqlite_conn() as conn:
            cur = conn.cursor()
            row = cur.execute(
                "SELECT * FROM store_configs WHERE store_code = ? AND is_active = 1",
                (clean_code,)
            ).fetchone()
            return dict(row) if row else None
    except Exception as e:
        print(f"[!] get_store_by_code error: {e}")
        return None


async def get_customer_lock(telegram_id: int) -> Optional[Dict[str, Any]]:
    """
    Kiểm tra xem khách hàng này đã bị gắn chết với cửa hàng nào chưa.
    Nếu cửa hàng đó bị xóa hoặc bị tắt (is_active = 0), tự động gỡ khóa để khách tự do!
    """
    try:
        with get_sqlite_conn() as conn:
            cur = conn.cursor()
            row = cur.execute(
                """SELECT c.*, s.store_name, s.store_slug, s.store_code, s.is_active
                   FROM customer_locks c
                   LEFT JOIN store_configs s ON s.id = c.store_id
                   WHERE c.telegram_id = ?""",
                (telegram_id,)
            ).fetchone()

            if not row:
                return None

            data = dict(row)
            # Nếu cửa hàng bị xóa hoặc tắt (is_active != 1) -> Gỡ khóa ngay
            if not data.get("is_active"):
                cur.execute("DELETE FROM customer_locks WHERE telegram_id = ?", (telegram_id,))
                conn.commit()
                return None

            return data
    except Exception as e:
        print(f"[!] get_customer_lock error: {e}")
        return None


async def set_customer_lock(telegram_id: int, store_id: int, store_slug: str):
    """Gắn chết khách hàng với cửa hàng này mãi mãi (không được đổi cửa hàng)."""
    try:
        with get_sqlite_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO customer_locks (telegram_id, store_id, store_slug, locked_at)
                   VALUES (?, ?, ?, datetime('now'))
                   ON CONFLICT(telegram_id) DO UPDATE SET
                   store_id = excluded.store_id,
                   store_slug = excluded.store_slug,
                   locked_at = excluded.locked_at""",
                (telegram_id, store_id, store_slug)
            )
            conn.commit()
    except Exception as e:
        print(f"[!] set_customer_lock error: {e}")


async def remove_customer_lock(telegram_id: int):
    """Gỡ khóa khách hàng khi shop bị xóa."""
    try:
        with get_sqlite_conn() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM customer_locks WHERE telegram_id = ?", (telegram_id,))
            conn.commit()
    except Exception as e:
        print(f"[!] remove_customer_lock error: {e}")


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


async def is_admin_telegram_id(telegram_id: int) -> bool:
    """Kiểm tra telegram_id có phải admin tối cao trong database không."""
    try:
        with get_sqlite_conn() as conn:
            cur = conn.cursor()
            row = cur.execute(
                "SELECT id FROM users WHERE telegram_id = ? AND is_admin = 1",
                (telegram_id,)
            ).fetchone()
            return bool(row)
    except Exception:
        return False


async def get_all_stores_for_admin() -> List[Dict[str, Any]]:
    """Lấy danh sách tất cả cửa hàng trong hệ thống cho Admin kiểm soát."""
    try:
        with get_sqlite_conn() as conn:
            cur = conn.cursor()
            rows = cur.execute(
                """SELECT s.*, u.email as owner_email, u.full_name as owner_name, u.plan as owner_plan,
                   (SELECT COUNT(*) FROM products p WHERE p.store_id = s.id) as product_count,
                   (SELECT COUNT(*) FROM customer_locks c WHERE c.store_id = s.id) as locked_customers_count
                   FROM store_configs s
                   LEFT JOIN users u ON u.id = s.user_id
                   ORDER BY s.id DESC"""
            ).fetchall()
            return [dict(r) for r in rows]
    except Exception as e:
        print(f"[!] get_all_stores_for_admin error: {e}")
        return []


async def toggle_store_active_db(store_id: int) -> Optional[Dict[str, Any]]:
    """Bật/Tắt hoạt động của cửa hàng. Nếu tắt, giải phóng tất cả khách hàng bị khóa!"""
    try:
        with get_sqlite_conn() as conn:
            cur = conn.cursor()
            row = cur.execute("SELECT id, store_name, is_active FROM store_configs WHERE id = ?", (store_id,)).fetchone()
            if not row:
                return None
            new_active = 0 if row["is_active"] == 1 else 1
            cur.execute("UPDATE store_configs SET is_active = ? WHERE id = ?", (new_active, store_id))
            freed = 0
            if new_active == 0:
                cur.execute("DELETE FROM customer_locks WHERE store_id = ?", (store_id,))
                freed = cur.rowcount
            conn.commit()
            return {
                "id": store_id,
                "store_name": row["store_name"],
                "is_active": new_active,
                "freed_locks": freed
            }
    except Exception as e:
        print(f"[!] toggle_store_active_db error: {e}")
        return None


async def unlock_all_store_customers_db(store_id: int) -> int:
    """Mở khóa toàn bộ khách hàng đang gắn chết với shop này."""
    try:
        with get_sqlite_conn() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM customer_locks WHERE store_id = ?", (store_id,))
            freed = cur.rowcount
            conn.commit()
            return freed
    except Exception as e:
        print(f"[!] unlock_all_store_customers_db error: {e}")
        return 0


async def regenerate_store_code_db(store_id: int) -> Optional[str]:
    """Cấp lại mã 4 số ngẫu nhiên mới không trùng lặp."""
    import random
    try:
        with get_sqlite_conn() as conn:
            cur = conn.cursor()
            for _ in range(100):
                new_code = str(random.randint(1000, 9999))
                exist = cur.execute("SELECT id FROM store_configs WHERE store_code = ?", (new_code,)).fetchone()
                if not exist:
                    cur.execute("UPDATE store_configs SET store_code = ? WHERE id = ?", (new_code, store_id))
                    conn.commit()
                    return new_code
            fallback = str(random.randint(1000, 9999))
            cur.execute("UPDATE store_configs SET store_code = ? WHERE id = ?", (fallback, store_id))
            conn.commit()
            return fallback
    except Exception as e:
        print(f"[!] regenerate_store_code_db error: {e}")
        return None
