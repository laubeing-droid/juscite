"""F53 产品侧接线测试（W2b-U49）：作者声明闭集＋决定引用三方投影。

全部合成材料。legal_entry 新增 AUTHOR_POLICY_METHODS 三方法组
（author.policy / author.check / author.projection，产品侧 author_policy
同进程公开面，零状态根）；U12/U14/U15 三机器通道的 author 入口收拢过闸
（本文件直接经三个真实面代码路径验证伪造作者具名拒）。harness 决定面
（U11，VERIFIED）零改动——投影经 harness.formal_proposal_list 冻结组
只读提案账（单测 subprocess seam 注入；真 public_entry 全链实跑对账在
tools/PENDING_OWNER_f53_author_decision_recon.py）。

fail-closed 负向（06:F53）：伪造 author=律师名＝f53_author_impersonation；
作者与通道错绑＝f53_author_channel_mismatch；accepted/rejected 行缺决定
引用＝f53_decision_ref_missing；跨提案引用错位＝
f53_cross_proposal_ref_mismatch。投影绝不静默呈现违例行。
"""

from __future__ import annotations

import base64
import io
import json
import sys
import tempfile
import unittest
import unittest.mock
import zipfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

import legal_entry  # noqa: E402
import docx_edit  # noqa: E402
from bridge_errors import NotConnected  # noqa: E402
import author_policy as ap  # noqa: E402
import document_redline as dr  # noqa: E402
import edits_protocol as ep  # noqa: E402
from test_f48_edits_protocol_wiring import (  # noqa: E402
    MIN_PARAGRAPHS, build_min_docx, edits_stream, edit_card,
)

AUTHOR_POLICY_METHODS = (
    "author.policy", "author.check", "author.projection",
)
FORGED_LAWYER = "王律师（合成·伪造）"


def _fake_entry_output(result):
    return json.dumps({"surface": "formalproposal", "method": "synthetic",
                       "result": result})


def patch_execute(testcase, *, payload):
    stdout = _fake_entry_output(payload)
    patcher = unittest.mock.patch.object(
        legal_entry, "_execute",
        lambda argv, env, timeout: SimpleNamespace(
            stdout=stdout, returncode=0))
    patcher.start()
    testcase.addCleanup(patcher.stop)


# --------------------------------------------------------------------------
# 1. 方法组＋策略视图
# --------------------------------------------------------------------------

class F53MethodGroupTests(unittest.TestCase):
    def test_method_group_frozen(self) -> None:
        self.assertEqual(legal_entry.AUTHOR_POLICY_METHODS,
                         frozenset(AUTHOR_POLICY_METHODS))
        # 伪方法（改策略/直改提案作者/代签决定）不在冻结组。
        for fake in ("author.set_policy", "author.impersonate",
                     "author.decide", "author.bake"):
            self.assertNotIn(fake, legal_entry.AUTHOR_POLICY_METHODS)

    def test_policy_view_closed_set(self) -> None:
        view = legal_entry.call("author.policy", {}, {})
        self.assertEqual(view["schema"], "juscite-f53-author-policy/1")
        # W4-U38：templates 通道（lvyin-templates）随 F56 装配面加入闭集，
        # 三既有绑定逐字不动（公开改口：闭集 3→4，W2b-U49 收拢先例延续）。
        # W4-U51（F120）：闭集增补 crossexam→lvyin-cross-exam（公开改口：
        # 原三通道钉集扩展一通道，既有三绑定零动）。
        # W5-U14（F143）：闭集增补 proofing→lvyin-proofing（公开改口：
        # 闭集 5→6，法律写作校对插件 document_proofing 校对候选提案
        # channel=machine；既有五绑定逐字零动）。
        self.assertEqual(
            view["machine_channels"],
            {"redline": {"author": "lvyin-redline", "kind": "machine"},
             "edits": {"author": "lvyin-edits", "kind": "machine"},
             "docxedit": {"author": "lvyin-docxedit", "kind": "machine"},
             "templates": {"author": "lvyin-templates", "kind": "machine"},
             "crossexam": {"author": "lvyin-cross-exam",
                           "kind": "machine"},
             "proofing": {"author": "lvyin-proofing", "kind": "machine"}})
        self.assertIn("no_lawyer_impersonation", view["rules"])
        self.assertIn("accept_requires_real_decision_ref", view["rules"])
        # 机器作者闭集与通道绑定互为镜像。
        self.assertEqual(
            {binding["author"]: channel
             for channel, binding in view["machine_channels"].items()},
            {"lvyin-redline": "redline", "lvyin-edits": "edits",
             "lvyin-docxedit": "docxedit",
             "lvyin-templates": "templates",
             "lvyin-cross-exam": "crossexam",
             "lvyin-proofing": "proofing"})


