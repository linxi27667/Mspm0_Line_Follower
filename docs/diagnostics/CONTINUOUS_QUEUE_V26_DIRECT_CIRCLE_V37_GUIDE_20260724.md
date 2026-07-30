# 连续运动 V26 / 中排无映射圆 V37 测试说明

日期：2026-07-24

## 本轮目的

本轮只验证一个问题：

> 去掉旧执行器每条 G1 完全停止、返回 `ok`、再重新启动的行为以后，
> 18 mm 圆是否明显恢复圆度。

这不是纸面映射复测，也不是字体测试。

## 必须配套使用的文件

- 固件：
  `keil\PAPER_A4_CONTINUOUS_QUEUE_GCODE_V26.hex`
- G-code：
  `gcode\PAPER_A4_CONTINUOUS_QUEUE_DIRECT_6CIRCLE_D18_GCODE_V37.gcode`
- 预览：
  `docs\diagnostics\PAPER_A4_CONTINUOUS_QUEUE_DIRECT_6CIRCLE_D18_GCODE_V37_PREVIEW.png`

固件 SHA-256：

`68B87F7A6058F35D6B3CEC1B50EE7E90EEADBE96B67C6EE03D29E3B4FD8B3255`

G-code SHA-256：

`BB2535E239BC3503A629B3D34FAA7936596A0F6E4C96CD484947302360B5762D`

`Jlink.jflash` 已指向本轮 V26 固件。

## 与旧固件的关键区别

- 双轴运动使用 32 块环形队列。
- 当前块结束时，步进中断直接装载下一块。
- 相同速度的相邻块不再关闭定时器并返回主循环。
- G0/G1 在安全检查并进入队列后返回 `ok`，不等待物理运动完成。
- M3、M5、G4 会等待队列清空，再落笔、抬笔或停顿。
- 队列运动增加了基础启停速度斜坡。
- 保留当前 `L1=205 mm`、`L2=203 mm` 的不等臂逆解。

本轮尚未实现作者 GRBL 的完整 junction-deviation 前瞻和 AMASS，因此不要把
V26 当成最终生产固件。

## 纸面映射状态

本轮固件：

`GCODE_SERIAL_PAPER_MAP_ENABLE = 0`

也就是 G-code 的 X/Y 直接进入当前用户坐标，再进入 SCARA 逆解。

V37 为了把图案放到纸面中间空白处，只用旧映射计算了六个圆的“中心落点”；
每个圆的 72 个圆周点是在该用户坐标中心周围直接按半径 9 mm 生成的，没有对
圆周逐点应用纸面映射。因此旧映射不会把本轮圆周主动拉成椭圆。

不要用 V26 发送旧的文字、4×7 校准或 V36 映射对照文件。它们与本轮坐标合同
不匹配。

## 图案位置

V37 只画一排 6 个圆：

- 名义纸面位置 Y = 140 mm
- 半径 = 9 mm
- 直径 = 18 mm
- 从左到右：CW、CCW、CW、CCW、CW、CCW
- 名义纸面圆心 X：41、63、94、116、147、169 mm

设计上放在上一张照片上下两排圆之间的空白区域。

## 操作步骤

1. 保持 A4、夹板、机械臂底座与上一轮相同，不要移动。
2. 用 `Jlink.jflash` 烧录 V26。
3. 复位并等待自动回零完成。
4. 发送 `STATUS`。
5. 必须看到：
   - `id=PAPER_A4_CONTINUOUS_QUEUE_GCODE_V26`
   - `map_enable=0`
   - `pen=UP`
   - 两个限位均已释放
6. 使用现有逐行等待 `ok` 的发送器发送 V37：

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\send_standard_gcode_wait_ok.ps1 `
  -FilePath .\gcode\PAPER_A4_CONTINUOUS_QUEUE_DIRECT_6CIRCLE_D18_GCODE_V37.gcode
```

## 现场重点观察

- 单个圆的 72 个小段之间不应出现肉眼可见的停顿。
- 只允许在每个圆结束后的 M5/M3 之间停顿。
- 如果仍能听到每个小段一次明显“顿、顿、顿”的声音，立即停止并记录串口日志。
- 出现限位触发、位置明显越界或图案可能覆盖旧笔迹时，立即发送 `STOP`。

## 拍照要求

画完后拍一张：

- 完整 A4 四个边角都在画面内；
- 尺子与圆处于同一平面；
- 镜头尽量垂直纸面；
- 六个圆都清晰；
- 不要旋转或镜像照片。

判断顺序：

1. 先看 CW/CCW 是否都变圆；
2. 再看左右区域是否仍有系统性的宽高差；
3. 最后才讨论坐标映射和机械标定。
