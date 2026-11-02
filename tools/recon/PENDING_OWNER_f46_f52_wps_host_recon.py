# -*- coding: utf-8 -*-
"""F46/F52 WPS 宿主半边 recon（W2b-U36）——真 WPS COM 原生修订→部分接受/
拒绝→重载回流→CAS/version 回读＋索引失效。

对账对象：产品侧 implementation/python/wps_host.py（legal_entry 冻结方法组
wpshost.*：available/review/decide）＋消费链＝U14 redline.redline 产物红线
DOCX（消费契约 REDLINE_CONSUMERS 已声明 W2b-U16-wps-host）与 U12 edits
编辑产物→真 WPS COM（pywin32 DispatchEx KWPS.Application 独立进程，绝不
附着用户已开窗口；进程内串行限流）→部分接受/部分拒绝→重读盘上实际文件
字节→harness formal_decide accept resultBytesB64（source=user_accept∈F114
闭集·resultSource=host_result_bytes，U11 合同）→canonical 新 version；
未接受/全拒绝一字不动 canonical（F52 硬断言）→相关索引 basis 失效（E15
assessment 与 F70 引用 basis 的 stale 联动，消费侧既有面）→重载回流（再开
文档修订状态与账一致）。LibreOffice 26.8 仅渲染辅助核（U14 先例）不替代
WPS 主验证。

红线：Word 半边不验——F46-word/F52-word 保持 NOT_RUN（§6.1 裁决#4 WPS
先行 Word 后补，回收点 W2-S1/W4-S2）；语料全合成；oc28 零触碰。

实跑覆盖（PENDING_OWNER_F46_F52_wps_host_recon）：
  C01 harness 链头只读亲验（分支 w2b-u36@75ee7fd6＝w2b-u25 链头·master
  929d0802 零动·工作树干净）→ C02 语料确定性（e12 --docx seed 20261017
  两遍逐字节＋自建复杂件两遍逐字节）→ C03 宿主探针（真启动 KWPS 读版本
  即退）→ C04 U14 红线产物（register/replay/compare＋b64 取件双 sha 复验
  ＋对账双不变式在册）→ C05 harness 提案登记（canonical rev1 一字不动·
  pending）→ C06 索引在 rev1 基上建立（E15 assessment newInputRefs=
  mat@v1＋F70 引用解析 0 条）→ C07 WPS 原生修订可见（宿主 Revisions 计数
  ==OOXML 标记计数·作者/日期＝提案声明·删除/插入全文＝红线报告四组）
  → C08 宿主部分接受/拒绝（接受组 P0+脚注·拒绝组表格·留置组 P3 不动）
  → C09 重读实际文件（接受组新文入正文平文·拒绝组旧值回平文·留置组
  双侧标记仍在·宿主剩余计数==OOXML 标记）→ C10 formal bake（rev2
  source=user_accept resultSource=host_result_bytes·CAS 字节亲验·rev1
  append-only 逐字节回读）→ C11 索引失效联动（E15 旧账钉 v1 vs 新头 v2
  stale＋重评 ad-2 old=v1/new=v2 落账＋F70 引用解析 rev1 基 0 条→rev2
  平文 1 条＝basis 已陈旧）→ C12 重载回流（新会话再开结果文件·剩余修订
  与账一致）→ C13 LibreOffice 渲染辅助核（仅 exit 0＋关键平文呈现）
  → C14 F52 拒绝路径（全拒绝→formal_decide reject→canonical 一字不动
  逐字节＋无新版本行）→ C15 既有修订链（U12 edits 产物携 prior-author
  900/901 入 WPS·部分接受→bake rev2·重载一致）→ C16 自建复杂件宿主保真
  （域 fldSimple/fldChar·合并单元格·编号·页眉脚·脚注·前手修订全保）
  → C17 桥负向（未配置/未知方法/方法组冻结/空决定面/选择器命中零修订
  具名拒）。

W3-U35 根因注记（2026-10-20）：C16 曾败于宿主漂移（fldchar_in 12 vs
before 6·三跑同相在案）——确定性探针 evidence/E13/patch-chain/ 钉定：
同 build 宿主（KWPS 12.1.0.28802，与 W2b-U36 首验同一构建）open 即重算
DATE 域并归一化 fldSimple→fldChar（缓存 2026-10-16→当日形，指令/格式
开关逐字保真，其余 15 子句全过；隔离臂 Open+SaveAs2 零修订动作即复现）。
宿主域计算不在本面（W2b-U36 边界原文），故 C16 结果文本按语义合同
「指令＋结果文本俱在·表示形可换语义不得丢」收敛：DATE 结果必
YYYY-MM-DD 形、PAGE 结果必非空数字，不钉缓存字面值。

用法：
  python -X utf8 tools/recon/PENDING_OWNER_f46_f52_wps_host_recon.py \
      [--profile desktop] [--profile selfhost]

退出码：0 = 全部 profile RECON_OK；2 = RECON_FAIL；3 = 环境缺失
（WPS/pywin32/harness 根/LibreOffice 任一缺失按缺失面分：WPS 缺＝3）。
证据：docs/construction/evidence/F46/wps/＋evidence/F52/wps/ JSON＋MD。
"""
from __future__ import annotations

import argparse
import base64
import contextlib
import hashlib
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import uuid as _uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "python"))

import legal_entry  # noqa: E402
from bridge_errors import NotConnected  # noqa: E402
import document_redline as dr  # noqa: E402
import edits_protocol as ep  # noqa: E402
import wps_host  # noqa: E402
from citation_verifier import parse_citations  # noqa: E402

DEFAULT_HARNESS_ROOT = Path(
    r"D:\Codex\1.法律工作区\legal-harness工作区\legal-harness-repo"
    r"\.local\worktrees\w2b-u36")
DEFAULT_PG_DSN = "postgresql://lh_app:e08-synth-only@127.0.0.1:55432/legal_harness"
SEED = 20261017
CHAIN_HEAD = "75ee7fd6"
MASTER_TIP = "929d0802"

MATTER = "m-f46f52-recon"
SCOPE = {"kind": "matter", "matterId": MATTER}
MAT_A = "mat-f46-main"          # 链A：部分接受 bake
MAT_B = "mat-f52-reject"        # 链B：全拒绝 canonical 不动
MAT_C = "mat-f46-prior"         # 链C：既有修订（U12 edits 产物）

AUTHOR = "lvyin-redline"
DATE = "2026-10-16T00:00:00Z"

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = "{%s}" % W_NS
_CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

# ---- 合成语料语义锚（链A 提案；全部含唯一标记便于确定性分组） ----------
# 文本互不交叠（含片段级）：分组分类器要求每个宿主修订片段唯一归属。
P0_NEW = "依据《合成数据安全法》第三条，F46A 接受组句，本段替换完成。"
P3_NEW = "F46L 留置组句，宿主不得触碰此段。"
TABLE_OLD = "480,000.00"
TABLE_NEW = "1,234,567.89"
FN_NEW = "本脚注已替换为 F46F 接受组注脚，全合成语料。"


def b64(content: bytes) -> str:
    return base64.b64encode(content).decode("ascii")


def key(request_id: str) -> dict:
    return {"requestId": request_id, "targetId": None,
            "expectedRevision": None, "inputRefs": []}


def mat_ref(material_id: str, version) -> dict:
    return {"owner": "harness", "kind": "material", "id": material_id,
            "version": str(version), "matterId": MATTER}


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


# --------------------------------------------------------------------------
# OOXML 只读检查器（独立第二实现：不依赖 w:ins/w:del 生成方）
# --------------------------------------------------------------------------

def _load_parts(raw: bytes) -> dict:
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        return {info.filename: zf.read(info.filename)
                for info in zf.infolist()}


def _norm(text: str) -> str:
    return re.sub(r"[\r\n\x07]", "", text)