# --------------------------------------------------------------------------
# 2. author.check：闭集＋绑定＋具名拒矩阵
# --------------------------------------------------------------------------

class F53AuthorCheckTests(unittest.TestCase):
    def test_bindings_ok(self) -> None:
        for channel, author in (("redline", "lvyin-redline"),
                                ("edits", "lvyin-edits"),
                                ("docxedit", "lvyin-docxedit")):
            with self.subTest(channel=channel):
                binding = legal_entry.call("author.check",
                                           {"channel": channel,
                                            "author": author}, {})
                self.assertEqual(binding, {"channel": channel,
                                           "author": author,
                                           "kind": "machine"})

    def test_forged_lawyer_name_refused(self) -> None:
        # 冒充律师名＝具名拒（三通道逐一）。
        for channel in ("redline", "edits", "docxedit"):
            with self.subTest(channel=channel):
                with self.assertRaises(NotConnected) as ctx:
                    legal_entry.call("author.check",
                                     {"channel": channel,
                                      "author": FORGED_LAWYER}, {})
                self.assertIn("f53_author_impersonation", str(ctx.exception))

    def test_channel_mismatch_refused(self) -> None:
        with self.assertRaises(NotConnected) as ctx:
            legal_entry.call("author.check",
                             {"channel": "redline", "author": "lvyin-edits"},
                             {})
        self.assertIn("f53_author_channel_mismatch", str(ctx.exception))

    def test_unknown_and_missing_refused(self) -> None:
        with self.assertRaises(NotConnected) as ctx:
            legal_entry.call("author.check",
                             {"channel": "wps", "author": "lvyin-redline"}, {})
        self.assertIn("f53_channel_unknown", str(ctx.exception))
        with self.assertRaises(NotConnected) as ctx:
            legal_entry.call("author.check",
                             {"channel": "docxedit", "author": ""}, {})
        self.assertIn("f53_author_required", str(ctx.exception))


# --------------------------------------------------------------------------
# 3. 收拢：三机器通道真实面代码路径的伪造作者具名拒
# --------------------------------------------------------------------------

