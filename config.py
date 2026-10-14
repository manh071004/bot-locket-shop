import os
import sys
import logging
from dotenv import load_dotenv

# Đảm bảo UTF-8 cho console Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Nạp file .env từ thư mục hiện tại
load_dotenv()

# Cấu hình logging
logging.basicConfig(
    format="[%(asctime)s] %(levelname)s - %(name)s: %(message)s",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log", encoding="utf-8")
    ]
)
logger = logging.getLogger("ShopBot")

# Thông tin Telegram Client (lấy tại https://my.telegram.org)
API_ID_RAW = os.getenv("API_ID", "")
API_ID = int(API_ID_RAW) if API_ID_RAW.isdigit() else 0
API_HASH = os.getenv("API_HASH", "").strip()

# Bot Token (lấy tại @BotFather)
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# Admin Telegram ID (Hỗ trợ ADMIN_ID hoặc ADMIN_CHAT_ID, có thể nhiều ID cách nhau bằng dấu phẩy)
ADMIN_IDS_RAW = os.getenv("ADMIN_ID") or os.getenv("ADMIN_CHAT_ID") or ""
ADMIN_IDS = []
if ADMIN_IDS_RAW:
    for item in str(ADMIN_IDS_RAW).split(","):
        item = item.strip()
        if item.isdigit():
            ADMIN_IDS.append(int(item))

# Cấu hình cổng thanh toán PayOS (https://payos.vn)
PAYOS_CLIENT_ID = os.getenv("PAYOS_CLIENT_ID", "").strip()
PAYOS_API_KEY = os.getenv("PAYOS_API_KEY", "").strip()
PAYOS_CHECKSUM_KEY = os.getenv("PAYOS_CHECKSUM_KEY", "").strip()
PAYOS_RETURN_URL = os.getenv("PAYOS_RETURN_URL", "https://t.me").strip()
PAYOS_CANCEL_URL = os.getenv("PAYOS_CANCEL_URL", "https://t.me").strip()

# Cấu hình ngân hàng dự phòng (VietQR)
BANK_ID = os.getenv("BANK_ID", "MB").strip()
BANK_ACCOUNT = os.getenv("BANK_ACCOUNT", "").strip()
BANK_ACCOUNT_NAME = os.getenv("BANK_ACCOUNT_NAME", "").strip()

# Cấu hình nhóm cộng đồng (Bắt buộc tham gia mới được dùng bot)
GROUP_ID_RAW = os.getenv("ADD_GROUP_ID", "").strip()
GROUP_ID = int(GROUP_ID_RAW) if (GROUP_ID_RAW.startswith("-") and GROUP_ID_RAW[1:].isdigit()) or GROUP_ID_RAW.isdigit() else 0
GROUP_INVITE_LINK = os.getenv("GROUP_INVITE_LINK", "https://t.me/+ce2GZWmD11MzYzll").strip()
# Cấu hình thời gian chờ (Timeout)
TIMEOUT_INPUT_SECONDS = int(os.getenv("TIMEOUT_INPUT_SECONDS", 180)) # 3 phút cho nhập liệu
TIMEOUT_PAYMENT_SECONDS = int(os.getenv("TIMEOUT_PAYMENT_SECONDS", 600)) # 10 phút cho thanh toán
BACKUP_INTERVAL_HOURS = int(os.getenv("BACKUP_INTERVAL_HOURS", 12)) # Tự động sao lưu mỗi 12 giờ
