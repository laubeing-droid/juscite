# -*- coding: utf-8 -*-
"""W2b-U50 / F17-wps wiring: 原生前端栈复用 WPS 宿主面（wpssurface.* 桥
方法组 → wps_host_surface 产品面 document-adapter 家族）。

义务 06:F17（17 卡；host=wps 实例）断言：「用户已冻结OpenCode原生UI服务
闭包…法律WordWPS编辑独立，不第二DOCX编辑器」。本测试只测产品桥与承载面
本体（recon 双 profile 全链对账在
tools/PENDING_OWNER_f17_wps_host_surface_recon.py，验收口径以 recon 为准）。

- 语料全合成（自建带前手修订 DOCX：全部合成文本；00-总协调 §6.1 裁决#1，
  绝无真实文档）。
- 真宿主测试：真 WPS COM 会话（KWPS.Application 独立进程）；未装
  pywin32/WPS＝整类诚实跳过（不假绿，F46/F52 U36 先例）。
- 零编辑实现（不第二 DOCX 编辑器）＝AST 断言（无 SaveAs/Accept/Reject/
  TypeText/GetActiveObject；导入闭包封闭）；Word 半边不在本面（§6.1
  裁决#4：F17-word 保持 NOT_RUN，回收点 W2-S1/W4-S2）。
"""
import base64
import io
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'python'))
import legal_entry  # noqa: E402
from legal_entry import call, NotConnected, WPS_SURFACE_METHODS  # noqa: E402

_W_URI = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

CITE_SENTENCE = "本段引用《合成数据安全法》第三条作为合成引文。"
BODY_TEXT = "合成正文段（W2b-U50 桥接测试全合成材料）。"
PRIOR_INS = "（前手插入的合成句，作者=prior-author）"
PRIOR_DEL = "（前手删除的合成句，宿主可见形）"


def _esc(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


def build_docx(with_revisions: bool = True) -> bytes:
    """全合成 DOCX：引文段＋正文段（＋段内前手 w:ins/w:del 段内形）。"""
    body = [
        f'<w:p><w:r><w:t>{_esc(CITE_SENTENCE)}</w:t></w:r></w:p>',
        f'<w:p><w:r><w:t>{_esc(BODY_TEXT)}</w:t></w:r></w:p>',
    ]
    if with_revisions:
        body.append(
            '<w:p><w:ins w:id="900" w:author="prior-author"'
            ' w:date="2026-09-01T00:00:00Z">'
            f"<w:r><w:t>{_esc(PRIOR_INS)}</w:t></w:r></w:ins></w:p>")
        body.append(
            '<w:p><w:del w:id="901" w:author="prior-author"'
            ' w:date="2026-09-02T00:00:00Z">'
            '<w:r><w:delText xml:space="preserve">'
            f"{_esc(PRIOR_DEL)}</w:delText></w:r></w:del></w:p>")
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
        f'<w:document xmlns:w="{_W_URI}"><w:body>'
        + "".join(body) + "</w:body></w:document>")
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


def _payload(with_revisions: bool = True) -> str:
    return base64.b64encode(build_docx(with_revisions)).decode()


def _cfg(state_root) -> dict:
    return {"wps_host_state_root": str(state_root)}


def _items():
    return {
        "decision_items": [{"ref": {"owner": "harness", "kind": "proposal",
                                    "id": "fp-1", "version": "1"},
                            "state": "pending"}],
        "grid_items": [{"ref": {"owner": "harness", "kind": "cell",
                                "id": "c1", "version": "1"},
                        "cell": "[1,2]", "value": "1,234,567.89",
                        "support": "NO_STAMP"}],
        "citation_items": [{"ref": {"owner": "juscite", "kind": "citation",
                                    "id": "cit-1", "version": "1"},
                            "quote": "《合成数据安全法》第三条",
                            "status": "UNVERIFIED"}],
    }


def _wps_installed() -> bool:
    try:
        import pythoncom  # noqa: F401
        import win32com.client  # noqa: F401
    except ImportError:
        return False
    import wps_host
    try:
        return bool(wps_host.wps_available().get("installed"))
    except Exception:
        return False


