#!/usr/bin/env node
// 功能 #13 法条手册合成自测（RE-13 完成定义「合成自测」步；红线①测试一律合成材料）。
// 两层：
//   A. 模型面（纯函数，不起桥）：契约四违规具名报错/解析全特征/效力推导含 UTC+8 边界/修订链 H1
//      三分支与防呆/跨法废止 H2 四防呆/标题分词语义。
//   B. 桥面（真子进程径）：自拉 bridge_host.mjs 独立实例（随机空闲口+BRIDGE_OC28_SSE=0 隔离，
//      BRIDGE_LAWBOOK_PACK_ROOT 指向临时包根），打 /api/legal/laws* 与 /api/legal/packs* 真端点——
//      能力标记/多包聚合同 ID 先到先得/坏包 fail-closed 排除/搜索双模式/详情带行号/422 具名违规/
//      篇内过滤/收藏无幂等/历史同词刷新/包延迟删除标记+撤销+下次启动物理清理。
// 收场杀自家实例（杀前核验命令行含 bridge_host.mjs）并清掉自己的 bridge-<port>.db* 与临时目录。
// 纯 Node 零依赖；单命令 exit 0/1，末行 LAWBOOK_SYNTH_PASS 可判。
// 用法：node tools/bridge/lawbook_synthetic.mjs
import { spawn, spawnSync } from "node:child_process";
import { createHash, randomUUID } from "node:crypto";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { homedir, tmpdir } from "node:os";
import { join } from "node:path";
import { DatabaseSync } from "node:sqlite";
import { fileURLToPath } from "node:url";
import {
  buildRepealChain, buildRevisionChain, deriveEffect, extractRepealedNames, extractValidFrom,
  LawbookContractError, parseLawMd, titleMatches, tokenizeQuery, todayCn, validateLawMd,
} from "./lawbook_model.mjs";

const REPO_ROOT = fileURLToPath(new URL("../../", import.meta.url));
let passed = 0, failed = 0;
function ok(n, msg) { passed += 1; console.log(`[lawbook-synth] ${n}: OK ${msg}`); }
function fail(n, msg, detail) { failed += 1; console.error(`[lawbook-synth] ${n}: FAIL ${msg}${detail ? `\n  ${detail}` : ""}`); }
function check(n, cond, msg, detail) { cond ? ok(n, msg) : fail(n, msg, detail); }

