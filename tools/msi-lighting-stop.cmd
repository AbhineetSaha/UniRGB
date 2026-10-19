@echo off
rem Temporarily stops MSI Center's lighting so UniRGB can drive the Mystic Light controller directly.
rem Run as administrator. Nothing is uninstalled or disabled: the services stay "Automatic" and
rem come back on the next reboot, or immediately with msi-lighting-start.cmd.
net session >nul 2>&1 || (echo Please right-click and "Run as administrator". & pause & exit /b 1)
echo Stopping MSI Mystic Light lighting...
sc stop Mystic_Light_Service
sc stop LightKeeperService
taskkill /F /IM LEDKeeper2.exe
echo.
echo Done. In UniRGB press Rescan; the MSI entry becomes controllable.
pause
