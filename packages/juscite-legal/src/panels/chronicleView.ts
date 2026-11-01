// 【施工波二轮·可视化B轨 UI 件】大事记（功能 #4 深化）面板侧投影纯函数。
// 依据：竞品情报/2026-10-29-规格波/可视化-B轨规格.md §四 A1——「底稿=既有事件账本的投影视图」。
// 本文件只做确定性投影（时间线事件行→大事记事实行），封闭 schema 校验与 A/B/C/D/E 判据守卫
// 全在桥面 @juscite/vizb（bridge vizbChronicleCheck/Render 为唯一判定源），此处零判据零渲染。
// 投影裁决（如实披露，宁缺不造）：
//   ① 只收「有日期 + 有带引文的材料出处 + 材料文本已取到」的事件——无日期不造日（fail-closed），
//      无引文即无照录内容（照录判据要求主要内容为源文子序列，笔记/备注是律师撰述不是照录）；
//   ② verb=eventType、title=eventType、locator、subjects 原样透传，不本地改写不改判
//      （封闭动词表/定位形态/标题字数等判定全在桥面，表外拒绝走补表流程）；
//   ③ 同一来源文档内的事实按引文在源文中首次出现位置排序（对应切分可复原判据的保序要求）；
//   ④ evidenceNo 恒 null（事件账本无证据编号概念）→ 桥面机械置「仅当事人陈述」并自动进不确定清单；
//   ⑤ docs 单册口径（volume 恒「卷一」，事件账本无分册概念，界面文案如实披露）。
// 结构对齐 @juscite/vizb src/chronicle/factbase.ts 的 FactBase（schema juscite.vizb.chronicle.factbase@1）；
// 字段单源在 vizb 包，此处仅视图层结构镜像，形状以桥面校验为准（面板不依赖 vizb 包，RPC 传 JSON）。
// 零运行时导入（纯函数自包含），Node 与浏览器两侧均可直接消费。

export interface ChronicleEventLike {
  eventId: string;
  eventType: string;
  date: string | null;
  sourceRefs: Array<{ filename: string; locator?: string; quote?: string }>;
  payload: { subjects?: unknown[] } | null;
}

export interface ChronicleDocText {
  filename: string;
  text: string;
  truncated: boolean;
}

export interface ChronicleFactRow {
  factNo: number;
  dateStr: string;
  datePrecision: "day";
  verb: string;
  title: string;
  content: string;
  sourceDoc: string;
  locator: string;
  evidenceNo: null;
  volume: string;
  subjects: string[];
  dispute: null;
  arithmeticNote: null;
}

export interface ChronicleFactBase {
  schema: "juscite.vizb.chronicle.factbase@1";
  caseTitle: string;
  docs: Array<{ docId: string; label: string; volume: string; text: string }>;
  facts: ChronicleFactRow[];
  uncertainty: string[];
}

export interface ChronicleProjection {
  factBase: ChronicleFactBase;
  included: number;
  excluded: Array<{ eventId: string; eventType: string; reason: string }>;
}

