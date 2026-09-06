@echo off
title Start OpenAIPDF Telegram Bot in Background
cd /d "%~dp0"
echo Starting OpenAIPDF Telegram Bot (@OpenAIPDF_bot) silently in the background...
wscript.exe "%~dp0run_bot_silent.vbs"
timeout /t 2 /nobreak >nul
echo.
echo ============================================================
echo   OpenAIPDF Telegram Bot is now running in the BACKGROUND!
echo   Handle: @OpenAIPDF_bot
echo   No terminal window will remain open.
echo   To check status: run status_bot.bat
echo   To stop the bot: run stop_bot.bat
echo ============================================================
echo.
pause
