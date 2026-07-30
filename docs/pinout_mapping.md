# 开发板引脚复用功能映射表 (AI 辅助分配专用)

本文档整理了开发板上下两排插针（左右两侧）的全部物理引脚及其对应的复用功能。
**提示给AI：** 请在重新分配引脚时，严格参考下表的“可选复用功能”，确保引脚冲突（如SPI、I2C、UART、TIMER等）最小化。电源引脚（3V3, 5V, GND）不可用作普通IO。

## 1. 顶部排针 (Top Header)

### 1.1 顶部左侧引脚 (Top Left)
| 物理引脚 | 电源/特殊功能 | 可选复用功能 (ADC, UART, SPI, I2C, TIMER, etc.) |
| :--- | :--- | :--- |
| GND | 地 | - |
| A26 | - | TIMG8-C0, TIMG7-C0, SPI1-CS0, ADC A0-1, UART3-TX |
| A24 | - | TIMG7-C1, TIMA1-C1, SPI0-CS2, ADC A0-3, UART2-RX |
| B24 | - | TIMG12-C1, TIMA0-C3, SPI0-CS1, ADC A0-5 |
| A22 | - | TIMA1-C0, TIMG8-C1, UART2-RX, ADC A0-7 |
| A15 | - | TIMA1-C0, TIMG6-C1, I2C1-SCL, ADC A1-0, DAC-OUT |
| A17 | - | TIMA0-C2, TIMG7-C1, SPI0-CS3, I2C1-SCL, ADC A1-2, SPI1-SCK, UART1-TX |
| B18 | - | TIMA1-C1, SPI1-CS2, UART2-RX, ADC A1-5 |
| A21 | - | TIMG8-C0, TIMG6-C0, TIMA0-C3, SPI0-SCK, ADC A1-7, UART2-TX, VREF- |
| A23 | - | TIMG7-C1, TIMG7-C0, TIMA0-C0, SPI0-CS3, VREF+ |
| 3V3 | 电源 (3.3V) | - |
| 5V  | 电源 (5V) | - |
| B22 | - | TIMG8-C1, SPI1-PICO |
| GND | 地 | - |
| B01 | - | TIMA1-C1, SPI1-CS3, UART0-RX |
| A07 | - | TIMG8-C0, TIMA0-C2, TIMG7-C1, TIMA0-C1 |
| B14 | - | TIMA0-C0, TIMG12-C1, SPI0-CS3, SPI1-POCI, SPI1-CS3 |
| A18 | - | BSL, TIMA1-C1, TIMG7-C1, SPI1-PICO, UART1-RX, I2C1-SDA, ADC A1-3 |
| 3V3 | 电源 (3.3V) | - |
| 5V  | 电源 (5V) | - |

### 1.2 顶部右侧引脚 (Top Right)
| 物理引脚 | 电源/特殊功能 | 可选复用功能 (ADC, UART, SPI, I2C, TIMER, etc.) |
| :--- | :--- | :--- |
| GND | 地 | - |
| A27 | - | TIMG7-C1, TIMG8-C1, SPI1-CS1, ADC A0-0, CAN-RX |
| A25 | - | TIMA0-C3, TIMG12-C1, SPI1-CS3, ADC A0-2, UART3-RX |
| B25 | - | SPI0-CS0, ADC A0-4 |
| B20 | - | TIMA0-C1, TIMG12-C0, TIMA0-C2, ADC A0-6, SPI1-CS0, SPI0-CS2 |
| A14 | - | TIMG12-C0, SPI0-PICO, UART3-TX, ADC A0-12 |
| A16 | - | TIMA1-C1, SPI1-POCI, I2C1-SDA, ADC A1-1 |
| B17 | - | TIMA0-C2, TIMA1-C0, SPI0-PICO, ADC A1-4, UART2-TX, SPI1-CS1 |
| B19 | - | TIMG8-C1, TIMG7-C1, SPI0-POCI, ADC A1-6 |
| A02 | - | ROSC, TIMG8-C1, TIMG7-C1, SPI0-CS0, SPI1-CS0 |
| GND | 地 | - |
| GND | 地 | - |
| B21 | - | TIMG8-C0, SPI1-POCI |
| A30 | - | TIMG8-C1, TIMG6-C1, I2C1-SDA |
| B00 | - | TIMA1-C0, TIMA0-C2, SPI1-CS2, UART0-TX |
| B10 | - | TIMG8-C0, TIMG6-C0, TIMG0-C0 |
| B11 | - | TIMG8-C1, TIMG6-C1, TIMG0-C1 |
| RST | 芯片复位 | - |
| GND | 地 | - |
| GND | 地 | - |

