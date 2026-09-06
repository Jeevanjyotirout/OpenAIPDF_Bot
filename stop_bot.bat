@echo off
title Stop OpenAIPDF Telegram Bot
echo Stopping any running OpenAIPDF Telegram Bot instances...
powershell -Command "Get-CimInstance Win32_Process | Where-Object { ($_.CommandLine -like '*run_bot.py*' -or $_.CommandLine -like '*bot.py*') -and $_.ProcessId -ne $PID } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; Write-Host ('Stopped bot process with PID ' + $_.ProcessId) }"
echo.
echo OpenAIPDF Telegram Bot stopped.
pause
