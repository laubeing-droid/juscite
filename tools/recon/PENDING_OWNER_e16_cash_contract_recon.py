"""E16 款源/转移/退款/分配/余额对账（W2b-U51）——双 profile（desktop/selfhost）。

对账对象：
  harness 分支 w2b-u51（基施工链头 w2b-u40@37b266e7＝…→w2b-u31(F82)→
  w2b-u40(F92) 同链接力）的 public_entry --cashcontract-json 封闭径；
  JC 分支 w2b-u51（基 w2b-u27@ac6209b＝main 8f762d3→E21(W2b-U19)→
  E19(W2b-U27) 同链接力）的 jc-cash-contract/1 确定性计算面（经 P01
  JCClient 钉定面真跑，jc_import_path 指向本单 JC worktree）。
desktop profile 与产品桥（legal_entry → 子进程 public_entry）完全同一条
链（SQLite 状态根）；selfhost profile＝PgMatterStore 直连 lh-pg-e08
（resolve_provider_method 同一封闭注册）。

实跑覆盖（05 §9.5 合成验收向量＋07 E16 acceptance，04§7/08§3 规格）：
  名义 120000 → 三款源 A 30000/Q 50000（法院中转·清偿效果待核）/
  B 100000（独立不含 Q）→ JC 余额向量逐阶段（source_total 180000/
  gross 130000→净 120000（真实退款 10000，历史 gross 不重写）→Q 划转
  后 gross 180000/净 170000/法院持有 0＝net170k 向量；source_total 恒
  180000 不得 230000）→ 每事件钉 JC 计算回执 ref（owner=jc sha256，
  digest 亲验与 JC 返回相等＝互钉）→ 分配钉 JC 分配回执（修订顶替生
  效集不重复分）。负向全具名：同源双计（harness realityKey UNIQUE＋JC
  同检双拒）／180k 混计 230k（组成不符＋转移造第二款源 JC typed 拒）／
  净额向量缺失（角色字段缺失拒＋向量恒十键）／浮点入参（harness+JC
  双拒）／塞 record_payment（ref_version_unavailable）／减免改判 kind
  拒／转移超持有／伪造 JC ref／分配超额/stale revision／桥负向（未配
  置 NOT_CONNECTED／未知方法 method_not_connected／方法组冻结）。

用法：
  python -X utf8 tools/recon/PENDING_OWNER_e16_cash_contract_recon.py \
      --profile desktop --profile selfhost

退出码：0 = 全部 profile RECON_OK；2 = RECON_FAIL；3 = 环境缺失。
证据：docs/construction/evidence/E16/<profile>/ JSON＋MD。
"""
from __future__ import annotations

import argparse
import contextlib
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
from legal_entry import HarnessCommandError, JCMethodFailure, NotConnected  # noqa: E402

DEFAULT_HARNESS_ROOT = Path(
    r"D:\Codex\1.法律工作区\legal-harness工作区\legal-harness-repo"
    r"\.local\worktrees\w2b-u51")
DEFAULT_JC_ROOT = Path(
    r"D:\Codex\1.法律工作区\juris-calculus工作区\juris-calculus"
    r"\.local\worktrees\w2b-u51")

MATTER = "m-e16-recon"
SCOPE = {"kind": "matter", "matterId": MATTER}

# lh-pg-e08 容器（E08 拓扑）：仅回环端口、合成专用凭据；可用 --pg-dsn 覆写。
DEFAULT_PG_DSN = "postgresql://lh_app:e08-synth-only@127.0.0.1:55432/legal_harness"

E16_HARNESS_METHODS = frozenset({
    "harness.cash_entitlement_register", "harness.cash_source_register",
    "harness.cash_transfer_record", "harness.cash_outflow_record",
    "harness.cash_allocation_record", "harness.cash_balance_read",
})
E16_JC_METHODS = frozenset({"cash.balance", "cash.allocate"})

# 05 §9.5 合成向量（整分）。名义 120000 元；A 30000、Q 50000（法院）、
# B 100000（独立不含 Q）；真实退款 10000；Q 划转 50000。
ENT_AMOUNT = 12_000_000
A_AMOUNT = 3_000_000
Q_AMOUNT = 5_000_000
B_AMOUNT = 10_000_000
REFUND_AMOUNT = 1_000_000

# create_local_client 需至少一个规则根（JC 不随附规则库）；本对账消费
# cash 面（零规则消费），入最小合成包以满足构造（e21/e19 recon 同纪律）。
RULE_PACK = {
    "schema_version": "jc/local-pack/1.0",
    "pack_version": "1.0.0",
    "sources": [{
        "source_id": "acceptance-statute", "jurisdiction": "TEST",
        "authority_tier": "official_first_party",
        "issuer": "Acceptance Test Authority", "title": "acceptance-statute",
        "publication_time": "2020-01-01T00:00:00Z",
        "effective_from": "2020-01-01T00:00:00Z",
        "retrieved_at": "2026-08-01T00:00:00Z",
        "locator": {"kind": "uri", "value": "example.invalid/acceptance",
                    "page": None, "span_start": None, "span_end": None},
        "content": ("SYNTHETIC acceptance rule text for engineering "
                    "verification only; no legal effect."),
        "structure_sections": ["ART-1"],
    }],
    "rules": [
        {"rule_id": "acc-base", "jurisdiction": "TEST",
         "governing_law": "acceptance-statute",
         "source_id": "acceptance-statute", "modality": "OBLIGATION",
         "premises": [{"fact_key": "acc.contract", "required": True}],
         "conclusion": {"value": "applies"},
         "effective_from": "2020-01-01T00:00:00Z"},
    ],
}


def key(request_id: str) -> dict:
    return {"requestId": request_id, "targetId": None,
            "expectedRevision": None, "inputRefs": []}


