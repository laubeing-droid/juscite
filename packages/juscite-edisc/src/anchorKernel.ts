// 【功能 #42 电子数据取证】锚内核（RE-42 §2.E/§3.1，纯模型零 I/O）。
// 证据固定粒度=页/坐标锚（与和讼 file_text_blocks 同门：页码+块序+坐标框+引擎+OCR 版本+源哈希，
// 命名我方自定——RE-42 §1.3 复用裁决"数据模型设计等价、字段级在手、功能等价自建、我方命名"）。
//
// 本文件只做确定性解析（正则/状态机，工作区工程约束 1），零大模型参与；
// 坐标系自定并显式携带版本与单位（RE-42 §5 UNKNOWN-3 口径）：
//   PDF_COORD_SYSTEM = "pdf-pt-v1-estwidth"
//     · 单位=PDF 点（pt），原点=页面左下（PDF 规范文本空间）
//     · x0/y0 = 文本矩阵（Tm/Td 累积）给出的行首基点 —— PDF 指令真值
//     · 高    = 当前字号（Tf 真值）
//     · 宽    = 确定性估宽（CJK 记 1em、其余记 0.5em）—— 估宽口径入锚记录，不冒充精确盒
// 旧锚不失效不变式（RE-42 §3.1 锚不变式）：块携带 fileHash 与落款 ocrVersion；
// 引擎/OCR 升级产生新版本时旧行并存，历史清单按其落款版本复现（由服务层入库保证，本层只携带）。
import { inflateRawSync } from "node:zlib";

// ── 数据模型（RE-42 §3.1 我方命名；个别通用字段名 page/bbox 与对照源同形属结构事实）──
export interface AnchoredBlock {
  blockId: string;
  page: number;
  seq: number;
  bbox: [number, number, number, number];
  coordSystem: string;
  text: string;
  engine: "text_layer" | "ocr_hook";
  ocrVersion: string | null;
  fileHash: string;
}

/** 聊天段结构化记录（RE-42 §2.H1：发送方/时间/内容逐段抽取，引用必带页/坐标锚） */
export interface ChatMessage {
  msgIndex: number;
  sender: string;
  sentAt: string;
  content: string;
  page: number;
  /** 内容首块锚（引用地址）；段内全部块序一并列出，供覆盖回跳 */
  anchorBlockId: string;
  contentBlockIds: string[];
  headerBlockId: string | null;
}

export const PDF_COORD_SYSTEM = "pdf-pt-v1-estwidth";
const CJK_FROM = 0x2e80; // CJK 部首起；以上按 1em 估宽
const round2 = (n: number) => Math.round(n * 100) / 100;

/** 确定性估宽：CJK 记 1em、其余 0.5em（口径见文件头） */
export function estimateTextWidth(text: string, fontSize: number): number {
  let em = 0;
  for (const ch of text) em += ch.codePointAt(0)! >= CJK_FROM ? 1 : 0.5;
  return em * fontSize;
}

// ── PDF 字符串字节还原：八进制转义→字节值；再按 UTF-8 严格解码，失败回落 latin1 ──
export function decodePdfStringBytes(sv: string): number[] {
  const out: number[] = [];
  for (let i = 0; i < sv.length; i++) {
    const ch = sv[i];
    if (ch === "\\") {
      const c = sv[++i];
      if (c === undefined) break;
      if (c === "n") out.push(10);
      else if (c === "r") out.push(13);
      else if (c === "t") out.push(9);
      else if (c === "b") out.push(8);
      else if (c === "f") out.push(12);
      else if (c >= "0" && c <= "7") {
        let oct = c;
        let k = 0;
        while (k < 2 && i + 1 < sv.length && sv[i + 1] >= "0" && sv[i + 1] <= "7") { oct += sv[++i]; k++; }
        out.push(parseInt(oct, 8) & 0xff);
      } else out.push(c.charCodeAt(0) & 0xff); // \( \) \\ 等
    } else out.push(ch.charCodeAt(0) & 0xff);
  }
  return out;
}
export function bytesToText(bytes: number[]): string {
  const buf = Buffer.from(bytes);
  try {
    return new TextDecoder("utf-8", { fatal: true }).decode(buf);
  } catch {
    return buf.toString("latin1"); // 传统单字节编码回落，不伪造多字节解读
  }
}

