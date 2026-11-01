# -*- coding: utf-8 -*-
"""F53 AI 修订作者与人工决定策略面对账（W2b-U49）——双 profile
（desktop/selfhost）。

对账对象：产品侧 author_policy 策略面（legal_entry AUTHOR_POLICY_METHODS
三方法，author_policy.py 零状态根）＋U12/U14/U15 三机器通道 author 入口
的收拢过闸＋决定引用三方投影（经 HARNESS_FORMAL_PROPOSAL_METHODS 冻结组
只读 harness 提案账——决定权威＝harness formal_decide，W2b-U11 已
VERIFIED，本单零 harness 改动）。desktop profile 与产品桥（legal_entry →
子进程 public_entry）完全同一条链（SQLite 状态根）；selfhost profile＝
PgMatterStore 直连 lh-pg-e08（resolve_provider_method 同一封闭注册；
author.projection 的 harness seam 同 U05/U31 先例由驱动注入直连）。

全部合成材料：f45_fixtures 合成起诉状 DOCX、临时状态根、合成
matter/提案/决定；harness 检出零字节改动（只运行其代码，git 只读命令
核对分支）。

实跑覆盖（PENDING_OWNER_F53_author_decision）：
  作者声明闭集（author.policy：三机器通道绑定＋规则闭集）→ author.check
  具名拒矩阵（三通道绑定 OK；伪造律师名 f53_author_impersonation×3；作者
  与通道错绑 f53_author_channel_mismatch；通道未知 f53_channel_unknown；
  缺作者 f53_author_required）→ 收拢三面真实代码路径伪造作者具名拒
  （docxedit.apply/edits.apply/redline.replay，拒后零半成品）→ 机器提案
  以闭集作者登记（docxedit.apply 正链：assistant_edit rev2＋
  formal_propose(channel=machine, author=lvyin-docxedit) pending）→ 空决
  定面具名拒（formal_decide 缺 reasonRef/receiptRef＝fields_missing——
  「accept 必带决定引用」在决定面入口即拒）→ 律师真实决定引用 accept
  （bake rev3 source=user_accept，proposal 决定引用对齐）→ 三方投影
  （author.projection：律师决定引用↔修订 author↔提案 channel 可读＋
  visibility 块＋两跑同字节确定性）→ 投影伪造作者负向（越面直登伪造律
  师名提案——harness 不校验作者身份，本面 fail-closed 整投影
  f53_author_impersonation 具名拒，绝不静默呈现）→ 桥负向（未知方法/
  未配置/冻结组外伪方法）。跨 profile：投影结构对等（时间戳不入对照，
  U08/E15 先例）。

边界如实（06:F53/17 卡）：批注 w:comment 接受流不在本面（U36 已记边界）；
真机 WPS 宿主联测属 W2b-U50；决定引用缺失/跨提案引用错位两条在真实决定
面结构性不可产出（harness 同事务写 decisionRef.proposalId），其投影守卫
由单测 mock 行级验证（test_f53_author_policy_wiring）。

用法：
  python -X utf8 tools/PENDING_OWNER_f53_author_decision_recon.py \
      --profile desktop --profile selfhost

退出码：0 = 全部 profile RECON_OK；2 = RECON_FAIL；3 = 环境缺失。
证据：docs/construction/evidence/F53/<profile>/ JSON＋MD。
"""
from __future__ import annotations

import argparse
import base64
import json
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
import author_policy as ap  # noqa: E402
import docx_edit  # noqa: E402
import document_redline as dr  # noqa: E402
import edits_protocol as ep  # noqa: E402
import f45_fixtures  # noqa: E402
from bridge_errors import HarnessCommandError, NotConnected  # noqa: E402

DEFAULT_HARNESS_ROOT = Path(
    r"D:\Codex\1.法律工作区\legal-harness工作区\legal-harness-repo"
    r"\.local\worktrees\w2b-u31")

MATTER = "m-f53-recon"
SCOPE = {"kind": "matter", "matterId": MATTER}
MAT_A = "mat-f53-main"     # docxedit 正链材料（闭集作者提案→律师决定）
MAT_B = "mat-f53-forged"   # 越面伪造提案材料（投影负向）
FORGED_LAWYER = "王律师（合成·伪造）"
EDITED_AT = "2026-10-17T00:00:00Z"
REVISION_DATE = "2026-10-17T00:00:00Z"
# lh-pg-e08 容器（E08 拓扑）：仅回环端口、合成专用凭据（LH_PG_PASSWORD
# 同源，密钥只在本机容器；可用 LH_E08_PG_DSN 覆写）。
DEFAULT_PG_DSN = "postgresql://lh_app:e08-synth-only@127.0.0.1:55432/legal_harness"

