# BSP层代码审查报告

## 审查结果总览

| 文件 | 状态 | 问题等级 | 说明 |
|-----|------|---------|------|
| bsp_encoder_motor.h/c | ⚠️ 有BUG | **严重** | Init函数指针签名不匹配 |
| bsp_servo.h/c | ✅ 符合规范 | 无 | 逻辑正确 |
| bsp_stepper.h/c | ⚠️ 有BUG | **严重** | 阻塞式延时，违反裸机规范 |
| bsp_sw_i2c.h/c | ✅ 符合规范 | 无 | 逻辑正确 |
| bsp_mpu6050.h/c | ✅ 符合规范 | 无 | 逻辑正确 |
| bsp_led.h/c | ⚠️ 有BUG | **严重** | 违反BSP层禁令（包含硬件操作） |
| bsp_key.h/c | ⚠️ 有BUG | **中等** | 全局数组设计问题 |
| bsp_uart.h/c | ⚠️ 有BUG | **严重** | 违反BSP层禁令（包含硬件头文件） |

---

## 详细问题分析

### 1. bsp_encoder_motor.h/c - Init函数指针签名不匹配 🔴 严重

**问题**：
```c
// bsp_encoder_motor.h 第40行
void (*Init)(void);  // 无参数

// bsp_encoder_motor.c 第17行
motor->Init();  // 调用无参数版本
```

但 APP 层已经改为：
```c
// app_encoder_motor.c
static void HW_Motor_Init(bsp_motor_t *motor)  // 有参数！
```

**后果**：函数指针签名不匹配，调用时会导致**未定义行为**（可能崩溃或静默失败）。

**修复方案**：
```c
// bsp_encoder_motor.h
void (*Init)(bsp_motor_t *motor);  // 改为有参数

// bsp_encoder_motor.c
if (motor->Init != NULL) {
    motor->Init(motor);  // 传入motor指针
}
```

---

### 2. bsp_stepper.c - 阻塞式延时 🔴 严重

**问题**：
```c
void BSP_Stepper_Run(...) {
    for (uint32_t i = 0; i < steps; i++) {
        stepper->Gpio_Write(...);
        stepper->Delay_us(delay_us);  // 阻塞等待！
        stepper->Gpio_Write(...);
        stepper->Delay_us(delay_us);  // 阻塞等待！
    }
}
```

**违反规范**：裸机架构师skills明确规定"所有异步行为必须用状态机实现，禁止阻塞等待"。

**后果**：
- 步进电机运行期间，整个系统被阻塞
- 无法响应按键、传感器等其他任务
- 时标轮询调度失效

**修复方案**：改为状态机 + 非阻塞延时
```c
typedef enum {
    STEPPER_IDLE = 0,
    STEPPER_DIR_SET,
    STEPPER_STEP_HIGH,
    STEPPER_STEP_LOW
} stepper_state_t;

void BSP_Stepper_Task(bsp_stepper_t *stepper) {
    switch (stepper->state) {
        case STEPPER_IDLE:
            if (stepper->steps_remaining > 0) {
                stepper->state = STEPPER_DIR_SET;
            }
            break;
        case STEPPER_DIR_SET:
            stepper->Gpio_Write(stepper->dir_pin.port, stepper->dir_pin.pin, stepper->dir);
            stepper->state = STEPPER_STEP_HIGH;
            break;
        case STEPPER_STEP_HIGH:
            stepper->Gpio_Write(stepper->step_pin.port, stepper->step_pin.pin, 1);
            stepper->delay_counter = 0;
            stepper->state = STEPPER_STEP_LOW;
            break;
        case STEPPER_STEP_LOW:
            stepper->delay_counter++;
            if (stepper->delay_counter >= stepper->delay_ticks) {
                stepper->Gpio_Write(stepper->step_pin.port, stepper->step_pin.pin, 0);
                stepper->steps_remaining--;
                stepper->state = STEPPER_STEP_HIGH;
            }
            break;
    }
}
```

---

### 3. bsp_led.c - 违反BSP层禁令 🔴 严重

**问题**：
```c
#include "bsp_common.h"  // 可能包含硬件头文件

void BSP_Led_Init(led_t *led) {
    for (uint8_t i = 0; i < BSP_LED_NUM; i++) {
        GPIO_WritePin(led[i].port, led[i].pin, led[i].state);  // 直接操作硬件！
    }
}
```

**违反规范**：BSP层"严禁包含任何硬件头文件"，且不应直接调用 `GPIO_WritePin`。

**修复方案**：使用函数指针抽象
```c
typedef struct {
    void    *port;
    uint32_t pin;
    uint8_t  state;
    void (*Gpio_Write)(void *port, uint32_t pin, uint8_t level);  // 新增
} led_t;

void BSP_Led_On(led_t *led) {
    if (led->Gpio_Write) {
        led->Gpio_Write(led->port, led->pin, LED_ON);
    }
    led->state = LED_ON;
}
```

---

### 4. bsp_uart.c - 违反BSP层禁令 🔴 严重

**问题**：
```c
#include <ti/driverlib/driverlib.h>  // 硬件头文件！
#include <ti/devices/msp/msp.h>       // 硬件头文件！

static void HW_UART_Periph_Init(void) {
    DL_UART_enablePower(BSP_UART_PERIPH);  // 直接操作硬件！
    ...
}
```

**违反规范**：BSP层"严禁包含任何硬件头文件"。

**修复方案**：将硬件初始化移到APP层
```c
// bsp_uart.h - 只保留纯逻辑
typedef struct {
    void (*Send)(const uint8_t *data, uint16_t len);
    void (*Rx_Callback)(uint8_t data);
} bsp_uart_t;

// app_uart.c - 硬件绑定
static void HW_UART_Send(const uint8_t *data, uint16_t len) {
    DL_UART_Main_transmitData(UART0, data[0]);
}
```

---

### 5. bsp_key.c - 全局数组设计问题 🟡 中等

**问题**：
```c
bsp_key_t bsp_keys[BSP_KEY_NUM];  // 全局数组定义在.c中

void BSP_Key_Scan(bsp_key_t *key) {
    for (uint8_t i = 0; i < BSP_KEY_NUM; i++) {  // 但遍历的是全局数组
        key[i].state = GPIO_ReadPin(key[i].port, key[i].pin);
        ...
    }
}
```

**问题**：函数参数 `key` 传入但实际遍历的是全局 `bsp_keys`，导致参数无用。

**修复方案**：移除全局数组，完全依赖参数
```c
void BSP_Key_Scan(bsp_key_t *keys, uint8_t num) {
    for (uint8_t i = 0; i < num; i++) {
        keys[i].state = ...;
        ...
    }
}
```

---

## 修复优先级

1. **🔴 立即修复**：bsp_encoder_motor.h Init签名不匹配（会导致崩溃）
2. **🔴 立即修复**：bsp_led.c/bsp_uart.c 违反BSP层禁令（架构错误）
3. **🔴 建议修复**：bsp_stepper.c 阻塞式延时（系统卡死风险）
4. **🟡 后续优化**：bsp_key.c 全局数组设计
