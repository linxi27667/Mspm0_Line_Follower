# 拼图装置 PCB 引脚分配表（V24）

## 1. 文档信息

| 项目 | 内容 |
|---|---|
| 项目 | 2026 电赛 E 题拼图装置 |
| 主控 | MSPM0G3507 |
| MCU 封装 | LQFP-64（PM） |
| 当前固件标识 | `PUZZLE_UART_XY_ACTUATOR_DRIVERS_V24` |
| 系统逻辑电压 | 3.3 V |
| 对应 SysConfig | `TI_moban.syscfg` |
| 对应执行器驱动 | `APP/Src/app_actuator.c` |
| 更新日期 | 2026-07-29 |

> [!IMPORTANT]
> 本文中的“LQFP-64 脚号”只适用于 MSPM0G3507 的 PM 封装，不能直接用于 48 引脚、32 引脚封装，也不能直接当作 LaunchPad 的 J1～J4 排针号。

## 2. 引脚使用总览

当前 V24 固件实际使用：

- 21 个应用 GPIO；
- 2 个 SWD 调试 GPIO；
- 1 个 NRST 复位引脚；
- VDD、VSS、VCORE 电源相关引脚；
- TB6612 的 STBY 直接连接 3.3 V，不占用 MCU GPIO。

## 3. 应用 GPIO 完整分配表

| LQFP-64 脚号 | MCU 引脚 | 方向 | 功能 | 外设/信号 | 电气配置 |
|---:|---|---|---|---|---|
| 56 | PA10 | 输出 | 大臂步进脉冲 | TIMA1_CCP0 / STAGE1_STEP | PWM 脉冲输出 |
| 57 | PA11 | 输出 | 大臂步进方向 | STAGE1_DIR | GPIO 输出 |
| 54 | PA8 | 输出 | 小臂步进脉冲 | TIMA0_CCP0 / STAGE2_STEP | PWM 脉冲输出 |
| 55 | PA9 | 输出 | 小臂步进方向 | STAGE2_DIR | GPIO 输出 |
| 30 | PA26 | 输入 | 大臂复位限位 | STAGE1_LIMIT | 内部上拉，低电平触发 |
| 31 | PA27 | 输入 | 小臂复位限位 | STAGE2_LIMIT | 内部上拉，低电平触发 |
| 28 | PB26 | 输入 | 按键1：全部电机重新回零 | KEY1_REHOME | 内部上拉，低电平触发 |
| 36 | PA29 | 输入 | 按键2：有效区域四角打点 | KEY2_AREA_MARK | 内部上拉，低电平触发 |
| 22 | PB23 | 输入 | 按键3：纸张原点打点 | KEY3_ORIGIN_MARK | 内部上拉，低电平触发 |
| 29 | PB27 | 输入 | 按键4：预留 | KEY4_RESERVED | 内部上拉，低电平触发 |
| 5 | PA12 | 输出 | 舵机控制 | TIMG0_CCP0 / SERVO_PWM | 50 Hz PWM |
| 52 | PB4 | 输出 | 视觉通信发送 | UART1_TX | 115200，3.3 V TTL |
| 53 | PB5 | 输入 | 视觉通信接收 | UART1_RX | 115200，3.3 V TTL |
| 49 | PA7 | 输出 | N20 旋转电机 PWM | TIMG7_CCP1 / TB6612_PWMA | 32 kHz PWM |
| 47 | PB0 | 输出 | N20 旋转电机方向1 | TB6612_AIN1 | GPIO 输出 |
| 48 | PB1 | 输出 | N20 旋转电机方向2 | TB6612_AIN2 | GPIO 输出 |
| 63 | PB11 | 输入 | N20 编码器 A 相 | ENCODER_A | 双边沿，无内部上下拉 |
| 2 | PB14 | 输入 | N20 编码器 B 相 | ENCODER_B | 双边沿，无内部上下拉 |
| 37 | PA30 | 输出 | 电磁铁 MOS 控制 | MAGNET_CTRL | 高电平吸取，低电平释放 |
| 62 | PB10 | 输出 | 状态/完成提示 LED | STATUS_LED | 高电平点亮 |
| 42 | PA2 | 输出 | 完成提示蜂鸣器 | BUZZER | 高电平鸣叫 |

