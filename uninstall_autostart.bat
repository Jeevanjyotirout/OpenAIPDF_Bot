@echo off
title Remove OpenAIPDF Telegram Bot Auto-Start
echo Removing OpenAIPDF Telegram Bot shortcut from Windows Startup folder...
powershell -Command "Remove-Item ([System.IO.Path]::Combine($env:APPDATA, 'Microsoft\Windows\Start Menu\Programs\Startup\OpenAIPDF_Bot.lnk')) -Force -ErrorAction SilentlyContinue; Write-Host 'Auto-Start Shortcut removed.' -ForegroundColor Green"
pause