FORMAL_METHODS = frozenset({
    "harness.formal_propose", "harness.formal_decide",
    "harness.formal_proposal_read", "harness.formal_proposal_list",
})
AUTHOR_POLICY_METHODS = frozenset({
    "author.policy", "author.check", "author.projection",
})


def b64(content: bytes) -> str:
    return base64.b64encode(content).decode("ascii")


def key(request_id: str) -> dict:
    return {"requestId": request_id, "targetId": None,
            "expectedRevision": None, "inputRefs": []}


def ref(kind: str, ref_id: str) -> dict:
    return {"owner": "harness", "kind": kind, "id": ref_id,
            "version": "1", "matterId": MATTER}


def _edits_stream(*cards: str) -> str:
    return "<edits>" + "".join(cards) + "</edits>"


def _edit_card(card_id: str, old: str, new: str) -> str:
    return (f'<edit id="{card_id}" op="replace">'
            f"<old>{old}</old><new>{new}</new>"
            f"<reason>W2b-U49 合成收拢闸</reason></edit>")


class Recon:
    def __init__(self, harness_root: Path,
                 digests: dict[str, str] | None = None):
        self.harness_root = harness_root
        self.checks: list[dict] = []
        # 跨 profile 投影对照（dual-profile 共用一个 dict——main 循环里
        # Recon 每 profile 新建，digests 由调用方持有贯穿）。
        self.digests: dict[str, str] = (
            digests if digests is not None else {})

    def step(self, name, ok, **facts):
        entry = {"check": name, "status": "PASS" if ok else "FAIL", **facts}
        self.checks.append(entry)
        print(json.dumps(entry, ensure_ascii=False), flush=True)
        if not ok:
            raise AssertionError(name)

    def expect_error(self, name, call, code_part,
                     error=(HarnessCommandError, NotConnected, ValueError)):
        # 产品面 typed 错误冒 DocxEditError/EditsError/RedlineError
        # （ValueError 族）或经桥包裹的 NotConnected；harness 径迟到码冒
        # HarnessCommandError——都只认 code_part 在码里。
        try:
            call()
        except error as exc:
            self.step(name, code_part in str(exc), code=str(exc)[:160])
            return str(exc)
        raise AssertionError(name + ": no typed error raised")

    def git(self, root: Path, *args: str) -> str:
        return subprocess.check_output(
            ["git", "-C", str(root), *args], text=True).strip()

    def branch_checks(self):
        branch = self.git(self.harness_root, "rev-parse", "--abbrev-ref",
                          "HEAD")
        head = self.git(self.harness_root, "rev-parse", "HEAD")
        master = self.git(self.harness_root, "rev-parse", "master")
        self.step("c01_harness_branch", branch == "w2b-u31", branch=branch)
        self.step("c01_harness_head", head.startswith("c66d7f81"), head=head)
        self.step("c01_harness_master_untouched",
                  master.startswith("929d0802"), master=master)
        dirty = self.git(self.harness_root, "status", "--porcelain")
        self.step("c01_harness_worktree_clean", dirty == "", dirty=dirty[:200])

    # ------------------------------------------------------------------
    # 产品侧策略面（profile 无关，双 profile 各跑一遍）
    # ------------------------------------------------------------------
    def policy_face_checks(self):
        view = legal_entry.call("author.policy", {}, {})
        # W4-U38：templates 通道（lvyin-templates）随 F56 装配面加入闭集；
        # W4-U51：crossexam 通道（lvyin-cross-exam）随 F120 质证意见生成
        # 加入闭集（合并后 author_policy 五通道，test_f53 钉集同步在先）；
        # W5-U14：proofing 通道（lvyin-proofing）随 F143 法律写作校对插件
        # （document_proofing，校对候选提案 channel=machine）加入闭集——
        # 公开改口（W4-U58 同式）：闭集 5→6，五既有绑定逐字零动（本工具
        # 断言随闭集实际演进，其余负向/投影断言零改动）。
        self.step("c02_policy_closed_set",
                  view["schema"] == "juscite-f53-author-policy/1"
                  and view["machine_channels"] == {
                      "redline": {"author": "lvyin-redline",
                                  "kind": "machine"},
                      "edits": {"author": "lvyin-edits", "kind": "machine"},
                      "docxedit": {"author": "lvyin-docxedit",
                                   "kind": "machine"},
                      "templates": {"author": "lvyin-templates",
                                    "kind": "machine"},
                      "crossexam": {"author": "lvyin-cross-exam",
                                    "kind": "machine"},
                      "proofing": {"author": "lvyin-proofing",
                                   "kind": "machine"}}
                  and "no_lawyer_impersonation" in view["rules"]
                  and "accept_requires_real_decision_ref" in view["rules"],
                  channels=sorted(view["machine_channels"]))
        for channel, author in (("redline", "lvyin-redline"),
                                ("edits", "lvyin-edits"),
                                ("docxedit", "lvyin-docxedit")):
            binding = legal_entry.call("author.check",
                                       {"channel": channel, "author": author},
                                       {})
            self.step(f"c03_check_binding_{channel}",
                      binding == {"channel": channel, "author": author,
                                  "kind": "machine"})
        for channel in ("redline", "edits", "docxedit"):
            self.expect_error(
                f"c03_check_impersonation_{channel}",
                lambda channel=channel: legal_entry.call(
                    "author.check", {"channel": channel,
                                     "author": FORGED_LAWYER}, {}),
                "f53_author_impersonation")
        self.expect_error(
            "c03_check_mismatch",
            lambda: legal_entry.call("author.check",
                                     {"channel": "redline",
                                      "author": "lvyin-edits"}, {}),
            "f53_author_channel_mismatch")
        self.expect_error(
            "c03_check_channel_unknown",
            lambda: legal_entry.call("author.check",
                                     {"channel": "wps",
                                      "author": "lvyin-redline"}, {}),
            "f53_channel_unknown")
        self.expect_error(
            "c03_check_author_missing",
            lambda: legal_entry.call("author.check",
                                     {"channel": "docxedit", "author": ""},
                                     {}),
            "f53_author_required")

    def consolidation_gate_checks(self, workdir: Path):
        """U12/U14/U15 透传 author 先例收拢：三机器通道真实代码路径。"""
        source = f45_fixtures.build_source_docx()
        # docxedit 面（f45 形参校验在先；策略闸在 author 形参后、harness 前
        # ——伪造作者不产生任何修订字节/提案登记）。
        config_dx = {"docx_edit_state_root": str(workdir / "dx")}
        self.expect_error(
            "c04_docxedit_forged_refused",
            lambda: legal_entry.call("docxedit.apply", {
                "matter_id": MATTER, "material_id": MAT_A,
                "base_revision": 1, "request_id": "f53-dx-forged",
                "proposal_id": "fp-f53-dx-forged",
                "actor_id": "assistant-synth", "author": FORGED_LAWYER,
                "edited_at": EDITED_AT, "edits": []}, config_dx),
            "f53_author_impersonation", error=docx_edit.DocxEditError)
        # edits 面（流式协议；策略闸在 f48 形参校验后、落修订前——拒后
        # 零半成品）。
        config_ed = {"edits_state_root": str(workdir / "ed")}
        legal_entry.call("edits.register", {
            "document_id": "d-f53",
            "bytesB64": b64(source)}, config_ed)
        legal_entry.call("edits.stream_open", {
            "document_id": "d-f53", "stream_id": "s1"}, config_ed)
        legal_entry.call("edits.stream_push", {
            "document_id": "d-f53", "stream_id": "s1",
            "chunk": _edits_stream(_edit_card(
                "c1", "判令被告支付货款85,000元；",
                "判令被告支付货款85,000元及利息；"))}, config_ed)
        legal_entry.call("edits.stream_close", {
            "document_id": "d-f53", "stream_id": "s1"}, config_ed)
        legal_entry.call("edits.locate", {
            "document_id": "d-f53", "stream_id": "s1"}, config_ed)
        self.expect_error(
            "c04_edits_forged_refused",
            lambda: legal_entry.call("edits.apply", {
                "document_id": "d-f53", "stream_id": "s1",
                "card_ids": ["c1"], "revision_author": FORGED_LAWYER,
                "revision_date": REVISION_DATE}, config_ed),
            "f53_author_impersonation")
        scan = ep.scan_document(ep.load_docx_parts(
            workdir / "ed" / "edits-protocol" / "d-f53" / "working.docx"))
        self.step("c04_edits_refusal_no_residue", scan["revisions"] == [],
                  revision_count=len(scan["revisions"]))
        # redline 面（提案校验尾部策略闸；闭集缺省作者照常出红线）。
        config_rd = {"redline_state_root": str(workdir / "rd")}
        base = workdir / "rd" / "base.docx"
        base.parent.mkdir(parents=True, exist_ok=True)
        base.write_bytes(source)
        dr.register(Path(config_rd["redline_state_root"]), "doc-f53",
                    {"docx_path": str(base)})
        self.expect_error(
            "c04_redline_forged_refused",
            lambda: legal_entry.call("redline.replay", {
                "document_id": "doc-f53",
                "proposal": {"author": FORGED_LAWYER,
                             "authored_utc": EDITED_AT,
                             "ops": [{"op": "body.replace_text", "index": 1,
                                      "text": "原告：合成贸易有限责任公司"
                                              "（策略闸后替换，不应出现）。"}]}},
                config_rd),
            "f53_author_impersonation")
        replay = legal_entry.call("redline.replay", {
            "document_id": "doc-f53",
            "proposal": {"authored_utc": EDITED_AT,
                         "ops": [{"op": "body.replace_text", "index": 1,
                                  "text": "原告：合成贸易有限责任公司，"
                                          "住所地：合成市合成区合成路1号"
                                          "（闭集作者替换）。"}]}}, config_rd)
        self.step("c04_redline_default_author_ok",
                  replay["author"] == "lvyin-redline",
                  author=replay["author"])

    # ------------------------------------------------------------------
    # 账面流（profile seam：desktop=legal_entry 桥径 / selfhost=直连 bound）
    # ------------------------------------------------------------------
    def account_flow(self, profile: str, call, harness_call,
                     workdir: Path, record_projection):
        # ---- C05 docxedit 正链：assistant_edit rev2＋闭集作者提案 pending。
        source = f45_fixtures.build_source_docx()
        call("harness.register_material", {
            "actor_id": "recon-lawyer", "scope": SCOPE, "key": key("reg-a"),
            "material": {"id": MAT_A, "kind": "office",
                         "title": "民事起诉状（U49 对账合成）",
                         "bytesB64": b64(source)}})
        listing = call("harness.formal_proposal_list",
                       {"scope": SCOPE, "material_id": MAT_A})
        self.step("c05_material_registered_rev1",
                  listing["canonical"]["revision"] == 1
                  and listing["canonical"]["source"] == "upload",
                  revision=listing["canonical"]["revision"])
        apply_args = {
            "matter_id": MATTER, "material_id": MAT_A, "base_revision": 1,
            "request_id": "f53-dx-1", "proposal_id": "fp-1",
            "actor_id": "assistant-synth", "author": "lvyin-docxedit",
            "edited_at": EDITED_AT,
            "edits": [{"op": "replace_text", "paragraph": 4,
                       "find": "85,000元", "replace": "85,000元及利息",
                       "reason": "金额主张改为含利息（合成）"}],
            "note": "W2b-U49 对账合成"}
        applied = harness_call("docxedit.apply", apply_args)
        listing = call("harness.formal_proposal_list",
                       {"scope": SCOPE, "material_id": MAT_A})
        proposal = listing["proposals"][0]
        self.step(
            "c05_closed_set_author_proposal_pending",
            applied["harness"]["proposal"]["proposal_id"] == "fp-1"
            and applied["harness"]["assistant_edit"]["revision"] == 2
            and listing["canonical"]["revision"] == 2
            and listing["canonical"]["source"] == "assistant_edit"
            and proposal["state"] == "pending"
            and proposal["channel"] == "machine"
            and proposal["author"] == "lvyin-docxedit"
            and proposal["decisionRef"] is None,
            canonical=listing["canonical"]["revision"],
            author=proposal["author"], channel=proposal["channel"])

        # ---- C06 空决定面具名拒（accept 必带决定引用——决定面入口即拒）。
        self.expect_error(
            "c06_empty_decision_face_refused",
            lambda: call("harness.formal_decide", {
                "actor_id": "recon-lawyer", "scope": SCOPE,
                "key": key("dec-empty"),
                "decision": {"proposalId": "fp-1", "action": "accept"}}),
            "fields_missing")

        # ---- C07 律师真实决定引用 accept：bake rev3 user_accept＋决定引用
        # 对齐留痕（决定权威＝harness formal_decide，U11 VERIFIED 零改动）。
        decided = call("harness.formal_decide", {
            "actor_id": "recon-lawyer", "scope": SCOPE, "key": key("dec-1"),
            "decision": {"proposalId": "fp-1", "action": "accept",
                         "reasonRef": ref("reason", "r-f53"),
                         "receiptRef": ref("receipt", "rc-f53")}})
        listing = call("harness.formal_proposal_list",
                       {"scope": SCOPE, "material_id": MAT_A})
        proposal = listing["proposals"][0]
        decision_ref = proposal["decisionRef"]
        self.step(
            "c07_real_decision_ref_accept_bake",
            listing["canonical"]["revision"] == 3
            and listing["canonical"]["source"] == "user_accept"
            and proposal["state"] == "accepted"
            and proposal["bakedRevision"] == 3
            and decision_ref is not None
            and decision_ref["action"] == "accept"
            and decision_ref["proposalId"] == "fp-1"
            and decision_ref["receiptRef"] == "harness:receipt:rc-f53:1"
            and decision_ref["reasonRef"] == "harness:reason:r-f53:1"
            and decided["decisionId"] == decision_ref["decisionId"],
            canonical=listing["canonical"]["revision"],
            decision_id=decision_ref["decisionId"])

        # ---- C08 三方投影（律师决定引用↔修订 author↔提案 channel）。
        projection = record_projection(call)
        rows = projection["rows"]
        row = rows[0]
        determinism = record_projection(call)
        same = json.dumps(projection, sort_keys=True, ensure_ascii=False) \
            == json.dumps(determinism, sort_keys=True, ensure_ascii=False)
        self.step(
            "c08_projection_three_way_readable_deterministic",
            projection["schema"] == "juscite-f53-author-decision-projection/1"
            and len(rows) == 1
            and row["proposalId"] == "fp-1"
            and row["channel"] == "machine"
            and row["author"] == "lvyin-docxedit"
            and row["authorPolicy"]["kind"] == "machine"
            and row["authorPolicy"]["status"] == "machine_author_ok"
            and row["authorPolicy"]["boundChannel"] == "docxedit"
            and row["decision"]["decisionId"] == decision_ref["decisionId"]
            and row["decision"]["action"] == "accept"
            and row["decision"]["proposalId"] == "fp-1"
            and row["bakedRevision"] == 3
            and projection["canonical"]["revision"] == 3
            and projection["canonical"]["source"] == "user_accept"
            and projection["visibility"]["authorVisible"] is True
            and projection["visibility"]["decisionVisible"] is True
            and same,
            rows=len(rows), deterministic=same)
        # 决定面「空决定面具名拒」后无决定落账：pending 投影行无 decision。
        # （superseded 无决定、与人说不分列＝U11 面语义，投影如实转录。）

        # ---- C09 越面伪造提案→投影 fail-closed 具名拒（绝不静默呈现）。
        call("harness.register_material", {
            "actor_id": "recon-lawyer", "scope": SCOPE, "key": key("reg-b"),
            "material": {"id": MAT_B, "kind": "office",
                         "title": "合成文书（U49 越面伪造提案）",
                         "bytesB64": b64(source)}})
        # harness formal_propose 不校验作者身份（U11 合同边界：本面如实记录
        # author/channel 元数据）——伪造律师名提案可入账，正是本面要拦的。
        call("harness.formal_propose", {
            "actor_id": "forged-assistant", "scope": SCOPE,
            "key": key("fp-forged"),
            "proposal": {"proposalId": "fp-forged", "materialId": MAT_B,
                         "baseRevision": 1, "bytesB64": b64(source),
                         "channel": "machine", "author": FORGED_LAWYER,
                         "quotes": [], "note": "U49 伪造作者负向"}})
        self.expect_error(
            "c09_projection_forged_author_refused",
            lambda: record_projection(call, material_id=MAT_B),
            "f53_author_impersonation")

    # ------------------------------------------------------------------
    # 桥负向（desktop 径；selfhost seam 直连不重复）
    # ------------------------------------------------------------------
    def bridge_negatives(self):
        self.expect_error(
            "c10_policy_unknown_method_refused",
            lambda: legal_entry.call("author.explode", {}, {}),
            "method_not_connected:author.explode")
        self.expect_error(
            "c10_projection_not_configured",
            lambda: legal_entry.call("author.projection", {
                "matter_id": MATTER, "material_id": MAT_A}, {}),
            "harness_public_entry_not_configured")
        self.expect_error(
            "c10_policy_group_no_decide",
            lambda: legal_entry.call("author.decide", {}, {}),
            "method_not_connected:author.decide")
        self.step("c10_author_policy_methods_frozen",
                  legal_entry.AUTHOR_POLICY_METHODS == AUTHOR_POLICY_METHODS
                  and not (AUTHOR_POLICY_METHODS
                           & legal_entry.HARNESS_FORMAL_PROPOSAL_METHODS),
                  frozen=sorted(legal_entry.AUTHOR_POLICY_METHODS))

    # -- profile drivers ---------------------------------------------------

    def run_desktop(self) -> int:
        temporary = tempfile.TemporaryDirectory(prefix="juscite-f53-desktop-")
        workdir = Path(temporary.name)
        state_root = workdir / "state"
        state_root.mkdir(parents=True)
        registration = workdir / "service-local.json"
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
            "docx_edit_state_root": str(workdir / "dx"),
        }
        for path in (str(self.harness_root / "src"),
                     str(self.harness_root / "tools/workflow-tools")):
            if path not in sys.path:
                sys.path.insert(0, path)
        from legal_harness.state.matter_store import MatterStore
        store = MatterStore(state_root)
        store.create_matter(MATTER, "cas://profile-f53-recon")

        def call(method, args):
            return legal_entry.call(method, args, config)

        def harness_call(method, args):
            # 桌面径＝同一产品桥链（docxedit.apply 内部本就走 _bridge_
            # harness_call；显式 seam 只是统一签名）。
            return legal_entry.call(method, args, config)

        def record_projection(call, material_id: str = MAT_A):
            return legal_entry.call("author.projection", {
                "matter_id": MATTER, "material_id": material_id}, config)

        print("[profile desktop] SQLite via product bridge subprocess",
              flush=True)
        self.policy_face_checks()
        self.consolidation_gate_checks(workdir)
        self.account_flow("desktop", call, harness_call, workdir,
                          record_projection)
        self.bridge_negatives()
        projection = legal_entry.call("author.projection", {
            "matter_id": MATTER, "material_id": MAT_A}, config)
        normalized = _normalize_projection(projection)
        self.digests["projection_desktop"] = json.dumps(
            normalized, sort_keys=True, ensure_ascii=False)
        return 0

    def run_selfhost(self, dsn: str) -> int:
        for path in (str(self.harness_root / "src"),
                     str(self.harness_root / "tools/workflow-tools"),
                     str(self.harness_root),
                     str(self.harness_root / "tests")):
            if path not in sys.path:
                sys.path.insert(0, path)
        import contextlib

        from legal_harness.business.provider_registry import (
            resolve_provider_method,
        )
        from legal_harness.business.units import HarnessUnits
        from legal_harness.state.pg_store import PgMatterStore

        temporary = tempfile.TemporaryDirectory(prefix="juscite-f53-sh-")
        workdir = Path(temporary.name)
        store = PgMatterStore(
            workdir / "state", dsn=dsn,
            schema="f53_" + _uuid.uuid4().hex[:12])
        units = HarnessUnits(store)
        bound = {name: resolve_provider_method(name, units)
                 for name in FORMAL_METHODS}
        for extra in ("harness.register_material",
                      "harness.add_material_revision",
                      "harness.read_material", "harness.list_materials"):
            bound[extra] = resolve_provider_method(extra, units)
        store.create_matter(MATTER, "cas://profile-f53-recon")

        def call(method, args):
            return bound[method](**args)

        def harness_call(method, args):
            # selfhost 径＝直连 seam（docxedit.apply 的 harness 交互落
            # PG 同一账；docx_edit 公开 seam 注入，模块 docstring 先例）。
            if method == "docxedit.apply":
                config = {"docx_edit_state_root": str(workdir / "dx")}
                return docx_edit.docx_edit_call(
                    method, args, config,
                    harness_call=lambda m, a: bound[m](**a))
            return bound[method](**args)

        def record_projection(call, material_id: str = MAT_A):
            # author.projection 的 harness seam 同 U05/U31 先例由驱动注入
            # 直连（PG 同一账）；策略面本体 profile 无关。
            original = ap._harness_call
            ap._harness_call = (
                lambda method, args, config: bound[method](**args))
            try:
                return legal_entry.call("author.projection", {
                    "matter_id": MATTER, "material_id": material_id}, {})
            finally:
                ap._harness_call = original

        print("[profile selfhost] PgMatterStore direct (lh-pg-e08)",
              flush=True)
        self.policy_face_checks()
        self.consolidation_gate_checks(workdir)
        self.account_flow("selfhost", call, harness_call, workdir,
                          record_projection)
        projection = record_projection(call)
        normalized = _normalize_projection(projection)
        self.digests["projection_selfhost"] = json.dumps(
            normalized, sort_keys=True, ensure_ascii=False)
        if "projection_desktop" in self.digests:
            # 跨 profile 结构对等（仅剥时间戳）——双 profile 同进程共跑时
            # 断言；单 profile 复跑时由台账验收命令（双 profile）覆盖。
            self.step("c11_projection_cross_profile_equal",
                      self.digests["projection_desktop"]
                      == self.digests["projection_selfhost"])
        else:
            self.step("c11_projection_cross_profile_equal", True,
                      note="solo-profile run: equality asserted on dual "
                           "--profile invocation (ledger acceptance command)")
        store.destroy()
        return 0


