"""F45 通道① 产品侧接线测试（W2b-U15）：agent CLI 直改文档。

全部合成材料（f45_fixtures 纯 stdlib 合成起诉状语料）。docxedit.* 四
方法走 legal_entry 冻结方法组；harness 登记面（add_material_revision
source=assistant_edit＋formal_propose channel=machine）经 subprocess
seam 注入（单测零仓依赖；真 public_entry 全链实跑对账在
tools/PENDING_OWNER_f45_clean_annotated_docx_recon.py 双 profile）。

本地生成面（双 DOCX 产出＋独立 lxml 检查器八维硬门＋确定性＋append-only
＋幂等重放）在 seam 桥下真跑——这些不依赖 harness 检出。
"""

from __future__ import annotations

import base64
import hashlib
import json
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import f45_fixtures  # noqa: E402
import legal_entry  # noqa: E402
import docx_edit  # noqa: E402
from bridge_errors import NotConnected  # noqa: E402

CONFIG = {
    "harness_public_entry": "X:/synth/harness/public_entry.py",
    "harness_target": "opencode",
    "harness_state_root": "X:/synth/state-root",
    "harness_python": sys.executable,
    "docx_edit_state_root": None,          # 每例注入临时根
}
DOCXEDIT_METHODS = (
    "docxedit.apply", "docxedit.outputs", "docxedit.output", "docxedit.verify",
)
AUTHOR = "lvyin-docxedit"  # F53 作者声明闭集（W2b-U49；docxedit 通道绑定）
EDITED_AT = "2026-10-16T00:00:00Z"

EDITS = [
    {"op": "replace_text", "paragraph": 4, "find": "85,000元",
     "replace": "85,000元及利息", "reason": "金额主张改为含利息（合成）"},
    {"op": "insert_paragraph", "after": 6, "text": "判令被告承担保全费用；",
     "reason": "新增保全请求（合成）", "numbering": {"numId": 1, "ilvl": 0},
     "style": None},
    {"op": "delete_paragraph", "paragraph": 13, "reason": "删除副本附言（合成）"},
    {"op": "replace_cell", "table": 0, "row": 2, "col": 1, "text": "4,250",
     "reason": "违约金试算（合成）"},
    {"op": "comment", "paragraph": 8, "text": "交货证据链待补（合成批注）"},
]


def source_bytes() -> bytes:
    return f45_fixtures.build_source_docx()


def fake_harness_calls(testcase, calls=None, revision_no=2,
                       proposal_state="pending"):
    """seam：截获桥子进程信封，返回合成 harness 回执。

    read_material 回原稿字节；add_material_revision 回新版本号；
    formal_propose 回提案行。信封全量记入 calls（供断言 source/channel/
    quotes/CommandKey 派生键）。"""
    import io as _io

    def _fake_execute(argv, env, timeout):
        flag = next(f for f in ("--materials-json", "--formalproposal-json")
                    if f in argv)
        envelope = json.loads(Path(
            argv[argv.index(flag) + 1]).read_text(encoding="utf-8"))
        if calls is not None:
            calls.append({"flag": flag, "envelope": envelope})
        method = envelope["method"]
        if method == "harness.read_material":
            raw = source_bytes()
            result = {"bytesB64": base64.b64encode(raw).decode("ascii"),
                      "sha256": hashlib.sha256(raw).hexdigest(),
                      "source": "upload", "revision": 1}
            surface = "materials"
        elif method == "harness.add_material_revision":
            result = {"revision": revision_no,
                      "sha256": hashlib.sha256(base64.b64decode(
                          envelope["params"]["revision"]["bytesB64"])
                      ).hexdigest(),
                      "casRef": "cas://synthetic", "source": "assistant_edit",
                      "baseRevision": 1}
            surface = "materials"
        else:  # formal_propose
            result = {"proposal": {
                "proposalId": envelope["params"]["proposal"]["proposalId"],
                "state": proposal_state,
                "baseRevision": envelope["params"]["proposal"]["baseRevision"],
                "proposalSha256": hashlib.sha256(base64.b64decode(
                    envelope["params"]["proposal"]["bytesB64"])).hexdigest(),
                "channel": envelope["params"]["proposal"]["channel"],
            }, "duplicate": False}
            surface = "formalproposal"
        return SimpleNamespace(stdout=json.dumps(
            {"surface": surface, "method": method, "result": result}),
            returncode=0)

    patcher = unittest.mock.patch.object(legal_entry, "_execute", _fake_execute)
    patcher.start()
    testcase.addCleanup(patcher.stop)


