# -*- coding: utf-8 -*-
"""F122 利益冲突查重 验收 recon（工单 W4-U53）。

06 F122（v1.5；owner=product+harness；desktop/selfhost 双实例；
acceptance：客户/相对方/别名冲突候选真实匹配，人工解除留范围记录；
preserved：收案前合规小件，规则匹配即可）。

验收命令（工单钦定，worktree 根 cwd）：
  python -X utf8 tools/PENDING_OWNER_f122_conflict_check_recon.py \\
      --profile desktop --profile selfhost
exit 0 = RECON_OK。

  - desktop 腿＝真产品入口 legal_entry 子进程径（CONFLICT_CHECK_METHODS
    冻结组 → harness public_entry --conflict-json 信封真子进程；临时
    SQLite 状态根）；
  - selfhost 腿＝PgMatterStore 直连 lh-pg-e08 独立 schema（同 E24/F118
    recon selfhost 腿同径；resolve_provider_method 同一封闭注册；用毕
    destroy）。

断言面（全合成材料；查询名/主体名全部假名域内合成文本）：
  S1 真实匹配＝确定性规则匹配：主体名精确/受控规范化（全角→半角、
     大小写折叠、空白折叠）跨案件命中他案主体字段；子串/近形/一字之
     差零命中（零模糊语义——LegalTech 约束 1）；
  S2 命中＝冲突候选账 append-only：同事实重查幂等不双记；旧行永不改写；
  S3 解除＝人工决定面（E24 F62 人审确认闸同构：未审不入库）——无决定
     凭据具名拒不入账；解除范围记录钉定谁/何时/基于什么范围（候选事实
     快照＋查检范围摘要＋决定凭据）；重复解除具名拒；
  S4 别名/曾用名维护留版本：撤销后生效集即时收窄（重查不命中），历史
     候选行钉定旧版本/文本快照不追溯改写；复活后重查出新行（新事实新
     候选）；
  S5 脱敏域纪律（F37 协调）：conflict 派发段 AST 零 anonymizer/rehydrate
     /模糊匹配引用；检索只读本仓账面（查询名原样透传 harness store）；
  S6 桥纪律：未配置 NotConnected 具名／封闭注册外方法具名拒（desktop
     子进程径＋selfhost 直连径同语义）；
  S7 双 profile 一致：desktop/selfhost 同一合成案卷同查同答（语义投影
     逐键相等——候选集/依据/角色/范围摘要）。
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

RUN_DATE = time.strftime("%Y%m%d")
REPO_ROOT = Path(__file__).resolve().parents[1]
LEGAL_ENTRY = REPO_ROOT / "implementation" / "python" / "legal_entry.py"

# harness 战役分支（A2 链）本单检出与 F122 面钉定
HARNESS_WORKTREE = Path(
    r"D:\Codex\1.法律工作区\legal-harness工作区\legal-harness-repo"
    r"\.local\worktrees\w4-u53")
HARNESS_PUBLIC_ENTRY = HARNESS_WORKTREE / Path(
    "tools/workflow-tools/harness/public_entry.py")
HARNESS_BRANCH = "w4-u53"

DEFAULT_PG_DSN = "postgresql://lh_app:e08-synth-only@127.0.0.1:55432/legal_harness"

MATTER_X = "m-f122-rx"   # 收案审查本案（desktop/selfhost 同名复算）
MATTER_A = "m-f122-ra"
MATTER_B = "m-f122-rb"

SCOPE_X = {"kind": "matter", "matterId": MATTER_X}
SCOPE_A = {"kind": "matter", "matterId": MATTER_A}
SCOPE_B = {"kind": "matter", "matterId": MATTER_B}

F122_METHODS = frozenset({
    "harness.conflict_case_party_attach", "harness.conflict_case_party_list",
    "harness.conflict_alias_record", "harness.conflict_alias_revoke",
    "harness.conflict_alias_list", "harness.conflict_check",
    "harness.conflict_release", "harness.conflict_candidates_list",
    "harness.conflict_candidate_read",
})


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _key(request_id: str) -> dict:
    return {"requestId": request_id, "targetId": None,
            "expectedRevision": None, "inputRefs": []}


def _party(party_id: str, display_name: str) -> dict:
    return {"id": party_id, "kind": "party", "version": "1",
            "displayName": display_name}


def _decision_ref(decision_id: str) -> dict:
    return {"owner": "host", "kind": "human-decision",
            "id": decision_id, "version": "1"}


class Checks:
    def __init__(self, profile: str) -> None:
        self.profile = profile
        self.items: list = []

    def step(self, check_id: str, ok: bool, detail: str = "", **extra) -> None:
        item = {"id": check_id, "status": "PASS" if ok else "FAIL",
                "detail": detail}
        if extra:
            item.update(extra)
        self.items.append(item)

    @property
    def failed(self) -> list:
        return [i for i in self.items if i["status"] != "PASS"]

    @property
    def verdict(self) -> str:
        return "RECON_OK" if self.items and not self.failed else "RECON_FAILED"


def call_entry(method: str, args: dict, config: dict) -> dict:
    """真产品入口子进程调用；返回 {exit, payload}。"""
    request_handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", suffix=".json", delete=False)
    config_handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", suffix=".json", delete=False)
    try:
        json.dump({"method": method, "args": args}, request_handle,
                  ensure_ascii=False)
        request_handle.close()
        json.dump(config, config_handle, ensure_ascii=False)
        config_handle.close()
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", str(LEGAL_ENTRY),
             "--request-json", request_handle.name,
             "--config", config_handle.name],
            capture_output=True, text=True, encoding="utf-8",
            timeout=600, cwd=str(REPO_ROOT))
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            payload = {"_raw": proc.stdout[-500:]}
        return {"exit": proc.returncode, "payload": payload}
    finally:
        os.unlink(request_handle.name)
        os.unlink(config_handle.name)


def call_harness(method: str, params: dict, state_root: Path) -> dict:
    """harness public_entry --conflict-json 信封子进程径（夹具/对照半边）。"""
    command_handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", suffix=".json", delete=False)
    try:
        json.dump({"method": method, "params": params}, command_handle,
                  ensure_ascii=False)
        command_handle.close()
        env = dict(os.environ)
        env["LH_LEGAL_STATE_ROOT"] = str(state_root)
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", str(HARNESS_PUBLIC_ENTRY),
             "--conflict-json", command_handle.name, "--target", "opencode"],
            capture_output=True, text=True, encoding="utf-8", timeout=600,
            cwd=str(HARNESS_WORKTREE), env=env)
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            payload = {"_raw": (proc.stdout + proc.stderr)[-500:]}
        return {"exit": proc.returncode, "payload": payload}
    finally:
        os.unlink(command_handle.name)


def entry_call(method: str, args: dict, config: dict) -> dict:
    """产品入口调用（类型化错误规范化为 HarnessCommandError 语义断言用；
    legal_entry 失败信封＝{"status": HARNESS_FAIL/NOT_CONNECTED, "code": …}
    ——错误链：public_entry FAIL.error → _harness_provider_entry →
    HarnessCommandError → legal_entry code 原样透传）。"""
    from bridge_errors import HarnessCommandError
    response = call_entry(method, args, config)
    if response["exit"] == 0:
        return response["payload"]["result"]
    code = response["payload"].get("code")         or response["payload"].get("error") or "entry_failed"
    raise HarnessCommandError(str(code))


def build_casebook(callable_contact, callable_conflict) -> None:
    """合成案卷（两件在办案件＋一件收案审查本案；全部假名域合成文本）。"""
    callable_contact("contacts.upsert",
                     {"actor_id": "lawyer-1", "scope": SCOPE_A,
                      "key": _key("cu-1"),
                      "party_ref": _party("p-hengda", "恒大合成集团有限公司"),
                      "alias_refs": [], "relationship_refs": []})
    callable_conflict("harness.conflict_alias_record",
                      {"actor_id": "lawyer-1", "key": _key("al-1"),
                       "party_ref": {"id": "p-hengda"},
                       "alias": "恒大合成控股", "alias_kind": "alias"})
    callable_conflict("harness.conflict_alias_record",
                      {"actor_id": "lawyer-1", "key": _key("al-2"),
                       "party_ref": {"id": "p-hengda"},
                       "alias": "恒大合成地产", "alias_kind": "former_name"})
    callable_conflict("harness.conflict_case_party_attach",
                      {"actor_id": "lawyer-1", "scope": SCOPE_A,
                       "key": _key("cp-1"),
                       "party_ref": {"id": "p-hengda"}, "role": "opposing"})
    callable_contact("contacts.upsert",
                     {"actor_id": "lawyer-1", "scope": SCOPE_A,
                      "key": _key("cu-2"),
                      "party_ref": _party("p-chengjian",
                                          "合成城建置业有限　公司"),
                      "alias_refs": [], "relationship_refs": []})
    callable_conflict("harness.conflict_case_party_attach",
                      {"actor_id": "lawyer-1", "scope": SCOPE_A,
                       "key": _key("cp-2"),
                       "party_ref": {"id": "p-chengjian"}, "role": "client"})
    callable_contact("contacts.upsert",
                     {"actor_id": "lawyer-1", "scope": SCOPE_B,
                      "key": _key("cu-3"),
                      "party_ref": _party("p-tencent",
                                          "ＡＢＣ合成腾讯科技有限公司"),
                      "alias_refs": [], "relationship_refs": []})
    callable_conflict("harness.conflict_case_party_attach",
                      {"actor_id": "lawyer-1", "scope": SCOPE_B,
                       "key": _key("cp-3"),
                       "party_ref": {"id": "p-tencent"}, "role": "client"})
    callable_contact("contacts.upsert",
                     {"actor_id": "lawyer-1", "scope": SCOPE_X,
                      "key": _key("cu-4"),
                      "party_ref": _party("p-newclient", "合成新委托人有限公司"),
                      "alias_refs": [], "relationship_refs": []})
    callable_conflict("harness.conflict_case_party_attach",
                      {"actor_id": "lawyer-1", "scope": SCOPE_X,
                       "key": _key("cp-4"),
                       "party_ref": {"id": "p-newclient"}, "role": "client"})


CHECK_QUERIES = [
    {"role": "client", "name": "恒大合成集团有限公司"},        # 精确名→A 相对方
    {"role": "opposing", "name": "abc合成腾讯科技有限公司"},   # 受控规范化→B 客户
    {"role": "client", "name": "恒大合成控股"},                # 别名→A
    {"role": "opposing", "name": "恒大合成地产"},              # 曾用名→A
    {"role": "client", "name": "合成城建置业有限 公司"},        # 空白折叠→A 客户
]


def section_s1_s4(checks: Checks, conflict_call, contact_call) -> dict:
    """S1-S4 主链（desktop 子进程径/selfhost 直连径共用断言面）。"""
    build_casebook(contact_call, conflict_call)

    # S1 真实匹配（四类依据）
    first = conflict_call(
        "harness.conflict_check",
        {"actor_id": "lawyer-1", "scope": SCOPE_X, "key": _key("ck-1"),
         "queries": CHECK_QUERIES})
    by_basis = {}
    for candidate in first["candidates"]:
        by_basis.setdefault(candidate["matchBasis"], []).append(candidate)
    checks.step(
        "s1_real_match_all_bases",
        sorted(by_basis) == ["alias", "exact_name", "former_name"]
        and len(by_basis.get("exact_name", [])) == 3,
        "bases=%s counts=%s" % (
            sorted(by_basis),
            {k: len(v) for k, v in sorted(by_basis.items())}))
    exact_a = by_basis.get("exact_name", [{}])[0]
    checks.step(
        "s1_client_query_hits_opposing_of_case_a",
        exact_a.get("queryRole") == "client"
        and exact_a.get("hitMatterId") == MATTER_A
        and exact_a.get("hitPartyRole") == "opposing",
        "candidate=%s" % json.dumps(exact_a, ensure_ascii=False)[:220])
    normalized = [c for c in by_basis.get("exact_name", [])
                  if c["hitMatterId"] == MATTER_B]
    checks.step(
        "s1_controlled_normalization_fullwidth",
        len(normalized) == 1
        and normalized[0]["matchedText"] == "ＡＢＣ合成腾讯科技有限公司"
        and normalized[0]["queryRole"] == "opposing",
        "hit=%s" % json.dumps(normalized, ensure_ascii=False)[:200])
    alias = by_basis.get("alias", [{}])
    former = by_basis.get("former_name", [{}])
    checks.step(
        "s1_alias_and_former_name_pinned_versions",
        alias and alias[0].get("aliasSeq") == 1
        and former and former[0].get("aliasSeq") == 2,
        "aliasSeq=%s formerSeq=%s" % (
            alias[0].get("aliasSeq") if alias else None,
            former[0].get("aliasSeq") if former else None))
    whitespace = [c for c in by_basis.get("exact_name", [])
                  if c["hitPartyId"] == "p-chengjian"]
    checks.step(
        "s1_whitespace_collapse_hit", len(whitespace) == 1,
        "hits=%d" % len(whitespace))
    checks.step(
        "s1_scope_pinned_all_other_matters",
        first["checkedMatterCount"] == 2
        and first["checkedMatterSetDigest"] == hashlib.sha256(
            "\n".join(sorted([MATTER_A, MATTER_B])).encode("utf-8")
        ).hexdigest(),
        "count=%s digest=%s" % (first["checkedMatterCount"],
                                first["checkedMatterSetDigest"][:16] + "…"))

    # S1 零模糊语义（子串/近形/一字之差零命中）
    no_fuzzy = conflict_call(
        "harness.conflict_check",
        {"actor_id": "lawyer-1", "scope": SCOPE_X, "key": _key("ck-neg"),
         "queries": [
             {"role": "client", "name": "腾讯"},
             {"role": "client", "name": "恒大合成集团有限公"},
             {"role": "client", "name": "恒大合成集团有限责任公司"}]})
    checks.step(
        "s1_no_fuzzy_substring_or_nearform",
        no_fuzzy["candidates"] == [],
        "unexpected=%d" % len(no_fuzzy["candidates"]))

    # S2 append-only＋幂等（同事实重查不双记）
    second = conflict_call(
        "harness.conflict_check",
        {"actor_id": "lawyer-1", "scope": SCOPE_X, "key": _key("ck-2"),
         "queries": [{"role": "client", "name": "恒大合成集团有限公司"}]})
    first_ids = [c["candidateId"] for c in first["candidates"]
                 if c["queryName"] == "恒大合成集团有限公司"]
    checks.step(
        "s2_same_facts_idempotent_no_duplicate",
        [c["candidateId"] for c in second["candidates"]] == first_ids
        and len(first_ids) == 1,
        "first=%s second=%s" % (first_ids,
                                [c["candidateId"] for c in
                                 second["candidates"]]))

    # S3 解除＝人工决定面（未审不入库）
    candidate_exact = next(c for c in first["candidates"]
                           if c["matchBasis"] == "exact_name"
                           and c["hitMatterId"] == MATTER_A)
    refused = False
    try:
        conflict_call(
            "harness.conflict_release",
            {"actor_id": "lawyer-1", "scope": SCOPE_X, "key": _key("rl-bad"),
             "candidate_ref": {"candidateId": candidate_exact["candidateId"]},
             "decision_ref": "not-a-ref"})
    except Exception as exc:  # HarnessCommandError / UnitsError 直连径
        refused = "ref_invalid" in str(exc) or "ref_owner_unknown" in str(exc)
    checks.step(
        "s3_release_without_decision_refused_named", refused,
        "typed refusal required (E24 F62 isomorphic)")
    view_before = conflict_call(
        "harness.conflict_candidate_read",
        {"scope": SCOPE_X, "candidate_id": candidate_exact["candidateId"]})
    checks.step(
        "s3_unreviewed_release_never_landed",
        view_before.get("released") is None,
        "released=%s" % view_before.get("released"))
    released = conflict_call(
        "harness.conflict_release",
        {"actor_id": "lawyer-1", "scope": SCOPE_X, "key": _key("rl-1"),
         "candidate_ref": {"candidateId": candidate_exact["candidateId"]},
         "decision_ref": _decision_ref("dec-f122-r1")})
    record = released["scopeRecord"]
    checks.step(
        "s3_release_scope_record_who_when_scope",
        record["releasedBy"] == "lawyer-1"
        and bool(record["releasedAt"])
        and record["candidateId"] == candidate_exact["candidateId"]
        and record["hitMatterId"] == MATTER_A
        and record["hitPartyRole"] == "opposing"
        and record["matchBasis"] == "exact_name"
        and record["checkedMatterCount"] == 2
        and record["checkedMatterSetDigest"] == first["checkedMatterSetDigest"]
        and "dec-f122-r1" in record["decisionRef"],
        "scope keys=%s" % sorted(record))
    view_after = conflict_call(
        "harness.conflict_candidate_read",
        {"scope": SCOPE_X, "candidate_id": candidate_exact["candidateId"]})
    checks.step(
        "s3_release_readback",
        view_after["released"] is not None
        and view_after["released"]["releasedBy"] == "lawyer-1"
        and view_after["released"]["scope"]["matchBasis"] == "exact_name",
        "released=%s" % json.dumps(view_after["released"],
                                   ensure_ascii=False)[:200])
    double_refused = False
    try:
        conflict_call(
            "harness.conflict_release",
            {"actor_id": "lawyer-1", "scope": SCOPE_X, "key": _key("rl-2"),
             "candidate_ref": {"candidateId": candidate_exact["candidateId"]},
             "decision_ref": _decision_ref("dec-f122-r2")})
    except Exception as exc:
        double_refused = "f122_candidate_already_released" in str(exc)
    checks.step(
        "s3_double_release_refused_named", double_refused,
        "one candidate one release")

    # S4 别名版本：撤销收窄＋历史钉定＋复活新行
    pinned_alias = next(c for c in first["candidates"]
                        if c["matchBasis"] == "alias")
    conflict_call(
        "harness.conflict_alias_revoke",
        {"actor_id": "lawyer-1", "key": _key("rv-1"),
         "party_ref": {"id": "p-hengda"}, "alias": "恒大合成控股",
         "alias_kind": "alias"})
    after_revoke = conflict_call(
        "harness.conflict_check",
        {"actor_id": "lawyer-1", "scope": SCOPE_X, "key": _key("ck-rv"),
         "queries": [{"role": "client", "name": "恒大合成控股"}]})
    checks.step(
        "s4_revoke_narrows_effective_scope",
        after_revoke["candidates"] == [],
        "post-revoke hits=%d" % len(after_revoke["candidates"]))
    pinned_view = conflict_call(
        "harness.conflict_candidate_read",
        {"scope": SCOPE_X, "candidate_id": pinned_alias["candidateId"]})
    checks.step(
        "s4_history_not_retroactively_rewritten",
        pinned_view["aliasSeq"] == 1
        and pinned_view["matchedText"] == "恒大合成控股"
        and pinned_view["matchBasis"] == "alias",
        "pinned=%s/%s" % (pinned_view["aliasSeq"], pinned_view["matchedText"]))
    revived = conflict_call(
        "harness.conflict_alias_record",
        {"actor_id": "lawyer-1", "key": _key("rv-2"),
         "party_ref": {"id": "p-hengda"}, "alias": "恒大合成控股",
         "alias_kind": "alias"})
    after_revive = conflict_call(
        "harness.conflict_check",
        {"actor_id": "lawyer-1", "scope": SCOPE_X, "key": _key("ck-rrv"),
         "queries": [{"role": "client", "name": "恒大合成控股"}]})
    checks.step(
        "s4_revive_creates_new_version_new_row",
        revived["created"] and revived["aliasSeq"] == 4
        and len(after_revive["candidates"]) == 1
        and after_revive["candidates"][0]["aliasSeq"] == 4
        and after_revive["candidates"][0]["candidateId"]
        != pinned_alias["candidateId"],
        "revivedSeq=%s newCandidate=%s" % (
            revived["aliasSeq"],
            after_revive["candidates"][0]["candidateId"]
            if after_revive["candidates"] else None))
    aliases = conflict_call(
        "harness.conflict_alias_list", {"party_ref": {"id": "p-hengda"}})
    effective = {(i["aliasKind"], i["aliasSeq"]): i["effective"]
                 for i in aliases["items"]}
    checks.step(
        "s4_alias_versions_effective_markers",
        effective.get(("alias", 1)) is False
        and effective.get(("alias", 3)) is False
        and effective.get(("alias", 4)) is True
        and effective.get(("former_name", 2)) is True,
        "effective=%s" % sorted("%s#%s=%s" % (kind, seq, eff)
                                for (kind, seq), eff in effective.items()))

    # 主体字段登记面负向（同案换角色具名拒）
    role_refused = False
    try:
        conflict_call(
            "harness.conflict_case_party_attach",
            {"actor_id": "lawyer-1", "scope": SCOPE_X, "key": _key("cp-bad"),
             "party_ref": {"id": "p-newclient"}, "role": "opposing"})
    except Exception as exc:
        role_refused = "f122_case_party_role_conflict" in str(exc)
    checks.step(
        "s4_case_party_role_conflict_refused", role_refused,
        "role switch never silently rewritten")

    return {"first": first, "release_record": record,
            "pinned": pinned_view, "revive": after_revive}


def section_s5_ast(checks: Checks) -> None:
    """S5 脱敏域纪律（F37 协调）：conflict 派发段零 anonymizer/rehydrate/
    模糊匹配引用；派发走唯一机械入口；冻结组恰九方法且在封闭注册表内。"""
    source = (REPO_ROOT / "implementation" / "python" / "legal_entry.py"
              ).read_text(encoding="utf-8")
    tree = ast.parse(source)
    conflict_if = None
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and isinstance(node.test, ast.Compare):
            names = {n.id for n in ast.walk(node.test)
                     if isinstance(n, ast.Name)}
            if "CONFLICT_CHECK_METHODS" in names:
                conflict_if = node
                break
    checks.step("s5_conflict_dispatch_present", conflict_if is not None)
    if conflict_if is None:
        return
    tokens = {n.id.lower() for n in ast.walk(conflict_if)
              if isinstance(n, ast.Name)} | {
        n.attr.lower() for n in ast.walk(conflict_if)
        if isinstance(n, ast.Attribute)}
    forbidden_hit = [w for w in ("anonymizer", "rehydrate", "difflib",
                                 "fuzz", "levenshtein") if w in tokens]
    calls = [n for n in ast.walk(conflict_if) if isinstance(n, ast.Call)]
    provider_calls = [c for c in calls
                      if isinstance(c.func, ast.Name)
                      and c.func.id == "_harness_provider_entry"]
    other_calls = [c for c in calls
                   if not (isinstance(c.func, ast.Name)
                           and c.func.id in ("_harness_provider_entry",
                                             "isinstance", "NotConnected"))]
    checks.step(
        "s5_desensitized_domain_no_mapping_access",
        conflict_if is not None and not forbidden_hit and len(provider_calls) == 1
        and not other_calls,
        "forbidden=%s provider_calls=%d other=%d" % (
            forbidden_hit, len(provider_calls), len(other_calls)))
    # 冻结组与封闭注册表对账
    sys.path.insert(0, str(REPO_ROOT / "implementation" / "python"))
    import legal_entry
    group = getattr(legal_entry, "CONFLICT_CHECK_METHODS", frozenset())
    registry_source = (HARNESS_WORKTREE / "src" / "legal_harness" /
                       "business" / "provider_registry.py").read_text(
                           encoding="utf-8")
    registered = set()
    for node in ast.walk(ast.parse(registry_source)):
        if isinstance(node, ast.Dict):
            for k in node.keys:
                if isinstance(k, ast.Constant) and isinstance(k.value, str) \
                        and k.value.startswith("harness.conflict_"):
                    registered.add(k.value)
    checks.step(
        "s5_frozen_group_nine_methods_in_closed_registry",
        len(group) == 9 and group.issubset(registered),
        "group=%d registered=%d missing=%s" % (
            len(group), len(registered), sorted(group - registered)
            if group - registered else []))


def section_s6_bridge(checks: Checks, config: dict) -> None:
    """S6 桥纪律（desktop 子进程径）：未配置具名／封闭注册外具名拒。"""
    unconfigured = call_entry(
        "harness.conflict_check",
        {"actor_id": "lawyer-1", "scope": SCOPE_X, "key": _key("nc"),
         "queries": [{"role": "client", "name": "甲"}]}, {})
    ok = (unconfigured["exit"] == 3
          and unconfigured["payload"].get("status") == "NOT_CONNECTED"
          and "harness_public_entry_not_configured"
          in str(unconfigured["payload"].get("code")))
    checks.step("s6_unconfigured_not_connected", ok,
                "exit=%s status=%s code=%s" % (
                    unconfigured["exit"],
                    unconfigured["payload"].get("status"),
                    str(unconfigured["payload"].get("code"))[:80]))
    if not ok:
        return
    response = call_entry("harness.conflict_auto_decide",
                          {"scope": SCOPE_X}, config)
    refused = (response["exit"] == 3
               and response["payload"].get("status") == "NOT_CONNECTED"
               and "method_not_connected" in str(response["payload"].get("code")))
    checks.step("s6_closed_registry_refused", refused,
                "exit=%s code=%s" % (response["exit"],
                                     str(response["payload"].get("code"))[:80]))


def run_desktop(recon_out: Path) -> int:
    sys.path.insert(0, str(REPO_ROOT / "implementation" / "python"))
    checks = Checks("desktop")
    started = datetime.now(timezone.utc)
    holder = tempfile.TemporaryDirectory(prefix="juscite-f122-desktop-")
    state_root = Path(holder.name) / "state"
    state_root.mkdir(parents=True)
    config = {
        "harness_public_entry": str(HARNESS_PUBLIC_ENTRY),
        "harness_target": "opencode",
        "harness_state_root": str(state_root),
        "harness_timeout": 120,
    }
    if str(REPO_ROOT / "implementation" / "python") not in sys.path:
        sys.path.insert(0, str(REPO_ROOT / "implementation" / "python"))
    if str(HARNESS_WORKTREE / "src") not in sys.path:
        sys.path.insert(0, str(HARNESS_WORKTREE / "src"))
    from legal_harness.state.matter_store import MatterStore
    store = MatterStore(state_root)
    for matter_id in (MATTER_X, MATTER_A, MATTER_B):
        store.create_matter(matter_id, "cas://profile-f122-desktop")

    def conflict_call(method, params):
        return entry_call(method, params, config)

    def contact_call(method, params):
        response = call_harness(method, params, state_root)
        if response["exit"] != 0:
            raise HarnessCommandError(
                str(response["payload"].get("error") or "harness_failed"))
        return response["payload"]["result"]

    try:
        checks.step(
            "s0_pinned_harness_worktree",
            HARNESS_PUBLIC_ENTRY.is_file(),
            "worktree=%s entry=%s" % (HARNESS_WORKTREE,
                                      sha256_file(HARNESS_PUBLIC_ENTRY)[:16]))
        section_s1_s4(checks, conflict_call, contact_call)
        section_s5_ast(checks)
        section_s6_bridge(checks, config)
        # S7 对照面：desktop 投影供跨 profile 对账
        listed = conflict_call("harness.conflict_candidates_list",
                               {"scope": SCOPE_X})
        checks.step(
            "s7_desktop_projection_captured",
            listed["count"] >= 3,
            "candidates=%d" % listed["count"])
        projection = {
            "candidates": [
                {k: v for k, v in item.items()
                 if k in ("candidateId", "queryRole", "hitMatterId",
                          "hitPartyRole", "matchBasis", "matchedNormalized",
                          "aliasSeq", "checkedMatterCount")}
                for item in listed["items"]],
        }
        recon_out.mkdir(parents=True, exist_ok=True)
        (recon_out / "f122-desktop-projection.json").write_text(
            json.dumps(projection, ensure_ascii=False, sort_keys=True,
                       indent=1), encoding="utf-8")
    finally:
        holder.cleanup()
    return finish(checks, started, recon_out)


def run_selfhost(recon_out: Path, dsn: str) -> int:
    """selfhost＝PgMatterStore 直连 lh-pg-e08 独立 schema（E24/F118 recon
    selfhost 腿同径；resolve_provider_method 同一封闭注册；用毕 destroy）。"""
    for path in (str(HARNESS_WORKTREE / "src"),
                 str(HARNESS_WORKTREE / "tools/workflow-tools"),
                 str(HARNESS_WORKTREE), str(HARNESS_WORKTREE / "tests")):
        if path not in sys.path:
            sys.path.insert(0, path)
    from legal_harness.business.provider_registry import (
        MethodNotWhitelisted,
        resolve_provider_method,
    )
    from legal_harness.business.units import HarnessUnits, UnitsError
    from legal_harness.state.pg_store import PgMatterStore

    checks = Checks("selfhost")
    started = datetime.now(timezone.utc)
    temporary = tempfile.TemporaryDirectory(prefix="juscite-f122-selfhost-")
    store = PgMatterStore(
        Path(temporary.name) / "state", dsn=dsn,
        schema="f122_" + uuid.uuid4().hex[:12])
    units = HarnessUnits(store)
    bound = {name: resolve_provider_method(name, units)
             for name in F122_METHODS}
    for matter_id in (MATTER_X, MATTER_A, MATTER_B):
        store.create_matter(matter_id, "cas://profile-f122-selfhost")

    class _BridgeError(Exception):
        pass

    def conflict_call(method, params):
        target = bound.get(method)
        if target is None:
            raise MethodNotWhitelisted(method)
        try:
            return target(**params)
        except UnitsError as exc:  # 直连径错误规范化为桥错误型（同 desktop 语义）
            raise _BridgeError(str(exc)) from exc

    def contact_call(method, params):
        contacts = {name: resolve_provider_method(name, units)
                    for name in ("contacts.upsert",)}
        try:
            return contacts[method](**params)
        except UnitsError as exc:
            raise _BridgeError(str(exc)) from exc

    try:
        checks.step(
            "s0_selfhost_pg_schema",
            True,
            "schema=%s dsn=%s" % (store.schema, dsn.split("@")[-1]))
        section_s1_s4(checks, conflict_call, contact_call)
        # 封闭注册负向（selfhost 同语义）
        try:
            resolve_provider_method("harness.conflict_auto_decide", units)
            checks.step("s6_selfhost_closed_registry_refused", False,
                        "expected MethodNotWhitelisted")
        except MethodNotWhitelisted as exc:
            checks.step("s6_selfhost_closed_registry_refused", True,
                        code=str(exc))
        # S7 对照面：selfhost 投影供跨 profile 对账
        listed = conflict_call("harness.conflict_candidates_list",
                               {"scope": SCOPE_X})
        projection = {
            "candidates": [
                {k: v for k, v in item.items()
                 if k in ("candidateId", "queryRole", "hitMatterId",
                          "hitPartyRole", "matchBasis", "matchedNormalized",
                          "aliasSeq", "checkedMatterCount")}
                for item in listed["items"]],
        }
        recon_out.mkdir(parents=True, exist_ok=True)
        (recon_out / "f122-selfhost-projection.json").write_text(
            json.dumps(projection, ensure_ascii=False, sort_keys=True,
                       indent=1), encoding="utf-8")
        checks.step(
            "s7_selfhost_projection_captured",
            len(projection["candidates"]) >= 3,
            "candidates=%d" % len(projection["candidates"]))
    finally:
        store.destroy()
        temporary.cleanup()
    return finish(checks, started, recon_out)


def finish(checks: Checks, started: datetime, recon_out: Path) -> int:
    finished = datetime.now(timezone.utc)
    doc = {
        "unit": "W4-U53",
        "instance": "F122",
        "profile": checks.profile,
        "verdict": checks.verdict,
        "counts": {"pass": sum(1 for c in checks.items
                               if c["status"] == "PASS"),
                   "total": len(checks.items)},
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "harness_pin": {"branch": HARNESS_BRANCH,
                        "head": _harness_head(),
                        "public_entry_sha256":
                            sha256_file(HARNESS_PUBLIC_ENTRY)},
        "checks": checks.items,
    }
    recon_out.mkdir(parents=True, exist_ok=True)
    out = recon_out / "recon-result.json"
    out.write_text(json.dumps(doc, ensure_ascii=False, sort_keys=True,
                              indent=1), encoding="utf-8")
    print("[%s] %s  %d/%d PASS  -> %s" % (
        checks.profile, checks.verdict, doc["counts"]["pass"],
        doc["counts"]["total"], out))
    for item in checks.failed:
        print("  FAIL %s: %s" % (item["id"], item["detail"]))
    return 0 if checks.verdict == "RECON_OK" else 1


def _harness_head() -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(HARNESS_WORKTREE),
        capture_output=True, text=True, encoding="utf-8")
    return proc.stdout.strip() if proc.returncode == 0 else "unknown"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", action="append",
                        choices=["desktop", "selfhost"],
                        help="可重复：--profile desktop --profile selfhost")
    parser.add_argument("--pg-dsn", default=DEFAULT_PG_DSN)
    args = parser.parse_args()
    profiles = args.profile or ["desktop", "selfhost"]
    exit_code = 0
    if "desktop" in profiles:
        exit_code |= run_desktop(REPO_ROOT / "evidence" / "F122" / "desktop")
    if "selfhost" in profiles:
        exit_code |= run_selfhost(
            REPO_ROOT / "evidence" / "F122" / "selfhost", args.pg_dsn)
    # S7 跨 profile 对账（两腿都跑了才有对照面）
    if set(profiles) == {"desktop", "selfhost"}:
        desktop = json.loads((REPO_ROOT / "evidence" / "F122" / "desktop" /
                              "f122-desktop-projection.json").read_text(
                                  encoding="utf-8"))
        selfhost = json.loads((REPO_ROOT / "evidence" / "F122" / "selfhost" /
                               "f122-selfhost-projection.json").read_text(
                                   encoding="utf-8"))
        same = desktop == selfhost
        print("[s7] cross-profile projection diff: %s" %
              ("null (逐键相等)" if same else "DIFF"))
        if not same:
            exit_code |= 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
