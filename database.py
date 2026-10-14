import os
import json
import time
import shutil
from datetime import datetime
from config import logger

DB_FILE = "db.json"
PRODUCTS_FILE = "products.json"

class Database:
    def __init__(self, db_path=DB_FILE):
        self.db_path = db_path
        self.data = {
            "users": {},
            "orders": {},
            "stats": {
                "total_revenue": 0,
                "total_orders": 0
            },
            "settings": {
                "admin_incognito": False
            }
        }
        self.load()

    def load(self):
        """Đọc cơ sở dữ liệu từ file json, tạo mới nếu chưa tồn tại"""
        if os.path.exists(self.db_path):
            try:
                with open(self.db_path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if content:
                        self.data = json.loads(content)
                        if "users" not in self.data:
                            self.data["users"] = {}
                        if "orders" not in self.data:
                            self.data["orders"] = {}
                        if "stats" not in self.data:
                            self.data["stats"] = {"total_revenue": 0, "total_orders": 0}
                        if "settings" not in self.data:
                            self.data["settings"] = {"admin_incognito": False}
                        logger.info(f"Đã tải database thành công: {len(self.data['users'])} users, {len(self.data['orders'])} orders.")
                        return
            except Exception as e:
                logger.error(f"Lỗi khi đọc file {self.db_path}: {e}")
                backup_name = f"{self.db_path}.corrupt.{int(time.time())}"
                shutil.copyfile(self.db_path, backup_name)
                logger.warning(f"Đã tạo bản sao lưu file lỗi sang {backup_name}")

        self.save()

    def is_admin_incognito(self) -> bool:
        """Kiểm tra chế độ ẩn danh của Admin (bật thì ẩn ID và thông tin liên hệ của Admin)"""
        return bool(self.data.get("settings", {}).get("admin_incognito", False))

    def toggle_admin_incognito(self) -> bool:
        """Bật/tắt chế độ ẩn danh cho Admin"""
        if "settings" not in self.data:
            self.data["settings"] = {}
        curr = self.data["settings"].get("admin_incognito", False)
        self.data["settings"]["admin_incognito"] = not curr
        self.save()
        return self.data["settings"]["admin_incognito"]

    def save(self):
        """Ghi an toàn dữ liệu ra file sử dụng atomic replace"""
        tmp_file = f"{self.db_path}.tmp"
        try:
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_file, self.db_path)
        except Exception as e:
            logger.error(f"Lỗi khi lưu database: {e}")
            if os.path.exists(tmp_file):
                try:
                    os.remove(tmp_file)
                except Exception:
                    pass

    # ------------------ USERS ------------------
    def get_or_create_user(self, user_id: int, username: str = None, first_name: str = None) -> dict:
        uid = str(user_id)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if uid not in self.data["users"]:
            self.data["users"][uid] = {
                "id": user_id,
                "username": username or "",
                "first_name": first_name or "",
                "joined_at": now_str,
                "total_spent": 0,
                "orders_count": 0,
                "free_claimed": {},
                "group_verified_at": 0, # Timestamp lần cuối xác minh nhóm (hết hạn sau 7 ngày)
                "referred_friend_id": None # ID người bạn đã giới thiệu (chống spam)
            }
            self.save()
        else:
            updated = False
            if username and self.data["users"][uid].get("username") != username:
                self.data["users"][uid]["username"] = username
                updated = True
            if first_name and self.data["users"][uid].get("first_name") != first_name:
                self.data["users"][uid]["first_name"] = first_name
                updated = True
            if "free_claimed" not in self.data["users"][uid]:
                self.data["users"][uid]["free_claimed"] = {}
                updated = True
            if "group_verified_at" not in self.data["users"][uid]:
                self.data["users"][uid]["group_verified_at"] = 0
                updated = True
            if "referred_friend_id" not in self.data["users"][uid]:
                self.data["users"][uid]["referred_friend_id"] = None
                updated = True
            if updated:
                self.save()

        return self.data["users"][uid]

    def is_group_verified(self, user_id: int) -> bool:
        """Kiểm tra xem người dùng đã xác minh vào nhóm trong vòng 7 ngày chưa"""
        uid = str(user_id)
        user = self.get_or_create_user(user_id)
        verified_time = user.get("group_verified_at", 0)
        # 7 ngày = 7 * 86400 giây = 604800 giây
        return (time.time() - verified_time) < (7 * 86400)

    def set_group_verified(self, user_id: int):
        """Lưu mốc thời gian xác minh vào nhóm thành công"""
        uid = str(user_id)
        if uid in self.data["users"]:
            self.data["users"][uid]["group_verified_at"] = time.time()
            self.save()

    def find_user_by_username_or_id(self, query: str):
        """Tìm user trong hệ thống theo username hoặc id (không phân biệt chữ hoa/thường)"""
        clean_q = query.strip().lstrip("@").lower()
        for u in self.data["users"].values():
            if str(u.get("id")) == clean_q:
                return u
            if u.get("username") and u.get("username").lower() == clean_q:
                return u
        return None

    def is_friend_already_used_as_referral(self, friend_id: int) -> bool:
        """Kiểm tra xem ID bạn bè này đã từng được ai điền để nhận quà trước đó chưa (Chống dùng 1 người cho nhiều tài khoản)"""
        for u in self.data["users"].values():
            if u.get("referred_friend_id") == friend_id:
                return True
        return False

    def set_user_referral_success(self, user_id: int, friend_id: int):
        """Ghi nhận người bạn đã giới thiệu thành công gắn cố định với user_id và friend_id"""
        uid = str(user_id)
        if uid in self.data["users"]:
            self.data["users"][uid]["referred_friend_id"] = friend_id
            self.save()

    def has_claimed_free(self, user_id: int, product_id: str) -> bool:
        uid = str(user_id)
        user = self.get_or_create_user(user_id)
        free_map = user.get("free_claimed", {})
        return bool(free_map.get(product_id, False))

    def set_claimed_free(self, user_id: int, product_id: str):
        uid = str(user_id)
        if uid in self.data["users"]:
            if "free_claimed" not in self.data["users"][uid]:
                self.data["users"][uid]["free_claimed"] = {}
            self.data["users"][uid]["free_claimed"][product_id] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.save()

    def get_all_user_ids(self) -> list:
        return [int(uid) for uid in self.data["users"].keys()]

    # ------------------ ORDERS ------------------
    def create_order(self, user_id: int, username: str, product: dict, customer_info: str, payos_order_code: int = None, payment_type: str = "payos") -> dict:
        now = datetime.now()
        now_str = now.strftime("%Y-%m-%d %H:%M:%S")
        order_id = f"DH{int(time.time() * 10) % 90000000 + 10000000}"
        
        order = {
            "order_id": order_id,
            "payos_order_code": payos_order_code,
            "user_id": user_id,
            "username": username or "",
            "product_id": product["id"],
            "product_name": product["name"],
            "amount": product["price"],
            "status": "COMPLETED" if product["price"] == 0 else "PENDING", # PENDING, PAID, COMPLETED, CANCELLED, EXPIRED
            "customer_info": customer_info,
            "payment_type": payment_type,
            "created_at": now_str,
            "paid_at": now_str if product["price"] == 0 else None,
            "delivered_at": None,
            "notes": ""
        }

        self.data["orders"][order_id] = order
        if str(user_id) in self.data["users"]:
            self.data["users"][str(user_id)]["orders_count"] = self.data["users"][str(user_id)].get("orders_count", 0) + 1
            if product["price"] == 0:
                self.set_claimed_free(user_id, product["id"])

        self.save()
        return order

    def update_order_status(self, order_id: str, new_status: str, extra_data: dict = None) -> bool:
        if order_id not in self.data["orders"]:
            return False
        
        order = self.data["orders"][order_id]
        old_status = order.get("status")
        order["status"] = new_status
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if new_status in ["PAID", "COMPLETED"] and old_status not in ["PAID", "COMPLETED"]:
            if not order.get("paid_at"):
                order["paid_at"] = now_str
            # Cập nhật chi tiêu của người dùng
            uid = str(order["user_id"])
            if uid in self.data["users"]:
                self.data["users"][uid]["total_spent"] = self.data["users"][uid].get("total_spent", 0) + order["amount"]
            self.data["stats"]["total_revenue"] = self.data["stats"].get("total_revenue", 0) + order["amount"]
            self.data["stats"]["total_orders"] = self.data["stats"].get("total_orders", 0) + 1

        if new_status == "COMPLETED" and not order.get("delivered_at"):
            order["delivered_at"] = now_str

        if extra_data:
            order.update(extra_data)

        self.save()
        return True

    def get_order(self, order_id: str) -> dict:
        return self.data["orders"].get(order_id)

    def get_order_by_payos_code(self, order_code: int) -> dict:
        for order in self.data["orders"].values():
            if order.get("payos_order_code") == order_code:
                return order
        return None

    def get_user_orders(self, user_id: int, limit: int = 10) -> list:
        user_orders = [o for o in self.data["orders"].values() if o.get("user_id") == user_id]
        user_orders.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return user_orders[:limit]

    def get_recent_orders(self, limit: int = 10) -> list:
        all_orders = list(self.data["orders"].values())
        all_orders.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return all_orders[:limit]

    def get_pending_delivery_orders(self) -> list:
        # Đơn đã trả tiền hoặc đơn 0đ nhưng chưa được admin bấm bàn giao
        pending = [
            o for o in self.data["orders"].values() 
            if o.get("status") in ["PAID", "COMPLETED"] and not o.get("delivered_at")
        ]
        pending.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return pending

    def get_statistics(self) -> dict:
        total_users = len(self.data["users"])
        total_orders = len(self.data["orders"])
        paid_orders = [o for o in self.data["orders"].values() if o.get("status") in ["PAID", "COMPLETED"]]
        total_revenue = sum(o.get("amount", 0) for o in paid_orders)
        
        # Thống kê hôm nay
        today_str = datetime.now().strftime("%Y-%m-%d")
        today_orders = [o for o in paid_orders if str(o.get("created_at", "")).startswith(today_str)]
        today_revenue = sum(o.get("amount", 0) for o in today_orders)

        return {
            "total_users": total_users,
            "total_orders": total_orders,
            "paid_orders_count": len(paid_orders),
            "total_revenue": total_revenue,
            "today_orders_count": len(today_orders),
            "today_revenue": today_revenue
        }

# Khởi tạo instance cơ sở dữ liệu dùng chung
db = Database()

def load_products():
    """Đọc danh sách sản phẩm từ file products.json"""
    if os.path.exists(PRODUCTS_FILE):
        try:
            with open(PRODUCTS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Lỗi đọc products.json: {e}")
    return []

def get_product_by_id(product_id: str):
    products = load_products()
    for p in products:
        if p["id"] == product_id:
            return p
    return None
