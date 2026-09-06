@echo off
rem ============================================================
rem  MKCL 构建
rem  产物：dist\MinecraftLauncher\MinecraftLauncher.exe（免 Python 运行）
rem ============================================================
setlocal
cd /d "%~dp0"

echo [1/4] 检查 Python...
python --version || (echo 未找到 python，请先安装 Python 3.10+ & exit /b 1)

echo [2/4] 创建虚拟环境 .venv ...
if not exist .venv python -m venv .venv
call .venv\Scripts\activate.bat

echo [3/4] 安装依赖...
python -m pip install --upgrade pip -q
python -m pip install -r requirements.txt pyinstaller -q

echo [4/4] 打包（onedir / windowed）...
python -m PyInstaller --noconfirm --clean --onedir --windowed --name MinecraftLauncher main.py

if exist dist\MinecraftLauncher\MinecraftLauncher.exe (
    echo.
    echo 构建成功：dist\MinecraftLauncher\MinecraftLauncher.exe
    echo 整个 dist\MinecraftLauncher 文件夹即为发布包，可拷贝到其他 Windows 机器运行。
) else (
    echo 构建失败，请检查上方日志。
    exit /b 1
)
endlocal
