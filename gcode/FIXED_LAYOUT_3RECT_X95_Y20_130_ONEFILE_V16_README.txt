Y=20..130 mm 三矩形独立标定 V16

只画中间一列，不画九宫格：
  X 固定为 95..115 mm
  下矩形 Y=20..40 mm
  中矩形 Y=65..85 mm
  上矩形 Y=110..130 mm

使用：
  1. 烧录 FIXED_LAYOUT_3RECT_X95_Y20_130_ONEFILE_V16.hex。
  2. 复位并等待自动归零。
  3. STATUS 确认版本：
       FIXED_LAYOUT_3RECT_X95_Y20_130_ONEFILE_V16
  4. 发送一次：
       FIXED_LAYOUT_3RECT_X95_Y20_130_ONEFILE_V16.gcode
  5. 自动画完三个矩形。

完成后从同一个 Y=0 纸边测量六条横边：
  下排下边、下排上边；
  中排下边、中排上边；
  上排下边、上排上边。

任何异常立即发送 STOP。
