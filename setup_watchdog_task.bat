@echo off
REM Create scheduled task to run GEXBOT watchdog every 2 minutes
schtasks /create /tn "GEXBOT Watchdog" /tr "C:\Users\Cameron\AppData\Local\Programs\Python\Python313\pythonw.exe D:\MyPythonProjects_2\GEXBOT\watchdog.py" /sc MINUTE /mo 2 /st 00:00 /it /f
echo Task created. Run manually: pythonw D:\MyPythonProjects_2\GEXBOT\watchdog.py
