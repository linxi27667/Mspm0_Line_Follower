固定摆放原点与作者坐标轴标定 V3

纸面最终原点 P0：
  当前固定俯视照片中的纸张右下角。

作者坐标方向：
  +X = 照片向上
  +Y = 照片向左

实际绘制的测量基准 O：
  command O = (170,20) mm
  O 不在纸边上，以避免贴边和 command X < 150 mm 的已知危险区域。

绘制内容：
  O 到 +X 箭头：30 mm
  O 到 +Y 箭头：30 mm

严格顺序：
1. 烧录并复位，等待自动归零完成。
2. STATUS 必须显示：
   id=FIXED_LAYOUT_ORIGIN_AXES_DRAW_V3
   state=WAIT_ALIGN action=M801 lim1=0 lim2=0 pen=UP
3. 只发送 FIXED_LAYOUT_ORIGIN_AXES_01_ALIGN_V3.gcode。
4. 收到 completed=ALIGN_X150_Y20、state=WAIT_DRAW、action=M802 后，
   检查笔尖位于纸内且周围至少有约 40 mm 空间。
5. 只发送 FIXED_LAYOUT_ORIGIN_AXES_02_DRAW_V3.gcode。
6. 完成后测量：
   A = O 到照片下方纸边的垂直距离（mm）
   B = O 到照片右方纸边的垂直距离（mm）
7. 回报 A、B。换算为：
   command_x = paper_x + (170 - A)
   command_y = paper_y + (20 - B)

旧作者摆放的估计值仅用于首次纸内安全检查：
  A 约 34 mm
  B 约 58 mm

任何方向错误、落点不在纸内、机械异常或限位触发，立即发送 STOP。
