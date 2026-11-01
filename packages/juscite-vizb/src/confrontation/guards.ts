// 对抗图数据层守卫（契约四；编号我方重编 VC- 前缀）：
//   VC-J 诉请固定（类型封闭+必填项+金额构成明细代码算术对平）
//   VC-K 抗辩归类（四分法封闭+举证责任由归类机械决定+三问路径+【待核验】先剥再查不豁免）
//   VC-P 程序站（管辖/主体/重复起诉三字段分列，缺一即错）
//   VC-M 成熟度（L0-L3 封闭；材料薄只降精确度不降结构：决定性照算照标、置信降低并列待补）
//   VC-D 决定性（规则算不由人标：三判据同时命中；从属性排除及单列例外；≥3 转分散态，不挑前两个）
//   VC-四段收口（反制空而再回应有内容=逻辑错误；无书面记载≠未获取；空段留位不立框）
// 图/表层判据（版面 M/R/T/L、深红计数、图表一致、字段出口）在 render.ts 的产物守卫。

import { claimRequiredMissing, checkClaimArithmetic } from "./arithmetic.ts";
import { BURDEN_OF, DEFENSE_CATEGORIES, stripUnverifiedMarker, type DefenseCategory } from "./tables.ts";
import { isAbsentSegment, isPresentSegment, segmentVerbatimViolations, type ConfrontationSemantic, type Element } from "./semantic.ts";

export interface CViolation { group: "VC-J" | "VC-K" | "VC-P" | "VC-M" | "VC-D" | "VC-四段收口" | "VC-照录"; code: string; msg: string }

/** 决定性规则（单一实现：守卫、渲染、分散态共用同一函数——规则算不由人标）。 */
export function decisiveOf(e: Element): boolean {
  if (e.subordinateTo && !e.independentlyTargeted) return false; // 从属性排除（另有独立抗辩指向的须单列=true）
  return e.disputed && e.burden === "claimant" && !e.evidenceStandardMet; // 三判据同时命中
}

export function guardConfrontation(sem: ConfrontationSemantic): CViolation[] {
  const v: CViolation[] = [];
  // ── VC-J ──
  for (const c of sem.claims) {
    const missing = claimRequiredMissing(c);
    if (missing.length) v.push({ group: "VC-J", code: "J-required", msg: `诉请 ${c.no} 按类型必填项缺：${missing.join("、")}（缺一即错）` });
    const arith = checkClaimArithmetic(c);
    if (!arith.ok && arith.error) v.push({ group: "VC-J", code: "J-arithmetic", msg: arith.error });
  }
  // ── VC-K ──
  for (const d of sem.defenses) {
    const stripped = stripUnverifiedMarker(String(d.category)).trim();
    if (!DEFENSE_CATEGORIES.includes(stripped as DefenseCategory)) {
      v.push({ group: "VC-K", code: "K-category", msg: `抗辩 ${d.no} 归类「${String(d.category)}」剥【待核验】后不在四分法封闭表（标记不豁免判据）` });
    } else {
      const mechanical = BURDEN_OF[stripped as DefenseCategory];
      if (d.burden != null && d.burden !== mechanical) {
        v.push({ group: "VC-K", code: "K-burden", msg: `抗辩 ${d.no} 归类「${stripped}」举证责任机械决定为${mechanical === "claimant" ? "请求方" : "抗辩方"}，与人标「${d.burden}」不一致` });
      }
    }
    const qs = Array.isArray(d.threeQuestions) ? d.threeQuestions : [];
    if (qs.length !== 3 || qs.some((q) => typeof q !== "string" || !q.trim())) {
      v.push({ group: "VC-K", code: "K-three-questions", msg: `抗辩 ${d.no} 缺三问路径（每条抗辩附三问：针对要件/事实主张/证据支撑；缺路径照报，待核验标记不豁免）` });
    }
  }
  // ── VC-P ──
  const P = [["jurisdiction", "管辖"], ["standing", "主体"], ["repeatedSuit", "重复起诉"]] as const;
  for (const [k, label] of P) {
    if (typeof sem.procedure?.[k] !== "string" || !sem.procedure[k]!.trim()) {
      v.push({ group: "VC-P", code: "P-fields", msg: `程序站「${label}」分列字段为空（分列审查，数关键词会漏；先过程序站再谈要件）` });
    }
  }
  // ── VC-M ──
  const lowEvidence = sem.elements.filter((e) => e.evidenceConfidence === "low");
  if (lowEvidence.length > 0 && sem.toComplete.length === 0) {
    v.push({ group: "VC-M", code: "M-to-complete", msg: `有 ${lowEvidence.length} 项要件证据置信=低但待补清单为空（材料薄只降精确度不降结构：证据置信降「低」并列明待补，禁止改写证明前景来表达材料薄）` });
  }
  // ── VC-D（判定不封顶；视觉强调≤2；≥3 转分散态——由产物守卫核图面；数据层如实全算）──
  // （决定性不存输入字段：由规则函数随时重算，无「人标对拍」面）
  // ── VC-四段收口 ──
  for (const e of sem.elements) {
    const counterPresent = isPresentSegment(e.counter);
    const secondPresent = isPresentSegment(e.second);
    if (!counterPresent && secondPresent) {
      v.push({ group: "VC-四段收口", code: "F-counter-empty-second-filled", msg: `要件 ${e.no}：反制为空而再回应有内容=逻辑错误（再回应只能回应反制；数据层拦截）` });
    }
    if (isAbsentSegment(e.counter) && isAbsentSegment(e.second)) {
      if (e.counter.reason === e.second.reason) {
        v.push({ group: "VC-四段收口", code: "F-absence-conflated", msg: `要件 ${e.no}：反制与再回应空段归因同为「${e.counter.reason}」（无书面记载与未获取严格分开）` });
      }
    }
    if (!isPresentSegment(e.claim)) v.push({ group: "VC-四段收口", code: "F-claim-missing", msg: `要件 ${e.no}：主张段缺失（每侧至少主张卡一张）` });
  }
  // ── VC-照录（四段正文=标名来源的子序列；来源必须实际存在）──
  for (const r of segmentVerbatimViolations(sem)) v.push({ group: "VC-照录", code: "C-verbatim", msg: `${r.path}：${r.msg}` });
  return v;
}

/** 分散态判定（≥3 处决定性）：全图无深红、结论条写明共几处；代码不替律师挑前两个。 */
export function scatteredMode(sem: ConfrontationSemantic): { scattered: boolean; decisiveCount: number } {
  const n = sem.elements.filter((e) => decisiveOf(e)).length;
  return { scattered: n >= 3, decisiveCount: n };
}
