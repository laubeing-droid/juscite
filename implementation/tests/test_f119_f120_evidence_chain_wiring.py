"""F119+F120 产品侧接线测试（W4-U51）：证据→质证链。

全部合成材料。legal_entry 新增 HARNESS_EVIDENCE_CHAIN_METHODS 九方法组
（--evidencechain-json 封闭信封）＋EVIDENCECAT_METHODS/CROSSEXAM_METHODS
两个产品面方法组。真 public_entry 全链实跑对账在
tools/PENDING_OWNER_f119_f120_evidence_chain_recon.py；本文件用 seam 注
入（subprocess mock＋产品面 bridge seam），单测零仓依赖。

fail-closed 主断言（06 acceptance 的产品半边）：
  - 空证据不编质证：crossexam_empty_evidence_no_fabrication；
  - 无 ref 的主张不生成：crossexam_claim_ref_required；
  - 引用过 F87 闸：闸拒＝整单具名拒（crossexam_gate_rejected）；
  - 目录真实生成：空目录具名拒（f119_empty_catalog_no_fabrication）；
  - F53 作者：crossexam→lvyin-cross-exam 闭集绑定（冒律师名具名拒）。
"""

from __future__ import annotations

import base64
import io
import json
import sys
import unittest
import unittest.mock
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

import legal_entry  # noqa: E402
from bridge_errors import HarnessCommandError, NotConnected  # noqa: E402

CONFIG = {
    "harness_public_entry": "X:/synth/harness/public_entry.py",
    "harness_target": "opencode",
    "harness_state_root": "X:/synth/state-root",
    "harness_python": sys.executable,
}
EVIDENCE_CHAIN_METHODS = (
    "harness.evidence_register", "harness.evidence_read",
    "harness.evidence_list", "harness.evidence_media_op_record",
    "harness.evidence_media_op_read", "harness.evidence_media_op_list",
    "harness.cross_exam_draft_record", "harness.cross_exam_read",
    "harness.cross_exam_list",
)


def patch_execute(testcase, *, stdout="", returncode=0, calls=None):
    def _fake(argv, env, timeout):
        if calls is not None:
            calls.append({"argv": argv, "env": env})
        return SimpleNamespace(stdout=stdout, returncode=returncode)
    patcher = unittest.mock.patch.object(legal_entry, "_execute", _fake)
    patcher.start()
    testcase.addCleanup(patcher.stop)


def evidencechain_output(result):
    return json.dumps({"surface": "evidencechain", "method": "synthetic",
                       "result": result})


class F119F120BridgeTests(unittest.TestCase):
    """legal_entry 方法组：白名单、evidencechain 信封、fail-closed。"""

    def test_method_groups_membership(self) -> None:
        self.assertEqual(legal_entry.HARNESS_EVIDENCE_CHAIN_METHODS,
                         frozenset(EVIDENCE_CHAIN_METHODS))
        # 账本面没有"生成/决定"方法——生成与人审决定在产品面/既有面。
        self.assertNotIn("harness.evidence_generate",
                         legal_entry.HARNESS_EVIDENCE_CHAIN_METHODS)
        self.assertNotIn("harness.cross_exam_decide",
                         legal_entry.HARNESS_EVIDENCE_CHAIN_METHODS)
        self.assertEqual(legal_entry.EVIDENCECAT_METHODS, frozenset({
            "evidencecat.generate", "evidencecat.read", "evidencecat.list",
            "evidencecat.media_probe", "evidencecat.media_process",
            "evidencecat.media_read"}))
        self.assertEqual(legal_entry.CROSSEXAM_METHODS, frozenset({
            "crossexam.generate", "crossexam.decide", "crossexam.read"}))

    def test_all_methods_ride_evidencechain_envelope(self) -> None:
        for method in EVIDENCE_CHAIN_METHODS:
            with self.subTest(method=method):
                calls: list = []
                patch_execute(
                    self, stdout=evidencechain_output({"ok": True}),
                    returncode=0, calls=calls)
                out = legal_entry.call(method, {"scope": {"kind": "matter",
                                                          "matterId": "m"}},
                                       CONFIG)
                self.assertEqual(out, {"ok": True})
                argv = calls[0]["argv"]
                self.assertIn("--evidencechain-json", argv)
                self.assertIn("--target", argv)

    def test_bridge_fail_closed_without_config(self) -> None:
        for method in EVIDENCE_CHAIN_METHODS:
            with self.subTest(method=method):
                with self.assertRaises(NotConnected) as caught:
                    legal_entry.call(method, {"scope": {}}, {})
                self.assertIn("harness_public_entry_not_configured",
                              str(caught.exception))

    def test_envelope_error_surfaces_typed_code(self) -> None:
        patch_execute(self, stdout=json.dumps(
            {"status": "FAIL", "error": "f119_material_ref_not_found:x"}),
            returncode=1)
        with self.assertRaises(HarnessCommandError) as caught:
            legal_entry.call("harness.evidence_register", {}, CONFIG)
        self.assertIn("f119_material_ref_not_found", str(caught.exception))

    def test_product_face_fail_closed_named(self) -> None:
        # 产品面错误码经 NotConnected 具名透传（不携材料内容）。
        patch_execute(self, stdout="", returncode=0)
        with self.assertRaises(NotConnected) as caught:
            legal_entry.call("evidencecat.generate", {}, CONFIG)
        self.assertIn("evidencecat_failed:f119_matter_id_invalid",
                      str(caught.exception))
        with self.assertRaises(NotConnected) as caught:
            legal_entry.call("crossexam.generate", {}, CONFIG)
        self.assertIn("crossexam_failed:crossexam_matter_id_invalid",
                      str(caught.exception))
        with self.assertRaises(NotConnected) as caught:
            legal_entry.call("evidencecat.explode", {}, CONFIG)
        # 白名单外方法在桥层即具名拒（不落产品面）。
        self.assertIn("method_not_connected:evidencecat.explode",
                      str(caught.exception))
        with self.assertRaises(NotConnected) as caught:
            legal_entry.call("crossexam.explode", {}, CONFIG)
        self.assertIn("method_not_connected:crossexam.explode",
                      str(caught.exception))


