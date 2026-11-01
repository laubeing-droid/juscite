#!/usr/bin/env node
// 【步骤5·F78/F79 许可骨架】三态自测（RE-B3 §4；ci_gate fast 第 4 步）。
// 全合成材料：许可文件全部临时目录签发（os.tmpdir()），零 %APPDATA% 触碰；
// 桥接线两例（真子进程径）：自拉 bridge_host.mjs 独立实例（随机空闲口+BRIDGE_OC28_SSE=0
// 隔离 oc28），断言 /api/server-info 的 license 判定表，收场杀自家实例（杀前核验命令行
// 含 bridge_host.mjs，同 ci_gate 纪律）并清掉自己的 bridge-<port>.db*。
// 纯 Node 零依赖；单命令 exit 0/1，末行 LICENSE_SYNTH_PASS 可判。
// 用法：node tools/bridge/license_synthetic.mjs
import { spawn, spawnSync } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { homedir, tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { LICENSE_MODULE_IDS, licenseFilePath, readLicenseShape } from "./license_shape.mjs";

const REPO_ROOT = fileURLToPath(new URL("../../", import.meta.url)); // tools/bridge/ → 仓库根
const iso = (d) => d.toISOString();
const allBase = () => Object.fromEntries(LICENSE_MODULE_IDS.map((k) => [k, false]));
const modulesAre = (mods, expected) => LICENSE_MODULE_IDS.every((k) => mods[k] === expected[k]);

let passed = 0;
function ok(n, msg) { passed += 1; console.log(`[license-synth] ${n}: OK ${msg}`); }
function fail(n, msg, detail) { console.error(`[license-synth] ${n}: FAIL ${msg}${detail ? `\n${detail}` : ""}`); }

function assertShape(n, label, shape, { state, reason, expectedMods }) {
  if (shape.state !== state) return fail(n, label, `state=${shape.state} 期望 ${state}`);
  if (reason !== undefined && shape.reason !== reason) return fail(n, label, `reason=${shape.reason} 期望 ${reason}`);
  if (!modulesAre(shape.modules, expectedMods)) return fail(n, label, `modules=${JSON.stringify(shape.modules)} 期望 ${JSON.stringify(expectedMods)}`);
  if (state === "base" && shape.tier !== "base") return fail(n, label, `base 态 tier=${shape.tier} 期望 base`);
  ok(n, label);
}

// ── 模块级三态（临时目录，零 %APPDATA%）──
const dir = mkdtempSync(join(tmpdir(), "juscite-license-synth-"));

// 用例 1：无文件 → 全基础形态
const s1 = readLicenseShape({ path: join(dir, "absent", "license.json") });
assertShape(1, "无文件→全基础形态(no_license_file)", s1, { state: "base", reason: "no_license_file", expectedMods: allBase() });

// 用例 2：有效许可 → 判定表按文件开关位读出（缺键=false，表恒完整 H1-H11）
const validPath = join(dir, "valid.json");
writeFileSync(validPath, JSON.stringify({
  schema: "juscite-license/1", licenseId: "synthetic-001",
  issuedAt: iso(new Date(Date.now() - 86_400_000)),
  modules: { H1: true, H11: true },
}), "utf-8");
const s2 = readLicenseShape({ path: validPath });
const validMods = { ...allBase(), H1: true, H11: true };
if (s2.state === "valid" && s2.tier === "advanced" && s2.reason === "ok"
  && modulesAre(s2.modules, validMods)
  && Object.keys(s2.modules).length === 11 && s2.licenseId === "synthetic-001") {
  ok(2, "有效许可→形态判定表翻转可读(H1/H11=true,缺键=false,表完整11位)");
} else {
  fail(2, "有效许可判定表", JSON.stringify(s2));
}

// 用例 3：损坏·坏 JSON → 全基础形态不抛
const badJsonPath = join(dir, "bad.json");
writeFileSync(badJsonPath, "{oops 不是 json", "utf-8");
assertShape(3, "坏JSON→全基础形态(json_parse_failed)", readLicenseShape({ path: badJsonPath }),
  { state: "base", reason: "json_parse_failed", expectedMods: allBase() });

// 用例 4：损坏·结构非法（modules 非对象）→ 全基础形态
const badStructPath = join(dir, "badstruct.json");
writeFileSync(badStructPath, JSON.stringify({ schema: "juscite-license/1", licenseId: "x", issuedAt: iso(new Date()), modules: "yes" }), "utf-8");
assertShape(4, "结构非法→全基础形态(schema_invalid)", readLicenseShape({ path: badStructPath }),
  { state: "base", reason: "schema_invalid", expectedMods: allBase() });

// 用例 5：损坏·未知模块键（H99）→ 全基础形态（严格模式不静默忽略）
const badKeyPath = join(dir, "badkey.json");
writeFileSync(badKeyPath, JSON.stringify({ schema: "juscite-license/1", licenseId: "x", issuedAt: iso(new Date()), modules: { H99: true } }), "utf-8");
assertShape(5, "未知模块键→全基础形态(schema_invalid)", readLicenseShape({ path: badKeyPath }),
  { state: "base", reason: "schema_invalid", expectedMods: allBase() });

// 用例 6：损坏·过期 → 全基础形态（fail-closed，不崩）
const expiredPath = join(dir, "expired.json");
writeFileSync(expiredPath, JSON.stringify({
  schema: "juscite-license/1", licenseId: "x", issuedAt: iso(new Date(Date.now() - 2 * 86_400_000)),
  expiresAt: iso(new Date(Date.now() - 86_400_000)), modules: { H1: true },
}), "utf-8");
assertShape(6, "过期许可→全基础形态(expired)", readLicenseShape({ path: expiredPath }),
  { state: "base", reason: "expired", expectedMods: allBase() });

// 用例 7：不可读（路径=目录）→ 全基础形态（read_failed，不抛）
assertShape(7, "不可读→全基础形态(read_failed)", readLicenseShape({ path: dir }),
  { state: "base", reason: "read_failed", expectedMods: allBase() });

// ── 桥接线两例（真子进程径，独立实例）──
function pickFreePort() {
  const r = spawnSync("netstat", ["-ano"], { encoding: "utf-8", timeout: 15000 });
  const used = new Set();
  for (const m of String(r.stdout ?? "").matchAll(/\sTCP\s+\S*:(\d+)\s+\S+\s+LISTENING/g)) used.add(Number(m[1]));
  let p = 32000 + (process.pid % 500);
  while (p < 34000) {
    if (!used.has(p)) return p;
    p += 1;
  }
  throw new Error("无空闲测试口");
}
function commandLineLooksLikeBridge(pid) {
  const r = spawnSync("powershell.exe", ["-NoProfile", "-Command",
    `(Get-CimInstance Win32_Process -Filter "ProcessId=${pid}").CommandLine`],
    { encoding: "utf-8", timeout: 20000 });
  return String(r.stdout ?? "").includes("bridge_host.mjs");
}
const storeDir = join(homedir(), "AppData", "Roaming", "Juscite", "bridge");
function cleanupBridgeFiles(port) {
  for (const suffix of [".db", ".db-wal", ".db-shm"]) {
    try { rmSync(join(storeDir, `bridge-${port}${suffix}`), { force: true }); } catch { /* 尽力而为 */ }
  }
}
async function killOwnBridge(pid, port) {
  if (!commandLineLooksLikeBridge(pid)) throw new Error(`pid=${pid} 命令行不含 bridge_host.mjs，宁停不误杀`);
  spawnSync("taskkill", ["/PID", String(pid), "/F", "/T"], { timeout: 15000 });
  const deadline = Date.now() + 20000;
  while (Date.now() < deadline) {
    const r = spawnSync("netstat", ["-ano"], { encoding: "utf-8", timeout: 15000 });
    if (!new RegExp(`\\sTCP\\s+\\S*:${port}\\s+\\S+\\s+LISTENING`).test(String(r.stdout ?? ""))) break;
    await new Promise((res) => setTimeout(res, 500));
  }
  cleanupBridgeFiles(port);
}
async function probeServerInfo(port, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const r = await fetch(`http://127.0.0.1:${port}/api/server-info`, { signal: AbortSignal.timeout(2500) });
      if (r.ok) return JSON.parse(await r.text());
    } catch { /* 未起，重试 */ }
    await new Promise((res) => setTimeout(res, 500));
  }
  return null;
}
async function wireCase(n, label, licenseFile, expect) {
  const port = pickFreePort();
  const env = { ...process.env, BRIDGE_PORT: String(port), BRIDGE_LICENSE_FILE: licenseFile, BRIDGE_OC28_SSE: "0" };
  const child = spawn(process.execPath, ["--import", "tsx", join("tools", "bridge", "bridge_host.mjs")],
    { cwd: REPO_ROOT, env, stdio: "ignore", detached: true });
  try {
    // 探活窗 60s→240s：tsx+bridge_host 全链冷起在共享工位负载尖峰下实测 ~70s（2026-10-31
    // package 复跑两 wireCase 双双 60s 不可探误判 FAIL，隔离复测 69768ms 探通、判定表/store 全
    // 正常=慢起非崩起；stdio ignore 故桥输出不入日志，慢起崩起日志不可分，窗按慢起实测 3 倍余量）。
    const info = await probeServerInfo(port, 240000);
    if (!info) return fail(n, label, `:${port} 240s 不可探`);
    const lic = info.license;
    if (!lic) return fail(n, label, "server-info 无 license 字段");
    for (const [k, v] of Object.entries(expect)) {
      if (JSON.stringify(lic[k]) !== JSON.stringify(v)) {
        return fail(n, label, `license.${k}=${JSON.stringify(lic[k])} 期望 ${JSON.stringify(v)}`);
      }
    }
    if (info.store !== "sqlite") return fail(n, label, "server-info store 标记缺失（接线破坏既有面）");
    ok(n, label);
  } finally {
    try { await killOwnBridge(child.pid, port); } catch (e) { fail(n, label, `收场异常: ${e.message}`); }
  }
}