def href(kind: str, ref_id: str) -> dict:
    return {"owner": "harness", "kind": kind, "id": ref_id,
            "version": "1", "matterId": MATTER}


def synth_entitlement() -> dict:
    return {
        "entitlementId": "ent-1",
        "nominalRef": href("judgment", "（2026）合01民初1号"),
        "amountMinor": ENT_AMOUNT, "currency": "CNY",
        "obligor": "被执行人甲/乙（合成）", "creditor": "客户（合成）",
        "effectiveEvidenceRefs": [href("document", "doc-effective-1")],
        "note": "生效名义债权（全合成）",
    }


def synth_source(source_id: str, amount: int, holder: str,
                 reality_key: str, **overrides) -> dict:
    source = {
        "sourcePaymentId": source_id, "entitlementId": "ent-1",
        "payer": "法院执行款专户" if holder == "court" else "被执行人（合成）",
        "payee": "法院代管" if holder == "court" else "客户（合成）",
        "amountMinor": amount, "currency": "CNY",
        "realityKey": reality_key,
        "voucherRefs": [href("voucher", f"v-{source_id}")],
        "occurredAt": "2026-03-01", "verifiedAt": "2026-03-02",
        "confirmDecisionRef": href("decision", f"dec-{source_id}"),
        "recoveryPurpose": "本金受偿（合成）", "holder": holder,
        "legalEffectStatus": "declared", "note": "全合成款源",
    }
    source.update(overrides)
    return source


def synth_q_source() -> dict:
    return synth_source("src-Q", Q_AMOUNT, "court", "court-transfer-Q-001",
                        legalEffectStatus="pending_review",
                        recoveryPurpose="法院中转款（清偿效果待核）",
                        occurredAt="2026-03-05")


def cash_events(sources, transfers=None, outflows=None, allocations=None):
    return {
        "entitlements": [{
            "entitlementId": "ent-1", "nominalRef": "（2026）合01民初1号",
            "amountMinor": ENT_AMOUNT, "currency": "CNY"}],
        "sources": sources,
        "transfers": transfers or [],
        "outflows": outflows or [],
        "allocations": allocations or [],
    }


