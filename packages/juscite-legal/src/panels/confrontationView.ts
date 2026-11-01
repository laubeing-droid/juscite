// 【施工波二轮·可视化B轨 UI 件】对抗视图（功能 #19 深化）面板侧纯函数。
// 依据：竞品情报/2026-10-29-规格波/可视化-B轨规格.md §四 A2——「数据源=语义 JSON（我方 schema 自定）」。
// 语义 JSON 是模型/律师侧产出（契约一：判断带三标、三处结论留空），面板不生产语义、不做任何
// 判断推演：此处只做 JSON 解析与只读摘要（供表格预览），封闭 schema 校验与 J/K/P/M/D 判据守卫
// 全在桥面 @juscite/vizb（bridge vizbConfrontationCheck/Render 为唯一判定源）。
// 结构对齐 @juscite/vizb src/confrontation/semantic.ts 的 ConfrontationSemantic
// （schema juscite.vizb.confrontation@1）；字段单源在 vizb 包，此处仅视图层只读镜像。
// 零运行时导入（纯函数自包含）。

export interface ConfrontationElementRow {
  no: string;
  issue: string;
  burden: string;
  lawConfidence: string;
  evidenceConfidence: string;
  disputed: boolean;
  evidenceStandardMet: boolean;
}

export interface ConfrontationSummary {
  ok: boolean;
  error: string | null;
  caseTitle: string;
  maturity: string;
  internalOnly: boolean;
  claimsCount: number;
  defensesCount: number;
  sourcesCount: number;
  toCompleteCount: number;
  rows: ConfrontationElementRow[];
}

/** 解析粘贴的语义 JSON 文本：只做 JSON.parse + 对象判定，不预校验 schema（判定在桥面）。 */
export function parseConfrontationSemantic(text: string): { ok: boolean; value: unknown; error: string | null } {
  try {
    const v: unknown = JSON.parse(text);
    if (typeof v !== "object" || v === null || Array.isArray(v)) {
      return { ok: false, value: null, error: "语义 JSON 须为对象（判定以桥面校验为准）" };
    }
    return { ok: true, value: v, error: null };
  } catch (e) {
    return { ok: false, value: null, error: `JSON 解析失败：${String((e as Error)?.message ?? e)}` };
  }
}

function asString(v: unknown, fallback: string): string {
  return typeof v === "string" ? v : fallback;
}

/** 只读摘要：要件行原样展示三标与争议标记；决定性判定不在此算（规则算在桥面）。 */
export function summarizeConfrontation(value: unknown): ConfrontationSummary {
  const o = (typeof value === "object" && value !== null && !Array.isArray(value) ? value : {}) as Record<string, unknown>;
  const elements = Array.isArray(o.elements) ? o.elements : [];
  const rows: ConfrontationElementRow[] = [];
  for (const el of elements) {
    if (typeof el !== "object" || el === null) continue;
    const e = el as Record<string, unknown>;
    rows.push({
      no: asString(e.no, ""),
      issue: asString(e.issue, ""),
      burden: asString(e.burden, ""),
      lawConfidence: asString(e.lawConfidence, ""),
      evidenceConfidence: asString(e.evidenceConfidence, ""),
      disputed: e.disputed === true,
      evidenceStandardMet: e.evidenceStandardMet === true,
    });
  }
  return {
    ok: rows.length > 0,
    error: rows.length > 0 ? null : "未读出要件行（以桥面校验为准）",
    caseTitle: asString(o.caseTitle, ""),
    maturity: asString(o.maturity, ""),
    internalOnly: o.internalOnly === true,
    claimsCount: Array.isArray(o.claims) ? o.claims.length : 0,
    defensesCount: Array.isArray(o.defenses) ? o.defenses.length : 0,
    sourcesCount: Array.isArray(o.sources) ? o.sources.length : 0,
    toCompleteCount: Array.isArray(o.toComplete) ? o.toComplete.length : 0,
    rows,
  };
}