class F53ConsolidationGateTests(unittest.TestCase):
    """U12/U14/U15 透传 author 先例收拢成策略面：三个面的 author 入口都过
    同一闸（author_policy.check_revision_author），伪造律师名在面边界即拒，
    不产生任何修订字节/提案登记。"""

    def test_docxedit_apply_forged_author_refused(self) -> None:
        with tempfile.TemporaryDirectory(prefix="juscite-f53-") as tmp:
            config = {"docx_edit_state_root": tmp}
            args = {"matter_id": "m-f53", "material_id": "mat-f53",
                    "base_revision": 1, "request_id": "req-f53",
                    "proposal_id": "fp-f53", "actor_id": "assistant-synth",
                    "author": FORGED_LAWYER,
                    "edited_at": "2026-10-17T00:00:00Z", "edits": []}
            # docxedit 面 typed 拒＝DocxEditError（U15 基线：f45_* 族错误
            # 原样上浮不经 NotConnected 包裹）；f53 码落同族错误码透传。
            with self.assertRaises(docx_edit.DocxEditError) as ctx:
                legal_entry.call("docxedit.apply", args, config)
            self.assertIn("f53_author_impersonation", str(ctx.exception))

    def test_edits_apply_forged_author_refused(self) -> None:
        with tempfile.TemporaryDirectory(prefix="juscite-f53-") as tmp:
            config = {"edits_state_root": tmp}
            legal_entry.call("edits.register", {
                "document_id": "d-f53",
                "bytesB64": base64.b64encode(build_min_docx()).decode(
                    "ascii")}, config)
            legal_entry.call("edits.stream_open", {
                "document_id": "d-f53", "stream_id": "s1"}, config)
            legal_entry.call("edits.stream_push", {
                "document_id": "d-f53", "stream_id": "s1",
                "chunk": edits_stream(edit_card(
                    "c1", "replace", MIN_PARAGRAPHS[0],
                    "被伪造作者拒绝句。"))}, config)
            legal_entry.call("edits.stream_close", {
                "document_id": "d-f53", "stream_id": "s1"}, config)
            legal_entry.call("edits.locate", {
                "document_id": "d-f53", "stream_id": "s1"}, config)
            with self.assertRaises(NotConnected) as ctx:
                legal_entry.call("edits.apply", {
                    "document_id": "d-f53", "stream_id": "s1",
                    "card_ids": ["c1"], "revision_author": FORGED_LAWYER,
                    "revision_date": "2026-10-17T00:00:00Z"}, config)
            self.assertIn("f53_author_impersonation", str(ctx.exception))
            # 拒后文档零修订标记（面边界拒，不产生半成品）。
            scan = ep.scan_document(ep.load_docx_parts(
                Path(tmp) / "edits-protocol" / "d-f53" / "working.docx"))
            self.assertEqual(scan["revisions"], [])

    def test_edits_apply_legal_author_binds(self) -> None:
        with tempfile.TemporaryDirectory(prefix="juscite-f53-") as tmp:
            config = {"edits_state_root": tmp}
            legal_entry.call("edits.register", {
                "document_id": "d-f53b",
                "bytesB64": base64.b64encode(build_min_docx()).decode(
                    "ascii")}, config)
            legal_entry.call("edits.stream_open", {
                "document_id": "d-f53b", "stream_id": "s1"}, config)
            legal_entry.call("edits.stream_push", {
                "document_id": "d-f53b", "stream_id": "s1",
                "chunk": edits_stream(edit_card(
                    "c1", "replace", MIN_PARAGRAPHS[0],
                    "闭集作者替换句。"))}, config)
            legal_entry.call("edits.stream_close", {
                "document_id": "d-f53b", "stream_id": "s1"}, config)
            legal_entry.call("edits.locate", {
                "document_id": "d-f53b", "stream_id": "s1"}, config)
            result = legal_entry.call("edits.apply", {
                "document_id": "d-f53b", "stream_id": "s1",
                "card_ids": ["c1"], "revision_author": "lvyin-edits",
                "revision_date": "2026-10-17T00:00:00Z"}, config)
            self.assertTrue(result["cards"][0]["revision_ids"])
            scan = ep.scan_document(ep.load_docx_parts(
                Path(tmp) / "edits-protocol" / "d-f53b" / "working.docx"))
            self.assertEqual({rev["author"] for rev in scan["revisions"]},
                             {"lvyin-edits"})

    def test_redline_replay_forged_author_refused(self) -> None:
        with tempfile.TemporaryDirectory(prefix="juscite-f53-") as tmp:
            state_root = Path(tmp)
            source = state_root / "base.docx"
            source.write_bytes(_single_para_docx())
            dr.register(state_root, "doc-f53", {"docx_path": str(source)})
            with self.assertRaises(NotConnected) as ctx:
                legal_entry.call("redline.replay", {
                    "document_id": "doc-f53",
                    "proposal": {"author": FORGED_LAWYER,
                                 "authored_utc": "2026-10-17T00:00:00Z",
                                 "ops": [{"op": "body.replace_text",
                                          "index": 0,
                                          "text": "策略闸后替换句。"}]}},
                    {"redline_state_root": tmp})
            self.assertIn("f53_author_impersonation", str(ctx.exception))
            # 闭集作者（缺省＝lvyin-redline）照常出红线——策略只挡伪造。
            replay = legal_entry.call("redline.replay", {
                "document_id": "doc-f53",
                "proposal": {"authored_utc": "2026-10-17T00:00:00Z",
                             "ops": [{"op": "body.replace_text", "index": 0,
                                      "text": "闭集作者替换句。"}]}},
                {"redline_state_root": tmp})
            self.assertEqual(replay["author"], "lvyin-redline")


# --------------------------------------------------------------------------
# 4. 决定引用三方投影（纯函数＋桥径）
# --------------------------------------------------------------------------

def _listing(proposals, canonical=None):
    return {"canonical": canonical or {"revision": 2, "source": "generated",
                                       "sha256": "a" * 64},
            "proposals": proposals, "proposalCount": len(proposals),
            "stateCounts": {}}


