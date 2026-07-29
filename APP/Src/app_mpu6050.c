/**
 * @file    app_mpu6050.c
 * @brief   MPU6050硬件绑定实现（MSPM0G3507）
 */
#include "app_mpu6050.h"
#include "comm_sw_i2c.h"
#include "bsp_common.h"
#include "ti_msp_dl_config.h"

/* ================= 1. 硬件底层函数 (HW_ 前缀) ================= */

static void HW_Delay_ms(uint32_t ms)
{
    BSP_Delay_ms(ms);
}

/* ================= 2. 对象实例化与引脚拼装 ================= */

bsp_mpu_t App_MPU = {
    .bus      = &App_I2C_Bus_1,
    .dev_addr = MPU6050_DEV_ADDR,
    .Delay_ms = HW_Delay_ms
};

/* ================= 3. 对外业务切入点 ================= */

void App_MPU6050_System_Init(void)
{
    BSP_MPU6050_Init_Device(&App_MPU);
}

void App_MPU6050_Read_Data(void)
{
    BSP_MPU6050_Read_Data(&App_MPU);
}