def revision_marks(parts: dict) -> dict:
    """OOXML 修订标记统计＋留置文本（w:ins/w:del 逐部件）。"""
    marks = {"ins": 0, "del": 0, "ins_text": [], "del_text": []}
    for name in ("word/document.xml", "word/footnotes.xml"):
        if name not in parts:
            continue
        root = ET.fromstring(parts[name])
        for el in root.iter(W + "ins"):
            marks["ins"] += 1
            marks["ins_text"].append(_norm("".join(
                t.text or "" for t in el.iter(W + "t"))))
        for el in root.iter(W + "del"):
            marks["del"] += 1
            marks["del_text"].append(_norm("".join(
                t.text or "" for t in el.iter(W + "delText"))))
    return marks


def plain_text(parts: dict, part: str = "word/document.xml") -> str:
    """现行平文（修订标记外）；ins 的新文不算平文（尚未接受）。"""
    root = ET.fromstring(parts[part])
    inside = set()

    def _walk(el):
        for child in el:
            if child.tag in (W + "ins", W + "del"):
                inside.add(id(child))
            _walk(child)
    _walk(root)
    out = []

    def _collect(el):
        for child in el:
            if id(child) in inside:
                continue
            if child.tag == W + "t":
                out.append(child.text or "")
            _collect(child)
    _collect(root)
    return _norm("".join(out))


def accepted_text(parts: dict, part: str = "word/document.xml") -> str:
    """接受语义全文（平文＋已接受 ins 不含＝仅平文；再并入留置 ins 新文
    供「接受全部后的应然」对照——本 recon 用于验证接受组语义）。"""
    root = ET.fromstring(parts[part])
    out = []

    def _collect(el):
        for child in el:
            if child.tag == W + "del":
                continue
            if child.tag == W + "t":
                out.append(child.text or "")
            _collect(child)
    _collect(root)
    return _norm("".join(out))


def _norm_space(text: str) -> str:
    return " ".join((text or "").split())


def field_instr_result(doc_xml: bytes) -> tuple[list, list]:
    """域状态机只读清点（document order）：返回（指令列表，结果文本列表）。

    fldSimple 与 fldChar 复杂域双形态统一归一：fldSimple 指令取 w:instr
    属性、结果取元素内 w:t；复杂域指令＝begin..separate 的 instrText 连接、
    结果＝separate..end 的 w:t 连接。指令折叠空白（W3-U35：宿主 open 即
    重算域结果为表示形漂移，指令面才是语义合同）。
    """
    root = ET.fromstring(doc_xml)
    instrs: list = []
    results: list = []
    state = "outside"
    instr_buf: list | None = None
    result_buf: list | None = None
    for el in root.iter():
        if el.tag == W + "fldSimple":
            instrs.append(_norm_space(el.get(W + "instr")))
            results.append(_norm("".join(
                t.text or "" for t in el.iter(W + "t"))))
        elif el.tag == W + "fldChar":
            kind = el.get(W + "fldCharType")
            if kind == "begin":
                instr_buf, result_buf = [], []
                state = "instr"
            elif kind == "separate":
                state = "result"
            elif kind == "end":
                instrs.append(_norm_space("".join(instr_buf or [])))
                results.append(_norm("".join(result_buf or [])))
                instr_buf = result_buf = None
                state = "outside"
        elif el.tag == W + "instrText" and state == "instr" \
                and instr_buf is not None:
            instr_buf.append(el.text or "")
        elif el.tag == W + "t" and state == "result" \
                and result_buf is not None:
            result_buf.append(el.text or "")
    return instrs, results


# --------------------------------------------------------------------------
# 自建复杂件（域/合并单元格/编号/页眉脚/脚注/前手修订——全合成确定性）
# --------------------------------------------------------------------------

PRIOR_INS_TEXT = "（前手插入的合成句F46P，作者=prior-author）"
PRIOR_DEL_TEXT = "（前手删除的合成句F46Q，应随拒绝回平文）"
D_BODY_SENTENCES = [
    "本件为 W2b-U36 自建复杂合成文书，含域、合并单元格与编号列表。",
    "第二段引用《合成贸易促进法》第二条作为合成标记锚。",
    "第三段为普通正文，与前手修订相邻。",
]
XML_DECL = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'


