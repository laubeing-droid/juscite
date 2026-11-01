#!/usr/bin/env node
// r12 波5 · 边界合同索引生成器（设计 §四 波5/§八 原则1-2，D4）。
// 产出两件（默认落 contracts/，--out-dir 可改——upgrade 门禁②步把类型快照生成到临时目录做 diff）：
//   ref-graph.json     = 边界引用图：树内注册点文件+自有包+桥 对 上游合同包(@zcode/*)/自有包(@juscite/*)
//                        的具名符号级 import 边（不含纯第三方 npm 依赖与 node: 内建，scope 见 meta.scope）。
//   type-snapshot.json = 合同面类型快照：被消费的 @zcode/* 具名导出符号的声明原文+sha256
//                        （真源=树内 packages/*/src，声明文本取自 ts-morph 符号表，非手写）。
// 扫描范围（确定性，与 ci_gate nodecheck 同口径取桥文件）：
//   1) tools/bridge 顶层 *.mjs+*.mts（排 .bak/_tmp_）——对 @zcode/*、@juscite/*、跨出桥目录的相对导入
//   2) 自有包 src：packages/{juscite-legal,juscite-runtime-port,juscite-runtime-adapters,juscite-desktop-pet,juscite-edisc,juscite-vizb}
//      ——对 @zcode/*、跨出本包的相对导入
//   3) contracts/pin-points.json pinPoints[].file（树内注册点）——对 @zcode/*、@juscite/* 导入
// 用法：
//   node scripts/gen-ref-graph.mjs                     # 生成到 contracts/
//   node scripts/gen-ref-graph.mjs --out-dir <dir>     # 生成到指定目录（门禁临时 diff 用）
//   node scripts/gen-ref-graph.mjs --root <dir>        # 扫描另一棵树（rebase 演练树定责用；ts-morph 仍取本树依赖）
// 纯 Node + ts-morph（既有依赖，不新增）；exit 0/1 可判。
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { Project, SyntaxKind, ts } from "ts-morph";

const SCRIPT_ROOT = fileURLToPath(new URL("../", import.meta.url)); // scripts/ → 仓库根（m1-u01）
const args = process.argv.slice(2);
function flagOf(name) {
  const i = args.indexOf(name);
  return i >= 0 ? args[i + 1] : undefined;
}
const ROOT = flagOf("--root") ? resolve(flagOf("--root")) : SCRIPT_ROOT;
const OUT_DIR = flagOf("--out-dir") ? resolve(flagOf("--out-dir")) : join(SCRIPT_ROOT, "contracts");
const DAY = new Date().toISOString().slice(0, 10);
const rel = (p) => relative(ROOT, p).replaceAll("\\", "/");

// ── 范围 ──
const BRIDGE_DIR = join(ROOT, "tools", "bridge");
const OWN_PACKAGES = ["juscite-legal", "juscite-runtime-port", "juscite-runtime-adapters", "juscite-desktop-pet", "juscite-edisc", "juscite-vizb", "juscite-flow", "juscite-office-bridge"]
  .map((p) => join(ROOT, "packages", p));
const PIN_FILE = join(SCRIPT_ROOT, "contracts", "pin-points.json"); // 注册点清单恒取本树（--root 演练树也用同清单）

function listDir(dir, exts, out = []) {
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    if (e.name.startsWith(".") || e.name === "node_modules" || e.name === "dist" || e.name.includes(".bak")) continue;
    const full = join(dir, e.name);
    if (e.isDirectory()) listDir(full, exts, out);
    else if (exts.some((x) => e.name.endsWith(x))) out.push(full);
  }
  return out;
}

// ── 收集扫描文件 ──
const bridgeFiles = existsSync(BRIDGE_DIR)
  ? readdirSync(BRIDGE_DIR)
      .filter((f) => (f.endsWith(".mjs") || f.endsWith(".mts")) && !f.includes(".bak") && !f.startsWith("_tmp_"))
      .sort()
      .map((f) => join(BRIDGE_DIR, f))
  : [];
