# 写字机项目交接说明（2026-07-20，V28 实测后）

## 给下一位处理者

请先完整阅读本文、V28 诊断文档和 V28 实机日志，再决定下一步。用户明确要求：凡是数据标签、测量基准、方向或机械状态存在歧义，必须立即询问，不能自行猜测后修改参数或生成固件。

项目 Git 工作区有大量用户已有修改和未跟踪文件。禁止 `reset`、`clean`、`checkout`、回滚或覆盖无关文件。

## 最终目标

让 MSPM0G3507 写字机可靠回零，接收机械臂大师逐行 G-code，并安全书写汉字“张佳乐”。

约束：

- 不移动现有限位开关；
- 舵机 `0°=落笔`、`90°=抬笔`；
- 所有正式轨迹必须先离线逆解、整数脉冲化、全路径限位/纸面检查；
- 当前阶段禁止直接切回正式 G-code；
- 不能用抬笔视频宣布直线或 A4 已验证。

## 固定硬件

```text
Stage1 STEP/DIR: PA10 / PA11
Stage2 STEP/DIR: PA8 / PA9
Servo:           PA12
Limits:          PA26 / PA27
UART1 TX/RX:     PB4 / PB5, 115200 8N1
AD / CE:         50 / 50 mm（不进入当前作者 FK 的两杆长度）
```

## 当前确认的几何与电气参数

源码：`APP/Inc/app_writer_motion.h`

```text
L1:                         205 mm
L2:                         203 mm
有效纸面方向:               +X 向右，+Y 向上
有效 machine offset:        (-129,+128) mm
Stage1:                     40.099216 steps/degree
Stage2:                     40.115790 steps/degree
theta limit:                -0.773082 degree
psi limit:                  134.177381 degrees
双臂人工基准姿态:           theta=0°, psi=135°
author line execution:      disabled
Cartesian segment:          1 mm
direction compensation:     disabled
independent preload:        disabled
A4 envelope probe limits:   enabled，仅供当前受限诊断使用
```

作者源码原始 offset 是 `(-135,+105)`；当前 `(-129,+128)` 已合并实机纸面原点，禁止擅自改回。

## 已确认的标定依据

### Stage1

Stage1 长弦测试多次得到约 `263 mm`，最终确认 `40.099216 steps/degree`。Stage1 在 V27/V28 原始单轴测试段中均强制为零脉冲。

### Stage2 比例

```text
V25: 2200 pulses -> 183 mm（与后续结果不一致，视为离群/旧候选）
V26: 1600 pulses -> 138.5 mm -> 40.108458 steps/degree
V27 正向多点: AB=34.5, AC=71, AD=105, AE=138 mm
V27 正反联合拟合: 40.115791 steps/degree, RMS=0.5195 mm
```

源码采用 `40.115790 steps/degree`，并按原始 33 脉冲限位差同步得到 `psi_limit=134.177381°`。不要只改单一比例而不更新依赖限位角。

## 当前核心问题：Stage2 换向回差

V27 路径：

```text
A -> B -> C -> D -> E -> D1 -> C1 -> B1 -> A1
0   400  800 1200 1600  1200   800   400    0 pulses
```

用户确认所有累计距离均以第一次 A 点为基准：

```text
AB / AB1 = 34.5 / 37 mm
AC / AC1 = 71 / 73 mm
AD / AD1 = 105 / 107 mm
AE       = 138 mm
AA1 = BB1 = CC1 = DD1 = 2 mm
全部返回点位于靠近 E 的一侧
```

`2 mm` 在 L2=203 mm 圆弧上相当于约 `0.5645°`，即约 `22.65` 个当前 Stage2 脉冲。

V28 在第一次返回段增加 23 脉冲：

```text
逻辑位置: 0,400,800,1200,1600,1200,800,400,0
电机位置: 0,400,800,1200,1600,1177,777,377,-23
八段脉冲: 400,400,400,400,423,400,400,400
```

V28 实测：

```text
BB1=0, CC1=0, DD1=0
AA1=2 mm，A1 越过 A，位于远离 E 的外侧
```

V28 日志证明固件执行正确：首个返回段为 423 脉冲，总脉冲 3223，Stage1 增量 0，9 个点完成，无限位错误。

关键解释：到达初始 A 前，日志显示 Stage2 最后一段方向已经是返回方向（`md2=-1`、电气 `d2=1`）。随后 A->B 首次切换到正向，但 V28 没有在这里补脉冲。因此：

- `BB1/CC1/DD1=0` 证明返回换向约需要 23 脉冲；
- `AA1=2 mm` 越过 A 不是“23 脉冲过补偿”，而是暴露了第一次正向换向同样约损失 23 脉冲；
- 当前证据支持两个方向均约有 23 脉冲的对称机械回差。

这仍然只是单轴、抬笔移动、静止点落笔的隔离结果。不能因此直接启用正式方向补偿。

## 为什么暂时不启用软件补偿

