@echo off
chcp 65001 >nul
rem Open config.yaml in Notepad
start "" notepad "%~dp0config.yaml"