def _row(proposal_id="fp-1", state="accepted", channel="machine",
         author="lvyin-docxedit", decision=None, **extra):
    row = {"proposalId": proposal_id, "seq": 1, "state": state,
           "channel": channel, "author": author,
           "decisionRef": decision, "bakedRevision": None,
           "supersededBy": None, "decidedAt": None}
    row.update(extra)
    return row


def _decision(proposal_id="fp-1", action="accept"):
    return {"decisionId": f"formal-dec-r1-{proposal_id}", "action": action,
            "receiptRef": {"owner": "harness", "kind": "receipt",
                           "id": "rc-f53", "version": "1",
                           "matterId": "m-f53"},
            "reasonRef": {"owner": "harness", "kind": "reason",
                          "id": "r-f53", "version": "1",
                          "matterId": "m-f53"},
            "proposalId": proposal_id, "decidedRevision": 2,
            "recordedAt": "2026-10-17T00:00:00Z"}


class F53DecisionProjectionTests(unittest.TestCase):
    def test_three_way_projection_readable(self) -> None:
        listing = _listing([
            _row("fp-1", "accepted", "machine", "lvyin-docxedit",
                 _decision("fp-1"), bakedRevision=3,
                 decidedAt="2026-10-17T00:00:00Z"),
            _row("fp-2", "rejected", "word", "王律师（宿主记录）",
                 _decision("fp-2", "reject")),
            _row("fp-3", "superseded", "machine", "lvyin-redline"),
        ])
        projection = ap.decision_projection(listing, "m-f53", "mat-f53")
        self.assertEqual(projection["schema"],
                         "juscite-f53-author-decision-projection/1")
        self.assertEqual(len(projection["rows"]), 3)
        accepted = projection["rows"][0]
        self.assertEqual(accepted["authorPolicy"],
                         {"kind": "machine", "status": "machine_author_ok",
                          "boundChannel": "docxedit"})
        # 律师决定引用↔修订 author↔提案 channel 三方同框可读。
        self.assertEqual(accepted["decision"]["decisionId"],
                         "formal-dec-r1-fp-1")
        self.assertEqual(accepted["decision"]["action"], "accept")
        self.assertEqual(accepted["channel"], "machine")
        self.assertEqual(accepted["author"], "lvyin-docxedit")
        self.assertTrue(projection["visibility"]["decisionVisible"])
        host = projection["rows"][1]
        self.assertEqual(host["authorPolicy"]["kind"], "host")
        superseded = projection["rows"][2]
        self.assertIsNone(superseded["decision"])

    def test_forged_author_row_refused(self) -> None:
        with self.assertRaises(ap.AuthorPolicyError) as ctx:
            ap.decision_projection(_listing([
                _row("fp-x", "pending", "machine", FORGED_LAWYER)]),
                "m-f53", "mat-f53")
        self.assertIn("f53_author_impersonation:fp-x", str(ctx.exception))

    def test_missing_decision_ref_refused(self) -> None:
        with self.assertRaises(ap.AuthorPolicyError) as ctx:
            ap.decision_projection(_listing([
                _row("fp-y", "accepted", "machine", "lvyin-edits",
                     decision=None)]), "m-f53", "mat-f53")
        self.assertIn("f53_decision_ref_missing:fp-y", str(ctx.exception))

    def test_cross_proposal_ref_mismatch_refused(self) -> None:
        decision = _decision("fp-else")
        with self.assertRaises(ap.AuthorPolicyError) as ctx:
            ap.decision_projection(_listing([
                _row("fp-z", "accepted", "machine", "lvyin-edits",
                     decision=decision)]), "m-f53", "mat-f53")
        self.assertIn("f53_cross_proposal_ref_mismatch:fp-else:fp-z",
                      str(ctx.exception))

    def test_decision_on_undecided_refused(self) -> None:
        with self.assertRaises(ap.AuthorPolicyError) as ctx:
            ap.decision_projection(_listing([
                _row("fp-s", "superseded", "machine", "lvyin-redline",
                     decision=_decision("fp-s"))]), "m-f53", "mat-f53")
        self.assertIn("f53_decision_on_undecided:fp-s", str(ctx.exception))

    def test_channel_and_state_closed_sets(self) -> None:
        with self.assertRaises(ap.AuthorPolicyError):
            ap.decision_projection(_listing([
                _row("fp-c", "pending", "email", "lvyin-edits")]),
                "m-f53", "mat-f53")
        with self.assertRaises(ap.AuthorPolicyError):
            ap.decision_projection(_listing([
                _row("fp-d", "cancelled", "machine", "lvyin-edits")]),
                "m-f53", "mat-f53")


