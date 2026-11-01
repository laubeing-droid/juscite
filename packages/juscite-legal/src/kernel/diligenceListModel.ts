// 【功能 #32 整理与尽调】清单内核：资料清单整理与缺失核对（RE-32 §2 行为 11-12 / §3 清单核对）。
// 行为 11＝按清单体系整理文件夹三件事：分类归档（材料→清单类目）、重命名（确定性命名方案）、
// 建索引（索引表文本随方案一并产出）；
// 行为 12＝对照清单逐项梳理缺失材料，输出补充尽调资料清单（缺失报告+补索清单文本，文案自写）。
// 匹配规则确定性（关键词/类目匹配+用户显式认领双通道），缺匹配=缺失如实报，不猜。
// 纯函数、零 IO。

export interface ChecklistItem {
  itemId: string;
  category: string;
  name: string;
  required: boolean;
  hint?: string;
}

export interface ChecklistTemplate {
  templateId: string;
  name: string;
  items: ChecklistItem[];
}

export interface CaseMaterialLite {
  materialId: string;
  title: string;
  documentSubtype: string;
  tags: string[];
}

// ── 默认清单模板（我方自编：类目×事项，文案自写；用户可换自定义模板走同一核对面）──
export const DEFAULT_CHECKLIST_TEMPLATE: ChecklistTemplate = {
  templateId: "diligence-default-v1",
  name: "尽调资料清单（通用底稿）",
  items: [
    { itemId: "c01", category: "主体资格", name: "营业执照及章程", required: true, hint: "现行有效版本" },
    { itemId: "c02", category: "主体资格", name: "工商登记档案", required: true, hint: "含设立与历次变更" },
    { itemId: "c03", category: "出资与财务", name: "验资报告", required: true },
    { itemId: "c04", category: "出资与财务", name: "历次实缴出资凭证", required: false },
    { itemId: "c05", category: "出资与财务", name: "近三年财务报表", required: true },
    { itemId: "c06", category: "股权变动", name: "股权转让协议", required: true, hint: "历次股转均需" },
    { itemId: "c07", category: "股权变动", name: "股东名册与出资证明", required: false },
    { itemId: "c08", category: "治理与人事", name: "董监高任免文件", required: true },
    { itemId: "c09", category: "治理与人事", name: "股东会与董事会决议", required: false },
    { itemId: "c10", category: "资产权属", name: "土地房产权属证书", required: false },
    { itemId: "c11", category: "资产权属", name: "知识产权权属证明", required: false },
    { itemId: "c12", category: "负债与涉诉", name: "银行借款合同", required: false },
    { itemId: "c13", category: "负债与涉诉", name: "重大诉讼与仲裁清单", required: true },
  ],
};

// 类目→分类归档的确定性关键词（材料标题/子类型命中即归该类；零命中→「待分类」如实报）
const CATEGORY_KEYWORDS: Array<{ category: string; keywords: string[] }> = [
  { category: "主体资格", keywords: ["营业执照", "工商", "登记", "章程", "主体"] },
  { category: "出资与财务", keywords: ["验资", "出资", "财务", "报表", "审计", "银行流水"] },
  { category: "股权变动", keywords: ["股转", "股权转让", "股东名册", "出资证明", "股权"] },
  { category: "治理与人事", keywords: ["任免", "聘任", "解聘", "董事", "监事", "高管", "决议", "股东会", "董事会"] },
  { category: "资产权属", keywords: ["土地", "房产", "不动产权", "知产", "专利", "商标", "著作权", "权属"] },
  { category: "负债与涉诉", keywords: ["借款", "担保", "诉讼", "仲裁", "执行", "负债", "函证"] },
];

export const UNCATEGORIZED = "待分类";

function classifyOne(m: CaseMaterialLite): string {
  const hay = `${m.title} ${m.documentSubtype ?? ""}`;
  for (const { category, keywords } of CATEGORY_KEYWORDS) {
    if (keywords.some((k) => hay.includes(k))) return category;
  }
  return UNCATEGORIZED;
}

