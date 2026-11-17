@echo off
chcp 65001>nul
cd /d "%~dp0"
echo ============================================
echo   安装语音助手依赖(只需运行一次)
echo ============================================
echo.
echo [1/2] 安装 CPU 版 PyTorch ...
python -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
echo.
echo [2/2] 安装其余依赖 ...
python -m pip install -r requirements.txt
echo.
echo 完成。首次启动会自动下载语音识别模型(几百 MB),请耐心等待。
echo.
pause
