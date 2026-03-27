@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion
title 车辆检测计数系统 -- 启动与环境检测

:: ================================================================
::  路径定义
:: ================================================================
set "ROOT=%~dp0"
if "!ROOT:~-1!"=="\" set "ROOT=!ROOT:~0,-1!"
set "BACKEND=!ROOT!\backend"
set "FRONTEND=!ROOT!\frontend"
set "VENV=!BACKEND!\venv"
set "VENV_PY=!VENV!\Scripts\python.exe"
set "VENV_PIP=!VENV!\Scripts\pip.exe"
set "ALEMBIC=!VENV!\Scripts\alembic.exe"

:: ================================================================
::  默认端口（从 .env 覆盖）
:: ================================================================
set "API_PORT=8000"
set "TCP_PORT=9000"
set "FE_PORT=5173"
set "MYSQL_PORT=3306"

:: 检测计数
set /a ERR=0
set /a WARN=0

cd /d "!ROOT!"
cls

echo.
echo  ==============================================================
echo   车辆检测计数系统  Vehicle Detection ^& Counter
echo   启动预检脚本 v1.0
echo  ==============================================================
echo.

:: ================================================================
::  STEP 1 -- 基础运行环境
:: ================================================================
echo  [STEP 1/6] 基础运行环境检测
echo  --------------------------------------------------------------

:: Python
set "PY_OK=0"
python --version >nul 2>&1
if errorlevel 1 (
    echo  [FAIL] Python 未安装或未加入 PATH
    echo         请访问 https://python.org 安装 Python 3.10+
    set /a ERR+=1
) else (
    for /f "tokens=2" %%v in ('python --version 2^>^&1') do set "PY_VER=%%v"
    for /f "tokens=1,2 delims=." %%a in ("!PY_VER!") do (
        set "PY_MAJ=%%a"
        set "PY_MIN=%%b"
    )
    if !PY_MAJ! LSS 3 (
        echo  [FAIL] Python !PY_VER! 版本过低，需要 3.10+
        set /a ERR+=1
    ) else if !PY_MAJ! EQU 3 if !PY_MIN! LSS 10 (
        echo  [WARN] Python !PY_VER!  (建议升级到 3.10+)
        set /a WARN+=1
        set "PY_OK=1"
    ) else (
        echo  [ OK ] Python !PY_VER!
        set "PY_OK=1"
    )
)

:: Node.js
set "NODE_OK=0"
node --version >nul 2>&1
if errorlevel 1 (
    echo  [FAIL] Node.js 未安装或未加入 PATH
    echo         请访问 https://nodejs.org 安装 Node.js 18+
    set /a ERR+=1
) else (
    for /f %%v in ('node --version 2^>^&1') do set "NODE_VER=%%v"
    echo  [ OK ] Node.js !NODE_VER!
    set "NODE_OK=1"
)

:: pnpm
set "PNPM_OK=0"
pnpm --version >nul 2>&1
if errorlevel 1 (
    echo  [WARN] pnpm 未安装，尝试自动安装...
    npm install -g pnpm >nul 2>&1
    pnpm --version >nul 2>&1
    if errorlevel 1 (
        echo  [FAIL] pnpm 安装失败，请手动运行: npm install -g pnpm
        set /a ERR+=1
    ) else (
        for /f %%v in ('pnpm --version 2^>^&1') do set "PNPM_VER=%%v"
        echo  [ OK ] pnpm !PNPM_VER! (已自动安装)
        set "PNPM_OK=1"
    )
) else (
    for /f %%v in ('pnpm --version 2^>^&1') do set "PNPM_VER=%%v"
    echo  [ OK ] pnpm !PNPM_VER!
    set "PNPM_OK=1"
)

echo.

:: ================================================================
::  STEP 2 -- 配置文件
:: ================================================================
echo  [STEP 2/6] 配置文件检测
echo  --------------------------------------------------------------

:: backend/.env
if not exist "!BACKEND!\.env" (
    echo  [WARN] backend\.env 不存在
    if exist "!BACKEND!\.env.example" (
        copy "!BACKEND!\.env.example" "!BACKEND!\.env" >nul
        echo  [ OK ] 已从 .env.example 复制到 backend\.env
        echo  [!!!]  请编辑 backend\.env 中的数据库密码 / JWT_SECRET_KEY !
        set /a WARN+=1
    ) else (
        echo  [FAIL] backend\.env 和 .env.example 均不存在，请手动创建
        set /a ERR+=1
    )
) else (
    echo  [ OK ] backend\.env 存在
)

