import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const outputDir = path.resolve(".");
const qaDir = path.join(outputDir, "qa");
await fs.mkdir(qaDir, { recursive: true });

const ticker = "NVDA";
const yahooHistoryUrl = `https://finance.yahoo.com/quote/${ticker}/history/`;
const yahooChartUrl = `https://query1.finance.yahoo.com/v8/finance/chart/${ticker}?range=1y&interval=1d&events=div%2Csplits&includeAdjustedClose=true`;

const response = await fetch(yahooChartUrl, {
  headers: {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/138 Safari/537.36",
    Accept: "application/json,text/plain,*/*",
  },
});
if (!response.ok) {
  throw new Error(`Yahoo Finance request failed: ${response.status} ${response.statusText}`);
}

const payload = await response.json();
if (payload?.chart?.error) {
  throw new Error(`Yahoo Finance response error: ${JSON.stringify(payload.chart.error)}`);
}
const result = payload?.chart?.result?.[0];
if (!result?.timestamp?.length) {
  throw new Error("Yahoo Finance returned no daily price observations.");
}

const quote = result.indicators?.quote?.[0];
const adjusted = result.indicators?.adjclose?.[0]?.adjclose;
if (!quote || !adjusted) {
  throw new Error("Yahoo Finance response did not include OHLCV and adjusted close fields.");
}

const isoDate = (value) => {
  const d = value instanceof Date ? value : new Date(value);
  return d.toISOString().slice(0, 10);
};

const rows = result.timestamp
  .map((ts, i) => ({
    date: new Date(ts * 1000),
    open: quote.open?.[i],
    high: quote.high?.[i],
    low: quote.low?.[i],
    close: quote.close?.[i],
    adjClose: adjusted?.[i],
    volume: quote.volume?.[i],
  }))
  .filter((row) =>
    [row.open, row.high, row.low, row.close, row.adjClose, row.volume].every(
      (value) => Number.isFinite(value),
    ),
  )
  .sort((a, b) => a.date - b.date);

if (rows.length < 200) {
  throw new Error(`Only ${rows.length} valid daily observations were returned; expected roughly one trading year.`);
}

const assumptions = {
  fast: 20,
  slow: 50,
  fee: 0.001,
  slippage: 0,
  initialCapital: 1,
  tradingDays: 252,
  riskFreeAnnual: 0,
};

const mean = (values) => values.reduce((sum, value) => sum + value, 0) / values.length;
const sampleStd = (values) => {
  if (values.length < 2) return 0;
  const avg = mean(values);
  return Math.sqrt(values.reduce((sum, value) => sum + (value - avg) ** 2, 0) / (values.length - 1));
};
const rollingAverage = (values, window, index) => {
  if (index + 1 < window) return null;
  let sum = 0;
  for (let i = index - window + 1; i <= index; i += 1) sum += values[i];
  return sum / window;
};

const prices = rows.map((row) => row.adjClose);
const dailyReturn = rows.map((_, i) => (i === 0 ? 0 : prices[i] / prices[i - 1] - 1));
const smaFast = prices.map((_, i) => rollingAverage(prices, assumptions.fast, i));
const smaSlow = prices.map((_, i) => rollingAverage(prices, assumptions.slow, i));
const signal = rows.map((_, i) =>
  smaFast[i] !== null && smaSlow[i] !== null && smaFast[i] > smaSlow[i] ? 1 : 0,
);
const position = rows.map((_, i) => (i === 0 ? 0 : signal[i - 1]));
const tradingCost = assumptions.fee + assumptions.slippage;
const strategyReturn = rows.map((_, i) => {
  if (i === 0) return 0;
  const turnover = position[i] !== position[i - 1] ? tradingCost : 0;
  return position[i] * dailyReturn[i] - turnover;
});
const strategyEquity = rows.map(() => 0);
strategyEquity[0] = assumptions.initialCapital;
for (let i = 1; i < rows.length; i += 1) {
  strategyEquity[i] = strategyEquity[i - 1] * (1 + strategyReturn[i]);
}

const buyHoldReturn = rows.map((_, i) => (i === 0 ? -tradingCost : dailyReturn[i]));
const buyHoldEquity = rows.map(() => 0);
buyHoldEquity[0] = assumptions.initialCapital * (1 + buyHoldReturn[0]);
for (let i = 1; i < rows.length; i += 1) {
  buyHoldEquity[i] = buyHoldEquity[i - 1] * (1 + buyHoldReturn[i]);
}

const runningPeak = (values) => {
  let peak = -Infinity;
  return values.map((value) => {
    peak = Math.max(peak, value);
    return peak;
  });
};
const strategyPeak = runningPeak(strategyEquity);
const buyHoldPeak = runningPeak(buyHoldEquity);
const strategyDrawdown = strategyEquity.map((value, i) => value / strategyPeak[i] - 1);
const buyHoldDrawdown = buyHoldEquity.map((value, i) => value / buyHoldPeak[i] - 1);
const entry = position.map((value, i) => (i > 0 && value === 1 && position[i - 1] === 0 ? 1 : 0));
const exit = position.map((value, i) => (i > 0 && value === 0 && position[i - 1] === 1 ? 1 : 0));