// ═══════════════ A. 模型面 ═══════════════
{
  // A1 契约四违规具名报错
  const cases = [
    ["无 INFO END\n## 一\n第一条 正文", "INFO_END_MISSING"],
    ["# 标题\n<!-- INFO END -->\n##\n第一条 正文", "BARE_HEADING"],
    ["# 标题\n<!-- INFO END -->\n<!-- TABLE -->\n| 甲 | 乙 |", "TABLE_UNCLOSED"],
    ["# 标题\n<!-- INFO END -->", "EMPTY_BODY"],
  ];
  let a1 = true;
  for (const [text, type] of cases) {
    const v = validateLawMd(text);
    if (v.ok || v.violations[0]?.type !== type) { a1 = false; fail("A1", `${type} 未检出`, JSON.stringify(v)); }
  }
  let threw = false;
  try { parseLawMd("缺 END\n第一条 x", "law-x"); } catch (e) {
    threw = e instanceof LawbookContractError && e.lawId === "law-x" && /INFO_END_MISSING@L0/.test(e.message);
  }
  check("A1", a1 && threw, "契约四违规具名报错（类型+行号+法 ID）");

  // A2 解析全特征
  const md = [
    "# 合成测试法", "", "（合成机关·二〇二六年制定）", "键一 值一", "<!-- INFO END -->",
    "## 第一编 总则", "### 第一章 通例", "",
    "第一条 这是第一条正文。", "续行并入本段。", "",
    "第二条 第二条含合成墨线词。", "",
    "<!-- FORCE BREAK -->", "强制分段独立段。", "",
    "<!-- TABLE -->", "| 列甲 | 列乙 |", "| --- | --- |", "| 甲1 | 乙1 |", "<!-- TABLE END -->",
  ].join("\n");
  const p = parseLawMd(md, "law-a2");
  check("A2a", p.titles.length === 1 && p.titles[0] === "合成测试法", "标题行收 titles", JSON.stringify(p.titles));
  check("A2b", p.info.length === 2 && p.info[0].key === "" && p.info[1].key === "键一", "信息块无键行+键值行", JSON.stringify(p.info));
  check("A2c", p.sections.length === 2 && p.sections[0].level === 2 && p.sections[1].level === 3, "##/### 层级收 sections");
  check("A2d", p.toc[0].children.length === 1 && p.toc[0].children[0].title === "第一章 通例", "TOC 树层级挂载");
  check("A2e", p.paragraphs.length === 4 && p.paragraphs[0].articleNo === "第一条" && p.paragraphs[0].text.includes("续行并入本段。"), "条号正则分段+续行拼接");
  check("A2f", p.paragraphs[2].text === "强制分段独立段。" && p.paragraphs[2].articleNo === null, "FORCE BREAK 强制分段");
  check("A2g", Array.isArray(p.paragraphs[3].table) && p.paragraphs[3].table.length === 2, "TABLE 管道行收且跳分隔行", JSON.stringify(p.paragraphs[3].table));
  check("A2h", p.paragraphs.every((x) => x.line >= 6), "段落带源行号（滚动锚）");

  // A3 修正案模式 + 超长续行
  const amd = parseLawMd("# 合成修正案\n<!-- INFO END -->\n一、第一处修改如下：\n-续行内容接上。\n二、第二处修改。", "law-a3");
  check("A3", amd.paragraphs[0].text === "一、第一处修改如下：续行内容接上。" && amd.paragraphs[1].articleNo === "二、", "修正案模式 - 行去杠续拼（H7c 超长续行同径不插换行）", JSON.stringify(amd.paragraphs.map((x) => x.text)));

  // A4 效力推导（today 注入钉定；UTC+8 口径）
  check("A4a", deriveEffect({ valid_to: "2099-12-31" }, "2026-10-28") === "current" && deriveEffect({ valid_from: "" }, "2026-10-28") === "current", "缺失 valid_from=已施行");
  check("A4b", deriveEffect({ valid_to: "2026-10-28" }, "2026-10-28") === "repealed", "valid_to==today 废止（含失效当天）");
  check("A4c", deriveEffect({ valid_from: "2026-10-29" }, "2026-10-28") === "not_yet", "valid_from 在未来=暂未施行");
  check("A4d", todayCn(Date.UTC(2026, 9, 28, 15, 0, 0)) === "2026-10-28" && todayCn(Date.UTC(2026, 9, 28, 16, 0, 0)) === "2026-10-29", "today=UTC+8 日历日（23:59/00:08 北京时刻跨日）");

  // A5 修订链 H1（三分支+防呆）
  const rows = [
    { id: "r1", name: "链法", level: "法律", publish: "2000-01-01", valid_from: "2000-01-01" },
    { id: "r2", name: "链法", level: "法律", publish: "2010-05-01", valid_from: "2010-10-01" }, // 正文提取≥公布→取正文
    { id: "r3", name: "链法", level: "法律", publish: "2020-02-01", valid_from: "" },
    { id: "s1", name: "缺版法", level: "法律", publish: "", valid_from: "" },
    { id: "s2", name: "缺版法", level: "法律", publish: "2015-01-01", valid_from: "" },
    { id: "j1", name: "解释法", level: "司法解释", publish: "2001-01-01", valid_from: "" },
    { id: "j2", name: "解释法", level: "司法解释", publish: "2021-01-01", valid_from: "" },
    { id: "m1", name: "歧级法", level: "法律", publish: "2005-01-01", valid_from: "" },
    { id: "m2", name: "歧级法", level: "行政法规", publish: "2015-01-01", valid_from: "" },
    { id: "u1", name: "独版法", level: "法律", publish: "2010-01-01", valid_from: "" },
  ];
  const ch = buildRevisionChain(rows);
  check("A5a", ch.updates.get("r1").ver === 3 && ch.updates.get("r1").valid_to === "2010-10-01", "ver=同名数+旧版 valid_to=新版 valid_from（三分支①）");
  check("A5b", ch.updates.get("r2").valid_to === "2020-02-01", "新版 valid_from 缺失→链内取其公布日（三分支③）");
  check("A5c", ch.updates.get("r3").valid_to === undefined && ch.updates.get("r3").ver === 3, "末版不回填 valid_to");
  check("A5d", ch.updates.get("s2").valid_to === undefined && ch.warnings.some((w) => w.includes("缺版法")), "缺 publish 警告不入链");
  check("A5e", ch.updates.get("j1").ver === 2 && ch.updates.get("j1").valid_to === undefined, "司法解释 ver 计数但不入链");
  check("A5f", ch.warnings.some((w) => w.includes("歧级法") && w.includes("level 不一致")), "level 不一致警告不入链");
  check("A5g", ch.updates.get("u1")?.ver === 1, "单版本 ver=1");
  // 单版本生效日：extractValidFrom 三分支 ingest 语义
  check("A5h", extractValidFrom("本法自2021年1月1日起施行。", "2020-05-28") === "2021-01-01", "①正文提取≥公布→取正文值");
  check("A5i", extractValidFrom("本法自2008年1月1日起施行。", "2012-12-28") === "2012-12-28", "②提取<公布→封顶公布日");
  check("A5j", extractValidFrom("无施行日正文。", "2019-04-23") === "" && extractValidFrom("本解释自公布之日起施行。", "2020-12-29") === "2020-12-29", "③无提取留空+关键词直取公布日");

  // A6 跨法废止 H2 四防呆
  const repRows = [
    { id: "old", name: "合成旧法", level: "法律", publish: "1999-03-15", valid_from: "" },
    { id: "fut", name: "未来法", level: "法律", publish: "2030-01-01", valid_from: "" },
    { id: "same", name: "废止者", level: "法律", publish: "2000-01-01", valid_from: "" },
    { id: "noeff", name: "无日法", level: "法律", publish: "", valid_from: "" },
  ];
  const repBodies = new Map([
    ["rep1", "第一千条 本法自2021年1月1日起施行。《中华人民共和国合成旧法》、《未来法》同时废止。"],
    ["rep2", "《废止者》同时废止。"], // 同名排除（与废止者自身同名的链归 H1）
    ["rep3", "《无日法》同时废止。"],
    ["rep4", "《无日废止目标法》同时废止。"], // 废止者自身无生效日 → 警告跳过
  ]);
  repRows.push({ id: "rep1", name: "废止者", level: "法律", publish: "2020-05-28", valid_from: "2021-01-01" });
  repRows.push({ id: "rep2", name: "废止者二", level: "法律", publish: "2001-01-01", valid_from: "" });
  repRows.push({ id: "rep3", name: "废止者三", level: "法律", publish: "2002-01-01", valid_from: "" });
  repRows.push({ id: "rep4", name: "无日废止者", level: "法律", publish: "", valid_from: "" });
  const rp = buildRepealChain(repRows, repBodies);
  check("A6a", extractRepealedNames("《中华人民共和国合成旧法》、《未来法》同时废止。").join("|") === "合成旧法|未来法", "书名号组抽取+去国名前缀");
  check("A6b", rp.updates.get("old")?.valid_to === "2021-01-01", "被废法最后一版 valid_to=新法施行日");
  check("A6c", !rp.updates.has("fut") && rp.warnings.some((w) => w.includes("未来法") && w.includes("防呆")), "发布期防呆（被废法须早于生效日已发布）");
  check("A6d", !rp.updates.has("same"), "同名排除");
  check("A6e", !rp.updates.has("noeff") && rp.warnings.some((w) => w.includes("无生效日期")), "无生效日警告跳过（废止者无日→警告不入链）");

  // A7 标题分词语义（顺序无关全包含）
  check("A7a", titleMatches("劳动合同法", "合同劳动") === true && titleMatches("劳动合同法", "劳动合") === true, "分词全包含顺序无关");
  check("A7b", titleMatches("劳动合同法", "劳动合同") === true && titleMatches("劳动合同法", "合同刑") === false, "包含直配+不命中否决");
}

