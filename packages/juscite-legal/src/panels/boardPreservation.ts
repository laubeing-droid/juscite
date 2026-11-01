// 【步骤4·#3 案件看板·补齐件】保全面纯函数（RE-3 行 19-20/23-24；§2.3 保全语义自写，§3.6 正则+词表禁 LLM 猜）。
// 三件：①保全条款抽取（四类资产期限规格+中文数字日期+「自X至Y」日期窗+目标/动作归一，实跑 CB-B7/B8 口径）；
//      ②后置解封压制（解封日期≥保全开始→不再提醒，实跑 CB-B11）；
//      ③开庭 session 四键去重+最新文档权威（一次/二次/第三次开庭/庭前询问听证，实跑 CB-B10）。
// 数据源边界（如实标注）：#4 时间线/#6 抽取产物未接入前，以上纯函数无 UI 数据面——接入后由节点文本流喂入。
// 抽不出的信息一律 null（UNKNOWN，fail-closed），不猜。
import { boardDayDiff } from "./boardCalendar.js";

// ── ① 保全条款抽取 ──
export type PreservationLabel = "银行账户" | "股权" | "车辆" | "不动产" | "原文";
export type PreservationAction = "续冻" | "续封";

export interface PreservationRow {
  raw: string; // 命中的原句片段
  target: string; // 目标短语（归一前原文截取）
  label: PreservationLabel; // 目标归一（CB 行 20）
  action: PreservationAction; // 动作归一：冻结/银行账户/股权→续冻，其余→续封
  startDate: string | null; // YYYY-MM-DD；日期窗起点或基准日
  expiresAt: string | null; // YYYY-MM-DD；年限推得或窗口至日；抽不出=null（UNKNOWN 不猜）
}

const CN_DIGITS: Record<string, number> = {
  零: 0, 一: 1, 二: 2, 两: 2, 三: 3, 四: 4, 五: 5, 六: 6, 七: 7, 八: 8, 九: 9, 十: 10,
};

/** 中文数字（一~十/两/含零位值串如「二零二六」）→数值；解析失败 null。 */
export function cnNumber(s: string): number | null {
  if (!s) return null;
  if (s.length === 1) {
    const v = CN_DIGITS[s];
    return v === undefined ? null : v;
  }
  // 含「零」= 逐位拼接（年份形态「二零二六」）；任一位非数字即失败
  if (s.includes("零")) {
    let acc = 0;
    for (const ch of s) {
      const v = CN_DIGITS[ch];
      if (v === undefined) return null;
      acc = acc * 10 + v;
    }
    return acc;
  }
  // 十/十X/X十/X十Y 的最小覆盖（保全年限词域：一~三年/两年内不会超出）
  if (s.startsWith("十")) {
    const tail = CN_DIGITS[s.slice(1)];
    return tail === undefined ? null : 10 + tail;
  }
  if (s.endsWith("十")) {
    const head = CN_DIGITS[s.slice(0, -1)];
    return head === undefined ? null : head * 10;
  }
  if (s.includes("十")) {
    const parts = s.split("十");
    if (parts.length !== 2) return null;
    const hv = CN_DIGITS[parts[0] ?? ""];
    const tv = CN_DIGITS[parts[1] ?? ""];
    return hv === undefined || tv === undefined ? null : hv * 10 + tv;
  }
  return null;
}

/** 年限词（「2 年」「一年」「两年」「一年半」）→月数；解析失败 null。 */
export function durationMonths(word: string): number | null {
  const m = /^([0-9一二两三四五六七八九十]+)年(半)?$/.exec(word.trim());
  if (!m || !m[1]) return null;
  const n = /^[0-9]+$/.test(m[1]) ? Number(m[1]) : cnNumber(m[1]);
  if (n === null || n <= 0) return null;
  return n * 12 + (m[2] ? 6 : 0);
}

function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

/** 年月日（阿拉伯或中文数字）→YYYY-MM-DD；非法（13 月/2 月 30 日等）null。 */
export function cnDateString(y: string, mo: string, d: string): string | null {
  const yy = /^[0-9]+$/.test(y) ? Number(y) : cnNumber(y);
  const mm = /^[0-9]+$/.test(mo) ? Number(mo) : cnNumber(mo);
  const dd = /^[0-9]+$/.test(d) ? Number(d) : cnNumber(d);
  if (yy === null || mm === null || dd === null) return null;
  const dt = new Date(yy, mm - 1, dd);
  if (dt.getFullYear() !== yy || dt.getMonth() !== mm - 1 || dt.getDate() !== dd) return null; // 真日历日
  return `${yy}-${pad2(mm)}-${pad2(dd)}`;
}

