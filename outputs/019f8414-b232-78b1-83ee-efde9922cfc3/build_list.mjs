import fs from "node:fs/promises";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const outputDir = "C:/Users/zjl/Desktop/zjl/TI/writer_robot/outputs/019f8414-b232-78b1-83ee-efde9922cfc3";
const outputPath = `${outputDir}/主要元器件及器材清单.xlsx`;
const previewPath = `${outputDir}/主要元器件及器材清单_preview.png`;

const rows = [
  [1, "四旋翼飞行器", "最大轴距不超过450 mm"],
  [2, "电动小车", "外形尺寸：长度≤35 cm，宽度≤25 cm；不得采用履带和麦氏轮"],
  [3, "短距离无线通信模块", ""],
  [4, "无线图像传输模块", ""],
  [5, "漆包线", ""],
  [6, "小型电磁铁", ""],
  [7, "钢球", "直径约1 cm"],
  [8, "三相可变电阻器", "50 Ω/3 A"],
  [9, "摄像头", "可带处理器模块"],
  [10, "可编程逻辑器件及其下载板", ""],
  [11, "嵌入式开发系统板", ""],
  [12, "TI MSPM0系统板", "可含板载调试下载模块"],
  [13, "微处理器最小系统板", "可含板载调试下载模块"],
  [14, "DDS芯片或模块", ""],
  [15, "A/D、D/A转换器", ""],
  [16, "运算放大器、电压比较器、乘法器", ""],
  [17, "可变增益集成宽带放大器", ""],
  [18, "大功率器件", ""],
  [19, "滑线变阻器", "20 Ω/5 A"],
  [20, "单相自耦调压器", "容量≥300 VA"],
  [21, "单相隔离变压器", "容量≥200 VA"],
  [22, "小型电机及驱动器", ""],
  [23, "磁环/磁芯", ""],
  [24, "铁芯磁环", "外径80 mm，内径50 mm，高度25 mm"],
  [25, "镀锌薄铁片", "厚度约0.3 mm"],
  [26, "显示屏", "≥6寸"],
  [27, "7段数码管", ""],
  [28, "小型继电器", ""],
  [29, "发光二极管", ""],
  [30, "光电传感器", ""],
  [31, "角度传感器", ""],
  [32, "蜂鸣器", ""],
  [33, "4分PPR水管", "外径约20 mm，壁厚约3.4 mm"],
];

await fs.mkdir(outputDir, { recursive: true });
const workbook = Workbook.create();
const sheet = workbook.worksheets.add("器材清单");
sheet.showGridLines = false;

sheet.getRange("A1:C1").merge();
sheet.getRange("A1").values = [["主要元器件及器材清单"]];
sheet.getRange("A2:C2").merge();
sheet.getRange("A2").values = [["根据提供图片整理｜共33项"]];
sheet.getRange("A4:C4").values = [["序号", "元器件/器材名称", "规格及要求"]];
sheet.getRange("A5:C37").values = rows;

sheet.getRange("A1:C1").format = {
  fill: "#1F4E78",
  font: { name: "Microsoft YaHei", size: 18, bold: true, color: "#FFFFFF" },
  horizontalAlignment: "center",
  verticalAlignment: "center",
};
sheet.getRange("A1:C1").format.rowHeight = 36;

sheet.getRange("A2:C2").format = {
  fill: "#DCE6F1",
  font: { name: "Microsoft YaHei", size: 10, color: "#44546A" },
  horizontalAlignment: "center",
  verticalAlignment: "center",
};
sheet.getRange("A2:C2").format.rowHeight = 24;

sheet.getRange("A4:C4").format = {
  fill: "#5B9BD5",
  font: { name: "Microsoft YaHei", size: 11, bold: true, color: "#FFFFFF" },
  horizontalAlignment: "center",
  verticalAlignment: "center",
  borders: { preset: "outside", style: "medium", color: "#4472C4" },
};
sheet.getRange("A4:C4").format.rowHeight = 26;

sheet.getRange("A5:C37").format = {
  font: { name: "Microsoft YaHei", size: 10, color: "#222222" },
  verticalAlignment: "center",
  borders: {
    insideHorizontal: { style: "thin", color: "#D9E2F3" },
    bottom: { style: "thin", color: "#A6A6A6" },
    left: { style: "thin", color: "#A6A6A6" },
    right: { style: "thin", color: "#A6A6A6" },
  },
};
sheet.getRange("A5:A37").format.horizontalAlignment = "center";
sheet.getRange("B5:C37").format.horizontalAlignment = "left";
sheet.getRange("C5:C37").format.wrapText = true;
sheet.getRange("A5:C37").format.rowHeight = 22;

for (let row = 5; row <= 37; row += 2) {
  sheet.getRange(`A${row}:C${row}`).format.fill = "#F6F9FC";
}

sheet.getRange("A1:A37").format.columnWidth = 9;
sheet.getRange("B1:B37").format.columnWidth = 30;
sheet.getRange("C1:C37").format.columnWidth = 54;
sheet.freezePanes.freezeRows(4);

const table = sheet.tables.add("A4:C37", true, "ComponentsListTable");
table.showFilterButton = true;
table.showBandedRows = false;

const inspect = await workbook.inspect({
  kind: "table",
  range: "器材清单!A1:C37",
  include: "values,formulas",
  tableMaxRows: 40,
  tableMaxCols: 4,
  maxChars: 12000,
});
console.log("INSPECT\n" + inspect.ndjson);

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 100 },
  summary: "final formula error scan",
});
console.log("ERROR_SCAN\n" + errors.ndjson);

const preview = await workbook.render({
  sheetName: "器材清单",
  range: "A1:C37",
  scale: 1.5,
  format: "png",
});
await fs.writeFile(previewPath, new Uint8Array(await preview.arrayBuffer()));

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(`OUTPUT\n${outputPath}\nPREVIEW\n${previewPath}`);
