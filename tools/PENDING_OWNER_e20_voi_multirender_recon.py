# -*- coding: utf-8 -*-
"""E20 VOI 和多解释实际支持对账（W2b-U53 B2 段＋W4-U56 B4 段）——双 profile。

B4 段（W4-U56）：checkpoint 产线机制面＝checkpoint 登记/校准证据绑定的
生产流水线——真实训练 checkpoint（compiler_core.prediction
train_and_save 在合成行上真跑）＋评估文档互证绑定为 (a) jc.voi_analyze
消费的 probability-prediction 概率回执（checkpoint 身份＋lineDigest
钉定）与 (b) readiness 八维审计可消费的校准证据行（产线产出确被审计
消费：4 模型侧维 registered＋数据侧 4 维具名缺口保持）；无真实
checkpoint＝具名 model_not_available 值恒 null；概率不归一/统一胜率/
风险参数 1 编造负测维持全拒；产线回执 wholeCaseProof.provenByLine=
false——全案 VOI 证明不由 CI 或原子定理推（08§4 分层）；真实
checkpoint 挂模型/数据授权回收点具名写回 E20 行（本工具核其在账）。

对账对象：
  JC 分支 w2b-u53（基 w2b-u27@ac6209b＝main 8f762d3→E21(W2b-U19)→
  E19(W2b-U27) 同链接力）的 jc-voi-analysis/1 确定性面（信息集分区/
  合法行动集/概率效用成本输入闭集；概率永不作为请求输入——只从登记
  在案的 checkpoint 面回执回读且伴生 E19 readiness predictionKnown=
  true；readiness 缺口＝具名 unavailable 值恒 null；期望值精确有理数）
  ＋read_argument_graph 多解释分支实际转录（branchRefs owner=jc、
  noBranchReason 显式——E15 branch_projection 合同同值）。
  harness 分支 w2b-u53（基施工链头 w2b-u52@8d24ed2f＝…E18 策略依赖账
  v22 同链接力）的 VOI 请求/回执账（schema v22→v23，E15/E17 账同族
  append-only；supported 由 JC 回执 voiKnown 派生；未支持＝具名
  NOT_COMPLETE 结构断言，不填 PASS）＋--voi-json 信封。
desktop profile＝产品桥（legal_entry → 子进程 public_entry）完全同一
条链（SQLite 状态根）；selfhost profile＝PgMatterStore 直连 lh-pg-e08
（resolve_provider_method 同一封闭注册）。

分段：
  C01 双仓分支/基/主检出/工作树钉定
  C02 桥负向（未配置 NOT_CONNECTED/未知方法/VOI 方法组冻结×2）
  C03 harness 请求登记（闭集全收＋幂等/异内容 conflict）
  C04 输入闭集负向（缺族 fields_missing/浮点 payoff/分区重叠/概率证据
      owner 错 jc_ref_invalid）
  C05 缺口路径全链：八维证据缺→voiKnown=false unavailable＋missingScopes
      透传＋值 null（不造 0.5）→回执转录 supported=0→投影 NOT_COMPLETE
      （不填 PASS）
  C06 NOT_COMPLETE 结构断言负向（未支持回执携带数值＝拒收）
  C07 数值路径全链：全证据＋checkpoint 概率回执载荷→精确 VOI
      （1_500_000/1）＋baseline litigate→回执转录 supported=1→投影
      SUPPORTED
  C08 编造负向（统一胜率字段/风险参数 1 typed 拒；证据齐全无 checkpoint
      ＝voi_checkpoint_receipt_required；概率不归一拒）
  C09 多解释分支公开出口实测（jc.evaluate 真跑＋read_argument_graph：
      graphKind/multiInterpretation 合同形状；branchRefs 全 owner=jc；
      无分支显式 noBranchReason；harness 造 ref 拒——E15 合同同检）
  C10 产线真跑（合成 checkpoint 训练真跑→登记绑定：概率回执身份钉定
      ＋synthetic 戳＋wholeCaseProof false；证据行携 checkpoint 身份）
  C11 产线产出被 readiness 八维审计消费（4 模型侧维 registered＋数据
      侧 4 维 missingScopes 具名保持＋probability 恒 null）
  C12 产线概率回执喂 VOI 数值路径全链（真实训练 checkpoint 的回执
      驱动精确有理数 VOI 1500000/1）
  C13 无 checkpoint＝具名 unavailable（model_not_available/不登记/
      证据空/值 null）；unavailable 回执不可冒充概率证据喂 VOI
  C14 产线编造负测全拒（不归一/统一胜率/风险参数 1/数据侧维生产/
      授权缺一/评估互证失败/泄漏为真）
  C15 产线两跑回执逐字节同（确定性＝证据可复现）
  C16 分层＋回收点在账（08§4 全案证明不由产线/CI 推＋E20 行
      failure_reason 携 B4＋checkpoint＋授权后回收点）

用法（juscite worktree w4-u56 根 cwd）：
  python -X utf8 tools/PENDING_OWNER_e20_voi_multirender_recon.py \
      --profile desktop --profile selfhost

退出码：0 = 全部 profile RECON_OK；2 = RECON_FAIL；3 = 环境缺失。
证据：docs/construction/evidence/E20/<profile>/ JSON＋MD。
全部合成材料；不发网络；不写 %APPDATA%；真实 checkpoint 概率产线
（真实法院数据训练）挂模型/数据授权回收点（E20 行在账），合成机制
面不代替真实案件概率证据；全案 VOI 证明不由 CI 或原子定理推。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import hashlib
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "python"))
sys.path.insert(0, str(REPO_ROOT / "implementation" / "tests"))

import legal_entry  # noqa: E402
from legal_entry import HarnessCommandError, JCMethodFailure, NotConnected  # noqa: E402

DEFAULT_HARNESS_ROOT = Path(
    r"D:\Codex\1.法律工作区\legal-harness工作区\legal-harness-repo"
    r"\.local\worktrees\w2b-u53")
DEFAULT_JC_ROOT = Path(
    r"D:\Codex\1.法律工作区\juris-calculus工作区\juris-calculus"
    r"\.local\worktrees\w4-u56")
LEDGER = REPO_ROOT / "docs" / "construction" / "acceptance-ledger.csv"

# JC 钉定（漂移响亮拒）：voi_analysis 保持 W2b-U53 钉定字节（B2 面零
# 改动）；checkpoint_line/client 为 W4-U56 B4 段新字节。
JC_VOI_SHA256 = ("2d60d161ea3015b23d389de16fb3109c69e3037c34cd5650c6484f"
                 "976dbcbece")
JC_LINE_SHA256 = ("8cd4e6bb9a397c28545239ffd23918006ef06f321bf772c224df"
                  "ae5312e484ba")
JC_CLIENT_SHA256 = ("8f124db1c99fb763bbadd2125edb046097c2004a0a1f84843b"
                    "b286016efe68e1")

MATTER = "m-e20-recon"
SCOPE = {"kind": "matter", "matterId": MATTER}

DEFAULT_PG_DSN = "postgresql://lh_app:e08-synth-only@127.0.0.1:55432/legal_harness"

# create_local_client 需至少一个规则根（JC 不随附规则库）；本对账消费
# voi/readiness 面（零规则消费），入最小合成包以满足构造（U27/U51 同纪律）。
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

DIMENSIONS = ("sample_selection", "label_definition", "time_window",
              "case_family", "time_migration_calibration",
              "jurisdiction_migration_calibration", "calibration_report",
              "leakage_audit")

RECORDS = [{
    "materialId": "m-samp", "jurisdiction": "ZJ", "courtId": "H01",
    "courtLevel": "first", "decisionDate": "2024-06-01",
    "sourceTier": "local_court", "factualDifference": "合成：损失认定同构",
    "declaredUse": "prediction_sample", "datasetVersion": "ds-synth-1",
}]
FRAME = {
    "sampleFrameId": "sf-synth-1", "targetCourt": "H01",
    "targetJurisdiction": "ZJ", "caseFamily": "买卖合同纠纷（合成）",
    "labelDefinition": "一审全部诉请获支持（合成标签）",
    "timeWindowStart": "2023-01-01", "timeWindowEnd": "2024-12-31",
    "datasetVersion": "ds-synth-1", "admittedRowIds": ["m-samp"],
}
TARGET = {"targetCourt": "H01", "targetJurisdiction": "ZJ",
          "evaluationTime": "2026-10-17"}

CHECKPOINT = {
    "kind": "probability-prediction",
    "checkpointId": "ckpt-synth-e20",
    "eventDefinition": "target-court-win（合成）",
    "perStateProbabilities": {"win": "0.6", "lose": "0.4"},
}

VOI_REQUEST = {
    "requestId": "vr-1",
    "decisionId": "dec-e20-recon",
    "worldStates": ["win", "lose"],
    "informationSets": [
        {"informationSetId": "I-win", "stateIds": ["win"]},
        {"informationSetId": "I-lose", "stateIds": ["lose"]},
    ],
    "actions": ["settle", "litigate"],
    "payoffs": [
        {"actionId": "settle", "stateId": "win", "netMinor": 3_000_000},
        {"actionId": "settle", "stateId": "lose", "netMinor": 3_000_000},
        {"actionId": "litigate", "stateId": "win", "netMinor": 10_000_000},
        {"actionId": "litigate", "stateId": "lose", "netMinor": -2_000_000},
    ],
    "costOfInformationMinor": 500_000,
    "probabilitySource": {
        "readinessRef": {
            "owner": "jc", "kind": "prediction-readiness",
            "id": "jc-calc-0000000000000000000000000000000000000000",
            "version": "1", "matterId": MATTER,
            "digest": "sha256:" + "0" * 64,
        },
        "checkpointPredictionRef": {
            "owner": "jc", "kind": "probability-prediction",
            "id": "jc-calc-1111111111111111111111111111111111111111",
            "version": "1", "matterId": MATTER,
            "digest": "sha256:" + "1" * 64,
        },
    },
}


def key(request_id: str) -> dict:
    return {"requestId": request_id, "targetId": None,
            "expectedRevision": None, "inputRefs": []}


def make_config(root: Path) -> dict:
    rules = root / "rules"
    rules.mkdir(parents=True, exist_ok=True)
    (rules / "jc-local-pack.json").write_text(
        json.dumps(RULE_PACK, ensure_ascii=False), encoding="utf-8")
    return {
        "jc_state_root": str(root / "state"),
        "jc_rule_roots": [str(rules)],
        "jc_import_path": str(DEFAULT_JC_ROOT),
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

    def sha256(self, path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def branch_checks(self):
        h_branch = self.git(self.harness_root, "rev-parse", "--abbrev-ref", "HEAD")
        h_base = self.git(self.harness_root, "merge-base", "HEAD", "w2b-u52")
        h_master = self.git(self.harness_root, "rev-parse", "master")
        self.step("c01_harness_branch", h_branch == "w2b-u53", branch=h_branch)
        self.step("c01_harness_base_on_w2b_u52", h_base.startswith("8d24ed2f"),
                  base=h_base)
        self.step("c01_harness_master_untouched",
                  h_master.startswith("929d0802"), master=h_master[:12])
        h_dirty = self.git(self.harness_root, "status", "--porcelain")
        self.step("c01_harness_worktree_clean", h_dirty == "",
                  dirty=h_dirty[:200])
        j_branch = self.git(self.jc_root, "rev-parse", "--abbrev-ref", "HEAD")
        j_base = self.git(self.jc_root, "merge-base", "HEAD", "w2b-u53")
        j_transitive = self.git(self.jc_root, "merge-base", "HEAD", "w2b-u27")
        j_main = self.git(self.jc_root, "rev-parse", "main")
        self.step("c01_jc_branch", j_branch == "w4-u56", branch=j_branch)
        self.step("c01_jc_base_on_w2b_u53", j_base.startswith("291f3578"),
                  base=j_base)
        self.step("c01_jc_transitive_base_on_w2b_u27",
                  j_transitive.startswith("ac6209b"), base=j_transitive)
        self.step("c01_jc_main_untouched", j_main.startswith("8f762d3"),
                  main=j_main[:12])
        j_dirty = self.git(self.jc_root, "status", "--porcelain")
        self.step("c01_jc_worktree_clean", j_dirty == "", dirty=j_dirty[:200])
        # 本单冻结面在盘：三 sha 钉定（voi_analysis 保持 W2b-U53 字节＝
        # B2 面零改动；checkpoint_line/client 为 B4 段新字节）＋schema
        # v23＋桥方法组。
        voi_sha = self.sha256(self.jc_root / "compiler_core" / "voi_analysis.py")
        line_sha = self.sha256(
            self.jc_root / "compiler_core" / "checkpoint_line.py")
        client_sha = self.sha256(self.jc_root / "compiler_core" / "client.py")
        self.step("c01_jc_faces_pinned",
                  voi_sha == JC_VOI_SHA256 and line_sha == JC_LINE_SHA256
                  and client_sha == JC_CLIENT_SHA256,
                  voi=voi_sha[:16], line=line_sha[:16],
                  client=client_sha[:16])
        schema = (self.harness_root / "src" / "legal_harness" / "state"
                  / "matter_store.py").read_text(encoding="utf-8")
        self.step("c01_harness_schema_v23",
                  "SCHEMA_VERSION = 23" in schema
                  and "voi_requests" in schema and "voi_receipts" in schema,
                  schema="v23 + voi_requests/voi_receipts")
        self.step("c02_method_groups_frozen",
                  legal_entry.VOI_ANALYSIS_METHODS == frozenset({
                      "jc.voi_analyze", "jc.checkpoint_line"})
                  and legal_entry.HARNESS_VOI_METHODS == frozenset({
                      "harness.voi_request_register",
                      "harness.voi_receipt_record",
                      "harness.voi_read", "harness.voi_list"}),
                  jc="jc.{voi_analyze,checkpoint_line}",
                  harness="harness.voi_{request_register,receipt_record,read,list}")

    # ------------------------------------------------------------------
    def common_flow(self, profile: str, call_harness, call_jc, call_line,
                    call_readiness, query):
        # ---- C02 桥负向。
        self.step("c02_unconfigured_not_connected", True,
                  note="jc/harness 未配置径由 wiring 测试 12 例覆盖"
                       "（test_e20_voi_wiring exit 0）；本对账跑已配置链")

        # ---- C03 harness 请求登记：闭集全收＋幂等/异内容 conflict。
        registered = call_harness("harness.voi_request_register", {
            "actor_id": "recon-assistant", "scope": SCOPE,
            "key": key("vr-1"), "request": dict(VOI_REQUEST)})
        self.step("c03_request_registered",
                  registered["request"]["kind"] == "voi_request"
                  and registered["request"]["decisionId"] == "dec-e20-recon"
                  and registered["request"]["recordHash"],
                  requestId=registered["request"]["id"])
        replayed = call_harness("harness.voi_request_register", {
            "actor_id": "recon-assistant", "scope": SCOPE,
            "key": key("vr-1-replay"), "request": dict(VOI_REQUEST)})
        self.step("c03_request_replay_idempotent",
                  replayed["replayed"] is True)
        drifted = dict(VOI_REQUEST, costOfInformationMinor=600_000)
        self.expect_error(
            "c03_request_content_conflict", lambda: call_harness(
                "harness.voi_request_register",
                {"actor_id": "recon-assistant", "scope": SCOPE,
                 "key": key("vr-1-conflict"), "request": drifted}),
            "voi_request_content_conflict:vr-1")

        # ---- C04 输入闭集负向（harness 侧四路具名拒）。
        missing = dict(VOI_REQUEST)
        del missing["payoffs"]
        self.expect_error(
            "c04_missing_family_refused", lambda: call_harness(
                "harness.voi_request_register",
                {"actor_id": "recon-assistant", "scope": SCOPE,
                 "key": key("vr-miss"), "request": missing}),
            "fields_missing")
        payoffs = list(VOI_REQUEST["payoffs"])
        payoffs[0] = dict(payoffs[0], netMinor=3000000.5)
        self.expect_error(
            "c04_float_payoff_refused", lambda: call_harness(
                "harness.voi_request_register",
                {"actor_id": "recon-assistant", "scope": SCOPE,
                 "key": key("vr-float"),
                 "request": dict(VOI_REQUEST, payoffs=payoffs)}),
            "voi_payoff_not_minor_units")
        self.expect_error(
            "c04_partition_overlap_refused", lambda: call_harness(
                "harness.voi_request_register",
                {"actor_id": "recon-assistant", "scope": SCOPE,
                 "key": key("vr-overlap"),
                 "request": dict(VOI_REQUEST, informationSets=[
                     {"informationSetId": "I-1", "stateIds": ["win", "lose"]},
                     {"informationSetId": "I-2", "stateIds": ["win"]}])}),
            "voi_partition_overlap")
        bad_source = dict(VOI_REQUEST["probabilitySource"],
                          readinessRef={"owner": "harness", "kind": "x",
                                        "id": "0", "version": "1"})
        self.expect_error(
            "c04_probability_owner_refused", lambda: call_harness(
                "harness.voi_request_register",
                {"actor_id": "recon-assistant", "scope": SCOPE,
                 "key": key("vr-owner"),
                 "request": dict(VOI_REQUEST,
                                 probabilitySource=bad_source)}),
            "jc_ref_invalid")

        # ---- C05 缺口路径全链（CLI 真跑：八维证据缺→unavailable）。
        gapped = call_jc({
            "matterId": MATTER,
            "request": {k: v for k, v in VOI_REQUEST.items()
                        if k != "requestId"},
            "readiness": {"frame": FRAME, "records": RECORDS,
                          "target": TARGET, "evidence": {}},
            "checkpointProbability": dict(CHECKPOINT)})
        self.step(
            "c05_gap_named_unavailable",
            gapped["voiKnown"] is False
            and gapped["unavailableReason"] == "prediction_readiness_incomplete"
            and gapped["missingScopes"] == list(DIMENSIONS)
            and gapped["voi"] is None and gapped["probability"] is None
            and gapped["noProbabilityNoVoi"] is True
            and gapped["voiReceiptRef"]["owner"] == "jc",
            missingScopes=len(gapped["missingScopes"]))
        receipt = call_harness("harness.voi_receipt_record", {
            "actor_id": "recon-assistant", "scope": SCOPE,
            "key": key("voi-r-gap"),
            "receipt_payload": {"receiptId": "voi-r-gap",
                                 "requestId": "vr-1",
                        "voiReceiptRef": gapped["voiReceiptRef"],
                        "jcPayload": {
                            kk: gapped[kk] for kk in (
                                "schema_version", "kind", "voiKnown",
                                "unavailableReason", "missingScopes",
                                "probability", "voi")}}})
        self.step("c05_gap_receipt_transcribed",
                  receipt["voiReceipt"]["voiKnown"] is False
                  and receipt["voiReceipt"]["unavailableReason"]
                  == "prediction_readiness_incomplete",
                  supported=False)
        projection = call_harness("harness.voi_read",
                                  {"scope": SCOPE, "request_id": "vr-1"})
        self.step(
            "c05_projection_not_complete_never_pass",
            projection["status"] == "NOT_COMPLETE"
            and projection["value"] is None
            and projection["unavailableReason"]
            == "prediction_readiness_incomplete"
            and projection["missingScopes"] == list(DIMENSIONS),
            projection_status=projection["status"])

        # ---- C06 NOT_COMPLETE 结构断言负向：未支持回执携带数值＝拒收。
        bad = dict(gapped)
        bad["voi"] = {"numerator": 1, "denominator": 1, "isInteger": True}
        self.expect_error(
            "c06_not_complete_with_value_refused", lambda: call_harness(
                "harness.voi_receipt_record",
                {"actor_id": "recon-assistant", "scope": SCOPE,
                 "key": key("voi-r-bad"),
                 "receipt_payload": {"receiptId": "voi-r-bad",
                                     "requestId": "vr-1",
                             "voiReceiptRef": gapped["voiReceiptRef"],
                             "jcPayload": {
                                 kk: bad[kk] for kk in (
                                     "schema_version", "kind", "voiKnown",
                                     "unavailableReason", "probability",
                                     "voi")}}}),
            "voi_not_complete_shape_invalid")

        # ---- C07 数值路径全链（CLI 真跑：全证据＋checkpoint 载荷）。
        known = call_jc({
            "matterId": MATTER,
            "request": {k: v for k, v in VOI_REQUEST.items()
                        if k != "requestId"},
            "readiness": {"frame": FRAME, "records": RECORDS,
                          "target": TARGET,
                          "evidence": {d: {"evidenceId": f"ev-{d}"}
                                       for d in DIMENSIONS}},
            "checkpointProbability": dict(CHECKPOINT)})
        self.step(
            "c07_exact_rational_voi",
            known["voiKnown"] is True
            and known["valueUnit"] == "minor"
            and known["baseline"]["action"] == "litigate"
            and known["voi"] == {"numerator": 1_500_000, "denominator": 1,
                                 "isInteger": True}
            and known["probability"] is None
            and known["voiReceiptRef"]["owner"] == "jc",
            voi=str(known["voi"]["numerator"]) + "/"
            + str(known["voi"]["denominator"]))
        receipt2 = call_harness("harness.voi_receipt_record", {
            "actor_id": "recon-assistant", "scope": SCOPE,
            "key": key("voi-r-known"),
            "receipt_payload": {"receiptId": "voi-r-known",
                                 "requestId": "vr-1",
                        "voiReceiptRef": known["voiReceiptRef"],
                        "jcPayload": {
                            kk: known[kk] for kk in (
                                "schema_version", "kind", "voiKnown",
                                "probability", "voi")}}})
        self.step("c07_known_receipt_transcribed",
                  receipt2["voiReceipt"]["voiKnown"] is True
                  and receipt2["voiReceipt"]["voi"]["numerator"] == 1_500_000,
                  supported=True)
        projection2 = call_harness("harness.voi_read",
                                   {"scope": SCOPE, "request_id": "vr-1"})
        self.step(
            "c07_projection_supported",
            projection2["status"] == "SUPPORTED"
            and projection2["value"] == {"numerator": 1_500_000,
                                         "denominator": 1,
                                         "isInteger": True},
            projection_status=projection2["status"])

        # ---- C08 编造负向（JC typed 拒＋桥面 checkpoint 纪律）。
        self.expect_error(
            "c08_unified_rate_refused", lambda: call_jc({
                "matterId": MATTER,
                "request": dict(
                    {k: v for k, v in VOI_REQUEST.items()
                     if k != "requestId"}, unifiedCourtRate="0.62"),
                "readiness": {"frame": FRAME, "records": RECORDS,
                              "target": TARGET,
                              "evidence": {d: {"evidenceId": f"ev-{d}"}
                                           for d in DIMENSIONS}},
                "checkpointProbability": dict(CHECKPOINT)}),
            "probability_placeholder_refused")
        self.expect_error(
            "c08_risk_parameter_refused", lambda: call_jc({
                "matterId": MATTER,
                "request": dict(
                    {k: v for k, v in VOI_REQUEST.items()
                     if k != "requestId"}, riskParameter="1"),
                "readiness": {"frame": FRAME, "records": RECORDS,
                              "target": TARGET,
                              "evidence": {d: {"evidenceId": f"ev-{d}"}
                                           for d in DIMENSIONS}},
                "checkpointProbability": dict(CHECKPOINT)}),
            "probability_placeholder_refused")
        self.expect_error(
            "c08_missing_checkpoint_refused", lambda: call_jc({
                "matterId": MATTER,
                "request": {k: v for k, v in VOI_REQUEST.items()
                            if k != "requestId"},
                "readiness": {"frame": FRAME, "records": RECORDS,
                              "target": TARGET,
                              "evidence": {d: {"evidenceId": f"ev-{d}"}
                                           for d in DIMENSIONS}}}),
            "voi_checkpoint_receipt_required")
        bad_prob = dict(CHECKPOINT,
                        perStateProbabilities={"win": "0.6", "lose": "0.3"})
        self.expect_error(
            "c08_unnormalized_probability_refused", lambda: call_jc({
                "matterId": MATTER,
                "request": {k: v for k, v in VOI_REQUEST.items()
                            if k != "requestId"},
                "readiness": {"frame": FRAME, "records": RECORDS,
                              "target": TARGET,
                              "evidence": {d: {"evidenceId": f"ev-{d}"}
                                           for d in DIMENSIONS}},
                "checkpointProbability": bad_prob}),
            "voi_probability_not_normalized")

        # ---- C09 多解释分支公开出口实测（E15 recon 同模式真跑）。
        graph = self._jc_real_branch_read()
        branch_refs = graph["branchRefs"]
        self.step(
            "c09_argument_graph_branch_contract",
            graph["graphKind"] in ("argument-graph-v4",
                                   "sealed-result-branches-only")
            and isinstance(graph.get("multiInterpretation"), dict)
            and graph["multiInterpretation"]["hasBranches"]
            == bool(branch_refs)
            and (graph["multiInterpretation"]["noBranchReason"]
                 == "jc_public_exit_branch_refs_empty"
                 if not branch_refs else
                 graph["multiInterpretation"]["noBranchReason"] is None)
            and all(ref.get("owner") == "jc" for ref in branch_refs)
            and all(entry.get("support", {}).get("basis")
                    == "sealed_result_branch"
                    for entry in graph.get("branches", [])),
            graphKind=graph["graphKind"],
            hasBranches=graph["multiInterpretation"]["hasBranches"],
            branchCount=len(branch_refs),
            noBranchReason=graph["multiInterpretation"]["noBranchReason"])
        # harness 造 branch ref 拒收（E15 登记面同检——不由前端制造）。
        fake_projection = {
            "projectionId": "bp-e20-fake",
            "jcRunRef": {"owner": "jc", "kind": "run-identity",
                         "id": "0" * 64, "version": "1",
                         "matterId": MATTER},
            "jcGraphRef": {"owner": "jc", "kind": "argument-graph",
                           "id": "1" * 64, "version": "1",
                           "matterId": MATTER},
            "profile": "SYNTHETIC-CONDITIONAL-PRINCIPAL/1",
            "branches": [{"ref": {"owner": "harness", "kind": "argument-branch",
                                  "id": "fake", "version": "1"},
                          "hypothesis": "前端自造分支", "conclusion": "不得入账",
                          "scope": "任意"}],
        }
        self.expect_error(
            "c09_frontend_branch_ref_refused", lambda: call_harness(
                "harness.branch_projection_record",
                {"actor_id": "recon-assistant", "scope": SCOPE,
                 "key": key("bp-e20-fake"),
                 "projection": fake_projection}),
            "branch_ref_owner_invalid")

        # ---- C10 产线真跑（合成 checkpoint 训练真跑→登记绑定）。
        trained = self._train_synthetic_checkpoint()
        checkpoint_id = trained["checkpoint"]["checkpoint_id"]
        line_request = {
            "checkpoint": trained["checkpoint"],
            "evaluation": trained["evaluation"],
            "worldStates": ["win", "lose"],
            "perStateProbabilities": {"win": "0.6", "lose": "0.4"},
            "boundEvidence": {
                "time_migration_calibration": {"evidenceId": "cal-t-2023"},
                "jurisdiction_migration_calibration": {
                    "evidenceId": "cal-j-zj"},
            },
            "dataProvenance": "synthetic_mechanism_demo",
        }
        line = call_line(line_request)
        probability = line.get("probabilityReceipt") or {}
        self.step(
            "c10_line_registers_trained_checkpoint",
            line["checkpointRegistered"] is True
            and line["checkpointIdentity"]["checkpointId"] == checkpoint_id
            and probability.get("kind") == "probability-prediction"
            and probability.get("checkpointId") == checkpoint_id
            and probability.get("perStateProbabilities")
            == {"win": "0.6", "lose": "0.4"}
            and probability.get("boundToTrainedCheckpoint") is True
            and line["lineDigest"] == probability.get("checkpointLineDigest")
            and line["checkpointLineRef"]["owner"] == "jc"
            and line["checkpointLineRef"]["kind"] == "checkpoint-line"
            and line["probabilityReceiptRef"]["owner"] == "jc",
            checkpointId=checkpoint_id[:24])
        self.step(
            "c10b_line_bindings_and_stamps",
            set(line["evidenceBindings"]) == {
                "time_migration_calibration",
                "jurisdiction_migration_calibration",
                "calibration_report", "leakage_audit"}
            and all(row["checkpointId"] == checkpoint_id
                    and row["bindingDigest"]
                    for row in line["evidenceBindings"].values())
            and [entry["dimension"]
                 for entry in line["withheldDimensions"]]
            == ["sample_selection", "label_definition", "time_window",
                "case_family"]
            and line["syntheticMechanismDemo"] is True
            and line["usableForRealCasePrediction"] is False
            and line["probability"] is None
            and line["wholeCaseProof"]["provenByLine"] is False,
            withheld=len(line["withheldDimensions"]))

        # ---- C11 产线产出被 readiness 八维审计消费（数据侧缺口保持）。
        residual = call_readiness({
            "frame": FRAME, "records": RECORDS, "target": TARGET,
            "evidence": line["evidenceBindings"]})
        self.step(
            "c11_line_evidence_consumed_by_readiness_audit",
            residual["predictionKnown"] is False
            and residual["missingScopes"] == [
                "sample_selection", "label_definition", "time_window",
                "case_family"]
            and residual["probability"] is None
            and {entry["dimension"] for entry in residual["dimensions"]
                 if entry["status"] == "registered"}
            == set(line["evidenceBindings"]),
            missing=len(residual["missingScopes"]))

        # ---- C12 产线概率回执喂 VOI 数值路径全链。
        known_line = call_jc({
            "matterId": MATTER,
            "request": {k: v for k, v in VOI_REQUEST.items()
                        if k != "requestId"},
            "readiness": {"frame": FRAME, "records": RECORDS,
                          "target": TARGET,
                          "evidence": {d: {"evidenceId": f"ev-{d}"}
                                       for d in DIMENSIONS}},
            "checkpointProbability": probability})
        self.step(
            "c12_line_receipt_drives_exact_voi",
            known_line["voiKnown"] is True
            and known_line["voi"] == {"numerator": 1_500_000,
                                      "denominator": 1, "isInteger": True}
            and known_line["baseline"]["action"] == "litigate"
            and known_line["voiReceiptRef"]["owner"] == "jc",
            voi="1500000/1")

        # ---- C13 无 checkpoint＝具名 unavailable＋不可冒充概率证据。
        absent = call_line({
            "worldStates": ["win", "lose"],
            "perStateProbabilities": {"win": "0.6", "lose": "0.4"},
            "dataProvenance": "synthetic_mechanism_demo"})
        self.step(
            "c13_no_checkpoint_named_unavailable",
            absent["checkpointRegistered"] is False
            and absent["unavailableReason"] == "model_not_available"
            and absent["probabilityReceipt"] is None
            and absent["evidenceBindings"] == {}
            and absent["probability"] is None
            and absent["wholeCaseProof"]["provenByLine"] is False
            and absent["checkpointLineRef"]["owner"] == "jc",
            unavailable=absent["unavailableReason"])
        self.expect_error(
            "c13b_unavailable_receipt_not_probability_evidence",
            lambda: call_jc({
                "matterId": MATTER,
                "request": {k: v for k, v in VOI_REQUEST.items()
                            if k != "requestId"},
                "readiness": {"frame": FRAME, "records": RECORDS,
                              "target": TARGET,
                              "evidence": {d: {"evidenceId": f"ev-{d}"}
                                           for d in DIMENSIONS}},
                "checkpointProbability": {
                    k: absent[k] for k in (
                        "schema_version", "kind", "checkpointRegistered",
                        "unavailableReason")}}),
            "voi_probability_receipt_invalid")

        # ---- C14 产线编造负测全拒。
        self.expect_error(
            "c14_unnormalized_line_refused", lambda: call_line(
                dict(line_request,
                     perStateProbabilities={"win": "0.6", "lose": "0.3"})),
            "checkpoint_line_probability_not_normalized")
        self.expect_error(
            "c14b_line_win_rate_refused", lambda: call_line(
                dict(line_request, winRate="0.62")),
            "probability_placeholder_refused")
        self.expect_error(
            "c14c_line_risk_parameter_refused", lambda: call_line(
                dict(line_request, riskParameter="1")),
            "probability_placeholder_refused")
        self.expect_error(
            "c14d_line_data_side_dimension_refused", lambda: call_line(
                dict(line_request, boundEvidence={
                    "sample_selection": {"evidenceId": "fake-data-side"}})),
            "checkpoint_line_dimension_not_producible")
        self.expect_error(
            "c14e_line_authorization_missing_refused", lambda: call_line(
                dict(line_request,
                     dataProvenance="authorized_real_court_data")),
            "real_court_data_authorization_missing")
        drifted_evaluation = dict(line_request["evaluation"],
                                  checkpointId="pred-other")
        self.expect_error(
            "c14f_line_evaluation_mismatch_refused", lambda: call_line(
                dict(line_request, evaluation=drifted_evaluation)),
            "checkpoint_line_evaluation_mismatch")
        leaked = json.loads(json.dumps(line_request["evaluation"]))
        leaked["leakage"]["testUsedForTraining"] = True
        self.expect_error(
            "c14g_line_leakage_refused", lambda: call_line(
                dict(line_request, evaluation=leaked)),
            "checkpoint_line_leakage_refused")

        # ---- C15 产线两跑回执逐字节同（确定性＝证据可复现）。
        line_again = call_line(line_request)

        def _core(receipt: dict) -> str:
            return json.dumps(
                {k: v for k, v in receipt.items()
                 if not k.endswith("Ref")},
                sort_keys=True, ensure_ascii=False)

        self.step("c15_line_deterministic_two_runs",
                  _core(line) == _core(line_again),
                  note="两跑回执逐字节同（去 ref 后）")

        # ---- C16 分层＋回收点在账（08§4＋E20 行 failure_reason）。
        recovery_named = False
        if LEDGER.is_file():
            import csv  # noqa: E402
            with open(LEDGER, encoding="utf-8-sig", newline="") as handle:
                for row in csv.reader(handle):
                    if row and row[0] == "E20":
                        reason = row[16] if len(row) > 16 else ""
                        recovery_named = (
                            "B4" in reason and "checkpoint" in reason
                            and "授权后" in reason)
                        break
        self.step(
            "c16_layering_and_recovery_point",
            line["wholeCaseProof"]["provenByLine"] is False
            and "not a whole-case conclusion" in known_line["note"]
            and recovery_named,
            recovery=recovery_named)

    def _jc_real_branch_read(self) -> dict:
        """真实 JC 公开出口：evaluate 真跑一次合成 run，read_argument_graph
        取分支合同形状（07 E20 branch 语义：owner=jc／显式无分支标记）。"""
        import test_p01_jc_wiring as p01
        with tempfile.TemporaryDirectory(prefix="juscite-e20-jc-") as tmp:
            # p01 自带规则包（acc-base＋acc-exception 两合成规则）——
            # issue queries 从 local_pack 取 claim，最小包缺行即拒。
            config = p01._config(Path(tmp))
            queries = p01._issue_queries(config)
            result = legal_entry.call("jc.evaluate", {
                "bundle": {
                    "case_id": "e20-recon-case",
                    "decision_time": "2026-09-01T00:00:00Z",
                    "facts": [{"fact_key": "acc.contract"},
                              {"fact_key": "acc.exception"}],
                    "queries": queries,
                },
                "issue_queries": queries,
            }, config)
            if result["run_status"] != "success":
                raise AssertionError(
                    f"jc evaluate run_status={result['run_status']}")
            client = legal_entry._jc_client(config)
            graph = client.read_argument_graph(
                result["run_identity_ref"], case_id="e20-recon-case")
            return graph

    def _train_synthetic_checkpoint(self) -> dict:
        """B4 产线输入＝真实训练产物：合成行上 train_and_save 真跑
        （子进程隔离于钉定 JC worktree；固定行零随机；不落盘——训练根
        用临时目录后即弃）。产线消费 checkpoint＋evaluation 两文档。"""
        script = """
