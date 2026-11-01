#!/usr/bin/env node
// S01 合成材料：CSV/XLSX 公式注入。全角起始符、零宽字符、双前缀、换行注入必须全部被守卫拦住。
// 纯数字金额与普通文本保持原样。不使用任何真实案件数据。
import { csvFormulaGuard, isCsvFormulaLead } from "../../packages/juscite-legal/src/kernel/tabularExportGuard.ts";

const MUST_BLOCK = [
  { name: "fullwidth-equals", value: "＝HYPERLINK(\"http://evil.example/x\",\"点\")" },
  { name: "fullwidth-plus", value: "＋cmd|'/C calc'!A0" },
  { name: "fullwidth-minus", value: "－2+3+cmd|'/C notepad'!A0" },
  { name: "fullwidth-at", value: "＠SUM(A1:A2)" },
  { name: "zwsp-equals", value: "\u200B=CMD|'/C calc'!A0" },
  { name: "zwnj-fullwidth-plus", value: "\u200C＋cmd|'/C calc'!A0" },
  { name: "zwsp-then-newline-fullwidth", value: "\u200B\n＝SUM(1+1)" },
  { name: "double-prefix", value: "=='=CMD|'/C calc'!A0" },
  { name: "newline-injection", value: "备注\n=CMD|'/C calc'!A0" },
  { name: "newline-crlf-at", value: "ok\r\n＠SUM(1)" },
];

const MUST_KEEP = ["-1200.00", "+300", "-1,200.50", "7200.00", "普通备注，含逗号", "第一行\n第二行"];

let failed = 0;
function check(name, cond, detail = "") {
  if (cond) console.log(`[S01] OK ${name}`);
  else {
    failed += 1;
    console.error(`[S01] FAIL ${name}${detail ? " — " + detail : ""}`);
  }
}

for (const { name, value } of MUST_BLOCK) {
  const guarded = csvFormulaGuard(value);
  const lead = isCsvFormulaLead(value);
  check(
    name,
    lead === true && guarded === `'${value}`,
    `lead=${lead} guarded=${JSON.stringify(guarded)}`,
  );
}

for (const value of MUST_KEEP) {
  check(`keep ${JSON.stringify(value)}`, csvFormulaGuard(value) === value, JSON.stringify(csvFormulaGuard(value)));
}

if (failed) {
  console.log("RESULT fail");
  process.exit(1);
}
console.log("RESULT pass");