## 2. 底部排针 (Bottom Header)

### 2.1 底部左侧引脚 (Bottom Left)
| 物理引脚 | 电源/特殊功能 | 可选复用功能 (ADC, UART, SPI, I2C, TIMER, etc.) |
| :--- | :--- | :--- |
| GND | 地 | - |
| A28 | - | UART0-TX, TIMG7-C0, TIMA1-C0, I2C0-SDA |
| A31 | - | UART0-RX, TIMA1-C1, TIMG7-C1, TIMG12-C1, I2C0-SCL |
| B04 | - | UART1-TX, TIMA1-C0, TIMA0-C2 |
| B05 | - | UART1-RX, TIMA0-C2, TIMA1-C1 |
| A10 | - | UART0-TX, TIMA1-C1, TIMA1-C0, TIMG12-C0, SPI0-POCI, I2C0-SDA, I2C1-SDA |
| A11 | - | UART0-RX, TIMA1-C0, TIMA1-C1, I2C0-SCL, I2C1-SCL |
| B12 | - | UART3-TX, TIMA0-C2, TIMA0-C1 |
| B13 | - | UART3-RX, TIMA0-C3, TIMG12-C0 |
| CLK | PA20 | - |
| 3V3 | 电源 (3.3V) | - |
| 5V  | 电源 (5V) | - |
| B07 | - | UART1-RX, TIMG6-C1, TIMG8-C1, SPI0-CS2, SPI1-POCI |
| B09 | - | TIMA0-C1, SPI1-SCK |
| A13 | - | UART3-RX, SPI0-POCI, TIMG0-C1, CAN-RX |
| B26 | - | TIMA1-C0, TIMA0-C3, TIMG6-C0, SPI0-CS1 |
| A29 | - | TIMA0-C2, TIMG8-C0, TIMG6-C0, I2C1-SCL |
| CHIP| 板载参考电压输出 | - |
| 3V3 | 电源 (3.3V) | - |
| 5V  | 电源 (5V) | - |

### 2.2 底部右侧引脚 (Bottom Right)
| 物理引脚 | 电源/特殊功能 | 可选复用功能 (ADC, UART, SPI, I2C, TIMER, etc.) |
| :--- | :--- | :--- |
| GND | 地 | - |
| A00 | - | TIMG8-C1, TIMA0-C0, UART0-TX, I2C0-SDA |
| A01 | - | TIMG8-C0, TIMA0-C1, UART0-RX, I2C0-SCL |
| A08 | - | TIMA0-C0, SPI0-CS0, UART1-TX |
| A09 | - | TIMA0-C1, SPI0-PICO, UART1-RX |
| B15 | - | TIMG8-C0, TIMG7-C0, UART2-TX, SPI1-PICO |
| B16 | - | TIMG7-C1, TIMG8-C1, UART2-RX, SPI1-SCK |
| B02 | - | TIMA1-C0, TIMA0-C3, UART3-TX, TIMG6-C0, I2C1-SCL |
| B03 | - | TIMA1-C1, TIMG6-C1, UART3-RX, I2C1-SDA |
| DIO | PA19 | - |
| GND | 地 | - |
| GND | 地 | - |
| B06 | - | TIMG6-C0, TIMG8-C0, UART1-TX, SPI1-CS0, SPI0-CS1 |
| B08 | - | TIMA0-C0, SPI1-PICO |
| A12 | - | TIMA0-C3, TIMG0-C0, CAN-TX, SPI0-SCK |
| B23 | - | SPI1-SCK |
| B27 | - | TIMG6-C1, TIMA1-C1, SPI1-CS1 |
| AGND| 模拟地 | - |
| GND | 地 | - |
| GND | 地 | - |