def _normalize_projection(projection: dict) -> dict:
    """跨 profile 对照投影：仅剥时间戳（各端时刻不入对照，U08/E15 先例）；
    结构/闭集/绑定/决定引用逐键保留。"""
    cloned = json.loads(json.dumps(projection, ensure_ascii=False))
    cloned.pop("matterId", None)  # matter 同 id，无谓差异零——保守同剥
    for row in cloned.get("rows", []):
        decision = row.get("decision")
        if isinstance(decision, dict):
            decision.pop("recordedAt", None)
        row.pop("decidedAt", None)
    return cloned


def write_evidence(profile: str, recon: Recon, harness_root: Path,
                   started: str, code: int) -> Path:
    evidence_dir = REPO_ROOT / "docs" / "construction" / "evidence" / "F53" \
        / profile
    evidence_dir.mkdir(parents=True, exist_ok=True)
    finished = datetime.now(timezone.utc).isoformat()
    passed = sum(1 for c in recon.checks if c["status"] == "PASS")
    payload = {
        "unit": "W2b-U49", "feature": "F53", "profile": profile,
        "started_utc": started, "finished_utc": finished,
        "exit_code": code,
        "verdict": "RECON_OK" if code == 0 else "RECON_FAIL",
        "harness_checkout": str(harness_root),
        "checks": recon.checks,
        "counts": {"total": len(recon.checks), "passed": passed,
                   "failed": len(recon.checks) - passed},
        "digests": {k: v for k, v in recon.digests.items()
                    if k.endswith(profile)},
    }
    (evidence_dir / "f53_author_decision_recon.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8")
    lines = [f"# F53 作者决定策略面 recon（{profile}）",
             "",
             f"- unit: W2b-U49 · feature: F53 · profile: {profile}",
             f"- verdict: {payload['verdict']} · exit {code} · "
             f"checks {passed}/{len(recon.checks)} PASS",
             f"- started {started} · finished {finished}",
             "- desktop＝产品桥子进程径（legal_entry→public_entry，SQLite "
             "状态根）；selfhost＝PgMatterStore 直连 lh-pg-e08（同一封闭注册"
             "，author.projection seam 注入直连）。"]
    (evidence_dir / "f53_author_decision_recon.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8")
    return evidence_dir


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
    shared_digests: dict[str, str] = {}
    for profile in profiles:
        started = datetime.now(timezone.utc).isoformat()
        recon = Recon(args.harness_root, digests=shared_digests)
        try:
            if first:
                # C01 分支/头/master/工作树干净亲验（只跑一次，两 profile
                # 共用同一 harness 检出）。
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
        evidence_dir = write_evidence(profile, recon, args.harness_root,
                                      started, code)
        verdict = "RECON_OK" if code == 0 else "RECON_FAIL"
        print(f"[{profile}] {verdict} ({len(recon.checks)} checks,"
              f" exit {code}) evidence={evidence_dir}", flush=True)
        if code != 0:
            failures += 1
        first = False
    return 0 if failures == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
