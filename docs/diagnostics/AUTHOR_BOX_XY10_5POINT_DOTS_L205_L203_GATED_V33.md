# V33 方框区域 XY10 五点端点诊断

## 目的

V31 的 `20 x 20 mm` 落笔方框位于 `X=150..170, Y=20..40 mm`，实测
X 边约 `19..21 mm`、Y 边约 `15..17 mm`。V32 在文字区域用抬笔移动和
静止点按得到 `W-E=40 mm`、`S-N=36.5 mm`、O 点簇约 `1 x 1 mm`。

两次测试同时改变了位置和笔压条件，因此不能直接判断 V31 更严重的 Y
缩短来自工作区位置，还是连续落笔和笔尖阻力。V33 只在 V31 方框原区域做
抬笔五点端点测试，保持全部机械参数不变。

V33 不启用方向补偿或 preload，不切换到 `GCODE_SERIAL`，也不读取或运行
`2.0.gcode`。

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
O = (160,30) mm
W = (150,30) mm
E = (170,30) mm
S = (160,20) mm
N = (160,40) mm
```

实际顺序：

```text
O, W, O, E, O, S, O, N, O
```

第一点是中心 O，不是 W。共有 9 次静止点按，8 个相邻目标的命令距离均为
`10 mm`；命令跨度 `W-E=20 mm`、`S-N=20 mm`。所有移动都必须抬笔，机器
不会命令绘制连接线。

## 固件与门控

```text
HEX:
keil/AUTHOR_BOX_XY10_5POINT_DOTS_L205_L203_GATED_V33.hex
SHA-256: 3F677BEEC71CBC335884114CDD0E6722BB6B2CCD8B648AD7FBB127F81A44E2B7

Build ID:
AUTHOR_BOX_XY10_5POINT_DOTS_L205_L203_GATED_V33

ALIGN gate:
gcode/AUTHOR_BOX_XY10_ALIGN_RUN_V33.gcode
SHA-256: 09C8AC2B36403133AC169C8F96BD3AEBFCFD206F0895A932C93CE34E74918CFE

DOTS gate:
gcode/AUTHOR_BOX_XY10_DOTS_RUN_V33.gcode
SHA-256: 4C4FF02D5B840AD1BF981029A169497834B7206AC9990928C5DEED9BAD7C623A
```

两个门控文件都只有 `G21/G90/G94/M5/M80x`，没有坐标、`G0/G1`、`M3`
或主机轨迹。

## 实机顺序

1. 只烧录上述命名 V33 HEX，复位并等待完整回零。
2. 发送 `STATUS`，确认 Build ID 正确，状态为
   `WAIT_ALIGN action=M801 lim1=0 lim2=0 pen=UP`。
3. 加载 `AUTHOR_BOX_XY10_ALIGN_RUN_V33.gcode`，只按一次 Run。
4. 等待 `completed=ALIGN state=WAIT_DOTS action=M805 pen=UP`。
5. A4 横放，用原口径的纸面 `(150,20) mm` 小十字对准抬起的笔尖，并固定
   四角。建议使用没有旧点迹的纸。
6. 加载 `AUTHOR_BOX_XY10_DOTS_RUN_V33.gcode`，只按一次 Run。
7. 等待 `state=DONE targets=9 marks=9 pen=UP rehome=1`。

不要连续发送两个门控文件。运行中只允许 `STATUS` 或 `STOP`。若出现连接线，
说明移动时笔尖接触了纸面，本次结果不能作为抬笔端点数据。机械危险时直接
切断电机电源。

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

O 使用五个中心落点形成的点簇几何中心。忽略纸上旧线；同时提供一张正上方
照片，毫米尺尽量与测量方向平行。

判读口径：若抬笔 V33 的 `S-N` 也约为 `16 mm`，优先判断为位置相关端点映射；
若接近 `18..20 mm`，V31 额外缩短主要来自连续落笔、笔压或笔尖阻力。该测试
本身不授权修改比例、启用方向补偿或直接写正式 G-code。

## 实机结果（2026-07-20）

用户确认终态为 `DONE targets=9 marks=9`，移动过程中没有新连接线。点中心
测量为：

```text
W-E = 20 mm
O-W = 10 mm
O-E = 10 mm
O-S = 8 mm
O-N = 8 mm
S-N = 16 mm
O 点簇最大 X 散布 = 1 mm
O 点簇最大 Y 散布 = 1 mm
```

因此该区域 X 比例为 `1.00`，Y 比例约为 `0.80`，且正负 Y 对称、中心返回
可重复。V33 抬笔移动仍复现了 V31 方框的 Y 缩短，排除了连续落笔阻力作为
主要原因。它也不支持使用方向补偿，因为误差不是单向的；与 V32 文字区域
约 `36.5/40=0.9125` 的 Y 比例相比，误差随工作区位置变化，不能使用单一
全局 Y 比例。

## 离线验证

```text
Keil:                         0 Errors, 0 Warnings
targets / marks:               9 / 9
unique points / center stamps: 5 / 5
dot Cartesian segments:        90
dot master pulses:              1153
minimum dot joint margin:       30.047988 degrees
minimum dot paper margin:       20.000000 mm
maximum line deviation:         0.096405 mm
maximum endpoint error:         0.040077 mm
```

检查命令：

```powershell
python .\tools\check_author_box_xy10_v33.py
```
