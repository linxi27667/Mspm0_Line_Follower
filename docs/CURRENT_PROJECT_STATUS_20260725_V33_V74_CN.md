# 写字机当前状态（V33 / V74）

- 当前固件：
  `keil/PAPER_A4_STANDARD_GCODE_AMASS_PLANNER_V33.hex`
- Build ID：
  `PAPER_A4_STANDARD_GCODE_AMASS_PLANNER_V33`
- HEX SHA-256：
  `B88F0E3C856A0C28E00F3E751FBE2A835E8A4A396BB7B2AAEC9B25775C2A402D`
- 构建结果：0 Error，0 Warning
- 当前字体 B：
  `assets/kenjoy_gfont/AA_GUO_JINGMING_b7c9ccc1.gfont`
- 字体 SHA-256：
  `D5D8E41EF24BF380FDAB57B4746795D691CC4E2DF878A394E4FA8C6D594C09F8`
- 诊断 G-code：
  `gcode/PAPER_A4_BFONT_DIGIT8_DIRECTION_JUNCTION_GCODE_V74.gcode`
- G-code SHA-256：
  `C4134BD22ECAD6F12362F861B297F77E416450EF516945A3586F7DA28A9F999E`

V33 相对 V32 只加入作者式 AMASS 低速多轴平滑。坐标、纸面映射、
逆解、绝对脉冲端点、回零和限位均未改变。方向补偿、preload 和
S 形预弯继续关闭。

离线分析确认 B 字体原始“8”在 12 mm 高度下：

- 21 个点，1 条连续笔画
- 最长原始折线段 4.233316 mm
- 起点与终点在腰部相距 2.071212 mm
- 固件绝对脉冲取整最大理论纸面误差 0.060767 mm

因此数字“8”的折线感和腰部结构有明确的字库来源；运动动态是否还会
叠加误差，需要用 V74 正反叠画实测。第三行 `T/+ /X` 是不依赖字体的
独立笔画接点基准。

完整说明：

`docs/diagnostics/PAPER_A4_STANDARD_GCODE_AMASS_PLANNER_V33_20260725.md`

注意：`Jlink.jflash` 仍指向旧 V31，烧录时必须手工选择 V33 HEX。
