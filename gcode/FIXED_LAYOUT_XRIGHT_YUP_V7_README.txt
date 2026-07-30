固定摆放最终方向坐标轴验证 V7

最终纸面坐标：
  +X = 朝纸张右边
  +Y = 朝纸张上边

V6 实测输入：
  当前向左轴水平且长度 20 mm；
  当前向上轴总长 20 mm，尖端向左偏 2 mm；
  当前向上分量 sqrt(20^2-2^2) = 19.8997 mm；
  当前向上轴左偏角 5.7392 deg。

V7 校正：
  +X 使用 V6 向左轴的精确反方向；
  +Y 消除 2 mm 左偏，并把向上分量补足到 20 mm。

测试 O：
  command O = (180,20) mm

目标 command 尖端：
  paper +X right 20 mm -> command (187.004,38.733)
  paper +Y up    20 mm -> command (161.876,28.922)

注意：
  为抵消实机二维映射误差，V7 的两个 command 向量本身不是 90 deg；
  离线反算后的纸面预测向量为：
    paper +X = (19.9995, 0.0000) mm
    paper +Y = (-0.0002,20.0000) mm

离线检查：
  command X 范围 161.876..187.416 mm
  command Y 范围 20.000..38.733 mm
  最小关节裕量 34.175 deg

严格顺序：
1. 烧录并复位，等待自动归零完成。
2. STATUS 必须显示：
   id=FIXED_LAYOUT_XRIGHT_YUP_20MM_V7
   state=WAIT_ALIGN action=M801 lim1=0 lim2=0 pen=UP
3. 发送 FIXED_LAYOUT_XRIGHT_YUP_01_MOVE_V7.gcode。
4. 收到 state=WAIT_DRAW action=M802 后确认笔尖在纸内。
5. 发送 FIXED_LAYOUT_XRIGHT_YUP_02_DRAW_V7.gcode。
6. 检查：
   +X 是否朝纸张右边且约 20 mm；
   +Y 是否朝纸张上边且约 20 mm；
   两条纸面轴是否垂直。

任何方向错误、落点不在纸内、机械异常或限位触发，立即发送 STOP。
