# 写字机项目交接增量（2026-07-20，V30 已构建、尚未实机运行）

## 阅读顺序

先读 `PROJECT_HANDOFF_20260720_AFTER_V28.md` 和其中引用的 V28 实机日志，再读本文及 `AUTHOR_STAGED_TEXT_DEMO_L205_L203_GATED_V30.md`。

原 V28 结论没有被推翻。用户确认 V28 后没有做新的机械调整，但希望先看较多文字的实际效果，并接受横向 A4。V30 因此只定义为非正式、分阶段试写，不是完整 A4 或正式汉字验收。

## 当前源码状态

```text
TASK/writer_test.h:
WRITER_TEST_MODE = WRITER_TEST_MODE_AUTHOR_TEXT_DEMO (25u)

Build ID:
AUTHOR_STAGED_TEXT_DEMO_L205_L203_GATED_V30

L1 / L2:                    205 / 203 mm
machine offset:             (-129,+128) mm
Stage1 / Stage2:            40.099216 / 40.115790 steps/degree
theta / psi limit:          -0.773082 / 134.177381 degrees
direction compensation:     disabled
independent preload:        disabled
author line execution:      disabled
Cartesian segment:          1 mm
A4 envelope probe limits:   enabled
```

概念中的双向 23 脉冲 V29 没有生成。V30 使用新版本号，避免把试写固件误认为 V29 补偿验证。

## V30 行为

V30 上电回零后不自动移动，不接受普通轨迹 G-code。必须依次使用四个 V30 独有门控：

```text
M801: 抬笔定位到 ALIGN=(150,20)
M802: A、+X、A1、+Y、A2 五个静止点
M803: 20x20 mm CW 小框和 20x20 mm CCW 小框
M804: 四行楷体轮廓文字
```

使用 `M801..M804` 是为了让仍装载 V28 的板子拒绝命令，避免 `M501` 与 V28 门控冲突。任何阶段运行中只允许 `STATUS` 或 `STOP`；其他串口命令会抬笔、急停并要求重新回零。

四行内容：

```text
写字机器人
今天来测试
横平竖直稳
张佳乐作品
```

## 坐标与摆纸

按用户 2026-07-20 提供的当前俯视照片，照片右侧为 `+X`，照片上方为 `+Y`。A4 横放，在纸上从左边向右量 150 mm、从下边向上量 20 mm 画十字。M801 完成后，将该十字对准抬起的笔尖，再贴牢纸张四角。

不要命令笔尖去纸面 `(0,0)`；该理论左下角受 Stage1 限位约束，不直接可达。

## 当前产物

```text
HEX:
keil/AUTHOR_STAGED_TEXT_DEMO_L205_L203_GATED_V30.hex
SHA-256: E37687122A384C8B090C5B78442B982DFE1C301D53055408B5F8E89B0E30F188

ALIGN gate:
gcode/AUTHOR_TEXT_DEMO_ALIGN_RUN_V30.gcode
SHA-256: 09C8AC2B36403133AC169C8F96BD3AEBFCFD206F0895A932C93CE34E74918CFE

AXES gate:
gcode/AUTHOR_TEXT_DEMO_AXES_RUN_V30.gcode
SHA-256: 8ABA4D0DEC45EB8C19AF22B2D8329EA4AB92EBED43419F4BCF3DFFE91759D345

BOX gate:
gcode/AUTHOR_TEXT_DEMO_BOX_RUN_V30.gcode
SHA-256: 849C36293F327D32CA96C2841E5E30AB67A0D672A10B25FDD158FCA752A6A144

TEXT gate:
gcode/AUTHOR_TEXT_DEMO_TEXT_RUN_V30.gcode
SHA-256: 3720684529170F025773D87984BFF49381DEB05F8D8DD3091C9BEDDD361C39FE

Backup:
backups/AUTHOR_STAGED_TEXT_DEMO_L205_L203_GATED_V30_20260720.zip
SHA-256: 6EFB61596CCB073A25B6D1E48CF9E53468FC71216E3F2BDDBF71D93947F51052
```

正确 Keil 工程构建为 `0 Errors, 0 Warnings`。完整离线验证命令：

```powershell
python .\tools\check_author_text_demo_v30.py
```

## 离线验证摘要

```text
text path points:             4381
path CRC32:                   5D2FEEE0
maximum draw point span:      0.728011 mm
AXES / BOX joint margin:      28.050108 degrees minimum
TEXT joint margin:            13.517178 degrees minimum
TEXT paper margin:            39.100000 mm minimum
maximum pulse-line deviation: 0.105099 mm
maximum endpoint error:       0.076534 mm
```

## 未完成的实机状态

V30 尚未烧录、尚未运行，不能宣称轴方向、小框或文字实机成功。板上最后已知状态仍可能是 V28 `DONE`；第一次 V30 运动前必须烧录命名 HEX、复位并完整重新回零。

实机后需要返回：

```text
A/+X 距离和方向
A/+Y 距离和方向
A/A1/A2 最大点簇直径
CW/CCW 两个小框的四边、对角线和闭合误差
一张垂直俯拍全纸照片
一张文字与小框近照
完整 UART/RTT 日志
```

## 仍然禁止

- 不要直接启用方向补偿或 preload；
- 不要切回 `GCODE_SERIAL`；
- 不要运行 `2.0.gcode`；
- 不要跳过 M801、M802、M803 直接发送 M804；
- 不要把本次轮廓字试写当作完整 A4、单线书法或正式精度验收；
- 不要在未复位重新回零的情况下开始下一次运动；
- 不要 reset/clean/checkout 或破坏脏工作区中的用户文件。
