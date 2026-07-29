/**
 * @file    app_led.c
 * @brief   LED硬件绑定实现（MSPM0G3507）
 */
#include "app_led.h"
#include "ti_msp_dl_config.h"

/* ================= 1. 硬件底层函数 (HW_ 前缀) ================= */

static void HW_Gpio_Write(void *port, uint32_t pin, uint8_t level)
{
    if (port == NULL) return;
    if (level) {
        DL_GPIO_setPins((GPIO_Regs *)port, pin);
    } else {
        DL_GPIO_clearPins((GPIO_Regs *)port, pin);
    }
}

/* ================= 2. 对象实例化与引脚拼装 ================= */

led_t app_leds[BSP_LED_NUM] = {
    {LED1_PORT, LED1_PIN, 0, HW_Gpio_Write},
    {LED2_PORT, LED2_PIN, 0, HW_Gpio_Write},
    {LED3_PORT, LED3_PIN, 0, HW_Gpio_Write},
    {LED4_PORT, LED4_PIN, 0, HW_Gpio_Write},
    {GPIOA, DL_GPIO_PIN_0, 0, HW_Gpio_Write},
    {GPIOA, DL_GPIO_PIN_1, 0, HW_Gpio_Write},
    {GPIOA, DL_GPIO_PIN_2, 0, HW_Gpio_Write},
    {GPIOA, DL_GPIO_PIN_3, 0, HW_Gpio_Write},
};

/* ================= 3. 对外业务切入点 ================= */

void App_LED_System_Init(void)
{
    BSP_Led_Init(app_leds);
}

void App_LED_On(uint8_t index)
{
    if (index < BSP_LED_NUM) BSP_Led_On(&app_leds[index]);
}

void App_LED_Off(uint8_t index)
{
    if (index < BSP_LED_NUM) BSP_Led_Off(&app_leds[index]);
}
