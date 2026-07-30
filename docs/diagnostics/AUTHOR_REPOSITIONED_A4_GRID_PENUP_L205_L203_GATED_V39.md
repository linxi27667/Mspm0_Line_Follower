# V39 重摆 A4 分阶段全抬笔网格探测

日期：2026-07-22

## 输入实机证据

V38 已确认当前照片方向：命令 `+X` 向照片上、`+Y` 向照片左，四次回中
正常，无异常声音、限位或碰撞。

用户按 `(29,111) mm` 十字重新摆纸后的照片：

`docs/diagnostics/A4_REPOSITIONED_ALIGN_29_111_ACTUAL_20260722.jpg`

SHA-256：
`82CA1DE41656A7552CF6AA9F6270A94DDF42FC4201F7BB8943275D1D21F119FC`

照片中纸张已经移到 ALIGN 笔尖的照片上方，笔尖位于靠近纸张下边的位置，
与 V38 实测方向和新平移方向一致。纸张上边附近仍有显示器支架；软件模型不
包含该实体，所以 V39 把上排中央和上排横向运动拆成两个独立门控。

## 坐标合同

```text
A4:                      297 x 210 mm
照片方向 paper +X:       上
照片方向 paper +Y:       左
纸面原点:                照片中的纸张右下角
ALIGN paper:             (29,111) mm
ALIGN command:           (150,20) mm
command mapping:         command = paper + (121,-91) mm
paper inset:             (15,15)..(282,195) mm
command inset:           (136,-76)..(403,104) mm
```

## 安全设计

- 全程抬笔，17 个路径目标的 `draw` 均为 0。
- 执行器不包含 `App_Servo_Pen_Down` 调用。
- 普通 G-code 禁用，不接受 V37 `M808`。
- 方向补偿和 preload 均关闭。
- 1 mm 笛卡尔分段保持不变。
- 八个探测阶段相互独立；每阶段结束后等待下一门控。
- 最大相邻目标跨度 `133.500000 mm`，小于 192 段规划限制。
- 任意异常可发送 `STOP`，随后必须重新回零。

离线验证：

```text
path points:                    17
path CRC32:                     F5B0377A
integer segments:               1622
master pulses:                  18476
pulse positions checked:        18477
minimum path joint margin:      12.295714 degrees
maximum DDA line deviation:     0.106445 mm
maximum endpoint error:         0.048545 mm
full 15 mm inset grid samples:  48508
minimum full-grid pose margin:  12.295714 degrees
minimum abs(sin(beta)):         0.254778537
maximum Jacobian condition:     7.720812
minimum outer radial gap:       48.999787 mm
```

模型未触碰 IK 死区、径向奇点、雅可比奇点或关节硬限位。实体支架、线缆、
笔架外形和自碰撞仍必须由分阶段实机观察确认。

## 固件

```text
Build ID:
AUTHOR_REPOSITIONED_A4_GRID_PENUP_L205_L203_GATED_V39

HEX:
keil/AUTHOR_REPOSITIONED_A4_GRID_PENUP_L205_L203_GATED_V39.hex

HEX SHA-256:
08EF93F610B68EF9780EC37FEE3D202020D87717FCF250575203EFC09BB5710A

Keil:
0 Error(s), 0 Warning(s)
```

## 严格门控顺序

```text
1. M801 ALIGN
   AUTHOR_REPOSITIONED_A4_GRID_ALIGN_RUN_V39.gcode

2. M817 BOTTOM_CENTER: paper (15,111)
   AUTHOR_REPOSITIONED_A4_GRID_BOTTOM_CENTER_RUN_V39.gcode

3. M818 BOTTOM_ROW: paper Y=15 -> 105 -> 195 -> 105 at X=15
   AUTHOR_REPOSITIONED_A4_GRID_BOTTOM_ROW_RUN_V39.gcode

4. M819 MIDDLE_CENTER: paper (148.5,105)
   AUTHOR_REPOSITIONED_A4_GRID_MIDDLE_CENTER_RUN_V39.gcode

5. M820 MIDDLE_ROW: paper Y=15 -> 105 -> 195 -> 105 at X=148.5
   AUTHOR_REPOSITIONED_A4_GRID_MIDDLE_ROW_RUN_V39.gcode

6. M821 TOP_CENTER: paper (282,105)
   AUTHOR_REPOSITIONED_A4_GRID_TOP_CENTER_RUN_V39.gcode

7. M822 TOP_ROW: paper Y=15 -> 105 -> 195 -> 105 at X=282
   AUTHOR_REPOSITIONED_A4_GRID_TOP_ROW_RUN_V39.gcode

8. M823 RETURN_MIDDLE: paper (148.5,105)
   AUTHOR_REPOSITIONED_A4_GRID_RETURN_MIDDLE_RUN_V39.gcode

9. M824 RETURN_ALIGN: paper (29,111)
   AUTHOR_REPOSITIONED_A4_GRID_RETURN_ALIGN_RUN_V39.gcode
```

## 实机步骤

1. 首次 V39 测试建议取下笔，或确认笔尖明显高于纸面。
2. 移除纸张及其 20 mm 外围上方的尺子、夹子和线缆。
3. 特别检查照片中的黑色显示器支架：在运行 M821 前，必须保证笔架移动到
   纸张上排中央时不会从下方或侧面撞到支架；不能确定高度时应直接移开支架。
4. 烧录命名 V39 HEX，复位并等待完整回零。
5. 运行 M801 ALIGN，等待 `WAIT_PROBE action=M817`；重新确认 `(29,111)`
   十字仍在抬起笔尖下方。
6. 从 M817 开始每次只运行一份文件，等完全停止并收到 `STAGE_DONE` 后再继续。
7. M817/M818 完成后确认下排全在纸上；M819/M820 完成后确认中排无碰撞。
8. M821 只到上排中央并停止。此时必须目视检查笔架、连杆和显示器支架间隙。
9. 只有 M821 无碰撞且上排左右方向全部清空后才能运行 M822。
10. M823、M824 依次返回中部和 ALIGN。M824 后为 `DONE`，再次运动必须复位。

任何阶段实际运动方向不符、目标离开纸面、移动明显异常、出现异响或限位触发，
立即发送 `STOP` 并停止后续阶段。不要运行 V37 `M808`、`2.0.gcode` 或
`GCODE_SERIAL`。
