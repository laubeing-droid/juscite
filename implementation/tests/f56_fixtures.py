"""F56 合成语料（W4-U38）：纯 stdlib 生成合成文书模板 DOCX。

测试一律合成材料（红线）——本模块是唯一语料来源，recon 与单测共用。
确定性：zip 时间戳钉定（1980-01-01）、零随机——同参数两跑同字节。

模板结构（变量载体＝正文内容控件 w:sdt，tag＝kind:变量名、alias＝问询
话术；五维结构/视觉检查面对照件齐备）：
  - 标题段（Heading1 语义）＋案由段
  - 带.tag 内容控件×7：text×3（court/plaintiff/defendant，其中 plaintiff
    双控件＝同名多控件填充面）、amount×2（claim/interest）、date×1、
    number×1
  - 无 tag 内容控件×1（tagless_controls 具名清点面）
  - 外链超链接×1（word/_rels/document.xml.rels TargetMode=External，
    外链具名检查面对照件）
  - styles/numbering/footer1/sectPr（部件恒等与 section 守恒对照件）
  - docProps/core.xml creator/lastModifiedBy（隐私具名检查对照件）
"""
from __future__ import annotations

import io
import zipfile

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
CP_NS = ("http://schemas.openxmlformats.org/package/2006/metadata/"
         "core-properties")
DC_NS = "http://purl.org/dc/elements/1.1/"
_ZIP_DATE = (1980, 1, 1, 0, 0, 0)

DECL = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'