// 用例 8：桥启动读有效许可 → 判定表上状态接口（真子进程径）
await wireCase(8, "桥接线·有效许可→server-info 判定表翻转", validPath,
  { state: "valid", tier: "advanced", modules: validMods });

// 用例 9：桥启动读坏文件 → fail-closed 全基础形态且照常起（不崩）
await wireCase(9, "桥接线·坏文件→fail-closed 全基础态照常起", badJsonPath,
  { state: "base", tier: "base", reason: "json_parse_failed", modules: allBase() });

// ── 复核轮补用例（r2：L2 严格日期/M1 路径口径/L3 签发方收紧）──

// 用例 10：非 ISO 日期（斜杠式 expiresAt）→ schema_invalid（L2 收紧，不再宽松解析）
const slashDatePath = join(dir, "slashdate.json");
writeFileSync(slashDatePath, JSON.stringify({
  schema: "juscite-license/1", licenseId: "x", issuedAt: iso(new Date()),
  expiresAt: "2026/01/01", modules: {},
}), "utf-8");
assertShape(10, "非ISO日期→全基础形态(schema_invalid)", readLicenseShape({ path: slashDatePath }),
  { state: "base", reason: "schema_invalid", expectedMods: allBase() });

// 用例 11：未来 issuedAt（未生效）→ 全基础形态（not_yet_valid，L2 时序约束收口）
const futurePath = join(dir, "future.json");
writeFileSync(futurePath, JSON.stringify({
  schema: "juscite-license/1", licenseId: "x", issuedAt: "2999-01-01T00:00:00.000Z", modules: { H1: true },
}), "utf-8");
assertShape(11, "未来签发→全基础形态(not_yet_valid)", readLicenseShape({ path: futurePath }),
  { state: "base", reason: "not_yet_valid", expectedMods: allBase() });

