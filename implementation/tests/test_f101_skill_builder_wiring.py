# -*- coding: utf-8 -*-
"""W5-U10 / F101 acceptance: agent/skill-builder 候选/预检/采用合同面 wiring.

验收向量（06:V7-101 逐字）：「自建skill/agent生成候选，经预检和用户采用
再执行，无自动扩权」。全部断言走真产品入口（legal_entry.call 同进程）；
候选生成对话轮＝合成候选注入（结构断言全程离线可跑，零模型零网络）；
预检＝既有 F96 skill.gate.validate 真校验（零第二合同权威）；采用＝
adoption.by 逐字 "user"（非用户通道 f101_adopt_requires_user typed 拒）
＋skill 经既有 F95 skill.zip.install 分发链真安装（零第二目录权威）；红
线：候选态永不直执行（本面零执行方法/零执行面引用 AST 钉定）；agent 候
选 permissions 只准 ask/deny 收窄（allow 规则 f101_agent_permission_allow
typed 拒＝无自动扩权）。材料全合成；每例独立状态根零串扰。
"""
import ast
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "python"))
import legal_entry
from bridge_errors import NotConnected

DIALOG = {"turns": [
    {"role": "user", "text": "帮我做一个合同续期提醒的技能，只要能拒答企业调查。"},
    {"role": "assistant", "text": "已按你的要求起草候选，预检通过后再请你采用。"},
]}

MARKER_DIALOG = "MAQDIALOGXQ 续期独句"
MARKER_NOTE = "NOTEXBODYY 采用标记"

SKILL_DOC = (
    "---\nname: 合同续期提醒\ndescription: 自建技能候选（合成）：合同续期"
    "提醒与拒绝企业调查\n---\n\n# 合同续期提醒（自建候选）\n\n"
    "## 执行合同（F96）\n\n```lvyin-skill-contract\n"
    '{"as_of": "2026-10-01", "evidence": {"mode": "four_state"}, '
    '"sources": [], "failure": {"on_gate_fail": "named_refusal_not_pass", '
    '"on_missing_data": "named_gap_no_fabrication"}, "evals": '
    '[{"id": "ev-refusal", "kind": "refusal", '
    '"scenario": "corporate_investigation_no_data_source", '
    '"expect": {"outcome": "refused"}}]}\n```\n\n'
    "## 失败纪律\n\n- 守门不过具名拒；缺数据具名缺口，绝不编造。\n")

SKILL_DOC_BAD_CONTRACT = SKILL_DOC.replace('"four_state"', '"two_state"')

AGENT_DOC_DENY = (
    "---\ndescription: 自建 agent 候选（合成）：只读复核助手\n"
    "mode: subagent\n"
    'permissions: [{"action": "shell", "resource": "*", "effect": "deny"}]\n'
    "---\n\n你是律引自建复核助手：只做只读复核，绝不执行任何写操作。\n")

AGENT_DOC_ALLOW = AGENT_DOC_DENY.replace('"deny"', '"allow"')


