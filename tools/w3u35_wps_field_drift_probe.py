#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""W3-U35 E13 c16 fldChar 漂移确定性复量探针（工单 W3-U35 ①②）。

在案事实（evidence/E13/logs/F46-wps+F52-wps.log:27,50·2026-10-18/19 三跑同相）：
  c16_selfbuilt_complex_host_fidelity FAIL，fields={instrtext:4,
  fldsimple_in:0, fldsimple_before:2, fldchar_in:12, fldchar_before:6}，
  remaining=0。W2b-U49 A/B 探针已证 main@e9a1fd4 原工具原面同败＝预存宿主
  漂移非回归。本探针把「漂移源」钉到子句级，解析/对比一律确定性
  （ElementTree 域状态机＋字节正则计数），不靠模型猜。

方法（全合成材料；真 WPS COM 会话，纪律同 implementation/python/wps_host.py：
DispatchEx KWPS.Application 独立进程·进程内串行锁·Visible=False·用毕必
Quit·工作文件落显式临时状态根·绝不写 %APPDATA%\\JusBench）：

  S0 生成器期望面＝tools/PENDING_OWNER_f46_f52_wps_host_recon.py 的
     build_complex_docx()（c16 所测同一字节面）——域状态机清点
     （form/instr/result 逐域）＋字节正则计数（fldSimple/fldChar/
     fldCharType=begin|separate|end/instrText）。
  S1 宿主版本面＝wpshost.available 真启动读 version/build（对照 W2b-U36
     钉定 12.1.0.28802）。
  S2 隔离臂（开+存，不动修订）：同一 COM 纪律 Open(可写)→立即 SaveAs2→
     域状态机清点——回答「漂移是否在 open/save 即发生、与 accept/reject
     无关」。
  S3 产品面回流＝legal_entry wpshost.review＋wpshost.decide（accept=
     前手插入 900 段·reject=前手删除 901 段，与 c16 同选择器）→重读盘上
     实际字节→域状态机清点＋修订标记统计。
  S4 c16 子句逐条复评＝把 c16 断言（PENDING_OWNER_f46_f52_wps_host_recon
     .py:929-953）拆成封闭子句清单，逐条对 S3 实际字节求值，每条
     PASS/FAIL＋实际值具名。
  S5 域对比判定＝before/after 逐域（form/instr 归一化/result）：
     - instr 集 preserved＋result 漂移（DATE 缓存值→当日形）＝宿主域重算
       （表示形漂移·指令语义保真）；
     - instr 缺失/变值＝真域丢失（宿主保真缺口）。
     判定输出「漂移源分类」字符串，供工单②分支裁量。

