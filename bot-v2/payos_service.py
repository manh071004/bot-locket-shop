import io
import time
import qrcode
import requests
from config import (
    PAYOS_CLIENT_ID,
    PAYOS_API_KEY,
    PAYOS_CHECKSUM_KEY,
    PAYOS_RETURN_URL,
    PAYOS_CANCEL_URL,
    BANK_ID,
    BANK_ACCOUNT,
    BANK_ACCOUNT_NAME,
    logger
)

# Khởi tạo PayOS client nếu đủ thông tin cấu hình
payos_client = None
if PAYOS_CLIENT_ID and PAYOS_API_KEY and PAYOS_CHECKSUM_KEY:
    try:
        from payos import PayOS
        payos_client = PayOS(
            client_id=PAYOS_CLIENT_ID,
            api_key=PAYOS_API_KEY,
            checksum_key=PAYOS_CHECKSUM_KEY
        )
        logger.info("Khởi tạo PayOS Service thành công!")
    except Exception as e:
        logger.error(f"Lỗi khởi tạo PayOS: {e}")
else:
    logger.warning("Chưa cấu hình đầy đủ PAYOS trong .env (PAYOS_CLIENT_ID, PAYOS_API_KEY, PAYOS_CHECKSUM_KEY). Sẽ sử dụng VietQR dự phòng!")

def is_payos_configured() -> bool:
    return payos_client is not None

def generate_order_code() -> int:
    """Tạo mã đơn hàng dạng số nguyên dương an toàn cho PayOS (dưới MAX_SAFE_INTEGER)"""
    return int(time.time() * 10) % 90000000 + 10000000

def create_payment_request(order_code: int, amount: int, description: str, buyer_name: str = None) -> dict:
    """Tạo link thanh toán PayOS hoặc fallback VietQR"""
    # Xóa ký tự đặc biệt khỏi description theo yêu cầu PayOS (tối đa 25 ký tự, không dấu)
    clean_desc = "".join(c for c in description if c.isalnum() or c in " -_")[:25].strip()
    if not clean_desc:
        clean_desc = f"DH{order_code}"

    if is_payos_configured():
        try:
            from payos.types import CreatePaymentLinkRequest
            request_data = CreatePaymentLinkRequest(
                order_code=order_code,
                amount=amount,
                description=clean_desc,
                cancel_url=PAYOS_CANCEL_URL,
                return_url=PAYOS_RETURN_URL,
                buyer_name=buyer_name or "Khach Hang"
            )
            # Gọi API tạo payment link
            res = payos_client.payment_requests.create(request_data)
            logger.info(f"Tạo link PayOS thành công cho đơn {order_code}: {res.checkout_url}")
            return {
                "success": True,
                "type": "payos",
                "order_code": order_code,
                "amount": res.amount,
                "description": res.description,
                "account_number": res.account_number,
                "account_name": res.account_name,
                "bin": res.bin,
                "checkout_url": res.checkout_url,
                "qr_code": res.qr_code
            }
        except Exception as e:
            logger.error(f"Lỗi khi gọi PayOS createPaymentLink: {e}")
            # Fallback sang VietQR dự phòng
    
    # Fallback VietQR thông thường
    return {
        "success": True,
        "type": "vietqr_manual",
        "order_code": order_code,
        "amount": amount,
        "description": clean_desc,
        "account_number": BANK_ACCOUNT or "CHƯA CẤU HÌNH",
        "account_name": BANK_ACCOUNT_NAME or "ADMIN SHOP",
        "bin": BANK_ID or "MB",
        "checkout_url": "",
        "qr_code": None
    }

def check_payment_status(order_code: int) -> str:
    """Kiểm tra trạng thái thanh toán đơn hàng từ PayOS: PAID, PENDING, CANCELLED, EXPIRED"""
    if not is_payos_configured():
        return "UNKNOWN"
    try:
        payment_info = payos_client.payment_requests.get(id=order_code)
        return payment_info.status # PENDING, PAID, CANCELLED, EXPIRED
    except Exception as e:
        logger.error(f"Lỗi khi kiểm tra trạng thái PayOS cho đơn {order_code}: {e}")
        return "ERROR"

def cancel_payment(order_code: int, reason: str = "Khách hủy đơn") -> bool:
    """Hủy link thanh toán trên PayOS"""
    if not is_payos_configured():
        return True
    try:
        payos_client.payment_requests.cancel(id=order_code, cancellation_reason=reason[:25])
        logger.info(f"Đã hủy link thanh toán PayOS {order_code}")
        return True
    except Exception as e:
        logger.warning(f"Không thể hủy link thanh toán PayOS {order_code}: {e}")
        return False

def generate_qr_image_bytes(qr_payload: str = None, bank_bin: str = None, account_no: str = None, amount: int = 0, description: str = "") -> io.BytesIO:
    """Tạo ảnh QR code (io.BytesIO) từ chuỗi PayOS QR hoặc tải VietQR"""
    buf = io.BytesIO()
    buf.name = f"vietqr_{int(time.time())}.png"

    # Nếu có sẵn chuỗi payload VietQR chuẩn từ PayOS
    if qr_payload:
        try:
            qr = qrcode.QRCode(
                version=None,
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=10,
                border=2,
            )
            qr.add_data(qr_payload)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            img.save(buf, format="PNG")
            buf.seek(0)
            return buf
        except Exception as e:
            logger.error(f"Lỗi tạo QR từ payload: {e}")

    # Nếu fallback sang API VietQR QuickLink trực tuyến
    if bank_bin and account_no:
        try:
            vietqr_url = f"https://img.vietqr.io/image/{bank_bin}-{account_no}-compact2.png?amount={amount}&addInfo={description}&accountName={BANK_ACCOUNT_NAME}"
            resp = requests.get(vietqr_url, timeout=5)
            if resp.status_code == 200:
                buf.write(resp.content)
                buf.seek(0)
                return buf
        except Exception as e:
            logger.error(f"Lỗi tải VietQR image: {e}")

    # Fallback cuối cùng: QR tự tạo với nội dung text
    text_data = f"NGAN HANG: {bank_bin or BANK_ID} | STK: {account_no or BANK_ACCOUNT} | SO TIEN: {amount} | ND: {description}"
    img = qrcode.make(text_data)
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf
