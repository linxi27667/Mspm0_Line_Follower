# V42 A4 15 mm 最小纸边距裁角安全轮廓抬笔探测

日期：2026-07-22

## 结论和目的

V41 已实机完成全部 `01..24` 中线探测。用户确定纸张四周至少保留 `15 mm`，并接受裁掉照片左上、左下
两个低余量角。V42 用严格编号门控和全程抬笔方式验证这个裁角轮廓，不开放普通 G-code，也不落笔。

完整 15 mm 内框是 `paper=(15,15)..(282,195)`，但其照片左下角模型余量仅约 `5.04°`，照片左上角
约 `5.40°` 且接近两连杆伸直奇点。因此 V42 使用以下六边形：

```text
paper coordinates, mm:
(15,15)
(281,15)
(281,162)
(257,193)
(82,193)
(17,145)
```

该六边形保留原定 15 mm 内框面积的约 `94.028298%`，所有纸边距均不小于 15 mm；照片左侧两个危险角被
斜边裁掉。后续文字转换器必须检查每个路径点和每段轨迹均位于此六边形内，不能只检查外接矩形。

## 坐标合同

```text
A4 横放：297 x 210 mm
纸面原点：照片右下角
paper +X：照片上
paper +Y：照片左
ALIGN command：(150,20) mm
ALIGN paper：(14,58) mm
command = paper + (136,-38) mm
纸张最小边距：15 mm
```

## 编号文件和大概位置

必须严格按 `01` 到 `25` 运行，不能跳号。中文顺序说明：`gcode/00_V42_RUN_ORDER.txt`。

| 编号 | 指令 | 运行后大概位置 |
|---:|---|---|
| 01 | M801 | 纸张右下区域原 ALIGN 十字 |
| 02 | M860 | 从 ALIGN 向照片上移动 1 mm，进入纸面 |
| 03 | M861 | 下半部分、左右接近中间的已验证文字区域 |
| 04 | M862 | 纸张正中心 |
| 05 | M863 | 从中心向照片右，到右半部分中间点 |
| 06 | M864 | 照片右边缘中央，距纸边约 15 mm |
| 07 | M865 | 沿照片右边缘向照片上移动 |
| 08 | M866 | 照片右上安全角，距两边约 15 mm |
| 09 | M867 | 沿照片上边缘向左，第一段 |
| 10 | M868 | 沿照片上边缘继续向左，第二段 |
| 11 | M869 | 照片左上裁角开始点 |
| 12 | M870 | 照片左上裁角斜边的另一端 |
| 13 | M871 | 照片左侧安全边界上段 |
| 14 | M872 | 照片左侧安全边界中段 |
| 15 | M873 | 照片左下裁角开始点 |
| 16 | M874 | 照片左下裁角斜边中间点 |
| 17 | M875 | 照片左下裁角结束点 |
| 18 | M876 | 沿照片下方安全边界向右的中间点 |
| 19 | M877 | 照片右下安全角，距纸边约 15 mm |
| 20 | M878 | 沿照片右边缘向上返回 |
| 21 | M879 | 返回照片右边缘中央 |
| 22 | M880 | 返回纸面右半部分中间点 |
| 23 | M881 | 返回纸张正中心 |
| 24 | M882 | 返回已验证文字区域 |
| 25 | M883 | 返回 ALIGN 十字 |

每个 G-code 文件严格只有 `G21/G90/G94/M5` 和自己的一条门控指令，不含 XYZ、F、M3、G0 或 G1。

## 离线验证

```text
path points:                         24
path stages:                         24
path CRC32:                          315ECAD8
Cartesian 1 mm segments:             1265
master pulses checked:               15603
minimum modeled joint margin:        15.660972 degrees
maximum DDA line deviation:          0.106842 mm
maximum endpoint error:              0.051548 mm
maximum gated target span:           79.525153 mm
pulse samples:                       15604
minimum abs(sin(beta)):              0.507454631
maximum Jacobian condition:          3.668865
polygon area fraction:               0.940282980
continuous polygon minimum margin:   15.660972 degrees
```

验证命令：

```text
python tools/check_author_a4_15mm_clipped_contour_v42.py
```

最终结果：`offline_author_a4_15mm_clipped_contour_v42=PASS motion=NONE`

上述模型仍不包含辅助四连杆死点；`command X >= 150 mm` 是根据 V38/V39 实机结果设置的经验保护，V42 仍需
逐点观察辅助杆，不得把离线结果当成实机四连杆证明。

## 固件

```text
Build ID:
AUTHOR_A4_15MM_CLIPPED_CONTOUR_PENUP_L205_L203_GATED_V42

HEX:
keil/AUTHOR_A4_15MM_CLIPPED_CONTOUR_PENUP_L205_L203_GATED_V42.hex

HEX SHA-256:
19681E4484B1EE23742D9C9E2A4B2D2FB156C9FDF27CC742D4A194B22712D686

Keil project:
keil/gpio_toggle_output_LP_MSPM0G3507_nortos_keil.uvprojx

Compiler/linker:
0 Error(s), 0 Warning(s)
```

Keil 的 SysConfig 前置命令仍会输出项目原有 PA8 选项诊断；本次没有修改引脚，后续编译、链接和 HEX 生成成功。

## 首次实机步骤

1. 保持 V41 的纸张和底座位置不动，确保笔尖抬起。
2. 烧录命名 V42 HEX，复位并等待完整回零。
3. 运行 `01_M801_ALIGN_V42.gcode`，确认笔尖仍对准原 ALIGN 十字，串口显示 `action=M860`。
4. 第一次只运行 `02_M860_ENTRY_V42.gcode`，完成后应显示
   `probe=1/24 state=WAIT_PROBE action=M861 pen=UP`。
5. 确认方向、辅助杆和周围物体正常后，再按编号继续。

出现辅助杆接近重合、小臂反向、卡顿、异响、限位或碰撞趋势，立即发送 `STOP`；STOP 后必须重新回零并从
`01` 开始。不得运行 V39 的 `M817..M824`、`2.0.gcode` 或 `GCODE_SERIAL`。