// ── 内容流记号类型（主扫描器内联于 extractAnchoredPdfBlocks）──
type Tok =
  | { t: "str"; sv: string }
  | { t: "arr"; items: Tok[] }
  | { t: "num"; v: number }
  | { t: "name"; v: string };

// 数组记号的独立解析（TJ 用）：只收字符串与数字
export function parseArrayLiteral(body: string, start: number): { items: Tok[]; end: number } {
  const items: Tok[] = [];
  let i = start;
  const n = body.length;
  while (i < n && body[i] !== "]") {
    const c = body[i];
    if (c === " " || c === "\n" || c === "\r" || c === "\t") { i++; continue; }
    if (c === "(") {
      let depth = 1; let sv = ""; i++;
      while (i < n && depth > 0) {
        const d = body[i];
        if (d === "\\") { sv += d + (body[i + 1] ?? ""); i += 2; continue; }
        if (d === "(") depth++;
        else if (d === ")") { depth--; if (depth === 0) break; }
        sv += d; i++;
      }
      i++; items.push({ t: "str", sv });
      continue;
    }
    if (/[0-9+.\-]/.test(c)) {
      let j = i;
      while (j < n && /[0-9+.\-]/.test(body[j])) j++;
      const v = Number(body.slice(i, j));
      if (Number.isFinite(v)) items.push({ t: "num", v });
      i = j;
      continue;
    }
    i++; // 其余（名字/分隔）跳过
  }
  return { items, end: i + 1 };
}

const num = (a: Tok[], k: number): number | null => {
  const t = a[a.length + k];
  return t && t.t === "num" ? t.v : null;
};

export interface PdfExtractResult {
  blocks: AnchoredBlock[];
  pageCount: number;
  /** 未被聊天段规则吸收的块数（H1 诚实口径：结构化不吞无主行） */
  engine: "text_layer";
}

/**
 * PDF 文本层锚抽取（RE-42 §2.E1）。支持的指令子集（确定性，不猜测）：
 * BT/ET、/Fn size Tf、a b c d e f Tm、tx ty Td、tx ty TD、n TL、T*、(s) Tj、[s n s] TJ、'。
 * 语义：Tm 取 e/f 为行首基点（旋转/缩放矩阵不外推——本版不伪造斜切坐标）；
 * Tj 不累积水平位移（PDF 规范 Tm 不随显示文本推进）；页归属按含文本操作的内容流顺序近似归页
 * （多数 PDF 一页一内容流，同 material_service 既有口径）。CID 无 CMap 的原始串按字节回落，
 * 不产出伪造正文——质量闸在服务层判定。
 */
