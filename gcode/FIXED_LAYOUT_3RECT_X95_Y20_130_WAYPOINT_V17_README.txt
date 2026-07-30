Y=20..130 mm 三矩形独立标定 V17

V16 不会移动的原因：
  归零点到 Y20 起点的单次规划超过 192 个 1 mm 路径段。

V17 修正：
  首次移动保持抬笔，分为两段：
    归零点 -> command (220,0)
    command (220,0) -> Y20 矩形起点
  两段均不超过规划缓冲区上限。

绘制目标不变：
  X=95..115 mm
  Y=20..40、65..85、110..130 mm

使用：
  1. 烧录 FIXED_LAYOUT_3RECT_X95_Y20_130_WAYPOINT_V17.hex。
  2. 复位并等待自动归零。
  3. STATUS 确认版本为：
       FIXED_LAYOUT_3RECT_X95_Y20_130_WAYPOINT_V17
  4. 发送一次：
       FIXED_LAYOUT_3RECT_X95_Y20_130_WAYPOINT_V17.gcode

任何异常立即发送 STOP。
