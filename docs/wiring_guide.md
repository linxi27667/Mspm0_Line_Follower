# 书写机器人 (Writer Robot) — 接线文档

## 系统概述

| 项目 | 详情 |
|------|------|
| 主控 | TI MSPM0G3507 (VSSOP-28) |
| 开发板 | LP-MSPM0G3507 LaunchPad |
| 系统时钟 | 32 MHz |
| RTOS | 裸机 (systick 时标切片调度) |
| 架构 | BSP → APP → TASK 三层架构 |

---

## 完整引脚分配表

### 步进电机 (SCARA 双轴)

| 功能 | 信号 | MCU 引脚 | LaunchPad 排针 | 备注 |
|------|------|----------|---------------|------|
| Stage1 (Arm1) 步进脉冲 | STEP | **PA10** (TIMA1_C0) | J1_5 | 接 A4988/DRV8825 驱动器 STEP 脚 |
| Stage1 (Arm1) 方向 | DIR | **PA11** | J1_6 | 接驱动器 DIR 脚 |
| Stage2 (Arm2) 步进脉冲 | STEP | **PA8** (TIMA0_C0) | J1_3 | 接 A4988/DRV8825 驱动器 STEP 脚 |
| Stage2 (Arm2) 方向 | DIR | **PA9** | J1_4 | 接驱动器 DIR 脚 |

### 限位开关 (归零)

| 功能 | 信号 | MCU 引脚 | LaunchPad 排针 | 电平逻辑 |
|------|------|----------|---------------|----------|
| Stage1 限位 | LIMIT1 | **PA26** | J4_17 | 常高 (内部上拉), 触发时拉低到 GND |
| Stage2 限位 | LIMIT2 | **PA27** | J4_18 | 常高 (内部上拉), 触发时拉低到 GND |

> 限位开关一端接对应引脚，另一端接 GND。

### 按键

| 按键 | MCU 引脚 | LaunchPad 排针 | 触发逻辑 |
|------|----------|---------------|----------|
| KEY1 | **PB0** | J4_35 | 低电平有效 (内部上拉) |
| KEY2 | **PB1** | J4_37 | 低电平有效 (内部上拉) |
| KEY3 | **PB2** | J4_39 | 低电平有效 (内部上拉) |
| KEY4 | **PA0** | J2_12 | 低电平有效 (内部上拉) |

> 按键一端接对应引脚，另一端接 GND。

### 用户 LED (低电平亮)

| LED | MCU 引脚 | LaunchPad 排针 |
|-----|----------|---------------|
| LED1 | **PB22** | J4_32 |
| LED2 | **PB21** | J2_15 |
| LED3 | **PB27** | J4_38 |
| LED4 | **PB16** | J2_11 |
| LED5 (备用) | **PA0** | J2_12 |
| LED6 (备用) | **PA1** | J2_14 |
| LED7 (备用) | **PA2** | J1_14 |
| LED8 (备用) | **PA3** | J1_15 |

> LED 串联 220Ω~1kΩ 限流电阻到 GND。

---

## 新增：舵机接口

| 功能 | MCU 引脚 | LaunchPad 排针 | 定时器通道 | 说明 |
|------|----------|---------------|-----------|------|
| **舵机 PWM** | **PA12** | J4_24 (底部右侧) | **TIMG0_C0** (IOMUX_PINCM34) | 50Hz PWM, 0.5~2.5ms 脉宽 |

### 舵机接线

```
SG90/MG996R 舵机:
  橙/白线 (信号)  → PA12  (J4_24)
  红线   (VCC)    → 5V   (外部电源, 不要用 LaunchPad 3.3V)
  棕/黑线 (GND)   → GND  (共地)
```

> 舵机必须使用 **外部 5V 电源**，LaunchPad 3.3V 无法驱动。务必将外部电源 GND 与 LaunchPad GND 相连。

### 舵机代码改动要点

```c
// app_servo.c — 需要配置的 IOMUX
DL_GPIO_initPeripheralOutputFunction(IOMUX_PINCM34, IOMUX_PINCM34_PF_TIMG0_CCP0);
// PA12 IOMUX = PINCM34, 复用功能选择 TIMG0_CCP0
```

---

## 新增：视觉通信串口 (UART1)

| 功能 | MCU 引脚 | LaunchPad 排针 | IOMUX | 说明 |
|------|----------|---------------|-------|------|
| **Vision TX** (主控→视觉) | **PB4** | **J1_9** (底部左侧) | IOMUX_PINCM17 UART1-TX | 接视觉模块 RX |
| **Vision RX** (视觉→主控) | **PB5** | **J1_8** (底部左侧) | IOMUX_PINCM18 UART1-RX | 接视觉模块 TX |

### 视觉模块接线 (以 OpenMV/K210 为例)

```
MSPM0G3507         视觉模块
   PB4 (TX)  ────→  RX (视觉模块)
   PB5 (RX)  ←────  TX (视觉模块)
   GND       ────   GND (共地)
```

| 参数 | 推荐值 |
|------|--------|
| 波特率 | **115200** (与主控 UART0 一致) 或 **921600** (高速) |
| 数据位 | 8 |
| 停止位 | 1 |
| 校验 | 无 |
| 流控 | 无 |

