@echo off
:: Luna Bot — Windows Stop Script (Batch Wrapper)
:: This script calls the PowerShell version of the stop script.

setlocal
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File "stop.ps1"
endlocal
pause
