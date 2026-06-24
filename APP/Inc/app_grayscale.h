/**
 * @file    app_grayscale.h
 * @brief   八路灰度传感器应用层声明（硬件绑定 + 业务逻辑入口）
 * @note    引脚配置需在SysConfig中完成：
 *          - AD0/AD1/AD2 配置为数字输出
 *          - OUT引脚配置为ADC模拟输入（添加ADC12模块）
 */
#ifndef APP_GRAYSCALE_H
#define APP_GRAYSCALE_H

#include "bsp_grayscale.h"

/* ============ 灰度传感器硬件配置 ============ */
/* 地址线 AD0/AD1/AD2 — 纯GPIO即可 */
/* PA16=PINCM38, PA12=PINCM34, PB3=PINCM16 */
#define GRAY_AD0_PORT           GPIOA
#define GRAY_AD0_PIN            DL_GPIO_PIN_16
#define GRAY_AD1_PORT           GPIOA
#define GRAY_AD1_PIN            DL_GPIO_PIN_12
#define GRAY_AD2_PORT           GPIOB
#define GRAY_AD2_PIN            DL_GPIO_PIN_3

/* ADC实例 — PA27 = ADC0通道0 (A0-0) */
#define GRAY_ADC_INST           GRAYSCALE_ADC_INST

/* ============ 业务接口声明 ============ */
extern bsp_grayscale_t App_Grayscale;

void App_Grayscale_System_Init(void);
void App_Grayscale_Update(void);
void App_Grayscale_Calibrate_White(void);
void App_Grayscale_Calibrate_Black(void);

#endif /* APP_GRAYSCALE_H */
