@echo off
REM ============================================================================
REM GEXBOT Watchdog - Windows Task Scheduler Setup
REM ============================================================================
REM Creates a scheduled task that runs the watchdog every 1 minute.
REM The watchdog checks all daemon processes and restarts any that crashed.
REM ============================================================================
setlocal enabledelayedexpansion
set "TASK_NAME=GEXBOT Watchdog"
set "SCRIPT_DIR=%~dp0"
set "WATCHDOG_PATH=%SCRIPT_DIR%watchdog.py"
set "PYTHON_EXE=C:\Users\Cameron\AppData\Local\Programs\Python\Python313\python.exe"
set "TEMP_XML=%TEMP%\gexbot_watchdog_task.xml"

if /I "%1"=="--remove" goto REMOVE
if /I "%1"=="--status" goto STATUS
goto INSTALL

:INSTALL
echo.
echo === Installing scheduled task: %TASK_NAME%
echo.
echo Watchdog : %WATCHDOG_PATH%
echo Python   : %PYTHON_EXE%
echo Schedule : Every 1 minute, runs indefinitely
echo.
echo Daemons monitored:
echo   - Zulu (gamma_scraper.py)
echo   - Zero Gamma (zero_gamma_scraper.py)
echo   - Regimebot (tv_screenshot.py)
echo.

REM Remove existing task first
schtasks /End /TN "%TASK_NAME%" >nul 2>&1
schtasks /Delete /TN "%TASK_NAME%" /F >nul 2>&1

REM Create XML task definition
> "%TEMP_XML%" echo ^<?xml version="1.0" encoding="UTF-16"?^>
>> "%TEMP_XML%" echo ^<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task"^>
>> "%TEMP_XML%" echo   ^<RegistrationInfo^>
>> "%TEMP_XML%" echo     ^<Description^>GEXBOT Watchdog - auto-restarts crashed daemons^</Description^>
>> "%TEMP_XML%" echo   ^</RegistrationInfo^>
>> "%TEMP_XML%" echo   ^<Triggers^>
>> "%TEMP_XML%" echo     ^<CalendarTrigger^>
>> "%TEMP_XML%" echo       ^<StartBoundary^>2026-06-29T00:00:00+01:00^</StartBoundary^>
>> "%TEMP_XML%" echo       ^<Enabled^>true^</Enabled^>
>> "%TEMP_XML%" echo       ^<ScheduleByWeek^>
>> "%TEMP_XML%" echo         ^<DaysOfWeek^>
>> "%TEMP_XML%" echo           ^<Monday/^>^<Tuesday/^>^<Wednesday/^>^<Thursday/^>^<Friday/^>^<Saturday/^>^<Sunday/^>
>> "%TEMP_XML%" echo         ^</DaysOfWeek^>
>> "%TEMP_XML%" echo         ^<WeeksInterval^>1^</WeeksInterval^>
>> "%TEMP_XML%" echo       ^</ScheduleByWeek^>
>> "%TEMP_XML%" echo     ^</CalendarTrigger^>
>> "%TEMP_XML%" echo     ^<BootTrigger^>
>> "%TEMP_XML%" echo       ^<Enabled^>true^</Enabled^>
>> "%TEMP_XML%" echo       ^<Delay^>PT2M^</Delay^>
>> "%TEMP_XML%" echo     ^</BootTrigger^>
>> "%TEMP_XML%" echo   ^</Triggers^>
>> "%TEMP_XML%" echo   ^<Principals^>
>> "%TEMP_XML%" echo     ^<Principal id="Author"^>
>> "%TEMP_XML%" echo       ^<LogonType^>InteractiveToken^</LogonType^>
>> "%TEMP_XML%" echo       ^<RunLevel^>HighestAvailable^</RunLevel^>
>> "%TEMP_XML%" echo     ^</Principal^>
>> "%TEMP_XML%" echo   ^</Principals^>
>> "%TEMP_XML%" echo   ^<Settings^>
>> "%TEMP_XML%" echo     ^<Enabled^>true^</Enabled^>
>> "%TEMP_XML%" echo     ^<AllowStartOnDemand^>true^</AllowStartOnDemand^>
>> "%TEMP_XML%" echo     ^<StartWhenAvailable^>true^</StartWhenAvailable^>
>> "%TEMP_XML%" echo     ^<ExecutionTimeLimit^>PT1H^</ExecutionTimeLimit^>
>> "%TEMP_XML%" echo     ^<Priority^>7^</Priority^>
>> "%TEMP_XML%" echo   ^</Settings^>
>> "%TEMP_XML%" echo   ^<Actions Context="Author"^>
>> "%TEMP_XML%" echo     ^<Exec^>
>> "%TEMP_XML%" echo       ^<Command^>%PYTHON_EXE%^</Command^>
>> "%TEMP_XML%" echo       ^<Arguments^>"%WATCHDOG_PATH%"^</Arguments^>
>> "%TEMP_XML%" echo     ^</Exec^>
>> "%TEMP_XML%" echo   ^</Actions^>
>> "%TEMP_XML%" echo ^</Task^>

REM Register the task - set to run every 1 minute via repetition
schtasks /Create /TN "%TASK_NAME%" /XML "%TEMP_XML%" /F
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to create task. Run as Administrator?
    del "%TEMP_XML%" >nul 2>&1
    pause
    exit /b 1
)

REM Set repetition interval to 1 minute
schtasks /Change /TN "%TASK_NAME%" /RI 1 /DU 24:00 >nul 2>&1

del "%TEMP_XML%" >nul 2>&1
echo [SUCCESS] Task created: runs every 1 minute + on startup.
echo.
goto END

:REMOVE
echo.
echo === Removing scheduled task: %TASK_NAME% ===
schtasks /End /TN "%TASK_NAME%" >nul 2>&1
schtasks /Delete /TN "%TASK_NAME%" /F
if %ERRORLEVEL% equ 0 ( echo [SUCCESS] Task removed. ) else ( echo [INFO] Task not found. )
goto END

:STATUS
echo.
echo === Task Status: %TASK_NAME% ===
schtasks /Query /TN "%TASK_NAME%" /V /FO LIST 2>&1
if %ERRORLEVEL% neq 0 ( echo [INFO] Task does not exist. )
goto END

:END
endlocal
