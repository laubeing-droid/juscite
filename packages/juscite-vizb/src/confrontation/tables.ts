// 庭审对抗图封闭表族（契约一：封闭表+表外拒绝+由律师补表；条目自拟，表达隔离）。
// 诉请类型表：每类型必填项缺一即错（J 组）；抗辩四分法：举证责任由归类机械决定（K 组）。

/** 诉请类型封闭表（我方自拟，民事通行）：类型 → 必填字段（缺一即错）。 */
export const CLAIM_TYPES = {
  payment: { label: "给付金钱", required: ["counterpart", "subjectMatter", "amount"] },
  performance: { label: "履行行为", required: ["counterpart", "subjectMatter", "deed"] },
  termination: { label: "解除合同", required: ["contract", "ground"] },
  invalidation: { label: "确认无效/撤销", required: ["contract", "ground"] },
  damages: { label: "损害赔偿", required: ["harm", "causation", "amount"] },
  declaration: { label: "确认法律关系", required: ["relation", "standing"] },
  possession: { label: "返还占有物", required: ["subjectMatter", "basis"] },
  interest: { label: "利息/违约金主张", required: ["principal", "rate", "period"] },
} as const;
export type ClaimType = keyof typeof CLAIM_TYPES;

/**
 * 抗辩四分法（我方自拟，机制=归类封闭＋举证责任机械决定）：
 *  denial=权利否认（事实不存在）→ 举证责任在请求方；
 *  impeditive=权利受制（权利发生受妨碍）→ 抗辩方；
 *  extinctive=权利消灭（已清偿/抵销等）→ 抗辩方；
 *  preclusive=权利排除（抗辩权阻止行使）→ 抗辩方。
 */
export const DEFENSE_CATEGORIES = ["denial", "impeditive", "extinctive", "preclusive"] as const;
export type DefenseCategory = (typeof DEFENSE_CATEGORIES)[number];

export const DEFENSE_CATEGORY_LABEL: Record<DefenseCategory, string> = {
  denial: "权利否认", impeditive: "权利受制", extinctive: "权利消灭", preclusive: "权利排除",
};

/** 举证责任机械映射：否认→请求方；其余三类→抗辩方（归类即定，人标不一致即错）。 */
export const BURDEN_OF: Record<DefenseCategory, "claimant" | "defendant"> = {
  denial: "claimant", impeditive: "defendant", extinctive: "defendant", preclusive: "defendant",
};
export const BURDEN_LABEL: Record<"claimant" | "defendant", string> = { claimant: "请求方", defendant: "抗辩方" };

/** 三问路径封闭模板（K 组：每条抗辩必须附三问，空即拒）。 */
export const DEFENSE_THREE_QUESTIONS = [
  "该抗辩针对哪一项请求权要件",
  "抗辩所依据的事实主张是什么",
  "该事实主张现有何证据支撑",
] as const;

/** 【待核验】标记：先剥再查、不豁免任何机械判据。 */
export const UNVERIFIED_MARKER = "【待核验】";
export function stripUnverifiedMarker(s: string): string {
  return s.split(UNVERIFIED_MARKER).join("");
}

/** 成熟度 L0–L3 封闭（M 组）。 */
export const MATURITY_LEVELS = ["L0", "L1", "L2", "L3"] as const;
export type MaturityLevel = (typeof MATURITY_LEVELS)[number];
export const MATURITY_LABEL: Record<MaturityLevel, string> = {
  L0: "仅有关键词线索", L1: "有单方材料", L2: "有双方材料未对质", L3: "经过对质可下判断",
};

/** 三档置信（判断带三标：法律层面置信/证据层面置信/来源；方向由三栏结构承担）。 */
export const CONFIDENCE_LEVELS = ["high", "mid", "low"] as const;
export type Confidence = (typeof CONFIDENCE_LEVELS)[number];
export const CONFIDENCE_LABEL: Record<Confidence, string> = { high: "高", mid: "中", low: "低" };

/** 四段攻防来源类型封闭（不得套用默认文书名：庭前常只有证据目录没有答辩状）。 */
export const SEGMENT_SOURCE_KINDS = [
  "起诉状", "答辩状", "代理意见", "质证意见", "证据目录", "庭审笔录", "其他文书",
] as const;
export type SegmentSourceKind = (typeof SEGMENT_SOURCE_KINDS)[number];

/** 空段归因（严格分开：「无书面记载」≠「未获取」；图上不立空框）。 */
export const ABSENCE_REASONS = ["无书面记载", "未获取"] as const;
export type AbsenceReason = (typeof ABSENCE_REASONS)[number];