:: 从 .env 读取端口
if exist "!BACKEND!\.env" (
    for /f "usebackq tokens=1* delims==" %%k in ("!BACKEND!\.env") do (
        if /i "%%k"=="API_PORT"  if not "%%l"=="" set "API_PORT=%%l"
        if /i "%%k"=="TCP_PORT"  if not "%%l"=="" set "TCP_PORT=%%l"
        if /i "%%k"=="DATABASE_URL" set "DB_URL=%%l"
    )
    echo  [INFO] 端口配置  API=!API_PORT!  TCP=!TCP_PORT!  FE=!FE_PORT!
)

:: frontend/.env.local
if not exist "!FRONTEND!\.env.local" (
    echo  [WARN] frontend\.env.local 不存在，正在生成默认配置...
    (
        echo # Auto-generated local config
        echo VITE_API_BASE_URL=http://localhost:!API_PORT!
        echo VITE_WS_BASE_URL=ws://localhost:!API_PORT!
        echo VITE_DEFAULT_DEVICE_ID=1
    ) > "!FRONTEND!\.env.local"
    echo  [ OK ] frontend\.env.local 已创建 (指向 localhost:!API_PORT!)
    set /a WARN+=1
) else (
    echo  [ OK ] frontend\.env.local 存在
)

:: YOLO 模型
if not exist "!BACKEND!\models\yolov8n.pt" (
    if not exist "!BACKEND!\models" mkdir "!BACKEND!\models"
    echo  [WARN] YOLO 模型不存在: backend\models\yolov8n.pt
    echo         后端首次启动时将自动下载 (~6MB，需联网)
    set /a WARN+=1
) else (
    for %%f in ("!BACKEND!\models\yolov8n.pt") do set "MODEL_BYTES=%%~zf"
    set /a MODEL_MB=!MODEL_BYTES! / 1048576
    echo  [ OK ] yolov8n.pt  (!MODEL_MB! MB)
)

echo.

:: ================================================================
::  STEP 3 -- Python 虚拟环境 & 依赖
:: ================================================================
echo  [STEP 3/6] Python 虚拟环境 ^& 依赖
echo  --------------------------------------------------------------

if "!PY_OK!"=="0" (
    echo  [SKIP] Python 环境异常，跳过
    goto STEP4
)

if not exist "!VENV!" (
    echo  [WARN] 虚拟环境不存在，正在创建 backend\venv ...
    python -m venv "!VENV!"
    if errorlevel 1 (
        echo  [FAIL] 创建虚拟环境失败
        set /a ERR+=1
        goto STEP4
    )
    echo  [ OK ] 虚拟环境已创建
)

if not exist "!VENV_PY!" (
    echo  [FAIL] 虚拟环境损坏，请删除 backend\venv 后重试
    set /a ERR+=1
    goto STEP4
)
echo  [ OK ] 虚拟环境: backend\venv

:: 检查核心包
"!VENV_PY!" -c "import fastapi, uvicorn, sqlalchemy, aiomysql, jose, bcrypt" >nul 2>&1
if errorlevel 1 (
    echo  [WARN] 依赖不完整，开始安装 requirements.txt (请等待)...
    "!VENV_PIP!" install -r "!BACKEND!\requirements.txt" -q --no-warn-script-location
    if errorlevel 1 (
        echo  [FAIL] pip install 失败，请手动运行:
        echo         cd backend ^&^& venv\Scripts\pip install -r requirements.txt
        set /a ERR+=1
    ) else (
        echo  [ OK ] Python 依赖安装完成
    )
) else (
    for /f %%v in ('"!VENV_PY!" -c "import fastapi;print(fastapi.__version__)" 2^>nul') do set "FA_VER=%%v"
    echo  [ OK ] FastAPI !FA_VER!，依赖完整
)

:STEP4
echo.

:: ================================================================
::  STEP 4 -- 前端依赖
:: ================================================================
echo  [STEP 4/6] 前端 Node 依赖
echo  --------------------------------------------------------------

if "!NODE_OK!"=="0" goto STEP4_SKIP
if "!PNPM_OK!"=="0" goto STEP4_SKIP

