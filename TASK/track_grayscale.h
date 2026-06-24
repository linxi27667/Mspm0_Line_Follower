/**
 * @file    track_grayscale.h
 * @brief   八路灰度传感器驱动（TASK层 — 直接操作GPIO+ADC12）
 * @note    硬件连接（由 SysConfig 生成 ti_msp_dl_config.h）:
 *          - ADC:  PA27 (ADC0)
 *          - AD0:  PA16, AD1: PA12, AD2: PB3
 *          74HC4051模拟多路复用，3根地址线选通道，1根ADC读模拟量
 */
#ifndef __TRACK_GRAYSCALE_H__
#define __TRACK_GRAYSCALE_H__

#include <stdint.h>
#include "ti_msp_dl_config.h"

/* ============================================================
 * 灰度传感器宏定义
 * ============================================================ */

/* 通道数 */
#define TRACK_GRAY_CHANNEL_NUM     8

/* 通道切换稳定时间(ms) — 基础款1ms，青春款10ms */
#define TRACK_GRAY_SETTLE_MS       1

/* ============================================================
 * 灰度传感器数据结构
 * ============================================================ */
typedef struct {
    uint8_t  digital[TRACK_GRAY_CHANNEL_NUM];   /* 8路数字值(1=黑,0=白) */
    uint16_t analog[TRACK_GRAY_CHANNEL_NUM];     /* 8路原始ADC值 */
    uint16_t white[TRACK_GRAY_CHANNEL_NUM];      /* 白纸校准值 */
    uint16_t black[TRACK_GRAY_CHANNEL_NUM];      /* 黑纸校准值 */
    uint8_t  current_ch;                         /* 当前扫描通道 */
    uint32_t last_switch_tick;                   /* 上次通道切换时间戳 */
    uint8_t  calibrated;                         /* 校准完成标志 */
    uint8_t  black_count;                        /* 当前黑色通道数 */
} Track_Grayscale_t;

/* ============================================================
 * 灰度传感器接口
 * ============================================================ */

/* 外部全局对象 */
extern Track_Grayscale_t Track_Gray;

void Track_Grayscale_Init(void);           /* 初始化：选通通道0 */
void Track_Grayscale_Scan(void);           /* 非阻塞扫描（每次1路） */
void Track_Grayscale_Calibrate_White(void);/* 白纸校准 */
void Track_Grayscale_Calibrate_Black(void);/* 黑纸校准 */

#endif /* __TRACK_GRAYSCALE_H__ */