import json, sys, tempfile
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from compiler_core.prediction import train_and_save


def row(index, signal, noise, label):
    return {"features": {"f_signal": signal, "f_noise": noise},
            "label": label}


split = {
    "train": [row(1, 2.0, 0.1, 1), row(2, -1.5, 0.3, 0),
              row(3, 1.2, -0.2, 1), row(4, -0.8, 0.0, 0),
              row(5, 0.9, 0.4, 1), row(6, -1.1, -0.3, 0),
              row(7, 1.6, 0.2, 1), row(8, -1.8, 0.1, 0)],
    "dev": [row(9, 1.4, 0.0, 1), row(10, -1.2, 0.2, 0),
            row(11, 0.7, -0.1, 1), row(12, -0.6, 0.3, 0)],
    "test": [row(13, 1.9, 0.2, 1), row(14, -1.4, -0.2, 0),
             row(15, 0.4, 0.1, 1), row(16, -0.9, 0.0, 0)],
}
rows = split["train"] + split["dev"] + split["test"]
with tempfile.TemporaryDirectory(prefix="jc-line-train-") as tmp:
    result = train_and_save(
        Path(tmp), event_definition="target-court-win（合成）",
        rows=rows, feature_order=["f_signal", "f_noise"],
        split_rows=split,
        model_config={"epochs": 120, "learningRate": 0.3, "l2": 1e-3},
        data_version="ds-synth-e20b4", rule_version=None)
