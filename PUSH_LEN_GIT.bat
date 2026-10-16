@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo.
echo ==========================================
echo   DANG DONG BO DU LIEU WEB SANG RENDER...
echo ==========================================
echo.

:: Tu dong sao chep botstore.db moi nhat tu Web Dashboard sang Render
if exist "..\bot tao bot ban hang\backend\botstore.db" (
    copy /y "..\bot tao bot ban hang\backend\botstore.db" "bot-tao\botstore.db" >nul
    echo [v] Da dong bo co so du lieu botstore.db tu Web Dashboard!
)

git add .
set /p msg="Ghi chu thay doi (Enter de bo qua): "
if "%msg%"=="" set msg=Update data and code from web dashboard

git commit -m "%msg%"
git push origin main

echo.
echo ==========================================
echo   XONG! Render se tu dong deploy sau ~1 phut
echo ==========================================
echo.
pause
