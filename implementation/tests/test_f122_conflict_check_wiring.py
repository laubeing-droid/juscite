# -*- coding: utf-8 -*-
"""F122 利益冲突查重产品桥接线测试（工单 W4-U53）。

06 F122（v1.5；owner=product+harness；acceptance：客户/相对方/别名冲突
候选真实匹配，人工解除留范围记录；preserved：收案前合规小件，规则匹配
即可）。产品面＝legal_entry 冻结方法组 CONFLICT_CHECK_METHODS（九方法
桥 harness.conflict_* 经 public_entry --conflict-json 信封；harness
docs/f122-conflict-check-contract.md）。

合同硬点（本测试主战场，全链真子进程 public_entry）：
  - 真实匹配＝确定性规则匹配（主体名/别名/曾用名精确+受控规范化——
    零模糊语义）；命中＝冲突候选账 append-only；
  - 解除＝人工决定面（decision_ref 必带——E24 F62 人审确认闸同构：
    未审不入库）留范围记录（谁/何时/基于什么范围）；
  - 别名/曾用名维护留版本（变更后历史匹配不追溯改写）；
  - 脱敏域纪律：conflict 派发段零 anonymizer/rehydrate 引用（AST 结构
    断言——检索在脱敏域内进行，原文名不出 anonymizer 映射）；
  - 桥 fail-closed：未配置 NotConnected／封闭注册外方法具名拒。

全程合成材料；查询名/主体名全部合成（假名域内文本）。
"""

from __future__ import annotations

import ast
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

import legal_entry  # noqa: E402
from bridge_errors import HarnessCommandError, NotConnected  # noqa: E402

# harness 战役分支（A2 链）本单 worktree 钉定
HARNESS_WORKTREE = Path(
    r"D:\Codex\1.法律工作区\legal-harness工作区\legal-harness-repo"
    r"\.local\worktrees\w4-u53")

MATTER_X = "m-f122-wx"   # 收案审查本案
MATTER_A = "m-f122-wa"   # 在办案件 A
MATTER_B = "m-f122-wb"   # 在办案件 B

SCOPE_X = {"kind": "matter", "matterId": MATTER_X}
SCOPE_A = {"kind": "matter", "matterId": MATTER_A}


def _key(request_id: str) -> dict:
    return {"requestId": request_id, "targetId": None,
            "expectedRevision": None, "inputRefs": []}


def _party(party_id: str, display_name: str) -> dict:
    return {"id": party_id, "kind": "party", "version": "1",
            "displayName": display_name}


def _decision_ref(decision_id: str) -> dict:
    return {"owner": "host", "kind": "human-decision",
            "id": decision_id, "version": "1"}


def _harness_config(state_root: Path) -> dict:
    if not (HARNESS_WORKTREE / "tools/workflow-tools/harness/public_entry.py"
            ).is_file():
        raise AssertionError(
            f"pinned harness w4-u53 worktree missing at {HARNESS_WORKTREE}; "
            "the F122 conflict bridge cannot be verified")
    return {
        "harness_public_entry":
            str(HARNESS_WORKTREE / "tools/workflow-tools/harness/public_entry.py"),
        "harness_target": "opencode",
        "harness_state_root": str(state_root),
        "harness_timeout": 120,
    }


def _harness_direct(method: str, params: dict, state_root: Path) -> dict:
    """夹具专用：harness public_entry 子进程直呼（W09 contacts_upsert 不在
    legal_entry 冻结组——F122 桥只路由 conflict 面；夹具建档经同一公开面
    子进程径，不 import harness 内部）。"""
    import os
    import subprocess
    import tempfile as _tf
    handle = _tf.NamedTemporaryFile("w", encoding="utf-8", suffix=".json",
                                    delete=False)
    try:
        json.dump({"method": method, "params": params}, handle,
                  ensure_ascii=False)
        handle.close()
        env = dict(os.environ)
        env["LH_LEGAL_STATE_ROOT"] = str(state_root)
        proc = subprocess.run(
            [sys.executable, "-X", "utf8",
             str(HARNESS_WORKTREE / "tools/workflow-tools/harness/public_entry.py"),
             "--conflict-json", handle.name, "--target", "opencode"],
            capture_output=True, text=True, encoding="utf-8", timeout=120,
            cwd=str(HARNESS_WORKTREE), env=env)
        payload = json.loads(proc.stdout)
        if proc.returncode != 0:
            raise HarnessCommandError(payload.get("error") or "harness_failed")
        return payload["result"]
    finally:
        os.unlink(handle.name)


