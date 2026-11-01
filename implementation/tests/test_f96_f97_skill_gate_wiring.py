"""W3-U18 / F96+F97 wiring: 技能执行合同守门与预装技能贯通
（skill.gate.* 桥方法组 → skill_gate 产品面）。

义务 06:F96（F96-desktop/F96-selfhost）「技能执行合同+验收格式（fail-
closed 门禁/证据四态/时点门禁/法源登记表/自带 evals）」＋台账断言「技能
自带证据/法源/时点/失败合同和 evals 真实守门；未核不签 PASS」＋08§3 引
证矩阵「测试绿≠内容通过」同构；06:F97（F97-desktop/F97-selfhost）「接案/
合同/法院来件/结案/计算预装技能真实贯通；无数据源不编企业调查」。

- 单测面：预装五件资产在仓且合同/模板恰一块；合同闭集负向（块缺失/多块/
  JSON 坏/字段闭集/时点格式与未来拒/证据 mode/failure 假成功值/来源类型
  闭集[企业数据无类型可声明]/来源与 eval 重复/expect 闭值）；证据四态
  （UNVERIFIED 无回执/VERIFIED run 过/STALE 字节变/REFUSED 真拒）；未核
  不签 PASS（validate 后未 run→UNVERIFIED pass_allowed=False；回执
  digest/结构/技能绑定负向）；PASS 汇总会计（eval 败→NOT_PASS eval_
  failed；来源未核→NOT_PASS source_not_verified）；预装计算技能经真实
  JC 夹具真算 PASS（闰日 20 分＝E21/F93 同源）＋两跑确定性；引证 eval 与
  法源登记表经 E22 冻结面在合成 codices 正式面真核验（现行/已废止/无码
  三态）；法源类型闭集与 refusal 场景闭集（F97 无数据源不编企业调查）；
  legal_entry 冻结组钉定与分派 fail-closed；面 AST 导入闭集（无网络/模
  型/子进程/编排依赖）。

desktop/selfhost 双 profile 真实安装链（git_local pin → skill.catalog.
install）与 CLI 子进程全链由验收命令
tools/PENDING_OWNER_f96_f97_skillgate_preset_recon.py 承担（工单指定）。
"""
import ast
import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

import legal_entry  # noqa: E402
import skill_gate  # noqa: E402
import skill_semantics  # noqa: E402
from bridge_errors import NotConnected  # noqa: E402

PRESETS = ROOT / "skill-presets"
FENCE = "`" * 3
PRESET_IDS = {"case-intake", "contract-review", "court-inbound",
              "case-close", "calc", "contract-risk-deep",
              "contract-domain-general", "contract-domain-sale",
              "contract-domain-lease", "contract-domain-construction",
              "contract-domain-loan", "contract-domain-labor",
              "contract-domain-service", "contract-domain-tech-dev",
              "contract-domain-equity", "contract-domain-ip-license",
              "contract-domain-security",
              # 他单预装件（RE-16 件3 / RE-4 件4，非 F96 合同结构面）：
              "research", "timeline-generation"}

# 真实 JC 夹具（W3-U16 同 pin：w2b-u55 链头）。
JC_REPO = Path(
    r"D:\Codex\1.法律工作区\juris-calculus工作区\juris-calculus"
    r"\.local\worktrees\w2b-u55")
JC_CLIENT_SHA256 = (
    "3bb8c56a364243af2acdf6200722e704553e582be9e6521aa854ab285bc8b215")

# E22 冻结面 v1.1（F70/F88 同 pin）。
LCCC_PATH = Path(
    r"D:\Codex\1.法律工作区\legal-cn-core-codices工作区"
    r"\legal-cn-core-codices-repo\.local\worktrees\w2a-u14"
    r"\lccc_consumer.py")
LCCC_SHA256 = (
    "55eea7c27e08d6b236b7ab7a83810c86ee0898c335c4668d875a492775db863a")


