"""
In-memory cart storage (dùng dict, đủ cho MVP).
Với scale lớn nên dùng Redis.
Format: {
    "tg_user_id:store_slug": {
        "store_id": int,
        "store_slug": str,
        "items": {product_id: {"name": str, "price": int, "qty": int}}
    }
}
"""

_carts: dict = {}
_user_store: dict = {}  # tg_user_id -> store_slug (để nhớ khách đang ở store nào)


def _key(tg_id: int, store_slug: str) -> str:
    return f"{tg_id}:{store_slug}"


def set_user_store(tg_id: int, store_slug: str):
    _user_store[tg_id] = store_slug


def get_user_store(tg_id: int) -> str | None:
    return _user_store.get(tg_id)


def get_cart(tg_id: int, store_slug: str) -> dict:
    return _carts.get(_key(tg_id, store_slug), {})


def add_to_cart(tg_id: int, store_slug: str, store_id: int, product: dict, qty: int = 1):
    key = _key(tg_id, store_slug)
    if key not in _carts:
        _carts[key] = {"store_id": store_id, "store_slug": store_slug, "items": {}}

    pid = str(product["id"])
    if pid in _carts[key]["items"]:
        _carts[key]["items"][pid]["qty"] += qty
    else:
        _carts[key]["items"][pid] = {
            "product_id": product["id"],
            "name": product["name"],
            "price": product["price"],
            "qty": qty,
        }


def remove_from_cart(tg_id: int, store_slug: str, product_id: int):
    key = _key(tg_id, store_slug)
    if key in _carts:
        pid = str(product_id)
        if pid in _carts[key]["items"]:
            del _carts[key]["items"][pid]


def update_qty(tg_id: int, store_slug: str, product_id: int, qty: int):
    key = _key(tg_id, store_slug)
    pid = str(product_id)
    if key in _carts and pid in _carts[key]["items"]:
        if qty <= 0:
            del _carts[key]["items"][pid]
        else:
            _carts[key]["items"][pid]["qty"] = qty


def clear_cart(tg_id: int, store_slug: str):
    key = _key(tg_id, store_slug)
    if key in _carts:
        del _carts[key]


def get_cart_total(tg_id: int, store_slug: str) -> int:
    cart = get_cart(tg_id, store_slug)
    items = cart.get("items", {})
    return sum(item["price"] * item["qty"] for item in items.values())


def get_cart_count(tg_id: int, store_slug: str) -> int:
    cart = get_cart(tg_id, store_slug)
    return sum(item["qty"] for item in cart.get("items", {}).values())
