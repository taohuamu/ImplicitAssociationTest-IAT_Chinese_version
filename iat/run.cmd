@echo off
chcp 65001 >nul
rem PsychoPy needs this to avoid an over-long environment variable on Windows
set PSYCHOPYNOPACKAGES=1
set "PY=C:\Users\mahogany\.workbuddy\binaries\python\versions\3.11.9\python.exe"
if not exist "%PY%" set "PY=python"
rem Start the experiment. You will be asked for a participant ID.
"%PY%" "%~dp0run.py" %*
if errorlevel 1 pause
