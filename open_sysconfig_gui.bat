@echo off
rem 启动 SysConfig 图形化界面加载当前项目的 TI_moban.syscfg
rem 双击此文件即可打开 SysConfig GUI

set SYSCONFIG_DIR=E:\MCU\MSPM0\sysconfig
set SDK_ROOT=E:\MCU\MSPM0\m0_sdk\mspm0_sdk_1_30_00_03
set PROJ_DIR=%~dp0
set SYSCFG_FILE=%PROJ_DIR%TI_moban.syscfg

echo Starting SysConfig GUI...
echo   SysConfig: %SYSCONFIG_DIR%
echo   SDK:       %SDK_ROOT%
echo   Config:    %SYSCFG_FILE%

start "" "%SYSCONFIG_DIR%\nw\nw.exe" "%SYSCONFIG_DIR%" --compiler keil -s "%SDK_ROOT%\.metadata\product.json" "%SYSCFG_FILE%"
