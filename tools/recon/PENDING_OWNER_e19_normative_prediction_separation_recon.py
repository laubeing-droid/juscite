# -*- coding: utf-8 -*-
"""E19 参考/经验/预测隔离 验收对账（W2b-U27 B2 段＋W4-U55 B4 段）——双 profile。

07 E19（B2 段 deps E15/E22＋B4 段 W4-U55）＋04§1/§8＋裁决#8-12（真实法院
数据=授权族，统一负测先行）：
规范理由与经验总体/预测样本用途分离（法院材料不因 normative 用途自动
并入 prediction 样本——显式 admission 也只对样本用途材料开放）；
时间/辖区迁移校准/泄漏缺失范围如实登记（八维证据缺一即具名缺口，
预测 unknown，回执永不携带概率）；检索分非胜率（盖戳＋塞概率字段
typed 拒）；无模型不造概率（默认 50%/风险参数 1/法院「统一胜率」
三种编造形态一律拒收；真实 checkpoint 面无模型＝model_not_available）。

B4 段（W4-U55）：时间/辖区迁移校准的计算框架真跑（合成数据全管线
可跑，逐箱精确有理数诊断，同输入同回执字节＝证据可复现）；出处闭集
显式——synthetic_mechanism_demo 回执盖 usableAsRealCalibrationEvidence
=false（合成校准回执永不清除真实目标法院 readiness 的迁移/校准两维
证据）；authorized_real_court_data 无非空 authorizationRef 即
real_court_data_authorization_missing typed 拒（fail-closed 不编造）；
回执 probability 恒 null。真实法院数据未授权＝readiness 面保持具名
缺口（missingScopes 列时间/辖区迁移校准）＋八维证据缺一即 unavailable
结构不变；授权后补实测回收点具名写回台账 E19 行（本工具核其在账）。

对账对象：JC 仓分支 w4-u55（基于 w2b-u27@ac6209b＝E19 链头；
compiler_core/calibration_transfer.py 新增＋client.py 四公开方法，
sha256 钉定漂移响亮拒；prediction_separation.py 保持 W2b-U27 钉定
字节不动＝B2 面零改动）；cases 仓（legal-cn-cases，lcr 公开面）
**只读引用零改动**——lcr/public_facade.py sha256 钉定＋git 工作树干净
亲验＋检索分非胜率/非总体样本标记源级核对。产品经 legal_entry 冻结
方法组 prediction.{declare,readiness,retrieval_guard,calibration_transfer}
（P01 JCClient 同域 config）。全部合成材料；不发网络；不写 %APPDATA%。

分段：
  S1 用途分离（声明闭集/三用途计数/声明面永不产出样本成员资格/
     分离计数 4 声明 1 入样/normative 显式 admission 拒/缺
     admittedRowIds 拒＝无隐式全量入样）
  S2 readiness 缺口如实（八维全缺具名/部分证据残缺口/证据齐全仍
     无概率＋真实无模型 predict→model_not_available）
  S3 编造形态三拒（默认 0.5/风险参数 1/统一胜率）
  S4 检索分非胜率（原样保留＋盖戳/winRate 塞值拒/浮点拒/
     cases 只读锚：lcr sha＋树干净＋notAPopulationSample 标记在源）
  S5 桥负向（未配置 exit 3/未知方法 not_connected/方法组冻结）
  S6 B4 校准机制面（合成真跑精确诊断/两跑同字节/未授权具名拒/
     出处闭集拒/winRate 塞值拒/浮点拒/合成回执不清除 readiness
     两维缺口/回收点在账）

用法（juscite worktree w4-u55 根 cwd）：
  python -X utf8 tools/recon/PENDING_OWNER_e19_normative_prediction_separation_recon.py \
      --profile desktop --profile selfhost

exit 0＝全部 profile RECON_OK；2＝RECON_FAIL；3＝环境缺失。证据 JSON＋MD
写 docs/construction/evidence/E19/<profile>/。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LEGAL_ENTRY = REPO_ROOT / "implementation" / "python" / "legal_entry.py"
EVIDENCE_ROOT = REPO_ROOT / "docs" / "construction" / "evidence"
LEDGER = REPO_ROOT / "docs" / "construction" / "acceptance-ledger.csv"

JC_REPO = Path(
    r"D:\Codex\1.法律工作区\juris-calculus工作区\juris-calculus\.local\worktrees\w4-u55")
JC_SEPARATION_SHA256 = "043605c6622959c053be3d70d3ebe3826c36b214ad617ed0b3da42b7f9ceb593"
JC_CALIBRATION_SHA256 = "2c4a8b9af1d981feaf1b7380bc77b704090fae470002a144379e573fb176053c"
JC_CLIENT_SHA256 = "3743ff49355bc22d64b330d5d3cb4b1f7f4cd7f45aaa1c6c123eeb48090f05c9"

CASES_REPO = Path(
    r"D:\Codex\1.法律工作区\legal-cn-cases工作区\legal-cn-cases")
CASES_LCR_FACADE_SHA256 = (
    "38c1959c30412192e6abd71ad683f4cc285ae9e4d9bfaeee7d4ca78cea61942f")

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
         "governing_law": "acceptance-statute", "source_id": "acceptance-statute",
         "modality": "OBLIGATION",
         "premises": [{"fact_key": "acc.contract", "required": True}],
         "conclusion": {"value": "applies"},
         "effective_from": "2020-01-01T00:00:00Z"},
    ],
}

DIMENSIONS = ("sample_selection", "label_definition", "time_window",
              "case_family", "time_migration_calibration",
              "jurisdiction_migration_calibration", "calibration_report",
              "leakage_audit")

RECORDS = [
    {"materialId": "m-norm-local", "jurisdiction": "ZJ", "courtId": "H01",
     "courtLevel": "first", "decisionDate": "2024-05-01",
     "sourceTier": "local_court",
     "factualDifference": "合成：无书面合同",
     "declaredUse": "normative_reference", "datasetVersion": "ds-synth-1"},
    {"materialId": "m-norm-supreme", "jurisdiction": "SC", "courtId": "SPC",
     "courtLevel": "retrial", "decisionDate": "2023-11-11",
     "sourceTier": "supreme_guidance",
     "factualDifference": "合成：程序阶段不同",
     "declaredUse": "normative_reference", "datasetVersion": "ds-synth-1"},
    {"materialId": "m-emp-neighbor", "jurisdiction": "JS", "courtId": "H02",
     "courtLevel": "second", "decisionDate": "2023-01-15",
     "sourceTier": "neighboring_province",
     "factualDifference": "合成：辖区不同",
     "declaredUse": "empirical_population", "datasetVersion": "ds-synth-1"},
    {"materialId": "m-samp", "jurisdiction": "ZJ", "courtId": "H01",
     "courtLevel": "first", "decisionDate": "2024-06-01",
     "sourceTier": "local_court",
     "factualDifference": "合成：损失认定同构",
     "declaredUse": "prediction_sample", "datasetVersion": "ds-synth-1"},
]

FRAME = {
    "sampleFrameId": "sf-synth-1", "targetCourt": "H01",
    "targetJurisdiction": "ZJ", "caseFamily": "买卖合同纠纷（合成）",
    "labelDefinition": "一审全部诉请获支持（合成标签）",
    "timeWindowStart": "2023-01-01", "timeWindowEnd": "2024-12-31",
    "datasetVersion": "ds-synth-1", "admittedRowIds": ["m-samp"],
}

TARGET = {"targetCourt": "H01", "targetJurisdiction": "ZJ",
          "evaluationTime": "2026-10-16"}

# W4-U55 B4 段合成校准请求（全合成行；预测分为十进制文本＝formal V4
# 禁浮点；出处闭集显式 synthetic_mechanism_demo）。
CAL_REQUEST = {
    "sampleFrameId": "sf-synth-b4", "targetCourt": "H01",
    "targetJurisdiction": "ZJ", "caseFamily": "买卖合同纠纷（合成）",
    "datasetVersion": "ds-synth-b4",
    "rows": [
        {"rowId": "r-1", "predictedScore": "0.8", "observedLabel": 1,
         "decisionDate": "2023-06-01", "jurisdiction": "ZJ"},
        {"rowId": "r-2", "predictedScore": "0.4", "observedLabel": 0,
         "decisionDate": "2023-06-02", "jurisdiction": "ZJ"},
        {"rowId": "r-3", "predictedScore": "0.6", "observedLabel": 1,
         "decisionDate": "2024-06-01", "jurisdiction": "JS"},
        {"rowId": "r-4", "predictedScore": "0.2", "observedLabel": 0,
         "decisionDate": "2024-06-02", "jurisdiction": "JS"},
    ],
    "timeBins": [
        {"binId": "t-2023", "start": "2023-01-01", "end": "2023-12-31"},
        {"binId": "t-2024", "start": "2024-01-01", "end": "2024-12-31"},
    ],
    "jurisdictionBins": [
        {"binId": "j-target", "jurisdictions": ["ZJ"]},
        {"binId": "j-neighbour", "jurisdictions": ["JS"]},
    ],
    "dataProvenance": "synthetic_mechanism_demo",
}


class Checks:
    def __init__(self):
        self.items: list[dict] = []

    def add(self, check_id: str, ok: bool, detail: str) -> bool:
        self.items.append({"id": check_id,
                           "status": "PASS" if ok else "FAIL",
                           "detail": detail})
        print("[%s] %s — %s" % ("PASS" if ok else "FAIL", check_id, detail),
              flush=True)
        return ok

    @property
    def all_passed(self):
        return all(i["status"] == "PASS" for i in self.items)

    @property
    def passed_count(self):
        return sum(i["status"] == "PASS" for i in self.items)


def call_cli(method: str, args: dict, config: dict):
    """真产品入口子进程径（legal_entry CLI；同 F64/F69/E21 recon 纪律）。"""
    with tempfile.TemporaryDirectory() as tmp:
        req = Path(tmp) / "request.json"
        conf = Path(tmp) / "config.json"
        req.write_text(json.dumps({"method": method, "args": args},
                                  ensure_ascii=False), encoding="utf-8")
        conf.write_text(json.dumps(config, ensure_ascii=False),
                        encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", str(LEGAL_ENTRY),
             "--request-json", str(req), "--config", str(conf)],
            capture_output=True, text=True, encoding="utf-8", timeout=300)
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            payload = {"status": "RAW", "stdout": proc.stdout[:400]}
        return proc.returncode, payload


def make_config(workspace: Path) -> dict:
    rules = workspace / "rules"
    rules.mkdir(parents=True, exist_ok=True)
    (rules / "jc-local-pack.json").write_text(
        json.dumps(RULE_PACK, ensure_ascii=False), encoding="utf-8")
    return {
        "jc_state_root": str(workspace / "state"),
        "jc_rule_roots": [str(rules)],
        "jc_import_path": str(JC_REPO),
    }


def _all_evidence():
    return {d: {"evidenceId": f"ev-{d}", "note": "合成证据引用"}
            for d in DIMENSIONS}


def expect_owner(checks: Checks, cid: str, method: str, args: dict,
                 config: dict):
    code, out = call_cli(method, args, config)
    ok = code == 0 and out.get("status") == "OWNER_RESPONSE"
    checks.add(cid, ok, f"{method} -> exit {code} {out.get('status', '')}")
    return out.get("result", {}) if ok else {}


def expect_typed_failure(checks: Checks, cid: str, method: str, args: dict,
                         config: dict, code_fragment: str):
    code, out = call_cli(method, args, config)
    ok = (code == 4 and out.get("status") == "JC_FAILURE"
          and code_fragment in str(out.get("code", "")))
    checks.add(cid, ok, f"{method} typed refusal {code_fragment} -> exit "
                        f"{code} {str(out.get('code', ''))[:120]}")


def jc_no_model_check(checks: Checks, config: dict):
    """真实 JC checkpoint 面无模型＝model_not_available（in-process 真调）。"""
    sys.path.insert(0, str(REPO_ROOT / "implementation" / "python"))
    if str(JC_REPO) not in sys.path:
        sys.path.insert(0, str(JC_REPO))
    for name in [m for m in list(sys.modules)
                 if m == "compiler_core" or m.startswith("compiler_core.")]:
        del sys.modules[name]
    import legal_entry  # noqa: E402
    from compiler_core.client import ClientV4Error  # noqa: E402
    client = legal_entry._jc_client(config)
    try:
        client.predict_outcome({"eventDefinition": "target-court-win",
                                "observationPoint": "filing"})
        checks.add("E19-C08b", False,
                   "predict_outcome without a model returned a value")
    except ClientV4Error as error:
        checks.add("E19-C08b", error.code == "model_not_available",
                   f"predict_outcome no-model -> {error.code}")


def cases_readonly_anchor(checks: Checks):
    """cases 仓只读锚：lcr sha 钉定＋工作树干净＋检索分非胜率标记在源。"""
    facade = CASES_REPO / "lcr" / "public_facade.py"
    if not facade.is_file():
        checks.add("E19-C12", False, f"cases repo missing at {CASES_REPO}")
        return
    sha = hashlib.sha256(facade.read_bytes()).hexdigest()
    sha_ok = sha == CASES_LCR_FACADE_SHA256
    dirty = subprocess.run(
        ["git", "-C", str(CASES_REPO), "status", "--porcelain"],
        capture_output=True, text=True).stdout.strip()
    clean_ok = dirty == ""
    source = facade.read_text(encoding="utf-8")
    markers_ok = ("'notAPopulationSample': True" in source
                  and "'jcVerified': False" in source
                  and "'promoteToVerifiedFact': False" in source)
    checks.add("E19-C12", sha_ok and clean_ok and markers_ok,
               f"lcr/public_facade.py sha {sha[:16]}… pinned={sha_ok}; "
               f"cases worktree clean={clean_ok}; "
               f"notAPopulationSample/jcVerified=False/"
               f"promoteToVerifiedFact=False markers in source={markers_ok}")


def run_profile(profile: str, workspace_root: Path) -> Checks:
    checks = Checks()
    workspace = workspace_root / profile
    workspace.mkdir(parents=True, exist_ok=True)
    config = make_config(workspace)

    # ---- pins ------------------------------------------------------------
    if not (JC_REPO / "compiler_core" / "calibration_transfer.py").is_file():
        checks.add("E19-PIN-0", False, f"JC worktree missing at {JC_REPO}")
        return checks
    pins_ok = all(
        hashlib.sha256((JC_REPO / rel).read_bytes()).hexdigest() == want
        for rel, want in (
            ("compiler_core/prediction_separation.py", JC_SEPARATION_SHA256),
            ("compiler_core/calibration_transfer.py", JC_CALIBRATION_SHA256),
            ("compiler_core/client.py", JC_CLIENT_SHA256)))
    branch = subprocess.run(
        ["git", "-C", str(JC_REPO), "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True, text=True).stdout.strip()
    checks.add("E19-PIN-0", pins_ok and branch == "w4-u55",
               f"JC w4-u55 worktree sha256 三钉定（prediction_separation 保持 "
               f"W2b-U27 字节＝B2 面零改动＋calibration_transfer 新增＋client） "
               f"branch={branch}")

    # ---- S1 use separation ----------------------------------------------
    declare = expect_owner(checks, "E19-C01", "prediction.declare",
                           {"matterId": "m-e19-recon", "records": RECORDS},
                           config)
    checks.add("E19-C01b",
               declare.get("declaredCount") == 4
               and declare.get("useCounts") == {
                   "normative_reference": 2, "empirical_population": 1,
                   "prediction_sample": 1}
               and declare.get("declaresSampleMembership") is False
               and declare.get("declarationRef", {}).get("owner") == "jc",
               "declare：三用途计数＋声明面永不产出样本成员资格＋ref owner=jc")

    ready_args = {"matterId": "m-e19-recon",
                  "request": {"frame": FRAME, "records": RECORDS,
                              "target": TARGET, "evidence": _all_evidence()}}
    ready = expect_owner(checks, "E19-C02", "prediction.readiness",
                         ready_args, config)
    separation = ready.get("separation", {})
    checks.add("E19-C02b",
               separation.get("declaredCount") == 4
               and separation.get("admittedSampleRowCount") == 1
               and separation.get("declaredNotInSample") == 3
               and separation.get("normativeUseNeverAutoAdmitted") is True,
               "分离计数：4 声明 1 入样 3 不在样本（normative/经验不并入）")

    expect_typed_failure(
        checks, "E19-C03", "prediction.readiness",
        {"matterId": "m-e19-recon",
         "request": {"frame": dict(FRAME, admittedRowIds=["m-norm-local"]),
                     "records": RECORDS, "target": TARGET,
                     "evidence": _all_evidence()}},
        config, "prediction_admission_use_conflict")

    frame_no_ids = dict(FRAME)
    del frame_no_ids["admittedRowIds"]
    expect_typed_failure(
        checks, "E19-C04", "prediction.readiness",
        {"matterId": "m-e19-recon",
         "request": {"frame": frame_no_ids, "records": RECORDS,
                     "target": TARGET, "evidence": _all_evidence()}},
        config, "prediction_frame_required:admittedRowIds")

    expect_typed_failure(
        checks, "E19-C05", "prediction.declare",
        {"matterId": "m-e19-recon",
         "records": [dict(RECORDS[0], winProbabilityHint="0.9")]},
        config, "reference_fields_not_closed")

    # ---- S2 readiness gaps ------------------------------------------------
    gaps = expect_owner(checks, "E19-C06", "prediction.readiness",
                        {"matterId": "m-e19-recon",
                         "request": {"frame": FRAME, "records": RECORDS,
                                     "target": TARGET, "evidence": {}}},
                        config)
    checks.add("E19-C06b",
               gaps.get("predictionKnown") is False
               and gaps.get("missingScopes") == list(DIMENSIONS)
               and gaps.get("probability") is None,
               "八维证据全缺＝具名缺口＋预测 unknown＋无概率")

    partial_ev = {"sample_selection": {"evidenceId": "ev-ss"},
                  "leakage_audit": {"evidenceId": "ev-la"}}
    partial = expect_owner(checks, "E19-C07", "prediction.readiness",
                           {"matterId": "m-e19-recon",
                            "request": {"frame": FRAME, "records": RECORDS,
                                        "target": TARGET,
                                        "evidence": partial_ev}},
                           config)
    residual = set(DIMENSIONS) - set(partial_ev)
    checks.add("E19-C07b",
               partial.get("predictionKnown") is False
               and set(partial.get("missingScopes") or []) == residual,
               "部分证据＝残缺六维具名（时间/辖区迁移/校准在缺口）")

    checks.add("E19-C08",
               ready.get("predictionKnown") is True
               and ready.get("missingScopes") == []
               and ready.get("probability") is None
               and ready.get("noModelNoProbability") is True,
               "证据齐全＝证据条件成立，回执仍无概率（概率须 checkpoint 面）")
    jc_no_model_check(checks, config)

    # ---- S3 fabrication shapes -------------------------------------------
    expect_typed_failure(
        checks, "E19-C09a", "prediction.readiness",
        {"matterId": "m-e19-recon",
         "request": {"frame": FRAME, "records": RECORDS,
                     "target": dict(TARGET, priorProbability="0.5"),
                     "evidence": _all_evidence()}},
        config, "probability_placeholder_refused")
    expect_typed_failure(
        checks, "E19-C09b", "prediction.readiness",
        {"matterId": "m-e19-recon",
         "request": {"frame": FRAME, "records": RECORDS,
                     "target": dict(TARGET, riskParameter="1"),
                     "evidence": _all_evidence()}},
        config, "probability_placeholder_refused")
    expect_typed_failure(
        checks, "E19-C09c", "prediction.readiness",
        {"matterId": "m-e19-recon",
         "request": {"frame": FRAME, "records": RECORDS,
                     "target": dict(TARGET, unifiedCourtRate="0.62"),
                     "evidence": _all_evidence()}},
        config, "probability_placeholder_refused")

    # ---- S4 retrieval score guard ----------------------------------------
    guard = expect_owner(checks, "E19-C10", "prediction.retrieval_guard", {
        "matterId": "m-e19-recon",
        "hits": [
            {"hitId": "h-1", "retrievalScore": "0.92",
             "canonicalDocId": "doc-1"},
            {"hitId": "h-2", "retrievalScore": "7"},
        ],
        "datasetVersion": "ds-synth-1", "indexVersion": "ix-synth-1",
    }, config)
    hits = guard.get("hits", [])
    checks.add("E19-C10b",
               guard.get("retrievalScoreUsableAsWinRate") is False
               and guard.get("probability") is None
               and len(hits) == 2
               and hits[0].get("retrievalScore") == "0.92"
               and hits[0].get("retrievalScoreIsNotWinRate") is True
               and hits[0].get("notAPopulationSample") is True
               and hits[0].get("probability") is None
               and guard.get("guardRef", {}).get("owner") == "jc",
               "检索分原样保留＋盖非胜率/非总体样本戳＋概率恒 null")

    expect_typed_failure(
        checks, "E19-C11", "prediction.retrieval_guard",
        {"matterId": "m-e19-recon",
         "hits": [{"hitId": "h-1", "retrievalScore": "0.92",
                   "winRate": "0.92"}]},
        config, "retrieval_score_used_as_win_rate")
    expect_typed_failure(
        checks, "E19-C11b", "prediction.retrieval_guard",
        {"matterId": "m-e19-recon",
         "hits": [{"hitId": "h-1", "retrievalScore": 12.5}]},
        config, "retrieval_score_invalid")
    cases_readonly_anchor(checks)

    # ---- S5 bridge negatives ---------------------------------------------
    code, out = call_cli("prediction.declare", {"records": RECORDS}, {})
    checks.add("E19-C13", code == 3 and out.get("status") == "NOT_CONNECTED",
               f"未配置 fail-closed exit {code} {out.get('code', '')[:80]}")
    code, out = call_cli("prediction.win_rate", {}, config)
    checks.add("E19-C14",
               code == 3 and "method_not_connected" in str(out.get("code", "")),
               f"未知方法 not_connected exit {code}")
    sys.path.insert(0, str(REPO_ROOT / "implementation" / "python"))
    import legal_entry  # noqa: E402
    checks.add("E19-C15",
               legal_entry.PREDICTION_SEPARATION_METHODS == frozenset({
                   "prediction.declare", "prediction.readiness",
                   "prediction.retrieval_guard",
                   "prediction.calibration_transfer"}),
               "方法组冻结 prediction.{declare,readiness,retrieval_guard,"
               "calibration_transfer}")

    # ---- S6 B4 calibration mechanism face (W4-U55) ------------------------
    cal = expect_owner(checks, "E19-B4-C01", "prediction.calibration_transfer",
                       {"matterId": "m-e19-recon", "request": CAL_REQUEST},
                       config)
    time_bins = cal.get("timeMigration", {}).get("bins", [])
    jur_bins = cal.get("jurisdictionMigration", {}).get("bins", [])
    exact_ok = (
        len(time_bins) == 2 and time_bins[0]["rowCount"] == 2
        and time_bins[0]["meanPredictedScore"] == {
            "numerator": 3, "denominator": 5, "isInteger": False}
        and time_bins[0]["observedFrequency"] == {
            "numerator": 1, "denominator": 2, "isInteger": False}
        and time_bins[0]["calibrationGap"] == {
            "numerator": -1, "denominator": 10, "isInteger": False}
        and jur_bins[0]["rowCount"] == 2
        and jur_bins[0]["meanPredictedScore"] == {
            "numerator": 3, "denominator": 5, "isInteger": False})
    checks.add("E19-B4-C01b",
               exact_ok
               and cal.get("schema_version") == "jc-calibration-transfer/1"
               and cal.get("calibrationTransferRef", {}).get("owner") == "jc",
               "合成校准真跑：逐箱精确有理数诊断（均值 3/5·频率 1/2·差 "
               "-1/10）＋回执 ref owner=jc")

    checks.add("E19-B4-C02",
               cal.get("syntheticMechanismDemo") is True
               and cal.get("realDataAuthorized") is False
               and cal.get("usableAsRealCalibrationEvidence") is False
               and cal.get("authorizationRef") is None
               and cal.get("probability") is None
               and cal.get("noModelNoProbability") is True,
               "合成回执盖不可用为真实校准证据戳＋概率恒 null（不造校准证据）")

    cal_again = expect_owner(checks, "E19-B4-C03",
                             "prediction.calibration_transfer",
                             {"matterId": "m-e19-recon",
                              "request": CAL_REQUEST},
                             config)

    def _core(receipt: dict) -> str:
        return json.dumps({key: value for key, value in receipt.items()
                           if not key.endswith("Ref")},
                          sort_keys=True, ensure_ascii=False)

    checks.add("E19-B4-C03b", _core(cal) == _core(cal_again),
               "两跑回执逐字节同（确定性＝证据可复现）")

    expect_typed_failure(
        checks, "E19-B4-C04", "prediction.calibration_transfer",
        {"matterId": "m-e19-recon",
         "request": dict(CAL_REQUEST,
                         dataProvenance="authorized_real_court_data")},
        config, "real_court_data_authorization_missing")
    expect_typed_failure(
        checks, "E19-B4-C05", "prediction.calibration_transfer",
        {"matterId": "m-e19-recon",
         "request": dict(CAL_REQUEST, dataProvenance="scraped_web_dump")},
        config, "calibration_provenance_invalid")
    expect_typed_failure(
        checks, "E19-B4-C06", "prediction.calibration_transfer",
        {"matterId": "m-e19-recon",
         "request": dict(CAL_REQUEST, rows=[
             dict(CAL_REQUEST["rows"][0], winRate="0.92")])},
        config, "probability_placeholder_refused")
    expect_typed_failure(
        checks, "E19-B4-C07", "prediction.calibration_transfer",
        {"matterId": "m-e19-recon",
         "request": dict(CAL_REQUEST, rows=[
             dict(CAL_REQUEST["rows"][0], predictedScore=0.75)])},
        config, "calibration_row_score_invalid")

    # 合成校准回执不是 readiness 证据：真实目标法院的迁移/校准两维
    # 维持具名缺口（八维证据缺一即 unavailable 结构不变）。
    evidence_without_calibration = {
        d: {"evidenceId": f"ev-{d}"} for d in DIMENSIONS
        if d not in ("time_migration_calibration",
                     "jurisdiction_migration_calibration")}
    residual_ready = expect_owner(
        checks, "E19-B4-C08", "prediction.readiness",
        {"matterId": "m-e19-recon",
         "request": {"frame": FRAME, "records": RECORDS, "target": TARGET,
                     "evidence": evidence_without_calibration}},
        config)
    checks.add("E19-B4-C08b",
               residual_ready.get("predictionKnown") is False
               and residual_ready.get("missingScopes") == [
                   "time_migration_calibration",
                   "jurisdiction_migration_calibration"]
               and residual_ready.get("probability") is None,
               "合成校准机制面不清除 readiness 迁移/校准两维＝具名缺口保持"
               "＋概率恒 null（缺一即 unavailable 结构不变）")

    # 授权后补实测回收点具名在账（台账 E19 行 failure_reason）。
    recovery_named = False
    if LEDGER.is_file():
        import csv  # noqa: E402
        with open(LEDGER, encoding="utf-8-sig", newline="") as handle:
            for row in csv.reader(handle):
                if row and row[0] == "E19":
                    reason = row[16] if len(row) > 16 else ""
                    recovery_named = ("B4" in reason and "授权后" in reason
                                      and "真实法院数据" in reason)
                    break
    checks.add("E19-B4-C09", recovery_named,
               "授权后补实测回收点具名写回 E19 行（B4＋真实法院数据＋授权后"
               "回收点在账 failure_reason）")
    return checks


def write_evidence(profile: str, checks: Checks, started: str,
                   code: int) -> Path:
    evidence_dir = EVIDENCE_ROOT / "E19" / profile
    evidence_dir.mkdir(parents=True, exist_ok=True)
    from datetime import datetime, timezone
    finished = datetime.now(timezone.utc).isoformat()
    summary = {
        "schema": "juscite-e19-normative-prediction-separation-recon/1",
        "unit": "W4-U55",
        "feature": "E19",
        "profile": profile,
        "verdict": "RECON_OK" if code == 0 else "RECON_FAIL",
        "started_at": started,
        "finished_at": finished,
        "jc_worktree": str(JC_REPO),
        "jc_branch": "w4-u55",
        "jc_base": "w2b-u27@ac6209b (E19 chain head)",
        "cases_repo": str(CASES_REPO),
        "checks": checks.items,
        "check_count": len(checks.items),
        "failed": [c["id"] for c in checks.items if c["status"] != "PASS"],
    }
    (evidence_dir / "e19_normative_prediction_separation_recon.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8")
    lines = [f"# E19 参考/经验/预测隔离 recon（{profile}）", "",
             f"- unit: W2b-U27 B2 段＋W4-U55 B4 段 · profile: {profile}",
             f"- verdict: **{summary['verdict']}**"
             f" ({len(checks.items)} checks, exit {code})",
             f"- JC: `{JC_REPO}` @ branch w4-u55"
             "（基 w2b-u27@ac6209b＝E19 链头；prediction_separation 保持 "
             "W2b-U27 钉定字节＝B2 面零改动）",
             f"- cases: `{CASES_REPO}` 只读引用零改动"
             "（lcr/public_facade.py sha 钉定＋工作树干净亲验）",
             f"- started: {started} · finished: {finished}", "",
             "| # | check | status |", "|---|---|---|"]
    for index, check in enumerate(checks.items, 1):
        lines.append(f"| {index} | {check['id']} | {check['status']} |")
    lines += ["",
              "全部合成材料；规范理由/经验总体/预测样本三用途分离结构性"
              "成立（声明面永不产出样本成员资格，normative 材料显式 "
              "admission 也拒）；八维证据缺口具名、回执永不携带概率；"
              "检索分盖非胜率戳；无模型＝model_not_available（真实 JC 面"
              "实测）。B4 段（W4-U55）：时间/辖区迁移校准计算框架合成数据"
              "真跑（逐箱精确有理数诊断，两跑回执逐字节同＝证据可复现）；"
              "synthetic_mechanism_demo 回执盖 usableAsRealCalibration"
              "Evidence=false——合成校准永不清除真实目标法院 readiness 的"
              "迁移/校准两维证据（缺一即 unavailable 结构不变）；"
              "authorized_real_court_data 无非空 authorizationRef 即 "
              "real_court_data_authorization_missing typed 拒（裁决#8-12 "
              "授权族 fail-closed 不编造）；真实法院数据未授权＝readiness "
              "面保持具名缺口＋probability 恒 null；授权后补实测回收点具名"
              "在账（E19 行 failure_reason）。"]
    (evidence_dir / "e19_normative_prediction_separation_recon.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8")
    return evidence_dir


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", action="append",
                        choices=["desktop", "selfhost"])
    args = parser.parse_args()
    profiles = args.profile or ["desktop"]
    if not (JC_REPO / "compiler_core" / "calibration_transfer.py").is_file():
        print("RECON_BLOCKED: pinned JC worktree missing:", JC_REPO)
        return 3
    if not (CASES_REPO / "lcr" / "public_facade.py").is_file():
        print("RECON_BLOCKED: cases repo missing:", CASES_REPO)
        return 3
    from datetime import datetime, timezone
    failures = 0
    for profile in profiles:
        started = datetime.now(timezone.utc).isoformat()
        with tempfile.TemporaryDirectory(prefix="juscite-e19-") as tmp:
            checks = run_profile(profile, Path(tmp))
        code = 0 if checks.all_passed else 2
        evidence_dir = write_evidence(profile, checks, started, code)
        verdict = "RECON_OK" if code == 0 else "RECON_FAIL"
        print(f"[{profile}] {verdict} ({checks.passed_count}/"
              f"{len(checks.items)} checks, exit {code}) "
              f"evidence={evidence_dir}", flush=True)
        if code != 0:
            failures += 1
    return 0 if failures == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
