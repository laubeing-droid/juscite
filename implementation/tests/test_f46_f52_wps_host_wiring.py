# -*- coding: utf-8 -*-
"""W2b-U36 / F46·F52 wiring: WPS 宿主自动化半边（wpshost.* 桥方法组 →
wps_host 产品面 document-adapter，通道②）。

义务 06:F46/F52 17 卡断言：「公开 proposal/base refs→宿主原生定位/修订/
比对→部分接受/拒绝→重读实际文件→CAS/version→Harness 正式采用；不模拟
DOCX」＋「Word 与 WPS 真实接受后回读新 CAS/version，未接受不改 canonical」。
本测试文件只测产品桥与宿主面本体重（harness bake/索引失效/重载回流的
全链对账在 tools/PENDING_OWNER_f46_f52_wps_host_recon.py，验收口径以
recon 为准）。

- 语料全合成（自建带前手修订 DOCX：全部合成文本；00-总协调 §6.1
  裁决#1，绝无真实文档）。
- 真宿主测试：真 WPS COM 会话（KWPS.Application 独立进程）；未装
  pywin32/WPS＝整类诚实跳过（不假绿，同 F54 LibreOffice 先例）。
- Word 半边不在本面（§6.1 裁决#4：F46-word/F52-word 保持 NOT_RUN）。
"""
import base64
import io
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'python'))
from legal_entry import call, NotConnected, WPS_HOST_METHODS  # noqa: E402

_W_URI = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_W = "{%s}" % _W_URI
W = _W

PRIOR_INS = "（前手插入的合成句，作者=prior-author）"
PRIOR_DEL = "（前手删除的合成句，拒绝后回平文）"
BODY_TEXT = "合成正文段：W2b-U36 桥接测试全合成材料。"
PLAIN_2 = "合成正文第二段，与修订无涉。"


def _esc(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


def build_prior_revisions_docx() -> bytes:
    """全合成 DOCX：两正文段＋段内前手 w:ins(900)/w:del(901)。"""
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
        f'<w:document xmlns:w="{_W_URI}"><w:body>'
        f"<w:p><w:r><w:t>{_esc(BODY_TEXT)}</w:t></w:r></w:p>"
        f"<w:p><w:r><w:t>{_esc(PLAIN_2)}</w:t></w:r></w:p>"
        '<w:p><w:ins w:id="900" w:author="prior-author"'
        ' w:date="2026-09-01T00:00:00Z">'
        f"<w:r><w:t>{_esc(PRIOR_INS)}</w:t></w:r></w:ins></w:p>"
        '<w:p><w:del w:id="901" w:author="prior-author"'
        ' w:date="2026-09-02T00:00:00Z">'
        '<w:r><w:delText xml:space="preserve">'
        f"{_esc(PRIOR_DEL)}</w:delText></w:r></w:del></w:p>"
        "</w:body></w:document>")
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/'
        'content-types">'
        '<Default Extension="rels" ContentType="application/vnd.'
        'openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/'
        'vnd.openxmlformats-officedocument.wordprocessingml.document'
        '.main+xml"/></Types>')
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/'
        '2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/'
        'officeDocument/2006/relationships/officeDocument"'
        ' Target="word/document.xml"/></Relationships>')
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, payload in (("[Content_Types].xml", content_types),
                              ("_rels/.rels", rels),
                              ("word/document.xml", document)):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, payload.encode("utf-8"))
    return buffer.getvalue()


def _plain_of(raw: bytes) -> str:
    """现行平文（修订标记外）。"""
    from xml.etree import ElementTree as ET
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        root = ET.fromstring(zf.read("word/document.xml"))
    out = []

    def _collect(el):
        for child in el:
            if child.tag in (W + "ins", W + "del"):
                continue
            if child.tag == W + "t":
                out.append(child.text or "")
            _collect(child)
    _collect(root)
    return "".join(out)


def _marks_of(raw: bytes) -> tuple:
    from xml.etree import ElementTree as ET
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        root = ET.fromstring(zf.read("word/document.xml"))
    ins = sum(1 for _ in root.iter(W + "ins"))
    dele = sum(1 for _ in root.iter(W + "del"))
    return ins, dele


def _wps_config(state_root) -> dict:
    return {"wps_host_state_root": str(state_root)}


def _wps_installed() -> bool:
    try:
        import pythoncom  # noqa: F401
        import win32com.client  # noqa: F401
    except ImportError:
        return False
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'python'))
    from wps_host import wps_available, WpsHostError
    try:
        return bool(wps_available().get("installed"))
    except WpsHostError:
        return False