def _load_generator():
    spec = importlib.util.spec_from_file_location(
        "e12_corpus_gen_f96", ROOT.parent / "tools" / "e12_corpus_gen.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_GEN = _load_generator()

RULE_PACK = {
    "schema_version": "jc/local-pack/1.0", "pack_version": "1.0.0",
    "sources": [{
        "source_id": "acceptance-statute", "jurisdiction": "TEST",
        "authority_tier": "official_first_party",
        "issuer": "Acceptance Test Authority",
        "title": "acceptance-statute",
        "publication_time": "2020-01-01T00:00:00Z",
        "effective_from": "2020-01-01T00:00:00Z",
        "retrieved_at": "2026-08-01T00:00:00Z",
        "locator": {"kind": "uri", "value": "example.invalid/acceptance",
                    "page": None, "span_start": None, "span_end": None},
        "content": ("SYNTHETIC acceptance rule text for engineering "
                    "verification only; no legal effect."),
        "structure_sections": ["ART-1"]}],
    "rules": [{
        "rule_id": "acc-base", "jurisdiction": "TEST",
        "governing_law": "acceptance-statute",
        "source_id": "acceptance-statute", "modality": "OBLIGATION",
        "premises": [{"fact_key": "acc.contract", "required": True}],
        "conclusion": {"value": "applies"},
        "effective_from": "2020-01-01T00:00:00Z"}],
}

CONTRACT_DOC = {
    "as_of": "2026-09-30",
    "evidence": {"mode": "four_state"},
    "sources": [],
    "failure": {"on_gate_fail": "named_refusal_not_pass",
                "on_missing_data": "named_gap_no_fabrication"},
    "evals": [
        {"id": "ev-1", "kind": "calculation",
         "matter_id": "m-f96-wiring",
         "input": {"principal_minor": 365000,
                   "segments": [{"start_date": "2024-02-28",
                                 "end_date": "2024-03-01",
                                 "annual_rate": "0.01"}]},
         "expect": {"amount_minor": 20}},
        {"id": "ev-2", "kind": "refusal",
         "scenario": "corporate_investigation_no_data_source",
         "expect": {"outcome": "refused"}},
    ],
}


def skill_markdown(skill_id: str = "lvyin-f96-wiring", contract=None,
                   raw_contract: str | None = None, extra_contract=False,
                   with_calc_step=False) -> str:
    doc = CONTRACT_DOC if contract is None else contract
    body = raw_contract if raw_contract is not None else json.dumps(
        doc, ensure_ascii=False)
    parts = ["---", "name: F96 接线测试技能",
             "description: 合同守门接线测试（全合成）", "---", "",
             "## 执行合同", "", FENCE + "lvyin-skill-contract",
             body, FENCE, ""]
    if extra_contract:
        parts += [FENCE + "lvyin-skill-contract", "{}", FENCE, ""]
    if with_calc_step:
        step = {"method": "calc.interest", "rule_version": "wiring 声明",
                "calendar_version": "wiring 声明",
                "input_domain": ["principal_minor", "segments"]}
        parts += ["## 计算步骤", "", FENCE + "lvyin-calc-step",
                  json.dumps(step, ensure_ascii=False), FENCE, ""]
    return "\n".join(parts)


def write_skill(root: Path, skill_id: str = "lvyin-f96-wiring", **kwargs
                ) -> Path:
    directory = root / "skills" / skill_id
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "SKILL.md"
    path.write_text(skill_markdown(skill_id, **kwargs), encoding="utf-8")
    return path


def fake_calc_entry(method: str, args: dict, config: dict):
    """seam：skill.calculate 真形（amount_minor=20）；其他一律 typed 拒。"""
    if method == "skill.calculate":
        return {"result": {"amount_minor": 20,
                           "calculationReceiptRef": {"owner": "jc"},
                           "independentChecker": {"agreed": True}}}
    raise NotConnected("method_not_connected:" + method)


# --------------------------------------------------------------------------
# F97 预装资产（首批五件＋RE-12 合同审查族十二件＋他单预装两件，共十九件；
# F96 合同结构面＝带执行合同块的前十七件）
# --------------------------------------------------------------------------


class PresetAssetsTest(unittest.TestCase):
    """F97：预装技能件在仓；带执行合同块的预装件合同结构成立。

    research / timeline-generation（RE-16 件3 / RE-4 件4）不携
    lvyin-skill-contract 块，不在 F96 合同结构面内，只入在仓集合断言。
    """

    @classmethod
    def setUpClass(cls):
        cls.dirs = sorted(
            p for p in PRESETS.iterdir()
            if p.is_dir() and (p / "SKILL.md").is_file())
        # F96 合同结构面＝SKILL.md 携执行合同块的预装件。
        cls.contract_dirs = [
            d for d in cls.dirs
            if "lvyin-skill-contract" in
            (d / "SKILL.md").read_text(encoding="utf-8")]

    def test_preset_skills_present(self):
        ids = {p.name for p in self.dirs}
        self.assertEqual(ids, PRESET_IDS)

    def test_catalog_declaration_public(self):
        catalog = json.loads(
            (PRESETS / "catalog.json").read_text(encoding="utf-8"))
        self.assertEqual(catalog["catalog_id"], "lvyin-presets-batch1")
        self.assertEqual(catalog["channel"], "public")

    def test_each_preset_contract_and_block_structure(self):
        for directory in self.contract_dirs:
            path = directory / "SKILL.md"
            parsed = skill_semantics.read_skill(str(path))
            self.assertEqual(parsed["id"], directory.name, directory.name)
            contract = skill_gate._contract_of(parsed)
            self.assertTrue(skill_gate._valid_iso_date(contract["as_of"]),
                            directory.name)
            # 恰一块执行合同＋恰一块执行语义块（列模板或计算步骤，随技能）。
            body = skill_semantics._body_of(parsed)
            contract_blocks = [block for lang, block in
                               skill_semantics._FENCE_RE.findall(body)
                               if lang == skill_gate.CONTRACT_BLOCK_LANG]
            self.assertEqual(len(contract_blocks), 1, directory.name)
            has_template = has_step = False
            try:
                skill_semantics._blocks_of(
                    body, skill_semantics.TEMPLATE_BLOCK_LANG, "x", "y")
                has_template = True
            except skill_semantics.SkillSemanticsError:
                has_template = False
            try:
                skill_semantics._blocks_of(
                    body, skill_semantics.CALC_STEP_BLOCK_LANG, "x", "y")
                has_step = True
            except skill_semantics.SkillSemanticsError:
                has_step = False
            self.assertEqual((has_template, has_step),
                             (True, False) if directory.name != "calc"
                             else (False, True), directory.name)

    def test_each_preset_sources_empty_and_carries_refusal_eval(self):
        """F97『无数据源不编企业调查』资产级：sources 全空表＋各带 refusal
        eval（corporate_investigation_no_data_source）。"""
        for directory in self.contract_dirs:
            parsed = skill_semantics.read_skill(str(directory / "SKILL.md"))
            contract = skill_gate._contract_of(parsed)
            self.assertEqual(contract["sources"], [], directory.name)
            refusal = [e for e in contract["evals"]
                       if e["kind"] == "refusal"]
            self.assertEqual(len(refusal), 1, directory.name)
            self.assertEqual(refusal[0]["scenario"],
                             "corporate_investigation_no_data_source",
                             directory.name)
            self.assertEqual(refusal[0]["expect"]["outcome"], "refused")

    def test_source_kinds_closed_set_has_no_corporate_kind(self):
        """企业数据等未接入来源在合同层就没有可声明类型——想声明即
        f96_source_kind_unknown（合同级拒绝＝无数据源不编企业调查）。"""
        self.assertEqual(skill_gate.SOURCE_KINDS, frozenset({"statute"}))
        self.assertEqual(skill_gate.REFUSAL_SCENARIOS,
                         frozenset({"corporate_investigation_no_data_source"
                                    }))


# --------------------------------------------------------------------------
# 合同闭集负向（fail-closed）
# --------------------------------------------------------------------------


class ContractClosedSetNegativeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="f96-neg-")
        self.addCleanup(self.tmp.cleanup)

    def _refuse(self, code_fragment, **kwargs):
        path = write_skill(Path(self.tmp.name), **kwargs)
        with self.assertRaises(skill_gate.SkillGateError) as ctx:
            skill_gate.validate_skill({"skill_path": str(path),
                                       "skill_id": path.parent.name})
        self.assertIn(code_fragment, str(ctx.exception))

    def test_missing_block(self):
        root = Path(self.tmp.name)
        directory = root / "skills" / "s-noblock"
        directory.mkdir(parents=True)
        (directory / "SKILL.md").write_text(
            "---\nname: x\n---\n\n正文无合同块。\n", encoding="utf-8")
        with self.assertRaises(skill_gate.SkillGateError) as ctx:
            skill_gate.validate_skill({"skill_path":
                                       str(directory / "SKILL.md"),
                                       "skill_id": "s-noblock"})
        self.assertIn("f96_contract_block_missing", str(ctx.exception))

    def test_not_unique_block(self):
        self._refuse("f96_contract_block_not_unique", skill_id="s-two",
                     extra_contract=True)

    def test_json_invalid(self):
        self._refuse("f96_contract_json_invalid", skill_id="s-badjson",
                     raw_contract="{not json")

    def test_fields_closed_set(self):
        bad = dict(CONTRACT_DOC)
        bad["extra_field"] = 1
        self._refuse("f96_contract_fields_invalid", skill_id="s-extra",
                     contract=bad)
        short = {k: v for k, v in CONTRACT_DOC.items() if k != "failure"}
        self._refuse("f96_contract_fields_invalid", skill_id="s-short",
                     contract=short)

    def test_as_of_format_and_future(self):
        bad = dict(CONTRACT_DOC, as_of="2026/09/30")
        self._refuse("f96_contract_as_of_invalid", skill_id="s-fmt",
                     contract=bad)
        bad2 = dict(CONTRACT_DOC, as_of="2026-13-99")
        self._refuse("f96_contract_as_of_invalid", skill_id="s-fmt2",
                     contract=bad2)
        future = dict(CONTRACT_DOC, as_of="2999-12-31")
        self._refuse("f96_contract_as_of_in_future", skill_id="s-future",
                     contract=future)

    def test_evidence_mode_closed(self):
        bad = dict(CONTRACT_DOC, evidence={"mode": "trust_me"})
        self._refuse("f96_contract_evidence_mode_invalid", skill_id="s-ev",
                     contract=bad)

    def test_failure_contract_refuses_fake_success(self):
        for failure in ({"on_gate_fail": "silent_pass",
                         "on_missing_data": "named_gap_no_fabrication"},
                        {"on_gate_fail": "named_refusal_not_pass",
                         "on_missing_data": "fabricate_fill"}):
            bad = dict(CONTRACT_DOC, failure=failure)
            with self.subTest(failure=failure):
                self._refuse("f96_failure_contract_invalid",
                             skill_id="s-fail", contract=bad)

    def test_source_kind_unknown_no_corporate_type(self):
        bad = dict(CONTRACT_DOC, sources=[
            {"id": "qcc", "kind": "corporate_database", "wjbs": None,
             "code31": None, "as_of": "20260930"}])
        self._refuse("f96_source_kind_unknown:corporate_database",
                     skill_id="s-src", contract=bad)

    def test_source_identifier_xor_and_duplicate(self):
        bad = dict(CONTRACT_DOC, sources=[
            {"id": "s1", "kind": "statute", "wjbs": "W1", "code31": "C1",
             "as_of": "20260930"}])
        self._refuse("f96_source_identifier_invalid", skill_id="s-xor",
                     contract=bad)
        bad2 = dict(CONTRACT_DOC, sources=[
            {"id": "s1", "kind": "statute", "wjbs": "W1", "code31": None,
             "as_of": "20260930"},
            {"id": "s1", "kind": "statute", "wjbs": "W2", "code31": None,
             "as_of": "20260930"}])
        self._refuse("f96_source_duplicate:s1", skill_id="s-dup",
                     contract=bad2)

    def test_eval_kind_unknown_duplicate_and_expect(self):
        bad = json.loads(json.dumps(CONTRACT_DOC))
        bad["evals"][0]["kind"] = "chat"
        self._refuse("f96_eval_kind_unknown:chat", skill_id="s-kind",
                     contract=bad)
        bad2 = json.loads(json.dumps(CONTRACT_DOC))
        bad2["evals"][1]["id"] = "ev-1"
        self._refuse("f96_eval_duplicate:ev-1", skill_id="s-dup2",
                     contract=bad2)
        bad3 = json.loads(json.dumps(CONTRACT_DOC))
        bad3["evals"][0]["expect"] = {"amount_minor": 20,
                                      "refused_code": "x"}
        self._refuse("f96_eval_expect_invalid", skill_id="s-exp",
                     contract=bad3)

    def test_citation_expect_decision_closed(self):
        base = json.loads(json.dumps(CONTRACT_DOC))
        base["evals"] = [{"id": "c1", "kind": "citation", "wjbs": "W",
                          "code31": None, "as_of": "20261016",
                          "expect": {"decision": "MAYBE"}}]
        self._refuse("f96_eval_expect_invalid", skill_id="s-dec",
                     contract=base)

    def test_selection_id_mismatch(self):
        path = write_skill(Path(self.tmp.name), skill_id="s-sel")
        with self.assertRaises(skill_gate.SkillGateError) as ctx:
            skill_gate.validate_skill({"skill_path": str(path),
                                       "skill_id": "other"})
        self.assertIn("f96_skill_id_mismatch", str(ctx.exception))


