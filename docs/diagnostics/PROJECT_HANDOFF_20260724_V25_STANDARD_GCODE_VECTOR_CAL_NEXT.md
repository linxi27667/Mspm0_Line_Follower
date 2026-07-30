# 写字机项目交接：V25 标准 G-code、4×7 纸面校正与下一步轨迹标定

更新时间：2026-07-24  
当前工程：MSPM0G3507 写字机  
当前固件 ID：`PAPER_A4_4X7_GRIDCAL_VERIFY_GCODE_V25`

> 这是当前应优先使用的交接文档。  
> `PROJECT_HANDOFF_20260723_AFTER_V44.md` 记录的是旧 V44 固定布局/门控流程，
> 对当前标准 G-code 坐标合同已经过时，不要让新对话继续按 V44、M801/M802
> 或旧 3×3 方框流程修改。

## 1. 给新对话的最短上下文

可以直接把下面这段交给新对话：

> 请先阅读
> `C:\Users\zjl\Desktop\zjl\TI\writer_robot\docs\diagnostics\PROJECT_HANDOFF_20260724_V25_STANDARD_GCODE_VECTOR_CAL_NEXT.md`。
> 当前是 MSPM0G3507 的 V25 标准 G-code 固件，不是旧 V44 门控固件。
> A4 纸和机械臂已经固定，纸面坐标原点在左下角，+X 向纸张右方，+Y 向纸张上方。
> 当前已经实现全局二次纸面映射和 4×7 局部校正；28 点静态检查通过。
> 目前不要继续按某一个汉字单独改 G-code，也不要恢复 V44。
> 下一步应先生成“三个纸面位置 × 八个方向”的等长直线轨迹校准 G-code，
> 用一张包含完整 A4 四角的俯拍照片自动分析横、竖、两条对角线及正反向差异，
> 分清字形数据、纸面映射、机械回差和落笔摩擦问题。

## 2. 当前工程和文件地址

### 2.1 当前唯一主工程

工程根目录：

`C:\Users\zjl\Desktop\zjl\TI\writer_robot`

正确的 Keil 工程：

`C:\Users\zjl\Desktop\zjl\TI\writer_robot\keil\gpio_toggle_output_LP_MSPM0G3507_nortos_keil.uvprojx`

不要误用同目录中带 `TI_moban_...` 名称的旧模板工程。

当前 Git 远端：

`https://github.com/linxi27667/TI_moban.git`

这个远端只是 MSPM0 模板/当前工程的来源，不是 DrawBot 作者固件仓库。

### 2.2 当前活动源码

- 模式选择：`TASK\writer_test.h`
- 标准 G-code 接收器：`TASK\gcode_serial.c`、`TASK\gcode_serial.h`
- 纸面坐标映射：`APP\Src\app_writer_paper_map.c`
- 纸面映射配置：`APP\Inc\app_writer_paper_map.h`
- 运动规划：`APP\Src\app_writer_motion.c`
- 机械参数：`APP\Inc\app_writer_motion.h`
- SCARA 正逆解：`MID\Src\mid_scara.c`
- 回零与限位：`TASK\writer_home.c`
- PB4/PB5 串口：`COMM\Src\comm_vision_uart.c`
- 舵机：`APP\Src\app_servo.c`
- 当前有效步进绑定：`APP\stepper\Inc\app_stepper.h`
- 主程序：`main.c`

注意：仓库中仍有一些旧目录和同名文件。当前步进头文件是
`APP\stepper\Inc\app_stepper.h`，不要误用旧的
`APP\Inc\app_stepper.h` 或其他历史副本。

### 2.3 当前构建产物

当前 HEX：

`C:\Users\zjl\Desktop\zjl\TI\writer_robot\keil\PAPER_A4_4X7_GRIDCAL_VERIFY_GCODE_V25.hex`

构建日志：

`C:\Users\zjl\Desktop\zjl\TI\writer_robot\keil\PAPER_A4_4X7_GRIDCAL_VERIFY_GCODE_V25_build.log`

