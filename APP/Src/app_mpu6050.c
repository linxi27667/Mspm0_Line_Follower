/**
 * @file    app_mpu6050.c
 * @brief   MPU6050 硬件绑定与实例化
 */
#include "app_mpu6050.h"
#include "app_sw_i2c.h"
#include "bsp_common.h"

/* ================= 1. 硬件底层函数 (HW_ 前缀) ================= */

static void HW_Delay_ms(uint32_t ms)
{
    BSP_Delay_ms(ms);
}

/* ================= 2. 实例化并依赖注入 ================= */

bsp_mpu_t App_MPU = {
    .bus      = &App_I2C_Bus_1,
    .dev_addr = 0x68,
    .Delay_ms = HW_Delay_ms
};

void App_MPU6050_System_Init(void)
{
    BSP_MPU6050_Init_Device(&App_MPU);
}
