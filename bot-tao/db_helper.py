import asyncpg
from config import DATABASE_URL
from typing import Optional
import json

_pg_url = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
_pool: Optional[asyncpg.Pool] = None

async def get_pool() -> Optional[asyncpg.Pool]:
    global _pool
    if _pool is None:
        try:
            if not _pg_url.startswith("postgresql"):
                return None
            _pool = await asyncpg.create_pool(_pg_url, min_size=1, max_size=5, timeout=3)
        except Exception:
            _pool = None
    return _pool

async def get_store_by_slug(slug: str) -> Optional[dict]:
    pool = await get_pool()
    if not pool:
        return None
    try:
        row = await pool.fetchrow(
            "SELECT * FROM store_configs WHERE store_slug = $1 AND is_active = true",
            slug
        )
        return dict(row) if row else None
    except Exception:
        return None

async def get_products_by_store(store_id: int, category_id: Optional[int] = None) -> list[dict]:
    pool = await get_pool()
    if not pool:
        return []
    try:
        if category_id:
            rows = await pool.fetch(
                "SELECT * FROM products WHERE store_id = $1 AND category_id = $2 AND is_available = true ORDER BY sort_order, id",
                store_id, category_id
            )
        else:
            rows = await pool.fetch(
                "SELECT * FROM products WHERE store_id = $1 AND is_available = true ORDER BY sort_order, id",
                store_id
            )
        return [dict(r) for r in rows]
    except Exception:
        return []

async def get_product_by_id(product_id: int, store_id: int) -> Optional[dict]:
    pool = await get_pool()
    if not pool:
        return None
    try:
        row = await pool.fetchrow(
            "SELECT * FROM products WHERE id = $1 AND store_id = $2 AND is_available = true",
            product_id, store_id
        )
        return dict(row) if row else None
    except Exception:
        return None

async def get_categories_by_store(store_id: int) -> list[dict]:
    pool = await get_pool()
    if not pool:
        return []
    try:
        rows = await pool.fetch(
            "SELECT * FROM categories WHERE store_id = $1 AND is_active = true ORDER BY sort_order, id",
            store_id
        )
        return [dict(r) for r in rows]
    except Exception:
        return []

async def create_order(store_id: int, order_code: str, customer_tg_id: int, customer_name: str, customer_username: str, items: list, total_amount: int) -> Optional[dict]:
    pool = await get_pool()
    if not pool:
        return None
    try:
        row = await pool.fetchrow(
            "INSERT INTO orders (store_id, order_code, customer_tg_id, customer_name, customer_username, items, total_amount, status) VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, 'pending') RETURNING *",
            store_id, order_code, customer_tg_id, customer_name, customer_username, json.dumps(items), total_amount
        )
        return dict(row) if row else None
    except Exception:
        return None

async def get_orders_by_customer(customer_tg_id: int, store_id: int, limit: int = 5) -> list[dict]:
    pool = await get_pool()
    if not pool:
        return []
    try:
        rows = await pool.fetch(
            "SELECT * FROM orders WHERE customer_tg_id = $1 AND store_id = $2 ORDER BY created_at DESC LIMIT $3",
            customer_tg_id, store_id, limit
        )
        return [dict(r) for r in rows]
    except Exception:
        return []

async def get_owner_telegram_id(store_id: int) -> Optional[int]:
    pool = await get_pool()
    if not pool:
        return None
    try:
        row = await pool.fetchrow(
            "SELECT u.telegram_id FROM users u JOIN store_configs s ON s.user_id = u.id WHERE s.id = $1",
            store_id
        )
        return row["telegram_id"] if row else None
    except Exception:
        return None