构建结果：

- Keil：`0 Error(s), 0 Warning(s)`
- HEX SHA-256：
  `863343E4B71A6B1CA4ACE9F5E008E4A86F8AEB15C53552562CD1A97D7C17D9AE`
- `Jlink.jflash` 当前已经指向这个 V25 HEX。

### 2.4 G-code、工具和诊断资料

目录：

- G-code：`C:\Users\zjl\Desktop\zjl\TI\writer_robot\gcode`
- 工具：`C:\Users\zjl\Desktop\zjl\TI\writer_robot\tools`
- 诊断文档：`C:\Users\zjl\Desktop\zjl\TI\writer_robot\docs\diagnostics`
- 备份：`C:\Users\zjl\Desktop\zjl\TI\writer_robot\backups`
- 构建产物：`C:\Users\zjl\Desktop\zjl\TI\writer_robot\keil`

当前 4×7 标准校准 G-code：

`gcode\PAPER_A4_4X7_REACH_RAW_DOT_GCODE_V23.gcode`

当前 V25 复测记录表：

`gcode\PAPER_A4_4X7_GRIDCAL_VERIFY_GCODE_V25_MEASUREMENTS.md`

当前通用串口发送器：

`tools\send_standard_gcode_wait_ok.ps1`

4×7 校正推导和检查工具：

- `tools\derive_paper_a4_4x7_grid_v24.py`
- `tools\derive_paper_a4_4x7_grid_v25.py`
- `tools\check_paper_a4_4x7_gridcal_verify_v25.py`

汉字“永”的两个诊断文件：

- 不应继续使用的 Hanzi Writer 版本：
  `gcode\PAPER_A4_CENTER_YONG_18MM_STANDARD_GCODE_V26.gcode`
- 手工单线诊断版本：
  `gcode\PAPER_A4_YONG_SINGLELINE_18MM_STANDARD_GCODE_V27.gcode`
- V27 静态检查：
  `tools\check_paper_a4_yong_singleline_v27.py`

V26、V27 都只是诊断，不是最终文字生成方案。

### 2.5 其他本地资源

旧的用户工程副本：

`C:\Users\zjl\Desktop\zjl\TI\writer_robot_source`

它不是当前工程，其中 README 的舵机引脚等信息已经过时。

微信临时照片目录：

`C:\Users\zjl\Documents\xwechat_files\wxid_ggj9bqut1ii122_6820\temp\RWTemp\2026-07\9e20f478899dc29eb19741386f9343c8`

这是临时目录，重要照片以后应复制到当前工程的固定资源目录，不能长期依赖
微信缓存路径。

## 3. 纸张、坐标系和固定放置方式

现在固定使用 A4 竖放：

- 纸面尺寸：210 mm × 297 mm。
- 纸面原点：纸张左下角。
- 纸面 +X：向纸张右方。
- 纸面 +Y：向纸张上方。
- 纸和机械臂的位置已经固定；一旦移动纸、夹板、机械臂底座或连杆，
  当前校准就不再有效。

当前固件允许并完成校准的纸面范围：

- X：25.0 ～ 185.0 mm
- Y：20.0 ～ 240.333333 mm
- 网格：4 列 × 7 行，共 28 个节点

这不是整张 A4 的数学边界，而是当前验证过并纳入映射的书写区。

## 4. 当前硬件合同

主控：MSPM0G3507，裸机程序。

引脚：

- 一级臂 STEP：PA10
- 一级臂 DIR：PA11
- 二级臂 STEP：PA8
- 二级臂 DIR：PA9
- 舵机：PA12 / TIMG0
- 一级臂限位：PA26
- 二级臂限位：PA27
- G-code 串口 UART1 TX：PB4
- G-code 串口 UART1 RX：PB5
- UART1：115200，8N1，无流控

限位开关：

- 当前按 NC 接法接到 GND。
- PA26、PA27 都启用内部上拉。
- 生成配置中准确出现 2 个 `DL_GPIO_RESISTOR_PULL_UP`。
- 正常闭合时输入为低；触发/断开时上拉为高，程序把高电平判断为限位触发。