if not exist "!FRONTEND!\node_modules\.bin\vite" (
    echo  [WARN] node_modules 不完整，执行 pnpm install (请等待)...
    cd /d "!FRONTEND!"
    pnpm install --reporter silent
    if errorlevel 1 (
        echo  [FAIL] pnpm install 失败
        echo         请手动: cd frontend ^&^& pnpm install
        set /a ERR+=1
    ) else (
        echo  [ OK ] 前端依赖安装完成
    )
    cd /d "!ROOT!"
) else (
    echo  [ OK ] node_modules 完整
)
goto STEP5

:STEP4_SKIP
echo  [SKIP] Node/pnpm 异常，跳过前端依赖检测
set /a ERR+=1

:STEP5
echo.

:: ================================================================
::  STEP 5 -- 端口占用检测
:: ================================================================
echo  [STEP 5/6] 端口占用检测
echo  --------------------------------------------------------------

set "MYSQL_UP=0"

:: MySQL 3306
set "CHK_PORT=!MYSQL_PORT!"
call :CheckPort
if "!PORT_BUSY!"=="1" (
    echo  [ OK ] MySQL  端口 !MYSQL_PORT! 正在监听 (服务运行中)
    set "MYSQL_UP=1"
) else (
    echo  [FAIL] MySQL  端口 !MYSQL_PORT! 未监听
    echo         请启动 MySQL 服务:  net start MySQL  或  net start MySQL80
    set /a ERR+=1
)

:: API 端口
set "CHK_PORT=!API_PORT!"
call :CheckPort
if "!PORT_BUSY!"=="1" (
    echo  [WARN] API    端口 !API_PORT! 已被占用 (PID=!PORT_PID!)
    echo         可能后端已运行，或需关闭占用进程
    set /a WARN+=1
) else (
    echo  [ OK ] API    端口 !API_PORT! 空闲
)

:: TCP 端口
set "CHK_PORT=!TCP_PORT!"
call :CheckPort
if "!PORT_BUSY!"=="1" (
    echo  [WARN] TCP    端口 !TCP_PORT! 已被占用 (PID=!PORT_PID!)
    set /a WARN+=1
) else (
    echo  [ OK ] TCP    端口 !TCP_PORT! 空闲 (STM32 接入)
)

:: 前端端口
set "CHK_PORT=!FE_PORT!"
call :CheckPort
if "!PORT_BUSY!"=="1" (
    echo  [WARN] 前端   端口 !FE_PORT! 已被占用 (PID=!PORT_PID!)
    echo         Vite 将自动切换到下一可用端口 (5174, 5175...)
    set /a WARN+=1
) else (
    echo  [ OK ] 前端   端口 !FE_PORT! 空闲
)

echo.

:: ================================================================
::  STEP 6 -- 数据库迁移 & 初始化
:: ================================================================
echo  [STEP 6/6] 数据库迁移 ^& 初始化
echo  --------------------------------------------------------------

if "!MYSQL_UP!"=="0" (
    echo  [SKIP] MySQL 未运行，跳过数据库检测
    set /a WARN+=1
    goto SUMMARY
)
if not exist "!VENV_PY!" (
    echo  [SKIP] 虚拟环境异常，跳过数据库检测
    goto SUMMARY
)

:: 用 Python 测试 TCP 连通性（无需 MySQL 客户端）
"!VENV_PY!" -c "import socket,sys; s=socket.socket(); s.settimeout(4); s.connect(('127.0.0.1',%MYSQL_PORT%)); s.close(); print('OK')" > "!TEMP!\traffic_dbping.txt" 2>&1
set /p DB_PING=<"!TEMP!\traffic_dbping.txt"
set "DB_PING=!DB_PING: =!"
if not "!DB_PING!"=="OK" (
    echo  [FAIL] 无法连接 MySQL (!DB_URL!)
    echo         请检查 backend\.env 中 DATABASE_URL 的主机、端口、用户名和密码
    set /a ERR+=1
    goto SUMMARY
)
echo  [ OK ] MySQL 服务器可达

