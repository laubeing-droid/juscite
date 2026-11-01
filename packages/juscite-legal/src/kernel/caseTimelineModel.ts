// 【步骤4·#4 案件时间线】CaseEvent 纯模型（RE-4-案件时间线.md 实现规格 §3）。
// 桥/UI/合成自测单一来源（同 caseGraphModel 先例）：枚举值域/确定性排序/去重键/行键/
// 开庭状态归一/日期精度兜底/抽取后处理/重抽合并，全部纯函数零依赖零模型。
// 确定性纪律（RE-4 §3）：日期一律 YYYY-MM-DD 字符串比较；金额只存原文串（amount_text，
// 禁浮点解析、不参与任何计算——金额推理走 JC 桥）；排序用显式业务次序表。
// ⚠ 过渡态：case_events 挂桥内轻量案件表族（迁移 0010_case_event），MatterStore 解挂后
// 随案件族一起翻牌真源（决策台账 2026-10-27 03:35 同 0005_case_board 注）。

// ── 通道一抽取线：CB 白名单 14 值（对拍 7；白名单外不抽，自由文本兜底仅在技能输出面）──
export const CB_EVENT_TYPES = [
  "接案", "申请立案", "正式立案", "保全", "解封", "开庭", "调解", "判决",
  "上诉", "二审开庭", "二审判决", "执行立案", "开发票", "还款期",
] as const;

// ── 通道二业务自动线：auto 事件枚举 21 值（LL F4 等量映射，文案自写：建案/程序增改受理/
//    环节增移/期限/开庭登记排期已开/材料/实收/任务/团队/结案重开暂停/服务激活完成/归档申请归档）──
export const AUTO_EVENT_TYPES = [
  "建案", "新增程序", "程序变更", "程序受理", "新增环节", "移除环节",
  "期限登记", "开庭登记", "开庭排期", "开庭已开", "材料登记", "实收登记", "任务登记",
  "团队变更", "结案", "重开", "暂停", "服务激活", "服务完成", "归档申请", "已归档",
] as const;

// ── 客户侧事实白名单 11 值（LL F6 等量；可见性过滤在查询层执行，不靠前端隐藏）──
export const FACT_EVENT_TYPES = [
  "建案", "新增程序", "新增环节", "移除环节", "期限登记", "开庭排期",
  "团队变更", "结案", "重开", "暂停", "已归档",
] as const;

// 唯一写入口闭集 = CB 14 ∪ auto 21（对拍 49；自由文本兜底仅抽取通道内部路径）
export const RECORDABLE_EVENT_TYPES: ReadonlySet<string> = new Set([...CB_EVENT_TYPES, ...AUTO_EVENT_TYPES]);

// 业务次序表 12 值（对拍 25/17；解封/还款期在白名单内但不在次序表→orderOf=99 同段垫底，C3 边角）
export const BUSINESS_ORDER: Readonly<Record<string, number>> = {
  接案: 0, 申请立案: 1, 正式立案: 2, 保全: 3, 开庭: 4, 调解: 5,
  判决: 6, 上诉: 7, 二审开庭: 8, 二审判决: 9, 执行立案: 10, 开发票: 11,
};

// 事实状态六档（对拍 36：confirmed/我方主张/对方主张/有争议/推断/未知）
export const CASE_EVENT_STATUSES = ["confirmed", "our_claim", "opponent_claim", "disputed", "inferred", "unknown"] as const;
// 重要度三档；来源三通道；provenance 三值
export const CASE_EVENT_IMPORTANCE = ["critical", "normal", "context"] as const;
export const CASE_EVENT_ORIGINS = ["llm_extract", "auto", "user"] as const;
export const CASE_EVENT_PROVENANCES = ["ai", "user", "system"] as const;

