固定摆放纸面坐标仿射校正验证 V4

状态：已判废，禁止继续执行。
现场照片确认 V4 引入剪切并破坏 X/Y 垂直关系；请改用 V5 归零重复性测试。

采用的 V3 实测值（mm）：
  O 点：A0=218, B0=142
  旧 +X 尖端：AX=189, BX=121
  旧 +Y 尖端：AY=229, BY=130

注意：
  用户最后一项写成了第二个 AX，本版按 BX=121 解释。

纸面坐标：
  原点 P0 = 纸张右下角
  +X = 朝纸张上边
  +Y = 朝纸张左边

V4 绘制内容：
  保留测量基准 O 的 command 坐标 (170,20)。
  从 O 绘制校正后的纸面 +X 箭头，目标长度 20 mm。
  从 O 绘制校正后的纸面 +Y 箭头，目标长度 20 mm。

校正后的 command 尖端：
  paper +X 20 mm -> command (157.565, 41.762)
  paper +Y 20 mm -> command (158.601,-10.052)

离线安全检查：
  command X 范围 157.565..170.000 mm
  command Y 范围 -10.052..41.762 mm
  最小关节裕量 30.022 deg

严格顺序：
1. 烧录并复位，等待自动归零完成。
2. STATUS 必须显示：
   id=FIXED_LAYOUT_AFFINE_AXES_20MM_V4
   state=WAIT_ALIGN action=M801 lim1=0 lim2=0 pen=UP
3. 发送 FIXED_LAYOUT_AFFINE_AXES_01_ALIGN_V4.gcode。
4. 收到 state=WAIT_DRAW action=M802 后检查笔尖在纸内。
5. 发送 FIXED_LAYOUT_AFFINE_AXES_02_DRAW_V4.gcode。
6. 正确结果应为：
   +X 尖端到下边 AX 约 238 mm，到右边 BX 约 142 mm；
   +Y 尖端到下边 AY 约 218 mm，到右边 BY 约 162 mm。
   两条轴均从 O 出发，纸面长度约 20 mm，且互相垂直。

任何方向错误、落点不在纸内、机械异常或限位触发，立即发送 STOP。