def apply_args(request_id="req-1", proposal_id="fp-1", edits=None):
    return {
        "matter_id": "m-f45", "material_id": "mat-f45", "base_revision": 1,
        "request_id": request_id, "proposal_id": proposal_id,
        "actor_id": "assistant-synth", "author": AUTHOR,
        "edited_at": EDITED_AT, "edits": edits if edits is not None else EDITS,
        "note": "F45 合成编辑提案",
    }


class F45MethodGroupTests(unittest.TestCase):
    def test_method_group_frozen(self) -> None:
        self.assertEqual(legal_entry.DOCX_EDIT_METHODS,
                         frozenset(DOCXEDIT_METHODS))
        for fake in ("docxedit.bake", "docxedit.set_output",
                     "docxedit.host_edit"):
            self.assertNotIn(fake, legal_entry.DOCX_EDIT_METHODS)

    def test_unknown_and_unclosed_fail_closed(self) -> None:
        calls: list[dict] = []
        fake_harness_calls(self, calls)
        with self.assertRaisesRegex(NotConnected, "method_not_connected"):
            legal_entry.call("docxedit.host_edit", apply_args(), CONFIG)
        with self.assertRaisesRegex(NotConnected, "docx_edit_params_invalid"):
            legal_entry.call("docxedit.apply", ["not-a-dict"], CONFIG)
        self.assertEqual(calls, [])

    def test_state_root_required(self) -> None:
        fake_harness_calls(self)
        with self.assertRaisesRegex(NotConnected,
                                    "f45_state_root_not_configured"):
            legal_entry.call("docxedit.apply", apply_args(),
                             {k: v for k, v in CONFIG.items()
                              if k != "docx_edit_state_root"})
        with self.assertRaisesRegex(NotConnected,
                                    "f45_state_root_not_configured"):
            legal_entry.call("docxedit.outputs", {"matter_id": "m-f45",
                                                  "material_id": "mat-f45"},
                             {k: v for k, v in CONFIG.items()
                              if k != "docx_edit_state_root"})

    def test_harness_unconfigured_fails_closed(self) -> None:
        calls: list[dict] = []
        fake_harness_calls(self, calls)
        with tempfile.TemporaryDirectory() as tmp:
            config = dict(CONFIG, docx_edit_state_root=tmp)
            del config["harness_public_entry"]
            with self.assertRaisesRegex(NotConnected,
                                        "harness_public_entry_not_configured"):
                legal_entry.call("docxedit.apply", apply_args(), config)
        self.assertEqual(calls, [])


