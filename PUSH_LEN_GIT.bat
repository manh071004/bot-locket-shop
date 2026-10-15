@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo.
echo ==========================================
echo   DANG TAI CODE LEN GITHUB + RENDER...
echo ==========================================
echo.

git add .

:: Hỏi ghi chú commit
set /p msg="Ghi chu thay doi (Enter de bo qua): "
if "%msg%"=="" set msg=Update code

git commit -m "%msg%"
git push origin main

echo.
echo ==========================================
echo   XONG! Render se tu dong deploy sau ~1 phut
echo ==========================================
echo.
pause
