# 马善政字体生成 G-code

项目已经固定官方 `MaShanZheng-Regular.ttf`，并提供适配当前
`PAPER_A4_CONTINUOUS_QUEUE_SAFE_HOME_YSHIFT15_GCODE_V28` 固件的生成器。

## 生成

先生成轮廓版做小范围测试：

```powershell
python .\tools\generate_ma_shan_zheng_gcode.py `
  --text "张佳乐作品" `
  --mode outline
```

生成更接近网页实心毛笔字的填充版：

```powershell
python .\tools\generate_ma_shan_zheng_gcode.py `
  --text "张佳乐作品" `
  --mode hatch `
  --hatch-spacing-mm 0.45
```

默认参数为：可见字高 9 mm、逻辑左边界 30 mm、逻辑顶边 220 mm、
F150、曲线离散步长不超过 0.40 mm。V28 固件还会应用全局
`Y +15 mm`，所以默认文字的实际纸面顶边约为 235 mm。生成器会检查
当前保留书写区和两关节角度余量，检查失败时不会输出新文件。

常用可调参数：

- `--height-mm 12`：改变字高；
- `--left-mm 30 --top-mm 220`：改变逻辑纸面位置；
- `--maximum-width-mm 150`：限制整段文字最大宽度；
- `--feed-mm-min 150`：改变落笔速度；
- `--output <path>`、`--preview <path>`、`--manifest <path>`：指定输出。

## 两种模式的差别

TTF 字体只包含封闭轮廓，没有真实毛笔笔顺，因此不能直接得到和
`.gfont` 一样的单线笔画：

- `outline` 描轮廓，建议先用它确认方向、位置和大小；
- `hatch` 用密集横线填充，最接近网页效果，但会频繁抬落笔；
- 若只做自动骨架化，可以得到单线近似，但笔顺和字形都无法与原字体
  完全一致，本工具没有把这种近似结果当作默认输出。

上机前必须确认烧录的是 V28，先核对预览和 JSON 清单，再用项目现有的
逐行等待 `ok` 发送方式运行。不要把这些文件发送给 V27 或更旧固件。
