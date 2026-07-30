# V30 已作废：禁止发送

V30 把 `.gfont` 的向下 Y 轴误当成纸面的向上 Y 轴，字形整体上下颠倒。
下面的旧发送命令仅为历史记录，禁止执行。请改用：

`PAPER_A4_ZHANG_JIA_LE_AA_GUO_32MM_TANGENT_GCODE_V31.gcode`

原 V30 `.gcode` 已改名为
`INVALID_DO_NOT_RUN_PAPER_A4_ZHANG_JIA_LE_CHEN_HAND_V30.gcode.txt`，
不能再被标准发送器按 G-code 文件选择。

# 历史内容：“张佳乐”

## 内容

- 文字：`张佳乐`
- 字体：资料包固定资源 `陈手写`
- 可见字高：约 32 mm
- 排列：A4 竖向纸面中部横排
- 速度：`F180`
- 每一笔：6 mm 抬笔切线预接近后落笔
- 固件继续使用：`PAPER_A4_4X7_GRIDCAL_VERIFY_GCODE_V25`
- 纸面映射继续使用：`A4_BASE_QUADRATIC_GRID4X7_CAL_V5`

三个字分别为 7、7、5 笔，共 19 笔。字体文件没有使用 Hanzi Writer `medians`，
也没有宋体自动骨架中接近零长度的伪笔画。

## 发送

请换一张干净 A4 纸，保持纸、夹板、机械臂底座和连杆位置不变。复位并等待自动回零完成：

```powershell
powershell -ExecutionPolicy Bypass -File `
  "C:\Users\zjl\Desktop\zjl\TI\writer_robot\tools\send_standard_gcode_wait_ok.ps1" `
  -FilePath "C:\Users\zjl\Desktop\zjl\TI\writer_robot\gcode\PAPER_A4_ZHANG_JIA_LE_CHEN_HAND_32MM_TANGENT_GCODE_V30.gcode" `
  -PortName COM7
```

出现任意 `error:` 后立即停止，复位并重新自动回零，不要从中间续发。

## 结果照片

请提供一张完整包含 A4 四角、无遮挡、尽量正上方拍摄的原图。尺子如需展示，可以另拍
第二张，不要遮挡第一张照片中的文字和纸张边缘。