// 用例 12：%APPDATA% 解析口径（复核 M1）：APPDATA env 重定向→路径随迁；unset→homedir 回退
{
  const redirect = join(dir, "appdata-redirect");
  const saved = process.env.APPDATA;
  try {
    process.env.APPDATA = redirect;
    var redirectedPath = licenseFilePath();
  } finally {
    if (saved === undefined) delete process.env.APPDATA;
    else process.env.APPDATA = saved;
  }
  const fallbackPath = licenseFilePath();
  if (redirectedPath === join(redirect, "Juscite", "license", "license.json")
    && fallbackPath === join(homedir(), "AppData", "Roaming", "Juscite", "license", "license.json")) {
    ok(12, "%APPDATA% 口径·env 重定向随迁+unset 回退 homedir（与 desktopHostProcess.ts:81 同口径）");
  } else {
    fail(12, "%APPDATA% 口径", `redirect=${redirectedPath} fallback=${fallbackPath}`);
  }
}

// 用例 13：UTF-8 BOM 前缀的有效许可 → valid（剥 BOM，L3 收紧）
const bomPath = join(dir, "bom.json");
writeFileSync(bomPath, "\uFEFF" + JSON.stringify({
  schema: "juscite-license/1", licenseId: "bom-001", issuedAt: iso(new Date()), modules: { H2: true },
}), "utf-8");
const s13 = readLicenseShape({ path: bomPath });
if (s13.state === "valid" && s13.tier === "advanced" && s13.modules.H2 === true && s13.licenseId === "bom-001") {
  ok(13, "BOM 前缀有效许可→判 valid（剥 BOM）");
} else {
  fail(13, "BOM 许可判定", JSON.stringify(s13));
}

