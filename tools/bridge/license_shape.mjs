// 【步骤5·F78/F79 许可骨架】许可文件读取与形态判定（RE-B3 · 自研设计 · 骨架级）。
// 许可文件不是凭据：内容只是形态开关（H1-H11 布尔位），无密钥、无签名、无网络。
// 三态（fail-closed）：无文件 | 损坏（JSON 解析失败 / 结构非法 / 未知模块键 / 非 ISO 日期 /
//   未生效 / 过期 / 不可读）→ 一律全基础形态（免费层全开、高级模块门全关），
//   不抛异常、不阻断启动；有效 → 形态判定表按文件开关位读出。
// 付费实体全挂起：开关只做判定输出，不接任何功能。
// 边界（本骨架明确不做，随 v2 商业化另单，回收点=tools/recon/PENDING_OWNER_f78_f79_license_recon.py 面）：
//   Ed25519 离线验签 / 在线激活 / 宽限预算 / 时钟回拨反制——上一代 V7 recon 资产只作形态参照，不接码。
import { existsSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

export const LICENSE_SCHEMA = "juscite-license/1";
// 高级模块开关位=功能账 §二付费层 H1-H11（全 ⏸ 挂起中；骨架只出判定表，不消费）。
export const LICENSE_MODULE_IDS = ["H1", "H2", "H3", "H4", "H5", "H6", "H7", "H8", "H9", "H10", "H11"];

// 许可文件路径：%APPDATA%\Juscite\license\license.json（路径钉死 Juscite 分区）。
// %APPDATA% 解析口径与桌面端单一口径一致（packages/desktop/src/main/desktopHostProcess.ts:81
// resolveOc28RegistrationFile 同款）：process.env.APPDATA 优先、homedir() 回退——APPDATA 重定向
// （漫游配置/便携）时许可与 oc28 注册文件同迁，不读错位（复核 M1 落实）。
// BRIDGE_LICENSE_FILE 可整体覆盖文件路径——仅测试覆盖用（先例=BRIDGE_LEARNING_ROOT，红线：只碰
// Juscite 分区）。放行条件③（RE-B3 §5）：v2 验签落地同单收掉本覆盖的产线可达（桌面端 spawn
// env 全量继承，desktopHostProcess.ts:186-190，不收即成旁路钩子）。
export function licenseFilePath() {
  const appData = process.env.APPDATA ?? join(homedir(), "AppData", "Roaming");
  return process.env.BRIDGE_LICENSE_FILE
    || join(appData, "Juscite", "license", "license.json");
}

function baseModules() {
  return Object.fromEntries(LICENSE_MODULE_IDS.map((id) => [id, false]));
}

// 严格 ISO-8601 日期：YYYY-MM-DD[Thh:mm[:ss[.fraction]][Z|±hh[:mm]]]（复核 L2 落实：
// 拒收 "2026/01/01"、纯数字 epoch 等宽松形态；数值/乱码经 typeof 即拒）。
// 复核缺口2 落实（分量回环比对）：V8 对越界日滚动翻转（"2026-02-30"→滚成 2026-03-02，
// NaN 兜不住），正则放行后必须逐分量核对——回环帧=字符串书写帧：date-only 与 "Z" 按
// 解析标准即 UTC；显式偏移按该偏移平移后取 UTC 分量；无时区 datetime 按本地时区解析
// （JS 标准双轨语义，签发方指引记档 RE-B3 §3.2）→本地分量。
function isIsoDateString(v) {
  const m = typeof v === "string"
    ? /^(\d{4})-(\d{2})-(\d{2})(?:[T\s](\d{2}):(\d{2})(?::(\d{2})(?:\.\d{1,9})?)?(Z|[+-]\d{2}:?\d{2})?)?$/.exec(v)
    : null;
  if (!m) return false;
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return false;
  let got;
  if (m[4] === undefined || m[7] === "Z") {
    got = [d.getUTCFullYear(), d.getUTCMonth() + 1, d.getUTCDate(), d.getUTCHours(), d.getUTCMinutes(), d.getUTCSeconds()];
  } else if (m[7] !== undefined) {
    const hm = m[7].slice(1).replace(":", "");
    const off = (m[7][0] === "-" ? -1 : 1) * (Number(hm.slice(0, 2)) * 60 + Number(hm.slice(2)));
    const w = new Date(d.getTime() + off * 60000);
    got = [w.getUTCFullYear(), w.getUTCMonth() + 1, w.getUTCDate(), w.getUTCHours(), w.getUTCMinutes(), w.getUTCSeconds()];
  } else {
    got = [d.getFullYear(), d.getMonth() + 1, d.getDate(), d.getHours(), d.getMinutes(), d.getSeconds()];
  }
  const want = [Number(m[1]), Number(m[2]), Number(m[3]), Number(m[4] ?? 0), Number(m[5] ?? 0), Number(m[6] ?? 0)];
  return got.every((g, i) => g === want[i]);
}

// 结构校验：返回 null=合法，否则返回损坏/未生效原因（schema_invalid | not_yet_valid | expired）。
// 严格模式：未知模块键、非布尔开关位、缺 modules、schema 不符、纯空白 licenseId——一律 fail-closed。
// 复核 L5 钉死：本函数不得引入可抛调用（现状全输入零抛点，对抗用例在案）；调用侧另有 catch 兜底，
//   两道闸共同保「许可任何态不阻断启动」（RE-B3 §3.4）。
function schemaCheck(doc, now) {
  if (typeof doc !== "object" || doc === null || Array.isArray(doc)) return "schema_invalid";
  if (doc.schema !== LICENSE_SCHEMA) return "schema_invalid";
  // 复核缺口1 落实：licenseId 字符白名单（[A-Za-z0-9._-]{1,128}，与 bridge_host.mjs:4758 同款）——
  // 此前只验长度/空白，含 \n 的 id 判 valid 进启动日志可伪造独立 [license] 行（日志注入面）。
  if (typeof doc.licenseId !== "string" || !/^[A-Za-z0-9._-]{1,128}$/.test(doc.licenseId)) return "schema_invalid";
  if (typeof doc.modules !== "object" || doc.modules === null || Array.isArray(doc.modules)) return "schema_invalid";
  for (const [k, v] of Object.entries(doc.modules)) {
    if (!LICENSE_MODULE_IDS.includes(k) || typeof v !== "boolean") return "schema_invalid";
  }
  if (!isIsoDateString(doc.issuedAt)) return "schema_invalid";
  if (new Date(doc.issuedAt).getTime() > now.getTime()) return "not_yet_valid";
  // expiresAt 可选；显式 null 视同缺省（签发方注意项收口，RE-B3 §3.2）。
  if (doc.expiresAt !== undefined && doc.expiresAt !== null) {
    if (!isIsoDateString(doc.expiresAt)) return "schema_invalid";
    if (new Date(doc.expiresAt).getTime() < now.getTime()) return "expired";
  }
  return null;
}

// 读许可文件 → 形态判定。任何输入（缺文件/坏字节/坏结构/未生效/过期/不可读）都不抛异常。
// 判定表形状：{ state: "base"|"valid", tier: "base"|"advanced", reason, path, modules(全 H1-H11), licenseId, expiresAt }
//   state=文件读取结论；tier=产品形态（base=全基础形态免费层全开；advanced=文件声明高级位）。
//   modules 恒为完整 H1-H11 表：base 态全 false；valid 态=文件开关位读出，缺键=false。
//   licenseId/expiresAt 仅在 valid 态回读（本地日志用，非凭据）；wire 面只出 state/tier/reason/modules。
export function readLicenseShape({ path = licenseFilePath(), now = new Date() } = {}) {
  const base = { state: "base", tier: "base", reason: "no_license_file", path, modules: baseModules(), licenseId: null, expiresAt: null };
  let raw;
  try {
    if (!existsSync(path)) return base;
    raw = readFileSync(path, "utf-8");
  } catch {
    return { ...base, reason: "read_failed" };
  }
  let doc;
  try {
    // UTF-8 BOM 剥除：Windows 记事本系编辑器写 JSON 常带 BOM，剥除防「放了文件仍基础形态」排障坑（复核 L3 落实）。
    doc = JSON.parse(raw.replace(/^\uFEFF/, ""));
  } catch {
    return { ...base, reason: "json_parse_failed" };
  }
  let bad;
  try {
    bad = schemaCheck(doc, now);
  } catch {
    bad = "schema_invalid"; // 复核 L5：判定链任何未来意外抛点也 fail-closed，许可任何态不阻断启动
  }
  if (bad) return { ...base, reason: bad };
  const modules = baseModules();
  for (const [k, v] of Object.entries(doc.modules)) modules[k] = v === true;
  return {
    state: "valid",
    tier: "advanced",
    reason: "ok",
    path,
    modules,
    licenseId: doc.licenseId,
    expiresAt: doc.expiresAt ?? null,
  };
}