// 协议行形状（桥 JSON-RPC / UI 共用；store 列 snake 由桥面映射）
export interface CaseEventProto {
  eventId: string;
  matterId: string;
  eventType: string;
  date: string | null;
  dateLabel: string | null;
  note: string | null;
  expiresAt: string | null;
  status: string;
  importance: string;
  phase: string | null;
  side: string | null;
  origin: string;
  sourceRefs: Array<{ filename: string; locator?: string; quote?: string }>;
  payload: CaseEventPayload | null;
  provenance: string;
  lockedFields: string[];
  orig: Partial<Pick<CaseEventProto, "eventType" | "date" | "note">> | null;
  deleted: boolean;
  createdAt: string;
  updatedAt: string;
}
// B2 八字段承载（§3 映射表：主体/行为性质/金额原文串/争议说明；键缺省=缺省，不另造列）
// confidence（对拍增补 63·对照源二和讼 case_events.confidence 等量）：AI 整理行的确凿程度
// 自评，0-1 数字（净化钳到两位小数）；只承载展示，不参与任何计算与排序。
export interface CaseEventPayload {
  subjects?: string[];
  behavior_nature?: string;
  amount_text?: string; // 原文串存储，禁浮点、不参与计算
  dispute_note?: string;
  confidence?: number; // 0-1，两位小数；缺省=模型未给，如实缺省不造值
}

// ── 日历日工具（§3.6 同款：正则+真日历日双校验；差值用归零到日的 Date 只作差值）──
export function isCalendarDate(v: unknown): v is string {
  if (typeof v !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(v)) return false;
  const parts = v.split("-").map(Number);
  const y = parts[0] as number, m = parts[1] as number, d = parts[2] as number;
  const dt = new Date(y, m - 1, d);
  return dt.getFullYear() === y && dt.getMonth() === m - 1 && dt.getDate() === d;
}
export function todayStr(now = new Date()): string {
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}
export function dayDiff(fromDate: string, toDate: string): number | null {
  const p = (s: string): number | null => {
    if (!isCalendarDate(s)) return null;
    const parts = s.split("-").map(Number);
    const y = parts[0] as number, m = parts[1] as number, d = parts[2] as number;
    return new Date(y, m - 1, d).getTime();
  };
  const a = p(fromDate);
  const b = p(toDate);
  return a === null || b === null ? null : Math.round((b - a) / 86_400_000);
}

// 次序值：次序表内取表值；白名单外/解封/还款期一律 99（C3 实测边角：同日排序垫底段）
export function eventOrderOf(eventType: string): number {
  return Object.prototype.hasOwnProperty.call(BUSINESS_ORDER, eventType)
    ? (BUSINESS_ORDER[eventType] as number)
    : 99;
}

// ── C3 确定性排序（full 口径，升序）：日期升序 → 同日按业务次序表 → 次序同值按创建序 →
//    无日期行沉底（次序表仍参与同段排序）→ 末位 event_id 兜底稳定。──
export function sortCaseEventsFull<T extends { eventType: string; date: string | null; createdAt: string; eventId: string }>(
  rows: ReadonlyArray<T>,
): T[] {
  return [...rows].sort((a, b) => {
    if (a.date && b.date && a.date !== b.date) return a.date < b.date ? -1 : 1;
    if (a.date && !b.date) return -1;
    if (!a.date && b.date) return 1;
    const oa = eventOrderOf(a.eventType);
    const ob = eventOrderOf(b.eventType);
    if (oa !== ob) return oa - ob;
    if (a.createdAt !== b.createdAt) return a.createdAt < b.createdAt ? -1 : 1;
    return a.eventId < b.eventId ? -1 : a.eventId > b.eventId ? 1 : 0;
  });
}

// D6 行键：event_type|date（raw 值计算，缺值空串占位——编辑改键不影响旧覆盖寻址）
export function rowKeyOf(eventType: string | null | undefined, date: string | null | undefined): string {
  return `${eventType ?? ""}|${date ?? ""}`;
}
// C4 去重键：date|event_type（与行键方向相反，两键并存不混用）
function dedupKeyOf(date: string | null | undefined, eventType: string | null | undefined): string {
  return `${date ?? ""}|${eventType ?? ""}`;
}