舵机：

- 0°：落笔
- 90°：抬笔
- 上电先抬笔并等待 700 ms，再自动回零。

## 5. 当前机械和运动参数

- 一级臂 L1：205 mm
- 二级臂 L2：203 mm
- 机械坐标偏移：X = -129 mm，Y = +128 mm
- 一级臂限位角：-0.773082°
- 二级臂限位角：134.177381°
- 一级臂：40.099216 step/°
- 二级臂：40.115790 step/°
- 回零后离开限位：1°
- 方向补偿：关闭
- 预加载补偿：关闭
- 内部笛卡尔规划分段：1 mm
- 内部最大规划段数：192
- G-code 落笔轨迹在纸面空间每 2 mm 再分段
- G-code 抬笔快速移动在内部用户空间每 20 mm 再分段

历史上测到二级臂换向间隙约 23 个脉冲，约 0.57°，纸面上约可表现为
2 mm 量级。旧的预加载补偿曾造成一个方向缩短、另一个方向放大，所以当前
保持关闭，不能在没有新正反向数据的情况下恢复。

## 6. 当前固件实际实现了什么

### 6.1 标准 G-code 模式

`TASK\writer_test.h` 当前选择：

`WRITER_TEST_MODE_GCODE_SERIAL`

固件 ID：

`PAPER_A4_4X7_GRIDCAL_VERIFY_GCODE_V25`

纸面映射 ID：

`A4_BASE_QUADRATIC_GRID4X7_CAL_V5`

支持的主要命令：

- `G0`、`G1`
- `G4`
- `G21`
- `G90`、`G91`
- `G94`
- `M3`、`M5`
- `M501`
- 独立 `F`、`S`、`Z` 元数据
- `STATUS`
- `STOP`

当前流程不再要求 V44 的 `M801/M802/...` 分步门控。

### 6.2 自动回零和安全状态

上电/复位后：

1. 舵机抬笔。
2. 等待 700 ms。
3. 两轴自动寻找限位并离开限位。
4. 回零成功后才启动 G-code 模式。

任何解析或运动错误都可能调用紧急停止并把运动状态锁为未就绪。
发生 `error:` 后不要继续发送下一行；应复位，让机器重新自动回零。

### 6.3 公共纸面映射

现在普通 G-code 坐标不是直接送给 SCARA 逆解，而是经过统一映射：

`标准纸面坐标 → 全局二次映射 → 4×7 局部残差双线性插值 → 用户/机械坐标 → SCARA 逆解 → 电机脉冲`

全局二次映射由先前 36 个纸面顶点拟合。

4×7 局部修正由两次 28 点测量得到：

1. V23 原始 4×7 点阵测量产生 V24 局部校正。
2. V24 再次测量 28 点，产生当前 V25 的第二次校正。

当前 `APP_WRITER_PAPER_GRID_CORRECTION_ENABLE` 为 1。

### 6.4 当前校准检查结果

`tools\check_paper_a4_4x7_gridcal_verify_v25.py`：

- PASS
- 28 个节点
- 4×7 校正已打开
- 复用标准 V23 点阵 G-code

`tools\check_paper_a4_yong_singleline_v27.py`：

- 静态路径检查 PASS
- 5 笔
- 6 个 G0
- 36 个 G1

注意：V27 静态检查通过只说明命令、边界和可达性通过，不代表实际字形已经正确。

## 7. 两轮 4×7 测量数据

目标网格：

- X：25.000、78.333、131.667、185.000 mm
- Y：20.000、56.667、93.333、130.000、167.000、203.667、240.333 mm

### 7.1 V23 原始点阵的实测结果

每行从左到右，共 7 行：

