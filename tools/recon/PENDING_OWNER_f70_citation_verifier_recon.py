# -*- coding: utf-8 -*-
"""F70 引证核验器验收对账（PENDING_OWNER 版，工单 W2a-U14）。

单条核验＋全文引用逐条范围记账（虚构/失效/误引不标全核），全部断言走
真产品入口（implementation/python/legal_entry.py 子进程径）；版本/效力/
时点经 W2a-U13 statute 面（statute.citation_gate 决策码在记录内回读）；
标题定位与真实取文经 E22 冻结面 v1.1（find_by_title/read_markdown_text）。

分段：
  S1 单条核验（真实本地数据锚点 8 个）：现行+真引文（含引用回读）/伪引文/
     张冠李戴/条文号不存在/已废止/已修订/失效/替代（多版本定版）/尚未施行/
     虚构（付费缺口具名不自采）；锚点行内事实由正式表独立复核。
  S2 全文档逐条记账（合成引用文档×真实法源数据）：每引用独立状态与计数；
     无文档级 PASS 笼统结论（响应 JSON 结构性断言）；反例三拒——虚构/
     失效/误引三条 verified_scoped 恒 False。
  S3 确定性解析：同输入字节级同输出；引号感知句界（引文含句号不断段）；
     书名号段界（引文归属不串门）；千位中文数字；款/项跟随；静态扫描
     citation_verifier.py 零网络/零写/零模型参与。
  S4 冻结面纪律：v1.1 面文件 sha256 钉定；find_by_title 只读（正式面指纹
     不变）；替代链 legal_relations 空表→replacement 恒 unknown 不编造。
  S5 桥 fail-closed：未配置/未知方法/缺参 exit 3 具名 NOT_CONNECTED。

用法（juscite worktree 根 cwd）：
  python -X utf8 tools/PENDING_OWNER_f70_citation_verifier_recon.py --profile desktop
  [--formal-root <codices 正式目录>] [--codices-repo <含 v1.1 lccc_consumer.py 目录>]
  [--evidence-root evidence/F70]

exit 0＝全部断言过；证据 JSON 写 <root>/<profile>/。
只读消费，不发任何网络请求，不写正式目录。
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
REPO_ROOT = Path(__file__).resolve().parents[1]
LEGAL_ENTRY = REPO_ROOT / "implementation" / "python" / "legal_entry.py"
CITATION_MODULE = REPO_ROOT / "implementation" / "python" / "citation_verifier.py"

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

# 真实数据锚点（2026-10-15 在盘实测；行内事实运行时由正式表独立复核）
ANCHORS = {
    # 现行＋真实 md 载体（引文/取文定位对象）
    "CUR": "中华人民共和国个人信息保护法",
    # 已废止（04，单版本——合同法 1999，被民法典废止）
    "ABO": "中华人民共和国合同法",
    # 已修订（03，单版本）
    "AMD": "中华人民共和国产品质量法",
    # 已失效（05，单版本，无失效日）
    "EXP": "沈阳市道路客运市场管理条例",
    # 尚未施行（02，单版本，SXRQ=20270101）
    "NTY": "中华人民共和国医疗保障法",
    # 多版本（03/2014、01/2019、02/2027）——替代/现行双时点锚点
    "SUP": "中华人民共和国商标法",
}
FABRICATED_TITLE = "中华人民共和国月球资源开发管辖法"
CUR_ARTICLE1_QUOTE = (
    "为了保护个人信息权益，规范个人信息处理活动，促进个人信息合理利用，"
    "根据宪法，制定本法。"
)
# 第七条真实正文片段（用于「引文真但在他条」的张冠李戴反例）
CUR_OTHER_ARTICLE_QUOTE = "处理个人信息应当遵循公开、透明原则"

NETWORK_MODULES = {
    "urllib", "urllib.request", "urllib.parse", "requests", "socket",
    "http", "http.client", "httpx", "aiohttp",
}
WRITE_MODES = {"w", "a", "x", "w+", "a+", "x+", "r+", "+"}
NONDETERMINISTIC_IMPORTS = {"random", "secrets"}


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
            timeout=600, cwd=str(REPO_ROOT))
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            payload = {"_raw": proc.stdout[-500:]}
        return {"exit": proc.returncode, "payload": payload}
    finally:
        os.unlink(request_handle.name)
        os.unlink(config_handle.name)


def _verify(citation: str, config: dict, as_of: str = RUN_DATE) -> dict:
    return call_entry("citation.verify",
                      {"citation": citation, "as_of": as_of}, config)


def expect_verify(checks: Checks, check_id: str, response: dict,
                  status: str, code: str | None = None,
                  verified: bool | None = None) -> dict:
    payload = response["payload"]
    result = payload.get("result", {}) if isinstance(payload, dict) else {}
    ok = (response["exit"] == 0
          and payload.get("status") == "OWNER_RESPONSE"
          and result.get("status") == status)
    detail = "exit=%s status=%s code=%s" % (
        response["exit"], result.get("status"), result.get("code"))
    if code is not None:
        ok = ok and result.get("code") == code
    if verified is not None:
        ok = ok and result.get("verified_scoped") is verified
        detail += " verified_scoped=%r" % result.get("verified_scoped")
    checks.add(check_id, ok, detail)
    return result


def section_s1(checks: Checks, rows: dict, config: dict) -> list:
    # 锚点行内事实独立复核（防锚点漂移静默过检）
    cur = [r for r in rows[ANCHORS["CUR"]] if r["SXX"] == "01"]
    checks.add("S1_anchor_row_facts",
               len(cur) == 1 and bool(cur[0]["SXRQ"])
               and len(rows[ANCHORS["ABO"]]) == 1
               and rows[ANCHORS["ABO"]][0]["SXX"] == "04"
               and len(rows[ANCHORS["AMD"]]) == 1
               and rows[ANCHORS["AMD"]][0]["SXX"] == "03"
               and len(rows[ANCHORS["EXP"]]) == 1
               and rows[ANCHORS["EXP"]][0]["SXX"] == "05"
               and len(rows[ANCHORS["NTY"]]) == 1
               and rows[ANCHORS["NTY"]][0]["SXX"] == "02"
               and rows[ANCHORS["NTY"]][0]["SXRQ"] > RUN_DATE
               and len(rows[ANCHORS["SUP"]]) == 3
               and sorted(r["SXX"] for r in rows[ANCHORS["SUP"]]) ==
               ["01", "02", "03"],
               "锚点行内事实：CUR 01；ABO 单版 04；AMD 单版 03；EXP 单版 05；"
               "NTY 单版 02 SXRQ>%s；SUP 三版本 01/02/03" % RUN_DATE)

    results = []
    # R1 现行＋真引文：支持核验过＋引用回读真文本
    r1 = expect_verify(checks, "S1_R1_current_real_quote_verified",
                       _verify("《%s》第一条规定：“%s”"
                               % (ANCHORS["CUR"], CUR_ARTICLE1_QUOTE), config),
                       "现行", "CURRENT_IN_FORCE_CITABLE", verified=True)
    ok = (r1.get("support", {}).get("quote_in_article") is True
          and r1.get("support", {}).get("article_located") is True
          and "为了保护个人信息权益"
          in (r1.get("support", {}).get("article_text") or ""))
    checks.add("S1_R1b_support_and_readback",
               ok, "真实取文定位过＋引用回读含第一条真实正文（quote_in_article"
                   "=True，article_text 回读）")
    results.append(r1)
    # R2 伪引文（全文亦无）→ 误引
    r2 = expect_verify(checks, "S1_R2_fabricated_quote_miscited",
                       _verify("《%s》第一条规定：“嫦娥资源归属月球共同体所有。”"
                               % ANCHORS["CUR"], config),
                       "误引", "QUOTE_NOT_IN_REAL_TEXT", verified=False)
    ok = (r2.get("support", {}).get("quote_in_article") is False
          and r2.get("support", {}).get("quote_in_document") is False)
    checks.add("S1_R2b_quote_absent_everywhere", ok,
               "伪引文：定位条文与全真实正文均无")
    # R3 张冠李戴（引文真实但在他条）→ 误引
    r3 = expect_verify(checks, "S1_R3_quote_misattribution_miscited",
                       _verify("《%s》第一条规定：“%s”"
                               % (ANCHORS["CUR"], CUR_OTHER_ARTICLE_QUOTE), config),
                       "误引", "QUOTE_MISATTRIBUTED", verified=False)
    ok = (r3.get("support", {}).get("quote_in_article") is False
          and r3.get("support", {}).get("quote_in_document") is True)
    checks.add("S1_R3b_quote_real_but_other_article", ok,
               "引文存在于真实正文他条（第七条内容冒充第一条）＝张冠李戴")
    # R4 条文号不存在 → 误引
    expect_verify(checks, "S1_R4_article_number_not_in_real_text",
                  _verify("《%s》第九百九十九条" % ANCHORS["CUR"], config),
                  "误引", "ARTICLE_NOT_IN_REAL_TEXT", verified=False)
    # R5 已废止（04）→ 不许引
    r5 = expect_verify(checks, "S1_R5_abolished_not_citable",
                       _verify("《%s》第五条" % ANCHORS["ABO"], config),
                       "已废止", "ABOLISHED_NOT_CITABLE", verified=False)
    results.append(r5)
    # R6 已修订（03 单版）→ 不许引＋替代 unknown
    r6 = expect_verify(checks, "S1_R6_amended_not_citable",
                       _verify("《%s》第二十一条" % ANCHORS["AMD"], config),
                       "已修订", "SUPERSEDED_NOT_CITABLE", verified=False)
    ok = r6.get("replacement") == "unknown" and "legal_relations" in (
        r6.get("replacement_reason") or "")
    checks.add("S1_R6b_replacement_unknown_no_fabrication", ok,
               "替代链空表→replacement=unknown 不编造替代版本")
    results.append(r6)
    # R7 已失效（05 单版）→ 失效
    r7 = expect_verify(checks, "S1_R7_expired_status",
                       _verify("《%s》第十条" % ANCHORS["EXP"], config),
                       "失效", "SUPERSEDED_NOT_CITABLE", verified=False)
    results.append(r7)
    # R8 替代（多版本：as_of=2015 无 ALLOWED→定版 03 旧版，同名更新版在库）
    r8 = expect_verify(checks, "S1_R8_superseded_by_newer_same_title",
                       _verify("《%s》第五十七条" % ANCHORS["SUP"], config,
                               as_of="20150101"),
                       "替代", "SUPERSEDED_NOT_CITABLE", verified=False)
    results.append(r8)
    # R9 同名现行版（as_of=2026 定版 01 版）→ 现行
    expect_verify(checks, "S1_R9_multiversion_resolves_to_in_force",
                  _verify("《%s》第一条" % ANCHORS["SUP"], config),
                  "现行", "CURRENT_IN_FORCE_CITABLE", verified=True)
    # R10 尚未施行（02 单版）→ 未知 fail-closed
    expect_verify(checks, "S1_R10_not_yet_in_force_unknown",
                  _verify("《%s》第一条" % ANCHORS["NTY"], config),
                  "未知", "NOT_YET_IN_FORCE_AT_AS_OF", verified=False)
    # R11 虚构标题（本面未命中）＋付费缺口具名声明＋不自采
    r11 = expect_verify(checks, "S1_R11_fabricated_title_local_miss",
                        _verify("《%s》第一条" % FABRICATED_TITLE, config),
                        "虚构", "LOCAL_FACE_TITLE_MISS", verified=False)
    gap = r11.get("degradation") or {}
    checks.add("S1_R11b_paid_gap_named_no_self_collection",
               "PAID" in str(gap.get("reason", ""))
               and gap.get("self_collection") == "none"
               and "http" not in json.dumps(r11, ensure_ascii=False),
               "虚构记录携带付费缺口具名声明（%s），self_collection=none，"
               "零 URL 披露——本地未命中≠全局不存在" % gap.get("reason"))
    # R12 版本/效力经 U13 面：决策码回读自 statute.citation_gate
    ok = all(r.get("decision") in ("ALLOWED", "BLOCKED", "UNKNOWN")
             and r.get("code") for r in results if r)
    checks.add("S1_R12_effect_via_u13_gate_face", ok,
               "全部状态记录 decision/code 来自 statute.citation_gate"
               "（W2a-U13 版本/效力面）：%s" %
               [r.get("code") for r in results if r])
    return results


BAD_DOC = (
    "原告主张依据《{ABO}》第五条（已废止不许引）。"
    "被告引用《{FAB}》第一条（本地面未命中=虚构）与《{CUR}》第九百九十九条"
    "（条文号不存在=误引）。"
    "另查明《{EXP}》第十条已失效；本案仍应适用《{CUR}》第一条：“{QUOTE}”"
    "与《{AMD}》第二十一条之规定。"
)


def section_s2(checks: Checks, config: dict) -> dict:
    doc = BAD_DOC.format(ABO=ANCHORS["ABO"], FAB=FABRICATED_TITLE,
                         CUR=ANCHORS["CUR"], EXP=ANCHORS["EXP"],
                         AMD=ANCHORS["AMD"], QUOTE=CUR_ARTICLE1_QUOTE)
    response = call_entry("citation.verify_document",
                          {"text": doc, "as_of": RUN_DATE}, config)
    payload = response["payload"]
    result = payload.get("result", {}) if response["exit"] == 0 else {}
    citations = result.get("citations", [])
    by_text = {c["citation_text"]: c for c in citations}

    want = {
        "《%s》第五条" % ANCHORS["ABO"]: "已废止",
        "《%s》第一条" % FABRICATED_TITLE: "虚构",
        "《%s》第九百九十九条" % ANCHORS["CUR"]: "误引",
        "《%s》第十条" % ANCHORS["EXP"]: "失效",
        "《%s》第一条" % ANCHORS["CUR"]: "现行",
        "《%s》第二十一条" % ANCHORS["AMD"]: "已修订",
    }
    got = {text: c.get("status") for text, c in by_text.items()}
    checks.add("S2A_every_citation_independent_status",
               response["exit"] == 0 and len(citations) == len(want)
               and got == want,
               "6 引用 6 独立状态：%s" % json.dumps(
                   got, ensure_ascii=False))
    summary = result.get("summary", {})
    checks.add("S2B_summary_counts_per_status",
               summary.get("total") == len(want)
               and summary.get("by_status") == {
                   "已废止": 1, "虚构": 1, "误引": 1, "失效": 1,
                   "现行": 1, "已修订": 1}
               and summary.get("accounting") == "per_citation_scoped",
               "by_status 计数逐状态对账＝%s" % summary.get("by_status"))
    # 无文档级 PASS 笼统结论（结构性断言：好/坏文档响应均无此类字段）
    dumped = json.dumps(result, ensure_ascii=False)
    good = call_entry("citation.verify_document",
                      {"text": "依据《%s》第一条：“%s”" % (
                          ANCHORS["CUR"], CUR_ARTICLE1_QUOTE),
                       "as_of": RUN_DATE}, config)
    good_dump = json.dumps(good["payload"].get("result", {}),
                           ensure_ascii=False)
    banned = ('"document_pass"', '"all_verified"', '"pass": true',
              '"overall"', '"document_verified"')
    checks.add("S2C_no_document_level_pass_verdict",
               response["exit"] == 0 and good["exit"] == 0
               and not any(b in dumped or b in good_dump for b in banned)
               and "逐条范围记账" in summary.get("note", ""),
               "好/坏文档响应均无 document_pass/all_verified/overall 类"
               "笼统字段；summary.note 明示无文档级 PASS")
    # 反例三拒：虚构/失效/误引 verified_scoped 恒 False（不能标全核）
    rejects = [by_text.get("《%s》第一条" % FABRICATED_TITLE),
               by_text.get("《%s》第十条" % ANCHORS["EXP"]),
               by_text.get("《%s》第九百九十九条" % ANCHORS["CUR"])]
    ok = all(r and r.get("verified_scoped") is False
             and r.get("status") in ("虚构", "失效", "误引") for r in rejects)
    checks.add("S2D_counterexample_triple_rejected", ok,
               "虚构/失效/误引三条 verified_scoped=False——"
               "虚构/失效/误引不能标全核（反例三拒）")
    # 同一文档同一部法两条引用状态互不覆盖（第一条现行 vs 第九十九条误引）
    ok = (by_text.get("《%s》第一条" % ANCHORS["CUR"], {}).get("status")
          == "现行"
          and by_text.get("《%s》第九百九十九条" % ANCHORS["CUR"], {})
          .get("status") == "误引")
    checks.add("S2E_same_statute_records_never_bleed", ok,
               "同法两条引用（第一条/第九百九十九条）状态互不覆盖："
               "现行/误引并存")
    return result


def section_s3(checks: Checks) -> None:
    sys.path.insert(0, str(REPO_ROOT / "implementation" / "python"))
    import citation_verifier as cv  # noqa: E402

    # 同输入字节级同输出（确定性）
    doc = BAD_DOC.format(ABO=ANCHORS["ABO"], FAB=FABRICATED_TITLE,
                         CUR=ANCHORS["CUR"], EXP=ANCHORS["EXP"],
                         AMD=ANCHORS["AMD"], QUOTE=CUR_ARTICLE1_QUOTE)
    a = json.dumps(cv.parse_citations(doc), ensure_ascii=False,
                   sort_keys=True)
    b = json.dumps(cv.parse_citations(doc), ensure_ascii=False,
                   sort_keys=True)
    checks.add("S3A_same_input_same_output", a == b and len(a) > 1000,
               "同一合成引用文档两次解析 JSON 字节级相同（%d 字符）" % len(a))
    # 引号感知句界：引文含句号不断段、引文归属不串门
    items = cv.parse_citations(
        "《甲法》第一条。《乙法》第二条：“乙的引文，含句号。”")
    ok = (len(items) == 2
          and items[0]["title"] == "甲法" and items[0]["quote"] is None
          and items[1]["quote"] == "乙的引文，含句号。")
    checks.add("S3B_quote_aware_segments", ok,
               "《边界断段＋引文内句号不断段＋引文归属乙不串甲：%s" %
               [(i["citation_text"], i["quote"]) for i in items])
    # 千位中文数字
    ok = all(cv.parse_cn_numeral(t) == v for t, v in (
        ("一", 1), ("十五", 15), ("一百零一", 101), ("九百九十九", 999),
        ("一千二百六十", 1260), ("二千零一", 2001)))
    checks.add("S3C_cn_numerals", ok and cv.parse_cn_numeral("x") is None,
               "中文法定数字解析含千位；非法字符拒绝返回 None")
    # 款/项跟随
    items = cv.parse_citations("依据《甲法》第二十条第三款处理。")
    checks.add("S3D_subrefs_attached", len(items) == 1
               and items[0]["subrefs"] == "第三款",
               "款跟随条文：%r" % items[0]["subrefs"])
    # 静态扫描：零网络/零写/零非确定模块
    tree = ast.parse(CITATION_MODULE.read_text(encoding="utf-8"))
    violations: list = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        else:
            names = []
        for name in names:
            if name.split(".")[0] in {m.split(".")[0]
                                      for m in NETWORK_MODULES}:
                violations.append("network_import:" + name)
            if name in NONDETERMINISTIC_IMPORTS:
                violations.append("nondeterministic_import:" + name)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id == "open":
            if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant) \
                    and node.args[1].value in WRITE_MODES:
                violations.append("write_mode_open")
    checks.add("S3E_module_static_scan", not violations,
               "AST 扫描 citation_verifier.py：%s"
               % (";".join(violations) or "零网络 import、零写模式 open、"
                  "零 random/secrets——解析纯正则/状态机，无模型参与"))


def section_s4(checks: Checks, formal_root: str, codices_repo: str) -> None:
    lccc_path = os.path.join(codices_repo, "lccc_consumer.py")
    checks.add("S4A_frozen_face_v11_pinned",
               os.path.isfile(lccc_path)
               and sha256_file(lccc_path) == LCCC_V11_SHA256,
               "lccc_consumer.py v1.1 sha256=%s（find_by_title＋进程级"
               "只读扫描缓存；漂移即响亮失败）" % LCCC_V11_SHA256[:16])
    # find_by_title 只读：消费前后正式面指纹不变
    sys.path.insert(0, codices_repo)
    import lccc_consumer  # noqa: E402
    consumer = lccc_consumer.LcccConsumer(formal_root)
    before = consumer.face_fingerprint()
    rows = consumer.find_by_title(ANCHORS["CUR"])
    consumer.find_by_title("不存在的标题")
    checks.add("S4B_find_by_title_readonly",
               consumer.face_fingerprint() == before and len(rows) >= 1
               and all(r["bt"] == ANCHORS["CUR"] for r in rows),
               "标题定位前后正式面指纹不变（只读）；命中 %d 版" % len(rows))
    # 精确匹配纪律：前缀/包含不命中
    checks.add("S4C_exact_match_no_fuzzy",
               consumer.find_by_title(ANCHORS["CUR"] + "实施细则") == []
               and consumer.find_by_title("个人信息保护法") == [],
               "子串/去前缀变体一律不命中（无模糊猜测）")
    # 替代链空表落地（继承 E22 冻结面事实）
    path = os.path.join(formal_root, "legal_relations.csv")
    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
        relations = [row for row in csv.DictReader(handle)]
    checks.add("S4D_legal_relations_empty_grounded", len(relations) == 0,
               "legal_relations.csv 数据行=%d（空表→replacement 恒 unknown "
               "是数据边界，非实现缺口）" % len(relations))


def section_s5(checks: Checks, codices_repo: str, formal_root: str) -> None:
    bad = _verify("《%s》第一条" % ANCHORS["CUR"], {})
    payload = bad["payload"]
    checks.add("S5A_unconfigured_bridge_fails_named_exit3",
               bad["exit"] == 3 and payload.get("status") == "NOT_CONNECTED"
               and payload.get("code") == "codices_import_path_not_configured",
               "空配置 → exit=%s %s/%s" % (bad["exit"],
                                           payload.get("status"),
                                           payload.get("code")))
    unknown = call_entry("citation.check_all",
                         {"text": "《%s》第一条" % ANCHORS["CUR"]},
                         {"codices_import_path": codices_repo,
                          "codices_formal_root": formal_root})
    payload = unknown["payload"]
    checks.add("S5B_unknown_method_fails_named_exit3",
               unknown["exit"] == 3 and payload.get("status") == "NOT_CONNECTED"
               and "method_not_connected" in str(payload.get("code")),
               "citation.check_all → exit=%s %s/%s" % (
                   unknown["exit"], payload.get("status"),
                   payload.get("code")))
    missing = call_entry("citation.verify_document",
                         {"as_of": RUN_DATE},
                         {"codices_import_path": codices_repo,
                          "codices_formal_root": formal_root})
    payload = missing["payload"]
    checks.add("S5C_missing_text_fails_named_exit3",
               missing["exit"] == 3
               and payload.get("status") == "NOT_CONNECTED"
               and str(payload.get("code"))
               == "citation_document_text_required",
               "verify_document 缺 text → exit=%s %s" % (
                   missing["exit"], payload.get("code")))


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("desktop", "selfhost"),
                        default="desktop")
    parser.add_argument("--formal-root", default=DEFAULT_FORMAL_ROOT)
    parser.add_argument("--codices-repo", default=DEFAULT_CODICES_REPO)
    parser.add_argument("--evidence-root", default="evidence/F70")
    args = parser.parse_args()

    lccc_path = os.path.join(args.codices_repo, "lccc_consumer.py")
    if not os.path.isfile(lccc_path):
        print("FATAL: lccc_consumer.py 不在 %s（E22 冻结面 v1.1）"
              % args.codices_repo)
        return 2
    if sha256_file(lccc_path) != LCCC_V11_SHA256:
        print("FATAL: 冻结面 v1.1 lccc_consumer.py sha256 漂移")
        return 2

    config = {
        "codices_import_path": args.codices_repo,
        "codices_formal_root": args.formal_root,
    }
    checks = Checks()
    rows = load_document_rows(args.formal_root)
    missing = [k for k, title in ANCHORS.items() if title not in rows]
    if missing:
        print("FATAL: 锚点标题未在正式表命中：%s" % missing)
        return 2
    s1_results = section_s1(checks, rows, config)
    doc_result = section_s2(checks, config)
    section_s3(checks)
    section_s4(checks, args.formal_root, args.codices_repo)
    section_s5(checks, args.codices_repo, args.formal_root)

    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True,
        cwd=str(REPO_ROOT)).stdout.strip()
    evidence = {
        "run_date": RUN_DATE,
        "profile": args.profile,
        "command": "python -X utf8 %s --profile %s --formal-root %s "
                   "--codices-repo %s"
                   % (sys.argv[0], args.profile, args.formal_root,
                      args.codices_repo),
        "cwd": str(REPO_ROOT),
        "subject_commit": commit,
        "formal_root": args.formal_root,
        "frozen_face": {
            "lccc_consumer.py(v1.1)": sha256_file(lccc_path),
            "legal_documents.csv": sha256_file(
                os.path.join(args.formal_root, "legal_documents.csv")),
            "legal_relations.csv": sha256_file(
                os.path.join(args.formal_root, "legal_relations.csv")),
        },
        "anchors": ANCHORS,
        "fabricated_title": FABRICATED_TITLE,
        "single_citations": [r for r in s1_results if r],
        "document_accounting": {
            "total": doc_result.get("summary", {}).get("total"),
            "by_status": doc_result.get("summary", {}).get("by_status"),
        },
        "checks": checks.items,
        "passed": checks.passed_count,
        "total": len(checks.items),
        "overall": "PASS" if checks.all_passed else "FAIL",
    }
    out_dir = REPO_ROOT / args.evidence_root / args.profile
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "f70-citation-verifier-recon.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=1),
        encoding="utf-8")
    print("---")
    print("RECON_%s %d/%d checks — profile=%s" % (
        "OK" if checks.all_passed else "FAIL",
        checks.passed_count, len(checks.items), args.profile))
    return 0 if checks.all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