const periodDays = (rows.at(-1).date - rows[0].date) / 86_400_000;
const metrics = (returns, equity, drawdown, exposureValues, trades, winMask) => {
  const analysisReturns = returns.slice(1);
  const vol = sampleStd(analysisReturns) * Math.sqrt(assumptions.tradingDays);
  const activeReturns = analysisReturns.filter((_, i) => winMask[i + 1]);
  return {
    totalReturn: equity.at(-1) / assumptions.initialCapital - 1,
    cagr: (equity.at(-1) / assumptions.initialCapital) ** (365 / periodDays) - 1,
    volatility: vol,
    sharpe:
      vol === 0
        ? 0
        : (mean(analysisReturns) * assumptions.tradingDays - assumptions.riskFreeAnnual) / vol,
    maxDrawdown: Math.min(...drawdown),
    trades,
    exposure: mean(exposureValues),
    winRate:
      activeReturns.length === 0
        ? 0
        : activeReturns.filter((value) => value > 0).length / activeReturns.length,
  };
};

const expectedBuyHold = metrics(
  buyHoldReturn,
  buyHoldEquity,
  buyHoldDrawdown,
  rows.map(() => 1),
  1,
  rows.map((_, i) => i > 0),
);
const expectedStrategy = metrics(
  strategyReturn,
  strategyEquity,
  strategyDrawdown,
  position,
  entry.reduce((sum, value) => sum + value, 0),
  position.map((value) => value === 1),
);

const escapeCsv = (value) => {
  if (value === null || value === undefined) return "";
  const text = value instanceof Date ? isoDate(value) : String(value);
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
};
const toCsv = (headers, dataRows) =>
  `\uFEFF${[headers, ...dataRows].map((row) => row.map(escapeCsv).join(",")).join("\r\n")}\r\n`;

const rawCsvHeaders = ["Date", "Open", "High", "Low", "Close", "Adj Close", "Volume"];
const rawCsvRows = rows.map((row) => [
  row.date,
  row.open,
  row.high,
  row.low,
  row.close,
  row.adjClose,
  row.volume,
]);
await fs.writeFile(path.join(outputDir, "NVDA_1y_daily.csv"), toCsv(rawCsvHeaders, rawCsvRows), "utf8");

const backtestCsvHeaders = [
  ...rawCsvHeaders,
  "Daily Return",
  `SMA ${assumptions.fast}`,
  `SMA ${assumptions.slow}`,
  "Signal at Close",
  "Next-Day Position",
  "Strategy Net Return",
  "Strategy Equity",
  "Buy & Hold Net Return",
  "Buy & Hold Equity",
  "Strategy Drawdown",
  "Buy & Hold Drawdown",
  "Entry",
  "Exit",
];
const backtestCsvRows = rows.map((row, i) => [
  row.date,
  row.open,
  row.high,
  row.low,
  row.close,
  row.adjClose,
  row.volume,
  dailyReturn[i],
  smaFast[i],
  smaSlow[i],
  signal[i],
  position[i],
  strategyReturn[i],
  strategyEquity[i],
  buyHoldReturn[i],
  buyHoldEquity[i],
  strategyDrawdown[i],
  buyHoldDrawdown[i],
  entry[i],
  exit[i],
]);
await fs.writeFile(
  path.join(outputDir, "NVDA_1y_backtest.csv"),
  toCsv(backtestCsvHeaders, backtestCsvRows),
  "utf8",
);

const workbook = Workbook.create();
const summary = workbook.worksheets.add("Summary");
const assumptionsSheet = workbook.worksheets.add("Assumptions");
const data = workbook.worksheets.add("Data");
const checks = workbook.worksheets.add("Checks");
const sources = workbook.worksheets.add("Sources");
const chartData = workbook.worksheets.add("Chart Data");

const colors = {
  navy: "#0F172A",
  blue: "#2563EB",
  lightBlue: "#DBEAFE",
  lightGray: "#F1F5F9",
  gray: "#64748B",
  green: "#008000",
  lightGreen: "#DCFCE7",
  red: "#DC2626",
  lightRed: "#FEE2E2",
  yellow: "#FEF9C3",
  white: "#FFFFFF",
  black: "#000000",
  border: "#CBD5E1",
};

for (const sheet of [summary, assumptionsSheet, data, checks, sources, chartData]) {
  sheet.showGridLines = false;
}