// ═══════════════ B. 桥面（真子进程径）═══════════════
const scratch = mkdtempSync(join(tmpdir(), "juscite-lawbook-"));
const packsRoot = join(scratch, "lawbook-packs");
mkdirSync(packsRoot, { recursive: true });

function buildMiniPack(dir, { name, laws, cats, hashBad = false }) {
  mkdirSync(join(dir, "content"), { recursive: true });
  const dbPath = join(dir, "pack.sqlite3");
  if (existsSync(dbPath)) rmSync(dbPath);
  const db = new DatabaseSync(dbPath);
  db.exec(`CREATE TABLE law (id TEXT PRIMARY KEY, name TEXT NOT NULL, subtitle TEXT, level TEXT NOT NULL,
    category_id TEXT, publish TEXT, valid_from TEXT DEFAULT '', valid_to TEXT DEFAULT '2099-12-31',
    ver INTEGER NOT NULL DEFAULT 1, tags TEXT NOT NULL DEFAULT '[]', filename TEXT NOT NULL, order_num INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE category (id TEXT PRIMARY KEY, name TEXT NOT NULL, folder TEXT, is_subfolder INTEGER NOT NULL DEFAULT 0,
    "group" TEXT, sort_order INTEGER NOT NULL DEFAULT 0);`);
  const qL = db.prepare("INSERT INTO law VALUES (?,?,?,?,?,?,?,?,?,?,?,?)");
  const qC = db.prepare('INSERT INTO category VALUES (?,?,?,?,?,?)');
  for (const c of cats) qC.run(...c);
  let i = 0;
  for (const l of laws) {
    writeFileSync(join(dir, "content", l.filename), l.md, "utf-8");
    qL.run(l.id, l.name, null, l.level ?? "法律", l.category_id, l.publish ?? null, l.valid_from ?? "", l.valid_to ?? "2099-12-31", l.ver ?? 1, "[]", l.filename, i++);
  }
  db.close();
  const buf = readFileSync(dbPath);
  const hash = createHash("sha256").update(buf).digest("hex");
  writeFileSync(join(dir, "pack.meta"), JSON.stringify({
    name, hash: hashBad ? "0".repeat(64) : hash, update: Math.floor(Date.now() / 1000), filesize: buf.length,
  }));
}

