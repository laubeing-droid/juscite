"""E12 全合成 OCR 验收语料生成器（律引 JusBench，工单 W2a-U01）。

依据 00-总协调 §6.1 裁决#1：5000 页 OCR 验收语料**全合成**——含故障样本，不用任何真实文档；
D:\\文档处理 是 OCR 引擎基准（pdf2md_core）不是语料库，本生成器不读它。

三种用法：
1. 生成：`python -X utf8 tools/e12_corpus_gen.py --pages 5000 --seed 20261015 --out <dir>`
   产合成页集（文本页/跨页表/旋转/重复/空白/低置信故障页）＋页号 bbox 金标＋总清单
   corpus_manifest.json ＋ corpus_digest.txt。
2. 复验：`python -X utf8 tools/e12_corpus_gen.py --verify <dir>`
   对既有语料目录重算哈希/配额/结构/PDF 一致性（E12 验收 W2a-U02 的复验入口）。
3. 自检：`python -X utf8 tools/e12_corpus_gen.py --selftest`
   临时目录小规模两遍生成逐文件比字节（同 seed 同字节）＋异 seed 差异＋--verify 全绿。
4. F48 DOCX 模式：`python -X utf8 tools/e12_corpus_gen.py --docx <dir> --seed 20261017`
   产全合成复杂 DOCX 两份（复杂版＋现存修订版）＋docx_manifest.json（F48 edits 验收语料）。

确定性口径：同 seed、同机、同 Python/Pillow/zlib/字体文件（font sha256 记入清单）→ 逐文件同字节。
金额一律整分（int cents）生成、Decimal 两位小数量化渲染；不写 %APPDATA%；产物落调用方目录
（默认 %TEMP%），不入 git（合成材料红线）。全部当事人/案号/金额均为合成虚构。
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import random
import re
import sys
import tempfile
import zlib
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_EVEN
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

SCHEMA = "juscite-e12-corpus/1"
GEN_REV = "tools/e12_corpus_gen.py r1 (W2a-U01)"
MANIFEST_NAME = "corpus_manifest.json"
DIGEST_NAME = "corpus_digest.txt"

# ---------- 版面常量（A4 @ dpi，默认 120） ----------
A4_IN = (8.27, 11.69)
DEFAULT_DPI = 120
MARGIN_X = 86
HEADER_Y = 48
BODY_TOP = 120
FOOTER_CY = None  # 运行时按页高算（H-58）
BODY_LINE_H = 30
BODY_FONT = 20
TITLE_FONT = 32
SMALL_FONT = 15
FOOTER_FONT = 18
TABLE_ROW_H = 64
TABLE_HEADER_H = 40
TABLE_FONT = 24
TABLE_TITLE_FONT = 26

# 故障/结构配额默认值（占总页数比例；精确整数按最大余数法落位）
DEFAULT_QUOTA = {
    "table": 0.10,    # 跨页表页（TABLE_SPAN+TABLE_CONT 合计）
    "rotated": 0.05,  # 旋转页 90/180/270
    "duplicate": 0.03,  # 重复页（字节级复刻同卷早前文本页）
    "blank": 0.03,    # 空白页
    "lowconf": 0.04,  # 低置信故障页（模糊+椒盐噪声降质）
}
FAULT_KINDS = ("rotated", "duplicate", "blank", "lowconf")

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simsun.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
]

DOC_TYPES = ["借款合同", "买卖合同", "房屋租赁", "劳动争议", "加工承揽"]
PLAINTIFFS = ["合某诚科技有限公司", "京某源贸易有限公司", "海某通实业有限公司", "深某立信息科技有限公司"]
DEFENDANTS = ["北某建工集团有限公司", "广某泰房地产开发有限公司", "杭某云网络科技有限公司", "蓉某信商贸有限公司"]

# 合成句池：全部虚构，不含任何真实主体。
SENTENCES = [
    "甲方与乙方经友好协商，就借款事宜达成如下条款，双方均确认本协议系真实意思表示。",
    "借款本金由甲方通过银行转账方式支付至乙方指定账户，到账日即视为放款完成。",
    "双方确认借款利率按年利率计算，利息自实际放款之日起算，按月结息。",
    "乙方应按还款计划表约定的期次、金额按时足额偿还本金及利息。",
    "若乙方未按期履行还款义务，甲方有权宣布全部剩余债务提前到期并要求立即清偿。",
    "因本合同引起的争议，双方应先行协商解决；协商不成的，提交有管辖权的人民法院裁判。",
    "合同一式两份，甲乙双方各执一份，自双方签字或盖章之日起生效。",
    "乙方保证其提供的全部资料真实、完整、有效，如有虚假愿承担相应法律责任。",
    "本合同履行过程中涉及的通知均应以书面形式送达对方载明的联系方式。",
    "甲方有权对借款使用情况进行监督，乙方应予以配合并提供相关凭证。",
    "还款计划表作为本合同附件，与本合同具有同等法律效力。",
    "任何一方违反本合同约定给对方造成损失的，应承担相应赔偿责任。",
    "双方确认本页所述金额均以人民币元为单位，数值保留两位小数。",
    "抵押物登记事项由双方共同办理，登记费用由乙方承担。",
    "乙方提前还款的，应至少提前十日书面通知甲方并经甲方确认。",
    "本协议项下之债务未经甲方书面同意不得转让给第三人。",
    "担保人对乙方在本合同项下的全部债务承担连带保证责任。",
    "保证期间自本合同生效之日起至全部债务清偿完毕之日止。",
    "因不可抗力致使合同无法履行的，双方互不承担违约责任但应及时通知对方。",
    "双方同意以签章页所载地址作为司法送达地址，适用于诉讼及执行程序。",
]

AMOUNT_RE_DIGITS = 2  # 金额渲染统一两位小数（整分）


def eprint(*a) -> None:
    print(*a, file=sys.stderr)


def utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_font(dpi: int, size: int) -> ImageFont.FreeTypeFont:
    for cand in FONT_CANDIDATES:
        if Path(cand).is_file():
            return ImageFont.truetype(cand, size)
    raise SystemExit(f"[FAIL] 找不到候选字体：{FONT_CANDIDATES}")


def font_path() -> Path:
    for cand in FONT_CANDIDATES:
        if Path(cand).is_file():
            return Path(cand)
    raise SystemExit(f"[FAIL] 找不到候选字体：{FONT_CANDIDATES}")


def cents_str(cents: int) -> str:
    """整分 → '12345.67'（Decimal 量化，禁浮点）。"""
    return str((Decimal(cents) / Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN))


# ---------- 配额：最大余数法精确落位 ----------
def quota_counts(pages: int, quota: dict[str, float]) -> dict[str, int]:
    """最大余数法：非 text 类合计席位 = round(pages×Σquota)，按小数部分从大到小补 1；text 拿兜底余额。"""
    floors: dict[str, int] = {}
    fracs: list[tuple[float, str]] = []
    used = 0
    total_raw = 0.0
    for k in sorted(quota):
        raw = pages * quota[k]
        total_raw += raw
        fl = math.floor(raw)
        floors[k] = fl
        fracs.append((raw - fl, k))
        used += fl
    rem = int(round(total_raw)) - used
    for _, k in sorted(fracs, key=lambda t: (-t[0], t[1])):
        if rem <= 0:
            break
        floors[k] += 1
        rem -= 1
    if rem > 0:  # 浮点尾差兜底：给最大比例项
        kmax = max(sorted(quota), key=lambda k: quota[k])
        floors[kmax] += rem
    floors["text"] = pages - sum(floors[k] for k in quota)
    return floors


# ---------- 文档与页型规划 ----------
def plan_corpus(rng: random.Random, pages: int, counts: dict[str, int]) -> list[dict]:
    """返回 doc 列表，每 doc 含 page_kinds 序列（约束：首页 TEXT；表组不跨卷；重复页引用同卷早前 TEXT）"""
    # 跨页表组分解：每组 2-4 页，组内连续
    groups: list[int] = []
    t = counts["table"]
    if t > 0:
        if t == 1:
            raise SystemExit("[FAIL] 跨页表配额页数为 1，无法成组（组最少 2 页）")
        if t % 3 == 1:
            groups += [2, 2]
            t -= 4
        elif t % 3 == 2:
            groups += [2]
            t -= 2
        groups += [3] * (t // 3)
        rng.shuffle(groups)
    if any(g < 2 for g in groups):
        raise SystemExit("[FAIL] 内部错误：表组 <2 页")

    # 各卷页数 18..48，尾卷 <8 并入前卷
    doc_lens: list[int] = []
    remaining = pages
    while remaining > 0:
        n = min(remaining, rng.randint(18, 48))
        if 0 < remaining - n < 8:
            n = remaining
        doc_lens.append(n)
        remaining -= n
    n_docs = len(doc_lens)

    text_units = counts["text"] - n_docs  # 每卷首页预留 1 页 TEXT（标题页）
    if text_units < 0:
        raise SystemExit(f"[FAIL] 页数太少：{n_docs} 卷需 {n_docs} 个标题页 > 文本配额 {counts['text']}")

    units: list[tuple[str, int]] = []
    units += [("TEXT", 1)] * text_units
    units += [("ROTATED", 1)] * counts["rotated"]
    units += [("DUPLICATE", 1)] * counts["duplicate"]
    units += [("BLANK", 1)] * counts["blank"]
    units += [("LOWCONF", 1)] * counts["lowconf"]
    units += [("TABLE", g) for g in groups]
    rng.shuffle(units)

    docs: list[dict] = []
    qi = 0
    for di, dlen in enumerate(doc_lens):
        kinds: list[list] = [["TEXT"]]  # 首页固定 TEXT 标题页
        slots = dlen - 1
        while slots > 0:
            # 从队列找下一个放得下的 unit；优先非 TEXT 保持混排，找不到放得下的非 TEXT 再找 TEXT
            pick = -1
            for j in range(qi, len(units)):
                if units[j][1] <= slots:
                    pick = j
                    break
            if pick == -1:
                # 队列剩余都放不下（只可能是表组），其后必须还有 TEXT unit 兜底不可能；fail-fast
                raise SystemExit(
                    f"[FAIL] 规划失败：卷 {di} 剩 {slots} 位放不下任何 unit（队首 {units[qi:qi+3]}）"
                )
            kind, ulen = units.pop(pick) if pick >= qi else (None, None)
            if kind == "TABLE":
                kinds.append(["TABLE_SPAN"] + ["TABLE_CONT"] * (ulen - 1))
            else:
                kinds.append([kind])
            slots -= ulen
        docs.append({"doc_index": di, "page_kinds": [k for unit in kinds for k in unit]})
    if units:
        # 全卷装满仍有剩余（理论上 text=1 的 unit 一定放得下任意空位，除非 slots=0 且队列非空——即配额超页）
        raise SystemExit(f"[FAIL] 规划失败：{len(units)} 个 unit 未落位（配额与页数不符）")
    return docs


# ---------- 页面渲染 ----------
class PageSpec:
    """一次生成的版面参数（全确定性）。"""

    def __init__(self, dpi: int):
        self.dpi = dpi
        self.W = round(A4_IN[0] * dpi)
        self.H = round(A4_IN[1] * dpi)
        self.footer_cy = self.H - 58


def _bbox_of_text(spec: PageSpec, text: str, font: ImageFont.FreeTypeFont, cx: int, cy: int) -> list[int]:
    w = int(font.getlength(text))
    asc, desc = font.getmetrics()
    h = asc + desc
    return [cx - w // 2, cy - h // 2, cx - w // 2 + w, cy - h // 2 + h]


def draw_frame(img: Image.Image, spec: PageSpec, fonts: dict, doc_code: str, page_no: int) -> dict:
    """页眉（合成标识）＋页脚页号。返回金标（未旋转坐标系）。"""
    draw = ImageDraw.Draw(img)
    gold: dict = {}
    header_text = f"合成测试卷 {doc_code}｜JUSCITE-E12 全合成语料（非真实案卷）"
    hf = fonts["small"]
    draw.text((MARGIN_X, HEADER_Y), header_text, font=hf, fill=128)
    w = int(hf.getlength(header_text))
    asc, desc = hf.getmetrics()
    gold["header"] = {"text": header_text, "bbox_px": [MARGIN_X, HEADER_Y, MARGIN_X + w, HEADER_Y + asc + desc]}
    tag_text = f"SYNTHETIC-E12"
    tag_w = int(hf.getlength(tag_text))
    draw.text((spec.W - MARGIN_X - tag_w, HEADER_Y), tag_text, font=hf, fill=128)
    gold["synthetic_tag"] = {
        "text": tag_text,
        "bbox_px": [spec.W - MARGIN_X - tag_w, HEADER_Y, spec.W - MARGIN_X, HEADER_Y + asc + desc],
    }
    pn_text = f"- {page_no} -"
    ff = fonts["footer"]
    draw.text((spec.W // 2, spec.footer_cy), pn_text, font=ff, fill=40, anchor="mm")
    gold["page_no"] = {
        "text": pn_text,
        "bbox_px": _bbox_of_text(spec, pn_text, ff, spec.W // 2, spec.footer_cy),
    }
    return gold


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    lines: list[str] = []
    cur = ""
    for ch in text:
        if draw.textlength(cur + ch, font=font) > max_w and cur:
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        lines.append(cur)
    return lines


def render_text_page(
    img: Image.Image, spec: PageSpec, fonts: dict, rng: random.Random, lines_budget: int, title_mode: bool, doc: dict
) -> dict:
    draw = ImageDraw.Draw(img)
    gold: dict = {}
    y = BODY_TOP
    max_w = spec.W - 2 * MARGIN_X
    bf = fonts["body"]
    if title_mode:
        tf = fonts["title"]
        draw.text((MARGIN_X, y), doc["title"], font=tf, fill=20)
        w = int(tf.getlength(doc["title"]))
        asc, desc = tf.getmetrics()
        gold["title_bbox_px"] = [MARGIN_X, y, MARGIN_X + w, y + asc + desc]
        y += asc + desc + 18
        for meta in (f"案号：{doc['case_no']}", f"原告：{doc['plaintiff']}", f"被告：{doc['defendant']}",
                     "（本卷为全合成测试材料，当事人、案号、金额均系虚构）"):
            draw.text((MARGIN_X, y), meta, font=bf, fill=60)
            y += BODY_LINE_H
        y += 14
    used = 0
    while used < lines_budget:
        para = rng.choice(SENTENCES)
        for ln in wrap_text(draw, "　　" + para, bf, max_w):
            if used >= lines_budget:
                break
            draw.text((MARGIN_X, y), ln, font=bf, fill=25)
            y += BODY_LINE_H
            used += 1
        y += 8  # 段间距
    return gold


def plan_table_rows(rng: random.Random, group_pages: int) -> dict:
    """按组页数生成还款计划行数与金额（整分）。行容量按版面常量推（首页含表题）。"""
    spec_page_cap_first = 15  # 首片段行容量（与渲染常量一致：BODY_TOP+60 起、行高 64）
    spec_page_cap_cont = 16   # 续片段行容量（BODY_TOP+20 起）
    if group_pages == 2:
        n = rng.randint(spec_page_cap_first + 1, spec_page_cap_first + spec_page_cap_cont - 2)  # 16..29：第 2 页 1..14 行
    else:
        n = rng.randint(spec_page_cap_first + spec_page_cap_cont + 1,  # 32：超出 2 页容量才要第 3 页
                        spec_page_cap_first + 2 * spec_page_cap_cont - 2)  # ..45：第 3 页 1..14 行＋合计行
    principal = rng.randrange(300_000, 20_000_000) * 100  # 30万~2000万元，整分
    rate_bp = rng.randrange(360, 1450)  # 3.60%~14.50%
    base = principal // n
    rem = principal - base * n
    start = date(2026, 1, 6)
    rows: list[dict] = []
    remaining_p = principal
    for i in range(1, n + 1):
        p_i = base + (rem if i == n else 0)
        interest = int(
            (Decimal(remaining_p) * Decimal(rate_bp) / Decimal(10000) / Decimal(12)).quantize(
                Decimal("1"), rounding=ROUND_HALF_EVEN
            )
        )
        rows.append({
            "installment": i,
            "date": (start + timedelta(days=30 * i)).isoformat(),
            "principal_cents": p_i,
            "interest_cents": interest,
            "total_cents": p_i + interest,
        })
        remaining_p -= p_i
    assert remaining_p == 0
    return {"n": n, "principal_cents": principal, "rate_bp": rate_bp, "rows": rows}


TABLE_COLUMNS = [
    ("期次", 0.12),
    ("还款日期", 0.22),
    ("应还本金（元）", 0.22),
    ("应还利息（元）", 0.22),
    ("合计（元）", 0.22),
]


def render_table_portion(img: Image.Image, spec: PageSpec, fonts: dict, tbl: dict,
                         row_slice: tuple[int, int], first_portion: bool) -> list[dict]:
    """画表格片段（首片段含表题），返回行金标。行高固定 → bbox 可解析推出。"""
    draw = ImageDraw.Draw(img)
    tf = fonts["table"]
    x0 = MARGIN_X
    total_w = spec.W - 2 * MARGIN_X
    col_x: list[tuple[int, int]] = []
    cx = x0
    for _, frac in TABLE_COLUMNS:
        w = int(total_w * frac)
        col_x.append((cx, cx + w))
        cx += w
    y = BODY_TOP + (60 if first_portion else 20)
    if first_portion:
        ttf = fonts["table_title"]
        title = "还款计划表（合成数据，金额单位：元）"
        draw.text((x0, BODY_TOP), title, font=ttf, fill=20)
        y = BODY_TOP + 60
    # 表头
    for (name, _), (cxa, cxb) in zip(TABLE_COLUMNS, col_x):
        draw.text(((cxa + cxb) // 2, y + TABLE_HEADER_H // 2), name, font=tf, fill=20, anchor="mm")
    draw.line([(x0, y + TABLE_HEADER_H), (cx, y + TABLE_HEADER_H)], fill=60, width=2)
    draw.line([(x0, y), (cx, y)], fill=60, width=2)
    yy = y + TABLE_HEADER_H
    row_gold: list[dict] = []
    r0, r1 = row_slice
    for i in range(r0, r1):
        row = tbl["rows"][i]
        texts = [str(row["installment"]), row["date"], cents_str(row["principal_cents"]),
                 cents_str(row["interest_cents"]), cents_str(row["total_cents"])]
        cells = []
        for (name, _), (cxa, cxb), txt in zip(TABLE_COLUMNS, col_x, texts):
            draw.text(((cxa + cxb) // 2, yy + TABLE_ROW_H // 2), txt, font=tf, fill=25, anchor="mm")
            cells.append({"col": name, "text": txt, "bbox_px": [cxa, yy, cxb, yy + TABLE_ROW_H]})
        row_gold.append({
            "installment": row["installment"],
            "page_row_index": i - r0,
            "cells": cells,
        })
        yy += TABLE_ROW_H
        draw.line([(x0, yy), (cx, yy)], fill=60, width=2)
    # 竖线
    for (cxa, _) in col_x:
        draw.line([(cxa, y), (cxa, yy)], fill=60, width=2)
    draw.line([(cx, y), (cx, yy)], fill=60, width=2)
    # 合计行（末片段末尾）
    if r1 == tbl["n"]:
        total_p = sum(r["principal_cents"] for r in tbl["rows"])
        total_i = sum(r["interest_cents"] for r in tbl["rows"])
        texts = ["合计", "—", cents_str(total_p), cents_str(total_i), cents_str(total_p + total_i)]
        cells = []
        for (name, _), (cxa, cxb), txt in zip(TABLE_COLUMNS, col_x, texts):
            draw.text(((cxa + cxb) // 2, yy + TABLE_ROW_H // 2), txt, font=tf, fill=20, anchor="mm")
            cells.append({"col": name, "text": txt, "bbox_px": [cxa, yy, cxb, yy + TABLE_ROW_H]})
        row_gold.append({"installment": "total", "page_row_index": r1 - r0, "cells": cells})
        yy += TABLE_ROW_H
        draw.line([(x0, yy), (cx, yy)], fill=60, width=2)
    return row_gold


def degrade_lowconf(img: Image.Image, rng: random.Random, spec: PageSpec) -> dict:
    """低置信降质：高斯模糊 + 椒盐噪声 + 灰度对比压低。全确定性。"""
    blur_radius = round(rng.uniform(0.9, 1.4), 2)
    noise_density = round(rng.uniform(0.05, 0.09), 3)
    ink_lift = rng.randint(40, 70)  # 黑字抬灰
    out = img.filter(ImageFilter.GaussianBlur(blur_radius))
    out = out.point(lambda v: min(255, v + ink_lift) if v < 128 else v)
    n_bytes = spec.W * spec.H
    noise = rng.randbytes(n_bytes)
    thresh = int(noise_density * 255)
    mask = Image.frombytes("L", (spec.W, spec.H), noise).point(lambda v: 255 if v < thresh else 0, mode="L")
    out = ImageChops.subtract(out, mask)
    return out, {"blur_radius": blur_radius, "noise_density": noise_density, "ink_lift": ink_lift}


ROTATE_MAP = {
    90: Image.ROTATE_90,      # 逆时针 90
    180: Image.ROTATE_180,
    270: Image.ROTATE_270,    # 逆时针 270 = 顺时针 90
}


def rotate_bbox(rect: list[int], angle: int, W: int, H: int) -> list[int]:
    """PIL transpose 逆时针旋转后的 bbox 解析变换（含 1px 边界保守扩展）。"""
    x0, y0, x1, y1 = rect
    if angle == 90:
        pts = [(y0, W - 1 - x1), (y1, W - 1 - x0)]
        return [min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts) + 1, max(p[1] for p in pts) + 1]
    if angle == 180:
        return [W - 1 - x1, H - 1 - y1, W - 1 - x0 + 1, H - 1 - y0 + 1]
    if angle == 270:
        pts = [(H - 1 - y1, x0), (H - 1 - y0, x1)]
        return [min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts) + 1, max(p[1] for p in pts) + 1]
    raise ValueError(angle)


def map_gold_bbox(gold: dict, angle: int, W: int, H: int) -> dict:
    out = {}
    for k, v in gold.items():
        if isinstance(v, dict) and "bbox_px" in v:
            out[k] = {**v, "bbox_px": rotate_bbox(v["bbox_px"], angle, W, H)}
        else:
            out[k] = v
    return out


# ---------- 最小确定性 PDF 装配（DeviceGray 8bit FlateDecode，无 /ID 无时间戳） ----------
def pdf_bytes(rasters: list[tuple[bytes, int, int]], dpi: int) -> bytes:
    """rasters: [(raw, w, h), ...]；旋转页 w/h 互换（横版页），MediaBox 逐页按各自尺寸。"""
    n_pages = len(rasters)
    # 对象编号：1 Catalog；2 Pages；每页 i(0基)：page=3+3i，image=4+3i，contents=5+3i
    n_objs = 2 + 3 * n_pages
    kids = " ".join(f"{3 + 3 * i} 0 R" for i in range(n_pages))
    bodies: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: f"<< /Type /Pages /Count {n_pages} /Kids [{kids}] >>".encode(),
    }
    for i, (raw, W, H) in enumerate(rasters):
        w_pt = f"{W * 72 / dpi:.2f}"
        h_pt = f"{H * 72 / dpi:.2f}"
        comp = zlib.compress(raw, 9)
        page_num = 3 + 3 * i
        img_num = 4 + 3 * i
        cont_num = 5 + 3 * i
        bodies[page_num] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {w_pt} {h_pt}] "
            f"/Resources << /XObject << /Im{i} {img_num} 0 R >> >> /Contents {cont_num} 0 R >>"
        ).encode()
        bodies[img_num] = (
            f"<< /Type /XObject /Subtype /Image /Width {W} /Height {H} "
            f"/ColorSpace /DeviceGray /BitsPerComponent 8 /Filter /FlateDecode /Length {len(comp)} >>\nstream\n"
        ).encode() + comp + b"\nendstream"
        content = f"q {w_pt} 0 0 {h_pt} 0 0 cm /Im{i} Do Q".encode()
        bodies[cont_num] = f"<< /Length {len(content)} >>\nstream\n".encode() + content + b"\nendstream"
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets: dict[int, int] = {}
    for num in range(1, n_objs + 1):
        offsets[num] = len(out)
        out += f"{num} 0 obj\n".encode() + bodies[num] + b"\nendobj\n"
    xref_pos = len(out)
    out += f"xref\n0 {n_objs + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for num in range(1, n_objs + 1):
        out += f"{offsets[num]:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {n_objs + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode()
    return bytes(out)


# ---------- 语料构建 ----------
def build_corpus(out_dir: Path, pages: int, seed: int, dpi: int, quota: dict[str, float],
                 quiet: bool = False) -> dict:
    rng = random.Random(seed)
    fpath = font_path()
    fsha = sha256_file(fpath)
    fonts = {
        "body": ImageFont.truetype(str(fpath), BODY_FONT),
        "title": ImageFont.truetype(str(fpath), TITLE_FONT),
        "small": ImageFont.truetype(str(fpath), SMALL_FONT),
        "footer": ImageFont.truetype(str(fpath), FOOTER_FONT),
        "table": ImageFont.truetype(str(fpath), TABLE_FONT),
        "table_title": ImageFont.truetype(str(fpath), TABLE_TITLE_FONT),
    }
    spec = PageSpec(dpi)
    counts = quota_counts(pages, quota)
    doc_plans = plan_corpus(rng, pages, counts)

    (out_dir / "pages").mkdir(parents=True, exist_ok=True)
    (out_dir / "docs").mkdir(parents=True, exist_ok=True)

    manifest: dict = {
        "schema": SCHEMA,
        "generator": GEN_REV,
        "seed": seed,
        "pages": pages,
        "dpi": dpi,
        "page_px": [spec.W, spec.H],
        "quota_requested": dict(quota),
        "quota_achieved": {},  # 末尾回填
        "env": {
            "python": sys.version.split()[0],
            "pillow": __import__("PIL").__version__,
            "zlib_runtime": zlib.ZLIB_RUNTIME_VERSION,
            "font_path": str(fpath),
            "font_sha256": fsha,
        },
        "documents": [],
        "tables": [],
    }

    kind_tally: dict[str, int] = {}
    table_seq = 0
    line_budget = (spec.H - 130 - BODY_TOP) // BODY_LINE_H  # 正文行预算

    for doc in doc_plans:
        di = doc["doc_index"]
        doc_id = f"doc_{di + 1:04d}"
        doc_code = f"SJ-E12-{di + 1:04d}"
        doc_type = DOC_TYPES[di % len(DOC_TYPES)]
        doc_meta = {
            "doc_id": doc_id,
            "doc_code": doc_code,
            "title": f"合成测试卷：{PLAINTIFFS[di % len(PLAINTIFFS)]}与{DEFENDANTS[di % len(DEFENDANTS)]}{doc_type}纠纷案",
            "case_no": f"（2026）京01民初{10001 + di}号",
            "plaintiff": PLAINTIFFS[di % len(PLAINTIFFS)],
            "defendant": DEFENDANTS[di % len(DEFENDANTS)],
        }
        kinds = doc["page_kinds"]
        n_doc_pages = len(kinds)

        # 该卷的跨页表规划：每个 TABLE_SPAN..TABLE_CONT 组一张表
        table_plans: dict[int, dict] = {}
        i = 0
        while i < n_doc_pages:
            if kinds[i] == "TABLE_SPAN":
                j = i
                while j + 1 < n_doc_pages and kinds[j + 1] == "TABLE_CONT":
                    j += 1
                group_pages = j - i + 1
                table_plans[i] = plan_table_rows(rng, group_pages)
                i = j + 1
            else:
                i += 1

        # 行容量：首片段 15 行，续片段 16 行（与 plan_table_rows 容量一致）
        cap_first, cap_cont = 15, 16
        page_files: list[dict] = []
        rasters: list[bytes] = []
        last_text_png: bytes | None = None
        last_text_idx: int | None = None
        table_rows_gold: dict[int, list[dict]] = {}

        for pi in range(n_doc_pages):
            kind = kinds[pi]
            page_no = pi + 1
            png_name = f"p{page_no:04d}.png"
            entry: dict = {"page": page_no, "kind": kind, "png": f"pages/{doc_id}/{png_name}"}

            if kind == "BLANK":
                img = Image.new("L", (spec.W, spec.H), 255)
                png = to_png(img)
                entry["expected_signal"] = "blank"
                entry["page_no_gold"] = None
            elif kind == "DUPLICATE":
                if last_text_png is None:
                    raise SystemExit(f"[FAIL] 内部错误：{doc_id} p{page_no} 重复页无源")
                png = last_text_png
                entry["duplicate_of"] = {"doc_id": doc_id, "page": last_text_idx}
                entry["expected_signal"] = f"duplicate_of:{doc_id}:p{last_text_idx:04d}"
                entry["page_no_gold"] = None  # 打印页号=源页页号，以源页金标为准
            else:
                img = Image.new("L", (spec.W, spec.H), 255)
                gold: dict = {}
                if kind == "TEXT":
                    gold.update(render_text_page(img, spec, fonts, rng, line_budget, title_mode=(pi == 0), doc=doc_meta))
                    entry["expected_signal"] = "read_ok"
                elif kind in ("TABLE_SPAN", "TABLE_CONT"):
                    entry["expected_signal"] = "read_ok"
                elif kind == "ROTATED":
                    gold.update(render_text_page(img, spec, fonts, rng, line_budget, title_mode=False, doc=doc_meta))
                    entry["expected_signal"] = "rotation_page"
                elif kind == "LOWCONF":
                    gold.update(render_text_page(img, spec, fonts, rng, line_budget, title_mode=False, doc=doc_meta))
                    entry["expected_signal"] = "low_confidence_or_fail"
                frame_gold = draw_frame(img, spec, fonts, doc_code, page_no)

                # 表格片段渲染（在 frame 之后画，覆盖正文区即可——正文页不含表）
                if kind in ("TABLE_SPAN", "TABLE_CONT"):
                    span_start = pi
                    while span_start > 0 and kinds[span_start] != "TABLE_SPAN":
                        span_start -= 1
                    tbl = table_plans[span_start]
                    table_seq_local = None
                    first_portion = kind == "TABLE_SPAN"
                    if first_portion:
                        row_slice = (0, min(cap_first, tbl["n"]))
                    else:
                        done = cap_first + cap_cont * (pi - span_start - 1)
                        row_slice = (min(done, tbl["n"]), min(done + cap_cont, tbl["n"]))
                    row_gold = render_table_portion(img, spec, fonts, tbl, row_slice, first_portion)
                    table_rows_gold.setdefault(span_start, []).extend(
                        [{**rg, "page": page_no} for rg in row_gold]
                    )
                    entry["table_portion"] = {
                        "row_slice": list(row_slice),
                        "first_portion": first_portion,
                    }

                if kind == "LOWCONF":
                    img, recipe = degrade_lowconf(img, rng, spec)
                    entry["lowconf_recipe"] = recipe

                if kind == "ROTATED":
                    angle = rng.choice([90, 180, 270])
                    img = img.transpose(ROTATE_MAP[angle])
                    gold = map_gold_bbox(gold, angle, spec.W, spec.H)
                    frame_gold = map_gold_bbox(frame_gold, angle, spec.W, spec.H)
                    entry["rotation"] = angle

                gold.update(frame_gold)
                png = to_png(img)
                entry["page_no_gold"] = gold["page_no"]
                entry["header_gold"] = gold["header"]
                entry["synthetic_tag_gold"] = gold["synthetic_tag"]
                if "title_bbox_px" in gold:
                    entry["title_bbox_px"] = gold["title_bbox_px"]
                if kind == "TEXT":
                    last_text_png = png
                    last_text_idx = page_no

            png_path = out_dir / "pages" / doc_id / png_name
            png_path.parent.mkdir(parents=True, exist_ok=True)
            png_path.write_bytes(png)
            rasters.append(png_to_raw(png, spec))
            entry["sha256"] = sha256_bytes(png)
            entry["bytes"] = len(png)
            page_files.append(entry)
            kind_tally[kind] = kind_tally.get(kind, 0) + 1

        # 跨页表金标汇总
        for span_start, rows in table_rows_gold.items():
            tbl = table_plans[span_start]
            table_seq += 1
            table_id = f"tbl_{table_seq:04d}"
            span_end = span_start
            while span_end + 1 < n_doc_pages and kinds[span_end + 1] == "TABLE_CONT":
                span_end += 1
            manifest["tables"].append({
                "table_id": table_id,
                "doc_id": doc_id,
                "pages": [span_start + 1, span_end + 1],
                "installments": tbl["n"],
                "principal_cents": tbl["principal_cents"],
                "rate_bp": tbl["rate_bp"],
                "columns": [c for c, _ in TABLE_COLUMNS],
                "reading_order_rows": sorted(rows, key=lambda r: (r["page"], r["page_row_index"])),
            })
            for e in page_files:
                if span_start < e["page"] <= span_end:
                    e["table_id"] = table_id

        pdf = pdf_bytes(rasters, dpi)
        pdf_path = out_dir / "docs" / f"{doc_id}.pdf"
        pdf_path.write_bytes(pdf)
        manifest["documents"].append({
            "doc_id": doc_id,
            "doc_code": doc_code,
            "title": doc_meta["title"],
            "case_no": doc_meta["case_no"],
            "pdf": f"docs/{doc_id}.pdf",
            "pdf_sha256": sha256_bytes(pdf),
            "pdf_bytes": len(pdf),
            "page_count": n_doc_pages,
            "page_files": page_files,
        })
        if not quiet:
            eprint(f"  [gen] {doc_id}: {n_doc_pages} 页 {pdf_path.name}({len(pdf)} B)")

    # 配额达成回填
    achieved = dict(kind_tally)
    achieved["table"] = achieved.get("TABLE_SPAN", 0) + achieved.get("TABLE_CONT", 0)
    manifest["quota_achieved"] = achieved
    for k, v in counts.items():
        if k == "table":
            if achieved["table"] != v:
                raise SystemExit(f"[FAIL] 配额不符 table: 达成 {achieved['table']} ≠ 目标 {v}")
        elif achieved.get(k.upper(), 0) != v:
            raise SystemExit(f"[FAIL] 配额不符 {k}: 达成 {achieved.get(k.upper(), 0)} ≠ 目标 {v}")
    if sum(v for k, v in achieved.items() if k != "table") != pages:
        raise SystemExit(f"[FAIL] 页数不符: {sum(v for k, v in achieved.items() if k != 'table')} ≠ {pages}")

    mpath = out_dir / MANIFEST_NAME
    mpath.write_text(json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    core = {"seed": seed, "pages": pages, "dpi": dpi, "schema": SCHEMA, "quota_requested": quota}
    digest = tree_digest(out_dir, core)
    (out_dir / DIGEST_NAME).write_text(f"{digest}  seed={seed} pages={pages} dpi={dpi}\n", encoding="ascii")
    return {"manifest": manifest, "digest": digest, "out": str(out_dir)}


def to_png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", compress_level=6)
    return buf.getvalue()


def png_to_raw(png: bytes, spec: PageSpec | None = None) -> tuple[bytes, int, int]:
    """PNG → (raw 灰度字节, w, h)。spec 给定时校验未旋转规格（旋转页 w/h 互换合法）。"""
    with Image.open(io.BytesIO(png)) as im:
        if im.mode != "L":
            raise SystemExit(f"[FAIL] 内部错误：PNG 模式异常 {im.mode}")
        if spec is not None and im.size not in ((spec.W, spec.H), (spec.H, spec.W)):
            raise SystemExit(f"[FAIL] 内部错误：PNG 规格异常 {im.size}")
        return im.tobytes(), im.size[0], im.size[1]


def tree_digest(out_dir: Path, core: dict) -> str:
    lines: list[str] = []
    for p in sorted(out_dir.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(out_dir).as_posix()
        if rel in (MANIFEST_NAME, DIGEST_NAME):
            continue
        lines.append(f"{rel} {sha256_file(p)}")
    payload = json.dumps(core, sort_keys=True, ensure_ascii=False).encode("utf-8") + b"\n" + "\n".join(lines).encode("utf-8")
    return sha256_bytes(payload)


# ---------- 复验 ----------
def ink_in_box(png: bytes, box: list[int]) -> bool:
    with Image.open(io.BytesIO(png)) as im:
        crop = im.crop(tuple(box))
        lo, _ = crop.getextrema()
        return lo < 200


def verify_corpus(out_dir: Path, pdf_deep: str = "sample") -> tuple[list[str], int]:
    fails: list[str] = []
    checks = 0
    mpath = out_dir / MANIFEST_NAME
    if not mpath.is_file():
        return [f"清单缺失: {mpath}"], 0
    manifest = json.loads(mpath.read_text(encoding="utf-8"))
    listed: set[str] = set()

    # 1) 文件集与哈希
    all_files = {p.relative_to(out_dir).as_posix() for p in out_dir.rglob("*") if p.is_file()}
    for doc in manifest["documents"]:
        listed.add(doc["pdf"])
        if not (out_dir / doc["pdf"]).is_file():
            fails.append(f"{doc['doc_id']} PDF 缺失 {doc['pdf']}")
            continue
        checks += 1
        if sha256_file(out_dir / doc["pdf"]) != doc["pdf_sha256"]:
            fails.append(f"{doc['doc_id']} PDF sha256 不符")
        for e in doc["page_files"]:
            listed.add(e["png"])
            pf = out_dir / e["png"]
            if not pf.is_file():
                fails.append(f"{doc['doc_id']} p{e['page']} PNG 缺失")
                continue
            checks += 1
            if sha256_file(pf) != e["sha256"]:
                fails.append(f"{doc['doc_id']} p{e['page']} PNG sha256 不符")
    extras = all_files - listed - {MANIFEST_NAME, DIGEST_NAME}
    if extras:
        fails.append(f"清单外多余文件 {len(extras)} 个：{sorted(extras)[:3]}")
    checks += 1

    # 2) 配额与页数
    tally: dict[str, int] = {}
    for doc in manifest["documents"]:
        for e in doc["page_files"]:
            tally[e["kind"]] = tally.get(e["kind"], 0) + 1
    got_table = tally.get("TABLE_SPAN", 0) + tally.get("TABLE_CONT", 0)
    if got_table != manifest["quota_achieved"].get("table"):
        fails.append(f"配额表页 recount {got_table} ≠ 清单 {manifest['quota_achieved'].get('table')}")
    checks += 1
    total = sum(tally.values())
    if total != manifest["pages"]:
        fails.append(f"页数 recount {total} ≠ {manifest['pages']}")
    checks += 1
    rq = manifest["quota_requested"]
    ex = quota_counts(manifest["pages"], rq)
    for k, v in ex.items():
        want = v if k != "text" else v
        gotk = got_table if k == "table" else tally.get(k.upper(), 0)
        if gotk != want:
            fails.append(f"配额 {k}: recount {gotk} ≠ 最大余数目标 {want}")
    checks += 1

    # 3) 结构与金标
    W, H = manifest["page_px"]
    doc_by_id = {d["doc_id"]: d for d in manifest["documents"]}
    for doc in manifest["documents"]:
        dup_src_png: dict[int, bytes] = {}
        for e in doc["page_files"]:
            png = (out_dir / e["png"]).read_bytes()
            k = e["kind"]
            if k == "BLANK":
                with Image.open(io.BytesIO(png)) as im:
                    lo, hi = im.getextrema()
                if (lo, hi) != (255, 255):
                    fails.append(f"{doc['doc_id']} p{e['page']} 空白页含墨 {im_extrema_str(png)}")
                checks += 1
            elif k == "DUPLICATE":
                src = e.get("duplicate_of")
                if not src or src["doc_id"] != doc["doc_id"] or src["page"] >= e["page"]:
                    fails.append(f"{doc['doc_id']} p{e['page']} 重复页源引用非法 {src}")
                else:
                    sp = out_dir / doc_by_id[src["doc_id"]]["page_files"][src["page"] - 1]["png"]
                    if (out_dir / e["png"]).read_bytes() != sp.read_bytes():
                        fails.append(f"{doc['doc_id']} p{e['page']} 重复页字节 ≠ 源页")
                checks += 1
            elif k == "ROTATED":
                if e.get("rotation") not in (90, 180, 270):
                    fails.append(f"{doc['doc_id']} p{e['page']} 旋转角非法 {e.get('rotation')}")
                checks += 1
            if e.get("page_no_gold") is not None:
                g = e["page_no_gold"]
                b = g["bbox_px"]
                pW, pH = (H, W) if e.get("rotation") in (90, 270) else (W, H)
                if not (0 <= b[0] < b[2] <= pW and 0 <= b[1] < b[3] <= pH):
                    fails.append(f"{doc['doc_id']} p{e['page']} 页号 bbox 越界 {b}")
                elif k != "LOWCONF" and not ink_in_box(png, b):
                    fails.append(f"{doc['doc_id']} p{e['page']} 页号 bbox 无墨")
                checks += 1
                if g["text"] != f"- {e['page']} -":
                    fails.append(f"{doc['doc_id']} p{e['page']} 页号文本 {g['text']!r} 与页码不符")
                checks += 1
            if k == "TEXT":
                dup_src_png[e["page"]] = png

    # 4) 跨页表
    for tbl in manifest["tables"]:
        pages = tbl["pages"]
        if pages[1] <= pages[0]:
            fails.append(f"{tbl['table_id']} 页区间非法 {pages}")
        checks += 1
        rows = tbl["reading_order_rows"]
        inst = [r["installment"] for r in rows if r["installment"] != "total"]
        if inst != list(range(1, tbl["installments"] + 1)):
            fails.append(f"{tbl['table_id']} 阅读序期次断裂: 前5={inst[:5]} 末={inst[-3:]}")
        checks += 1
        if rows[-1]["installment"] != "total":
            fails.append(f"{tbl['table_id']} 缺合计行")
        checks += 1
        amounts = [c["text"] for r in rows for c in r["cells"] if "（元）" in c["col"]]
        for a in amounts:
            if a != "—" and not _is_cents(a):
                fails.append(f"{tbl['table_id']} 金额格式非法 {a!r}")
                break
        checks += 1
        for r in rows:
            if not (tbl["pages"][0] <= r["page"] <= tbl["pages"][1]):
                fails.append(f"{tbl['table_id']} 行页码越界 {r['page']}")
                break
        checks += 1

    # 5) PDF 一致性（PyMuPDF）
    try:
        import fitz  # type: ignore
    except ImportError:
        eprint("  [verify] PyMuPDF 未装，PDF 深检跳过（PNG 哈希已全验）")
        fitz = None
    if fitz is not None:
        for doc in manifest["documents"]:
            pdoc = fitz.open(out_dir / doc["pdf"])
            checks += 1
            if pdoc.page_count != doc["page_count"]:
                fails.append(f"{doc['doc_id']} PDF 页数 {pdoc.page_count} ≠ {doc['page_count']}")
            indices = _pdf_deep_indices(doc["page_count"], pdf_deep)
            for i in indices:
                page = pdoc[i]
                checks += 1
                png = (out_dir / doc["page_files"][i]["png"]).read_bytes()
                expected, ew, eh = png_to_raw(png)
                if (round(page.rect.width * 100), round(page.rect.height * 100)) != (
                    round(ew * 72 / manifest["dpi"] * 100), round(eh * 72 / manifest["dpi"] * 100)
                ):
                    fails.append(f"{doc['doc_id']} PDF p{i+1} MediaBox {page.rect} 不符")
                imgs = page.get_images(full=True)
                if not imgs:
                    fails.append(f"{doc['doc_id']} PDF p{i+1} 无嵌入图")
                    continue
                xref = imgs[0][0]
                raw = pdoc.xref_stream(xref)
                if raw != expected:
                    fails.append(f"{doc['doc_id']} PDF p{i+1} 嵌入像素 ≠ PNG 像素")
            pdoc.close()

    # 6) 摘要复算
    core = {"seed": manifest["seed"], "pages": manifest["pages"], "dpi": manifest["dpi"],
            "schema": manifest["schema"], "quota_requested": manifest["quota_requested"]}
    d = tree_digest(out_dir, core)
    dfile = out_dir / DIGEST_NAME
    if not dfile.is_file() or not dfile.read_text(encoding="ascii").startswith(d):
        fails.append(f"corpus_digest 复算不符: {d}")
    checks += 1
    return fails, checks


def _is_cents(a: str) -> bool:
    return re.fullmatch(r"\d+\.\d{2}", a) is not None


def im_extrema_str(png: bytes) -> str:
    with Image.open(io.BytesIO(png)) as im:
        return str(im.getextrema())


def _pdf_deep_indices(page_count: int, mode: str) -> list[int]:
    if mode == "all":
        return list(range(page_count))
    if mode == "none":
        return []
    return sorted({0, page_count // 2, page_count - 1})


# ---------- 自检 ----------
def selftest(pages: int = 144, keep: bool = False) -> int:
    root = Path(tempfile.mkdtemp(prefix="juscite-e12-selftest-"))
    eprint(f"[selftest] 根目录 {root}")
    fails: list[str] = []
    seed = 20261015

    a = root / "a"
    eprint(f"[selftest] 1/6 生成 A（pages={pages} seed={seed}）")
    ra = build_corpus(a, pages, seed, DEFAULT_DPI, DEFAULT_QUOTA)
    m = ra["manifest"]
    if len(m["documents"]) < 3:
        fails.append(f"卷数过少 {len(m['documents'])}，自检样本不足")
    kinds_present = set(m["quota_achieved"]) & {"TABLE_SPAN", "ROTATED", "DUPLICATE", "BLANK", "LOWCONF"}
    if kinds_present != {"TABLE_SPAN", "ROTATED", "DUPLICATE", "BLANK", "LOWCONF"}:
        fails.append(f"自检样本未覆盖全部页型 {kinds_present}")
    if not any(d["page_count"] >= 20 for d in m["documents"]):
        fails.append("无 ≥20 页的卷，结构代表性不足")

    eprint("[selftest] 2/6 生成 B（同 seed）→ 逐文件字节比对")
    b = root / "b"
    build_corpus(b, pages, seed, DEFAULT_DPI, DEFAULT_QUOTA, quiet=True)
    fa = {p.relative_to(a).as_posix(): sha256_file(p) for p in a.rglob("*") if p.is_file()}
    fb = {p.relative_to(b).as_posix(): sha256_file(p) for p in b.rglob("*") if p.is_file()}
    if set(fa) != set(fb):
        fails.append(f"同 seed 文件集不同: A-only={sorted(set(fa)-set(fb))[:3]} B-only={sorted(set(fb)-set(fa))[:3]}")
    diff = [k for k in sorted(set(fa) & set(fb)) if fa[k] != fb[k]]
    if diff:
        fails.append(f"同 seed 有 {len(diff)} 个文件哈希不同（应逐字节相同）: {diff[:3]}")
    if not (a / MANIFEST_NAME).read_bytes() == (b / MANIFEST_NAME).read_bytes():
        fails.append("同 seed 清单字节不同")

    eprint("[selftest] 3/6 生成 C（异 seed）→ 摘要必须不同")
    c = root / "c"
    rc = build_corpus(c, pages, seed + 1, DEFAULT_DPI, DEFAULT_QUOTA, quiet=True)
    if rc["digest"] == ra["digest"]:
        fails.append("异 seed 摘要相同（seed 未生效）")

    eprint("[selftest] 4/6 --verify A（配额/结构/金标/PDF 全深检）")
    vf, vc = verify_corpus(a, pdf_deep="all")
    fails += vf

    eprint("[selftest] 5/6 --verify C")
    vf2, _ = verify_corpus(c, pdf_deep="sample")
    fails += vf2

    eprint("[selftest] 6/6 断言汇总")
    eprint(f"[selftest] A 摘要={ra['digest'][:16]}… C 摘要={rc['digest'][:16]}… verify 检查项 A={vc}")
    if fails:
        for f in fails:
            eprint(f"  [FAIL] {f}")
        eprint(f"[selftest] FAIL（{len(fails)} 项不合格）")
        return 1
    eprint(f"[selftest] PASS（{pages} 页×3 生成 + 同seed字节级复验 + 异seed差异 + verify 全绿）")
    if not keep:
        import shutil
        shutil.rmtree(root, ignore_errors=True)
    else:
        eprint(f"[selftest] --keep 保留 {root}")
    return 0


# ============================================================ W2a-U15 附件夹具
# F38/F44 义务用全合成附件夹具：含 PII 扫描页（OCR→人审→烧入→复扫链）＋
# F44 四类反例五文件（黑框下文本层/隐藏文本/元数据 Info+XMP/图片残留
# 裁切区+alt）。全部确定性手建（PIL 渲染＋字节级 PDF 组装，无 reportlab
# 依赖）；同 seed 同字节。PII 全合成（身份证校验位按 GB11643 权重派生）。

ATT_SCHEMA = "juscite-f38-f44-attachments/1"
ATT_GEN_REV = "tools/e12_corpus_gen.py attachments r1 (W2a-U15)"
ATT_DIGEST_NAME = "attachments_digest.txt"

_ID_WEIGHTS = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
_ID_CODES = "10X98765432"


def _id_card_valid(prefix17: str) -> str:
    total = sum(int(d) * w for d, w in zip(prefix17, _ID_WEIGHTS))
    return prefix17 + _ID_CODES[total % 11]


ATT_PHONE = ["13700002222", "13700003333", "13700004444"]
ATT_ID = [_id_card_valid("11010119900307867"),
          _id_card_valid("11010119900307901"),
          _id_card_valid("11010119900307231")]
ATT_ADDRESS = ["北京市海淀区合成路12号院3号楼", "北京市朝阳区合成路9号"]
ATT_CASE = ["（2026）京01民初91001号", "（2026）京01民初91002号",
            "（2026）京01民初91003号"]
ATT_PERSON = "王合成"


def _mini_pdf(bodies: dict[int, bytes]) -> bytes:
    """任意对象集的字节级 PDF 组装（xref 逐号补齐空位）。确定性。"""
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets: dict[int, int] = {}
    for num in sorted(bodies):
        offsets[num] = len(out)
        out += f"{num} 0 obj\n".encode() + bodies[num] + b"\nendobj\n"
    size = max(bodies) + 1
    xref_pos = len(out)
    out += f"xref\n0 {size}\n".encode()
    out += b"0000000000 65535 f \n"
    for num in range(1, size):
        if num in offsets:
            out += f"{offsets[num]:010d} 00000 n \n".encode()
        else:
            out += b"0000000000 65535 f \n"
    out += f"trailer\n<< /Size {size} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode()
    return bytes(out)


def _pdf_stream(dict_extra: str, payload: bytes) -> bytes:
    return (f"<< {dict_extra} /Length {len(payload)} >>\nstream\n").encode() \
        + payload + b"\nendstream"


def _draw_lines(img: Image.Image, font, lines: list[tuple[str, int, int]],
                fill: int = 25) -> None:
    draw = ImageDraw.Draw(img)
    for text, x, y in lines:
        draw.text((x, y), text, font=font, fill=fill)


def _text_box(font, text: str, x: int, y: int) -> list[int]:
    w = int(font.getlength(text))
    asc, desc = font.getmetrics()
    return [x, y, x + w, y + asc + desc]


def _ce_blackbox(pdf_phone: str, pdf_id: str) -> bytes:
    """反例①黑框下文本层仍在：可见文本＋黑矩形覆印（视觉遮蔽≠删除）。"""
    content = "\n".join([
        "BT /F1 12 Tf 0 0 0 rg",
        "1 0 0 1 40 760 Td (synthetic benign header) Tj",
        f"1 0 0 1 40 700 Td (tel {pdf_phone}) Tj",
        f"1 0 0 1 40 670 Td (id {pdf_id}) Tj",
        "ET",
        "0 0 0 rg 36 662 300 52 re f",
    ]).encode()
    bodies = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: b"<< /Type /Pages /Count 1 /Kids [3 0 R] >>",
        3: (b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            b"/Resources << /Font << /F1 6 0 R >> >> /Contents 5 0 R >>"),
        5: _pdf_stream("", content),
        6: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }
    return _mini_pdf(bodies)


def _ce_hidden_text(pdf_phone: str, pdf_id: str) -> bytes:
    """反例②隐藏文本：白色填充＋渲染模式 3（不可见），文本层可整取。"""
    content = "\n".join([
        "BT /F1 12 Tf",
        "0 Tr 0 0 0 rg",
        "1 0 0 1 40 760 Td (synthetic benign header) Tj",
        "1 1 1 rg",
        f"1 0 0 1 40 700 Td (tel {pdf_phone}) Tj",
        "3 Tr 0 0 0 rg",
        f"1 0 0 1 40 670 Td (id {pdf_id}) Tj",
        "ET",
    ]).encode()
    bodies = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: b"<< /Type /Pages /Count 1 /Kids [3 0 R] >>",
        3: (b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            b"/Resources << /Font << /F1 6 0 R >> >> /Contents 5 0 R >>"),
        5: _pdf_stream("", content),
        6: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }
    return _mini_pdf(bodies)


def _ce_metadata(pdf_phone: str, pdf_id: str) -> bytes:
    """反例③元数据残留：Info 字典＋XMP 流携 PII（docProps·XMP 同类）。"""
    w, h = 496, 702
    img = Image.new("L", (w, h), 255)
    _draw_lines(img, ImageFont.truetype(str(font_path()), 26),
                [("synthetic benign page (all synthetic)", 24, 40)])
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    jpeg = buf.getvalue()
    xmp = (f'<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF '
           f'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
           f'<rdf:Description rdf:about="" contact="{pdf_phone}" '
           f'note="id {pdf_id}"/></rdf:RDF></x:xmpmeta>').encode()
    content = f"q {w * 72 // 120} 0 0 {h * 72 // 120} 0 0 cm /Im0 Do Q".encode()
    bodies = {
        1: b"<< /Type /Catalog /Pages 2 0 R /Metadata 7 0 R >>",
        2: b"<< /Type /Pages /Count 1 /Kids [3 0 R] >>",
        3: (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {w * 72 // 120} "
            f"{h * 72 // 120}] /Resources << /XObject << /Im0 4 0 R >> >> "
            f"/Contents 5 0 R >>").encode(),
        4: _pdf_stream(
            f"/Type /XObject /Subtype /Image /Width {w} /Height {h} "
            f"/ColorSpace /DeviceGray /BitsPerComponent 8 /Filter /DCTDecode",
            jpeg),
        5: _pdf_stream("", content),
        6: (f"<< /Author ({pdf_phone}) /Subject (synthetic id {pdf_id}) "
            f"/Creator (e12 attachments ce) >>").encode(),
        7: _pdf_stream("/Type /Metadata /Subtype /XML", xmp),
    }
    pdf = _mini_pdf(bodies)
    return pdf.replace(b"/Root 1 0 R >>", b"/Root 1 0 R /Info 6 0 R >>")


def _ce_image_clip(pdf_phone: str, pdf_id: str) -> bytes:
    """反例④a图片残留·裁切区：全页图像携 PII 像素，裁切只露上缘无 PII 区。"""
    w, h = 496, 702
    font = ImageFont.truetype(str(font_path()), 26)
    img = Image.new("L", (w, h), 255)
    _draw_lines(img, font, [
        ("synthetic benign header (all synthetic)", 24, 30),
        (f"tel {pdf_phone}", 24, 470),
        (f"id {pdf_id}", 24, 540),
    ])
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    w_pt, h_pt = w * 72 // 120, h * 72 // 120
    content = (f"q 0 {h_pt - h_pt // 3} {w_pt} {h_pt // 3} re W n "
               f"{w_pt} 0 0 {h_pt} 0 0 cm /Im0 Do Q").encode()
    bodies = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: b"<< /Type /Pages /Count 1 /Kids [3 0 R] >>",
        3: (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {w_pt} {h_pt}] "
            f"/Resources << /XObject << /Im0 4 0 R >> >> /Contents 5 0 R >>"
            ).encode(),
        4: _pdf_stream(
            f"/Type /XObject /Subtype /Image /Width {w} /Height {h} "
            f"/ColorSpace /DeviceGray /BitsPerComponent 8 /Filter /DCTDecode",
            buf.getvalue()),
        5: _pdf_stream("", content),
    }
    return _mini_pdf(bodies)


def _ce_image_alt(pdf_phone: str) -> bytes:
    """反例④b图片残留·alt：/Alt 替代文本携 PII（结构树 Figure）。"""
    w, h = 496, 702
    img = Image.new("L", (w, h), 255)
    _draw_lines(img, ImageFont.truetype(str(font_path()), 26),
                [("synthetic benign page (all synthetic)", 24, 40)])
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    w_pt, h_pt = w * 72 // 120, h * 72 // 120
    content = f"q {w_pt} 0 0 {h_pt} 0 0 cm /Im0 Do Q".encode()
    bodies = {
        1: b"<< /Type /Catalog /Pages 2 0 R /StructTreeRoot 8 0 R >>",
        2: b"<< /Type /Pages /Count 1 /Kids [3 0 R] >>",
        3: (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {w_pt} {h_pt}] "
            f"/Resources << /XObject << /Im0 4 0 R >> >> /Contents 5 0 R >>"
            ).encode(),
        4: _pdf_stream(
            f"/Type /XObject /Subtype /Image /Width {w} /Height {h} "
            f"/ColorSpace /DeviceGray /BitsPerComponent 8 /Filter /DCTDecode",
            buf.getvalue()),
        5: _pdf_stream("", content),
        8: b"<< /Type /StructTreeRoot /K [9 0 R] >>",
        9: (f"<< /Type /StructElem /S /Figure /P 8 0 R "
            f"/Alt (figure caption contact {pdf_phone}) >>").encode(),
    }
    return _mini_pdf(bodies)


def build_attachments(out_dir: Path, seed: int, dpi: int = DEFAULT_DPI) -> dict:
    """附件夹具构建（确定性）：3 含 PII 扫描页卷＋F44 五反例。"""
    rng = random.Random(seed)
    spec = PageSpec(dpi)
    fpath = font_path()
    fonts = {
        "title": ImageFont.truetype(str(fpath), 34),
        "body": ImageFont.truetype(str(fpath), 26),
        "small": ImageFont.truetype(str(fpath), 20),
    }
    (out_dir / "pages").mkdir(parents=True, exist_ok=True)
    (out_dir / "docs").mkdir(parents=True, exist_ok=True)
    ce_dir = out_dir / "counterexamples"
    ce_dir.mkdir(parents=True, exist_ok=True)

    documents = []
    for idx in range(3):
        doc_id = f"att_{idx + 1:04d}"
        img = Image.new("L", (spec.W, spec.H), 255)
        draw = ImageDraw.Draw(img)
        gold_pii: list[dict] = []
        y = 140
        draw.text((MARGIN_X, y), "合成附件材料（全合成测试材料）",
                  font=fonts["title"], fill=20)
        y += 78
        rows = [
            ("案号：", ATT_CASE[idx], "case_number"),
            ("联系电话：", ATT_PHONE[idx], "phone"),
            ("身份证号：", ATT_ID[idx], "id_card"),
        ]
        if idx == 1:
            rows.append(("经办人：", ATT_PERSON, "PERSON"))
        if idx in (0, 1):
            rows.append(("住址：", ATT_ADDRESS[idx], "personal_address"))
        for label, value, cls in rows:
            draw.text((MARGIN_X, y), label, font=fonts["body"], fill=25)
            lw = int(fonts["body"].getlength(label))
            draw.text((MARGIN_X + lw, y), value, font=fonts["body"], fill=25)
            gold_pii.append({
                "surface": value, "class_id": cls,
                "box": _text_box(fonts["body"], value, MARGIN_X + lw, y)})
            y += 52
        y += 26
        for _ in range(9):
            para = rng.choice(SENTENCES)
            for ln in wrap_text(draw, "　　" + para, fonts["body"],
                                spec.W - 2 * MARGIN_X):
                draw.text((MARGIN_X, y), ln, font=fonts["body"], fill=35)
                y += 38
                if y > spec.H - 160:
                    break
            y += 10
        draw.text((MARGIN_X, spec.H - 100),
                  "SJ-F38-ATT（本页为全合成测试材料，当事人、证件、电话均系虚构）",
                  font=fonts["small"], fill=80)

        kind = "TEXT"
        if idx == 2:
            # 低置信页：固定降质配方（模糊+椒盐+灰度抬升，同 degrade_lowconf 式；
            # 强度按 F40 钉定引擎实测调定：min line conf 压到 0.60 以下）
            blur, density, lift = 1.7, 0.13, 75
            out_img = img.filter(ImageFilter.GaussianBlur(blur))
            out_img = out_img.point(lambda v: min(255, v + lift) if v < 128 else v)
            n_bytes = spec.W * spec.H
            noise = rng.randbytes(n_bytes)
            thresh = int(density * 255)
            mask = Image.frombytes("L", (spec.W, spec.H), noise).point(
                lambda v: 255 if v < thresh else 0, mode="L")
            img = ImageChops.subtract(out_img, mask)
            kind = "LOWCONF"

        png = to_png(img)
        png_path = out_dir / "pages" / doc_id / "p0001.png"
        png_path.parent.mkdir(parents=True, exist_ok=True)
        png_path.write_bytes(png)
        raw = png_to_raw(png, spec)
        pdf = pdf_bytes([raw], dpi)
        pdf_path = out_dir / "docs" / f"{doc_id}.pdf"
        pdf_path.write_bytes(pdf)
        documents.append({
            "doc_id": doc_id,
            "doc_code": f"SJ-F38-ATT-{idx + 1:04d}",
            "title": f"合成附件：{PLAINTIFFS[idx]}材料说明（{ATT_CASE[idx]}）",
            "case_no": ATT_CASE[idx],
            "pdf": f"docs/{doc_id}.pdf",
            "pdf_sha256": sha256_bytes(pdf),
            "pdf_bytes": len(pdf),
            "page_count": 1,
            "kind": kind,
            "gold_pii": gold_pii,
            "page_files": [{
                "page": 1, "kind": kind,
                "png": f"pages/{doc_id}/p0001.png",
                "sha256": sha256_bytes(png), "bytes": len(png),
            }],
        })
        eprint(f"  [att] {doc_id}: kind={kind} gold_pii={len(gold_pii)}")

    counterexamples = {
        "ce_blackbox_textlayer.pdf": _ce_blackbox(ATT_PHONE[0], ATT_ID[0]),
        "ce_hidden_text.pdf": _ce_hidden_text(ATT_PHONE[1], ATT_ID[1]),
        "ce_metadata_info_xmp.pdf": _ce_metadata(ATT_PHONE[2], ATT_ID[2]),
        "ce_image_clip_residual.pdf": _ce_image_clip(ATT_PHONE[0], ATT_ID[1]),
        "ce_image_alt.pdf": _ce_image_alt(ATT_PHONE[2]),
    }
    ce_manifest = []
    ce_classes = {
        "ce_blackbox_textlayer.pdf":
            ["text_layer_present", "text_layer_pii"],
        "ce_hidden_text.pdf":
            ["text_layer_present", "text_layer_pii", "hidden_text_render_mode"],
        "ce_metadata_info_xmp.pdf": ["metadata_pii", "xmp_pii"],
        "ce_image_clip_residual.pdf": ["image_clip_residual"],
        "ce_image_alt.pdf": ["residual_string_pii"],
    }
    for name, payload in counterexamples.items():
        (ce_dir / name).write_bytes(payload)
        ce_manifest.append({
            "file": f"counterexamples/{name}",
            "f44_class": ce_classes[name],
            "sha256": sha256_bytes(payload), "bytes": len(payload),
        })
        eprint(f"  [att] {name}: {len(payload)} B → {ce_classes[name]}")

    manifest = {
        "schema": ATT_SCHEMA,
        "generator": ATT_GEN_REV,
        "seed": seed,
        "dpi": dpi,
        "page_px": [spec.W, spec.H],
        "env": {
            "python": sys.version.split()[0],
            "pillow": __import__("PIL").__version__,
            "zlib_runtime": zlib.ZLIB_RUNTIME_VERSION,
            "font_path": str(fpath),
            "font_sha256": sha256_file(fpath),
        },
        "documents": documents,
        "counterexamples": ce_manifest,
    }
    (out_dir / MANIFEST_NAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8")
    core = {"seed": seed, "dpi": dpi, "schema": ATT_SCHEMA}
    digest = tree_digest(out_dir, core)
    (out_dir / ATT_DIGEST_NAME).write_text(
        f"{digest}  seed={seed} attachments dpi={dpi}\n", encoding="ascii")
    return {"manifest": manifest, "digest": digest,
            "pages": len(documents), "counterexamples": len(ce_manifest),
            "out": str(out_dir)}


# ============================================================ W2b-U03 引证夹具
# F88 可答/应拒双集合黄金集：合成 codices 正式面（FACE_FILES 十文件＋合成
# md 载体）＋ adversarial 黄金集清单。全部手钉确定性内容（标签必须精确，
# 随机化只会削弱标签可对表性）；seed 钉入清单与摘要 core。六指标阈值表
# 出处＝judicex gold_runner.py（蓝图 L13；竞品情报 2026-10-12/repos/
# TEARDOWN-doc-haus-judicex.md §3.2）——阈值在消费侧 f88_dualset_ci.py。

CIT_SCHEMA = "juscite-f88-citations-golden/1"
CIT_GEN_REV = "tools/e12_corpus_gen.py citations r1 (W2b-U03)"
GOLDEN_NAME = "f88_golden_set.json"
CIT_DIGEST_NAME = "f88_citations_digest.txt"
CIT_FACE_DIR = "codices_face"

CIT_DOC_COLUMNS = ["WJBS", "BT", "GBRQ", "SXX", "DE_01018", "SXRQ", "SHXRQ",
                   "DE_01001", "DE_01021"]
CIT_FIXED_AS_OF = "20261016"   # 黄金集钉定评估时点（确定性：非今日函数）
CIT_PAST_AS_OF = "20150101"    # 替代（多版本旧时点）变体用


def _cit_wjbs(seq: str, gbrq: str) -> tuple[str, str]:
    """(body31, WJBS)：category+agency+公布日+序号+内部序+文件类型。"""
    body = "0100" + "0000001001" + gbrq + seq + "000" + "00"
    return body, "1.2.156.3005.6-" + body


# 合成法規（全部标题含「合成」；carrier=md 载体条款 {条文键: 条文文本}）。
# 键格式与 split_articles 对齐：'- **第一条**' 行的数字键（"1"/"3"/"20"）。
CIT_STATUTES = [
    # (标题, 序号, GBRQ, SXX, SXRQ, SHXRQ, carrier条款 dict 或 None, 无GB码?)
    ("中华人民共和国合成数据保护法", "0101", "20210820", "01", "20211101", "",
     {"第一条": "为了规范合成数据处理活动，保护合成数据权益，制定本法。",
      "第二条": "在中华人民共和国境内处理合成数据，适用本法。",
      "第三条": "处理合成数据应当遵循合法、正当、必要原则。",
      "第四条": "任何组织不得非法收集、使用合成数据。",
      "第五条": "合成数据处理者应当采取必要措施，保障合成数据安全。"}, False),
    ("中华人民共和国合成贸易促进法", "0102", "20181105", "01", "20190101", "",
     {"第一条": "为了促进合成贸易健康发展，规范合成贸易活动，制定本法。",
      "第二条": "合成贸易争端应当优先通过协商解决。",
      "第三条": "合成贸易活动应当遵循诚实信用原则。",
      "第六条": "合成贸易数据应当依法有序流动。",
      "第二十条": "合成贸易合同的订立应当采用书面形式。"}, False),
    # 多版本（同名新旧）：as_of=2026 定新版现行；as_of=2015 定旧版→替代
    ("中华人民共和国合成换代测定法", "0103", "20050101", "03", "20050601", "",
     {"第一条": "为了规范旧版合成换代测定活动，制定本法。",
      "第二条": "旧版合成换代测定适用范围由配套细则规定。"}, False),
    ("中华人民共和国合成换代测定法", "0104", "20181201", "01", "20190101", "",
     {"第一条": "为了规范合成换代测定活动，制定本法。",
      "第二条": "合成换代测定适用于合成产业全流程。",
      "第三条": "合成换代测定应当接受全程监督。"}, False),
    # 尚未施行（02，SXRQ 晚于钉定 as_of）
    ("中华人民共和国合成未来施行法", "0105", "20260626", "02", "20270101", "",
     {"第一条": "本法施行后规范合成未来活动秩序。"}, False),
    # 已废止（04，有/无失效日）
    ("中华人民共和国合成旧管理条例", "0106", "20150101", "04", "20150601",
     "20200101", None, False),
    ("中华人民共和国合成无期废止法", "0107", "20170101", "04", "20170601",
     "", None, False),
    # 已修订（03 单版本）
    ("中华人民共和国合成修订贸易法", "0108", "20081227", "03", "20090101",
     "", None, False),
    # 已失效（05 单版本）
    ("中华人民共和国合成失效条例", "0109", "20120301", "05", "20120601",
     "", None, False),
    # 无 GB 码（DE_01001 空＝结构性缺口→未知 fail-closed）
    ("中华人民共和国合成无码条例", "0110", "20200101", "01", "20200601",
     "", None, True),
]

# 虚构标题（正式面不存在的标题→本地面未命中=虚构·本地段）
CIT_FABRICATED_TITLES = ["中华人民共和国合成月球管辖法",
                         "中华人民共和国合成深空采矿法"]

# 黄金集条目（手钉标签）。期望值全部按 citation_verifier→statute_validity
# →lccc_consumer v1.1 的实测语义逐条推演钉定：
#   set ∈ {answerable, refuse}；expected_wjbs=None 表示期望路由到"未命中"；
#   must_cite=可答集应肯定条文号；must_not_cite=应拒集绝不可肯定条文号；
#   expected_excerpts=引用回读（support.article_text）应含片段。
_CIT_WJBS_BY_SEQ = {seq: _cit_wjbs(seq, gbrq)[1]
                    for _t, seq, gbrq, _s, _x, _h, _c, _n in CIT_STATUTES}
_CIT_W = {
    "A1": _CIT_WJBS_BY_SEQ["0101"], "A2": _CIT_WJBS_BY_SEQ["0102"],
    "M_OLD": _CIT_WJBS_BY_SEQ["0103"], "M_NEW": _CIT_WJBS_BY_SEQ["0104"],
    "NTY": _CIT_WJBS_BY_SEQ["0105"], "ABO1": _CIT_WJBS_BY_SEQ["0106"],
    "ABO2": _CIT_WJBS_BY_SEQ["0107"], "AMD": _CIT_WJBS_BY_SEQ["0108"],
    "EXP": _CIT_WJBS_BY_SEQ["0109"], "NOCODE": _CIT_WJBS_BY_SEQ["0110"],
}

CIT_GOLDEN_ITEMS = [
    # -------- 可答集（12）：覆盖正确＝现行＋真定位＋（有引文时）支持核验过
    {"id": "ans-0001", "set": "answerable",
     "citation": "《中华人民共和国合成数据保护法》第一条规定："
                 "“为了规范合成数据处理活动，保护合成数据权益，制定本法。”",
     "as_of": CIT_FIXED_AS_OF, "expected_status": "现行",
     "expected_code": "CURRENT_IN_FORCE_CITABLE", "expected_decision": "ALLOWED",
     "expected_wjbs": _CIT_W["A1"], "expected_verified": True,
     "must_cite": [1], "must_not_cite": [], "expected_excerpts": ["规范合成数据处理活动"],
     "note": "现行＋真引文支持核验＋引用回读"},
    {"id": "ans-0002", "set": "answerable",
     "citation": "《中华人民共和国合成数据保护法》第三条",
     "as_of": CIT_FIXED_AS_OF, "expected_status": "现行",
     "expected_code": "CURRENT_IN_FORCE_CITABLE", "expected_decision": "ALLOWED",
     "expected_wjbs": _CIT_W["A1"], "expected_verified": True,
     "must_cite": [3], "must_not_cite": [], "expected_excerpts": [],
     "note": "现行无引文（条文定位级）"},
    {"id": "ans-0003", "set": "answerable",
     "citation": "《中华人民共和国合成数据保护法》",
     "as_of": CIT_FIXED_AS_OF, "expected_status": "现行",
     "expected_code": "CURRENT_IN_FORCE_CITABLE", "expected_decision": "ALLOWED",
     "expected_wjbs": _CIT_W["A1"], "expected_verified": True,
     "must_cite": [], "must_not_cite": [], "expected_excerpts": [],
     "note": "标题级引用（无条文）——范围记账停在标题级"},
    {"id": "ans-0004", "set": "answerable",
     "citation": "《中华人民共和国合成贸易促进法》第二条规定："
                 "“合成贸易争端应当优先通过协商解决。”",
     "as_of": CIT_FIXED_AS_OF, "expected_status": "现行",
     "expected_code": "CURRENT_IN_FORCE_CITABLE", "expected_decision": "ALLOWED",
     "expected_wjbs": _CIT_W["A2"], "expected_verified": True,
     "must_cite": [2], "must_not_cite": [], "expected_excerpts": ["优先通过协商解决"],
     "note": "第二法现行＋真引文"},
    {"id": "ans-0005", "set": "answerable",
     "citation": "《中华人民共和国合成贸易促进法》第二十条",
     "as_of": CIT_FIXED_AS_OF, "expected_status": "现行",
     "expected_code": "CURRENT_IN_FORCE_CITABLE", "expected_decision": "ALLOWED",
     "expected_wjbs": _CIT_W["A2"], "expected_verified": True,
     "must_cite": [20], "must_not_cite": [], "expected_excerpts": [],
     "note": "复合中文数字条文号（二十）"},
    {"id": "ans-0006", "set": "answerable",
     "citation": "《中华人民共和国合成贸易促进法》第六条第一款",
     "as_of": CIT_FIXED_AS_OF, "expected_status": "现行",
     "expected_code": "CURRENT_IN_FORCE_CITABLE", "expected_decision": "ALLOWED",
     "expected_wjbs": _CIT_W["A2"], "expected_verified": True,
     "must_cite": [6], "must_not_cite": [], "expected_excerpts": [],
     "note": "款跟随（第一款）"},
    {"id": "ans-0007", "set": "answerable",
     "citation": "《中华人民共和国合成换代测定法》第一条",
     "as_of": CIT_FIXED_AS_OF, "expected_status": "现行",
     "expected_code": "CURRENT_IN_FORCE_CITABLE", "expected_decision": "ALLOWED",
     "expected_wjbs": _CIT_W["M_NEW"], "expected_verified": True,
     "must_cite": [1], "must_not_cite": [], "expected_excerpts": [],
     "note": "多版本同名：as_of=2026 定版新版（01）——路由正确性硬扣"},
    {"id": "ans-0008", "set": "answerable",
     "citation": "《中华人民共和国合成换代测定法》第三条规定："
                 "“合成换代测定应当接受全程监督。”",
     "as_of": CIT_FIXED_AS_OF, "expected_status": "现行",
     "expected_code": "CURRENT_IN_FORCE_CITABLE", "expected_decision": "ALLOWED",
     "expected_wjbs": _CIT_W["M_NEW"], "expected_verified": True,
     "must_cite": [3], "must_not_cite": [], "expected_excerpts": ["全程监督"],
     "note": "多版本定版后真引文（新版载体）"},
    {"id": "ans-0009", "set": "answerable",
     "citation": "《中华人民共和国合成数据保护法》第四条",
     "as_of": CIT_FIXED_AS_OF, "expected_status": "现行",
     "expected_code": "CURRENT_IN_FORCE_CITABLE", "expected_decision": "ALLOWED",
     "expected_wjbs": _CIT_W["A1"], "expected_verified": True,
     "must_cite": [4], "must_not_cite": [], "expected_excerpts": [],
     "note": "现行条文定位"},
    {"id": "ans-0010", "set": "answerable",
     "citation": "《中华人民共和国合成贸易促进法》",
     "as_of": CIT_FIXED_AS_OF, "expected_status": "现行",
     "expected_code": "CURRENT_IN_FORCE_CITABLE", "expected_decision": "ALLOWED",
     "expected_wjbs": _CIT_W["A2"], "expected_verified": True,
     "must_cite": [], "must_not_cite": [], "expected_excerpts": [],
     "note": "第二法标题级引用"},
    {"id": "ans-0011", "set": "answerable",
     "citation": "《中华人民共和国合成数据保护法》第二条规定："
                 "“在中华人民共和国境内处理合成数据，适用本法。”",
     "as_of": CIT_FIXED_AS_OF, "expected_status": "现行",
     "expected_code": "CURRENT_IN_FORCE_CITABLE", "expected_decision": "ALLOWED",
     "expected_wjbs": _CIT_W["A1"], "expected_verified": True,
     "must_cite": [2], "must_not_cite": [], "expected_excerpts": ["适用本法"],
     "note": "第二条自身真引文（张冠李戴反例的真阳性对照）"},
    {"id": "ans-0012", "set": "answerable",
     "citation": "《中华人民共和国合成数据保护法》第五条第二款",
     "as_of": CIT_FIXED_AS_OF, "expected_status": "现行",
     "expected_code": "CURRENT_IN_FORCE_CITABLE", "expected_decision": "ALLOWED",
     "expected_wjbs": _CIT_W["A1"], "expected_verified": True,
     "must_cite": [5], "must_not_cite": [], "expected_excerpts": [],
     "note": "条＋款组合定位"},
    # -------- 应拒集（15）：正确拒绝＝verified_scoped=False＋具名不利状态
    {"id": "ref-0001", "set": "refuse",
     "citation": "《中华人民共和国合成月球管辖法》第一条",
     "as_of": CIT_FIXED_AS_OF, "expected_status": "虚构",
     "expected_code": "LOCAL_FACE_TITLE_MISS", "expected_decision": None,
     "expected_wjbs": None, "expected_verified": False,
     "must_cite": [], "must_not_cite": [1], "expected_excerpts": [],
     "note": "虚构标题（本地面未命中）＋付费缺口具名"},
    {"id": "ref-0002", "set": "refuse",
     "citation": "《中华人民共和国合成深空采矿法》",
     "as_of": CIT_FIXED_AS_OF, "expected_status": "虚构",
     "expected_code": "LOCAL_FACE_TITLE_MISS", "expected_decision": None,
     "expected_wjbs": None, "expected_verified": False,
     "must_cite": [], "must_not_cite": [], "expected_excerpts": [],
     "note": "虚构标题级引用"},
    {"id": "ref-0003", "set": "refuse",
     "citation": "《中华人民共和国合成数据保护法》第九十九条",
     "as_of": CIT_FIXED_AS_OF, "expected_status": "误引",
     "expected_code": "ARTICLE_NOT_IN_REAL_TEXT", "expected_decision": "ALLOWED",
     "expected_wjbs": _CIT_W["A1"], "expected_verified": False,
     "must_cite": [], "must_not_cite": [99], "expected_excerpts": [],
     "note": "条文号不存在于真实正文（诱导引不存在条文）"},
    {"id": "ref-0004", "set": "refuse",
     "citation": "《中华人民共和国合成贸易促进法》第八十八条",
     "as_of": CIT_FIXED_AS_OF, "expected_status": "误引",
     "expected_code": "ARTICLE_NOT_IN_REAL_TEXT", "expected_decision": "ALLOWED",
     "expected_wjbs": _CIT_W["A2"], "expected_verified": False,
     "must_cite": [], "must_not_cite": [88], "expected_excerpts": [],
     "note": "第二法条文号不存在"},
    {"id": "ref-0005", "set": "refuse",
     "citation": "《中华人民共和国合成数据保护法》第一条规定："
                 "“月球资源归全体合成居民共有，任何单位不得侵占。”",
     "as_of": CIT_FIXED_AS_OF, "expected_status": "误引",
     "expected_code": "QUOTE_NOT_IN_REAL_TEXT", "expected_decision": "ALLOWED",
     "expected_wjbs": _CIT_W["A1"], "expected_verified": False,
     "must_cite": [], "must_not_cite": [1], "expected_excerpts": [],
     "note": "伪引文（全文亦无）——08§3 引证矩阵「伪quote」"},
    {"id": "ref-0006", "set": "refuse",
     "citation": "《中华人民共和国合成数据保护法》第一条规定："
                 "“在中华人民共和国境内处理合成数据，适用本法。”",
     "as_of": CIT_FIXED_AS_OF, "expected_status": "误引",
     "expected_code": "QUOTE_MISATTRIBUTED", "expected_decision": "ALLOWED",
     "expected_wjbs": _CIT_W["A1"], "expected_verified": False,
     "must_cite": [], "must_not_cite": [1], "expected_excerpts": [],
     "note": "张冠李戴（引文真但在第二条）——「存在但不支持命题」"},
    {"id": "ref-0007", "set": "refuse",
     "citation": "《中华人民共和国合成贸易促进法》第二十条规定："
                 "“合成贸易合同一律采用口头形式订立。”",
     "as_of": CIT_FIXED_AS_OF, "expected_status": "误引",
     "expected_code": "QUOTE_NOT_IN_REAL_TEXT", "expected_decision": "ALLOWED",
     "expected_wjbs": _CIT_W["A2"], "expected_verified": False,
     "must_cite": [], "must_not_cite": [20], "expected_excerpts": [],
     "note": "第二法伪引文（与真文义相反）"},
    {"id": "ref-0008", "set": "refuse",
     "citation": "《中华人民共和国合成旧管理条例》第五条",
     "as_of": CIT_FIXED_AS_OF, "expected_status": "已废止",
     "expected_code": "ABOLISHED_NOT_CITABLE", "expected_decision": "BLOCKED",
     "expected_wjbs": _CIT_W["ABO1"], "expected_verified": False,
     "must_cite": [], "must_not_cite": [5], "expected_excerpts": [],
     "note": "已废止（有失效日）检索到也不许引"},
    {"id": "ref-0009", "set": "refuse",
     "citation": "《中华人民共和国合成无期废止法》第五条",
     "as_of": CIT_FIXED_AS_OF, "expected_status": "已废止",
     "expected_code": "ABOLISHED_NOT_CITABLE", "expected_decision": "BLOCKED",
     "expected_wjbs": _CIT_W["ABO2"], "expected_verified": False,
     "must_cite": [], "must_not_cite": [5], "expected_excerpts": [],
     "note": "已废止（无失效日）仍不许引"},
    {"id": "ref-0010", "set": "refuse",
     "citation": "《中华人民共和国合成修订贸易法》第二十一条",
     "as_of": CIT_FIXED_AS_OF, "expected_status": "已修订",
     "expected_code": "SUPERSEDED_NOT_CITABLE", "expected_decision": "BLOCKED",
     "expected_wjbs": _CIT_W["AMD"], "expected_verified": False,
     "must_cite": [], "must_not_cite": [21], "expected_excerpts": [],
     "note": "已修订（03 单版）不许引"},
    {"id": "ref-0011", "set": "refuse",
     "citation": "《中华人民共和国合成失效条例》第十条",
     "as_of": CIT_FIXED_AS_OF, "expected_status": "失效",
     "expected_code": "SUPERSEDED_NOT_CITABLE", "expected_decision": "BLOCKED",
     "expected_wjbs": _CIT_W["EXP"], "expected_verified": False,
     "must_cite": [], "must_not_cite": [10], "expected_excerpts": [],
     "note": "已失效（05 单版）"},
    {"id": "ref-0012", "set": "refuse",
     "citation": "《中华人民共和国合成换代测定法》第一条",
     "as_of": CIT_PAST_AS_OF, "expected_status": "替代",
     "expected_code": "SUPERSEDED_NOT_CITABLE", "expected_decision": "BLOCKED",
     "expected_wjbs": _CIT_W["M_OLD"], "expected_verified": False,
     "must_cite": [], "must_not_cite": [1], "expected_excerpts": [],
     "note": "多版本旧时点定版旧版＋同名新版在库→替代——08§3「旧法」"},
    {"id": "ref-0013", "set": "refuse",
     "citation": "《中华人民共和国合成未来施行法》第一条",
     "as_of": CIT_FIXED_AS_OF, "expected_status": "未知",
     "expected_code": "NOT_YET_IN_FORCE_AT_AS_OF", "expected_decision": "BLOCKED",
     "expected_wjbs": _CIT_W["NTY"], "expected_verified": False,
     "must_cite": [], "must_not_cite": [1], "expected_excerpts": [],
     "note": "尚未施行（时点冲突）→未知 fail-closed 不签现行"},
    {"id": "ref-0014", "set": "refuse",
     "citation": "《中华人民共和国合成无码条例》第一条",
     "as_of": CIT_FIXED_AS_OF, "expected_status": "未知",
     "expected_code": "FACE_STRUCTURAL_GAP_FAIL_CLOSED:NO_GB_FILE_CODE_SCOPE_GAP",
     "expected_decision": "UNKNOWN",
     "expected_wjbs": _CIT_W["NOCODE"], "expected_verified": False,
     "must_cite": [], "must_not_cite": [1], "expected_excerpts": [],
     "note": "无 GB 码（效力 unknown）——08§3「效力unknown」"},
    {"id": "ref-0015", "set": "refuse",
     "citation": "《中华人民共和国合成月球管辖法》第六十条",
     "as_of": CIT_FIXED_AS_OF, "expected_status": "虚构",
     "expected_code": "LOCAL_FACE_TITLE_MISS", "expected_decision": None,
     "expected_wjbs": None, "expected_verified": False,
     "must_cite": [], "must_not_cite": [60], "expected_excerpts": [],
     "note": "虚构标题＋虚构条文号（诱导题 adv-001 同型）"},
]

_CIT_CN_NUM = {"一": "1", "二": "2", "三": "3", "四": "4", "五": "5",
               "六": "6", "二十": "20"}


def _carrier_md(title: str, wjbs: str, articles: dict) -> str:
    """合成 md 载体（frontmatter＋题名＋'- **第N条**' 条款式，与
    split_articles 状态机对齐）。source_sha256 为合成占位（64 hex 派生）。"""
    sha = hashlib.sha256(("f88-carrier:" + wjbs).encode("utf-8")).hexdigest()
    lines = [
        "---",
        'object_type: "legal_document"',
        'identifier: "%s"' % wjbs,
        'source_sha256: "%s"' % sha,
        "---",
        "",
        "# " + title,
        "",
    ]
    for marker, text in articles.items():
        lines.append("- **%s**\u3000\u3000%s" % (marker, text))
        lines.append("")
    return "\n".join(lines)


def build_citations(out_dir: Path, seed: int) -> dict:
    """F88 双集合黄金集构建（确定性手钉；seed 入清单与摘要 core）。"""
    rng = random.Random(seed)  # 钉定（当前内容手钉不消耗随机数；保留口径）
    assert rng is not None
    face = out_dir / CIT_FACE_DIR
    face.mkdir(parents=True, exist_ok=True)
    statutes_manifest = []
    with (face / "legal_documents.csv").open("w", encoding="utf-8-sig",
                                             newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(CIT_DOC_COLUMNS)
        for title, seq, gbrq, sxx, sxrq, shxrq, carrier, nocode in CIT_STATUTES:
            body, wjbs = _cit_wjbs(seq, gbrq)
            writer.writerow([wjbs, title, gbrq, sxx, sxx, sxrq, shxrq,
                             "" if nocode else body, "国家法律法规数据库"])
            entry = {"title": title, "wjbs": wjbs, "sxx": sxx, "gbrq": gbrq,
                     "sxrq": sxrq, "shxrq": shxrq,
                     "has_file_code": not nocode,
                     "carrier_md": None}
            if carrier is not None:
                md = _carrier_md(title, wjbs, carrier)
                md_name = "carrier_%s.md" % wjbs
                (face / md_name).write_text(md, encoding="utf-8")
                entry["carrier_md"] = md_name
                entry["carrier_sha256"] = sha256_bytes(md.encode("utf-8"))
            statutes_manifest.append(entry)
            eprint("  [cit] %s %s sxx=%s sxrq=%s carrier=%s"
                   % (title, wjbs, sxx, sxrq, "yes" if carrier else "no"))
    for name in ("legal_contents.csv", "legal_relations.csv",
                 "legal_sources.csv", "cases.csv", "case_legal_references.csv",
                 "case_holdings.csv", "practice_references.csv"):
        (face / name).write_text("WJBS\n", encoding="utf-8-sig")
    (face / "README.md").write_text(
        "synthetic F88 citations golden-set face (all synthetic; seed=%d)\n"
        % seed, encoding="utf-8")
    (face / "SHA256SUMS").write_text(
        "synthetic-f88-citations-fixture seed=%d\n" % seed, encoding="utf-8")

    answerable = [it for it in CIT_GOLDEN_ITEMS if it["set"] == "answerable"]
    refuse = [it for it in CIT_GOLDEN_ITEMS if it["set"] == "refuse"]
    manifest = {
        "schema": CIT_SCHEMA,
        "generator": CIT_GEN_REV,
        "seed": seed,
        "fixed_as_of": CIT_FIXED_AS_OF,
        "past_as_of_variant": CIT_PAST_AS_OF,
        "face_dir": CIT_FACE_DIR,
        "face_files": sorted(p.name for p in face.iterdir()),
        "statutes": statutes_manifest,
        "fabricated_titles": CIT_FABRICATED_TITLES,
        "counts": {"answerable": len(answerable), "refuse": len(refuse),
                   "common": len(CIT_GOLDEN_ITEMS)},
        "metrics_source": "judicex gold_runner.py 阈值表（蓝图 L13；竞品情报 "
                          "2026-10-12/repos/TEARDOWN-doc-haus-judicex.md §3.2）"
                          "——六指标与阈值由消费侧 f88_dualset_ci.py 冻结",
        "items": CIT_GOLDEN_ITEMS,
        "note": "全合成材料（标题全部含「合成」，正文手钉）；as_of 钉定常量"
                "（非今日函数）；期望标签按 F70 核验链（citation_verifier→"
                "statute_validity→lccc_consumer v1.1）逐条推演钉定",
    }
    (out_dir / GOLDEN_NAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True)
        + "\n", encoding="utf-8")
    core = {"schema": CIT_SCHEMA, "seed": seed, "mode": "citations"}
    digest = citations_digest(out_dir, core)
    (out_dir / CIT_DIGEST_NAME).write_text(
        "%s  seed=%d citations golden answerable=%d refuse=%d\n"
        % (digest, seed, len(answerable), len(refuse)), encoding="ascii")
    return {"manifest": manifest, "digest": digest,
            "answerable": len(answerable), "refuse": len(refuse),
            "out": str(out_dir)}


def citations_digest(out_dir: Path, core: dict) -> str:
    """黄金集全树摘要（排除摘要文件自身；含黄金集清单与合成面全部文件）。"""
    lines: list[str] = []
    for p in sorted(out_dir.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(out_dir).as_posix()
        if rel == CIT_DIGEST_NAME:
            continue
        lines.append("%s %s" % (rel, sha256_file(p)))
    payload = (json.dumps(core, sort_keys=True, ensure_ascii=False)
               .encode("utf-8") + b"\n" + "\n".join(lines).encode("utf-8"))
    return sha256_bytes(payload)


# ---------- W2b-U12 F48 模式：全合成复杂 DOCX（seed 钉定，同 seed 同字节） ----------

DOCX_SCHEMA = "juscite-e12-docx/1"
DOCX_MANIFEST = "docx_manifest.json"
DOCX_GEN_REV = "tools/e12_corpus_gen.py docx-mode r1 (W2b-U12)"

_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"

DOCX_SENTENCES = [
    "原告与被告于合成日期签订编号为F48-合-0001的买卖合同，约定由原告向被告供应合成设备一批。",
    "合同项下货款总额为人民币壹佰贰拾万元整，被告应在验收合格后三十日内一次性付清。",
    "被告收货后仅支付部分货款，剩余款项经原告多次催告至今未付，已构成根本违约。",
    "原告据此请求解除双方签订的买卖合同，并由被告承担相应违约责任。",
    "双方在合同中明确约定争议由合同签订地有管辖权的人民法院管辖。",
    "本诉状所涉当事人名称、案号与金额均为合成虚构，不指向任何真实主体。",
    "原告已就本案保全事宜另行提出申请，恳请法院依法审查并作出裁定。",
    "被告以货物存在质量瑕疵为由拒付尾款，但未在约定的异议期内提出书面异议。",
    "原告按合同约定履行了全部供货义务，有送货单与验收记录为凭。",
    "上述事实有合同原件、转账凭证及双方往来函件予以佐证，足以认定。",
]
DOCX_TABLE_HEADER = ["款项名称", "金额（元）", "约定支付日期"]
DOCX_TABLE_ROWS = [
    ["首期货款", "480,000.00", "2026-03-31"],
    ["到期货款", "360,000.00", "2026-06-30"],
    ["验收尾款", "360,000.00", "2026-09-30"],
]


def _xml_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _docx_xml_decl() -> str:
    return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'


def _docx_paragraph(text: str, split_offsets: list[int], *,
                    bold: bool = False, centered: bool = False,
                    footnote_ref: bool = False) -> str:
    """合成段落：文本按 split_offsets 切成多个 w:r（真实 Word 常见的跨 run
    文本，逼 F48 引擎真做 run 切分定位）。"""
    out = ["<w:p>"]
    if centered:
        out.append('<w:pPr><w:jc w:val="center"/></w:pPr>')
    if bold:
        out.append('<w:r><w:rPr><w:b/></w:rPr>'
                   f"<w:t>{_xml_escape(text)}</w:t></w:r>")
    else:
        pieces = []
        previous = 0
        for offset in sorted(set(split_offsets)) + [len(text)]:
            pieces.append(text[previous:offset])
            previous = offset
        for piece in pieces:
            if piece:
                out.append(f"<w:r><w:t>{_xml_escape(piece)}</w:t></w:r>")
    if footnote_ref:
        out.append('<w:r><w:rPr><w:rStyle w:val="a4"/></w:rPr>'
                   '<w:footnoteReference w:id="1"/></w:r>')
    out.append("</w:p>")
    return "".join(out)


def _docx_table() -> str:
    rows = [DOCX_TABLE_HEADER] + DOCX_TABLE_ROWS
    out = ["<w:tbl>", '<w:tblGrid><w:gridCol w:w="2800"/>'
           '<w:gridCol w:w="2800"/><w:gridCol w:w="2800"/></w:tblGrid>']
    for row in rows:
        out.append("<w:tr>")
        for cell in row:
            out.append('<w:tc><w:tcPr><w:tcW w:w="2800" w:type="dxa"/></w:tcPr>'
                       f"<w:p><w:r><w:t>{_xml_escape(cell)}</w:t></w:r></w:p>"
                       "</w:tc>")
        out.append("</w:tr>")
    out.append("</w:tbl>")
    return "".join(out)


def _docx_sect_pr() -> str:
    return ('<w:sectPr><w:headerReference w:type="default" r:id="rId3"/>'
            '<w:footerReference w:type="default" r:id="rId4"/>'
            '<w:pgSz w:w="11906" w:h="16838"/>'
            '<w:pgMar w:top="1440" w:right="1800" w:bottom="1440"'
            ' w:left="1800" w:header="851" w:footer="992" w:gutter="0"/>'
            "</w:sectPr>")


def _docx_complex_document(seed: int) -> tuple[str, dict]:
    """复杂 DOCX 正文：标题＋多段落（跨 run 切分）＋表＋脚注引用段＋
    重复句（供 quote_not_unique 负例）；返回 (document.xml, 文本清单)。"""
    rng = random.Random(seed)
    paragraphs = list(DOCX_SENTENCES)
    rng.shuffle(paragraphs)
    repeat_at = sorted(rng.sample(range(len(paragraphs)), 2))
    splits: list[list[int]] = []
    for text in paragraphs:
        splits.append(sorted({len(text) // 3, 2 * len(text) // 3})
                      if len(text) > 12 else [])
    body = [_docx_paragraph("民事起诉状（F48 全合成语料）", [],
                            bold=True, centered=True)]
    manifest_paragraphs = []
    for index, text in enumerate(paragraphs):
        if index in repeat_at:
            # 重复句：同句入两段（quote_not_unique 负例素材；清单记一次）
            body.append(_docx_paragraph(text, splits[index]))
            body.append(_docx_paragraph(text, splits[index]))
            manifest_paragraphs.append({"text": text, "repeat": True,
                                        "run_splits": splits[index]})
            continue
        body.append(_docx_paragraph(text, splits[index]))
        manifest_paragraphs.append({"text": text, "repeat": False,
                                    "run_splits": splits[index]})
    body.append(_docx_table())
    footnote_text = "本脚注内容同为合成虚构，用于验证脚注部件在编辑后字节保真。"
    body.append(_docx_paragraph(
        "如表所列款项到期未获清偿，原告依法主张逾期利息。（见脚注）", [7, 21],
        footnote_ref=True))
    body.append(_docx_sect_pr())
    document = (_docx_xml_decl()
                + f'<w:document xmlns:w="{_W_NS}" xmlns:r="{_R_NS}">'
                + "<w:body>" + "".join(body) + "</w:body></w:document>")
    texts = {
        "paragraphs": manifest_paragraphs,
        "footnote_paragraph": "如表所列款项到期未获清偿，原告依法主张逾期利息。（见脚注）",
        "footnote_text": footnote_text,
        "table_header": DOCX_TABLE_HEADER,
        "table_rows": DOCX_TABLE_ROWS,
    }
    return document, texts


def _docx_existing_revisions_document(seed: int) -> tuple[str, dict]:
    """带前手现存修订的 DOCX：w:ins(id=900)/w:del(id=901) 作者=prior-author
    （逼 F48 引擎 id 分配越过既有修订、对账不误认他作者修订）。"""
    rng = random.Random(seed + 1)
    paragraphs = list(DOCX_SENTENCES[:6])
    rng.shuffle(paragraphs)
    inserted = "（前手插入的合成句，作者=prior-author）"
    deleted = "（前手删除的合成句，应随 w:delText 留痕）"
    body = [_docx_paragraph("合成修订前文书（F48 全合成语料）", [],
                            bold=True, centered=True)]
    for index, text in enumerate(paragraphs):
        body.append(_docx_paragraph(text, [len(text) // 2] if len(text) > 12 else []))
        if index == 1:
            body.append(
                '<w:ins w:id="900" w:author="prior-author"'
                ' w:date="2026-09-01T00:00:00Z">'
                f"<w:r><w:t>{_xml_escape(inserted)}</w:t></w:r></w:ins>")
            body.append("<w:p/>")
        if index == 3:
            body.append(
                '<w:del w:id="901" w:author="prior-author"'
                ' w:date="2026-09-02T00:00:00Z">'
                '<w:r><w:delText xml:space="preserve">'
                f"{_xml_escape(deleted)}</w:delText></w:r></w:del>")
            body.append("<w:p/>")
    body.append(_docx_sect_pr())
    document = (_docx_xml_decl()
                + f'<w:document xmlns:w="{_W_NS}" xmlns:r="{_R_NS}">'
                + "<w:body>" + "".join(body) + "</w:body></w:document>")
    texts = {
        "paragraphs": [{"text": text, "repeat": False,
                        "run_splits": [len(text) // 2] if len(text) > 12 else []}
                       for text in paragraphs],
        "prior_ins": {"id": "900", "author": "prior-author", "text": inserted},
        "prior_del": {"id": "901", "author": "prior-author", "text": deleted},
    }
    return document, texts


def _docx_header_footer() -> tuple[str, str]:
    header = (_docx_xml_decl()
              + f'<w:hdr xmlns:w="{_W_NS}" xmlns:r="{_R_NS}">'
              + '<w:p><w:pPr><w:jc w:val="center"/></w:pPr>'
              "<w:r><w:t>F48 全合成语料页眉（律引）</w:t></w:r></w:p></w:hdr>")
    footer = (_docx_xml_decl()
              + f'<w:ftr xmlns:w="{_W_NS}" xmlns:r="{_R_NS}">'
              + '<w:p><w:pPr><w:jc w:val="center"/></w:pPr>'
              "<w:r><w:t>第 1 页（合成）</w:t></w:r></w:p></w:ftr>")
    return header, footer


def _docx_footnotes(footnote_text: str) -> str:
    return (_docx_xml_decl()
            + f'<w:footnotes xmlns:w="{_W_NS}" xmlns:r="{_R_NS}">'
            + '<w:footnote w:type="separator" w:id="-1"><w:p>'
            '<w:pPr><w:spacing w:after="0" w:line="240"'
            ' w:lineRule="auto"/></w:pPr></w:p></w:footnote>'
            + '<w:footnote w:type="continuationSeparator" w:id="0"><w:p>'
            '<w:pPr><w:spacing w:after="0" w:line="240"'
            ' w:lineRule="auto"/></w:pPr></w:p></w:footnote>'
            + f'<w:footnote w:id="1"><w:p><w:r>'
            f"<w:t>{_xml_escape(footnote_text)}</w:t></w:r></w:p></w:footnote>"
            + "</w:footnotes>")


def _docx_styles() -> str:
    return (_docx_xml_decl()
            + f'<w:styles xmlns:w="{_W_NS}">'
            + '<w:style w:type="paragraph" w:default="1" w:styleId="Normal">'
            '<w:name w:val="Normal"/></w:style>'
            + '<w:style w:type="character" w:styleId="a4">'
            '<w:name w:val="footnote reference"/></w:style>'
            + "</w:styles>")


def _docx_content_types() -> str:
    main = "application/vnd.openxmlformats-officedocument.wordprocessingml."
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            f'<Types xmlns="{_CT_NS}">'
            '<Default Extension="rels" ContentType="application/vnd.'
            'openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            f'<Override PartName="/word/document.xml" ContentType="{main}'
            'document.main+xml"/>'
            f'<Override PartName="/word/styles.xml" ContentType="{main}styles+xml"/>'
            f'<Override PartName="/word/footnotes.xml" ContentType="{main}'
            'footnotes+xml"/>'
            f'<Override PartName="/word/header1.xml" ContentType="{main}header+xml"/>'
            f'<Override PartName="/word/footer1.xml" ContentType="{main}footer+xml"/>'
            "</Types>")


def _docx_root_rels() -> str:
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            f'<Relationships xmlns="{_REL_NS}">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/'
            'officeDocument/2006/relationships/officeDocument"'
            ' Target="word/document.xml"/>'
            "</Relationships>")


def _docx_document_rels() -> str:
    base = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            f'<Relationships xmlns="{_REL_NS}">'
            f'<Relationship Id="rId1" Type="{base}styles" Target="styles.xml"/>'
            f'<Relationship Id="rId2" Type="{base}footnotes"'
            ' Target="footnotes.xml"/>'
            f'<Relationship Id="rId3" Type="{base}header" Target="header1.xml"/>'
            f'<Relationship Id="rId4" Type="{base}footer" Target="footer1.xml"/>'
            "</Relationships>")


def _write_docx(path: Path, parts: list[tuple[str, str]]) -> None:
    import zipfile as _zf
    with _zf.ZipFile(path, "w", _zf.ZIP_DEFLATED) as zf:
        for name, payload in parts:
            info = _zf.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = _zf.ZIP_DEFLATED
            zf.writestr(info, payload.encode("utf-8"))


def build_docx_corpus(out_dir: Path, seed: int) -> dict:
    """F48 全合成复杂 DOCX 语料：两份 DOCX（复杂版＋现存修订版）＋清单。

    确定性：内容手钉＋seed 只控段落顺序抽样；zip 全部件固定时间戳
    (1980-01-01)固定顺序——同 seed 同机同 Python/zlib → 逐字节相同。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    header, footer = _docx_header_footer()
    complex_xml, complex_texts = _docx_complex_document(seed)
    prior_xml, prior_texts = _docx_existing_revisions_document(seed)
    common_tail = [
        ("word/styles.xml", _docx_styles()),
        ("word/footnotes.xml", _docx_footnotes(complex_texts["footnote_text"])),
        ("word/header1.xml", header),
        ("word/footer1.xml", footer),
        ("word/_rels/document.xml.rels", _docx_document_rels()),
    ]
    complex_parts = ([("[Content_Types].xml", _docx_content_types()),
                      ("_rels/.rels", _docx_root_rels()),
                      ("word/document.xml", complex_xml)] + common_tail)
    prior_parts = ([("[Content_Types].xml", _docx_content_types()),
                    ("_rels/.rels", _docx_root_rels()),
                    ("word/document.xml", prior_xml)] + common_tail)
    complex_name = "f48_doc_complex.docx"
    prior_name = "f48_doc_existing_revisions.docx"
    _write_docx(out_dir / complex_name, complex_parts)
    _write_docx(out_dir / prior_name, prior_parts)
    files = []
    for name in (complex_name, prior_name):
        files.append({"name": name, "bytes": (out_dir / name).stat().st_size,
                      "sha256": sha256_file(out_dir / name)})
    texts = {"repeat_paragraph": next((p["text"] for p
                                       in complex_texts["paragraphs"]
                                       if p["repeat"]), None),
             **{k: v for k, v in complex_texts.items()},
             "prior_document": prior_texts}
    manifest = {
        "schema": DOCX_SCHEMA, "generator": DOCX_GEN_REV, "seed": seed,
        "files": files, "texts": texts,
        "note": "全合成虚构（当事人/案号/金额皆假）；F48 验收调用钉 "
                "--seed 20261017",
    }
    digest = sha256_bytes(json.dumps(manifest, sort_keys=True,
                                     ensure_ascii=False).encode("utf-8"))
    manifest["digest"] = digest
    (out_dir / DOCX_MANIFEST).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8")
    return {"manifest": manifest, "digest": digest}


