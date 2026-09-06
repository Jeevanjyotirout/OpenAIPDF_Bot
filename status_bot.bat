@echo off
title OpenAIPDF Telegram Bot Status
echo Checking OpenAIPDF Telegram Bot status...
echo.
powershell -Command "$procs = Get-CimInstance Win32_Process | Where-Object { ($_.CommandLine -like '*run_bot.py*' -or $_.CommandLine -like '*bot.py*') -and $_.ProcessId -ne $PID }; if ($procs) { Write-Host '>>> BOT IS RUNNING LIVE in background!' -ForegroundColor Green; $procs | Select-Object ProcessId, CommandLine | Format-Table -AutoSize } else { Write-Host '>>> BOT IS NOT RUNNING.' -ForegroundColor Yellow; Write-Host 'To start it, double-click start_bot_background.bat' }"
echo.
pause
