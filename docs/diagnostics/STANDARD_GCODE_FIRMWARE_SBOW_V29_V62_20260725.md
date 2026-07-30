# 标准 G-code 固件内 S 形补偿：V29 / V62

日期：2026-07-25

## 坐标契约

V29 开始恢复真正的标准纸面坐标输入。上位机发送的 `G0/G1 X/Y`
就是名义 A4 纸面毫米坐标，不再离线写入基础映射或预弯坐标。

固件执行顺序：

1. 接收标准纸面坐标；
2. 应用 V60 实测 S 形反向预弯和 X 比例修正；
3. 转入旧基础二次映射的坐标约定；
4. 执行基础二次纸面到用户坐标映射；
5. 应用统一的用户坐标 `Y +15 mm`；
6. 进入两关节逆解和连续运动队列。

正式补偿不依赖特殊 G-code 点列。每条标准 `G1` 由固件按最大 1 mm
纸面步长自动细分。

## V29 固件

- ID：`PAPER_A4_STANDARD_GCODE_SBOW_PAPERMAP_YSHIFT15_V29`
- 纸面映射：启用
- S 形补偿：启用
- 旧 4×7 残差：禁用
- 基础二次映射：保留
- 全局 Y 平移：`+15 mm`
- Keil：`0 Error(s), 0 Warning(s)`
- HEX：
  `keil/PAPER_A4_STANDARD_GCODE_SBOW_PAPERMAP_YSHIFT15_V29.hex`
- HEX SHA-256：
  `5C9CC85D1004C846FD6813BC4326F58869FE890660410EC17ED4B6D7F3B98054`

`Jlink.jflash` 已指向 V29 HEX。

烧录后 `STATUS` 必须包含：

```text
id=PAPER_A4_STANDARD_GCODE_SBOW_PAPERMAP_YSHIFT15_V29
paper_map=A4_BASE_QUADRATIC_SBOW_PCHIP_CAL_V6
grid4x7=0
sbow=1
map_enable=1
shift_y100=1500
```

## 实测补偿节点

竖线从物理纸面 `Y=235` 向下：

| 向下距离 / mm | 0 | 7 | 55 | 125 | 160 |
|---:|---:|---:|---:|---:|---:|
| X 误差 / mm | 0 | 0 | -2 | 0 | +4 |

横线从物理纸面 `X=25` 向右：

| 向右距离 / mm | 0 | 40 | 92.5 | 160 |
|---:|---:|---:|---:|---:|
| Y 误差 / mm | 0 | -2 | 0 | +4 |

节点之间使用 PCHIP 平滑插值。X 比例按实测 `165/160=1.03125`
反向修正。

## V62 标准验证 G-code

- 文件：
  `gcode/PAPER_A4_STANDARD_XY_LINES_F300_FIRMWARE_SBOW_GCODE_V62.gcode`
- G0：4
- G1：4
- 上位机离线映射：无
- 上位机离线预弯：无
- SHA-256：
  `331F1CD360EA364D93DC3650A154C30FF38223AE98616D74599814D95E60B5CF`

V61 只用于确认数学补偿方向；V29 烧录后不要再发送 V61。
