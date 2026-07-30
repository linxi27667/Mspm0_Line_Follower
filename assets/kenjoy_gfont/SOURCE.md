# 固定单线字体资源

## 陈手写

- 项目文件：`CHEN_HANDWRITING_cf5b1677.gfont`
- 字体内部名称：`陈手写`
- `.gfont` em：400
- 字符数：2576
- SHA-256：`1B1D959A1B75106C8F94D1D95A9930FDF7DD54BA445C6CED0B84E55368F9644B`
- 原始文件：
  `C:\Users\zjl\Downloads\25.11.11drawbot完整资料包\生成gcode\奎享雕刻软件（绿色版）（生成gcode）\奎享雕刻软件（绿色版）\gcodeFonts\cf5b1677-7521-4bd3-8752-28516db036b6_download.gfont`

这份文件来自用户本机保存的 DrawBot 中文资料包。这里只固定项目所需的原始二进制，
不改变字体内容，也不对资料包未提供的授权信息作额外推断。

首个正式样例选择它而不是 Hanzi Writer `medians`，原因是“张、佳、乐”分别具有
7、7、5 条明确单线路径，没有 TTF 自动骨架字体中大量接近零长度的伪笔画。

2026-07-24 更正：使用该字体生成的 V30 不能上机。V30 把 `.gfont` 的向下
Y 轴误当成纸面的向上 Y 轴，导致整个字形上下颠倒；此外“佳”只有 7 条路径，
字形观感也不适合作为本轮正式样例。

## aa郭敬明字体

- 项目文件：`AA_GUO_JINGMING_b7c9ccc1.gfont`
- 字体内部名称：`aa郭敬明字体`
- `.gfont` em：525
- 字符数：2576
- SHA-256：`D5D8E41EF24BF380FDAB57B4746795D691CC4E2DF878A394E4FA8C6D594C09F8`
- 原始文件：
  `C:\Users\zjl\Downloads\25.11.11drawbot完整资料包\生成gcode\奎享雕刻软件（绿色版）（生成gcode）\奎享雕刻软件（绿色版）\gcodeFonts\b7c9ccc1-bb61-4fe1-842a-c8269b0922fc.gfont`

V31 直接使用该文件中“张、佳、乐”的原始点、原始路径顺序和原始路径方向，
分别为 7、8、5 笔。只做统一缩放、平移和
`paper_y = baseline_y - source_y * scale` 坐标系转换，不重画或修改字形。

## 宋体

- 项目文件：`SONG_ec900461.gfont`
- 字体内部名称：`宋体`
- `.gfont` em：600
- 字符数：2598
- SHA-256：`A74332F3F53C77B02DE6637ED8AAF0D5010E61444B1216D3E291A6AEA1419C24`
- 原始文件：
  `C:\Users\zjl\Downloads\25.11.11drawbot完整资料包\生成gcode\奎享雕刻软件（绿色版）（生成gcode）\奎享雕刻软件（绿色版）\gcodeFonts\ec900461-6461-471a-9236-3309b1bd18b8_download.gfont`

V32 直接使用该文件中“张、佳、乐”的 15、9、13 条原始路径。该宋体资源把
部分字端装饰保存为单独微路径，32 mm 字高时其中 6 条约为 0.10～0.15 mm。
V32 为了保持字库原貌没有删除这些路径，并在清单和检查结果中明确记录。

## 没有如果

- 项目文件：`MEIYOU_RUGUO_e31cdaaa.gfont`
- 字体内部名称：`没有如果`
- `.gfont` em：600
- 字符数：2576
- SHA-256：`569C56EE629D29E1F1172D66F1FE8205E810801A6437FA8490006FE1CB3DD6D6`
- 原始文件：
  `C:\Users\zjl\Downloads\25.11.11drawbot完整资料包\生成gcode\奎享雕刻软件（绿色版）（生成gcode）\奎享雕刻软件（绿色版）\gcodeFonts\e31cdaaa-b96e-4faa-a599-08562252f36f_download.gfont`

V45 直接使用该文件中“张佳乐作品”的 7、8、4、7、9 条原始路径。选择它作为
9 mm 小字的第二种字体，是因为它比宋体更接近手写笔迹，同时比资料包内更潦草的
字体容易辨认；生成器只做统一缩放、排版、Y 轴方向转换和纸面映射，不修改字形。

## 吸口雾霾压压惊

- 项目文件：`XIKOU_WUMAI_YAYA_JING_1d6c6baa.gfont`
- 字体内部名称：`吸口雾霾压压惊`
- `.gfont` em：400
- 字符数：2358
- SHA-256：`9377ADD7793C0B7965E21E6B7660DD6E1B6A90EE455DA076E36FB8D483C14B3A`
- 原始文件：
  `C:\Users\zjl\Downloads\25.11.11drawbot完整资料包\生成gcode\奎享雕刻软件（绿色版）（生成gcode）\奎享雕刻软件（绿色版）\gcodeFonts\1d6c6baa-cf66-4edc-9e5b-049875c3c162_download.gfont`

V46 按用户在全字体对照中的选择，直接使用该文件中“张佳乐作品”的
10、10、7、5、12 条原始路径。生成器保持 9 mm 字高、第三行位置、F150 和
0.4 mm 纸面细分，与 V44 宋体小字作单变量字体对照。
