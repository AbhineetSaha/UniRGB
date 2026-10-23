@echo off
rem Builds dist\UniRGB\ (UniRGB.exe and its _internal folder) and, if Inno Setup is installed,
rem dist\UniRGB-Setup-<version>.exe. Build-time tools: tools\install-pyinstaller.cmd ; winget install JRSoftware.InnoSetup
rem One folder instead of a self-unpacking exe, no UPX and a bootloader compiled here: all three make
rem antivirus programs much less likely to mistake UniRGB for malware.
cd /d "%~dp0.."
rem devlab is a developer tool (virtual devices); it never ships in the app
python -m PyInstaller --noconfirm --onedir --noupx --noconsole --name UniRGB --icon unirgb\ui\logo.ico ^
  --exclude-module devlab --add-data "unirgb\ui;unirgb\ui" UniRGB.py || exit /b 1
echo Built dist\UniRGB\UniRGB.exe
set ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe
if not exist "%ISCC%" set ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe
if not exist "%ISCC%" (echo Inno Setup not found: skipping the installer & exit /b 0)
python tools\fetch_pawnio.py || exit /b 1
"%ISCC%" /Q installer\UniRGB.iss || exit /b 1
echo Built the installer in dist\