class F119F120AuthorPolicyTests(unittest.TestCase):
    """F53 作者闭集扩展：crossexam→lvyin-cross-exam。"""

    def test_crossexam_channel_bound(self) -> None:
        from author_policy import (AuthorPolicyError, CHANNEL_AUTHORS,
                                   check_revision_author)
        self.assertEqual(CHANNEL_AUTHORS["crossexam"], "lvyin-cross-exam")
        binding = check_revision_author("crossexam", "lvyin-cross-exam")
        self.assertEqual(binding, {"channel": "crossexam",
                                   "author": "lvyin-cross-exam",
                                   "kind": "machine"})
        with self.assertRaises(AuthorPolicyError) as caught:
            check_revision_author("crossexam", "律师甲（合成）")
        self.assertIn("f53_author_impersonation", str(caught.exception))
        with self.assertRaises(AuthorPolicyError) as caught:
            check_revision_author("crossexam", "lvyin-redline")
        self.assertIn("f53_author_channel_mismatch", str(caught.exception))


class F119F120FaceChainTests(unittest.TestCase):
    """产品面全链（seam 注入直接 units；合成 DOCX/PDF 夹具）。"""

    def setUp(self) -> None:
        import tempfile
        self._tmp = tempfile.TemporaryDirectory(prefix="f119f120-wire-")
        self.addCleanup(self._tmp.cleanup)
        state = Path(self._tmp.name)
        self.state = state

        sys.path.insert(0, str(_harness_root() / "src"))
        from legal_harness.business.units import HarnessUnits
        from legal_harness.state.matter_store import MatterStore
        self.store = MatterStore(state / "matter")
        self.units = HarnessUnits(self.store)
        self.matter = "m-wire"
        self.store.create_matter(self.matter, "cas://wire")
        scope = {"kind": "matter", "matterId": self.matter}
        self.scope = scope

        def key(rid):
            return {"requestId": rid, "targetId": None,
                    "expectedRevision": None, "inputRefs": []}
        self.key = key

        mini_pdf = (b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\n"
                    b"endobj\n2 0 obj\n<< /Type /Pages /Kids [3 0 R] "
                    b"/Count 1 >>\nendobj\n3 0 obj\n<< /Type /Page "
                    b"/Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\n"
                    b"trailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n9\n"
                    b"%%EOF\n")
        self.units.register_material(
            "lawyer-1", scope, key("m1"),
            {"id": "mat-src-1", "kind": "scan", "title": "证据源（合成）",
             "bytesB64": base64.b64encode(mini_pdf).decode()})
        self.units.save_issue(
            "lawyer-1", scope, key("i1"),
            {"id": "iss-1", "revision": 1, "title": "对方主张已付清（合成）",
             "claimRefs": [], "factRefs": [], "partyIds": ["p-def"]})
        self.units.evidence_register(
            "lawyer-1", scope, key("e1"),
            {"evidenceId": "ev-1", "evidenceNo": "原告证据一",
             "name": "购销合同（合成）", "kind": "documentary",
             "sourceParty": "plaintiff",
             "materialRef": {"materialId": "mat-src-1", "revision": 1},
             "pageSegments": [{"docId": "doc-1", "pageFrom": 1,
                               "pageTo": 1}],
             "proveFacts": ["证明合同关系（合成）"]})

        # E12 解析产物（documented 布局最小夹具）。
        batch_dir = state / "material-parse" / "b-wire" / "doc-1"
        batch_dir.mkdir(parents=True)
        (state / "material-parse" / "b-wire" / "batch.json").write_text(
            json.dumps({"batch_id": "b-wire", "documents": [
                {"doc_id": "doc-1", "page_count": 1,
                 "pages": [{"page": 1, "signal": "READ_OK"}]}]},
                ensure_ascii=False), encoding="utf-8")
        (batch_dir / "page-0001.json").write_text(json.dumps(
            {"page": 1, "signal": "READ_OK",
             "page_no": {"versions": [{"version": 1, "source": "engine",
                                       "text": "1", "bbox": None,
                                       "confidence": 0.99}],
                         "current_version": 1}}, ensure_ascii=False),
            encoding="utf-8")

        self.config = {
            "evidence_catalog_state_root": str(state / "cat"),
            "cross_exam_state_root": str(state / "cx"),
            "extraction_gate_state_root": str(state / "gate"),
            "material_parse_state_root": str(state),
            # 闸面不在此文件实跑（真 codices 钉定面在 recon）；引用主张
            # 路径以闸拒注入断言（fail-closed 结构性）。
            "codices_import_path": "X:/synth/codices-repo",
            "codices_formal_root": "X:/synth/codices",
        }
        self._patch_bridges()

    def _patch_bridges(self) -> None:
        units, key = self.units, self.key
        bound = {
            "harness.evidence_list": lambda a: units.evidence_list(**a),
            "harness.evidence_read": lambda a: units.evidence_read(**a),
            "harness.evidence_media_op_list":
                lambda a: units.evidence_media_op_list(**a),
            "harness.evidence_media_op_record":
                lambda a: units.evidence_media_op_record(**a),
            "harness.evidence_media_op_read":
                lambda a: units.evidence_media_op_read(**a),
            "harness.cross_exam_list": lambda a: units.cross_exam_list(**a),
            "harness.cross_exam_read": lambda a: units.cross_exam_read(**a),
            "harness.cross_exam_draft_record":
                lambda a: units.cross_exam_draft_record(**a),
            "harness.read_material": lambda a: units.read_material(**a),
            "harness.register_material":
                lambda a: units.register_material(**a),
            "harness.formal_propose": lambda a: units.formal_propose(**a),
            "harness.formal_decide": lambda a: units.formal_decide(**a),
            "harness.formal_proposal_list":
                lambda a: units.formal_proposal_list(**a),
        }

        def direct_bridge(method, args, config):
            if method in bound:
                return bound[method](args)
            import legal_entry as le
            return le.call(method, args, config)

        import evidence_catalog as ec
        import cross_exam as cx
        for module in (ec, cx):
            patcher = unittest.mock.patch.object(module, "_bridge_call",
                                                 direct_bridge)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.ec, self.cx = ec, cx

    # -- F119 ---------------------------------------------------------------

    def test_f119_generate_gate_and_replay(self) -> None:
        out = self.ec.generate(self.config, {
            "matter_id": self.matter, "parse_batch_id": "b-wire",
            "request_id": "r-cat"})
        self.assertEqual(out["rows"], 1)
        replay = self.ec.generate(self.config, {
            "matter_id": self.matter, "parse_batch_id": "b-wire",
            "request_id": "r-cat"})
        self.assertEqual(out, replay)
        read = self.ec.read_output(self.config, {
            "matter_id": self.matter, "request_id": "r-cat"})
        payload = base64.b64decode(read["docx_b64"])
        import docx as pydocx
        doc = pydocx.Document(io.BytesIO(payload))
        table = doc.tables[0]
        self.assertEqual(
            [c.text for c in table.rows[0].cells],
            ["证据编号", "证据名称", "证据形式", "举证方", "页段",
             "待证事项", "媒体加工", "关联质证"])
        self.assertEqual(table.rows[1].cells[0].text, "原告证据一")
        self.assertEqual(table.rows[1].cells[4].text, "doc-1 第1-1页")

    def test_f119_empty_catalog_refused(self) -> None:
        self.store.create_matter("m-none", "cas://none")
        with self.assertRaises(self.ec.EvidenceCatalogError) as caught:
            self.ec.generate(self.config, {
                "matter_id": "m-none", "parse_batch_id": "b-wire",
                "request_id": "r-none"})
        self.assertIn("f119_empty_catalog_no_fabrication",
                      str(caught.exception))

    def test_f119_segment_binding_fail_closed(self) -> None:
        with self.assertRaises(self.ec.EvidenceCatalogError) as caught:
            self.ec.generate(self.config, {
                "matter_id": self.matter, "parse_batch_id": "b-missing",
                "request_id": "r-x"})
        self.assertIn("f119_parse_batch_not_registered", str(caught.exception))

    def test_f119_media_pdf_to_image_real_run(self) -> None:
        try:
            import pypdfium2  # noqa: F401
        except ImportError:
            self.skipTest("pypdfium2 unavailable")
        res = self.ec.media_process(self.config, {
            "matter_id": self.matter, "media_op_id": "mo-1",
            "actor_id": "assistant-1", "evidence_id": "ev-1",
            "op_kind": "pdf_to_image",
            "source": {"material_id": "mat-src-1", "revision": 1},
            "dpi": 150, "pages": [1]})
        self.assertEqual(len(res["outputs"]), 1)
        read = self.ec.media_read(self.config, {
            "matter_id": self.matter, "media_op_id": "mo-1"})
        self.assertEqual(read["outputs"][0]["sha256"],
                         res["outputs"][0]["sha256"])
        # 二次加工同参数同字节（确定性渲染）。
        res2 = self.ec.media_process(self.config, {
            "matter_id": self.matter, "media_op_id": "mo-2",
            "actor_id": "assistant-1", "evidence_id": "ev-1",
            "op_kind": "pdf_to_image",
            "source": {"material_id": "mat-src-1", "revision": 1},
            "dpi": 150, "pages": [1]})
        self.assertEqual(res2["outputs"][0]["sha256"],
                         res["outputs"][0]["sha256"])

    def test_f119_media_unknown_evidence_refused(self) -> None:
        with self.assertRaises(self.ec.EvidenceCatalogError) as caught:
            self.ec.media_process(self.config, {
                "matter_id": self.matter, "media_op_id": "mo-x",
                "actor_id": "assistant-1", "evidence_id": "ev-none",
                "op_kind": "pdf_to_image",
                "source": {"material_id": "mat-src-1", "revision": 1},
                "dpi": 150, "pages": [1]})
        self.assertIn("f119_evidence_unresolved:evidence_not_found",
                      str(caught.exception))

    # -- F120 ---------------------------------------------------------------

    def test_f120_empty_evidence_and_missing_ref_refused(self) -> None:
        self.store.create_matter("m-empty", "cas://empty")
        with self.assertRaises(self.cx.CrossExamError) as caught:
            self.cx.generate(self.config, {
                "matter_id": "m-empty", "opinion_id": "cx-e",
                "request_id": "r-e", "actor_id": "a",
                "claims": [{"claim_id": "c", "evidence_id": "ev-1",
                            "counter_issue_id": "iss-1",
                            "position": "authenticity", "text": "x"}]})
        self.assertIn("crossexam_empty_evidence_no_fabrication",
                      str(caught.exception))
        with self.assertRaises(self.cx.CrossExamError) as caught:
            self.cx.generate(self.config, {
                "matter_id": self.matter, "opinion_id": "cx-r",
                "request_id": "r-r", "actor_id": "a",
                "claims": [{"claim_id": "c", "evidence_id": "ev-1",
                            "position": "authenticity", "text": "x"}]})
        self.assertIn("crossexam_claim_ref_required", str(caught.exception))

    def test_f120_citation_gate_required_and_refused(self) -> None:
        # 引用主张缺 as_of＝具名拒（效力时点不猜）。
        with self.assertRaises(self.cx.CrossExamError) as caught:
            self.cx.generate(self.config, {
                "matter_id": self.matter, "opinion_id": "cx-a",
                "request_id": "r-a", "actor_id": "a",
                "claims": [{"claim_id": "c", "evidence_id": "ev-1",
                            "counter_issue_id": "iss-1",
                            "position": "legality",
                            "text": "依据《中华人民共和国个人信息保护法》"
                                    "第一条（合成）。"}]})
        self.assertIn("crossexam_gate_as_of_required", str(caught.exception))
        # 引用主张过闸：钉定面缺失＝闸不开（fail-closed，不假 CITATION_*
        # VERIFIED）。
        with self.assertRaises(NotConnected):
            self.cx.generate(self.config, {
                "matter_id": self.matter, "opinion_id": "cx-b",
                "request_id": "r-b", "actor_id": "a",
                "as_of": "20261021",
                "claims": [{"claim_id": "c", "evidence_id": "ev-1",
                            "counter_issue_id": "iss-1",
                            "position": "legality",
                            "text": "依据《中华人民共和国个人信息保护法》"
                                    "第一条（合成）。"}]})

    def test_f120_plain_chain_full_and_decide(self) -> None:
        res = self.cx.generate(self.config, {
            "matter_id": self.matter, "opinion_id": "cx-1",
            "request_id": "r-1", "actor_id": "assistant-1",
            "claims": [{"claim_id": "c-1", "evidence_id": "ev-1",
                        "counter_issue_id": "iss-1",
                        "position": "authenticity",
                        "text": "该证据形式完整，真实性无异议（合成）。"}]})
        self.assertEqual(res["claims_recorded"], 1)
        read = self.cx.read(self.config, {
            "matter_id": self.matter, "opinion_id": "cx-1"})
        row = read["author_decision_projection"]["rows"][0]
        self.assertEqual(row["author"], "lvyin-cross-exam")
        self.assertEqual(row["state"], "pending")
        # 律师终审：accept 必带编辑后字节；决定引用必带。
        import docx as pydocx
        opinion_path = (Path(self.state) / "cx" / "cross-exam" / self.matter
                        / "outputs" / "0001" / "opinion.docx")
        doc = pydocx.Document(str(opinion_path))
        doc.paragraphs[0].runs[0].text = "质证意见（终审）"
        buf = io.BytesIO()
        doc.save(buf)
        with self.assertRaises(self.cx.CrossExamError) as caught:
            self.cx.decide(self.config, {
                "matter_id": self.matter, "request_id": "r-d0",
                "actor_id": "lawyer-1", "proposal_id": res["proposal_id"],
                "material_id": res["material_id"], "action": "accept"})
        self.assertIn("crossexam_decision_ref_required",
                      str(caught.exception))
        dec = self.cx.decide(self.config, {
            "matter_id": self.matter, "request_id": "r-d1",
            "actor_id": "lawyer-1", "proposal_id": res["proposal_id"],
            "material_id": res["material_id"], "action": "accept",
            "reason_ref": {"owner": "host", "kind": "decision",
                           "id": "dr-1", "version": "1"},
            "receipt_ref": {"owner": "host", "kind": "receipt",
                            "id": "rcpt-1", "version": "1"},
            "result_bytes_b64": base64.b64encode(buf.getvalue())
            .decode("ascii")})
        self.assertIn("canonical", dec)
        read2 = self.cx.read(self.config, {
            "matter_id": self.matter, "opinion_id": "cx-1"})
        row2 = read2["author_decision_projection"]["rows"][0]
        self.assertEqual(row2["state"], "accepted")
        self.assertTrue(row2.get("decision"))
        self.assertEqual(
            read2["author_decision_projection"]["canonical"]["source"],
            "user_accept")


def _harness_root() -> Path:
    import os
    env = os.environ.get("JUSCITE_W4U51_HARNESS_ROOT")
    if env:
        return Path(env)
    root = Path(__file__).resolve().parent
    for _ in range(8):
        if root.name == "jusbench工作区":
            guess = (root.parent / "legal-harness工作区"
                     / "legal-harness-repo" / ".local" / "worktrees"
                     / "w4-u51")
            if (guess / "src" / "legal_harness").is_dir():
                return guess
            break
        root = root.parent
    # 兜底：本机 editable 安装（conftest 同款语义；缺依赖时跳过标记）。
    try:
        import legal_harness  # noqa: F401
    except ImportError:
        raise unittest.SkipTest("harness source unavailable") from None
    return Path(sys.modules["legal_harness"].__file__).parents[2]


if __name__ == "__main__":
    unittest.main()
