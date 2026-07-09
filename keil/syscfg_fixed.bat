@echo off
rem 修复版 syscfg.bat — 添加 --device 参数解决 "Missing argument" 错误
rem 原版位置: E:\MCU\MSPM0\m0_sdk\mspm0_sdk_1_30_00_03\tools\keil\syscfg.bat

set SYSCFG_PATH="E:\MCU\MSPM0\sysconfig\sysconfig_cli.bat"

if not exist "%SYSCFG_PATH%" (
    echo.
    echo Couldn't find Sysconfig Tool %SYSCFG_PATH%
    echo "Update the file located at <sdk path>/tools/keil/syscfg.bat"
    echo.
    exit
)

echo Using Sysconfig Tool from %SYSCFG_PATH%
echo "Update the file located at <sdk path>/tools/keil/syscfg.bat to use a different version"

set PROJ_DIR=%~1
set PROJ_DIR=%PROJ_DIR:'=%

set SYSCFG_FILE=%~2
set SYSCFG_FILE=%SYSCFG_FILE:'=%

:: Search for the root of the SDK by going up one directory
:: However, if we don't find it after 20 times then give up
set SDK_ROOT=%PROJ_DIR%
set iter=0
:up_one
if exist "%SDK_ROOT%\.metadata\product.json" (
    goto found
) else if %iter% geq 20 (
	@echo "Couldn't find .metadata\product.json, using fallback SDK path"
	set SDK_ROOT=E:\MCU\MSPM0\m0_sdk\mspm0_sdk_1_30_00_03
) else (
	set /a iter=%iter%+1
	set SDK_ROOT=%SDK_ROOT%..\
	goto up_one
)
:found

rem 关键修复: 添加 --device/--package/--part 参数 (CLI 不会从 .syscfg 的 @cliArgs 行读取)
%SYSCFG_PATH% -o "%PROJ_DIR%.." -s "%SDK_ROOT%\.metadata\product.json" --device MSPM0G350X --package "LQFP-64(PM)" --part Default --compiler keil "%PROJ_DIR%..\%SYSCFG_FILE%"
