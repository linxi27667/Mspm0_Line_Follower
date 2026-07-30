# 嵌入式架构重构计划 - 符合裸机版Skills规范

## 问题诊断

根据"嵌入式架构师(裸机版)"skills规范，发现以下不符合项：

### 1. app_encoder_motor.c - HW_Timer_Init 违反规范
**当前代码**：
```c
static void HW_Timer_Init(void)
{
    DL_TimerG_enableClock(App_Motor_Left.pwm_timer);  // 直接访问全局对象
    DL_TimerG_startCounter(App_Motor_Left.pwm_timer, DL_TIMER_COUNTER_RUN);
    DL_TimerG_enableClock(App_Motor_Left.enc_timer);  // 直接访问全局对象
    DL_TimerG_startCounter(App_Motor_Left.enc_timer, DL_TIMER_COUNTER_RUN);
}
```

**Skills规范要求**：
```c
static void HW_Motor_Init(bsp_motor_t *motor) {
    if (motor == NULL) return;
    DL_TimerG_enableClock(motor->pwm_timer);  // 通过参数访问
    DL_TimerG_enableClock(motor->enc_timer);  // 通过参数访问
    motor->Gpio_Config();
}
```

**问题**：HW函数直接访问全局对象 `App_Motor_Left`，而不是通过参数传入。这导致：
- BSP层无法复用（换电机对象要重写HW函数）
- 违反"函数指针必须通过参数传递"的规范

### 2. app_stepper.c - HW_Stepper_Init 符合规范
```c
static void HW_Stepper_Init(void)  // 无参数，但内部只调用HW_GPIO_Config
{
    HW_GPIO_Config();  // GPIO配置已绑定到宏，无需传参
}
```
**判断**：步进电机只需GPIO配置，无需定时器，当前设计合理。

### 3. app_sw_i2c.c - HW_I2C_Init 符合规范
```c
static void HW_I2C_Init(void)  // 无参数，但内部只配置GPIO
{
    DL_GPIO_initDigitalOutputFeatures(...);  // 使用宏定义
}
```
**判断**：I2C只需GPIO配置，无需传参，当前设计合理。

---

## 修改计划

### 修改文件1: app_encoder_motor.c

**目标**：将 `HW_Timer_Init(void)` 改为 `HW_Motor_Init(bsp_motor_t *motor)`

**修改内容**：
1. 函数签名改为 `static void HW_Motor_Init(bsp_motor_t *motor)`
2. 内部使用 `motor->pwm_timer`、`motor->enc_timer` 访问
3. 调用 `motor->Gpio_Config()`
4. 对象实例化中 `.Init = HW_Motor_Init`
5. `App_Motor_System_Init()` 中调用 `HW_Motor_Init(&App_Motor_Left)`

**修改后代码**：
```c
static void HW_Motor_Init(bsp_motor_t *motor)
{
    if (motor == NULL) return;
    
    DL_TimerG_enableClock(motor->pwm_timer);
    DL_TimerG_startCounter(motor->pwm_timer, DL_TIMER_COUNTER_RUN);

    DL_TimerG_enableClock(motor->enc_timer);
    DL_TimerG_startCounter(motor->enc_timer, DL_TIMER_COUNTER_RUN);
    
    motor->Gpio_Config();
}

bsp_motor_t App_Motor_Left = {
    ...
    .Gpio_Config = HW_GPIO_Config,
    .Init        = HW_Motor_Init,  // 改为 HW_Motor_Init
    ...
};

void App_Motor_System_Init(void)
{
    HW_Motor_Init(&App_Motor_Left);  // 传入对象指针
    BSP_Motor_Init_Device(&App_Motor_Left);
}
```

---

## 验证清单

- [ ] app_encoder_motor.c 编译无错误
- [ ] HW_Motor_Init 通过参数访问 motor->pwm_timer/motor->enc_timer
- [ ] 对象实例化中 .Init 指向 HW_Motor_Init
- [ ] App_Motor_System_Init 调用 HW_Motor_Init(&App_Motor_Left)
- [ ] app_stepper.c 无需修改（已符合规范）
- [ ] app_sw_i2c.c 无需修改（已符合规范）
