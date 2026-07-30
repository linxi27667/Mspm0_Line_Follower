# V32 最终参数 XY20 五点端点诊断

## 目的

V31 方框的实测边长按左、上、右、下顺序为：

```text
CW:  15, 21, 16, 21 mm
CCW: 16, 19, 17, 20 mm
```

对应方向平均值为 `+X=20.5 mm`、`-X=20.0 mm`、`+Y=16.0 mm`、
`-Y=16.0 mm`。V32 用抬笔移动后的独立点按，判断 Y 缩短来自端点映射，
还是只出现在连续落笔画线过程中。

V32 不修改机械参数，不启用方向补偿，不切换到 `GCODE_SERIAL`，也不读取
或运行 `2.0.gcode`。

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
point-to-point move feed:    240 mm/min
servo:                      0 degrees down, 90 degrees up
```

## 五个唯一位置

```text
O = (205,65) mm
W = (185,65) mm
E = (225,65) mm
S = (205,45) mm
N = (205,85) mm
```

实际顺序：

```text
O, W, O, E, O, S, O, N, O
```

共有 9 次点按：W/E/S/N 各一次，O 点五次。每个相邻目标的命令距离都是
20 mm，移动时笔必须处于抬起状态，不会命令绘制连接线。

测量示意图：

```text
docs/diagnostics/AUTHOR_FINAL_XY20_5POINT_DOTS_L205_L203_GATED_V32_PREVIEW.png
SHA-256: 2B53AFA6F4D7E5E3D4834356B042387D3184C1364C3D2DD0994CF429AF4FFE20
```

图中的蓝色线和文字只用于标注尺寸，机器只点黑色五个位置。

## 固件

```text
keil/AUTHOR_FINAL_XY20_5POINT_DOTS_L205_L203_GATED_V32.hex
SHA-256: 4560544A97F3AB4EF8495277B14C33FFF93929B5806256E6A883C4FD1C037C75

Build ID: AUTHOR_FINAL_XY20_5POINT_DOTS_L205_L203_GATED_V32
Build:    0 Errors, 0 Warnings
```

只烧录上述命名 HEX，不烧录 `keil/Objects` 下的通用 HEX。

## 两个门控文件

```text
gcode/AUTHOR_FINAL_XY20_ALIGN_RUN_V32.gcode
SHA-256: 09C8AC2B36403133AC169C8F96BD3AEBFCFD206F0895A932C93CE34E74918CFE

gcode/AUTHOR_FINAL_XY20_DOTS_RUN_V32.gcode
SHA-256: 4C4FF02D5B840AD1BF981029A169497834B7206AC9990928C5DEED9BAD7C623A
```

ALIGN 文件最后一行是 `M801`；DOTS 文件最后一行是 V32 独有的 `M805`。
两个文件都没有 X/Y、`G0/G1`、`M3` 或主机轨迹。

## 实机顺序

1. 烧录命名的 V32 HEX，复位并等待完整回零。
2. 发送 `STATUS`，确认 Build ID 正确，并且为
   `state=WAIT_ALIGN action=M801 lim1=0 lim2=0 pen=UP`。
3. 加载 ALIGN 文件，只按一次 Run。
4. 等待 `completed=ALIGN state=WAIT_DOTS action=M805 pen=UP`。
5. 使用原来的纸面 `(150,20) mm` 小十字对齐并固定横向 A4。
6. 加载 DOTS 文件，只按一次 Run。
7. 等待 `state=DONE targets=9 marks=9 pen=UP rehome=1`。

不要连续发送两个文件。运行中只允许 `STATUS` 或 `STOP`。如果出现连接线，
说明测试时笔尖实际接触纸面，不能把结果当作“无纸面阻力”的端点诊断。

## 离线结果

```text
unique points:                  5
marks:                          9
center stamps:                  5
inter-target commanded moves:   8 x 20 mm
W-E / S-N commanded spans:      40 / 40 mm
dot-path Cartesian segments:    215
dot-path master pulses:         2726
minimum joint margin:           30.047988 degrees
minimum paper margin:           45.000000 mm
maximum line deviation:         0.099976 mm
maximum endpoint error:         0.066357 mm
```

检查命令：

```powershell
python .\tools\check_author_final_xy20_v32.py
```

## 返回测量

所有结果使用毫米、点中心到点中心：

```text
W-E =
S-N =
O-W =
O-E =
O-S =
O-N =
O 点簇最大 X 散布 =
O 点簇最大 Y 散布 =
```

其中 `W-E` 和 `S-N` 是主判据。O 使用五个落点所形成点簇的几何中心。
同时提供一张正上方照片，毫米尺必须与 X/Y 方向平行。
