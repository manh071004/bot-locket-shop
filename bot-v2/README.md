# 🤖 Bot Telegram Bán Hàng Dịch Vụ Bản Quyền (Version 2)

Bot Telegram tự động bán hàng và kích hoạt dịch vụ, được xây dựng bằng **Telethon** kết hợp với cổng thanh toán tự động **PayOS (VietQR 24/7)** và hệ thống quản trị, sao lưu dữ liệu tự động chống thất thoát dữ liệu.

---

## 📦 Danh Mục Sản Phẩm Tích Hợp Sẵn

Hệ thống đã cấu hình sẵn 5 mặt hàng theo yêu cầu trong file [products.json](file:///products.json):

| STT | Tên Dịch Vụ | Giá Bán | Mô Tả & Thời Hạn |
| :---: | :--- | :---: | :--- |
| **1** | 🎁 **Locket Gold Free** | **0 VNĐ** | Miễn phí trải nghiệm, mỗi khách hàng chỉ nhận 1 lần |
| **2** | 💛 **Locket Gold Chính Chủ** | **80.000 VNĐ** | Gói chính chủ 2 năm (24 tháng), bảo hành 1 đổi 1 |
| **3** | 🎨 **Canva Pro Edu** | **40.000 VNĐ** | Nâng cấp chính chủ email 12 tháng (1 năm) |
| **4** | 👑 **Admin Canva Pro Edu** | **120.000 VNĐ** | Quyền quản trị viên chính chủ 2 năm (tự mời team) |
| **5** | 🤖 **Gemini Pro (Advanced)** | **200.000 VNĐ** | Tài khoản / Gói Google Gemini Pro 18 tháng |

> 💡 **Tùy biến cho từng mặt hàng:** Bạn có thể tự do thay đổi tên, giá, mô tả và câu hỏi yêu cầu khách nhập thông tin (Email, SĐT, Username...) trực tiếp trong file `products.json` mà không cần chỉnh sửa mã nguồn!

---

## ⚡ Các Tính Năng Nổi Bật

1. **Thanh Toán Tự Động 24/7 (PayOS VietQR):**
   - Tự động sinh mã VietQR chuẩn ngân hàng với đúng số tiền và nội dung đơn hàng duy nhất (`DH...`).
   - Tự động kiểm tra giao dịch (Polling mỗi 5 giây). Khi khách chuyển tiền thành công, bot gửi thông báo tức thì cho khách và Admin.
   - Nút kiểm tra trạng thái và mở trang thanh toán PayOS trực tiếp.

2. **Quy Trình Nhận Locket Gold Free 0đ:**
   - Khách chỉ cần nhập thông tin (Email/Username Locket).
   - Kiểm tra chống spam (mỗi người dùng chỉ được nhận 1 lần).
   - Đơn hàng 0đ được chuyển thẳng tới Admin để kích hoạt quà tặng.

3. **Cơ Chế Hàng Chờ & Timeout:**
   - **Timeout nhập liệu:** 3 phút (180 giây).
   - **Timeout thanh toán:** 10 phút (600 giây). Nếu quá hạn chưa chuyển tiền, đơn hàng và link thanh toán sẽ tự động được hủy an toàn.

4. **Bảo Vệ & Sao Lưu Dữ Liệu Chống Mất Mát (Backup):**
   - Cơ sở dữ liệu JSON cục bộ [db.json](file:///db.json) sử dụng cơ chế ghi an toàn (Atomic File Replacement).
   - **Lệnh thủ công `/backup`:** Admin chỉ cần gõ `/backup` là bot gửi trực tiếp file `db.json` vào tin nhắn Telegram cá nhân.
   - **Tự động sao lưu định kỳ:** Mỗi **12 tiếng**, bot tự động gửi file `db.json` đính kèm báo cáo doanh thu về Telegram của Admin.

5. **Bảng Điều Khiển Quản Trị Viên (Admin Panel - `/admin`):**
   - Thống kê doanh thu tổng, doanh thu hôm nay, tổng số đơn hàng và tổng khách hàng.
   - Danh sách các đơn hàng chờ bàn giao.
   - **Bàn giao 1 chạm:** Admin chỉ cần bấm `[✅ Đã Bàn Giao Dịch Vụ]`, bot tự động gửi thông báo kích hoạt thành công tới khách hàng!
   - **Gửi thông báo toàn hệ thống (Broadcast):** Gửi tin nhắn đồng loạt tới tất cả khách hàng đã từng tương tác với bot.

---

## 🚀 Hướng Dẫn Chạy Bot

### 1. Cấu Hình Biến Môi Trường (.env)
Kiểm tra file `.env` đã có đầy đủ thông tin:
```env
API_ID=35415782
API_HASH=your_api_hash
BOT_TOKEN=your_bot_token
ADMIN_CHAT_ID=8337687095
PAYOS_CLIENT_ID=...
PAYOS_API_KEY=...
PAYOS_CHECKSUM_KEY=...
```

### 2. Chạy Thử Trên Máy Tính Windows
Mở terminal tại thư mục dự án và chạy:
```powershell
python main.py
```

### 3. Hướng Dẫn Triển Khai Trên VPS Cloudfly / Ubuntu (24.04)
1. Cài đặt các thư viện cần thiết (vượt qua cơ chế PEP 668 của Ubuntu 24.04):
   ```bash
   pip3 install --break-system-packages -r requirements.txt
   ```
2. Khởi tạo phiên chạy nền `screen` để giữ bot online liên tục:
   ```bash
   screen -S bot
   ```
3. Khởi chạy bot:
   ```bash
   python3 main.py
   ```
4. Thoát khỏi màn hình screen (bot vẫn chạy ngầm):
   - Nhấn tổ hợp phím: `Ctrl + A` sau đó nhấn phím `D`.
5. Khi muốn quay lại xem log của bot:
   ```bash
   screen -r bot
   ```

---

## 📂 Cấu Trúc Mã Nguồn

```
bot tele v2 ban hang/
├── main.py              # Xử lý sự kiện bot, tin nhắn, nút bấm và background tasks
├── config.py            # Đọc file cấu hình .env, thiết lập logging chuẩn UTF-8
├── database.py          # Quản lý cơ sở dữ liệu db.json & products.json an toàn
├── payos_service.py     # Tích hợp PayOS API, tạo link thanh toán & mã VietQR
├── products.json        # Danh mục 5 mặt hàng (có thể chỉnh sửa tuỳ ý)
├── requirements.txt     # Danh sách thư viện Python cần thiết
├── .env.example         # File mẫu cấu hình
└── README.md            # Tài liệu hướng dẫn sử dụng
```