输出：evidence/E13/patch-chain/w3u35-field-drift-probe.json/.md。
退出码：0=测量完成（子句判定是数据不是门）；3=WPS/pywin32 缺失；
2=探针自身失败。
"""
from __future__ import annotations

import base64
import json
import re
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))
sys.path.insert(0, str(REPO_ROOT / "implementation" / "python"))

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

import legal_entry  # noqa: E402
import wps_host  # noqa: E402
import PENDING_OWNER_f46_f52_wps_host_recon as recon  # noqa: E402

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = "{%s}" % W_NS
PINNED_BUILD = "12.1.0.28802"
OUT_DIR = REPO_ROOT / "evidence" / "E13" / "patch-chain"

DATE_INSTR_NORM = 'DATE \\@ "YYYY-MM-DD"'


def norm_instr(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def byte_counts(doc_xml: bytes) -> dict:
    xml = doc_xml.decode("utf-8")
    return {
        "fldSimple_tag": len(re.findall(r"<w:fldSimple[ >]", xml)),
        "fldChar_tag": len(re.findall(r"<w:fldChar[ >]", xml)),
        "fldChar_begin": len(re.findall(r'w:fldCharType="begin"', xml)),
        "fldChar_separate": len(re.findall(r'w:fldCharType="separate"', xml)),
        "fldChar_end": len(re.findall(r'w:fldCharType="end"', xml)),
        "instrText": xml.count("instrText"),
        "byte_fldSimple": doc_xml.count(b"fldSimple"),
        "byte_fldChar": doc_xml.count(b"fldChar"),
        "byte_instrText": doc_xml.count(b"instrText"),
    }


def field_census(doc_xml: bytes) -> list:
    """域状态机清点（document order；fldSimple 与 fldChar 复杂域双形态）。

    返回 [{form, instr(归一化), result(平文)}]；复杂域 instr=begin..separate
    的 instrText 连接，result=separate..end 的 w:t 连接。
    """
    root = ET.fromstring(doc_xml)
    fields: list = []
    state = "outside"
    cur: dict | None = None
    for el in root.iter():
        if el.tag == W + "fldSimple":
            fields.append({
                "form": "fldSimple",
                "instr": norm_instr(el.get(W + "instr") or ""),
                "result": recon._norm("".join(
                    t.text or "" for t in el.iter(W + "t"))),
            })
        elif el.tag == W + "fldChar":
            kind = el.get(W + "fldCharType")
            if kind == "begin":
                cur = {"form": "complex", "instr": "", "result": ""}
                state = "instr"
            elif kind == "separate":
                state = "result"
            elif kind == "end":
                if cur is not None:
                    cur["instr"] = norm_instr(cur["instr"])
                    fields.append(cur)
                cur, state = None, "outside"
        elif el.tag == W + "instrText" and state == "instr" \
                and cur is not None:
            cur["instr"] += (el.text or "")
        elif el.tag == W + "t" and state == "result" and cur is not None:
            cur["result"] += (el.text or "")
    return fields


def classify(before: list, after: list) -> dict:
    """生成器期望面 vs WPS 行为面确定性对比→漂移源分类。"""
    before_instrs = sorted(f["instr"] for f in before)
    after_instrs = sorted(f["instr"] for f in after)
    per_field = []
    instr_preserved = before_instrs == after_instrs
    date_result_drift = None
    for bf in before:
        match = next((af for af in after if af["instr"] == bf["instr"]), None)
        if match is None:
            per_field.append({"instr": bf["instr"], "after": None,
                              "instr_preserved": False,
                              "result_preserved": None})
            continue
        result_preserved = match["result"] == bf["result"]
        if bf["instr"].upper().startswith("DATE") \
                and match["result"] != bf["result"]:
            date_result_drift = {
                "before": bf["result"], "after": match["result"],
                "after_date_shaped": bool(
                    re.fullmatch(r"\d{4}-\d{2}-\d{2}", match["result"]))}
        per_field.append({"instr": bf["instr"],
                          "before_form": bf["form"],
                          "after_form": match["form"],
                          "before_result": bf["result"],
                          "after_result": match["result"],
                          "instr_preserved": True,
                          "result_preserved": result_preserved})
    extra = [f for f in after
             if f["instr"] not in before_instrs]
    lost = [i for i in before_instrs if i not in after_instrs]
    if lost:
        verdict = "field_lost_by_host（真域丢失·宿主保真缺口）"
    elif not instr_preserved:
        verdict = "instruction_mutated_by_host（指令变值·宿主保真缺口）"
    elif date_result_drift is not None:
        verdict = ("host_field_recalc_representation_only"
                   "（宿主域重算·指令语义保真·缓存结果值漂移）")
    elif all(p["result_preserved"] for p in per_field) and not extra:
        verdict = "roundtrip_fidelity_full（域全保真）"
    else:
        verdict = "other_named_drift"
    return {"verdict": verdict, "instr_preserved": instr_preserved,
            "per_field": per_field, "extra_after": extra,
            "date_result_drift": date_result_drift}


def c16_clauses(recon_parts_before: dict, review: dict, decide: dict,
                parts_after: dict) -> list:
    """c16 断言（recon 工具 :929-953）拆封闭子句逐条对实际字节求值。"""
    sb_marks = recon.revision_marks(recon_parts_before)
    doc_xml_d = parts_after["word/document.xml"]
    plain_d = recon.plain_text(parts_after)
    marks_d = recon.revision_marks(parts_after)
    clauses = [
        ("revision_count==ins+del_before(2)",
         review["revision_count"] == sb_marks["ins"] + sb_marks["del"],
         {"host": review["revision_count"],
          "ooxml": sb_marks["ins"] + sb_marks["del"]}),
        ("instrText_bytes>=2", doc_xml_d.count(b"instrText") >= 2,
         {"actual": doc_xml_d.count(b"instrText")}),
        ("DATE_in_xml", b"DATE" in doc_xml_d, {}),
        ("PAGE_in_xml", b"PAGE" in doc_xml_d, {}),
        ("cached_date_2026-10-16_in_plain",
         "2026-10-16" in plain_d,
         {"date_hits": plain_d.count("2026-10-16")}),
        ("static_text_当日页码_in_plain", "当日页码" in plain_d, {}),
        ("gridSpan_in_xml", b"gridSpan" in doc_xml_d, {}),
        ("numId_in_xml", b"numId" in doc_xml_d, {}),
        ("header_part_kept", "word/header1.xml" in parts_after, {}),
        ("footer_part_kept", "word/footer1.xml" in parts_after, {}),
        ("footnotes_part_kept", "word/footnotes.xml" in parts_after, {}),
        ("numbering_part_kept", "word/numbering.xml" in parts_after, {}),
        ("prior_ins_text_in_plain",
         recon._norm(recon.PRIOR_INS_TEXT) in plain_d, {}),
        ("prior_del_text_in_plain",
         recon._norm(recon.PRIOR_DEL_TEXT) in plain_d, {}),
        ("marks_after==remaining",
         marks_d["ins"] + marks_d["del"] == decide["remaining_count"],
         {"marks": marks_d["ins"] + marks_d["del"],
          "remaining": decide["remaining_count"]}),
        ("remaining==0", decide["remaining_count"] == 0,
         {"remaining": decide["remaining_count"]}),
    ]
    return [{"clause": name, "ok": bool(ok), "facts": facts}
            for name, ok, facts in clauses]


def main() -> int:
    try:
        import pythoncom  # noqa: F401
        import win32com.client  # noqa: F401
    except ImportError:
        print("PROBE_BLOCKED: pywin32 missing")
        return 3
    probe = wps_host.wps_available()
    if not probe.get("installed"):
        print("PROBE_BLOCKED: KWPS.Application unavailable")
        return 3

    doc = {
        "schema": "juscite-w3u35-field-drift-probe/1",
        "started": datetime.now(timezone.utc).isoformat(),
        "in_case_facts": {
            "source": "evidence/E13/logs/F46-wps+F52-wps.log:27,50",
            "fields": {"instrtext": 4, "fldsimple_in": 0,
                       "fldsimple_before": 2, "fldchar_in": 12,
                       "fldchar_before": 6},
            "ab_probe": "W2b-U49：main@e9a1fd4 原工具原面同败＝预存宿主漂移"},
    }

    # ---- S0 生成器期望面 ------------------------------------------------
    self_built = recon.build_complex_docx()
    parts_before = recon._load_parts(self_built)
    doc_xml_before = parts_before["word/document.xml"]
    census_before = field_census(doc_xml_before)
    counts_before = byte_counts(doc_xml_before)
    doc["generator_surface"] = {
        "sha256_prefix": recon.sha256_bytes(self_built)[:16],
        "census": census_before, "counts": counts_before}
    print("[S0] generator census:", json.dumps(census_before, ensure_ascii=False))
    print("[S0] generator counts:", json.dumps(counts_before))

    # ---- S1 宿主版本面 --------------------------------------------------
    host = probe["host"]
    doc["host_surface"] = {"progid": host["progid"],
                           "version": host["version"],
                           "build": host["build"],
                           "build_matches_w2bu36_pinned":
                               host["build"] == PINNED_BUILD}
    print("[S1] host:", json.dumps(doc["host_surface"]))

    # ---- S2 隔离臂：Open+SaveAs2 不动修订 -------------------------------
    tmp = tempfile.TemporaryDirectory(prefix="juscite-w3u35-probe-")
    state_root = Path(tmp.name) / "state"
    state_root.mkdir(parents=True)
    with wps_host._wps_session(state_root,
                               "probe-" + uuid.uuid4().hex[:8]) as (app, work):
        src = work / "open-save.docx"
        src.write_bytes(self_built)
        d = app.Documents.Open(str(src), False, False)
        try:
            out = work / "open-save-result.docx"
            d.SaveAs2(str(out), 12)
            d.Close(False)
        except Exception as exc:  # noqa: BLE001
            raise AssertionError("save_arm_failed:" + type(exc).__name__) \
                from None
        open_save_bytes = out.read_bytes()
    os_parts = recon._load_parts(open_save_bytes)
    census_opensave = field_census(os_parts["word/document.xml"])
    counts_opensave = byte_counts(os_parts["word/document.xml"])
    doc["open_save_arm"] = {
        "census": census_opensave, "counts": counts_opensave,
        "classification": classify(census_before, census_opensave)}
    print("[S2] open+save census:",
          json.dumps(census_opensave, ensure_ascii=False))

    # ---- S3 产品面回流（与 c16 同选择器） -------------------------------
    product_config = {"wps_host_state_root": str(state_root / "wps-host")}
    review = legal_entry.call("wpshost.review",
                              {"docx_b64": base64.b64encode(self_built)
                               .decode("ascii")}, product_config)
    accept_d, reject_d = [], []
    for rev in review["revisions"]:
        text = recon._norm(rev["text"])
        if text and text in recon.PRIOR_INS_TEXT:
            accept_d.append({"type": rev["type_name"], "mode": "equals",
                             "text": rev["text"]})
        elif text and text in recon.PRIOR_DEL_TEXT:
            reject_d.append({"type": rev["type_name"], "mode": "equals",
                             "text": rev["text"]})
    decide = legal_entry.call("wpshost.decide", {
        "docx_b64": base64.b64encode(self_built).decode("ascii"),
        "accept": accept_d, "reject": reject_d}, product_config)
    result_bytes = base64.b64decode(decide["result_docx_b64"])
    parts_after = recon._load_parts(result_bytes)
    census_after = field_census(parts_after["word/document.xml"])
    counts_after = byte_counts(parts_after["word/document.xml"])
    doc["product_roundtrip"] = {
        "review_revision_count": review["revision_count"],
        "acted_accept": len(decide["acted_accept"]),
        "acted_reject": len(decide["acted_reject"]),
        "remaining_count": decide["remaining_count"],
        "census": census_after, "counts": counts_after}
    print("[S3] roundtrip census:", json.dumps(census_after, ensure_ascii=False))
    print("[S3] roundtrip counts:", json.dumps(counts_after))

    # ---- S4 c16 子句逐条复评 --------------------------------------------
    clauses = c16_clauses(parts_before, review, decide, parts_after)
    doc["c16_clauses"] = clauses
    failed = [c["clause"] for c in clauses if not c["ok"]]
    doc["c16_failed_clauses"] = failed
    print("[S4] c16 failed clauses:", json.dumps(failed, ensure_ascii=False))

    # ---- S5 域对比判定 ----------------------------------------------------
    doc["field_comparison"] = classify(census_before, census_after)

    doc["finished"] = datetime.now(timezone.utc).isoformat()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUT_DIR / "w3u35-field-drift-probe.json"
    json_path.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                         encoding="utf-8")
    lines = [
        "# W3-U35 c16 fldChar 漂移确定性复量探针", "",
        f"- 起止：{doc['started']} → {doc['finished']}",
        f"- 宿主：{host['progid']} version={host['version']} "
        f"build={host['build']}"
        f"（与 W2b-U36 钉定 {PINNED_BUILD} "
        f"{'一致' if doc['host_surface']['build_matches_w2bu36_pinned'] else '不一致'}）",
        "",
        "## 生成器期望面（c16 所测同字节面）",
        "",
        "| form | instr | result |", "|---|---|---|",
    ]
    for f in census_before:
        lines.append(f"| {f['form']} | `{f['instr']}` | {f['result']} |")
    lines += ["", "## 产品面回流（wpshost.review+decide 实际字节）", "",
              "| form | instr | result |", "|---|---|---|"]
    for f in census_after:
        lines.append(f"| {f['form']} | `{f['instr']}` | {f['result']} |")
    lines += ["", f"- 计数 before：`{json.dumps(counts_before)}`",
              f"- 计数 after：`{json.dumps(counts_after)}`",
              f"- 隔离臂（Open+SaveAs2 不动修订）分类："
              f"**{doc['open_save_arm']['classification']['verdict']}**",
              f"- 产品面回流分类：**{doc['field_comparison']['verdict']}**",
              "",
              "## c16 子句逐条复评", "",
              "| 子句 | 判定 | 事实 |", "|---|---|---|"]
    for c in clauses:
        lines.append(f"| `{c['clause']}` | {'PASS' if c['ok'] else '**FAIL**'} "
                     f"| `{json.dumps(c['facts'], ensure_ascii=False)}` |")
    lines += ["", f"- **c16 败因子句＝{json.dumps(failed, ensure_ascii=False)}**",
              ""]
    md_path = OUT_DIR / "w3u35-field-drift-probe.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print("[out]", json_path.relative_to(REPO_ROOT))
    print("[out]", md_path.relative_to(REPO_ROOT))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as error:
        print("PROBE_FAIL:", error)
        raise SystemExit(2) from None