:: 初始化标记（避免每次都重跑 init_db）
set "INIT_MARKER=!BACKEND!\.db_initialized"
if not exist "!INIT_MARKER!" (
    echo  [INFO] 首次运行，执行 init_db.py (建表 + 创建默认 admin)...
    cd /d "!BACKEND!"
    "!VENV_PY!" init_db.py > "!TEMP!\traffic_initdb.txt" 2>&1
    if errorlevel 1 (
        echo  [FAIL] init_db.py 执行失败，输出:
        type "!TEMP!\traffic_initdb.txt"
        set /a ERR+=1
    ) else (
        type "!TEMP!\traffic_initdb.txt"
        echo. > "!INIT_MARKER!"
        echo  [ OK ] 数据库初始化完成
        echo  [!!!]  默认账号: admin   默认密码: admin123   (首次登录须修改)
    )
    cd /d "!ROOT!"
) else (
    echo  [INFO] 执行 alembic upgrade head (检查是否有新迁移)...
    cd /d "!BACKEND!"
    "!ALEMBIC!" upgrade head > "!TEMP!\traffic_alembic.txt" 2>&1
    if errorlevel 1 (
        echo  [WARN] Alembic 迁移返回错误，详细输出:
        type "!TEMP!\traffic_alembic.txt"
        set /a WARN+=1
    ) else (
        echo  [ OK ] 数据库表结构已是最新版本
    )
    cd /d "!ROOT!"
)

:: ================================================================
::  汇总
:: ================================================================
:SUMMARY
echo.
echo  ==============================================================
echo   检测结果：  错误 !ERR! 个    警告 !WARN! 个
echo  ==============================================================
echo.

if !ERR! GTR 0 (
    echo  [FAIL] 存在 !ERR! 个错误，无法启动服务
    echo         请根据上方 [FAIL] 提示逐一修复后重试
    echo.
    pause
    exit /b 1
)

if !WARN! GTR 0 (
    echo  [WARN] 存在 !WARN! 个警告（不影响启动）
    echo.
)

:: ================================================================
::  启动服务
:: ================================================================
echo  即将在独立窗口中启动以下服务：
echo.
echo    后端 FastAPI + TCP Server
echo      REST API  :  http://localhost:!API_PORT!
echo      Swagger   :  http://localhost:!API_PORT!/docs
echo      STM32 TCP :  localhost:!TCP_PORT!
echo.
echo    前端 Vite Dev Server
echo      http://localhost:!FE_PORT!
echo.

set /p "CONFIRM=  按 Enter 启动，输入 n 取消: "
if /i "!CONFIRM!"=="n"  goto ABORT
if /i "!CONFIRM!"=="no" goto ABORT

:: 启动后端
echo.
echo  [INFO] 启动后端服务...
start "Backend :!API_PORT!" cmd /k ^
    "cd /d "!BACKEND!" && ^
    echo. && ^
    echo  ===  后端服务已启动  API=!API_PORT!  TCP=!TCP_PORT!  === && ^
    echo. && ^
    call venv\Scripts\activate.bat && ^
    uvicorn main:app --reload --host 0.0.0.0 --port !API_PORT! --log-level info"

timeout /t 2 /nobreak >nul

:: 启动前端
echo  [INFO] 启动前端开发服务器...
start "Frontend :!FE_PORT!" cmd /k ^
    "cd /d "!FRONTEND!" && ^
    echo. && ^
    echo  ===  前端服务已启动  http://localhost:!FE_PORT!  === && ^
    echo. && ^
    pnpm dev"

:: 等待服务启动再开浏览器
timeout /t 4 /nobreak >nul
echo  [INFO] 正在打开浏览器...
start "" "http://localhost:!FE_PORT!"

echo.
echo  ==============================================================
echo   所有服务已启动！关闭对应窗口即可停止对应服务
echo  ==============================================================
echo.
echo   前端界面  :  http://localhost:!FE_PORT!
echo   API 文档  :  http://localhost:!API_PORT!/docs
echo   STM32 TCP :  localhost:!TCP_PORT!
echo.
echo   默认账号  :  admin     默认密码: admin123
echo   (首次登录须强制修改密码)
echo.
goto END

:ABORT
echo.
echo  已取消
echo.
goto END

:: ================================================================
::  子程序：检测端口占用
::  输入：CHK_PORT
::  输出：PORT_BUSY (0/1)，PORT_PID
:: ================================================================
:CheckPort
set "PORT_BUSY=0"
set "PORT_PID="
for /f "tokens=5" %%p in ('netstat -aon 2^>nul ^| findstr ":%CHK_PORT% " ^| findstr "LISTENING"') do (
    set "PORT_BUSY=1"
    set "PORT_PID=%%p"
)
exit /b 0

:END
endlocal
pause