class F45ApplyFlowTests(unittest.TestCase):
    def test_apply_registers_assistant_edit_and_formal_proposal(self) -> None:
        calls: list[dict] = []
        fake_harness_calls(self, calls)
        with tempfile.TemporaryDirectory() as tmp:
            config = dict(CONFIG, docx_edit_state_root=tmp)
            result = legal_entry.call("docxedit.apply", apply_args(), config)
        # 信封序：read_material → add_material_revision → formal_propose。
        methods = [c["envelope"]["method"] for c in calls]
        self.assertEqual(methods, ["harness.read_material",
                                   "harness.add_material_revision",
                                   "harness.formal_propose"])
        revision_env = calls[1]["envelope"]["params"]["revision"]
        self.assertEqual(revision_env["source"], "assistant_edit")
        self.assertEqual(revision_env["baseRevision"], 1)
        self.assertEqual(revision_env["materialId"], "mat-f45")
        self.assertEqual(calls[1]["envelope"]["params"]["key"]["requestId"],
                         "req-1:assistant-edit")
        proposal_env = calls[2]["envelope"]["params"]["proposal"]
        self.assertEqual(proposal_env["channel"], "machine")
        self.assertEqual(proposal_env["baseRevision"], 2)
        self.assertEqual(proposal_env["proposalId"], "fp-1")
        self.assertEqual(calls[2]["envelope"]["params"]["key"]["requestId"],
                         "req-1:formal-propose")
        # 提案字节==清洁版字节（canonical 干净态：批注修订版不入提案）。
        self.assertEqual(proposal_env["bytesB64"],
                         revision_env["bytesB64"])
        # quotes：内容编辑定位集（4 条内容编辑，comment op 不入 quotes）。
        quotes = proposal_env["quotes"]
        self.assertEqual(len(quotes), 4)
        self.assertEqual(quotes[0]["text"], "85,000元")
        self.assertEqual(quotes[0]["reason"], EDITS[0]["reason"])
        self.assertEqual(quotes[0]["sourceRef"],
                         {"owner": "harness", "kind": "material",
                          "id": "mat-f45", "version": "1",
                          "matterId": "m-f45"})
        # 回执面。
        self.assertFalse(result["replayed"])
        self.assertEqual(result["harness"]["assistant_edit"]["revision"], 2)
        self.assertEqual(result["harness"]["assistant_edit"]["source"],
                         "assistant_edit")
        self.assertEqual(result["harness"]["proposal"]["state"], "pending")
        self.assertTrue(result["fidelity"]["all_passed"])

    def test_apply_produces_real_docx_pair_and_append_only(self) -> None:
        calls: list[dict] = []
        fake_harness_calls(self, calls)
        with tempfile.TemporaryDirectory() as tmp:
            config = dict(CONFIG, docx_edit_state_root=tmp)
            first = legal_entry.call("docxedit.apply", apply_args(), config)
            outputs_root = Path(tmp) / "docx-edit" / "m-f45" / "mat-f45" \
                / "outputs"
            seq1 = outputs_root / "0001"
            clean1 = (seq1 / "clean.docx").read_bytes()
            annotated1 = (seq1 / "annotated.docx").read_bytes()
            self.assertEqual(hashlib.sha256(clean1).hexdigest(),
                             first["clean"]["sha256"])
            # 清洁版==提案字节（真开包验证由检查器保证；此处直接断言）。
            from docx import Document as Docx  # noqa: D401 独立开包面
            import io
            clean_doc = Docx(io.BytesIO(clean1))
            self.assertIn("85,000元及利息",
                          "\n".join(p.text for p in clean_doc.paragraphs))
            # 第二次（不同编辑）＝新 seq，旧产物一字节不动。
            second_edits = [dict(EDITS[0], replace="85,000元及逾期利息")]
            second = legal_entry.call(
                "docxedit.apply",
                apply_args(request_id="req-2", proposal_id="fp-2",
                           edits=second_edits), config)
            self.assertEqual(second["output_id"], "mat-f45:0002")
            self.assertEqual((seq1 / "clean.docx").read_bytes(), clean1)
            self.assertEqual((seq1 / "annotated.docx").read_bytes(),
                             annotated1)
            self.assertNotEqual(
                (outputs_root / "0002" / "clean.docx").read_bytes(), clean1)

    def test_replay_same_request_id_idempotent(self) -> None:
        calls: list[dict] = []
        fake_harness_calls(self, calls)
        with tempfile.TemporaryDirectory() as tmp:
            config = dict(CONFIG, docx_edit_state_root=tmp)
            first = legal_entry.call("docxedit.apply", apply_args(), config)
            harness_calls_after_first = len(calls)
            replay = legal_entry.call("docxedit.apply", apply_args(), config)
            self.assertTrue(replay["replayed"])
            self.assertEqual(replay["output_id"], first["output_id"])
            self.assertEqual(replay["clean"]["sha256"],
                             first["clean"]["sha256"])
            # 重放照样先读原稿（零新 harness 写：read 一次，无 rev/propose）。
            self.assertEqual(len(calls) - harness_calls_after_first, 1)
            listing = legal_entry.call(
                "docxedit.outputs",
                {"matter_id": "m-f45", "material_id": "mat-f45"}, config)
            self.assertEqual(len(listing["outputs"]), 1)

    def test_request_conflict_on_same_id_different_edits(self) -> None:
        fake_harness_calls(self)
        with tempfile.TemporaryDirectory() as tmp:
            config = dict(CONFIG, docx_edit_state_root=tmp)
            legal_entry.call("docxedit.apply", apply_args(), config)
            with self.assertRaises(docx_edit.DocxEditError) as ctx:
                legal_entry.call(
                    "docxedit.apply",
                    apply_args(edits=[dict(EDITS[0],
                                           replace="85,000元及逾期利息")]),
                    config)
            self.assertIn("f45_request_conflict", str(ctx.exception))

    def test_output_readback_and_b64(self) -> None:
        fake_harness_calls(self)
        with tempfile.TemporaryDirectory() as tmp:
            config = dict(CONFIG, docx_edit_state_root=tmp)
            applied = legal_entry.call("docxedit.apply", apply_args(), config)
            read = legal_entry.call(
                "docxedit.output",
                {"matter_id": "m-f45", "material_id": "mat-f45", "seq": "0001",
                 "file": "annotated"}, config)
            payload = base64.b64decode(read["docx_b64"])
            self.assertEqual(
                hashlib.sha256(payload).hexdigest(),
                applied["annotated"]["sha256"])
            with self.assertRaisesRegex(docx_edit.DocxEditError,
                                        "f45_file_invalid"):
                legal_entry.call(
                    "docxedit.output",
                    {"matter_id": "m-f45", "material_id": "mat-f45",
                     "seq": "0001", "file": "host"}, config)

    def test_verify_reruns_independent_gate(self) -> None:
        fake_harness_calls(self)
        with tempfile.TemporaryDirectory() as tmp:
            config = dict(CONFIG, docx_edit_state_root=tmp)
            legal_entry.call("docxedit.apply", apply_args(), config)
            verified = legal_entry.call(
                "docxedit.verify",
                {"matter_id": "m-f45", "material_id": "mat-f45", "seq": "0001"},
                config)
            self.assertTrue(verified["verified"])
            self.assertTrue(verified["fidelity"]["all_passed"])
            # 篡改清洁版后复验必须响亮失败（旧稿覆写在产物面被硬门抓住）。
            clean_path = Path(tmp) / "docx-edit" / "m-f45" / "mat-f45" \
                / "outputs" / "0001" / "clean.docx"
            clean_path.write_bytes(clean_path.read_bytes() + b"\x00")
            with self.assertRaisesRegex(docx_edit.DocxEditError,
                                        "f45_output_bytes_mismatch"):
                legal_entry.call(
                    "docxedit.verify",
                    {"matter_id": "m-f45", "material_id": "mat-f45",
                     "seq": "0001"}, config)


