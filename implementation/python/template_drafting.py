"""F56 文书模板起草（模板库＋变量填充＋访谈式三段）——产品侧
document-adapter 公开面（W4-U38；06:F56 owner=product+harness，B4；
python_entry P04 binding=templates.register/render/save_answers）。

义务 06:F56 断言：「真实模板变量/问询装配可回读；缺模板/变量不发明；
版本和授权保留」。保留历史要求（06 col26）：确定性「变量-问询-装配」
比 LLM 直出可靠——本面零模型零网络零随机，全程确定性解析（正则＋
xml.etree 状态无关遍历）。

访谈式三段（每段产物在账可回读，缺件 typed 拒、绝不发明值）：
  段① 变量问询 templates.interview：模板（ harness 正式材料，rev 钉定
       CAS 随读必验）→ 变量清单确定性提取（Word 内容控件 w:sdt 的
       w:tag＝「kind:变量名」、w:alias＝问询话术）→ 问题集（kind 闭集
       text/date/amount/number；alias 缺省回落变量名）。
  段② 填充 templates.save_answers：答案表对照问题集确定性校验（缺变量/
       多变量/类型不符 一律具名拒；金额十进制串禁浮点、日期真日历）→
       append-only 答案账（钉定模板 sha256+版本）。
  段③ 装配 templates.render：答案表→确定性填充（控件 sdtPr/sdtContent
       外零改动）→结构/视觉具名检查（E13 模板结构视觉段承接：
       content control 外结构、style/numbering/section、外链、隐私、
       占位残留、独立 lxml 检查器——硬维不过不出产物）→ 经 U11 合同
       入 harness 正式材料版本链：add_material_revision
       (source=assistant_edit∈F114 闭集)＋formal_propose
       (channel=machine, author=lvyin-templates, quotes=占位定位集)。

模板库 templates.register（版本＋授权保留）：外置模板经 harness 正式
文件链消费（05§8「外置模板由Harness正式文件链消费」）——v1＝
harness.register_material（upload，律师自备外部文件语义），vN+1＝
add_material_revision（缺省 upload＝用户侧字节语义，F114 合同原文）；
产品侧版本账 append-only（versions/<seq>.json 不删不改），每版本钉
sha256＋授权元数据（license/source/notice，登记时声明、逐字保留，
缺失＝f56_license_required 拒——保留授权不是事后补写）。

纪律（与 F45 docx_edit/F54 conversion 同族同基线）：
- 确定性：零时钟入产物（zip 时间戳钉定 1980-01-01；版本/答案/装配账
  全 seq 序＋内容寻址，manifest 无时间字段）——同输入两跑同字节；
  装配字节＝纯函数(模板字节, 答案表)，跨 profile（desktop SQLite 桥 /
  selfhost PgMatterStore 直连）逐字节相等。
- append-only：模板版本/答案表/装配产物三账只追加（同 id 同内容幂等
  重放、同 id 异内容具名冲突）；harness 版本链 rev1 模板字节永久可
  回读（read_material 随读必验 sha）。
- fail-closed：未配置状态根/harness 桥＝NOT_CONNECTED；缺模板
  （f56_template_not_found）/缺变量（f56_answers_missing_variables，
  拒答清单具名、不发明值）/答案表与模板版本错钉
  （f56_answers_template_mismatch）/结构硬维不过
  （f56_structure_check_failed:<维>）/独立检查器不过
  （f56_checker_failed:<维>）一律 typed error（f56_*），错误码不携
  材料内容；author 过 F53 策略面（templates 通道绑定 lvyin-templates，
  伪造律师名＝f53_author_impersonation）。

边界（如实，不伪称）：
- v1 变量载体＝正文内容控件（word/document.xml body 内 w:sdt）；页眉/
  页脚等其它部件出现带 tag 控件＝登记即 f56_control_outside_body 具名
  拒（不静默丢、不假装支持）；无 tag 内容控件＝非变量载体，结构保真
  原样保留（tagless_controls 具名清点）。
- kind 闭集 text/date/amount/number 为本单设计裁量（tag 前缀承载，
  模板内自描述——确定性提取的全部信息都在模板文件里，无需第二映射），
  入账于台账行；choice 等它类不前造。
- 答案值＝单行字符串（控制字符/换行具名拒）；金额 kind＝十进制/千位
  逗号串（Decimal 语义，浮点 JSON 数值＝f56_answer_not_string 拒），
  本面零金额算术（算术属 JC P01 面）。
- 律师接受/拒绝决定面＝harness formal_decide（U11 已 VERIFIED）不在
  本面；真机 UI 面不前造（公开面回读同族先例）。
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
import threading
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

SCHEMA = "juscite-f56-template-drafting/1"
TEMPLATE_SCHEMA = "juscite-f56-template/1"
ANSWERS_SCHEMA = "juscite-f56-answers/1"
RENDERING_SCHEMA = "juscite-f56-rendering/1"
STATE_SUBDIR = "templates"
# 06:F56 装配产物＝机器生成提案字节：F47 通道闭集 machine；F114 闭集
# 来源 assistant_edit（与 F45 通道①同一 U11 合同登记形态）。
CHANNEL = "machine"
ASSISTANT_SOURCE = "assistant_edit"
# F53 作者声明闭集（templates 通道绑定，W2b-U49 策略面扩展随本单）。
AUTHOR_CHANNEL = "templates"

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"

# 变量 kind 闭集（tag 前缀；本单设计裁量，见模块头边界节）。
KINDS = ("text", "date", "amount", "number")
TAG_RE = re.compile(r"^(text|date|amount|number):([a-z][a-z0-9_]{0,63})$")
# amount＝十进制/千位逗号串（Decimal 语义；浮点与算式拒不进答案账）。
_AMOUNT_RE = re.compile(r"^-?(\d{1,3}(,\d{3})+|\d+)(\.\d+)?$")
_NUMBER_RE = re.compile(r"^-?\d+(\.\d+)?$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

_MATTER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_REQUEST_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")

# E13 模板结构视觉段归一化哨兵（两侧同形替换后比较——正文比较永不出现
# 该串；哨兵只存在于比较用归一化形，不落任何产物）。
_FILL_MARKER = "@@F56-FILLED:%s@@"

_ZIP_DATE = (1980, 1, 1, 0, 0, 0)
_XML_DECL = (b'<?xml version="1.0" encoding="UTF-8" '
             b'standalone="yes"?>\n')

_LOCK = threading.Lock()

# 结构/视觉具名检查的硬维（任一不过＝不出产物）。外链/隐私两维＝具名
# 报告维（信息性——本面不改 rels/core.xml，字节级恒等由部件恒等维覆盖）。
STRUCTURE_HARD_DIMS = (
    "parts_identical_except_document",
    "outside_controls_unchanged",
    "controls_all_filled",
    "placeholder_residue_zero",
    "styles_part_identical",
    "numbering_part_identical",
    "sections_preserved",
    "document_rels_identical",
)


class TemplateDraftingError(ValueError):
    """Typed F56 face failure; str() is a code, never material content."""

    error_code = "f56_invalid"


def _fail(code: str) -> TemplateDraftingError:
    return TemplateDraftingError(code)


def _q(tag: str) -> str:
    return f"{{{W_NS}}}{tag}"


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def content_digest(docx_bytes: bytes) -> str:
    """部件级内容摘要（zip 容器时间戳不参与）——跨次装配可复现锚。"""
    with zipfile.ZipFile(io.BytesIO(docx_bytes)) as zf:
        parts = [f"{info.filename}:{_sha256(zf.read(info.filename))}"
                 for info in zf.infolist()]
    return _sha256("\n".join(sorted(parts)).encode("utf-8"))


def _atomic_write(path: Path, payload: str) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# 模板解析：变量清单确定性提取（正则＋ET 遍历，零猜测）
# ---------------------------------------------------------------------------

def _control_tag(sdt) -> str | None:
    pr = sdt.find(_q("sdtPr"))
    if pr is None:
        return None
    node = pr.find(_q("tag"))
    if node is None:
        return None
    value = node.get(_q("val"))
    return value if value else None


def _control_alias(sdt) -> str | None:
    pr = sdt.find(_q("sdtPr"))
    if pr is None:
        return None
    node = pr.find(_q("alias"))
    if node is None:
        return None
    value = node.get(_q("val"))
    return value if value else None


def _control_text(sdt) -> str:
    return "".join(node.text or "" for node in sdt.iter(_q("t")))


def parse_template(docx_bytes: bytes) -> dict:
    """模板结构模型：document.xml 解析＋带 tag 控件清单（文档序）。

    登记级校验全在此一道闸：非 DOCX/非 XML 拒；零带 tag 控件拒
    （f56_template_no_variables——模板无变量不成模板，不发明变量）；
    tag 形不合法（f56_template_tag_invalid）/同名异 kind
    （f56_template_tag_conflict）/占位文本空（f56_template_placeholder_
    empty——提案 quote 需非空定位文本）/正文外部件带 tag 控件
    （f56_control_outside_body）一律具名拒。"""
    try:
        zf = zipfile.ZipFile(io.BytesIO(docx_bytes))
    except (zipfile.BadZipFile, OSError) as exc:
        raise _fail("f56_template_unreadable:" + type(exc).__name__) from None
    with zf:
        names = zf.namelist()
        if "word/document.xml" not in names:
            raise _fail("f56_template_not_docx")
        raw = zf.read("word/document.xml")
        try:
            root = ET.fromstring(raw)
        except ET.ParseError as exc:
            raise _fail(
                "f56_template_xml_invalid:" + type(exc).__name__) from None
        _register_prefixes(raw)

        # 正文外部件带 tag 控件＝不支持的变量位置，登记即拒（不静默丢）。
        for name in names:
            if not name.endswith(".xml") or name == "word/document.xml":
                continue
            try:
                part_root = ET.fromstring(zf.read(name))
            except ET.ParseError:
                continue  # 非正文 XML 部件不解析不判（部件级恒等检查覆盖）
            for node in part_root.iter(_q("sdt")):
                if _control_tag(node) is not None:
                    raise _fail("f56_control_outside_body:" + name)

        controls: list[dict] = []
        tagless = 0
        for sdt in root.iter(_q("sdt")):
            tag = _control_tag(sdt)
            if tag is None:
                tagless += 1
                continue
            match = TAG_RE.match(tag)
            if match is None:
                raise _fail("f56_template_tag_invalid:" + tag)
            placeholder = _control_text(sdt)
            if not placeholder.strip():
                raise _fail("f56_template_placeholder_empty:" + tag)
            controls.append({"tag": tag, "kind": match.group(1),
                             "name": match.group(2),
                             "alias": _control_alias(sdt),
                             "placeholder": placeholder})
        if not controls:
            raise _fail("f56_template_no_variables")

        variables: list[dict] = []
        by_name: dict[str, dict] = {}
        for control in controls:
            known = by_name.get(control["name"])
            if known is None:
                known = {"name": control["name"], "kind": control["kind"],
                         "question": control["alias"] or control["name"],
                         "placeholder": control["placeholder"],
                         "controls": 0}
                by_name[control["name"]] = known
                variables.append(known)
            elif known["kind"] != control["kind"]:
                raise _fail("f56_template_tag_conflict:" + control["tag"])
            known["controls"] += 1
        sections = len(list(root.iter(_q("sectPr"))))
        return {"root": root, "raw_document": raw, "controls": controls,
                "variables": variables, "tagless_controls": tagless,
                "sections": sections}


def _register_prefixes(raw_document_xml: bytes) -> None:
    """原稿根元素声明的 xmlns 前缀注册进 ET 序列化器（F45 同款）。"""
    match = re.search(rb'<[A-Za-z0-9_:][^>]*>', raw_document_xml)
    if match is None:
        return
    for prefix, uri in re.findall(
            rb'xmlns:([A-Za-z0-9_.-]+)="([^"]+)"', match.group(0)):
        try:
            ET.register_namespace(prefix.decode("ascii"), uri.decode("ascii"))
        except (UnicodeDecodeError, ValueError):
            continue


# ---------------------------------------------------------------------------
# 确定性填充＋结构/视觉具名检查（E13 模板结构视觉段承接）
# ---------------------------------------------------------------------------

def fill_template(template_bytes: bytes, variables: list[dict],
                  answers: dict[str, str]) -> bytes:
    """确定性装配：仅替换带 tag 控件的 sdtContent 内运行（sdtPr 与控件
    外结构零改动）；同输入两跑同字节。answers 必须已过 save_answers
    校验（此处按变量名取值，缺值＝KeyError 不可达——render 前置校验）。"""
    model = parse_template(template_bytes)
    root = model["root"]
    unmatched = {v["name"] for v in variables}
    for sdt in root.iter(_q("sdt")):
        tag = _control_tag(sdt)
        if tag is None:
            continue
        match = TAG_RE.match(tag)
        name = match.group(2)
        value = answers[name]
        unmatched.discard(name)
        content = sdt.find(_q("sdtContent"))
        if content is None:
            raise _fail("f56_control_content_missing:" + tag)
        first_rpr = None
        for run in content.iter(_q("r")):
            first_rpr = run.find(_q("rPr"))
            break
        for child in list(content):
            content.remove(child)
        run = ET.SubElement(content, _q("r"))
        if first_rpr is not None:
            run.append(ET.fromstring(ET.tostring(first_rpr)))
        text = ET.SubElement(run, _q("t"))
        text.set(XML_SPACE, "preserve")
        text.text = value
    if unmatched:
        raise _fail("f56_control_missing_for_variable:"
                    + ",".join(sorted(unmatched)))
    document_xml = _XML_DECL + ET.tostring(root, encoding="utf-8",
                                           xml_declaration=False)

    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(template_bytes)) as src, \
            zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for name in src.namelist():
            payload = (document_xml if name == "word/document.xml"
                       else src.read(name))
            info = zipfile.ZipInfo(name, date_time=_ZIP_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            dst.writestr(info, payload)
    return out.getvalue()


def _normalized_document(docx_bytes: bytes) -> bytes:
    """比较用归一化形：带 tag 控件的 sdtContent 整体替换为规范单运行
    （哨兵文本）——两侧同形后逐字节比较，判定「控件外结构＋控件身份
    （sdtPr/tag/alias）不变」。哨兵形不落任何产物。"""
    model = parse_template(docx_bytes)
    root = model["root"]
    for sdt in root.iter(_q("sdt")):
        tag = _control_tag(sdt)
        if tag is None:
            continue
        match = TAG_RE.match(tag)
        content = sdt.find(_q("sdtContent"))
        for child in list(content):
            content.remove(child)
        run = ET.SubElement(content, _q("r"))
        text = ET.SubElement(run, _q("t"))
        text.set(XML_SPACE, "preserve")
        text.text = _FILL_MARKER % match.group(2)
    return ET.tostring(root, encoding="utf-8", xml_declaration=False)


def structure_report(template_bytes: bytes, assembled_bytes: bytes,
                     variables: list[dict],
                     answers: dict[str, str]) -> dict:
    """结构/视觉具名检查（E13 模板结构视觉段承接；全部具名可回读）。

    硬维（不过＝装配拒）：部件恒等（document.xml 外逐字节）、控件外
    结构恒等（归一化形逐字节）、控件全填充、占位残留为零、styles/
    numbering 部件恒等、section 数守恒、document.xml.rels 恒等（外链
    关系不被装配改写）。具名信息维：外链计数、隐私元数据（core.xml
    creator/lastModifiedBy 具名呈现）。"""
    with zipfile.ZipFile(io.BytesIO(template_bytes)) as src, \
            zipfile.ZipFile(io.BytesIO(assembled_bytes)) as dst:
        src_names = src.namelist()
        dst_names = dst.namelist()
        parts_ok = src_names == dst_names and all(
            src.read(name) == dst.read(name)
            for name in src_names if name != "word/document.xml")
        styles_ok = ("word/styles.xml" not in src_names
                     or src.read("word/styles.xml")
                     == dst.read("word/styles.xml"))
        numbering_ok = ("word/numbering.xml" not in src_names
                        or src.read("word/numbering.xml")
                        == dst.read("word/numbering.xml"))
        rels_ok = ("word/_rels/document.xml.rels" not in src_names
                   or src.read("word/_rels/document.xml.rels")
                   == dst.read("word/_rels/document.xml.rels"))
        rels_xml = (src.read("word/_rels/document.xml.rels")
                    if "word/_rels/document.xml.rels" in src_names else b"")
    external_links = 0
    if rels_xml:
        rels_root = ET.fromstring(rels_xml)
        for rel in rels_root:
            if rel.get("TargetMode") == "External":
                external_links += 1

    outside_ok = (_normalized_document(template_bytes)
                  == _normalized_document(assembled_bytes))

    asm_model = parse_template(assembled_bytes)
    asm_text_by_name: dict[str, list[str]] = {}
    for sdt in asm_model["root"].iter(_q("sdt")):
        tag = _control_tag(sdt)
        if tag is None:
            continue
        name = TAG_RE.match(tag).group(2)
        asm_text_by_name.setdefault(name, []).append(_control_text(sdt))
    controls_ok = all(
        asm_text_by_name.get(v["name"]) == [answers[v["name"]]] * v["controls"]
        for v in variables)
    filled_full_text = "".join(
        node.text or "" for node in asm_model["root"].iter(_q("t")))
    residue = [v["placeholder"] for v in variables
               if v["placeholder"] in filled_full_text]
    residue_ok = not residue

    privacy = _privacy_metadata(template_bytes)

    report = {
        "named_dims": list(STRUCTURE_HARD_DIMS) + ["external_links",
                                                   "privacy"],
        "parts_identical_except_document": parts_ok,
        "outside_controls_unchanged": outside_ok,
        "controls_all_filled": controls_ok,
        "placeholder_residue_zero": residue_ok,
        "styles_part_identical": styles_ok,
        "numbering_part_identical": numbering_ok,
        "sections_preserved": asm_model["sections"] == _sections_count(
            template_bytes),
        "document_rels_identical": rels_ok,
        "external_links": {"count": external_links,
                           "note": "rels 恒等由部件恒等维覆盖；外链计数具名"
                                   "呈现，装配不改写外链关系"},
        "privacy": privacy,
    }
    report["failed_dims"] = [dim for dim in STRUCTURE_HARD_DIMS
                             if report[dim] is not True]
    report["all_passed"] = not report["failed_dims"]
    return report


def _sections_count(docx_bytes: bytes) -> int:
    model = parse_template(docx_bytes)
    return model["sections"]


def _privacy_metadata(docx_bytes: bytes) -> dict:
    """隐私维具名：docProps/core.xml 元数据字段逐名呈现（装配原样保留，
    不清洗不发明——命名即检查）。"""
    names = {"creator": "{http://purl.org/dc/elements/1.1/}creator",
             "lastModifiedBy": "{http://schemas.openxmlformats.org/"
                               "package/2006/metadata/core-properties}"
                               "lastModifiedBy"}
    fields: dict[str, str | None] = {"part_present": False,
                                     "creator": None,
                                     "lastModifiedBy": None}
    with zipfile.ZipFile(io.BytesIO(docx_bytes)) as zf:
        if "docProps/core.xml" in zf.namelist():
            fields["part_present"] = True
            root = ET.fromstring(zf.read("docProps/core.xml"))
            for key, tag in names.items():
                node = root.find(tag)
                fields[key] = node.text if node is not None else None
    return fields


def independent_check(template_bytes: bytes, assembled_bytes: bytes,
                      variables: list[dict],
                      answers: dict[str, str]) -> dict:
    """独立检查器（lxml/etree 解析路径——与生成引擎 xml.etree 不同算路，
    F45 python-docx/lxml 先例同族）：控件填充逐一对账＋控件外文本投影
    恒等＋占位残留。缺 lxml＝f56_checker_unavailable fail-closed 不静默
    跳过。"""
    try:
        from lxml import etree as LET
    except ImportError:
        raise _fail("f56_checker_unavailable") from None
    w = "{%s}" % W_NS

    def _parse(docx_bytes: bytes):
        with zipfile.ZipFile(io.BytesIO(docx_bytes)) as zf:
            return LET.fromstring(zf.read("word/document.xml"))

    tpl_root = _parse(template_bytes)
    asm_root = _parse(assembled_bytes)

    def _tag_of(sdt):
        pr = sdt.find(w + "sdtPr")
        if pr is None:
            return None
        node = pr.find(w + "tag")
        return node.get(w + "val") if node is not None else None

    def _text_of(node) -> str:
        return "".join(t.text or "" for t in node.iter(w + "t"))

    dims: dict[str, bool] = {}
    asm_by_tag: dict[str, list[str]] = {}
    for sdt in asm_root.iter(w + "sdt"):
        tag = _tag_of(sdt)
        if tag is not None:
            asm_by_tag.setdefault(tag, []).append(_text_of(sdt))
    dims["checker_controls_filled"] = all(
        asm_by_tag.get(f"{v['kind']}:{v['name']}",
                       [None] * v["controls"])
        == [answers[v["name"]]] * v["controls"] for v in variables)

    def _outside_projection(root) -> list[str]:
        """控件外文本投影：带 tag 控件祖先链上的 w:t 全部剔除（lxml
        getparent 逐级上溯——与生成引擎 iter() 语义不同算路）。"""
        pieces = []
        for node in root.iter(w + "t"):
            parent = node.getparent()
            tagged = False
            while parent is not None:
                if parent.tag == w + "sdt" and _tag_of(parent) is not None:
                    tagged = True
                    break
                parent = parent.getparent()
            if not tagged:
                pieces.append(node.text or "")
        return pieces

    tpl_projection = _outside_projection(tpl_root)
    asm_projection = _outside_projection(asm_root)
    dims["checker_outside_projection_equal"] = \
        tpl_projection == asm_projection
    dims["checker_placeholder_residue_zero"] = not [
        v["placeholder"] for v in variables
        if v["placeholder"] in "".join(asm_projection
                                       + [x for texts in asm_by_tag.values()
                                          for x in texts])]
    failed = [name for name, ok in dims.items() if ok is not True]
    return {"checker": "lxml/etree", "dims": dims,
            "failed_dims": failed, "all_passed": not failed}


# ---------------------------------------------------------------------------
# 状态账（三账 append-only：模板版本/答案表/装配产物）
# ---------------------------------------------------------------------------

def _registry_root(state_root: Path) -> Path:
    return Path(state_root) / STATE_SUBDIR / "registry"


def _answers_root(state_root: Path) -> Path:
    return Path(state_root) / STATE_SUBDIR / "answers"


def _renderings_root(state_root: Path) -> Path:
    return Path(state_root) / STATE_SUBDIR / "renderings"


def _next_seq(directory: Path, pattern: str = r"^\d{4}$") -> str:
    directory.mkdir(parents=True, exist_ok=True)
    seq = 0
    for entry in directory.iterdir():
        if entry.is_dir() or entry.suffix == ".json":
            stem = entry.name.split(".")[0]
            if re.match(pattern, stem):
                seq = max(seq, int(stem))
    return f"{seq + 1:04d}"


def _load_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _manifest_path(state_root: Path, template_id: str,
                   version: int | None = None) -> Path:
    base = _registry_root(state_root) / template_id / "versions"
    if version is None:
        seqs = sorted(int(p.name.split(".")[0]) for p in base.glob("*.json")
                      if p.name.split(".")[0].isdigit())
        if not seqs:
            raise _fail("f56_template_not_found:" + template_id)
        version = seqs[-1]
    return base / f"{version:04d}.json"


def _load_manifest(state_root: Path, template_id: str,
                   version: int | None) -> dict:
    manifest = _load_json(_manifest_path(state_root, template_id, version))
    if manifest is None:
        raise _fail("f56_template_not_found:" + template_id)
    return manifest


def _bridge_harness_call(config: dict):
    """缺省 harness 径＝产品桥（F45 同款 seam）。"""
    import legal_entry

    def call(method: str, args: dict):
        return legal_entry.call(method, args, config)
    return call


def _read_template_bytes(harness_call, matter_id: str, material_id: str,
                         revision: int, expect_sha: str) -> bytes:
    payload = harness_call("harness.read_material", {
        "scope": {"kind": "matter", "matterId": matter_id},
        "material_id": material_id, "revision": revision})
    try:
        raw = base64.b64decode(payload["bytesB64"])
        if payload.get("sha256") != _sha256(raw):
            raise _fail("f56_template_bytes_mismatch")
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, TemplateDraftingError):
            raise
        raise _fail("f56_template_readback_invalid") from None
    if _sha256(raw) != expect_sha:
        raise _fail("f56_template_bytes_mismatch")
    return raw


def _material_head(harness_call, matter_id: str, material_id: str) -> int:
    listing = harness_call("harness.list_materials", {
        "scope": {"kind": "matter", "matterId": matter_id}})
    for material in listing.get("materials", []):
        if material.get("id") == material_id:
            return int(material["currentRevision"])
    raise _fail("f56_template_not_found:" + material_id)


# ---------------------------------------------------------------------------
# 模板库登记（版本＋授权保留，append-only）
# ---------------------------------------------------------------------------

def register_template(state_root: Path, config: dict, args: dict,
                      harness_call=None) -> dict:
    """templates.register：模板登记入正式文件链＋产品版本账。

    v1＝harness.register_material（upload＝律师自备外部文件，F114 合同
    原文 revision 1 恒 upload）；vN+1＝add_material_revision（缺省
    source＝upload 用户侧字节语义）。同 template_id 同 sha＝幂等重放；
    同 id 异 sha＝新版本行（append-only，旧版本与授权元数据永不改写）。
    授权元数据登记时声明、逐字保留；缺 license/source＝
    f56_license_required 拒（保留授权不是事后补写）。"""
    if not isinstance(args, dict):
        raise _fail("f56_params_invalid")
    template_id = args.get("template_id")
    if not isinstance(template_id, str) or not _ID_RE.match(template_id):
        raise _fail("f56_template_id_invalid")
    matter_id = args.get("matter_id")
    if not isinstance(matter_id, str) or not _MATTER_RE.match(matter_id):
        raise _fail("f56_matter_invalid")
    material_id = args.get("material_id")
    if not isinstance(material_id, str) or not _ID_RE.match(material_id):
        raise _fail("f56_material_id_invalid")
    title = args.get("title")
    if not isinstance(title, str) or not title.strip():
        raise _fail("f56_title_invalid")
    actor_id = args.get("actor_id")
    if not isinstance(actor_id, str) or not actor_id:
        raise _fail("f56_actor_invalid")
    license_meta = args.get("license")
    if not isinstance(license_meta, dict) \
            or not isinstance(license_meta.get("license"), str) \
            or not license_meta["license"].strip() \
            or not isinstance(license_meta.get("source"), str) \
            or not license_meta["source"].strip():
        raise _fail("f56_license_required")
    notice = license_meta.get("notice")
    if notice is not None and not isinstance(notice, str):
        raise _fail("f56_license_invalid")
    bytes_b64 = args.get("bytes_b64")
    if not isinstance(bytes_b64, str):
        raise _fail("f56_template_bytes_invalid")
    try:
        template_bytes = base64.b64decode(bytes_b64)
    except (ValueError, TypeError):
        raise _fail("f56_template_bytes_invalid") from None
    model = parse_template(template_bytes)
    sha = _sha256(template_bytes)
    if harness_call is None:
        harness_call = _bridge_harness_call(config)

    with _LOCK:
        versions_dir = _registry_root(state_root) / template_id / "versions"
        existing = _load_json(_manifest_path(state_root, template_id, None)) \
            if versions_dir.is_dir() else None
        if existing is not None:
            if existing["matter_id"] != matter_id:
                raise _fail("f56_template_matter_mismatch")
            if existing["sha256"] == sha:
                view = _template_view(existing)
                view["replayed"] = True
                return view
        if existing is None:
            receipt = harness_call("harness.register_material", {
                "actor_id": actor_id,
                "scope": {"kind": "matter", "matterId": matter_id},
                "key": {"requestId": f"{template_id}:register",
                        "targetId": None, "expectedRevision": None,
                        "inputRefs": []},
                "material": {"id": material_id, "kind": "office",
                             "title": title, "bytesB64": bytes_b64}})
            revision = int(receipt["revision"])
        else:
            receipt = harness_call("harness.add_material_revision", {
                "actor_id": actor_id,
                "scope": {"kind": "matter", "matterId": matter_id},
                "key": {"requestId": f"{template_id}:register:"
                                    f"{sha[:16]}",
                        "targetId": None, "expectedRevision": None,
                        "inputRefs": []},
                "revision": {"materialId": material_id,
                             "bytesB64": bytes_b64}})
            revision = int(receipt["revision"])
        seq = _next_seq(versions_dir)
        manifest = {
            "schema": TEMPLATE_SCHEMA,
            "template_id": template_id,
            "version": int(seq),
            "seq": seq,
            "matter_id": matter_id,
            "material_id": material_id,
            "material_revision": revision,
            "title": title,
            "kind": "office",
            "sha256": sha,
            "bytes": len(template_bytes),
            "content_digest": content_digest(template_bytes),
            "license": {"license": license_meta["license"],
                        "source": license_meta["source"],
                        "notice": notice},
            "variables": model["variables"],
            "controls_total": len(model["controls"]),
            "tagless_controls": model["tagless_controls"],
            "sections": model["sections"],
        }
        _atomic_write(versions_dir / f"{seq}.json",
                      json.dumps(manifest, ensure_ascii=False, indent=1,
                                 sort_keys=True) + "\n")
        view = _template_view(manifest)
        view["replayed"] = False
        return view


def _template_view(manifest: dict) -> dict:
    return {key: manifest[key] for key in (
        "schema", "template_id", "version", "seq", "matter_id",
        "material_id", "material_revision", "title", "kind", "sha256",
        "bytes", "content_digest", "license", "variables", "controls_total",
        "tagless_controls", "sections")}


def template_view(state_root: Path, args: dict) -> dict:
    """templates.template：指定（或最新）版本账回读（append-only 可读）。"""
    if not isinstance(args, dict):
        raise _fail("f56_params_invalid")
    template_id = args.get("template_id")
    if not isinstance(template_id, str) or not _ID_RE.match(template_id):
        raise _fail("f56_template_id_invalid")
    version = args.get("version")
    if version is not None and (isinstance(version, bool)
                                or not isinstance(version, int)
                                or version < 1):
        raise _fail("f56_version_invalid")
    return _template_view(_load_manifest(state_root, template_id, version))


def list_templates(state_root: Path, args: dict) -> dict:
    """templates.list：模板库视图（每模板各版本一行，append-only）。"""
    rows = []
    base = _registry_root(state_root)
    if base.is_dir():
        for template_dir in sorted(base.iterdir()):
            versions_dir = template_dir / "versions"
            if not versions_dir.is_dir():
                continue
            for path in sorted(versions_dir.glob("*.json")):
                manifest = _load_json(path)
                if manifest is None:
                    raise _fail("f56_registry_corrupt:" + path.name)
                rows.append(_template_view(manifest))
    return {"schema": SCHEMA, "templates": rows, "count": len(rows)}


# ---------------------------------------------------------------------------
# 段① 变量问询
# ---------------------------------------------------------------------------

def interview(state_root: Path, config: dict, args: dict,
              harness_call=None) -> dict:
    """templates.interview：问题集生成（变量清单确定性提取的可回读面）。

    模板字节经 harness CAS 随读必验后重提取，与登记账逐字对照（漂移＝
    f56_template_drift 具名拒——登记账不是第二真源，漂移即响亮失败）。"""
    if not isinstance(args, dict):
        raise _fail("f56_params_invalid")
    template_id = args.get("template_id")
    if not isinstance(template_id, str) or not _ID_RE.match(template_id):
        raise _fail("f56_template_id_invalid")
    version = args.get("version")
    if version is not None and (isinstance(version, bool)
                                or not isinstance(version, int)
                                or version < 1):
        raise _fail("f56_version_invalid")
    manifest = _load_manifest(state_root, template_id, version)
    if harness_call is None:
        harness_call = _bridge_harness_call(config)
    template_bytes = _read_template_bytes(
        harness_call, manifest["matter_id"], manifest["material_id"],
        manifest["material_revision"], manifest["sha256"])
    model = parse_template(template_bytes)
    if json.dumps(model["variables"], ensure_ascii=False, sort_keys=True) \
            != json.dumps(manifest["variables"], ensure_ascii=False,
                          sort_keys=True) \
            or model["tagless_controls"] != manifest["tagless_controls"]:
        raise _fail("f56_template_drift")
    questions = [{"name": v["name"], "kind": v["kind"],
                  "question": v["question"], "required": True,
                  "placeholder": v["placeholder"], "controls": v["controls"]}
                 for v in manifest["variables"]]
    return {
        "schema": SCHEMA,
        "segment": "interview",
        "template": {"template_id": template_id,
                     "version": manifest["version"],
                     "sha256": manifest["sha256"],
                     "material_revision": manifest["material_revision"],
                     "title": manifest["title"]},
        "questions": questions,
        "variables_count": len(questions),
        "controls_total": manifest["controls_total"],
        "answers_schema": {"shape": "flat object keyed by variable name",
                           "value": "single-line string per kind "
                                    "(date YYYY-MM-DD / amount decimal or "
                                    "thousand-comma / number decimal / "
                                    "text any printable single-line)",
                           "float_refused": "f56_answer_not_string"},
    }


# ---------------------------------------------------------------------------
# 段② 填充（答案账）
# ---------------------------------------------------------------------------

def _validate_value(variable: dict, value) -> str:
    if isinstance(value, bool) or not isinstance(value, str):
        raise _fail("f56_answer_not_string:" + variable["name"])
    if not value.strip():
        raise _fail("f56_answer_value_invalid:" + variable["name"])
    if _CONTROL_CHARS_RE.search(value) or "\n" in value or "\r" in value \
            or "\t" in value:
        raise _fail("f56_answer_multiline:" + variable["name"])
    kind = variable["kind"]
    if kind == "date":
        if not _DATE_RE.match(value):
            raise _fail("f56_answer_value_invalid:" + variable["name"])
        year, month, day = (int(part) for part in value.split("-"))
        import datetime as _dt
        try:
            _dt.date(year, month, day)
        except ValueError:
            raise _fail("f56_answer_value_invalid:" + variable["name"]) \
                from None
    elif kind == "amount":
        if not _AMOUNT_RE.match(value):
            raise _fail("f56_answer_value_invalid:" + variable["name"])
    elif kind == "number":
        if not _NUMBER_RE.match(value):
            raise _fail("f56_answer_value_invalid:" + variable["name"])
    return value


def save_answers(state_root: Path, args: dict) -> dict:
    """templates.save_answers：答案账 append-only（段②）。

    完整性硬闸：变量名集合与模板问题集恰等（缺＝f56_answers_missing_
    variables 具名清单、多＝f56_answers_unknown_variables——不发明值、
    不发明变量）；逐值 kind 校验。同 answers_id 同内容＝幂等重放；异
    内容＝f56_answers_id_conflict。"""
    if not isinstance(args, dict):
        raise _fail("f56_params_invalid")
    template_id = args.get("template_id")
    if not isinstance(template_id, str) or not _ID_RE.match(template_id):
        raise _fail("f56_template_id_invalid")
    version = args.get("version")
    if version is not None and (isinstance(version, bool)
                                or not isinstance(version, int)
                                or version < 1):
        raise _fail("f56_version_invalid")
    answers_id = args.get("answers_id")
    if not isinstance(answers_id, str) or not _REQUEST_RE.match(answers_id):
        raise _fail("f56_answers_id_invalid")
    matter_id = args.get("matter_id")
    if not isinstance(matter_id, str) or not _MATTER_RE.match(matter_id):
        raise _fail("f56_matter_invalid")
    answers = args.get("answers")
    if not isinstance(answers, dict):
        raise _fail("f56_answers_invalid")
    manifest = _load_manifest(state_root, template_id, version)
    if manifest["matter_id"] != matter_id:
        raise _fail("f56_template_matter_mismatch")
    names = {v["name"] for v in manifest["variables"]}
    given = set(answers)
    missing = sorted(names - given)
    unknown = sorted(given - names)
    if missing:
        raise _fail("f56_answers_missing_variables:"
                    + ",".join(missing))
    if unknown:
        raise _fail("f56_answers_unknown_variables:" + ",".join(unknown))
    by_name = {v["name"]: v for v in manifest["variables"]}
    clean = {name: _validate_value(by_name[name], answers[name])
             for name in sorted(names)}
    sheet = {
        "schema": ANSWERS_SCHEMA,
        "answers_id": answers_id,
        "matter_id": matter_id,
        "template_id": template_id,
        "template_version": manifest["version"],
        "template_sha256": manifest["sha256"],
        "answers": clean,
        "answers_sha256": _sha256(json.dumps(
            clean, ensure_ascii=False, sort_keys=True).encode("utf-8")),
    }
    with _LOCK:
        answers_dir = (_answers_root(state_root) / matter_id / template_id)
        answers_dir.mkdir(parents=True, exist_ok=True)
        path = answers_dir / f"{answers_id}.json"
        existing = _load_json(path)
        if existing is not None:
            if existing.get("answers_sha256") != sheet["answers_sha256"] \
                    or existing.get("template_sha256") \
                    != sheet["template_sha256"]:
                raise _fail("f56_answers_id_conflict:" + answers_id)
            view = dict(existing)
            view["replayed"] = True
            return view
        _atomic_write(path, json.dumps(sheet, ensure_ascii=False, indent=1,
                                       sort_keys=True) + "\n")
    view = dict(sheet)
    view["replayed"] = False
    return view


def read_answers(state_root: Path, args: dict) -> dict:
    """templates.answers：答案账回读（可回读断言面）。"""
    if not isinstance(args, dict):
        raise _fail("f56_params_invalid")
    template_id = args.get("template_id")
    if not isinstance(template_id, str) or not _ID_RE.match(template_id):
        raise _fail("f56_template_id_invalid")
    matter_id = args.get("matter_id")
    if not isinstance(matter_id, str) or not _MATTER_RE.match(matter_id):
        raise _fail("f56_matter_invalid")
    answers_id = args.get("answers_id")
    if not isinstance(answers_id, str) or not _REQUEST_RE.match(answers_id):
        raise _fail("f56_answers_id_invalid")
    sheet = _load_json(_answers_root(state_root) / matter_id / template_id
                       / f"{answers_id}.json")
    if sheet is None:
        raise _fail("f56_answers_not_found:" + answers_id)
    view = dict(sheet)
    view["replayed"] = False
    return view


# ---------------------------------------------------------------------------
# 段③ 装配（结构/视觉检查→harness 正式材料版本链＋提案）
# ---------------------------------------------------------------------------

def _find_rendering(material_dir: Path, request_id: str) -> dict | None:
    outputs = material_dir / "outputs"
    if not outputs.is_dir():
        return None
    for entry in sorted(outputs.iterdir(), reverse=True):
        manifest = _load_json(entry / "manifest.json")
        if manifest is not None and manifest.get("request_id") == request_id:
            return manifest
    return None


def _quotes_for_proposal(model_vars: list[dict], matter_id: str,
                         material_id: str, template_revision: int) -> list:
    """占位定位集→F47 提案 quotes（占位文本＝模板内精确定位；理由＝
    变量名＋kind，确定性、不含答案内容）。每控件一条（同名多控件多条）。"""
    source_ref = {"owner": "harness", "kind": "material",
                  "id": material_id, "version": str(template_revision),
                  "matterId": matter_id}
    quotes = []
    for variable in model_vars:
        for _ in range(variable["controls"]):
            quotes.append({
                "text": variable["placeholder"],
                "reason": f"模板变量填充：{variable['name']}"
                          f"（{variable['kind']}）",
                "sourceRef": dict(source_ref)})
    return quotes


def render(state_root: Path, config: dict, args: dict,
           harness_call=None) -> dict:
    """templates.render：访谈段③装配——填充→结构/视觉硬门→正式链登记。

    单一条流：答案表载入（模板钉校验）→模板字节 CAS 随读必验→确定性
    填充→结构具名检查（硬维不过＝f56_structure_check_failed:<维>，
    不留产物）→独立 lxml 检查器（不过＝f56_checker_failed:<维>）→
    add_material_revision(source=assistant_edit∈F114 闭集)＋
    formal_propose(channel=machine, quotes=占位定位集)→产物 append-only
    落盘。同 request id 重放幂等返回。"""
    if not isinstance(args, dict):
        raise _fail("f56_params_invalid")
    template_id = args.get("template_id")
    if not isinstance(template_id, str) or not _ID_RE.match(template_id):
        raise _fail("f56_template_id_invalid")
    version = args.get("version")
    if version is not None and (isinstance(version, bool)
                                or not isinstance(version, int)
                                or version < 1):
        raise _fail("f56_version_invalid")
    matter_id = args.get("matter_id")
    if not isinstance(matter_id, str) or not _MATTER_RE.match(matter_id):
        raise _fail("f56_matter_invalid")
    answers_id = args.get("answers_id")
    if not isinstance(answers_id, str) or not _REQUEST_RE.match(answers_id):
        raise _fail("f56_answers_id_invalid")
    request_id = args.get("request_id")
    if not isinstance(request_id, str) or not _REQUEST_RE.match(request_id):
        raise _fail("f56_request_id_invalid")
    proposal_id = args.get("proposal_id")
    if not isinstance(proposal_id, str) or not _REQUEST_RE.match(proposal_id):
        raise _fail("f56_proposal_id_invalid")
    actor_id = args.get("actor_id")
    if not isinstance(actor_id, str) or not actor_id:
        raise _fail("f56_actor_invalid")
    author = args.get("author")
    if not isinstance(author, str) or not author:
        raise _fail("f56_author_required")
    # F53 作者策略面过闸（templates 通道绑定 lvyin-templates；冒充律师
    # 名＝f53_author_impersonation，通道错绑＝f53_author_channel_mismatch）。
    from author_policy import check_revision_author, AuthorPolicyError
    try:
        check_revision_author(AUTHOR_CHANNEL, author)
    except AuthorPolicyError as exc:
        raise _fail(str(exc)) from None
    note = args.get("note")
    if note is not None and not isinstance(note, str):
        raise _fail("f56_note_invalid")
    if harness_call is None:
        harness_call = _bridge_harness_call(config)

    with _LOCK:
        manifest = _load_manifest(state_root, template_id, version)
        if manifest["matter_id"] != matter_id:
            raise _fail("f56_template_matter_mismatch")
        sheet = _load_json(_answers_root(state_root) / matter_id
                           / template_id / f"{answers_id}.json")
        if sheet is None:
            raise _fail("f56_answers_not_found:" + answers_id)
        if sheet.get("template_sha256") != manifest["sha256"] \
                or sheet.get("template_version") != manifest["version"]:
            raise _fail("f56_answers_template_mismatch")
        template_bytes = _read_template_bytes(
            harness_call, manifest["matter_id"], manifest["material_id"],
            manifest["material_revision"], manifest["sha256"])
        answers = sheet["answers"]

        material_dir = (_renderings_root(state_root) / matter_id
                        / template_id)
        replay = _find_rendering(material_dir, request_id)
        assembled = fill_template(template_bytes, manifest["variables"],
                                  answers)
        if replay is not None:
            if replay["assembled"]["sha256"] != _sha256(assembled):
                raise _fail("f56_request_conflict")
            view = _rendering_view(replay)
            view["replayed"] = True
            return view

        structure = structure_report(template_bytes, assembled,
                                     manifest["variables"], answers)
        if not structure["all_passed"]:
            raise _fail("f56_structure_check_failed:"
                        + ",".join(structure["failed_dims"]))
        checker = independent_check(template_bytes, assembled,
                                    manifest["variables"], answers)
        if not checker["all_passed"]:
            raise _fail("f56_checker_failed:"
                        + ",".join(checker["failed_dims"]))

        assembled_b64 = base64.b64encode(assembled).decode("ascii")
        head = _material_head(harness_call, matter_id,
                              manifest["material_id"])
        revision_receipt = harness_call("harness.add_material_revision", {
            "actor_id": actor_id,
            "scope": {"kind": "matter", "matterId": matter_id},
            "key": {"requestId": f"{request_id}:assistant-edit",
                    "targetId": None, "expectedRevision": None,
                    "inputRefs": []},
            "revision": {"materialId": manifest["material_id"],
                         "bytesB64": assembled_b64,
                         "baseRevision": head,
                         "source": ASSISTANT_SOURCE}})
        assistant_revision = int(revision_receipt["revision"])
        proposal_receipt = harness_call("harness.formal_propose", {
            "actor_id": actor_id,
            "scope": {"kind": "matter", "matterId": matter_id},
            "key": {"requestId": f"{request_id}:formal-propose",
                    "targetId": None, "expectedRevision": None,
                    "inputRefs": []},
            "proposal": {
                "proposalId": proposal_id,
                "materialId": manifest["material_id"],
                "baseRevision": assistant_revision,
                "bytesB64": assembled_b64,
                "channel": CHANNEL,
                "author": author,
                "quotes": _quotes_for_proposal(
                    manifest["variables"], matter_id,
                    manifest["material_id"], manifest["material_revision"]),
                "note": note}})
        proposal_row = proposal_receipt["proposal"]

        outputs_dir = material_dir / "outputs"
        outputs_dir.mkdir(parents=True, exist_ok=True)
        seq = _next_seq(outputs_dir, pattern=r"^\d{4}$")
        out_dir = outputs_dir / seq
        staging = out_dir.with_name(out_dir.name + ".staging")
        staging.mkdir(parents=True, exist_ok=False)
        try:
            staging.joinpath("assembled.docx").write_bytes(assembled)
            rendering = {
                "schema": RENDERING_SCHEMA,
                "output_id": f"{template_id}:{seq}",
                "request_id": request_id,
                "matter_id": matter_id,
                "template_id": template_id,
                "template_version": manifest["version"],
                "template_sha256": manifest["sha256"],
                "answers_id": answers_id,
                "answers_sha256": sheet["answers_sha256"],
                "channel": CHANNEL,
                "author": author,
                "assembled": {"file": "assembled.docx",
                              "sha256": _sha256(assembled),
                              "content_digest": content_digest(assembled),
                              "bytes": len(assembled)},
                "structure_visual": structure,
                "independent_check": checker,
                "harness": {
                    "assistant_edit": {
                        "revision": assistant_revision,
                        "source": revision_receipt.get("source"),
                        "sha256": revision_receipt.get("sha256"),
                        "cas_ref": revision_receipt.get("casRef"),
                        "base_revision": revision_receipt.get(
                            "baseRevision"),
                    },
                    "proposal": {
                        "proposal_id": proposal_id,
                        "state": proposal_row.get("state"),
                        "channel": proposal_row.get("channel"),
                        "author": proposal_row.get("author"),
                        "base_revision": proposal_row.get("baseRevision"),
                        "quotes_count": len(proposal_row.get("quotes", [])),
                    },
                },
            }
            _atomic_write(staging / "manifest.json",
                          json.dumps(rendering, ensure_ascii=False,
                                     indent=1, sort_keys=True) + "\n")
            os.replace(staging, out_dir)
        except OSError:
            if staging.exists():
                for child in staging.iterdir():
                    child.unlink()
                staging.rmdir()
            raise
        view = _rendering_view(rendering)
        view["replayed"] = False
        return view


def _rendering_view(rendering: dict) -> dict:
    return {key: rendering[key] for key in (
        "schema", "output_id", "request_id", "matter_id", "template_id",
        "template_version", "template_sha256", "answers_id",
        "answers_sha256", "channel", "author", "assembled",
        "structure_visual", "independent_check", "harness")}


def list_renderings(state_root: Path, args: dict) -> dict:
    """templates.renderings：装配产物清单（append-only 可回读）。"""
    if not isinstance(args, dict):
        raise _fail("f56_params_invalid")
    template_id = args.get("template_id")
    if not isinstance(template_id, str) or not _ID_RE.match(template_id):
        raise _fail("f56_template_id_invalid")
    matter_id = args.get("matter_id")
    if not isinstance(matter_id, str) or not _MATTER_RE.match(matter_id):
        raise _fail("f56_matter_invalid")
    outputs = _renderings_root(state_root) / matter_id / template_id \
        / "outputs"
    rows = []
    if outputs.is_dir():
        for entry in sorted(outputs.iterdir()):
            manifest = _load_json(entry / "manifest.json")
            if manifest is None:
                raise _fail("f56_rendering_corrupt:" + entry.name)
            rows.append(_rendering_view(manifest))
    return {"schema": SCHEMA, "renderings": rows, "count": len(rows)}


# ---------------------------------------------------------------------------
# legal_entry 唯一分发
# ---------------------------------------------------------------------------

def templates_call(method: str, args: dict, config: dict,
                   harness_call=None) -> dict:
    """legal_entry templates.* 唯一分发（fail-closed 同基线）。

    配置级缺状态根＝NOT_CONNECTED（同全桥纪律）；业务级 typed 拒＝
    TemplateDraftingError（f56_* 码，同 DocxEditError 先例）。"""
    from bridge_errors import NotConnected
    state_root = config.get("templates_state_root")
    if not state_root:
        raise NotConnected("f56_state_root_not_configured")
    if method == "templates.register":
        return register_template(Path(state_root), config, args,
                                 harness_call=harness_call)
    if method == "templates.list":
        return list_templates(Path(state_root), args)
    if method == "templates.template":
        return template_view(Path(state_root), args)
    if method == "templates.interview":
        return interview(Path(state_root), config, args,
                         harness_call=harness_call)
    if method == "templates.save_answers":
        return save_answers(Path(state_root), args)
    if method == "templates.answers":
        return read_answers(Path(state_root), args)
    if method == "templates.render":
        return render(Path(state_root), config, args,
                      harness_call=harness_call)
    if method == "templates.renderings":
        return list_renderings(Path(state_root), args)
    raise _fail("f56_method_unknown")