// C4/对拍 26：按 date|event_type 去重保留首现（双缺项行不参与去重判定，由调用方先行过滤）
export function dedupByKeyKeepFirst<T>(items: ReadonlyArray<T>, keyOf: (it: T) => string): T[] {
  const seen = new Set<string>();
  const out: T[] = [];
  for (const it of items) {
    const k = keyOf(it);
    if (seen.has(k)) continue;
    seen.add(k);
    out.push(it);
  }
  return out;
}

// ── C7 开庭状态归一（status_text 层）：未来→将于 X 开庭／当天→今日开庭／过去→已于 X 开庭 ──
export function hearingStatusText(date: string | null | undefined, baseToday: string): string | null {
  if (!date || !isCalendarDate(date)) return null;
  const d = dayDiff(baseToday, date);
  if (d === null) return null;
  if (d > 0) return `将于 ${date} 开庭`;
  if (d === 0) return "今日开庭";
  return `已于 ${date} 开庭`;
}

// ── B18 日期精度三级 + 文案兜底：精确日 / 模糊范围（原文）/ 两者皆无（待核对，不编日期）──
export type DatePrecision = "exact" | "range" | "unknown";
export function displayDateOf(row: { date: string | null; dateLabel: string | null }): { text: string; precision: DatePrecision } {
  if (row.date && isCalendarDate(row.date)) return { text: row.date, precision: "exact" };
  if (row.dateLabel && String(row.dateLabel).trim()) return { text: `${row.dateLabel}（日期待核对）`, precision: "range" };
  return { text: "日期待核对", precision: "unknown" };
}

// 状态/重要度归一：白名单外回落默认（confirmed/normal——列默认语义，不静默造新档）
export function normalizeStatus(v: unknown): string {
  return (CASE_EVENT_STATUSES as readonly string[]).includes(String(v)) ? String(v) : "confirmed";
}
export function normalizeImportance(v: unknown): string {
  return (CASE_EVENT_IMPORTANCE as readonly string[]).includes(String(v)) ? String(v) : "normal";
}

// source_refs 四元组净化：{document_id,filename,locator,quote}→落库 {filename,locator,quote}，
// 非对象/无名条目丢弃；quote 截 300 字（防整段材料回流）；数量帽 8。
export function sanitizeSourceRefs(v: unknown): Array<{ filename: string; locator?: string; quote?: string }> {
  if (!Array.isArray(v)) return [];
  const out: Array<{ filename: string; locator?: string; quote?: string }> = [];
  for (const it of v.slice(0, 8)) {
    if (!it || typeof it !== "object") continue;
    const filename = typeof (it as { filename?: unknown }).filename === "string" ? (it as { filename: string }).filename.trim() : "";
    if (!filename) continue;
    const locator = typeof (it as { locator?: unknown }).locator === "string" ? (it as { locator: string }).locator.trim() : "";
    const quoteRaw = typeof (it as { quote?: unknown }).quote === "string" ? (it as { quote: string }).quote : "";
    out.push({ filename, ...(locator ? { locator } : {}), ...(quoteRaw ? { quote: quoteRaw.slice(0, 300) } : {}) });
  }
  return out;
}

