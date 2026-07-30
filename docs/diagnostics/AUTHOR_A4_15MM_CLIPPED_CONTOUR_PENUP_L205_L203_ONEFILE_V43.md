# V43 A4 15 mm 裁角安全轮廓一键抬笔测试

日期：2026-07-22

## 目的

V42 使用 25 个独立文件，是为了在每个新边界点人工确认。用户要求减少点击，因此 V43 把 ALIGN、纸面入口、
裁角轮廓和返回全部合并为一个固件内自动路径。

不能把 V42 的 25 条门控简单拼接：旧固件在前一段运动尚未结束时收到下一条命令会进入
`unexpected_uart_while_running` 并紧急停止。V43 改用一个新触发指令 `M890`，由固件内部按顺序执行全部目标。

## 唯一 G-code

```text
gcode/V43_ONE_FILE/01_M890_RUN_ALL_ALIGN_CONTOUR_RETURN_V43.gcode
```

文件严格只有五行：

```text
G21
G90
G94
M5
M890
```

普通 G-code 仍禁用，不接受 XYZ、F、M3、G0 或 G1。

## 自动过程

发送一次 `M890` 后，固件自动：

1. 从完整回零后的当前位置移动到原 ALIGN 十字。
2. 进入纸面并经过 V41 已验证区域和纸面中心。
3. 绕行“至少 15 mm 纸边距＋照片左侧两个角裁切”的六边形轮廓。
4. 返回纸面中心、已验证区域和 ALIGN 十字。
5. 进入 `DONE`，必须重新回零才能再次运行。

全程强制抬笔，移动速度从 V42 的 `600 mm/min` 降为 `300 mm/min`；每个关键点自动停留 `1500 ms`。
预计总运行时间约 5 分钟。`STATUS` 和 `STOP` 在运行期间保持可用。

## 纸面安全轮廓

```text
paper polygon, mm:
(15,15)
(281,15)
(281,162)
(257,193)
(82,193)
(17,145)
```

该轮廓约保留完整 15 mm 内框面积的 `94.028298%`，不会进入照片左上、左下的低余量角。

## 离线验证

```text
path points:                         25, including ALIGN at both ends
automatic stages:                    1
path CRC32:                          F1AAA103
home release cases:                  64
Cartesian 1 mm segments:             1347
master pulses:                       16916..16925
minimum contour joint margin:        15.660972 degrees
maximum DDA line deviation:          0.118727 mm
maximum endpoint error:              0.051548 mm
maximum internal target span:        79.525153 mm
contour pulse samples:               15604
minimum abs(sin(beta)):              0.507454631
maximum Jacobian condition:          3.668865
continuous polygon minimum margin:   15.660972 degrees
```

回零释放后的最初位置贴近已测限位，因此“回零到 ALIGN”最小模型限位余量为 `0.022463°`；这是 V30 以来
同一条已经使用的回零释放路径。到达 ALIGN 后，裁角轮廓最低余量为 `15.660972°`。

验证命令：

```text
python tools/check_author_a4_15mm_clipped_contour_onefile_v43.py
```

最终结果：`offline_author_a4_15mm_clipped_contour_onefile_v43=PASS motion=NONE`

## 固件

```text
Build ID:
AUTHOR_A4_15MM_CLIPPED_CONTOUR_PENUP_L205_L203_ONEFILE_V43

HEX:
keil/AUTHOR_A4_15MM_CLIPPED_CONTOUR_PENUP_L205_L203_ONEFILE_V43.hex

HEX SHA-256:
CEDB989DF655F96AA60CFE18E11E832006C121B20306CA1F3045CB7C7A97CC7F

Keil project:
keil/gpio_toggle_output_LP_MSPM0G3507_nortos_keil.uvprojx

Compiler/linker:
0 Error(s), 0 Warning(s)
```

方向补偿和 preload 保持关闭，笛卡尔分段保持 1 mm，引脚没有修改。Keil 的 SysConfig 前置命令仍输出项目原有
PA8 选项诊断，但后续编译、链接和 HEX 生成成功。

## 实机步骤

1. 保持纸张和底座位置不动，确保笔尖抬起，清除轮廓周围的显示器支架、线缆和其他障碍物。
2. 烧录 V43 HEX，复位并等待完整回零。
3. 串口应显示 `state=WAIT_ALIGN action=M890`。
4. 只发送唯一的 V43 G-code 文件一次，然后留在机器旁观察约 5 分钟。
5. 正常结束应显示：
   `completed=PROBE probe=1/1 state=DONE action=NONE pen=UP rehome=1`。

出现辅助杆接近重合、小臂反向、卡顿、异响、限位、线缆拉扯或碰撞趋势，立即发送 `STOP` 或断电；停止后必须
重新回零。不得运行 V39 的 `M817..M824`、`2.0.gcode` 或 `GCODE_SERIAL`。

## 2026-07-22 实机结果和下一阶段决定

用户确认 V43 已绕裁角轮廓完整运行一圈，过程中没有进入辅助杆死点，也没有出现两连杆奇点、小臂反向、卡顿或
异常运动。该结果证明当前轮廓具有实机抬笔可到达性，但不等于整张纸的坐标比例、正交性和重复精度已经校准。

用户要求下一阶段按纸面区域逐片校准，使用已知尺寸的十字或正方形测量局部 X/Y 比例、正交性和闭合误差。照片
右下角在后续写字范围中需要比原 15 mm 边距进一步缩进；正式数值必须通过校准图实测后确定，不能只根据照片猜测。
