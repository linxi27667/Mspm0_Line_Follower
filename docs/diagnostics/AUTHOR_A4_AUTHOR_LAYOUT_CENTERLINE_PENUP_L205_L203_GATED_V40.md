# V40 作者摆纸 A4 中心线分阶段抬笔验证

日期：2026-07-22

## 结论和适用范围

V40 只验证新纸位的入口、已验证文字中心和新 A4 纸面中心。它不是完整 A4
边界固件，也没有恢复普通 G-code。

V39 的 `M817` 从 `(150,20)` 向 `(136,20)` 运动时，实机越过了“主臂与
副臂拉杆重合”的机械肘节死点，小臂随后反向。该死点不在原作者和当前固件的
两连杆 SCARA 模型中。V39 的 `M817..M824` 全部撤销，不得继续使用。

已知实机边界只适用于 `Y=20 mm` 的这条路径：

```text
V38 (140,20): 实机安全
V39 (136,20): 路径中越过辅助连杆死点并发生小臂反向
```

因此 V40 使用任务级经验门控 `command X >= 150 mm`，相对已知安全点再留
`10 mm`。这只能保护本次中心线路径，不能证明所有 Y 下的完整机械死点边界。

## 作者摆纸和新坐标

作者照片和原资料包三维装配均显示：底座完全放在纸外，由机械臂从纸外伸入。
用户已经按该方式重新摆放横向 A4，并确认：

```text
paper +X = 照片上
paper +Y = 照片左
纸面原点 = 照片中的纸张右下角
ALIGN command = (150,20) mm
ALIGN paper = (14,58) mm
command = paper + (136,-38) mm
```

实机俯视照片：

`docs/diagnostics/A4_AUTHOR_LAYOUT_ALIGN_14_58_ACTUAL_20260722.jpg`

照片 SHA-256：

`025A5ECD563426D0DCFF789EC6CE6F9E3AC60FD8EE12C2394CC6FCF1706B4572`

V39 越过辅助连杆死点后的近照：

`docs/diagnostics/AUX_TOGGLE_CROSSED_V39_ACTUAL_20260722.jpg`

照片 SHA-256：

`137D01D261D1AE348361491DB930F1582435798D6C9170D723A28988B0B9157D`

用户已手动恢复正确机械分支、重新回零并完成 ALIGN。显示器支架也已移出纸面
上方范围。

## V40 严格门控

| 顺序 | 门控 | 命令坐标 mm | 纸面坐标 mm | 作用 |
|---|---|---:|---:|---|
| 1 | M801 | (150,20) | (14,58) | ALIGN |
| 2 | M825 | (151,20) | (15,58) | 纸内入口，向 +X 仅 1 mm |
| 3 | M826 | (205,65) | (69,103) | V34/V35/V36 已使用的文字中心区域 |
| 4 | M827 | (284.5,67) | (148.5,105) | 新 A4 纸面中心 |
| 5 | M828 | (205,65) | (69,103) | 分阶段返回已验证中心 |
| 6 | M829 | (150,20) | (14,58) | 分阶段返回 ALIGN |

每个门控只包含一个抬笔目标，完成后必须停住并等待下一个门控。执行器运行时
收到其他串口命令会进入错误状态并要求重新回零。

V40 不包含 `M817..M824`，不包含落笔调用，不接受普通 G-code，不启用方向补偿
或 preload，也不启用作者单块直线执行。

## 离线验证

```text
path points:                         5
path CRC32:                          928E55B1
Cartesian 1 mm segments:             270
master pulses checked:               3716
minimum actual-path joint margin:    30.047988 degrees
maximum DDA line deviation:          0.091064 mm
maximum endpoint error:              0.051548 mm
maximum gated target span:           79.525153 mm
actual path command X minimum:       150.0 mm
V38 known-safe comparison X:         140.0 mm
V39 known-unsafe target X:           136.0 mm
```

按新纸位扫描完整 15 mm 内框时，数学模型得到：

```text
paper inset:                         (15,15)..(282,195) mm
command inset:                       (151,-23)..(418,157) mm
grid samples:                        48508
minimum modeled joint margin:        5.041713 degrees
minimum abs(sin(beta)):              0.202146959
maximum Jacobian condition:          9.792145
```

