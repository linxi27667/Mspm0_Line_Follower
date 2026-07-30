# V29 切线预接近复测说明

## 目的

V29 用抬笔状态下的 6 mm 切线预接近消除 G1 起步时的关节换向，同时在纸面右侧增加
三个纯落笔控制点，用一张照片区分“关节回差”与“笔架落笔侧移”。

本轮不需要重新编译或烧录，继续使用：

- 固件 ID：`PAPER_A4_4X7_GRIDCAL_VERIFY_GCODE_V25`
- 纸面映射：`A4_BASE_QUADRATIC_GRID4X7_CAL_V5`

## 发送

请换一张干净 A4 纸，但纸、夹板、机械臂底座和连杆的固定位置不能改变。复位并等待自动
回零完成后发送：

```powershell
powershell -ExecutionPolicy Bypass -File `
  "C:\Users\zjl\Desktop\zjl\TI\writer_robot\tools\send_standard_gcode_wait_ok.ps1" `
  -FilePath "C:\Users\zjl\Desktop\zjl\TI\writer_robot\gcode\PAPER_A4_3POS_8DIR_20MM_TANGENT_APPROACH_GCODE_V29.gcode" `
  -PortName COM7
```

出现任意 `error:` 后立即停止，复位并重新自动回零，不要从中间续发。

## 拍照时重点

右侧 X=165 mm 处会有下、中、上三个纯落笔控制点。请重点观察：

- 它们是接近圆点，还是被拉成长约 3～4 mm 的竖线。
- 三组左右横线的命令起点是否还翘头/低头。
- 右侧两条斜线的最右端是否还先走竖线再转向。

照片需要完整拍到 A4 四角、无遮挡、镜头尽量正对纸面。尺子可以另拍第二张，不要挡住
第一张用于单应性校正的照片。
