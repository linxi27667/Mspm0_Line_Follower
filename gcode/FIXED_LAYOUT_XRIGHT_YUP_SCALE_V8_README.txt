固定摆放 X/Y 最终方向与比例验证 V8

最终纸面坐标：
  +X = 朝纸张右边
  +Y = 朝纸张上边

V7 现场结果：
  方向正确；
  两轴垂直；
  paper +Y = 20 mm；
  paper +X = 15 mm。

V8 比例修正：
  X command 向量乘以 20/15 = 4/3；
  Y command 主轴向量完全不变；
  箭头侧翼按校正后的纸面坐标重新计算。

测试 O：
  command O = (180,20) mm

目标 command 尖端：
  paper +X right 20 mm -> command (189.339,44.978)
  paper +Y up    20 mm -> command (161.876,28.922)

离线现场模型反算：
  paper +X = (20.0001,-0.0001) mm
  paper +Y = (-0.0002,20.0000) mm

安全检查：
  command X 范围 161.876..189.339 mm
  command Y 范围 20.000..44.978 mm
  最小关节裕量 34.175 deg

严格顺序：
1. 烧录并复位，等待自动归零完成。
2. STATUS 必须显示：
   id=FIXED_LAYOUT_XRIGHT_YUP_SCALE20_V8
   state=WAIT_ALIGN action=M801 lim1=0 lim2=0 pen=UP
3. 发送 FIXED_LAYOUT_XRIGHT_YUP_SCALE_01_MOVE_V8.gcode。
4. 收到 state=WAIT_DRAW action=M802 后确认笔尖在纸内。
5. 发送 FIXED_LAYOUT_XRIGHT_YUP_SCALE_02_DRAW_V8.gcode。
6. 检查 +X 向右 20 mm、+Y 向上 20 mm、两轴垂直。

任何方向错误、落点不在纸内、机械异常或限位触发，立即发送 STOP。