```text
(25.0,42.0)  (84.0,42.0)  (140.0,40.0)  (193.0,40.0)
(26.8,75.0)  (84.2,77.7)  (138.5,77.0)  (189.0,76.2)
(26.3,111.0) (72.3,113.0) (132.0,114.0) (183.5,113.0)
(29.0,149.0) (81.0,151.0) (133.7,152.0) (183.5,151.0)
(28.4,187.5) (71.0,185.5) (130.2,186.7) (182.0,188.0)
(27.0,226.0) (80.0,224.0) (133.7,224.3) (183.5,223.9)
(20.5,255.0) (77.5,255.0) (133.5,257.0) (180.6,260.0)
```

这组数据进入 `tools\derive_paper_a4_4x7_grid_v24.py`。

### 7.2 V24 校正后的再次实测结果

```text
(27.3,14.0)  (80.5,14.8)  (133.0,15.0)  (186.0,14.3)
(25.0,51.0)  (78.5,51.2)  (131.5,51.2)  (184.0,51.0)
(22.7,88.0)  (70.9,89.0)  (122.5,88.0)  (181.5,88.0)
(24.0,125.0) (81.5,126.0) (131.9,125.0) (184.0,125.0)
(23.0,161.0) (71.0,162.0) (127.5,161.0) (181.6,161.0)
(23.6,200.0) (81.0,200.5) (131.0,200.0) (182.3,199.0)
(20.1,233.0) (75.0,233.4) (128.0,234.0) (185.0,236.0)
```

这组数据进入 `tools\derive_paper_a4_4x7_grid_v25.py`，形成当前 V25。

更早的三个矩形四角测量对发现“不同区域形变不同”有诊断价值，但当前公共
映射已经由更完整的 4×7 数据取代；以后不要再用三个矩形的专用 G-code
偏移作为生产校正。

## 8. 已经遇到的主要问题和结论

### 8.1 旧固定布局坐标与纸面方向混乱

早期 V1～V18 以及 V44 使用固定布局和自定义门控命令。曾出现：

- 用户认为 X 应向纸张右方、Y 应向纸张上方，但运动方向与照片方向混淆。
- 横竖虽然接近垂直，整体仍旋转或局部歪斜。
- 只调单条 X/Y 线或单个矩形，换一个区域又变形。
- 把每个区域写成专用 G-code 会掩盖公共坐标映射问题。

当前结论：旧 V44 流程只能作为历史诊断，不再作为主线。

### 8.2 限位开关一度看起来失效

根因与引脚/输入上拉/开关逻辑合同有关。当前已经固定为：

- PA26、PA27
- NC 到 GND
- 内部上拉
- 高电平表示触发/断线

当前自动回零使用这套合同。

### 8.3 纸面不同区域出现不同形变

9 个矩形和后续 3 个矩形表明，误差不是简单的整体平移、整体旋转或一个
仿射矩阵可以解决。只改某个 G-code 会不断重复无效劳动。

因此改成公共的：

- 全局二次基线
- 4×7 局部残差校正

所有标准 G-code 都复用同一映射，不再给每个字符或每个矩形单独加偏移。

### 8.4 串口发送过快导致落笔错误

出现过：

`error:pen_down_without_paper_position`

原因是固件还没有接受并完成有效纸面 `G0`，就收到 `M3`；或者上位机连续
发送命令而不等待每行 `ok`。

解决方法：必须一行一行发送，每行收到 `ok` 后再发下一行。
`tools\send_standard_gcode_wait_ok.ps1` 已经实现这个握手。

### 8.5 `motion_rejected`

出现过：

`error:motion_rejected`

一旦前面发生解析/运动错误，固件会紧急停止并把运动状态锁住；这时继续发
第一个 `G0` 仍会被拒绝。

解决方法：

1. 停止继续发送。
2. 复位固件。
3. 等待自动回零完成。
4. `STATUS` 确认空闲、限位释放、抬笔。
5. 再从 G-code 文件第一行开始。

### 8.6 PowerShell 发送脚本路径错误

旧脚本曾因 `$PSScriptRoot` 为空而报：

`Join-Path : 无法将参数绑定到参数“Path”`

当前脚本已经改用 `$MyInvocation.MyCommand.Path` 求脚本目录，并允许通过
`-FilePath` 显式指定 G-code。