function addMonths(iso: string, months: number): string | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!m) return null;
  const y = Number(m[1]);
  const mo = Number(m[2]);
  const d = Number(m[3]);
  const target = new Date(y, mo - 1 + months, d);
  // 月末溢出（1/31+1 月→3/3）按夹取口径：失败则回退当月末——确定性优先，宁可落到月末不可跨入下月
  if (target.getDate() !== d) {
    return `${target.getFullYear()}-${pad2(target.getMonth() + 1)}-${pad2(new Date(target.getFullYear(), target.getMonth() + 1, 0).getDate())}`;
  }
  return `${target.getFullYear()}-${pad2(target.getMonth() + 1)}-${pad2(target.getDate())}`;
}

const TARGET_WORDS: Array<{ re: RegExp; label: PreservationLabel; norm: string }> = [
  { re: /(银行账户|银行存款|银行账号)/, label: "银行账户", norm: "银行账户" },
  { re: /(股权|股份)/, label: "股权", norm: "股权" },
  { re: /(机动车|车辆)/, label: "车辆", norm: "车辆" },
  { re: /(不动产|房产|房屋|厂房)/, label: "不动产", norm: "不动产" },
];
const ACTION_WORDS = /(冻结|查封|扣押)/;

/**
 * 保全条款抽取（确定性正则+词表）：逐句切分，命中动作词的句子产出一行；
 * 期限规格（CB-B7）：银行账户 1 年 / 车辆 2 年 / 股权 3 年 / 不动产 3 年（写明年限以文本为准，
 * 文本未写年限时按四类规格推）；「自X至Y」日期窗以窗口至日为准。
 */
export function extractPreservationClauses(text: string, baseDate: string | null): PreservationRow[] {
  if (typeof text !== "string" || !text.trim()) return [];
  const DEFAULT_MONTHS: Record<PreservationLabel, number | null> = {
    银行账户: 12, 股权: 36, 车辆: 24, 不动产: 36, 原文: null, // CB-B7 四类规格；原文目标无规格不猜
  };
  const rows: PreservationRow[] = [];
  for (const rawSentence of text.split(/[。；;！!？?\n]/)) {
    const sentence = rawSentence.trim();
    if (!sentence || !ACTION_WORDS.test(sentence)) continue;
    const hit = TARGET_WORDS.find((t) => t.re.test(sentence));
    const label: PreservationLabel = hit ? hit.label : "原文";
    const target = hit ? hit.norm : sentence.replace(ACTION_WORDS, "").trim().slice(0, 24) || "原文";
    const action: PreservationAction = label === "银行账户" || label === "股权" || /冻结/.test(sentence) ? "续冻" : "续封";
    let startDate: string | null = null;
    let expiresAt: string | null = null;
    // 「自X年X月X日至X年X月X日」日期窗（CB-B7 日期窗口径）
    const range = /自\s*(\d{4}|[〇一二两三四五六七八九十]+)\s*年\s*([0-9一二两三四五六七八九十]+)\s*月\s*([0-9一二两三四五六七八九十]+)\s*日\s*至\s*(\d{4}|[〇一二两三四五六七八九十]+)\s*年\s*([0-9一二两三四五六七八九十]+)\s*月\s*([0-9一二两三四五六七八九十]+)\s*日/.exec(sentence);
    if (range && range[1] && range[2] && range[3] && range[4] && range[5] && range[6]) {
      startDate = cnDateString(range[1], range[2], range[3]);
      expiresAt = cnDateString(range[4], range[5], range[6]);
    } else {
      // 年限词：文中写明者优先，否则按四类规格；中文数字日期起点若在句中一并采用
      const dur = /(?:期限[为是]?|冻结|查封|扣押)?\s*([0-9一二两三四五六七八九十]+\s*年(?:半)?)\s*[，,；;]?/.exec(sentence
        .replace(/自[^至]*至[^，,；;。]*/, ""));
      const months = dur && dur[1] ? durationMonths(dur[1].replace(/\s+/g, "")) : null;
      const startM = /(\d{4}|[〇一二两三四五六七八九十]+)\s*年\s*([0-9一二两三四五六七八九十]+)\s*月\s*([0-9一二两三四五六七八九十]+)\s*日/.exec(sentence);
      const start = startM && startM[1] && startM[2] && startM[3] ? cnDateString(startM[1], startM[2], startM[3]) : baseDate;
      const effMonths = months ?? DEFAULT_MONTHS[label];
      if (start) startDate = start;
      if (start && effMonths !== null) expiresAt = addMonths(start, effMonths);
    }
    rows.push({ raw: sentence, target, label, action, startDate, expiresAt });
  }
  return rows;
}