// Assumptions sheet
assumptionsSheet.mergeCells("A1:D1");
assumptionsSheet.getRange("A1").values = [[" NVDA 백테스트 가정"]];
assumptionsSheet.getRange("A1:D1").format = {
  fill: colors.navy,
  font: { bold: true, color: colors.white, size: 16 },
  verticalAlignment: "center",
};
assumptionsSheet.getRange("A3:C14").values = [
  ["항목", "값", "설명"],
  ["티커", ticker, "NASDAQ 상장 NVIDIA 보통주"],
  ["단기 이동평균", assumptions.fast, "조정종가 기준 고정 거래일; 변경 시 보고서 재생성"],
  ["장기 이동평균", assumptions.slow, "조정종가 기준 고정 거래일; 변경 시 보고서 재생성"],
  ["편도 거래비용", assumptions.fee, "진입 또는 청산 때마다 차감"],
  ["슬리피지", assumptions.slippage, "예시에서는 0%"],
  ["초기자본", assumptions.initialCapital, "정규화 지수"],
  ["연간 거래일", assumptions.tradingDays, "연환산 기준"],
  ["무위험수익률", assumptions.riskFreeAnnual, "샤프지수 계산"],
  ["체결 규칙", "다음 거래일", "당일 종가 신호를 다음 거래일부터 적용"],
  ["가격 기준", "조정종가", "배당·분할 조정값"],
  ["현금 수익률", 0, "포지션이 없을 때 0%"],
];
assumptionsSheet.getRange("A3:C3").format = {
  fill: colors.blue,
  font: { bold: true, color: colors.white },
  horizontalAlignment: "center",
};
assumptionsSheet.getRange("B7:B11").format = {
  fill: colors.yellow,
  font: { color: "#0000FF" },
};
assumptionsSheet.getRange("B4:B6").format = {
  fill: colors.lightGray,
  font: { color: colors.black },
};
assumptionsSheet.getRange("B12:B14").format = {
  fill: colors.lightGray,
  font: { color: colors.black },
};
assumptionsSheet.getRange("B7:B8").format.numberFormat = "0.00%;[Red](0.00%);-";
assumptionsSheet.getRange("B9").format.numberFormat = "0.0000";
assumptionsSheet.getRange("B11").format.numberFormat = "0.00%;[Red](0.00%);-";
assumptionsSheet.getRange("B14").format.numberFormat = "0.00%;[Red](0.00%);-";
assumptionsSheet.getRange("A17:C19").values = [
  ["표시 규칙", "색상", "의미"],
  ["입력", "파란 글씨", "사용자가 바꿀 수 있는 가정"],
  ["연결", "초록 글씨", "다른 시트를 참조하는 수식"],
];
assumptionsSheet.getRange("A17:C17").format = {
  fill: colors.lightGray,
  font: { bold: true, color: colors.navy },
};
assumptionsSheet.getRange("B18").format = { font: { color: "#0000FF" } };
assumptionsSheet.getRange("B19").format = { font: { color: colors.green } };
assumptionsSheet.getRange("A3:C14").format.borders = {
  preset: "outside",
  style: "thin",
  color: colors.border,
};
assumptionsSheet.getRange("A1:D1").format.rowHeight = 28;
assumptionsSheet.getRange("A:A").format.columnWidth = 22;
assumptionsSheet.getRange("B:B").format.columnWidth = 18;
assumptionsSheet.getRange("C:C").format.columnWidth = 48;
assumptionsSheet.freezePanes.freezeRows(3);

// Data sheet
const dataHeaders = [
  "Date",
  "Open",
  "High",
  "Low",
  "Close",
  "Adj Close",
  "Volume",
  "Daily Return",
  "SMA Fast",
  "SMA Slow",
  "Signal at Close",
  "Position",
  "Strategy Net Return",
  "Strategy Equity",
  "Buy & Hold Net Return",
  "Buy & Hold Equity",
  "Strategy Peak",
  "Strategy Drawdown",
  "Buy & Hold Peak",
  "Buy & Hold Drawdown",
  "Entry",
  "Exit",
  "Signal Lag Check",
];
data.getRange("A1:W1").values = [dataHeaders];
data.getRange(`A2:G${rows.length + 1}`).values = rows.map((row) => [
  row.date,
  row.open,
  row.high,
  row.low,
  row.close,
  row.adjClose,
  row.volume,
]);

