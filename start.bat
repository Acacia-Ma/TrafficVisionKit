@echo off
setlocal enabledelayedexpansion
chcp 936 >nul 2>&1
title Vehicle Detection System -- Startup Checker v1.2

::  ================================================================
::  All paths built directly from %~dp0 to avoid chained !var! bugs
::  ================================================================
set "BACKEND=%~dp0backend"
set "FRONTEND=%~dp0frontend"
set "VENV=%~dp0backend\venv"
set "VENV_PY=%~dp0backend\venv\Scripts\python.exe"
set "VENV_PIP=%~dp0backend\venv\Scripts\pip.exe"
set "ALEMBIC=%~dp0backend\venv\Scripts\alembic.exe"
set "ENV_FILE=%~dp0backend\.env"
set "ENV_EXAMPLE=%~dp0backend\.env.example"
set "FE_ENV=%~dp0frontend\.env.local"
set "YOLO_MODEL=%~dp0backend\models\yolov8n.pt"
set "INIT_MARKER=%~dp0backend\.db_initialized"

set "API_PORT=8000"
set "TCP_PORT=9000"
set "FE_PORT=5173"
set "MYSQL_PORT=3306"
set /a ERR=0
set /a WARN=0

cls
echo.
echo  ==============================================================
echo   Vehicle Detection ^& Counter  /  Startup Checker  v1.2
echo  ==============================================================
echo.

::  ================================================================
::  STEP 1  --  Runtime Prerequisites
::  ================================================================
echo  [STEP 1/6]  Runtime Prerequisites
echo  -------------------------------------------------------

