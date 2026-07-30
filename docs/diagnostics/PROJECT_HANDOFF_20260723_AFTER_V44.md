# 写字机器人项目交接摘要（2026-07-23，当前 V44）

## 新对话必须先确认

1. V44 是否已经烧录；
2. 是否发送过 `STATUS`，返回的 Build ID 和状态是什么；
3. 是否已经运行过 `M891`；
4. 2026-07-23 最新照片只是拍照，还是移动过底座、A4 纸或夹板。

只要底座、纸张或夹板移动过，旧 ALIGN 立即失效。必须重新回零、重新对齐和重新确认坐标，不能直接运行 V44。

## 强制约束

1. 先完整读取：
   `docs/diagnostics/PROJECT_HANDOFF_20260720_AFTER_V28.md`
2. 再读取：
   `docs/diagnostics/AUTHOR_STAGE2_RETURN_TAKEUP_23_V28_ACTUAL_LOG_20260720.txt`
3. 然后读取：
   `docs/diagnostics/PROJECT_HANDOFF_20260720_AFTER_V30.md`
   `docs/diagnostics/AUTHOR_V7_TEXT_Y1095_X2_L205_L203_GATED_V35.md`
   `docs/diagnostics/AUTHOR_KAISHU_MEDIAN_16MM_L205_L203_GATED_V36.md`
   `docs/diagnostics/AUTHOR_A4_15MM_CLIPPED_CONTOUR_PENUP_L205_L203_ONEFILE_V43.md`
   `docs/diagnostics/AUTHOR_A4_3X3_20MM_SQUARE_CROSS_DRAW_L205_L203_ONEFILE_V44.md`
4. 数据、方向、原点或测量基准不确定时先询问，不得猜测。
5. 禁止 `reset/clean/checkout`；工作区有大量用户修改和未跟踪文件。
6. 方向补偿关闭，preload 关闭。
7. 不直接切换 `GCODE_SERIAL`，不运行 `2.0.gcode`。
8. 不运行 V39 的 `M817..M824`。
9. 断电、`STOP`、复位或重新烧录后，必须重新完成回零。

## 项目和资源位置

- 主项目：
  `C:\Users\zjl\Desktop\zjl\TI\writer_robot`
- 唯一正确 Keil 工程：
  `C:\Users\zjl\Desktop\zjl\TI\writer_robot\keil\gpio_toggle_output_LP_MSPM0G3507_nortos_keil.uvprojx`
- 当前参数：
  `APP\Inc\app_writer_motion.h`
- 当前任务选择：
  `TASK\writer_test.h`
- 当前执行器：
  `TASK\author_text_demo.c`
- 当前路径数据：
  `TASK\author_text_demo_path.h`
- 诊断资料：
  `docs\diagnostics`
- 固件备份：
  `backups`
- G-code：
  `gcode`
- 离线检查器：
  `tools`
- 汉字数据：
  `assets\hanzi_writer_data_68d10a4`
- 待写 Word 文档：
  `C:\Users\zjl\Desktop\日记本.docx`
- 用户历史源码：
  `C:\Users\zjl\Desktop\zjl\TI\writer_robot_source`
  该目录不是当前主工程，其中 README 的舵机 PA7 已过时。
- 原资料包：
  `C:\Users\zjl\Downloads\25.11.11drawbot完整资料包`

## 2026-07-23 最新实机摆放

照片：

`C:\Users\zjl\Desktop\zjl\TI\writer_robot\docs\diagnostics\CURRENT_AUTHOR_LIKE_A4_PLACEMENT_ACTUAL_20260723.jpg`

SHA-256：

`3FB55DD03F2FDF1F5D76824312124651AE5384B206DBB9FBF8FA23E6195CA7D9`

照片中的实际空间顺序已经与作者方案相似：

1. 电机、主转轴和底座位于 A4 纸外；
2. 机械臂从纸外伸向纸面；
3. 笔夹和笔尖位于纸面上方；
4. A4 横放在垫板/夹板上，底座不会压住 A4；
5. 控制板和驱动板位于底座一侧，不占用写字纸面。

该摆放解决了旧方案中“笔尖对准时底座会压住 A4，无法使用整张纸”的问题。

“与作者类似”只指机械摆放顺序，不代表以下内容相同：

- 固件和控制板；
- 坐标方向和原点；
- 臂长、减速比和步数；
- 回零角度、限位位置和校准参数；
- 可写范围和安全边界。

不能只根据照片宣称整张 A4 都安全。辅助四连杆死点不在当前两连杆数学模型中，仍需依靠 V43 实机轮廓和分区校准验证。

## 当前纸面合同

- A4 横放：左右 `297 mm`，上下 `210 mm`
- 纸面原点：照片中的纸张右下角
- `paper +X`：照片向上
- `paper -X`：照片向下
- `paper +Y`：照片向左
- `paper -Y`：照片向右
- ALIGN command：`(150,20) mm`
- ALIGN paper：`(14,58) mm`
- 换算：
  `command = paper + (136,-38) mm`

当前安全裁角多边形：