class F101SkillBuilderTests(unittest.TestCase):
    def setUp(self):
        self._workspace = Path(tempfile.mkdtemp(prefix="f101_wiring_"))
        self.config = {
            "skill_builder_state_root": str(self._workspace / "builder"),
            "skill_catalog_state_root": str(self._workspace / "catalog"),
        }

    def tearDown(self):
        shutil.rmtree(self._workspace, ignore_errors=True)

    # -- helpers -----------------------------------------------------------

    def propose(self, kind="skill", document=None, dialog=None):
        return legal_entry.call("skill.builder.propose", {
            "kind": kind, "dialog": dialog or DIALOG,
            "document": document or {"filename": "SKILL.md",
                                     "text": SKILL_DOC}}, self.config)

    def precheck(self, candidate_id):
        return legal_entry.call("skill.builder.precheck",
                                {"candidate_id": candidate_id},
                                self.config)

    def adopt(self, candidate_id, by="user", note="用户采用"):
        return legal_entry.call("skill.builder.adopt", {
            "candidate_id": candidate_id,
            "adoption": {"by": by, "note": note}}, self.config)

    def records_path(self) -> Path:
        return self._workspace / "builder" / "candidates.jsonl"

    # -- 冻结方法组与桥面 ---------------------------------------------------

    def test_frozen_method_group(self):
        self.assertEqual(legal_entry.SKILL_BUILDER_METHODS,
                         frozenset({"skill.builder.propose",
                                    "skill.builder.precheck",
                                    "skill.builder.adopt",
                                    "skill.builder.read"}))

    def test_unknown_method_fails_closed(self):
        with self.assertRaises(NotConnected) as ctx:
            legal_entry.call("skill.builder.execute", {}, self.config)
        self.assertIn("method_not_connected", str(ctx.exception))

    def test_missing_state_root_fails_closed(self):
        with self.assertRaises(NotConnected) as ctx:
            legal_entry.call("skill.builder.propose",
                             {"kind": "skill", "dialog": DIALOG,
                              "document": {"filename": "SKILL.md",
                                           "text": SKILL_DOC}}, {})
        self.assertIn("f101_state_root_not_configured",
                      str(ctx.exception))

    def test_params_closed_set(self):
        with self.assertRaises(NotConnected) as ctx:
            legal_entry.call("skill.builder.propose",
                             {"kind": "skill", "dialog": DIALOG,
                              "document": {"filename": "SKILL.md",
                                           "text": SKILL_DOC},
                              "extra": 1}, self.config)
        self.assertIn("f101_propose_params_invalid", str(ctx.exception))

    # -- propose：候选生成对话轮（合成候选注入） -----------------------------

    def test_propose_skill_candidate_staged(self):
        out = self.propose()
        self.assertEqual(out["status"], "staged")
        self.assertFalse(out["idempotent"])
        self.assertTrue(out["candidate_id"].startswith("skill-"))
        self.assertEqual(len(out["candidate_id"]), len("skill-") + 8)
        record = legal_entry.call("skill.builder.read",
                                  {"candidate_id": out["candidate_id"]},
                                  self.config)
        entry = record["candidates"][0]
        self.assertEqual(entry["status"], "staged")
        self.assertEqual(entry["document_sha256"], out["document_sha256"])
        self.assertEqual(entry["origin"]["turn_count"], 2)
        self.assertEqual(entry["origin"]["roles"], ["user", "assistant"])

    def test_propose_log_content_free(self):
        dialog = {"turns": [
            {"role": "user", "text": MARKER_DIALOG + "，请生成候选。"},
            {"role": "assistant", "text": "候选已起草。"},
        ]}
        self.propose(dialog=dialog)
        raw = self.records_path().read_text(encoding="utf-8")
        self.assertNotIn(MARKER_DIALOG, raw)
        self.assertNotIn("合同续期提醒的技能", raw)
        self.assertIn("dialog_sha256", raw)

    def test_propose_idempotent_same_bytes(self):
        first = self.propose()
        second = self.propose()
        self.assertEqual(first["candidate_id"], second["candidate_id"])
        self.assertTrue(second["idempotent"])
        listing = legal_entry.call("skill.builder.read",
                                   {"candidate_id": None}, self.config)
        ids = [c["candidate_id"] for c in listing["candidates"]]
        self.assertEqual(ids.count(first["candidate_id"]), 1)

    def test_propose_requires_user_origin(self):
        dialog = {"turns": [
            {"role": "assistant", "text": "我主动给你造一个技能。"},
            {"role": "user", "text": "好的。"},
        ]}
        with self.assertRaises(NotConnected) as ctx:
            self.propose(dialog=dialog)
        self.assertIn("f101_origin_user_missing", str(ctx.exception))

    def test_propose_kind_closed_set(self):
        with self.assertRaises(NotConnected) as ctx:
            self.propose(kind="tool")
        self.assertIn("f101_kind_unknown:tool", str(ctx.exception))

    def test_propose_skill_filename_closed(self):
        with self.assertRaises(NotConnected) as ctx:
            self.propose(document={"filename": "skill.md",
                                   "text": SKILL_DOC})
        self.assertIn("f101_document_filename_invalid", str(ctx.exception))

    def test_propose_parse_failure_leaves_no_record(self):
        bad = "正文（无 frontmatter，原生不可加载）。\n"
        with self.assertRaises(NotConnected) as ctx:
            self.propose(document={"filename": "SKILL.md", "text": bad})
        self.assertIn("f101_document_parse_failed", str(ctx.exception))
        self.assertIn("f93_", str(ctx.exception))
        listing = legal_entry.call("skill.builder.read",
                                   {"candidate_id": None}, self.config)
        self.assertEqual(listing["count"], 0)
        self.assertFalse((self._workspace / "builder" / "candidates")
                         .exists())

    # -- 预检：F96 门禁复用＋无自动扩权闸 -----------------------------------

    def test_precheck_skill_pass_uses_f96_gate_validate(self):
        out = self.propose()
        pre = self.precheck(out["candidate_id"])
        self.assertEqual(pre["result"], "PASS")
        self.assertEqual([c["id"] for c in pre["checks"]],
                         ["f96_gate_validate"])
        self.assertTrue(pre["contract_sha256"])
        self.assertEqual(pre["as_of"], "2026-10-01")

    def test_precheck_skill_bad_contract_named_refusal(self):
        out = self.propose(document={"filename": "SKILL.md",
                                     "text": SKILL_DOC_BAD_CONTRACT})
        with self.assertRaises(NotConnected) as ctx:
            self.precheck(out["candidate_id"])
        code = str(ctx.exception)
        self.assertIn("f101_precheck_contract_failed", code)
        self.assertIn("f96_contract_evidence_mode_invalid", code)

    def test_precheck_agent_allow_permission_typed_refusal(self):
        out = self.propose(kind="agent",
                           document={"filename": "review-helper.md",
                                     "text": AGENT_DOC_ALLOW})
        with self.assertRaises(NotConnected) as ctx:
            self.precheck(out["candidate_id"])
        self.assertIn("f101_agent_permission_allow:1", str(ctx.exception))

    def test_precheck_agent_deny_only_passes(self):
        out = self.propose(kind="agent",
                           document={"filename": "review-helper.md",
                                     "text": AGENT_DOC_DENY})
        pre = self.precheck(out["candidate_id"])
        self.assertEqual(pre["result"], "PASS")
        no_esc = next(c for c in pre["checks"]
                      if c["id"] == "no_auto_escalation")
        self.assertTrue(no_esc["passed"])

    def test_precheck_unknown_candidate(self):
        with self.assertRaises(NotConnected) as ctx:
            self.precheck("skill-00000000")
        self.assertIn("f101_candidate_missing", str(ctx.exception))

    # -- 采用：用户独占＋经既有分发链 ---------------------------------------

    def test_adopt_requires_explicit_user(self):
        out = self.propose()
        cid = out["candidate_id"]
        self.precheck(cid)
        for by in ("assistant", "model", "auto", "system"):
            with self.assertRaises(NotConnected) as ctx:
                self.adopt(cid, by=by, note="非用户通道自采用")
            self.assertIn("f101_adopt_requires_user:" + by,
                          str(ctx.exception))

    def test_adopt_requires_precheck(self):
        out = self.propose()
        with self.assertRaises(NotConnected) as ctx:
            self.adopt(out["candidate_id"], note="未预检直接采用")
        self.assertIn("f101_precheck_required", str(ctx.exception))

    def test_adopt_candidate_modified_after_precheck(self):
        out = self.propose()
        cid = out["candidate_id"]
        self.precheck(cid)
        Path(out["staged_path"]).write_text(
            SKILL_DOC + "\n<!-- 追加 -->\n", encoding="utf-8")
        with self.assertRaises(NotConnected) as ctx:
            self.adopt(cid, note="字节已变仍要采用")
        self.assertIn("f101_candidate_modified", str(ctx.exception))

    def test_adopt_skill_installs_via_zip_chain(self):
        out = self.propose()
        cid = out["candidate_id"]
        self.precheck(cid)
        adopted = self.adopt(cid, note=MARKER_NOTE)
        self.assertEqual(adopted["status"], "adopted")
        receipt = adopted["adoption"]
        self.assertEqual(receipt["by"], "user")
        self.assertEqual(receipt["channel"], "skill.zip.install")
        install = receipt["install"]
        self.assertEqual(install["status"], "INSTALLED")
        self.assertEqual(install["skills"], [cid])
        self.assertTrue(receipt["zip_sha256"])
        record = legal_entry.call("skill.builder.read",
                                  {"candidate_id": cid}, self.config)
        self.assertEqual(record["candidates"][0]["status"], "adopted")
        raw = self.records_path().read_text(encoding="utf-8")
        self.assertNotIn(MARKER_NOTE, raw)  # note 只入 sha（零内容留痕）

    def test_adopt_agent_materializes_declaration_only(self):
        out = self.propose(kind="agent",
                           document={"filename": "review-helper.md",
                                     "text": AGENT_DOC_DENY})
        cid = out["candidate_id"]
        self.precheck(cid)
        adopted = self.adopt(cid, note="采用只读复核助手")
        self.assertEqual(adopted["status"], "adopted")
        self.assertEqual(adopted["adoption"]["channel"],
                         "adopted_declaration")
        artifact = Path(adopted["adoption"]["artifact"])
        self.assertTrue(artifact.is_file())
        self.assertEqual(artifact.read_text(encoding="utf-8"),
                         AGENT_DOC_DENY)

    def test_read_digest_tamper_typed_refusal(self):
        out = self.propose()
        self.precheck(out["candidate_id"])
        original = self.records_path().read_bytes()
        lines = original.decode("utf-8").splitlines()
        record = json.loads(lines[0])
        record["status"] = "adopted"  # 未采用谎称已采用
        lines[0] = json.dumps(record, ensure_ascii=False, sort_keys=True,
                              separators=(",", ":"))
        self.records_path().write_text("\n".join(lines) + "\n",
                                       encoding="utf-8")
        with self.assertRaises(NotConnected) as ctx:
            legal_entry.call("skill.builder.read",
                             {"candidate_id": None}, self.config)
        self.assertIn("f101_record_digest_mismatch", str(ctx.exception))
        self.records_path().write_bytes(original)
        restored = legal_entry.call("skill.builder.read",
                                    {"candidate_id": None}, self.config)
        self.assertEqual(restored["count"], 1)

    # -- 红线结构断言：候选态永不直执行 -------------------------------------

    def test_face_never_references_execution_surface(self):
        source = (HERE / "python" / "skill_builder.py").read_text(
            encoding="utf-8")
        for forbidden in ("skill.gate.run", "skill.calculate",
                          "skill.review_instantiate", "skill.route.decide",
                          "skill.route.log", "exec(", "eval(",
                          "subprocess", "socket", "urllib", "os.system"):
            self.assertNotIn(forbidden, source,
                             "执行面引用出现：%s" % forbidden)

    def test_face_bridge_calls_closed_set(self):
        import skill_builder
        source = (HERE / "python" / "skill_builder.py").read_text(
            encoding="utf-8")
        tree = ast.parse(source)
        calls = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) \
                    and isinstance(node.func, ast.Name) \
                    and node.func.id == "_bridge_call":
                first = node.args[0] if node.args else None
                if isinstance(first, ast.Name):
                    # 模块级具名常量（字面量的唯一别名形态）。
                    value = getattr(skill_builder, first.id)
                else:
                    self.assertIsInstance(first, ast.Constant,
                                          "桥出方法必须字面量/具名常量")
                    value = first.value
                calls.append(value)
        self.assertEqual(sorted(calls),
                         sorted(["skill.gate.validate",
                                 "skill.zip.install"]))

    def test_face_import_closed_set(self):
        source = (HERE / "python" / "skill_builder.py").read_text(
            encoding="utf-8")
        tree = ast.parse(source)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0]
                                for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertLessEqual(imported,
                             {"__future__", "hashlib", "io", "json", "re",
                              "zipfile", "pathlib", "bridge_errors",
                              "skill_semantics", "legal_entry"})

    def test_bridge_method_group_only(self):
        wired = (HERE / "python" / "legal_entry.py").read_text(
            encoding="utf-8")
        self.assertIn("SKILL_BUILDER_METHODS", wired)
        self.assertIn("skill_builder_failed", wired)
        for method in legal_entry.SKILL_BUILDER_METHODS:
            self.assertIn(method, wired)


if __name__ == "__main__":
    unittest.main()
