# V31 V7 单线字双遍对照测试

## 目的

V31 只验证一件事：在当前最终机械参数和安全门控不变的条件下，将 V30
的楷体轮廓路径替换为 V7 实机写过的单线“张佳乐”轨迹，观察字形是否恢复。

本版本不是正式多行文字固件。它不启用方向补偿，不切换到 `GCODE_SERIAL`，
也不读取或运行 `2.0.gcode`。

## 固定合同

```text
L1 / L2:                    205 / 203 mm
machine offset:             (-129,+128) mm
Stage1 / Stage2:            40.099216 / 40.115790 steps/degree
theta / psi limit:          -0.773082 / 134.177381 degrees
direction compensation:     disabled
independent preload:        disabled
author line execution:      disabled
Cartesian segment:          1 mm
move / draw feed:           600 / 240 mm/min
servo:                      0 degrees down, 90 degrees up
pen settle:                 500 ms
```

回零、ALIGN、AXES 和 BOX 路径与 V30 相同。

## 单线路径

来源：

```text
backups/GCODE_HOME0_135_CENTER_ANCHOR_V7_20260718_222427/gcode/G_Code.txt.gcode
SHA-256: 901648BF916FBF353F1026387F520284D39FA77782B1BC081496B06B0FA208FD
```

原 V7 检查口径：262 行、27 笔、140 次有效运动（G0=26、G1=114），最终抬笔。

V31 不缩放原字形。它将路径水平居中到 V30 已验证的文字区域，并使用 V30
原来的两条基线：

```text
first copy baseline Y:      67.0 mm
second copy baseline Y:     87.0 mm
generated bounds:           X=197.6..214.3, Y=61.3..87.0 mm
points:                     292
pen-up stroke starts:       54 (27 per copy)
draw points:                238
path CRC32:                 8D4C4EBD
```

由于继续使用 V30 的 `0.15 mm` 位置容差，292 个目标中有 42 个微小目标不启动
电机；落笔/抬笔状态仍逐笔执行。这与原 V7 检查器也会忽略低于位置容差的微动
是同一类处理。

预览：

```text
docs/diagnostics/AUTHOR_STAGED_V7_SINGLELINE_X2_L205_L203_GATED_V31_PREVIEW.png
SHA-256: 90D7CCDAD34FA90EE2F659478547DB87803CB831CF8293A546E80E6E7ED190B1
```

灰色斜线是抬笔换行移动，不会落笔画出。

## 固件

```text
keil/AUTHOR_STAGED_V7_SINGLELINE_X2_L205_L203_GATED_V31.hex
SHA-256: 02C5E5B81661D9CEBADFAB901FA10D6EFE52F7AC00E6083920D46EAC17B043A2

Build ID: AUTHOR_STAGED_V7_SINGLELINE_X2_L205_L203_GATED_V31
Build:    0 Errors, 0 Warnings
```

只烧录上述命名 HEX，不烧录 `keil/Objects` 下的通用 HEX。

## A4 坐标和 ALIGN

```text
A4:             横放，长边左右、短边上下
照片右侧:       +X
照片上方:       +Y
纸面原点:       左下角
ALIGN:          (150,20) mm
```

在纸上从左边缘向右量 `150 mm`、从下边缘向上量 `20 mm` 画小十字。
完成 M801 后移动并固定 A4，使小十字位于抬起的笔尖正下方。

## 四个门控文件

```text
gcode/AUTHOR_V7_SINGLELINE_ALIGN_RUN_V31.gcode
SHA-256: 09C8AC2B36403133AC169C8F96BD3AEBFCFD206F0895A932C93CE34E74918CFE

gcode/AUTHOR_V7_SINGLELINE_AXES_RUN_V31.gcode
SHA-256: 8ABA4D0DEC45EB8C19AF22B2D8329EA4AB92EBED43419F4BCF3DFFE91759D345

gcode/AUTHOR_V7_SINGLELINE_BOX_RUN_V31.gcode
SHA-256: 849C36293F327D32CA96C2841E5E30AB67A0D672A10B25FDD158FCA752A6A144

gcode/AUTHOR_V7_SINGLELINE_TEXT_RUN_V31.gcode
SHA-256: 3720684529170F025773D87984BFF49381DEB05F8D8DD3091C9BEDDD361C39FE
```

每个文件只有 `G21/G90/G94/M5/M80x`，没有坐标、落笔或主机轨迹。

## 严格实机顺序

1. 烧录命名的 V31 HEX，复位并等待完整回零。
2. 发送 `STATUS`，确认 Build ID 正确，且为
   `state=WAIT_ALIGN action=M801 lim1=0 lim2=0 pen=UP`。
3. 加载 ALIGN 文件，只按一次 Run。等待
   `completed=ALIGN state=WAIT_AXES action=M802`。
4. 用 `(150,20)` 小十字对齐并固定横向 A4。
5. 加载 AXES 文件，只按一次 Run。等待
   `completed=AXES state=WAIT_BOX action=M803`，并确认 +X 向右、+Y 向上。
6. 加载 BOX 文件，只按一次 Run。等待
   `completed=BOX state=WAIT_TEXT action=M804`，并确认两只框均在纸上且运动安全。
7. 加载 TEXT 文件，只按一次 Run。它先写下方一遍，再写上方一遍。
8. 等待 `completed=TEXT state=DONE pen=UP rehome=1`。再次运动前必须复位回零。

不要把四个门控文件连续发送。状态不匹配时发送下一门，会得到 `wrong_gate`；
应先发送 `STATUS` 核对当前 `state/action`，不要重复发送或跳过阶段。

运行阶段只允许 `STATUS` 或 `STOP`。机械危险时直接切断电机电源。

## 离线结果

```text
TEXT executor targets:          250
TEXT Cartesian segments:       415
TEXT master pulses:             3056
TEXT minimum joint margin:      29.745201 degrees
TEXT minimum paper margin:      61.300000 mm
TEXT maximum line deviation:    0.089848 mm
TEXT maximum endpoint error:    0.064721 mm
```

检查命令：

```powershell
python .\tools\check_author_v7_singleline_v31.py
```