:: ---------- Python ----------
python --version >nul 2>&1
if errorlevel 1 (
    echo  [FAIL] Python not found.  Install 3.10+ from https://python.org
    set /a ERR+=1
    set "PY_OK=0"
    goto CHECK_NODE
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set "PY_VER=%%v"
echo  [ OK ] Python %PY_VER%
set "PY_OK=1"

:CHECK_NODE
:: ---------- Node.js ----------
node --version >nul 2>&1
if errorlevel 1 (
    echo  [FAIL] Node.js not found.  Install 18+ from https://nodejs.org
    set /a ERR+=1
    set "NODE_OK=0"
    goto CHECK_PNPM
)
for /f %%v in ('node --version 2^>^&1') do set "NODE_VER=%%v"
echo  [ OK ] Node.js %NODE_VER%
set "NODE_OK=1"

:CHECK_PNPM
:: ---------- pnpm ----------
pnpm --version >nul 2>&1
if errorlevel 1 (
    echo  [WARN] pnpm not found, installing via npm...
    npm install -g pnpm >nul 2>&1
    pnpm --version >nul 2>&1
    if errorlevel 1 (
        echo  [FAIL] pnpm install failed.  Run: npm install -g pnpm
        set /a ERR+=1
        set "PNPM_OK=0"
        goto STEP2
    )
    echo  [ OK ] pnpm installed
    set "PNPM_OK=1"
    goto STEP2
)
for /f %%v in ('pnpm --version 2^>^&1') do set "PNPM_VER=%%v"
echo  [ OK ] pnpm %PNPM_VER%
set "PNPM_OK=1"

::  ================================================================
::  STEP 2  --  Config Files
::  ================================================================
:STEP2
echo.
echo  [STEP 2/6]  Config Files
echo  -------------------------------------------------------

:: ---------- backend/.env ----------
if not exist "%ENV_FILE%" (
    if exist "%ENV_EXAMPLE%" (
        copy "%ENV_EXAMPLE%" "%ENV_FILE%" >nul
        echo  [ OK ] backend\.env created from .env.example  -- EDIT passwords!
        set /a WARN+=1
    ) else (
        echo  [FAIL] backend\.env missing and no .env.example found
        set /a ERR+=1
        goto ENV_DONE
    )
) else (
    echo  [ OK ] backend\.env exists
)

:: Read ports from .env (simple findstr approach)
for /f "usebackq tokens=1* delims==" %%k in ("%ENV_FILE%") do (
    if /i "%%k"=="API_PORT"   set "API_PORT=%%l"
    if /i "%%k"=="TCP_PORT"   set "TCP_PORT=%%l"
    if /i "%%k"=="DATABASE_URL" set "DB_URL=%%l"
)
echo  [INFO] Ports:  API=%API_PORT%  TCP=%TCP_PORT%  Frontend=%FE_PORT%

:ENV_DONE
:: ---------- frontend/.env.local ----------
if not exist "%FE_ENV%" (
    echo VITE_API_BASE_URL=http://localhost:%API_PORT%  > "%FE_ENV%"
    echo VITE_WS_BASE_URL=ws://localhost:%API_PORT%    >> "%FE_ENV%"
    echo VITE_DEFAULT_DEVICE_ID=1                      >> "%FE_ENV%"
    echo  [ OK ] frontend\.env.local created
    set /a WARN+=1
) else (
    echo  [ OK ] frontend\.env.local exists
)

:: ---------- YOLO model ----------
if not exist "%YOLO_MODEL%" (
    if not exist "%~dp0backend\models" mkdir "%~dp0backend\models"
    echo  [WARN] YOLO model missing: backend\models\yolov8n.pt
    echo         Will be auto-downloaded on first backend start
    set /a WARN+=1
) else (
    for %%f in ("%YOLO_MODEL%") do set /a MODEL_MB=%%~zf / 1048576
    echo  [ OK ] yolov8n.pt  ^(%MODEL_MB% MB^)
)

::  ================================================================
::  STEP 3  --  Python venv + dependencies
::  ================================================================
echo.
echo  [STEP 3/6]  Python venv and Dependencies
echo  -------------------------------------------------------

if "%PY_OK%"=="0" (
    echo  [SKIP] Python unavailable
    goto STEP4
)

:: Check or create venv
if exist "%VENV_PY%" goto VENV_OK

if exist "%VENV%" (
    echo  [WARN] venv exists but python.exe missing - recreating...
    rmdir /s /q "%VENV%"
)
echo  [WARN] Creating venv at backend\venv ...
python -m venv "%VENV%"
if errorlevel 1 (
    echo  [FAIL] venv creation failed
    set /a ERR+=1
    goto STEP4
)
echo  [ OK ] venv created

:VENV_OK
echo  [ OK ] venv OK

:: Check core packages
"%VENV_PY%" -c "import fastapi,uvicorn,sqlalchemy,aiomysql,jose,bcrypt" >nul 2>&1
if errorlevel 1 (
    echo  [WARN] Dependencies incomplete - running pip install...
    "%VENV_PIP%" install -r "%BACKEND%\requirements.txt" -q --no-warn-script-location
    if errorlevel 1 (
        echo  [FAIL] pip install failed.
        echo         Try manually: cd backend ^&^& venv\Scripts\pip install -r requirements.txt
        set /a ERR+=1
        goto STEP4
    )
    echo  [ OK ] Dependencies installed
    goto STEP4
)
for /f %%v in ('"%VENV_PY%" -c "import fastapi;print(fastapi.__version__)" 2^>nul') do set "FA_VER=%%v"
echo  [ OK ] FastAPI %FA_VER% -- all dependencies OK

::  ================================================================
::  STEP 4  --  Frontend node_modules
::  ================================================================
:STEP4
echo.
echo  [STEP 4/6]  Frontend node_modules
echo  -------------------------------------------------------

if "%NODE_OK%"=="0" (
    echo  [SKIP] Node.js unavailable
    set /a ERR+=1
    goto STEP5
)
if "%PNPM_OK%"=="0" (
    echo  [SKIP] pnpm unavailable
    set /a ERR+=1
    goto STEP5
)

if exist "%FRONTEND%\node_modules\.bin\vite" (
    echo  [ OK ] node_modules OK
    goto STEP5
)

echo  [WARN] node_modules incomplete - running pnpm install...
cd /d "%FRONTEND%"
pnpm install --reporter silent
if errorlevel 1 (
    echo  [FAIL] pnpm install failed.  Try: cd frontend ^&^& pnpm install
    set /a ERR+=1
) else (
    echo  [ OK ] Frontend dependencies installed
)
cd /d "%~dp0"

::  ================================================================
::  STEP 5  --  Port availability
::  ================================================================
:STEP5
echo.
echo  [STEP 5/6]  Port Availability
echo  -------------------------------------------------------

:: MySQL 3306
set "CHK_PORT=%MYSQL_PORT%"
call :CheckPort
if "%PORT_BUSY%"=="1" (
    echo  [ OK ] MySQL  port %MYSQL_PORT% LISTENING  ^(service running^)
    set "MYSQL_UP=1"
) else (
    echo  [FAIL] MySQL  port %MYSQL_PORT% not listening
    echo         Start MySQL:  net start MySQL80   or   net start MySQL
    set /a ERR+=1
    set "MYSQL_UP=0"
)

:: API port -- if busy by python, offer to kill it
set "CHK_PORT=%API_PORT%"
call :CheckPort
if "%PORT_BUSY%"=="1" (
    echo  [WARN] API  port %API_PORT% busy  PID=%PORT_PID%
    tasklist /fi "PID eq %PORT_PID%" 2>nul | findstr /i "python" >nul 2>&1
    if not errorlevel 1 (
        echo  [INFO] Old python/uvicorn process detected -- killing PID=%PORT_PID% ...
        taskkill /F /PID %PORT_PID% >nul 2>&1
        echo  [ OK ] Killed.  Port %API_PORT% is now free.
    ) else (
        echo  [WARN] Non-python process on port %API_PORT% -- please free it manually
        set /a WARN+=1
    )
) else (
    echo  [ OK ] API    port %API_PORT% free
)

:: TCP port -- same logic
set "CHK_PORT=%TCP_PORT%"
call :CheckPort
if "%PORT_BUSY%"=="1" (
    echo  [WARN] TCP  port %TCP_PORT% busy  PID=%PORT_PID%
    tasklist /fi "PID eq %PORT_PID%" 2>nul | findstr /i "python" >nul 2>&1
    if not errorlevel 1 (
        echo  [INFO] Old python process on TCP port -- killing PID=%PORT_PID% ...
        taskkill /F /PID %PORT_PID% >nul 2>&1
        echo  [ OK ] Killed.  Port %TCP_PORT% is now free.
    ) else (
        echo  [ OK ] TCP    port %TCP_PORT% free  ^(STM32 endpoint^)
        set /a WARN+=1
    )
) else (
    echo  [ OK ] TCP    port %TCP_PORT% free  ^(STM32 endpoint^)
)

:: Frontend port
set "CHK_PORT=%FE_PORT%"
call :CheckPort
if "%PORT_BUSY%"=="1" (
    echo  [WARN] FE     port %FE_PORT% busy ^(PID=%PORT_PID%^) -- Vite will pick next port
    set /a WARN+=1
) else (
    echo  [ OK ] FE     port %FE_PORT% free
)

::  ================================================================
::  STEP 6  --  Database migration / init
::  ================================================================
echo.
echo  [STEP 6/6]  Database Migration and Init
echo  -------------------------------------------------------

if "%MYSQL_UP%"=="0" (
    echo  [SKIP] MySQL not running
    goto SUMMARY
)
if not exist "%VENV_PY%" (
    echo  [SKIP] venv missing
    goto SUMMARY
)

:: Test TCP connectivity to MySQL
"%VENV_PY%" -c "import socket;s=socket.socket();s.settimeout(4);s.connect(('127.0.0.1',%MYSQL_PORT%));s.close();print('OK')" >"%TEMP%\td_dbping.txt" 2>&1
set /p DB_PING=<"%TEMP%\td_dbping.txt"
if not "%DB_PING%"=="OK" (
    echo  [FAIL] Cannot connect to MySQL -- check DATABASE_URL in backend\.env
    set /a ERR+=1
    goto SUMMARY
)
echo  [ OK ] MySQL reachable

if exist "%INIT_MARKER%" (
    echo  [INFO] Running alembic upgrade head...
    cd /d "%BACKEND%"
    "%ALEMBIC%" upgrade head >"%TEMP%\td_alembic.txt" 2>&1
    if errorlevel 1 (
        echo  [WARN] Alembic returned non-zero:
        type "%TEMP%\td_alembic.txt"
        set /a WARN+=1
    ) else (
        echo  [ OK ] Schema up to date
    )
    cd /d "%~dp0"
    goto SUMMARY
)

echo  [INFO] First run -- init_db.py (create tables + default admin)...
cd /d "%BACKEND%"
"%VENV_PY%" init_db.py >"%TEMP%\td_initdb.txt" 2>&1
if errorlevel 1 (
    echo  [FAIL] init_db.py failed:
    type "%TEMP%\td_initdb.txt"
    set /a ERR+=1
) else (
    type "%TEMP%\td_initdb.txt"
    echo.  >"%INIT_MARKER%"
    echo  [ OK ] DB initialized   login: admin / admin123  ^(change on first login!^)
)
cd /d "%~dp0"

::  ================================================================
::  Summary + Launch
::  ================================================================
:SUMMARY
echo.
echo  ==============================================================
if %ERR% EQU 0 (
    echo   Result:  Errors=0  Warnings=%WARN%  --  READY
) else (
    echo   Result:  Errors=%ERR%  Warnings=%WARN%  --  CANNOT START
)
echo  ==============================================================
echo.

if %ERR% GTR 0 (
    echo  Fix all [FAIL] items above, then re-run this script.
    echo.
    pause
    exit /b 1
)

echo  Services to start in new windows:
echo    Backend  :  http://localhost:%API_PORT%   (API + TCP %TCP_PORT%)
echo    Frontend :  http://localhost:%FE_PORT%
echo    API docs :  http://localhost:%API_PORT%/docs
echo.
echo  Default login:  admin / admin123   (must change on first login)
echo.
set /p "GO=  Press Enter to start, type n to cancel:  "
if /i "%GO%"=="n"  goto ABORT
if /i "%GO%"=="no" goto ABORT

echo.
echo  [INFO] Starting backend...
start "Backend :%API_PORT%" cmd /k "cd /d "%BACKEND%" && call venv\Scripts\activate.bat && echo. && echo  Backend started  API=%API_PORT%  TCP=%TCP_PORT% && echo. && uvicorn main:app --reload --host 0.0.0.0 --port %API_PORT% --log-level info"

timeout /t 2 /nobreak >nul

echo  [INFO] Starting frontend...
start "Frontend :%FE_PORT%" cmd /k "cd /d "%FRONTEND%" && echo. && echo  Frontend started  http://localhost:%FE_PORT% && echo. && pnpm dev"

timeout /t 4 /nobreak >nul
echo  [INFO] Opening browser...
start "" "http://localhost:%FE_PORT%"

echo.
echo  ==============================================================
echo   All services started.  Close windows to stop.
echo  ==============================================================
echo.
echo   Frontend  :  http://localhost:%FE_PORT%
echo   API docs  :  http://localhost:%API_PORT%/docs
echo   TCP       :  localhost:%TCP_PORT%
echo.
goto END

:ABORT
echo  Cancelled.
goto END

:: ================================================================
::  Subroutine -- check if a port is in use
::  Input:  CHK_PORT
::  Output: PORT_BUSY (0=free 1=busy), PORT_PID
:: ================================================================
:CheckPort
set "PORT_BUSY=0"
set "PORT_PID="
netstat -aon 2>nul | findstr ":%CHK_PORT% " | findstr "LISTENING" >"%TEMP%\td_port.txt"
for /f "tokens=5" %%p in (%TEMP%\td_port.txt) do (
    set "PORT_BUSY=1"
    set "PORT_PID=%%p"
)
del "%TEMP%\td_port.txt" 2>nul
exit /b 0

:END
endlocal
pause