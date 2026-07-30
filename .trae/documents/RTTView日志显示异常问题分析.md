# RTTView 日志显示异常问题分析计划

## 📋 问题现象

用户发现一个**非常奇怪的现象**：

| 情况 | DEBUG 日志状态 | Speed 显示 |
|------|---------------|-----------|
| **情况 1** | 启用 DEBUG 日志 | ✅ 正常（11） |
| **情况 2** | 注释 DEBUG 日志 | ❌ 异常（0-1） |

**矛盾点**：注释日志不应该影响功能逻辑！

---

## 🔍 可能的原因分析

### **原因 1：RTTView 脚本解析问题**

用户提供的 RTTView 路径：`E:\MCU\BSP\RTTView`

RTTView 脚本可能：
- 没有正确解析日志格式
- 缓冲区刷新不及时
- 日志过滤逻辑有问题

### **原因 2：RTT 缓冲区时序问题**

当 DEBUG 日志启用时：
- RTT 缓冲区频繁刷新
- MOTOR 日志能正确显示

当 DEBUG 日志注释时：
- RTT 缓冲区刷新频率降低
- MOTOR 日志可能被延迟或覆盖

### **原因 3：编译器优化问题**

注释日志后，编译器可能：
- 优化了某些变量访问
- 改变了代码执行顺序
- 但这不太可能，因为 Position 是正确的

### **原因 4：main.c 中打印时机问题**

main.c 中：
```c
App_Motor_Update_Status();  // 更新 encoder_speed

if (50ms 定时) {
    log_i("MOTOR", "Spd:%d ...", App_Motor_Left.encoder_speed);
}
```

问题可能是：
- `encoder_speed` 在 50ms 内被多次更新
- 最后一次更新可能返回 0（因为计数器溢出边界）

---

## 🎯 诊断步骤

### **步骤 1：检查 RTTView 脚本**

查看 `E:\MCU\BSP\RTTView` 目录下的脚本，确认：
- 日志解析逻辑
- 缓冲区刷新机制
- 是否有过滤或延迟

### **步骤 2：分析 main.c 执行流程**

问题可能是：
- `App_Motor_Update_Status()` 在 while(1) 中**每次循环都调用**
- 但 `log_i` 只在 **50ms 定时**时打印
- 在 50ms 内，`encoder_speed` 可能被更新了**多次**
- 最后一次更新可能返回很小的值（溢出边界）

### **步骤 3：验证假设**

修改 main.c，只在 50ms 定时内调用一次 `App_Motor_Update_Status()`：

```c
while (1) 
{
    /* 非阻塞 50ms 打印 */
    if ((s_sys_tick - s_last_print_tick) >= PRINT_INTERVAL_MS) {
        s_last_print_tick = s_sys_tick;
        
        /* 只在打印时更新一次 */
        App_Motor_Update_Status();
        
        log_i("MOTOR", "Spd:%d Pos:%d PWM:%d", ...);
    }
}
```

---

## 🔧 修复方案

### **方案 1：修改 main.c 执行逻辑**

将 `App_Motor_Update_Status()` 移到 50ms 定时块内，确保每次打印前只更新一次。

### **方案 2：检查 RTTView 脚本**

如果 RTTView 有问题，可能需要修改脚本或使用官方 RTT Viewer。

---

## 📝 实施步骤

1. [ ] 检查 RTTView 脚本目录内容
2. [ ] 分析 main.c 执行流程问题
3. [ ] 修改 main.c，将 Update_Status 移到定时块内
4. [ ] 编译测试
5. [ ] 验证 Speed 显示是否正常

---

## ⚠️ 注意事项

- Position 正常增加说明累加逻辑正确
- 问题可能是 `encoder_speed` 在 50ms 内被多次更新，最后一次值很小
- DEBUG 日志启用时，每次更新都打印，所以能看到正确的值