const lastRow = rows.length + 1;
const prevLastRow = lastRow - 1;
data.getRange("H2").values = [[0]];
data.getRange("H3").formulas = [["=F3/F2-1"]];
data.getRange(`H3:H${lastRow}`).fillDown();
const fastFirstFormulaRow = assumptions.fast + 1;
const slowFirstFormulaRow = assumptions.slow + 1;
data.getRange(`I2:I${fastFirstFormulaRow - 1}`).values = Array.from(
  { length: fastFirstFormulaRow - 2 },
  () => [null],
);
data.getRange(`I${fastFirstFormulaRow}`).formulas = [[`=AVERAGE(F2:F${fastFirstFormulaRow})`]];
data.getRange(`I${fastFirstFormulaRow}:I${lastRow}`).fillDown();
data.getRange(`J2:J${slowFirstFormulaRow - 1}`).values = Array.from(
  { length: slowFirstFormulaRow - 2 },
  () => [null],
);
data.getRange(`J${slowFirstFormulaRow}`).formulas = [[`=AVERAGE(F2:F${slowFirstFormulaRow})`]];
data.getRange(`J${slowFirstFormulaRow}:J${lastRow}`).fillDown();
data.getRange("K2").formulas = [["=IF(COUNT(I2:J2)=2,IF(I2>J2,1,0),0)"]];
data.getRange(`K2:K${lastRow}`).fillDown();
data.getRange("L2").values = [[0]];
data.getRange("L3").formulas = [["=K2"]];
data.getRange(`L3:L${lastRow}`).fillDown();
data.getRange("M2").values = [[0]];
data.getRange("M3").formulas = [["=L3*H3-IF(L3<>L2,'Assumptions'!$B$7+'Assumptions'!$B$8,0)"]];
data.getRange(`M3:M${lastRow}`).fillDown();
data.getRange("N2").formulas = [["='Assumptions'!$B$9"]];
data.getRange("N3").formulas = [["=N2*(1+M3)"]];
data.getRange(`N3:N${lastRow}`).fillDown();
data.getRange("O2").formulas = [["=-('Assumptions'!$B$7+'Assumptions'!$B$8)"]];
data.getRange("O3").formulas = [["=H3"]];
data.getRange(`O3:O${lastRow}`).fillDown();
data.getRange("P2").formulas = [["='Assumptions'!$B$9*(1+O2)"]];
data.getRange("P3").formulas = [["=P2*(1+O3)"]];
data.getRange(`P3:P${lastRow}`).fillDown();
data.getRange("Q2").formulas = [["=N2"]];
data.getRange("Q3").formulas = [["=MAX(Q2,N3)"]];
data.getRange(`Q3:Q${lastRow}`).fillDown();
data.getRange("R2").formulas = [["=N2/Q2-1"]];
data.getRange("R3").formulas = [["=N3/Q3-1"]];
data.getRange(`R3:R${lastRow}`).fillDown();
data.getRange("S2").formulas = [["=P2"]];
data.getRange("S3").formulas = [["=MAX(S2,P3)"]];
data.getRange(`S3:S${lastRow}`).fillDown();
data.getRange("T2").formulas = [["=P2/S2-1"]];
data.getRange("T3").formulas = [["=P3/S3-1"]];
data.getRange(`T3:T${lastRow}`).fillDown();
data.getRange("U2").values = [[0]];
data.getRange("U3").formulas = [["=IF(AND(L3=1,L2=0),1,0)"]];
data.getRange(`U3:U${lastRow}`).fillDown();
data.getRange("V2").values = [[0]];
data.getRange("V3").formulas = [["=IF(AND(L3=0,L2=1),1,0)"]];
data.getRange(`V3:V${lastRow}`).fillDown();
data.getRange("W2").values = [[0]];
data.getRange("W3").formulas = [["=IF(L3=K2,0,1)"]];
data.getRange(`W3:W${lastRow}`).fillDown();

data.getRange("A1:W1").format = {
  fill: colors.navy,
  font: { bold: true, color: colors.white },
  horizontalAlignment: "center",
  verticalAlignment: "center",
  wrapText: true,
};
data.getRange(`A2:A${lastRow}`).format.numberFormat = "yyyy-mm-dd";
data.getRange(`B2:F${lastRow}`).format.numberFormat = "$0.00;[Red]($0.00);-";
data.getRange(`G2:G${lastRow}`).format.numberFormat = "#,##0;[Red](#,##0);-";
data.getRange(`H2:H${lastRow}`).format.numberFormat = "0.00%;[Red](0.00%);-";
data.getRange(`I2:J${lastRow}`).format.numberFormat = "$0.00;[Red]($0.00);-";
data.getRange(`K2:L${lastRow}`).format.numberFormat = "0";
data.getRange(`M2:M${lastRow}`).format.numberFormat = "0.00%;[Red](0.00%);-";
data.getRange(`N2:N${lastRow}`).format.numberFormat = "0.0000";
data.getRange(`O2:O${lastRow}`).format.numberFormat = "0.00%;[Red](0.00%);-";
data.getRange(`P2:Q${lastRow}`).format.numberFormat = "0.0000";
data.getRange(`R2:R${lastRow}`).format.numberFormat = "0.00%;[Red](0.00%);-";
data.getRange(`S2:S${lastRow}`).format.numberFormat = "0.0000";
data.getRange(`T2:T${lastRow}`).format.numberFormat = "0.00%;[Red](0.00%);-";
data.getRange(`U2:V${lastRow}`).format.numberFormat = "0";
data.getRange(`W2:W${lastRow}`).format.numberFormat = "0";
data.getRange(`I2:J${lastRow}`).format.font = { color: colors.green };
data.getRange(`M2:P${lastRow}`).format.font = { color: colors.green };
data.getRange(`R2:T${lastRow}`).format.font = { color: colors.black };
data.getRange(`R2:R${lastRow}`).conditionalFormats.add("cellIs", {
  operator: "lessThan",
  formula: 0,
  format: { font: { color: colors.red }, fill: colors.lightRed },
});
data.getRange(`T2:T${lastRow}`).conditionalFormats.add("cellIs", {
  operator: "lessThan",
  formula: 0,
  format: { font: { color: colors.red }, fill: colors.lightRed },
});
const dataTable = data.tables.add(`A1:W${lastRow}`, true, "NvdaBacktestData");
dataTable.style = "TableStyleMedium2";
data.freezePanes.freezeRows(1);
data.freezePanes.freezeColumns(1);
data.getRange("A:A").format.columnWidth = 12;
data.getRange("B:F").format.columnWidth = 11;
data.getRange("G:G").format.columnWidth = 14;
data.getRange("H:J").format.columnWidth = 13;
data.getRange("K:L").format.columnWidth = 14;
data.getRange("M:P").format.columnWidth = 17;
data.getRange("Q:T").format.columnWidth = 18;
data.getRange("U:V").format.columnWidth = 9;
data.getRange("W:W").format.columnWidth = 16;
data.getRange("1:1").format.rowHeight = 34;