// payload 净化：五键白名单（subjects/behavior_nature/amount_text/dispute_note/confidence），
// amount_text 只收字符串原文（禁浮点——数字输入一律丢，不解析不转换）；subjects 限 12 条非空
// 字符串；confidence 收 0-1 数值（数字或纯数字串均可，钳到 [0,1] 两位小数，其余丢弃不造值）。
export function sanitizePayload(v: unknown): CaseEventPayload | null {
  if (!v || typeof v !== "object" || Array.isArray(v)) return null;
  const src = v as Record<string, unknown>;
  const out: CaseEventPayload = {};
  if (Array.isArray(src.subjects)) {
    const subjects = src.subjects
      .filter((s): s is string => typeof s === "string" && !!s.trim())
      .map((s) => s.trim().slice(0, 80))
      .slice(0, 12);
    if (subjects.length) out.subjects = subjects;
  }
  for (const k of ["behavior_nature", "dispute_note"] as const) {
    if (typeof src[k] === "string" && (src[k] as string).trim()) out[k] = (src[k] as string).trim().slice(0, 400);
  }
  if (typeof src.amount_text === "string" && src.amount_text.trim()) out.amount_text = src.amount_text.trim().slice(0, 80);
  const rawConf = typeof src.confidence === "number" ? src.confidence
    : typeof src.confidence === "string" && /^-?\d+(\.\d+)?$/.test(src.confidence.trim()) ? Number(src.confidence.trim())
    : NaN;
  if (Number.isFinite(rawConf)) out.confidence = Math.round(Math.min(1, Math.max(0, rawConf)) * 100) / 100;
  return Object.keys(out).length ? out : null;
}

// ══ 件2：通道一 LLM 抽取后处理 + 编辑流（RE-4 §3 通道一/编辑流；全部纯函数）══

// 可编辑字段（D2：事件类型/日期/备注三字段；行以 event_id 寻址，覆盖直写行本身——
// rowKey 改用未编辑 raw 值计算的防孤儿语义在本表按主键寻址下天然成立）
export const EDITABLE_FIELDS = ["eventType", "date", "note"] as const;
export type EditableField = (typeof EDITABLE_FIELDS)[number];

// 抽取行（后处理产物，落库前形状；eventType 允许白名单外自由文本兜底——§3 列契约）
export interface ExtractedRow {
  eventType: string;
  date: string | null;
  dateLabel: string | null;
  note: string | null;
  expiresAt: string | null;
  status: string;
  importance: string;
  phase: string | null;
  side: string | null;
  sourceRefs: Array<{ filename: string; locator?: string; quote?: string }>;
  payload: CaseEventPayload | null;
}

// ── 解析模型输出（B17/B22）：文本中取最外层 JSON 数组（容 ``` 围栏）；不可解析→抛错
// （通道一状态机转失败态+重试）；合法 JSON 但非数组→兜底空数组不抛（B22 渲染同规）。──
export function parseExtractionOutput(raw: string): unknown[] {
  const text = String(raw ?? "");
  const start = text.indexOf("[");
  const end = text.lastIndexOf("]");
  if (start === -1 || end === -1 || end <= start) {
    // 无数组形态：非数组 JSON（对象/null）按 B22 兜底空；整段连 JSON 都不像→显式报错
    try {
      const v = JSON.parse(text.trim());
      return Array.isArray(v) ? v : [];
    } catch {
      throw new Error("模型输出不含可解析的 JSON 数组，抽取失败（可重试）");
    }
  }
  const slice = text.slice(start, end + 1);
  let v: unknown;
  try {
    v = JSON.parse(slice);
  } catch {
    throw new Error("模型输出 JSON 解析失败，抽取失败（可重试）");
  }
  return Array.isArray(v) ? v : [];
}