## 4. 两路步进电机驱动接口

### 4.1 大臂步进电机

| 驱动器信号 | MSPM0 引脚 | LQFP-64 脚号 |
|---|---|---:|
| STEP/PUL | PA10 | 56 |
| DIR | PA11 | 57 |
| 限位开关输入 | PA26 | 30 |
| GND | 系统 GND | 41 |

### 4.2 小臂步进电机

| 驱动器信号 | MSPM0 引脚 | LQFP-64 脚号 |
|---|---|---:|
| STEP/PUL | PA8 | 54 |
| DIR | PA9 | 55 |
| 限位开关输入 | PA27 | 31 |
| GND | 系统 GND | 41 |

步进驱动器的电机电源不能由 MCU 的 3.3 V 引脚提供。驱动器信号地、电机电源地和 MCU 地必须连接在一起。

## 5. 限位开关和按键接线

所有限位开关和按键均为内部上拉、低电平触发，接线方式如下：

```text
MSPM0 GPIO ───── 按键或限位开关 ───── GND
```

| 状态 | GPIO 电平 |
|---|---|
| 松开/未触发 | 高电平 |
| 按下/触发 | 低电平 |

按键或限位开关的另一端应接 GND，不要接 3.3 V。

## 6. 舵机接口

| 舵机接口 | 连接 |
|---|---|
| PWM 信号 | PA12，LQFP-64 第5脚 |
| 舵机电源 | 按舵机额定电压外部供电 |
| 舵机 GND | 与 MSPM0 共地 |

PA12 输出 50 Hz 舵机 PWM。舵机电源不能由 MCU GPIO 提供。

## 7. K230/串口助手接口

| MSPM0 端 | 对端连接 |
|---|---|
| PB4 / UART1_TX | K230 RX |
| PB5 / UART1_RX | K230 TX |
| GND | K230 GND |

串口配置：

```text
115200 baud
8 data bits
1 stop bit
no parity
3.3 V TTL
```

MSPM0 和 K230 必须共地。该接口不能直接连接 RS-232 电平。

## 8. TB6612 与 N20 旋转电机

### 8.1 TB6612 控制接口

| TB6612 引脚 | 连接 | 说明 |
|---|---|---|
| PWMA | PA7 | 32 kHz PWM |
| AIN1 | PB0 | 方向控制 |
| AIN2 | PB1 | 方向控制 |
| STBY | 直接接 3.3 V | 不连接 MCU |
| VCC | 3.3 V | TB6612 逻辑电源 |
| VM | 电机电源 | 原驱动包测试使用 5 V |
| AO1、AO2 | N20 电机两端 | 电机输出 |
| GND | 系统公共地 | 必须与 MCU 共地 |

PB10 不再用于 STBY，PB10 现在只用于状态 LED。

### 8.2 N20 编码器接口

| 编码器接口 | MSPM0 引脚 | LQFP-64 脚号 |
|---|---|---:|
| A 相 | PB11 | 63 |
| B 相 | PB14 | 2 |
| GND | 系统 GND | 41 |
| VCC | 按编码器额定电压连接 | — |

注意事项：

- 编码器输出到 MSPM0 的电压不能超过 3.3 V；
- PB11、PB14 当前没有配置内部上拉或下拉；
- 编码器双边沿和四倍频读取代码已经完成；
- 当前固件默认关闭编码器中断，只有调用 `App_RotationEncoder_Enable()` 后才开始计数；
- 目前编码器尚未接入拼图旋转控制逻辑。

## 9. 电磁铁 MOS 模块

| MOS 模块接口 | 连接 |
|---|---|
| IN/TRIG | PA30，LQFP-64 第37脚 |
| GND | 系统 GND |
| 模块/线圈电源 | 根据模块和电磁铁规格外部供电 |

控制逻辑：

| PA30 电平 | 电磁铁状态 |
|---|---|
| 高电平 | 通电吸取拼图 |
| 低电平 | 断电放下拼图 |

