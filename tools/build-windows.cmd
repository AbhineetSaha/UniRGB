@echo off
rem Builds dist\UniRGB.exe (standalone) and, if Inno Setup is installed, dist\UniRGB-Setup-<version>.exe.
rem Build-time tools only: pip install pyinstaller ; winget install JRSoftware.InnoSetup
cd /d "%~dp0.."
python -m PyInstaller --noconfirm --onefile --noconsole --name UniRGB ^
  --add-data "unirgb\ui;unirgb\ui" UniRGB.py || exit /b 1
echo Built dist\UniRGB.exe
set ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe
if not exist "%ISCC%" set ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe
if not exist "%ISCC%" (echo Inno Setup not found: skipping the installer & exit /b 0)
"%ISCC%" /Q installer\UniRGB.iss || exit /b 1
echo Built the installer in dist\
