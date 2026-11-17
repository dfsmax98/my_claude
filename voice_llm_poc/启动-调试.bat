@echo off
chcp 65001>nul
cd /d "%~dp0"
echo ============================================
echo   语音助手(调试模式,此窗口显示运行日志)
echo   关掉本窗口即退出程序
echo ============================================
echo.
REM 优先用本目录 venv 的 python,否则用系统 python
set PY=python
if exist "venv\Scripts\python.exe" set PY=venv\Scripts\python.exe
if exist ".venv\Scripts\python.exe" set PY=.venv\Scripts\python.exe
"%PY%" main.py --tray
echo.
echo 程序已退出。
pause
