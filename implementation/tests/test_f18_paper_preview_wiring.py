"""W3-U21 / F18 wiring: 纸张 CSS 文书观感（paper.* 桥方法组 → paper_preview
产品面 document-adapter 家族）。

义务 06:F18 断言：「纸张 CSS 文书观感（衬线+页边距+微阴影）」＋验收行
「纸张预览与真实DOCX/PDF分页分别核；缩放阅读不遮正文」＋08§3 文书行
「CSS预览/文件存在/HTML.doc 不等正式DOCX」。

- 内容面/负向：纯单测（无 soffice，手造 docx 字节）——paper.document
  确定性＋零分页字段（CSS 预览结构性不携带分页主张）＋typed 负向。
- 分页参照面：真 LibreOffice（--convert-to pdf；soffice.com 阻塞二进制）
  ——未安装/不可执行整类跳过（如实 NOT_INSTALLED，绝不假绿）。页数/逐页
  文本自 PDF 实测（pdfium），复用 F54 pdf_facts；语料全合成。
- 实测口径（本机 LibreOffice 26.8.1.1）：同输入两跑 document 逐键相等；
  分页参照页数/逐页文本跨状态根复现（内容级）；PDF 字节不主张逐字节
  确定（内嵌时间戳元数据，如实不断言）。
"""
import sys
import tempfile
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
from legal_entry import call, NotConnected  # noqa: E402
from pdf_conversion import _resolve_soffice  # noqa: E402

_W_URI = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
DEFAULT_SOFFICE = r"C:\Program Files\LibreOffice\program\soffice.exe"


def _synthetic_docx(path: Path, paragraphs: int = 60) -> bytes:
    """全合成多段 DOCX（确定性；A4＋公文页边距 sectPr，正文全虚构）。"""
    body = "".join(
        "<w:p><w:r><w:t>合成段落%03d：当事人与金额均为虚构，本行用于"
        "纸张预览与真实分页分别核，绝无真实案件内容。</w:t></w:r></w:p>"
        % i for i in range(paragraphs))
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="%s"><w:body>%s'
        '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="2098" w:right="1474" w:bottom="1984" '
        'w:left="1588"/></w:sectPr></w:body></w:document>' % (_W_URI, body))
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/'
        'content-types"><Default Extension="rels" ContentType="application/'
        'vnd.openxmlformats-package.relationships+xml"/><Default Extension='
        '"xml" ContentType="application/xml"/><Override PartName="/word/'
        'document.xml" ContentType="application/vnd.openxmlformats-'
        'officedocument.wordprocessingml.document.main+xml"/></Types>')
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/'
        '2006/relationships"><Relationship Id="rId1" Type="http://'
        'schemas.openxmlformats.org/officeDocument/2006/relationships/'
        'officeDocument" Target="word/document.xml"/></Relationships>')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("word/document.xml", document)
    return path.read_bytes()


@pytest.fixture()
def workdir(tmp_path):
    docx = tmp_path / "f18-synth.docx"
    _synthetic_docx(docx)
    return {"tmp": tmp_path, "docx": docx}


@pytest.fixture()
def base_config(workdir):
    return {"paper_state_root": str(workdir["tmp"] / "state"),
            "libreoffice_soffice": DEFAULT_SOFFICE}


# --------------------------------------------------------------------------
# paper.document（内容面：确定性＋零分页字段）
# --------------------------------------------------------------------------

def test_f18_document_deterministic_no_page_fields(workdir, base_config):
    first = call("paper.document", {"docx_path": str(workdir["docx"])},
                 base_config)
    second = call("paper.document", {"docx_path": str(workdir["docx"])},
                  base_config)
    # 同输入两跑逐键相等（无时钟无随机）
    assert first == second
    assert first["schema"] == "juscite-f18-paper-preview/1"
    # 结构性零分页字段：CSS 预览面没有 page_count/pages 可冒充（08§3）
    assert "page_count" not in first and "pages" not in first
    assert first["pagination"] == {
        "carried_by_preview": False,
        "preview_rendering": "css_continuous_sheet_no_page_claims",
        "official_reference_method": "paper.pagination_reference",
        "css_preview_is_not_official_pagination": True,
    }
    assert first["counts"]["paragraphs"] == 60
    assert first["counts"]["blocks"] == 60
    assert first["blocks"][0]["text"].startswith("合成段落000")
    # 内容全量在预览面（无截断冒充）
    assert first["counts"]["chars"] > 0