PA30 只输出 MOS 模块的控制电平，不能直接给电磁铁线圈供电。

## 10. LED 和蜂鸣器

| 功能 | MCU 引脚 | LQFP-64 脚号 | 有效电平 |
|---|---|---:|---|
| 状态/完成 LED | PB10 | 62 | 高电平有效 |
| 蜂鸣器 | PA2 | 42 | 高电平有效 |

上电时 LED 和蜂鸣器默认关闭。

如果使用裸 LED，必须串联限流电阻。如果使用的不是带驱动模块的有源蜂鸣器，应根据工作电流增加三极管或 MOS 驱动，不能在没有确认电流的情况下直接由 PA2 供电。

## 11. SWD 烧录与调试接口

| LQFP-64 脚号 | MCU 引脚 | 调试接口 |
|---:|---|---|
| 12 | PA19 | SWDIO |
| 13 | PA20 | SWCLK |
| 38 | NRST | RESET |
| 40 | VDD | 3.3 V / VTref |
| 41 | VSS | GND |

PCB 建议至少预留以下烧录端口：

```text
3.3V / VTref
GND
SWDIO
SWCLK
NRST
```

## 12. MCU 电源相关引脚

| LQFP-64 脚号 | 引脚 | 连接要求 |
|---:|---|---|
| 40 | VDD | 3.3 V 电源 |
| 41 | VSS | GND |
| 32 | VCORE | 按 TI 参考设计连接核心稳压电容，不能作为普通电源输出 |
| 38 | NRST | 复位/调试接口 |

当前系统按 3.3 V 逻辑设计。每个电源入口和电机驱动器附近均应布置合适的去耦和储能电容。

## 13. PCB 网络命名建议

建议在原理图中使用以下网络名：

```text
STAGE1_STEP
STAGE1_DIR
STAGE1_LIMIT_N

STAGE2_STEP
STAGE2_DIR
STAGE2_LIMIT_N

KEY1_REHOME_N
KEY2_AREA_MARK_N
KEY3_ORIGIN_MARK_N
KEY4_RESERVED_N

SERVO_PWM

K230_UART_TX
K230_UART_RX

ROTATE_MOTOR_PWM
ROTATE_MOTOR_AIN1
ROTATE_MOTOR_AIN2
ROTATE_ENCODER_A
ROTATE_ENCODER_B

MAGNET_CTRL
STATUS_LED
BUZZER

SWDIO
SWCLK
NRST
```

名称末尾的 `_N` 表示该信号低电平有效。

## 14. 上电默认安全状态

V24 固件上电初始化完成后：

| 外设 | 默认状态 |
|---|---|
| 两路步进电机 | 等待回零程序控制 |
| N20 旋转电机 | 停止、滑行 |
| 电磁铁 | 关闭 |
| LED | 关闭 |
| 蜂鸣器 | 关闭 |
| 编码器中断 | 关闭 |
| 舵机 | 抬笔位置 |

## 15. LaunchPad 使用提醒

如果 PCB 是给整个 LP-MSPM0G3507 LaunchPad 插接使用，而不是直接焊接 LQFP-64 MCU，需要重新按照 LaunchPad 的 J1～J4 BoosterPack 排针和底部扩展排针映射连接。

LaunchPad 上部分引脚还连接了板载电路或跳线，例如：

- PA10、PA11 与 XDS 后台 UART 路径有关；
- PA26、PA27 与板载光传感器跳线有关；
- PB26、PB27 与板载 RGB LED 跳线有关。

设计 LaunchPad 底板时应结合跳线状态检查冲突，不能直接把本文的 LQFP-64 脚号当成 LaunchPad 排针号。

## 16. 参考资料

- [TI MSPM0G3507 产品与数据手册页面](https://www.ti.com/product/MSPM0G3507)
- [TI LP-MSPM0G3507 LaunchPad 用户指南](https://www.ti.com/lit/ug/slau873d/slau873d.pdf)
- 项目配置：`TI_moban.syscfg`
- 自动生成引脚定义：`ti_msp_dl_config.h`
- 执行器接口：`APP/Inc/app_actuator.h`

