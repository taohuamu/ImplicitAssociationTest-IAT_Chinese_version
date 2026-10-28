@echo off
chcp 65001 >nul
rem PsychoPy needs this to avoid an over-long environment variable on Windows
set PSYCHOPYNOPACKAGES=1
set "PY=C:\Users\mahogany\.workbuddy\binaries\python\versions\3.11.9\python.exe"
if not exist "%PY%" set "PY=python"
rem Score all csv files under data\ and write processed.csv
"%PY%" "%~dp0score.py"
echo.
pause