历史 `WORKSPACE_STAGE2_PRELOAD_28_4P5MM_V3` 曾在连续落笔方框中使用 28 脉冲独立 preload，实测造成 CW 明显缩小、CCW 明显放大。其旧比例为 48.8 steps/degree，28 脉冲约 `0.574°`，与当前 23 脉冲约 `0.573°` 的物理角度几乎相同。

因此固定补脉冲目前只能说明可校正可重复的单轴换向失位，尚未证明适合双轴联动、连续笔压和汉字轨迹。

优先机械排查：

1. Stage2 电机轴与主动轮紧定螺钉；
2. 从动轮与关节轴是否相对转动；
3. Stage2 皮带张力、齿形啮合和轮的歪斜；
4. 第二关节轴承、衬套或螺栓的角向间隙；
5. 第二臂、笔架和笔尖横向松动。

建议抬笔断电，固定 Stage2 主动轮/电机轴后轻推笔尖，并在轴与轮之间画贯穿标记线定位松动来源。不要通过修改 `steps/degree` 掩盖回差。

## 当前源码和固件状态

```text
TASK/writer_test.h:
WRITER_TEST_MODE = WRITER_TEST_MODE_STAGE2_CHORD_CAL (24u)

Build ID:
AUTHOR_STAGE2_RETURN_TAKEUP_23_L203_GATED_V28
```

当前 V28 不是通用 G-code 固件。它只接受 `G21/G90/G94/M5/M501` 门控、`STATUS` 和 `STOP`，拒绝普通轨迹 G-code，且只允许单次运行。

最后已知板上日志状态：

```text
V28 DONE
raw_total=3223
marks=9
stage1_delta=0
final_motor_offset=-23
pen=UP
rehome=1
```

无论板子现在是否仍通电，任何下一次运动前都应复位并重新回零。

## 当前 V28 产物

```text
HEX:
C:\Users\zjl\Desktop\zjl\TI\writer_robot\keil\AUTHOR_STAGE2_RETURN_TAKEUP_23_L203_GATED_V28.hex
SHA-256: F944FC50448C75607D0577F397E3CBA0567BF6C53D800EE31887E11FAB6B3F06

门控 G-code:
C:\Users\zjl\Desktop\zjl\TI\writer_robot\gcode\AUTHOR_STAGE2_RETURN_TAKEUP_23_RUN_V28.gcode
SHA-256: 16518E55E269CF3B8631D1223D5BEF19DB5B499BF55D4804EB8B0F61B84ED875

备份:
C:\Users\zjl\Desktop\zjl\TI\writer_robot\backups\AUTHOR_STAGE2_RETURN_TAKEUP_23_L203_GATED_V28_20260720.zip
SHA-256: 2BC78026469BE78E28CA312F704A8EF350C00AACDE474352CCD88DB186CB191C
```

正确 Keil 工程构建结果：`0 Errors, 0 Warnings`。构建前仍会出现已知的 PA8 SysConfig package-model 提示，但实际编译、链接和 HEX 生成成功。

## G-code 在哪里

### 当前 V28 门控文件（不是轨迹）

`C:\Users\zjl\Desktop\zjl\TI\writer_robot\gcode\AUTHOR_STAGE2_RETURN_TAKEUP_23_RUN_V28.gcode`

内容只有：

```gcode
G21
G90
G94
M5
M501
```

### 历史矩形 G-code

```text
CW:  C:\Users\zjl\Desktop\zjl\TI\writer_robot\gcode\AUTHOR_SAFE_170X120_CW_SINGLE_V19.gcode
CCW: C:\Users\zjl\Desktop\zjl\TI\writer_robot\gcode\AUTHOR_SAFE_170X120_CCW_SINGLE_V20.gcode
```

这些属于旧几何/旧标定阶段，不能直接当作当前正式验证结论。

### 最终待检查的写字 G-code

```text
C:\Users\zjl\Desktop\zjl\TI\writer_robot_source\2.0.gcode
大小: 27512 bytes
当前行数: 1039
SHA-256: 2F084117B4C1A17A15719B5FBDF36E1960EF3A5BA3DF8F6A7620D98FB69C315C
```

它包含 `G0/G1/G4/G21/G90/M3/M5`，当前 V28 不能运行它。早期“262 行、协议错误=0、超限点=0”的检查对应旧文件/旧坐标合同，不能套用到这个 1039 行文件。正式写字前必须以当前文件哈希和最终机械参数重新离线解析、逆解、整数脉冲化及限位检查。

## 工程与资料路径

