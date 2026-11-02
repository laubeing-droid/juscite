"""F141 评论/分享协作＋F142 文档生命周期治理（审批流）对账——双 profile。

对账对象：harness 分支 w5-u13（基战役链头 w5-u06@98a562fd＝A2 分支链常
驻；master 929d0802 零动）的公开面——desktop profile 走产品桥（legal_entry
HARNESS_COLLABDOC_METHODS → 子进程 public_entry --collabdoc-json、
HARNESS_APPROVAL_METHODS → --approval-json、HARNESS_FORMAL_LIFECYCLE_
METHODS → 既有 --prepare-formal-json/--commit-formal-json P02 信封；
SQLite 状态根）；selfhost profile＝PgMatterStore 直连 lh-pg-e08
（resolve_provider_method 同一封闭注册）。合同 harness
docs/f141-f142-collab-lifecycle-contract.md；schema v37 三账
（collab_doc_comments / formal_approval_rounds / formal_approval_pages，
同 owner 同库扩不新库）。

acceptance（台账 F141/F142-desktop/selfhost assertion 逐字）：
- F141「评论/分享按对象权限及版本，撤销立失效，不越权原件」：
  C1x 块＝评论写路径作者实时过 F04 read 门（逐操作同事务求值＝撤权即
  时生效，F04/F92 已 VERIFIED 先例）；评论显式钉 F08 材料链真实
  revision（无『最新版』自动跟随）；被分享者读路径＝F05 分享 token 承
  载且 (materialId, revision) 逐字绑定——越权对象/越权版本具名拒（红线
  负测）；投影键闭集无原件字节字段（红线负测：原件标记串不出现在任何
  投影字节）；撤销（manual）与成员撤权级联（member_revoked）两因解析
  第一步具名拒（红线负测：撤销后立即失效）。P04 save_case_note/
  start_review_round 既有 v1 语义零改动复用（C11 引用形态逐键断言）。
- F142「正式文档生命周期/审批采用后实记；v1已有文件终局不得等v2」：
  C2x 块＝审批轮锚定 preparation 清单（run/type/sha，sha 必须真实在
  CAS）；决定唯一入账通道＝显式 decide（manage 门实时求值；免登录审批
  页只读不扩权——浏览零记账＝采用后实记的负测：view 前后决定面字段恒
  空）；重开＝追加下一轮（open 轮未决不得重开）；页 token 只存 sha256
  （原始串不在状态根 DB 文件字节）、permitted_scope 闭集单值
  approval_view、撤销立失效。preserved＝C27/C4x：commit_formal 终局面
  零改动回归断言（审批账有行与无行时既有类型面同码＋finalization.py 源
  零引用审批标识＋schema 零触发器）；desktop C40 段＝真实 P02 管线
  （RuntimeFixture 合成 run → prepare_formal 经桥 → 审批锚定真实
  preparation → decide 采用后实记 → commit_formal 经桥终局 PASS）——
  审批 documentSha256 与终局交付 output_sha256 逐字相等＝审批锚定确切
  字节，且终局不等审批（管线行为回归同时由 harness verify 清单
  finalization/main-chain 既有测试承载）。

selfhost 与 desktop 的共同流逐检对齐（同一段代码跑两条腿）；真实 P02
RuntimeFixture 管线段仅 desktop（RuntimeFixture 不持 PG——E08 双后端
由 harness verify 清单承载，本对账 selfhost 腿如实不含该段，不冒充）。

全部合成材料：临时状态根、合成 org/email/user/文档字节/合成 preparation
清单；harness 检出零字节改动（只运行其代码，git 只读命令核对分支）；
%APPDATA% 零触碰；金额不入场；确定性解析零模型；不 push。

用法：
  python -X utf8 tools/recon/PENDING_OWNER_f141_f142_collab_lifecycle_recon.py \
      --profile desktop --profile selfhost

退出码：0 = 全部 profile RECON_OK；2 = RECON_FAIL；3 = 环境缺失。
证据：evidence/F141/<profile>/＋evidence/F142/<profile>/＋
docs/construction/evidence/F141|F142/<profile>/ 镜像（JSON＋MD）。
"""
from __future__ import annotations

import argparse
import base64
import contextlib
import hashlib
import json
import sqlite3
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

DEFAULT_HARNESS_ROOT = Path(
    r"D:\Codex\1.法律工作区\legal-harness工作区\legal-harness-repo"
    r"\.local\worktrees\w5-u13")

MATTER = "m-f141f142-recon"
SCOPE = {"kind": "matter", "matterId": MATTER}
DOC_MARKER = "F141-SYNTH-ORIGINAL-BYTES-不外泄"
ADMIN = "recon-admin"
MEMBER = "recon-member"
GRANTEE = "recon-grantee"
REVIEWER = "recon-reviewer"
ORG = "org-recon-f141"
ALL_ACTIONS = ("read", "write", "events", "export", "manage")

COLLABDOC_METHODS = frozenset({
    "harness.start_review_round", "harness.save_case_note",
    "harness.collab_doc_comment_save", "harness.collab_doc_comment_read",
    "harness.collab_doc_comment_shared_read",
})
APPROVAL_METHODS = frozenset({
    "harness.formal_approval_open", "harness.formal_approval_page_issue",
    "harness.formal_approval_page_view", "harness.formal_approval_decide",
    "harness.formal_approval_page_revoke", "harness.formal_approval_read",
    "harness.formal_approval_list",
})
FORMAL_LIFECYCLE_METHODS = frozenset({
    "harness.prepare_formal", "harness.commit_formal",
})
# 对账自用 bootstrapping（F04/F05/F08 既有 VERIFIED 面，本单零改动消费）。
BOOT_METHODS = frozenset({
    "harness.case_member_declare", "harness.case_permission_rule",
    "harness.register_material", "harness.add_material_revision",
    "harness.collab_invite_create", "harness.collab_invite_accept",
    "harness.collab_grant_direct", "harness.collab_member_revoke",
    "harness.collab_share_token_issue", "harness.collab_share_token_revoke",
})