// ── ② 后置解封压制（CB-B11：解封日期≥保全开始→压制；无解封/解封早于开始→保留） ──
export interface PreserveLike {
  id: string;
  startDate: string | null; // 保全开始日
}
export interface UnsealLike {
  id: string;
  date: string; // 解封日
}

/** 返回被压制（不再提醒）的保全行 id 集合。 */
export function suppressedByUnseal(
  preserveRows: readonly PreserveLike[],
  unsealRows: readonly UnsealLike[],
): Set<string> {
  const suppressed = new Set<string>();
  for (const p of preserveRows) {
    if (!p.startDate) continue; // 无开始日无法比较→不压制（保留提醒，宁提醒勿漏）
    for (const u of unsealRows) {
      const diff = boardDayDiff(p.startDate, u.date);
      if (diff !== null && diff >= 0) {
        suppressed.add(p.id);
        break;
      }
    }
  }
  return suppressed;
}

// ── ③ 开庭 session 四键去重+最新文档权威（CB-B10） ──
export type HearingSessionKey = "first" | "second" | "third" | "pretrial";

export interface HearingLike {
  id: string;
  title: string;
  docRank: number; // 文档新旧序（越大越新；来源 #4/#6 接入后=文档时间/序号）
  date?: string;
}

/** session 键：一次/第二次/第三次开庭、庭前询问/听证；未命中 null（不去重）。 */
export function hearingSessionKeyOf(title: string): HearingSessionKey | null {
  if (/庭前询问|庭前谈话|听证/.test(title)) return "pretrial";
  if (/第二次开庭|再次开庭/.test(title)) return "second";
  if (/第三次开庭/.test(title)) return "third";
  if (/第一次开庭|开庭/.test(title)) return "first";
  return null;
}

/** 同键保留 docRank 最大行（最新文档权威），返回去重后列表（保持入参相对序）。 */
export function dedupHearingsBySession(rows: readonly HearingLike[]): HearingLike[] {
  const bestByKey = new Map<HearingSessionKey, HearingLike>();
  for (const r of rows) {
    const key = hearingSessionKeyOf(r.title);
    if (!key) continue;
    const cur = bestByKey.get(key);
    if (!cur || r.docRank > cur.docRank || (r.docRank === cur.docRank && r.id < cur.id)) {
      bestByKey.set(key, r);
    }
  }
  const out: HearingLike[] = [];
  const emitted = new Set<string>();
  for (const r of rows) {
    const key = hearingSessionKeyOf(r.title);
    if (!key) { out.push(r); continue; }
    const best = bestByKey.get(key);
    if (best && best.id === r.id && !emitted.has(r.id)) {
      emitted.add(r.id);
      out.push(r);
    }
  }
  return out;
}

// ── 【#4 时间线开庭行去重】对拍行 24 接线（r9 补齐：纯函数此前仅自测在库、显示路径未并）──
// 时间线开庭族行（同案同 session 键多文档登记，如两份材料都记了同一次开庭）进日历/下一节点前
// 按键坍缩，同键保留 updatedAt 最新行（最新文档权威=CB 口径；时间戳相同取 id 序小，确定性）。
// 键=案 id+session 键（hearingSessionOf 族表）；「二审开庭」不在 CB 四键内，自成一族，
// 不与一审开庭互吞。非 hearing/未绑案/键表未命中的行不去重（原样保留）。
export interface TimelineHearingRow {
  id: string;
  caseId: string | null;
  kind: string; // "hearing" 才参与去重
  title: string; // 事件类型（开庭/二审开庭/开庭排期…）
  updatedAt: string; // 文档新旧序（ISO 串可比）
}

export function boardDedupTimelineHearings<T extends TimelineHearingRow>(rows: readonly T[]): T[] {
  const keyOf = (r: T): string | null => {
    if (r.kind !== "hearing" || !r.caseId) return null;
    if (r.title === "二审开庭") return `${r.caseId}::second-instance`;
    const sk = hearingSessionKeyOf(r.title);
    return sk === null ? null : `${r.caseId}::${sk}`;
  };
  const best = new Map<string, T>();
  for (const r of rows) {
    const k = keyOf(r);
    if (k === null) continue;
    const cur = best.get(k);
    if (!cur || r.updatedAt > cur.updatedAt || (r.updatedAt === cur.updatedAt && r.id < cur.id)) {
      best.set(k, r);
    }
  }
  return rows.filter((r) => {
    const k = keyOf(r);
    if (k === null) return true;
    const b = best.get(k);
    return b !== undefined && b.id === r.id;
  });
}
