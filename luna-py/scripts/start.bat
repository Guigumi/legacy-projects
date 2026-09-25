@echo off
:: Luna Bot — Windows Starter Script (Batch Wrapper)
:: This script calls the PowerShell version of the starter script.

setlocal
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File "start.ps1"
endlocal
pause
