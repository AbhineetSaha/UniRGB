@echo off
rem Builds dist\UniRGB.exe (standalone, no Python needed to run it).
rem PyInstaller is a build-time tool only: pip install pyinstaller
cd /d "%~dp0.."
python -m PyInstaller --noconfirm --onefile --noconsole --name UniRGB ^
  --add-data "unirgb\ui;unirgb\ui" UniRGB.py || exit /b 1
echo Built dist\UniRGB.exe
