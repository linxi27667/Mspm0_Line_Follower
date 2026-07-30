# V34 文字区域局部 Y1095 五点端点诊断

## 目的

V32 在文字区域中心 `O=(205,65) mm` 的实测为：

```text
W-E = 40 mm（命令 40 mm）
S-N = 36.5 mm（命令 40 mm）
O-W / O-E = 20 / 20 mm
O-S / O-N = 18 / 18 mm
O 点簇 = 1 x 1 mm
```

V33 又证明方框区域 X 正确而 Y 只有 `16/20=0.80`，因此误差随工作区位置
变化，不能修改全局电机比例或使用一个全局 Y 系数。V34 只验证文字区域附近
的局部、对称 Y 坐标放大，不修改运动学参数。

V34 不启用方向补偿或 preload，不切换到 `GCODE_SERIAL`，也不读取或运行
`2.0.gcode`。

## 局部换算基准

按 V32 的主测量长基准计算：

```text
文字区域 Y 实测比例 = 36.5 / 40 = 0.9125
所需局部命令倍率     = 40 / 36.5 = 1.0958904109
```

当前诊断坐标采用 `0.1 mm` 网格，因此倍率落为 `1.095`：目标实体半径
`20 mm` 对应命令半径 `21.9 mm`，命令总跨度 `43.8 mm`。若 V32 的局部
比例可重复，预测实体跨度为 `43.8 x 0.9125 = 39.9675 mm`。这是待实机验证
的假设，不是已经成立的校准结论。

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
O = (205,65.0) mm
W = (185,65.0) mm
E = (225,65.0) mm
S = (205,43.1) mm
N = (205,86.9) mm
```

实际顺序：

```text
O, W, O, E, O, S, O, N, O
```

第一点是中心 O。共有 9 次静止点按；X 命令跨度为 `40 mm`，Y 命令跨度为
`43.8 mm`。所有移动都必须抬笔，机器不会命令绘制连接线。

## 固件与门控

```text
HEX:
keil/AUTHOR_TEXT_Y1095_5POINT_DOTS_L205_L203_GATED_V34.hex
SHA-256: 51711CDD1D1F70C22270F12EC156968C4AF2B94D7457FEF9EAFB1501AA23224D

Build ID:
AUTHOR_TEXT_Y1095_5POINT_DOTS_L205_L203_GATED_V34

ALIGN gate:
gcode/AUTHOR_TEXT_Y1095_ALIGN_RUN_V34.gcode
SHA-256: 09C8AC2B36403133AC169C8F96BD3AEBFCFD206F0895A932C93CE34E74918CFE

DOTS gate:
gcode/AUTHOR_TEXT_Y1095_DOTS_RUN_V34.gcode
SHA-256: 4C4FF02D5B840AD1BF981029A169497834B7206AC9990928C5DEED9BAD7C623A
```

两个门控文件都只有 `G21/G90/G94/M5/M80x`，没有坐标、`G0/G1`、`M3`
或主机轨迹。

## 实机顺序

1. 只烧录上述命名 V34 HEX，复位并等待完整回零。
2. 发送 `STATUS`，确认 Build ID 正确，状态为
   `WAIT_ALIGN action=M801 lim1=0 lim2=0 pen=UP`。
3. 加载 `AUTHOR_TEXT_Y1095_ALIGN_RUN_V34.gcode`，只按一次 Run。
4. 等待 `completed=ALIGN state=WAIT_DOTS action=M805 pen=UP`。
5. A4 横放，用纸面 `(150,20) mm` 小十字对准抬起的笔尖，并固定四角。
   建议使用没有旧点迹的纸。
6. 加载 `AUTHOR_TEXT_Y1095_DOTS_RUN_V34.gcode`，只按一次 Run。
7. 等待 `state=DONE targets=9 marks=9 pen=UP rehome=1`。

不要连续发送两个门控文件。运行中只允许 `STATUS` 或 `STOP`。若出现连接线，
本次数据无效。机械危险时直接切断电机电源。

## 返回测量

全部使用毫米、点中心到点中心：

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

O 使用五个中心落点形成的点簇几何中心。主判据是直接测量的 `W-E` 和
`S-N`。若 `S-N` 稳定落在约 `39..41 mm` 且 O 点簇仍紧密，才允许把同一
局部 Y 换算带入文字区域的下一次小规模试写；V34 本身不授权全局校准。

## 实机结果（2026-07-20）

用户报告四个 O 到端点的距离均为 `20 mm`，因此 `W-E` 与 `S-N` 均约为
`40 mm`；中心重复落点的最大差约为 `1 mm`。V34 验证了文字区域的局部
`Y=1.095` 命令换算，同时保持 X 尺寸正确。该结论只覆盖本次验证的文字区域
和坐标范围，不能推广为整张 A4 的全局比例。

## 离线验证

```text
Keil:                         0 Errors, 0 Warnings
targets / marks:               9 / 9
unique points / center stamps: 5 / 5
commanded W-E / S-N:           40.0 / 43.8 mm
dot Cartesian segments:        223
dot master pulses:              2806
minimum dot joint margin:       30.047988 degrees
minimum dot paper margin:       43.100000 mm
maximum line deviation:         0.099976 mm
maximum endpoint error:         0.066357 mm
```

检查命令：

```powershell
python .\tools\check_author_text_y1095_v34.py
```
