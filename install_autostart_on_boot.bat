@echo off
title Install OpenAIPDF Telegram Bot Auto-Start on Windows Boot
echo ============================================================
echo   Installing Auto-Start for OpenAIPDF Telegram Bot...
echo ============================================================
cd /d "%~dp0"

powershell -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut([System.IO.Path]::Combine($env:APPDATA, 'Microsoft\Windows\Start Menu\Programs\Startup\OpenAIPDF_Bot.lnk')); $s.TargetPath = [System.IO.Path]::Combine((Get-Location).Path, 'run_bot_silent.vbs'); $s.WorkingDirectory = (Get-Location).Path; $s.Save(); Write-Host 'Auto-Start Shortcut successfully created in Windows Startup folder!' -ForegroundColor Green"

echo.
echo ============================================================
echo   Done! The Telegram bot will now automatically start
echo   silently in the background every time you turn on your PC!
echo   You never need to manually start it again.
echo ============================================================
echo.
pause
