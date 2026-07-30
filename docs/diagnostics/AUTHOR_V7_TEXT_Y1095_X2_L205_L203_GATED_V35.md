# V35 V7 单线字局部 Y1095 两行试写

## 目的

V34 在文字区域中心 `O=(205,65) mm` 的实机结果为：

```text
O-W / O-E / O-S / O-N = 20 / 20 / 20 / 20 mm
中心重复落点最大差约 1 mm
```

因此 V35 只把已经验证的文字区域局部 `Y=1.095` 命令换算用于一次小范围试写，
观察存档 V7 单线字形“张佳乐”在当前机械参数下的实际效果。该换算没有推广到整张
A4，也没有修改电机比例、机械臂长度、零点、限位角或全局运动学。

V35 不启用方向补偿或 preload，不切换到 `GCODE_SERIAL`，不运行
`2.0.gcode`。固件只有 `M801 ALIGN` 和 `M806 TEXT` 两个可达运动阶段。

## 固定参数

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

## 字形来源与局部换算

字形来源：

```text
backups/GCODE_HOME0_135_CENTER_ANCHOR_V7_20260718_222427/gcode/G_Code.txt.gcode
SHA-256: 901648BF916FBF353F1026387F520284D39FA77782B1BC081496B06B0FA208FD
```

存档 V7 源路径为 262 行、27 笔、140 次有效运动，最终抬笔。V35 不缩放 X，
只围绕文字区域 `Y=65 mm` 使用以下局部命令换算：

```text
command_y = 65 + (desired_y - 65) * 1.095
```

两遍字形的目标基线分别为 `Y=67 mm` 和 `Y=85 mm`。执行时先写下方一遍，
再写上方一遍。

```text
文字内容:                    张佳乐 × 2
每遍目标尺寸:                约 16.7 x 5.7 mm
目标物理范围:                X=197.6..214.3, Y=61.3..85.0 mm
固件命令范围:                X=197.6..214.3, Y=60.9..86.9 mm
目标基线间距:                18.0 mm
路径点:                      292
抬笔笔画起点:                54（每遍 27）
落笔路径点:                  238
路径 CRC32:                  87F7042F
```

预览：

```text
docs/diagnostics/AUTHOR_V7_TEXT_Y1095_X2_L205_L203_GATED_V35_PREVIEW.png
SHA-256: A837D734BEBD5A1038E159B231218EB483B88E7E662C657A27849E038AF738F2
```

预览中的浅灰线仅表示抬笔移动，不会写到纸上。红点是 `(150,20) mm` 的
ALIGN 对纸位置；V35 不再执行 V31 的轴线或方框阶段。

## 固件与门控文件

```text
HEX:
keil/AUTHOR_V7_TEXT_Y1095_X2_L205_L203_GATED_V35.hex
SHA-256: 8030AA4211343FD63BB6043CE887A33678EBECB57E730512FBB6DD6E149E109C

Build ID:
AUTHOR_V7_TEXT_Y1095_X2_L205_L203_GATED_V35

ALIGN gate:
gcode/AUTHOR_V7_TEXT_Y1095_ALIGN_RUN_V35.gcode
SHA-256: 09C8AC2B36403133AC169C8F96BD3AEBFCFD206F0895A932C93CE34E74918CFE

TEXT gate:
gcode/AUTHOR_V7_TEXT_Y1095_TEXT_RUN_V35.gcode
SHA-256: 0247F2FA25F534D0B5EA5E9ADD08AECA180D77413A8AAABC7C16C1F23CF3ED38
```

两个门控文件都只有 `G21/G90/G94/M5/M80x`，没有坐标、`G0/G1`、`M3`
或主机轨迹。

## A4 对齐

```text
A4 放置:       横向，297 mm 左右，210 mm 上下
纸面 +X:       向右
纸面 +Y:       向上
纸面原点:      左下角
ALIGN:         (150,20) mm
```

在纸上从左边缘向右量 `150 mm`、从下边缘向上量 `20 mm`，画一个小十字。
M801 完成且笔保持抬起后，移动并固定 A4，使小十字正好位于笔尖正下方。
这样两行字的目标位置位于纸面左边起约 `197.6 mm`、下边起约
`61.3..85.0 mm` 的小区域内。

## 严格实机顺序

1. 只烧录上述命名 V35 HEX。复位并等待完整回零结束。
2. 发送 `STATUS`，确认 Build ID 正确，并且为
   `state=WAIT_ALIGN action=M801 lim1=0 lim2=0 pen=UP`。
3. 加载 `AUTHOR_V7_TEXT_Y1095_ALIGN_RUN_V35.gcode`，只按一次 Run。
4. 等待 `completed=ALIGN state=WAIT_TEXT action=M806 pen=UP`。
5. 按上一节的方法对齐并固定横向 A4。
6. 加载 `AUTHOR_V7_TEXT_Y1095_TEXT_RUN_V35.gcode`，只按一次 Run。
7. 等待 `completed=TEXT state=DONE action=NONE pen=UP rehome=1`。

不要把两个门控文件连续发送。若出现 `wrong_gate`，先发送 `STATUS` 核对当前
`state/action`，不要重复发送或跳过阶段。运行过程中只允许 `STATUS` 或 `STOP`；
机械危险时直接切断电机电源。完成后再次运动前必须复位并重新回零。

## 离线验证

```text
Keil:                              0 Errors, 0 Warnings
protected V28..V34 artifacts:      PASS
V7 source and external 2.0 hash:   PASS
home-release combinations:         64 / 64
path points / executor targets:     292 / 254
epsilon-skipped motion targets:     38
TEXT Cartesian segments:            427
TEXT master pulses:                 3629
minimum TEXT joint margin:          29.720274 degrees
minimum TEXT paper margin:          60.900000 mm
maximum TEXT line deviation:        0.096036 mm
maximum TEXT endpoint error:        0.074285 mm
```

检查命令：

```powershell
python .\tools\check_author_v7_text_y1095_v35.py
```

Keil 构建前仍会显示交接文档已记录的 PA8 SysConfig package-model 提示；实际
编译、链接及 HEX 生成结果为 `0 Errors, 0 Warnings`。
