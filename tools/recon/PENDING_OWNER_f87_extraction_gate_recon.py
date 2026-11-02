# -*- coding: utf-8 -*-
"""F87 引文核验接抽取路径强制闸验收对账（PENDING_OWNER 版，工单 W2b-U02）。

强制闸合同（06 行 F87 acceptance / 07 E14 顺序纪律）：
  独立核验服务先实现（W2a-U14 已 VERIFIED 的 citation.{parse,verify,
  verify_document}＋statute.citation_gate），再接抽取——本闸零第二核验器；
  quote 存在不等于命题支持；伪引文/旧版本拒绝；格候选不伪已核（未核
  状态具名）；fail-closed。全部断言走真产品入口
  （implementation/python/legal_entry.py 子进程径）。

分段：
  G0 前置：E22 冻结面 v1.1 文件在盘＋sha256 钉定；真实锚点行内事实由
     正式表独立复核（消费断言仍只走闸→核验服务→冻结面）。
  G1 登记纪律：混合候选批次入册即具名 UNVERIFIED/PENDING_GATE；携带
     闸状态字段的登记（伪造未遂）响亮拒。
  G2 强制闸执行：真核验服务径跑闸——好候选（现行真引文）引用级
     CITATION_VERIFIED；伪引文/张冠李戴/条文号不存在/虚构标题/旧版本
     （已废止/已修订/替代@2015）/尚未施行未知/无引用 全 REJECTED 理由
     具名；状态与理由均落闭集。
  G3 quote 存在不等于命题支持：最好结局 proposition_support 恒
     UNSIGNED_QUOTE_EXISTENCE_IS_NOT_PROPOSITION_SUPPORT；结构断言响应
     无任何命题级 PASS 形态字段；引用级事实（quote_in_article=True/
     引用回读）在场。
  G4 未核不伪已核＋不串门：只登记不过闸的批次回读恒 UNVERIFIED 具名；
     同批好坏候选并存互不覆盖。
  G5 fail-closed：缺 as_of/坏 as_of/面未钉定/面漂移（复制面文件改字节
     →响亮拒且批次不被污染）/未知方法/未知批次 全 exit 3 具名。
  G6 确定性＋零第二核验器：同输入两状态根两跑闸结论语义相等；AST 扫描
     extraction_gate.py 零网络/零直读正式表/零第二核验器函数。
  G7 顺序纪律回读：闸响应 verification_face/face_sha256 钉定链在案。

用法（juscite worktree 根 cwd；双 profile 单次调用）：
  python -X utf8 tools/recon/PENDING_OWNER_f87_extraction_gate_recon.py \
      --profile desktop --profile selfhost

exit 0＝全部 profile 全部断言过（RECON_OK）；证据 JSON 写
evidence/F87/<profile>/。只读消费，不发任何网络请求，不写正式目录，
不触碰 oc28 与 %APPDATA%。
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

csv.field_size_limit(10 ** 9)

RUN_DATE = time.strftime("%Y%m%d")
REPO_ROOT = Path(__file__).resolve().parents[2]
LEGAL_ENTRY = REPO_ROOT / "implementation" / "python" / "legal_entry.py"
GATE_MODULE = REPO_ROOT / "implementation" / "python" / "extraction_gate.py"

DEFAULT_FORMAL_ROOT = (
    r"D:\Codex\1.法律工作区\legal-cn-core-codices工作区\legal-cn-core-codices"
)
# E22 冻结面 v1.1（codices 分支 jusbench/w2a-u14-f70-citation @ dc0caf68e）
DEFAULT_CODICES_REPO = (
    r"D:\Codex\1.法律工作区\legal-cn-core-codices工作区"
    r"\legal-cn-core-codices-repo\.local\worktrees\w2a-u14"
)
LCCC_V11_SHA256 = (
    "55eea7c27e08d6b236b7ab7a83810c86ee0898c335c4668d875a492775db863a"
)

# 真实数据锚点（2026-10-15/16 在盘实测；行内事实运行时由正式表独立复核）
ANCHORS = {
    "CUR": "中华人民共和国个人信息保护法",   # 现行（01）
    "ABO": "中华人民共和国合同法",           # 已废止（04 单版）
    "AMD": "中华人民共和国产品质量法",       # 已修订（03 单版）
    "SUP": "中华人民共和国商标法",           # 三版本；@2015 定版 03=替代
}
FABRICATED_TITLE = "中华人民共和国月球资源开发管辖法"
CUR_ARTICLE1_QUOTE = (
    "为了保护个人信息权益，规范个人信息处理活动，促进个人信息合理利用，"
    "根据宪法，制定本法。"
)
CUR_OTHER_ARTICLE_QUOTE = "处理个人信息应当遵循公开、透明原则"  # 第七条

GATE_UNVERIFIED = "UNVERIFIED"
GATE_CITATION_VERIFIED = "CITATION_VERIFIED"
GATE_REJECTED = "REJECTED"

# 命题级 PASS 形态禁串（quote 存在不等于命题支持——结构断言）
BANNED_PROPOSITION_PASS = (
    '"proposition_supported"', '"supported": true', '"pass": true',
    '"proposition_pass"', '"all_verified"', '"batch_pass"',
)


class Checks:
    def __init__(self):
        self.items: list[dict] = []

    def add(self, check_id: str, ok: bool, detail: str) -> bool:
        self.items.append(
            {"id": check_id, "status": "PASS" if ok else "FAIL",
             "detail": detail}
        )
        print("[%s] %s — %s" % ("PASS" if ok else "FAIL", check_id, detail))
        return ok

    @property
    def all_passed(self) -> bool:
        return all(item["status"] == "PASS" for item in self.items)

    @property
    def passed_count(self) -> int:
        return sum(1 for item in self.items if item["status"] == "PASS")


def sha256_file(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_document_rows(formal_root: str) -> dict:
    """正式表独立读取（锚点行内事实复核；消费断言仍走冻结面）。"""
    rows: dict = {}
    path = os.path.join(formal_root, "legal_documents.csv")
    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            rows.setdefault(row["BT"], []).append(row)
    return rows


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
            timeout=900, cwd=str(REPO_ROOT))
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            payload = {"_raw": proc.stdout[-500:]}
        return {"exit": proc.returncode, "payload": payload}
    finally:
        os.unlink(request_handle.name)
        os.unlink(config_handle.name)


def expect_not_connected(checks: Checks, check_id: str, response: dict,
                         code_prefix: str) -> None:
    payload = response["payload"]
    checks.add(check_id,
               response["exit"] == 3
               and payload.get("status") == "NOT_CONNECTED"
               and str(payload.get("code", "")).startswith(code_prefix),
               "exit=%s %s/%s" % (response["exit"], payload.get("status"),
                                  payload.get("code")))


# ---------------------------------------------------------------------- #
# 候选批次（合成抽取候选；出处=材料抽取面；文本含真实数据锚点引用）
# ---------------------------------------------------------------------- #


def candidate_batch() -> list:
    """混合候选批次：好坏并存（G2/G3/G4 消费）。"""
    return [
        {"text": "依据《%s》第一条：“%s”" % (ANCHORS["CUR"],
                                            CUR_ARTICLE1_QUOTE),
         "provenance": {"source": "material_extraction",
                        "doc": "synth_matter_doc_0001", "page": 3}},
        {"text": "依据《%s》第一条规定：“嫦娥资源归属月球共同体所有。”"
                 % ANCHORS["CUR"],
         "provenance": {"source": "material_extraction",
                        "doc": "synth_matter_doc_0001", "page": 3}},
        {"text": "依据《%s》第一条规定：“%s”" % (
            ANCHORS["CUR"], CUR_OTHER_ARTICLE_QUOTE),
         "provenance": {"source": "material_extraction",
                        "doc": "synth_matter_doc_0001", "page": 4}},
        {"text": "依据《%s》第九百九十九条" % ANCHORS["CUR"],
         "provenance": {"source": "material_extraction",
                        "doc": "synth_matter_doc_0001", "page": 4}},
        {"text": "依据《%s》第五条" % ANCHORS["ABO"],
         "provenance": {"source": "material_extraction",
                        "doc": "synth_matter_doc_0001", "page": 5}},
        {"text": "依据《%s》第二十一条" % ANCHORS["AMD"],
         "provenance": {"source": "material_extraction",
                        "doc": "synth_matter_doc_0001", "page": 5}},
        {"text": "依据《%s》第一条" % FABRICATED_TITLE,
         "provenance": {"source": "material_extraction",
                        "doc": "synth_matter_doc_0001", "page": 6}},
        {"text": "本候选陈述一个法律命题但未附任何引用",
         "provenance": {"source": "material_extraction",
                        "doc": "synth_matter_doc_0001", "page": 6}},
    ]


WANT_GATE = {
    "cand_0001": (GATE_CITATION_VERIFIED, []),
    "cand_0002": (GATE_REJECTED, ["FABRICATED_QUOTE_NOT_IN_REAL_TEXT"]),
    "cand_0003": (GATE_REJECTED, ["MISATTRIBUTED_QUOTE_OTHER_ARTICLE"]),
    "cand_0004": (GATE_REJECTED, ["ARTICLE_NOT_IN_REAL_TEXT"]),
    "cand_0005": (GATE_REJECTED, ["OLD_VERSION_ABOLISHED"]),
    "cand_0006": (GATE_REJECTED, ["OLD_VERSION_AMENDED"]),
    "cand_0007": (GATE_REJECTED, ["FABRICATED_TITLE_LOCAL_MISS"]),
    "cand_0008": (GATE_REJECTED, ["NO_CITATION_PARSED"]),
}


def gate_projection(gate_response: dict) -> dict:
    """闸结论语义投影（确定性对比用；剥离时间戳/序号等跑次元数据）。"""
    return {
        r["candidate_id"]: (r["gate_status"],
                            [x["reason"] for x in r["rejection_reasons"]])
        for r in gate_response["results"]}


def run_profile(profile: str, formal_root: str, codices_repo: str) -> dict:
    """单 profile 全段对账；返回证据 dict。"""
    print("=== profile=%s ===" % profile)
    checks = Checks()
    state_root = Path(tempfile.mkdtemp(prefix="f87-recon-%s-" % profile))
    config = {
        "codices_import_path": codices_repo,
        "codices_formal_root": formal_root,
        "extraction_gate_state_root": str(state_root),
        "codices_face_sha256": LCCC_V11_SHA256,
    }
    rows = load_document_rows(formal_root)

    # G0 前置：冻结面钉定＋锚点行内事实独立复核
    lccc_path = os.path.join(codices_repo, "lccc_consumer.py")
    cur = [r for r in rows[ANCHORS["CUR"]] if r["SXX"] == "01"]
    checks.add("G0A_frozen_face_v11_pinned",
               os.path.isfile(lccc_path)
               and sha256_file(lccc_path) == LCCC_V11_SHA256,
               "lccc_consumer.py v1.1 sha256=%s…（漂移即响亮失败）"
               % LCCC_V11_SHA256[:16])
    checks.add("G0B_anchor_row_facts",
               len(cur) == 1 and bool(cur[0]["SXRQ"])
               and len(rows[ANCHORS["ABO"]]) == 1
               and rows[ANCHORS["ABO"]][0]["SXX"] == "04"
               and len(rows[ANCHORS["AMD"]]) == 1
               and rows[ANCHORS["AMD"]][0]["SXX"] == "03"
               and len(rows[ANCHORS["SUP"]]) == 3,
               "锚点行内事实：CUR 01；ABO 单版 04；AMD 单版 03；"
               "SUP 三版本（03/01/02）")

    # G1 登记纪律：未核状态具名＋伪造闸字段拒
    reg = call_entry("extraction.register",
                     {"batch_id": "main_batch",
                      "candidates": candidate_batch()}, config)
    payload = reg["payload"].get("result", {}) if reg["exit"] == 0 else {}
    statuses = payload.get("gate_status_by_candidate", {})
    checks.add("G1A_register_names_unverified",
               reg["exit"] == 0 and len(statuses) == 8
               and set(statuses.values()) == {GATE_UNVERIFIED},
               "8 候选入册即具名 %s（%d 条）" % (
                   GATE_UNVERIFIED, len(statuses)))
    read = call_entry("extraction.candidates", {"batch_id": "main_batch"},
                      config)
    views = (read["payload"].get("result", {})
             .get("candidates", [])) if read["exit"] == 0 else []
    checks.add("G1B_ungated_readback_named_unverified",
               read["exit"] == 0 and len(views) == 8 and all(
                   v.get("gate_status") == GATE_UNVERIFIED
                   and v.get("proposition_support") == "PENDING_GATE"
                   and v.get("rejection_reasons") == []
                   and v.get("provenance", {}).get("source")
                   == "material_extraction" for v in views),
               "未过闸回读：gate_status/proposition_support 具名在场，"
               "出处随候选回读")
    forged = call_entry("extraction.register", {
        "batch_id": "forge_batch",
        "candidates": [{"text": "依据《%s》第一条" % ANCHORS["CUR"],
                        "gate_status": GATE_CITATION_VERIFIED}]}, config)
    expect_not_connected(checks, "G1C_forged_gate_fields_refused", forged,
                         "extraction_register_gate_fields_refused:")

    # G2 强制闸执行（真核验服务径；一次子进程付一次冷扫）
    gate = call_entry("extraction.gate",
                      {"batch_id": "main_batch", "as_of": RUN_DATE}, config)
    gate_result = gate["payload"].get("result", {}) if gate["exit"] == 0 else {}
    got = gate_projection(gate_result)
    checks.add("G2A_gate_outcomes_closed_reasons",
               gate["exit"] == 0 and got == WANT_GATE,
               "8 候选闸结论＝%s" % json.dumps(got, ensure_ascii=False))
    reasons_ok = all(
        reason in {"NO_CITATION_PARSED", "FABRICATED_TITLE_LOCAL_MISS",
                   "FABRICATED_QUOTE_NOT_IN_REAL_TEXT",
                   "MISATTRIBUTED_QUOTE_OTHER_ARTICLE",
                   "ARTICLE_NOT_IN_REAL_TEXT", "OLD_VERSION_ABOLISHED",
                   "OLD_VERSION_AMENDED", "OLD_VERSION_EXPIRED",
                   "OLD_VERSION_SUPERSEDED", "UNKNOWN_FAIL_CLOSED"}
        for _, reasons in got.values() for reason in reasons)
    checks.add("G2B_rejection_reasons_closed_set",
               reasons_ok and gate_result.get("by_gate_status") == {
                   GATE_CITATION_VERIFIED: 1, GATE_REJECTED: 7},
               "理由闭集＋计数=%s" % gate_result.get("by_gate_status"))
    # 旧版本·替代（商标法@2015 定版 03，同名更新版在库）
    call_entry("extraction.register", {
        "batch_id": "sup2015",
        "candidates": [{"text": "依据《%s》第五十七条" % ANCHORS["SUP"],
                        "provenance": {"source": "material_extraction",
                                       "doc": "synth_matter_doc_0002"}}],
    }, config)
    gate2015 = call_entry("extraction.gate",
                          {"batch_id": "sup2015", "as_of": "20150101"},
                          config)
    r2015 = gate2015["payload"].get("result", {}) \
        if gate2015["exit"] == 0 else {}
    sup2015 = gate_projection(r2015).get("cand_0001", (None, []))
    checks.add("G2C_old_version_superseded_rejected",
               sup2015 == (GATE_REJECTED, ["OLD_VERSION_SUPERSEDED"]),
               "商标法@2015 旧版本候选 → %s" % json.dumps(
                   sup2015, ensure_ascii=False))

    # G3 quote 存在不等于命题支持
    good = call_entry("extraction.candidate", {
        "batch_id": "main_batch", "candidate_id": "cand_0001"}, config)
    good_view = good["payload"].get("result", {}) if good["exit"] == 0 else {}
    history = good_view.get("gate_history") or []
    citation = history[-1]["citations"][0] if history and \
        history[-1].get("citations") else {}
    checks.add("G3A_quote_exists_never_signs_proposition",
               good["exit"] == 0
               and good_view.get("gate_status") == GATE_CITATION_VERIFIED
               and good_view.get("proposition_support")
               == "UNSIGNED_QUOTE_EXISTENCE_IS_NOT_PROPOSITION_SUPPORT",
               "最好结局=引用级 CITATION_VERIFIED；proposition_support=%r"
               % good_view.get("proposition_support"))
    checks.add("G3B_no_proposition_level_pass_fields",
               good["exit"] == 0 and not any(
                   b in json.dumps(good_view, ensure_ascii=False)
                   for b in BANNED_PROPOSITION_PASS),
               "候选回读无任何命题级 PASS 形态字段（结构断言）")
    checks.add("G3C_citation_level_facts_readable",
               citation.get("status") == "现行"
               and citation.get("verified_scoped") is True
               and citation.get("quote_in_article") is True,
               "引用级事实回读：现行/verified_scoped/quote_in_article=True"
               "（引用核验事实在案，命题支持另判）")

    # G4 未核不伪已核＋同批不串门
    call_entry("extraction.register", {
        "batch_id": "never_gated",
        "candidates": [{"text": "依据《%s》第一条：“%s”" % (
            ANCHORS["CUR"], CUR_ARTICLE1_QUOTE)}]}, config)
    ng = call_entry("extraction.candidates", {"batch_id": "never_gated"},
                    config)
    ng_view = ng["payload"].get("result", {}) if ng["exit"] == 0 else {}
    checks.add("G4A_ungated_batch_never_verified",
               ng["exit"] == 0 and ng_view.get("gate_runs") == 0
               and [c.get("gate_status") for c in ng_view.get(
                   "candidates", [])] == [GATE_UNVERIFIED],
               "只登记不过闸的批次回读恒 %s 具名（不缺席不伪已核）"
               % GATE_UNVERIFIED)
    mixed = call_entry("extraction.candidates", {"batch_id": "main_batch"},
                       config)
    mixed_views = mixed["payload"].get("result", {}).get(
        "candidates", []) if mixed["exit"] == 0 else []
    by_id = {c.get("candidate_id"): c for c in mixed_views}
    checks.add("G4B_mixed_batch_no_status_bleed",
               by_id.get("cand_0001", {}).get("gate_status")
               == GATE_CITATION_VERIFIED
               and by_id.get("cand_0002", {}).get("gate_status")
               == GATE_REJECTED
               and by_id.get("cand_0005", {}).get("gate_status")
               == GATE_REJECTED,
               "同批好坏并存：cand_0001 过闸 / cand_0002 伪引文 / "
               "cand_0005 旧版本——互不覆盖")

    # G5 fail-closed（全部 exit 3 具名）
    expect_not_connected(checks, "G5A_gate_missing_as_of",
                         call_entry("extraction.gate",
                                    {"batch_id": "sup2015"}, config),
                         "extraction_gate_as_of_required_fail_closed")
    expect_not_connected(checks, "G5B_gate_malformed_as_of",
                         call_entry("extraction.gate", {
                             "batch_id": "sup2015",
                             "as_of": "2026-10-16"}, config),
                         "extraction_gate_as_of_must_be_yyyymmdd")
    unpinned = dict(config)
    unpinned.pop("codices_face_sha256")
    expect_not_connected(checks, "G5C_unpinned_face_refused",
                         call_entry("extraction.gate", {
                             "batch_id": "sup2015",
                             "as_of": RUN_DATE}, unpinned),
                         "extraction_gate_face_sha_pin_required")
    drift_dir = Path(tempfile.mkdtemp(prefix="f87-recon-drift-"))
    (drift_dir / "lccc_consumer.py").write_bytes(
        Path(lccc_path).read_bytes() + b"\n# simulated drift\n")
    drifted = dict(config)
    drifted["codices_import_path"] = str(drift_dir)
    expect_not_connected(checks, "G5D_face_drift_fails_loud",
                         call_entry("extraction.gate", {
                             "batch_id": "sup2015",
                             "as_of": RUN_DATE}, drifted),
                         "codices_face_sha256_drift:")
    after_drift = call_entry("extraction.candidates",
                             {"batch_id": "sup2015"}, drifted)
    checks.add("G5D2_drift_refusal_leaves_state_unpolluted",
               after_drift["exit"] == 0
               and [c.get("gate_status") for c in after_drift["payload"]
                    .get("result", {}).get("candidates", [])] == [
                   GATE_REJECTED],
               "漂移拒后批次状态不被污染（2015 旧版本批此前闸结论 REJECTED"
               "原样，无第二次闸跑发生）")
    expect_not_connected(checks, "G5E_unknown_batch",
                         call_entry("extraction.candidates",
                                    {"batch_id": "ghost"}, config),
                         "extraction_batch_not_registered:ghost")
    expect_not_connected(checks, "G5F_unknown_method",
                         call_entry("extraction.mark_verified",
                                    {"batch_id": "sup2015"}, config),
                         "method_not_connected:")

    # G6 确定性＋零第二核验器（静态纪律）
    state2 = Path(tempfile.mkdtemp(prefix="f87-recon-det-"))
    config2 = dict(config)
    config2["extraction_gate_state_root"] = str(state2)
    call_entry("extraction.register",
               {"batch_id": "main_batch", "candidates": candidate_batch()},
               config2)
    gate2 = call_entry("extraction.gate",
                       {"batch_id": "main_batch", "as_of": RUN_DATE}, config2)
    gate2_result = gate2["payload"].get("result", {}) \
        if gate2["exit"] == 0 else {}
    checks.add("G6A_same_input_same_gate_verdicts",
               gate_projection(gate2_result) == got,
               "同输入两状态根两跑闸结论语义相等（确定性）")
    source = GATE_MODULE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    violations: list = []
    network = {"urllib", "requests", "socket", "http", "httpx", "aiohttp"}
    verifier_functions = {"resolve_effectivity", "document_markdown",
                          "read_markdown_text", "find_by_title",
                          "split_articles", "_support_check",
                          "_status_from_gate"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        else:
            names = []
        for name in names:
            if name.split(".")[0] in network:
                violations.append("network_import:" + name)
        if isinstance(node, ast.FunctionDef) \
                and node.name in verifier_functions:
            violations.append("second_verifier_fn:" + node.name)
    checks.add("G6B_gate_module_static_discipline",
               not violations
               and "legal_documents.csv" not in source
               and "verify_citation" in source,
               "AST：零网络/零直读正式表/零第二核验器函数；"
               "核验唯一权威 citation_verifier.verify_citation 在案"
               + ("；违例=" + ";".join(violations) if violations else ""))

    # G7 顺序纪律回读
    checks.add("G7A_verification_face_chain_in_record",
               "citation.verify(W2a-U14 VERIFIED)" in
               gate_result.get("verification_face", "")
               and gate_result.get("face_sha256") == LCCC_V11_SHA256,
               "闸记录核验面链=%r＋钉定 sha 回读" %
               gate_result.get("verification_face"))

    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True,
        cwd=str(REPO_ROOT)).stdout.strip()
    return {
        "run_date": RUN_DATE,
        "profile": profile,
        "command": "python -X utf8 " + " ".join(sys.argv[1:]),
        "cwd": str(REPO_ROOT),
        "subject_commit": commit,
        "formal_root": formal_root,
        "frozen_face": {
            "lccc_consumer.py(v1.1)": sha256_file(lccc_path),
            "legal_documents.csv": sha256_file(
                os.path.join(formal_root, "legal_documents.csv")),
        },
        "anchors": ANCHORS,
        "gate_projection": {k: list(v) for k, v in got.items()},
        "by_gate_status": gate_result.get("by_gate_status"),
        "checks": checks.items,
        "passed": checks.passed_count,
        "total": len(checks.items),
        "overall": "PASS" if checks.all_passed else "FAIL",
        "checks_summary": checks,
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", action="append",
                        choices=("desktop", "selfhost"), dest="profiles",
                        help="发行形态（可重复；不给则双形态全跑）")
    parser.add_argument("--formal-root", default=DEFAULT_FORMAL_ROOT)
    parser.add_argument("--codices-repo", default=DEFAULT_CODICES_REPO)
    parser.add_argument("--evidence-root", default="evidence/F87")
    args = parser.parse_args()
    profiles = args.profiles or ["desktop", "selfhost"]

    lccc_path = os.path.join(args.codices_repo, "lccc_consumer.py")
    if not os.path.isfile(lccc_path):
        print("FATAL: lccc_consumer.py 不在 %s（E22 冻结面 v1.1）"
              % args.codices_repo)
        return 2
    if sha256_file(lccc_path) != LCCC_V11_SHA256:
        print("FATAL: 冻结面 v1.1 lccc_consumer.py sha256 漂移")
        return 2
    rows = load_document_rows(args.formal_root)
    missing = [k for k, title in ANCHORS.items() if title not in rows]
    if missing:
        print("FATAL: 锚点标题未在正式表命中：%s" % missing)
        return 2

    all_ok = True
    for profile in profiles:
        evidence = run_profile(profile, args.formal_root, args.codices_repo)
        out_dir = REPO_ROOT / args.evidence_root / profile
        out_dir.mkdir(parents=True, exist_ok=True)
        summary = evidence.pop("checks_summary")
        (out_dir / "f87-extraction-gate-recon.json").write_text(
            json.dumps(evidence, ensure_ascii=False, indent=1),
            encoding="utf-8")
        all_ok = all_ok and summary.all_passed
        print("---")
        print("profile=%s: %d/%d checks" % (profile, summary.passed_count,
                                            len(summary.items)))
    print("RECON_%s（%s）" % ("OK" if all_ok else "FAIL",
                             "+".join(profiles)))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