/** 投影：时间线事件 → 大事记事实底稿。同输入两跑结果逐字节一致（确定性纪律）。 */
export function projectChronicleFactBase(
  events: ChronicleEventLike[],
  docTexts: ChronicleDocText[],
  caseTitle: string,
): ChronicleProjection {
  const textOf = new Map<string, string>();
  for (const d of docTexts) textOf.set(d.filename, d.text);

  interface Draft {
    eventId: string;
    eventType: string;
    dateStr: string;
    verb: string;
    title: string;
    content: string;
    sourceDoc: string;
    locator: string;
    subjects: string[];
    quoteAt: number; // 引文在源文中首次出现位置（-1=未命中，保持入序）
  }
  const drafts: Draft[] = [];
  const excluded: ChronicleProjection["excluded"] = [];

  for (const ev of events) {
    if (typeof ev.date !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(ev.date)) {
      excluded.push({ eventId: ev.eventId, eventType: ev.eventType, reason: "无确切日期（不造日，认不准不编入）" });
      continue;
    }
    const ref = (ev.sourceRefs ?? []).find(
      (r) => typeof r.filename === "string" && r.filename.length > 0
        && typeof r.quote === "string" && r.quote.length > 0,
    );
    if (!ref) {
      excluded.push({ eventId: ev.eventId, eventType: ev.eventType, reason: "缺带引文的材料出处（无照录内容）" });
      continue;
    }
    const text = textOf.get(ref.filename);
    if (typeof text !== "string") {
      excluded.push({ eventId: ev.eventId, eventType: ev.eventType, reason: "材料文本未取到（引用无法核照录）" });
      continue;
    }
    drafts.push({
      eventId: ev.eventId,
      eventType: ev.eventType,
      dateStr: ev.date,
      verb: ev.eventType, // 原样透传：动词封闭表判定在桥面
      title: ev.eventType, // 原样透传：标题字数/定性词判定在桥面
      content: ref.quote!, // 照录：引文即主要内容，子序列核验在桥面
      sourceDoc: ref.filename,
      locator: typeof ref.locator === "string" ? ref.locator : "", // 原样透传：定位形态判定在桥面
      subjects: (ev.payload?.subjects ?? []).filter((s): s is string => typeof s === "string" && s.length > 0),
      quoteAt: text.indexOf(ref.quote!),
    });
  }

  // 同源事实按引文首现位置排序（稳定排序，未命中者保持相对入序）；跨来源按来源首次出现次序分组拼接
  const docOrder: string[] = [];
  for (const d of drafts) if (!docOrder.includes(d.sourceDoc)) docOrder.push(d.sourceDoc);
  const facts: ChronicleFactRow[] = [];
  docOrder.forEach((docId, docIdx) => {
    drafts
      .filter((d) => d.sourceDoc === docId)
      .map((d, i) => ({ d, i }))
      .sort((a, b) => (a.d.quoteAt - b.d.quoteAt) || (a.i - b.i))
      .forEach(({ d }) => {
        facts.push({
          factNo: facts.length + 1, // 顺序分配、删行不回收（本投影每次重建，号随重建序）
          dateStr: d.dateStr,
          datePrecision: "day",
          verb: d.verb,
          title: d.title,
          content: d.content,
          sourceDoc: d.sourceDoc,
          locator: d.locator,
          evidenceNo: null,
          volume: "卷一", // 单册口径：事件账本无分册概念
          subjects: d.subjects,
          dispute: null, // 争点恒空：律师在 Excel 母表回填
          arithmeticNote: null,
        });
      });
    void docIdx;
  });

  return {
    factBase: {
      schema: "juscite.vizb.chronicle.factbase@1",
      caseTitle,
      docs: docOrder.map((docId) => ({ docId, label: docId, volume: "卷一", text: textOf.get(docId) ?? "" })),
      facts,
      uncertainty: [], // 起底恒空：无书证事实由桥面 composeChronicle 机械联动补入
    },
    included: facts.length,
    excluded,
  };
}

// ── 摄入对账（I 组共用前置）面板侧载荷 ──
// 面板只有「整份材料全文」，没有逐页文本通道：按整份单页口径对账（如实披露），
// manifest 不带 pageCount（页数轨无数据不查，只查份数轨）；文本取不到的材料故意缺席
// pages → 桥面判「该读没读」拒绝。明示不读=用户在时间轴面板勾选忽略且该材料仍被引用。

export interface IntakePayload {
  pages: Array<{ docId: string; pageNo: number; text: string }>;
  skips: Array<{ docId: string; reason: string }>;
  manifest: Array<{ docId: string; label: string; kind: "unknown" }>;
}

/** 组装摄入对账载荷：referenced=底稿引用的材料名集合；ignored=用户明示忽略的材料名集合。 */
export function buildIntakePayload(
  docTexts: ChronicleDocText[],
  referenced: string[],
  ignored: string[],
): IntakePayload {
  const ignoredSet = new Set(ignored);
  return {
    pages: docTexts.map((d) => ({ docId: d.filename, pageNo: 1, text: d.text })),
    skips: referenced.filter((n) => ignoredSet.has(n))
      .map((n) => ({ docId: n, reason: "用户在时间轴面板勾选忽略抽取（明示不读留痕）" })),
    manifest: referenced.map((n) => ({ docId: n, label: n, kind: "unknown" as const })),
  };
}

/** 下载文件名净化：去路径分隔与系统保留字符，空则回退「案件」。 */
export function sanitizeDownloadName(raw: string): string {
  const cleaned = raw.replace(/[\\/:*?"<>|\r\n]+/g, "").trim();
  return cleaned.length ? cleaned : "案件";
}
