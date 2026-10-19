@echo off
rem Starts UniRGB without a console window. Use the Quit button in the app to stop it.
cd /d "%~dp0"
start "" pythonw -m unirgb %*