def test_f18_document_negatives_typed(workdir, base_config):
    with pytest.raises(NotConnected) as missing:
        call("paper.document",
             {"docx_path": str(workdir["tmp"] / "no.docx")}, base_config)
    assert "f18_docx_not_found" in str(missing.value)
    bad = workdir["tmp"] / "bad.docx"
    bad.write_bytes(b"not a zip")
    with pytest.raises(NotConnected) as unreadable:
        call("paper.document", {"docx_path": str(bad)}, base_config)
    assert "f18_docx_unreadable" in str(unreadable.value)
    with pytest.raises(NotConnected) as nopath:
        call("paper.document", {}, base_config)
    assert "f18_docx_path_required" in str(nopath.value)


# --------------------------------------------------------------------------
# paper.pagination_reference（真实分页唯一参照：LibreOffice 渲染实测）
# --------------------------------------------------------------------------

def _soffice_ready() -> bool:
    return _resolve_soffice({"libreoffice_soffice": DEFAULT_SOFFICE}) \
        is not None


@pytest.mark.skipif(not _soffice_ready(), reason="LibreOffice NOT_INSTALLED")
def test_f18_reference_real_render_measured(workdir, base_config):
    ref = call("paper.pagination_reference",
               {"docx_path": str(workdir["docx"])}, base_config)
    assert ref["schema"] == "juscite-f18-paper-preview/1"
    # 真实分页：多页 PDF 实测（非 DOCX 数学推导非 CSS 近似）
    assert ref["page_count"] >= 2
    assert len(ref["pages"]) == ref["page_count"]
    assert ref["total_lines"] >= 60      # 每段至少一行，全覆盖
    assert all(p["line_count"] > 0 and p["first_line"] for p in ref["pages"])
    assert ref["engine"]["name"] == "libreoffice"
    assert ref["engine"]["version"]      # 实测 --version
    assert Path(ref["engine"]["binary"]).name.startswith("soffice")
    # 参照与预览的边界显式声明（不冒 CSS 预览）
    assert ref["disclaimer"] == "official_render_reference_not_css_preview"
    assert ref["reference_kind"] == "LibreOffice_PDF_render_measured_by_pdfium"
    assert (Path(base_config["paper_state_root"]) / "paper-preview"
            / ref["docx"]["content_digest"][:16] / "reference.pdf").is_file()
    # 同内容幂等复用（渲染一次；页数/逐页文本不变）
    again = call("paper.pagination_reference",
                 {"docx_path": str(workdir["docx"])}, base_config)
    assert again["reference"]["rendered"] == "reused"
    assert again["page_count"] == ref["page_count"]
    assert again["pages"] == ref["pages"]
    # 跨状态根（新渲染）：内容级复现——页数与逐页文本相等；PDF 字节不主张
    # 逐字节确定（内嵌时间戳元数据，如实记录 sha256 不断言相等）。
    other = dict(base_config,
                 paper_state_root=str(workdir["tmp"] / "state-b"))
    fresh = call("paper.pagination_reference",
                 {"docx_path": str(workdir["docx"])}, other)
    assert fresh["reference"]["rendered"] == "fresh"
    assert fresh["page_count"] == ref["page_count"]
    assert fresh["pages"] == ref["pages"]


@pytest.mark.skipif(not _soffice_ready(), reason="LibreOffice NOT_INSTALLED")
def test_f18_reference_negatives_typed(workdir):
    no_root = {"libreoffice_soffice": DEFAULT_SOFFICE}
    with pytest.raises(NotConnected) as noroot:
        call("paper.pagination_reference",
             {"docx_path": str(workdir["docx"])}, no_root)
    assert "f18_state_root_not_configured" in str(noroot.value)
    no_soffice = {"paper_state_root": str(workdir["tmp"] / "state")}
    with pytest.raises(NotConnected) as nosoffice:
        call("paper.pagination_reference",
             {"docx_path": str(workdir["docx"])}, no_soffice)
    assert "f18_soffice_not_configured" in str(nosoffice.value)


# --------------------------------------------------------------------------
# 桥面：方法组封闭（未知方法不在 paper.* 内＝既有 method_not_connected）
# --------------------------------------------------------------------------

def test_f18_bridge_frozen_method_group(workdir, base_config):
    with pytest.raises(NotConnected) as unknown:
        call("paper.repaginate", {"docx_path": str(workdir["docx"])},
             base_config)
    assert "method_not_connected:paper.repaginate" in str(unknown.value)
    with pytest.raises(NotConnected) as noargs:
        call("paper.document", None, base_config)
    assert "paper_params_invalid" in str(noargs.value)