class F17SurfaceMethodGroupTests(unittest.TestCase):
    """桥冻结面＋零编辑纪律（无宿主依赖，任何环境必跑）。"""

    def test_method_group_frozen(self):
        self.assertEqual(WPS_SURFACE_METHODS, frozenset({
            "wpssurface.available", "wpssurface.mount"}))

    def test_attach_method_not_connected(self):
        with self.assertRaises(NotConnected) as ctx:
            call("wpssurface.attach", {}, _cfg("whatever"))
        self.assertIn("method_not_connected:wpssurface.attach",
                      str(ctx.exception))

    def test_mount_requires_state_root(self):
        with self.assertRaises(NotConnected) as ctx:
            call("wpssurface.mount", {"docx_b64": _payload()}, {})
        self.assertIn("f17wps_state_root_not_configured", str(ctx.exception))

    def test_attach_attempts_named_refusal(self):
        with tempfile.TemporaryDirectory(prefix="f17-attach-") as tmp:
            for key in ("attach_running", "attach_existing",
                        "get_active_object"):
                with self.assertRaises(NotConnected) as ctx:
                    call("wpssurface.mount",
                         {"docx_b64": _payload(), key: True}, _cfg(tmp))
                self.assertIn("f17wps_attach_refused:" + key,
                              str(ctx.exception))
                with self.assertRaises(NotConnected) as ctx:
                    call("wpssurface.available", {key: True}, _cfg(tmp))
                self.assertIn("f17wps_attach_refused:" + key,
                              str(ctx.exception))

    def test_bad_payload_named_refusals(self):
        with tempfile.TemporaryDirectory(prefix="f17-payload-") as tmp:
            cfg = _cfg(tmp)
            for args, code in (
                    ({}, "f17wps_docx_required"),
                    ({"docx_b64": "not-base64!!"}, "f17wps_docx_b64_invalid"),
                    ({"docx_b64": base64.b64encode(b"JUNK").decode()},
                     "f17wps_docx_not_a_package")):
                with self.assertRaises(NotConnected) as ctx:
                    call("wpssurface.mount", dict(args, **_items()), cfg)
                self.assertIn(code, str(ctx.exception))

    def test_closed_set_named_refusals(self):
        """闭集外状态响亮拒（014 review-ops 投影纪律同款）。"""
        payload = _payload()
        with tempfile.TemporaryDirectory(prefix="f17-closed-") as tmp:
            cfg = _cfg(tmp)
            cases = [
                ({"decision_items": [{"ref": _ref(), "state": "approved"}]},
                 "f17wps_decision_state_invalid:approved"),
                ({"grid_items": [{"ref": _ref(), "cell": "[1,2]",
                                  "value": "1", "support": "VERIFIED"}]},
                 "f17wps_grid_support_invalid:VERIFIED"),
                ({"citation_items": [{"ref": _ref(), "quote": "引文",
                                      "status": "VERIFIED"}]},
                 "f17wps_citation_status_invalid:VERIFIED"),
                ({"decision_items": [{"ref": {"owner": "harness",
                                              "kind": "proposal"},
                                      "state": "pending"}]},
                 "f17wps_ref_invalid:decision"),
                ({"decision_items": "不是列表"}, "f17wps_decisions_invalid"),
                ({"grid_items": [None]}, "f17wps_grid_item_invalid"),
            ]
            for extra, code in cases:
                with self.assertRaises(NotConnected) as ctx:
                    call("wpssurface.mount",
                         dict({"docx_b64": payload}, **extra), cfg)
                self.assertIn(code, str(ctx.exception))

    def test_zero_edit_ast_discipline(self):
        """不第二 DOCX 编辑器＝AST 结构断言：零编辑实现＋无附着路径＋导入
        闭包（只看代码结构，注释/文档串不参与判定）。"""
        source = (Path(__file__).resolve().parents[1] / "python"
                  / "wps_host_surface.py").read_text(encoding="utf-8")
        import ast
        tree = ast.parse(source)
        forbidden_attrs = {"SaveAs", "SaveAs2", "Accept", "Reject",
                           "TypeText", "GetActiveObject", "AddOLEControl"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                self.assertNotIn(
                    node.attr, forbidden_attrs,
                    "编辑/附着实现出现于 AST: %s@%d" % (
                        node.attr, node.lineno))
            if isinstance(node, ast.Call):
                func = node.func
                name = func.id if isinstance(func, ast.Name) else (
                    func.attr if isinstance(func, ast.Attribute) else "")
                self.assertNotIn(
                    name, forbidden_attrs,
                    "编辑/附着调用出现于 AST: %s@%d" % (name, node.lineno))
        # 会话纪律沿用 U36：同一把进程内全局锁（wps_host._LOCK）
        self.assertTrue(any(
            isinstance(node, ast.Attribute) and node.attr == "_LOCK"
            and isinstance(node.value, ast.Name)
            and node.value.id == "wps_host"
            for node in ast.walk(tree)),
            "surface 会话未复用 wps_host._LOCK 全局串行锁")
        # 导入闭包封闭（stdlib＋wps_host 复用，零第二权威零编辑面）
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.add(node.module or "")
        self.assertTrue(imports <= {
            "__future__", "base64", "hashlib", "json", "tempfile", "uuid",
            "winreg", "contextlib", "pathlib", "wps_host"},
            "import closure drifted: %s" % sorted(imports))

    def test_projection_closed_sets_pinned(self):
        import wps_host_surface as surface
        self.assertEqual(
            surface.SUPPORT_STATUSES,
            frozenset({"SUPPORTED_CITATION_LEVEL", "UNSUPPORTED_REJECTED",
                       "STALE_CELL_ADVANCED", "INVALIDATED", "NO_STAMP"}))
        self.assertEqual(
            surface.DECISION_STATES,
            frozenset({"pending", "accepted", "rejected", "superseded"}))
        # 引用三态＝F87 闸闭集同源钉定（登记即 UNVERIFIED；本面不代签）
        from extraction_gate import GATE_STATUSES
        self.assertEqual(surface.CITATION_STATUSES, frozenset(GATE_STATUSES))
        self.assertEqual(surface.SECTION_KINDS,
                         frozenset({"revision", "decision", "grid",
                                    "citation"}))

    def test_panel_builder_deterministic(self):
        import wps_host_surface as surface
        revisions = [
            {"index": 1, "type": 1, "type_name": "insert",
             "author": "prior-author", "date": "d", "text": PRIOR_INS},
            {"index": 2, "type": 2, "type_name": "delete",
             "author": "prior-author", "date": "d", "text": PRIOR_DEL},
        ]
        lines_a = surface._panel_lines(revisions, [_decision()], [_grid()],
                                       [_citation()])
        lines_b = surface._panel_lines(revisions, [_decision()], [_grid()],
                                       [_citation()])
        self.assertEqual(lines_a, lines_b)
        self.assertEqual(surface.panel_sha256(lines_a),
                         surface.panel_sha256(lines_b))
        self.assertTrue(all(line["kind"] in surface.SECTION_KINDS
                            for line in lines_a))


def _ref():
    return {"owner": "harness", "kind": "proposal", "id": "fp-1",
            "version": "1"}


def _decision():
    return {"kind": "decision", "ref": _ref(), "state": "pending"}


def _grid():
    return {"kind": "grid", "ref": dict(_ref(), kind="cell", id="c1"),
            "cell": "[1,2]", "value": "1,234,567.89", "support": "NO_STAMP"}


def _citation():
    return {"kind": "citation", "ref": {"owner": "juscite",
                                        "kind": "citation", "id": "cit-1",
                                        "version": "1"},
            "quote": "《合成数据安全法》第三条", "status": "UNVERIFIED"}


class F17SurfaceWpsHostTests(unittest.TestCase):
    """真 WPS COM 会话（未装＝整类诚实跳过，不假绿）。"""

    @classmethod
    def setUpClass(cls):
        if not _wps_installed():
            raise unittest.SkipTest(
                "KWPS.Application / pywin32 不可用——真宿主承载面跳过"
                "（U36 先例）；方法组/负向/AST 在 F17SurfaceMethodGroupTests"
                " 无宿主必跑")
        cls.tmp = Path(tempfile.mkdtemp(prefix="f17-wps-"))
        cls.cfg = _cfg(cls.tmp)
        cls.payload = _payload(with_revisions=True)
        cls.clean_payload = _payload(with_revisions=False)

    def test_available_carrier_probe(self):
        probe = call("wpssurface.available", {}, self.cfg)
        self.assertTrue(probe["installed"])
        self.assertEqual(probe["host"]["progid"], "KWPS.Application")
        self.assertTrue(probe["carrier"]["probe_readback_equal"])
        self.assertEqual(probe["carrier"]["kind"], "commandbar")
        self.assertTrue(probe["carrier"]["temporary"])

    def test_mount_projects_four_sections_with_channel_crosscheck(self):
        # 通道对账：修订区＝wpshost.review（U36 已 VERIFIED 通道）同文档输出
        review = call("wpshost.review", {"docx_b64": self.payload}, self.cfg)
        out = call("wpssurface.mount",
                   dict({"docx_b64": self.payload}, **_items()), self.cfg)
        self.assertTrue(out["panel"]["readback_equal"])
        self.assertEqual(out["revision_count"], review["revision_count"])
        self.assertEqual(out["sections"],
                         {"revision": 2, "decision": 1, "grid": 1,
                          "citation": 1})
        expected = ["[修订]%d·%s·%s·%s" % (
            rev["index"], rev["type_name"], rev["author"], rev["text"])
            for rev in review["revisions"]]
        got = [line["caption"] for line in out["panel"]["lines"]
               if line["kind"] == "revision"]
        self.assertEqual(got, expected)
        self.assertIn("[决定]pending·harness:proposal:fp-1@v1",
                      out["panel"]["lines"][2]["caption"])
        self.assertIn("[格值][1,2]=1,234,567.89·支持=NO_STAMP",
                      out["panel"]["lines"][3]["caption"])
        self.assertIn("[引用]UNVERIFIED·《合成数据安全法》第三条",
                      out["panel"]["lines"][4]["caption"])
        import hashlib
        self.assertEqual(
            out["source_sha256"],
            hashlib.sha256(base64.b64decode(self.payload)).hexdigest())

    def test_mount_deterministic_across_sessions(self):
        args = dict({"docx_b64": self.payload}, **_items())
        first = call("wpssurface.mount", args, self.cfg)
        second = call("wpssurface.mount", args, self.cfg)
        self.assertEqual(first["panel"]["panel_sha256"],
                         second["panel"]["panel_sha256"])

    def test_mount_clean_doc_empty_panel_named_refusal(self):
        with self.assertRaises(NotConnected) as ctx:
            call("wpssurface.mount", {"docx_b64": self.clean_payload},
                 self.cfg)
        self.assertIn("f17wps_panel_empty", str(ctx.exception))

    def test_no_wps_named_refusal_real_registry(self):
        """未装＝注册表探针缺失先名于派发（真注册表查询真拒）。"""
        import wps_host_surface as surface
        self.assertTrue(surface._progid_registered("KWPS.Application"))
        self.assertFalse(surface._progid_registered(
            "KWPS.NotInstalled.Application"))
        with self.assertRaises(surface.WpsSurfaceError) as ctx:
            with surface._surface_session(
                    self.tmp, "neg",
                    launch={"progid": "KWPS.NotInstalled.Application"}):
                pass
        self.assertIn("f17wps_host_unavailable:no_wps", str(ctx.exception))

    def test_dispatch_refused_real_com(self):
        """COM 拒＝已注册 ProgID 在不可能启动上下文下真派发真拒
        （CLSCTX_INPROC_SERVER：KWPS 是本地服务器，无进程内类——真 COM
        拒绝，非模拟）。"""
        import pythoncom
        import wps_host_surface as surface
        with self.assertRaises(surface.WpsSurfaceError) as ctx:
            with surface._surface_session(
                    self.tmp, "neg",
                    launch={"clsctx": pythoncom.CLSCTX_INPROC_SERVER}):
                pass
        self.assertIn("f17wps_host_unavailable:dispatch_refused",
                      str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