---

## 3. 当前引脚占用总览

### 3.1 顶部左侧 (Top Left)

| 物理引脚 | 功能 | 外设 | 状态 |
| :--- | :--- | :--- | :--- |
| GND | 地 | — | — |
| A26 | **Stage1 限位** | GPIO 输入 (上拉) | ✅ 已用 |
| A24 | — | 空闲 | 🟢 可用 |
| B24 | — | 空闲 | 🟢 可用 |
| A22 | — | 空闲 | 🟢 可用 |
| A15 | — | 空闲 | 🟢 可用 |
| A17 | — | 空闲 | 🟢 可用 |
| B18 | — | 空闲 | 🟢 可用 |
| A21 | — | 空闲 | 🟢 可用 |
| A23 | — | 空闲 | 🟢 可用 |
| 3V3 | 电源 3.3V | — | — |
| 5V  | 电源 5V | — | — |
| B22 | — | 空闲 | 🟢 可用 |
| GND | 地 | — | — |
| B01 | — | 空闲 | 🟢 可用 |
| A07 | — | 空闲 | 🟢 可用 |
| B14 | — | 空闲 | 🟢 可用 |
| A18 | — | 空闲 | 🟢 可用 |
| 3V3 | 电源 3.3V | — | — |
| 5V  | 电源 5V | — | — |

### 3.2 顶部右侧 (Top Right)

| 物理引脚 | 功能 | 外设 | 状态 |
| :--- | :--- | :--- | :--- |
| GND | 地 | — | — |
| A27 | **Stage2 限位** | GPIO 输入 (上拉) | ✅ 已用 |
| A25 | — | 空闲 | 🟢 可用 |
| B25 | — | 空闲 | 🟢 可用 |
| B20 | — | 空闲 | 🟢 可用 |
| A14 | **编码器 DIR1** | GPIO 输出 | ✅ 已用 |
| A16 | — | 空闲 | 🟢 可用 |
| B17 | — | 空闲 | 🟢 可用 |
| B19 | — | 空闲 | 🟢 可用 |
| A02 | — | 空闲 | 🟢 可用 |
| GND | 地 | — | — |
| GND | 地 | — | — |
| B21 | — | 空闲 | 🟢 可用 |
| A30 | — | 空闲 | 🟢 可用 |
| B00 | — | 空闲 | 🟢 可用 |
| B10 | — | 空闲 | 🟢 可用 |
| B11 | — | 空闲 | 🟢 可用 |
| RST | 芯片复位 | — | — |
| GND | 地 | — | — |
| GND | 地 | — | — |

### 3.3 底部左侧 (Bottom Left)

| 物理引脚 | 功能 | 外设 | 状态 |
| :--- | :--- | :--- | :--- |
| GND | 地 | — | — |
| A28 | — | 空闲 | 🟢 可用 |
| A31 | — | 空闲 | 🟢 可用 |
| **B04** | **Vision TX** ⭐ | **UART1-TX** (PB4) | ✅ 新分配 |
| **B05** | **Vision RX** ⭐ | **UART1-RX** (PB5) | ✅ 新分配 |
| A10 | **Stage1 STEP** | TIMA1_C0 + UART0-TX (分时) | ✅ 已用 |
| A11 | **Stage1 DIR** | GPIO 输出 + UART0-RX (分时) | ✅ 已用 |
| B12 | — | 空闲 | 🟢 可用 |
| B13 | — | 空闲 | 🟢 可用 |
| CLK | **SWCLK** (PA20) | 调试口 | ⛔ 保留 |
| 3V3 | 电源 3.3V | — | — |
| 5V  | 电源 5V | — | — |
| B07 | — | 空闲 | 🟢 可用 |
| B09 | — | 空闲 | 🟢 可用 |
| A13 | — | 空闲 | 🟢 可用 |
| B26 | — | 空闲 | 🟢 可用 |
| A29 | — | 空闲 | 🟢 可用 |
| CHIP | 参考电压 | — | — |
| 3V3 | 电源 3.3V | — | — |
| 5V  | 电源 5V | — | — |

