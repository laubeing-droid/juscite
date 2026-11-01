// 契约三「文字=原句子序列（照录原文）」核心机制（净室自写）：
//  - 保真兜底：主要内容去标点后必须是源文本去标点后的子序列（保序包含），只许少取不许改写；
//  - 呈报简表裁剪：按句读边界取前缀，不按字截、不加省略号，一律句号收尾；
//    首句超行时按次级边界（冒号分号＞逗号＞顿号）取最长前缀且至少占满一行；
//  - 折行避孤字：末行少于三字从上一行借字；标点不悬挂出版心。
// 全部纯函数、零依赖、同输入同输出。

/** 去标点（中西文标点与空白全剥，只留实字符）——子序列判定前的归一化。 */
export function stripPunct(s: string): string {
  let out = "";
  for (const ch of s) {
    const c = ch.codePointAt(0)!;
    const isPunctOrSpace =
      (c >= 0x20 && c <= 0x2f) || (c >= 0x3a && c <= 0x40) || (c >= 0x5b && c <= 0x60) || (c >= 0x7b && c <= 0x7e)
      || (c >= 0x3000 && c <= 0x303f) // CJK 标点区
      || (c >= 0xff00 && c <= 0xffef && c < 0xff10) || (c >= 0xff1a && c <= 0xff20) || (c >= 0xff3b && c <= 0xff40) || (c >= 0xff5b && c <= 0xff65)
      || c === 0x2014 || c === 0x2026 || c === 0x00b7; // —…·
    if (!isPunctOrSpace) out += ch;
  }
  return out;
}

/** 保序子序列判定（双指针，与 stripPunct / firstDivergence 同用码点）。 */
export function isSubsequence(needle: string, haystack: string): boolean {
  const n = [...needle];
  const h = [...haystack];
  let i = 0;
  for (let j = 0; i < n.length && j < h.length; j++) {
    if (n[i] === h[j]) i++;
  }
  return i === n.length;
}

/** 首个分歧点（报错定位用）：返回 needle 中第一个无法在 haystack 保序匹配到的下标。 */
export function firstDivergence(needle: string, haystack: string): number {
  let i = 0; let j = 0;
  const n = [...needle]; const h = [...haystack];
  while (i < n.length && j < h.length) {
    if (n[i] === h[j]) { i++; j++; } else j++;
  }
  return i < n.length ? i : -1;
}

/** 句读定义：主句读（可收尾）＝。！？；；次级边界层级＝冒号分号＞逗号＞顿号。 */
const SENTENCE_ENDERS = new Set(["。", "！", "？", "；", "!", "?", ";"]);
const SECONDARY_TIERS: ReadonlyArray<ReadonlySet<string>> = [
  new Set(["：", "：", ":", ";", "；"]), // 第一层级：冒号·分号
  new Set(["，", ","]), // 第二层级：逗号
  new Set(["、"]), // 第三层级：顿号
];

/** 按主句读切句（保留分隔符在句尾）。 */
export function splitSentences(text: string): string[] {
  const out: string[] = [];
  let cur = "";
  for (const ch of text) {
    cur += ch;
    if (SENTENCE_ENDERS.has(ch)) { out.push(cur); cur = ""; }
  }
  if (cur) out.push(cur);
  return out;
}

export interface BriefClip {
  /** 画进图的内容（可能已补句号收尾；除此之外一字未动）。 */
  painted: string;
  /** 行数组（已折行+避孤字，每行 ≤ 每行字数）。 */
  lines: string[];
  /** 是否为整段（未裁剪）。 */
  full: boolean;
  /** 断言一：画进图的内容（去标点）必须是原文（去标点）前缀。 */
  isPrefix: boolean;
  /** 断言二：停在句读上（前缀末尾后紧跟主句读，或覆盖整段）。 */
  stopsAtBoundary: boolean;
}

/**
 * 简表裁剪（契约三·呈报面）：逐句累加取到完整句为止，至多 maxLines 行（每行 lineChars 字）；
 * 首句超行→次级边界取最长前缀且至少占满一行（宁可多占一行不出半句话）；
 * 一律句号收尾（仅补规范标点，不动内容）；不加省略号；折行避孤字（末行<3 字从上一行借一字）。
 */
export function clipForBrief(content: string, lineChars: number, maxLines: number): BriefClip {
  const chars = [...content];
  const budget = lineChars * maxLines;
  let taken = 0; // 取到的原文字符数（chars 下标，不含补写的句号）
  const sentences = splitSentences(content);
  for (const s of sentences) {
    if ([...s].length + taken <= budget) taken += [...s].length;
    else break;
  }
  if (taken === 0) {
    // 首句超行：次级边界分层取最长前缀（先在预算内找，找不到放宽一行——宁可多占一行）
    for (let widen = 0; widen <= 1 && taken === 0; widen++) {
      const limit = budget + widen * lineChars;
      for (const tier of SECONDARY_TIERS) {
        let best = -1;
        for (let i = 0; i < chars.length && i < limit; i++) if (tier.has(chars[i]!)) best = i;
        if (best >= (widen === 0 ? lineChars - 1 : 0)) { taken = best + 1; break; } // 预算内须至少占满一行；放宽档兜住任何长度
      }
    }
    if (taken === 0) taken = Math.min(chars.length, budget); // 全段无任何句读的退化档：满预算截断（记录在断言二，守卫面如实报）
  }
  const paintedCore = chars.slice(0, taken).join("");
  const lastCh = paintedCore.charAt(paintedCore.length - 1);
  const painted = SENTENCE_ENDERS.has(lastCh) ? paintedCore : paintedCore + "。"; // 句号收尾（规范标点）
  // 折行 + 避孤字（末行<3 字从上一行借一字——只挪位置不改字）
  const all = [...painted];
  const lines: string[] = [];
  for (let i = 0; i < all.length; i += lineChars) lines.push(all.slice(i, i + lineChars).join(""));
  if (lines.length >= 2 && [...lines[lines.length - 1]!].length < 3 && [...lines[lines.length - 2]!].length > 1) {
    const prev = [...lines[lines.length - 2]!];
    const borrowed = prev.pop()!;
    lines[lines.length - 2] = prev.join("");
    lines[lines.length - 1] = borrowed + lines[lines.length - 1]!;
  }
  // 两条出图断言（契约三：只验前缀不够，还必须停在句读上——取文末字必须是句末点号或逗顿冒分等读点；
  // 截九个字也是前缀，但末字是实字即半句话）
  const stripped = stripPunct(painted);
  const strippedFull = stripPunct(content);
  const isPrefix = strippedFull.startsWith(stripped);
  const lastTaken = chars[taken - 1] ?? "";
  const stopsAtBoundary = taken >= chars.length || SENTENCE_ENDERS.has(lastTaken) || SECONDARY_TIERS.some((t) => t.has(lastTaken));
  return { painted, lines, full: taken >= chars.length, isPrefix, stopsAtBoundary };
}
