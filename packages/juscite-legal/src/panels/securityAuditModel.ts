// 功能 #30 安全审计中心（RE-30 §3.6/§3.7）：面板纯模型——行分类/场景映射/时间格式化/
// 摘要截断/命中 chips/合计，全部确定性函数（法律工作区约束：禁模型猜，正则与查表）。
// 文案一律自写（RE-30 §5 表达隔离）；类目与脱敏规则族的通用 PII 分类对齐。

export type AuditRow = {
  id: string;
  ts: string | null;
  actor: string | null;
  action: string;
  target: string | null;
  detail: string | null;
  prev_hash: string | null;
  hash: string;
};

// 隐私行 detail JSON（RE-30 §3.2 字段面）；敏感原文任何情况下不在此出现
export type PrivacyRedactionDetail = {
  kind: "privacy-redaction";
  requestId?: string;
  scenario?: string;
  provider?: string;
  model?: string;
  policyVersion?: string;
  status?: "success" | "error" | "aborted";
  originalChars?: number;
  outboundChars?: number;
  totalMatches?: number;
  counts?: Record<string, number>;
  toolCalls?: number;
  payloadDigest?: string;
  errorCode?: string;
};

export type AuditTab = "all" | "privacy" | "ops";

// 我方规则族版本常量（对拍 8/26：值+类目数注；随 #8 落地演进）
export const AUDIT_POLICY_VERSION = "juscite-redaction-v1";

// 14 类规则目录（RE-30 §2.4：类目与 #8 规则族对齐，名称+一句说明均自写）
export const REDACTION_RULE_CATALOG: Array<{ id: string; name: string; description: string }> = [
  { id: "person_name", name: "姓名", description: "自然人姓名，含全名与可识别的姓名组合。" },
  { id: "organization", name: "机构名称", description: "公司、机关、团体等组织实体名称。" },
  { id: "case_number", name: "案号", description: "法院案号、仲裁案号等案件编号。" },
  { id: "id_card", name: "身份证号", description: "居民身份证号码。" },
  { id: "mobile", name: "手机号", description: "手机电话号码。" },
  { id: "landline", name: "座机号", description: "固定电话号码（含区号）。" },
  { id: "bank_card", name: "银行卡号", description: "银行账户与银行卡号码。" },
  { id: "email", name: "邮箱", description: "电子邮件地址。" },
  { id: "address", name: "地址", description: "居住地、通讯地址等地理位置信息。" },
  { id: "passport", name: "护照号", description: "护照证件号码。" },
  { id: "credit_code", name: "统一社会信用代码", description: "法人与其他组织的统一社会信用代码。" },
  { id: "vehicle_plate", name: "车牌号", description: "机动车号牌号码。" },
  { id: "secret", name: "密钥令牌", description: "API 密钥、令牌等凭据字符串。" },
  { id: "local_path", name: "本地路径", description: "本机文件路径与目录信息。" },
];

const RULE_NAME_BY_ID = new Map(REDACTION_RULE_CATALOG.map((r) => [r.id, r.name] as const));
const RULE_DESC_BY_ID = new Map(REDACTION_RULE_CATALOG.map((r) => [r.id, r.description] as const));
export function ruleName(id: string): string {
  return RULE_NAME_BY_ID.get(id) ?? id;
}
export function ruleDescription(id: string): string {
  return RULE_DESC_BY_ID.get(id) ?? "自定义规则类目。";
}

// 场景映射（RE-30 §3.2：按 requestId 前缀 9 类；场景名对应我方任务类型，文案自写）
const SCENARIO_NAMES: Record<string, string> = {
  catalog: "证据目录",
  summary: "案件摘要",
  strategy: "策略推演",
  risk: "风险评估",
  drafting: "文书起草",
  trial_brief: "庭审要点",
  case_brief: "案件简报",
  chat: "案件对话",
  autofill: "自动填充",
};
export function scenarioName(key: string): string {
  return SCENARIO_NAMES[key] ?? key;
}
// brief- 前缀族按庭审关键词细分（庭审要点/案件简报）；case_autofill 显式传入优先
export function scenarioKeyOf(requestId: string | null | undefined, explicit?: string): string {
  if (explicit && SCENARIO_NAMES[explicit]) return explicit;
  if (explicit === "case_autofill") return "autofill";
  const rid = typeof requestId === "string" ? requestId : "";
  if (rid.startsWith("catalog-")) return "catalog";
  if (rid.startsWith("sum-") || rid.startsWith("summary")) return "summary";
  if (rid.startsWith("strat-")) return "strategy";
  if (rid.startsWith("risk-")) return "risk";
  if (rid.startsWith("gen-")) return "drafting";
  if (rid.startsWith("brief-")) {
    return /trial|庭审/i.test(rid) ? "trial_brief" : "case_brief";
  }
  return "chat";
}

