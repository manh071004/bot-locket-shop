#!/bin/bash
echo "========================================="
echo " KHOI DONG HE THONG MULTI-BOT TREN RENDER"
echo "========================================"

echo "[+] Khoi dong bot-v2..."
cd bot-v2
python main.py &
BOT_V2_PID=$!
cd ..
echo "[v] bot-v2 dang chay"

wait $BOT_V2_PID