# --------------------------------------------------------------------------
# 证据四态与未核不签 PASS（seam 注入）
# --------------------------------------------------------------------------


class FourStatesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="f96-4st-")
        self.addCleanup(self.tmp.cleanup)

    def test_unverified_without_receipt(self):
        path = write_skill(Path(self.tmp.name), skill_id="s-unv",
                           with_calc_step=True)
        out = skill_gate.verify_receipt({"skill_path": str(path),
                                         "receipt": None})
        self.assertEqual(out["state"], "UNVERIFIED")
        self.assertFalse(out["pass_allowed"])   # 未核不签 PASS

    def test_verified_then_stale_on_byte_change(self):
        root = Path(self.tmp.name)
        path = write_skill(root, skill_id="s-stale", with_calc_step=True)
        with unittest.mock.patch.object(skill_gate, "_entry_call",
                                        fake_calc_entry):
            receipt = skill_gate.run_gate({"skill_path": str(path),
                                           "skill_id": "s-stale"}, {})
        self.assertEqual(receipt["gate"], "PASS")
        verified = skill_gate.verify_receipt({"skill_path": str(path),
                                              "receipt": receipt})
        self.assertEqual(verified["state"], "VERIFIED")
        self.assertTrue(verified["pass_allowed"])
        # 技能字节变（同 id 新文件）→ STALE，旧回执不覆盖新内容。
        new_root = root / "new"
        new_path = write_skill(new_root, skill_id="s-stale",
                               with_calc_step=True)
        with open(new_path, "a", encoding="utf-8"):
            pass
        text = new_path.read_text(encoding="utf-8") + "尾注改动。\n"
        new_path.write_text(text, encoding="utf-8")
        stale = skill_gate.verify_receipt({"skill_path": str(new_path),
                                           "receipt": receipt})
        self.assertEqual(stale["state"], "STALE")
        self.assertFalse(stale["pass_allowed"])

    def test_refused_state_for_negative_eval(self):
        doc = json.loads(json.dumps(CONTRACT_DOC))
        doc["evals"] = [
            {"id": "neg", "kind": "calculation",
             "matter_id": "m", "input": {"principal_minor": 1},
             "expect": {"refused_code": "FLOAT_FORBIDDEN"}}]
        root = Path(self.tmp.name)
        path = write_skill(root, skill_id="s-ref", contract=doc,
                           with_calc_step=True)

        def refusing_seam(method, args, config):
            raise NotConnected("JC_FAILURE:FLOAT_FORBIDDEN")

        with unittest.mock.patch.object(skill_gate, "_entry_call",
                                        refusing_seam):
            receipt = skill_gate.run_gate({"skill_path": str(path),
                                           "skill_id": "s-ref"}, {})
        entry = receipt["evals"][0]
        self.assertEqual(entry["state"], "REFUSED")
        self.assertTrue(entry["passed"])
        self.assertEqual(receipt["gate"], "PASS")   # 真拒＝该 eval 断言过

    def test_receipt_tamper_and_binding_negatives(self):
        root = Path(self.tmp.name)
        path = write_skill(root, skill_id="s-tamper", with_calc_step=True)
        with unittest.mock.patch.object(skill_gate, "_entry_call",
                                        fake_calc_entry):
            receipt = skill_gate.run_gate({"skill_path": str(path),
                                           "skill_id": "s-tamper"}, {})
        tampered = dict(receipt)
        tampered["gate"] = "PASS"
        tampered.pop("receiptSha256", None)
        forged = dict(receipt, reasons=["forged:reason"])
        # digest 对不上（内容改了 digest 未重算）。
        with self.assertRaises(skill_gate.SkillGateError) as ctx:
            skill_gate.verify_receipt({"skill_path": str(path),
                                       "receipt": forged})
        self.assertIn("f96_receipt_digest_mismatch", str(ctx.exception))
        # 结构坏。
        with self.assertRaises(skill_gate.SkillGateError) as ctx:
            skill_gate.verify_receipt({"skill_path": str(path),
                                       "receipt": {"schema": "x"}})
        self.assertIn("f96_receipt_invalid", str(ctx.exception))
        # 技能 id 绑定不符（真不同 id 的技能文件）。
        other = write_skill(root, skill_id="s-tamper2",
                            with_calc_step=True)
        with self.assertRaises(skill_gate.SkillGateError) as ctx:
            skill_gate.verify_receipt({"skill_path": str(other),
                                       "receipt": receipt})
        self.assertIn("f96_receipt_skill_mismatch", str(ctx.exception))