# ============================================================ W4-U35 印章/PS 痕迹金标盒夹具
# F42 印章/PS 疑似视觉检测：合成语料带金标印章/PS 痕迹盒（--attachments
# 扩展先例 W2a-U15 同式）。两卷八页：印章页（强红/浅淡/叠字大章）＋红色
# PS 贴块（视觉异常向正例）＋对照页（净页/红字线误报向例证/非红贴块漏报
# 向例证＝检测局限具名边界/空白）。金标盒（gold_boxes）入清单但 F42 服务
# 面白名单（_PAGE_FIELDS 闭集）结构性不读；全部确定性绘制（零随机数）；
# 同 seed 同字节。页面几何（1240×1754）与印迹配色沿用 W4-U21 anonymizer
# stamp_visual 面真引擎组实测钉定（钉定参数 min_area 1200px 下环带≈9.4k
# px、贴块≈33k px 均在检；浅淡印迹落 0.55-0.65 置信带如实可检）。

STAMP_SCHEMA = "juscite-f42-stamp-gold/1"
STAMP_GEN_REV = "tools/e12_corpus_gen.py stamp-boxes r1 (W4-U35)"
STAMP_DIGEST_NAME = "f42_stamp_digest.txt"
STAMP_PAGE_W, STAMP_PAGE_H = 1240, 1754
STAMP_RED = (185, 30, 35)         # 强红（HSV S≈214，检测参数带内）
STAMP_RED_DARK = (140, 20, 25)    # 贴块接缝深红（仍在红主导带内）
STAMP_PALE = (225, 130, 135)      # 浅淡印泥（S≈108，低饱和可检带）
STAMP_DARK_PATCH = (70, 70, 72)   # 非红篡改贴块（S≈7——探针范围外例证）
STAMP_BODY_LINES = 18


