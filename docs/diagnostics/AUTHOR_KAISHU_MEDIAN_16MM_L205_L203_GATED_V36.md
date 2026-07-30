# V36 大字单线楷体“张佳乐”试写

## 目的

V35 实机照片表明，两遍约 `16.7 x 5.7 mm` 的“张佳乐”都以相近方式失真，
没有明显的累积漂移。照片中的额外长斜线由用户误碰产生，抬笔和收笔机构确认正常。

```text
docs/diagnostics/AUTHOR_V7_TEXT_Y1095_X2_V35_ACTUAL_20260721.jpg
SHA-256: BEF99373F0BA10BD3070F972EBC2138E407D003D101B3D467404A2B079E4C37A
```

V35 每个字只有约 `5..6 mm` 高，而中心重复落点最大差约 `1 mm`，同时 292 个
路径目标中有 38 个落在 `0.15 mm` 位置容差内而不启动电机。V36 只改变字形来源
和字的尺寸，用一行大字区分“小字路径问题”和机械跟踪问题。

V36 不修改当前运动学或电机参数，不启用方向补偿或 preload，不切换到
`GCODE_SERIAL`，不运行 `2.0.gcode`。

## 固定机械与执行参数

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

这些参数与 V35 相同，因此本次结果只比较放大后的笔顺中心线字形。

## 楷体笔顺数据

V36 使用 Hanzi Writer Data 中按标准笔顺排列的 `medians` 中心线，不描字体外轮廓，
也不填充空心字。

```text
source repository: https://github.com/chanind/hanzi-writer-data
pinned commit:     68d10a4b21150cae5e1ebbd223eed289cf32d90c

张 U+5F20: 7 strokes, 53 median points
佳 U+4F73: 8 strokes, 44 median points
乐 U+4E50: 5 strokes, 33 median points
```

项目内固定数据：

```text
assets/hanzi_writer_data_68d10a4/u5f20.json
SHA-256: 2B7ABF0BE39617AC5B3F68917DAC2E6520C926AA2F7B0F2AF6C2B50C19CB682D

assets/hanzi_writer_data_68d10a4/u4f73.json
SHA-256: C830BB19E18D515D4992E2D8B464BE7AEFD14D318C36A7A292ED34A0D5D59C20

assets/hanzi_writer_data_68d10a4/u4e50.json
SHA-256: E5B3D2904512D9B0AC920FABE82E7C5CF1BE5BC8B1931F0FEE5D59398284CD75
```

数据许可证为项目内保留的 `ARPHICPL.TXT`，SHA-256：
`5590533436C70F10F2F524EE61456238C290175C6662FBE1C700B5F038A6D328`。

## 尺寸和位置

三个字从左向右各写一次，共 20 笔。最大字符高度设为 `16 mm`，使用同一个比例，
所以三个字保留原始相对大小：

```text
张: 约 15.70 x 14.47 mm
佳: 约 17.07 x 16.00 mm
乐: 约 13.38 x 14.23 mm
```

整行以纸面 `(205,65) mm` 为中心：

```text
目标物理范围: X=179.151..229.690, Y=57.000..73.000 mm
固件命令范围: X=179.2..229.7,   Y=56.2..73.8 mm
```

Y 命令继续使用 V34 已验证的文字区域局部换算：

```text
command_y = 65 + (desired_y - 65) * 1.095
```

路径共有 `130` 个点：20 个抬笔笔画起点和 110 个落笔点，CRC32 为
`D1D77A40`。所有 130 个目标都会实际进入运动规划，`epsilon_skips=0`。

预览：

```text
docs/diagnostics/AUTHOR_KAISHU_MEDIAN_16MM_L205_L203_GATED_V36_PREVIEW.png
SHA-256: A056368CE94503E56215C151C55F719919916793FFF03A62D05E53EB6B35F240

docs/diagnostics/AUTHOR_KAISHU_MEDIAN_16MM_L205_L203_GATED_V36_DETAIL.png
SHA-256: B01BAFF796639B2E098A3C4DF43A2DB8188AC4DA094A7E3F2975A973F96E1305
```

预览中的黑线会落笔，浅灰细线只是抬笔换笔画，不会写到纸上。细节图网格每小格
为 `1 mm`，较深网格每 `5 mm` 一格。

## 固件和门控

```text
HEX:
keil/AUTHOR_KAISHU_MEDIAN_16MM_L205_L203_GATED_V36.hex
SHA-256: 37506BE659CE6652D8016F8894EBDFA5EFA310FE544D5D3D655B5AAE32BC3054

Build ID:
AUTHOR_KAISHU_MEDIAN_16MM_L205_L203_GATED_V36

ALIGN gate:
gcode/AUTHOR_KAISHU_MEDIAN_16MM_ALIGN_RUN_V36.gcode
SHA-256: 09C8AC2B36403133AC169C8F96BD3AEBFCFD206F0895A932C93CE34E74918CFE

TEXT gate:
gcode/AUTHOR_KAISHU_MEDIAN_16MM_TEXT_RUN_V36.gcode
SHA-256: AB153DD6D3965B4589C8010DD9EFEEE2DE3831BFBC971C52B1DBCC234473FF7B
```

V36 的 TEXT 门控是 `M807`。不要使用 V35 的 `M806` 文件。两个 V36 门控文件
都只有 `G21/G90/G94/M5/M80x`，没有坐标、`G0/G1`、`M3` 或主机轨迹。

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

## 严格实机顺序

1. 只烧录上述命名 V36 HEX，复位并等待完整回零结束。
2. 发送 `STATUS`，确认 Build ID 正确，并且为
   `state=WAIT_ALIGN action=M801 lim1=0 lim2=0 pen=UP`。
3. 加载 `AUTHOR_KAISHU_MEDIAN_16MM_ALIGN_RUN_V36.gcode`，只按一次 Run。
4. 等待 `completed=ALIGN state=WAIT_TEXT action=M807 pen=UP`。
5. 按上一节的方法对齐并固定横向 A4。
6. 加载 `AUTHOR_KAISHU_MEDIAN_16MM_TEXT_RUN_V36.gcode`，只按一次 Run。
7. 等待 `completed=TEXT state=DONE action=NONE pen=UP rehome=1`。

不要把两个门控文件连续发送。若出现 `wrong_gate`，先发送 `STATUS` 核对当前
`state/action`，不要重复发送或跳过阶段。运行过程中只允许 `STATUS` 或 `STOP`；
机械危险时直接切断电机电源。完成后再次运动前必须复位并重新回零。

## 离线验证

```text
Keil:                              0 Errors, 0 Warnings
protected V28..V35 artifacts:      PASS
V7 source / Kaishu data / 2.0:     hash PASS
home-release combinations:         64 / 64
path points / executor targets:     130 / 130
epsilon-skipped motion targets:     0
TEXT Cartesian segments:            417
TEXT master pulses:                 4386
minimum TEXT joint margin:          29.346356 degrees
minimum TEXT paper margin:          56.200000 mm
maximum TEXT line deviation:        0.102244 mm
maximum TEXT endpoint error:        0.068131 mm
```

检查命令：

```powershell
python .\tools\check_author_kaishu_median_v36.py
```

Keil 构建前仍会显示交接文档已记录的 PA8 SysConfig package-model 提示；实际
编译、链接及 HEX 生成结果为 `0 Errors, 0 Warnings`。