// Summary sheet
summary.mergeCells("A1:I1");
summary.getRange("A1").values = [["NVDA 최근 1년 백테스트"]];
summary.getRange("A1:I1").format = {
  fill: colors.navy,
  font: { bold: true, color: colors.white, size: 18 },
  verticalAlignment: "center",
};
summary.mergeCells("A2:I2");
summary.getRange("A2").values = [[
  "매수 후 보유 vs. SMA 20/50 · 조정종가 · 신호 다음 거래일 적용 · 편도 거래비용 0.10%",
]];
summary.getRange("A2:I2").format = {
  fill: colors.lightBlue,
  font: { color: colors.navy, italic: true },
  wrapText: true,
};
summary.getRange("A4:H4").values = [["티커", null, "시작일", null, "종료일", null, "거래일 수", null]];
summary.getRange("B4").formulas = [["='Assumptions'!$B$4"]];
summary.getRange("D4").formulas = [["='Data'!$A$2"]];
summary.getRange("F4").formulas = [[`='Data'!$A$${lastRow}`]];
summary.getRange("H4").formulas = [[`=COUNT('Data'!$A$2:$A$${lastRow})`]];
summary.getRange("A4:H4").format.borders = { preset: "outside", style: "thin", color: colors.border };
summary.getRange("A4:C4").format.fill = colors.lightGray;
summary.getRange("E4:G4").format.fill = colors.lightGray;
summary.getRange("A4:C4").format.font = { bold: true, color: colors.navy };
summary.getRange("E4:G4").format.font = { bold: true, color: colors.navy };
summary.getRange("B4").format.font = { color: colors.green };
summary.getRange("D4").format.font = { color: colors.green };
summary.getRange("F4").format.font = { color: colors.green };
summary.getRange("H4").format.font = { color: colors.green };
summary.getRange("D4").format.numberFormat = "yyyy-mm-dd";
summary.getRange("F4").format.numberFormat = "yyyy-mm-dd";
summary.getRange("A6:I6").values = [[
  "전략",
  "총수익률",
  "CAGR",
  "연환산 변동성",
  "샤프지수",
  "최대낙폭",
  "진입 횟수",
  "시장 노출",
  "승률",
]];
summary.getRange("A7:A8").values = [["매수 후 보유"], ["SMA 20/50"]];
summary.getRange("B7").formulas = [[`='Data'!$P$${lastRow}/'Assumptions'!$B$9-1`]];
summary.getRange("C7").formulas = [[
  `=('Data'!$P$${lastRow}/'Assumptions'!$B$9)^(365/('Data'!$A$${lastRow}-'Data'!$A$2))-1`,
]];
summary.getRange("D7").formulas = [[
  `=STDEV.S('Data'!$O$3:$O$${lastRow})*SQRT('Assumptions'!$B$10)`,
]];
summary.getRange("E7").formulas = [[
  `=(AVERAGE('Data'!$O$3:$O$${lastRow})*'Assumptions'!$B$10-'Assumptions'!$B$11)/D7`,
]];
summary.getRange("F7").formulas = [[`=MIN('Data'!$T$2:$T$${lastRow})`]];
summary.getRange("G7").values = [[1]];
summary.getRange("H7").values = [[1]];
summary.getRange("I7").formulas = [[
  `=COUNTIF('Data'!$O$3:$O$${lastRow},">0")/COUNT('Data'!$O$3:$O$${lastRow})`,
]];
summary.getRange("B8").formulas = [[`='Data'!$N$${lastRow}/'Assumptions'!$B$9-1`]];
summary.getRange("C8").formulas = [[
  `=('Data'!$N$${lastRow}/'Assumptions'!$B$9)^(365/('Data'!$A$${lastRow}-'Data'!$A$2))-1`,
]];
summary.getRange("D8").formulas = [[
  `=STDEV.S('Data'!$M$3:$M$${lastRow})*SQRT('Assumptions'!$B$10)`,
]];
summary.getRange("E8").formulas = [[
  `=(AVERAGE('Data'!$M$3:$M$${lastRow})*'Assumptions'!$B$10-'Assumptions'!$B$11)/D8`,
]];
summary.getRange("F8").formulas = [[`=MIN('Data'!$R$2:$R$${lastRow})`]];
summary.getRange("G8").formulas = [[`=SUM('Data'!$U$2:$U$${lastRow})`]];
summary.getRange("H8").formulas = [[`=AVERAGE('Data'!$L$2:$L$${lastRow})`]];
summary.getRange("I8").formulas = [[
  `=IFERROR(COUNTIFS('Data'!$L$3:$L$${lastRow},1,'Data'!$M$3:$M$${lastRow},">0")/COUNTIF('Data'!$L$3:$L$${lastRow},1),0)`,
]];
summary.getRange("A6:I6").format = {
  fill: colors.blue,
  font: { bold: true, color: colors.white },
  horizontalAlignment: "center",
  wrapText: true,
};
summary.getRange("A7:I8").format.borders = { preset: "outside", style: "thin", color: colors.border };
summary.getRange("A8:I8").format.fill = "#EFF6FF";
summary.getRange("B7:I8").format.font = { color: colors.green };
summary.getRange("B7:D8").format.numberFormat = "0.00%;[Red](0.00%);-";
summary.getRange("E7:E8").format.numberFormat = "0.00x;[Red](0.00x);-";
summary.getRange("F7:F8").format.numberFormat = "0.00%;[Red](0.00%);-";
summary.getRange("G7:G8").format.numberFormat = "0";
summary.getRange("H7:I8").format.numberFormat = "0.00%;[Red](0.00%);-";
summary.getRange("B7:C8").conditionalFormats.add("cellIs", {
  operator: "greaterThanOrEqual",
  formula: 0,
  format: { font: { color: "#166534", bold: true }, fill: colors.lightGreen },
});
summary.getRange("B7:C8").conditionalFormats.add("cellIs", {
  operator: "lessThan",
  formula: 0,
  format: { font: { color: colors.red, bold: true }, fill: colors.lightRed },
});
summary.mergeCells("A10:I10");
summary.getRange("A10").values = [[
  "주의: 과거 성과는 미래 수익을 보장하지 않습니다. 세금·환율·호가 스프레드는 제외했고, 마지막 보유 포지션의 청산 비용은 반영하지 않았습니다.",
]];
summary.getRange("A10:I10").format = {
  fill: colors.yellow,
  font: { color: colors.navy, italic: true },
  wrapText: true,
};