### 3.4 底部右侧 (Bottom Right)

| 物理引脚 | 功能 | 外设 | 状态 |
| :--- | :--- | :--- | :--- |
| GND | 地 | — | — |
| A00 | **KEY4** / LED5 | GPIO 输入+输出 (PA0) | ✅ 已用 |
| A01 | **LED6** (备用) | GPIO 输出 (PA1) | ✅ 已用 |
| A08 | **Stage2 STEP** | TIMA0_C0 (PA8) | ✅ 已用 |
| A09 | **Stage2 DIR** | GPIO 输出 (PA9) | ✅ 已用 |
| B15 | — | 空闲 | 🟢 可用 |
| B16 | **LED4** | GPIO 输出 (PB16) | ✅ 已用 |
| B02 | **KEY3** | GPIO 输入 (PB2) | ✅ 已用 |
| B03 | — | 空闲 | 🟢 可用 |
| DIO | **SWDIO** (PA19) | 调试口 | ⛔ 保留 |
| GND | 地 | — | — |
| GND | 地 | — | — |
| B06 | — | 空闲 | 🟢 可用 |
| B08 | — | 空闲 | 🟢 可用 |
| **A12** | **舵机 PWM** ⭐ | **TIMG0_C0** (PA12) | ✅ 新分配 |
| B23 | — | 空闲 | 🟢 可用 |
| B27 | **LED3** | GPIO 输出 (PB27) | ✅ 已用 |
| AGND | 模拟地 | — | — |
| GND | 地 | — | — |
| GND | 地 | — | — |

---

## 4. 启动配置引脚 (LaunchPad J5/J6/J7 跳线)

| 引脚 | 功能 | 已分配用途 | 状态 |
| :--- | :--- | :--- | :--- |
| **PB22** | — | **LED1** (J5 跳线) | ✅ 已用 |
| **PB21** | — | **LED2** (J6 跳线) | ✅ 已用 |
| **PB27** | — | **LED3** (J7 跳线) | ✅ 已用 |
| **PB16** | — | **LED4** | ✅ 已用 |
| **PB0** | — | **KEY1** | ✅ 已用 |
| **PB1** | — | **KEY2** | ✅ 已用 |
| **PB2** | — | **KEY3** | ✅ 已用 |
| **PB8** | — | **MPU6050 SCL** (软件 I2C) | ✅ 已用 |
| **PB9** | — | **MPU6050 SDA** (软件 I2C) | ✅ 已用 |
| **PA14** | — | **编码器 DIR1** | ✅ 已用 |
| **PA15** | — | **编码器 DIR2** | ✅ 已用 |

---

## 5. 新增引脚快速索引

| 功能 | 引脚 | 排针位置 | IOMUX | 说明 |
| :--- | :--- | :--- | :--- | :--- |
| ⭐ **舵机 PWM** | **PA12** | 底部右侧 A12 | `PINCM34` → `TIMG0_CCP0` | 50Hz, 0.5~2.5ms |
| ⭐ **Vision TX** | **PB4** | 底部左侧 B04 | `PINCM17` → `UART1_TX` | 115200-8-N-1 |
| ⭐ **Vision RX** | **PB5** | 底部左侧 B05 | `PINCM18` → `UART1_RX` | 115200-8-N-1 |

> **图例**: ✅ 已用 | 🟢 可用 | ⛔ 保留 (不可占用) | ⭐ 本次新分配
