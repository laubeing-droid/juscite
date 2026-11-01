"""F05 协作面完整化对账（W4-U31）——org 邀请/email 直授 RBAC/分享 token/
升级弃权档案——双 profile。

对账对象：harness 分支 w4-u31（基战役链头 w4-u01@23f56d70＝w3-u20→
w4-u01/F118v1.5 同链接力；master 929d0802 零动＝A2 裁决 00-总协调.md:252
「分支保留不合并」）的公开面——desktop profile 走产品桥（legal_entry
HARNESS_COLLAB_METHODS → 子进程 public_entry --collab-json 信封；SQLite
状态根）；selfhost profile＝PgMatterStore 直连 lh-pg-e08
（resolve_provider_method 同一封闭注册）。合同 harness
docs/f05-collab-surface-contract.md；schema v30 四账。

acceptance（台账 F05-desktop/F05-selfhost assertion）：「邀请/直授/撤权
按角色落真实权限；旧分享token失效且无越权文档」。落真实权限的唯一落点
＝F04 求值 _case_membership roster 回落（case_members 案行优先零漂移；
F04/F92 既有面 W3-U07 已 VERIFIED——本对账 C05d 钉案行优先零漂移）；
旧 token 失效＝成员撤权同事务级联 token revoked（C08）＋邀请 token 撤销
/复用具名拒（C09）。

升级弃权档案＝升级路径权限语义变化留档（C10 闭集留档＋回读；留档事实
随证据落 evidence/F05/<profile>/ waiverArchive 节）。

全部合成材料：临时状态根、合成 org/email/user/文档字节；harness 检出
零字节改动（只运行其代码，git 只读命令核对分支）；%APPDATA% 零触碰；
不 push。

用法：
  python -X utf8 tools/PENDING_OWNER_f05_collaboration_recon.py \
      --profile desktop --profile selfhost

退出码：0 = 全部 profile RECON_OK；2 = RECON_FAIL；3 = 环境缺失。
证据：evidence/F05/<profile>/＋docs/construction/evidence/F05/<profile>/
镜像（JSON＋MD，含 waiverArchive 回读）。
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

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "python"))
sys.path.insert(0, str(REPO_ROOT / "implementation" / "tests"))

import legal_entry  # noqa: E402
from legal_entry import HarnessCommandError, NotConnected  # noqa: E402

DEFAULT_HARNESS_ROOT = Path(
    r"D:\Codex\1.法律工作区\legal-harness工作区\legal-harness-repo"
    r"\.local\worktrees\w4-u31")

MATTER = "m-f05-recon"
SCOPE = {"kind": "matter", "matterId": MATTER}
DOC_MARKER = "F05-SYNTH-SHARE-DOC-MARKER-不外泄"
ADMIN = "recon-admin"
MEMBER = "recon-member"
GRANTEE = "recon-grantee"
ORG = "org-recon-f05"
OTHER_ORG = "org-recon-other"

# lh-pg-e08 容器（E08 拓扑）：仅回环端口、合成专用凭据（可用 --pg-dsn 覆写）。
DEFAULT_PG_DSN = "postgresql://lh_app:e08-synth-only@127.0.0.1:55432/legal_harness"

COLLAB_METHODS = frozenset({
    "harness.collab_invite_create", "harness.collab_invite_accept",
    "harness.collab_invite_revoke", "harness.collab_grant_direct",
    "harness.collab_member_revoke", "harness.collab_member_read",
    "harness.collab_share_token_issue", "harness.collab_share_token_resolve",
    "harness.collab_share_token_revoke",
    "harness.collab_upgrade_waiver_record",
    "harness.collab_upgrade_waiver_read",
})
ALL_ACTIONS = ("read", "write", "events", "export", "manage")

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
    except (HarnessCommandError, ValueError, Exception) as exc:  # noqa: BLE001
        return code_part in str(exc), str(exc)
    return False, "no typed error raised"


class Recon:
    def __init__(self, harness_root: Path):
        self.harness_root = harness_root
        self.checks: list[dict] = []
        self.waiver_archive: dict | None = None

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
        base = self.git(self.harness_root, "merge-base", "HEAD", "w4-u01")
        master = self.git(self.harness_root, "rev-parse", "master")
        self.step("c01_harness_branch", branch == "w4-u31", branch=branch)
        self.step("c01_harness_base_on_w4_u01_chain_head",
                  base.startswith("23f56d70"), base=base)
        self.step("c01_harness_master_untouched_A2",
                  master.startswith("929d0802"), master=master)
        dirty = self.git(self.harness_root, "status", "--porcelain")
        self.step("c01_harness_worktree_clean", dirty == "", dirty=dirty[:200])

    # ------------------------------------------------------------------
    # C02–C12：call(method, args) 走被测链；query/exec 直读同一库。
    # ------------------------------------------------------------------
    def common_flow(self, profile: str, call, query, execute,
                    db_file: Path | None):
        # ---- C02 org 邀请创建：token 只在本回执出现一次；账面只存 sha256。
        created = call("harness.collab_invite_create", {
            "actor_id": ADMIN, "key": key("inv-1"),
            "invite": {"inviteId": "inv-recon-1", "orgId": ORG,
                       "email": "grantee@example.com",
                       "roles": ["paralegal"]}})
        invite_token = created["inviteToken"]
        self.step("c02_invite_created_pending",
                  created["state"] == "pending"
                  and invite_token.startswith("lhinv-")
                  and created["roles"] == ["paralegal"],
                  inviteId=created["inviteId"])
        row = query("SELECT invite_token_hash FROM collab_org_invitations"
                    " WHERE invite_id='inv-recon-1'", ())
        digest = hashlib.sha256(invite_token.encode("utf-8")).hexdigest()
        self.step("c02_invite_token_sha256_at_rest",
                  row[0]["invite_token_hash"] == digest
                  and invite_token not in row[0]["invite_token_hash"],
                  stored="sha256")
        if db_file is not None:
            raw = db_file.read_bytes()
            self.step("c02_invite_raw_token_absent_in_db_file",
                      invite_token.encode("utf-8") not in raw,
                      scanned=str(db_file.name))

        # ---- C03 邀请接受：名册 active；旧 token 复用/未知具名拒。
        accepted = call("harness.collab_invite_accept", {
            "actor_id": GRANTEE, "key": key("ia-1"),
            "accept": {"inviteToken": invite_token, "userId": GRANTEE}})
        self.step("c03_invite_accepted_roster_active",
                  accepted["source"] == "invite_accepted"
                  and accepted["state"] == "active"
                  and accepted["orgId"] == ORG,
                  memberSeq=accepted["memberSeq"])
        projection = call("harness.collab_member_read", {"org_id": ORG})
        by_user = {m["userId"]: m for m in projection["members"]}
        self.step("c03_member_read_projection",
                  by_user[GRANTEE]["state"] == "active"
                  and by_user[GRANTEE]["roles"] == ["paralegal"],
                  activeCount=projection["activeCount"])
        self.expect_error(
            "c03_invite_token_used_refused",
            lambda: call("harness.collab_invite_accept", {
                "actor_id": "other", "key": key("ia-2"),
                "accept": {"inviteToken": invite_token,
                           "userId": "other"}}),
            "f05_invite_token_used")
        self.expect_error(
            "c03_invite_token_unknown_refused",
            lambda: call("harness.collab_invite_accept", {
                "actor_id": "other", "key": key("ia-3"),
                "accept": {"inviteToken": "lhinv-not-a-real-token",
                           "userId": "other"}}),
            "f05_invite_token_unknown")

        # ---- C04 email 直授：无需邀请即 active；重复直授＝追加末条生效。
        granted = call("harness.collab_grant_direct", {
            "actor_id": ADMIN, "key": key("gd-1"),
            "grant": {"orgId": ORG, "userId": MEMBER,
                      "email": "member@example.com",
                      "roles": ["paralegal"]}})
        self.step("c04_direct_grant_active",
                  granted["source"] == "direct_grant"
                  and granted["state"] == "active")
        call("harness.collab_grant_direct", {
            "actor_id": ADMIN, "key": key("gd-2"),
            "grant": {"orgId": ORG, "userId": MEMBER,
                      "email": "member@example.com",
                      "roles": ["reviewer"]}})
        projection = call("harness.collab_member_read",
                          {"org_id": ORG, "user_id": MEMBER})
        self.step("c04_regrant_latest_row_wins",
                  projection["members"][0]["roles"] == ["reviewer"]
                  and projection["memberCount"] == 1,
                  roles=projection["members"][0]["roles"])
        # 恢复 paralegal 角色供后续断言（再追加一行）。
        call("harness.collab_grant_direct", {
            "actor_id": ADMIN, "key": key("gd-3"),
            "grant": {"orgId": ORG, "userId": MEMBER,
                      "email": "member@example.com",
                      "roles": ["paralegal"]}})

        # ---- C05 邀请/直授按角色落真实权限（acceptance 前半）。
        # 受管案 bootstrap（F04 武装窗：admin 案行＋全量 allow）＋角色规则。
        call("harness.case_member_declare", {
            "actor_id": ADMIN, "scope": SCOPE, "key": key("mb-boot"),
            "members": [{"userId": ADMIN, "orgId": ORG,
                         "roles": ["case-admin"]}]})
        call("harness.case_permission_rule", {
            "actor_id": ADMIN, "scope": SCOPE, "key": key("rl-boot"),
            "rules": [rule("user", ADMIN, action, "allow")
                      for action in ALL_ACTIONS]})
        call("harness.case_permission_rule", {
            "actor_id": ADMIN, "scope": SCOPE, "key": key("rl-role"),
            "rules": [rule("role", "paralegal", "read", "allow")]})
        doc = ("合成材料文档：%s；余额 123456.78 元。"
               % DOC_MARKER).encode("utf-8")
        call("harness.register_material", {
            "actor_id": ADMIN, "scope": SCOPE, "key": key("mat-1"),
            "material": {"id": "mat-recon-doc", "kind": "digital_text",
                         "title": "合成分享文档（F05 对账）",
                         "bytesB64": base64.b64encode(
                             doc).decode("ascii"),
                         "matterId": MATTER}})
        # 直授前：GRANTEE 无案行＋未进名册＝membership 拒（F04 既有语义）。
        # ——GRANTEE 已在名册（C03 接受）；改用未入册的局外人验证 membership 拒。
        self.expect_error(
            "c05_outsider_membership_denied",
            lambda: call("harness.list_materials",
                         {"scope": SCOPE, "actor_id": "recon-ghost"}),
            "case_permission_denied:read:membership")
        # GRANTEE（邀请路径）与 MEMBER（直授路径）：roster 回落供给 org+roles
        # → 规则段 role paralegal 命中 → read 面真实放行。
        for who in (GRANTEE, MEMBER):
            listed = call("harness.list_materials",
                          {"scope": SCOPE, "actor_id": who})
            self.step("c05_roster_backed_read_allowed_%s" % who,
                      any(item["id"] == "mat-recon-doc"
                          for item in listed["materials"]),
                      materialCount=listed["materialCount"])
        # write 面未授权 → 规则段无匹配 fail-closed（default deny）。
        self.expect_error(
            "c05_write_face_default_denied",
            lambda: call("harness.register_material", {
                "actor_id": MEMBER, "scope": SCOPE, "key": key("mat-x"),
                "material": {"id": "mat-xx", "kind": "digital_text",
                             "title": "越权写", "bytesB64": "eA==",
                             "matterId": MATTER}}),
            "case_permission_denied:write:default")
        # C05d F04 零漂移：案行声明优先于名册——both-user 同时持有名册行
        # （ORG）与案行（OTHER_ORG），求值必须走案行（memberSource=case、
        # orgId=OTHER_ORG）——W3-U07 已 VERIFIED 语义不被 roster 回落改写。
        call("harness.collab_grant_direct", {
            "actor_id": ADMIN, "key": key("gd-both"),
            "grant": {"orgId": ORG, "userId": "both-user",
                      "email": "both@example.com",
                      "roles": ["paralegal"]}})
        call("harness.case_member_declare", {
            "actor_id": ADMIN, "scope": SCOPE, "key": key("mb-case"),
            "members": [{"userId": "both-user", "orgId": OTHER_ORG,
                         "roles": ["paralegal"]}]})
        view = call("harness.case_permission_read",
                    {"scope": SCOPE, "actor_id": "both-user"})
        self.step("c05d_case_row_precedence_zero_drift",
                  view["actorView"]["read"]["membership"]["memberSource"]
                  == "case"
                  and view["actorView"]["read"]["membership"]["orgId"]
                  == OTHER_ORG,
                  membership=view["actorView"]["read"]["membership"])

        # ---- C06 分享 token 签发（export 门＋受授人门＋材料门＋id 冲突）。
        issued = call("harness.collab_share_token_issue", {
            "actor_id": ADMIN, "scope": SCOPE, "key": key("tok-1"),
            "token": {"tokenId": "tok-recon-1",
                      "materialId": "mat-recon-doc", "action": "read",
                      "granteeUserId": GRANTEE}})
        share_token = issued["shareToken"]
        self.step("c06_token_issued_shape",
                  share_token.startswith("lhshk-")
                  and issued["materialRevision"] == 1
                  and issued["action"] == "read"
                  and issued["granteeUserId"] == GRANTEE,
                  tokenId=issued["tokenId"])
        row = query("SELECT token_hash FROM collab_share_tokens"
                    " WHERE token_id='tok-recon-1'", ())
        self.step("c06_token_sha256_at_rest",
                  row[0]["token_hash"] == hashlib.sha256(
                      share_token.encode("utf-8")).hexdigest(),
                  stored="sha256")
        if db_file is not None:
            raw = db_file.read_bytes()
            self.step("c06_share_raw_token_absent_in_db_file",
                      share_token.encode("utf-8") not in raw,
                      scanned=str(db_file.name))
        # 无 export 授权签发人拒（user limited 只有 read）。
        call("harness.case_member_declare", {
            "actor_id": ADMIN, "scope": SCOPE, "key": key("mb-lim"),
            "members": [{"userId": "limited", "orgId": ORG,
                         "roles": ["paralegal"]}]})
        call("harness.case_permission_rule", {
            "actor_id": ADMIN, "scope": SCOPE, "key": key("rl-lim"),
            "rules": [rule("user", "limited", "read", "allow")]})
        self.expect_error(
            "c06_issuer_without_export_denied",
            lambda: call("harness.collab_share_token_issue", {
                "actor_id": "limited", "scope": SCOPE, "key": key("tok-l"),
                "token": {"tokenId": "tok-lim",
                          "materialId": "mat-recon-doc", "action": "read",
                          "granteeUserId": GRANTEE}}),
            "case_permission_denied:export")
        # 受授人非名册成员拒。
        self.expect_error(
            "c06_grantee_not_member_denied",
            lambda: call("harness.collab_share_token_issue", {
                "actor_id": ADMIN, "scope": SCOPE, "key": key("tok-g"),
                "token": {"tokenId": "tok-ghost",
                          "materialId": "mat-recon-doc", "action": "read",
                          "granteeUserId": "ghost"}}),
            "f05_grantee_not_active_member")
        # 材料不存在拒。
        self.expect_error(
            "c06_material_missing_denied",
            lambda: call("harness.collab_share_token_issue", {
                "actor_id": ADMIN, "scope": SCOPE, "key": key("tok-m"),
                "token": {"tokenId": "tok-nomaterial",
                          "materialId": "mat-ghost", "action": "read",
                          "granteeUserId": GRANTEE}}),
            "f05_material_not_found")
        # 同 tokenId 再签发冲突。
        self.expect_error(
            "c06_token_id_conflict",
            lambda: call("harness.collab_share_token_issue", {
                "actor_id": ADMIN, "scope": SCOPE, "key": key("tok-2"),
                "token": {"tokenId": "tok-recon-1",
                          "materialId": "mat-recon-doc", "action": "read",
                          "granteeUserId": GRANTEE}}),
            "f05_token_id_conflict")

        # ---- C07 token 解析＝活体权限求值（token 只携身份不携权）。
        resolved = call("harness.collab_share_token_resolve",
                        {"token": share_token})
        self.step("c07_resolve_granted",
                  resolved["access"] == "granted"
                  and resolved["materialId"] == "mat-recon-doc"
                  and resolved["materialSha256"],
                  materialSha256=resolved["materialSha256"][:16])
        # 规则段收紧（paralegal read → deny）后同一 active token 立即拒。
        call("harness.case_permission_rule", {
            "actor_id": ADMIN, "scope": SCOPE, "key": key("rl-tighten"),
            "rules": [rule("role", "paralegal", "read", "deny")]})
        self.expect_error(
            "c07_resolve_live_permission_denied",
            lambda: call("harness.collab_share_token_resolve",
                         {"token": share_token}),
            "f05_share_token_permission_denied:read:rule")
        call("harness.case_permission_rule", {
            "actor_id": ADMIN, "scope": SCOPE, "key": key("rl-restore"),
            "rules": [rule("role", "paralegal", "read", "allow")]})
        resolved = call("harness.collab_share_token_resolve",
                        {"token": share_token})
        self.step("c07_resolve_restored", resolved["access"] == "granted")
        self.expect_error(
            "c07_token_unknown_refused",
            lambda: call("harness.collab_share_token_resolve",
                         {"token": "lhshk-not-a-real-token"}),
            "f05_share_token_unknown")

        # ---- C08 撤权：名册失权＋同事务级联 token revoked＋两条读路全拒
        # ＋可达文档集合零增长（acceptance 后半·硬断言）。
        # 撤权前基线：GRANTEE 可达文档（read 面）＝{mat-recon-doc}。
        before = call("harness.list_materials",
                      {"scope": SCOPE, "actor_id": GRANTEE})
        before_ids = sorted(item["id"] for item in before["materials"])
        revoked = call("harness.collab_member_revoke", {
            "actor_id": ADMIN, "key": key("rvk-1"),
            "revoke": {"orgId": ORG, "userId": GRANTEE}})
        self.step("c08_revoke_cascades_token",
                  revoked["state"] == "revoked"
                  and revoked["revokedShareTokens"] == 1
                  and revoked["revokedTokenIds"] == ["tok-recon-1"],
                  revokedTokens=revoked["revokedShareTokens"])
        # 读路一：旧分享 token 解析＝revoked:member_revoked（入账原因原样）。
        self.expect_error(
            "c08_old_share_token_dead",
            lambda: call("harness.collab_share_token_resolve",
                         {"token": share_token}),
            "f05_share_token_revoked:member_revoked")
        # 读路二：成员身份 read 面＝membership 拒（roster 末条 revoked）。
        self.expect_error(
            "c08_member_read_denied_after_revoke",
            lambda: call("harness.list_materials",
                         {"scope": SCOPE, "actor_id": GRANTEE}),
            "case_permission_denied:read:membership")
        # 账面事实：token 行 state/revoked_reason 可回读。
        row = query("SELECT state, revoked_reason FROM collab_share_tokens"
                    " WHERE token_id='tok-recon-1'", ())
        self.step("c08_token_ledger_revoked_readable",
                  row[0]["state"] == "revoked"
                  and row[0]["revoked_reason"] == "member_revoked",
                  reason=row[0]["revoked_reason"])
        # 复授后旧 token 仍死（级联不可逆——恢复只来自新名册授权，
        # 旧 token 永不重新得权）。
        call("harness.collab_grant_direct", {
            "actor_id": ADMIN, "key": key("gd-4"),
            "grant": {"orgId": ORG, "userId": GRANTEE,
                      "email": "grantee@example.com",
                      "roles": ["paralegal"]}})
        self.expect_error(
            "c08_old_token_still_dead_after_regrant",
            lambda: call("harness.collab_share_token_resolve",
                         {"token": share_token}),
            "f05_share_token_revoked:member_revoked")
        # 周期收口：复授后可达集合恰回到基线（整个撤权/复授周期零净增长
        # ——恢复来自 regrant 而非旧 token，由上检具名证明；撤权窗内可达
        # 集合＝空集 ⊆ 基线，由 c08 两读路具名拒证明）。
        after = call("harness.list_materials",
                     {"scope": SCOPE, "actor_id": GRANTEE})
        after_ids = sorted(item["id"] for item in after["materials"])
        self.step("c08_reachable_documents_zero_net_growth",
                  after_ids == before_ids,
                  before=before_ids, after=after_ids)
        # 撤权新 token 需重发：新签发（新 tokenId）可解析。
        issued2 = call("harness.collab_share_token_issue", {
            "actor_id": ADMIN, "scope": SCOPE, "key": key("tok-3"),
            "token": {"tokenId": "tok-recon-2",
                      "materialId": "mat-recon-doc", "action": "read",
                      "granteeUserId": GRANTEE}})
        resolved2 = call("harness.collab_share_token_resolve",
                         {"token": issued2["shareToken"]})
        self.step("c08_new_token_after_regrant_works",
                  resolved2["access"] == "granted")

        # ---- C09 邀请 token 生命周期：撤销后接受具名拒；再撤具名拒。
        created2 = call("harness.collab_invite_create", {
            "actor_id": ADMIN, "key": key("inv-2"),
            "invite": {"inviteId": "inv-recon-2", "orgId": ORG,
                       "email": "late@example.com",
                       "roles": ["paralegal"]}})
        call("harness.collab_invite_revoke", {
            "actor_id": ADMIN, "key": key("irv-1"),
            "revoke": {"inviteId": "inv-recon-2"}})
        self.expect_error(
            "c09_revoked_invite_accept_refused",
            lambda: call("harness.collab_invite_accept", {
                "actor_id": "late", "key": key("ia-4"),
                "accept": {"inviteToken": created2["inviteToken"],
                           "userId": "late"}}),
            "f05_invite_token_revoked")
        self.expect_error(
            "c09_invite_double_revoke_refused",
            lambda: call("harness.collab_invite_revoke", {
                "actor_id": ADMIN, "key": key("irv-2"),
                "revoke": {"inviteId": "inv-recon-2"}}),
            "f05_invite_not_pending")
        # 撤成员无 active 行再撤＝具名拒不吞。
        call("harness.collab_member_revoke", {
            "actor_id": ADMIN, "key": key("rvk-2"),
            "revoke": {"orgId": ORG, "userId": MEMBER}})
        self.expect_error(
            "c09_double_revoke_refused",
            lambda: call("harness.collab_member_revoke", {
                "actor_id": ADMIN, "key": key("rvk-3"),
                "revoke": {"orgId": ORG, "userId": MEMBER}}),
            "f05_member_not_active")

        # ---- C10 升级弃权档案：闭集留档＋回读＋闭集外具名拒。
        changes = ["legacy_share_links_invalidated",
                   "share_tokens_live_permission_bound",
                   "default_deny_managed_cases"]
        recorded = call("harness.collab_upgrade_waiver_record", {
            "actor_id": ADMIN, "key": key("waiv-1"),
            "waiver": {"waiverId": "waiv-recon-1", "orgId": ORG,
                       "fromSemantics": "legacy_share_raw_access",
                       "toSemantics": "rbac_live_permission",
                       "changes": changes,
                       "acknowledgedBy": ADMIN}})
        self.step("c10_waiver_recorded",
                  recorded["waiverId"] == "waiv-recon-1"
                  and recorded["toSemantics"] == "rbac_live_permission",
                  changes=recorded["changes"])
        read_back = call("harness.collab_upgrade_waiver_read",
                         {"waiver_id": "waiv-recon-1"})
        self.step("c10_waiver_read_back",
                  read_back["changes"] == sorted(changes)
                  and read_back["acknowledgedBy"] == ADMIN
                  and read_back["fromSemantics"]
                  == "legacy_share_raw_access",
                  recordedAt=read_back["recordedAt"])
        self.waiver_archive = read_back
        self.expect_error(
            "c10_waiver_from_closed_set",
            lambda: call("harness.collab_upgrade_waiver_record", {
                "actor_id": ADMIN, "key": key("waiv-2"),
                "waiver": {"waiverId": "waiv-x", "orgId": ORG,
                           "fromSemantics": "made_up_semantics",
                           "toSemantics": "rbac_live_permission",
                           "changes": ["default_deny_managed_cases"],
                           "acknowledgedBy": ADMIN}}),
            "f05_waiver_from_invalid")
        self.expect_error(
            "c10_waiver_changes_closed_set",
            lambda: call("harness.collab_upgrade_waiver_record", {
                "actor_id": ADMIN, "key": key("waiv-3"),
                "waiver": {"waiverId": "waiv-y", "orgId": ORG,
                           "fromSemantics": "open_case_access",
                           "toSemantics": "rbac_live_permission",
                           "changes": ["not_in_closed_set"],
                           "acknowledgedBy": ADMIN}}),
            "f05_waiver_changes_invalid")
        self.expect_error(
            "c10_waiver_id_conflict",
            lambda: call("harness.collab_upgrade_waiver_record", {
                "actor_id": ADMIN, "key": key("waiv-4"),
                "waiver": {"waiverId": "waiv-recon-1", "orgId": ORG,
                           "fromSemantics": "open_case_access",
                           "toSemantics": "rbac_live_permission",
                           "changes": ["default_deny_managed_cases"],
                           "acknowledgedBy": ADMIN}}),
            "f05_waiver_id_conflict")

        # ---- C11 DB 级扫描：四账行数。
        counts = {}
        for table in ("collab_org_members", "collab_org_invitations",
                      "collab_share_tokens", "collab_upgrade_waivers"):
            counts[table] = query("SELECT COUNT(*) AS n FROM %s" % table,
                                  ())[0]["n"]
        self.step("c11_db_four_ledgers",
                  counts["collab_org_members"] >= 5
                  and counts["collab_org_invitations"] == 2
                  and counts["collab_share_tokens"] == 2
                  and counts["collab_upgrade_waivers"] == 1,
                  counts=counts)

    def bridge_negatives(self, config):
        # ---- C12 桥负向：未配置/未知方法/方法组冻结。
        try:
            legal_entry.call("harness.collab_member_read",
                             {"org_id": ORG}, {})
            raise AssertionError("bridge_not_configured_expected")
        except NotConnected as exc:
            self.step("c12_bridge_not_configured",
                      "harness_public_entry_not_configured" in str(exc))
        try:
            legal_entry.call("harness.collab_member_grant",
                             {"org_id": ORG}, config)
            raise AssertionError("bridge_unknown_method_expected")
        except NotConnected as exc:
            self.step("c12_bridge_unknown_method_refused",
                      "method_not_connected" in str(exc))
        self.step("c12_method_group_frozen",
                  legal_entry.HARNESS_COLLAB_METHODS == COLLAB_METHODS)

    # -- profile drivers ---------------------------------------------------

    def run_desktop(self) -> int:
        temporary = tempfile.TemporaryDirectory(
            prefix="juscite-f05-desktop-")
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
        if str(self.harness_root / "src") not in sys.path:
            sys.path.insert(0, str(self.harness_root / "src"))
        from legal_harness.state.matter_store import MatterStore
        store = MatterStore(state_root)
        store.create_matter(MATTER, "cas://profile-f05-recon")
        db_file = store.database_path

        def call(method, args):
            return legal_entry.call(method, args, config)

        def query(sql, params):
            with contextlib.closing(store._connect()) as connection:
                connection.row_factory = sqlite3.Row
                rows = connection.execute(sql, params).fetchall()
            return [dict(row) for row in rows]

        def execute(sql, params):
            with store.transaction() as connection:
                connection.execute(sql, params)

        print("[profile desktop] SQLite via product bridge subprocess"
              " (--collab-json)", flush=True)
        try:
            self.common_flow("desktop", call, query, execute, db_file)
            self.bridge_negatives(config)
        finally:
            _ = execute  # keep signature parity
        return 0

    def run_selfhost(self, dsn: str) -> int:
        if str(self.harness_root / "src") not in sys.path:
            sys.path.insert(0, str(self.harness_root / "src"))
        from legal_harness.business.provider_registry import (
            resolve_provider_method,
        )
        from legal_harness.business.units import HarnessUnits
        from legal_harness.state.pg_store import PgMatterStore

        temporary = tempfile.TemporaryDirectory(
            prefix="juscite-f05-selfhost-")
        store = PgMatterStore(
            Path(temporary.name) / "state", dsn=dsn,
            schema="f05_" + _uuid.uuid4().hex[:12])
        units = HarnessUnits(store)
        methods = set(COLLAB_METHODS) | {
            "harness.case_member_declare", "harness.case_permission_rule",
            "harness.case_permission_read", "harness.register_material",
            "harness.list_materials",
        }
        bound = {name: resolve_provider_method(name, units)
                 for name in sorted(methods)}
        store.create_matter(MATTER, "cas://profile-f05-recon")

        def call(method, args):
            return bound[method](**args)

        def query(sql, params):
            with contextlib.closing(store._connect()) as connection:
                rows = connection.execute(sql, params).fetchall()
            return [dict(row) for row in rows]

        def execute(sql, params):
            with store.transaction() as connection:
                connection.execute(sql, params)

        print("[profile selfhost] PgMatterStore direct (lh-pg-e08)",
              flush=True)
        try:
            self.common_flow("selfhost", call, query, execute, None)
        finally:
            store.destroy()
        return 0


def write_evidence(profile: str, recon: Recon, harness_root: Path,
                   started: str, code: int) -> list[Path]:
    finished = datetime.now(timezone.utc).isoformat()
    summary = {
        "schema": "juscite-f05-collaboration-recon/1",
        "unit": "W4-U31",
        "features": ["F05"],
        "profile": profile,
        "verdict": "RECON_OK" if code == 0 else "RECON_FAIL",
        "started_at": started,
        "finished_at": finished,
        "harness_worktree": str(harness_root),
        "harness_branch": "w4-u31",
        "harness_base": "w4-u01@23f56d70 (w3-u20→w4-u01/F118v1.5 链头；"
                        "master 929d0802 零动＝A2 裁决)",
        "acceptance": "邀请/直授/撤权按角色落真实权限；旧分享token失效且"
                      "无越权文档",
        "checks": recon.checks,
        "check_count": len(recon.checks),
        "failed": [c["check"] for c in recon.checks
                   if c["status"] != "PASS"],
        "waiverArchive": recon.waiver_archive,
    }
    payload = json.dumps(summary, ensure_ascii=False, indent=1)
    written: list[Path] = []
    for base in (REPO_ROOT / "evidence" / "F05" / profile,
                 REPO_ROOT / "docs" / "construction" / "evidence"
                 / "F05" / profile):
        base.mkdir(parents=True, exist_ok=True)
        path = base / "f05_collaboration_recon.json"
        path.write_text(payload + "\n", encoding="utf-8")
        lines = [
            "# F05 协作面完整化对账（%s）" % profile,
            "",
            f"- unit: W4-U31 · profile: {profile}",
            f"- verdict: **{summary['verdict']}**"
            f" ({len(recon.checks)} checks, exit {code})",
            f"- harness: `{harness_root}` @ branch w4-u31"
            "（基 w4-u01@23f56d70 战役链头；master 929d0802 零动＝A2）",
            f"- acceptance: 邀请/直授/撤权按角色落真实权限；"
            "旧分享token失效且无越权文档",
            f"- started: {started} · finished: {finished}",
            "",
            "| # | check | status |",
            "|---|---|---|",
        ]
        for index, check in enumerate(recon.checks, 1):
            lines.append(f"| {index} | {check['check']}"
                         f" | {check['status']} |")
        (base / "f05_collaboration_recon.md").write_text(
            "\n".join(lines) + "\n", encoding="utf-8")
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