// Chart helper uses monthly endpoints to keep the x-axis readable.
const monthEndIndexes = [];
for (let i = 0; i < rows.length; i += 1) {
  const month = isoDate(rows[i].date).slice(0, 7);
  const nextMonth = i + 1 < rows.length ? isoDate(rows[i + 1].date).slice(0, 7) : null;
  if (month !== nextMonth) monthEndIndexes.push(i);
}
chartData.getRange("A1:C1").values = [["월", "매수 후 보유", "SMA 20/50"]];
chartData.getRange(`A2:A${monthEndIndexes.length + 1}`).values = monthEndIndexes.map((i) => [
  isoDate(rows[i].date).slice(0, 7),
]);
chartData.getRange(`B2:C${monthEndIndexes.length + 1}`).formulas = monthEndIndexes.map((i) => {
  const sourceRow = i + 2;
  return [[`='Data'!$P$${sourceRow}`, `='Data'!$N$${sourceRow}`][0], [`='Data'!$P$${sourceRow}`, `='Data'!$N$${sourceRow}`][1]];
});
chartData.getRange("A1:C1").format = {
  fill: colors.blue,
  font: { bold: true, color: colors.white },
};
chartData.getRange(`B2:C${monthEndIndexes.length + 1}`).format = {
  font: { color: colors.green },
  numberFormat: "0.0000",
};
chartData.getRange("A:A").format.columnWidth = 14;
chartData.getRange("B:C").format.columnWidth = 18;
chartData.freezePanes.freezeRows(1);

const chart = summary.charts.add("line", {
  chartType: "line",
  title: "$1 투자금의 누적 성장",
  hasLegend: true,
});
const buySeries = chart.series.add("매수 후 보유");
buySeries.categoryFormula = `'Chart Data'!$A$2:$A$${monthEndIndexes.length + 1}`;
buySeries.formula = `'Chart Data'!$B$2:$B$${monthEndIndexes.length + 1}`;
buySeries.fill = colors.gray;
const strategySeries = chart.series.add("SMA 20/50");
strategySeries.categoryFormula = `'Chart Data'!$A$2:$A$${monthEndIndexes.length + 1}`;
strategySeries.formula = `'Chart Data'!$C$2:$C$${monthEndIndexes.length + 1}`;
strategySeries.fill = colors.blue;
chart.title = "$1 투자금의 누적 성장";
chart.titleTextStyle.fontSize = 13;
chart.hasLegend = true;
chart.xAxis = { axisType: "textAxis", textStyle: { fontSize: 9 } };
const chartValues = [...buyHoldEquity, ...strategyEquity];
const chartMin = Math.max(0, Math.floor((Math.min(...chartValues) - 0.05) * 10) / 10);
const chartMax = Math.ceil((Math.max(...chartValues) + 0.05) * 10) / 10;
chart.yAxis = {
  numberFormatCode: "0.00x",
  textStyle: { fontSize: 9 },
  min: chartMin,
  max: chartMax,
};
chart.setPosition("A12", "I29");