def _stamp_seal(d, cx: int, cy: int, r: int, color, star: bool = True,
                text: str = "SYN-SEAL") -> None:
    """圆章：环带＋五角星＋环内弧排字（确定性；同 W4-U21 实测式样）。"""
    import math
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=color,
              width=max(4, r // 14))
    if star:
        pts = []
        for k in range(10):
            rr = r * 0.38 if k % 2 == 0 else r * 0.16
            a = -math.pi / 2 + k * math.pi / 5
            pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
        d.polygon(pts, fill=color)
    if text:
        n = len(text)
        rr = r * 0.72
        for i, ch in enumerate(text):
            a = -math.pi / 2 + (i - (n - 1) / 2) * (
                math.pi * 1.4 / max(1, n - 1))
            d.text((cx + rr * math.cos(a) - 5, cy + rr * math.sin(a) - 7),
                   ch, fill=color)


def _stamp_page(kind: str) -> tuple[Image.Image, list[dict]]:
    """单页确定性绘制：正文行＋按 kind 叠加印迹/贴块。返回（图，金标盒）。"""
    img = Image.new("RGB", (STAMP_PAGE_W, STAMP_PAGE_H), (255, 255, 255))
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype(str(font_path()), 24)
    gold: list[dict] = []
    if kind != "blank":
        for line in range(STAMP_BODY_LINES):
            d.text((90, 120 + line * 42),
                   f"SJ-F42-{kind}-line{line:02d} 0123456789 合成正文行",
                   font=font, fill=(25, 25, 25))
    if kind == "seal_strong":
        cx, cy, r = 920, 330, 150
        _stamp_seal(d, cx, cy, r, STAMP_RED)
        gold.append({"kind": "seal_red_strong", "cx": cx, "cy": cy,
                     "box": [cx - r, cy - r, cx + r, cy + r]})
    elif kind == "seal_pale":
        cx, cy, r = 350, 1200, 140
        _stamp_seal(d, cx, cy, r, STAMP_PALE)
        gold.append({"kind": "seal_red_pale", "cx": cx, "cy": cy,
                     "box": [cx - r, cy - r, cx + r, cy + r]})
    elif kind == "seal_overlap":
        cx, cy, r = 620, 877, 190
        _stamp_seal(d, cx, cy, r, STAMP_RED)
        gold.append({"kind": "seal_red_overlap", "cx": cx, "cy": cy,
                     "box": [cx - r, cy - r, cx + r, cy + r]})
    elif kind == "ps_red_paste":
        # PS 贴块（视觉异常向正例）：红色矩形贴块＋深红接缝边——红色主导
        # 探针按疑似视觉异常报出；不构成任何真伪结论（局限声明随记录）。
        x0, y0, x1, y1 = 700, 950, 920, 1100
        d.rectangle([x0, y0, x1, y1], fill=STAMP_RED)
        d.rectangle([x0, y0, x1, y1], outline=STAMP_RED_DARK, width=6)
        gold.append({"kind": "ps_red_paste", "cx": (x0 + x1) // 2,
                     "cy": (y0 + y1) // 2, "box": [x0, y0, x1, y1]})
    elif kind == "red_text":
        # 误报向例证：红色文字＋红色下划线（细划线低于 min_area/aspect 过滤
        # ——钉定参数下不报；局限声明具名红色元素可能误报的方向）。
        big = ImageFont.truetype(str(font_path()), 30)
        d.text((120, 900), "RED-LINE-SYN-0123", font=big, fill=STAMP_RED)
        d.line([120, 940, 640, 940], fill=STAMP_RED, width=3)
    elif kind == "ps_nonred_paste":
        # 漏报向例证（检测局限具名边界）：非红篡改贴块在红色主导探针
        # 检测范围外——如实不检出，作局限例证入证（不是缺陷）。
        x0, y0, x1, y1 = 640, 1000, 790, 1110
        d.rectangle([x0, y0, x1, y1], fill=STAMP_DARK_PATCH)
        gold.append({"kind": "ps_nonred_out_of_scope", "cx": (x0 + x1) // 2,
                     "cy": (y0 + y1) // 2, "box": [x0, y0, x1, y1]})
    return img, gold


def build_stamp_boxes(out_dir: Path, seed: int) -> dict:
    """F42 金标盒语料构建（确定性，零随机数）：两卷八页，金标盒随清单。"""
    fpath = font_path()
    plan = [
        ("doc_f42_a", "SJ-F42-A",
         [("seal_strong", "强红印章"), ("seal_pale", "浅淡印泥"),
          ("seal_overlap", "叠字大章"), ("ps_red_paste", "红色 PS 贴块")]),
        ("doc_f42_b", "SJ-F42-B",
         [("clean", "净页"), ("red_text", "红字线"),
          ("ps_nonred_paste", "非红贴块"), ("blank", "空白")]),
    ]
    (out_dir / "pages").mkdir(parents=True, exist_ok=True)
    documents = []
    for doc_id, doc_code, pages in plan:
        page_files = []
        for page, (kind, label) in enumerate(pages, start=1):
            img, gold = _stamp_page(kind)
            png = to_png(img)
            rel = f"pages/{doc_id}/p{page:04d}.png"
            (out_dir / rel).parent.mkdir(parents=True, exist_ok=True)
            (out_dir / rel).write_bytes(png)
            page_files.append({
                "page": page, "kind": kind, "png": rel,
                "sha256": sha256_bytes(png), "bytes": len(png),
                "gold_boxes": gold,      # 金标：服务面白名单结构性不读
            })
            eprint(f"  [stamp] {doc_id} p{page}: {kind}（{label}）"
                   f" gold={len(gold)}")
        documents.append({
            "doc_id": doc_id, "doc_code": doc_code,
            "title": f"合成印章痕迹卷：{doc_code}（全合成测试材料）",
            "page_count": len(page_files), "page_files": page_files,
        })
    manifest = {
        "schema": STAMP_SCHEMA,
        "generator": STAMP_GEN_REV,
        "seed": seed,
        "page_px": [STAMP_PAGE_W, STAMP_PAGE_H],
        "env": {"python": sys.version.split()[0],
                "pillow": __import__("PIL").__version__,
                "font_path": str(fpath), "font_sha256": sha256_file(fpath)},
        "documents": documents,
        "note": "全合成（印章/贴块皆绘制产物）；F42 验收调用钉 --seed "
                "20261020；金标盒仅验收侧直读，登记面结构性不读",
    }
    (out_dir / MANIFEST_NAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True)
        + "\n", encoding="utf-8")
    core = {"seed": seed, "schema": STAMP_SCHEMA, "page_px":
            [STAMP_PAGE_W, STAMP_PAGE_H]}
    digest = tree_digest(out_dir, core)
    (out_dir / STAMP_DIGEST_NAME).write_text(
        f"{digest}  seed={seed} stamp-boxes\n", encoding="ascii")
    gold_total = sum(len(pf["gold_boxes"])
                     for d in documents for pf in d["page_files"])
    return {"manifest": manifest, "digest": digest, "pages": 8,
            "gold_boxes": gold_total, "out": str(out_dir)}


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(description="E12 全合成 OCR 验收语料生成器（同 seed 同字节）")
    ap.add_argument("--attachments", metavar="DIR", default=None,
                    help="W2a-U15 F38/F44 附件夹具模式：合成含 PII 扫描页"
                         "（att_0001 干净/att_0002 含人名/att_0003 低置信）＋"
                         "F44 五反例 PDF（黑框文本层/隐藏文本/Info+XMP 元数据/"
                         "图像裁切区/alt）→ 附件目录（corpus_manifest.json 与"
                         " OCR 基础线面同式可直接登记）")
    ap.add_argument("--citations", metavar="DIR", default=None,
                    help="W2b-U03 F88 双集合黄金集模式：合成 codices 正式面"
                         "（codices_face/ 十文件＋合成 md 载体）＋adversarial 黄金集"
                         " f88_golden_set.json（可答 12＋应拒 15 全合成；内容手钉"
                         "确定性，seed 钉入清单与摘要——F88 验收调用钉 --seed 20261016）")
    ap.add_argument("--docx", metavar="DIR", default=None,
                    help="W2b-U12 F48 模式：全合成复杂 DOCX 两份（f48_doc_"
                         "complex.docx＝标题/跨run段落/表格/页眉脚/脚注＋重复句"
                         "负例素材；f48_doc_existing_revisions.docx＝前手 w:ins/"
                         "w:del 现存修订）＋docx_manifest.json（seed 钉定，F48 "
                         "验收调用钉 --seed 20261017；同 seed 逐字节相同）")
    ap.add_argument("--stamp-boxes", metavar="DIR", dest="stamp_boxes",
                    default=None,
                    help="W4-U35 F42 模式：合成印章/PS 痕迹金标盒语料两卷八页"
                         "（强红/浅淡/叠字印章＋红色 PS 贴块正例；净页/红字线"
                         "误报向/非红贴块漏报向/空白对照）——金标盒随清单，"
                         "F42 验收调用钉 --seed 20261020；同 seed 逐字节相同")
    ap.add_argument("--pages", type=int, default=5000, help="总页数（默认 5000，最少 24）")
    ap.add_argument("--seed", type=int, default=20261015)
    ap.add_argument("--out", default=os.path.join(tempfile.gettempdir(), "juscite-e12-corpus"),
                    help="输出根（默认 %%TEMP%%\\juscite-e12-corpus；体积产物不入 git）")
    ap.add_argument("--dpi", type=int, default=DEFAULT_DPI)
    ap.add_argument("--quota-table", type=float, default=DEFAULT_QUOTA["table"])
    ap.add_argument("--quota-rotated", type=float, default=DEFAULT_QUOTA["rotated"])
    ap.add_argument("--quota-duplicate", type=float, default=DEFAULT_QUOTA["duplicate"])
    ap.add_argument("--quota-blank", type=float, default=DEFAULT_QUOTA["blank"])
    ap.add_argument("--quota-lowconf", type=float, default=DEFAULT_QUOTA["lowconf"])
    ap.add_argument("--verify", metavar="DIR", help="复验既有语料目录（不重新生成）")
    ap.add_argument("--pdf-deep", choices=["sample", "all", "none"], default="sample",
                    help="--verify 时 PDF 像素深检范围")
    ap.add_argument("--selftest", action="store_true", help="小规模自检（生成/复验/同seed复算全链）")
    ap.add_argument("--selftest-pages", type=int, default=144)
    ap.add_argument("--keep", action="store_true", help="selftest 保留临时目录")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest(pages=max(24, args.selftest_pages), keep=args.keep)

    if args.attachments:
        out = Path(args.attachments)
        if out.exists() and any(out.iterdir()):
            eprint(f"[FAIL] 输出目录非空: {out}（请换空目录或先清理）")
            return 1
        r = build_attachments(out, args.seed, args.dpi)
        eprint(f"[att] 完成：{r['pages']} 附件页 / 反例 {r['counterexamples']} 例")
        eprint(f"[att] 清单 {out / 'corpus_manifest.json'}")
        eprint(f"[att] 摘要 {r['digest']}")
        return 0

    if args.citations:
        out = Path(args.citations)
        if out.exists() and any(out.iterdir()):
            eprint(f"[FAIL] 输出目录非空: {out}（请换空目录或先清理）")
            return 1
        r = build_citations(out, args.seed)
        eprint(f"[cit] 完成：可答 {r['answerable']} / 应拒 {r['refuse']} 条"
               f"（共同分母 {r['answerable'] + r['refuse']}）")
        eprint(f"[cit] 合成面 {out / CIT_FACE_DIR}")
        eprint(f"[cit] 黄金集 {out / GOLDEN_NAME}")
        eprint(f"[cit] 摘要 {r['digest']}")
        return 0

    if args.docx:
        out = Path(args.docx)
        if out.exists() and any(out.iterdir()):
            eprint(f"[FAIL] 输出目录非空: {out}（请换空目录或先清理）")
            return 1
        r = build_docx_corpus(out, args.seed)
        eprint(f"[docx] 完成：{len(r['manifest']['files'])} 份合成 DOCX"
               f"（seed {args.seed} 钉定）")
        eprint(f"[docx] 清单 {out / DOCX_MANIFEST}")
        eprint(f"[docx] 摘要 {r['digest']}")
        return 0

    if args.stamp_boxes:
        out = Path(args.stamp_boxes)
        if out.exists() and any(out.iterdir()):
            eprint(f"[FAIL] 输出目录非空: {out}（请换空目录或先清理）")
            return 1
        r = build_stamp_boxes(out, args.seed)
        eprint(f"[stamp] 完成：{r['pages']} 页两卷，金标盒 {r['gold_boxes']} "
               f"个（seed {args.seed} 钉定）")
        eprint(f"[stamp] 清单 {out / MANIFEST_NAME}")
        eprint(f"[stamp] 摘要 {r['digest']}")
        return 0

    if args.verify:
        out = Path(args.verify)
        if not out.is_dir():
            eprint(f"[FAIL] 目录不存在: {out}")
            return 1
        fails, checks = verify_corpus(out, pdf_deep=args.pdf_deep)
        for f in fails:
            eprint(f"  [FAIL] {f}")
        if fails:
            eprint(f"[verify] FAIL：{len(fails)} 项不合格（{checks} 项检查）")
            return 1
        eprint(f"[verify] PASS（{checks} 项检查，摘要文件与重算一致）")
        return 0

    if args.pages < 24:
        eprint("[FAIL] --pages 最少 24（保证卷结构与表组可规划）")
        return 1
    quota = {
        "table": args.quota_table, "rotated": args.quota_rotated, "duplicate": args.quota_duplicate,
        "blank": args.quota_blank, "lowconf": args.quota_lowconf,
    }
    if any(not (0.0 <= v < 0.5) for v in quota.values()) or sum(quota.values()) > 0.9:
        eprint(f"[FAIL] 配额非法：{quota}（各 0~0.5，合计 ≤0.9）")
        return 1
    out = Path(args.out)
    if out.exists() and any(out.iterdir()):
        eprint(f"[FAIL] 输出目录非空: {out}（请换空目录或先清理）")
        return 1
    r = build_corpus(out, args.pages, args.seed, args.dpi, quota)
    m = r["manifest"]
    eprint(f"[gen] 完成：{m['pages']} 页 / {len(m['documents'])} 卷 / 表 {len(m['tables'])} 组")
    eprint(f"[gen] 配额达成：{json.dumps(m['quota_achieved'], ensure_ascii=False, sort_keys=True)}")
    eprint(f"[gen] 清单 {out / MANIFEST_NAME}")
    eprint(f"[gen] 摘要 {r['digest']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