const MD_A1 = [
  "# 合成测试法", "", "（合成机关 二〇二六年制定）", "制定机关 合成常委会", "<!-- INFO END -->",
  "## 第一编 总则", "", "第一条 合成测试法第一条正文，含合成墨线词。", "续行并入。", "",
  "第二条 第二条正文。", "",
].join("\n");
const MD_A2 = [
  "# 合成废止法", "", "<!-- INFO END -->", "## 第一章 通例", "", "第一条 本法已废止留档。留档独词苦瓜藤。第一条正文。",
].join("\n");
const MD_A3 = [
  "# 合成未来法", "", "<!-- INFO END -->", "", "第一条 本法尚未施行。第一条正文。",
].join("\n");
const MD_B1 = [
  "# 合成贝塔法", "", "<!-- INFO END -->", "## 第一章 通例", "", "第一条 贝塔法正文，独立词苦瓜藤。",
].join("\n");
const MD_B2 = [
  "# 合成修正案", "", "（合成机关 修正）", "<!-- INFO END -->", "一、第一处修改：", "-续行接上。", "二、第二处修改。",
].join("\n");
const MD_BAD = [ // 契约违规：缺 INFO END
  "# 合成残法", "", "## 第一章", "", "第一条 正文被吞风险。",
].join("\n");

