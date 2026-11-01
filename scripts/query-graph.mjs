#!/usr/bin/env node
// r12 波5 · 边界合同索引查询（contracts/ref-graph.json + contracts/pin-points.json 只读查询）。
// 用法：
//   node scripts/query-graph.mjs summary                    # 计数概览
//   node scripts/query-graph.mjs consumers <module> [符号]   # 谁在消费该上游模块（可再按符号过滤）
//   node scripts/query-graph.mjs symbols <module>           # 该上游模块被消费的全部具名导出
//   node scripts/query-graph.mjs imports <文件子串>          # 该文件的边界 import 边
//   node scripts/query-graph.mjs pins [id]                  # 树内注册点清单（可按 id 取单条）
// exit 0=命中，1=未命中/用法错。纯 Node，零依赖。
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = fileURLToPath(new URL("../", import.meta.url));
const graphPath = join(ROOT, "contracts", "ref-graph.json");
const pinsPath = join(ROOT, "contracts", "pin-points.json");
if (!existsSync(graphPath)) {
  console.error("[query-graph] 缺 contracts/ref-graph.json——先跑 node scripts/gen-ref-graph.mjs");
  process.exit(1);
}
const graph = JSON.parse(readFileSync(graphPath, "utf-8"));
const pinsDoc = existsSync(pinsPath) ? JSON.parse(readFileSync(pinsPath, "utf-8")) : null;
const [cmd, a1, a2] = process.argv.slice(2);
const out = (s) => console.log(s);
let hits = 0;

if (cmd === "summary") {
  out(`扫描 ${graph.meta.counts.scannedFiles} 文件，${graph.meta.counts.edges} 边，${graph.meta.counts.consumedExports} 个上游消费符号 / ${graph.meta.counts.contractModules} 合同模块`);
  out(`基线 ${graph.meta.baseline}`);
  const byMod = {};
  for (const c of graph.consumedExports) byMod[c.module] = (byMod[c.module] ?? 0) + 1;
  for (const [m, n] of Object.entries(byMod).sort()) out(`  ${m}: ${n} 符号`);
  if (pinsDoc) out(`注册点 ${pinsDoc.pinPoints.length} 条（contracts/pin-points.json）`);
  hits = 1;
} else if (cmd === "consumers" && a1) {
  const rows = graph.consumedExports.filter((c) => c.module === a1 && (!a2 || c.symbol === a2));
  for (const c of rows) {
    hits++;
    out(`${c.module} :: ${c.symbol}  ←  ${c.consumers.join(", ")}`);
  }
} else if (cmd === "symbols" && a1) {
  const rows = graph.consumedExports.filter((c) => c.module === a1);
  for (const c of rows) {
    hits++;
    out(`${c.symbol}  (${c.consumers.length} 消费方; decl: ${c.decl ?? "unresolved"})`);
  }
} else if (cmd === "imports" && a1) {
  for (const e of graph.edges.filter((e) => e.from.includes(a1))) {
    hits++;
    out(`${e.from} → ${e.spec} [${e.kind}] ${e.symbols.map((s) => s.name + (s.alias ? " as " + s.alias : "")).join(", ")}${e.resolved ? "  ⟶ " + e.resolved : ""}`);
  }
} else if (cmd === "pins") {
  const rows = pinsDoc ? pinsDoc.pinPoints.filter((p) => !a1 || String(p.id) === a1) : [];
  for (const p of rows) {
    hits++;
    out(`#${p.id} [${p.kind}] ${p.file}\n    ${p.what}\n    符号: ${p.symbols.map((s) => s.name).join(", ")}`);
  }
} else {
  console.error("用法: node scripts/query-graph.mjs <summary|consumers <module> [符号]|symbols <module>|imports <文件子串>|pins [id]>");
  process.exit(1);
}
if (hits === 0) {
  console.error(`[query-graph] 无命中（${cmd} ${a1 ?? ""}${a2 ?? ""}）`);
  process.exit(1);
}