### 8.7 矩形正确不等于汉字正确

矩形和点阵主要验证端点位置；汉字还会暴露：

- 短线段量化
- 连续换向
- 对角线方向误差
- 笔尖摩擦和笔架弹性
- 笔画数据本身不适合作单线书写

所以完成 4×7 点位校正之后，不能直接断言文字链路已经完成。

### 8.8 “永”字的问题

机器并不认识“横、竖、撇、捺”这些语义。机器真正执行的是：

`字形数据 → 每笔坐标点序列 → G0/G1 线段 → 纸面映射 → 逆解 → 脉冲`

V26 直接使用 Hanzi Writer `medians`，实际写出的结构不正确。这个数据主要
服务于动画笔顺/中线展示，不是可靠的生产级单线字体。

V27 是手工画的单线“永”，预览可辨认，但实际纸面结果仍明显不理想。
这说明目前至少还不能分清：

- 字形坐标设计是否不对；
- 横竖斜线在短线段和换向时是否变形；
- 笔尖落笔后是否因摩擦产生弯曲。

因此继续只改“永”的坐标没有足够诊断意义。

## 9. 当前目标

当前目标不是马上批量写字，也不是继续给某一个汉字手工补偿。

下一步应建立一个与字形无关的“基本轨迹体检”：

### 9.1 三个纸面位置

在当前安全书写区的：

- 下部
- 中部
- 上部

各画同一套轨迹，以判断误差是否随纸面位置变化。

### 9.2 每个位置画八个方向

建议使用相同长度、相同速度的独立直线：

1. 水平向右
2. 水平向左
3. 竖直向上
4. 竖直向下
5. `/` 方向正向
6. `/` 方向反向
7. `\` 方向正向
8. `\` 方向反向

“八方向”本质上是四条几何方向分别做正向和反向，用来暴露换向间隙。

建议首轮：

- 线长 20 mm
- `F180`
- 每条线独立抬落笔
- 三个区域集成在一个标准 G-code 文件
- 不修改当前 V25 公共映射

### 9.3 用户需要提供的数据

首轮不要求用户逐条用尺测很多数字。

用户只需提供一张：

- 正上方俯拍
- 完整看见 A4 四个角
- 轨迹清楚
- 镜头尽量不要倾斜

然后利用已知 A4 尺寸做照片单应性校正，自动计算：

- 每条线的实际角度
- 实际长度
- 直线弯曲程度
- 三个区域的局部旋转、比例和剪切
- 同一路径正反方向的端点差异

### 9.4 根据结果决定修改哪里

- 如果八方向在三个位置都正确：
  运动程序暂不改，问题主要在字形前端，应建立真正的单线中文字库/骨架路径。
- 如果同一区域所有方向同样旋转或缩放：
  修改公共纸面映射，不修改单个汉字。
- 如果误差随纸面位置明显变化：
  继续完善局部映射或机械模型。
- 如果同一条线正向和反向明显不同：
  再设计方向/回差补偿，并先用轨迹验证，不能直接恢复旧预加载参数。
- 如果抬笔端点正确、落笔直线弯曲：
  优先检查笔压、笔尖摩擦、笔架刚性和舵机落笔角。

完成基本轨迹体检后，再进入：

1. 正规单线中文字体或字体骨架生成；
2. 标准 G-code 输出；
3. 多字符排版；
4. 全纸面复测。

## 10. 当前标准发送方法

当前串口：`COM7`  
波特率：115200

发送任意标准 G-code：

```powershell
powershell -ExecutionPolicy Bypass -File `
  "C:\Users\zjl\Desktop\zjl\TI\writer_robot\tools\send_standard_gcode_wait_ok.ps1" `
  -FilePath "C:\Users\zjl\Desktop\zjl\TI\writer_robot\gcode\你的文件.gcode" `
  -PortName COM7
```

发送器会先发 `STATUS`，要求：

