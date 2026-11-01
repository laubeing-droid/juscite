# -*- coding: utf-8 -*-
"""F91 abstain 反修复＋operational 模式验收对账（PENDING_OWNER 版，工单
W4-U46）。

06 行 F91（v1.5；owner=product+harness）acceptance：「覆盖充分题可纠正
误拒答但重过闸；操作性材料整理仍输出且标边界」；preserved：「防 fail-
closed 被用户当『动不动拒绝用』」。

分段（全部断言走真产品入口 implementation/python/legal_entry.py 子进程
径＋harness public_entry 子进程径；材料全合成）：
  S1 拒答具名入账：理由闭集＋缺失输入必带（08§4 fail-closed 具名不空
     称）＋有账可查（list/read）＋重复 id 拒。
  S2 反修复正向（覆盖充分题可纠正误拒答）：纠正候选引用在本地法源真实
     命中（覆盖证据=逐条 W2a-U14 核验记录，不模型自评）→ 强制重过同一
     F87 闸（extraction.register→extraction.gate 同一路径凭据）→
     CORRECTED_DELIVERABLE（引用级；proposition_support 恒不代签）。
  S3 反修复 fail-closed 红线不松动：伪引文纠正→闸 REJECTED 不交付；
     未施行法纠正→UNKNOWN_FAIL_CLOSED 照样拒；闸拒事件如实入账。
  S4 覆盖充分性判定绑定可具名证据：零引用/虚构标题→COVERAGE_
     INSUFFICIENT（证据 face 具名 W2a-U14 verify_citation；不收自评主
     张）；纠正候选自带闸状态字段→具名拒（伪造已核未遂）。
  S5 operational 照常交付：操作性闭集任务不经法律闸产出＋『非法律结
     论』边界标记恒带＋同输入两跑同字节＋携带法律结论字段具名拒＋闭集
     外操作拒。
  S6 结构断言（AST＋闸账回查）：operational_deliver 函数体零法律闸调
     用；反修复面零第二核验算法定义；S2 纠正产物的闸凭据在 F87 闸账
     （extraction_gate_state_root/batches/<batch>.json）逐字段回查一致
     ——「纠正产物走同一 citation_gate/extraction_gate 路径」的物理证据。
  S7 harness 账本半边（legal-harness 战役分支 abstain_events v32，
     public_entry --abstain-json 子进程径）：全链事件入账回读＋账本级
     反修复负测（repair_gate_passed 无凭据拒/状态错配拒/operational 无
     边界标记拒）＋abstain_list 计数。
  S8 桥 fail-closed：缺 abstain_state_root → exit 3 具名 NOT_CONNECTED。

用法（juscite worktree w4-u46 根 cwd）：
  python -X utf8 tools/PENDING_OWNER_f91_abstain_operational_recon.py --profile desktop --profile selfhost

exit 0＝所请求全部 profile 断言全过（每 profile 各 RECON_OK）；证据
JSON 写 evidence/F91/<profile>/。只读消费，不发任何网络请求。
"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

RUN_DATE = time.strftime("%Y%m%d")
REPO_ROOT = Path(__file__).resolve().parents[1]
LEGAL_ENTRY = REPO_ROOT / "implementation" / "python" / "legal_entry.py"
ABSTAIN_MODULE = REPO_ROOT / "implementation" / "python" / "abstain_operational.py"

# harness 战役分支（A2 链）检出与 F91 面钉定
HARNESS_WORKTREE = Path(
    r"D:\Codex\1.法律工作区\legal-harness工作区\legal-harness-repo"
    r"\.local\worktrees\w4-u46")
HARNESS_PUBLIC_ENTRY = HARNESS_WORKTREE / Path(
    "tools/workflow-tools/harness/public_entry.py")
HARNESS_BRANCH = "w4-u46"
ABSTAIN_SURFACE = "abstain"

# 钉定公开面 v1.1（与 test_f87_extraction_gate_wiring 同钉定）
LCCC_PATH = Path(
    r"D:\Codex\1.法律工作区\legal-cn-core-codices工作区"
    r"\legal-cn-core-codices-repo\.local\worktrees\w2a-u14\lccc_consumer.py"
)
LCCC_SHA256 = (
    "55eea7c27e08d6b236b7ab7a83810c86ee0898c335c4668d875a492775db863a"
)

AS_OF = "20261016"
DOC_COLUMNS = ["WJBS", "BT", "GBRQ", "SXX", "DE_01018", "SXRQ", "SHXRQ",
               "DE_01001", "DE_01021"]
SYN_CUR = "中华人民共和国合成数据保护法"
SYN_QUOTE_ART1 = "为了规范合成数据处理活动，保护合成数据权益，制定本法。"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _body(date8: str, seq: str = "0001") -> str:
    return "0100" + "0000001001" + date8 + seq + "000" + "00"


def build_synthetic_formal_root(base: Path) -> Path:
    """合成 codices 正式面（现行＋已废止＋尚未施行；零真实法条内容）。"""
    root = base / "formal"
    root.mkdir(parents=True, exist_ok=True)
    docs = [
        (SYN_CUR, _body("20210820", "0091"), "01", "20211101", ""),
        ("中华人民共和国合成旧管理条例", _body("20150101"), "04",
         "20150601", "20200101"),
        ("中华人民共和国合成未来施行法", _body("20260626"), "02",
         "20270101", ""),
    ]
    with (root / "legal_documents.csv").open("w", encoding="utf-8-sig",
                                             newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(DOC_COLUMNS)
        for title, body, sxx, sxrq, shxrq in docs:
            writer.writerow(["1.2.156.3005.6-" + body, title, body[14:22],
                             sxx, sxx, sxrq, shxrq, body,
                             "国家法律法规数据库"])
    for name in ("legal_contents.csv", "legal_relations.csv",
                 "legal_sources.csv", "cases.csv",
                 "case_legal_references.csv", "case_holdings.csv",
                 "practice_references.csv"):
        (root / name).write_text("WJBS\n", encoding="utf-8-sig")
    cur_wjbs = "1.2.156.3005.6-" + _body("20210820", "0091")
    md_cur = (
        "---\nobject_type: \"legal_document\"\nidentifier: \"%s\"\n---\n\n"
        "# %s\n\n"
        "- **第一条**\u3000\u3000%s\n\n"
        "- **第二条**\u3000\u3000在中华人民共和国境内处理合成数据，适用本法。\n\n"
        "- **第三条**\u3000\u3000处理合成数据应当遵循合法、正当、必要原则。\n"
        % (cur_wjbs, SYN_CUR, SYN_QUOTE_ART1))
    (root / ("carrier_%s.md" % cur_wjbs)).write_text(md_cur,
                                                     encoding="utf-8")
    (root / "README.md").write_text("synthetic F91 recon face\n",
                                    encoding="utf-8")
    (root / "SHA256SUMS").write_text("synthetic\n", encoding="utf-8")
    return root


class Checks:
    def __init__(self) -> None:
        self.items: list = []

    def add(self, check_id: str, ok: bool, detail: str) -> None:
        self.items.append({"id": check_id, "ok": bool(ok),
                           "detail": detail})

    @property
    def passed_count(self) -> int:
        return sum(1 for item in self.items if item["ok"])

    @property
    def all_passed(self) -> bool:
        return bool(self.items) and all(item["ok"] for item in self.items)


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
    """harness public_entry --abstain-json 子进程径（账本半边）。"""
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
             "--abstain-json", command_handle.name, "--target", "opencode"],
            capture_output=True, text=True, encoding="utf-8", timeout=600,
            cwd=str(HARNESS_WORKTREE), env=env)
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            payload = {"_raw": (proc.stdout + proc.stderr)[-500:]}
        return {"exit": proc.returncode, "payload": payload}
    finally:
        os.unlink(command_handle.name)


def result_of(response: dict) -> dict:
    payload = response.get("payload", {})
    if isinstance(payload, dict):
        return payload.get("result") or {}
    return {}


def section_s1(checks: Checks, config: dict) -> None:
    r = call_entry("abstain.record",
                   {"abstain_id": "abs-s1", "reason": "UNKNOWN_KEY_INPUT",
                    "question_text": "本案违约金应如何计算（合成问题）",
                    "missing_inputs": ["as_of 时点"]}, config)
    result = result_of(r)
    checks.add("S1-record-named", r["exit"] == 0
               and result.get("reason") == "UNKNOWN_KEY_INPUT"
               and len(result.get("question_digest", "")) == 64,
               "exit=%s reason=%s digest64=%s" % (
                   r["exit"], result.get("reason"),
                   len(result.get("question_digest", "")) == 64))
    read = result_of(call_entry("abstain.read", {"abstain_id": "abs-s1"},
                                config))
    checks.add("S1-read-chain", read.get("events")
               and read["events"][0]["kind"] == "abstain_recorded",
               "events=%s" % len(read.get("events", [])))
    listing = result_of(call_entry("abstain.list", {}, config))
    checks.add("S1-list-queryable", listing.get("count", 0) >= 1,
               "count=%s" % listing.get("count"))
    bad = call_entry("abstain.record",
                     {"abstain_id": "abs-s1-bad", "reason": "模型觉得不会",
                      "question_text": "q"}, config)
    checks.add("S1-reason-closed-set", bad["exit"] == 3
               and "not_in_closed_set" in json.dumps(bad["payload"]),
               "exit=%s code=%s" % (bad["exit"],
                                    bad["payload"].get("code")))
    empty = call_entry("abstain.record",
                       {"abstain_id": "abs-s1-empty",
                        "reason": "UNKNOWN_KEY_INPUT", "question_text": "q",
                        "missing_inputs": []}, config)
    checks.add("S1-fail-closed-named-not-vacuous", empty["exit"] == 3
               and "missing_inputs_required_for_fail_closed"
               in json.dumps(empty["payload"]),
               "exit=%s code=%s" % (empty["exit"],
                                    empty["payload"].get("code")))


def section_s2(checks: Checks, config: dict, scratch: Path) -> None:
    call_entry("abstain.record",
                     {"abstain_id": "abs-s2", "reason": "GATE_REJECTED",
                      "question_text": "误拒答的题（合成）",
                      "missing_inputs": []}, config)
    r = call_entry("abstain.repair_submit",
                   {"abstain_id": "abs-s2",
                    "corrected_text": "依据《%s》第一条：“%s”"
                                      % (SYN_CUR, SYN_QUOTE_ART1),
                    "as_of": AS_OF}, config)
    result = result_of(r)
    coverage_ok = (result.get("coverage", {}).get("sufficient") is True
                   and any(item.get("identifier")
                           for item in result["coverage"]["evidence"])
                   and "verify_citation" in result["coverage"]["face"])
    gate_ok = (result.get("status") == "CORRECTED_DELIVERABLE"
               and result.get("gate_ref", {}).get("gateStatus")
               == "CITATION_VERIFIED"
               and result.get("gate_ref", {}).get("gateBatchId", "")
               .startswith("f91-")
               and "citation.verify" in result.get("gate_face", ""))
    deliverable = result.get("deliverable") or {}
    checks.add("S2-repair-coverage-named-evidence", coverage_ok,
               "sufficient=%s face=%s" % (
                   result.get("coverage", {}).get("sufficient"),
                   result.get("coverage", {}).get("face")))
    checks.add("S2-repair-repassed-same-gate", gate_ok,
               "status=%s gateBatch=%s gateFace=%s" % (
                   result.get("status"),
                   result.get("gate_ref", {}).get("gateBatchId"),
                   result.get("gate_face")))
    checks.add("S2-proposition-support-never-signed",
               deliverable.get("proposition_support")
               == "UNSIGNED_QUOTE_EXISTENCE_IS_NOT_PROPOSITION_SUPPORT",
               "proposition_support=%s"
               % deliverable.get("proposition_support"))
    # S6 物理证据前置：闸账回查数据暂存
    (scratch / "s2_gate_batch.json").write_text(json.dumps({
        "batch_id": result.get("gate_ref", {}).get("gateBatchId"),
        "run_seq": result.get("gate_ref", {}).get("gateRunSeq"),
        "candidate_id": result.get("gate_ref", {}).get("candidateId"),
    }, ensure_ascii=False), encoding="utf-8")


def section_s3(checks: Checks, config: dict) -> None:
    call_entry("abstain.record",
                     {"abstain_id": "abs-s3", "reason": "GATE_REJECTED",
                      "question_text": "纠错题（合成）",
                      "missing_inputs": []}, config)
    fake = result_of(call_entry(
        "abstain.repair_submit",
        {"abstain_id": "abs-s3",
         "corrected_text": "依据《%s》第一条：“凭空捏造的引文。”" % SYN_CUR,
         "as_of": AS_OF}, config))
    checks.add("S3-fake-quote-still-rejected-fail-closed",
               fake.get("status") == "REJECTED_GATE_FAIL_CLOSED"
               and fake.get("deliverable") is None
               and fake.get("gate_ref", {}).get("gateStatus") == "REJECTED",
               "status=%s deliverable=%s gateStatus=%s" % (
                   fake.get("status"), fake.get("deliverable") is None,
                   fake.get("gate_ref", {}).get("gateStatus")))
    future = result_of(call_entry(
        "abstain.repair_submit",
        {"abstain_id": "abs-s3",
         "corrected_text": "依据《中华人民共和国合成未来施行法》第一条",
         "as_of": AS_OF}, config))
    checks.add("S3-unknown-input-still-blocks-not-loosened",
               future.get("status") == "REJECTED_GATE_FAIL_CLOSED"
               and future.get("deliverable") is None,
               "status=%s" % future.get("status"))
    read = result_of(call_entry("abstain.read", {"abstain_id": "abs-s3"},
                                config))
    rejected_events = [e for e in read.get("events", [])
                       if e.get("kind") == "repair_gate_rejected"]
    checks.add("S3-gate-rejection-recorded-in-chain",
               len(rejected_events) == 2,
               "repair_gate_rejected=%d" % len(rejected_events))


def section_s4(checks: Checks, config: dict) -> None:
    call_entry("abstain.record",
                     {"abstain_id": "abs-s4",
                      "reason": "COVERAGE_INSUFFICIENT",
                      "question_text": "无覆盖题（合成）",
                      "missing_inputs": []}, config)
    no_ref = result_of(call_entry(
        "abstain.repair_submit",
        {"abstain_id": "abs-s4",
         "corrected_text": "这是没有引用的纠正主张（合成）。",
         "as_of": AS_OF}, config))
    fabricated = result_of(call_entry(
        "abstain.repair_submit",
        {"abstain_id": "abs-s4",
         "corrected_text": "依据《中华人民共和国合成月球管辖法》第一条",
         "as_of": AS_OF}, config))
    checks.add("S4-no-citable-reference-insufficient",
               no_ref.get("status") == "REPAIR_COVERAGE_INSUFFICIENT"
               and no_ref.get("coverage", {}).get("sufficient") is False,
               "status=%s" % no_ref.get("status"))
    checks.add("S4-fabricated-title-insufficient",
               fabricated.get("status") == "REPAIR_COVERAGE_INSUFFICIENT"
               and all(item.get("identifier") is None
                       for item in fabricated["coverage"]["evidence"]),
               "status=%s identifiers=%s" % (
                   fabricated.get("status"),
                   [item.get("identifier")
                    for item in fabricated["coverage"]["evidence"]]))
    checks.add("S4-evidence-face-named-not-self-assessed",
               "verify_citation" in fabricated["coverage"]["face"]
               and isinstance(fabricated["coverage"]["evidence"], list),
               "face=%s" % fabricated["coverage"]["face"])
    forged = call_entry(
        "abstain.repair_submit",
        {"abstain_id": "abs-s4", "corrected_text": "纠正（合成）",
         "as_of": AS_OF, "gate_status": "CITATION_VERIFIED"}, config)
    checks.add("S4-forged-gate-fields-refused", forged["exit"] == 3
               and "gate_fields_refused"
               in json.dumps(forged["payload"]),
               "exit=%s code=%s" % (forged["exit"],
                                    forged["payload"].get("code")))


def section_s5(checks: Checks, config: dict) -> None:
    text = "第一段　　有  空格。\n# 标题\n第二段。"
    first = call_entry("operational.deliver",
                       {"operation": "normalize", "text": text}, config)
    again = call_entry("operational.deliver",
                       {"operation": "normalize", "text": text}, config)
    r1, r2 = result_of(first), result_of(again)
    checks.add("S5-operational-delivers-unblocked", first["exit"] == 0
               and r1.get("boundary_mark") == "NON_LEGAL_CONCLUSION"
               and r1.get("gate_status") is None
               and "非法律结论" in r1.get("boundary_note", ""),
               "exit=%s boundary=%s gate_status=%s" % (
                   first["exit"], r1.get("boundary_mark"),
                   r1.get("gate_status")))
    checks.add("S5-deterministic-two-runs-identical",
               first["exit"] == 0 and again["exit"] == 0
               and r1.get("output_sha256") == r2.get("output_sha256")
               and r1.get("output") == r2.get("output"),
               "sha_equal=%s" % (r1.get("output_sha256")
                                 == r2.get("output_sha256")))
    split = result_of(call_entry(
        "operational.deliver",
        {"operation": "split_sections",
         "text": "# 甲节\n内容甲\n## 乙节\n内容乙"}, config))
    checks.add("S5-operations-closed-set",
               "甲节" in split.get("output", "")
               and split.get("boundary_mark") == "NON_LEGAL_CONCLUSION",
               "output_has_sections=%s" % ("甲节" in split.get("output", "")))
    bad_op = call_entry("operational.deliver",
                        {"operation": "give_legal_advice", "text": "x"},
                        config)
    checks.add("S5-operation-not-in-set-refused", bad_op["exit"] == 3
               and "not_in_closed_set" in json.dumps(bad_op["payload"]),
               "exit=%s" % bad_op["exit"])
    legal = call_entry("operational.deliver",
                       {"operation": "normalize", "text": "t",
                        "extra": {"gate_status": "CITATION_VERIFIED"}},
                       config)
    legal2 = call_entry("operational.deliver",
                        {"operation": "normalize", "text": "t",
                         "extra": {"legal_conclusion": "胜诉"}}, config)
    checks.add("S5-legal-conclusion-fields-refused",
               legal["exit"] == 3 and legal2["exit"] == 3
               and "legal_fields_refused" in json.dumps(legal["payload"])
               and "legal_fields_refused" in json.dumps(legal2["payload"]),
               "exit=%s/%s" % (legal["exit"], legal2["exit"]))


def section_s6(checks: Checks, config: dict, scratch: Path) -> None:
    source = ABSTAIN_MODULE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    op_clean = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) \
                and node.name == "operational_deliver":
            names = {n.id for n in ast.walk(node)
                     if isinstance(n, ast.Name)}
            op_clean = not (names & {"verify_citation", "parse_citations",
                                     "gate_run", "register"})
            break
    checks.add("S6-ast-operational-zero-legal-gate-calls",
               op_clean is True, "op_clean=%s" % op_clean)
    defined = {node.name for node in ast.walk(tree)
               if isinstance(node, ast.FunctionDef)}
    checks.add("S6-ast-repair-no-second-verifier",
               "verify_citation" not in defined
               and "parse_citations" not in defined
               and "from citation_verifier import" in source
               and "import extraction_gate" in source,
               "defined_local_verifiers=%s" % sorted(
                   defined & {"verify_citation", "parse_citations"}))
    # 闸账回查：S2 纠正产物凭据与 F87 闸账逐字段一致（同一物理路径证据）
    saved = json.loads((scratch / "s2_gate_batch.json").read_text(
        encoding="utf-8"))
    batch_id = saved["batch_id"]
    batch_path = (Path(config["extraction_gate_state_root"]) / "batches"
                  / (batch_id + ".json"))
    gate_ok = False
    detail = "batch_missing"
    if batch_path.is_file():
        batch = json.loads(batch_path.read_text(encoding="utf-8"))
        run = next((run for run in batch.get("gate_runs", [])
                    if run["run_seq"] == saved["run_seq"]), None)
        if run:
            match = next((res for res in run["results"]
                          if res["candidate_id"] == saved["candidate_id"]),
                         None)
            gate_ok = (match is not None
                       and match["gate_status"] == "CITATION_VERIFIED"
                       and run.get("verification_face", "")
                       .startswith("citation.verify"))
            detail = ("run=%s candidate=%s status=%s face=%s" % (
                saved["run_seq"], saved["candidate_id"],
                match["gate_status"] if match else None,
                run.get("verification_face")))
        else:
            detail = "run_missing"
    checks.add("S6-gate-ledger-cross-check-same-path", gate_ok, detail)
    face = sha256_file(LCCC_PATH)
    checks.add("S6-codices-face-pin-intact", face == LCCC_SHA256,
               "sha_match=%s" % (face == LCCC_SHA256))


def _key(request_id: str) -> dict:
    return {"requestId": request_id, "targetId": None,
            "expectedRevision": None, "inputRefs": []}


_MATTER_SCOPE = {"kind": "matter", "matterId": "m-f91-rec"}
_SYNTH_PROFILE_REF = {"owner": "harness", "kind": "profile", "id": "litigation",
                      "version": "1", "matterId": None, "digest": None}
_SYNTH_INTAKE_REF = {"owner": "harness", "kind": "intake", "id": "intake-f91",
                     "version": "1", "matterId": None, "digest": None}


def section_s7(checks: Checks, harness_state: Path) -> None:
    # 案件先建（abstain_events REFERENCES matters；合成 profile/intake ref）
    call_harness("harness.create_matter",
                 {"actor_id": "assistant-1", "scope": _MATTER_SCOPE,
                  "key": _key("matter-f91"),
                  "profile_ref": _SYNTH_PROFILE_REF,
                  "intake_ref": _SYNTH_INTAKE_REF}, harness_state)
    digest = "c" * 64
    gate_ref = {"gateBatchId": "f91-abs-s7-repair_001", "gateRunSeq": 1,
                "candidateId": "cand_0001", "gateStatus": "CITATION_VERIFIED"}
    boundary = "NON_LEGAL_CONCLUSION"
    r1 = call_harness("harness.abstain_event_record",
                      {"actor_id": "assistant-1", "scope": _MATTER_SCOPE,
                       "key": _key("k1"),
                       "event": {"abstainId": "abs-s7",
                                 "eventKind": "abstain_recorded",
                                 "questionDigest": digest,
                                 "payload": {"summary":
                                             "拒答具名（合成 recon）"}}},
                      harness_state)
    r2 = call_harness("harness.abstain_event_record",
                      {"actor_id": "assistant-1", "scope": _MATTER_SCOPE,
                       "key": _key("k2"),
                       "event": {"abstainId": "abs-s7",
                                 "eventKind": "repair_gate_passed",
                                 "questionDigest": digest,
                                 "payload": {"summary":
                                             "纠正重过闸通过（合成 recon）"},
                                 "gateRef": gate_ref}}, harness_state)
    r3 = call_harness("harness.abstain_event_record",
                      {"actor_id": "assistant-1", "scope": _MATTER_SCOPE,
                       "key": _key("k3"),
                       "event": {"abstainId": "abs-s7",
                                 "eventKind": "operational_delivered",
                                 "questionDigest": digest,
                                 "payload": {"summary":
                                             "操作性交付（合成 recon）"},
                                 "boundaryMark": boundary}}, harness_state)
    checks.add("S7-harness-full-chain-recorded",
               r1["exit"] == 0 and r2["exit"] == 0 and r3["exit"] == 0,
               "exits=%s/%s/%s" % (r1["exit"], r2["exit"], r3["exit"]))
    read = call_harness("harness.abstain_read",
                        {"scope": _MATTER_SCOPE, "abstain_id": "abs-s7"},
                        harness_state)
    kinds = [e.get("eventKind") for e in
             (read["payload"].get("result", {}).get("events") or [])] \
        if read["exit"] == 0 else []
    checks.add("S7-harness-chain-readback",
               kinds == ["abstain_recorded", "repair_gate_passed",
                         "operational_delivered"],
               "kinds=%s" % kinds)
    no_ref = call_harness("harness.abstain_event_record",
                          {"actor_id": "assistant-1",
                           "scope": _MATTER_SCOPE,
                           "key": _key("k4"),
                           "event": {"abstainId": "abs-s7-bad",
                                     "eventKind": "repair_gate_passed",
                                     "questionDigest": digest,
                                     "payload": {"summary":
                                                 "无凭据纠正（合成）"}}},
                          harness_state)
    checks.add("S7-harness-repair-requires-gate-ref",
               no_ref["exit"] != 0
               and "abstain_gate_ref_required"
               in json.dumps(no_ref["payload"]),
               "exit=%s err=%s" % (no_ref["exit"],
                                   json.dumps(no_ref["payload"])[:120]))
    wrong = call_harness("harness.abstain_event_record",
                         {"actor_id": "assistant-1",
                          "scope": _MATTER_SCOPE,
                          "key": _key("k5"),
                          "event": {"abstainId": "abs-s7-bad2",
                                    "eventKind": "repair_gate_passed",
                                    "questionDigest": digest,
                                    "payload": {"summary": "状态错配"},
                                    "gateRef": dict(
                                        gate_ref,
                                        gateStatus="REJECTED")}},
                         harness_state)
    no_mark = call_harness("harness.abstain_event_record",
                           {"actor_id": "assistant-1",
                            "scope": _MATTER_SCOPE,
                            "key": _key("k6"),
                            "event": {"abstainId": "abs-s7-bad3",
                                      "eventKind": "operational_delivered",
                                      "questionDigest": digest,
                                      "payload": {"summary": "无标记"}}},
                           harness_state)
    checks.add("S7-harness-gate-status-match-closed",
               wrong["exit"] != 0
               and "abstain_gate_passed_status_invalid"
               in json.dumps(wrong["payload"]),
               "exit=%s" % wrong["exit"])
    checks.add("S7-harness-operational-boundary-required",
               no_mark["exit"] != 0
               and "abstain_operational_boundary_required"
               in json.dumps(no_mark["payload"]),
               "exit=%s" % no_mark["exit"])
    listing = call_harness("harness.abstain_list",
                           {"scope": _MATTER_SCOPE}, harness_state)
    items = listing["payload"].get("result", {}).get("items") \
        if listing["exit"] == 0 else []
    checks.add("S7-harness-list-counts",
               listing["exit"] == 0 and len(items or []) == 1
               and (items or [{}])[0].get("events") == 3,
               "items=%s" % json.dumps(items))


def section_s8(checks: Checks) -> None:
    r = call_entry("abstain.record",
                   {"abstain_id": "abs-s8", "reason": "GATE_REJECTED",
                    "question_text": "q", "missing_inputs": []}, {})
    checks.add("S8-bridge-fail-closed-unconfigured",
               r["exit"] == 3
               and r["payload"].get("code")
               == "abstain_state_root_not_configured",
               "exit=%s code=%s" % (r["exit"], r["payload"].get("code")))


def run_profile(profile: str) -> tuple[Checks, dict]:
    with tempfile.TemporaryDirectory(prefix="f91-recon-") as scratch_name:
        scratch = Path(scratch_name)
        formal_root = build_synthetic_formal_root(scratch)
        config = {
            "abstain_state_root": str(scratch / "abstain-state"),
            "extraction_gate_state_root": str(scratch / "gate-state"),
            "codices_import_path": str(LCCC_PATH.parent),
            "codices_formal_root": str(formal_root),
            "codices_face_sha256": LCCC_SHA256,
        }
        checks = Checks()
        section_s1(checks, config)
        section_s2(checks, config, scratch)
        section_s3(checks, config)
        section_s4(checks, config)
        section_s5(checks, config)
        section_s6(checks, config, scratch)
        section_s7(checks, scratch / "harness-state")
        section_s8(checks)
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True,
        cwd=str(REPO_ROOT)).stdout.strip()
    harness_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True,
        cwd=str(HARNESS_WORKTREE)).stdout.strip()
    evidence = {
        "run_date": RUN_DATE,
        "unit": "W4-U46",
        "profile": profile,
        "command": "python -X utf8 tools/"
                   "PENDING_OWNER_f91_abstain_operational_recon.py "
                   "--profile %s" % profile,
        "cwd": str(REPO_ROOT),
        "subject_commit": commit,
        "harness": {
            "branch": HARNESS_BRANCH,
            "subject_commit": harness_commit,
            "public_entry": str(HARNESS_PUBLIC_ENTRY),
            "ledger": "abstain_events(schema v32)",
        },
        "frozen_face": {
            "lccc_consumer.py(E22 v1.1)": LCCC_SHA256,
            "abstain_operational.py": sha256_file(ABSTAIN_MODULE),
        },
        "checks": checks.items,
        "passed": checks.passed_count,
        "total": len(checks.items),
        "overall": "RECON_OK" if checks.all_passed else "RECON_FAIL",
    }
    out_dir = REPO_ROOT / "evidence" / "F91" / profile
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "recon-result.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=1),
        encoding="utf-8")
    print("---")
    print("RECON_%s %d/%d checks — profile=%s" % (
        "OK" if checks.all_passed else "FAIL",
        checks.passed_count, len(checks.items), profile))
    for item in checks.items:
        if not item["ok"]:
            print("  FAIL %s: %s" % (item["id"], item["detail"]))
    return checks, evidence


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", action="append",
                        choices=("desktop", "selfhost"), dest="profiles",
                        help="可重复：--profile desktop --profile selfhost")
    args = parser.parse_args()
    profiles = args.profiles or ["desktop"]

    if not LEGAL_ENTRY.is_file():
        print("FATAL: 产品入口缺 %s" % LEGAL_ENTRY)
        return 2
    if not LCCC_PATH.is_file():
        print("FATAL: 钉定公开面缺 %s" % LCCC_PATH)
        return 2
    if sha256_file(LCCC_PATH) != LCCC_SHA256:
        print("FATAL: lccc_consumer.py sha256 漂移（E22 v1.1 钉定失效）")
        return 2
    if not HARNESS_PUBLIC_ENTRY.is_file():
        print("FATAL: harness 战役分支检出缺 %s" % HARNESS_PUBLIC_ENTRY)
        return 2

    all_checks = []
    for profile in profiles:
        checks, _ = run_profile(profile)
        all_checks.append((profile, checks))
    return 0 if all(c.all_passed for _, c in all_checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