function safeName(s: string): string {
  return String(s ?? "").replace(/[\\/:*?"<>|\r\n]/gu, "_").trim().slice(0, 60) || "未命名";
}

export interface OrganizeAssignment {
  materialId: string;
  originalTitle: string;
  category: string;
  renameTo: string;
}

export interface OrganizePlan {
  assignments: OrganizeAssignment[];
  uncategorized: string[];
  indexMd: string;
}

// ── 行为 11：分类归档+重命名+建索引 ──
export function organizePlan(template: ChecklistTemplate, materials: CaseMaterialLite[]): OrganizePlan {
  const categories = [...new Set(template.items.map((i) => i.category)), UNCATEGORIZED];
  const assignments: OrganizeAssignment[] = [];
  const perCat = new Map<string, number>();
  const uncategorized: string[] = [];
  for (const m of materials) {
    const category = classifyOne(m);
    if (category === UNCATEGORIZED) uncategorized.push(m.title || m.materialId);
    const n = (perCat.get(category) ?? 0) + 1;
    perCat.set(category, n);
    // 重命名方案（自定确定性规则）：清单类目/两位序号/原文件名
    const renameTo = `${category}/${String(n).padStart(2, "0")}-${safeName(m.title)}`;
    assignments.push({ materialId: m.materialId, originalTitle: m.title, category, renameTo });
  }
  const lines = [
    `# 资料整理索引（${template.name}）`,
    "",
    "| 序号 | 清单类目 | 原登记名 | 归档命名 |",
    "|---|---|---|---|",
  ];
  assignments.forEach((a, i) => {
    lines.push(`| ${i + 1} | ${a.category} | ${a.originalTitle} | ${a.renameTo} |`);
  });
  if (uncategorized.length) {
    lines.push("", `## 待分类（${uncategorized.length} 件，需人工定类）`, ...uncategorized.map((t) => `- ${t}`));
  }
  lines.push("", `类目覆盖：${categories.filter((c) => perCat.has(c)).join("、") || "无"}`);
  return { assignments, uncategorized, indexMd: lines.join("\n") + "\n" };
}

export interface MissingCheckInput {
  template: ChecklistTemplate;
  assignments: OrganizeAssignment[];
  /** 用户显式认领：清单项→材料（材料标题含该项关键词的自动匹配之外的第二通道） */
  claims?: Array<{ itemId: string; materialId: string }>;
  materials: CaseMaterialLite[];
}

export interface MissingOutcome {
  missing: Array<{ item: ChecklistItem; reason: string }>;
  covered: Array<{ item: ChecklistItem; matchedTitles: string[] }>;
  supplementMd: string;
}

// ── 行为 12：对照清单逐项核对→缺失报告+补充尽调资料清单 ──
export function checkMissing(input: MissingCheckInput): MissingOutcome {
  const { template, assignments, materials } = input;
  const byId = new Map(materials.map((m) => [m.materialId, m]));
  const claims = new Map<string, string[]>();
  for (const c of input.claims ?? []) {
    const list = claims.get(c.itemId) ?? [];
    list.push(c.materialId);
    claims.set(c.itemId, list);
  }
  const missing: Array<{ item: ChecklistItem; reason: string }> = [];
  const covered: Array<{ item: ChecklistItem; matchedTitles: string[] }> = [];
  for (const item of template.items) {
    const matchedTitles = new Set<string>();
    for (const a of assignments) {
      if (a.category !== item.category || a.category === UNCATEGORIZED) continue;
      const m = byId.get(a.materialId);
      if (!m) continue;
      if (itemMatch(item.name, m.title) || itemMatch(item.name, m.documentSubtype)) matchedTitles.add(m.title);
    }
    for (const mid of claims.get(item.itemId) ?? []) {
      const m = byId.get(mid);
      if (m) matchedTitles.add(m.title);
    }
    if (matchedTitles.size > 0) covered.push({ item, matchedTitles: [...matchedTitles] });
    else {
      missing.push({
        item,
        reason: item.required ? "必需项尚无对应材料" : "可选项暂缺（按项目情况决定是否索取）",
      });
    }
  }
  const lines = [
    "# 补充尽调资料清单",
    "",
    `依据「${template.name}」逐项核对，尚缺 ${missing.length} 项（其中必需 ${missing.filter((x) => x.item.required).length} 项）。请按下表补齐：`,
    "",
    "| 清单类目 | 待补充事项 | 必需/可选 | 备注 |",
    "|---|---|---|---|",
  ];
  for (const x of missing) {
    lines.push(`| ${x.item.category} | ${x.item.name} | ${x.item.required ? "必需" : "可选"} | ${x.item.hint ?? x.reason} |`);
  }
  lines.push("", "已核对到位的事项不再列入；材料补齐后请重新执行缺失核对。");
  return { missing, covered, supplementMd: lines.join("\n") + "\n" };
}

/** 确定性匹配：清单事项名与材料名互相包含其一关键词（按 ≥2 字词段拆分），零命中不算匹配 */
function itemMatch(itemName: string, materialName: string): boolean {
  const segs = String(itemName ?? "").split(/[（）()\/、\s]+/u).map((s) => s.trim()).filter((s) => s.length >= 2);
  const hay = String(materialName ?? "");
  return segs.some((seg) => hay.includes(seg));
}
