/**
 * @file    track_grayscale.c
 * @brief   八路灰度传感器驱动实现 — 直接操作 GPIO + ADC12
 */
#include "track_grayscale.h"

/* systick_ms 定义在 main.c */
extern volatile uint32_t systick_ms;

/* ============================================================
 * 全局对象
 * ============================================================ */
Track_Grayscale_t Track_Gray = {0};

/* ============================================================
 * 内部函数
 * ============================================================ */

/* 设置通道选择地址线 AD0/AD1/AD2 */
static void Track_Grayscale_Select(uint8_t ch)
{
    if ((ch >> 0) & 1) DL_GPIO_setPins  (Grayscale_ADDR_A_PORT, Grayscale_ADDR_A_AD0_PIN);
    else               DL_GPIO_clearPins(Grayscale_ADDR_A_PORT, Grayscale_ADDR_A_AD0_PIN);

    if ((ch >> 1) & 1) DL_GPIO_setPins  (Grayscale_ADDR_A_PORT, Grayscale_ADDR_A_AD1_PIN);
    else               DL_GPIO_clearPins(Grayscale_ADDR_A_PORT, Grayscale_ADDR_A_AD1_PIN);

    if ((ch >> 2) & 1) DL_GPIO_setPins  (Grayscale_ADDR_B_PORT, Grayscale_ADDR_B_AD2_PIN);
    else               DL_GPIO_clearPins(Grayscale_ADDR_B_PORT, Grayscale_ADDR_B_AD2_PIN);
}

/* 读取 ADC12 转换结果（12位, 0~4095） */
static uint16_t Track_Grayscale_Read_ADC(void)
{
    DL_ADC12_startConversion(GRAYSCALE_ADC_INST);
    while (DL_ADC12_isConversionStarted(GRAYSCALE_ADC_INST)) {}
    return DL_ADC12_getMemResult(GRAYSCALE_ADC_INST, DL_ADC12_MEM_IDX_0);
}

/* 滞回比较器 — 抗抖动判断单通道黑白 */
static void Track_Grayscale_Hysteresis(uint8_t ch)
{
    uint16_t grayW = (Track_Gray.black[ch] + 2 * Track_Gray.white[ch]) / 3;
    uint16_t grayB = (2 * Track_Gray.black[ch] + Track_Gray.white[ch]) / 3;

    if (Track_Gray.analog[ch] > grayW) {
        Track_Gray.digital[ch] = 0;        /* 白色 */
    } else if (Track_Gray.analog[ch] < grayB) {
        Track_Gray.digital[ch] = 1;        /* 黑色 */
    }
    /* grayB ≤ analog ≤ grayW → 保持上一状态 */
}

/* ============================================================
 * 对外接口
 * ============================================================ */

void Track_Grayscale_Init(void)
{
    for (uint8_t i = 0; i < TRACK_GRAY_CHANNEL_NUM; i++) {
        Track_Gray.digital[i] = 0;
        Track_Gray.analog[i]  = 0;
        Track_Gray.white[i]   = 0;
        Track_Gray.black[i]   = 0;
    }
    Track_Gray.current_ch       = 0;
    Track_Gray.last_switch_tick = 0;
    Track_Gray.calibrated       = 0;
    Track_Gray.black_count      = 0;

    /* 选通通道0，开始第一轮扫描 */
    Track_Grayscale_Select(0);
    Track_Gray.last_switch_tick = systick_ms;
}

void Track_Grayscale_Scan(void)
{
    uint32_t now = systick_ms;
    if ((now - Track_Gray.last_switch_tick) < TRACK_GRAY_SETTLE_MS) return;
    Track_Gray.last_switch_tick = now;

    /* ① 读取当前通道 ADC 值 */
    Track_Gray.analog[Track_Gray.current_ch] = Track_Grayscale_Read_ADC();

    /* ② 滞回比较（需校准后才生效） */
    if (Track_Gray.calibrated) {
        Track_Grayscale_Hysteresis(Track_Gray.current_ch);
    }

    /* ③ 切换到下一个通道 */
    Track_Gray.current_ch = (Track_Gray.current_ch + 1) & 0x07;
    Track_Grayscale_Select(Track_Gray.current_ch);
}

void Track_Grayscale_Calibrate_White(void)
{
    for (uint8_t i = 0; i < TRACK_GRAY_CHANNEL_NUM; i++) {
        Track_Gray.white[i] = Track_Gray.analog[i];
    }
    Track_Gray.calibrated = 1;
}

void Track_Grayscale_Calibrate_Black(void)
{
    for (uint8_t i = 0; i < TRACK_GRAY_CHANNEL_NUM; i++) {
        Track_Gray.black[i] = Track_Gray.analog[i];
    }
    Track_Gray.calibrated = 1;
}
