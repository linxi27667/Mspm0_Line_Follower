Y=20..130 mm 三矩形分区校正复测 V18

目标矩形：
  下方：X=95..115 mm，Y=20..40 mm
  中间：X=95..115 mm，Y=65..85 mm
  上方：X=95..115 mm，Y=110..130 mm

V18 校正数据来自 V17 的十二个手工实测角点。
每个区域独立拟合局部仿射变形，再叠加原有纸面到机械命令变换。

使用：
  1. 烧录 FIXED_LAYOUT_3RECT_X95_Y20_130_LOCALCAL_V18.hex。
  2. 复位并等待自动归零。
  3. STATUS 确认版本：
       FIXED_LAYOUT_3RECT_X95_Y20_130_LOCALCAL_V18
  4. 发送一次：
       FIXED_LAYOUT_3RECT_X95_Y20_130_LOCALCAL_V18.gcode

正常过程会先输出 WAYPOINT_DONE，再依次绘制 Y20、Y65、Y110。
发生任何异常立即发送 STOP。
