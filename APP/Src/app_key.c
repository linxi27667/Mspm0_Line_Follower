/**
 * @file    app_key.c
 * @brief   按键硬件绑定实现（MSPM0G3507）
 * @note    GPIO引脚和上拉电阻由SysConfig配置，无需手动初始化
 */
#include "app_key.h"
#include "app_common.h"

/* ================= 1. 硬件底层函数 (HW_ 前缀) ================= */

static uint8_t HW_Pin_Read(void *port, uint32_t pin)
{
    if (port == NULL) return KEY_RELEASE;
    return GPIO_ReadPin((GPIO_Regs *)port, pin);
}

/* ================= 2. 对象实例化与引脚拼装 ================= */

bsp_key_t Key_Devices[BSP_KEY_NUM] = {
    [0] = { .port = KEY1_PORT, .pin = KEY1_PIN, .Pin_Read = HW_Pin_Read, .judge = BSP_KEY_JUDGE_IDLE, .state = KEY_RELEASE },
    [1] = { .port = KEY2_PORT, .pin = KEY2_PIN, .Pin_Read = HW_Pin_Read, .judge = BSP_KEY_JUDGE_IDLE, .state = KEY_RELEASE },
    [2] = { .port = KEY3_PORT, .pin = KEY3_PIN, .Pin_Read = HW_Pin_Read, .judge = BSP_KEY_JUDGE_IDLE, .state = KEY_RELEASE },
    [3] = { .port = KEY4_PORT, .pin = KEY4_PIN, .Pin_Read = HW_Pin_Read, .judge = BSP_KEY_JUDGE_IDLE, .state = KEY_RELEASE },
};

/* ================= 3. 对外业务切入点 ================= */

void App_Key_Init(void)
{
    Bsp_Key_Init(Key_Devices, BSP_KEY_NUM);
}

void Key_Scan_Task(void)
{
    Bsp_Key_Scan(Key_Devices, BSP_KEY_NUM);
}

bsp_key_event_t Key_GetEvent(uint8_t index)
{
    if (index >= BSP_KEY_NUM) return BSP_KEY_EVENT_IDLE;
    return Bsp_Key_GetEvent(&Key_Devices[index]);
}