```text
(15,15)
(281,15)
(281,162)
(257,193)
(82,193)
(17,145)
```

它保留完整 15 mm 内框约 `94.03%` 的面积。右下区域还需要根据 V44 实测结果决定是否进一步缩进。

## 当前硬件和接线

- Stage1 大臂 STEP/DIR：`PA10/PA11`
- Stage2 小臂 STEP/DIR：`PA8/PA9`
- 舵机信号：`PA12`
- Stage1/Stage2 限位：`PA26/PA27`
- UART1：`PB4/PB5，115200 8N1`
- USB-TTL：
  `PB4(TX) -> TTL RX`
  `PB5(RX) <- TTL TX`
  `GND -> GND`
- 串口为 3.3 V 电平；开发板已有供电时不要再接 USB-TTL 的 VCC。
- 舵机红线接稳定 5 V，棕/黑线接 GND，信号接 PA12；舵机电源与开发板必须共地，不能接 12 V。
- 限位按 NC 方案：
  `PA26/PA27 -> 限位 NC`
  `限位 COM -> GND`
  正常闭合为低电平，触发断开后由内部上拉变为高电平。
- 当前固件只控制驱动器 STEP/DIR。若重新接 EN/RST/SLP/MS 或电机线，必须先确认驱动器是 A4988 还是 DRV8825。
- 带电时禁止插拔步进电机。

## 当前机械参数

- `L1/L2 = 205/203 mm`
- machine offset：`(-129,+128) mm`
- Stage1/Stage2：`40.099216/40.115790 steps/degree`
- theta/psi limit：`-0.773082/134.177381°`
- 方向补偿关闭
- preload 关闭
- 笛卡尔分段：`1 mm`
- V44 抬笔速度：`300 mm/min`
- V44 落笔速度：`240 mm/min`
- 舵机：`0°落笔，90°抬笔`

## 已遇到的主要问题

1. Stage2 换向回差  
   V28 实测约 `23 pulses`、`0.57°`、纸面约 `2 mm`。旧 preload 会造成一个方向缩短、另一个方向放大，因此正式固件保持关闭，不能直接加入补偿。

2. 小字对误差太敏感  
   V34 在旧文字中心区域四个方向约为 20 mm，中心重复点最大约差 1 mm。V35 两次写约 `16.7 x 5.7 mm` 的“张佳乐”失真相近，说明不是明显累积漂移，而是小字尺寸相对误差太大。

3. 局部修正不能推广全纸  
   旧中心区域曾使用：
   `command_y = 65 + (desired_y - 65) x 1.095`
   这个只在旧局部区域验证，不能直接用于整张 A4。

4. 旧纸位会让底座压住 A4  
   已通过当前作者式摆放解决：底座完全放在纸外，机械臂由纸外伸入。

5. 辅助四连杆死点  
   V39 的 `M817` 从 command `(150,20)` 移向 `(136,20)` 时越过辅助杆和大臂重合点，随后小臂反向。它不是普通 SCARA 两连杆 IK 奇点。当前采用实机经验保护：`command X >= 150 mm`，并永久停用 V39 `M817..M824`。

6. 完整 15 mm 矩形边界并非全部安全  
   左侧两个角的关节余量低，左上还接近两连杆伸展奇点，因此改为六边裁角安全轮廓。

7. 奎享原始 G-code 不能直接运行  
   原始页面方向、原点、字库、速度和当前固件门控不一致。必须先经过离线转换和检查。

8. 旧 `2.0.gcode` 不可运行  
   该文件为图片/矢量输出，共 1039 行，坐标约 `X=0..331.646，Y=-331.067..0`，不符合当前纸面合同。

9. 运行文件过多  
   V41/V42 曾需要 24/25 个文件。V43 和 V44 已改为一个 G-code 文件触发固件内部完整流程。

## 已实现和验证的内容

### V43：裁角安全轮廓

Build ID：

`AUTHOR_A4_15MM_CLIPPED_CONTOUR_PENUP_L205_L203_ONEFILE_V43`

用户已经完成整圈抬笔实机验证：

- 没有进入辅助四连杆死点；
- 没有两连杆奇点；
- 没有小臂反向；
- 没有卡顿、异响或碰撞；
- 正常返回。

这只证明当前摆放和对齐下轮廓抬笔可到达，不等于坐标比例、正交性和落笔精度已经校准。

### V44：九宫格 20 mm 方框十字落笔校准

Build ID：

`AUTHOR_A4_3X3_20MM_SQUARE_CROSS_DRAW_L205_L203_ONEFILE_V44`

唯一 HEX：

`keil\AUTHOR_A4_3X3_20MM_SQUARE_CROSS_DRAW_L205_L203_ONEFILE_V44.hex`

HEX SHA-256：

`EA9CCB7BAF88D6332B10C1D07B4DD8B25AD15B4A2966B7E1A1989D84A48E25EF`

唯一运行文件：

`gcode\V44_ONE_FILE\01_M891_RUN_ALL_9_ZONES_20MM_SQUARE_CROSS_V44.gcode`

G-code SHA-256：

`6E0FD6907994AD67CDA3778C9281E93FE5CD97ABAAF1B14702F4C7F426F4D572`

