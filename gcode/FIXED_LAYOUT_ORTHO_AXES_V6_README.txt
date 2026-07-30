固定摆放正交坐标轴旋转验证 V6

状态：已完成诊断，目标轴定义已被用户修订，不作为最终坐标固件。
最终目标为 +X 朝纸张右边、+Y 朝纸张上边。

前提：
  V5 三次归零单点测试已通过。
  V4 仿射参数已判废，V6 不使用剪切和独立轴缩放。

纸面坐标定义：
  +X = 朝纸张上边
  +Y = 朝纸张左边

测试 O：
  command O = (180,20) mm

校正方法：
  旧 command +X 相对纸张向下方向向右偏约 20.5 deg。
  V6 反转正方向并进行 20.5 deg 刚性旋转。
  两个 command 目标向量等长且严格垂直：
    paper +X 20 mm -> command (161.267,27.004)
    paper +Y 20 mm -> command (172.996, 1.267)

离线检查：
  command 两轴长度 19.9995 mm
  command 两轴夹角 90.0000 deg
  command X 范围 161.267..180.000 mm
  command Y 范围   1.267..27.477 mm
  最小关节裕量 34.417 deg

严格顺序：
1. 烧录并复位，等待自动归零完成。
2. STATUS 必须显示：
   id=FIXED_LAYOUT_ORTHO_AXES_20MM_V6
   state=WAIT_ALIGN action=M801 lim1=0 lim2=0 pen=UP
3. 发送 FIXED_LAYOUT_ORTHO_AXES_01_MOVE_V6.gcode。
4. 收到 state=WAIT_DRAW action=M802 后确认笔尖在纸内。
5. 发送 FIXED_LAYOUT_ORTHO_AXES_02_DRAW_V6.gcode。
6. 检查：
   X 箭头是否朝纸张上边；
   Y 箭头是否朝纸张左边；
   两轴是否垂直；
   两轴是否均约 20 mm。

任何方向错误、落点不在纸内、机械异常或限位触发，立即发送 STOP。
