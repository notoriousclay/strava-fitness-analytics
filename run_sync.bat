@echo off
cd /d "c:\Users\My PC\strava-fitness-analytics"
echo =================================================== >> sync.log
echo [%DATE% %TIME%] Starting Strava & Google Fit Sync... >> sync.log
"C:\Users\My PC\AppData\Local\Python\pythoncore-3.14-64\python.exe" sync.py >> sync.log 2>&1
"C:\Users\My PC\AppData\Local\Python\pythoncore-3.14-64\python.exe" sync_google_fit.py >> sync.log 2>&1
echo [%DATE% %TIME%] Sync completed with exit code %ERRORLEVEL% >> sync.log