class Recon:
    def __init__(self, harness_root: Path, jc_root: Path):
        self.harness_root = harness_root
        self.jc_root = jc_root
        self.checks: list[dict] = []

    def step(self, name, ok, **facts):
        entry = {"check": name, "status": "PASS" if ok else "FAIL", **facts}
        self.checks.append(entry)
        print(json.dumps(entry, ensure_ascii=False), flush=True)
        if not ok:
            raise AssertionError(name)

    def expect_error(self, name, call, code_part,
                     error=(HarnessCommandError, ValueError, JCMethodFailure)):
        # desktop 桥链合同码冒 HarnessCommandError／JC typed 拒冒
        # JCMethodFailure；selfhost 直连公开面冒 UnitsError（ValueError
        # 子类）——三者都只认 code_part 在码里。
        try:
            call()
        except error as exc:
            self.step(name, code_part in str(exc), code=str(exc)[:220])
            return str(exc)
        raise AssertionError(name + ": no typed error raised")

    def git(self, root: Path, *args: str) -> str:
        return subprocess.check_output(
            ["git", "-C", str(root), *args], text=True).strip()

    def branch_checks(self):
        # harness 侧：分支/基/主检出/工作树干净。
        h_branch = self.git(self.harness_root, "rev-parse", "--abbrev-ref", "HEAD")
        h_base = self.git(self.harness_root, "merge-base", "HEAD", "w2b-u40")
        h_master = self.git(self.harness_root, "rev-parse", "master")
        self.step("c01_harness_branch", h_branch == "w2b-u51", branch=h_branch)
        self.step("c01_harness_base_on_w2b_u40", h_base.startswith("37b266e7"),
                  base=h_base)
        self.step("c01_harness_master_untouched",
                  h_master.startswith("929d0802"), master=h_master[:12])
        h_dirty = self.git(self.harness_root, "status", "--porcelain")
        self.step("c01_harness_worktree_clean", h_dirty == "",
                  dirty=h_dirty[:200])
        # JC 侧：分支/基/主检出/工作树干净。
        j_branch = self.git(self.jc_root, "rev-parse", "--abbrev-ref", "HEAD")
        j_base = self.git(self.jc_root, "merge-base", "HEAD", "w2b-u27")
        j_main = self.git(self.jc_root, "rev-parse", "main")
        self.step("c01_jc_branch", j_branch == "w2b-u51", branch=j_branch)
        self.step("c01_jc_base_on_w2b_u27", j_base.startswith("ac6209b"),
                  base=j_base)
        self.step("c01_jc_main_untouched", j_main.startswith("8f762d3"),
                  main=j_main[:12])
        j_dirty = self.git(self.jc_root, "status", "--porcelain")
        self.step("c01_jc_worktree_clean", j_dirty == "", dirty=j_dirty[:200])

    # ------------------------------------------------------------------
    # C02 起：call_harness(method, args)＝harness 被测链；
    # call_jc(method, args)＝P01 钉定面真算；query(sql, params)＝直读库。
    # ------------------------------------------------------------------
    def common_flow(self, profile: str, call_harness, call_jc, query,
                    raw_record_payment):
        # ---- C02 名义登记（主张金额层，与款源/到账分开）。
        registered = call_harness("harness.cash_entitlement_register", {
            "actor_id": "recon-assistant", "scope": SCOPE,
            "key": key("ent-1"), "entitlement": synth_entitlement()})
        self.step("c02_entitlement_registered",
                  registered["entitlement"]["amountMinor"] == ENT_AMOUNT
                  and registered["entitlement"]["nominalRef"]["id"]
                  == "（2026）合01民初1号",
                  amount=registered["entitlement"]["amountMinor"])

        # ---- C03 三款源：A/B 落客户、Q 落法院（三持有列不混）；JC 余额
        # 阶段三向量（source_total 180000/gross 130000/法院持有 50000）。
        sources = [synth_source("src-A", A_AMOUNT, "client", "bank-tx-A-001"),
                   synth_q_source(),
                   synth_source("src-B", B_AMOUNT, "client", "bank-tx-B-001",
                                occurredAt="2026-03-10")]
        for index, source in enumerate(sources, 1):
            call_harness("harness.cash_source_register", {
                "actor_id": "recon-assistant", "scope": SCOPE,
                "key": key(f"src-{index}"), "source": source})
        jc_stage3 = call_jc("cash.balance", {
            "matterId": MATTER,
            "events": cash_events(sources)})
        vector = jc_stage3["net_vector"]
        self.step("c03_stage3_vector",
                  vector["source_total_minor"] == 18_000_000
                  and vector["client_gross_minor"] == 13_000_000
                  and vector["court_held_minor"] == Q_AMOUNT
                  and vector["client_net_minor"] == 13_000_000
                  and vector["over_entitlement_minor"] == 6_000_000,
                  vector={k: vector[k] for k in sorted(vector)})
        stage3_ref = jc_stage3["cashBalanceRef"]

        # ---- C04 真实退款 10000（钉 JC 回执）：历史 gross 不重写、
        # net=120000；减免/改判 kind 具名拒。
        call_harness("harness.cash_outflow_record", {
            "actor_id": "recon-assistant", "scope": SCOPE,
            "key": key("out-1"),
            "outflow": {"outflowId": "out-1", "kind": "refund",
                        "linkedSourcePaymentId": "src-B",
                        "amountMinor": REFUND_AMOUNT, "currency": "CNY",
                        "payer": "客户（合成）", "payee": "被执行人乙",
                        "voucherRefs": [href("voucher", "v-refund-1")],
                        "occurredAt": "2026-03-15",
                        "jcBalanceRef": stage3_ref,
                        "note": "有真凭证返还10000（合成）"}})
        self.expect_error(
            "c04_remission_kind_refused",
            lambda: call_harness("harness.cash_outflow_record", {
                "actor_id": "recon-assistant", "scope": SCOPE,
                "key": key("out-remission"),
                "outflow": {"outflowId": "out-rem", "kind": "remission",
                            "amountMinor": REFUND_AMOUNT, "currency": "CNY",
                            "voucherRefs": [href("voucher", "v-rem")],
                            "occurredAt": "2026-03-15",
                            "jcBalanceRef": stage3_ref}}),
            "cash_outflow_kind_invalid")
        jc_stage4 = call_jc("cash.balance", {
            "matterId": MATTER,
            "events": cash_events(sources, outflows=[{
                "outflowId": "out-1", "kind": "refund",
                "amountMinor": REFUND_AMOUNT,
                "occurredAt": "2026-03-15"}])})
        vector = jc_stage4["net_vector"]
        self.step("c04_refund_keeps_gross",
                  vector["source_total_minor"] == 18_000_000
                  and vector["client_gross_minor"] == 13_000_000
                  and vector["outflow_total_minor"] == REFUND_AMOUNT
                  and vector["client_net_minor"] == 12_000_000
                  and vector["court_held_minor"] == Q_AMOUNT,
                  vector={k: vector[k] for k in ("source_total_minor",
                                                "client_net_minor")})
        stage4_ref = jc_stage4["cashBalanceRef"]

        # ---- C05 Q 划转客户（钉 JC 回执）：只动持有列——source_total 恒
        # 180000 不得 230000；gross 180000/净 170000/法院持有 0＝net170k
        # 向量；转移造第二款源 JC typed 拒。
        call_harness("harness.cash_transfer_record", {
            "actor_id": "recon-assistant", "scope": SCOPE,
            "key": key("tr-1"),
            "transfer": {"transferId": "tr-Q-1",
                         "sourcePaymentId": "src-Q",
                         "fromHolder": "court", "toHolder": "client",
                         "amountMinor": Q_AMOUNT, "currency": "CNY",
                         "voucherRefs": [href("voucher", "v-q-drawdown")],
                         "occurredAt": "2026-03-20",
                         "decisionRef": href("decision", "dec-q-drawdown"),
                         "jcBalanceRef": stage4_ref,
                         "note": "原Q实际划给客户（合成划转凭证）"}})
        self.expect_error(
            "c05_transfer_minting_second_source_jc_refused",
            lambda: call_jc("cash.balance", {
                "matterId": MATTER,
                "events": cash_events(sources, transfers=[{
                    "transferId": "tr-ghost", "sourcePaymentId": "src-ghost",
                    "fromHolder": "court", "toHolder": "client",
                    "amountMinor": Q_AMOUNT,
                    "occurredAt": "2026-03-20"}])}),
            "cash_transfer_source_unknown")
        jc_stage5 = call_jc("cash.balance", {
            "matterId": MATTER,
            "events": cash_events(sources, transfers=[{
                "transferId": "tr-Q-1", "sourcePaymentId": "src-Q",
                "fromHolder": "court", "toHolder": "client",
                "amountMinor": Q_AMOUNT, "occurredAt": "2026-03-20"}],
                outflows=[{"outflowId": "out-1", "kind": "refund",
                           "amountMinor": REFUND_AMOUNT,
                           "occurredAt": "2026-03-15"}])})
        vector = jc_stage5["net_vector"]
        self.step("c05_stage5_vector_170k_source_total_unchanged",
                  vector["source_total_minor"] == 18_000_000
                  and vector["client_gross_minor"] == 18_000_000
                  and vector["client_net_minor"] == 17_000_000
                  and vector["court_held_minor"] == 0
                  and vector["outflow_total_minor"] == REFUND_AMOUNT
                  and jc_stage5["columns"]["sources_minor"] == 18_000_000
                  and jc_stage5["columns"]["transfers_minor"] == Q_AMOUNT,
                  net=vector["client_net_minor"],
                  source_total=vector["source_total_minor"])
        stage5_ref = jc_stage5["cashBalanceRef"]
        # 重导 Q 划转凭证幂等（JC 面）：同 id 同内容折叠，向量逐字节同。
        jc_stage5_replay = call_jc("cash.balance", {
            "matterId": MATTER,
            "events": cash_events(sources, transfers=[{
                "transferId": "tr-Q-1", "sourcePaymentId": "src-Q",
                "fromHolder": "court", "toHolder": "client",
                "amountMinor": Q_AMOUNT, "occurredAt": "2026-03-20"}],
                outflows=[{"outflowId": "out-1", "kind": "refund",
                           "amountMinor": REFUND_AMOUNT,
                           "occurredAt": "2026-03-15"}])})
        self.step("c05_replay_idempotent_same_digest",
                  jc_stage5_replay["cashBalanceRef"]["digest"]
                  == stage5_ref["digest"],
                  digest=stage5_ref["digest"][:24])

        # ---- C06 分配：先 JC cash.allocate 真算拿回执，再入账（钉回执）。
        allocation_plan = {
            "sources": sources,
            "allocations": [{
                "allocationId": "al-1", "revision": 1,
                "sourcePaymentId": "src-A", "projectId": "本金",
                "amountMinor": A_AMOUNT, "currency": "CNY",
                "ruleBasis": {"name": "合成分配规则（到账顺序全额冲抵本金）",
                              "authorityRefs": [href("decision", "rule-1")],
                              "selection": "到账顺序（合成声明）"},
                "legalEffectScope": {
                    "declaredScope": "本金清偿效果以生效名义核定为准（合成声明）"},
            }]}
        jc_allocation = call_jc("cash.allocate", {
            "matterId": MATTER, "request": allocation_plan})
        self.step("c06_jc_allocation_sheet",
                  jc_allocation["perSourceView"]["src-A"]["allocatedMinor"]
                  == A_AMOUNT
                  and jc_allocation["cashAllocationRef"]["owner"] == "jc",
                  allocated=A_AMOUNT)
        call_harness("harness.cash_allocation_record", {
            "actor_id": "recon-assistant", "scope": SCOPE,
            "key": key("al-1"),
            "allocation": {"allocationId": "al-1", "revision": 1,
                           "sourcePaymentId": "src-A", "projectId": "本金",
                           "amountMinor": A_AMOUNT, "currency": "CNY",
                           "ruleBasis": {"name": "合成分配规则（到账顺序"
                                         "全额冲抵本金）",
                                         "authorityRefs": [href("decision",
                                                                "rule-1")]},
                           "legalEffectScope": {
                               "declaredScope": "本金清偿效果以生效名义核定"
                                                "为准（合成声明）"},
                           "jcAllocationRef": jc_allocation["cashAllocationRef"],
                           "note": "全合成分配行"}})
        # 修订顶替：rev2 生效集不重复分（2500000 取代 3000000）。
        revised_plan = {"sources": sources, "allocations": [{
            "allocationId": "al-1", "revision": 2,
            "sourcePaymentId": "src-A", "projectId": "本金",
            "amountMinor": 2_500_000, "currency": "CNY",
            "ruleBasis": {"name": "合成分配规则（到账顺序全额冲抵本金）",
                          "authorityRefs": [href("decision", "rule-1")]}}]}
        jc_revised = call_jc("cash.allocate", {
            "matterId": MATTER, "request": revised_plan})
        call_harness("harness.cash_allocation_record", {
            "actor_id": "recon-assistant", "scope": SCOPE,
            "key": key("al-1-r2"),
            "allocation": {"allocationId": "al-1", "revision": 2,
                           "sourcePaymentId": "src-A", "projectId": "本金",
                           "amountMinor": 2_500_000, "currency": "CNY",
                           "ruleBasis": {"name": "合成分配规则（到账顺序"
                                         "全额冲抵本金）",
                                         "authorityRefs": [href("decision",
                                                                "rule-1")]},
                           "jcAllocationRef": jc_revised["cashAllocationRef"]}})

        # ---- C07 harness 余额投影（终态）：向量与 JC 面逐键一致＋JC 回
        # 执互钉亲验（分配行 digest==JC 返回 digest）＋待核名单照记。
        balance = call_harness("harness.cash_balance_read", {"scope": SCOPE})
        nv = balance["netVector"]
        pinned_allocation = balance["allocations"]["rows"][0]
        self.step("c07_harness_vector_matches_jc",
                  nv["sourceTotalMinor"] == 18_000_000
                  and nv["clientGrossMinor"] == 18_000_000
                  and nv["outflowTotalMinor"] == REFUND_AMOUNT
                  and nv["clientNetMinor"] == 17_000_000
                  and nv["courtHeldMinor"] == 0
                  and nv["entitlementTotalMinor"] == ENT_AMOUNT
                  and nv["overEntitlementMinor"] == 6_000_000
                  and nv["allocatedTotalMinor"] == 2_500_000
                  and nv["unallocatedTotalMinor"] == 15_500_000
                  and balance["columns"] == {
                      "sourcesMinor": 18_000_000,
                      "transfersMinor": Q_AMOUNT,
                      "outflowsMinor": REFUND_AMOUNT,
                      "allocationsMinor": 2_500_000},
                  net=nv["clientNetMinor"])
        self.step("c07_jc_receipt_pinned_digest_equal",
                  pinned_allocation["jcAllocationRef"]["digest"]
                  == jc_revised["cashAllocationRef"]["digest"]
                  and pinned_allocation["jcAllocationRef"]["owner"] == "jc",
                  digest=pinned_allocation["jcAllocationRef"]["digest"][:24])
        self.step("c07_legal_effect_pending_review_kept",
                  balance["legalEffectPendingReview"] == ["src-Q"]
                  and balance["sourceViews"]["src-Q"]["legalEffectStatus"]
                  == "pending_review",
                  pending=balance["legalEffectPendingReview"])

        # ---- C08 负向四件套（具名拒）：
        # ①180k 混计 230k：组成不符（本金 180k+利息 50k 塞进 180k 款源）。
        mixed = synth_source("src-B", 18_000_000, "client", "k-mixed",
                             composition=[
                                 {"partKind": "principal",
                                  "amountMinor": 18_000_000},
                                 {"partKind": "interest",
                                  "amountMinor": 5_000_000}])
        self.expect_error(
            "c08_composition_mixing_230k_refused",
            lambda: call_harness("harness.cash_source_register", {
                "actor_id": "recon-assistant", "scope": SCOPE,
                "key": key("src-mixed"), "source": mixed}),
            "cash_composition_mismatch")
        # ②同源双计：同 realityKey 第二路来账（harness UNIQUE＋JC 同检）。
        self.expect_error(
            "c08_same_source_duplicate_harness_refused",
            lambda: call_harness("harness.cash_source_register", {
                "actor_id": "recon-assistant", "scope": SCOPE,
                "key": key("src-dup"),
                "source": synth_source("src-Q-transfer", Q_AMOUNT,
                                       "client", "court-transfer-Q-001")}),
            "cash_source_reality_duplicate")
        self.expect_error(
            "c08_same_source_duplicate_jc_refused",
            lambda: call_jc("cash.balance", {
                "matterId": MATTER,
                "events": cash_events(sources + [synth_source(
                    "src-Q-transfer", Q_AMOUNT, "client",
                    "court-transfer-Q-001")])}),
            "cash_source_reality_duplicate")
        # ③净额向量缺失：款源缺 holder（列归属）→ JC typed 拒；harness
        # 投影结构性恒带十键向量（无只回总数形态）。
        incomplete = synth_source("src-X", 1, "client", "k-x")
        del incomplete["holder"]
        self.expect_error(
            "c08_vector_role_field_missing_refused",
            lambda: call_jc("cash.balance", {
                "matterId": MATTER, "events": cash_events([incomplete])}),
            "cash_field_missing")
        self.step("c08_net_vector_always_present",
                  set(nv) == {"sourceTotalMinor", "clientGrossMinor",
                              "outflowTotalMinor", "clientNetMinor",
                              "courtHeldMinor", "otherHeldMinor",
                              "allocatedTotalMinor", "unallocatedTotalMinor",
                              "entitlementTotalMinor",
                              "overEntitlementMinor"},
                  keys=len(nv))
        # ④浮点入参：harness 与 JC 双具名拒。
        float_source = synth_source("src-f", 0, "client", "k-f")
        float_source["amountMinor"] = 30000.0
        self.expect_error(
            "c08_float_input_harness_refused",
            lambda: call_harness("harness.cash_source_register", {
                "actor_id": "recon-assistant", "scope": SCOPE,
                "key": key("src-f"), "source": float_source}),
            "cash_amount_not_minor_units")
        jc_float = synth_source("src-A", 0, "client", "bank-tx-A-001")
        jc_float["amountMinor"] = 30000.5
        self.expect_error(
            "c08_float_input_jc_refused",
            lambda: call_jc("cash.balance", {
                "matterId": MATTER, "events": cash_events([jc_float])}),
            "cash_amount_not_minor_units")

        # ---- C09 更多具名拒：转移超持有／无 JC 回执／伪造 JC ref／分配
        # 超额／stale revision／塞 record_payment（结构性分账反面）。
        self.expect_error(
            "c09_transfer_exceeds_held_refused",
            lambda: call_harness("harness.cash_transfer_record", {
                "actor_id": "recon-assistant", "scope": SCOPE,
                "key": key("tr-over"),
                "transfer": {"transferId": "tr-over",
                             "sourcePaymentId": "src-Q",
                             "fromHolder": "court", "toHolder": "client",
                             "amountMinor": 1, "currency": "CNY",
                             "voucherRefs": [href("voucher", "v-over")],
                             "occurredAt": "2026-03-21",
                             "jcBalanceRef": stage5_ref}}),
            "cash_transfer_exceeds_held")
        no_jc = {"transferId": "tr-nojc", "sourcePaymentId": "src-Q",
                 "fromHolder": "court", "toHolder": "client",
                 "amountMinor": 1, "currency": "CNY",
                 "voucherRefs": [href("voucher", "v-nojc")],
                 "occurredAt": "2026-03-21"}
        self.expect_error(
            "c09_transfer_without_jc_receipt_refused",
            lambda: call_harness("harness.cash_transfer_record", {
                "actor_id": "recon-assistant", "scope": SCOPE,
                "key": key("tr-nojc"), "transfer": no_jc}),
            "fields_missing")
        fabricated = {"transferId": "tr-fab", "sourcePaymentId": "src-Q",
                      "fromHolder": "court", "toHolder": "client",
                      "amountMinor": 1, "currency": "CNY",
                      "voucherRefs": [href("voucher", "v-fab")],
                      "occurredAt": "2026-03-21",
                      "jcBalanceRef": {"owner": "harness", "kind": "x",
                                       "id": "y", "version": "1",
                                       "digest": "sha256:abc"}}
        self.expect_error(
            "c09_fabricated_jc_ref_refused",
            lambda: call_harness("harness.cash_transfer_record", {
                "actor_id": "recon-assistant", "scope": SCOPE,
                "key": key("tr-fab"), "transfer": fabricated}),
            "jc_ref_invalid")
        self.expect_error(
            "c09_allocation_exceeds_source_refused",
            lambda: call_harness("harness.cash_allocation_record", {
                "actor_id": "recon-assistant", "scope": SCOPE,
                "key": key("al-over"),
                "allocation": {"allocationId": "al-over", "revision": 1,
                               "sourcePaymentId": "src-A",
                               "projectId": "本金",
                               "amountMinor": 18_000_000,
                               "currency": "CNY",
                               "ruleBasis": {"name": "合成"},
                               "jcAllocationRef": jc_revised[
                                   "cashAllocationRef"]}}),
            "cash_allocation_exceeds_source")
        # stale revision：al-2 先记 rev2，再投从未入账的 rev1 → 具名拒
        # （al-1@rev1 已在账，异内容重放走更具体的 content_conflict）。
        al2_rev2 = {"allocationId": "al-2", "revision": 2,
                    "sourcePaymentId": "src-B", "projectId": "本金",
                    "amountMinor": 2_000_000, "currency": "CNY",
                    "ruleBasis": {"name": "合成"},
                    "jcAllocationRef": jc_revised["cashAllocationRef"]}
        call_harness("harness.cash_allocation_record", {
            "actor_id": "recon-assistant", "scope": SCOPE,
            "key": key("al-2-r2"), "allocation": al2_rev2})
        self.expect_error(
            "c09_allocation_stale_revision_refused",
            lambda: call_harness("harness.cash_allocation_record", {
                "actor_id": "recon-assistant", "scope": SCOPE,
                "key": key("al-2-stale"),
                "allocation": {"allocationId": "al-2", "revision": 1,
                               "sourcePaymentId": "src-B",
                               "projectId": "本金",
                               "amountMinor": 1_000_000,
                               "currency": "CNY",
                               "ruleBasis": {"name": "合成"},
                               "jcAllocationRef": jc_revised[
                                   "cashAllocationRef"]}}),
            "cash_allocation_revision_stale")
        # 结构性分账两面：①产品桥层——record_payment 不在桥冻结组，
        # method_not_connected（无路由即无旁路）；②harness 公开面层——
        # 塞账单通道记案件回款＝billId 语义不存在 ref_version_unavailable。
        try:
            legal_entry.call("harness.record_payment", {
                "actor_id": "recon-assistant", "scope": SCOPE,
                "key": key("pay-cash-bridge"),
                "payment": {"id": "pay-cash-bridge", "revision": 1,
                            "billId": "bill-cash", "billVersion": 1,
                            "paidMinor": 18_000_000,
                            "occurredAt": "2026-03-01",
                            "sourceRef": href("voucher", "v-cash")}},
                {"harness_public_entry": str(
                    self.harness_root / "tools/workflow-tools/harness"
                    "/public_entry.py"), "harness_target": "opencode",
                 "harness_state_root": "X:/synth-unused"})
            raise AssertionError("record_payment_bridge_expected_refused")
        except NotConnected as exc:
            self.step("c09_record_payment_not_on_bridge",
                      "method_not_connected:harness.record_payment"
                      in str(exc), code=str(exc)[:120])
        self.expect_error(
            "c09_cash_through_record_payment_refused",
            lambda: raw_record_payment("recon-assistant", SCOPE,
                                       key("pay-cash"),
                                       {"id": "pay-cash-1", "revision": 1,
                                        "billId": "bill-cash",
                                        "billVersion": 1,
                                        "paidMinor": 18_000_000,
                                        "occurredAt": "2026-03-01",
                                        "sourceRef": href("voucher",
                                                          "v-cash")}),
            "ref_version_unavailable")
        # 负向零残留：负测后款源仍 3 行、分配生效额仍 2500000。
        after = call_harness("harness.cash_balance_read", {"scope": SCOPE})
        self.step("c09_negatives_left_ledger_unchanged",
                  len(after["sources"]) == 3
                  and after["netVector"]["allocatedTotalMinor"] == 4_500_000
                  and after["netVector"]["sourceTotalMinor"] == 18_000_000,
                  sources=len(after["sources"]),
                  allocated=after["netVector"]["allocatedTotalMinor"])

        # ---- C10 asOf 截至（5 阶段向量逐行）＋项目过滤。
        stage_views = {}
        for stage_as_of in ("2026-03-01", "2026-03-05", "2026-03-10",
                            "2026-03-15", "2026-03-20"):
            view = call_harness("harness.cash_balance_read", {
                "scope": SCOPE, "as_of": stage_as_of})
            v = view["netVector"]
            stage_views[stage_as_of] = (
                v["sourceTotalMinor"], v["clientGrossMinor"],
                v["clientNetMinor"], v["courtHeldMinor"])
        # 05 §9.5 五阶段逐行（source_total | gross | net | 法院持有）。
        self.step("c10_as_of_stage_values_exact",
                  stage_views["2026-03-01"]
                  == (3_000_000, 3_000_000, 3_000_000, 0)
                  and stage_views["2026-03-05"]
                  == (8_000_000, 3_000_000, 3_000_000, Q_AMOUNT)
                  and stage_views["2026-03-10"]
                  == (18_000_000, 13_000_000, 13_000_000, Q_AMOUNT)
                  and stage_views["2026-03-15"]
                  == (18_000_000, 13_000_000, 12_000_000, Q_AMOUNT)
                  and stage_views["2026-03-20"]
                  == (18_000_000, 18_000_000, 17_000_000, 0),
                  stages=stage_views)
        by_project = call_harness("harness.cash_balance_read", {
            "scope": SCOPE, "project_id": "本金"})
        self.step("c10_project_filter",
                  by_project["allocations"]["perProject"] == {"本金": 4_500_000}
                  and by_project["allocations"]["supersededIds"]
                  == ["al-1", "al-2"],
                  perProject=by_project["allocations"]["perProject"])

        # ---- C11 DB 级扫描：五账行数＋payments 表零行（结构性分账）。
        entitlement_rows = query(
            "SELECT COUNT(*) AS n FROM cash_entitlements WHERE matter_id=?",
            (MATTER,))[0]["n"]
        source_rows = query(
            "SELECT COUNT(*) AS n FROM cash_sources WHERE matter_id=?",
            (MATTER,))[0]["n"]
        transfer_rows = query(
            "SELECT COUNT(*) AS n FROM cash_transfers WHERE matter_id=?",
            (MATTER,))[0]["n"]
        outflow_rows = query(
            "SELECT COUNT(*) AS n FROM cash_outflows WHERE matter_id=?",
            (MATTER,))[0]["n"]
        allocation_rows = query(
            "SELECT COUNT(*) AS n FROM cash_allocations WHERE matter_id=?",
            (MATTER,))[0]["n"]
        payment_rows = query(
            "SELECT COUNT(*) AS n FROM payments WHERE bill_id=?",
            ("bill-cash",))[0]["n"]
        self.step("c11_db_level_scan_five_ledgers",
                  (entitlement_rows, source_rows, transfer_rows,
                   outflow_rows, allocation_rows) == (1, 3, 1, 1, 3)
                  and payment_rows == 0,
                  ledgers=(entitlement_rows, source_rows, transfer_rows,
                           outflow_rows, allocation_rows),
                  payments=payment_rows)

        # ---- C12 跨案不可见。
        return balance

    def bridge_negatives(self, config, call_jc):
        # ---- C13 桥负向：未配置/未知方法/方法组冻结。
        try:
            legal_entry.call("harness.cash_source_register",
                             {"scope": SCOPE}, {})
            raise AssertionError("bridge_not_configured_expected")
        except NotConnected as exc:
            self.step("c13_bridge_not_configured",
                      "harness_public_entry_not_configured" in str(exc))
        try:
            legal_entry.call("harness.cash_source_delete",
                             {"scope": SCOPE}, config)
            raise AssertionError("bridge_unknown_method_expected")
        except NotConnected as exc:
            self.step("c13_bridge_unknown_method_refused",
                      "method_not_connected" in str(exc))
        self.step("c13_method_groups_frozen",
                  legal_entry.HARNESS_CASH_METHODS == E16_HARNESS_METHODS
                  and legal_entry.CASH_CONTRACT_METHODS == E16_JC_METHODS)
        # JC 桥负向：未配置 jc_state_root。
        try:
            legal_entry.call("cash.balance", {"matterId": MATTER,
                                              "events": {}}, {})
            raise AssertionError("jc_not_configured_expected")
        except NotConnected as exc:
            self.step("c13_jc_not_configured",
                      "jc_state_root_not_configured" in str(exc))

    # -- profile drivers ---------------------------------------------------

    def _jc_config(self, workspace: Path) -> dict:
        rules = workspace / "rules"
        rules.mkdir(parents=True, exist_ok=True)
        (rules / "jc-local-pack.json").write_text(
            json.dumps(RULE_PACK, ensure_ascii=False), encoding="utf-8")
        return {
            "jc_state_root": str(workspace / "state"),
            "jc_rule_roots": [str(rules)],
            "jc_import_path": str(self.jc_root),
        }

    def run_desktop(self) -> int:
        temporary = tempfile.TemporaryDirectory(prefix="juscite-e16-desktop-")
        state_root = Path(temporary.name) / "state"
        state_root.mkdir(parents=True)
        registration = Path(temporary.name) / "service-local.json"
        registration.write_text(json.dumps(
            {"url": "http://127.0.0.1:1", "password": "synthetic-recon"}),
            encoding="utf-8")
        config = {
            "harness_public_entry":
                str(self.harness_root / "tools/workflow-tools/harness/public_entry.py"),
            "harness_target": "opencode",
            "harness_state_root": str(state_root),
            "harness_service_registration": str(registration),
            "harness_timeout": 120,
        }
        for path in (str(self.harness_root / "src"),
                     str(self.harness_root / "tools/workflow-tools")):
            if path not in sys.path:
                sys.path.insert(0, path)
        from legal_harness.business.units import HarnessUnits
        from legal_harness.state.matter_store import MatterStore
        store = MatterStore(state_root)
        store.create_matter(MATTER, "cas://profile-e16-recon")

        def call_harness(method, args):
            return legal_entry.call(method, args, config)

        def call_jc(method, args):
            return legal_entry.call(method, args,
                                    self._jc_config(Path(temporary.name)))

        def query(sql, params):
            import sqlite3
            with contextlib.closing(store._connect()) as connection:
                connection.row_factory = sqlite3.Row
                rows = connection.execute(sql, params).fetchall()
            return [dict(row) for row in rows]

        units = HarnessUnits(store)

        def raw_record_payment(actor_id, scope, command_key_value, payment):
            return units.record_payment(actor_id, scope, command_key_value,
                                        payment)

        print("[profile desktop] SQLite via product bridge subprocess",
              flush=True)
        self.common_flow("desktop", call_harness, call_jc, query,
                         raw_record_payment)
        self.bridge_negatives(config, call_jc)
        return 0

    def run_selfhost(self, dsn: str) -> int:
        for path in (str(self.harness_root / "src"),
                     str(self.harness_root / "tools/workflow-tools"),
                     str(self.harness_root),
                     str(self.harness_root / "tests")):
            if path not in sys.path:
                sys.path.insert(0, path)
        from legal_harness.business.provider_registry import (
            resolve_provider_method,
        )
        from legal_harness.business.units import HarnessUnits
        from legal_harness.state.pg_store import PgMatterStore

        temporary = tempfile.TemporaryDirectory(prefix="juscite-e16-selfhost-")
        store = PgMatterStore(
            Path(temporary.name) / "state", dsn=dsn,
            schema="e16_" + _uuid.uuid4().hex[:12])
        units = HarnessUnits(store)
        methods = set(E16_HARNESS_METHODS) | {"harness.record_payment"}
        bound = {name: resolve_provider_method(name, units)
                 for name in methods}
        store.create_matter(MATTER, "cas://profile-e16-recon")

        def call_harness(method, args):
            return bound[method](**args)

        def raw_record_payment(actor_id, scope, command_key_value, payment):
            return bound["harness.record_payment"](
                actor_id=actor_id, scope=scope, key=command_key_value,
                payment=payment)

        def call_jc(method, args):
            return legal_entry.call(method, args,
                                    self._jc_config(Path(temporary.name)))

        def query(sql, params):
            with contextlib.closing(store._connect()) as connection:
                rows = connection.execute(sql, params).fetchall()
            return [dict(row) for row in rows]

        print("[profile selfhost] PgMatterStore direct (lh-pg-e08)",
              flush=True)
        self.common_flow("selfhost", call_harness, call_jc, query,
                         raw_record_payment)
        self.bridge_negatives({}, call_jc)
        store.destroy()
        return 0