// ── 确定性后处理（禁 LLM 二次加工）：双缺项过滤/日期格式兜底（坏日期→date_label 保留原文，
//    不编日历日）/开庭·执行立案专项校验警告（对拍 11/13）/白名单外类型自由文本兜底/
//    date|event_type 去重保留首现（仅对带日期行去重；无日期行语义键退化，全保留走沉底段）。──
export function postprocessExtracted(items: ReadonlyArray<unknown>): { rows: ExtractedRow[]; warnings: string[] } {
  const warnings: string[] = [];
  const rows: ExtractedRow[] = [];
  for (const it of items) {
    if (!it || typeof it !== "object" || Array.isArray(it)) continue;
    const src = it as Record<string, unknown>;
    const rawType = typeof src.event_type === "string" ? src.event_type.trim() : typeof src.eventType === "string" ? src.eventType.trim() : "";
    const rawDate = typeof src.date === "string" ? src.date.trim() : "";
    // B13/§3 通道一-4：date 与 event_type 双缺项过滤
    if (!rawType && !rawDate) continue;
    let date: string | null = null;
    let dateLabel: string | null = typeof src.date_label === "string" && src.date_label.trim() ? src.date_label.trim().slice(0, 80) : null;
    if (rawDate) {
      if (isCalendarDate(rawDate)) date = rawDate;
      else { date = null; dateLabel = dateLabel ?? String(rawDate).slice(0, 80); } // 坏日期如实沉到原文描述，不造日历日
    }
    const note = typeof src.note === "string" ? src.note.trim().slice(0, 500) || null : null;
    const rawExpires = typeof src.expires_at === "string" ? src.expires_at.trim() : "";
    const expiresAt = rawExpires && isCalendarDate(rawExpires) ? rawExpires : null;
    const row: ExtractedRow = {
      eventType: rawType.slice(0, 40),
      date,
      dateLabel,
      note,
      expiresAt,
      status: normalizeStatus(src.status),
      importance: normalizeImportance(src.importance),
      phase: typeof src.phase === "string" && src.phase.trim() ? src.phase.trim().slice(0, 40) : null,
      side: typeof src.side === "string" && src.side.trim() ? src.side.trim().slice(0, 40) : null,
      sourceRefs: sanitizeSourceRefs(src.source_refs),
      payload: sanitizePayload(src.payload),
    };
    // 专项纪律校验面（对拍 11/13）：只警告不阻断（抽取内容仍如实入库）
    if (row.eventType === "开庭" && !row.note) warnings.push("开庭节点缺庭审详情备注（时间/法院/法庭/地址）");
    if (row.eventType === "执行立案" && row.note && !/(执|执恢|执保)/.test(row.note)) {
      warnings.push("执行立案节点备注未见执行案号（执/执恢/执保字样）");
    }
    // 对拍增补 63（对照源二）：AI 整理行逐条须带（材料名+页码/段落）双引用与置信度——
    // 缺失只警告不编造不丢弃（反编造铁律：缺出处/缺置信度如实缺省，验收面以警告透出）。
    const label = `${row.eventType || "未命名节点"}${row.date ? ` ${row.date}` : ""}`;
    if (!row.sourceRefs.some((r) => r.filename && r.locator)) warnings.push(`节点「${label}」缺（材料名+页码/段落）双引用出处`);
    if (row.payload?.confidence === undefined) warnings.push(`节点「${label}」缺置信度`);
    rows.push(row);
  }
  // C4 去重：date|event_type 保留首现（仅带日期行参与）
  const withDate = dedupByKeyKeepFirst(rows.filter((r) => r.date), (r) => `${r.date}|${r.eventType}`);
  const undated = rows.filter((r) => !r.date);
  return { rows: [...withDate, ...undated], warnings };
}