// 隐私行判定（RE-30 §3.6 等量容错）：action==="privacy.redaction" 且 detail 为 JSON 且
// kind==="privacy-redaction"；解析失败一律回退按操作行渲染。
export function privacyDetailOf(row: AuditRow): PrivacyRedactionDetail | null {
  if (row.action !== "privacy.redaction") return null;
  try {
    const d = JSON.parse(row.detail ?? "") as unknown;
    if (d && typeof d === "object" && (d as { kind?: string }).kind === "privacy-redaction") {
      return d as PrivacyRedactionDetail;
    }
  } catch {
    /* 回退操作行 */
  }
  return null;
}

// 详情有效行回退链（RE-30 §3.7 关键等量）：m = 过滤集.find(id===selectedId) ?? 过滤集[0] ?? null
export function selectEffectiveRow(filtered: AuditRow[], selectedId: string | null): AuditRow | null {
  return filtered.find((r) => r.id === selectedId) ?? filtered[0] ?? null;
}

// 时间显示（RE-30 §2.5）：先试 ISO 再试空格变体，失败原样回退；输出 M/D HH:mm
export function formatAuditTime(ts: string | null | undefined): string {
  if (typeof ts !== "string" || !ts) return "—";
  let d = new Date(ts);
  if (Number.isNaN(d.getTime())) d = new Date(ts.replace(" ", "T"));
  if (Number.isNaN(d.getTime())) return ts;
  const mm = String(d.getMonth() + 1);
  const dd = String(d.getDate());
  const hh = String(d.getHours()).padStart(2, "0");
  const mi = String(d.getMinutes()).padStart(2, "0");
  return `${mm}/${dd} ${hh}:${mi}`;
}

// 安全摘要截断（RE-30 §2.7/对拍 26：仅 length>24 才截断 前12…后8；≤24 原样；空→null）
export function truncateDigest(digest: string | null | undefined): string | null {
  if (typeof digest !== "string" || !digest) return null;
  if (digest.length <= 24) return digest;
  return `${digest.slice(0, 12)}…${digest.slice(-8)}`;
}

export type HitChip = { name: string; count: number };

// 命中 chips（RE-30 §2.5）：按命中数降序取前 3；>3 类折叠为 +N 类；0 命中单独提示
export function hitChipsOf(counts: Record<string, number> | undefined): {
  chips: HitChip[];
  overflow: number;
  zero: boolean;
} {
  const entries = Object.entries(counts ?? {}).filter(([, n]) => Number.isFinite(n) && n > 0);
  const sorted = entries.sort((a, b) => (b[1] - a[1]) || a[0].localeCompare(b[0]));
  const chips = sorted.slice(0, 3).map(([id, count]) => ({ name: ruleName(id), count }));
  return { chips, overflow: Math.max(0, sorted.length - 3), zero: sorted.length === 0 };
}

// 详情命中规则列表（数量+名+说明）
export function hitLinesOf(counts: Record<string, number> | undefined): Array<{
  id: string; count: number; name: string; description: string;
}> {
  return Object.entries(counts ?? {})
    .filter(([, n]) => Number.isFinite(n) && n > 0)
    .sort((a, b) => (b[1] - a[1]) || a[0].localeCompare(b[0]))
    .map(([id, count]) => ({ id, count, name: ruleName(id), description: ruleDescription(id) }));
}

// 摘要卡合计（RE-30 §2.3）：命中总数=totalMatches 优先，缺失按 counts 求和
export function totalHitsOf(rows: AuditRow[]): number {
  let sum = 0;
  for (const row of rows) {
    const d = privacyDetailOf(row);
    if (!d) continue;
    if (typeof d.totalMatches === "number" && Number.isFinite(d.totalMatches)) {
      sum += d.totalMatches;
    } else {
      for (const n of Object.values(d.counts ?? {})) {
        if (typeof n === "number" && Number.isFinite(n)) sum += n;
      }
    }
  }
  return sum;
}

// 操作行 detail 文本摘要（RE-30 §2.5：detail 文本摘要或回退）
export function opsDetailSummary(row: AuditRow): string {
  const text = typeof row.detail === "string" ? row.detail.trim() : "";
  if (!text) return "无补充说明";
  return text.length > 48 ? `${text.slice(0, 48)}…` : text;
}