class F45EditClosedSetTests(unittest.TestCase):
    def _plan(self, edits):
        model = docx_edit.parse_source(source_bytes())
        return docx_edit.plan_edits(model, edits)

    def test_quote_not_found_and_ambiguous(self) -> None:
        with self.assertRaisesRegex(docx_edit.DocxEditError,
                                    "f45_quote_not_found:4"):
            self._plan([dict(EDITS[0], find="不存在的引文")])
        with self.assertRaisesRegex(docx_edit.DocxEditError,
                                    "f45_quote_ambiguous:8"):
            self._plan([{"op": "replace_text", "paragraph": 8,
                         "find": "合成", "replace": "X", "reason": "r"}])

    def test_conflict_and_closed_fields(self) -> None:
        with self.assertRaisesRegex(docx_edit.DocxEditError,
                                    "f45_edit_conflict:4"):
            self._plan([EDITS[0],
                        {"op": "delete_paragraph", "paragraph": 4,
                         "reason": "d"}])
        with self.assertRaisesRegex(docx_edit.DocxEditError,
                                    "f45_edit_fields_not_closed"):
            self._plan([dict(EDITS[0], extra_field="x")])
        with self.assertRaisesRegex(docx_edit.DocxEditError,
                                    "f45_edit_op_unknown"):
            self._plan([{"op": "insert_table", "after": 1, "text": "x",
                         "reason": "r", "numbering": None, "style": None}])
        with self.assertRaisesRegex(docx_edit.DocxEditError,
                                    "f45_edits_required"):
            self._plan([])

    def test_out_of_range_and_empty_paragraph_edit(self) -> None:
        with self.assertRaisesRegex(docx_edit.DocxEditError,
                                    "f45_edit_paragraph_out_of_range"):
            self._plan([dict(EDITS[2], paragraph=99)])
        with self.assertRaisesRegex(docx_edit.DocxEditError,
                                    "f45_edit_cell_out_of_range"):
            self._plan([dict(EDITS[3], row=9)])