def _esc(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


def _d_paragraph(text: str) -> str:
    return f"<w:p><w:r><w:t>{_esc(text)}</w:t></w:r></w:p>"


def build_complex_docx() -> bytes:
    """确定性自建复杂 DOCX（无时钟、无随机；同输入字节级同输出）。"""
    body = []
    body.append('<w:p><w:pPr><w:jc w:val="center"/></w:pPr>'
                '<w:r><w:rPr><w:b/></w:rPr><w:t>'
                "自建复杂文书（W2b-U36 全合成）</w:t></w:r></w:p>")
    # 段1：域（fldSimple DATE ＋ fldChar PAGE 两形态）
    body.append(
        "<w:p>"
        '<w:fldSimple w:instr=" DATE \\@ &quot;YYYY-MM-DD&quot; ">'
        "<w:r><w:t>2026-10-16</w:t></w:r></w:fldSimple>"
        "<w:r><w:t> 当日页码：</w:t></w:r>"
        '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
        '<w:r><w:instrText xml:space="preserve"> PAGE </w:instrText></w:r>'
        '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
        "<w:r><w:t>1</w:t></w:r>"
        '<w:r><w:fldChar w:fldCharType="end"/></w:r>'
        "</w:p>")
    # 段2-4：正文（第 3 段前手插入修订 900——修订标记必须在段内，宿主
    # 才认；e12 前手件 body 级 w:ins 对宿主不可见，故本面自建）
    body.append(_d_paragraph(D_BODY_SENTENCES[0]))
    body.append(_d_paragraph(D_BODY_SENTENCES[1]))
    body.append(
        '<w:p><w:ins w:id="900" w:author="prior-author"'
        ' w:date="2026-09-01T00:00:00Z">'
        f"<w:r><w:t>{_esc(PRIOR_INS_TEXT)}</w:t></w:r></w:ins></w:p>")
    body.append(_d_paragraph(D_BODY_SENTENCES[2]))
    # 段5：前手删除修订 901（段内 delText）
    body.append(
        '<w:p><w:del w:id="901" w:author="prior-author"'
        ' w:date="2026-09-02T00:00:00Z">'
        '<w:r><w:delText xml:space="preserve">'
        f"{_esc(PRIOR_DEL_TEXT)}</w:delText></w:r></w:del></w:p>")
    # 编号列表（numbering numId=1 两项）
    for item in ("编号项一（合成）", "编号项二（合成）"):
        body.append('<w:p><w:pPr><w:numPr><w:ilvl w:val="0"/>'
                    '<w:numId w:val="1"/></w:numPr></w:pPr>'
                    f"<w:r><w:t>{_esc(item)}</w:t></w:r></w:p>")
    # 合并单元格表（首行 2+3 列 gridSpan=2 合并）
    body.append("<w:tbl><w:tblGrid>"
                '<w:gridCol w:w="2800"/><w:gridCol w:w="2800"/>'
                '<w:gridCol w:w="2800"/></w:tblGrid>'
                "<w:tr>"
                '<w:tc><w:tcPr><w:tcW w:w="2800" w:type="dxa"/></w:tcPr>'
                "<w:p><w:r><w:t>表头甲</w:t></w:r></w:p></w:tc>"
                '<w:tc><w:tcPr><w:tcW w:w="5600" w:type="dxa"/>'
                '<w:gridSpan w:val="2"/></w:tcPr>'
                "<w:p><w:r><w:t>表头乙丙（合并）</w:t></w:r></w:p></w:tc>"
                "</w:tr><w:tr>"
                + "".join(
                    '<w:tc><w:tcPr><w:tcW w:w="2800" w:type="dxa"/></w:tcPr>'
                    f"<w:p><w:r><w:t>{_esc(cell)}</w:t></w:r></w:p></w:tc>"
                    for cell in ("数据一", "数据二", "数据三"))
        + "</w:tr></w:tbl>")
    # 脚注引用段
    body.append('<w:p><w:r><w:t>本段带脚注引用锚。</w:t></w:r>'
                '<w:r><w:footnoteReference w:id="1"/></w:r></w:p>')
    body.append('<w:sectPr><w:headerReference w:type="default"'
                ' r:id="rId3"/><w:footerReference w:type="default"'
                ' r:id="rId4"/><w:pgSz w:w="11906" w:h="16838"/>'
                '<w:pgMar w:top="1440" w:right="1800" w:bottom="1440"'
                ' w:left="1800" w:header="851" w:footer="992"'
                ' w:gutter="0"/></w:sectPr>')
    document = (XML_DECL + f'<w:document xmlns:w="{W_NS}"'
                + f' xmlns:r="{_R_NS}"><w:body>'
                + "".join(body) + "</w:body></w:document>")
    main = "application/vnd.openxmlformats-officedocument.wordprocessingml."
    numbering = (XML_DECL + f'<w:numbering xmlns:w="{W_NS}">'
                 '<w:abstractNum w:abstractNumId="10">'
                 '<w:lvl w:ilvl="0"><w:start w:val="1"/>'
                 '<w:numFmt w:val="decimal"/><w:lvlText w:val="%1."/>'
                 '<w:lvlJc w:val="left"/></w:lvl></w:abstractNum>'
                 '<w:num w:numId="1"><w:abstractNumId w:val="10"/></w:num>'
                 "</w:numbering>")
    footnotes = (XML_DECL + f'<w:footnotes xmlns:w="{W_NS}">'
                 + f' xmlns:r="{_R_NS}">'
                 '<w:footnote w:type="separator" w:id="-1"><w:p/></w:footnote>'
                 '<w:footnote w:type="continuationSeparator" w:id="0">'
                 "<w:p/></w:footnote>"
                 '<w:footnote w:id="1"><w:p><w:r><w:t>'
                 "自建复杂件脚注（W2b-U36 全合成）"
                 "</w:t></w:r></w:p></w:footnote></w:footnotes>")
    header = (XML_DECL + f'<w:hdr xmlns:w="{W_NS}" xmlns:r="{_R_NS}">'
              '<w:p><w:pPr><w:jc w:val="center"/></w:pPr>'
              "<w:r><w:t>W2b-U36 页眉（合成）</w:t></w:r></w:p></w:hdr>")
    footer = (XML_DECL + f'<w:ftr xmlns:w="{W_NS}" xmlns:r="{_R_NS}">'
              '<w:p><w:pPr><w:jc w:val="center"/></w:pPr>'
              "<w:r><w:t>W2b-U36 页脚（合成）</w:t></w:r></w:p></w:ftr>")
    styles = (XML_DECL + f'<w:styles xmlns:w="{W_NS}">'
              '<w:style w:type="paragraph" w:default="1" w:styleId="Normal">'
              '<w:name w:val="Normal"/></w:style></w:styles>')
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        f'<Types xmlns="{_CT_NS}">'
        '<Default Extension="rels" ContentType="application/vnd.'
        'openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        f'<Override PartName="/word/document.xml" ContentType="{main}'
        'document.main+xml"/>'
        f'<Override PartName="/word/styles.xml" ContentType="{main}styles+xml"/>'
        f'<Override PartName="/word/numbering.xml" ContentType="{main}'
        'numbering+xml"/>'
        f'<Override PartName="/word/footnotes.xml" ContentType="{main}'
        'footnotes+xml"/>'
        f'<Override PartName="/word/header1.xml" ContentType="{main}header+xml"/>'
        f'<Override PartName="/word/footer1.xml" ContentType="{main}footer+xml"/>'
        "</Types>")
    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        f'<Relationships xmlns="{_REL_NS}">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/'
        'officeDocument/2006/relationships/officeDocument"'
        ' Target="word/document.xml"/></Relationships>')
    base = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"
    doc_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        f'<Relationships xmlns="{_REL_NS}">'
        f'<Relationship Id="rId1" Type="{base}styles" Target="styles.xml"/>'
        f'<Relationship Id="rId2" Type="{base}footnotes"'
        ' Target="footnotes.xml"/>'
        f'<Relationship Id="rId3" Type="{base}header" Target="header1.xml"/>'
        f'<Relationship Id="rId4" Type="{base}footer" Target="footer1.xml"/>'
        f'<Relationship Id="rId5" Type="{base}numbering"'
        ' Target="numbering.xml"/>'
        "</Relationships>")
    parts = [
        ("[Content_Types].xml", content_types),
        ("_rels/.rels", root_rels),
        ("word/document.xml", document),
        ("word/_rels/document.xml.rels", doc_rels),
        ("word/styles.xml", styles),
        ("word/numbering.xml", numbering),
        ("word/footnotes.xml", footnotes),
        ("word/header1.xml", header),
        ("word/footer1.xml", footer),
    ]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, payload in parts:
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, payload.encode("utf-8"))
    return buffer.getvalue()


# --------------------------------------------------------------------------
# 分组分类器：把宿主修订文本唯一归入（旧文∪新文）组
# --------------------------------------------------------------------------

def classify_revisions(revisions: list, groups: dict) -> dict:
    """把宿主修订按文本归属唯一分组；多组命中/零命中即拒（fail-loud）。

    groups: {组名: {"texts": [旧全文, 新全文]}}
    返回 {组名: [选择器…]}（type＋text_equals 精确选择器）。
    """
    selectors = {name: [] for name in groups}
    for rev in revisions:
        text = _norm(rev["text"])
        hits = [name for name, spec in groups.items()
                if any(text and text in anchor for anchor in spec["texts"])]
        if len(hits) != 1:
            raise AssertionError(
                f"revision_uniquely_classifiable_failed:"
                f"{rev['type_name']}:{len(hits)}")
        selectors[hits[0]].append(
            {"type": rev["type_name"], "mode": "equals", "text": rev["text"]})
    return selectors


# --------------------------------------------------------------------------
# Recon 驱动
# --------------------------------------------------------------------------