summary.mergeCells("A31:I31");
summary.getRange("A31").values = [[
  `데이터: Yahoo Finance | 조회 시각 ${new Date().toISOString()} | 완료 거래일 ${isoDate(rows.at(-1).date)}`,
]];
summary.getRange("A31:I31").format = {
  font: { color: colors.gray, size: 9 },
  wrapText: true,
};
summary.getRange("A:A").format.columnWidth = 18;
summary.getRange("B:I").format.columnWidth = 15;
summary.getRange("1:1").format.rowHeight = 30;
summary.getRange("2:2").format.rowHeight = 28;
summary.getRange("6:6").format.rowHeight = 32;
summary.getRange("10:10").format.rowHeight = 34;
summary.freezePanes.freezeRows(2);

// Checks sheet
checks.mergeCells("A1:G1");
checks.getRange("A1").values = [[" 백테스트 검증"]];
checks.getRange("A1:G1").format = {
  fill: colors.navy,
  font: { bold: true, color: colors.white, size: 16 },
};
checks.getRange("A3:G3").values = [["검증 항목", "실제", "기대값", "차이", "허용오차", "상태", "메모"]];
checks.getRange("A4:A11").values = [
  ["매수 후 보유 총수익률"],
  ["SMA 총수익률"],
  ["매수 후 보유 최대낙폭"],
  ["SMA 최대낙폭"],
  ["거래일 수"],
  ["첫 날짜"],
  ["마지막 날짜"],
  ["신호 익일 적용 불일치"],
];
checks.getRange("B4:B11").formulas = [
  ["='Summary'!$B$7"],
  ["='Summary'!$B$8"],
  ["='Summary'!$F$7"],
  ["='Summary'!$F$8"],
  [`=COUNT('Data'!$A$2:$A$${lastRow})`],
  ["='Data'!$A$2"],
  [`='Data'!$A$${lastRow}`],
  [`=SUM('Data'!$W$3:$W$${lastRow})`],
];
checks.getRange("C4:C11").values = [
  [expectedBuyHold.totalReturn],
  [expectedStrategy.totalReturn],
  [expectedBuyHold.maxDrawdown],
  [expectedStrategy.maxDrawdown],
  [rows.length],
  [rows[0].date],
  [rows.at(-1).date],
  [0],
];
checks.getRange("D4").formulas = [["=B4-C4"]];
checks.getRange("D4:D11").fillDown();
checks.getRange("E4:E11").values = [[1e-6], [1e-6], [1e-6], [1e-6], [0], [0], [0], [0]];
checks.getRange("F4").formulas = [["=IF(ABS(D4)<=E4,\"OK\",\"FAIL\")"]];
checks.getRange("F4:F11").fillDown();
checks.getRange("G4:G11").values = [
  ["JS 독립 계산과 Excel 수식 비교"],
  ["JS 독립 계산과 Excel 수식 비교"],
  ["JS 독립 계산과 Excel 수식 비교"],
  ["JS 독립 계산과 Excel 수식 비교"],
  ["원천 데이터 행 수"],
  ["조회 구간 첫 거래일"],
  ["가장 최근 완료 거래일"],
  ["Position(t) = Signal(t-1) 확인"],
];
checks.getRange("A13:E13").merge();
checks.getRange("A13").values = [["전체 모델 상태"]];
checks.getRange("F13").formulas = [["=IF(COUNTIF(F4:F11,\"OK\")=8,\"OK\",\"FAIL\")"]];
checks.getRange("A3:G3").format = {
  fill: colors.blue,
  font: { bold: true, color: colors.white },
  horizontalAlignment: "center",
};
checks.getRange("A4:G11").format.borders = { preset: "outside", style: "thin", color: colors.border };
checks.getRange("B4:B11").format.font = { color: colors.green };
checks.getRange("B4:E7").format.numberFormat = "0.00000000";
checks.getRange("B9:C10").format.numberFormat = "yyyy-mm-dd";
checks.getRange("D9:E10").format.numberFormat = "0";
checks.getRange("F4:F13").conditionalFormats.add("containsText", {
  text: "OK",
  format: { font: { color: "#166534", bold: true }, fill: colors.lightGreen },
});
checks.getRange("F4:F13").conditionalFormats.add("containsText", {
  text: "FAIL",
  format: { font: { color: colors.red, bold: true }, fill: colors.lightRed },
});
checks.getRange("A13:F13").format = {
  fill: colors.lightGray,
  font: { bold: true, color: colors.navy },
  borders: { preset: "outside", style: "thin", color: colors.border },
};
checks.getRange("A:A").format.columnWidth = 28;
checks.getRange("B:F").format.columnWidth = 16;
checks.getRange("G:G").format.columnWidth = 40;
checks.getRange("1:1").format.rowHeight = 28;
checks.freezePanes.freezeRows(3);

