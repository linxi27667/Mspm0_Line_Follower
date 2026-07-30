# 图片 / SVG 转写字机 G-code

`draw_to_gcode.py` 是独立的电脑端转换器。它只读取图片并生成文件，不打开
串口、不自动发送、不修改或编译写字机固件。

图形界面 EXE 的源码入口是 `draw_to_gcode_gui.py`，构建脚本是
`build_draw_to_gcode_exe.ps1`。GUI 固定使用当前 V33/V8 机械配置，默认不开放
Y<130 mm 的未验证区域。

重新构建 EXE：

```powershell
python -m pip install -r tools\draw_to_gcode_build_requirements.txt
powershell -ExecutionPolicy Bypass -File tools\build_draw_to_gcode_exe.ps1
```

## 支持范围

- PNG、JPG、BMP、TIFF、WEBP：`outline`、`edge`、`hatch`。
- SVG：`outline`。曲线会在电脑端展开成 `G1` 折线。
- 输出：标准 A4 纸面毫米坐标 G-code、同源矢量 SVG、PNG 预览和 JSON 安全清单。
- 默认只允许当前实物已验证的上部区域：X=25..185 mm、Y=130..235 mm。

SVG 需要轻量解析库：

```powershell
python -m pip install -r tools\draw_to_gcode_requirements.txt
```

OpenCV、NumPy 和 Pillow 沿用项目现有 Python 环境。

## 基本使用

黑白线稿或 Logo：

```powershell
python tools\draw_to_gcode.py C:\path\picture.png --mode outline
```

照片边缘：

```powershell
python tools\draw_to_gcode.py C:\path\photo.jpg --mode edge --blur-px 3 --canny-low 70 --canny-high 170
```

黑色填充区域排线：

```powershell
python tools\draw_to_gcode.py C:\path\logo.png --mode hatch --hatch-spacing-mm 1.2
```

SVG 线稿：

```powershell
python tools\draw_to_gcode.py C:\path\drawing.svg --mode outline --rotate-deg 90
```

默认排版框为左下角 `(30,135)`、宽 150 mm、高 95 mm。可以明确指定：

```powershell
python tools\draw_to_gcode.py C:\path\picture.png `
  --left-mm 40 --bottom-mm 150 --width-mm 120 --height-mm 70 `
  --output gcode\MY_DRAWING.gcode
```

## 输出检查

每次会产生：

- `.gcode`：只使用当前固件支持的标准指令和纸面坐标。
- `.vector.svg`：与 G-code 同源的 A4 纸面矢量路径，可继续编辑或打印。
- `.preview.png`：黑色为落笔轨迹，灰色为抬笔移动，橙色为落笔前预走。
- `.json`：输入哈希、边界、路径数量、长度、最低关节余量和时间下限。

预览确认无误后，先检查机器状态，不要跳过 Build ID 和纸面映射检查：

```powershell
powershell -ExecutionPolicy Bypass -File tools\send_standard_gcode_wait_ok.ps1 `
  -FilePath gcode\MY_DRAWING.gcode -PreflightOnly
```

转换器不会替用户执行发送动作。

## 重要参数

- `--threshold auto|0..255`：黑白分割阈值，默认 Otsu 自动阈值。
- `--invert`：把亮区域当作前景。
- `--simplify-mm`：轨迹简化公差，默认 0.15 mm。
- `--min-path-mm`：删除短噪声轨迹，默认 0.8 mm。
- `--approach-mm`：落笔前沿首段切向抬笔预走，默认最多 5 mm。
- `--max-paths`：默认最多 2000 条，防止照片噪声造成数十分钟舵机等待。
- `--allow-unverified-area`：明确允许 Y<130 mm；默认禁止。
- `--force`：明确覆盖已存在的输出；默认拒绝覆盖。

当前舵机每条独立路径包含一次落笔和一次抬笔，固定等待约 1.4 秒。复杂图片应
优先提高去噪、简化或排线间距，而不是盲目调高 `--max-paths`。

## 测试

```powershell
python tools\test_draw_to_gcode.py
```
