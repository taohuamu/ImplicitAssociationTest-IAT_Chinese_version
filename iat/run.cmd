@echo off
chcp 65001 >nul
rem 关闭 PsychoPy 对第三方包目录的处理，避免环境变量过长导致启动失败
set PSYCHOPYNOPACKAGES=1
set "PY=C:\Users\mahogany\.workbuddy\binaries\python\versions\3.11.9\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" "%~dp0run.py" %*
if errorlevel 1 pause
