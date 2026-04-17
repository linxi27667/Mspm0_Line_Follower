/**
 * @file    app_key.c
 * @brief   按键硬件绑定与初始化（MSPM0G3507）
 */
#include "app_key.h"
#include "main.h"
#include "bsp_common.h"

/* ================= 1. 硬件底层函数 ================= */

static void HW_GPIO_Config(void)
{
    DL_GPIO_initDigitalInputFeatures(GPIOB,
        DL_GPIO_PIN_0 | DL_GPIO_PIN_1 | DL_GPIO_PIN_2,
        DL_GPIO_INPUT_PULL_UP | DL_GPIO_INPUT_HYSTERESIS);

    DL_GPIO_initDigitalInputFeatures(GPIOA,
        DL_GPIO_PIN_0,
        DL_GPIO_INPUT_PULL_UP | DL_GPIO_INPUT_HYSTERESIS);
}

/* ================= 2. 对象实例化与引脚拼装 ================= */

bsp_key_t app_keys[BSP_KEY_NUM] = {
    [0] = { .port = GPIOB, .pin = DL_GPIO_PIN_0, .judge = BSP_KEY_JUDGE_IDLE, .state = KEY_RELEASE },
    [1] = { .port = GPIOB, .pin = DL_GPIO_PIN_1, .judge = BSP_KEY_JUDGE_IDLE, .state = KEY_RELEASE },
    [2] = { .port = GPIOB, .pin = DL_GPIO_PIN_2, .judge = BSP_KEY_JUDGE_IDLE, .state = KEY_RELEASE },
    [3] = { .port = GPIOA, .pin = DL_GPIO_PIN_0, .judge = BSP_KEY_JUDGE_IDLE, .state = KEY_RELEASE },
};

/* ================= 3. 对外业务切入点 ================= */

void App_Key_System_Init(void)
{
    HW_GPIO_Config();
    BSP_Key_Init();
}

void App_Key_Scan_Task(void)
{
    BSP_Key_Scan(app_keys);
}