- `id=PAPER_A4_4X7_GRIDCAL_VERIFY_GCODE_V25`
- `paper_map=A4_BASE_QUADRATIC_GRID4X7_CAL_V5`
- `grid4x7=1`
- `busy=0`
- `lim1=0`
- `lim2=0`
- `pen=UP`

然后逐行发送并等待 `ok`。

不要用普通串口工具一次性粘贴整个文件。

## 11. 构建方法

工作目录：

`C:\Users\zjl\Desktop\zjl\TI\writer_robot\keil`

Keil 命令：

```powershell
& "C:\Keil_v5\UV4\UV4.exe" `
  -b "gpio_toggle_output_LP_MSPM0G3507_nortos_keil.uvprojx" `
  -j0 `
  -o "build_log.txt"
```

SysConfig 重新生成后要检查：

```text
DL_GPIO_RESISTOR_PULL_UP
```

必须准确出现 2 次，对应 PA26、PA27。

用户已经能自行通过 J-Link 烧录。除非用户明确要求，不要假设烧录已经完成；
改固件后应先给出新的 HEX、构建日志和固件 ID，再由用户烧录。

## 12. 作者源码、链接和版本关系

这里必须区分四套东西，不能统称为“作者同一版本”。

### 12.1 DrawBot 作者参考源码：本地 ZIP

本地目录：

`C:\Users\zjl\Downloads\DrawBot-ramps-main\DrawBot-ramps-main`

核心文件：

- `grbl-scara-ramps\scara.c`
- `grbl-scara-ramps\scara.h`
- `grbl-scara-ramps\defaults_scara.h`
- `grbl-scara-ramps\grbl.h`

这套源码面向：

- AVR Mega2560
- RAMPS 1.4
- GRBL 0.9j
- GRBL build `20160317`
- 默认 L1/L2 = 200/200 mm
- 默认步进参数 48.8
- 默认 theta/psi = 45.43°/95.67°
- SCARA offset = X -135 mm、Y +105 mm
- 舵机使用 `M3 Sx` / `M5`

它不是 MSPM0 工程，参数也不是当前实机的 205/203 mm 参数。

### 12.2 DrawBot 作者参考源码：在线 GitHub

仓库：

`https://github.com/akv47/DrawBot-ramps`

源码目录：

`https://github.com/akv47/DrawBot-ramps/tree/main/grbl-scara-ramps`

SCARA 核心：

`https://github.com/akv47/DrawBot-ramps/blob/main/grbl-scara-ramps/scara.c`

2026-07-24 核对结果：

- 默认分支：`main`
- `main` 最新提交：
  `98c9330fd86aed19e9bac0cea9abe44431fd08b3`
- 提交时间：2021-03-10
- 在线仓库没有正式 Release。
- 已对本地 ZIP 的 45 个文件和在线该提交的 45 个 blob 做 Git blob
  哈希全量比对：`0 mismatch`。

因此可以确认：

> 当前电脑中的 `DrawBot-ramps-main` 本地 ZIP 与在线 GitHub
> `98c9330fd86aed19e9bac0cea9abe44431fd08b3` 的文件树相同。

旧交接文档中“本地 ZIP commit 未知、可能与在线 main 不同”的说法已经被这次
全量哈希核对更新。

但是这只证明“本地源码 ZIP = 在线 GitHub 这个提交”，不证明它与下面的
中文 HEX、上位机软件或机械模型是同一发行版本。

### 12.3 Thingiverse 机械项目

链接：

`https://www.thingiverse.com/thing:3096135`

GitHub README 把它列为主要机械项目。它主要描述机械结构，不是一个可与
GitHub commit 一一对应的固件版本。

### 12.4 作者/项目视频

链接：

`https://www.youtube.com/watch?v=nXxYWECz4rc`

视频展示版本不能自动等同于当前 GitHub `main`、中文 HEX 或 MSPM0 移植。

### 12.5 MakerWorld 参考页面

链接：

`https://makerworld.com/zh/models/712239-a-writing-robot-arm-the-drawbot?from=search#profileId-1268105`

