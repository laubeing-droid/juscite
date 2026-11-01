// 摄入对账（I 组，#4/#19 共用前置；机制吸收自 TC 摄入判据，实现自写）：
//  - 逐页可读字符数探测（不看字体表）：剥页码标记后再计数；
//  - 可读字符过少的页判扫描件嫌疑；文字型材料仅末页印页码，剥页码后不误判；
//  - 完备性对账份数与页数两轨都平，三态=已读/明示不读/该读没读，仅第三态拒绝；
//  - 外部锚（卷宗页码）是扫描件唯一对账把手：扫描件无锚不可对账，如实报需 OCR，不静默放行。

export interface IntakePage {
  docId: string;
  pageNo: number;
  text: string;
  /** 卷宗页码（扫描件的外部锚）。 */
  anchor?: string;
}

export interface IntakeSkip {
  docId: string;
  pageNo?: number;       // 缺省=整份明示不读
  reason: string;        // 必须给理由（留痕）
}

export interface IntakeManifestDoc {
  docId: string;
  label: string;
  pageCount?: number;    // 已知才查页数轨；未知则只查份数轨
  kind?: "text" | "scan" | "unknown"; // 声明形态；未声明按 unknown 探测
}

export interface IntakeResult {
  ok: boolean; // 仅「该读没读」为假
  docs: Array<{
    docId: string;
    state: "read" | "explicitlySkipped" | "missing" | "partial-missing";
    pagesRead: number;
    pagesExpected: number | null;
    pagesExplicitlySkipped: number;
    pagesMissing: number[];
    scanSuspect: boolean;
    suspectPages: number[];
    anchorsMissing: boolean; // 扫描件嫌疑且页无外部锚
    notes: string[];
  }>;
  logs: string[];
}

const READABLE_MIN = 12;        // 剥页码后单页可读字符低于此数=扫描嫌疑页
const SCAN_SUSPECT_RATIO = 0.8; // 嫌疑页占比不低于此=整册扫描嫌疑

/** 剥页码标记：整行只有阿拉伯/罗马数字、「第 N 页/共 N 页」的行整行移除后再计数。 */
export function stripPageMarkers(text: string): string {
  return text
    .split(/\r?\n/)
    .filter((line) => {
      const t = line.trim();
      if (!t) return true; // 空行保留（版面逻辑不破坏，只是计数时本来就零贡献）
      if (/^\d{1,4}$/.test(t)) return false;
      if (/^[ivxlcdm]{1,7}$/i.test(t)) return false;
      if (/^第\s*\d{1,4}\s*页(共\s*\d{1,4}\s*页)?$/.test(t)) return false;
      if (/^page\s*\d{1,4}$/i.test(t)) return false;
      return true;
    })
    .join("\n");
}

/** 可读字符计数（CJK+字母+数字；标点空白不算）。 */
export function readableChars(text: string): number {
  let n = 0;
  for (const ch of text) {
    const c = ch.codePointAt(0)!;
    if ((c >= 0x4e00 && c <= 0x9fff) || (c >= 0x3400 && c <= 0x4dbf) || (c >= 0x41 && c <= 0x5a) || (c >= 0x61 && c <= 0x7a) || (c >= 0x30 && c <= 0x39)) n++;
  }
  return n;
}

// ══ #6 材料通道衔接面（B 轨规格 A7：只读公开行为契约；页文本+卷宗页码锚从真 PDF 解析来）══
// #6 公开导出的 PDF 文本层块结构面（{page, text,…} 取最小两键——结构兼容即可，不耦合其余字段）。
export interface PdfLayerBlock { page: number; text: string }

/**
 * 卷宗页码锚（外部锚）：页文本中独立成行的页码标记取其数字为锚值；无标记=null。
 * 标记口径与 stripPageMarkers 同族（第N页/纯数字行/罗马数字/英文 page N）——
 * 扫描件唯一对账把手：缺锚如实返回 null，由对账报「需补锚或 OCR」，不静默放行。
 */
export function volumeAnchorOf(pageText: string): string | null {
  for (const line of pageText.split(/\r?\n/)) {
    const t = line.trim();
    if (!t) continue;
    const m = /^第\s*(\d{1,4})\s*页/.exec(t);
    if (m) return m[1]!;
    if (/^\d{1,4}$/.test(t)) return t;
    if (/^[ivxlcdm]{1,7}$/i.test(t)) return t.toLowerCase();
    const p = /^page\s*(\d{1,4})$/i.exec(t);
    if (p) return p[1]!;
  }
  return null;
}

/**
 * #6 PDF 文本层块 → IntakePage[]：按页归组（页内块间换行），每页剥锚前先取卷宗页码锚。
 * 空白页（该页无块）照立页且文本为空——由可读字符探测如实判嫌疑，不替材料藏页。
 */
