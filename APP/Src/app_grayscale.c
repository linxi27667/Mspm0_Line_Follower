/**
 * @file    app_grayscale.c
 * @brief   八路灰度传感器硬件绑定实现（MSPM0G3507）
 */
#include "app_grayscale.h"
#include "app_common.h"
#include "ti_msp_dl_config.h"

/* ================= 1. 硬件底层函数 (HW_ 前缀) ================= */

static void HW_Gray_Init(void)
{
    /* GPIO和ADC由SysConfig配置，此处预留 */
}

static void HW_Gray_Gpio_Write(void *port, uint32_t pin, uint8_t level)
{
    if (port == NULL) return;
    GPIO_WritePin((GPIO_Regs *)port, pin, level);
}

static uint16_t HW_Gray_ADC_Read(void)
{
    /* 启动ADC软件转换 */
    DL_ADC12_startConversion(GRAY_ADC_INST);
    /* 等待转换完成 — 轮询SC位（转换开始时置位，完成时清零），加超时保护防止卡死 */
    uint32_t timeout = 100000u;
    while (DL_ADC12_isConversionStarted(GRAY_ADC_INST)) {
        if (--timeout == 0) break;
    }
    /* 读取结果（12位，0~4095） */
    return DL_ADC12_getMemResult(GRAY_ADC_INST, DL_ADC12_MEM_IDX_0);
}

static uint32_t HW_Gray_GetTick(void)
{
    return Bsp_GetTick();
}

/* ================= 2. 对象实例化与引脚拼装 ================= */

bsp_grayscale_t Grayscale_Sensor = {
    .ad0        = {GRAY_AD0_PORT, GRAY_AD0_PIN},
    .ad1        = {GRAY_AD1_PORT, GRAY_AD1_PIN},
    .ad2        = {GRAY_AD2_PORT, GRAY_AD2_PIN},
    .settle_ms  = BSP_GRAY_SETTLE_MS,

    .Init       = HW_Gray_Init,
    .Gpio_Write = HW_Gray_Gpio_Write,
    .ADC_Read   = HW_Gray_ADC_Read,
    .GetTick    = HW_Gray_GetTick
};

/* ================= 3. 对外业务切入点 ================= */

void App_Grayscale_Init(void)
{
    Bsp_Grayscale_Init_Device(&Grayscale_Sensor);
}

void Grayscale_Update(void)
{
    Bsp_Grayscale_Update(&Grayscale_Sensor);
}

void Grayscale_Calibrate_White(void)
{
    Bsp_Grayscale_Calibrate_White(&Grayscale_Sensor);
}

void Grayscale_Calibrate_Black(void)
{
    Bsp_Grayscale_Calibrate_Black(&Grayscale_Sensor);
}
