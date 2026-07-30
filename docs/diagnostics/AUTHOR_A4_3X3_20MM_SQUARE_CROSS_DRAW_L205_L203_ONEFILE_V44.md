# V44 A4 九宫格 20 mm 方框十字一键落笔校准

日期：2026-07-22

## 2026-07-23 当前实机摆放照片

当前最新摆放照片：

```text
docs/diagnostics/CURRENT_AUTHOR_LIKE_A4_PLACEMENT_ACTUAL_20260723.jpg
SHA-256:
3FB55DD03F2FDF1F5D76824312124651AE5384B206DBB9FBF8FA23E6195CA7D9
```

照片确认的机械摆放关系与作者方案相似：

1. 电机、主转轴和底座位于 A4 纸外，不再压住纸面；
2. 机械臂由纸张外侧伸入纸面，笔夹位于纸面上方；
3. A4 横向放置在垫板/夹板上，纸面和底座相互分开；
4. 这种顺序解决了旧摆放中“为了让笔尖对准十字，底座会压到 A4 纸”的结构冲突。

这里的“与作者类似”只表示实体布置顺序相似，不表示本项目的软件、坐标、臂长、零点或固件版本与作者完全相同。照片也不能单独证明整个纸面没有辅助四连杆死点或两连杆奇点，安全结论仍以 V43 的实机轨迹和后续校准结果为准。

如果这张照片是在移动底座、纸张或夹板之后拍摄的，则旧 ALIGN、V43 安全轮廓与 V44 九宫格的物理对应关系必须视为失效；需要重新回零、重新运行 ALIGN 并重新确认坐标后，才能运行 `M891`。如果只是拍照且底座、纸张和夹板都未移动，则可以继续沿用原对齐。

## 目的和前提

V43 已由用户实机完成裁角安全轮廓整圈抬笔验证，没有进入辅助四连杆死点、两连杆奇点或发生小臂反向。
V44 在同一底座位置、同一纸位和同一坐标合同下，第一次把整片安全区域划成 9 个局部区域进行尺寸校准。

每个区域自动画：

1. 一个 `20 x 20 mm` 闭合正方形；
2. 一条 `20 mm` 中心水平线；
3. 一条 `20 mm` 中心竖直线。

每区共 3 次落笔，9 区共 27 次落笔。区域和笔画之间全部抬笔。本次不是文字书写，也没有开放普通 G-code。

如果纸张或底座在 V43 之后发生移动，当前 ALIGN 和全部纸面坐标立即失效，不得运行 V44，必须先重新对齐。

## 唯一运行文件

```text
gcode/V44_ONE_FILE/01_M891_RUN_ALL_9_ZONES_20MM_SQUARE_CROSS_V44.gcode
```

文件严格只有：

```text
G21
G90
G94
M5
M891
```

普通 G-code 仍禁用。固件不接受主机发送的 XYZ、F、M3、G0 或 G1。

## 纸面方向和九个区域

```text
A4：横放 297 x 210 mm
纸面原点：俯视照片中的纸张右下角
paper +X：照片向上
paper +Y：照片向左
ALIGN command：(150,20) mm
ALIGN paper：(14,58) mm
command = paper + (136,-38) mm
```

运行顺序采用蛇形路线，减少跨纸移动。左下和左上因 V43 裁角向纸内收；照片右下标记的最近两条纸边均为
`30 mm`。

| 顺序 | 照片上的大概位置 | 方框中心 paper mm | 方框覆盖 paper mm |
|---:|---|---:|---:|
| 1 | 照片右下 | (40,40) | X=30..50, Y=30..50 |
| 2 | 照片下边中间 | (40,105) | X=30..50, Y=95..115 |
| 3 | 照片左下，因裁角向纸内上移 | (80,170) | X=70..90, Y=160..180 |
| 4 | 照片左边中部 | (148.5,170) | X=138.5..158.5, Y=160..180 |
| 5 | 纸张正中心 | (148.5,105) | X=138.5..158.5, Y=95..115 |
| 6 | 照片右边中部 | (148.5,40) | X=138.5..158.5, Y=30..50 |
| 7 | 照片右上 | (270,40) | X=260..280, Y=30..50 |
| 8 | 照片上边中间 | (270,105) | X=260..280, Y=95..115 |
| 9 | 照片左上，因裁角向纸内收 | (260,165) | X=250..270, Y=155..175 |

## 固定机械和执行参数

```text
L1 / L2：                         205 / 203 mm
machine offset：                  (-129,+128) mm
Stage1 / Stage2：                 40.099216 / 40.115790 steps/degree
theta / psi limit：               -0.773082 / 134.177381 degrees
direction compensation：          disabled
independent preload：             disabled
author line execution：           disabled
Cartesian segment：               1 mm
pen-up move feed：                300 mm/min
pen-down draw feed：              240 mm/min
servo：                           0 degrees down, 90 degrees up
pen settle：                      500 ms
ALIGN pause：                     3000 ms
```

