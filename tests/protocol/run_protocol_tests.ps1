$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$testExe = Join-Path $env:TEMP "writer_robot_protocol_tests.exe"
$cloudTestExe = Join-Path $env:TEMP "writer_robot_cloud_state_tests.exe"

& gcc `
    -std=c11 `
    -Wall `
    -Wextra `
    -Werror `
    -pedantic `
    -static `
    "-I$projectRoot\BSP\Inc" `
    (Join-Path $PSScriptRoot "test_writer_protocol.c") `
    (Join-Path $projectRoot "BSP\Src\bsp_esp_at.c") `
    (Join-Path $projectRoot "BSP\Src\bsp_mqtt.c") `
    (Join-Path $projectRoot "BSP\Src\bsp_writer_protocol.c") `
    (Join-Path $projectRoot "BSP\Src\bsp_writer_job.c") `
    -o $testExe

if ($LASTEXITCODE -ne 0) {
    throw "Protocol test compilation failed with exit code $LASTEXITCODE"
}

& $testExe
if ($LASTEXITCODE -ne 0) {
    throw "Protocol tests failed with exit code $LASTEXITCODE"
}

& gcc `
    -std=c11 `
    -Wall `
    -Wextra `
    -Werror `
    -pedantic `
    -static `
    -ffunction-sections `
    -fdata-sections `
    "-I$projectRoot\TASK" `
    "-I$projectRoot\APP\Inc" `
    "-I$projectRoot\BSP\Inc" `
    "-I$projectRoot\COMM\Inc" `
    "-I$projectRoot\RTT EasyLog\RTT_easylog\easylogger\inc" `
    (Join-Path $PSScriptRoot "test_writer_cloud_state.c") `
    (Join-Path $projectRoot "BSP\Src\bsp_esp_at.c") `
    (Join-Path $projectRoot "BSP\Src\bsp_mqtt.c") `
    (Join-Path $projectRoot "BSP\Src\bsp_writer_protocol.c") `
    (Join-Path $projectRoot "BSP\Src\bsp_writer_job.c") `
    "-Wl,--gc-sections" `
    -o $cloudTestExe

if ($LASTEXITCODE -ne 0) {
    throw "Writer cloud state test compilation failed with exit code $LASTEXITCODE"
}

& $cloudTestExe
if ($LASTEXITCODE -ne 0) {
    throw "Writer cloud state tests failed with exit code $LASTEXITCODE"
}