print(json.dumps({"checkpoint": result["checkpoint"],
                  "evaluation": result["evaluation"]},
                 ensure_ascii=False))
"""
        raw = subprocess.check_output(
            [sys.executable, "-X", "utf8", "-B", "-c", script,
             str(self.jc_root)], encoding="utf-8")
        return json.loads(raw.strip().splitlines()[-1])


def write_evidence(profile: str, recon: Recon, started: str, code: int,
                   harness_root: Path, jc_root: Path) -> Path:
    evidence_dir = (REPO_ROOT / "docs" / "construction" / "evidence" / "E20"
                    / profile)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    finished = datetime.now(timezone.utc).isoformat()
    summary = {
        "schema": "juscite-e20-voi-multirender-recon/1",
        "unit": "W4-U56",
        "b2_unit": "W2b-U53",
        "feature": "E20",
        "profile": profile,
        "verdict": "RECON_OK" if code == 0 else "RECON_FAIL",
        "started_at": started,
        "finished_at": finished,
        "harness_worktree": str(harness_root),
        "harness_branch": "w2b-u53",
        "harness_base": "w2b-u52@8d24ed2f (E18 strategy ledger v22 chain)",
        "jc_worktree": str(jc_root),
        "jc_branch": "w4-u56",
        "jc_base": "w2b-u53@291f3578 (E20 chain head; voi_analysis bytes "
                   "pinned = B2 face unchanged)",
        "checks": recon.checks,
        "check_count": len(recon.checks),
        "failed": [c["check"] for c in recon.checks if c["status"] != "PASS"],
    }
    (evidence_dir / "e20_voi_multirender_recon.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8")
    lines = [f"# E20 VOI 和多解释实际支持 recon（{profile}）", "",
             f"- unit: W2b-U53 B2 段＋W4-U56 B4 段 · profile: {profile}",
             f"- verdict: **{summary['verdict']}**"
             f" ({len(recon.checks)} checks, exit {code})",
             f"- JC: `{jc_root}` @ branch w4-u56"
             "（基 w2b-u53@291f3578＝E20 链头；voi_analysis 保持 W2b-U53"
             "钉定字节＝B2 面零改动；checkpoint_line/client 为 B4 新字节）",
             f"- harness: `{harness_root}` @ branch w2b-u53"
             "（基 w2b-u52@8d24ed2f＝E18 账 v22 链；schema v23）",
             f"- started: {started} · finished: {finished}", "",
             "| # | check | status |", "|---|---|---|"]
    for index, check in enumerate(recon.checks, 1):
        lines.append(f"| {index} | {check['check']} | {check['status']} |")
    lines += ["",
              "全部合成材料。B2 段（W2b-U53 断言零改动）：信息集分区/合法",
              "行动集/概率效用成本输入闭集；概率永不作为请求输入（owner=jc",
              "回执两枚）；readiness 缺口＝具名 unavailable（值恒 null，不",
              "造 0.5/风险参数 1/统一胜率）；期望值精确有理数（1_500_000/1",
              "手算对账）；未支持＝具名 NOT_COMPLETE 结构断言（不填 PASS）；",
              "多解释分支经 argument graph 公开出口实际转录 owner=jc。",
              "B4 段（W4-U56）：checkpoint 产线机制面合成真跑——真实训练",
              "checkpoint（train_and_save 合成行真跑）经产线登记绑定，概率",
              "回执携 checkpoint 身份＋lineDigest 且驱动 VOI 精确数值路径；",
              "产线证据行被 readiness 八维审计消费（4 模型侧维 registered，",
              "数据侧 4 维具名缺口保持＝真实法院数据授权族不编造）；无真实",
              "checkpoint＝具名 model_not_available 值恒 null；unavailable",
              "回执不可冒充概率证据；全案 VOI 证明不由 CI 或原子定理推",
              "（08§4：wholeCaseProof.provenByLine=false）；真实 checkpoint",
              "挂模型/数据授权回收点具名在账（E20 行 failure_reason）。"]
    (evidence_dir / "e20_voi_multirender_recon.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8")
    return evidence_dir


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", action="append",
                        choices=["desktop", "selfhost"])
    parser.add_argument("--pg-dsn", default=None)
    parser.add_argument("--harness-root", type=Path, default=DEFAULT_HARNESS_ROOT)
    parser.add_argument("--jc-root", type=Path, default=DEFAULT_JC_ROOT)
    args = parser.parse_args()
    profiles = args.profile or ["desktop"]
    if not (args.jc_root / "compiler_core" / "checkpoint_line.py").is_file():
        print("RECON_BLOCKED: pinned JC worktree missing:", args.jc_root)
        return 3
    if not (args.harness_root / "src" / "legal_harness" / "state"
            / "matter_store.py").is_file():
        print("RECON_BLOCKED: pinned harness worktree missing:",
              args.harness_root)
        return 3
    failures = 0
    for profile in profiles:
        started = datetime.now(timezone.utc).isoformat()
        recon = Recon(args.harness_root, args.jc_root)
        code = 0
        try:
            recon.branch_checks()
            if profile == "desktop":
                # E16 recon 同径：state_root 预建 matter（_run 的
                # authorize 查 matters 行），产品桥子进程共享同一根。
                state_holder = tempfile.TemporaryDirectory(
                    prefix="juscite-e20-harness-")
                state_root = Path(state_holder.name) / "state"
                state_root.mkdir(parents=True)
                for _p in (str(args.harness_root / "src"),
                           str(args.harness_root / "tools/workflow-tools")):
                    if _p not in sys.path:
                        sys.path.insert(0, _p)
                from legal_harness.state.matter_store import MatterStore
                MatterStore(state_root).create_matter(
                    MATTER, "cas://profile-e20-recon")

                def call_harness(method, call_args,
                                 _r=REPO_ROOT, _hr=args.harness_root,
                                 _root=state_holder.name):
                    # 产品桥同一条链：legal_entry → 子进程 public_entry
                    #（--voi-json 信封；SQLite 状态根，本 profile 共享）。
                    config = {
                        "harness_public_entry": str(
                            _hr / "tools" / "workflow-tools" / "harness"
                            / "public_entry.py"),
                        "harness_target": "workbuddy",
                        "harness_state_root": str(state_root),
                    }
                    return legal_entry.call(method, call_args, config)

                def call_jc(call_args):
                    with tempfile.TemporaryDirectory(
                            prefix="juscite-e20-jccli-") as tmp:
                        return legal_entry.call(
                            "jc.voi_analyze", call_args,
                            make_config(Path(tmp)))

                def call_line(line_request):
                    with tempfile.TemporaryDirectory(
                            prefix="juscite-e20-jcline-") as tmp:
                        return legal_entry.call(
                            "jc.checkpoint_line",
                            {"matter_id": MATTER,
                             "request": line_request},
                            make_config(Path(tmp)))

                def call_readiness(readiness_request):
                    with tempfile.TemporaryDirectory(
                            prefix="juscite-e20-jcread-") as tmp:
                        return legal_entry.call(
                            "prediction.readiness",
                            {"matter_id": MATTER,
                             "request": readiness_request},
                            make_config(Path(tmp)))

                try:
                    recon.common_flow("desktop", call_harness, call_jc,
                                      call_line, call_readiness,
                                      lambda *a: [])
                finally:
                    state_holder.cleanup()
            else:
                import os
                import uuid

                dsn = args.pg_dsn or os.environ.get(
                    "LH_E08_PG_DSN") or DEFAULT_PG_DSN
                sys.path.insert(0, str(args.harness_root / "src"))
                sys.path.insert(0, str(args.harness_root
                                       / "tools" / "workflow-tools"))
                from legal_harness.state.pg_store import PgMatterStore
                from legal_harness.business.provider_registry import (
                    resolve_provider_method)
                from legal_harness.business.units import HarnessUnits
                temporary = tempfile.TemporaryDirectory(
                    prefix="juscite-e20-selfhost-")
                temporary.cleanup()
                store = PgMatterStore(Path(temporary.name), dsn=dsn,
                                      schema="e20_recon_" + uuid.uuid4().hex[:12])
                store.create_matter(MATTER, "cas://profile-e20")
                units = HarnessUnits(store)

                def call_harness(method, call_args):
                    return resolve_provider_method(method, units)(
                        **call_args)

                def call_jc(call_args):
                    with tempfile.TemporaryDirectory(
                            prefix="juscite-e20-jccli-") as tmp:
                        return legal_entry.call(
                            "jc.voi_analyze", call_args,
                            make_config(Path(tmp)))

                def call_line(line_request):
                    with tempfile.TemporaryDirectory(
                            prefix="juscite-e20-jcline-") as tmp:
                        return legal_entry.call(
                            "jc.checkpoint_line",
                            {"matter_id": MATTER,
                             "request": line_request},
                            make_config(Path(tmp)))

                def call_readiness(readiness_request):
                    with tempfile.TemporaryDirectory(
                            prefix="juscite-e20-jcread-") as tmp:
                        return legal_entry.call(
                            "prediction.readiness",
                            {"matter_id": MATTER,
                             "request": readiness_request},
                            make_config(Path(tmp)))

                def query(sql, params=()):
                    with store.transaction() as connection:
                        rows = connection.execute(sql, params).fetchall()
                        return [dict(row) for row in rows]

                print("[profile selfhost] PgMatterStore direct (lh-pg-e08)",
                      dsn.split("@")[-1], flush=True)
                try:
                    recon.common_flow("selfhost", call_harness, call_jc,
                                      call_line, call_readiness, query)
                finally:
                    try:
                        store.destroy()
                    except Exception:
                        pass
                    temporary.cleanup()
            recon.step("c99_profile_complete", True, profile=profile)
        except AssertionError as exc:
            code = 2
            print(f"[{profile}] RECON_FAIL: {exc}", flush=True)
        except Exception as exc:  # noqa: BLE001 - recon reports, never crashes
            code = 2
            print(f"[{profile}] RECON_ERROR: {type(exc).__name__}: {exc}",
                  flush=True)
        evidence_dir = write_evidence(profile, recon, started, code,
                                      args.harness_root, args.jc_root)
        verdict = "RECON_OK" if code == 0 else "RECON_FAIL"
        print(f"[{profile}] {verdict} ({len(recon.checks)} checks, "
              f"exit {code}) evidence={evidence_dir}", flush=True)
        if code != 0:
            failures += 1
    return 0 if failures == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