const ownFiles = OWN_PACKAGES.flatMap((d) => (existsSync(d) ? listDir(d, [".ts", ".tsx"]) : [])).sort();
let pinPoints = [];
let pinFiles = [];
if (existsSync(PIN_FILE)) {
  const pinsDoc = JSON.parse(readFileSync(PIN_FILE, "utf-8"));
  pinPoints = pinsDoc.pinPoints ?? [];
  pinFiles = [...new Set(pinPoints.map((p) => p.file).filter(Boolean))]
    .map((f) => join(ROOT, ...f.split("/")))
    .filter((f) => existsSync(f))
    .sort();
}
const scanFiles = [...new Set([...bridgeFiles, ...ownFiles, ...pinFiles])];

// ── ts-morph 工程：手工加文件（不拖 tsconfig 全量）；合同包 src 入程序供符号解析 ──
const project = new Project({
  skipAddingFilesFromTsConfig: true,
  skipFileDependencyResolution: true,
  compilerOptions: {
    allowJs: true,
    module: ts.ModuleKind.NodeNext,
    moduleResolution: ts.ModuleResolutionKind.Bundler, // exports 映射直达 src/*.ts（workspace 真源）
    target: ts.ScriptTarget.ES2022,
    esModuleInterop: true,
    skipLibCheck: true,
  },
});
for (const f of scanFiles) project.addSourceFileAtPath(f);
// 合同包真源入程序（被消费符号的声明必须可解析；即使 node_modules 符号链接解析失效也不落空）
const CONTRACT_SOURCES = [
  join(ROOT, "packages", "rpc", "src"),
  join(ROOT, "packages", "shared", "src"),
  join(ROOT, "packages", "services", "src"),
  join(ROOT, "packages", "client", "src"),
];
for (const d of CONTRACT_SOURCES) if (existsSync(d)) project.addSourceFilesAtPaths([join(d, "**", "*.ts").replaceAll("\\", "/")]);

function inScope(spec, fromFile) {
  if (spec.startsWith("node:")) return false;
  if (spec.startsWith("@zcode/") || spec.startsWith("@juscite/")) return true;
  if (spec.startsWith(".")) {
    const target = resolve(fromFile, "..", spec);
    if (fromFile.startsWith(BRIDGE_DIR)) return !target.startsWith(BRIDGE_DIR); // 桥内相对互导不记
    const own = OWN_PACKAGES.find((d) => fromFile.startsWith(d));
    if (own) return !target.startsWith(own); // 包内相对互导不记
    return false; // 树内注册点对本包内部的相对导入不属边界
  }
  return false; // 纯第三方 npm 依赖（ws/react/lucide-react…）不属上游合同边界，meta.scope 记口径
}
function resolveSpec(spec, fromFile) {
  const sf = project.getSourceFile(resolve(fromFile, "..", spec)) ?? null;
  if (sf) return rel(sf.getFilePath());
  const entry = contractEntryOf(spec); // @zcode/* 走 exports 真源（ts 解析可能落 dist types，不可作 resolved）
  return entry ? rel(entry) : null;
}
// @zcode/<pkg>[/<sub>] → packages/<pkg>/package.json exports 映射的树内 .ts 真源入口（§八原则1：消费上游真源）
function contractEntryOf(spec) {
  if (!spec.startsWith("@zcode/")) return null;
  const parts = spec.split("/");
  const pkgDir = join(ROOT, "packages", parts[1]);
  const pkgJsonPath = join(pkgDir, "package.json");
  if (!existsSync(pkgJsonPath)) return null;
  let exportsMap;
  try { exportsMap = JSON.parse(readFileSync(pkgJsonPath, "utf-8")).exports ?? {}; } catch { return null; }
  const key = "./" + parts.slice(2).join("/");
  const raw = exportsMap[key === "./" ? "." : key];
  const target = typeof raw === "string" ? raw : raw?.default ?? raw?.types ?? null;
  if (!target || !target.endsWith(".ts") || target.includes("dist/")) return null;
  const entry = join(pkgDir, ...target.split("/"));
  return existsSync(entry) ? entry : null;
}
function symbolsOfImport(decl) {
  const clause = decl.getImportClause();
  const syms = [];
  if (!clause) return [{ name: "<side-effect>", form: "side-effect" }];
  if (clause.getDefaultImport()) syms.push({ name: clause.getDefaultImport().getText(), form: "default" });
  if (clause.getNamespaceImport()) syms.push({ name: clause.getNamespaceImport().getText(), form: "namespace" });
  for (const ni of clause.getNamedImports()) {
    const alias = ni.getAliasNode()?.getText();
    syms.push(alias ? { name: ni.getName(), alias, form: "named" } : { name: ni.getName(), form: "named" });
  }
  return syms;
}

