# 🤖 Multi-Bot Monorepo - Server Render $7

Hệ thống chạy nhiều bot Telegram trên **1 server Render duy nhất**, mỗi bot hoàn toàn độc lập.

## 📁 Cấu Trúc

```
/
├── start.sh          ← Script Render chạy để khởi động TẤT CẢ bot
├── .gitignore        ← Bảo vệ .env và db.json của mọi bot
├── README.md         ← File này
│
├── bot-v2/           ← Bot bán hàng Locket/Canva/Gemini (Version 2)
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── payos_service.py
│   ├── products.json
│   ├── requirements.txt
│   └── .env.example
│
└── bot-tao/          ← Bot mới (thêm code sau)
    ├── main.py
    ├── requirements.txt
    └── .env.example
```

## 🚀 Cách Thêm Bot Mới (Về Sau)

1. Tạo thư mục mới: `bot-ten-bot/`
2. Thêm `main.py` và `requirements.txt` vào thư mục đó
3. Mở `start.sh`, copy khối bot và đổi tên thư mục
4. Thêm `.env` vào `.gitignore`
5. Trên Render: thêm biến môi trường mới cho bot đó
6. Commit & push → Render tự deploy

## ⚙️ Cấu Hình Render

- **Type:** Background Worker
- **Build Command:** `pip install -r bot-v2/requirements.txt && pip install -r bot-tao/requirements.txt`  
  *(hoặc để `start.sh` tự cài)*
- **Start Command:** `bash start.sh`
- **Environment Variables:** Thêm biến cho **TẤT CẢ** bot với prefix để phân biệt:
  - `BOT_V2_TOKEN`, `BOT_V2_ADMIN_CHAT_ID`, v.v. → cho bot-v2
  - `BOT_TAO_TOKEN`, `BOT_TAO_ADMIN_CHAT_ID`, v.v. → cho bot-tao

## 🔒 Bảo Mật

- File `.env` **KHÔNG BAO GIỜ** được commit lên GitHub
- Mỗi bot đọc biến môi trường riêng của mình
- Render quản lý secrets qua Environment Variables dashboard