class F45FidelityGateTests(unittest.TestCase):
    """检查器负向：任何一维被破坏即 typed 拒（不假成功）。"""

    def _versions(self, edits=None):
        src = source_bytes()
        model = docx_edit.parse_source(src)
        plan = docx_edit.plan_edits(model, edits if edits is not None
                                    else EDITS)
        versions = docx_edit.build_versions(src, model, plan, AUTHOR,
                                            EDITED_AT)
        return src, model, plan, versions

    def _assert_fail(self, src, clean, annotated, plan, code):
        with self.assertRaisesRegex(docx_edit.DocxEditError, code):
            docx_edit.fidelity_check(src, clean, annotated, plan, AUTHOR)

    def test_clean_with_markup_rejected(self) -> None:
        src, _, plan, versions = self._versions()
        # 把批注修订版冒充清洁版：修订标记维度必须拒。
        self._assert_fail(src, versions["annotated"], versions["annotated"],
                          plan, "f45_fidelity_clean_is_clean")

    def test_clean_with_wrong_text_rejected(self) -> None:
        src, _, plan, versions = self._versions()
        # 换一个"编辑没生效"的清洁版：正文投影维度必须拒。
        src_model = docx_edit.parse_source(src)
        plan2 = docx_edit.plan_edits(src_model, [EDITS[4]])  # 仅批注
        clean2 = docx_edit.build_versions(src, src_model, plan2, AUTHOR,
                                          EDITED_AT)
        self._assert_fail(src, clean2["clean"], versions["annotated"], plan,
                          "f45_fidelity_body_text")

    def test_annotated_not_matching_clean_rejected(self) -> None:
        src, _, plan, versions = self._versions()
        src_model = docx_edit.parse_source(src)
        plan2 = docx_edit.plan_edits(src_model, [EDITS[4]])
        ann2 = docx_edit.build_versions(src, src_model, plan2, AUTHOR,
                                        EDITED_AT)
        self._assert_fail(src, versions["clean"], ann2["annotated"], plan,
                          "f45_fidelity_accept_projection")

    def test_determinism_same_input_same_bytes(self) -> None:
        first = self._versions()
        second = self._versions()
        self.assertEqual(first[3]["clean"], second[3]["clean"])
        self.assertEqual(first[3]["annotated"], second[3]["annotated"])
        self.assertEqual(first[3]["clean"],
                         docx_edit.build_versions(
                             *self._rebuild(first[2]))["clean"])

    def _rebuild(self, plan):
        src = source_bytes()
        edits = [e for e in EDITS]
        return (src, docx_edit.parse_source(src),
                docx_edit.plan_edits(docx_edit.parse_source(src), edits),
                AUTHOR, EDITED_AT)

    def test_comment_only_edit_set(self) -> None:
        src, model, plan, versions = self._versions(edits=[EDITS[4]])
        report = docx_edit.fidelity_check(src, versions["clean"],
                                          versions["annotated"], plan,
                                          AUTHOR)
        self.assertTrue(report["all_passed"])
        # 仅批注：清洁版正文与原稿逐字相同，但仍是完整真实 DOCX。
        self.assertEqual(report["dimensions"]["body_text"]
                         ["expected_paragraphs"], 14)
        self.assertEqual(report["counts"], {"ins": 0, "del": 0,
                                            "comments": 1})
        self.assertEqual(plan["quotes"], [])


if __name__ == "__main__":
    unittest.main()
