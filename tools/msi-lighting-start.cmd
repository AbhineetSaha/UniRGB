@echo off
rem Restarts MSI Center's lighting after direct control. Run as administrator.
net session >nul 2>&1 || (echo Please right-click and "Run as administrator". & pause & exit /b 1)
sc start LightKeeperService
sc start Mystic_Light_Service
echo LEDKeeper2 is relaunched by MSI Center (or at next sign-in).
echo MSI Center will re-apply its own lighting profile.
pause
