"""W5-U14 / F143 wiring: 法律写作校对插件（一致性/术语，定位原文可接受
拒绝）（proofing.* 桥方法组 → document_proofing 产品面 document-adapter
家族）。

义务 06:V7-143 断言（验收向量逐字）：「一致性/术语校对定位原文且可接受
拒绝；不同语义不自动合并」。红线：合并仅限逐条确定性同语义判定，语义
冲突候选必须留人。定位沿 F50/F51 引用原文重锚定纪律：禁偏移换算·不就
近匹配。语料全合成（00-总协调 §6.1 裁决#1）。
"""
import ast
import base64
import hashlib
import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'python'))
from legal_entry import call, NotConnected  # noqa: E402

MODULE_PATH = Path(__file__).resolve().parents[1] / 'python' \
    / 'document_proofing.py'


def _esc(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _p_xml(text: str) -> str:
    run = (f'<w:r><w:t xml:space="preserve">{_esc(text)}</w:t></w:r>'
           if text else "")
    return f"<w:p>{run}</w:p>"


def _tbl_xml(rows) -> str:
    grid = '<w:gridCol w:w="2400"/>' * len(rows[0])
    trs = []
    for row in rows:
        tcs = "".join(
            '<w:tc><w:tcPr><w:tcW w:w="2400" w:type="dxa"/></w:tcPr>'
            + _p_xml(cell) + "</w:tc>" for cell in row)
        trs.append(f"<w:tr>{tcs}</w:tr>")
    return ('<w:tbl><w:tblPr><w:tblW w:w="0" w:type="auto"/></w:tblPr>'
            f'<w:tblGrid>{grid}</w:tblGrid>{"".join(trs)}</w:tbl>')


BODY = [
    "合成测试合同（F143-TEST 编号 SYN-F143-T-001；全部当事人与金额均为虚构）",
    "第一条 甲方：合成当事人甲（虚构）。",
    "第二条 本合同总价款为人民币叁拾陆万元。",
    "第三条 乙方收取订金后三日内启动合成服务。",
    "第四条 订金以外的费用调整须经甲方书面同意。",
    "第五条 乙方经办人身份证号由甲方留存备查；合同金额小写360000元。",
]
TABLE = [["款项", "约定"], ["付款方式", "订金占比百分之三十"]]
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def build_docx(body_texts=BODY, table=TABLE, extra_paragraph=None) -> bytes:
    body = [_p_xml(t) for t in body_texts]
    if extra_paragraph is not None:
        body.append(_p_xml(extra_paragraph))
    body.insert(4, _tbl_xml(table))
    body.append('<w:sectPr><w:pgSz w:w="11906" w:h="16838"/></w:sectPr>')
    document = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                f'\r\n<w:document xmlns:w="{W_NS}"><w:body>{"".join(body)}'
                "</w:body></w:document>")
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/'
        'content-types"><Default Extension="rels" ContentType='
        '"application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType='
        '"application/vnd.openxmlformats-officedocument.'
        'wordprocessingml.document.main+xml"/></Types>')
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/'
        '2006/relationships"><Relationship Id="rId1" Type="http://schemas.'
        'openxmlformats.org/officeDocument/2006/relationships/officeDocument"'
        ' Target="word/document.xml"/></Relationships>')
    parts = {"[Content_Types].xml": content_types, "_rels/.rels": rels,
             "word/document.xml": document}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, text in parts.items():
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, text.encode("utf-8"))
    return buf.getvalue()


FIXTURE = build_docx()
B64 = base64.b64encode(FIXTURE).decode("ascii")


def _cfg(root) -> dict:
    return {"proofing_state_root": str(root)}


def _register(cfg, document_id="d-t", bytes_b64=B64):
    return call("proofing.register",
                {"document_id": document_id, "matter_id": "M-SYN",
                 "bytesB64": bytes_b64}, cfg)


def _cid(cands, rule_id, status):
    return next(c["candidate_id"] for c in cands["candidates"]
                if c["rule_id"] == rule_id and c["status"] == status)


