# 标准 G-code 右半区竖线补偿：V30 / V64

日期：2026-07-25

## 修改目的

V29 将右侧竖线测得的 S 形 X 误差无条件应用到了整个纸面，因此左侧原本正常的
竖线也会被预弯。V30 保留标准纸面坐标输入和原有基础映射，但把竖线 S 形补偿限制
到纸张右半区。

## V30 固件

- ID：`PAPER_A4_STANDARD_GCODE_RIGHT_SBOW_PAPERMAP_YSHIFT15_V30`
- 映射 ID：`A4_BASE_QUADRATIC_RIGHT_SBOW_PCHIP_CAL_V7`
- 左半区 `X <= 105 mm`：竖线 S 形补偿权重为 0
- 右半区 `105 < X < 185 mm`：使用 smoothstep 平滑增加权重
- 最右侧 `X = 185 mm`：使用完整竖线 S 形补偿
- 横线 Y 误差补偿：保持 V29 不变
- 全局 X 比例和 `Y +15 mm`：保持不变
- 旧 4×7 残差表：继续禁用

竖线补偿权重：

| 标准纸面 X / mm | 25 | 65 | 105 | 125 | 145 | 165 | 185 |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 权重 | 0 | 0 | 0 | 0.15625 | 0.5 | 0.84375 | 1 |

HEX：

`keil/PAPER_A4_STANDARD_GCODE_RIGHT_SBOW_PAPERMAP_YSHIFT15_V30.hex`

SHA-256：

`0BD63C3FE9CC893D5CFFF64DA469B26621D40A857423AD9A62037EDD54154B43`

Keil 构建结果：`0 Error(s), 0 Warning(s)`。

烧录后 `STATUS` 必须包含：

```text
id=PAPER_A4_STANDARD_GCODE_RIGHT_SBOW_PAPERMAP_YSHIFT15_V30
paper_map=A4_BASE_QUADRATIC_RIGHT_SBOW_PCHIP_CAL_V7
grid4x7=0
sbow=1
vsbow_right=1
map_enable=1
```

## V64 标准大回环

文件：

`gcode/PAPER_A4_STANDARD_FULL_WIDTH_160MM_SQUARE_SPIRAL_F300_RIGHT_SBOW_GCODE_V64.gcode`

该文件仍然只有标准 A4 纸面毫米坐标，没有离线映射或离线预弯。图形尺寸和 V63
完全相同，用于直接比较左侧竖线是否恢复。

G-code SHA-256：

`AF61124BFFEB665D68B2A20B93C6312515E32109513767046DA94778495FDC00`

离线检查结果：

```text
firmware_right_sbow_v30=PASS
left_half_vertical_sbow=OFF
right_edge_vertical_sbow=FULL
safe_samples=2026
min_joint_margin=5.728524deg
```
