# V30 作废说明

`PAPER_A4_ZHANG_JIA_LE_CHEN_HAND_32MM_TANGENT_GCODE_V30.gcode` 已作废并
改名归档为
`INVALID_DO_NOT_RUN_PAPER_A4_ZHANG_JIA_LE_CHEN_HAND_V30.gcode.txt`，
禁止继续上机。

原因：

1. V30 使用了错误的 `.gfont` Y 轴变换：
   `paper_y = baseline_y + source_y * scale`。
2. `.gfont` 的 Y 值向下增大，纸面 Y 值向上增大，因此 V30 的字形整体
   上下颠倒。
3. V30 选择的“陈手写”中“佳”只有 7 条路径，字形观感也不符合要求。

替代文件：

`gcode/PAPER_A4_ZHANG_JIA_LE_AA_GUO_32MM_TANGENT_GCODE_V31.gcode`

V31 使用 `aa郭敬明字体` 中 7/8/5 条原始字库路径，并改为：

`paper_y = baseline_y - source_y * scale`
