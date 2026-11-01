// 功能 #31 支持通道（RE-31 §3 实现规格·自研）：工单 + 授权诊断包 + 无运营平台降级形态。
// 三条线（§3.4 差异裁决）：有 opsApi 配置 → 全自动 POST（形状等量竞品端点：POST /support/tickets、
// GET /support/tickets?requester=（x-ticket-key 头）、POST /support/diagnostics）；无任何配置 → 降级
// 形态=纯本地操作（工单 Markdown 落盘 + 诊断包 JSON 交渲染层导出），不受 #9 隐身模式约束；
// 隐身闸只断"有配置的自动上传"（§3.2 出站闸）。
// 等量边界（RE-31 §1/§2）：工单/诊断线 fetch 无显式超时无重试（A8 等量；60s 兜底=渲染层计时器，
// A18 不向桥传取消）；app_version 取真版本不复刻 B16 漂移；诊断包只嵌 license state/reason 两键
// （B19 等量），table_counts 对桥内五存储面计数（表缺失/查询失败={} 静默降级，B18 等量）。
// 测试覆盖口径（先例=BRIDGE_LICENSE_FILE）：BRIDGE_SUPPORT_ROOT / BRIDGE_OPS_CONFIG_FILE 仅测试
// 覆盖用，产线不设即落 %APPDATA%\Juscite 分区（红线：只碰 Juscite）。
import { randomBytes } from "node:crypto";
import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { readLicenseShape } from "./license_shape.mjs";

const REPO_ROOT = fileURLToPath(new URL("../../", import.meta.url)); // tools/bridge/ → 仓库根

// ── 路径口径（与 license_shape.mjs:24-28 同款：APPDATA env 优先、homedir 回退；测试可整体覆盖）──
function jusciteAppDataDir() {
  const appData = process.env.APPDATA ?? join(homedir(), "AppData", "Roaming");
  return join(appData, "Juscite");
}
export function supportRootDir() {
  return process.env.BRIDGE_SUPPORT_ROOT || join(jusciteAppDataDir(), "support");
}
export function opsConfigFilePath() {
  return process.env.BRIDGE_OPS_CONFIG_FILE || join(jusciteAppDataDir(), "ops-config.json");
}

// ── app_version：桌面端 spawn 经 JUSCITE_APP_VERSION 传 app.getVersion()（不复刻 B16 硬编码漂移）；
// 独立跑桥（合成自测/dev 裸桥）回退读仓库根 package.json version；再不行 "unknown"（诚实占位）。──
export function appVersionOf() {
  const env = process.env.JUSCITE_APP_VERSION;
  if (typeof env === "string" && env.trim()) return env.trim();
  try {
    const pkg = JSON.parse(readFileSync(join(REPO_ROOT, "package.json"), "utf-8"));
    if (typeof pkg?.version === "string" && pkg.version.trim()) return pkg.version.trim();
  } catch { /* 布局缺文件 → 占位 */ }
  return "unknown";
}

// ── C27 等量（差异=无默认远端）：env JUSCITE_SUPPORT_OPS_API > ops-config.json（{"opsApi": <base>}）
// > 无任何配置=null（降级形态）。env 与文件两来源剥尾斜杠（C27 同款 replace(/\/+$/,'')）；
// 坏 JSON/空值/非字符串 → 该来源跳过（静默落下一层，最终无配置=降级，不抛）。──
export function resolveOpsBase({ env = process.env, configFile = opsConfigFilePath(), readFile = readFileSync } = {}) {
  const strip = (s) => s.replace(/\/+$/, "");
  const fromEnv = typeof env.JUSCITE_SUPPORT_OPS_API === "string" ? env.JUSCITE_SUPPORT_OPS_API.trim() : "";
  if (fromEnv) return { opsApi: strip(fromEnv), source: "env" };
  try {
    if (existsSync(configFile)) {
      const doc = JSON.parse(readFile(configFile, "utf-8"));
      const v = typeof doc?.opsApi === "string" ? doc.opsApi.trim() : "";
      if (v) return { opsApi: strip(v), source: "file" };
    }
  } catch { /* 坏配置 → 视同无文件层，落降级 */ }
  return { opsApi: null, source: "none" };
}

// ── 工单密钥（A6 等量生成规则）：randomBytes(24) → base64url 32 字符。──
export function generateTicketKey() {
  return randomBytes(24).toString("base64url");
}

// ── E31 文件名时间戳：UTC ISO 压缩形（含毫秒），如 20261027T083012456Z。──
export function timestampCompact(now = new Date()) {
  return now.toISOString().replace(/[-:]/g, "").replace(/\.\d{3}Z$/, (m) => m.slice(1)); // 20261027T083012.456Z → 083012456Z
}

function singleLine(v) {
  return String(v).replace(/[\r\n]+/g, " ").trim();
}

// ── §3.5 降级工单 Markdown：头部元数据（HTML 注释包裹、key: value 机器可解析）+ 正文。
// 元数据字段固定 7 项（requester/ticket_key/subject/created_at/app_version/platform/arch）；
// 值单行化防断行注入破坏解析；正文=主题+描述原文（描述空=标题行保留、内容留空）。──
export function buildTicketMarkdown({ requester, ticketKey, subject, content, createdAtIso, appVersion, platform, arch }) {
  const meta = [
    `requester: ${singleLine(requester)}`,
    `ticket_key: ${singleLine(ticketKey)}`,
    `subject: ${singleLine(subject)}`,
    `created_at: ${singleLine(createdAtIso)}`,
    `app_version: ${singleLine(appVersion)}`,
    `platform: ${singleLine(platform)}`,
    `arch: ${singleLine(arch)}`,
  ].join("\n");
  const body = [
    `# ${singleLine(subject)}`,
    "",
    "## 问题描述",
    "",
    String(content ?? ""),
    "",
  ].join("\n");
  return `<!-- juscite-support-ticket\n${meta}\n-->\n\n${body}`;
}

