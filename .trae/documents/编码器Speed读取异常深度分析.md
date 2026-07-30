# 编码器 Speed 读取异常问题分析与修复计划

## 📋 问题现象

从日志数据分析：
```
[I] MOTOR: Spd:-1 Pos:-3308744 PWM:50
[I] MOTOR: Spd:0 Pos:-3311669 PWM:50
[I] MOTOR: Spd:-1 Pos:-3314592 PWM:50
...
```

| 现象 | 数值 | 问题分析 |
|------|------|----------|
| **Speed** | 大部分 -1 或 0 | ❌ 异常，正常应该每次约 100-1000 |
| **Position** | 每次变化约 -2924 | ⚠️ 正常范围 |
| **PWM** | 50 | ✅ 正常 |

---

## 🔍 问题根源分析

### **关键矛盾点**

1. **Speed 大部分为 -1**：说明 `encoder_speed` 大部分时间是 -1
2. **Position 变化正常**：说明累加是正确的
3. **但 Speed 和 Position 对不上**：如果 Speed=-1，Position 应该几乎不变

### **可能的原因**

#### **原因 1：DL_Timer_getTimerCount 在 QEI 模式下不是返回编码器值**

在 QEI 模式下，`DL_Timer_getTimerCount` 可能返回的是**普通计数器**，而不是 QEI 位置计数。

#### **原因 2：有符号/无符号转换问题**

```c
uint32_t current_count = DL_Timer_getTimerCount(...) & 0xFFFF;  // 返回 0-65535
int16_t delta = (int16_t)(current_count - last_count);          // 可能有符号问题
```

如果 `current_count = 0`，`last_count = 1`：
- `current_count - last_count = -1` (uint32_t 结果是 4294967295)
- `(int16_t)(-1)` = -1

#### **原因 3：计数器在 QEI 模式下是 0 或很小**

如果 QEI 计数器初始值很小或一直是 0，那差值就会很小甚至为负。

---

## 🎯 诊断步骤

### **步骤 1：添加调试打印，直接显示计数器原始值**

修改 `HW_Enc_Read` 函数，添加调试日志：

```c
static int32_t HW_Enc_Read(void *enc_timer)
{
    static uint32_t last_count = 0;
    static bool first_read = true;

    uint32_t current_count = DL_Timer_getTimerCount((GPTIMER_Regs *)enc_timer) & 0xFFFF;

    if (first_read) {
        last_count = current_count;
        first_read = false;
        log_i("DEBUG", "First Read: %u", current_count);
        return 0;
    }

    uint32_t raw_delta = current_count - last_count;
    int16_t delta = (int16_t)(current_count - last_count);

    log_i("DEBUG", "Cur:%u Last:%u Raw:%u Delta:%d",
          current_count, last_count, raw_delta, delta);

    last_count = current_count;
    return (int32_t)delta;
}
```

### **步骤 2：检查 SysConfig QEI 配置**

确认 Encoder_Timer (TIMG8) 的配置：
- Mode: QEI (不是 Capture)
- Count Direction: 确认是正向还是反向
- Load Value: 应该是 65535 (16位计数器)

### **步骤 3：检查硬件接线**

- E1A → PB21
- E1B → PB22
- 确认编码器是增量式编码器

---

## 🔧 修复方案

### **方案 1：如果 QEI 计数器是向下计数**

修改 delta 计算：

```c
// 向下计数时，差值取反
int16_t delta = (int16_t)(last_count - current_count);
```

### **方案 2：如果 DL_Timer_getTimerCount 返回的不是 QEI 值**

可能需要在 SysConfig 中使用不同的 QEI 配置，或者使用其他寄存器读取 QEI 位置。

### **方案 3：检查 QEI 计数方向寄存器**

MSPM0 的 QEI 模块有一个方向寄存器 `QDIR`，可以读取当前计数方向。

---

## 📝 实施步骤

1. [ ] 修改 `HW_Enc_Read` 添加调试日志
2. [ ] 编译并下载
3. [ ] 观察原始计数器值和差值
4. [ ] 根据调试结果确定修复方案
5. [ ] 应用修复并验证

---

## ⚠️ 注意事项

- Speed 大部分为 -1 说明 `delta = -1` 大部分时间
- 这可能意味着 `current_count <= last_count` 大部分时间
- 需要确认 QEI 计数器是向上还是向下计数