### 为什么不用 UART0

当前 UART0 (PA10/PA11) 与步进电机 STEP/DIR 共用引脚（通过 `DL_GPIO_initPeripheralOutputFunction` 重映射），运动期间无法同时通信。UART1 独立引脚，可全时双工通信。

### UART1 初始化参考代码

> 代码文件已生成: `COMM/Inc/comm_vision_uart.h`, `COMM/Src/comm_vision_uart.c`
> 在 `main.c` 中 `while(1)` 前调用 `App_Vision_UART_Init()`，主循环中调用 `App_Vision_UART_Task()` 即可。

```c
// main.c 中集成示例
#include "comm_vision_uart.h"

int main(void)
{
    // ... 其他初始化 ...
    App_Vision_UART_Init();

    while (1) {
        App_Vision_UART_Task();
        // ... 其他任务 ...
    }
}
```

---

## 其他已用外设

### 编码器直流电机 (可选)

| 功能 | MCU 引脚 | LaunchPad 排针 |
|------|----------|---------------|
| DIR1 | **PA14** | J4_13 |
| DIR2 | **PA15** | J4_14 |
| PWM | TIMG7 Ch.0 | (待 SysConfig 分配) |
| 编码器 | TIMG8 | (待 SysConfig 分配) |

### MPU6050 (软件 I2C)

| 功能 | MCU 引脚 | LaunchPad 排针 |
|------|----------|---------------|
| SCL | **PB8** | J4_40 |
| SDA | **PB9** | J2_13 |

```
MPU6050:
  VCC → 3.3V
  GND → GND
  SCL → PB8
  SDA → PB9
```

### 灰度传感器 (74HC4051 模拟多路选通, 待配置)

| 功能 | 符号 | 状态 |
|------|------|------|
| 地址选择 A | `Grayscale_ADDR_A_AD0_PIN` | 引脚待分配 |
| 地址选择 B | `Grayscale_ADDR_A_AD1_PIN` | 引脚待分配 |
| 地址选择 C | `Grayscale_ADDR_B_AD2_PIN` | 引脚待分配 |
| ADC 输入 | PA27 (ADC0 A0-0) | 待 SysConfig 配置 |

---

## LaunchPad 排针位置速查

```
        顶部排针 (J1, J2)
  ┌─────────────────────────────┐
  │ GND A26 A24 B24 A22 A15 ... │  J1 左侧
  │ A17 B18 A21 A23 3V3 5V  ... │  J1 左侧
  │ ...  3V3 5V                │  J2 右侧
  ├─────────────────────────────┤
  │                             │
  │      MSPM0G3507 DGS28       │
  │                             │
  ├─────────────────────────────┤
  │ GND A28 A31 B04 B05 A10 ... │  J4 底部
  │ A11 B12 B13 CLK 3V3 5V  ... │  J3 底部
  │ B07 B09 A13 B26 A29 CHIP ...│  J3 底部
  └─────────────────────────────┘

  新增引脚位置:
    PA12 (舵机)    → J4_24 (底部右侧, 标号 J4 Pin 24)
    PB4  (Vision TX) → J1_9  (底部左侧, 标号 J1 Pin 9)
    PB5  (Vision RX) → J1_8  (底部左侧, 标号 J1 Pin 8)
```

---

## 电源接线

```
  外部 12V 电源
    ├──→ A4988/DRV8825 步进驱动器 VMOT
    │    (驱动器逻辑供电可接 LaunchPad 5V 或 12V 经降压模块)
    ├──→ (降压模块 → 5V) → 舵机 VCC
    └── GND 共地 → LaunchPad GND
                     → 驱动器 GND
                     → 舵机 GND
                     → 视觉模块 GND

  LaunchPad USB 5V (调试用) 或 外部 5V:
    → LaunchPad 5V/VDD
```

> 所有设备务必**共地**。步进电机和舵机使用外部电源，不要从 LaunchPad 3.3V/5V 取电。

---

## 引脚占用总览 (快速查重)

```
PA0  : KEY4 / LED5 (备用)
PA1  : LED6 (备用)
PA2  : LED7 (备用)
PA3  : LED8 (备用)
PA8  : Stage2 STEP (TIMA0_C0)
PA9  : Stage2 DIR
PA10 : Stage1 STEP + UART0 TX (分时复用)
PA11 : Stage1 DIR + UART0 RX (分时复用)
PA12 : ⭐ 舵机 PWM (TIMG0_C0)        【新增】
PA14 : 编码器电机 DIR1
PA15 : 编码器电机 DIR2
PA19 : SWDIO (调试口, 勿占用)
PA20 : SWCLK (调试口, 勿占用)
PA26 : Stage1 限位开关
PA27 : Stage2 限位开关
PB0  : KEY1
PB1  : KEY2
PB2  : KEY3
PB4  : ⭐ Vision UART1 TX             【新增】
PB5  : ⭐ Vision UART1 RX             【新增】
PB8  : MPU6050 SW I2C SCL
PB9  : MPU6050 SW I2C SDA
PB16 : LED4
PB21 : LED2
PB22 : LED1
PB27 : LED3
```
