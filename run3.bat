@echo off
rem SET LOGFILE=logfile.txt
rem echo Logging started at %date% %time% > %LOGFILE%

setlocal
cd /d "%~dp0"

call .porto-venv\Scripts\activate.bat
if errorlevel 1 (
    echo Failed to activate the virtual environment.
    exit /b 1
)

if not exist .env (
    echo Missing .env file. Create it before running the bot.
    exit /b 1
)

for /f "usebackq eol=# tokens=1,* delims==" %%A in (".env") do set "%%A=%%B"

pip install -r requirements.txt

rem python web_app.py >> %LOGFILE% 2>&1
python web_app_multiagent.py --demo 3
exit /b %errorlevel%
