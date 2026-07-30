固定纸张 A4 九宫格 20 x 20 mm 矩形单文件测试 V13

纸张定义：
  A4 竖放，宽 210 mm、高 297 mm。
  原点位于纸张左下角。
  +X 朝纸张右方，+Y 朝纸张上方。
  固定摆放方式和 V11 现场确认时完全相同。

区域与自动顺序：
  R11 左上 -> R12 中上 -> R13 右上
                                  |
  R21 左中 <- R22 中中 <- R23 右中
  |
  R31 左下 -> R32 中下 -> R33 右下

每个区域绘制一个 20 x 20 mm 闭合矩形：
  右 20 -> 上 20 -> 左 20 -> 下 20

操作：
  1. 烧录 V13 并复位，等待自动归零完成。
  2. 发送 STATUS，确认：
       id=FIXED_LAYOUT_A4_GRID9_SQUARES_ONEFILE_V13
       state=WAIT_ALIGN action=M801
       lim1=0 lim2=0 pen=UP
  3. 确认纸张和机械周围无障碍后，只发送一次：
       FIXED_LAYOUT_A4_GRID9_ONEFILE_V13.gcode
  4. 固件会自动移动并依次画完九个矩形。
  5. 最终串口返回 DONE completed_count=9/9。

运行过程中：
  STATUS  可查询当前区域与进度。
  STOP    立即抬笔并停止，之后必须复位和重新归零。
  任意限位开关触发会自动抬笔、急停并进入 ERROR。
