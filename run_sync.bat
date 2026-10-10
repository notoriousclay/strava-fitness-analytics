@echo off
cd /d "c:\Users\My PC\strava-fitness-analytics"
echo =================================================== >> sync.log
echo [%DATE% %TIME%] Starting Strava Fitness Sync... >> sync.log
"C:\Users\My PC\AppData\Local\Python\pythoncore-3.14-64\python.exe" sync.py >> sync.log 2>&1
echo [%DATE% %TIME%] Strava Fitness Sync completed with exit code %ERRORLEVEL% >> sync.log