// Sources sheet
sources.mergeCells("A1:F1");
sources.getRange("A1").values = [[" 출처 및 감사 기록"]];
sources.getRange("A1:F1").format = {
  fill: colors.navy,
  font: { bold: true, color: colors.white, size: 16 },
};
sources.getRange("A3:F3").values = [["항목", "티커", "기간/조회일", "출처", "URL", "메모"]];
sources.getRange("A4:F6").values = [
  [
    "일별 OHLCV 및 조정종가",
    ticker,
    `${isoDate(rows[0].date)} ~ ${isoDate(rows.at(-1).date)}`,
    "Yahoo Finance",
    yahooChartUrl,
    `${rows.length}개 완료 거래일. 통화 USD. 거래소 ${result.meta?.fullExchangeName ?? result.meta?.exchangeName ?? "NASDAQ"}`,
  ],
  [
    "사람이 확인 가능한 가격 이력 페이지",
    ticker,
    `UTC ${new Date().toISOString()}`,
    "Yahoo Finance",
    yahooHistoryUrl,
    "CSV 원천 데이터의 브라우저 확인용 링크",
  ],
  [
    "백테스트 방법론",
    ticker,
    `UTC ${new Date().toISOString()}`,
    "로컬 계산",
    "",
    "조정종가 SMA 교차, 종가 신호를 다음 거래일부터 적용, 편도 비용 0.10%",
  ],
];
sources.getRange("A3:F3").format = {
  fill: colors.blue,
  font: { bold: true, color: colors.white },
  horizontalAlignment: "center",
};
sources.getRange("A4:F6").format = {
  wrapText: true,
  verticalAlignment: "top",
  borders: { preset: "outside", style: "thin", color: colors.border },
};
sources.getRange("E4:E5").format.font = { color: colors.red };
sources.getRange("A:A").format.columnWidth = 30;
sources.getRange("B:B").format.columnWidth = 10;
sources.getRange("C:C").format.columnWidth = 28;
sources.getRange("D:D").format.columnWidth = 18;
sources.getRange("E:E").format.columnWidth = 58;
sources.getRange("F:F").format.columnWidth = 52;
sources.getRange("1:1").format.rowHeight = 28;
sources.getRange("4:6").format.rowHeight = 52;
sources.freezePanes.freezeRows(3);

workbook.comments.setSelf({ displayName: "김현수" });
workbook.comments.addThread(
  { cell: sources.getRange("E4") },
  `가격 데이터는 Yahoo Finance chart endpoint에서 ${new Date().toISOString()}에 조회했습니다.`,
);
workbook.comments.addThread(
  { cell: assumptionsSheet.getRange("B7") },
  "편도 거래비용 가정입니다. 진입과 청산 각각에 적용됩니다.",
);

const summaryInspect = await workbook.inspect({
  kind: "table",
  range: "Summary!A1:I10",
  include: "values,formulas",
  tableMaxRows: 12,
  tableMaxCols: 10,
});
const checksInspect = await workbook.inspect({
  kind: "table",
  range: "Checks!A3:G13",
  include: "values,formulas",
  tableMaxRows: 15,
  tableMaxCols: 8,
});
const errorInspect = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!",
  options: { useRegex: true, maxResults: 100 },
  summary: "final formula error scan",
});
const drawingInspect = await workbook.inspect({
  kind: "drawing",
  sheetId: "Summary",
  maxChars: 2000,
});

const renderTargets = [
  ["Summary", "A1:I31", "summary.png", 1.5],
  ["Assumptions", "A1:D19", "assumptions.png", 1.4],
  ["Data", "A1:W26", "data_sample.png", 1.0],
  ["Checks", "A1:G13", "checks.png", 1.4],
  ["Sources", "A1:F6", "sources.png", 1.2],
  ["Chart Data", `A1:C${monthEndIndexes.length + 1}`, "chart_data.png", 1.4],
];
for (const [sheetName, range, filename, scale] of renderTargets) {
  const preview = await workbook.render({ sheetName, range, scale, format: "png" });
  await fs.writeFile(path.join(qaDir, filename), new Uint8Array(await preview.arrayBuffer()));
}

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(path.join(outputDir, "NVDA_1y_backtest.xlsx"));

const report = {
  source: yahooChartUrl,
  rows: rows.length,
  firstDate: isoDate(rows[0].date),
  lastDate: isoDate(rows.at(-1).date),
  firstAdjClose: rows[0].adjClose,
  lastAdjClose: rows.at(-1).adjClose,
  expectedBuyHold,
  expectedStrategy,
  lastSignal: signal.at(-1),
  lastPosition: position.at(-1),
  inspect: {
    summary: summaryInspect.ndjson,
    checks: checksInspect.ndjson,
    errors: errorInspect.ndjson,
    drawings: drawingInspect.ndjson,
  },
};
await fs.writeFile(path.join(qaDir, "verification.json"), JSON.stringify(report, null, 2), "utf8");
console.log(JSON.stringify(report, null, 2));
