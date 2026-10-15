#!/bin/bash
# ============================================================
# MONOREPO STARTER - Chạy tất cả bot song song
# Thêm bot mới: copy khối bên dưới và đổi tên thư mục
# ============================================================

echo "=========================================="
echo " KHỞI ĐỘNG HỆ THỐNG MULTI-BOT"
echo "=========================================="

# Cài dependencies cho từng bot
echo "[*] Cài thư viện cho bot-v2..."
pip install -r bot-v2/requirements.txt -q

echo "[*] Cài thư viện cho bot-tao..."
pip install -r bot-tao/requirements.txt -q

echo ""
echo "[✓] Bắt đầu chạy các bot..."
echo ""

# ──────────────────────────────────────────────
# BOT 1: bot-v2 (Bot bán hàng Locket/Canva/Gemini)
# ──────────────────────────────────────────────
echo "[*] Khởi động bot-v2..."
cd bot-v2 && python main.py &
BOT_V2_PID=$!
cd ..
echo "[✓] bot-v2 đang chạy (PID: $BOT_V2_PID)"

# ──────────────────────────────────────────────
# BOT 2: bot-tao (Bot mới - thêm sau)
# ──────────────────────────────────────────────
echo "[*] Khởi động bot-tao..."
cd bot-tao && python main.py &
BOT_TAO_PID=$!
cd ..
echo "[✓] bot-tao đang chạy (PID: $BOT_TAO_PID)"

# ──────────────────────────────────────────────
# THÊM BOT MỚI Ở ĐÂY (copy khối trên, đổi tên)
# ──────────────────────────────────────────────
# echo "[*] Khởi động bot-moi..."
# cd bot-moi && python main.py &
# BOT_MOI_PID=$!
# cd ..

echo ""
echo "=========================================="
echo " TẤT CẢ BOT ĐÃ KHỞI ĐỘNG THÀNH CÔNG"
echo "=========================================="
echo " bot-v2  PID: $BOT_V2_PID"
echo " bot-tao PID: $BOT_TAO_PID"
echo "=========================================="

# Giữ process cha sống - đợi TẤT CẢ process con
# Nếu 1 bot crash, các bot khác vẫn chạy bình thường
wait $BOT_V2_PID
wait $BOT_TAO_PID
