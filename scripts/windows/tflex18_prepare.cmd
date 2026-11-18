@echo off
REM Launch from T-FLEX CAD 18 -> Settings -> User commands -> External application.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tflex18_prepare.ps1" %*
if errorlevel 1 (
  echo T-FLEX Figurine Studio stopped with an error. See the console details.
  pause
)