class F143MethodGroupTests(unittest.TestCase):
    def test_method_group_frozen(self) -> None:
        self.assertEqual(
            legal_entry_PROOFING_METHODS(),
            {"proofing.register", "proofing.ruleset_read", "proofing.scan",
             "proofing.candidates", "proofing.decide", "proofing.propose",
             "proofing.proposal_read", "proofing.read_document",
             "proofing.list"})

    def test_bridge_dispatch_and_fail_closed(self) -> None:
        with self.assertRaises(NotConnected) as ctx:
            call("proofing.scan", {"document_id": "d"}, {})
        self.assertIn("f143_state_root_not_configured", str(ctx.exception))
        with self.assertRaises(NotConnected) as ctx:
            call("proofing.bake", {"document_id": "d"},
                 _cfg(tempfile.mkdtemp()))
        self.assertIn("method_not_connected:proofing.bake",
                      str(ctx.exception))


def legal_entry_PROOFING_METHODS():
    import legal_entry
    return set(legal_entry.PROOFING_METHODS)


class F143RegisterRulesetTests(unittest.TestCase):
    def test_ruleset_frozen_synthetic(self) -> None:
        view = call("proofing.ruleset_read", {}, {})
        recomputed = hashlib.sha256(json.dumps(
            list(__import__("document_proofing").RULESET),
            ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
        self.assertEqual(view["schema"], "juscite-f143-proofing/1")
        self.assertEqual(view["ruleset_sha256"], recomputed)
        self.assertEqual(len(view["rules"]), 5)
        self.assertTrue(all(r["kind"] in ("terminology", "consistency")
                            for r in view["rules"]))
        self.assertTrue(view["frozen"])
        self.assertEqual(view["author"], "lvyin-proofing")

    def test_register_idempotent_and_mismatch_refused(self) -> None:
        cfg = _cfg(tempfile.mkdtemp())
        reg = _register(cfg)
        self.assertFalse(reg["idempotent"])
        self.assertEqual(reg["sha256"], hashlib.sha256(FIXTURE).hexdigest())
        again = _register(cfg)
        self.assertTrue(again["idempotent"])
        with self.assertRaises(NotConnected) as ctx:
            _register(cfg, bytes_b64=base64.b64encode(
                build_docx(body_texts=BODY[:3])).decode("ascii"))
        self.assertIn("f143_document_bytes_mismatch", str(ctx.exception))
        with self.assertRaises(NotConnected) as ctx:
            _register(_cfg(tempfile.mkdtemp()), document_id="../escape")
        self.assertIn("f143_document_id_invalid", str(ctx.exception))


class F143ScanCandidatesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = _cfg(tempfile.mkdtemp())
        _register(self.cfg)

    def test_scan_verbatim_anchor_zero_position_on_ambiguous(self) -> None:
        # 重复段落（quote 双命中）→ T-02/C-04 歧义；无重复 fixture 歧义面
        # 用第二文档验证。
        scan = call("proofing.scan", {"document_id": "d-t"}, self.cfg)
        self.assertEqual(scan["counts"],
                         {"total": 7, "located": 7, "ambiguous": 0})
        for f in scan["findings"]:
            self.assertFalse(f["offset_conversion_used"])
            self.assertEqual(f["position_source"], "verbatim_quote_match")
            if f["location_status"] == "AMBIGUOUS":
                self.assertNotIn("locator", f)
                self.assertNotIn("trace_span", f)
        # 歧义构造：重复第五条 → T-02 两处发现 quote 双命中零位置字段
        cfg2 = _cfg(tempfile.mkdtemp())
        dup = build_docx(extra_paragraph=BODY[5])
        call("proofing.register",
             {"document_id": "d-dup", "bytesB64": base64.b64encode(
                 dup).decode("ascii")}, cfg2)
        scan2 = call("proofing.scan", {"document_id": "d-dup"}, cfg2)
        self.assertEqual(scan2["counts"],
                         {"total": 9, "located": 5, "ambiguous": 4})
        ambiguous = [f for f in scan2["findings"]
                     if f["location_status"] == "AMBIGUOUS"]
        self.assertEqual(len(ambiguous), 4)
        for f in ambiguous:
            self.assertNotIn("locator", f)
            self.assertNotIn("trace_span", f)
            self.assertGreaterEqual(f["quote_hits"], 2)

    def test_candidates_merge_conflict_needs_review(self) -> None:
        cands = call("proofing.candidates", {"document_id": "d-t"},
                     self.cfg)
        self.assertEqual(cands["state_counts"],
                         {"proposed": 4, "conflict": 2, "needs_review": 0})
        by = {c["rule_id"]: c for c in cands["candidates"]}
        # 合并红线：T-01 两处命中（第三条含收取订金＝冲突侧独立出候选；
        # 第四条＋表格单元格两处干净命中并同一条 proposed 候选）
        t01 = by["T-01"]
        self.assertEqual(t01["status"], "proposed")
        self.assertEqual(len(t01["occurrences"]), 2)
        self.assertEqual(t01["merge_key"], ["T-01", "订金", "定金"])
        self.assertEqual(t01["reason"], "merged_same_semantics_deterministic")
        # 语义冲突：T-01×T-05 重叠 span（收取订金⊃订金）各自独立候选互指
        conflicts = [c for c in cands["candidates"]
                     if c["status"] == "conflict"]
        self.assertEqual({c["rule_id"] for c in conflicts},
                         {"T-01", "T-05"})
        self.assertTrue(all(c["conflict_with"] for c in conflicts))
        # 冲突候选定位照给（冲突在语义不在位置）
        for c in conflicts:
            for occ in c["occurrences"]:
                self.assertIn("locator", occ)
                self.assertIn("trace_span", occ)
        # 确定性：candidates_sha256 与重算一致；双根同摘要
        self.assertEqual(
            cands["candidates_sha256"],
            hashlib.sha256(json.dumps(
                {k: v for k, v in cands.items()
                 if k != "candidates_sha256"},
                ensure_ascii=False, sort_keys=True)
                .encode("utf-8")).hexdigest())
        cfg2 = _cfg(tempfile.mkdtemp())
        _register(cfg2)
        cands2 = call("proofing.candidates", {"document_id": "d-t"}, cfg2)
        self.assertEqual(cands2["candidates_sha256"],
                         cands["candidates_sha256"])

    def test_needs_review_zero_position_merged_per_quote(self) -> None:
        cfg = _cfg(tempfile.mkdtemp())
        dup = build_docx(extra_paragraph=BODY[5])
        call("proofing.register",
             {"document_id": "d-dup", "bytesB64": base64.b64encode(
                 dup).decode("ascii")}, cfg)
        cands = call("proofing.candidates", {"document_id": "d-dup"}, cfg)
        self.assertEqual(cands["state_counts"],
                         {"proposed": 2, "conflict": 2, "needs_review": 2})
        needs = [c for c in cands["candidates"]
                 if c["status"] == "needs_review"]
        for c in needs:
            self.assertEqual(c["reason"],
                             "quote_not_unique_no_position_left_to_human")
            # 零位置字段：occurrences 仅携 quote＋finding_id（F50 红线）
            self.assertTrue(
                all(sorted(o.keys()) == ["finding_id", "quote"]
                    for o in c["occurrences"]))
            self.assertGreaterEqual(len(c["occurrences"]), 2)


class F143DecideProposeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = _cfg(tempfile.mkdtemp())
        _register(self.cfg)
        self.cands = call("proofing.candidates",
                          {"document_id": "d-t"}, self.cfg)

    def test_decision_ledger_append_only_idempotent(self) -> None:
        c01 = _cid(self.cands, "T-01", "proposed")
        first = call("proofing.decide",
                     {"document_id": "d-t", "candidate_id": c01,
                      "action": "accept", "actor_id": "lawyer-a"},
                     self.cfg)
        self.assertTrue(first["recorded"])
        repeat = call("proofing.decide",
                      {"document_id": "d-t", "candidate_id": c01,
                       "action": "accept", "actor_id": "lawyer-a"},
                      self.cfg)
        self.assertFalse(repeat["recorded"])
        self.assertTrue(repeat["idempotent"])
        flip = call("proofing.decide",
                    {"document_id": "d-t", "candidate_id": c01,
                     "action": "reject", "actor_id": "lawyer-a"}, self.cfg)
        self.assertTrue(flip["recorded"])
        with self.assertRaises(NotConnected) as ctx:
            call("proofing.decide",
                 {"document_id": "d-t", "candidate_id": "c-absent",
                  "action": "accept", "actor_id": "x"}, self.cfg)
        self.assertIn("f143_candidate_unknown", str(ctx.exception))
        with self.assertRaises(NotConnected) as ctx:
            call("proofing.decide",
                 {"document_id": "d-t", "candidate_id": c01,
                  "action": "maybe", "actor_id": "x"}, self.cfg)
        self.assertIn("f143_action_invalid", str(ctx.exception))

    def test_conflict_both_accepted_propose_refused(self) -> None:
        # 红线：语义冲突候选必须留人——两条冲突候选同受＝propose 具名拒
        call("proofing.decide",
             {"document_id": "d-t", "candidate_id": _cid(self.cands,
                                                         "T-01", "conflict"),
              "action": "accept", "actor_id": "lawyer-a"}, self.cfg)
        call("proofing.decide",
             {"document_id": "d-t", "candidate_id": _cid(self.cands,
                                                         "T-05", "conflict"),
              "action": "accept", "actor_id": "lawyer-a"}, self.cfg)
        with self.assertRaises(NotConnected) as ctx:
            call("proofing.propose", {"document_id": "d-t"}, self.cfg)
        self.assertIn("f143_conflict_candidates_accepted",
                      str(ctx.exception))

    def test_propose_ops_and_real_docx(self) -> None:
        call("proofing.decide",
             {"document_id": "d-t", "candidate_id": _cid(self.cands,
                                                         "T-01", "conflict"),
              "action": "reject", "actor_id": "lawyer-a"}, self.cfg)
        for rule in ("T-01", "C-03", "C-04", "T-02"):
            call("proofing.decide",
                 {"document_id": "d-t",
                  "candidate_id": _cid(self.cands, rule, "proposed"),
                  "action": "accept", "actor_id": "lawyer-a"}, self.cfg)
        prop = call("proofing.propose", {"document_id": "d-t"}, self.cfg)
        ops = prop["proposal"]["ops"]
        self.assertEqual(
            ops,
            [{"op": "body.replace_text", "index": 2,
              "text": BODY[2].replace("叁拾陆万元", "叁拾陆万元整")},
             {"op": "table.cell_text", "table": 0, "row": 1, "col": 1,
              "text": "定金占比百分之三十"},
             {"op": "body.replace_text", "index": 4,
              "text": BODY[4].replace("订金", "定金")},
             {"op": "body.replace_text", "index": 5,
              "text": BODY[5].replace("身份证号", "公民身份号码")
              .replace("360000", "360,000.00")}])
        # 真实 DOCX：非 document.xml 部件逐字节保真
        from document_redline import _read_package_bytes
        from edits_protocol import build_text_index
        orig = _read_package_bytes(FIXTURE)
        corrected = _read_package_bytes(base64.b64decode(
            call("proofing.read_document", {"document_id": "d-t"},
                 self.cfg)["bytesB64"]))
        self.assertTrue(all(orig["parts"][n] == corrected["parts"][n]
                            for n in orig["parts"]
                            if n != "word/document.xml"))
        text, _ = build_text_index(corrected["trees"]["word/document.xml"])
        self.assertIn("叁拾陆万元整", text)
        # 被拒候选（T-01 冲突侧＝第三条）原文零动（人说不＝文档不动）
        self.assertIn("收取订金", text)
        self.assertIn("定金占比百分之三十", text)
        self.assertIn("公民身份号码", text)
        self.assertIn("360,000.00", text)
        # 幂等重提案同 id 同 corrected sha
        again = call("proofing.propose", {"document_id": "d-t"}, self.cfg)
        self.assertTrue(again["idempotent"])
        self.assertEqual(again["proposal"]["proposal_id"],
                         prop["proposal"]["proposal_id"])
        # proposal_read 回读一致
        read = call("proofing.proposal_read", {"document_id": "d-t"},
                    self.cfg)
        self.assertEqual(read["proposal_id"],
                         prop["proposal"]["proposal_id"])
        self.assertEqual(read["corrected_on_disk_sha256"],
                         prop["proposal"]["corrected"]["sha256"])

    def test_reanchor_verbatim_not_offset_conversion(self) -> None:
        # F50 纪律：propose 对已接受候选逐条 quote 重搜（唯一命中才取位）；
        # 文本漂移（quote 不再唯一/不在）＝具名拒不猜改。直接以双命中文档
        # 验证：接受 proposed T-01（其 occurrence quote 在重复文档中唯一）
        # 后篡改状态根不可行——改以 needs_review 候选接受路径验证零位置
        # 不自动应用。
        cfg = _cfg(tempfile.mkdtemp())
        dup = build_docx(extra_paragraph=BODY[5])
        call("proofing.register",
             {"document_id": "d-dup", "bytesB64": base64.b64encode(
                 dup).decode("ascii")}, cfg)
        cands = call("proofing.candidates", {"document_id": "d-dup"}, cfg)
        call("proofing.decide",
             {"document_id": "d-dup",
              "candidate_id": _cid(cands, "T-02", "needs_review"),
              "action": "accept", "actor_id": "lawyer-a"}, cfg)
        with self.assertRaises(NotConnected) as ctx:
            call("proofing.propose", {"document_id": "d-dup"}, cfg)
        self.assertIn("f143_candidate_not_located", str(ctx.exception))

    def test_determinism_two_roots(self) -> None:
        call("proofing.decide",
             {"document_id": "d-t", "candidate_id": _cid(self.cands,
                                                         "T-01", "conflict"),
              "action": "reject", "actor_id": "lawyer-a"}, self.cfg)
        for rule in ("T-01", "C-03"):
            call("proofing.decide",
                 {"document_id": "d-t",
                  "candidate_id": _cid(self.cands, rule, "proposed"),
                  "action": "accept", "actor_id": "lawyer-a"}, self.cfg)
        p1 = call("proofing.propose", {"document_id": "d-t"}, self.cfg)
        cfg2 = _cfg(tempfile.mkdtemp())
        _register(cfg2)
        cands2 = call("proofing.candidates", {"document_id": "d-t"}, cfg2)
        call("proofing.decide",
             {"document_id": "d-t", "candidate_id": _cid(cands2,
                                                         "T-01", "conflict"),
              "action": "reject", "actor_id": "lawyer-a"}, cfg2)
        for rule in ("T-01", "C-03"):
            call("proofing.decide",
                 {"document_id": "d-t",
                  "candidate_id": _cid(cands2, rule, "proposed"),
                  "action": "accept", "actor_id": "lawyer-a"}, cfg2)
        p2 = call("proofing.propose", {"document_id": "d-t"}, cfg2)

        def strip(node):
            if isinstance(node, dict):
                return {k: strip(v) for k, v in node.items()
                        if not k.endswith("_utc")}
            if isinstance(node, list):
                return [strip(v) for v in node]
            return node
        self.assertEqual(json.dumps(strip(p1["proposal"]), sort_keys=True),
                         json.dumps(strip(p2["proposal"]), sort_keys=True))


class F143AstDisciplineTests(unittest.TestCase):
    def test_import_closure_and_no_fuzzy_network(self) -> None:
        tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
        allowed = {"__future__", "hashlib", "json", "os", "re", "threading",
                   "datetime", "pathlib", "base64", "edits_protocol",
                   "document_redline"}
        self.assertTrue(imports <= allowed, sorted(imports))
        self.assertFalse(imports & {"random", "urllib", "socket", "http",
                                    "requests", "difflib", "subprocess"})
        calls = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = getattr(node.func, "id", None) \
                    or getattr(node.func, "attr", None)
                if name:
                    calls.add(name)
        # 不就近匹配＝结构性缺席（非阈值 0）
        self.assertFalse(calls & {"get_close_matches", "SequenceMatcher",
                                  "fuzz"})

    def test_error_codes_never_carry_material(self) -> None:
        cfg = _cfg(tempfile.mkdtemp())
        fragments = ("订金", "定金", "叁拾陆", "360000", "身份证号")
        codes = []
        for method, args in (
                ("proofing.scan", {"document_id": "d-absent"}),
                ("proofing.proposal_read", {"document_id": "d-absent"}),
                ("proofing.decide", {"document_id": "d-absent",
                                     "candidate_id": "c-x",
                                     "action": "accept",
                                     "actor_id": "x"})):
            try:
                call(method, args, cfg)
            except NotConnected as exc:
                codes.append(str(exc))
        for code in codes:
            for fragment in fragments:
                self.assertNotIn(fragment, code)


if __name__ == "__main__":
    unittest.main()