完整备份：

`backups\AUTHOR_A4_3X3_20MM_SQUARE_CROSS_DRAW_L205_L203_ONEFILE_V44_20260722.zip`

备份 SHA-256：

`844B7FA849483589D44CEA765C4C0746F37121F3F3239BE4AACADBFFF58E2E43`

V44 已完成：

- Keil 编译 `0 errors / 0 warnings`
- 完整离线检查通过
- 9 个区域
- 每区一个 `20 x 20 mm` 闭合方框
- 每区一条 20 mm 横线和一条 20 mm 竖线
- 共 27 次落笔、88 个路径点
- 预计运行约 9.43 分钟
- 新纸内点最低 `command X=166 mm`
- ALIGN 最低 `command X=150 mm`

V44 是否已经烧录或实机运行，目前没有明确确认，不能写成已经完成。

运行前 `STATUS` 应看到：

```text
id=AUTHOR_A4_3X3_20MM_SQUARE_CROSS_DRAW_L205_L203_ONEFILE_V44 state=WAIT_ALIGN action=M891 lim1=0 lim2=0 pen=UP
```

正常结束应看到：

```text
completed=CALIBRATION run=1/1 state=DONE action=NONE pen=UP rehome=1
```

## 当前目标

最近一步：

1. 先确认最新摆放是否移动了底座、纸张或夹板；
2. 如移动过，重新回零并重新完成 ALIGN；
3. 烧录和运行 V44；
4. 测量九个区域的方框四边、对角线、闭合差、横竖中心线、垂直度、弯曲和重影；
5. 拍一张垂直俯拍全纸照片，并拍误差明显区域近照；
6. 根据九区数据建立局部比例、正交和位置修正。

最终目标：

1. 编写“Word/奎享/Hanzi 路径 -> 当前纸面坐标”的离线转换器；
2. 强制检查速度、缺字、安全裁角多边形、IK、限位、辅助死点经验边界和整数脉冲；
3. 在安全范围内尽量用满 A4，书写 `C:\Users\zjl\Desktop\日记本.docx` 的两三行或更多文字；
4. 完成实机验证前不恢复无限制 `GCODE_SERIAL`。

## 奎享 G-code 生成软件

- 主程序：
  `C:\Users\zjl\Downloads\25.11.11drawbot完整资料包\生成gcode\奎享雕刻软件（绿色版）（生成gcode）\奎享雕刻软件（绿色版）\奎享雕刻机.exe`
- 插件：
  同目录 `plugs\GcodeTools.jar`
- 教程：
  `C:\Users\zjl\Downloads\25.11.11drawbot完整资料包\生成gcode\【教程】奎享雕刻导出Gcode教程.pdf`
- 用户配置：
  `C:\Users\zjl\.gcodetools`
- 反编译结果：
  `C:\Users\zjl\Desktop\zjl\TI\writer_robot\tmp\reverse\kenjoy_cfr_0152\decompiled`

当前结论：可以把“笔记”模式作为文字排版和单线路径前端，但原始 G-code 不能直接发送给 V44，必须经过项目专用转换和检查。

## 作者源码、链接和版本关系

### 本地作者参考源码

`C:\Users\zjl\Downloads\DrawBot-ramps-main\DrawBot-ramps-main`

核心文件包括 `scara.c/scara.h`。这是下载的 GitHub ZIP，没有 `.git` 历史，因此准确 commit 未知。它面向 `MEGA2560 + RAMPS 1.4`，是 GRBL 0.9j 修改版本，包含作者原始 offset、`$M` 标定和 `M3 Sx/M5` 舵机控制。

### GitHub 在线仓库

`https://github.com/akv47/DrawBot-ramps`

在线 main 可能已经变化，不能默认与本地 ZIP 完全一致。

### Thingiverse 机械项目

`https://www.thingiverse.com/thing:3096135`

项目名为 MG-mossbot。它主要代表机械结构项目，不等于 GitHub 固件版本。

### 作者视频

`https://www.youtube.com/watch?v=nXxYWECz4rc`

### MakerWorld 参考页面

`https://makerworld.com/zh/models/712239-a-writing-robot-arm-the-drawbot?from=search#profileId-1268105`

### 原中文资料包

`C:\Users\zjl\Downloads\25.11.11drawbot完整资料包`

其中包含 `drawbot1.2.0.2.hex`、`机械臂大师1.1.0.1.exe`、`机械臂大师1.2.1.msi`。目前没有证据证明这些二进制就是由本地 GitHub ZIP 编译，因此必须把它视为第三套独立发行内容。

### 当前 MSPM0 工程

当前 V44 是基于 MSPM0G3507 的独立移植和门控实现，不等同于：

1. 本地 GitHub ZIP；
2. GitHub 在线 main；
3. Thingiverse 机械项目；
4. 中文资料包二进制。

### 汉字数据

`https://github.com/chanind/hanzi-writer-data`

本地固定版本目录：

`assets\hanzi_writer_data_68d10a4`

它只提供汉字路径数据，也不是作者固件的一部分。