const edges = [];
for (const f of scanFiles) {
  const sf = project.getSourceFile(f);
  const from = rel(f);
  for (const decl of sf.getImportDeclarations()) {
    const spec = decl.getModuleSpecifierValue();
    if (!inScope(spec, f)) continue;
    edges.push({ from, spec, kind: "import", symbols: symbolsOfImport(decl), resolved: resolveSpec(spec, f) });
  }
  for (const re of sf.getExportDeclarations()) {
    const spec = re.getModuleSpecifierValue();
    if (!spec || !inScope(spec, f)) continue;
    const syms = re.getNamedExports().map((ne) => {
      const alias = ne.getAliasNode()?.getText();
      return alias ? { name: ne.getName(), alias, form: "re-export" } : { name: ne.getName(), form: "re-export" };
    });
    edges.push({ from, spec, kind: "export-from", symbols: syms.length ? syms : [{ name: "<star>", form: "re-export-star" }], resolved: resolveSpec(spec, f) });
  }
  for (const call of sf.getDescendantsOfKind(SyntaxKind.CallExpression)) {
    if (call.getExpression().getKind() !== SyntaxKind.ImportKeyword) continue;
    const arg = call.getArguments()[0];
    if (!arg) continue;
    const spec = arg.getText().replace(/^["']|["']$/g, "");
    if (!inScope(spec, f)) continue;
    edges.push({ from, spec, kind: "dynamic-import", symbols: [{ name: "<dynamic>", form: "dynamic" }], resolved: resolveSpec(spec, f) });
  }
}
edges.sort((a, b) => (a.from + a.spec + a.kind).localeCompare(b.from + b.spec + b.kind));

// ── 聚合：@zcode/* 具名导出消费面（consumedExports + 类型快照）──
const checker = project.getTypeChecker();
const consumed = new Map(); // "module\0symbol" -> { module, symbol, consumers:Set }
const declOf = new Map(); // "module\0symbol" -> { decl, hash, text }
function preferSource(paths) {
  const underSrc = paths.filter((p) => /\/packages\/[^/]+\/src\//.test(p));
  return underSrc[0] ?? paths[0] ?? null;
}
for (const e of edges) {
  if (!e.spec.startsWith("@zcode/")) continue;
  for (const s of e.symbols) {
    if (s.form !== "named" && s.form !== "default") continue;
    const key = e.spec + "\0" + s.name;
    if (!consumed.has(key)) consumed.set(key, { module: e.spec, symbol: s.name, consumers: new Set() });
    consumed.get(key).consumers.add(e.from);
    if (declOf.has(key)) continue;
    // 声明解析：入口=包 exports 映射的树内 src 真源（ts 裸解析会落 dist types，不作数）；桶再导出经别名链追到声明文件
    const entrySf = contractEntryOf(e.spec) ? project.getSourceFile(contractEntryOf(e.spec)) : null;
    let sym = entrySf?.getExportSymbols().find((x) => x.getName() === s.name) ?? null;
    try {
      for (let i = 0; sym && i < 5 && sym.hasFlags(ts.SymbolFlags.Alias); i++) { // export {X} from 是别名：追到底（非别名再调即抛，必须以旗标守门）
        const next = checker.getAliasedSymbol(sym);
        if (next === sym) break;
        sym = next;
      }
      const declPaths = (sym?.getDeclarations() ?? []).map((d) => d.getSourceFile().getFilePath().replaceAll("\\", "/"));
      const chosen = preferSource(declPaths);
      const declNode = sym?.getDeclarations().find((d) => d.getSourceFile().getFilePath().replaceAll("\\", "/") === chosen);
      if (declNode) {
        const text = declNode.getText();
        declOf.set(key, { decl: chosen ? rel(chosen) : null, hash: "sha256:" + createHash("sha256").update(text).digest("hex"), text });
        continue;
      }
    } catch { /* 落入下方 unresolved 记录 */ }
    declOf.set(key, { decl: null, hash: "sha256:unresolved", text: null });
  }
}
const consumedExports = [...consumed.values()]
  .map((c) => ({ module: c.module, symbol: c.symbol, decl: declOf.get(c.module + "\0" + c.symbol)?.decl ?? null, consumers: [...c.consumers].sort() }))
  .sort((a, b) => (a.module + a.symbol).localeCompare(b.module + b.symbol));

const typeSnapshot = {
  meta: { generated: DAY, generator: "scripts/gen-ref-graph.mjs", root: rel(ROOT) || ".", note: "合同面类型快照（设计 §五②/§八原则1）：被消费 @zcode/* 具名导出的声明原文+sha256；升级后重生成 diff，形变即爆红" },
  symbols: {},
};
for (const c of consumedExports) {
  const d = declOf.get(c.module + "\0" + c.symbol);
  (typeSnapshot.symbols[c.module] ??= {})[c.symbol] = { decl: d?.decl ?? null, hash: d?.hash ?? "sha256:unresolved", text: d?.text ?? null };
}

const refGraph = {
  meta: {
    generated: DAY,
    generator: "scripts/gen-ref-graph.mjs",
    baseline: "upstream/main=3c5b227649371507ddc4eb46ac5133afe6db1cab (3.16.2 原树)",
    scope: "边界引用图：桥(tools/bridge 顶层 .mjs/.mts 排 .bak/_tmp_)+自有包(juscite-legal/runtime-port/runtime-adapters/desktop-pet/edisc/vizb) src+树内注册点(contracts/pin-points.json) 对 @zcode/*、@juscite/* 与跨域相对导入；node: 内建、纯第三方 npm 依赖(ws/react/lucide-react 等)、域内相对互导不记",
    counts: { scannedFiles: scanFiles.length, edges: edges.length, consumedExports: consumedExports.length, contractModules: Object.keys(typeSnapshot.symbols).length },
  },
  edges,
  consumedExports,
};

mkdirSync(OUT_DIR, { recursive: true });
writeFileSync(join(OUT_DIR, "ref-graph.json"), JSON.stringify(refGraph, null, 2) + "\n");
writeFileSync(join(OUT_DIR, "type-snapshot.json"), JSON.stringify(typeSnapshot, null, 2) + "\n");
console.log(`[gen-ref-graph] 扫描 ${scanFiles.length} 文件 → ${edges.length} 边，@zcode/* 消费导出 ${consumedExports.length} 符号 / ${Object.keys(typeSnapshot.symbols).length} 合同模块`);
console.log(`[gen-ref-graph] REF_GRAPH_WRITE ${join(OUT_DIR, "ref-graph.json")}`);
console.log(`[gen-ref-graph] TYPE_SNAPSHOT_WRITE ${join(OUT_DIR, "type-snapshot.json")}`);
const unresolved = consumedExports.filter((c) => !c.decl);
if (unresolved.length) console.log(`[gen-ref-graph] WARN unresolved ${unresolved.length}: ${unresolved.slice(0, 5).map((c) => c.module + ":" + c.symbol).join(", ")}`);