export function extractAnchoredPdfBlocks(buf: Buffer, fileHash = ""): PdfExtractResult {
  const raw = buf.toString("latin1");
  const pageCount = Math.max(1, (raw.match(/\/Type\s*\/Page[^s]/g) ?? []).length);
  const blocks: AnchoredBlock[] = [];
  let seq = 0;
  let pageCursor = 0;
  for (const m of raw.matchAll(/stream\r?\n([\s\S]*?)endstream/g)) {
    let body = m[1];
    const head = raw.slice(Math.max(0, m.index! - 300), m.index!);
    if (/FlateDecode/.test(head)) {
      try {
        body = inflateRawSync(Buffer.from(m[1], "latin1")).toString("latin1");
      } catch {
        continue;
      }
    }
    if (!/\bTj\b|\bTJ\b/.test(body)) continue;
    const page = Math.min(pageCursor, pageCount - 1) + 1;
    pageCursor += 1;

    // 指令解释器：只维护行首基点/字号/行距
    let x = 0, y = 0, fontSize = 0, leading = 0;
    const emit = (sv: string) => {
      const text = bytesToText(decodePdfStringBytes(sv)).trim();
      if (!text) return;
      blocks.push({
        blockId: `eb_${page}_${String(seq).padStart(4, "0")}`,
        page, seq: seq++,
        bbox: [round2(x), round2(y), round2(x + estimateTextWidth(text, fontSize)), round2(y + fontSize)],
        coordSystem: PDF_COORD_SYSTEM,
        text, engine: "text_layer", ocrVersion: null, fileHash,
      });
    };

    let i = 0;
    const n = body.length;
    const args: Tok[] = [];
    while (i < n) {
      const c = body[i];
      if (c === " " || c === "\n" || c === "\r" || c === "\t") { i++; continue; }
      if (c === "%") { while (i < n && body[i] !== "\n") i++; continue; }
      if (c === "(") {
        let depth = 1; let sv = ""; i++;
        while (i < n && depth > 0) {
          const d = body[i];
          if (d === "\\") { sv += d + (body[i + 1] ?? ""); i += 2; continue; }
          if (d === "(") depth++;
          else if (d === ")") { depth--; if (depth === 0) break; }
          sv += d; i++;
        }
        i++; args.push({ t: "str", sv });
        continue;
      }
      if (c === "[") {
        const r = parseArrayLiteral(body, i + 1);
        args.push({ t: "arr", items: r.items });
        i = r.end;
        continue;
      }
      if (c === "/") {
        let j = i + 1;
        while (j < n && !/[\s/\[\]<>(){}%]/.test(body[j])) j++;
        args.push({ t: "name", v: body.slice(i + 1, j) });
        i = j;
        continue;
      }
      if (/[0-9+.\-]/.test(c)) {
        let j = i;
        while (j < n && /[0-9+.\-]/.test(body[j])) j++;
        const v = Number(body.slice(i, j));
        if (Number.isFinite(v)) args.push({ t: "num", v });
        i = j;
        continue;
      }
      let j = i;
      while (j < n && /[A-Za-z'"*]/.test(body[j])) j++;
      const op = body.slice(i, j);
      i = j;
      if (!op) continue;
      switch (op) {
        case "BT": x = 0; y = 0; break; // 文本矩阵回单位阵（规范行为）
        case "Tf": {
          const s = num(args, -1);
          if (s !== null && s > 0) fontSize = s;
          break;
        }
        case "Tm": {
          const ex = num(args, -2), ey = num(args, -1);
          if (ex !== null && ey !== null) { x = ex; y = ey; }
          break;
        }
        case "Td": {
          const dx = num(args, -2), dy = num(args, -1);
          if (dx !== null && dy !== null) { x += dx; y += dy; }
          break;
        }
        case "TD": {
          const dx = num(args, -2), dy = num(args, -1);
          if (dx !== null && dy !== null) { x += dx; y += dy; leading = -dy; }
          break;
        }
        case "TL": {
          const l = num(args, -1);
          if (l !== null) leading = l;
          break;
        }
        case "T*": y -= leading; break;
        case "Tj": {
          const a0 = args[args.length - 1];
          if (a0 && a0.t === "str") emit(a0.sv);
          break;
        }
        case "TJ": {
          const a0 = args[args.length - 1];
          if (a0 && a0.t === "arr") {
            const sv = a0.items.filter((it): it is { t: "str"; sv: string } => it.t === "str").map((it) => it.sv).join("");
            if (sv) emit(sv);
          }
          break;
        }
        case "'": {
          y -= leading;
          const a0 = args[args.length - 1];
          if (a0 && a0.t === "str") emit(a0.sv);
          break;
        }
        default: break; // 其余指令与坐标无关，忽略
      }
      args.length = 0;
    }
  }
  return { blocks, pageCount: Math.max(pageCount, blocks.length ? blocks[blocks.length - 1].page : 0), engine: "text_layer" };
}

// ── 聊天段结构化（RE-42 §2.H1）：两类常见导出行式的确定性识别 ──
// 行式一（两行式）：头行“发送方 + 时间”，随后块为内容，直到下一头行；
// 行式二（单行式）：“[时间] 发送方：内容”。
// 页眉页脚页码行（整行仅“第N页/页码 N/M”形态）不并入消息内容，按无主块保留（不硬归）。
const HEADER_RE = /^(\S{1,32}?)\s+(\d{4}-\d{2}-\d{2}\s+\d{1,2}:\d{2}(?::\d{2})?)$/u;
const INLINE_RE = /^\[(\d{4}-\d{2}-\d{2}\s+\d{1,2}:\d{2}(?::\d{2})?)\]\s*(\S{1,32}?)\s*[：:]\s*([\s\S]*)$/u;
const PAGE_MARK_RE = /^[（(【\[]?\s*(?:第\s*\d+\s*页|\d+\s*\/\s*\d+)\s*[)）】\]]?$/u;

export interface ChatParseResult {
  messages: ChatMessage[];
  /** 未能结构化的块（页眉/页脚/分隔等）：如实保留计数，不硬归 */
  unstructuredBlockIds: string[];
}

export function parseChatSegments(blocks: AnchoredBlock[]): ChatParseResult {
  const messages: ChatMessage[] = [];
  const used = new Set<string>();
  let idx = 0;
  let pending: { sender: string; sentAt: string; headerBlockId: string; contentBlocks: AnchoredBlock[] } | null = null;
  const flush = () => {
    if (!pending) return;
    const contentBlocks = pending.contentBlocks;
    if (contentBlocks.length) {
      messages.push({
        msgIndex: idx++,
        sender: pending.sender,
        sentAt: pending.sentAt,
        content: contentBlocks.map((b) => b.text).join("\n"),
        page: contentBlocks[0].page,
        anchorBlockId: contentBlocks[0].blockId,
        contentBlockIds: contentBlocks.map((b) => b.blockId),
        headerBlockId: pending.headerBlockId,
      });
      for (const b of contentBlocks) used.add(b.blockId);
    }
    pending = null;
  };
  for (const b of blocks) {
    const hm = HEADER_RE.exec(b.text);
    if (hm) {
      flush();
      used.add(b.blockId);
      pending = { sender: hm[1], sentAt: hm[2], headerBlockId: b.blockId, contentBlocks: [] };
      continue;
    }
    const im = INLINE_RE.exec(b.text);
    if (im) {
      flush();
      used.add(b.blockId);
      const inline: AnchoredBlock = { ...b, text: im[3] }; // 内容锚仍挂本块
      pending = { sender: im[2], sentAt: im[1], headerBlockId: b.blockId, contentBlocks: [inline] };
      flush();
      used.add(b.blockId);
      continue;
    }
    if (PAGE_MARK_RE.test(b.text)) continue; // 页码/页眉行不入消息（保留为无主块）
    if (pending) pending.contentBlocks.push(b);
    // 无 pending 的散行留 unstructured
  }
  flush();
  const unstructuredBlockIds = blocks.filter((b) => !used.has(b.blockId)).map((b) => b.blockId);
  return { messages, unstructuredBlockIds };
}

/** 锚不变式（RE-42 §3.1）：块哈希须与源哈希一致才可被引用 */
export function anchorInvariantOk(sourceFileHash: string, block: { fileHash: string }): boolean {
  return Boolean(sourceFileHash) && sourceFileHash === block.fileHash;
}

/** 页内块筛选（页卡阅读面 E4：整页覆盖，不抽样） */
export function blocksOfPage(blocks: AnchoredBlock[], page: number): AnchoredBlock[] {
  return blocks.filter((b) => b.page === page).sort((a, b) => a.seq - b.seq);
}