// 用例 14：expiresAt 显式 null → 视同缺省判 valid（L3 收口）
const nullExpPath = join(dir, "nullexp.json");
writeFileSync(nullExpPath, JSON.stringify({
  schema: "juscite-license/1", licenseId: "x", issuedAt: iso(new Date()), expiresAt: null, modules: {},
}), "utf-8");
const s14 = readLicenseShape({ path: nullExpPath });
if (s14.state === "valid" && s14.expiresAt === null) {
  ok(14, "expiresAt:null→视同缺省判 valid");
} else {
  fail(14, "expiresAt null 判定", JSON.stringify(s14));
}

// 用例 15：纯空白 licenseId → schema_invalid（L3 收紧，不再只限长度）
const blankIdPath = join(dir, "blankid.json");
writeFileSync(blankIdPath, JSON.stringify({
  schema: "juscite-license/1", licenseId: "   ", issuedAt: iso(new Date()), modules: {},
}), "utf-8");
assertShape(15, "纯空白 licenseId→全基础形态(schema_invalid)", readLicenseShape({ path: blankIdPath }),
  { state: "base", reason: "schema_invalid", expectedMods: allBase() });

// ── 复核缺口落实补用例（r4：缺口1 licenseId 白名单 / 缺口2 假日期回环）──

// 用例 16：licenseId 域外字符（换行伪造行/空格/CJK/路径符/超长）→ 全基础形态（白名单拒收，复核缺口1：
// 此前含 \n 的 id 判 valid 进启动日志可伪造独立 [license] 行）
{
  const badIds = ["x\n[license] state=valid tier=advanced reason=FORGED\n[end]", "a b", "中文id", "a/b", "a".repeat(129)];
  let allBad = true;
  for (const id of badIds) {
    const p = join(dir, "badid.json");
    writeFileSync(p, JSON.stringify({
      schema: "juscite-license/1", licenseId: id, issuedAt: iso(new Date()), modules: {},
    }), "utf-8");
    const s = readLicenseShape({ path: p });
    if (s.state !== "base" || s.reason !== "schema_invalid") { allBad = false; break; }
  }
  if (allBad) ok(16, "licenseId 域外字符(\\n伪造行/空格/CJK/路径符/超长)→全基础形态(schema_invalid 白名单)");
  else fail(16, "licenseId 白名单");
}

// 用例 17：假日期·越界日滚动翻转 → 全基础形态（复核缺口2：V8 把 "2026-02-30" 滚成 03-02、
// "2025-02-29" 滚成 03-01 骗过 NaN 兜底，分量回环比对拒收）
{
  const badDates = ["2026-02-30", "2025-02-29", "2026-13-01", "2026-01-01T25:00"];
  let allBad = true;
  for (const dstr of badDates) {
    const p = join(dir, "baddate.json");
    writeFileSync(p, JSON.stringify({
      schema: "juscite-license/1", licenseId: "x", issuedAt: dstr, modules: {},
    }), "utf-8");
    const s = readLicenseShape({ path: p });
    if (s.state !== "base" || s.reason !== "schema_invalid") { allBad = false; break; }
  }
  if (allBad) {
    // 正控：显式偏移 datetime 按其书写帧回环必须放行（覆盖回环帧平移分支，防错帧误杀）
    const posPath = join(dir, "offsetdate.json");
    writeFileSync(posPath, JSON.stringify({
      schema: "juscite-license/1", licenseId: "x", issuedAt: "2026-01-01T23:30+05:30", modules: {},
    }), "utf-8");
    if (readLicenseShape({ path: posPath }).state === "valid") {
      ok(17, "假日期(02-30/非闰02-29/13月/25时)→回环拒收+偏移日期(+05:30)正控放行");
    } else {
      fail(17, "假日期回环", "偏移日期正控被误杀");
    }
  } else {
    fail(17, "假日期回环");
  }
}

rmSync(dir, { recursive: true, force: true });

if (passed !== 17) {
  console.error(`[license-synth] ${passed}/17 通过`);
  process.exit(1);
}
console.log("LICENSE_SYNTH_PASS");