export function pagesFromPdfBlocks(docId: string, blocks: PdfLayerBlock[]): IntakePage[] {
  const byPage = new Map<number, string[]>();
  let maxPage = 0;
  for (const b of blocks ?? []) {
    const p = Math.max(1, Math.floor(Number(b?.page) || 1));
    if (!byPage.has(p)) byPage.set(p, []);
    byPage.get(p)!.push(String(b?.text ?? ""));
    maxPage = Math.max(maxPage, p);
  }
  const pages: IntakePage[] = [];
  for (let p = 1; p <= maxPage; p++) {
    const text = (byPage.get(p) ?? []).join("\n");
    const anchor = volumeAnchorOf(text);
    pages.push(anchor != null ? { docId, pageNo: p, text, anchor } : { docId, pageNo: p, text });
  }
  return pages;
}

/** #6 材料公开投影 → 对账清单行：pageCount 已知才查页数轨；kind 未声明按 unknown 探测。 */
export function manifestDocFromMaterial(m: { docId: string; label: string; pageCount?: number | null; kind?: "text" | "scan" | "unknown" }): IntakeManifestDoc {
  const out: IntakeManifestDoc = { docId: m.docId, label: m.label };
  if (m.pageCount != null) out.pageCount = m.pageCount;
  if (m.kind) out.kind = m.kind;
  return out;
}

/** 摄入对账（三态完备性：仅「该读没读」拒绝；明示不读放行并留痕）。 */
export function reconcileIntake(pages: IntakePage[], skips: IntakeSkip[], manifest: IntakeManifestDoc[]): IntakeResult {
  const logs: string[] = [];
  const byDoc = new Map<string, IntakePage[]>();
  for (const p of pages) {
    if (!byDoc.has(p.docId)) byDoc.set(p.docId, []);
    byDoc.get(p.docId)!.push(p);
  }
  const skipDoc = new Set(skips.filter((s) => s.pageNo == null).map((s) => s.docId));
  const skipPage = new Set(skips.filter((s) => s.pageNo != null).map((s) => `${s.docId}#${s.pageNo}`));
  for (const s of skips) logs.push(`[intake] 明示不读：${s.docId}${s.pageNo != null ? `#${s.pageNo}` : "（整份）"}，理由=${s.reason}`);

  const docs = manifest.map((m) => {
    const got = (byDoc.get(m.docId) ?? []).slice().sort((a, b) => a.pageNo - b.pageNo);
    const notes: string[] = [];
    const suspectPages: number[] = [];
    for (const p of got) {
      const rc = readableChars(stripPageMarkers(p.text));
      if (rc < READABLE_MIN) suspectPages.push(p.pageNo);
    }
    const scanSuspect = m.kind === "scan" || (got.length > 0 && suspectPages.length / got.length >= SCAN_SUSPECT_RATIO);
    if (scanSuspect && m.kind !== "scan") notes.push(`探测为扫描件嫌疑（嫌疑页 ${suspectPages.join(",") || "无"}，剥页码后可读字符 < ${READABLE_MIN}）`);
    if (m.kind === "scan") notes.push("声明的扫描件");
    const anchorsMissing = scanSuspect && got.some((p) => !p.anchor);
    if (anchorsMissing) notes.push("扫描件对账依赖外部锚（卷宗页码），存在缺锚页：需补锚或 OCR 后重对账，不静默放行");

    const pagesRead = got.filter((p) => !skipPage.has(`${p.docId}#${p.pageNo}`)).length;
    const expected = m.pageCount ?? null;
    const accounted = new Set<number>();
    for (const p of got) accounted.add(p.pageNo);
    const pagesMissing: number[] = [];
    if (expected != null) {
      for (let i = 1; i <= expected; i++) if (!accounted.has(i) && !skipPage.has(`${m.docId}#${i}`)) pagesMissing.push(i);
    }
    let state: IntakeResult["docs"][number]["state"];
    if (skipDoc.has(m.docId) && got.length === 0) state = "explicitlySkipped";
    else if (got.length === 0 && !skipDoc.has(m.docId)) state = "missing";
    else if (pagesMissing.length > 0) state = "partial-missing";
    else state = skipDoc.has(m.docId) ? "explicitlySkipped" : "read";
    return {
      docId: m.docId, state, pagesRead, pagesExpected: expected,
      pagesExplicitlySkipped: skipDoc.has(m.docId) ? got.length : [...skipPage].filter((k) => k.startsWith(`${m.docId}#`)).length,
      pagesMissing, scanSuspect, suspectPages, anchorsMissing, notes,
    };
  });
  const bad = docs.filter((d) => d.state === "missing" || d.state === "partial-missing");
  for (const d of bad) logs.push(`[intake] 拒绝：${d.docId} 该读没读（状态=${d.state}${d.pagesMissing.length ? `，缺页=${d.pagesMissing.join(",")}` : "，整份缺失"}）`);
  return { ok: bad.length === 0, docs, logs };
}
