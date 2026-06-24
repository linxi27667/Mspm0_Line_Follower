/**
 * @file    app_key.c
 * @brief   按键硬件绑定实现（MSPM0G3507）
 */
#include "app_key.h"
#include "ti_msp_dl_config.h"
#include "bsp_common.h"

/* PINCM 索引定义（MSPM0G3507 引脚映射） */
#define KEY1_PINCM  12  /* PB0 */
#define KEY2_PINCM  13  /* PB1 */
#define KEY3_PINCM  15  /* PB2 */
#define KEY4_PINCM  1   /* PA0 */

/* ================= 1. 硬件底层函数 (HW_ 前缀) ================= */

static void HW_GPIO_Config(void)
{
    /* 每个按键引脚单独配置为上拉输入 + 滞回 */
    DL_GPIO_initDigitalInputFeatures(KEY1_PINCM,
        DL_GPIO_INVERSION_DISABLE, DL_GPIO_RESISTOR_PULL_UP,
        DL_GPIO_HYSTERESIS_ENABLE, DL_GPIO_WAKEUP_DISABLE);
    DL_GPIO_initDigitalInputFeatures(KEY2_PINCM,
        DL_GPIO_INVERSION_DISABLE, DL_GPIO_RESISTOR_PULL_UP,
        DL_GPIO_HYSTERESIS_ENABLE, DL_GPIO_WAKEUP_DISABLE);
    DL_GPIO_initDigitalInputFeatures(KEY3_PINCM,
        DL_GPIO_INVERSION_DISABLE, DL_GPIO_RESISTOR_PULL_UP,
        DL_GPIO_HYSTERESIS_ENABLE, DL_GPIO_WAKEUP_DISABLE);
    DL_GPIO_initDigitalInputFeatures(KEY4_PINCM,
        DL_GPIO_INVERSION_DISABLE, DL_GPIO_RESISTOR_PULL_UP,
        DL_GPIO_HYSTERESIS_ENABLE, DL_GPIO_WAKEUP_DISABLE);
}

/* ================= 2. 对象实例化与引脚拼装 ================= */

bsp_key_t app_keys[BSP_KEY_NUM] = {
    [0] = { .port = KEY1_PORT, .pin = KEY1_PIN, .judge = BSP_KEY_JUDGE_IDLE, .state = KEY_RELEASE },
    [1] = { .port = KEY2_PORT, .pin = KEY2_PIN, .judge = BSP_KEY_JUDGE_IDLE, .state = KEY_RELEASE },
    [2] = { .port = KEY3_PORT, .pin = KEY3_PIN, .judge = BSP_KEY_JUDGE_IDLE, .state = KEY_RELEASE },
    [3] = { .port = KEY4_PORT, .pin = KEY4_PIN, .judge = BSP_KEY_JUDGE_IDLE, .state = KEY_RELEASE },
};

/* ================= 3. 对外业务切入点 ================= */

void App_Key_System_Init(void)
{
    HW_GPIO_Config();
    BSP_Key_Init(app_keys, BSP_KEY_NUM);
}

void App_Key_Scan_Task(void)
{
    BSP_Key_Scan(app_keys, BSP_KEY_NUM);
}

bsp_key_event_t App_Key_GetEvent(uint8_t index)
{
    if (index >= BSP_KEY_NUM) return BSP_KEY_EVENT_IDLE;
    return BSP_Key_GetEvent(&app_keys[index]);
}
