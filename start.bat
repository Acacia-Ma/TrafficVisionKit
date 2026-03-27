@echo off
setlocal enabledelayedexpansion
chcp 936 >nul 2>&1
title Vehicle Detection System -- Startup Checker

:: ================================================================
::  Directories
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
::  Default ports (overridden from .env below)
:: ================================================================
set "API_PORT=8000"
set "TCP_PORT=9000"
set "FE_PORT=5173"
set "MYSQL_PORT=3306"

set /a ERR=0
set /a WARN=0

cd /d "!ROOT!"
cls

echo.
echo  ==============================================================
echo   Vehicle Detection ^& Counter System
echo   Startup Environment Checker  v1.1
echo  ==============================================================
echo.

:: ================================================================
::  STEP 1  --  Runtime prerequisites
:: ================================================================
echo  [STEP 1/6]  Runtime Prerequisites
echo  --------------------------------------------------------------

:: Python
set "PY_OK=0"
python --version >nul 2>&1
if errorlevel 1 (
    echo  [FAIL] Python not found in PATH
    echo         Install Python 3.10+ from https://python.org
    set /a ERR+=1
) else (
    for /f "tokens=2" %%v in ('python --version 2^>^&1') do set "PY_VER=%%v"
    for /f "tokens=1,2 delims=." %%a in ("!PY_VER!") do (
        set "PY_MAJ=%%a"
        set "PY_MIN=%%b"
    )
    if !PY_MAJ! LSS 3 (
        echo  [FAIL] Python !PY_VER! is too old, need 3.10+
        set /a ERR+=1
    ) else if !PY_MAJ! EQU 3 if !PY_MIN! LSS 10 (
        echo  [WARN] Python !PY_VER!  ^(recommend 3.10+^)
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
    echo  [FAIL] Node.js not found in PATH
    echo         Install Node.js 18+ from https://nodejs.org
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
    echo  [WARN] pnpm not found, trying auto install...
    npm install -g pnpm >nul 2>&1
    pnpm --version >nul 2>&1
    if errorlevel 1 (
        echo  [FAIL] pnpm install failed.  Run manually: npm install -g pnpm
        set /a ERR+=1
    ) else (
        echo  [ OK ] pnpm installed automatically
        set "PNPM_OK=1"
    )
) else (
    for /f %%v in ('pnpm --version 2^>^&1') do set "PNPM_VER=%%v"
    echo  [ OK ] pnpm !PNPM_VER!
    set "PNPM_OK=1"
)

echo.

:: ================================================================
::  STEP 2  --  Config files
:: ================================================================
echo  [STEP 2/6]  Config Files
echo  --------------------------------------------------------------

:: backend/.env
if not exist "!BACKEND!\.env" (
    echo  [WARN] backend\.env missing
    if exist "!BACKEND!\.env.example" (
        copy "!BACKEND!\.env.example" "!BACKEND!\.env" >nul
        echo  [ OK ] Copied from .env.example  ^-^-  EDIT DB PASSWORD / JWT_SECRET_KEY!
        set /a WARN+=1
    ) else (
        echo  [FAIL] Neither .env nor .env.example found in backend\
        set /a ERR+=1
    )
) else (
    echo  [ OK ] backend\.env  exists
)

:: Read ports from .env
if exist "!BACKEND!\.env" (
    for /f "usebackq tokens=1* delims==" %%k in ("!BACKEND!\.env") do (
        if /i "%%k"=="API_PORT"   if not "%%l"=="" set "API_PORT=%%l"
        if /i "%%k"=="TCP_PORT"   if not "%%l"=="" set "TCP_PORT=%%l"
        if /i "%%k"=="DATABASE_URL" set "DB_URL=%%l"
    )
    echo  [INFO] Ports:  API=!API_PORT!  TCP=!TCP_PORT!  Frontend=!FE_PORT!
)

:: frontend/.env.local
if not exist "!FRONTEND!\.env.local" (
    echo  [WARN] frontend\.env.local missing, creating default...
    (
        echo VITE_API_BASE_URL=http://localhost:!API_PORT!
        echo VITE_WS_BASE_URL=ws://localhost:!API_PORT!
        echo VITE_DEFAULT_DEVICE_ID=1
    ) > "!FRONTEND!\.env.local"
    echo  [ OK ] frontend\.env.local  created  ^(localhost:!API_PORT!^)
    set /a WARN+=1
) else (
    echo  [ OK ] frontend\.env.local  exists
)

:: YOLO model
if not exist "!BACKEND!\models\yolov8n.pt" (
    if not exist "!BACKEND!\models" mkdir "!BACKEND!\models"
    echo  [WARN] YOLO model not found: backend\models\yolov8n.pt
    echo         It will be downloaded automatically on first backend start
    set /a WARN+=1
) else (
    for %%f in ("!BACKEND!\models\yolov8n.pt") do set "MSIZ=%%~zf"
    set /a MMB=!MSIZ! / 1048576
    echo  [ OK ] yolov8n.pt  ^(!MMB! MB^)
)

echo.

:: ================================================================
::  STEP 3  --  Python venv & dependencies
:: ================================================================
echo  [STEP 3/6]  Python venv ^& Dependencies
echo  --------------------------------------------------------------

if "!PY_OK!"=="0" (
    echo  [SKIP] Python unavailable
    goto STEP4
)

if not exist "!VENV!" (
    echo  [WARN] venv not found, creating backend\venv...
    python -m venv "!VENV!"
    if errorlevel 1 (
        echo  [FAIL] venv creation failed
        set /a ERR+=1
        goto STEP4
    )
    echo  [ OK ] venv created
)

if not exist "!VENV_PY!" (
    echo  [FAIL] venv broken (python.exe missing). Delete backend\venv and retry.
    set /a ERR+=1
    goto STEP4
)
echo  [ OK ] venv OK: backend\venv

"!VENV_PY!" -c "import fastapi,uvicorn,sqlalchemy,aiomysql,jose,bcrypt" >nul 2>&1
if errorlevel 1 (
    echo  [WARN] Dependencies incomplete, installing requirements.txt...
    "!VENV_PIP!" install -r "!BACKEND!\requirements.txt" -q --no-warn-script-location
    if errorlevel 1 (
        echo  [FAIL] pip install failed.
        echo         Run manually: cd backend ^&^& venv\Scripts\pip install -r requirements.txt
        set /a ERR+=1
    ) else (
        echo  [ OK ] Dependencies installed
    )
) else (
    for /f %%v in ('"!VENV_PY!" -c "import fastapi;print(fastapi.__version__)" 2^>nul') do set "FA_VER=%%v"
    echo  [ OK ] FastAPI !FA_VER!  --  all dependencies OK
)

:STEP4
echo.

:: ================================================================
::  STEP 4  --  Frontend node_modules
:: ================================================================
echo  [STEP 4/6]  Frontend Node Modules
echo  --------------------------------------------------------------

if "!NODE_OK!"=="0" goto STEP4_SKIP
if "!PNPM_OK!"=="0" goto STEP4_SKIP

if not exist "!FRONTEND!\node_modules\.bin\vite" (
    echo  [WARN] node_modules incomplete, running pnpm install...
    cd /d "!FRONTEND!"
    pnpm install --reporter silent
    if errorlevel 1 (
        echo  [FAIL] pnpm install failed.  Run: cd frontend ^&^& pnpm install
        set /a ERR+=1
    ) else (
        echo  [ OK ] Frontend dependencies installed
    )
    cd /d "!ROOT!"
) else (
    echo  [ OK ] node_modules OK
)
goto STEP5

:STEP4_SKIP
echo  [SKIP] Node/pnpm unavailable
set /a ERR+=1

:STEP5
echo.

:: ================================================================
::  STEP 5  --  Port availability
:: ================================================================
echo  [STEP 5/6]  Port Availability
echo  --------------------------------------------------------------

set "MYSQL_UP=0"

:: MySQL
set "CHK_PORT=!MYSQL_PORT!"
call :CheckPort
if "!PORT_BUSY!"=="1" (
    echo  [ OK ] MySQL  port !MYSQL_PORT! is LISTENING  ^(service running^)
    set "MYSQL_UP=1"
) else (
    echo  [FAIL] MySQL  port !MYSQL_PORT! not listening  ^(MySQL service not started^)
    echo         Try:  net start MySQL80   or   net start MySQL
    set /a ERR+=1
)

:: API
set "CHK_PORT=!API_PORT!"
call :CheckPort
if "!PORT_BUSY!"=="1" (
    echo  [WARN] API    port !API_PORT! busy  ^(PID=!PORT_PID!^)  backend may already be running
    set /a WARN+=1
) else (
    echo  [ OK ] API    port !API_PORT! free
)

:: TCP
set "CHK_PORT=!TCP_PORT!"
call :CheckPort
if "!PORT_BUSY!"=="1" (
    echo  [WARN] TCP    port !TCP_PORT! busy  ^(PID=!PORT_PID!^)
    set /a WARN+=1
) else (
    echo  [ OK ] TCP    port !TCP_PORT! free  ^(STM32 endpoint^)
)

:: Frontend
set "CHK_PORT=!FE_PORT!"
call :CheckPort
if "!PORT_BUSY!"=="1" (
    echo  [WARN] FE     port !FE_PORT! busy  ^(PID=!PORT_PID!^)  Vite will pick next available port
    set /a WARN+=1
) else (
    echo  [ OK ] FE     port !FE_PORT! free
)

echo.

:: ================================================================
::  STEP 6  --  Database migration / init
:: ================================================================
echo  [STEP 6/6]  Database Migration ^& Init
echo  --------------------------------------------------------------

if "!MYSQL_UP!"=="0" (
    echo  [SKIP] MySQL not running, skipping DB check
    set /a WARN+=1
    goto SUMMARY
)
if not exist "!VENV_PY!" (
    echo  [SKIP] venv unavailable, skipping DB check
    goto SUMMARY
)

:: TCP reachability test
"!VENV_PY!" -c "import socket,sys;s=socket.socket();s.settimeout(4);s.connect(('127.0.0.1',%MYSQL_PORT%));s.close();print('OK')" > "!TEMP!\td_dbping.txt" 2>&1
set /p DB_PING=<"!TEMP!\td_dbping.txt"
set "DB_PING=!DB_PING: =!"

if not "!DB_PING!"=="OK" (
    echo  [FAIL] Cannot reach MySQL: !DB_URL!
    echo         Check DATABASE_URL in backend\.env
    set /a ERR+=1
    goto SUMMARY
)
echo  [ OK ] MySQL reachable

set "INIT_MARKER=!BACKEND!\.db_initialized"
if not exist "!INIT_MARKER!" (
    echo  [INFO] First run -- executing init_db.py ^(create tables + default admin^)...
    cd /d "!BACKEND!"
    "!VENV_PY!" init_db.py > "!TEMP!\td_initdb.txt" 2>&1
    if errorlevel 1 (
        echo  [FAIL] init_db.py failed:
        type "!TEMP!\td_initdb.txt"
        set /a ERR+=1
    ) else (
        type "!TEMP!\td_initdb.txt"
        echo. > "!INIT_MARKER!"
        echo  [ OK ] Database initialized
        echo  [!!!]  Default account:  admin / admin123  ^(change on first login^)
    )
    cd /d "!ROOT!"
) else (
    echo  [INFO] Running: alembic upgrade head...
    cd /d "!BACKEND!"
    "!ALEMBIC!" upgrade head > "!TEMP!\td_alembic.txt" 2>&1
    if errorlevel 1 (
        echo  [WARN] Alembic returned non-zero:
        type "!TEMP!\td_alembic.txt"
        set /a WARN+=1
    ) else (
        echo  [ OK ] Schema up to date
    )
    cd /d "!ROOT!"
)

:: ================================================================
::  Summary
:: ================================================================
:SUMMARY
echo.
echo  ==============================================================
if !ERR! EQU 0 (
    echo   Result:  Errors=0   Warnings=!WARN!   -- READY TO START
) else (
    echo   Result:  Errors=!ERR!   Warnings=!WARN!   -- CANNOT START
)
echo  ==============================================================
echo.

if !ERR! GTR 0 (
    echo  Fix all [FAIL] items above, then re-run this script.
    echo.
    pause
    exit /b 1
)

echo  Services to be launched in separate windows:
echo.
echo    Backend  FastAPI + TCP
echo      REST API  :  http://localhost:!API_PORT!
echo      Swagger   :  http://localhost:!API_PORT!/docs
echo      STM32 TCP :  localhost:!TCP_PORT!
echo.
echo    Frontend Vite Dev Server
echo      http://localhost:!FE_PORT!
echo.
echo  Default login:  admin / admin123   ^(must change on first login^)
echo.

set /p "GO=  Press Enter to start, type n to cancel:  "
if /i "!GO!"=="n"  goto ABORT
if /i "!GO!"=="no" goto ABORT

:: Start backend
echo.
echo  [INFO] Starting backend...
start "Backend :!API_PORT!" cmd /k ^
    "cd /d "!BACKEND!" && call venv\Scripts\activate.bat && echo. && echo  === Backend started  API=!API_PORT!  TCP=!TCP_PORT! === && echo. && uvicorn main:app --reload --host 0.0.0.0 --port !API_PORT! --log-level info"

timeout /t 2 /nobreak >nul

:: Start frontend
echo  [INFO] Starting frontend dev server...
start "Frontend :!FE_PORT!" cmd /k ^
    "cd /d "!FRONTEND!" && echo. && echo  === Frontend started  http://localhost:!FE_PORT! === && echo. && pnpm dev"

timeout /t 4 /nobreak >nul

:: Open browser
echo  [INFO] Opening browser...
start "" "http://localhost:!FE_PORT!"

echo.
echo  ==============================================================
echo   All services started.  Close the windows to stop them.
echo  ==============================================================
echo.
echo   Frontend  :  http://localhost:!FE_PORT!
echo   API docs  :  http://localhost:!API_PORT!/docs
echo   TCP port  :  !TCP_PORT!  ^(STM32^)
echo.
goto END

:ABORT
echo  Cancelled.
goto END

:: ================================================================
::  Subroutine: check if a port is in use
::  Input:  CHK_PORT
::  Output: PORT_BUSY (0/1), PORT_PID
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