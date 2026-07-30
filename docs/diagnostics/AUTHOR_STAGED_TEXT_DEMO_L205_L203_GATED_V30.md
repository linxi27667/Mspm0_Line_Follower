# V30 横向 A4 分阶段多字试写

## 定位

这是一次“先看书写效果”的非正式试写，不是完整 A4、直线精度或正式汉字固件验收。

- 当前没有进行新的机械调整；按 V28 结果，Stage2 换向仍按约 `2 mm` 回差看待；
- 方向补偿、独立 preload 和 author line execution 均保持关闭；
- 不使用 `GCODE_SERIAL`，不读取或运行 `2.0.gcode`；
- 固件上电回零后不自动移动，四个阶段必须依次由 V30 独有的 `M801..M804` 单独门控；
- 文字使用 Windows 楷体轮廓，共四行，不是单线书法字形。

四行内容：

```text
写字机器人
今天来测试
横平竖直稳
张佳乐作品
```

## 当前参数

```text
L1 / L2:                    205 / 203 mm
machine offset:             (-129,+128) mm
Stage1 / Stage2:            40.099216 / 40.115790 steps/degree
theta / psi limit:          -0.773082 / 134.177381 degrees
direction compensation:     disabled
independent preload:        disabled
Cartesian segment:          1 mm
servo:                      0 degrees down, 90 degrees up
```

## 坐标和摆纸

按用户提供的当前俯视照片：

```text
照片右侧 = +X
照片上方 = +Y
A4 横放：长边左右，短边上下
纸面 (0,0) = A4 左下角
```

纸面 `(0,0)` 自身受 Stage1 限位约束，不能命令笔尖直接到零点。V30 使用可达的对纸基准：

```text
ALIGN = (150,20) mm
```

上电前先在横向 A4 上画一个小十字：从纸张左边缘向右量 `150 mm`，从纸张下边缘向上量 `20 mm`。V30 完成 `M801` 后，笔尖会抬笔停在 ALIGN；移动纸张，使这个十字位于笔尖正下方，然后把纸张四角贴平。

如果这种摆放会让纸张、手、线缆或机械臂进入齿轮/连杆危险区，停止操作，不要通过旋转坐标或修改 offset 解决。

预览：

`docs/diagnostics/AUTHOR_STAGED_TEXT_DEMO_L205_L203_GATED_V30_PREVIEW.png`

灰框是本次离线检查的保守子区域 `X=145..275, Y=15..125 mm`。左下两只小框分别按 CW 和 CCW 绘制；文字范围是 `X=154.0..257.9, Y=47.0..122.9 mm`。

## 固件和四个门控文件

固件：

```text
keil/AUTHOR_STAGED_TEXT_DEMO_L205_L203_GATED_V30.hex
SHA-256: E37687122A384C8B090C5B78442B982DFE1C301D53055408B5F8E89B0E30F188
```

门控文件：

```text
gcode/AUTHOR_TEXT_DEMO_ALIGN_RUN_V30.gcode
SHA-256: 09C8AC2B36403133AC169C8F96BD3AEBFCFD206F0895A932C93CE34E74918CFE

gcode/AUTHOR_TEXT_DEMO_AXES_RUN_V30.gcode
SHA-256: 8ABA4D0DEC45EB8C19AF22B2D8329EA4AB92EBED43419F4BCF3DFFE91759D345

gcode/AUTHOR_TEXT_DEMO_BOX_RUN_V30.gcode
SHA-256: 849C36293F327D32CA96C2841E5E30AB67A0D672A10B25FDD158FCA752A6A144

gcode/AUTHOR_TEXT_DEMO_TEXT_RUN_V30.gcode
SHA-256: 3720684529170F025773D87984BFF49381DEB05F8D8DD3091C9BEDDD361C39FE
```

每个文件都只有：

```gcode
G21
G90
G94
M5
M80x
```

它们不包含 X/Y、`G0/G1`、`M3` 或任何主机轨迹。

## 严格运行顺序

1. 烧录命名的 V30 HEX，不要烧录 `keil/Objects` 下会变化的通用 HEX。
2. 复位，等待完整回零和限位释放。
3. 确认 Build ID 为 `AUTHOR_STAGED_TEXT_DEMO_L205_L203_GATED_V30`，状态为 `WAIT_ALIGN`，`lim1=0 lim2=0 pen=UP`。
4. 在 Mechanical Arm Master 使用 `115200 8N1` 加载 ALIGN 文件，只按一次 Run。
5. 等待 `ok STAGE_DONE ... completed=ALIGN state=WAIT_AXES action=M802`。
6. 按上面的 `(150,20)` 十字对齐横向 A4，并贴牢四角。
7. 加载 AXES 文件，只按一次 Run。它依次打 `A、+X、A1、+Y、A2` 五个静止点。
8. 等待 `WAIT_BOX`。确认 `+X` 点在 A 的照片右侧约 20 mm，`+Y` 点在 A 的照片上方约 20 mm；观察 A/A1/A2 点簇的回差。方向错误或点簇异常时不要继续。
9. 加载 BOX 文件，只按一次 Run。它画左侧 20x20 mm CW 小框和右侧 20x20 mm CCW 小框。
10. 等待 `WAIT_TEXT`。确认两个框都在纸上、没有危险方向、闭合和尺寸能够接受；否则不要继续。
11. 加载 TEXT 文件，只按一次 Run。预计约 12–15 分钟，不要在运行中发送其他命令。
12. 等待 `completed=TEXT state=DONE ... pen=UP rehome=1`。下一次运动前复位并重新回零。

任何运行阶段只允许 `STATUS` 或 `STOP`。运行中收到其他串口命令，固件会抬笔、急停并要求重新回零。机械危险时直接切断电机电源，不要依赖上位机 Stop。

## 离线结果

```text
generated text points:        4381
pen-up contour starts:        76
draw points:                  4305
path CRC32:                   5D2FEEE0
maximum draw point span:      0.728011 mm

AXES minimum joint margin:    28.050108 degrees
BOX minimum joint margin:     28.050108 degrees
TEXT minimum joint margin:    13.517178 degrees
TEXT minimum paper margin:    39.100000 mm
maximum pulse-line deviation: 0.105099 mm
maximum endpoint error:       0.076534 mm

Keil project:                 gpio_toggle_output_LP_MSPM0G3507_nortos_keil.uvprojx
build:                        0 Errors, 0 Warnings
program size:                 Code=43016, RO-data=36092, RW-data=128, ZI-data=29784
```

检查命令：

```powershell
python .\tools\check_author_text_demo_v30.py
```

备份：

```text
backups/AUTHOR_STAGED_TEXT_DEMO_L205_L203_GATED_V30_20260720.zip
SHA-256: 6EFB61596CCB073A25B6D1E48CF9E53468FC71216E3F2BDDBF71D93947F51052
```
