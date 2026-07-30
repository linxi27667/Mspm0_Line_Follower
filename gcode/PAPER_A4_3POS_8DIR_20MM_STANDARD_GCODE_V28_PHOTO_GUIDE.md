# V28 三位置八方向轨迹校准：发送与拍照说明

## 文件与固件合同

- G-code：`PAPER_A4_3POS_8DIR_20MM_STANDARD_GCODE_V28.gcode`
- 轨迹示意图：`../docs/diagnostics/PAPER_A4_3POS_8DIR_20MM_STANDARD_GCODE_V28_PREVIEW.png`
- 固件 ID：`PAPER_A4_4X7_GRIDCAL_VERIFY_GCODE_V25`
- 纸面映射 ID：`A4_BASE_QUADRATIC_GRID4X7_CAL_V5`
- 串口：`COM7`，115200，8N1，无流控
- 本轮不修改 V25 固件、不修改 4×7 公共纸面映射。

## 轨迹布局

纸张继续 A4 竖放，纸面原点在左下角，+X 向右，+Y 向上。下、中、上
三个区域的名义中心分别为：

- `(105.000, 56.667)` mm
- `(105.000, 130.000)` mm
- `(105.000, 203.667)` mm

每个区域有 8 条彼此独立的 20 mm 直线，速度均为 `F180`。每组从上到下：

1. 水平：左侧 `+X`，右侧 `-X`
2. 竖直：左侧 `+Y`，右侧 `-Y`
3. `/`：左侧 `+X+Y`，右侧 `-X-Y`
4. `\`：左侧 `+X-Y`，右侧 `-X+Y`

每条线都严格使用 `G0 起点 → M3 → G1 终点 → M5`，不存在落笔连接线。

## 发送

先复位并等待自动回零完成。发送器会先检查固件 ID、纸面映射、忙碌状态、
限位状态和笔状态，然后逐行等待 `ok`：

```powershell
powershell -ExecutionPolicy Bypass -File `
  "C:\Users\zjl\Desktop\zjl\TI\writer_robot\tools\send_standard_gcode_wait_ok.ps1" `
  -FilePath "C:\Users\zjl\Desktop\zjl\TI\writer_robot\gcode\PAPER_A4_3POS_8DIR_20MM_STANDARD_GCODE_V28.gcode" `
  -PortName COM7
```

若出现任意 `error:`，立即停止发送，复位并等待重新自动回零；不要从中间续发。

## 拍照

完成后只需要提供一张原始照片：

- 镜头尽量位于纸面正上方，避免倾斜和广角畸变。
- 完整拍到 A4 四个角，不要裁掉纸边。
- 轨迹清楚、对焦准确、光线均匀，尽量避免阴影压住线条。
- 不要移动纸、夹板、机械臂底座或连杆。
- 不必手工逐条测量，也不要在照片上画线或压缩后再上传。

收到原图后，可先用 A4 四角做单应性校正，再自动比较三处轨迹的角度、
长度、弯曲、局部旋转/比例/剪切及同一路径正反方向的端点差。
