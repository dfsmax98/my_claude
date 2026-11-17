@echo off
chcp 65001>nul
cd /d "%~dp0"
echo ============================================
echo   语音助手(网页版)
echo   启动后会自动打开浏览器;关掉本窗口即退出
echo ============================================
echo.
set PY=python
if exist "venv\Scripts\python.exe" set PY=venv\Scripts\python.exe
if exist ".venv\Scripts\python.exe" set PY=.venv\Scripts\python.exe
"%PY%" main.py --web
echo.
echo 程序已退出。
pause
