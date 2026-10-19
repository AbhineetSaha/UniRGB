@echo off
rem Stops Razer Synapse and MSI Center from starting with Windows. Nothing is uninstalled.
rem Undo everything with vendor-autostart-restore.cmd (also run as administrator).
net session >nul 2>&1 || (echo Please right-click and "Run as administrator". & pause & exit /b 1)
set BK=%LOCALAPPDATA%\UniRGB\vendor-autostart-backup
if not exist "%BK%" mkdir "%BK%"
echo Backing up the Razer startup entry to %BK%
reg export "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" "%BK%\run-key.reg" /y >nul
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v RazerAppEngine /f
for %%S in ("Razer Chroma SDK Diagnostic Service" "Razer Chroma SDK Server" "Razer Chroma SDK Service" "Razer Game Manager Service 3" "RazerExperienceService" "RGS" "Mystic_Light_Service" "LightKeeperService" "MSI_Center_Service" "MSI_Case_Service") do (
  sc config %%S start= demand >nul
  sc stop %%S >nul 2>&1
  echo   %%~S: set to Manual and stopped
)
taskkill /F /IM RazerAppEngine.exe >nul 2>&1
taskkill /F /IM LEDKeeper2.exe >nul 2>&1
echo.
echo Done. Razer Synapse and MSI Center will no longer start with Windows.
pause