class F122ConflictCheckWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.holder = tempfile.TemporaryDirectory(prefix="juscite-f122-wiring-")
        state_root = Path(cls.holder.name) / "state"
        state_root.mkdir(parents=True)
        cls.config = _harness_config(state_root)
        sys.path.insert(0, str(HARNESS_WORKTREE / "src"))
        from legal_harness.state.matter_store import MatterStore
        store = MatterStore(state_root)
        for matter_id in (MATTER_X, MATTER_A, MATTER_B):
            store.create_matter(matter_id, "cas://profile-f122-wiring")
        cls.state_root = state_root
        # 在办案件 A：相对方「恒大合成集团有限公司」＋版本别名/曾用名；
        # 客户「合成城建置业有限　公司」（全角空格登记）。
        _harness_direct(
            "contacts.upsert",
            {"actor_id": "lawyer-1", "scope": SCOPE_A, "key": _key("cu-1"),
             "party_ref": _party("p-hengda", "恒大合成集团有限公司"),
             "alias_refs": [], "relationship_refs": []}, cls.state_root)
        legal_entry.call(
            "harness.conflict_alias_record",
            {"actor_id": "lawyer-1", "key": _key("al-1"),
             "party_ref": {"id": "p-hengda"}, "alias": "恒大合成控股",
             "alias_kind": "alias"}, cls.config)
        legal_entry.call(
            "harness.conflict_alias_record",
            {"actor_id": "lawyer-1", "key": _key("al-2"),
             "party_ref": {"id": "p-hengda"}, "alias": "恒大合成地产",
             "alias_kind": "former_name"}, cls.config)
        legal_entry.call(
            "harness.conflict_case_party_attach",
            {"actor_id": "lawyer-1", "scope": SCOPE_A, "key": _key("cp-1"),
             "party_ref": {"id": "p-hengda"}, "role": "opposing"}, cls.config)
        _harness_direct(
            "contacts.upsert",
            {"actor_id": "lawyer-1", "scope": SCOPE_A, "key": _key("cu-2"),
             "party_ref": _party("p-chengjian", "合成城建置业有限　公司"),
             "alias_refs": [], "relationship_refs": []}, cls.state_root)
        legal_entry.call(
            "harness.conflict_case_party_attach",
            {"actor_id": "lawyer-1", "scope": SCOPE_A, "key": _key("cp-2"),
             "party_ref": {"id": "p-chengjian"}, "role": "client"}, cls.config)
        # 在办案件 B：客户「ＡＢＣ合成腾讯科技有限公司」（全角拉丁登记）。
        _harness_direct(
            "contacts.upsert",
            {"actor_id": "lawyer-1",
             "scope": {"kind": "matter", "matterId": MATTER_B},
             "key": _key("cu-3"),
             "party_ref": _party("p-tencent", "ＡＢＣ合成腾讯科技有限公司"),
             "alias_refs": [], "relationship_refs": []}, cls.state_root)
        legal_entry.call(
            "harness.conflict_case_party_attach",
            {"actor_id": "lawyer-1",
             "scope": {"kind": "matter", "matterId": MATTER_B},
             "key": _key("cp-3"),
             "party_ref": {"id": "p-tencent"}, "role": "client"}, cls.config)
        # 收案审查本案：客户「合成新委托人」。
        _harness_direct(
            "contacts.upsert",
            {"actor_id": "lawyer-1", "scope": SCOPE_X, "key": _key("cu-4"),
             "party_ref": _party("p-newclient", "合成新委托人有限公司"),
             "alias_refs": [], "relationship_refs": []}, cls.state_root)
        legal_entry.call(
            "harness.conflict_case_party_attach",
            {"actor_id": "lawyer-1", "scope": SCOPE_X, "key": _key("cp-4"),
             "party_ref": {"id": "p-newclient"}, "role": "client"}, cls.config)
        # 首轮收案前查重（四类匹配依据全用）。
        cls.first_check = legal_entry.call(
            "harness.conflict_check",
            {"actor_id": "lawyer-1", "scope": SCOPE_X, "key": _key("ck-1"),
             "queries": [
                 {"role": "client", "name": "恒大合成集团有限公司"},
                 {"role": "opposing", "name": "abc合成腾讯科技有限公司"},
                 {"role": "client", "name": "恒大合成控股"},
                 {"role": "opposing", "name": "恒大合成地产"},
                 {"role": "client", "name": "合成城建置业有限 公司"}]},
            cls.config)

    @classmethod
    def tearDownClass(cls):
        cls.holder.cleanup()

    # -- 真实匹配（确定性规则匹配，四类依据） ------------------------

    def test_01_real_matching_all_bases_with_scope_pin(self):
        result = self.first_check
        by_basis = {}
        for candidate in result["candidates"]:
            by_basis.setdefault(candidate["matchBasis"], []).append(candidate)
        self.assertEqual(sorted(by_basis),
                         ["alias", "exact_name", "former_name"])
        exact_a = [c for c in by_basis["exact_name"]
                   if c["hitMatterId"] == MATTER_A
                   and c["hitPartyId"] == "p-hengda"]
        # 客户查询命中他案相对方＝对抗性冲突事实入账（不产结论）
        self.assertEqual(exact_a[0]["queryRole"], "client")
        self.assertEqual(exact_a[0]["hitPartyRole"], "opposing")
        # 受控规范化：全角拉丁/全角空格折叠后精确命中
        normalized = [c for c in by_basis["exact_name"]
                      if c["hitMatterId"] == MATTER_B]
        self.assertEqual(normalized[0]["matchedText"], "ＡＢＣ合成腾讯科技有限公司")
        whitespace = [c for c in by_basis["exact_name"]
                      if c["hitPartyId"] == "p-chengjian"]
        self.assertEqual(len(whitespace), 1)
        # 别名/曾用名钉版本号
        self.assertEqual(by_basis["alias"][0]["aliasSeq"], 1)
        self.assertEqual(by_basis["former_name"][0]["aliasSeq"], 2)
        # 查检范围钉定：全所除本案＝2 件
        self.assertEqual(result["checkedMatterCount"], 2)
        # 候选账落行（append-only 账面）
        listed = legal_entry.call(
            "harness.conflict_candidates_list", {"scope": SCOPE_X},
            self.config)
        self.assertEqual(listed["count"], len(result["candidates"]))

    def test_02_no_fuzzy_semantics(self):
        result = legal_entry.call(
            "harness.conflict_check",
            {"actor_id": "lawyer-1", "scope": SCOPE_X, "key": _key("ck-neg"),
             "queries": [
                 {"role": "client", "name": "腾讯"},
                 {"role": "client", "name": "恒大合成集团有限公"},
                 {"role": "client", "name": "恒大合成集团有限责任公司"}]},
            self.config)
        self.assertEqual(result["candidates"], [])

    def test_03_check_idempotent_same_facts_no_duplicate_rows(self):
        again = legal_entry.call(
            "harness.conflict_check",
            {"actor_id": "lawyer-1", "scope": SCOPE_X, "key": _key("ck-2"),
             "queries": [{"role": "client", "name": "恒大合成集团有限公司"}]},
            self.config)
        first_ids = [c["candidateId"] for c in self.first_check["candidates"]
                     if c["queryName"] == "恒大合成集团有限公司"]
        self.assertEqual([c["candidateId"] for c in again["candidates"]],
                         first_ids)
        listed = legal_entry.call(
            "harness.conflict_candidates_list", {"scope": SCOPE_X},
            self.config)
        self.assertEqual(listed["count"], len(self.first_check["candidates"]))

    # -- 人工解除（E24 F62 人审确认闸同构：未审不入库） ----------------

    def test_04_release_without_decision_refused_named(self):
        candidate_id = self.first_check["candidates"][0]["candidateId"]
        with self.assertRaises(HarnessCommandError) as caught:
            legal_entry.call(
                "harness.conflict_release",
                {"actor_id": "lawyer-1", "scope": SCOPE_X,
                 "key": _key("rl-bad"),
                 "candidate_ref": {"candidateId": candidate_id},
                 "decision_ref": "not-a-ref"}, self.config)
        self.assertIn("ref_invalid", str(caught.exception))
        with self.assertRaises(HarnessCommandError) as caught:
            legal_entry.call(
                "harness.conflict_release",
                {"actor_id": "lawyer-1", "scope": SCOPE_X,
                 "key": _key("rl-bad2"),
                 "candidate_ref": {"candidateId": candidate_id},
                 "decision_ref": {"owner": "no-such-owner",
                                  "kind": "human-decision", "id": "d",
                                  "version": "1"}}, self.config)
        self.assertIn("ref_owner_unknown", str(caught.exception))
        # 未审不入库：解除未发生（候选仍无解除记录）
        view = legal_entry.call(
            "harness.conflict_candidate_read",
            {"scope": SCOPE_X, "candidate_id": candidate_id}, self.config)
        self.assertIsNone(view["released"])

    def test_05_release_records_who_when_scope(self):
        candidate = next(c for c in self.first_check["candidates"]
                         if c["matchBasis"] == "exact_name"
                         and c["hitMatterId"] == MATTER_A)
        released = legal_entry.call(
            "harness.conflict_release",
            {"actor_id": "lawyer-1", "scope": SCOPE_X, "key": _key("rl-1"),
             "candidate_ref": {"candidateId": candidate["candidateId"]},
             "decision_ref": _decision_ref("dec-f122-w1")}, self.config)
        record = released["scopeRecord"]
        self.assertEqual(record["releasedBy"], "lawyer-1")
        self.assertTrue(record["releasedAt"])
        self.assertEqual(record["hitMatterId"], MATTER_A)
        self.assertEqual(record["hitPartyRole"], "opposing")
        self.assertEqual(record["queryRole"], "client")
        self.assertEqual(record["checkedMatterCount"], 2)
        self.assertEqual(record["checkedMatterSetDigest"],
                         self.first_check["checkedMatterSetDigest"])
        self.assertIn("dec-f122-w1", record["decisionRef"])
        # 解除状态可回读；重复解除具名拒
        view = legal_entry.call(
            "harness.conflict_candidate_read",
            {"scope": SCOPE_X, "candidate_id": candidate["candidateId"]},
            self.config)
        self.assertEqual(view["released"]["releasedBy"], "lawyer-1")
        self.assertEqual(view["released"]["scope"]["matchBasis"], "exact_name")
        with self.assertRaises(HarnessCommandError) as caught:
            legal_entry.call(
                "harness.conflict_release",
                {"actor_id": "lawyer-1", "scope": SCOPE_X,
                 "key": _key("rl-2"),
                 "candidate_ref": {"candidateId": candidate["candidateId"]},
                 "decision_ref": _decision_ref("dec-f122-w2")}, self.config)
        self.assertIn("f122_candidate_already_released",
                      str(caught.exception))

    # -- 别名版本：变更后历史匹配不追溯改写 --------------------------

    def test_06_alias_revoke_narrows_scope_keeps_history_pinned(self):
        pinned = next(c for c in self.first_check["candidates"]
                      if c["matchBasis"] == "alias")
        legal_entry.call(
            "harness.conflict_alias_revoke",
            {"actor_id": "lawyer-1", "key": _key("rv-1"),
             "party_ref": {"id": "p-hengda"}, "alias": "恒大合成控股",
             "alias_kind": "alias"}, self.config)
        # 生效集即时收窄：重查不命中
        result = legal_entry.call(
            "harness.conflict_check",
            {"actor_id": "lawyer-1", "scope": SCOPE_X, "key": _key("ck-rv"),
             "queries": [{"role": "client", "name": "恒大合成控股"}]},
            self.config)
        self.assertEqual(result["candidates"], [])
        # 历史候选行原样（钉定 aliasSeq=1/文本快照不追溯改写）
        view = legal_entry.call(
            "harness.conflict_candidate_read",
            {"scope": SCOPE_X, "candidate_id": pinned["candidateId"]},
            self.config)
        self.assertEqual(view["aliasSeq"], 1)
        self.assertEqual(view["matchedText"], "恒大合成控股")
        # 版本全列带生效标记
        aliases = legal_entry.call(
            "harness.conflict_alias_list", {"party_ref": {"id": "p-hengda"}},
            self.config)
        effective = {(i["aliasKind"], i["aliasSeq"]): i["effective"]
                     for i in aliases["items"]}
        self.assertFalse(effective[("alias", 1)])
        self.assertTrue(effective[("former_name", 2)])

    # -- 主体字段登记面负向 ------------------------------------------

    def test_07_case_party_role_conflict_refused(self):
        with self.assertRaises(HarnessCommandError) as caught:
            legal_entry.call(
                "harness.conflict_case_party_attach",
                {"actor_id": "lawyer-1", "scope": SCOPE_X,
                 "key": _key("cp-bad"),
                 "party_ref": {"id": "p-newclient"}, "role": "opposing"},
                self.config)
        self.assertIn("f122_case_party_role_conflict", str(caught.exception))
        view = legal_entry.call(
            "harness.conflict_case_party_list", {"scope": SCOPE_X},
            self.config)
        self.assertEqual(
            [(i["partyId"], i["role"]) for i in view["items"]],
            [("p-newclient", "client")])

    # -- 桥纪律（fail-closed＋AST 结构断言） --------------------------

    def test_08_bridge_fail_closed(self):
        # 未配置桥＝NotConnected 具名（fail-closed 不空转）
        with self.assertRaises(NotConnected) as caught:
            legal_entry.call(
                "harness.conflict_check",
                {"actor_id": "lawyer-1", "scope": SCOPE_X, "key": _key("x"),
                 "queries": [{"role": "client", "name": "甲"}]}, {})
        self.assertIn("harness_public_entry_not_configured", str(caught.exception))
        # 封闭注册外方法＝具名拒（无自动代解/无静默成功）
        with self.assertRaises(NotConnected) as caught:
            legal_entry.call(
                "harness.conflict_auto_decide",
                {"scope": SCOPE_X}, self.config)
        self.assertIn("method_not_connected", str(caught.exception))

    def test_09_ast_conflict_dispatch_in_desensitized_domain(self):
        """脱敏域纪律结构断言：conflict 派发段零 anonymizer/rehydrate/
        模糊匹配引用；冻结方法组恰九方法；派发走唯一机械入口。"""
        source = (ROOT / "python" / "legal_entry.py").read_text(
            encoding="utf-8")
        tree = ast.parse(source)
        conflict_if = None
        for node in ast.walk(tree):
            if isinstance(node, ast.If) and isinstance(node.test, ast.Compare):
                names = {n.id for n in ast.walk(node.test)
                         if isinstance(n, ast.Name)}
                if "CONFLICT_CHECK_METHODS" in names:
                    conflict_if = node
                    break
        self.assertIsNotNone(conflict_if,
                              "conflict dispatch branch missing")
        tokens = {n.id.lower() for n in ast.walk(conflict_if)
                  if isinstance(n, ast.Name)} | {
            n.attr.lower() for n in ast.walk(conflict_if)
            if isinstance(n, ast.Attribute)}
        for forbidden in ("anonymizer", "rehydrate", "difflib",
                          "fuzz", "levenshtein"):
            self.assertNotIn(forbidden, tokens)
        # 派发体只走 _harness_provider_entry（唯一机械入口；isinstance 守卫
        # 与 NotConnected 例外之外零其他调用形态）
        calls = [n for n in ast.walk(conflict_if) if isinstance(n, ast.Call)]
        provider_calls = [c for c in calls
                          if isinstance(c.func, ast.Name)
                          and c.func.id == "_harness_provider_entry"]
        other_calls = [c for c in calls
                       if not (isinstance(c.func, ast.Name)
                               and c.func.id in ("_harness_provider_entry",
                                                 "isinstance", "NotConnected"))]
        self.assertEqual(len(provider_calls), 1)
        self.assertEqual(other_calls, [])
        # 冻结方法组恰九方法、全数在 harness 封闭注册表内
        registry = ast.parse((HARNESS_WORKTREE / "src" / "legal_harness" /
                              "business" / "provider_registry.py").read_text(
                                  encoding="utf-8"))
        registered = set()
        for node in ast.walk(registry):
            if isinstance(node, ast.Dict):
                for key in node.keys:
                    if isinstance(key, ast.Constant) \
                            and isinstance(key.value, str) \
                            and key.value.startswith("harness.conflict_"):
                        registered.add(key.value)
        group = legal_entry.CONFLICT_CHECK_METHODS
        self.assertEqual(len(group), 9)
        self.assertTrue(group.issubset(registered),
                        f"{group - registered} not in closed registry")

    def test_10_frozen_method_group_exported(self):
        self.assertTrue(
            legal_entry.CONFLICT_CHECK_METHODS.isdisjoint(
                {"contacts.check_conflicts", "contacts.decide_conflict"}),
            "F122 surface must not rebuild the W09 contacts face")


if __name__ == "__main__":
    unittest.main()