def write_evidence(profile: str, recon: Recon, harness_root: Path,
                   jc_root: Path, started: str, code: int) -> Path:
    evidence_dir = REPO_ROOT / "docs" / "construction" / "evidence" / "E16" \
        / profile
    evidence_dir.mkdir(parents=True, exist_ok=True)
    finished = datetime.now(timezone.utc).isoformat()
    summary = {
        "schema": "juscite-e16-cash-contract-recon/1",
        "unit": "W2b-U51",
        "feature": "E16",
        "profile": profile,
        "verdict": "RECON_OK" if code == 0 else "RECON_FAIL",
        "started_at": started,
        "finished_at": finished,
        "harness_worktree": str(harness_root),
        "harness_branch": "w2b-u51",
        "harness_base": "w2b-u40@37b266e7（施工链头＝…→w2b-u31/F82→"
                        "w2b-u40/F92 同链接力；master 929d0802 零动）",
        "jc_worktree": str(jc_root),
        "jc_branch": "w2b-u51",
        "jc_base": "w2b-u27@ac6209b（main 8f762d3→E21/W2b-U19→E19/W2b-U27"
                   " 同链接力）",
        "checks": recon.checks,
        "check_count": len(recon.checks),
        "failed": [c["check"] for c in recon.checks
                   if c["status"] != "PASS"],
    }
    payload = json.dumps(summary, ensure_ascii=False, indent=1)
    (evidence_dir / "e16_cash_contract_recon.json").write_text(
        payload + "\n", encoding="utf-8")
    lines = [f"# E16 款源/转移/退款/分配/余额 recon（{profile}）",
             "",
             f"- unit: W2b-U51 · profile: {profile}",
             f"- verdict: **{summary['verdict']}**"
             f" ({len(recon.checks)} checks, exit {code})",
             f"- harness: `{harness_root}` @ branch w2b-u51"
             "（基 w2b-u40@37b266e7；master 929d0802 零动）",
             f"- JC: `{jc_root}` @ branch w2b-u51（基 w2b-u27@ac6209b）",
             f"- started: {started} · finished: {finished}",
             "",
             "| # | check | status |",
             "|---|---|---|"]
    for index, check in enumerate(recon.checks, 1):
        lines.append(f"| {index} | {check['check']}"
                     f" | {check['status']} |")
    lines += ["", "全部合成材料；desktop＝产品桥子进程全链（SQLite 状态根），"
              "selfhost＝PgMatterStore 直连 lh-pg-e08（同一封闭注册）；"
              "05 §9.5 五阶段向量逐行（30000/80000/130000/120000/170000，"
              "source_total 恒 180000 不得 230000）；每转移/流出/分配事件"
              "钉 JC 计算回执 ref（digest 亲验相等＝互钉）；负向四件套"
              "（同源双计/230k 混计/净额向量缺失/浮点入参）＋塞 "
              "record_payment 全具名拒。"]
    (evidence_dir / "e16_cash_contract_recon.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8")
    return evidence_dir


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", action="append",
                        choices=["desktop", "selfhost"])
    parser.add_argument("--harness-root", type=Path,
                        default=DEFAULT_HARNESS_ROOT)
    parser.add_argument("--jc-root", type=Path, default=DEFAULT_JC_ROOT)
    parser.add_argument("--pg-dsn", default=DEFAULT_PG_DSN)
    args = parser.parse_args()
    profiles = args.profile or ["desktop"]
    if not (args.harness_root / "tools/workflow-tools/harness/public_entry.py").exists():
        print("RECON_BLOCKED: harness root missing public_entry:",
              args.harness_root)
        return 3
    if not (args.jc_root / "compiler_core" / "cash_contract.py").exists():
        print("RECON_BLOCKED: JC root missing cash_contract:", args.jc_root)
        return 3
    failures = 0
    first = True
    for profile in profiles:
        started = datetime.now(timezone.utc).isoformat()
        recon = Recon(args.harness_root, args.jc_root)
        try:
            if first:
                # C01 双仓分支/基/主检出/工作树干净亲验（只跑一次，两
                # profile 共用同一检出）。
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
                                      args.jc_root, started, code)
        verdict = "RECON_OK" if code == 0 else "RECON_FAIL"
        print(f"[{profile}] {verdict} ({len(recon.checks)} checks,"
              f" exit {code}) evidence={evidence_dir}", flush=True)
        if code != 0:
            failures += 1
        first = False
    return 0 if failures == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