```text
项目根目录:
C:\Users\zjl\Desktop\zjl\TI\writer_robot

唯一正确 Keil 工程:
C:\Users\zjl\Desktop\zjl\TI\writer_robot\keil\gpio_toggle_output_LP_MSPM0G3507_nortos_keil.uvprojx

禁止使用的旧工程:
C:\Users\zjl\Desktop\zjl\TI\writer_robot\keil\TI_moban_LP_MSPM0G3507_nortos_keil.uvprojx

当前参数:
C:\Users\zjl\Desktop\zjl\TI\writer_robot\APP\Inc\app_writer_motion.h

当前测试选择:
C:\Users\zjl\Desktop\zjl\TI\writer_robot\TASK\writer_test.h

V28 执行器:
C:\Users\zjl\Desktop\zjl\TI\writer_robot\TASK\stage2_chord_cal_test.c
C:\Users\zjl\Desktop\zjl\TI\writer_robot\TASK\stage2_chord_cal_test.h

诊断文档目录:
C:\Users\zjl\Desktop\zjl\TI\writer_robot\docs\diagnostics

V28 说明:
C:\Users\zjl\Desktop\zjl\TI\writer_robot\docs\diagnostics\AUTHOR_STAGE2_RETURN_TAKEUP_23_L203_GATED_V28.md

V28 完整实机日志:
C:\Users\zjl\Desktop\zjl\TI\writer_robot\docs\diagnostics\AUTHOR_STAGE2_RETURN_TAKEUP_23_V28_ACTUAL_LOG_20260720.txt
SHA-256: BA0129BE96C05E71998C84BE568424861003178493EBE9F99050F91FB75DC27B

V28 离线检查器:
C:\Users\zjl\Desktop\zjl\TI\writer_robot\tools\check_stage2_return_takeup_v28.py

Stage2 旧 28 脉冲 preload 结论:
C:\Users\zjl\Desktop\zjl\TI\writer_robot\docs\workspace_stage2_preload_28_2026-07-18.md

参考资料包:
C:\Users\zjl\Downloads\25.11.11drawbot完整资料包

作者参考工程:
C:\Users\zjl\Downloads\DrawBot-ramps-main\DrawBot-ramps-main

作者 scara 源码:
C:\Users\zjl\Downloads\DrawBot-ramps-main\DrawBot-ramps-main\grbl-scara-ramps\scara.c
C:\Users\zjl\Downloads\DrawBot-ramps-main\DrawBot-ramps-main\grbl-scara-ramps\scara.h

作者 GitHub:
https://github.com/akv47/DrawBot-ramps

MakerWorld:
https://makerworld.com/zh/models/712239-a-writing-robot-arm-the-drawbot?from=search#profileId-1268105

V17 视频:
C:\Users\zjl\Documents\xwechat_files\wxid_ggj9bqut1ii122_6820\msg\video\2026-07\52290cf237ce089cf5d48adbcf8f342c.mp4

V17 视频分析:
C:\Users\zjl\Desktop\zjl\TI\writer_robot\docs\diagnostics\v17_loop_video_20260719
```

## A4 状态

完整 A4 尚未通过当前几何和实机落笔验证。旧 V11 平移 A4 包络使用了被实机否定的旧纸面合同，禁止重新烧录。此前关于作者原点 A4 可达性和安全子区域的数字是在旧 `L1=L2=200`、旧比例/限位下计算的，当前 `L1=205/L2=203` 后必须重新离线搜索，不能直接沿用。

只有在机械回差处理、双向点线和矩形实线验证完成后，才搜索“保持作者轴方向、平移纸张原点”的完整 `297x210 mm` 区域；仍需先抬笔分点/单圈门控测试，再允许落笔。

## 建议下一步顺序

1. 先检查并尽量消除 Stage2 机械松动；目标是把无补偿笔尖回差降到 `0.5 mm` 左右或以下。
2. 机械处理后重新做“无补偿、最终比例”的 Stage2 双向点测试；不要用 V28 判断修复后的原始回差，因为 V28 内含一次 23 脉冲补偿。
3. 如果机械上无法进一步降低且回差多次稳定，再做双向 23 脉冲隔离验证。可选 V29 设计（尚未生成）：

```text
逻辑位置: 0,400,800,1200,1600,1200,800,400,0
电机位置: 0,423,823,1223,1623,1200,800,400,0
总脉冲: 3246
预期: AA1=BB1=CC1=DD1=0，最终 motor offset=0
```

4. 即使 V29 成功，也先做无连续笔压的 Cartesian 点/短线验证，再做单次门控落笔线和小矩形；不得直接把 23 脉冲加入正式汉字。
5. 重新做当前几何下的 CW/CCW 矩形实线和闭合验证。
6. 再重新搜索 A4 平移原点和安全包络。
7. 最后切回 `GCODE_SERIAL`，恢复适合 G-code 的直线执行策略，并针对当前 1039 行 `2.0.gcode` 完整离线复核后，才书写“张佳乐”。

## 禁止事项

- 不要修改 `steps/degree` 来掩盖换向回差；
- 不要直接启用 `APP_WRITER_DIRECTION_COMP_ENABLE`；
- 不要再次使用 `WORKSPACE_STAGE2_PRELOAD_28_4P5MM_V3.hex`；
- 不要直接运行 V11 或当前 `2.0.gcode`；
- 不要关闭硬限位保护或跳过离线轨迹检查；
- 不要仅凭抬笔视频判断直线、尺寸或 A4 成功；
- 不要改回作者原始 offset；
- 不要在未复位重新回零的情况下继续运动；
- 不要破坏当前脏 Git 工作区中的用户文件。