这是机械结构参考页面，不是当前固件源码版本。

### 12.6 中文完整资料包

本地目录：

`C:\Users\zjl\Downloads\25.11.11drawbot完整资料包`

主要内容：

- `drawbot1.2.0.2.hex`
- `机械臂大师1.1.0.1.exe`
- `机械臂大师1.2.1.msi`
- `机械臂大师修复版`
- XLoader / avrdude
- CH340 驱动
- 奎享雕刻 G-code 生成软件和教程
- LaserGRBL 中文版
- 照片和视频

版本结论：

> `drawbot1.2.0.2.hex` 是没有对应构建信息的 AVR 二进制。
> 目前没有源码、map、编译日志或哈希清单能证明它由 GitHub
> `98c9330...` 编译，因此必须把中文资料包视为独立发行内容。

这就是“源码和资料包版本不能混为一谈”的准确含义。

### 12.7 当前 MSPM0 移植

当前工程：

`C:\Users\zjl\Desktop\zjl\TI\writer_robot`

当前 V25 是参考作者 SCARA 思路后，为 MSPM0G3507、当前电机、当前限位、
205/203 mm 连杆和固定 A4 纸位置重新实现的独立移植。

它不等同于：

1. AVR GitHub 源码版本；
2. 中文 `drawbot1.2.0.2.hex`；
3. 机械臂大师软件版本；
4. Thingiverse/MakerWorld 机械模型版本；
5. 视频中展示的版本。

## 13. 汉字和字体资源

Hanzi Writer 数据仓库：

`https://github.com/chanind/hanzi-writer-data`

本地固定资源：

`C:\Users\zjl\Desktop\zjl\TI\writer_robot\assets\hanzi_writer_data_68d10a4`

固定提交：

`68d10a4b21150cae5e1ebbd223eed289cf32d90c`

当前本地只保存了“张、佳、乐”等需要的数据。它不是 DrawBot 作者固件的一部分。

更重要的是：Hanzi Writer 的 `medians` 不应直接当成最终单线中文字库。
V26 “永”已经证明，数据格式可转换成 G-code，不代表写出来的单线字形正确。

中文资料包内的奎享 `.gfont` 可能更接近实际雕刻/单线字体资源，但在成为
正式生成链路前，必须先完成下一步八方向轨迹标定，避免把机械误差误认为
字体误差。

## 14. 新对话必须遵守的约束

1. 不要恢复 V44、M801/M802 或 3×3 固定布局作为主线。
2. 不要移动纸、夹板、机械臂底座或连杆。
3. 不要只为一个字符写专用固件补偿。
4. 不要把 Hanzi Writer `medians` 当成已经验证的单线字体。
5. 不要在没有正反向轨迹数据时恢复旧预加载/方向补偿。
6. 不要连续粘贴 G-code；必须逐行等待 `ok`。
7. 任意 `error:` 后复位并重新自动回零。
8. 不要清理、reset 或 checkout 当前仓库；工作树有大量历史修改和未跟踪
   产物，全部都可能是用户数据。
9. 修改固件后必须重新构建、检查 0 error/0 warning、检查两个限位上拉，
   并使用新的唯一固件 ID 和 HEX 名称。
10. 当前第一任务是轨迹体检，不是直接批量写字。

## 15. 下一位助手接手后的第一项具体工作

在不修改 V25 固件和公共映射的前提下：

1. 选择当前安全区的下、中、上三个中心位置。
2. 生成一个标准 G-code 文件。
3. 每个位置画水平、竖直、`/`、`\` 四种方向，各做正反向，共 8 条。
4. 每条 20 mm、`F180`、独立抬落笔，避免线段相互连接。
5. 写静态检查脚本，检查边界、笔状态、命令顺序、三组轨迹完全同构。
6. 先给用户轨迹示意图和 G-code 路径。
7. 用户发送后只需拍一张能看见 A4 四角的正上方照片。
8. 基于照片做 A4 单应性校正和自动测量，再决定是修字体、纸面映射、
   方向回差还是笔架机械问题。