class Recon:
    def __init__(self, harness_root: Path, state_root: Path,
                 product_config: dict):
        self.harness_root = harness_root
        self.state_root = state_root
        self.product_config = product_config
        self.checks: list[dict] = []

    def step(self, name, ok, feature="F46", **facts):
        entry = {"check": name, "feature": feature,
                 "status": "PASS" if ok else "FAIL", **facts}
        self.checks.append(entry)
        print(json.dumps(entry, ensure_ascii=False), flush=True)
        if not ok:
            raise AssertionError(name)

    def expect_error(self, name, call, code_part,
                     error=(NotConnected, ValueError), feature="F46"):
        try:
            call()
        except error as exc:
            self.step(name, code_part in str(exc), feature=feature,
                      code=str(exc))
            return str(exc)
        raise AssertionError(name + ": no typed error raised")

    def git(self, root: Path, *args: str) -> str:
        return subprocess.check_output(
            ["git", "-C", str(root), *args], text=True,
            encoding="utf-8", errors="replace").strip()

    def branch_checks(self):
        branch = self.git(self.harness_root, "rev-parse",
                          "--abbrev-ref", "HEAD")
        head = self.git(self.harness_root, "rev-parse", "HEAD")
        base = self.git(self.harness_root, "merge-base", "HEAD", "w2b-u25")
        master = self.git(self.harness_root, "rev-parse", "master")
        self.step("c01_harness_branch", branch == "w2b-u36", branch=branch)
        self.step("c01_harness_chain_head_readonly",
                  head.startswith(CHAIN_HEAD) and base.startswith(CHAIN_HEAD),
                  head=head[:12], base=base[:12])
        self.step("c01_harness_master_untouched",
                  master.startswith(MASTER_TIP), master=master[:12])
        dirty = self.git(self.harness_root, "status", "--porcelain")
        self.step("c01_harness_worktree_clean", dirty == "",
                  dirty=dirty[:200])

    # -- 产品面直呼（wpshost.*；profile 无关同一条链） ---------------------
    def wps(self, method: str, args: dict) -> dict:
        return legal_entry.call(method, args, self.product_config)

    def redline(self, method: str, args: dict) -> dict:
        return dr.redline_call(method, args, {"redline_state_root": str(
            self.state_root / "redline")})

    # ------------------------------------------------------------------
    def common_flow(self, profile: str, call_harness, harness_ok,
                    query_harness):
        # ---- C02 合成语料确定性
        corpus_a = Path(tempfile.mkdtemp(prefix="juscite-u36-corpus-a-"))
        corpus_b = Path(tempfile.mkdtemp(prefix="juscite-u36-corpus-b-"))
        for out in (corpus_a, corpus_b):
            code = subprocess.call(
                [sys.executable, "-X", "utf8",
                 str(REPO_ROOT / "tools" / "e12_corpus_gen.py"),
                 "--docx", str(out), "--seed", str(SEED)])
            if code != 0:
                raise AssertionError("generator_failed:" + str(out))
        manifest = json.loads(
            (corpus_a / "docx_manifest.json").read_text(encoding="utf-8"))
        byte_identical = all(
            (corpus_a / item["name"]).read_bytes()
            == (corpus_b / item["name"]).read_bytes()
            for item in manifest["files"])
        sha_match = all(
            sha256_bytes((corpus_a / item["name"]).read_bytes())
            == item["sha256"] for item in manifest["files"])
        self.step("c02_corpus_deterministic",
                  byte_identical and sha_match and manifest["seed"] == SEED,
                  files=[f["name"] for f in manifest["files"]])
        complex_doc = (corpus_a / "f48_doc_complex.docx").read_bytes()
        prior_doc = (corpus_a / "f48_doc_existing_revisions.docx").read_bytes()
        paragraphs = manifest["texts"]["paragraphs"]

        def body_index(pos: int) -> int:
            """manifest 段位→正文段索引（0=标题；重复句占两段）。"""
            extra = sum(1 for p in paragraphs[:pos] if p["repeat"])
            return 1 + pos + extra

        p0_old = paragraphs[0]["text"]
        p3_old = paragraphs[4]["text"]
        idx_p0, idx_p3 = body_index(0), body_index(4)
        table_old = TABLE_OLD
        fn_old = manifest["texts"]["footnote_text"]
        self_built = build_complex_docx()
        self.step("c02_selfbuilt_complex_deterministic",
                  self_built == build_complex_docx(),
                  sha256=sha256_bytes(self_built)[:16],
                  parts=sorted(_load_parts(self_built)))

        # ---- C03 宿主探针（真启动即退）
        probe = self.wps("wpshost.available", {})
        self.step("c03_wps_host_probe",
                  probe.get("installed") is True
                  and probe["host"]["version"] is not None,
                  host=probe.get("host"), feature="F46")

        # ---- C04 U14 红线产物（消费契约取件）
        reg = self.redline("redline.register", {
            "document_id": "d-u36", "docx_b64": b64(complex_doc),
            "matter_id": MATTER})
        # 正文段索引含标题（0=标题）；接受组=manifest 位0、留置组=位4
        # （两段皆非重复句，锚文本片段互不交叠——分组分类器唯一归属）
        ops = [
            {"op": "body.replace_text", "index": idx_p0, "text": P0_NEW},
            {"op": "body.replace_text", "index": idx_p3, "text": P3_NEW},
            {"op": "table.cell_text", "table": 0, "row": 1, "col": 1,
             "text": TABLE_NEW},
            {"op": "footnote.replace_text", "id": 1, "text": FN_NEW},
        ]
        rep = self.redline("redline.replay", {
            "document_id": "d-u36",
            "proposal": {"ops": ops, "author": AUTHOR,
                         "authored_utc": DATE}})
        cmp = self.redline("redline.compare", {
            "document_id": "d-u36", "proposal_id": rep["proposal_id"]})
        fetched = self.redline("redline.redline", {
            "redline_id": cmp["redline_id"]})
        redline_bytes = base64.b64decode(fetched["docx_b64"])
        report_again = self.redline("redline.report", {
            "redline_id": cmp["redline_id"]})
        marks_in_product = revision_marks(_load_parts(redline_bytes))
        self.step("c04_redline_product_contract",
                  fetched["sha256"] == cmp["redline"]["sha256"]
                  == report_again["redline"]["sha256"]
                  and sha256_bytes(redline_bytes) == fetched["sha256"]
                  and cmp["reconciliation"] == {
                      "accept_all_equals_replay": True,
                      "reject_all_equals_baseline": True,
                      "readback_content_complete": True}
                  and "W2b-U16-wps-host" in fetched["consumers"]
                  and reg["baseline"]["sha256"]
                  == sha256_bytes(complex_doc),
                  redline_id=cmp["redline_id"],
                  revision_groups=cmp["revisions"]["count"],
                  ooxml_marks=marks_in_product["ins"]
                  + marks_in_product["del"])

        # ---- C05 harness 提案登记（canonical 一字不动）
        call_harness("harness.register_material", {
            "actor_id": "recon-lawyer", "scope": SCOPE, "key": key("reg-a"),
            "material": {"id": MAT_A, "kind": "office",
                         "title": "民事起诉状（U36 对账合成·主链）",
                         "bytesB64": b64(complex_doc)}})
        quotes = [
            {"text": p0_old, "reason": "接受组正文替换",
             "sourceRef": mat_ref(MAT_A, 1)},
            {"text": table_old, "reason": "拒绝组表单元格改",
             "sourceRef": mat_ref(MAT_A, 1)},
        ]
        propose = call_harness("harness.formal_propose", {
            "actor_id": "recon-assistant", "scope": SCOPE, "key": key("fp-1"),
            "proposal": {"proposalId": "fp-1", "materialId": MAT_A,
                         "baseRevision": 1, "bytesB64": b64(redline_bytes),
                         "channel": "machine", "author": AUTHOR,
                         "quotes": quotes, "note": "U36 全合成·WPS 宿主链"}})
        listing = call_harness("harness.formal_proposal_list", {
            "scope": SCOPE, "material_id": MAT_A})
        self.step("c05_harness_proposal_pending_canonical_untouched",
                  harness_ok
                  and propose["proposal"]["state"] == "pending"
                  and listing["canonical"]["revision"] == 1
                  and listing["canonical"]["sha256"]
                  == sha256_bytes(complex_doc)
                  and listing["proposals"][0]["state"] == "pending",
                  canonical=listing["canonical"]["revision"])

        # ---- C06 索引建立在 rev1 基上（E15 assessment＋F70 引用解析）
        ad1 = call_harness("harness.assessment_delta_record", {
            "actor_id": "recon-lawyer", "scope": SCOPE, "key": key("ad-1"),
            "delta": {"deltaId": "ad-1", "changeReason": "material",
                      "oldInputRefs": [mat_ref(MAT_A, 1)],
                      "newInputRefs": [mat_ref(MAT_A, 1)],
                      "items": [{"kind": "fact",
                                 "ref": {"owner": "harness", "kind": "fact",
                                         "id": "fact-u36-anchor",
                                         "version": "1",
                                         "matterId": MATTER},
                                 "outcome": "maintained",
                                 "reason": "U36 合成：基线事实索引锚",
                                 "basisRefs": [mat_ref(MAT_A, 1)]}]}})
        citations_rev1 = parse_citations(
            plain_text(_load_parts(complex_doc)))
        self.step("c06_indexes_on_rev1_basis",
                  ad1["delta"]["deltaId"] == "ad-1"
                  and citations_rev1 == [],
                  citation_count=len(citations_rev1),
                  pinned_version="1", feature="F52")

        # ---- C07 WPS 原生修订可见
        review = self.wps("wpshost.review", {"docx_b64": b64(redline_bytes)})
        host_count = review["revision_count"]
        authors = {rev["author"] for rev in review["revisions"]}
        dates_raw = [rev["date"] for rev in review["revisions"]]
        del_join = "".join(_norm(rev["text"]) for rev in review["revisions"]
                           if rev["type"] == 2)
        ins_join = "".join(_norm(rev["text"]) for rev in review["revisions"]
                           if rev["type"] == 1)
        report_del_join = "".join(
            str(r.get("deleted_text") or "")
            for r in cmp["revisions"]["items"])
        report_ins_join = "".join(
            str(r.get("inserted_text") or "")
            for r in cmp["revisions"]["items"])
        self.step("c07_wps_native_revisions_visible",
                  host_count == marks_in_product["ins"]
                  + marks_in_product["del"]
                  and host_count > 0
                  and authors == {AUTHOR}
                  and all(d.startswith(DATE[:10]) for d in dates_raw)
                  and del_join.replace(" ", "")
                  == report_del_join.replace(" ", "")
                  and ins_join.replace(" ", "")
                  == report_ins_join.replace(" ", ""),
                  host_count=host_count,
                  ooxml_marks=marks_in_product["ins"]
                  + marks_in_product["del"],
                  authors=sorted(authors))

        # ---- C08 宿主部分接受/拒绝（分组选择器）
        groups = {
            "accept_p0": {"texts": [p0_old, P0_NEW]},
            "reject_table": {"texts": [table_old, TABLE_NEW]},
            "accept_fn": {"texts": [fn_old, FN_NEW]},
            "leave_p3": {"texts": [p3_old, P3_NEW]},
        }
        selectors = classify_revisions(review["revisions"], groups)
        decide = self.wps("wpshost.decide", {
            "docx_b64": b64(redline_bytes),
            "accept": selectors["accept_p0"] + selectors["accept_fn"],
            "reject": selectors["reject_table"]})
        result_bytes = base64.b64decode(decide["result_docx_b64"])
        self.step("c08_wps_partial_accept_reject",
                  len(decide["acted_accept"]) > 0
                  and len(decide["acted_reject"]) > 0
                  and decide["remaining_count"] > 0
                  and len(selectors["leave_p3"]) > 0,
                  accepted=len(decide["acted_accept"]),
                  rejected=len(decide["acted_reject"]),
                  remaining=decide["remaining_count"],
                  leave_group_marks=len(selectors["leave_p3"]))

        # ---- C09 重读实际文件（部分状态语义）
        parts = _load_parts(result_bytes)
        marks = revision_marks(parts)
        plain = plain_text(parts)
        fn_plain = plain_text(parts, "word/footnotes.xml")
        forward = accepted_text(parts)
        ins_all = "".join(marks["ins_text"])
        del_all = "".join(marks["del_text"])
        self.step("c09_reread_actual_file_partial_state",
                  P0_NEW in plain and FN_NEW in fn_plain
                  and fn_old not in fn_plain
                  and TABLE_NEW not in plain and table_old in plain
                  and table_old not in del_all
                  and "F46L" in ins_all
                  and p3_old not in plain
                  and marks["ins"] + marks["del"]
                  == decide["remaining_count"],
                  accepted_group_plain=P0_NEW in plain,
                  rejected_group_old_plain=table_old in plain,
                  leave_group_marked="F46L" in ins_all,
                  remaining_marks=marks["ins"] + marks["del"],
                  host_remaining=decide["remaining_count"])

        # ---- C10 formal bake：CAS/version 回读
        decided = call_harness("harness.formal_decide", {
            "actor_id": "recon-lawyer", "scope": SCOPE, "key": key("dec-1"),
            "decision": {"proposalId": "fp-1", "action": "accept",
                         "reasonRef": {"owner": "harness", "kind": "reason",
                                       "id": "r-u36", "version": "1",
                                       "matterId": MATTER},
                         "receiptRef": {"owner": "harness", "kind": "receipt",
                                        "id": "rc-u36", "version": "1",
                                        "matterId": MATTER},
                         "resultBytesB64": decide["result_docx_b64"]}})
        baked = call_harness("harness.read_material", {
            "scope": SCOPE, "material_id": MAT_A, "revision": 2})
        rev1 = call_harness("harness.read_material", {
            "scope": SCOPE, "material_id": MAT_A, "revision": 1})
        self.step("c10_formal_bake_user_accept",
                  harness_ok
                  and decided["canonical"]["revision"] == 2
                  and base64.b64decode(baked["bytesB64"]) == result_bytes
                  and baked["source"] == "user_accept"
                  and baked["resultSource"] == "host_result_bytes"
                  and baked["sha256"] == sha256_bytes(result_bytes)
                  and base64.b64decode(rev1["bytesB64"]) == complex_doc,
                  canonical=decided["canonical"]["revision"],
                  source=baked["source"],
                  result_source=baked["resultSource"], feature="F52")

        # ---- C11 索引失效联动（E15 stale＋重评＋F70 引用 basis）
        listing2 = call_harness("harness.formal_proposal_list", {
            "scope": SCOPE, "material_id": MAT_A})
        head_revision = listing2["canonical"]["revision"]
        citations_rev2 = parse_citations(plain_text(parts))
        ad2 = call_harness("harness.assessment_delta_record", {
            "actor_id": "recon-lawyer", "scope": SCOPE, "key": key("ad-2"),
            "delta": {"deltaId": "ad-2", "changeReason": "material",
                      "oldInputRefs": [mat_ref(MAT_A, 1)],
                      "newInputRefs": [mat_ref(MAT_A, 2)],
                      "items": [{"kind": "fact",
                                 "ref": {"owner": "harness", "kind": "fact",
                                         "id": "fact-u36-anchor",
                                         "version": "1",
                                         "matterId": MATTER},
                                 "outcome": "may_change",
                                 "reason": "U36 合成：canonical 已由宿主"
                                           "部分接受推进到 rev2，rev1 基"
                                           "索引陈旧须重评",
                                 "basisRefs": [mat_ref(MAT_A, 2)]}]}})
        ad2_read = call_harness("harness.assessment_delta_read", {
            "scope": SCOPE, "delta_id": "ad-2"})
        self.step("c11_index_basis_stale_linkage",
                  head_revision == 2
                  and citations_rev1 == [] and len(citations_rev2) == 1
                  and citations_rev2[0]["title"] == "合成数据安全法"
                  and ad2["delta"]["deltaId"] == "ad-2"
                  and ad2_read["delta"]["delta"]["newInputRefs"][0]
                  ["version"] == "2"
                  and ad2_read["delta"]["delta"]["oldInputRefs"][0]
                  ["version"] == "1",
                  rev1_parse=len(citations_rev1),
                  rev2_parse=len(citations_rev2),
                  head=head_revision, feature="F52")

        # ---- C12 重载回流（新会话再开实际结果文件）
        reload_view = self.wps("wpshost.review", {
            "docx_b64": decide["result_docx_b64"]})
        remaining_in_account = sorted(
            (rev["type"], _norm(rev["text"]))
            for rev in decide["remaining_revisions"])
        remaining_in_reload = sorted(
            (rev["type"], _norm(rev["text"]))
            for rev in reload_view["revisions"])
        self.step("c12_reload_revision_state_matches_ledger",
                  reload_view["revision_count"] == decide["remaining_count"]
                  and remaining_in_account == remaining_in_reload
                  and reload_view["source_sha256"] == decide["result_sha256"],
                  reloaded=reload_view["revision_count"], feature="F52")

        # ---- C13 LibreOffice 渲染辅助核（不替代 WPS 主验证）
        lo = self._render_pdf(result_bytes)
        pdf_text = self._pdf_text(lo) if lo else ""
        self.step("c13_libreoffice_render_auxiliary",
                  lo is not None and P0_NEW[:12] in pdf_text,
                  pdf=lo.name if lo else None)

        # ---- C14 F52 拒绝路径：全拒绝→canonical 一字不动
        call_harness("harness.register_material", {
            "actor_id": "recon-lawyer", "scope": SCOPE, "key": key("reg-b"),
            "material": {"id": MAT_B, "kind": "office",
                         "title": "民事起诉状（U36 对账合成·拒绝链）",
                         "bytesB64": b64(complex_doc)}})
        call_harness("harness.formal_propose", {
            "actor_id": "recon-assistant", "scope": SCOPE, "key": key("fp-2"),
            "proposal": {"proposalId": "fp-2", "materialId": MAT_B,
                         "baseRevision": 1, "bytesB64": b64(redline_bytes),
                         "channel": "machine", "author": AUTHOR,
                         "quotes": quotes, "note": "U36 拒绝链"}})
        review_b = self.wps("wpshost.review", {"docx_b64": b64(redline_bytes)})
        reject_all = [
            {"type": rev["type_name"], "mode": "equals", "text": rev["text"]}
            for rev in review_b["revisions"]]
        decide_b = self.wps("wpshost.decide", {
            "docx_b64": b64(redline_bytes), "accept": [], "reject": reject_all})
        parts_b = _load_parts(base64.b64decode(decide_b["result_docx_b64"]))
        marks_b = revision_marks(parts_b)
        plain_b = plain_text(parts_b)
        baseline_plain = plain_text(_load_parts(complex_doc))
        decided_b = call_harness("harness.formal_decide", {
            "actor_id": "recon-lawyer", "scope": SCOPE, "key": key("dec-2"),
            "decision": {"proposalId": "fp-2", "action": "reject",
                         "reasonRef": {"owner": "harness", "kind": "reason",
                                       "id": "r-u36b", "version": "1",
                                       "matterId": MATTER},
                         "receiptRef": {"owner": "harness", "kind": "receipt",
                                        "id": "rc-u36b", "version": "1",
                                        "matterId": MATTER}}})
        listing_b = call_harness("harness.formal_proposal_list", {
            "scope": SCOPE, "material_id": MAT_B})
        rev1_b = call_harness("harness.read_material", {
            "scope": SCOPE, "material_id": MAT_B, "revision": 1})
        revisions_b = query_harness(
            "SELECT COUNT(*) AS n FROM material_candidates"
            " WHERE matter_id=? AND material_id=?",
            (MATTER, MAT_B))[0]["n"] if harness_ok else 1
        self.step("c14_f52_reject_all_canonical_untouched",
                  harness_ok
                  and marks_b["ins"] == 0 and marks_b["del"] == 0
                  and plain_b.replace(" ", "") == baseline_plain.replace(" ", "")
                  and decided_b["proposal"]["state"] == "rejected"
                  and listing_b["canonical"]["revision"] == 1
                  and listing_b["canonical"]["sha256"]
                  == sha256_bytes(complex_doc)
                  and base64.b64decode(rev1_b["bytesB64"]) == complex_doc
                  and revisions_b == 1,
                  host_remaining=decide_b["remaining_count"],
                  canonical=listing_b["canonical"]["revision"],
                  version_rows=revisions_b, feature="F52")

        # ---- C15 既有修订链（U12 edits 产物携 prior-author 入 WPS）
        # 载体＝自建复杂件（前手 900/901 在段内＝宿主可见形；e12 前手件
        # 的 body 级修订标记对宿主不可见，如实不用）
        edits_cfg = {"edits_state_root": str(self.state_root / "edits")}
        legal_entry.call("edits.register", {
            "document_id": "d-prior", "bytesB64": b64(self_built)}, edits_cfg)
        stream = ("<edits>"
                  '<edit id="p1" op="replace"><old>' + D_BODY_SENTENCES[1]
                  + "</old><new>F46E 后到修订句（替换前手段落）。</new>"
                  "<reason>U36 既有修订链</reason></edit>"
                  "</edits>")
        legal_entry.call("edits.stream_open", {
            "document_id": "d-prior", "stream_id": "sp"}, edits_cfg)
        legal_entry.call("edits.stream_push", {
            "document_id": "d-prior", "stream_id": "sp", "chunk": stream},
            edits_cfg)
        legal_entry.call("edits.stream_close", {
            "document_id": "d-prior", "stream_id": "sp"}, edits_cfg)
        legal_entry.call("edits.locate", {
            "document_id": "d-prior", "stream_id": "sp"}, edits_cfg)
        apply_c = legal_entry.call("edits.apply", {
            "document_id": "d-prior", "stream_id": "sp", "card_ids": ["p1"],
            "revision_author": "lvyin-edits",
            "revision_date": DATE}, edits_cfg)
        working = (self.state_root / "edits" / "edits-protocol" / "d-prior"
                   / "working.docx")
        working_bytes = working.read_bytes()
        new_ids = apply_c["cards"][0]["revision_ids"]
        review_c = self.wps("wpshost.review", {"docx_b64": b64(working_bytes)})
        host_authors_c = {rev["author"] for rev in review_c["revisions"]}
        call_harness("harness.register_material", {
            "actor_id": "recon-lawyer", "scope": SCOPE, "key": key("reg-c"),
            "material": {"id": MAT_C, "kind": "office",
                         "title": "合成修订前文书（U36 既有修订链）",
                         "bytesB64": b64(working_bytes)}})
        call_harness("harness.formal_propose", {
            "actor_id": "recon-assistant", "scope": SCOPE, "key": key("fp-3"),
            "proposal": {"proposalId": "fp-3", "materialId": MAT_C,
                         "baseRevision": 1, "bytesB64": b64(working_bytes),
                         "channel": "machine", "author": "lvyin-edits",
                         "quotes": [{"text": D_BODY_SENTENCES[1],
                                     "reason": "U36 既有修订链",
                                     "sourceRef": mat_ref(MAT_C, 1)}],
                         "note": "U36 全合成·既有修订链"}})
        # 接受前手插入（900）＋接受后到修订；拒绝前手删除（901）
        accept_c, reject_c = [], []
        for rev in review_c["revisions"]:
            text = _norm(rev["text"])
            if text == _norm(PRIOR_INS_TEXT) or rev["author"] == \
                    "lvyin-edits":
                accept_c.append({"type": rev["type_name"], "mode": "equals",
                                 "text": rev["text"]})
            elif text and text in PRIOR_DEL_TEXT:
                reject_c.append({"type": rev["type_name"], "mode": "equals",
                                 "text": rev["text"]})
        decide_c = self.wps("wpshost.decide", {
            "docx_b64": b64(working_bytes), "accept": accept_c,
            "reject": reject_c})
        result_c = base64.b64decode(decide_c["result_docx_b64"])
        parts_c = _load_parts(result_c)
        plain_c = plain_text(parts_c)
        marks_c = revision_marks(parts_c)
        decided_c = call_harness("harness.formal_decide", {
            "actor_id": "recon-lawyer", "scope": SCOPE, "key": key("dec-3"),
            "decision": {"proposalId": "fp-3", "action": "accept",
                         "reasonRef": {"owner": "harness", "kind": "reason",
                                       "id": "r-u36c", "version": "1",
                                       "matterId": MATTER},
                         "receiptRef": {"owner": "harness", "kind": "receipt",
                                        "id": "rc-u36c", "version": "1",
                                        "matterId": MATTER},
                         "resultBytesB64": decide_c["result_docx_b64"]}})
        baked_c = call_harness("harness.read_material", {
            "scope": SCOPE, "material_id": MAT_C, "revision": 2})
        reload_c = self.wps("wpshost.review", {
            "docx_b64": decide_c["result_docx_b64"]})
        self.step("c15_existing_revisions_chain_bake",
                  host_authors_c == {"prior-author", "lvyin-edits"}
                  and all(int(v) > 901 for v in new_ids)
                  and _norm(PRIOR_INS_TEXT) in plain_c
                  and _norm(PRIOR_DEL_TEXT) in plain_c
                  and "F46E 后到修订句" in plain_c
                  and marks_c["ins"] + marks_c["del"]
                  == decide_c["remaining_count"]
                  and decided_c["canonical"]["revision"] == 2
                  and baked_c["source"] == "user_accept"
                  and base64.b64decode(baked_c["bytesB64"]) == result_c
                  and reload_c["revision_count"] == decide_c["remaining_count"],
                  host_authors=sorted(host_authors_c),
                  new_ids=new_ids,
                  remaining=decide_c["remaining_count"])

        # ---- C16 自建复杂件宿主保真（域/合并单元格/编号/页眉脚/前手修订）
        sb_parts = _load_parts(self_built)
        sb_marks = revision_marks(sb_parts)
        fldsimple_before = sb_parts["word/document.xml"].count(b"fldSimple")
        fldchar_before = sb_parts["word/document.xml"].count(b"fldChar")
        review_d = self.wps("wpshost.review", {"docx_b64": b64(self_built)})
        accept_d, reject_d = [], []
        for rev in review_d["revisions"]:
            text = _norm(rev["text"])
            if text and text in PRIOR_INS_TEXT:
                accept_d.append({"type": rev["type_name"], "mode": "equals",
                                 "text": rev["text"]})
            elif text and text in PRIOR_DEL_TEXT:
                reject_d.append({"type": rev["type_name"], "mode": "equals",
                                 "text": rev["text"]})
        decide_d = self.wps("wpshost.decide", {
            "docx_b64": b64(self_built), "accept": accept_d,
            "reject": reject_d})
        result_d = base64.b64decode(decide_d["result_docx_b64"])
        parts_d = _load_parts(result_d)
        plain_d = plain_text(parts_d)
        marks_d = revision_marks(parts_d)
        doc_xml_d = parts_d["word/document.xml"]
        instrs_d, results_d = field_instr_result(doc_xml_d)
        # 域保真＝语义面（指令＋结果文本俱在）：WPS 归一化 fldSimple→
        # fldChar 复杂域形，表示形可换、语义不得丢（如实按语义断言）。
        # W3-U35 根因在案：宿主 open 即重算 DATE 域（缓存 2026-10-16→
        # 当日形·指令/格式开关逐字保真·探针 evidence/E13/patch-chain/），
        # 故结果文本按「俱在＋格式形态」断言（DATE 结果必 YYYY-MM-DD 形、
        # PAGE 结果必非空数字），不钉缓存字面值（宿主域计算不在本面，
        # W2b-U36 边界原文）。
        self.step("c16_selfbuilt_complex_host_fidelity",
                  review_d["revision_count"] == sb_marks["ins"]
                  + sb_marks["del"]
                  and doc_xml_d.count(b"instrText") >= 2
                  and b"DATE" in doc_xml_d and b"PAGE" in doc_xml_d
                  and sorted(instrs_d) == sorted([
                      'DATE \\@ "YYYY-MM-DD"', "PAGE"])
                  and len(results_d) == 2
                  and re.fullmatch(r"\d{4}-\d{2}-\d{2}",
                                   results_d[0]) is not None
                  and re.fullmatch(r"\d+", results_d[1]) is not None
                  and "当日页码" in plain_d
                  and b"gridSpan" in doc_xml_d
                  and b"numId" in doc_xml_d
                  and "word/header1.xml" in parts_d
                  and "word/footer1.xml" in parts_d
                  and "word/footnotes.xml" in parts_d
                  and "word/numbering.xml" in parts_d
                  and _norm(PRIOR_INS_TEXT) in plain_d
                  and _norm(PRIOR_DEL_TEXT) in plain_d
                  and marks_d["ins"] + marks_d["del"]
                  == decide_d["remaining_count"]
                  and decide_d["remaining_count"] == 0,
                  fields=dict(
                      instrtext=doc_xml_d.count(b"instrText"),
                      fldsimple_in=doc_xml_d.count(b"fldSimple"),
                      fldsimple_before=fldsimple_before,
                      fldchar_in=doc_xml_d.count(b"fldChar"),
                      fldchar_before=fldchar_before,
                      instr_after=instrs_d,
                      results_after=results_d),
                  remaining=decide_d["remaining_count"])

        # ---- C17 桥负向（含真宿主负向：命中零修订具名拒）
        self.expect_error("c17_bridge_not_configured", lambda: legal_entry.call(
            "wpshost.review", {"docx_b64": b64(self_built)}, {}),
            "wps46_state_root_not_configured")
        self.expect_error("c17_bridge_unknown_method", lambda: legal_entry.call(
            "wpshost.bake", {}, self.product_config),
            "method_not_connected")
        self.step("c17_method_group_frozen",
                  legal_entry.WPS_HOST_METHODS == frozenset({
                      "wpshost.available", "wpshost.review",
                      "wpshost.decide"}))
        self.expect_error("c17_decide_empty_named_refusal", lambda: self.wps(
            "wpshost.decide", {"docx_b64": b64(self_built),
                               "accept": [], "reject": []}),
            "wps46_decide_empty")
        self.expect_error(
            "c17_no_revision_matched_named_refusal", lambda: self.wps(
                "wpshost.decide", {"docx_b64": b64(self_built),
                                   "accept": [{"type": "insert",
                                               "mode": "equals",
                                               "text": "文档中不存在的句子"}],
                                   "reject": []}),
            "wps46_no_revision_matched")

    # -- LibreOffice 渲染辅助（U14 先例：仅核可开＋关键平文呈现） ---------
    def _render_pdf(self, docx_bytes: bytes):
        soffice = _find_soffice()
        if soffice is None:
            return None
        out_dir = self.state_root / "lo-render"
        out_dir.mkdir(parents=True, exist_ok=True)
        staging = out_dir / ("render-" + _uuid.uuid4().hex[:8])
        staging.mkdir()
        try:
            (staging / "input.docx").write_bytes(docx_bytes)
            profile = (self.state_root / "lo-profile").resolve()
            profile.mkdir(parents=True, exist_ok=True)
            argv = [str(soffice), "--headless", "--norestore",
                    "--nolockcheck",
                    "-env:UserInstallation=" + profile.as_uri(),
                    "--convert-to", "pdf", "--outdir",
                    str(staging), str(staging / "input.docx")]
            proc = subprocess.run(argv, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace",
                                  timeout=300)
            pdf = staging / "input.pdf"
            if proc.returncode != 0 or not pdf.is_file():
                return None
            return pdf
        except Exception:
            return None

    @staticmethod
    def _pdf_text(pdf_path: Path) -> str:
        try:
            from pypdf import PdfReader
        except ImportError:
            try:
                from PyPDF2 import PdfReader  # type: ignore
            except ImportError:
                return ""
        try:
            reader = PdfReader(str(pdf_path))
            return "".join(page.extract_text() or "" for page in reader.pages)
        except Exception:
            return ""


