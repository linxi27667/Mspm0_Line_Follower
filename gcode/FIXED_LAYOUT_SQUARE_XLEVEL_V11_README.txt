固定摆放 X 水平修正 20 x 20 mm 正方形 V11

V10 现场结果：
  四边长度正确；
  Y 方向正确；
  20 mm X 边的终点向上偏约 2 mm。

V11 修正：
  X 实际水平分量 sqrt(20^2-2^2) = 19.8997 mm；
  X 上偏角 asin(2/20) = 5.7392 deg；
  只消除 X 的 2 mm 向上分量，并把水平分量补足到 20 mm；
  Y command 向量保持不变。

新方框位置：
  位于 V10 方框上方 10 mm，避免两次线条重叠。

绘制顺序：
  右 20 mm -> 上 20 mm -> 左 20 mm -> 下 20 mm -> 闭合

command 顶点：
  S  = (175.213, 72.006)
  X  = (188.690, 94.405)
  XY = (172.022,106.677)
  Y  = (158.546, 84.278)
  S  = (175.213, 72.006)

离线纸面反算：
  side 1 = ( 20.0003,-0.0004) mm
  side 2 = ( -0.0001,20.0003) mm
  side 3 = (-19.9998,-0.0004) mm
  side 4 = ( -0.0003,-19.9995) mm
  command 闭合误差 = 0.0000 mm

安全检查：
  command X 范围 158.546..188.690 mm
  command Y 范围 72.006..106.677 mm
  最小关节裕量 19.815 deg

严格顺序：
1. 烧录并复位，等待自动归零完成。
2. STATUS 必须显示：
   id=FIXED_LAYOUT_SQUARE_XLEVEL_20MM_V11
   state=WAIT_ALIGN action=M801 lim1=0 lim2=0 pen=UP
3. 发送 FIXED_LAYOUT_SQUARE_XLEVEL_01_MOVE_V11.gcode。
4. 收到 state=WAIT_DRAW action=M802 后确认笔尖位于空白纸面。
5. 发送 FIXED_LAYOUT_SQUARE_XLEVEL_02_DRAW_V11.gcode。
6. 测量宽、高、两条对角线和闭合间隙，并检查 X 边是否平行纸张下边。

任何方向错误、落点不在纸内、机械异常或限位触发，立即发送 STOP。