# lh-pg-e08 容器（E08 拓扑）：仅回环端口、合成专用凭据（可用 --pg-dsn 覆写）。
DEFAULT_PG_DSN = "postgresql://lh_app:e08-synth-only@127.0.0.1:55432/legal_harness"
# P02 隐私闸：prepare/commit 必须携带同一份非空禁值清单（synth 值）。
LIVE_FORBIDDEN = ["f142-synth-forbidden-当事人甲"]

_KEY_SEQ = {"n": 0}


def key(request_id: str) -> dict:
    """CommandKey：requestId 自动追加流水号（同键重放会回缓存原回执，
    探针必须每次新 id 才测到真实求值）。"""
    _KEY_SEQ["n"] += 1
    return {"requestId": "%s-%d" % (request_id, _KEY_SEQ["n"]),
            "targetId": None, "expectedRevision": None, "inputRefs": []}


def rule(kind: str, principal: str, action: str, effect: str) -> dict:
    return {"principalKind": kind, "principalId": principal,
            "action": action, "effect": effect}


def expect_bridge_error(call, code_part):
    try:
        call()
    except Exception as exc:  # noqa: BLE001 - typed-code probe
        return code_part in str(exc), str(exc)
    return False, "no typed error raised"


class Recon:
    def __init__(self, harness_root: Path):
        self.harness_root = harness_root
        self.checks: list[dict] = []
        self.live_pipeline: dict | None = None

    def step(self, name, ok, **facts):
        entry = {"check": name, "status": "PASS" if ok else "FAIL", **facts}
        self.checks.append(entry)
        print(json.dumps(entry, ensure_ascii=False), flush=True)
        if not ok:
            raise AssertionError(name)

    def expect_error(self, name, call_, code_part):
        ok, code = expect_bridge_error(call_, code_part)
        self.step(name, ok, code=code[:180])
        return code

    def git(self, root: Path, *args: str) -> str:
        return subprocess.check_output(
            ["git", "-C", str(root), *args], text=True).strip()

    def branch_checks(self):
        branch = self.git(self.harness_root, "rev-parse", "--abbrev-ref",
                          "HEAD")
        base = self.git(self.harness_root, "merge-base", "HEAD", "w5-u06")
        master = self.git(self.harness_root, "rev-parse", "master")
        self.step("c01_harness_branch", branch == "w5-u13", branch=branch)
        self.step("c01_harness_base_on_w5_u06_chain_head",
                  base.startswith("98a562fd"), base=base)
        self.step("c01_harness_master_untouched_A2",
                  master.startswith("929d0802"), master=master)
        dirty = self.git(self.harness_root, "status", "--porcelain")
        self.step("c01_harness_worktree_clean", dirty == "", dirty=dirty[:200])

    # ------------------------------------------------------------------
    # C0x–C4x：call(method, args) 走被测链；query/exec 直读同一库。
    # ------------------------------------------------------------------
    def common_flow(self, profile: str, call, query, execute,
                    db_file: Path | None):
        # ---- C00 schema v37：三账在库＋同库不新库（F05/F114/P04 既有账
        # 同一 schema 共存）＋零触发器（preserved 结构半边）。
        if db_file is not None:
            with self.store.transaction() as connection:
                tables = {row[0] for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'")}
                triggers = connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='trigger'"
                ).fetchall()
            triggers = [row[0] for row in triggers]
        else:
            with self.store.transaction() as connection:
                tables = {row[0] for row in connection.execute(
                    "SELECT table_name FROM information_schema.tables"
                    " WHERE table_schema=?", (self._pg_schema,))}
                triggers = connection.execute(
                    "SELECT trigger_name FROM information_schema.triggers"
                    " WHERE trigger_schema=?", (self._pg_schema,)).fetchall()
            triggers = [row[0] for row in triggers]
        self.step("c00_schema_v37_three_ledgers",
                  {"collab_doc_comments", "formal_approval_rounds",
                   "formal_approval_pages"} <= tables,
                  tables=sorted(t for t in tables
                                if t.startswith(("collab_doc", "formal_"))))
        self.step("c00_same_owner_no_new_db",
                  {"collab_share_tokens", "case_notes", "review_rounds",
                   "material_candidates"} <= tables,
                  sharedSchema="matter-store")
        self.step("c00_zero_triggers_preserved", triggers == [],
                  triggerCount=len(triggers))

        # ---- C10 F04 武装窗（bootstrap）＋F05 名册＋F08 材料链两版。
        call("harness.case_member_declare", {
            "actor_id": ADMIN, "scope": SCOPE, "key": key("mb-boot"),
            "members": [{"userId": ADMIN, "orgId": ORG,
                         "roles": ["case-admin"]}]})
        call("harness.case_permission_rule", {
            "actor_id": ADMIN, "scope": SCOPE, "key": key("rl-boot"),
            "rules": [rule("user", ADMIN, action, "allow")
                      for action in ALL_ACTIONS]
            + [rule("role", "paralegal", "read", "allow")]})
        call("harness.collab_grant_direct", {
            "actor_id": ADMIN, "key": key("gd-member"),
            "grant": {"orgId": ORG, "userId": MEMBER,
                      "email": "member@synth.example",
                      "roles": ["paralegal"]}})
        call("harness.collab_grant_direct", {
            "actor_id": ADMIN, "key": key("gd-grantee"),
            "grant": {"orgId": ORG, "userId": GRANTEE,
                      "email": "grantee@synth.example",
                      "roles": ["paralegal"]}})
        self.step("c10_bootstrap_armed", True,
                  admin=ADMIN, roster=sorted({MEMBER, GRANTEE}))
        doc_v1 = ("原件合成材料 v1：%s" % DOC_MARKER).encode("utf-8")
        call("harness.register_material", {
            "actor_id": ADMIN, "scope": SCOPE, "key": key("mat-1"),
            "material": {"id": "doc-main", "kind": "digital_text",
                         "title": "合成协作文档（F141 对账）",
                         "bytesB64": base64.b64encode(doc_v1).decode("ascii"),
                         "matterId": MATTER}})
        doc_v2 = ("原件合成材料 v2：%s" % DOC_MARKER).encode("utf-8")
        call("harness.add_material_revision", {
            "actor_id": ADMIN, "scope": SCOPE, "key": key("mat-2"),
            "revision": {"materialId": "doc-main",
                         "bytesB64": base64.b64encode(doc_v2).decode("ascii")}})
        self.step("c10_material_chain_two_revisions", True,
                  material="doc-main", revisions=[1, 2])

        # ---- C11 P04 既有面零改动复用（17 卡 STATIC_REUSE）。
        round1 = call("harness.start_review_round", {
            "actor_id": ADMIN, "scope": SCOPE, "key": key("rr-1"),
            "material_refs": [{"owner": "harness", "kind": "material",
                               "id": "doc-main", "version": "1"}],
            "purpose": "核对批注"})
        self.step("c11_start_review_round_reuse_zero_change",
                  round1["ref"]["kind"] == "review-round"
                  and round1["ref"]["matterId"] == MATTER
                  and round1["revision"] == 1,
                  roundId=round1["ref"]["id"])
        note1 = call("harness.save_case_note", {
            "actor_id": ADMIN, "scope": SCOPE, "key": key("sn-1"),
            "review_round_ref": {"id": round1["ref"]["id"]},
            "note_ref": {"owner": "harness", "kind": "case-note",
                         "id": "note-recon-1"},
            "source_locations": []})
        self.step("c11_save_case_note_reuse_zero_change",
                  note1["ref"]["kind"] == "case-note"
                  and note1["ref"]["matterId"] == MATTER,
                  noteId=note1["ref"]["id"])

        # ---- C12 评论写路径：钉真实 revision＋行级钉定＋冲突/缺版具名拒。
        saved = call("harness.collab_doc_comment_save", {
            "actor_id": ADMIN, "scope": SCOPE, "key": key("cs-1"),
            "comment": {"commentId": "cm-recon-1", "materialId": "doc-main",
                        "revision": 1, "body": "第一段金额请与对账单核对"}})
        self.step("c12_comment_saved_pinned_revision",
                  saved["materialRevision"] == 1
                  and saved["authorUserId"] == ADMIN,
                  commentId=saved["commentId"])
        row = query("SELECT body_sha256, material_revision, state"
                    " FROM collab_doc_comments WHERE comment_id='cm-recon-1'",
                    ())
        self.step("c12_comment_row_pinned_sha",
                  row[0]["body_sha256"] == hashlib.sha256(
                      "第一段金额请与对账单核对".encode("utf-8")).hexdigest()
                  and int(row[0]["material_revision"]) == 1
                  and row[0]["state"] == "active")
        self.expect_error(
            "c12_comment_id_conflict",
            lambda: call("harness.collab_doc_comment_save", {
                "actor_id": ADMIN, "scope": SCOPE, "key": key("cs-2"),
                "comment": {"commentId": "cm-recon-1",
                            "materialId": "doc-main", "revision": 1,
                            "body": "另一条内容"}}),
            "f141_comment_conflict:cm-recon-1")
        self.expect_error(
            "c12_revision_must_exist_no_latest_follow",
            lambda: call("harness.collab_doc_comment_save", {
                "actor_id": ADMIN, "scope": SCOPE, "key": key("cs-3"),
                "comment": {"commentId": "cm-recon-2",
                            "materialId": "doc-main", "revision": 9,
                            "body": "x"}}),
            "f141_material_revision_not_found:doc-main:9")

        # ---- C13 成员写/读路径（roster 回落 read 门实时求值）。
        saved_member = call("harness.collab_doc_comment_save", {
            "actor_id": MEMBER, "scope": SCOPE, "key": key("cs-4"),
            "comment": {"commentId": "cm-recon-3", "materialId": "doc-main",
                        "revision": 1, "body": "成员批注：日期建议改期"}})
        self.step("c13_member_comment_via_live_read_gate",
                  saved_member["authorUserId"] == MEMBER)
        read = call("harness.collab_doc_comment_read", {
            "actor_id": MEMBER, "scope": SCOPE,
            "material_id": "doc-main", "revision": 1})
        self.step("c13_member_read_projection",
                  read["total"] == 2
                  and {c["commentId"] for c in read["comments"]}
                  == {"cm-recon-1", "cm-recon-3"},
                  total=read["total"])
        # 局外人＝membership 拒（F04 既有语义零漂移）。
        self.expect_error(
            "c13_outsider_membership_denied",
            lambda: call("harness.collab_doc_comment_read", {
                "actor_id": "recon-ghost", "scope": SCOPE,
                "material_id": "doc-main", "revision": 1}),
            "case_permission_denied:read:membership")

        # ---- C14 被分享者读路径：对象权限及版本（acceptance 主断言）。
        issued = call("harness.collab_share_token_issue", {
            "actor_id": ADMIN, "scope": SCOPE, "key": key("tok-1"),
            "token": {"tokenId": "tok-recon-141", "materialId": "doc-main",
                      "action": "read", "granteeUserId": GRANTEE,
                      "materialRevision": 1}})
        share_token = issued["shareToken"]
        self.step("c14_token_issued_bound_revision",
                  share_token.startswith("lhshk-")
                  and issued["materialRevision"] == 1,
                  tokenId=issued["tokenId"])
        shared = call("harness.collab_doc_comment_shared_read", {
            "token": share_token, "material_id": "doc-main", "revision": 1})
        projection = json.dumps(shared, ensure_ascii=False)
        self.step("c14_shared_read_granted_pinned_view",
                  shared["access"] == "granted"
                  and shared["scope"] == "shared_comment_view"
                  and shared["materialRevision"] == 1
                  and shared["total"] == 2,
                  comments=shared["total"])
        # 红线负测：投影键闭集＋原件标记串不在任何投影字节（不越权原件）。
        self.step("c14_no_original_bytes_in_projection",
                  "content" not in shared and "bytes" not in shared
                  and DOC_MARKER not in projection,
                  keys=sorted(shared))

        # ---- C15 越权负测（具名拒）：越权版本/越权对象/未知 token。
        self.expect_error(
            "c15_overreach_version_named_refused",
            lambda: call("harness.collab_doc_comment_shared_read", {
                "token": share_token, "material_id": "doc-main",
                "revision": 2}),
            "f141_share_revision_not_granted:2:1")
        self.expect_error(
            "c15_overreach_object_named_refused",
            lambda: call("harness.collab_doc_comment_shared_read", {
                "token": share_token, "material_id": "doc-other",
                "revision": 1}),
            "f141_share_object_mismatch:doc-other")
        self.expect_error(
            "c15_unknown_token_named_refused",
            lambda: call("harness.collab_doc_comment_shared_read", {
                "token": "lhshk-not-a-real-token",
                "material_id": "doc-main", "revision": 1}),
            "f05_share_token_unknown")

        # ---- C16 撤销立失效（红线负测）：manual 与 member_revoked 两因。
        call("harness.collab_share_token_revoke", {
            "actor_id": ADMIN, "key": key("tr-1"),
            "revoke": {"tokenId": "tok-recon-141"}})
        self.expect_error(
            "c16_manual_revoke_immediate_named_refused",
            lambda: call("harness.collab_doc_comment_shared_read", {
                "token": share_token, "material_id": "doc-main",
                "revision": 1}),
            "f05_share_token_revoked:manual")
        issued2 = call("harness.collab_share_token_issue", {
            "actor_id": ADMIN, "scope": SCOPE, "key": key("tok-2"),
            "token": {"tokenId": "tok-recon-141b", "materialId": "doc-main",
                      "action": "read", "granteeUserId": GRANTEE,
                      "materialRevision": 1}})
        revoked = call("harness.collab_member_revoke", {
            "actor_id": ADMIN, "key": key("mr-grantee"),
            "revoke": {"orgId": ORG, "userId": GRANTEE}})
        self.step("c16_member_revoke_cascades_token",
                  "tok-recon-141b" in revoked["revokedTokenIds"],
                  revokedTokens=revoked["revokedTokenIds"])
        self.expect_error(
            "c16_cascade_revoke_immediate_named_refused",
            lambda: call("harness.collab_doc_comment_shared_read", {
                "token": issued2["shareToken"], "material_id": "doc-main",
                "revision": 1}),
            "f05_share_token_revoked:member_revoked")

        # ---- C20 F142 审批锚定：清单三元组＋CAS 在位负测。
        sha_a = self.write_preparation(call, query, "run-synth-a",
                                       "complaint")
        self.expect_error(
            "c20_preparation_missing_named_refused",
            lambda: call("harness.formal_approval_open", {
                "actor_id": ADMIN, "scope": SCOPE, "key": key("ao-0"),
                "request": {"approvalId": "appr-ghost",
                            "runId": "run-ghost"}}),
            "f142_preparation_not_found:run-ghost")
        opened = call("harness.formal_approval_open", {
            "actor_id": ADMIN, "scope": SCOPE, "key": key("ao-1"),
            "request": {"approvalId": "appr-recon-1",
                        "runId": "run-synth-a"}})
        self.step("c20_approval_open_binds_preparation",
                  opened["state"] == "open" and opened["roundSeq"] == 1
                  and opened["documentSha256"] == sha_a
                  and opened["documentType"] == "complaint",
                  approvalId=opened["approvalId"])
        self.expect_error(
            "c20_open_round_no_second_open",
            lambda: call("harness.formal_approval_open", {
                "actor_id": ADMIN, "scope": SCOPE, "key": key("ao-2"),
                "request": {"approvalId": "appr-recon-1",
                            "runId": "run-synth-a"}}),
            "f142_approval_already_open:appr-recon-1:1")

        # ---- C21 免登录审批页：token 只存 sha256；同 pageId 冲突。
        page = call("harness.formal_approval_page_issue", {
            "actor_id": ADMIN, "scope": SCOPE, "key": key("pg-1"),
            "page": {"pageId": "page-recon-1",
                     "approvalId": "appr-recon-1"}})
        page_token = page["pageToken"]
        row = query("SELECT page_token_hash, permitted_scope, state"
                    " FROM formal_approval_pages WHERE page_id='page-recon-1'",
                    ())
        self.step("c21_page_token_sha256_at_rest",
                  page_token.startswith("lhapg-")
                  and row[0]["page_token_hash"] == hashlib.sha256(
                      page_token.encode("utf-8")).hexdigest()
                  and row[0]["permitted_scope"] == "approval_view"
                  and row[0]["state"] == "active",
                  scope=row[0]["permitted_scope"])
        if db_file is not None:
            raw = db_file.read_bytes()
            self.step("c21_page_raw_token_absent_in_db_file",
                      page_token.encode("utf-8") not in raw,
                      scanned=str(db_file.name))
        self.expect_error(
            "c21_page_id_conflict",
            lambda: call("harness.formal_approval_page_issue", {
                "actor_id": ADMIN, "scope": SCOPE, "key": key("pg-2"),
                "page": {"pageId": "page-recon-1",
                         "approvalId": "appr-recon-1"}}),
            "f142_page_id_conflict:page-recon-1")

        # ---- C22 免登录浏览：限定范围只读；浏览零记账（采用后实记）。
        view1 = call("harness.formal_approval_page_view",
                     {"token": page_token})
        self.step("c22_page_view_limited_readonly",
                  view1["access"] == "granted"
                  and view1["permittedScope"] == "approval_view"
                  and view1["approval"] == {"state": "open"}
                  and view1["documentSha256"] == sha_a
                  and "no_document_bytes" in view1["boundary"],
                  keys=sorted(view1))
        self.step("c22_view_projection_no_bytes",
                  "bytes" not in view1 and "content" not in view1
                  and DOC_MARKER not in json.dumps(view1,
                                                   ensure_ascii=False))
        call("harness.formal_approval_page_view", {"token": page_token})
        row = query("SELECT decision_json, decided_by, decided_at"
                    " FROM formal_approval_rounds"
                    " WHERE approval_id='appr-recon-1' AND round_seq=1", ())
        self.step("c22_view_records_zero_decisions",
                  row[0]["decision_json"] is None
                  and row[0]["decided_by"] is None
                  and row[0]["decided_at"] is None,
                  recorded="nothing")

        # ---- C23 决定门：manage 实时求值（免登录页不扩权）＋决定闭集。
        call("harness.case_member_declare", {
            "actor_id": ADMIN, "scope": SCOPE, "key": key("mb-rev"),
            "members": [{"userId": REVIEWER, "orgId": ORG,
                         "roles": ["paralegal"]}]})
        self.expect_error(
            "c23_decide_without_manage_named_refused",
            lambda: call("harness.formal_approval_decide", {
                "actor_id": REVIEWER, "scope": SCOPE, "key": key("dc-0"),
                "decision": {"approvalId": "appr-recon-1",
                             "decision": "approved",
                             "decisionRef": "receipt:rev"}}),
            "case_permission_denied:manage:default")
        self.expect_error(
            "c23_decision_closed_set",
            lambda: call("harness.formal_approval_decide", {
                "actor_id": ADMIN, "scope": SCOPE, "key": key("dc-1"),
                "decision": {"approvalId": "appr-recon-1",
                             "decision": "maybe",
                             "decisionRef": "receipt:x"}}),
            "f142_decision_invalid:maybe")

        # ---- C24 采用后实记：显式 decide 唯一入账通道；二次决定具名拒。
        decided = call("harness.formal_approval_decide", {
            "actor_id": ADMIN, "scope": SCOPE, "key": key("dc-2"),
            "decision": {"approvalId": "appr-recon-1",
                         "decision": "approved",
                         "decisionRef": "receipt:recon-dc-2026-001"}})
        self.step("c24_decide_records_on_adoption",
                  decided["state"] == "approved"
                  and decided["decidedBy"] == ADMIN
                  and decided["decisionRef"] == "receipt:recon-dc-2026-001",
                  roundSeq=decided["roundSeq"])
        row = query("SELECT state, decision_json, decided_by, decision_ref"
                    " FROM formal_approval_rounds"
                    " WHERE approval_id='appr-recon-1' AND round_seq=1", ())
        self.step("c24_decision_row_verified",
                  row[0]["state"] == "approved"
                  and json.loads(row[0]["decision_json"])
                  == {"decision": "approved",
                      "decisionRef": "receipt:recon-dc-2026-001"}
                  and row[0]["decision_ref"] == "receipt:recon-dc-2026-001")
        self.expect_error(
            "c24_second_decide_named_refused",
            lambda: call("harness.formal_approval_decide", {
                "actor_id": ADMIN, "scope": SCOPE, "key": key("dc-3"),
                "decision": {"approvalId": "appr-recon-1",
                             "decision": "rejected",
                             "decisionRef": "receipt:x"}}),
            "f142_approval_already_decided:appr-recon-1:1")
        self.expect_error(
            "c24_page_issue_on_decided_round_refused",
            lambda: call("harness.formal_approval_page_issue", {
                "actor_id": ADMIN, "scope": SCOPE, "key": key("pg-3"),
                "page": {"pageId": "page-recon-2",
                         "approvalId": "appr-recon-1"}}),
            "f142_approval_not_open:appr-recon-1:1")

        # ---- C25 页撤销立失效＋严格具名。
        revoked_page = call("harness.formal_approval_page_revoke", {
            "actor_id": ADMIN, "key": key("rv-1"),
            "revoke": {"pageId": "page-recon-1"}})
        self.step("c25_page_revoke_manual",
                  revoked_page["revokedReason"] == "manual")
        self.expect_error(
            "c25_view_after_revoke_named_refused",
            lambda: call("harness.formal_approval_page_view",
                         {"token": page_token}),
            "f142_page_revoked:manual")
        self.expect_error(
            "c25_double_revoke_named_refused",
            lambda: call("harness.formal_approval_page_revoke", {
                "actor_id": ADMIN, "key": key("rv-2"),
                "revoke": {"pageId": "page-recon-1"}}),
            "f142_page_not_active:page-recon-1")

        # ---- C26 重开＝追加下一轮；回读投影无 token hash。
        sha_b = self.write_preparation(call, query, "run-synth-b",
                                       "legal_opinion")
        reopened = call("harness.formal_approval_open", {
            "actor_id": ADMIN, "scope": SCOPE, "key": key("ao-3"),
            "request": {"approvalId": "appr-recon-1",
                        "runId": "run-synth-b"}})
        self.step("c26_reopen_appends_new_round",
                  reopened["roundSeq"] == 2
                  and reopened["state"] == "open"
                  and reopened["documentSha256"] == sha_b,
                  roundSeq=reopened["roundSeq"])
        read_back = call("harness.formal_approval_read", {
            "actor_id": ADMIN, "scope": SCOPE,
            "approval_id": "appr-recon-1"})
        self.step("c26_read_projection_rounds_desc_no_token_hash",
                  [r["roundSeq"] for r in read_back["rounds"]] == [2, 1]
                  and [r["state"] for r in read_back["rounds"]]
                  == ["open", "approved"]
                  and "token" not in json.dumps(read_back),
                  rounds=len(read_back["rounds"]))
        listing = call("harness.formal_approval_list", {
            "actor_id": ADMIN, "scope": SCOPE})
        by_id = {a["approvalId"]: a for a in listing["approvals"]}
        self.step("c26_list_latest_round_summary",
                  by_id["appr-recon-1"]["state"] == "open"
                  and by_id["appr-recon-1"]["roundCount"] == 2,
                  approvals=len(listing["approvals"]))

        # ---- C27 preserved：v1 已有文件终局不得等 v2（零改动回归断言）。
        # ①既有类型面同码：审批账有行时缺 run/preparation 的 commit_formal
        # 与本面引入前完全同码（KeyError run_not_found 先于一切审批逻辑）
        # ②finalization.py 源零引用审批标识（commit 路径结构上不可能读审
        # 批账）——②在 profile 分支做（需 harness 源路径）。
        code = self.expect_error(
            "c27_commit_typeface_identical_with_approval_rows",
            lambda: self.finalization.commit_formal("run-synth-a"),
            "run_not_found:run-synth-a")
        _ = code

        # ---- C28 DB 账行计数。
        counts = {}
        for table in ("collab_doc_comments", "formal_approval_rounds",
                      "formal_approval_pages"):
            counts[table] = query(
                "SELECT COUNT(*) AS n FROM %s" % table, ())[0]["n"]
        self.step("c28_db_three_ledgers",
                  counts["collab_doc_comments"] == 2
                  and counts["formal_approval_rounds"] == 2
                  and counts["formal_approval_pages"] == 1,
                  counts=counts)

    def write_preparation(self, call, query, run_id: str,
                          document_type: str) -> str:
        """合成 preparation 清单（真实流程由 P02 prepare_formal 落盘；本
        对账 C2x 块用同形合成清单供审批锚定——sha 必须真实在 CAS）。"""
        sha = self.store.cas.put_bytes(
            ("正式文档合成字节:%s" % run_id).encode("utf-8"))["sha256"]
        prep_root = self.store.state_root / "finalization" / run_id
        prep_root.mkdir(parents=True, exist_ok=True)
        (prep_root / "preparation.json").write_text(json.dumps(
            {"schema_version": "1.0", "run_id": run_id,
             "document_type": document_type, "output_sha256": sha}),
            encoding="utf-8")
        return sha

    def preserved_source_checks(self, harness_src: Path):
        """C27②＋C00 触发器已验：finalization.py 源零引用审批/评论标识
        （commit_formal 终局面零改动——v1 终局不等 v2 的结构半边）。"""
        source = (harness_src / "legal_harness" / "finalization.py"
                  ).read_text(encoding="utf-8")
        clean = all(marker not in source
                    for marker in ("formal_approval", "collab_doc_comment"))
        self.step("c27_finalization_source_zero_approval_reference",
                  clean, scanned="finalization.py")

    # -- desktop 独有：真实 P02 管线段（C40）＋桥负向（C30）--------------

    def live_pipeline_flow(self, call, query):
        """C40 真实管线：RuntimeFixture 合成 formal run → prepare_formal
        经桥（P02 既有信封）→ 审批锚定真实 preparation → 页签发/浏览 →
        decide 采用后实记 → commit_formal 经桥终局 PASS。审批锚定与终局
        交付同字节；终局不等审批（decide 在 commit 之前完成但 commit 不
        读审批账——行为由 P02 既有面保证，本段实测同管线上审批共存）。"""
        sys.path.insert(0, str(self.harness_root))
        from tests.helpers.runtime_fixture import (
            RuntimeFixture,
            baseline_request,
        )
        from legal_harness.qc import QCService

        run_id = "run-live-f142"  # 标签仅供证据显示；真实 run id 以 start 回执为准。
        request = baseline_request(
            matter_id=MATTER, task_id="f142-live", output_type="formal_document",
            objective="F142 recon live pipeline",
            matter_profile_ref="cas://" + "a" * 64,
            materials_manifest_ref=None,
        )
        request["document_contract_ref"] = self.runtime.document_contract_ref()
        run = self.runtime.start(request)
        real_run_id = run["run_id"]
        content = json.dumps(
            {"正文": {"kind": "paragraphs",
                      "items": ["事实与理由第一段（合成）",
                                "事实与理由第二段（合成）"],
                      "style_id": "Normal"}},
            ensure_ascii=False).encode("utf-8")
        artifact = "cas://" + self.store.cas.put_bytes(content)["sha256"]

        def make_result(node, _):
            return {"schema_version": "1.0", "node_id": node["node_id"],
                    "role_id": node["role_id"],
                    "role_contract_hash": node["role_contract_hash"],
                    "artifacts": [artifact[6:]], "claims": [],
                    "payload": {"issues": [], "defects": [],
                                "proposed_tasks": [], "notes": []},
                    "open_gaps": []}

        self.runtime.complete_graph(run["run_id"], make_result)
        self.store.advance_round(run["run_id"])
        qc = QCService(self.store)
        refs = ["qc://" + qc.evaluate(run["run_id"], plane, [artifact])[
            "receipt_id"]
            for plane in qc.required_planes("formal_document")]
        prepared = call("harness.prepare_formal", {
            "schema_version": "1.0", "run_id": real_run_id,
            "document_type": "complaint", "output_name": "recon-f142.docx",
            "fills_ref": artifact, "qc_receipt_refs": refs,
            "forbidden_values": LIVE_FORBIDDEN})
        self.step("c40_prepare_formal_via_bridge",
                  prepared["status"] == "NEEDS_FINAL_CHECK"
                  and len(prepared["output_sha256"]) == 64,
                  outputSha256=prepared["output_sha256"][:16])
        approval = call("harness.formal_approval_open", {
            "actor_id": ADMIN, "scope": SCOPE, "key": key("ao-live"),
            "request": {"approvalId": "appr-live",
                        "runId": real_run_id}})
        self.step("c40_approval_anchors_real_preparation",
                  approval["documentSha256"] == prepared["output_sha256"]
                  and approval["state"] == "open",
                  documentSha256=approval["documentSha256"][:16])
        live_page = call("harness.formal_approval_page_issue", {
            "actor_id": ADMIN, "scope": SCOPE, "key": key("pg-live"),
            "page": {"pageId": "page-live",
                     "approvalId": "appr-live"}})
        live_view = call("harness.formal_approval_page_view",
                         {"token": live_page["pageToken"]})
        self.step("c40_page_view_over_real_run",
                  live_view["approval"] == {"state": "open"}
                  and live_view["documentSha256"]
                  == prepared["output_sha256"])
        decided = call("harness.formal_approval_decide", {
            "actor_id": ADMIN, "scope": SCOPE, "key": key("dc-live"),
            "decision": {"approvalId": "appr-live",
                         "decision": "approved",
                         "decisionRef": "receipt:recon-live-001"}})
        self.step("c40_decide_after_adoption",
                  decided["state"] == "approved")
        committed = call("harness.commit_formal", {
            "schema_version": "1.0", "run_id": real_run_id,
            "forbidden_values": LIVE_FORBIDDEN})
        delivered_sha = committed["document_receipt"]["output_sha256"]
        self.step("c40_commit_formal_terminal_unaffected_by_approval",
                  committed["status"] == "PASS"
                  and delivered_sha == prepared["output_sha256"],
                  terminalStatus=committed.get("status"))
        row = query("SELECT document_sha256 FROM formal_approval_rounds"
                    " WHERE approval_id='appr-live' AND round_seq=1", ())
        self.step("c40_approval_sha_equals_delivered_bytes",
                  row[0]["document_sha256"] == delivered_sha,
                  shaEqualsDelivery=True)
        self.live_pipeline = {
            "runId": real_run_id,
            "documentSha256": delivered_sha,
            "approvalId": "appr-live",
            "terminal": committed["status"],
        }

    def bridge_negatives(self, config):
        # ---- C30 桥负向：未配置/未知方法/方法组冻结/P02 FAIL 信封。
        try:
            legal_entry.call("harness.formal_approval_list",
                             {"actor_id": ADMIN, "scope": SCOPE}, {})
            raise AssertionError("bridge_not_configured_expected")
        except NotConnected as exc:
            self.step("c30_bridge_not_configured",
                      "harness_public_entry_not_configured" in str(exc))
        try:
            legal_entry.call("harness.formal_approval_force_decide",
                             {"approvalId": "x"}, config)
            raise AssertionError("bridge_unknown_method_expected")
        except NotConnected as exc:
            self.step("c30_bridge_unknown_method_refused",
                      "method_not_connected" in str(exc))
        self.step("c30_method_groups_frozen",
                  legal_entry.HARNESS_COLLABDOC_METHODS == COLLABDOC_METHODS
                  and legal_entry.HARNESS_APPROVAL_METHODS == APPROVAL_METHODS
                  and legal_entry.HARNESS_FORMAL_LIFECYCLE_METHODS
                  == FORMAL_LIFECYCLE_METHODS)
        try:
            legal_entry.call("harness.collab_doc_comment_force_allow",
                             {"commentId": "x"}, config)
            raise AssertionError("bridge_forged_method_expected")
        except NotConnected as exc:
            self.step("c30_forged_bypass_methods_absent",
                      "method_not_connected" in str(exc))

    # -- profile drivers ---------------------------------------------------

    def run_desktop(self) -> int:
        temporary = tempfile.TemporaryDirectory(
            prefix="juscite-f141f142-desktop-")
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
            "harness_timeout": 180,
        }
        if str(self.harness_root / "src") not in sys.path:
            sys.path.insert(0, str(self.harness_root / "src"))
        from legal_harness.state.matter_store import MatterStore
        from legal_harness.finalization import FinalizationService
        self.store = MatterStore(state_root)
        self.store.create_matter(MATTER, "cas://profile-f141f142-recon")
        self.finalization = FinalizationService(self.store)
        db_file = self.store.database_path

        def call(method, args):
            return legal_entry.call(method, args, config)

        def query(sql, params):
            with contextlib.closing(self.store._connect()) as connection:
                connection.row_factory = sqlite3.Row
                rows = connection.execute(sql, params).fetchall()
            return [dict(row) for row in rows]

        def execute(sql, params):
            with self.store.transaction() as connection:
                connection.execute(sql, params)

        print("[profile desktop] SQLite via product bridge subprocess"
              " (--collabdoc-json/--approval-json/--prepare-formal-json/"
              "--commit-formal-json)", flush=True)
        self.common_flow("desktop", call, query, execute, db_file)
        self.preserved_source_checks(self.harness_root / "src")
        sys.path.insert(0, str(self.harness_root))
        from tests.helpers.runtime_fixture import RuntimeFixture
        self.runtime = RuntimeFixture(self.store)
        self.live_pipeline_flow(call, query)
        self.bridge_negatives(config)
        return 0

    def run_selfhost(self, dsn: str) -> int:
        if str(self.harness_root / "src") not in sys.path:
            sys.path.insert(0, str(self.harness_root / "src"))
        from legal_harness.business.provider_registry import (
            resolve_provider_method,
        )
        from legal_harness.business.units import HarnessUnits
        from legal_harness.finalization import FinalizationService
        from legal_harness.state.pg_store import PgMatterStore

        temporary = tempfile.TemporaryDirectory(
            prefix="juscite-f141f142-selfhost-")
        self._pg_schema = "f141f142_" + _uuid.uuid4().hex[:12]
        self.store = PgMatterStore(
            Path(temporary.name) / "state", dsn=dsn,
            schema=self._pg_schema)
        units = HarnessUnits(self.store)
        self.finalization = FinalizationService(self.store)
        methods = (COLLABDOC_METHODS | APPROVAL_METHODS | BOOT_METHODS)
        bound = {name: resolve_provider_method(name, units)
                 for name in sorted(methods)}
        self.store.create_matter(MATTER, "cas://profile-f141f142-recon")

        def call(method, args):
            return bound[method](**args)

        def query(sql, params):
            with contextlib.closing(self.store._connect()) as connection:
                rows = connection.execute(sql, params).fetchall()
            return [dict(row) for row in rows]

        def execute(sql, params):
            with self.store.transaction() as connection:
                connection.execute(sql, params)

        print("[profile selfhost] PgMatterStore direct (lh-pg-e08)",
              flush=True)
        try:
            self.common_flow("selfhost", call, query, execute, None)
            self.preserved_source_checks(self.harness_root / "src")
        finally:
            store = self.store
            store.destroy()
        return 0