def wps_host_set():  # pragma: no cover - kept for external assertion parity
    return frozenset({"wpshost.available", "wpshost.review",
                      "wpshost.decide"})


def _find_soffice() -> Path | None:
    for candidate in (r"C:\Program Files\LibreOffice\program\soffice.com",
                      r"C:\Program Files\LibreOffice\program\soffice.exe"):
        path = Path(candidate)
        if path.is_file():
            return path
    return None


# --------------------------------------------------------------------------
# profile 驱动
# --------------------------------------------------------------------------

HARNESS_METHODS_USED = (
    "harness.register_material", "harness.read_material",
    "harness.formal_propose", "harness.formal_decide",
    "harness.formal_proposal_list",
    "harness.assessment_delta_record", "harness.assessment_delta_read",
)


def run_profile(profile: str, harness_root: Path, pg_dsn: str) -> tuple:
    """跑一个 profile；返回 (recon, exit_code)。

    分支亲验先于业务流；业务流任何异常保留已完成的 checks 再以 code=2
    返回（证据如实记 FAIL，不静默丢半程）。
    """
    temporary = tempfile.TemporaryDirectory(prefix="juscite-u36-" + profile)
    state_root = Path(temporary.name) / "state"
    state_root.mkdir(parents=True)
    product_config = {
        "wps_host_state_root": str(state_root / "wps-host"),
    }
    recon = Recon(harness_root, state_root, product_config)
    try:
        recon.branch_checks()
        if profile == "desktop":
            registration = Path(temporary.name) / "service-local.json"
            registration.write_text(json.dumps(
                {"url": "http://127.0.0.1:1",
                 "password": "synthetic-recon"}), encoding="utf-8")
            product_config.update({
                "harness_public_entry": str(
                    harness_root / "tools/workflow-tools/harness"
                    "/public_entry.py"),
                "harness_target": "opencode",
                "harness_state_root": str(state_root),
                "harness_service_registration": str(registration),
                "harness_timeout": 120,
            })
            for path in (str(harness_root / "src"),
                         str(harness_root / "tools/workflow-tools")):
                if path not in sys.path:
                    sys.path.insert(0, path)
            from legal_harness.state.matter_store import MatterStore
            store = MatterStore(state_root)
            store.create_matter(MATTER, "cas://u36-recon")

            def call_harness(method, args):
                return legal_entry.call(method, args, product_config)

            def query(sql, params):
                import sqlite3
                with contextlib.closing(store._connect()) as connection:
                    connection.row_factory = sqlite3.Row
                    rows = connection.execute(sql, params).fetchall()
                return [dict(row) for row in rows]

            print("[profile desktop] SQLite via product bridge subprocess",
                  flush=True)
            recon.common_flow("desktop", call_harness=call_harness,
                              harness_ok=True, query_harness=query)
        else:
            for path in (str(harness_root / "src"),
                         str(harness_root / "tools/workflow-tools"),
                         str(harness_root), str(harness_root / "tests")):
                if path not in sys.path:
                    sys.path.insert(0, path)
            from legal_harness.business.provider_registry import (
                resolve_provider_method,
            )
            from legal_harness.business.units import HarnessUnits
            from legal_harness.state.pg_store import PgMatterStore
            store = PgMatterStore(
                Path(temporary.name) / "state", dsn=pg_dsn,
                schema="u36_" + _uuid.uuid4().hex[:12])
            units = HarnessUnits(store)
            bound = {name: resolve_provider_method(name, units)
                     for name in HARNESS_METHODS_USED}
            store.create_matter(MATTER, "cas://u36-recon")

            def call_harness(method, args):
                return bound[method](**args)

            def query(sql, params):
                with contextlib.closing(store._connect()) as connection:
                    rows = connection.execute(sql, params).fetchall()
                return [dict(row) for row in rows]

            print("[profile selfhost] PgMatterStore direct (lh-pg-e08)",
                  flush=True)
            recon.common_flow("selfhost", call_harness=call_harness,
                              harness_ok=True, query_harness=query)
            store.destroy()
        return recon, 0
    except Exception as error:  # noqa: BLE001 - keep partial checks
        print(f"RECON_FAIL[{profile}]: {error}", flush=True)
        recon.checks.append({"check": "recon_driver", "feature": "F46",
                             "status": "FAIL",
                             "error": str(error)[:400]})
        return recon, 2