## 自动过程

发送一次 `M891` 后，固件自动：

1. 抬笔移动到 ALIGN 十字并停留约 3 秒；
2. 经过 V40/V41/V43 已验证入口、文字中心和纸面中心；
3. 按 1 到 9 的顺序画九个方框十字；
4. 抬笔返回纸面中心、已验证中心和 ALIGN；
5. 进入 `DONE`，必须重新回零才能再次运行。

预计运行约 `9.43 分钟`。运行期间 `STATUS` 和 `STOP` 可用；其他串口输入会急停并要求重新回零。

## 离线验证

```text
path points：                       88
pen-up targets：                    34
pen-down targets：                  54
zones / strokes：                   9 / 27
path CRC32：                        058FBC5C
total draw length：                 1080.000 mm
draw paper bounds：                 X=30..280, Y=30..180 mm
home release cases：                64
Cartesian 1 mm segments：           2359
master pulses：                     28946..28955
minimum post-ALIGN joint margin：   17.555488 degrees
maximum DDA line deviation：        0.118727 mm
maximum endpoint error：            0.080030 mm
maximum internal target span：      140.239973 mm
pulse samples：                     27634
minimum abs(sin(beta))：            0.585766427
maximum Jacobian condition：        3.090971
estimated runtime：                 9.43 minutes
```

模型没有进入两连杆 IK/径向/雅可比奇点。辅助四连杆仍不在数学模型中，因此继续使用实机经验保护
`command X >= 150 mm`。V44 新的纸内校准点最低 `command X=166 mm`，ALIGN 最低为 `150 mm`。

验证命令：

```text
python tools/check_author_a4_3x3_calibration_onefile_v44.py
```

最终结果：

`offline_author_a4_3x3_calibration_onefile_v44=PASS motion=NONE`

## 固件

```text
Build ID：
AUTHOR_A4_3X3_20MM_SQUARE_CROSS_DRAW_L205_L203_ONEFILE_V44

HEX：
keil/AUTHOR_A4_3X3_20MM_SQUARE_CROSS_DRAW_L205_L203_ONEFILE_V44.hex

HEX SHA-256：
EA9CCB7BAF88D6332B10C1D07B4DD8B25AD15B4A2966B7E1A1989D84A48E25EF

Keil project：
keil/gpio_toggle_output_LP_MSPM0G3507_nortos_keil.uvprojx

Compiler/linker：
0 Error(s), 0 Warning(s)

完整备份：
backups/AUTHOR_A4_3X3_20MM_SQUARE_CROSS_DRAW_L205_L203_ONEFILE_V44_20260722.zip

备份 SHA-256：
844B7FA849483589D44CEA765C4C0746F37121F3F3239BE4AACADBFFF58E2E43
```

Keil 的 SysConfig 前置命令仍显示项目已有的 PA8 选项诊断，之后编译、链接和 HEX 生成成功；本次没有改变引脚。

## 首次实机顺序

1. 确认底座和 A4 从 V43 后没有移动，纸张四角固定，笔尖抬起。
2. 清除纸面上方的尺子、显示器支架、线缆和其他障碍物。
3. 烧录命名 V44 HEX，复位并等待完整回零。
4. 发送 `STATUS`，必须看到正确 Build ID、`state=WAIT_ALIGN action=M891`、`lim1=0 lim2=0 pen=UP`。
5. 只运行唯一 V44 G-code 一次。
6. 笔尖到 ALIGN 后会停约 3 秒。若没有对准原十字，立即发送 `STOP`，不得继续。
7. 全程留在机器旁观察约 10 分钟，不要再发送其他文件。
8. 正常结束应看到：

```text
completed=CALIBRATION run=1/1 state=DONE action=NONE pen=UP rehome=1
```

出现辅助杆接近重合、小臂反向、卡顿、异响、限位、纸张移动、线缆拉扯或碰撞趋势，立即发送 `STOP` 或断电。
停止后必须重新回零。不得运行 V39 `M817..M824`、`2.0.gcode` 或 `GCODE_SERIAL`。

## 实测后需要记录

每个编号分别测量：

```text
上边 / 下边长度
左边 / 右边长度
两条对角线
方框起终点闭合差
中心横线长度
中心竖线长度
横竖线是否垂直
是否出现弯曲、重影、缺口或方向突变
```

还需要一张垂直俯拍全纸照片和有明显误差区域的近照。根据九区实测结果再决定局部比例/正交修正，不能提前把
旧中心区域的 `Y x 1.095` 推广到整张纸。