def write_evidence(profile: str, recon: Recon, harness_root: Path,
                   started: str, code: int) -> list[Path]:
    finished = datetime.now(timezone.utc).isoformat()
    features = ["F141", "F142"]
    payloads = {}
    for feature in features:
        summary = {
            "schema": "juscite-f141-f142-collab-lifecycle-recon/1",
            "unit": "W5-U13",
            "features": [feature],
            "profile": profile,
            "verdict": "RECON_OK" if code == 0 else "RECON_FAIL",
            "started_at": started,
            "finished_at": finished,
            "harness_worktree": str(harness_root),
            "harness_branch": "w5-u13",
            "harness_base":
                "w5-u06@98a562fd（A2 分支链常驻；master 929d0802 零动）",
            "acceptance": (
                "评论/分享按对象权限及版本，撤销立失效，不越权原件"
                if feature == "F141" else
                "正式文档生命周期/审批采用后实记；v1已有文件终局不得等v2"),
            "checks": recon.checks,
            "check_count": len(recon.checks),
            "failed": [c["check"] for c in recon.checks
                       if c["status"] != "PASS"],
            "livePipeline": recon.live_pipeline,
        }
        payload = json.dumps(summary, ensure_ascii=False, indent=1)
        lines = [
            "# F141/F142 协作与生命周期治理对账（%s）——%s" % (profile,
                                                             feature),
            "",
            f"- unit: W5-U13 · profile: {profile}",
            f"- verdict: **{summary['verdict']}**"
            f" ({len(recon.checks)} checks, exit {code})",
            f"- harness: `{harness_root}` @ branch w5-u13"
            "（基 w5-u06@98a562fd 战役链头；master 929d0802 零动）",
            f"- acceptance: {summary['acceptance']}",
            f"- started: {started} · finished: {finished}",
            "",
            "| # | check | status |",
            "|---|---|---|",
        ]
        for index, check in enumerate(recon.checks, 1):
            lines.append(f"| {index} | {check['check']}"
                         f" | {check['status']} |")
        payloads[feature] = (payload, "\n".join(lines) + "\n")
    written: list[Path] = []
    for feature, (payload, markdown) in payloads.items():
        for base in (REPO_ROOT / "evidence" / feature / profile,
                     REPO_ROOT / "docs" / "construction" / "evidence"
                     / feature / profile):
            base.mkdir(parents=True, exist_ok=True)
            path = base / "f141_f142_collab_lifecycle_recon.json"
            path.write_text(payload + "\n", encoding="utf-8")
            (base / "f141_f142_collab_lifecycle_recon.md").write_text(
                markdown, encoding="utf-8")
            written.append(path)
    return written


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", action="append",
                        choices=["desktop", "selfhost"])
    parser.add_argument("--harness-root", type=Path,
                        default=DEFAULT_HARNESS_ROOT)
    parser.add_argument("--pg-dsn", default=DEFAULT_PG_DSN)
    args = parser.parse_args()
    profiles = args.profile or ["desktop"]
    if not (args.harness_root
            / "tools/workflow-tools/harness/public_entry.py").exists():
        print("RECON_BLOCKED: harness root missing public_entry:",
              args.harness_root)
        return 3
    failures = 0
    first = True
    for profile in profiles:
        started = datetime.now(timezone.utc).isoformat()
        recon = Recon(args.harness_root)
        try:
            if first:
                recon.branch_checks()
            if profile == "desktop":
                code = recon.run_desktop()
            else:
                code = recon.run_selfhost(args.pg_dsn)
        except Exception as error:  # noqa: BLE001 - reported per profile
            print(f"RECON_FAIL[{profile}]: {error}", flush=True)
            recon.checks.append({"check": "recon_driver", "status": "FAIL",
                                 "error": str(error)[:400]})
            code = 2
        written = write_evidence(profile, recon, args.harness_root,
                                 started, code)
        verdict = "RECON_OK" if code == 0 else "RECON_FAIL"
        print(f"[{profile}] {verdict} ({len(recon.checks)} checks,"
              f" exit {code}) evidence={written[0]}", flush=True)
        if code != 0:
            failures += 1
        first = False
    return 0 if failures == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