def write_evidence(recon: Recon, profile: str, started: str, code: int,
                   profiles_run: list) -> list[Path]:
    out = []
    finished = datetime.now(timezone.utc).isoformat()
    for feature in ("F46", "F52"):
        feature_checks = [c for c in recon.checks if c["feature"] == feature]
        if code != 0 and not any(c["status"] != "PASS"
                                 for c in feature_checks):
            feature_checks = feature_checks + [
                c for c in recon.checks if c["check"] == "recon_driver"]
        evidence_dir = REPO_ROOT / "docs" / "construction" / "evidence" \
            / feature / "wps"
        evidence_dir.mkdir(parents=True, exist_ok=True)
        summary = {
            "schema": "juscite-f46-f52-wps-host-recon/1",
            "unit": "W2b-U36", "feature": feature, "host": "wps",
            "profile": profile, "profiles_run": profiles_run,
            "verdict": "RECON_OK" if code == 0 else "RECON_FAIL",
            "started_at": started, "finished_at": finished,
            "harness_worktree": str(recon.harness_root),
            "harness_branch": "w2b-u36",
            "harness_base": "w2b-u25@" + CHAIN_HEAD + " (chain head, "
                            "read-only consumption)",
            "corpus": "tools/e12_corpus_gen.py --docx seed 20261017 "
                      "+ self-built complex docx (fields/merged table/"
                      "numbering/header-footer/footnote/prior revisions)",
            "word_side": "NOT_RUN (kept for W2-S1/W4-S2 per ruling #4)",
            "checks": feature_checks,
            "check_count": len(feature_checks),
            "failed": [c["check"] for c in feature_checks
                       if c["status"] != "PASS"],
        }
        payload = json.dumps(summary, ensure_ascii=False, indent=1)
        (evidence_dir / ("f46_f52_wps_host_recon." + profile
                         + ".json")).write_text(payload + "\n",
                                                encoding="utf-8")
        # 末位 profile 另写无后缀主档（验收命令出口＝证据主档）
        if profile == profiles_run[-1]:
            (evidence_dir / "f46_f52_wps_host_recon.json").write_text(
                payload + "\n", encoding="utf-8")
        lines = [f"# {feature} WPS 宿主半边 recon（wps·{profile}）",
                 "",
                 f"- unit: W2b-U36 · feature: {feature} · host: wps"
                 f" · profile: {profile}",
                 f"- verdict: **{summary['verdict']}**"
                 f" ({len(feature_checks)} checks, exit {code})",
                 f"- harness: `{recon.harness_root}` @ branch w2b-u36"
                 f"（链头 w2b-u25@{CHAIN_HEAD} 只读消费；master "
                 f"{MASTER_TIP} 零动）",
                 "- 语料：e12_corpus_gen --docx seed 20261017＋自建复杂件"
                 "（域/合并单元格/编号/页眉脚/脚注/前手修订）",
                 f"- Word 半边：NOT_RUN（§6.1 裁决#4，回收点 W2-S1/W4-S2）",
                 f"- profiles: {', '.join(profiles_run)}",
                 f"- started: {started} · finished: {finished}",
                 "",
                 "| # | check | status |",
                 "|---|---|---|"]
        for index, check in enumerate(feature_checks, 1):
            lines.append(f"| {index} | {check['check']}"
                         f" | {check['status']} |")
        lines += ["", "全部合成材料；真 WPS COM 会话（KWPS.Application "
                  "独立进程·串行限流·用毕即退）。"]
        (evidence_dir / ("f46_f52_wps_host_recon." + profile
                         + ".md")).write_text("\n".join(lines) + "\n",
                                              encoding="utf-8")
        if profile == profiles_run[-1]:
            (evidence_dir / "f46_f52_wps_host_recon.md").write_text(
                "\n".join(lines) + "\n", encoding="utf-8")
        out.append(evidence_dir)
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", action="append",
                        choices=["desktop", "selfhost"])
    parser.add_argument("--harness-root", type=Path,
                        default=DEFAULT_HARNESS_ROOT)
    parser.add_argument("--pg-dsn", default=DEFAULT_PG_DSN)
    args = parser.parse_args()
    profiles = args.profile or ["desktop"]
    if not (args.harness_root / "tools/workflow-tools/harness"
            "/public_entry.py").exists():
        print("RECON_BLOCKED: harness root missing public_entry:",
              args.harness_root)
        return 3
    try:
        import pythoncom  # noqa: F401
        import win32com.client  # noqa: F401
    except ImportError:
        print("RECON_BLOCKED: pywin32 missing (WPS host face unavailable)")
        return 3
    probe = wps_host.wps_available()
    if not probe.get("installed"):
        print("RECON_BLOCKED: KWPS.Application unavailable")
        return 3
    print("[host] WPS probe:", json.dumps(probe, ensure_ascii=False),
          flush=True)
    failures = 0
    for profile in profiles:
        started = datetime.now(timezone.utc).isoformat()
        recon, code = run_profile(profile, args.harness_root, args.pg_dsn)
        evidence_dirs = write_evidence(recon, profile, started, code,
                                       profiles)
        verdict = "RECON_OK" if code == 0 else "RECON_FAIL"
        print(f"[{profile}] {verdict} ({len(recon.checks)} checks,"
              f" exit {code}) evidence={[str(p) for p in evidence_dirs]}",
              flush=True)
        if code != 0:
            failures += 1
    return 0 if failures == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
