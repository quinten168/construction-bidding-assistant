import fs from "node:fs/promises";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const base = "/Users/wenyuzhong/Downloads/CSI ELP 2026-selected/csi-bid-intelligence-ci-model/ci_model/model_1_wenyu/04_evaluation/outputs";
const inputCsv = `${base}/shortlist_metrics_rule_logistic_20260621.csv`;
const outputDir = `${base}/codex_shortlist_metrics_20260621`;
const outputXlsx = `${outputDir}/model1_shortlist_metrics_rule_logistic_20260621.xlsx`;
const previewPng = `${outputDir}/metrics_preview.png`;
const definitionsPreviewPng = `${outputDir}/definitions_preview.png`;

const csvText = await fs.readFile(inputCsv, "utf8");
const workbook = await Workbook.fromCSV(csvText, { sheetName: "Metrics" });
const metrics = workbook.worksheets.getItem("Metrics");
const used = metrics.getUsedRange();

metrics.showGridLines = false;
metrics.freezePanes.freezeRows(1);
metrics.freezePanes.freezeColumns(6);

used.format.font = { name: "Aptos", size: 10, color: "#1F2937" };
used.format.rowHeight = 22;
metrics.getRange("A1:U1").format = {
  fill: "#D9F2E3",
  font: { name: "Aptos", size: 10, bold: true, color: "#111827" },
  borders: { bottom: { style: "medium", color: "#9CA3AF" } },
  verticalAlignment: "center",
  wrapText: false,
};
metrics.getRange("A1:U3").format.borders = {
  insideHorizontal: { style: "thin", color: "#D1D5DB" },
  bottom: { style: "thin", color: "#D1D5DB" },
};
metrics.getRange("H2:U3").format.numberFormat = "0.00%";
metrics.getRange("A2:A3").format.numberFormat = "0";
metrics.getRange("G2:G3").format.numberFormat = "#,##0";
metrics.getRange("A2:G3").format.horizontalAlignment = "left";
metrics.getRange("H2:U3").format.horizontalAlignment = "right";

metrics.getRange("A:A").format.columnWidth = 12;
metrics.getRange("B:B").format.columnWidth = 20;
metrics.getRange("C:C").format.columnWidth = 38;
metrics.getRange("D:D").format.columnWidth = 38;
metrics.getRange("E:E").format.columnWidth = 22;
metrics.getRange("F:F").format.columnWidth = 10;
metrics.getRange("G:G").format.columnWidth = 10;
metrics.getRange("H:U").format.columnWidth = 22;

const table = metrics.tables.add("A1:U3", true, "ShortlistMetricsTable");
table.style = "TableStyleMedium4";
table.showFilterButton = true;
table.showBandedRows = false;

const definitions = workbook.worksheets.add("Definitions");
definitions.showGridLines = false;
definitions.getRange("A1:C1").merge();
definitions.getRange("A1").values = [["Model 1 Shortlist Metrics — Definitions"]];
definitions.getRange("A1:C1").format = {
  fill: "#14532D",
  font: { name: "Aptos Display", size: 15, bold: true, color: "#FFFFFF" },
  rowHeight: 30,
  verticalAlignment: "center",
};
definitions.getRange("A3:C11").values = [
  ["Metric", "Definition", "Evaluation scope"],
  ["Precision@K", "Actual bidders captured in the global Top-K divided by K.", "All 243 test projects"],
  ["Recall@K", "Actual bidders captured in the global Top-K divided by all actual bidders for the project.", "All 243 test projects"],
  ["Priority Precision@K", "Captured priority bidders divided by priority candidates appearing inside the same global Top-K.", "Projects with at least one priority recommendation in Top-K"],
  ["Priority Recall@K", "Captured priority bidders divided by all actual priority bidders for the project.", "Projects with at least one actual priority bidder"],
  ["Discovery Precision@K", "Captured discovery bidders divided by discovery candidates appearing inside the same global Top-K.", "Projects with at least one discovery recommendation in Top-K"],
  ["Discovery Recall@K", "Captured discovery bidders divided by all actual discovery bidders for the project.", "Projects with at least one actual discovery bidder"],
  ["NDCG@K", "Binary-relevance discounted cumulative gain normalized by the ideal ordering of actual bidders.", "All 243 test projects"],
  ["Priority / Discovery", "Priority IDs come from reference/competitor_priority.csv; all other candidates are discovery.", "One shared global shortlist; tiers are not ranked separately"],
];
definitions.getRange("A3:C3").format = {
  fill: "#D9F2E3",
  font: { bold: true, color: "#111827" },
  borders: { bottom: { style: "medium", color: "#9CA3AF" } },
};
definitions.getRange("A4:C11").format = {
  font: { name: "Aptos", size: 10, color: "#1F2937" },
  borders: { insideHorizontal: { style: "thin", color: "#E5E7EB" } },
  verticalAlignment: "top",
  wrapText: true,
};
definitions.getRange("A13:C13").merge();
definitions.getRange("A13").values = [["Rule-based baseline"]];
definitions.getRange("A13:C13").format = {
  fill: "#E8F5EC",
  font: { bold: true, color: "#14532D" },
};
definitions.getRange("A14:C14").merge();
definitions.getRange("A14").values = [["rule_score = 3×same-county prior bids + 2×same-type prior bids + 1.5×same-family prior bids + 1×recent-12m bids + 0.5×prior wins − 0.25×years since last bid"]];
definitions.getRange("A14:C14").format = { wrapText: true, font: { name: "Aptos", size: 10, color: "#1F2937" }, rowHeight: 34 };
definitions.getRange("A16:C16").merge();
definitions.getRange("A16").values = [["Source artifacts"]];
definitions.getRange("A16:C16").format = {
  fill: "#E8F5EC",
  font: { bold: true, color: "#14532D" },
};
definitions.getRange("A17:C19").values = [
  ["Scores", "ranking_predictions.csv generated 2026-06-19", "Rule-based score and logistic regression only"],
  ["Actual bidders", "data/processed/bidder_results.csv from the same scoring snapshot", "Used for project-level recall denominators"],
  ["Candidate rule", "county_state_type_plus_state_recent_12m", "Test split only"],
];
definitions.getRange("A17:C19").format = {
  wrapText: true,
  borders: { insideHorizontal: { style: "thin", color: "#E5E7EB" } },
  verticalAlignment: "top",
};
definitions.getRange("A:A").format.columnWidth = 26;
definitions.getRange("B:B").format.columnWidth = 72;
definitions.getRange("C:C").format.columnWidth = 44;
definitions.freezePanes.freezeRows(3);

await fs.mkdir(outputDir, { recursive: true });
const preview = await workbook.render({ sheetName: "Metrics", range: "A1:U3", scale: 1.5, format: "png" });
await fs.writeFile(previewPng, new Uint8Array(await preview.arrayBuffer()));
const definitionsPreview = await workbook.render({ sheetName: "Definitions", range: "A1:C19", scale: 1.25, format: "png" });
await fs.writeFile(definitionsPreviewPng, new Uint8Array(await definitionsPreview.arrayBuffer()));
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputXlsx);

const inspect = await workbook.inspect({
  kind: "table",
  range: "Metrics!A1:U3",
  include: "values,formulas",
  tableMaxRows: 5,
  tableMaxCols: 24,
});
const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 50 },
  summary: "final formula error scan",
});
console.log(inspect.ndjson);
console.log(errors.ndjson);
console.log(outputXlsx);
