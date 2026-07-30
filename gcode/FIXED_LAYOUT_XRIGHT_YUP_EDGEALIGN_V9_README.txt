固定摆放纸边对齐坐标轴验证 V9

最终纸面坐标：
  +X = 平行纸张下边，朝纸张右边
  +Y = 垂直纸张下边，朝纸张上边

V8 现场结果：
  X/Y 方向、长度和垂直度正确；
  X、Y 整体共同逆时针偏转；
  20 mm X 箭头尖端相对 O 向上偏约 2.5..3.0 mm；
  Y 轴也呈相同的整体旋转。

V9 取偏移区间中值：
  rise = 2.75 mm
  angle = asin(2.75/20) = 7.9032 deg

校正：
  把完整的 V8 纸面坐标系统一顺时针旋转 7.9032 deg；
  不单独拉扯 X 或 Y；
  保留两轴 20 mm 长度与纸面垂直关系。

测试 O：
  command O = (180,20) mm

目标 command 尖端：
  paper +X right 20 mm -> command (191.742,43.514)
  paper +Y up    20 mm -> command (163.332,32.272)

离线现场模型反算：
  paper +X = (20.0000,0.0002) mm
  paper +Y = (-0.0001,20.0003) mm

安全检查：
  command X 范围 163.332..191.742 mm
  command Y 范围 20.000..43.514 mm
  最小关节裕量 33.868 deg

严格顺序：
1. 烧录并复位，等待自动归零完成。
2. STATUS 必须显示：
   id=FIXED_LAYOUT_XRIGHT_YUP_EDGEALIGN_V9
   state=WAIT_ALIGN action=M801 lim1=0 lim2=0 pen=UP
3. 发送 FIXED_LAYOUT_XRIGHT_YUP_EDGEALIGN_01_MOVE_V9.gcode。
4. 收到 state=WAIT_DRAW action=M802 后确认笔尖在纸内。
5. 发送 FIXED_LAYOUT_XRIGHT_YUP_EDGEALIGN_02_DRAW_V9.gcode。
6. 检查 X 平行纸张下边向右、Y 朝上、两轴均 20 mm 且垂直。

任何方向错误、落点不在纸内、机械异常或限位触发，立即发送 STOP。
