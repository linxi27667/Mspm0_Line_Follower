/**
 * @file    bsp_grayscale.c
 * @brief   八路灰度传感器核心逻辑实现（BSP — 纯逻辑，跨平台）
 * @note    非阻塞状态机：每次调用只读1路，8次完成一轮扫描
 *          含归一化(0=白,1=黑) + 滞回比较 + black_count统计
 */
#include "bsp_grayscale.h"

/* ================= 内部函数 ================= */

/* 设置通道选择地址线（AD0/AD1/AD2 = ch的二进制） */
static void Gray_Select_Channel(bsp_grayscale_t *gs, uint8_t ch)
{
    if (gs->Gpio_Write) {
        gs->Gpio_Write(gs->ad0.port, gs->ad0.pin, (ch >> 0) & 1);
        gs->Gpio_Write(gs->ad1.port, gs->ad1.pin, (ch >> 1) & 1);
        gs->Gpio_Write(gs->ad2.port, gs->ad2.pin, (ch >> 2) & 1);
    }
}

/* 滞回比较器 — 抗抖动判断单通道黑白
 * GrayW = (black + 2*white) / 3  灰白阈值（偏白侧）
 * GrayB = (2*black + white) / 3  灰黑阈值（偏黑侧）
 * ADC > GrayW → 白;  ADC < GrayB → 黑;  中间区域保持上一状态 */
static void Gray_Hysteresis(bsp_grayscale_t *gs, uint8_t ch)
{
    uint16_t grayW = (gs->black[ch] + 2 * gs->white[ch]) / 3;
    uint16_t grayB = (2 * gs->black[ch] + gs->white[ch]) / 3;

    if (gs->analog[ch] > grayW) {
        gs->digital[ch] = 0;        /* 白色 */
    } else if (gs->analog[ch] < grayB) {
        gs->digital[ch] = 1;        /* 黑色 */
    }
    /* grayB ≤ analog ≤ grayW → 保持上一状态（惯性抗抖动） */
}

/* 归一化：将 ADC 值映射到 0(白)~1(黑)
 * 未校准时用简单线性映射; 校准后用白/黑基准值映射 */
static void Gray_Normalize(bsp_grayscale_t *gs, uint8_t ch)
{
    if (!gs->calibrated) {
        /* 未校准：简单线性映射 (ADC越大→越白→norm越小) */
        gs->norm[ch] = 1.0f - (float)gs->analog[ch] / (float)BSP_GRAY_ADC_MAX;
        return;
    }

    uint16_t w = gs->white[ch];
    uint16_t b = gs->black[ch];
    uint16_t range = w - b;
    if (range < 1) range = 1;  /* 防止除零 */

    int32_t val = (int32_t)gs->analog[ch] - b;
    if (val < 0) val = 0;
    if (val > range) val = range;

    /* norm=0 → 白（高ADC），norm=1 → 黑（低ADC） */
    gs->norm[ch] = 1.0f - (float)val / (float)range;
}

/* 统计黑色通道数 */
static void Gray_Count_Black(bsp_grayscale_t *gs)
{
    gs->black_count = 0;
    for (uint8_t i = 0; i < BSP_GRAY_CHANNEL_NUM; i++) {
        if (gs->digital[i]) gs->black_count++;
    }
}

/* ================= 1. 设备初始化 ================= */
void Bsp_Grayscale_Init_Device(bsp_grayscale_t *gs)
{
    if (gs == NULL) return;

    /* 稳定时间缺省值 */
    if (gs->settle_ms == 0) gs->settle_ms = BSP_GRAY_SETTLE_MS;

    /* 清零所有数据 */
    for (uint8_t i = 0; i < BSP_GRAY_CHANNEL_NUM; i++) {
        gs->analog[i]  = 0;
        gs->norm[i]    = 0;
        gs->white[i]   = 0;
        gs->black[i]   = 0;
        gs->digital[i] = 0;
    }

    gs->current_ch       = 0;
    gs->data_ready       = 0;
    gs->calibrated       = 0;
    gs->black_count      = 0;
    gs->last_switch_tick = 0;

    /* 调用硬件初始化（GPIO/ADC由APP层SysConfig配置） */
    if (gs->Init) gs->Init();

    /* 初始选通通道0，开始第一轮扫描 */
    Gray_Select_Channel(gs, 0);
    if (gs->GetTick) gs->last_switch_tick = gs->GetTick();
}

/* ================= 2. 非阻塞更新（状态机） ================= */
void Bsp_Grayscale_Update(bsp_grayscale_t *gs)
{
    if (gs == NULL || gs->ADC_Read == NULL || gs->GetTick == NULL) return;

    /* 未到稳定时间，跳过本次调用 */
    uint32_t now = gs->GetTick();
    if ((now - gs->last_switch_tick) < gs->settle_ms) return;

    gs->last_switch_tick = now;

    /* ① 读取当前通道ADC值（上一次选通的通道，现已稳定） */
    gs->analog[gs->current_ch] = gs->ADC_Read();

    /* ② 归一化（0=白, 1=黑） */
    Gray_Normalize(gs, gs->current_ch);

    /* ③ 滞回比较（需校准后才生效） */
    if (gs->calibrated) {
        Gray_Hysteresis(gs, gs->current_ch);
    } else {
        /* 未校准时用归一化阈值判断 */
        gs->digital[gs->current_ch] =
            (gs->norm[gs->current_ch] > 0.5f) ? 1 : 0;
    }

    /* ④ 切换到下一个通道 */
    gs->current_ch = (gs->current_ch + 1) & 0x07;
    Gray_Select_Channel(gs, gs->current_ch);

    /* ⑤ 一轮8路扫描完成 */
    if (gs->current_ch == 0) {
        Gray_Count_Black(gs);
        gs->data_ready = 1;
    }
}

/* ================= 3. 校准接口 ================= */
/* 使用方法：先让传感器扫描至少一轮（data_ready=1），再调用校准 */
void Bsp_Grayscale_Calibrate_White(bsp_grayscale_t *gs)
{
    if (gs == NULL) return;
    for (uint8_t i = 0; i < BSP_GRAY_CHANNEL_NUM; i++) {
        gs->white[i] = gs->analog[i];
    }
    gs->calibrated = 1;
}

void Bsp_Grayscale_Calibrate_Black(bsp_grayscale_t *gs)
{
    if (gs == NULL) return;
    for (uint8_t i = 0; i < BSP_GRAY_CHANNEL_NUM; i++) {
        gs->black[i] = gs->analog[i];
    }
    gs->calibrated = 1;
}
