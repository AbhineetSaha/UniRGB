@echo off
rem Restores the start modes recorded on 2026-10-19 before UniRGB changed them.
net session >nul 2>&1 || (echo Please right-click and "Run as administrator". & pause & exit /b 1)
for %%S in ("Razer Chroma SDK Diagnostic Service" "Razer Chroma SDK Server" "Razer Chroma SDK Service" "Razer Game Manager Service 3" "RazerExperienceService" "RGS" "Mystic_Light_Service" "LightKeeperService" "MSI_Center_Service" "MSI_Case_Service") do (
  sc config %%S start= auto >nul
  sc start %%S >nul 2>&1
  echo   %%~S: Automatic, started
)
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v RazerAppEngine /t REG_SZ /f /d "\"C:\Program Files\Razer\RazerAppEngine\RazerAppEngine.exe\" --url-params=apps=synapse,chroma-app --launch-force-hidden=synapse,chroma-app --autoStart=1" >nul
echo Razer Synapse startup entry restored. Sign out and back in (or reboot) to launch it.
pause
