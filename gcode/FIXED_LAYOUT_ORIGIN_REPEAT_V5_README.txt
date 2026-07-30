固定摆放归零重复性单点测试 V5

目的：
  检查每次复位、自动归零后，同一个 command 坐标是否回到同一物理位置。
  本版不画坐标轴，不使用 V4 仿射参数。

固定测试点：
  command R = (180,20) mm

每一轮严格顺序：
1. 保持机器、纸张和底板完全不动，烧录后复位并等待自动归零完成。
2. STATUS 必须显示：
   id=FIXED_LAYOUT_ORIGIN_REPEAT_DOT_V5
   state=WAIT_ALIGN action=M801 lim1=0 lim2=0 pen=UP
3. 发送 FIXED_LAYOUT_ORIGIN_REPEAT_01_MOVE_V5.gcode。
4. 收到 completed=MOVE_REPEAT_X180_Y20、state=WAIT_DRAW、
   action=M802 后，确认笔尖位于纸内。
5. 发送 FIXED_LAYOUT_ORIGIN_REPEAT_02_DOT_V5.gcode。
6. 固件只在 R 点落笔 350 ms，XY 不移动，然后立即抬笔。
7. 收到 DONE 后复位，重新自动归零，再重复第 2~6 步。

总共执行三轮。三轮之间：
  不移动纸张；
  不移动写字机底座；
  不手动转动电机或机械臂；
  不改变笔架。

判断：
  三点完全重合或中心偏差 <=0.5 mm：归零重复性暂时通过。
  点间偏差 >1.0 mm：停止坐标校正，优先检查限位触发和归零释放过程。

任何机械异常、落点不在纸内或限位触发，立即发送 STOP。
