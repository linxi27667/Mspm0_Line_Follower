/**
 * @file    app_led.c
 * @brief   LED 硬件绑定实现（MSPM0G3507）
 */
#include "app_led.h"
#include "main.h"
#include "bsp_common.h"

/* ================= 1. 硬件引脚定义 ================= */
#define APP_LED1_PORT  GPIOB
#define APP_LED1_PIN   DL_GPIO_PIN_22   /* USER_LED_1 */
#define APP_LED2_PORT  GPIOB
#define APP_LED2_PIN   DL_GPIO_PIN_21   /* USER_LED_2 */
#define APP_LED3_PORT  GPIOB
#define APP_LED3_PIN   DL_GPIO_PIN_27   /* USER_LED_3 */
#define APP_LED4_PORT  GPIOB
#define APP_LED4_PIN   DL_GPIO_PIN_16   /* USER_TEST */
/* 其余 4 个 LED 映射到 GPIOA 引脚（可根据实际板子修改） */
#define APP_LED5_PORT  GPIOA
#define APP_LED5_PIN   DL_GPIO_PIN_0
#define APP_LED6_PORT  GPIOA
#define APP_LED6_PIN   DL_GPIO_PIN_1
#define APP_LED7_PORT  GPIOA
#define APP_LED7_PIN   DL_GPIO_PIN_2
#define APP_LED8_PORT  GPIOA
#define APP_LED8_PIN   DL_GPIO_PIN_3

/* ================= 2. 对象实例化 ================= */
led_t app_leds[BSP_LED_NUM] = {
    {APP_LED1_PORT, APP_LED1_PIN, LED_OFF},
    {APP_LED2_PORT, APP_LED2_PIN, LED_OFF},
    {APP_LED3_PORT, APP_LED3_PIN, LED_OFF},
    {APP_LED4_PORT, APP_LED4_PIN, LED_OFF},
    {APP_LED5_PORT, APP_LED5_PIN, LED_OFF},
    {APP_LED6_PORT, APP_LED6_PIN, LED_OFF},
    {APP_LED7_PORT, APP_LED7_PIN, LED_OFF},
    {APP_LED8_PORT, APP_LED8_PIN, LED_OFF},
};

/* ================= 3. 对外业务切入点 ================= */

void App_LED_System_Init(void)
{
    BSP_Led_Init(app_leds);
}
