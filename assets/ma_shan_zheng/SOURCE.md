# Ma Shan Zheng（马善政毛笔楷书）

- 字体文件：`MaShanZheng-Regular.ttf`
- 字体家族：`Ma Shan Zheng`
- 上游：[Google Fonts / Ma Shan Zheng](https://github.com/google/fonts/tree/main/ofl/mashanzheng)
- SHA-256：`6D2546BB189C732A8CA29AF9E22457B152387D158AA459E4AC2CE1E51788B7FB`
- 许可证：SIL Open Font License 1.1，完整文本见 `OFL.txt`
- Google Fonts 页面：<https://fonts.google.com/specimen/Ma+Shan+Zheng>

该 TTF 保存的是有粗细变化的封闭字形轮廓，并不保存真实毛笔书写的
笔画中心线或笔顺。项目工具 `tools/generate_ma_shan_zheng_gcode.py`
提供两种转换：

- `outline`：描字形边界，运动量较小，但写出来是空心轮廓；
- `hatch`：用水平排线填充字形，外观更接近网页上的实心毛笔字，
  但落笔次数、G-code 行数和耗时都会明显增加。

字体、许可证和 Google Fonts 元数据均于 2026-07-25 从 Google Fonts
官方仓库下载。
