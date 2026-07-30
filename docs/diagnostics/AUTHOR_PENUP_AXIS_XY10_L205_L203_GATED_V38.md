# V38 全抬笔独立门控 XY10 方向探测

日期：2026-07-22

## 目的

用户提供的 V37 ALIGN 实机照片表明，旧的 `(150,20)` ALIGN 点位于当前纸张
上部偏右，V37 的 `(11,88)` 摆纸平移没有得到实物空间验证。因此停止 V37
`M808`，先用 V38 在 ALIGN 周围确认命令轴对应的真实物理方向。

实机照片：
`docs/diagnostics/V37_ALIGN_ACTUAL_20260722.jpg`

SHA-256：
`A3F9EF701210E487667CC945C6E727E641762830823A52494307ED533FA76463`

V38 不验证整页 A4，不写字，不启用普通 G-code，也不包含 V37 的全页扫掠。

## 安全设计

- ALIGN 仍为已经使用过的 `(150,20) mm`。
- 所有探测点均抬笔，路径中落笔目标为 0。
- 执行器不包含 `App_Servo_Pen_Down` 调用。
- 每份门控文件只移动一次，完成后停住并等待下一份文件。
- 每次最大直线位移：`10.000000 mm`。
- 顺序：`+X、回中、-X、回中、+Y、回中、-Y、回中`。
- 方向补偿关闭，preload 关闭，普通 G-code 禁用。
- 1 mm 笛卡尔分段保持不变。

离线整数脉冲检查：

```text
targets:                    8
independent gates:          8
draw targets:               0
path CRC32:                 F5813CC8
segments:                   80
master pulses:              974
pulse positions checked:    975
minimum joint margin:       26.082823 degrees
maximum DDA deviation:      0.093719 mm
maximum endpoint error:     0.039768 mm
beta range:                 134.024092..139.982587 degrees
minimum abs(sin(beta)):     0.643020391
maximum Jacobian condition: 2.746351
```

## 固件

```text
Build ID:
AUTHOR_PENUP_AXIS_XY10_L205_L203_GATED_V38

HEX:
keil/AUTHOR_PENUP_AXIS_XY10_L205_L203_GATED_V38.hex

SHA-256:
9777B6F4DE143A7426F28F6126C990B392F4BE2EA3822E9DF2FE3408670B4A6A

Keil build:
0 Error(s), 0 Warning(s)
```

## 必须严格依次运行的门控文件

```text
1. AUTHOR_PENUP_AXIS_PROBE_ALIGN_RUN_V38.gcode       M801  -> ALIGN
2. AUTHOR_PENUP_AXIS_PROBE_X_PLUS_10_RUN_V38.gcode   M809  -> (160,20)
3. AUTHOR_PENUP_AXIS_PROBE_X_CENTER_RUN_V38.gcode    M810  -> (150,20)
4. AUTHOR_PENUP_AXIS_PROBE_X_MINUS_10_RUN_V38.gcode  M811  -> (140,20)
5. AUTHOR_PENUP_AXIS_PROBE_X_RETURN_RUN_V38.gcode    M812  -> (150,20)
6. AUTHOR_PENUP_AXIS_PROBE_Y_PLUS_10_RUN_V38.gcode   M813  -> (150,30)
7. AUTHOR_PENUP_AXIS_PROBE_Y_CENTER_RUN_V38.gcode    M814  -> (150,20)
8. AUTHOR_PENUP_AXIS_PROBE_Y_MINUS_10_RUN_V38.gcode  M815  -> (150,10)
9. AUTHOR_PENUP_AXIS_PROBE_Y_RETURN_RUN_V38.gcode    M816  -> (150,20)
```

每份文件只有 `G21/G90/G94/M5/M80x`，没有 X/Y 坐标、`G0/G1`、`M3`
或主机轨迹。固件只接受当前状态所需的下一条门控，顺序错误会拒绝。

## 实机步骤

1. 确认笔已经明显抬起；首次测试也可以暂时取下笔。
2. 清除笔尖周围至少 20 mm 内的夹子、尺子和线缆。
3. 烧录命名的 V38 HEX，复位并等待完整回零。
4. 发送 `STATUS`，确认 Build ID 为 V38，并显示
   `WAIT_ALIGN action=M801 lim1=0 lim2=0 pen=UP`。
5. 只运行第 1 份 ALIGN 文件，等待 `WAIT_PROBE action=M809`。
6. 从第 2 份开始，每次只运行一份；等待完全停止和 `STAGE_DONE` 后，记录
   笔尖相对照片的移动方向，再运行下一份。
7. 任何一次移动明显超过 10 mm、靠近障碍、出现异常声响或限位触发，立即
   发送 `STOP`，不要再运行后续文件。
8. M816 完成后状态为 `DONE`，笔尖回到 ALIGN；下一轮必须重新复位回零。

建议按下列格式回报：

```text
M809 (+X) = 照片左 / 右 / 上 / 下
M811 (-X) = 照片左 / 右 / 上 / 下
M813 (+Y) = 照片左 / 右 / 上 / 下
M815 (-Y) = 照片左 / 右 / 上 / 下
四次回中是否回到原点 = 是/否
异常声音、限位或碰撞 = 有/无
```

禁止运行 V37 的 `M808`，禁止运行 `2.0.gcode`，禁止切换到
`GCODE_SERIAL`。

## 实机结果（2026-07-22）

用户按顺序完成全部 V38 门控并确认：

```text
M809 (+X) = 照片上
M811 (-X) = 照片下
M813 (+Y) = 照片左
M815 (-Y) = 照片右
M810/M812/M814/M816 回中 = 正常，回到同一位置
异常声音、限位或碰撞 = 无
```

因此当前照片方向下，若纸面 X 沿 A4 的 297 mm 长边、纸面 Y 沿 210 mm
短边，则纸面 `+X` 应朝照片上方、纸面 `+Y` 应朝照片左方，纸面左下原点
位于照片中的纸张右下角。V37 使用的实物摆纸方向不成立，`M808` 保持停用。