buildMiniPack(join(packsRoot, "alpha"), {
  name: "alpha",
  cats: [
    ["caaa0000000000000000000000000ca1", "测试民法", "测试民法", 1, "测试组块", 1],
    ["caaa0000000000000000000000000ca2", "测试已废", "测试已废", 1, "", 900],
  ],
  laws: [
    { id: "a00000000000000000000000000000a1", name: "合成测试法", category_id: "caaa0000000000000000000000000ca1", publish: "2020-01-01", valid_from: "2020-03-01", filename: "合成测试法.md", md: MD_A1 },
    { id: "a00000000000000000000000000000a2", name: "合成废止法", category_id: "caaa0000000000000000000000000ca2", publish: "1999-03-15", valid_from: "1999-10-01", valid_to: "2021-01-01", ver: 2, filename: "合成废止法.md", md: MD_A2 },
    { id: "a00000000000000000000000000000a3", name: "合成未来法", category_id: "caaa0000000000000000000000000ca1", publish: "2026-01-01", valid_from: "2999-01-01", filename: "合成未来法.md", md: MD_A3 },
  ],
});
buildMiniPack(join(packsRoot, "beta"), {
  name: "beta",
  cats: [["cbbb0000000000000000000000000cb1", "测试贝塔", "测试贝塔", 1, "测试组块", 2]],
  laws: [
    { id: "a00000000000000000000000000000a1", name: "合成测试法（贝塔重名版）", category_id: "cbbb0000000000000000000000000cb1", publish: "2021-01-01", filename: "贝塔重名.md", md: MD_B1 }, // 同 ID：先到先得应被弃；首条供包抽检自检
    { id: "b00000000000000000000000000000b2", name: "合成修正案", level: "法律", category_id: "cbbb0000000000000000000000000cb1", publish: "2022-02-02", filename: "合成修正案.md", md: MD_B2 },
    { id: "c00000000000000000000000000000c1", name: "合成残法", category_id: "cbbb0000000000000000000000000cb1", filename: "合成残法.md", md: MD_BAD }, // 契约违规法：detail 422 具名报错路径
  ],
});
buildMiniPack(join(packsRoot, "bad"), {
  name: "bad", hashBad: true,
  cats: [["cbad0000000000000000000000000cb1", "测试坏包", "测试坏包", 1, "", 901]],
  laws: [{ id: "d00000000000000000000000000000d1", name: "合成坏包法", category_id: "cbad0000000000000000000000000cb1", filename: "坏包法.md", md: MD_A1 }],
});
// gamma：包校验合法但唯一法抽检解析自检失败 → 整包 error 排除（§3.1 抽检路径）
buildMiniPack(join(packsRoot, "gamma"), {
  name: "gamma",
  cats: [["cgm0000000000000000000000000cg1", "测试残卷", "测试残卷", 1, "", 902]],
  laws: [{ id: "e00000000000000000000000000000e1", name: "合成孤残法", category_id: "cgm0000000000000000000000000cg1", filename: "合成孤残法.md", md: MD_BAD }],
});
// 延迟删除：预置 gone 包 + gone.delete 标记 → 桥启动时物理清理
mkdirSync(join(packsRoot, "gone"), { recursive: true });
writeFileSync(join(packsRoot, "gone", "pack.meta"), "{}");
writeFileSync(join(packsRoot, "gone.delete"), "");

function pickFreePort() {
  for (let p = 31400 + Math.floor(Math.random() * 2000); ; p += 1) {
    const r = spawnSync("powershell.exe", ["-NoProfile", "-Command",
      `(Test-NetConnection -ComputerName 127.0.0.1 -Port ${p} -InformationLevel Quiet -WarningAction SilentlyContinue)`],
      { encoding: "utf-8", timeout: 20000 });
    if (String(r.stdout ?? "").trim() !== "True") return p;
  }
}
function commandLineLooksLikeBridge(pid) {
  const r = spawnSync("powershell.exe", ["-NoProfile", "-Command",
    `(Get-CimInstance Win32_Process -Filter "ProcessId=${pid}").CommandLine`],
    { encoding: "utf-8", timeout: 20000 });
  return String(r.stdout ?? "").includes("bridge_host.mjs");
}
const BRIDGE_PORT = pickFreePort();
const storeDir = join(homedir(), "AppData", "Roaming", "Juscite", "bridge");
function cleanupBridgeFiles() {
  for (const suffix of [".db", ".db-wal", ".db-shm"]) {
    try { rmSync(join(storeDir, `bridge-${BRIDGE_PORT}${suffix}`), { force: true }); } catch { /* 尽力而为 */ }
  }
}