class F46F52MethodGroupTests(unittest.TestCase):
    """桥冻结面（无宿主依赖，任何环境必跑）。"""

    def test_method_group_frozen(self):
        self.assertEqual(WPS_HOST_METHODS, frozenset({
            "wpshost.available", "wpshost.review", "wpshost.decide"}))

    def test_unknown_method_refused(self):
        with self.assertRaises(NotConnected) as ctx:
            call("wpshost.bake", {}, _wps_config("whatever"))
        self.assertIn("method_not_connected", str(ctx.exception))

    def test_review_requires_state_root(self):
        payload = base64.b64encode(build_prior_revisions_docx()).decode()
        with self.assertRaises(NotConnected) as ctx:
            call("wpshost.review", {"docx_b64": payload}, {})
        self.assertIn("wps46_state_root_not_configured", str(ctx.exception))

    def test_decide_requires_state_root(self):
        payload = base64.b64encode(build_prior_revisions_docx()).decode()
        with self.assertRaises(NotConnected) as ctx:
            call("wpshost.decide", {"docx_b64": payload}, {})
        self.assertIn("wps46_state_root_not_configured", str(ctx.exception))

    def test_bad_payload_named_refusal(self):
        with tempfile.TemporaryDirectory(prefix="f46-neg-") as tmp:
            cfg = _wps_config(Path(tmp))
            with self.assertRaises(NotConnected) as ctx:
                call("wpshost.review", {"docx_b64": "not-base64!!"}, cfg)
            self.assertIn("wps46_docx_b64_invalid", str(ctx.exception))
            with self.assertRaises(NotConnected) as ctx:
                call("wpshost.review", {}, cfg)
            self.assertIn("wps46_docx_required", str(ctx.exception))
            with self.assertRaises(NotConnected) as ctx:
                call("wpshost.decide",
                     {"docx_b64": base64.b64encode(
                         build_prior_revisions_docx()).decode(),
                      "accept": [], "reject": []}, cfg)
            self.assertIn("wps46_decide_empty", str(ctx.exception))

    def test_selector_validation_named_refusals(self):
        payload = base64.b64encode(build_prior_revisions_docx()).decode()
        with tempfile.TemporaryDirectory(prefix="f46-sel-") as tmp:
            cfg = _wps_config(Path(tmp))
            for bad in ({"mode": "fuzzy", "text": "x"},
                        {"mode": "equals"},
                        {"mode": "equals", "text": ""},
                        {"mode": "equals", "text": "x", "type": "nonsense"}):
                with self.assertRaises(NotConnected) as ctx:
                    call("wpshost.decide",
                         {"docx_b64": payload, "accept": [bad],
                          "reject": []}, cfg)
                self.assertIn("wps46_selector", str(ctx.exception))
            with self.assertRaises(NotConnected) as ctx:
                call("wpshost.decide",
                     {"docx_b64": payload, "accept": "不是列表",
                      "reject": []}, cfg)
                self.assertIn("wps46_selectors_invalid", str(ctx.exception))


class F46F52WpsHostTests(unittest.TestCase):
    """真 WPS COM 会话（未装＝整类诚实跳过，不假绿）。"""

    @classmethod
    def setUpClass(cls):
        if not _wps_installed():
            raise unittest.SkipTest(
                "KWPS.Application / pywin32 不可用——真宿主面跳过（F54 "
                "LibreOffice 未装整类跳过同例）；方法组/负向在 "
                "F46F52MethodGroupTests 无宿主必跑")
        cls.tmp = Path(tempfile.mkdtemp(prefix="f46-wps-"))
        cls.cfg = _wps_config(cls.tmp)
        cls.docx = build_prior_revisions_docx()
        cls.payload = base64.b64encode(cls.docx).decode()

    def test_available_reports_host(self):
        probe = call("wpshost.available", {}, self.cfg)
        self.assertTrue(probe["installed"])
        self.assertEqual(probe["host"]["progid"], "KWPS.Application")
        self.assertTrue(probe["host"]["version"])

    def test_review_sees_native_revisions(self):
        review = call("wpshost.review", {"docx_b64": self.payload}, self.cfg)
        texts = [rev["text"] for rev in review["revisions"]]
        self.assertEqual(review["revision_count"], 2)
        self.assertTrue(any(PRIOR_INS in t for t in texts))
        self.assertTrue(any(PRIOR_DEL in t for t in texts))
        self.assertEqual({rev["author"] for rev in review["revisions"]},
                         {"prior-author"})
        types = {rev["type_name"] for rev in review["revisions"]}
        self.assertEqual(types, {"insert", "delete"})

    def test_decide_accept_and_reject_then_reread(self):
        decide = call("wpshost.decide", {
            "docx_b64": self.payload,
            "accept": [{"type": "insert", "mode": "contains",
                        "text": PRIOR_INS[:6]}],
            "reject": [{"type": "delete", "mode": "contains",
                        "text": PRIOR_DEL[:6]}]}, self.cfg)
        result = base64.b64decode(decide["result_docx_b64"])
        self.assertTrue(decide["acted_accept"])
        self.assertTrue(decide["acted_reject"])
        self.assertEqual(decide["remaining_count"], 0)
        ins, dele = _marks_of(result)
        self.assertEqual((ins, dele), (0, 0))
        plain = _plain_of(result)
        # 接受 ins＝新文入平文；拒绝 del＝旧文回平文（部分接受语义）
        self.assertIn(PRIOR_INS, plain)
        self.assertIn(PRIOR_DEL, plain)
        self.assertIn(BODY_TEXT, plain)
        # 重读实际文件＝盘上字节（sha 与产物一致）
        import hashlib
        self.assertEqual(decide["result_sha256"],
                         hashlib.sha256(result).hexdigest())

    def test_decide_reload_state_consistent(self):
        decide = call("wpshost.decide", {
            "docx_b64": self.payload,
            "accept": [{"type": "insert", "mode": "contains",
                        "text": PRIOR_INS[:6]}],
            "reject": []}, self.cfg)
        reload_view = call("wpshost.review", {
            "docx_b64": decide["result_docx_b64"]}, self.cfg)
        self.assertEqual(reload_view["revision_count"],
                         decide["remaining_count"])
        account = sorted((rev["type"], rev["text"])
                         for rev in decide["remaining_revisions"])
        reloaded = sorted((rev["type"], rev["text"])
                          for rev in reload_view["revisions"])
        self.assertEqual(account, reloaded)

    def test_decide_no_match_named_refusal(self):
        with self.assertRaises(NotConnected) as ctx:
            call("wpshost.decide", {
                "docx_b64": self.payload,
                "accept": [{"type": "insert", "mode": "equals",
                            "text": "文档中不存在的句子"}],
                "reject": []}, self.cfg)
        self.assertIn("wps46_no_revision_matched", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