class GateRunAccountingTest(unittest.TestCase):
    """PASS 汇总会计：败 eval／未核来源必须 NOT_PASS 且 reasons 具名。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="f96-acct-")
        self.addCleanup(self.tmp.cleanup)

    def _run(self, contract, entry_seam, resolve_seam=None):
        root = Path(self.tmp.name)
        path = write_skill(root, skill_id="s-acct", contract=contract,
                           with_calc_step=True)
        real = skill_gate._entry_call

        def seam(method, args, config):
            if method == "statute.citation_gate" \
                    and resolve_seam is not None:
                return resolve_seam(method, args, config)
            return entry_seam(method, args, config)

        with unittest.mock.patch.object(skill_gate, "_entry_call", seam):
            return skill_gate.run_gate({"skill_path": str(path),
                                        "skill_id": "s-acct"}, {})

    def test_eval_failure_not_pass_with_named_reason(self):
        doc = json.loads(json.dumps(CONTRACT_DOC))
        doc["evals"][0]["expect"] = {"amount_minor": 999}

        def wrong_entry(method, args, config):
            if method == "skill.calculate":
                return {"result": {"amount_minor": 20}}
            raise NotConnected("method_not_connected:" + method)

        receipt = self._run(doc, wrong_entry)
        self.assertEqual(receipt["gate"], "NOT_PASS")
        self.assertIn("eval_failed:ev-1", receipt["reasons"])

    def test_source_unverified_blocks_pass(self):
        doc = json.loads(json.dumps(CONTRACT_DOC))
        doc["sources"] = [{"id": "law1", "kind": "statute",
                           "wjbs": "W1", "code31": None,
                           "as_of": "20261016"}]

        def entry(method, args, config):
            if method == "skill.calculate":
                return {"result": {"amount_minor": 20}}
            raise NotConnected("method_not_connected:" + method)

        def unknown_gate(method, args, config):
            return {"decision": "UNKNOWN", "status_label": "unknown",
                    "code": "NOT_FOUND_UNKNOWN:LOCAL_FACE_NOT_FOUND"}

        receipt = self._run(doc, entry, unknown_gate)
        self.assertEqual(receipt["gate"], "NOT_PASS")
        self.assertIn("source_not_verified:law1", receipt["reasons"])
        self.assertEqual(receipt["sourcesRegistry"][0]["state"],
                         "UNVERIFIED")

    def test_source_refused_state_for_abolished(self):
        doc = json.loads(json.dumps(CONTRACT_DOC))
        doc["sources"] = [{"id": "law1", "kind": "statute",
                           "wjbs": "W1", "code31": None,
                           "as_of": "20261016"}]

        def entry(method, args, config):
            if method == "skill.calculate":
                return {"result": {"amount_minor": 20}}
            raise NotConnected("method_not_connected:" + method)

        def abolished_gate(method, args, config):
            return {"decision": "BLOCKED", "status_label": "已废止",
                    "code": "ABOLISHED_NOT_CITABLE"}

        receipt = self._run(doc, entry, abolished_gate)
        self.assertEqual(receipt["gate"], "NOT_PASS")
        self.assertEqual(receipt["sourcesRegistry"][0]["state"], "REFUSED")
        # 全绿时 PASS。
        def valid_gate(method, args, config):
            return {"decision": "ALLOWED", "status_label": "有效",
                    "code": "OK"}

        receipt2 = self._run(doc, entry, valid_gate)
        self.assertEqual(receipt2["gate"], "PASS")
        self.assertEqual(receipt2["sourcesRegistry"][0]["state"],
                         "VERIFIED")


# --------------------------------------------------------------------------
# 预装技能真实贯通（真 JC 真算；真合成 codices 面）
# --------------------------------------------------------------------------


class PresetRealComputeTest(unittest.TestCase):
    """F97：计算预装技能经真实 JC 公开面真算 → PASS（守门真实贯通）。"""

    @classmethod
    def setUpClass(cls):
        client = JC_REPO / "compiler_core" / "client.py"
        if not client.is_file() or hashlib.sha256(
                client.read_bytes()).hexdigest() != JC_CLIENT_SHA256:
            raise unittest.SkipTest("JC w2b-u55 钉定链头不在位（跳过真算）")

    def test_calc_preset_pass_with_real_jc(self):
        tmp = tempfile.TemporaryDirectory(prefix="f96-jc-")
        self.addCleanup(tmp.cleanup)
        ws = Path(tmp.name)
        rules = ws / "rules"
        rules.mkdir()
        (rules / "jc-local-pack.json").write_text(
            json.dumps(RULE_PACK, ensure_ascii=False), encoding="utf-8")
        config = {"jc_state_root": str(ws / "jc-state"),
                  "jc_rule_roots": [str(rules)],
                  "jc_import_path": str(JC_REPO)}
        path = ROOT / "skill-presets" / "calc" / "SKILL.md"
        receipt = skill_gate.run_gate({"skill_path": str(path),
                                       "skill_id": "calc"}, config)
        self.assertEqual(receipt["gate"], "PASS")
        self.assertEqual(receipt["reasons"], [])
        states = {e["id"]: (e["state"], e["passed"])
                  for e in receipt["evals"]}
        self.assertEqual(states["ev-calc-leapday"], ("VERIFIED", True))
        self.assertEqual(states["ev-calc-refusal"], ("REFUSED", True))
        # 回执绑定：VERIFIED pass_allowed=True；两跑 gate 相同。
        out = skill_gate.verify_receipt({"skill_path": str(path),
                                         "receipt": receipt})
        self.assertEqual((out["state"], out["pass_allowed"]),
                         ("VERIFIED", True))
        receipt2 = skill_gate.run_gate({"skill_path": str(path),
                                        "skill_id": "calc"}, config)
        self.assertEqual(receipt2["gate"], "PASS")
        self.assertEqual(
            [(e["id"], e["state"], e["passed"])
             for e in receipt2["evals"]],
            [(e["id"], e["state"], e["passed"])
             for e in receipt["evals"]])


class CitationRealFaceTest(unittest.TestCase):
    """引证 eval 与法源登记表经 E22 冻结面在合成 codices 正式面真核验。"""

    @classmethod
    def setUpClass(cls):
        if not LCCC_PATH.is_file() or hashlib.sha256(
                LCCC_PATH.read_bytes()).hexdigest() != LCCC_SHA256:
            raise unittest.SkipTest("E22 冻结面 v1.1 钉定不在位（跳过）")
        cls.dir = Path(tempfile.mkdtemp(prefix="f96-codices-"))
        _GEN.build_citations(cls.dir, 20261016)
        cls.config = {"codices_import_path": str(LCCC_PATH.parent),
                      "codices_formal_root": str(cls.dir / "codices_face")}
        cls.W = _GEN._CIT_W
        cls.AS_OF = _GEN.CIT_FIXED_AS_OF

    def _citation_eval_receipt(self, wjbs, decision):
        doc = json.loads(json.dumps(CONTRACT_DOC))
        doc["evals"] = [{"id": "c1", "kind": "citation", "wjbs": wjbs,
                         "code31": None, "as_of": self.AS_OF,
                         "expect": {"decision": decision}}]
        tmp = tempfile.TemporaryDirectory(prefix="f96-cite-")
        self.addCleanup(tmp.cleanup)
        path = write_skill(Path(tmp.name), skill_id="s-cite",
                           contract=doc)
        return skill_gate.run_gate({"skill_path": str(path),
                                    "skill_id": "s-cite"}, self.config)

    def test_citation_decisions_in_force_abolished_nocode(self):
        good = self._citation_eval_receipt(self.W["A1"], "ALLOWED")
        self.assertEqual(good["gate"], "PASS")
        abolished = self._citation_eval_receipt(self.W["ABO1"], "BLOCKED")
        self.assertEqual(abolished["gate"], "PASS")
        nocode = self._citation_eval_receipt(self.W["NOCODE"], "UNKNOWN")
        self.assertEqual(nocode["gate"], "PASS")
        # 断言与实际相反 → NOT_PASS（eval_failed 具名）。
        wrong = self._citation_eval_receipt(self.W["ABO1"], "ALLOWED")
        self.assertEqual(wrong["gate"], "NOT_PASS")
        self.assertIn("eval_failed:c1", wrong["reasons"])
        self.assertEqual(wrong["evals"][0]["state"], "UNVERIFIED")

    def test_sources_registry_three_states(self):
        doc = json.loads(json.dumps(CONTRACT_DOC))
        # evals 全 refusal（必过），sources 三条三态。
        doc["evals"] = [CONTRACT_DOC["evals"][1]]
        doc["sources"] = [
            {"id": "current", "kind": "statute", "wjbs": self.W["A1"],
             "code31": None, "as_of": self.AS_OF},
            {"id": "abolished", "kind": "statute", "wjbs": self.W["ABO1"],
             "code31": None, "as_of": self.AS_OF},
            {"id": "nocode", "kind": "statute", "wjbs": self.W["NOCODE"],
             "code31": None, "as_of": self.AS_OF},
        ]
        tmp = tempfile.TemporaryDirectory(prefix="f96-reg-")
        self.addCleanup(tmp.cleanup)
        path = write_skill(Path(tmp.name), skill_id="s-reg", contract=doc)
        receipt = skill_gate.run_gate({"skill_path": str(path),
                                       "skill_id": "s-reg"}, self.config)
        states = {s["id"]: s["state"] for s in receipt["sourcesRegistry"]}
        self.assertEqual(states["current"], "VERIFIED")
        self.assertEqual(states["abolished"], "REFUSED")
        self.assertEqual(states["nocode"], "UNVERIFIED")
        self.assertEqual(receipt["gate"], "NOT_PASS")
        self.assertIn("source_not_verified:abolished", receipt["reasons"])
        self.assertIn("source_not_verified:nocode", receipt["reasons"])


# --------------------------------------------------------------------------
# 冻结组钉定与分派 fail-closed
# --------------------------------------------------------------------------


class FreezeAndDispatchTest(unittest.TestCase):
    def test_frozen_group_equality(self):
        self.assertEqual(legal_entry.SKILL_GATE_METHODS,
                         skill_gate.SKILL_GATE_METHODS)
        self.assertEqual(
            skill_gate.SKILL_GATE_METHODS,
            {"skill.gate.validate", "skill.gate.run",
             "skill.gate.verify_receipt"})

    def test_dispatch_unknown_method_not_connected(self):
        with self.assertRaises(NotConnected) as ctx:
            legal_entry.call("skill.gate.route", {}, {})
        self.assertIn("method_not_connected", str(ctx.exception))

    def test_dispatch_params_closed_set(self):
        with self.assertRaises(NotConnected) as ctx:
            legal_entry.call("skill.gate.validate",
                             {"skill_path": "x", "skill_id": "y",
                              "extra": 1}, {})
        self.assertIn("f96_validate_params_invalid", str(ctx.exception))
        with self.assertRaises(NotConnected) as ctx:
            legal_entry.call("skill.gate.run",
                             {"skill_path": "x"}, {})
        self.assertIn("f96_run_params_invalid", str(ctx.exception))
        with self.assertRaises(NotConnected) as ctx:
            legal_entry.call("skill.gate.verify_receipt", {}, {})
        self.assertIn("f96_verify_params_invalid", str(ctx.exception))

    def test_gate_error_typed_wrapping(self):
        # SkillGateError → NotConnected("skill_gate_failed:f96_*")。
        tmp = tempfile.TemporaryDirectory(prefix="f96-wrap-")
        self.addCleanup(tmp.cleanup)
        path = write_skill(Path(tmp.name), skill_id="s-wrap")
        with self.assertRaises(NotConnected) as ctx:
            legal_entry.call("skill.gate.validate",
                             {"skill_path": str(path), "skill_id": "nope"},
                             {})
        self.assertIn("skill_gate_failed:f96_skill_id_mismatch",
                      str(ctx.exception))

    def test_evidence_states_closed_set(self):
        self.assertEqual(skill_gate.EVIDENCE_STATES,
                         {"VERIFIED", "UNVERIFIED", "STALE", "REFUSED"})
        self.assertEqual(
            skill_gate.EVAL_KINDS,
            {"calculation", "review_instantiate", "citation", "refusal"})


class ImportClosureASTTest(unittest.TestCase):
    """面 AST：顶层导入闭集（无网络/模型/子进程/编排依赖；legal_entry 仅
    函数内延迟导入＝与 skill_semantics 同款 seam 纪律）。"""

    def test_top_level_imports_closed(self):
        tree = ast.parse((ROOT / "python" / "skill_gate.py").read_text(
            encoding="utf-8"))
        imported = set()
        for node in tree.body:
            if isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module or "")
        self.assertEqual(
            imported,
            {"__future__", "hashlib", "json", "re",
             "datetime", "bridge_errors", "skill_semantics"})
        banned = ("urllib", "socket", "subprocess", "requests", "http",
                  "sqlite3", "os")
        self.assertFalse(imported & set(banned),
                         "skill_gate 顶层出现禁面导入：%s"
                         % (imported & set(banned)))

    def test_no_dynamic_exec(self):
        source = (ROOT / "python" / "skill_gate.py").read_text(
            encoding="utf-8")
        for marker in ("exec(", "eval(", "os.system", "__import__"):
            self.assertNotIn(marker, source, marker)


if __name__ == "__main__":
    unittest.main()
