# -*- coding: utf-8 -*-
"""F03+F113 双后端同合同对照与案件稳定身份对账（W3-U06）——双 profile。

对账对象：
  harness 分支 w3-u06（基施工链头 w3-u03@f858f9cc＝schema v24 链，本单
  v24→v25）的 --caseanchor-json 封闭径＋既有 E08 双后端切片；
  juscite 分支 w3-u06（基 main=4cb9026）的 legal_entry
  HARNESS_CASE_ANCHOR_METHODS 冻结组（--caseanchor-json 信封）。
desktop profile 与产品桥（legal_entry → 子进程 public_entry）完全同一
条链（SQLite 状态根）；selfhost profile＝PgMatterStore 直连 lh-pg-e08
（resolve_provider_method 同一封闭注册，E16/U05 先例）。

覆盖（06 F03/F113 双实例验收格）：
  F03 SQLite/PG 同合同逐表事务/幂等/版本/租约/CAS 引用/终局对照、真并
  发与迁移——harness E08 双后端切片与 schema v12→v25 迁移 PG 幂等重放
  已在 verify.ps1 -Full 门禁内真跑（W2b 各单反复实证），本对账补：
  ①逐表登记（canonical 表清单＋逐表列名/列型两后端对照）；②中文查询
  统一夹具（同一合成中文案卷种子两后端同查同答：归一 digest 精确／中
  文前缀/尾缀子串 LIKE／散件反查）；③E08 既有切片登记面静态对账（并
  发/迁移/租约/终局/CAS 切片类在盘，实跑证明随 verify -Full 门禁）。
  F113 案件/项目/案号稳定身份、散件可归案、非诉无案号合法——六方法
  全语义双 profile 同集断言（identity_kind 闭集／案号确定性归一解析／
  跨案同号具名拒／改号 revision 留痕／散件互钉幂等/反查）。
  边界如实：全文索引候选评测（FTS5 三方案 vs zhparser/pg_jieba）属
  F67（cases 仓已交付；zhparser/pg_jieba 在 lh-pg-e08 如实
  unavailable）；本对账的中文夹具是 harness 存储层查询语义同合同对照，
  不作全文召回主张。

用法：
  python -X utf8 tools/recon/PENDING_OWNER_f03_f113_dualdb_identity_recon.py
  （juscite worktree 根 cwd，缺省双 profile；--profile 可选单跑）

退出码：0 = 全部 profile RECON_OK；2 = RECON_FAIL；3 = 环境缺失。
证据：docs/construction/evidence/F03/<profile>/ 与
  docs/construction/evidence/F113/<profile>/。
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import subprocess
import sys
import tempfile
import uuid as _uuid
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "python"))
sys.path.insert(0, str(REPO_ROOT / "implementation" / "tests"))

import legal_entry  # noqa: E402
from legal_entry import HarnessCommandError, NotConnected  # noqa: E402

HARNESS_ROOT = Path(
    r"D:\Codex\1.法律工作区\legal-harness工作区\legal-harness-repo"
    r"\.local\worktrees\w3-u06")
JUSCITE_MAIN_PIN = "4cb9026"
HARNESS_CHAIN_PIN = "f858f9cc"
HARNESS_MASTER_PIN = "929d0802"

# lh-pg-e08 容器（E08 拓扑）：仅回环端口、合成专用凭据；--pg-dsn 可覆写。
DEFAULT_PG_DSN = "postgresql://lh_app:e08-synth-only@127.0.0.1:55432/legal_harness"

F113_METHODS = frozenset({
    "harness.case_identity_register", "harness.case_identity_read",
    "harness.case_number_resolve", "harness.case_anchor_attach",
    "harness.case_anchor_list", "harness.case_anchor_item_read",
})

MATTER_A = "m-f03f113-a"
MATTER_B = "m-f03f113-b"
SCOPE_A = {"kind": "matter", "matterId": MATTER_A}
SCOPE_B = {"kind": "matter", "matterId": MATTER_B}

# 合成中文夹具（全合成，seed 语义钉定：同一字符串两 profile 逐字节相同）。
CASE_NUMBER_FULLWIDTH = "（2026）京0105民初 8888号"
CASE_NUMBER_HALFWIDTH = "(2026)京0105民初8888号"
COURT_A = "合成第一人民法院"
COURT_B = "合成商事调解中心"
ANCHOR_TEXT = "合成证据清单（中文）"

E08_SLICE_CLASSES = (
    "CommandTxTests", "ConcurrencyTests", "CasReferenceTests",
    "LeaseTests", "FinalityTests", "OrgIsolationTests",
    "MigrationTests", "F113CaseAnchorSliceTests", "TableRegistrationTests",
    "ChineseQueryFixtureTests",
)


def key(request_id: str) -> dict:
    return {"requestId": request_id, "targetId": None,
            "expectedRevision": None, "inputRefs": []}


def strip_row(row: dict | None) -> dict | None:
    if row is None:
        return None
    return {k: v for k, v in row.items()
            if k not in ("recordHash", "createdAt")}


class Recon:
    def __init__(self, harness_root: Path,
                 projections: dict | None = None):
        self.harness_root = harness_root
        self.checks: list[dict] = []
        # 双 profile 对照用共享投影仓（跨实例存活，main 持有）。
        self.projections: dict = projections if projections is not None else {}

    def step(self, name, ok, **facts):
        entry = {"check": name, "status": "PASS" if ok else "FAIL", **facts}
        self.checks.append(entry)
        print(json.dumps(entry, ensure_ascii=False), flush=True)
        if not ok:
            raise AssertionError(name)

    def expect_error(self, name, call, code_part):
        try:
            call()
        except (HarnessCommandError, NotConnected, ValueError) as exc:
            self.step(name, code_part in str(exc), code=str(exc)[:200])
            return str(exc)
        raise AssertionError(name + ": no typed error raised")

    def git(self, root: Path, *args: str) -> str:
        return subprocess.check_output(
            ["git", "-C", str(root), *args], text=True).strip()

    def branch_checks(self):
        h_branch = self.git(self.harness_root, "rev-parse",
                            "--abbrev-ref", "HEAD")
        h_base = self.git(self.harness_root, "merge-base", "HEAD", "w3-u03")
        h_master = self.git(self.harness_root, "rev-parse", "master")
        self.step("c01_harness_branch", h_branch == "w3-u06", branch=h_branch)
        self.step("c01_harness_base_on_w3_u03",
                  h_base.startswith(HARNESS_CHAIN_PIN), base=h_base[:12])
        self.step("c01_harness_master_untouched",
                  h_master.startswith(HARNESS_MASTER_PIN), master=h_master[:12])
        h_dirty = self.git(self.harness_root, "status", "--porcelain")
        self.step("c01_harness_worktree_clean", h_dirty == "",
                  dirty=h_dirty[:200])
        j_branch = self.git(REPO_ROOT, "rev-parse", "--abbrev-ref", "HEAD")
        j_base = self.git(REPO_ROOT, "merge-base", "HEAD", "main")
        # 账房改口（W3-U06 合并后主仓树复验）：原字面断言 j_branch==w3-u06
        # 只适配 worktree 模式；合并后 main 树被测＝同工单提交已并入。
        # 实质不变量：被测树要么是工单分支本体（基点钉定不漂），
        # 要么是 main 且 merge-base(HEAD, w3-u06)==w3-u06 头（工单提交全含）。
        j_merged_tip = self.git(REPO_ROOT, "merge-base", "HEAD", "w3-u06")
        j_wt = self.git(REPO_ROOT, "rev-parse", "--verify", "w3-u06")
        on_branch = j_branch == "w3-u06" and j_base.startswith(JUSCITE_MAIN_PIN)
        merged_mode = j_branch == "main" and j_merged_tip == j_wt and bool(j_wt)
        self.step("c01_juscite_branch", on_branch or merged_mode,
                  branch=j_branch, merged_tip=j_merged_tip[:12],
                  worktree_tip=j_wt[:12])
        self.step("c01_juscite_base_on_main",
                  (on_branch and j_base.startswith(JUSCITE_MAIN_PIN))
                  or merged_mode, base=j_base[:12])

    # ------------------------------------------------------------------
    # 共同流程：call(method, args)＝被测链（desktop=产品桥子进程全链 /
    # selfhost=同封闭注册直连）；query(sql, params)＝直读本 profile 库。
    # ------------------------------------------------------------------
    def common_flow(self, profile: str, call, query, store):
        import sqlite3

        # ---- C02 F03 逐表登记：canonical 表清单＋逐表列名/列型对照。
        sys.path.insert(0, str(self.harness_root / "src"))
        for _name in [m for m in list(sys.modules)
                      if m == "legal_harness"
                      or m.startswith("legal_harness.")]:
            del sys.modules[_name]
        from legal_harness.state.pg_store import canonical_table_names
        registry = canonical_table_names()
        sys.path.remove(str(self.harness_root / "src"))
        for _name in [m for m in list(sys.modules)
                      if m == "legal_harness"
                      or m.startswith("legal_harness.")]:
            del sys.modules[_name]
        self.step("c02_table_registry_size", len(registry) >= 95
                  and "case_identity" in registry
                  and "case_anchors" in registry,
                  tables=len(registry))
        columns: dict[str, list] = {}
        with contextlib.closing(store._connect()) as connection:
            if profile == "desktop":
                connection.row_factory = sqlite3.Row
                for table in registry:
                    columns[table] = [
                        (r["name"], str(r["type"]).lower())
                        for r in connection.execute(
                            f"PRAGMA table_info({table})").fetchall()]
            else:
                for table in registry:
                    columns[table] = [
                        (r[0], str(r[1]).lower())
                        for r in connection.execute(
                            "SELECT column_name, data_type FROM"
                            " information_schema.columns WHERE table_schema=?"
                            " AND table_name=? ORDER BY ordinal_position",
                            (store.schema, table)).fetchall()]
        empty = [t for t, cols in columns.items() if not cols]
        self.step("c02_tables_registered_no_empty", empty == [], empty=empty)
        # 案件锚点两账列序逐表登记（本单新表面）。
        self.step("c02_case_identity_columns",
                  columns["case_identity"] == [
                      ("matter_id", "text"), ("revision", "integer"),
                      ("identity_kind", "text"), ("case_number", "text"),
                      ("case_number_digest", "text"),
                      ("payload_json", "text"), ("record_hash", "text"),
                      ("current", "integer"), ("created_at", "text")],
                  got=columns["case_identity"])
        self.step("c02_case_anchors_columns",
                  columns["case_anchors"] == [
                      ("matter_id", "text"), ("anchor_id", "text"),
                      ("item_digest", "text"), ("item_ref_json", "text"),
                      ("record_hash", "text"), ("created_at", "text")],
                  got=columns["case_anchors"])
        with contextlib.closing(store._connect()) as connection:
            if profile == "desktop":
                version = connection.execute(
                    "SELECT value FROM metadata WHERE key='schema_version'",
                ).fetchone()[0]
            else:
                version = connection.execute(
                    "SELECT value FROM metadata WHERE key='schema_version'",
                ).fetchone()[0]
        self.step("c02_schema_version_pinned_25", str(version) == "25",
                  version=str(version))

        # ---- C03 案件建账（P04 既有面由驱动方建，见 profile 驱动）。
        read0 = call("harness.case_identity_read", {"scope": SCOPE_A})
        self.step("c03_unregistered_identity_null",
                  read0["identity"] is None and read0["revisionCount"] == 0)

        # ---- C04 非诉无案号合法＋项目无案号合法＋诉前未获号合法。
        non_lit = call("harness.case_identity_register", {
            "actor_id": "recon", "scope": SCOPE_A, "key": key("ci-nl"),
            "identity": {"identityKind": "non_litigation",
                         "caseNumber": None, "court": COURT_B,
                         "note": "非诉无案号合法（合成）"}})
        self.step("c04_non_litigation_no_number_lawful",
                  non_lit["identity"]["caseNumber"] is None
                  and non_lit["identity"]["caseNumberDigest"] is None
                  and non_lit["identity"]["identityKind"] == "non_litigation")
        project = call("harness.case_identity_register", {
            "actor_id": "recon", "scope": SCOPE_A, "key": key("ci-pj"),
            "identity": {"identityKind": "project", "caseNumber": None,
                         "court": None, "note": "常法项目（合成）"}})
        self.step("c04_project_no_number_lawful",
                  project["revision"] == 2
                  and project["identity"]["identityKind"] == "project")
        pre_filing = call("harness.case_identity_register", {
            "actor_id": "recon", "scope": SCOPE_B, "key": key("ci-pre"),
            "identity": {"identityKind": "litigation", "caseNumber": None,
                         "court": COURT_A, "note": "诉前未获号（合成）"}})
        self.step("c04_litigation_prefiling_no_number_lawful",
                  pre_filing["identity"]["caseNumberDigest"] is None)

        # ---- C05 案号稳定身份：全角＋内嵌空白原文入账，digest 钉归一形；
        # 半角无空白变体解析回同一案件。
        litigation = call("harness.case_identity_register", {
            "actor_id": "recon", "scope": SCOPE_B, "key": key("ci-lit"),
            "identity": {"identityKind": "litigation",
                         "caseNumber": CASE_NUMBER_FULLWIDTH,
                         "court": COURT_A, "note": None}})
        identity_digest = litigation["identity"]["caseNumberDigest"]
        expected_digest = hashlib.sha256(
            CASE_NUMBER_HALFWIDTH.encode("utf-8")).hexdigest()
        self.step("c05_digest_pins_normalized_form",
                  identity_digest == expected_digest
                  and litigation["identity"]["caseNumber"]
                  == CASE_NUMBER_FULLWIDTH,
                  digest=identity_digest[:16])
        resolved = call("harness.case_number_resolve",
                        {"case_number": CASE_NUMBER_HALFWIDTH})
        self.step("c05_resolve_halfwidth_variant",
                  resolved["resolved"]
                  and resolved["matterId"] == MATTER_B
                  and resolved["caseNumberDigest"] == identity_digest
                  and resolved["caseNumber"] == CASE_NUMBER_HALFWIDTH)

        # ---- C06 跨案件同号（归一形相同）＝具名拒。
        self.expect_error(
            "c06_cross_matter_same_number_refused",
            lambda: call("harness.case_identity_register", {
                "actor_id": "recon", "scope": SCOPE_A, "key": key("ci-x"),
                "identity": {"identityKind": "litigation",
                             "caseNumber": CASE_NUMBER_HALFWIDTH,
                             "court": None, "note": None}}),
            "case_number_anchor_conflict:" + MATTER_B)

        # ---- C07 改号＝追加 revision 旧行 current=0（旧号不再解析）。
        amended = call("harness.case_identity_register", {
            "actor_id": "recon", "scope": SCOPE_B, "key": key("ci-am"),
            "identity": {"identityKind": "litigation",
                         "caseNumber": "（2026）京0105民初99999号",
                         "court": COURT_A, "note": "补正案号（合成）"}})
        read_b = call("harness.case_identity_read", {"scope": SCOPE_B})
        stale = call("harness.case_number_resolve",
                     {"case_number": CASE_NUMBER_HALFWIDTH})
        # SCOPE_B 此前已有两行（c04 诉前无号 rev1＋c05 全角案号 rev2）。
        self.step("c07_amendment_appends_and_retires",
                  amended["revision"] == 3
                  and read_b["revisionCount"] == 3
                  and read_b["identity"]["caseNumber"]
                  == "（2026）京0105民初99999号"
                  and stale["resolved"] is False)

        # ---- C08 同内容幂等（新 requestId）；同键异内容 conflict。
        replayed = call("harness.case_identity_register", {
            "actor_id": "recon", "scope": SCOPE_B, "key": key("ci-rp"),
            "identity": {"identityKind": "litigation",
                         "caseNumber": "（2026）京0105民初99999号",
                         "court": COURT_A, "note": "补正案号（合成）"}})
        self.step("c08_same_content_idempotent",
                  replayed["replayed"] and replayed["revision"] == 3)
        self.expect_error(
            "c08_same_key_different_content_conflict",
            lambda: call("harness.case_identity_register", {
                "actor_id": "recon", "scope": SCOPE_B,
                "key": key("ci-rp"),
                "identity": {"identityKind": "project", "caseNumber": None,
                             "court": None, "note": None}}),
            "idempotency_conflict")

        # ---- C09 散件可归案：互钉＋幂等＋反向解析；跨案归档是记录事实。
        digest = hashlib.sha256(ANCHOR_TEXT.encode("utf-8")).hexdigest()
        item_ref = {"owner": "host", "kind": "upload", "id": "证据清单-1",
                    "version": "1", "digest": digest}
        attached = call("harness.case_anchor_attach", {
            "actor_id": "recon", "scope": SCOPE_B, "key": key("at-1"),
            "item_ref": dict(item_ref), "item_digest": digest})
        reattached = call("harness.case_anchor_attach", {
            "actor_id": "recon", "scope": SCOPE_B, "key": key("at-2"),
            "item_ref": dict(item_ref), "item_digest": digest})
        self.step("c09_anchor_attach_and_idempotent",
                  attached["anchor"]["itemDigest"] == digest
                  and attached["anchor"]["itemRef"]["id"] == "证据清单-1"
                  and reattached["replayed"] is True)
        listing = call("harness.case_anchor_list", {"scope": SCOPE_B})
        item_view = call("harness.case_anchor_item_read",
                         {"item_digest": digest})
        self.step("c09_anchor_list_and_item_read",
                  listing["anchorCount"] == 1
                  and item_view["anchorCount"] == 1
                  and item_view["anchors"][0]["matterId"] == MATTER_B)
        cross = call("harness.case_anchor_attach", {
            "actor_id": "recon", "scope": SCOPE_A, "key": key("at-3"),
            "item_ref": dict(item_ref), "item_digest": digest})
        item_view2 = call("harness.case_anchor_item_read",
                          {"item_digest": digest})
        self.step("c09_cross_matter_anchor_is_recorded_fact",
                  cross["anchor"]["matterId"] == MATTER_A
                  and item_view2["anchorCount"] == 2)
        self.expect_error(
            "c09_anchor_digest_mismatch_refused",
            lambda: call("harness.case_anchor_attach", {
                "actor_id": "recon", "scope": SCOPE_A, "key": key("at-4"),
                "item_ref": dict(item_ref), "item_digest": "0" * 64}),
            "case_anchor_digest_mismatch")
        self.expect_error(
            "c09_anchor_digest_format_refused",
            lambda: call("harness.case_anchor_attach", {
                "actor_id": "recon", "scope": SCOPE_A, "key": key("at-5"),
                "item_ref": {"owner": "host", "kind": "upload", "id": "x",
                             "version": "1", "digest": "XYZ"},
                "item_digest": "XYZ"}),
            "case_anchor_digest_invalid")

        # ---- C10 输入闭集与 kind 闭集负向。
        self.expect_error(
            "c10_identity_kind_closed_set",
            lambda: call("harness.case_identity_register", {
                "actor_id": "recon", "scope": SCOPE_A, "key": key("ci-k1"),
                "identity": {"identityKind": "arbitration",
                             "caseNumber": None, "court": None,
                             "note": None}}),
            "case_identity_kind_invalid")
        self.expect_error(
            "c10_identity_fields_closed_set",
            lambda: call("harness.case_identity_register", {
                "actor_id": "recon", "scope": SCOPE_A, "key": key("ci-k2"),
                "identity": {"identityKind": "litigation",
                             "caseNumber": None, "court": None,
                             "note": None, "amountMinor": 1}}),
            "fields_not_closed")
        self.expect_error(
            "c10_identity_fields_missing",
            lambda: call("harness.case_identity_register", {
                "actor_id": "recon", "scope": SCOPE_A, "key": key("ci-k3"),
                "identity": {"identityKind": "litigation",
                             "court": None, "note": None}}),
            "fields_missing:['caseNumber']")

        # ---- C11 F03 中文查询统一夹具（两后端同查同答，键级对照在 C13）。
        cn = {
            "exact": query(
                "SELECT matter_id FROM case_identity"
                " WHERE case_number_digest=?", (expected_digest,)),
            # 中文前缀/尾缀 LIKE 只认 current 行（历史 revision 是账本事
            # 实；身份查询与 case_number_resolve 同语义只认现行锚点行）。
            "prefix": query(
                "SELECT matter_id, case_number FROM case_identity"
                " WHERE case_number LIKE ? AND current=1"
                " ORDER BY matter_id",
                ("（2026%",)),
            "suffix": query(
                "SELECT matter_id FROM case_identity"
                " WHERE case_number LIKE ? AND current=1"
                " ORDER BY matter_id",
                ("%民初99999号",)),
            "anchor": query(
                "SELECT matter_id, item_digest FROM case_anchors"
                " WHERE item_digest=? ORDER BY matter_id", (digest,)),
        }
        self.step("c11_chinese_fixture_exact_normalized_digest",
                  cn["exact"] == [{"matter_id": MATTER_B}], got=cn["exact"])
        self.step("c11_chinese_fixture_prefix_like",
                  cn["prefix"] == [{"matter_id": MATTER_B,
                                    "case_number":
                                    "（2026）京0105民初99999号"}],
                  got=cn["prefix"])
        self.step("c11_chinese_fixture_suffix_like",
                  cn["suffix"] == [{"matter_id": MATTER_B}], got=cn["suffix"])
        self.step("c11_chinese_fixture_anchor_reverse",
                  cn["anchor"] == [{"matter_id": MATTER_A,
                                    "item_digest": digest},
                                   {"matter_id": MATTER_B,
                                    "item_digest": digest}])
        return {
            "identity_a": strip_row(call("harness.case_identity_read",
                                         {"scope": SCOPE_A})["identity"]),
            "identity_b": strip_row(call("harness.case_identity_read",
                                         {"scope": SCOPE_B})["identity"]),
            "resolve": {"resolved": resolved["resolved"],
                        "caseNumber": resolved["caseNumber"],
                        "caseNumberDigest": resolved["caseNumberDigest"],
                        "matterId": resolved["matterId"]},
            "anchors_b": [strip_row(a) for a in listing["anchors"]],
            "chinese_fixture": cn,
        }

    def bridge_negatives(self, config):
        try:
            legal_entry.call("harness.case_identity_register",
                             {"scope": SCOPE_A}, {})
            raise AssertionError("bridge_not_configured_expected")
        except NotConnected as exc:
            self.step("c12_bridge_not_configured",
                      "harness_public_entry_not_configured" in str(exc))
        try:
            legal_entry.call("harness.case_identity_delete",
                             {"scope": SCOPE_A},
                             config or {"harness_public_entry": "x",
                                        "harness_target": "opencode"})
            raise AssertionError("bridge_unknown_method_expected")
        except NotConnected as exc:
            self.step("c12_bridge_unknown_method_refused",
                      "method_not_connected" in str(exc))
        self.step("c12_method_group_frozen",
                  legal_entry.HARNESS_CASE_ANCHOR_METHODS == F113_METHODS)

    def e08_slice_registration(self):
        # F03 事务/幂等/版本/租约/CAS/终局/并发/迁移＝E08 既有切片；实跑
        # 证明随 verify.ps1 -Full 门禁（本单收口复跑），此处登记切片在盘
        # 且挂 verify 清单。
        e08_path = (self.harness_root / "tests" / "test_e08_dual_backend.py"
                    ).read_text(encoding="utf-8")
        missing = [c for c in E08_SLICE_CLASSES
                   if f"class {c}" not in e08_path]
        self.step("c13_e08_slice_classes_registered", missing == [],
                  missing=missing)
        verify_ps1 = (self.harness_root / "verify.ps1").read_text(
            encoding="utf-8")
        self.step("c13_e08_and_f113_mounted_on_verify_gate",
                  "tests.test_e08_dual_backend" in verify_ps1
                  and "tests.test_f113_case_anchor" in verify_ps1)

    # -- profile drivers ---------------------------------------------------

    def run_desktop(self) -> int:
        temporary = tempfile.TemporaryDirectory(prefix="juscite-f03f113-d-")
        state_root = Path(temporary.name) / "state"
        state_root.mkdir(parents=True)
        registration = Path(temporary.name) / "service-local.json"
        registration.write_text(json.dumps(
            {"url": "http://127.0.0.1:1", "password": "synthetic-recon"}),
            encoding="utf-8")
        config = {
            "harness_public_entry":
                str(self.harness_root
                    / "tools/workflow-tools/harness/public_entry.py"),
            "harness_target": "opencode",
            "harness_state_root": str(state_root),
            "harness_service_registration": str(registration),
            "harness_timeout": 120,
        }
        sys.path.insert(0, str(self.harness_root / "src"))
        for _name in [m for m in list(sys.modules)
                      if m == "legal_harness"
                      or m.startswith("legal_harness.")]:
            del sys.modules[_name]
        from legal_harness.business.units import HarnessUnits
        from legal_harness.state.matter_store import MatterStore
        store = MatterStore(state_root)
        units = HarnessUnits(store)
        units.create_matter("recon", SCOPE_A, key("mk-a"),
                            {"owner": "harness", "kind": "profile",
                             "id": "prof-f03f113", "version": "1"},
                            {"owner": "host", "kind": "intake",
                             "id": "in-a", "version": "1"})
        units.create_matter("recon", SCOPE_B, key("mk-b"),
                            {"owner": "harness", "kind": "profile",
                             "id": "prof-f03f113", "version": "1"},
                            {"owner": "host", "kind": "intake",
                             "id": "in-b", "version": "1"})
        for _name in [m for m in list(sys.modules)
                      if m == "legal_harness"
                      or m.startswith("legal_harness.")]:
            del sys.modules[_name]
        sys.path.remove(str(self.harness_root / "src"))

        def call(method, args):
            return legal_entry.call(method, args, config)

        def query(sql, params):
            import sqlite3
            with contextlib.closing(store._connect()) as connection:
                connection.row_factory = sqlite3.Row
                return [dict(r) for r in
                        connection.execute(sql, params).fetchall()]

        print("[profile desktop] SQLite via product bridge subprocess",
              flush=True)
        projection = self.common_flow("desktop", call, query, store)
        self.bridge_negatives(config)
        self.e08_slice_registration()
        self.projections["desktop"] = projection
        return 0

    def run_selfhost(self, dsn: str) -> int:
        sys.path.insert(0, str(self.harness_root / "src"))
        sys.path.insert(0, str(self.harness_root / "tools/workflow-tools"))
        for _name in [m for m in list(sys.modules)
                      if m == "legal_harness"
                      or m.startswith("legal_harness.")]:
            del sys.modules[_name]
        from legal_harness.business.provider_registry import (
            resolve_provider_method,
        )
        from legal_harness.business.units import HarnessUnits
        from legal_harness.state.pg_store import PgMatterStore

        temporary = tempfile.TemporaryDirectory(
            prefix="juscite-f03f113-sh-")
        store = PgMatterStore(
            Path(temporary.name) / "state", dsn=dsn,
            schema="f03f113_" + _uuid.uuid4().hex[:12])
        units = HarnessUnits(store)
        bound = {name: resolve_provider_method(name, units)
                 for name in F113_METHODS}
        units.create_matter("recon", SCOPE_A, key("mk-a"),
                            {"owner": "harness", "kind": "profile",
                             "id": "prof-f03f113", "version": "1"},
                            {"owner": "host", "kind": "intake",
                             "id": "in-a", "version": "1"})
        units.create_matter("recon", SCOPE_B, key("mk-b"),
                            {"owner": "harness", "kind": "profile",
                             "id": "prof-f03f113", "version": "1"},
                            {"owner": "host", "kind": "intake",
                             "id": "in-b", "version": "1"})

        def call(method, args):
            return bound[method](**args)

        def query(sql, params):
            with contextlib.closing(store._connect()) as connection:
                cursor = connection.execute(sql, params)
                columns = [c[0] for c in cursor.description]
                return [dict(zip(columns, row))
                        for row in cursor.fetchall()]

        try:
            print("[profile selfhost] PgMatterStore direct (lh-pg-e08)",
                  flush=True)
            projection = self.common_flow("selfhost", call, query, store)
            self.bridge_negatives(None)
            self.e08_slice_registration()
            self.projections["selfhost"] = projection
        finally:
            store.destroy()
            sys.path.remove(str(self.harness_root / "src"))
            sys.path.remove(str(self.harness_root / "tools/workflow-tools"))
        return 0

    def cross_profile_comparison(self):
        # C14：两 profile 投影逐键相等（时间戳/recordHash 已剥——先例）。
        # 仅在双 profile 全部跑完后由 main 调用一次。
        desktop = self.projections.get("desktop")
        selfhost = self.projections.get("selfhost")
        if desktop is None or selfhost is None:
            self.step("c14_cross_profile_projection_equal", False,
                      note="缺少 profile 投影",
                      have=sorted(self.projections))
            return
        self.step("c14_cross_profile_projection_equal",
                  desktop == selfhost,
                  diff=_first_diff(desktop, selfhost))


def _first_diff(a, b, path="$"):
    if type(a) is not type(b):
        return f"{path}: type {type(a).__name__} vs {type(b).__name__}"
    if isinstance(a, dict):
        for key in sorted(set(a) | set(b)):
            if key not in a:
                return f"{path}.{key}: missing in desktop"
            if key not in b:
                return f"{path}.{key}: missing in selfhost"
            sub = _first_diff(a[key], b[key], f"{path}.{key}")
            if sub:
                return sub
        return None
    if isinstance(a, list):
        if len(a) != len(b):
            return f"{path}: len {len(a)} vs {len(b)}"
        for index, (x, y) in enumerate(zip(a, b)):
            sub = _first_diff(x, y, f"{path}[{index}]")
            if sub:
                return sub
        return None
    return None if a == b else f"{path}: {a!r} vs {b!r}"


def write_evidence(feature: str, profile: str, recon: Recon, started: str,
                   code: int) -> Path:
    evidence_dir = (REPO_ROOT / "docs" / "construction" / "evidence"
                    / feature / profile)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    finished = datetime.now(timezone.utc).isoformat()
    summary = {
        "schema": "juscite-f03-f113-dualdb-identity-recon/1",
        "unit": "W3-U06",
        "feature": feature,
        "profile": profile,
        "verdict": "RECON_OK" if code == 0 else "RECON_FAIL",
        "started_at": started,
        "finished_at": finished,
        "harness_worktree": str(recon.harness_root),
        "harness_branch": "w3-u06",
        "harness_base": ("w3-u03@" + HARNESS_CHAIN_PIN
                         + "（施工链头＝…→W2b-U53@a2d99869 同链接力；"
                           "master " + HARNESS_MASTER_PIN + " 零动）"),
        "checks": recon.checks,
        "check_count": len(recon.checks),
        "failed": [c["check"] for c in recon.checks
                   if c["status"] != "PASS"],
    }
    stem = ("f03_dualdb_recon" if feature == "F03"
            else "f113_case_anchor_recon")
    (evidence_dir / f"{stem}.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8")
    lines = [f"# {feature} recon（{profile}）——W3-U06", "",
             f"- unit: W3-U06 · profile: {profile}",
             f"- verdict: **{summary['verdict']}**"
             f" ({len(recon.checks)} checks, exit {code})",
             f"- harness: `{recon.harness_root}` @ branch w3-u06"
             f"（基 w3-u03@{HARNESS_CHAIN_PIN}；master {HARNESS_MASTER_PIN}"
             " 零动）",
             f"- started: {started} · finished: {finished}",
             "",
             "| # | check | status |", "|---|---|---|"]
    for index, check in enumerate(recon.checks, 1):
        lines.append(f"| {index} | {check['check']} | {check['status']} |")
    lines += ["", "全部合成材料；desktop＝产品桥子进程全链（SQLite 状态根），"
              "selfhost＝PgMatterStore 直连 lh-pg-e08（同一封闭注册）。"
              + ("F03 逐表登记＋中文查询统一夹具＋E08 切片登记面（真并发/"
                 "迁移实跑随 verify.ps1 -Full 门禁）；"
                 if feature == "F03" else
                 "F113 案件/项目/案号稳定身份（确定性归一解析/跨案同号拒/"
                 "改号留痕）＋散件可归案（互钉/幂等/反查）＋非诉无案号合法；")
              + "全文索引候选评测属 F67（zhparser/pg_jieba 本机如实 "
              "unavailable），不作全文召回主张。"]
    (evidence_dir / f"{stem}.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8")
    return evidence_dir


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", action="append",
                        choices=["desktop", "selfhost"])
    parser.add_argument("--harness-root", type=Path, default=HARNESS_ROOT)
    parser.add_argument("--pg-dsn", default=DEFAULT_PG_DSN)
    args = parser.parse_args()
    profiles = args.profile or ["desktop", "selfhost"]
    if not (args.harness_root
            / "tools/workflow-tools/harness/public_entry.py").exists():
        print("RECON_BLOCKED: harness root missing public_entry:",
              args.harness_root)
        return 3
    failures = 0
    projections: dict = {}
    runs: list = []
    for index, profile in enumerate(profiles):
        started = datetime.now(timezone.utc).isoformat()
        recon = Recon(args.harness_root, projections)
        code = 0
        try:
            if index == 0:
                recon.branch_checks()
            if profile == "desktop":
                recon.run_desktop()
            else:
                recon.run_selfhost(args.pg_dsn)
        except Exception as error:  # noqa: BLE001 - reported per profile
            print(f"RECON_FAIL[{profile}]: {error}", flush=True)
            recon.checks.append({"check": "recon_driver", "status": "FAIL",
                                 "error": str(error)[:400]})
            code = 2
        runs.append((profile, recon, started, code))

    # C14 双 profile 投影对照：全部跑完后执行一次，结论同时并入两份
    # 证据（任何 profile 中途失败即不对照——如实 FAIL 记账）。
    if len(profiles) == 2:
        comparison = Recon(args.harness_root, projections)
        try:
            comparison.cross_profile_comparison()
        except Exception as error:  # noqa: BLE001 - reported per profile
            comparison.checks.append({"check": "c14_driver",
                                      "status": "FAIL",
                                      "error": str(error)[:400]})
        c14_failed = any(c["status"] != "PASS"
                         for c in comparison.checks)
        for profile, recon, _started, code in runs:
            recon.checks.extend(comparison.checks)
            if c14_failed and code == 0:
                runs[runs.index((profile, recon, _started, code))] = (
                    profile, recon, _started, 2)

    for profile, recon, started, code in runs:
        for feature in ("F03", "F113"):
            evidence_dir = write_evidence(feature, profile, recon, started,
                                          code)
        verdict = "RECON_OK" if code == 0 else "RECON_FAIL"
        print(f"[{profile}] {verdict} ({len(recon.checks)} checks,"
              f" exit {code}) evidence={evidence_dir}", flush=True)
        if code != 0:
            failures += 1
    return 0 if failures == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
