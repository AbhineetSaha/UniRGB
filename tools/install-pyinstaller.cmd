@echo off
rem Installs PyInstaller with its bootloader compiled on this machine instead of the stock prebuilt one.
rem The stock bootloader is shared with countless other programs, malware included, so antivirus models
rem flag it far more often. Needs a C compiler: Visual Studio Build Tools with the C++ workload.
set PYINSTALLER_COMPILE_BOOTLOADER=1
python -m pip install --force-reinstall --no-cache-dir --no-binary pyinstaller pyinstaller==6.22.3 || exit /b 1