let bridgePid = 0;
try {
  const env = {
    ...process.env, BRIDGE_PORT: String(BRIDGE_PORT), BRIDGE_OC28_SSE: "0", BRIDGE_OC28_PASSWORD: "synth",
    BRIDGE_LAWBOOK_PACK_ROOT: packsRoot,
  };
  const child = spawn(process.execPath, ["--import", "tsx", join("tools", "bridge", "bridge_host.mjs")],
    { cwd: REPO_ROOT, env, stdio: ["ignore", "pipe", "pipe"] });
  bridgePid = child.pid;
  child.stdout.on("data", () => {}); child.stderr.on("data", (d) => process.stderr.write(`[bridge] ${d}`));

  async function probeServerInfo(timeoutMs) {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      try {
        const r = await fetch(`http://127.0.0.1:${BRIDGE_PORT}/api/server-info`, { signal: AbortSignal.timeout(2500) });
        if (r.ok) return JSON.parse(await r.text());
      } catch { /* 未起，重试 */ }
      await new Promise((res) => setTimeout(res, 500));
    }
    return null;
  }
  const info = await probeServerInfo(60000);
  if (!info) throw new Error("桥 60s 不可探");
  const j = async (path, init) => {
    const r = await fetch(`http://127.0.0.1:${BRIDGE_PORT}${path}`, init);
    return { status: r.status, body: await r.json().catch(() => ({})) };
  };
  const post = (path, obj) => j(path, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(obj) });

  // B1 能力标记 + 启动期延迟删除落地
  check("B1", info.lawbook === 1 && info.store === "sqlite", "/api/server-info 携 lawbook 能力标记");
  check("B2", !existsSync(join(packsRoot, "gone")) && !existsSync(join(packsRoot, "gone.delete")), "上次会话 .delete 标记本次启动物理清理（等量 E7 延迟删除）");

  // B3 包状态：好包 success / 坏包 error fail-closed 排除
  const st = await j("/api/legal/laws/status");
  const byName = Object.fromEntries((st.body.packs ?? []).map((p) => [p.name, p]));
  check("B3", st.body.available === true && byName.alpha?.state === "success" && byName.beta?.state === "success"
    && byName.bad?.state === "error" && /sha256/.test(byName.bad?.reason ?? "") && byName.alpha?.lawCount === 3,
    "包校验：好包 success、坏包 sha256 对账失败=error 排除", JSON.stringify(byName));

  // B4 多包聚合：同 ID 先到先得（alpha 在前，beta 重名版被弃）
  const cats = await j("/api/legal/laws/categories");
  const total = cats.body.total;
  const dupCat = cats.body.dept.find((d) => d.name === "测试贝塔");
  check("B4", total === 5 && dupCat?.count === 2, `同 ID 先到先得（total=${total}，贝塔 cat 计数=${dupCat?.count}，重名版已弃）`, JSON.stringify(cats.body));
  const lvOrder = cats.body.levelOrder;
  check("B5", cats.body.levels.length === 1 && cats.body.levels[0]?.level === "法律"
    && lvOrder.length === 11 && lvOrder[0] === "宪法" && lvOrder[10] === "其他",
    `阶位序表固定 11 档（levels=${cats.body.levels.map((l) => l.level).join(",")}，序表首尾=${lvOrder[0]}/${lvOrder[10]}）`);
  const gp = cats.body.dept.find((d) => d.group === "测试组块");
  check("B6", gp?.count === 2, "group 组块跨包聚合计数", JSON.stringify(gp));

  // B7 搜索双模式
  const s1 = await j("/api/legal/laws?query=" + encodeURIComponent("测试合成") + "&mode=title");
  check("B7a", s1.body.count === 1 && s1.body.results[0]?.name === "合成测试法", "标题分词全包含顺序无关（测试合成→合成测试法）");
  const s2 = await j("/api/legal/laws?query=" + encodeURIComponent("苦瓜藤") + "&mode=fulltext");
  check("B7b", s2.body.count === 1 && s2.body.results[0]?.name === "合成废止法", "全文模式命中正文");
  const s3 = await j("/api/legal/laws?query=" + encodeURIComponent("第一条正文") + "&mode=fulltext");
  check("B7c", s3.body.count === 3 && !s3.body.results.some((r) => r.name === "合成坏包法"), "多法命中+坏包法不入聚合");
  const s4 = await j("/api/legal/laws?query=" + encodeURIComponent("合成") + "&mode=title&category=" + encodeURIComponent("caaa0000000000000000000000000ca1"));
  check("B7d", s4.body.count === 2, "category 过滤");
  const s5 = await j("/api/legal/laws?query=&mode=title");
  check("B7e", s5.body.count === 0, "空查询=空结果");
  const s6 = await j("/api/legal/laws?query=&mode=title&level=" + encodeURIComponent("法律"));
  check("B7f", s6.body.count === 5, "level 过滤=阶位分组浏览承载（A2/对拍 1 双分组同构）", JSON.stringify(s6.body.count));
  const s7 = await j("/api/legal/laws?query=&mode=title&level=" + encodeURIComponent("宪法"));
  check("B7g", s7.body.count === 0, "level 无命中=空列表");

  // B8 详情（带行号/效力/meta 形态）+ 404 + 422 具名违规
  const d1 = await j("/api/legal/laws/a00000000000000000000000000000a1");
  check("B8a", d1.status === 200 && d1.body.content?.titles?.[0] === "合成测试法"
    && d1.body.content?.info?.some((kv) => kv.key === "制定机关")
    && d1.body.content?.sections?.[0]?.level === 2
    && d1.body.content?.paragraphs?.[0]?.line >= 7
    && d1.body.content?.toc?.length === 1, "详情：titles/info/sections/toc/paragraphs 带行号", JSON.stringify(d1.body.content?.titles));
  check("B8b", d1.body.law?.effect === "current" && d1.body.law?.publishShow === false, "现行法 effect=current；ver=1 不显公布日（双条件）");
  const d2 = await j("/api/legal/laws/a00000000000000000000000000000a2");
  check("B8c", d2.body.law?.effect === "repealed" && d2.body.law?.publishShow === true, "已废法 effect=repealed；ver>1 且 publish 非空→显公布日");
  const d3 = await j("/api/legal/laws/a00000000000000000000000000000a3");
  check("B8d", d3.body.law?.effect === "not_yet", "未施行 effect=not_yet");
  const d4 = await j("/api/legal/laws/no-such-id");
  check("B8e", d4.status === 404 && /不存在/.test(d4.body.error?.message ?? ""), "未知法 404");
  const d5 = await j("/api/legal/laws/c00000000000000000000000000000c1");
  check("B8f", d5.status === 422 && d5.body.error?.violations?.[0]?.type === "INFO_END_MISSING"
    && d5.body.error?.lawId === "c00000000000000000000000000000c1", "契约违规 422 具名报错（法 ID+类型+行号）", JSON.stringify(d5.body.error));

  // B9 修正案解析经桥（- 续行）
  const d6 = await j("/api/legal/laws/b00000000000000000000000000000b2");
  check("B9", d6.status === 200 && d6.body.content?.paragraphs?.[0]?.text === "一、第一处修改：续行接上。", "修正案模式 - 行续拼经桥解析");

  // B10 篇内过滤（服务端做；保留含命中的节；零命中空列表）
  const f1 = await j("/api/legal/laws/a00000000000000000000000000000a1?q=" + encodeURIComponent("合成墨线"));
  check("B10a", f1.body.hitCount === 1 && f1.body.paragraphs?.[0]?.text.includes("合成墨线") && f1.body.sections?.length === 1, "命中段+保留节");
  const f2 = await j("/api/legal/laws/a00000000000000000000000000000a1?q=" + encodeURIComponent("不存在的词组"));
  check("B10b", f2.body.hitCount === 0 && f2.body.paragraphs?.length === 0 && f2.body.firstHitLine === null, "全不命中=空列表（UI 空态占位承接）");

  // B11 搜索历史：落库/同词刷新不新增/空文本不落/独立域隔离/单删/清空
  await post("/api/legal/laws/history", { text: "合成测试", scope: "shared" });
  const h1r = await post("/api/legal/laws/history", { text: "合成测试", scope: "shared" });
  const h1 = await j("/api/legal/laws/history?scope=shared");
  check("B11a", h1r.body.refreshed === true && h1.body.items?.length === 1, "同词重复提交=刷新时间戳不新增");
  const h2r = await post("/api/legal/laws/history", { text: "  ", scope: "shared" });
  check("B11b", h2r.body.stored === false, "空文本不落库");
  await post("/api/legal/laws/history", { text: "贝塔词", scope: "standalone", lawId: "a00000000000000000000000000000a1" });
  const h2 = await j("/api/legal/laws/history?scope=standalone&lawId=a00000000000000000000000000000a1");
  const h3 = await j("/api/legal/laws/history?scope=shared");
  check("B11c", h2.body.items?.length === 1 && h3.body.items?.length === 1, "共享/独立两制隔离");
  await post("/api/legal/laws/history/delete", { rowId: h2.body.items[0].rowId });
  const h4 = await j("/api/legal/laws/history?scope=standalone&lawId=a00000000000000000000000000000a1");
  check("B11d", h4.body.items?.length === 0, "单条删除");
  await post("/api/legal/laws/history/clear", { scope: "shared" });
  const h5 = await j("/api/legal/laws/history?scope=shared");
  check("B11e", h5.body.items?.length === 0, "清空");

  // B12 收藏：夹 CRUD+级联+无幂等+整法开关+移动
  const fA = await post("/api/legal/laws/favorites/folders", { action: "create", name: "合成甲夹" });
  const fB = await post("/api/legal/laws/favorites/folders", { action: "create", name: "合成乙夹" });
  check("B12a", fA.body.id && fB.body.id, "新建两夹");
  await post("/api/legal/laws/favorites/content", { lawId: "a00000000000000000000000000000a1", line: 8, folderId: fA.body.id });
  await post("/api/legal/laws/favorites/content", { lawId: "a00000000000000000000000000000a1", line: 8, folderId: fA.body.id }); // 重复收藏同夹
  let fav = await j("/api/legal/laws/favorites");
  check("B12b", fav.body.contents?.length === 2, "无幂等：重复收藏=重复条目（等量竞品）");
  await post("/api/legal/laws/favorites/folders", { action: "rename", folderId: fA.body.id, name: "合成甲夹改" });
  const t1 = await post("/api/legal/laws/favorites/law/toggle", { lawId: "a00000000000000000000000000000a1" });
  const tState = await j("/api/legal/laws/favorites/law?lawId=a00000000000000000000000000000a1");
  check("B12c", t1.body.favorited === true && tState.body.favorited === true, "整法收藏开+回读");
  const t2 = await post("/api/legal/laws/favorites/law/toggle", { lawId: "a00000000000000000000000000000a1" });
  check("B12d", t2.body.favorited === false, "整法收藏关（toggle）");
  await post("/api/legal/laws/favorites/content/move", { rowIds: [fav.body.contents[0].rowId], folderId: fB.body.id });
  fav = await j("/api/legal/laws/favorites");
  check("B12e", fav.body.folders?.[0]?.name === "合成甲夹改" && fav.body.contents.filter((c) => c.folderId === fB.body.id).length === 1, "改名持久+跨夹移动");
  const del = await post("/api/legal/laws/favorites/folders", { action: "delete", folderId: fB.body.id });
  fav = await j("/api/legal/laws/favorites");
  check("B12f", del.body.deletedContents >= 1 && fav.body.contents?.length === 1, "删夹级联连删夹内收藏");
  const fC = await post("/api/legal/laws/favorites/folders", { action: "create", name: "合成丙夹" });
  await post("/api/legal/laws/favorites/folders", { action: "reorder", orderedIds: [fC.body.id, fA.body.id] });
  fav = await j("/api/legal/laws/favorites");
  check("B12g", fav.body.folders?.[0]?.id === fC.body.id && fav.body.folders?.[1]?.id === fA.body.id, "拖拽排序持久");

  // B13 包管理面：列表态/延迟删除标记/撤销
  const p1 = await j("/api/legal/packs");
  check("B13a", p1.body.packs?.length === 4 && p1.body.packs.every((p) => p.hash !== "" || p.state === "error"), "包列表（四字段+状态）");
  await post("/api/legal/packs/delete", { name: "beta" });
  check("B13b", existsSync(join(packsRoot, "beta.delete")) && existsSync(join(packsRoot, "beta")), "删除=只写 .delete 标记不立即删（等量 E7）");
  const p2 = await j("/api/legal/packs");
  check("B13c", p2.body.packs.find((p) => p.name === "beta")?.state === "deleted", "标记后包态=deleted");
  await post("/api/legal/packs/revert", { name: "beta" });
  check("B13d", !existsSync(join(packsRoot, "beta.delete")), "撤销删除标记");

  console.log(`[lawbook-synth] 桥面 ${passed + failed} 查完成`);
} catch (e) {
  fail("BRIDGE", e.message);
} finally {
  // ── 收场：只杀自家桥（杀前核验命令行），清库文件与临时目录 ──
  if (bridgePid) {
    if (!commandLineLooksLikeBridge(bridgePid)) {
      console.error(`[lawbook-synth] 拒绝杀 pid=${bridgePid}（命令行不含 bridge_host.mjs，宁停不误杀）`);
    } else {
      spawnSync("taskkill", ["/PID", String(bridgePid), "/F", "/T"], { timeout: 15000 });
      const deadline = Date.now() + 20000;
      while (Date.now() < deadline) {
        const r = spawnSync("netstat", ["-ano"], { encoding: "utf-8", timeout: 15000 });
        if (!new RegExp(`\\sTCP\\s+\\S*:${BRIDGE_PORT}\\s+\\S+\\s+LISTENING`).test(String(r.stdout ?? ""))) break;
        await new Promise((res) => setTimeout(res, 500));
      }
    }
  }
  cleanupBridgeFiles();
  try { rmSync(scratch, { recursive: true, force: true }); } catch { /* 尽力而为 */ }
}

console.log(`[lawbook-synth] ${passed} passed, ${failed} failed`);
if (failed > 0) { console.log("LAWBOOK_SYNTH_FAIL"); process.exit(1); }
console.log("LAWBOOK_SYNTH_PASS");
process.exit(0);