// ── 定向 hint（对拍 8 同构：8 类加节点 + 3 类不加 + 空默认；按文件名确定性正则，禁 LLM 猜）──
export function docHintOf(filename: string): { addNodes: boolean; hint: string } {
  const f = String(filename ?? "");
  if (/起诉状/.test(f)) return { addNodes: true, hint: "重点抽「申请立案」节点（立案申请日）。" };
  if (/判决书/.test(f)) return { addNodes: true, hint: "重点抽「判决」节点（判决作出日；反诉仍按原诉视角表述）。" };
  if (/调解书/.test(f)) return { addNodes: true, hint: "重点抽「调解」节点；分期履行的每期另加「还款期」行（date=该期付款日，note 注明期次与金额；计划时点不当实际履行）。" };
  if (/受理通知|应诉通知|立案通知/.test(f)) return { addNodes: true, hint: "重点抽「正式立案」节点。" };
  if (/解封/.test(f)) return { addNodes: true, hint: "抽「解封」节点，expires_at 置空（解封即取消续封提醒）。" };
  if (/保全|查封|扣押|冻结/.test(f)) return { addNodes: true, hint: "重点抽「保全」节点（带 expires_at 到期日；我方保全申请书不是期限依据、不得写 expires_at）。" };
  if (/传票|开庭通知/.test(f)) return { addNodes: true, hint: "每次开庭单独一条「开庭」行；note 写开庭时间+承办法院+第几法庭+法院地址，禁止写当事人住所地/送达地址。" };
  if (/上诉状/.test(f)) return { addNodes: true, hint: "重点抽「上诉」节点（上诉状提交日）。" };
  if (/委托合同|代理合同|委托代理/.test(f)) return { addNodes: true, hint: "重点抽「接案」节点（合同签订日）。" };
  if (/裁定书|答辩状|执行通知书|执行裁定/.test(f)) return { addNodes: false, hint: "本材料只用于核对当事人等基本信息，不加时间线节点。" };
  return { addNodes: true, hint: "" }; // 空默认分支：无定向提示，按通用规则抽
}

// ── 抽取 prompt 装配（全自写文案；白名单/反编造/格式合同/专项纪律都在此单源）──
export interface CorpusItem { name: string; text: string; hint: string; addNodes: boolean }
export function assembleExtractionPrompt(corpus: ReadonlyArray<CorpusItem>, baseToday: string): string {
  const parts: string[] = [];
  parts.push("你是办案时间线整理助手。从下面的案件材料全文中抽取办案时间线节点，只输出一个 JSON 数组，不要输出任何解释、前言、结语或 Markdown 代码块。");
  parts.push("【事件类型白名单（event_type 只能用这些值）】接案、申请立案、正式立案、保全、解封、开庭、调解、判决、上诉、二审开庭、二审判决、执行立案、开发票、还款期。");
  parts.push("【反编造铁律】材料里没有的节点不要造；抽不到就返回 []；禁止用「无」「待定」「不详」之类的占位词；没有把握到具体日的日期不要编日期，改用 date_label 写原文时段描述。");
  parts.push("【输出格式】JSON 数组，每个元素含以下字段：event_type（白名单内）、date（YYYY-MM-DD，不确定就省略）、date_label（模糊时段原文，可省略）、note（备注，可省略）、expires_at（到期日 YYYY-MM-DD，仅保全/还款期类，可省略）、status（confirmed/our_claim/opponent_claim/disputed/inferred/unknown 之一，可省略默认 confirmed）、importance（critical/normal/context 之一，可省略默认 normal）、phase（阶段分组，可省略）、side（我方/对方，可省略）、payload（对象，可省略：subjects=涉及主体字符串数组；behavior_nature=行为性质原文；amount_text=涉及金额原文串，只抄原文不要换算；dispute_note=争议说明）、source_refs（数组：出处材料名/页码段落定位/原句摘录）。");
  parts.push("【出处与置信度纪律】每个事件必须逐条给出可核查的出处：source_refs 至少一条 {filename, locator, quote}，locator 写页码或段落定位（文件+页码/段落双引用，缺一不可）；材料里查不到出处的节点不要输出，不要猜页码；每个事件同时给出 payload.confidence（0-1 小数，把握越高越接近 1，拿不准就给低值，不要留空）。");
  parts.push("【专项纪律】开庭行 note 必须写开庭时间+承办法院+第几法庭+法院地址，禁止写当事人住所地/送达地址/通讯地址；保全行 expires_at 按标的类型：资金冻结一年、车辆等动产二年、不动产股权等三年（自保全之日起算），解封行 expires_at 置空；执行立案行 note 必须写完整执行案号（执/执恢/执保字号），不写审判案号；还款期是计划时点不当实际履行；金额只抄原文串，不要计算不要换算成数字。");
  parts.push("【其他规则】同一事件在多份材料重复出现的合并为一条（出处都写进 source_refs）；多次开庭各成一条不合并；今天日期是 " + baseToday + "，只作参照，不要把材料事件日期改成今天。");
  parts.push("【材料全文】（按份编号，每份前的【定向提示】只约束该份材料）");
  corpus.forEach((c, i) => {
    const head = `第 ${i + 1} 份《${c.name}》` + (c.hint ? `【定向提示】${c.hint}` : "") + (c.addNodes ? "" : "（本份只核对信息，不抽节点）");
    parts.push(head + "\n" + c.text);
  });
  parts.push("现在只输出 JSON 数组。");
  return parts.join("\n\n");
}

