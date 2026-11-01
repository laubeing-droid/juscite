// 金额构成明细核算（J 组后半：主张确定数额必须附结构化构成明细，代码做算术——
// 明细合计与主张额相符，差额必须为显式调整项且注明依据；取不出确定数额不核算）。
// 整型分算术（LegalTech 红线：金额禁浮点）；纯脚本，不进 JC（算术非规则，规格 §五.3）。

import { CLAIM_TYPES, type ClaimType } from "./tables.ts";
import type { Claim } from "./semantic.ts";

export interface ClaimArithmeticResult {
  claimNo: string;
  checked: boolean;              // false=主张额不确定（claimedCents=null），如实不核算
  itemsSumCents: number | null;
  adjustmentsSumCents: number | null;
  claimedCents: number | null;
  ok: boolean;
  error: string | null;
}

export function checkClaimArithmetic(c: Claim): ClaimArithmeticResult {
  if (c.claimedCents == null) {
    return { claimNo: c.no, checked: false, itemsSumCents: null, adjustmentsSumCents: null, claimedCents: null, ok: true,
      error: null }; // 取不出确定数额：不核算（J 组放行此形态，图/表如实标「数额未定」）
  }
  const itemsSum = c.items.reduce((a, b) => a + b.cents, 0);
  const adjSum = c.adjustments.reduce((a, b) => a + b.cents, 0);
  if (itemsSum + adjSum !== c.claimedCents) {
    return { claimNo: c.no, checked: true, itemsSumCents: itemsSum, adjustmentsSumCents: adjSum, claimedCents: c.claimedCents, ok: false,
      error: `诉请 ${c.no} 金额不平：明细合计 ${(itemsSum / 100).toFixed(2)} 元＋调整项 ${(adjSum / 100).toFixed(2)} 元 ≠ 主张 ${(c.claimedCents / 100).toFixed(2)} 元（差额必须列为显式调整项并注明依据）` };
  }
  if (c.claimedCents > 0 && c.items.length === 0) {
    return { claimNo: c.no, checked: true, itemsSumCents: 0, adjustmentsSumCents: adjSum, claimedCents: c.claimedCents, ok: false,
      error: `诉请 ${c.no} 主张确定数额但无构成明细（主张确定数额必须附结构化构成明细）` };
  }
  return { claimNo: c.no, checked: true, itemsSumCents: itemsSum, adjustmentsSumCents: adjSum, claimedCents: c.claimedCents, ok: true, error: null };
}

/** 诉请类型必填项检查（J 组前半：按类型必填缺一即错）。 */
export function claimRequiredMissing(c: Claim): string[] {
  const def = CLAIM_TYPES[c.type as ClaimType];
  if (!def) return ["type"];
  return def.required.filter((k) => !c.required || typeof c.required[k] !== "string" || !c.required[k]!.trim());
}
