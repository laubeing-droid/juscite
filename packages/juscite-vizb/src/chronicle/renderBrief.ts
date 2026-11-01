// 大事记 A4 呈报简表渲染（契约二：简表渲染零自由量——同一份渲染输入换格式呈现，
// 不重读材料、不重判断；字号/行高/版心/避头规则全为常量或由常量算出）。
// 输出=每页一张 SVG（A4 竖版）；分组色块是简表唯一允许的红色用途；
// 呈报件纪律：无内部痕迹标注、页码、句号收尾、序号连号。

import { xmlEscape } from "../shared/xml.ts";
import { deriveEvidenceStatus, type FactBase } from "./factbase.ts";
import { sortedFacts } from "./guards.ts";
import { clipForBrief } from "./textcheck.ts";

// ── 常量（0.1mm 单位；A4 竖版 2100×2970）──
export const BRIEF_PAGE = { w: 2100, h: 2970 } as const;
export const BRIEF_MARGIN = { top: 200, right: 200, bottom: 200, left: 200 } as const;
export const BRIEF_BODY_W = BRIEF_PAGE.w - BRIEF_MARGIN.left - BRIEF_MARGIN.right; // 1700
/** 简表列（我方自定）：序号/日期/事项/内容/证据状态。 */
export const BRIEF_COLS = [110, 360, 400, 630, 200] as const;
export const BRIEF_FONT = 34;                       // 正文字号（0.1mm 系）
export const BRIEF_LINE_H = 46;                     // 行高
export const BRIEF_CONTENT_CHARS = Math.floor(BRIEF_COLS[3]! / BRIEF_FONT); // 630/34=18 字/行
export const BRIEF_MAX_LINES = 3;                   // 主要内容至多三行
export const BRIEF_GROUP_RED = "#b3403a";           // 分组色块唯一红值
const INK = "#1f2937";
const MUTED = "#6b7280";
const LINE = "#d1d5db";
const FONT_STACK = "'Noto Sans CJK SC','Source Han Sans SC','Microsoft YaHei',sans-serif";

/** 内部痕迹禁词（只查机器撰写面——呈报件不出现程序标注；照录内容不在查验范围）。 */
export const BRIEF_BANNED_MARKERS = ["本程序新证据", "读图转写", "待补证标记", "内部痕迹"] as const;

export interface BriefRowPainted {
  factNo: number;
  dateLabel: string;
  item: string;
  lines: string[];
  evidence: string;
}

/** 渲染（纯函数）。返回每页 SVG；分页由常量行高反解（版心底界−页脚带）。 */
export function renderBrief(fb: FactBase): string[] {
  const facts = sortedFacts(fb);
  const volumes = [...new Set(facts.map((f) => f.volume))];
  const pages: string[] = [];
  let parts: string[] = [];
  let y = BRIEF_MARGIN.top;
  let pageNo = 1;
  const headerH = 150;
  const footerH = 120;
  const groupHeaderH = 90;
  const rowPad = 20;
  const bodyBottom = BRIEF_PAGE.h - BRIEF_MARGIN.bottom - footerH;

  const flush = () => {
    pages.push(svgPage(parts, pageNo));
    parts = [];
    y = BRIEF_MARGIN.top + headerH;
    pageNo += 1;
  };
  const ensure = (h: number) => { if (y + h > bodyBottom) flush(); };

  y += headerH;
  parts.push(`<text class="meta" x="${BRIEF_MARGIN.left}" y="${BRIEF_MARGIN.top + 90}" font-size="52" font-weight="700" fill="${INK}" font-family="${FONT_STACK}">${xmlEscape(`${fb.caseTitle}·大事记（呈报简表）`)}</text>`);
  for (const vol of volumes) {
    const volFacts = facts.filter((f) => f.volume === vol);
    ensure(groupHeaderH);
    parts.push(`<rect class="group" x="${BRIEF_MARGIN.left}" y="${y}" width="${BRIEF_BODY_W}" height="70" fill="${BRIEF_GROUP_RED}"/>`
      + `<text class="meta" x="${BRIEF_MARGIN.left + 24}" y="${y + 48}" font-size="36" font-weight="700" fill="#ffffff" font-family="${FONT_STACK}">${xmlEscape(`${vol}（${volFacts.length} 条）`)}</text>`);
    y += groupHeaderH;
    for (const f of volFacts) {
      const clip = clipForBrief(f.content, BRIEF_CONTENT_CHARS, BRIEF_MAX_LINES);
      const rowH = rowPad * 2 + BRIEF_LINE_H * Math.max(1, clip.lines.length);
      ensure(rowH);
      const x0 = BRIEF_MARGIN.left;
      const xNo = x0;
      const xDate = x0 + BRIEF_COLS[0]!;
      const xItem = xDate + BRIEF_COLS[1]!;
      const xContent = xItem + BRIEF_COLS[2]!;
      const xEvidence = xContent + BRIEF_COLS[3]!;
      parts.push(`<text class="no" x="${xNo + 30}" y="${y + rowPad + 34}" font-size="${BRIEF_FONT}" fill="${MUTED}" font-family="${FONT_STACK}">${f.factNo}</text>`);
      parts.push(`<text class="date" x="${xDate}" y="${y + rowPad + 34}" font-size="${BRIEF_FONT}" fill="${INK}" font-family="${FONT_STACK}">${xmlEscape(f.dateStr)}</text>`);
      parts.push(`<text class="item" x="${xItem}" y="${y + rowPad + 34}" font-size="${BRIEF_FONT}" fill="${INK}" font-family="${FONT_STACK}">${xmlEscape(`${f.verb}·${f.title}`)}</text>`);
      clip.lines.forEach((ln, li) => {
        parts.push(`<text class="content" x="${xContent}" y="${y + rowPad + 34 + li * BRIEF_LINE_H}" font-size="${BRIEF_FONT}" fill="${INK}" font-family="${FONT_STACK}">${xmlEscape(ln)}</text>`);
      });
      parts.push(`<text class="meta" x="${xEvidence}" y="${y + rowPad + 34}" font-size="28" fill="${MUTED}" font-family="${FONT_STACK}">${xmlEscape(deriveEvidenceStatus(f))}</text>`);
      y += rowH;
    }
  }
  flush();
  return pages;
}

function svgPage(parts: string[], pageNo: number): string {
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n`
    + `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${BRIEF_PAGE.w} ${BRIEF_PAGE.h}" width="${BRIEF_PAGE.w / 10}mm" height="${BRIEF_PAGE.h / 10}mm" font-family="${FONT_STACK}">`
    + `<desc>juscite-vizb 大事记呈报简表·确定性渲染（内容=原文前缀·停在句读·句号收尾）</desc>`
    + parts.join("")
    + `<text class="meta" x="${BRIEF_PAGE.w - BRIEF_MARGIN.right}" y="${BRIEF_PAGE.h - BRIEF_MARGIN.bottom - 24}" font-size="28" fill="${MUTED}" text-anchor="end" font-family="${FONT_STACK}">第 ${pageNo} 页</text>`
    + `</svg>`;
}