// ── 编辑流：字段覆盖（provenance=user+locked_fields+orig 原值快照；首次编辑才记原值，
//    重复编辑不覆盖快照——↺ 永远回到抽取原值）──
export function applyCaseEventEdit(
  row: CaseEventProto,
  fields: Partial<Pick<CaseEventProto, "eventType" | "date" | "note">>,
  nowIso: string,
): { cols: Record<string, unknown>; editedFields: EditableField[] } {
  if (row.origin === "auto") throw new Error("业务动作事件的事实由动作定义，不可编辑字段值（只能隐藏）");
  const editedFields: EditableField[] = [];
  const cols: Record<string, unknown> = {};
  const orig: NonNullable<CaseEventProto["orig"]> = { ...(row.orig ?? {}) };
  const locked = new Set(row.lockedFields);
  if (fields.eventType !== undefined) {
    const t = String(fields.eventType).trim();
    if (!t) throw new Error("事件类型不能为空");
    if (t.length > 40) throw new Error("事件类型过长（≤40 字）");
    if (!locked.has("eventType")) orig.eventType = row.eventType;
    locked.add("eventType");
    cols.event_type = t;
    editedFields.push("eventType");
  }
  if (fields.date !== undefined) {
    if (fields.date !== null && !isCalendarDate(fields.date)) {
      throw new Error("日期须为 YYYY-MM-DD 日历日或 null（实收 " + JSON.stringify(fields.date) + "）");
    }
    if (!locked.has("date")) orig.date = row.date;
    locked.add("date");
    cols.date = fields.date ?? null;
    editedFields.push("date");
  }
  if (fields.note !== undefined) {
    if (fields.note !== null && typeof fields.note !== "string") throw new Error("备注须为字符串或 null");
    if (!locked.has("note")) orig.note = row.note;
    locked.add("note");
    cols.note = fields.note === null ? null : String(fields.note).slice(0, 500);
    editedFields.push("note");
  }
  if (!editedFields.length) throw new Error("无可编辑字段");
  cols.orig_json = JSON.stringify(orig);
  cols.locked_fields_json = JSON.stringify([...locked]);
  cols.provenance = "user";
  cols.updated_at = nowIso;
  return { cols, editedFields };
}

// ── 编辑流：逐字段 ↺ 恢复到抽取原值（清锁；锁清空且来源为 llm_extract 时 provenance 回 ai）──
export function restoreCaseEventField(
  row: CaseEventProto,
  field: EditableField,
  nowIso: string,
): { cols: Record<string, unknown> } {
  if (!row.lockedFields.includes(field)) throw new Error("该字段没有被覆盖，无需恢复");
  const orig = row.orig ?? {};
  if (!(field in orig)) throw new Error("覆盖原值缺失，无法恢复（数据异常，fail-closed）");
  const cols: Record<string, unknown> = {};
  if (field === "eventType") cols.event_type = orig.eventType ?? "";
  if (field === "date") cols.date = orig.date ?? null;
  if (field === "note") cols.note = orig.note ?? null;
  const locked = row.lockedFields.filter((f) => f !== field);
  cols.locked_fields_json = JSON.stringify(locked);
  if (!locked.length && row.origin === "llm_extract") cols.provenance = "ai";
  cols.updated_at = nowIso;
  return { cols };
}