# 极小包（无 core/styles/numbering/footer——拒绝面与多控件单测专用）。
MINIMAL_CONTENT_TYPES = DECL + (
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/'
    'content-types">'
    '<Default Extension="rels" ContentType="application/vnd.'
    'openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" ContentType="application/vnd.'
    'openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    '</Types>')
MINIMAL_ROOT_RELS = DECL + (
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
    'relationships"><Relationship Id="rId1" Type="http://schemas.'
    'openxmlformats.org/officeDocument/2006/relationships/officeDocument"'
    ' Target="word/document.xml"/></Relationships>')

CONTENT_TYPES = DECL + (
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/'
    'content-types">'
    '<Default Extension="rels" ContentType="application/vnd.'
    'openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" ContentType="application/vnd.'
    'openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    '<Override PartName="/word/styles.xml" ContentType="application/vnd.'
    'openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
    '<Override PartName="/word/numbering.xml" ContentType="application/vnd.'
    'openxmlformats-officedocument.wordprocessingml.numbering+xml"/>'
    '<Override PartName="/word/footer1.xml" ContentType="application/vnd.'
    'openxmlformats-officedocument.wordprocessingml.footer+xml"/>'
    '<Override PartName="/docProps/core.xml" ContentType="application/vnd.'
    'openxmlformats-package.core-properties+xml"/>'
    '</Types>')

ROOT_RELS = DECL + (
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
    'relationships"><Relationship Id="rId1" Type="http://schemas.'
    'openxmlformats.org/officeDocument/2006/relationships/officeDocument"'
    ' Target="word/document.xml"/><Relationship Id="rId2" Type="http://'
    'schemas.openxmlformats.org/package/2006/relationships/metadata/'
    'core-properties" Target="docProps/core.xml"/></Relationships>')

# rId100＝外链对照件（TargetMode=External；外链具名检查的计数对照=1）。
DOC_RELS = DECL + (
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
    'relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/'
    'officeDocument/2006/relationships/styles" Target="styles.xml"/>'
    '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/'
    'officeDocument/2006/relationships/numbering" Target="numbering.xml"/>'
    '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/'
    'officeDocument/2006/relationships/footer" Target="footer1.xml"/>'
    '<Relationship Id="rId100" Type="http://schemas.openxmlformats.org/'
    'officeDocument/2006/relationships/hyperlink" '
    'Target="https://synth.example.invalid/template" '
    'TargetMode="External"/>'
    '</Relationships>')

STYLES = DECL + (
    '<w:styles xmlns:w="' + W_NS + '">'
    '<w:style w:type="paragraph" w:styleId="Normal">'
    '<w:name w:val="Normal"/><w:pPr><w:spacing w:line="360"/></w:pPr>'
    '</w:style>'
    '<w:style w:type="paragraph" w:styleId="Heading1">'
    '<w:name w:val="heading 1"/>'
    '<w:pPr><w:jc w:val="center"/></w:pPr>'
    '<w:rPr><w:b/><w:sz w:val="36"/></w:rPr></w:style>'
    '</w:styles>')

NUMBERING = DECL + (
    '<w:numbering xmlns:w="' + W_NS + '">'
    '<w:abstractNum w:abstractNumId="0">'
    '<w:lvl w:ilvl="0"><w:start w:val="1"/>'
    '<w:numFmt w:val="decimal"/><w:lvlText w:val="%1."/></w:lvl>'
    '</w:abstractNum>'
    '<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>'
    '</w:numbering>')

FOOTER = DECL + (
    '<w:ftr xmlns:w="' + W_NS + '"><w:p><w:pPr><w:jc w:val="center"/></w:pPr>'
    '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
    '<w:r><w:instrText xml:space="preserve"> PAGE </w:instrText></w:r>'
    '<w:r><w:fldChar w:fldCharType="end"/></w:r></w:p></w:ftr>')

# 隐私具名检查对照件（装配原样保留、逐名呈现——不清洗不发明）。
CORE = DECL + (
    '<cp:coreProperties xmlns:cp="' + CP_NS + '" xmlns:dc="' + DC_NS + '">'
    '<dc:creator>合成模板组（synthetic）</dc:creator>'
    '<cp:lastModifiedBy>合成模板组（synthetic）</cp:lastModifiedBy>'
    '</cp:coreProperties>')


def _escape(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


def _sdt(tag: str | None, alias: str | None, placeholder: str,
         bold: bool = False) -> str:
    """内容控件：tag/alias 入 sdtPr（模板自描述），占位文本单运行。"""
    pr = ""
    if alias is not None:
        pr += f'<w:alias w:val="{_escape(alias)}"/>'
    if tag is not None:
        pr += f'<w:tag w:val="{_escape(tag)}"/>'
    rpr = "<w:rPr><w:b/></w:rPr>" if bold else ""
    return ('<w:sdt><w:sdtPr>' + pr + '</w:sdtPr><w:sdtContent>'
            f'<w:r>{rpr}<w:t xml:space="preserve">{_escape(placeholder)}'
            '</w:t></w:r></w:sdtContent></w:sdt>')


def document_xml() -> str:
    """合成起诉状模板正文（控件×8＝带 tag×7＋无 tag×1；外链×1）。"""
    blocks = [
        '<w:p><w:pPr><w:pStyle w:val="Heading1"/><w:jc w:val="center"/>'
        '</w:pPr><w:r><w:rPr><w:b/></w:rPr>'
        '<w:t xml:space="preserve">民事起诉状（合成模板）</w:t></w:r></w:p>',
        '<w:p><w:r><w:t xml:space="preserve">案由：合成购销合同纠纷。'
        '</w:t></w:r>'
        '<w:hyperlink r:id="rId100">'
        '<w:r><w:rPr><w:color w:val="0000FF"/></w:rPr>'
        '<w:t xml:space="preserve">模板使用说明（外链对照件）</w:t></w:r>'
        '</w:hyperlink></w:p>',
        '<w:p><w:r><w:t xml:space="preserve">原告：</w:t></w:r>'
        + _sdt("text:plaintiff", "原告名称", "【原告名称】", bold=True)
        + '<w:r><w:t xml:space="preserve">，住所地：</w:t></w:r>'
        + _sdt("text:plaintiff_address", "原告住所地", "【原告住所地】")
        + '<w:r><w:t xml:space="preserve">。</w:t></w:r></w:p>',
        '<w:p><w:r><w:t xml:space="preserve">被告：</w:t></w:r>'
        + _sdt("text:defendant", "被告名称", "【被告名称】", bold=True)
        + '<w:r><w:t xml:space="preserve">，住所地：</w:t></w:r>'
        + _sdt(None, None, "固定说明文本（无 tag 控件——结构保真面对照件）")
        + '<w:r><w:t xml:space="preserve">。</w:t></w:r></w:p>',
        '<w:p><w:r><w:t xml:space="preserve">诉讼请求：</w:t></w:r></w:p>',
        '<w:p><w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/>'
        '</w:numPr></w:pPr><w:r><w:t xml:space="preserve">判令被告支付'
        '货款</w:t></w:r>'
        + _sdt("amount:claim_total", "货款总额（元）", "【货款总额】")
        + '<w:r><w:t xml:space="preserve">元及利息</w:t></w:r>'
        + _sdt("amount:interest_total", "利息总额（元）", "【利息总额】")
        + '<w:r><w:t xml:space="preserve">元；</w:t></w:r></w:p>',
        '<w:p><w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/>'
        '</w:numPr></w:pPr><w:r><w:t xml:space="preserve">本案诉讼费用'
        '由被告承担；</w:t></w:r></w:p>',
        '<w:p><w:r><w:t xml:space="preserve">事实与理由：双方于</w:t></w:r>'
        + _sdt("date:contract_date", "合同签订日", "【合同签订日】")
        + '<w:r><w:t xml:space="preserve">签订《合成购销合同》，被告尚欠'
          '货款未付。</w:t></w:r></w:p>',
        '<w:p><w:r><w:t xml:space="preserve">此致</w:t></w:r></w:p>',
        '<w:p><w:r><w:t xml:space="preserve">'
        '</w:t></w:r>'
        + _sdt("text:court", "受诉法院全称", "【受诉法院全称】", bold=True)
        + '</w:p>',
        '<w:p><w:r><w:t xml:space="preserve">附：本起诉状副本</w:t></w:r>'
        + _sdt("number:copies", "副本份数", "【副本份数】")
        + '<w:r><w:t xml:space="preserve">份。</w:t></w:r></w:p>',
    ]
    body = "".join(blocks)
    return DECL + (
        '<w:document xmlns:w="' + W_NS + '" xmlns:r="' + R_NS + '">'
        '<w:body>' + body
        + '<w:sectPr><w:footerReference w:type="default" r:id="rId3"/>'
          '<w:pgSz w:w="11906" w:h="16838"/>'
          '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134"'
          ' w:left="1134"/></w:sectPr></w:body></w:document>')


def build_template_docx() -> bytes:
    """合成模板 DOCX 字节（确定性：两跑同字节）。"""
    out = io.BytesIO()
    parts = {
        "[Content_Types].xml": CONTENT_TYPES,
        "_rels/.rels": ROOT_RELS,
        "docProps/core.xml": CORE,
        "word/document.xml": document_xml(),
        "word/_rels/document.xml.rels": DOC_RELS,
        "word/styles.xml": STYLES,
        "word/numbering.xml": NUMBERING,
        "word/footer1.xml": FOOTER,
    }
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, payload in parts.items():
            info = zipfile.ZipInfo(name, date_time=_ZIP_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, payload.encode("utf-8"))
    return out.getvalue()


# 同名多控件对照件：plaintiff 出现两次的极小模板（多控件填充面单测）。
def build_repeat_template_docx() -> bytes:
    document = DECL + (
        '<w:document xmlns:w="' + W_NS + '"><w:body>'
        '<w:p><w:r><w:t xml:space="preserve">申请人：</w:t></w:r>'
        + _sdt("text:party", "当事人名称", "【当事人名称】")
        + '</w:p>'
        '<w:p><w:r><w:t xml:space="preserve">被申请人：</w:t></w:r>'
        + _sdt("text:party", "当事人名称", "【当事人名称】")
        + '</w:p>'
        '</w:body></w:document>')
    return _write_parts({
        "[Content_Types].xml": MINIMAL_CONTENT_TYPES,
        "_rels/.rels": MINIMAL_ROOT_RELS,
        "word/document.xml": document,
    })


# 页脚带 tag 控件对照件（f56_control_outside_body 拒绝面对照）。
def build_footer_control_docx() -> bytes:
    footer = DECL + (
        '<w:ftr xmlns:w="' + W_NS + '"><w:p>'
        + _sdt("text:footer_var", "页脚变量", "【页脚变量】")
        + '</w:p></w:ftr>')
    return _write_parts({
        "[Content_Types].xml": MINIMAL_CONTENT_TYPES,
        "_rels/.rels": MINIMAL_ROOT_RELS,
        "word/document.xml": DECL + (
            '<w:document xmlns:w="' + W_NS + '" xmlns:r="' + R_NS + '">'
            '<w:body><w:p><w:r><w:t xml:space="preserve">正文</w:t></w:r>'
            + _sdt("text:body_var", "正文变量", "【正文变量】")
            + '</w:p><w:sectPr><w:footerReference w:type="default" '
              'r:id="rId3"/></w:sectPr></w:body></w:document>'),
        "word/_rels/document.xml.rels": DOC_RELS,
        "word/footer1.xml": footer,
    })


# 零控件普通文档对照件（f56_template_no_variables 拒绝面对照）。
def build_plain_docx() -> bytes:
    return _write_parts({
        "[Content_Types].xml": MINIMAL_CONTENT_TYPES,
        "_rels/.rels": MINIMAL_ROOT_RELS,
        "word/document.xml": DECL + (
            '<w:document xmlns:w="' + W_NS + '"><w:body>'
            '<w:p><w:r><w:t xml:space="preserve">普通文档无控件</w:t></w:r>'
            '</w:p></w:body></w:document>'),
    })


def _write_parts(parts: dict) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, payload in parts.items():
            info = zipfile.ZipInfo(name, date_time=_ZIP_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, payload.encode("utf-8"))
    return out.getvalue()


# 访谈答案对照集（全合成；与 build_template_docx 变量集恰等）。
ANSWERS = {
    "plaintiff": "合成贸易有限责任公司",
    "plaintiff_address": "合成市合成区合成路1号",
    "defendant": "合成实业有限公司",
    "claim_total": "85,000.00",
    "interest_total": "4,250.50",
    "contract_date": "2026-01-15",
    "court": "合成市合成区人民法院",
    "copies": "2",
}