// E38 解析：从 Markdown 头部元数据读字段（容错：缺键=null；值单行化后的原文）。
export function parseTicketMarkdown(text) {
  const out = { requester: null, ticketKey: null, subject: null, createdAt: null, appVersion: null, platform: null, arch: null };
  if (typeof text !== "string") return out;
  const m = /<!--\s*juscite-support-ticket\s*\n([\s\S]*?)-->/.exec(text);
  if (!m) return out;
  for (const line of m[1].split(/\r?\n/)) {
    const kv = /^([a-zA-Z_]+):\s?(.*)$/.exec(line);
    if (!kv) continue;
    const v = kv[2].trim();
    if (kv[1] === "requester") out.requester = v || null;
    else if (kv[1] === "ticket_key") out.ticketKey = v || null;
    else if (kv[1] === "subject") out.subject = v || null;
    else if (kv[1] === "created_at") out.createdAt = v || null;
    else if (kv[1] === "app_version") out.appVersion = v || null;
    else if (kv[1] === "platform") out.platform = v || null;
    else if (kv[1] === "arch") out.arch = v || null;
  }
  return out;
}

// ── E31/E32：目录不存在递归建；文件名 UTC 毫秒时间戳；撞名追加 -2/-3… 序号不覆盖。──
export function writeTicketFile({ rootDir = supportRootDir(), markdown, now = new Date(), writeFile = writeFileSync } = {}) {
  try {
    mkdirSync(rootDir, { recursive: true }); // E31
  } catch (e) {
    // E33：建目录失败同写失败——错误含目标完整路径，渲染层保留表单可重试
    throw new Error(`工单落盘失败：${e?.message ?? e}（目标：${rootDir}）`);
  }
  const base = `ticket-${timestampCompact(now)}`;
  let fileName = `${base}.md`;
  for (let n = 2; existsSync(join(rootDir, fileName)); n += 1) {
    if (n > 1000) throw new Error(`工单落盘失败：目录内撞名序号耗尽（${rootDir}）`);
    fileName = `${base}-${n}.md`;
  }
  const path = join(rootDir, fileName);
  try {
    writeFile(path, markdown, "utf-8");
  } catch (e) {
    // E33：错误含目标完整路径，渲染层保留表单可重试
    throw new Error(`工单落盘失败：${e?.message ?? e}（目标：${path}）`);
  }
  return { path, fileName };
}

// ── E38 降级列表：枚举 ticket-*.md，按文件名时间戳倒序；主题解析自头部元数据。
// 目录不存在/枚举失败 → { rows: [], error }（渲染层空列表+一次性提示，落空对拍 34「本地面可提示」）。
// 时间戳以文件名为准（E38「文件名时间戳倒序」）；跨桶可见为有意差异（RE-31 §2 E38）：按文件全域
// 枚举、不按 requester 过滤。──
export function listLocalTickets({ rootDir = supportRootDir(), readText = (p) => readFileSync(p, "utf-8") } = {}) {
  let names;
  try {
    if (!existsSync(rootDir)) return { rows: [], error: "support_dir_absent" };
    names = readdirSync(rootDir);
  } catch (e) {
    return { rows: [], error: `枚举失败：${e?.message ?? e}` };
  }
  const rows = [];
  for (const name of names) {
    const m = /^ticket-(\d{8}T\d{9}Z)(?:-\d+)?\.md$/.exec(name);
    if (!m) continue;
    const path = join(rootDir, name);
    let subject = null;
    try {
      subject = parseTicketMarkdown(readText(path)).subject;
    } catch { /* 单文件不可读：保留条目、主题空（时间戳来自文件名） */ }
    rows.push({ fileName: name, createdAt: m[1], subject, path });
  }
  rows.sort((a, b) => (a.createdAt < b.createdAt ? 1 : a.createdAt > b.createdAt ? -1 : 0));
  return { rows, error: null };
}

// ── B15/B17-B20 诊断包：9 键固定键序 JSON。table_counts=桥内五存储面 COUNT(*)（B18：任一查询
// 抛错或库缺失 → {} 静默降级，包照常出）；license 只嵌 state/reason（B19）；agent_status/note 自写。──
const DIAGNOSTIC_TABLES = [
  ["case_board_cases", "cases"],
  ["document_chunks", "documents"],
  ["demo_evidence", "evidence"],
  ["case_board_events", "schedules"],
  ["audit_log", "audit"],
];
export function buildSupportDiagnostics({ appVersion = appVersionOf(), license = readLicenseShape(), db = null, now = new Date(), platform = process.platform, arch = process.arch } = {}) {
  let tableCounts = {};
  if (db) {
    try {
      tableCounts = {};
      for (const [table, key] of DIAGNOSTIC_TABLES) {
        const row = db.prepare(`SELECT COUNT(*) AS n FROM ${table}`).get();
        tableCounts[key] = Number(row?.n ?? 0);
      }
    } catch {
      tableCounts = {}; // B18 等量：表缺失/查询抛错 → {} 静默降级
    }
  }
  // 键序=RE-31 §3.1 固定 9 键（等量 B15）
  return {
    payload: {
      app_version: appVersion,
      platform,
      arch,
      generated_at: now.toISOString(),
      license_state: license.state,
      license_reason: license.reason,
      agent_status: "见运行日志",
      table_counts: tableCounts,
      note: "诊断包只含版本、平台与各数据面条数统计，不含案件内容与材料。",
    },
  };
}
export function buildSupportDiagnosticsJson(params) {
  return JSON.stringify(buildSupportDiagnostics(params).payload);
}