这些整页数字仅是信息性模型结果，尚未包含辅助连杆肘节死点，也没有获得实机
边界授权。V40 不提供上述完整内框的运动入口。

验证命令：

```text
python tools/check_author_a4_author_layout_centerline_v40.py
```

最终结果：

`offline_author_a4_author_layout_centerline_v40=PASS motion=NONE`

## 固件

```text
Build ID:
AUTHOR_A4_AUTHOR_LAYOUT_CENTERLINE_PENUP_L205_L203_GATED_V40

Keil project:
keil/gpio_toggle_output_LP_MSPM0G3507_nortos_keil.uvprojx

HEX:
keil/AUTHOR_A4_AUTHOR_LAYOUT_CENTERLINE_PENUP_L205_L203_GATED_V40.hex

HEX SHA-256:
4DBF1A835D668112ABBF62F698ED1EF04CCE126E3632CD249E5B62D00E2B42A3

Compiler/linker:
0 Error(s), 0 Warning(s)
```

Keil 的 SysConfig 前置命令仍会报告项目原有的 `PA8` 选项诊断；本次使用已经
实机验证的生成配置继续编译，最终编译、链接和 HEX 生成均成功。引脚映射未在
V40 中修改。

## G-code 门控文件

```text
gcode/AUTHOR_A4_AUTHOR_LAYOUT_ALIGN_RUN_V40.gcode
gcode/AUTHOR_A4_AUTHOR_LAYOUT_ENTRY_RUN_V40.gcode
gcode/AUTHOR_A4_AUTHOR_LAYOUT_VERIFIED_CENTER_RUN_V40.gcode
gcode/AUTHOR_A4_AUTHOR_LAYOUT_PAPER_CENTER_RUN_V40.gcode
gcode/AUTHOR_A4_AUTHOR_LAYOUT_RETURN_VERIFIED_RUN_V40.gcode
gcode/AUTHOR_A4_AUTHOR_LAYOUT_RETURN_ALIGN_RUN_V40.gcode
```

每份文件严格只有 `G21/G90/G94/M5` 和自己的单一门控命令，不含 XYZ、F、M3、
G0 或 G1。

## 首次实机步骤

1. 保持新纸位不动，取下笔或确保笔尖明显高于纸面。
2. 烧录命名 V40 HEX，复位并等待完整回零。
3. 只运行 V40 ALIGN 文件，确认状态为 `WAIT_PROBE action=M825`，并确认笔尖仍
   对准纸面 `(14,58)` 十字。
4. 只运行 V40 ENTRY 文件 `M825`。它只从 `(150,20)` 移到 `(151,20)`。
5. 完全停止后观察主臂与副臂拉杆的间隙，并报告串口 `STAGE_DONE`。首次测试到此
   为止，不要直接运行 M826。

任何方向异常、辅助杆间隙变小、小臂反向、异响、限位或实体碰撞，立即发送
`STOP`；停止后必须重新回零。不得运行 V39 网格文件、`2.0.gcode` 或
`GCODE_SERIAL`。

## 2026-07-22 实机结果

用户按顺序完成 `M801`、`M825`、`M826`、`M827`、`M828`、`M829`，最终串口状态为
`probe=5/5 state=DONE action=NONE pen=UP rehome=1`。用户确认所有方向、运动和返回均正常，未出现辅助杆重合、
小臂反向、卡顿、异响或碰撞。

因此已经实机验证以下往返中心路径：

```text
ALIGN command (150,20)
paper entry (151,20)
verified center (205,65)
paper center (284.5,67)
return to verified center
return to ALIGN
```

纸面中心实机照片：
`docs/diagnostics/A4_AUTHOR_LAYOUT_PAPER_CENTER_V40_ACTUAL_20260722.jpg`

返回已验证中心实机照片：
`docs/diagnostics/A4_AUTHOR_LAYOUT_RETURN_VERIFIED_V40_ACTUAL_20260722.jpg`

V40 仍只证明中心路径，不代表 A4 四角和完整纸面已经验证。