// ── 重抽合并（D7 COALESCE 语义，纯函数）：只对 origin=llm_extract 行增量合并——
//    同 rowKey（event|date raw）命中→未锁字段更新（锁字段保现值=COALESCE）；旧有键新语料
//    没有的→保留（防子集语料静默抹除）；新键→插入；user/auto 行一律不碰。──
export interface MergePlan {
  inserts: ExtractedRow[];
  updates: Array<{ eventId: string; cols: Record<string, unknown> }>;
  keptCount: number;
}
export function planCaseEventMerge(existing: ReadonlyArray<CaseEventProto>, incoming: ReadonlyArray<ExtractedRow>, nowIso: string): MergePlan {
  const byKey = new Map<string, CaseEventProto>();
  for (const r of existing) {
    if (r.origin !== "llm_extract" || r.deleted) continue;
    byKey.set(rowKeyOf(r.eventType, r.date), r);
  }
  const plan: MergePlan = { inserts: [], updates: [], keptCount: 0 };
  const hit = new Set<string>();
  for (const inc of incoming) {
    const key = rowKeyOf(inc.eventType, inc.date);
    const cur = byKey.get(key);
    if (!cur) { plan.inserts.push(inc); continue; }
    hit.add(key);
    const cols: Record<string, unknown> = {};
    const locked = new Set(cur.lockedFields);
    if (!locked.has("eventType") && inc.eventType !== cur.eventType) cols.event_type = inc.eventType;
    if (!locked.has("date") && (inc.date ?? null) !== cur.date) cols.date = inc.date;
    if (!locked.has("note") && (inc.note ?? null) !== cur.note) cols.note = inc.note;
    if (!locked.has("date")) cols.date_label = inc.dateLabel; // date 未锁时精度描述随新抽走
    if (Object.keys(cols).length) {
      cols.updated_at = nowIso;
      plan.updates.push({ eventId: cur.eventId, cols });
    }
  }
  for (const key of byKey.keys()) if (!hit.has(key)) plan.keptCount += 1;
  return plan;
}

// ── 工作汇报「办案时间轴」节（对拍 35 = CB C12 等量；文案自写表达隔离，2026-10-28 补齐件）──
// 输入=full 口径行（覆盖已应用+软删已滤+C3 排序：日期升序+业务次序表=「按日期+标签排序」等量）。
// 每条=日期（加粗承载面）＋「：」＋事件＋（备注「 — 」连接）；无日期/无事件逐项兜底；空表整句。
// 日期兜底判据=isCalendarDate（坏串不进汇报日期位，落兜底词如实显示，不造日历日）。
export interface CaseReportLine {
  dateText: string; // 已过兜底链（不空串）
  eventText: string;
  noteText: string | null;
}
export const CASE_REPORT_DATE_FALLBACK = "日期未录";
export const CASE_REPORT_EVENT_FALLBACK = "未名事项";
export const CASE_REPORT_EMPTY_TEXT = "该案暂无时间线节点。";

export function buildCaseTimelineReportLines(
  rows: ReadonlyArray<{ eventType: string; date: string | null; note: string | null }>,
): { empty: boolean; lines: CaseReportLine[] } {
  if (!Array.isArray(rows) || rows.length === 0) return { empty: true, lines: [] };
  const lines: CaseReportLine[] = rows.map((r) => ({
    dateText: r.date && isCalendarDate(r.date) ? r.date : CASE_REPORT_DATE_FALLBACK,
    eventText: typeof r.eventType === "string" && r.eventType.trim() ? r.eventType.trim() : CASE_REPORT_EVENT_FALLBACK,
    noteText: typeof r.note === "string" && r.note.trim() ? r.note.trim() : null,
  }));
  return { empty: false, lines };
}
