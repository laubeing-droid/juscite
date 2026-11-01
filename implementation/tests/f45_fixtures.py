"""F45 合成语料（W2b-U15）：纯 stdlib 生成合成法律文书 DOCX 原稿。

测试一律合成材料（红线）——本模块是唯一语料来源，recon 与单测共用。
确定性：zip 时间戳钉定（1980-01-01）、零随机——同参数两跑同字节。

语料结构（正文/表格/编号三要素齐备）：
  - 标题段（居中粗体，样式 Heading1 语义）
  - 当事人段（带 rPr 字体的正文 runs）
  - 诉讼请求编号段×3（w:numPr numId=1 ilvl=0，十进制编号）
  - 事实与理由段×2
  - 违约金计算表 3×3（w:tbl/w:tr/w:tc）
  - 结尾段＋sectPr（页脚 footer1.xml 带页码域——未编辑部件逐字节保真的
    对照面）
"""
from __future__ import annotations

import io
import zipfile

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_ZIP_DATE = (1980, 1, 1, 0, 0, 0)

DECL = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'

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
    '</Types>')

ROOT_RELS = DECL + (
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
    'relationships"><Relationship Id="rId1" Type="http://schemas.'
    'openxmlformats.org/officeDocument/2006/relationships/officeDocument"'
    ' Target="word/document.xml"/></Relationships>')

DOC_RELS = DECL + (
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
    'relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/'
    'officeDocument/2006/relationships/styles" Target="styles.xml"/>'
    '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/'
    'officeDocument/2006/relationships/numbering" Target="numbering.xml"/>'
    '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/'
    'officeDocument/2006/relationships/footer" Target="footer1.xml"/>'
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
    '<w:style w:type="character" w:styleId="CommentReference">'
    '<w:name w:val="annotation reference"/></w:style>'
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


def _para(text: str, *, style: str | None = None, numbered: bool = False,
          bold: bool = False, preserve: bool = True) -> str:
    ppr = ""
    inner = ""
    if style is not None:
        inner += f'<w:pStyle w:val="{style}"/>'
    if numbered:
        inner += ('<w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/>'
                  '</w:numPr>')
    if inner:
        ppr = f"<w:pPr>{inner}</w:pPr>"
    rpr = "<w:rPr><w:b/></w:rPr>" if bold else ""
    space = ' xml:space="preserve"' if preserve else ""
    return (f"<w:p>{ppr}<w:r>{rpr}<w:t{space}>{_escape(text)}"
            f"</w:t></w:r></w:p>")


def _escape(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


def _cell(text: str) -> str:
    return ('<w:tc><w:tcPr><w:tcW w:w="2800" w:type="dxa"/></w:tcPr>'
            + _para(text) + "</w:tc>")


def _table(rows: list[list[str]]) -> str:
    body = "".join(
        "<w:tr>" + "".join(_cell(cell) for cell in row) + "</w:tr>"
        for row in rows)
    return ('<w:tbl><w:tblPr><w:tblW w:w="0" w:type="auto"/><w:tblBorders>'
            '<w:top w:val="single" w:sz="4"/><w:left w:val="single" w:sz="4"/>'
            '<w:bottom w:val="single" w:sz="4"/>'
            '<w:right w:val="single" w:sz="4"/>'
            '</w:tblBorders></w:tblPr>' + body + "</w:tbl>")


def document_xml(variant: str = "complaint") -> str:
    """合成文书正文。variant=complaint（民事起诉状式）唯一形态。"""
    if variant != "complaint":
        raise ValueError("f45_fixture_variant_unknown")
    blocks = [
        _para("民事起诉状（合成语料）", style="Heading1", bold=True),
        _para("原告：合成贸易有限责任公司，住所地：合成市合成区合成路1号。"),
        _para("被告：合成实业有限公司，住所地：合成市合成区测试路2号。"),
        _para("诉讼请求：", bold=True),
        _para("判令被告支付货款85,000元；", numbered=True),
        _para("判令被告支付违约金，按日万分之五计算；", numbered=True),
        _para("本案诉讼费用由被告承担。", numbered=True),
        _para("事实与理由："),
        _para("2026年1月，原告与被告签订《合成购销合同》，约定原告向被告"
              "供应合成设备，货款总额85,000元，验收后30日内支付。"),
        _para("原告已按约交付全部设备，被告仅支付部分货款，尚欠"
              "85,000元至今未付。"),
        _table([
            ["项目", "金额（元）", "备注"],
            ["货款本金", "85,000", "合同总额"],
            ["违约金", "0", "按日万分之五另计"],
        ]),
        _para("综上，为维护原告合法权益，特向贵院提起诉讼，请求依法"
              "判如所请。"),
        _para("此致"),
        _para("合成市合成区人民法院"),
        _para("附：本起诉状副本一份。"),
    ]
    body = "".join(blocks)
    return DECL + (
        '<w:document xmlns:w="' + W_NS + '" xmlns:r="' + R_NS + '">'
        '<w:body>' + body
        + '<w:sectPr><w:footerReference w:type="default" r:id="rId3"/>'
          '<w:pgSz w:w="11906" w:h="16838"/>'
          '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134"'
          ' w:left="1134"/></w:sectPr></w:body></w:document>')


def build_source_docx(variant: str = "complaint") -> bytes:
    """合成原稿 DOCX 字节（确定性：同参数两跑同字节）。"""
    out = io.BytesIO()
    parts = {
        "[Content_Types].xml": CONTENT_TYPES,
        "_rels/.rels": ROOT_RELS,
        "word/document.xml": document_xml(variant),
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