class F53BridgeProjectionTests(unittest.TestCase):
    """legal_entry 径：author.projection 经 HARNESS_FORMAL_PROPOSAL_METHODS
    冻结组只读提案账（subprocess seam 注入）；未配置＝fail-closed。"""

    CONFIG = {
        "harness_public_entry": "X:/synth/harness/public_entry.py",
        "harness_target": "opencode",
        "harness_state_root": "X:/synth/state-root",
        "harness_python": sys.executable,
    }

    def test_projection_rides_frozen_group(self) -> None:
        captured: list[list] = []

        def _capture(argv, env, timeout):
            captured.append({"argv": list(argv), "envelope": json.loads(
                Path(argv[argv.index("--formalproposal-json") + 1]
                     ).read_text(encoding="utf-8"))})
            return SimpleNamespace(stdout=_fake_entry_output(_listing([
                _row("fp-1", "accepted", "machine", "lvyin-docxedit",
                     _decision("fp-1"))])), returncode=0)

        patcher = unittest.mock.patch.object(legal_entry, "_execute",
                                             _capture)
        patcher.start()
        self.addCleanup(patcher.stop)
        projection = legal_entry.call("author.projection", {
            "matter_id": "m-f53", "material_id": "mat-f53"}, self.CONFIG)
        self.assertEqual(projection["rows"][0]["decision"]["decisionId"],
                         "formal-dec-r1-fp-1")
        envelope = captured[0]["envelope"]
        self.assertEqual(envelope["method"], "harness.formal_proposal_list")
        # 只读：冻结组内无写方法可被投影径触达。
        self.assertIn("harness.formal_proposal_list",
                      legal_entry.HARNESS_FORMAL_PROPOSAL_METHODS)

    def test_projection_forged_row_refused_through_bridge(self) -> None:
        patch_execute(self, payload=_listing([
            _row("fp-f", "pending", "machine", FORGED_LAWYER)]))
        with self.assertRaises(NotConnected) as ctx:
            legal_entry.call("author.projection", {
                "matter_id": "m-f53", "material_id": "mat-f53"},
                self.CONFIG)
        self.assertIn("f53_author_impersonation", str(ctx.exception))

    def test_projection_not_configured_fail_closed(self) -> None:
        with self.assertRaises(NotConnected) as ctx:
            legal_entry.call("author.projection", {
                "matter_id": "m-f53", "material_id": "mat-f53"}, {})
        self.assertIn("harness_public_entry_not_configured",
                      str(ctx.exception))


# --------------------------------------------------------------------------
# 夹具
# --------------------------------------------------------------------------

def _single_para_docx() -> bytes:
    """单段最小合成 DOCX（redline 闸测试用；全合成虚构文本）。"""
    w_ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    document = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                f'<w:document xmlns:w="{w_ns}"><w:body>'
                '<w:p><w:r><w:t>合成基线句，用于作者策略闸测试。</w:t></w:r>'
                '</w:p></w:body></w:document>')
    content_types = ('<?xml version="1.0" encoding="UTF-8"?>'
                     '<Types xmlns="http://schemas.openxmlformats.org/'
                     'package/2006/content-types"><Default Extension="rels"'
                     ' ContentType="application/vnd.openxmlformats-package.'
                     'relationships+xml"/><Default Extension="xml"'
                     ' ContentType="application/xml"/><Override PartName='
                     '"/word/document.xml" ContentType="application/'
                     'vnd.openxmlformats-officedocument.'
                     'wordprocessingml.document.main+xml"/></Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/'
            'package/2006/relationships"><Relationship Id="rId1" Type='
            '"http://schemas.openxmlformats.org/officeDocument/2006/'
            'relationships/officeDocument" Target="word/document.xml"/>'
            '</Relationships>')
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, payload in (("[Content_Types].xml", content_types),
                              ("_rels/.rels", rels),
                              ("word/document.xml", document)):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, payload.encode("utf-8"))
    return buffer.getvalue()


if __name__ == "__main__":
    unittest.main()
