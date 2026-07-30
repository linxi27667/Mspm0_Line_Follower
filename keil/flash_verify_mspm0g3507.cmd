@echo off
setlocal
set "JLINK_EXE=C:\Program Files\SEGGER\JLink_V958\JLink.exe"
set "SCRIPT=%~dp0flash_verify_mspm0g3507.jlink"

if not exist "%JLINK_EXE%" (
  echo ERROR: J-Link V9.58 was not found.
  exit /b 1
)

"%JLINK_EXE%" -device MSPM0G3507 -if SWD -speed 100 -autoconnect 1 -ExitOnError 1 -CommanderScript "%SCRIPT%"
exit /b %ERRORLEVEL%
