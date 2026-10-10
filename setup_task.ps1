$TaskName = "StravaFitnessSync"
$ScriptPath = "c:\Users\My PC\strava-fitness-analytics\run_sync.bat"
$WorkingDirectory = "c:\Users\My PC\strava-fitness-analytics"

# Define Action
$Action = New-ScheduledTaskAction -Execute $ScriptPath -WorkingDirectory $WorkingDirectory

# Define Trigger (Daily at 8:00 PM / 20:00)
$Trigger = New-ScheduledTaskTrigger -Daily -At 8:00PM

# Define Settings (Allow execution on demand, run if missed, don't stop if on battery)
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

# Register or update task
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description "Daily sync of Strava activities to BigQuery at 8:00 PM"

Write-Host "✅ Scheduled Task '$TaskName' registered successfully for 8:00 PM daily."
