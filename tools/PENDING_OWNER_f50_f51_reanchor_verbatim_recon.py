#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""F50+F51 义务验收 recon（W2b-U13）：引用原文重锚定＋引用前逐字核验
——双 profile（desktop/selfhost）四实例（F50-desktop/F50-selfhost/
F51-desktop/F51-selfhost）。

义务 06:F50 断言：「定位一律引用原文重锚定、禁偏移换算；插入后按原文
重锚仍定位正确；零/多命中不以偏移强改」。
义务 06:F51 断言：「引用前逐字核验（NOT FOUND 禁呈现，不就近匹配）；
引用逐字定位成功才改；NOT_FOUND 拒自动修改并给人工入口」。
反例集（工单钦定）＝同形文本多命中／近形文本零命中逐字对账。

硬门（每 profile，真桥 CLI 子进程径）：
- C01 登记即逐字验证：唯一命中才建锚（span==独立复算）＋同键同事实幂等
  （anchors.json 字节不动）。
- C02 插入/删除后重锚仍定位正确（F50 本体）：前插→shift==插入长度；
  后插→shift==0；前删→shift==-删除长度；position_source 恒 quote 搜索。
- C03 同形文本多命中反例：quote 出现 2 次→AMBIGUOUS 且响应零位置字段
  ——偏移换算值（登记 span＋已知插入量）明明可得且恰好命中其一，本面
  仍不给任何 span（不以偏移强改）；locate 纯查询不写状态。
- C04 近形文本零命中反例：引文内一字之差／ASCII 大小写折叠／全半角
  逗号——全部 NOT_FOUND 零位置字段（大小写不折叠、零规范化；偏移换算
  本可返回陈旧位置，本面不给）。
- C51a F51 正向：唯一逐字命中才 PROCEED（proposed_text==独立复算；
  人工队列为空）；纯核验态（无 replacement）auto_edit=None。
- C06 NOT_FOUND 拒自动修改＋人工入口：NOT_FOUND_REFUSED 无
  proposed_text/span；队列条目 reason=not_found；同内容幂等（重发同
  entry_id 不双登）；异拟改文 append-only 追加。
- C07 多命中拒自动修改＋人工入口：AMBIGUOUS_REFUSED＋reason=ambiguous。
- C08 人工入口闭集字段回读（字段闭集＋pending＋append-only 不改写）。
- C09 登记负向：quote 缺失/重复具名拒；同键异文本重登记具名拒（溯源
  不可改写）；anchor.read 溯源事实全程未变。
- C10 桥 fail-closed 负向（缺状态根/未知方法/坏 id/未登记锚）＋错误码
  纯码不携材料内容。
- C11 确定性：同序列两状态根（剥时间戳）规范化摘要相等＋跨 profile
  anchor_id/entry_id 相等。
- C12 语料只读锚＋AST 纪律（导入闭集；无随机/网络/模糊匹配面——
  不就近匹配是结构性缺席）。

语料全合成（00-总协调 §6.1 裁决#1，绝无真实文档）。

用法（juscite worktree w2b-u13 仓根 cwd）：
  python -X utf8 tools/PENDING_OWNER_f50_f51_reanchor_verbatim_recon.py \
      --profile desktop --profile selfhost

退出码：0＝全部 profile RECON_OK；2＝RECON_FAIL；3＝环境缺失。
证据：docs/construction/evidence/{F50,F51}/<profile>/（同一跑批双义务
目录，F38/F44 先例）。
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TEMP = Path(os.environ.get("TEMP", "."))
BRIDGE = REPO / "implementation" / "python" / "legal_entry.py"
SCHEMA = "juscite-f50-f51-document-anchor/1"
MODULE = REPO / "implementation" / "python" / "document_anchor.py"

# 跨 profile 确定性锚（desktop 先跑落值，selfhost 复核相等）
_CROSS_PROFILE: dict[str, str] = {}

# 全合成语料（确定性内容，无 RNG）
DOC_CONTRACT = (
    "合成测试合同（F50-F51-RECON，全部当事人与金额均为虚构）\n"
    "合同编号：SYN-F50-2026-001\n"
    "甲方：合成当事人甲（虚构）\n"
    "乙方：合成当事人乙（虚构）\n"
    "第三条 价款与支付\n"
    "3.1 合同总价款为人民币360,000.00元（大写：叁拾陆万元整），一次性支付。\n"
    "3.2 甲方应在每期验收合格后三十日内支付当期价款；逾期按日万分之五支付违约金。\n"
    "第四条 交付与验收\n"
    "4.1 乙方应于2026年12月31日前完成全部合成交付物并通过验收。\n"
    "第五条 其他\n"
    "5.1 本合同为合成测试文本，不构成任何真实法律行为。\n"
)
QUOTE_A = ("甲方应在每期验收合格后三十日内支付当期价款；"
           "逾期按日万分之五支付违约金。")
INSERT_BEFORE = "3.0 本合同价款已包含全部税费与运费。\n"
DUP_LINE = ("\n备注条款（复述）：甲方应在每期验收合格后三十日内支付当期价款；"
            "逾期按日万分之五支付违约金。\n")
REPL_A = ("甲方应在每期验收合格后四十五日内支付当期价款；"
          "逾期按日万分之五支付违约金。")
REPL_A2 = "（人工复核后拟改文本·二号方案）"
REPL_A3 = "（多命中情形拟改文本）"

DOC_MEMO = (
    "合成会议备忘录（F50-F51-RECON，全部内容虚构）\n"
    "会议时间：2026-10-16 10:00（虚构）\n"
    "出席人员：合成人员一、合成人员二\n"
    "决议一：Party A shall pay within 30 days after acceptance.\n"
    "决议二：合同金额小写 360,000.00 元与合同文本记载一致。\n"
    "决议三：其余事项按合成合同原条款执行。\n"
)
QUOTE_B = "Party A shall pay within 30 days after acceptance."
QUOTE_C = "合同金额小写 360,000.00 元与合同文本记载一致。"
REPL_B = "Party A shall pay within 45 days after acceptance."


def eprint(*a) -> None:
    print(*a, file=sys.stderr, flush=True)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_corpus(corpus: Path) -> bool:
    if (corpus / "doc-contract.txt").is_file() \
            and (corpus / "doc-memo.txt").is_file():
        return True
    corpus.mkdir(parents=True, exist_ok=True)
    eprint(f"[GEN] 合成语料不存在，生成 → {corpus}")
    (corpus / "doc-contract.txt").write_text(DOC_CONTRACT, encoding="utf-8",
                                             newline="")
    (corpus / "doc-memo.txt").write_text(DOC_MEMO, encoding="utf-8",
                                         newline="")
    return (corpus / "doc-contract.txt").is_file() \
        and (corpus / "doc-memo.txt").is_file()


def corpus_identity_digest(corpus: Path) -> str:
    parts = [sha256_file(corpus / n)
             for n in ("doc-contract.txt", "doc-memo.txt")]
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def find_all(text: str, quote: str) -> list[int]:
    """独立复算（与被验面同型算法，供对账）。"""
    hits, start = [], 0
    while True:
        idx = text.find(quote, start)
        if idx < 0:
            return hits
        hits.append(idx)
        start = idx + 1


def canonical_digest(obj) -> str:
    """剥时间戳后的规范化摘要（确定性对账；created_utc/registered utc 类
    全剥）。"""
    def strip(node):
        if isinstance(node, dict):
            return {k: strip(v) for k, v in node.items()
                    if not k.endswith("_utc")}
        if isinstance(node, list):
            return [strip(v) for v in node]
        return node
    return sha256_bytes(json.dumps(strip(obj), ensure_ascii=False,
                                   sort_keys=True).encode("utf-8"))


# --------------------------------------------------------------------------
# 真桥 CLI 子进程径（与产品桌面/服务调用完全同形）
# --------------------------------------------------------------------------

def bridge_call(config: dict, method: str, args: dict,
                timeout: int = 120) -> tuple[int, dict]:
    with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", suffix=".json", delete=False) as req, \
         tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", suffix=".json", delete=False) as cfg:
        json.dump({"method": method, "args": args}, req, ensure_ascii=False)
        json.dump(config, cfg, ensure_ascii=False)
        req_name, cfg_name = req.name, cfg.name
    try:
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", str(BRIDGE),
             "--request-json", req_name, "--config", cfg_name],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout)
        payload = {}
        if proc.stdout.strip():
            try:
                payload = json.loads(proc.stdout)
            except json.JSONDecodeError:
                payload = {"raw": proc.stdout[-400:]}
        return proc.returncode, payload
    finally:
        os.unlink(req_name)
        os.unlink(cfg_name)


def _mini_sequence(cfg: dict, corpus: Path) -> list[dict]:
    """确定性小序列（C11 两根对账＋跨 profile 锚）：登记 A/B、前插重锚、
    B 正向改、A 近形拒改。返回响应列表（含 status 字段供失败对账）。"""
    t0 = (corpus / "doc-contract.txt").read_text(encoding="utf-8")
    m0 = (corpus / "doc-memo.txt").read_text(encoding="utf-8")
    t1 = t0.replace("3.1 ", INSERT_BEFORE + "3.1 ", 1)
    out = []
    rc, r = bridge_call(cfg, "anchor.register", {
        "document_id": "doc-contract", "matter_id": "M-SYN-001",
        "quote": QUOTE_A, "text": t0})
    out.append({"rc": rc, "anchor_id": r.get("result", {}).get("anchor_id")})
    rc, r = bridge_call(cfg, "anchor.register", {
        "document_id": "doc-memo", "matter_id": "M-SYN-001",
        "quote": QUOTE_B, "text": m0})
    out.append({"rc": rc, "anchor_id": r.get("result", {}).get("anchor_id")})
    anchor_a = out[0]["anchor_id"]
    anchor_b = out[1]["anchor_id"]
    rc, r = bridge_call(cfg, "anchor.locate", {
        "document_id": "doc-contract", "anchor_id": anchor_a, "text": t1})
    out.append({"rc": rc, "verbatim": r.get("result", {}).get("verbatim")})
    rc, r = bridge_call(cfg, "anchor.gate_edit", {
        "document_id": "doc-memo", "anchor_id": anchor_b, "text": m0,
        "replacement": REPL_B})
    out.append({"rc": rc, "gate": r.get("result", {}).get("gate")})
    near = t1.replace("三十日内", "45日内", 1)
    rc, r = bridge_call(cfg, "anchor.gate_edit", {
        "document_id": "doc-contract", "anchor_id": anchor_a, "text": near,
        "replacement": REPL_A2})
    out.append({"rc": rc, "gate": r.get("result", {}).get("gate"),
                "verbatim": r.get("result", {}).get("verbatim")})
    return out


def run_profile(profile: str, args, corpus: Path) -> int:
    evidence_f50 = REPO / "docs" / "construction" / "evidence" / "F50" \
        / profile
    evidence_f51 = REPO / "docs" / "construction" / "evidence" / "F51" \
        / profile
    state = Path(args.state) if args.state else \
        TEMP / f"juscite-f50f51-state-{profile}"
    if state.exists() and any(state.iterdir()):
        eprint(f"[{profile}] 状态根非空，另起子目录：{state}")
        state = state / f"run-{datetime.now(timezone.utc).strftime('%H%M%S')}"
    config = {"anchor_state_root": str(state)}
    digest_before = corpus_identity_digest(corpus)
    started = now_iso()
    checks: list[dict] = []
    metrics: dict = {}

    def record(name: str, ok: bool, detail: str) -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": detail})
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}", flush=True)

    print(f"\n===== profile {profile}（state={state}）=====", flush=True)

    t0 = (corpus / "doc-contract.txt").read_text(encoding="utf-8")
    m0 = (corpus / "doc-memo.txt").read_text(encoding="utf-8")
    anchors_json = state / "document-anchor" / "doc-contract" / "anchors.json"

    # ---------------------------------------- C01 登记即逐字验证＋幂等
    rc, res = bridge_call(config, "anchor.register", {
        "document_id": "doc-contract", "matter_id": "M-SYN-001",
        "quote": QUOTE_A, "text": t0})
    reg = res.get("result", {})
    anchor_a = reg.get("anchor_id", "")
    expected_span = t0.find(QUOTE_A)
    anchors_before = anchors_json.read_bytes() if anchors_json.is_file() \
        else None
    rc2, res2 = bridge_call(config, "anchor.register", {
        "document_id": "doc-contract", "matter_id": "M-SYN-001",
        "quote": QUOTE_A, "text": t0})
    reg2 = res2.get("result", {})
    record("C01_register_verbatim_unique_idempotent",
           rc == 0 and rc2 == 0
           and reg.get("schema") == SCHEMA
           and reg.get("registered_matches") == 1
           and reg.get("registered_span") == [expected_span,
                                              expected_span + len(QUOTE_A)]
           and anchor_a.startswith("a-") and len(anchor_a) == 2 + 16
           and reg2.get("anchor_id") == anchor_a
           and reg2.get("idempotent") is True
           and anchors_json.is_file()
           and anchors_json.read_bytes() == anchors_before,
           f"span==独立复算 [{expected_span},{expected_span + len(QUOTE_A)}]；"
           f"重复登记幂等（anchor_id 同、anchors.json 字节不动）；"
           f"anchor_id={anchor_a}")
    metrics["anchor_a"] = anchor_a

    # ---------------------------------------- C02 插入/删除后重锚仍正确
    t1 = t0.replace("3.1 ", INSERT_BEFORE + "3.1 ", 1)     # 锚前插入
    rc, res = bridge_call(config, "anchor.locate", {
        "document_id": "doc-contract", "anchor_id": anchor_a, "text": t1})
    v = res.get("result", {}).get("verbatim", {})
    rc_after, res_after = bridge_call(config, "anchor.locate", {
        "document_id": "doc-contract", "anchor_id": anchor_a,
        "text": t0 + "附则（合成）：本合同一式两份。\n"})          # 锚后插入
    v_after = res_after.get("result", {}).get("verbatim", {})
    del_chunk = "3.1 合同总价款为人民币360,000.00元（大写：叁拾陆万元整），一次性支付。\n"
    t_del = t0.replace(del_chunk, "", 1)                   # 锚前删除
    rc_del, res_del = bridge_call(config, "anchor.locate", {
        "document_id": "doc-contract", "anchor_id": anchor_a, "text": t_del})
    v_del = res_del.get("result", {}).get("verbatim", {})
    record("C02_insert_delete_reanchor_located",
           rc == 0 and rc_after == 0 and rc_del == 0
           and v.get("status") == "LOCATED" and v.get("matches") == 1
           and v.get("span") == [t1.find(QUOTE_A),
                                 t1.find(QUOTE_A) + len(QUOTE_A)]
           and v.get("shift") == len(INSERT_BEFORE)
           and v.get("position_source") == "verbatim_quote_match"
           and v.get("offset_conversion_used") is False
           and v_after.get("status") == "LOCATED"
           and v_after.get("shift") == 0
           and v_del.get("status") == "LOCATED"
           and v_del.get("shift") == -len(del_chunk),
           f"锚前插 {len(INSERT_BEFORE)} 字→重锚 span==复算 shift="
           f"{v.get('shift')}；锚后插→shift=0；锚前删 {len(del_chunk)} 字"
           f"→shift={v_del.get('shift')}；位移全部由原文重搜吸收"
           f"（offset_conversion_used=false）")

    # ---------------------------------------- C03 同形多命中反例（禁偏移强改）
    t2 = t1 + DUP_LINE                                        # quote 第二次出现
    hits2 = find_all(t2, QUOTE_A)
    offset_guess = expected_span + len(INSERT_BEFORE)   # 偏移换算值（本可得）
    anchors_bytes_before_locate = anchors_json.read_bytes()
    rc, res = bridge_call(config, "anchor.locate", {
        "document_id": "doc-contract", "anchor_id": anchor_a, "text": t2})
    v = res.get("result", {}).get("verbatim", {})
    no_position = all(k not in v for k in
                      ("span", "shift", "position_source"))
    record("C03_same_shape_multi_hit_no_offset_force",
           len(hits2) == 2 and offset_guess in hits2
           and rc == 0 and v.get("status") == "AMBIGUOUS"
           and v.get("matches") == 2 and no_position
           and anchors_json.read_bytes() == anchors_bytes_before_locate,
           f"同形 quote 命中 {len(hits2)} 处→AMBIGUOUS 且响应零位置字段"
           f"（span/shift/position_source 全无）；偏移换算值 {offset_guess}"
           f" 明明可得且恰为真命中之一，本面不以偏移强改；locate 纯查询"
           f"状态字节不动")

    # ---------------------------------------- C04 近形零命中反例（逐字对账）
    near_digit = t1.replace("三十日内", "45日内", 1)           # 一字之差
    rc_nd, res_nd = bridge_call(config, "anchor.locate", {
        "document_id": "doc-contract", "anchor_id": anchor_a,
        "text": near_digit})
    v_nd = res_nd.get("result", {}).get("verbatim", {})
    rc_b, res_b = bridge_call(config, "anchor.register", {
        "document_id": "doc-memo", "matter_id": "M-SYN-001",
        "quote": QUOTE_B, "text": m0})
    anchor_b = res_b.get("result", {}).get("anchor_id", "")
    rc_c, res_c = bridge_call(config, "anchor.register", {
        "document_id": "doc-memo", "quote": QUOTE_C, "text": m0})
    anchor_c = res_c.get("result", {}).get("anchor_id", "")
    memo_lower = m0.replace(QUOTE_B, QUOTE_B.lower(), 1)      # 大小写折叠
    rc_case, res_case = bridge_call(config, "anchor.locate", {
        "document_id": "doc-memo", "anchor_id": anchor_b,
        "text": memo_lower})
    v_case = res_case.get("result", {}).get("verbatim", {})
    memo_fullwidth = m0.replace("360,000.00", "360，000.00", 1)  # 全半角
    rc_fw, res_fw = bridge_call(config, "anchor.locate", {
        "document_id": "doc-memo", "anchor_id": anchor_c,
        "text": memo_fullwidth})
    v_fw = res_fw.get("result", {}).get("verbatim", {})
    record("C04_near_shape_zero_hit_verbatim_reconciliation",
           rc_nd == 0 and v_nd.get("status") == "NOT_FOUND"
           and v_nd.get("matches") == 0
           and all(k not in v_nd for k in ("span", "shift"))
           and rc_b == 0 and rc_c == 0
           and rc_case == 0 and v_case.get("status") == "NOT_FOUND"
           and rc_fw == 0 and v_fw.get("status") == "NOT_FOUND"
           and all(k not in v_fw for k in ("span", "shift")),
           "近形三反例全部 NOT_FOUND 零位置字段：一字之差（三十→45）／"
           "ASCII 大小写折叠（Party A→party a，大小写不折叠）／全半角"
           "逗号（360,000.00→360，000.00）；偏移换算本可返回陈旧 span，"
           "本面逐字对账不通过即不给位置")

    # ---------------------------------------- C05 F51 正向（定位成功才改）
    rc_q, res_q = bridge_call(config, "anchor.manual_queue", {
        "document_id": "doc-contract"})
    queue_empty = res_q.get("result", {}).get("entries", [])
    rc, res = bridge_call(config, "anchor.gate_edit", {
        "document_id": "doc-contract", "anchor_id": anchor_a, "text": t1,
        "replacement": REPL_A})
    g = res.get("result", {})
    v = g.get("verbatim", {})
    expected_proposed = t1.replace(QUOTE_A, REPL_A, 1)
    rc_v, res_v = bridge_call(config, "anchor.gate_edit", {
        "document_id": "doc-contract", "anchor_id": anchor_a, "text": t1})
    gv = res_v.get("result", {}).get("gate", {})
    record("C05_gate_proceed_only_on_verbatim_located",
           rc == 0 and g.get("gate", {}).get("status") == "PROCEED"
           and g.get("gate", {}).get("auto_edit")
           == "permitted_verbatim_located"
           and g.get("gate", {}).get("proposed_text") == expected_proposed
           and v.get("status") == "LOCATED" and v.get("matches") == 1
           and queue_empty == []
           and rc_v == 0 and gv.get("mode") == "verify_only"
           and gv.get("auto_edit") is None,
           "唯一逐字命中→PROCEED；proposed_text==独立复算（t1.replace）；"
           "人工队列为空；纯核验态（无 replacement）auto_edit=None（引用"
           "呈现闸：NOT_FOUND 禁呈现由状态字段承担）")

    # --------------------------- C06 NOT_FOUND 拒自动修改＋人工入口（幂等/追加）
    rc, res = bridge_call(config, "anchor.gate_edit", {
        "document_id": "doc-contract", "anchor_id": anchor_a,
        "text": near_digit, "replacement": REPL_A2})
    g = res.get("result", {})
    v = g.get("verbatim", {})
    gate = g.get("gate", {})
    entry_id = gate.get("manual_entry_id", "")
    rc_repeat, res_repeat = bridge_call(config, "anchor.gate_edit", {
        "document_id": "doc-contract", "anchor_id": anchor_a,
        "text": near_digit, "replacement": REPL_A2})
    rc_alt, res_alt = bridge_call(config, "anchor.gate_edit", {
        "document_id": "doc-contract", "anchor_id": anchor_a,
        "text": near_digit, "replacement": REPL_A3})
    rc_q, res_q = bridge_call(config, "anchor.manual_queue", {
        "document_id": "doc-contract"})
    entries = res_q.get("result", {}).get("entries", [])
    record("C06_not_found_refused_manual_entry",
           rc == 0 and gate.get("status") == "NOT_FOUND_REFUSED"
           and gate.get("auto_edit") == "refused"
           and "proposed_text" not in gate
           and v.get("status") == "NOT_FOUND" and "span" not in v
           and bool(entry_id)
           and rc_repeat == 0
           and res_repeat.get("result", {}).get("gate", {})
           .get("manual_entry_id") == entry_id
           and rc_alt == 0 and bool(res_alt.get("result", {}).get("gate", {})
                                    .get("manual_entry_id"))
           and len(entries) == 2
           and entries[0]["manual_entry_id"] == entry_id
           and entries[0]["reason"] == "not_found"
           and entries[0]["quote"] == QUOTE_A
           and entries[0]["replacement"] == REPL_A2
           and entries[0]["status"] == "pending",
           f"近形文本→NOT_FOUND_REFUSED：无 proposed_text/span（拒自动"
           f"修改）；人工入口 {entry_id} reason=not_found 携 quote+拟改文；"
           f"同内容重发幂等（同 entry_id 不双登）；异拟改文 append-only "
           f"追加（队列 {len(entries)} 条）")
    metrics["manual_entry_not_found"] = entry_id

    # --------------------------- C07 多命中拒自动修改＋人工入口
    rc, res = bridge_call(config, "anchor.gate_edit", {
        "document_id": "doc-contract", "anchor_id": anchor_a,
        "text": t2, "replacement": REPL_A3})
    g = res.get("result", {})
    gate = g.get("gate", {})
    rc_q, res_q = bridge_call(config, "anchor.manual_queue", {
        "document_id": "doc-contract"})
    entries = res_q.get("result", {}).get("entries", [])
    amb = [e for e in entries if e.get("reason") == "ambiguous"]
    record("C07_ambiguous_refused_manual_entry",
           rc == 0 and g.get("verbatim", {}).get("status") == "AMBIGUOUS"
           and gate.get("status") == "AMBIGUOUS_REFUSED"
           and gate.get("auto_edit") == "refused"
           and "proposed_text" not in gate
           and len(amb) == 1 and amb[0]["quote"] == QUOTE_A
           and len(entries) == 3,
           f"同形多命中→AMBIGUOUS_REFUSED（不猜命中哪一个）；人工入口 "
           f"reason=ambiguous；队列共 {len(entries)} 条 append-only")

    # ---------------------------------------- C08 人工入口闭集字段回读
    closed_fields = {"schema", "manual_entry_id", "anchor_id",
                     "document_id", "matter_id", "reason", "quote",
                     "replacement", "text_sha256", "status", "created_utc"}
    ids = [e.get("manual_entry_id") for e in entries]
    record("C08_manual_queue_closed_fields",
           all(set(e.keys()) <= closed_fields for e in entries)
           and all(e.get("schema") == SCHEMA for e in entries)
           and all(e.get("reason") in ("not_found", "ambiguous")
                   for e in entries)
           and all(e.get("status") == "pending" for e in entries)
           and len(set(ids)) == len(ids),
           f"人工入口 {len(entries)} 条字段全在闭集内；reason 闭集 "
           f"{{not_found,ambiguous}}；status 全 pending（人工处置在宿主/"
           f"人侧，本面不代决）；条目 id 唯一不改写")

    # ---------------------------------------- C09 登记负向＋溯源不变
    rc_miss, res_miss = bridge_call(config, "anchor.register", {
        "document_id": "doc-contract", "quote": "本引文在文本中不存在（合成反例）",
        "text": t0})
    t_dup = t0 + DUP_LINE
    rc_dup, res_dup = bridge_call(config, "anchor.register", {
        "document_id": "doc-contract-dup", "quote": QUOTE_A, "text": t_dup})
    rc_conf, res_conf = bridge_call(config, "anchor.register", {
        "document_id": "doc-contract", "matter_id": "M-SYN-001",
        "quote": QUOTE_A, "text": t1})
    rc_read, res_read = bridge_call(config, "anchor.read", {
        "document_id": "doc-contract", "anchor_id": anchor_a})
    read_rec = res_read.get("result", {})
    record("C09_register_negatives_provenance_immutable",
           rc_miss == 3 and "f50_anchor_not_found" in str(res_miss.get("code"))
           and rc_dup == 3 and "f50_anchor_ambiguous" in str(res_dup.get("code"))
           and rc_conf == 3 and "f50_anchor_reregistration_conflict"
           in str(res_conf.get("code"))
           and rc_read == 0
           and read_rec.get("registered_span") == reg.get("registered_span")
           and read_rec.get("text_sha256") == reg.get("text_sha256"),
           "quote 缺失→f50_anchor_not_found；quote 重复→f50_anchor_ambiguous"
           "（登记即验证）；同键异文本重登记→f50_anchor_reregistration_"
           "conflict（溯源不可改写，重锚走 locate）；anchor.read 溯源事实"
           "全程==登记时值（span/文本 sha 不变）")

    # ---------------------------------------- C10 桥 fail-closed 负向
    rc_nc, res_nc = bridge_call({}, "anchor.locate",
                                {"document_id": "x", "anchor_id": "a-x",
                                 "text": "x"})
    rc_unknown, res_unknown = bridge_call(config, "anchor.explode", {})
    rc_badid, res_badid = bridge_call(config, "anchor.register", {
        "document_id": "../escape", "quote": "x", "text": "x"})
    rc_unreg, res_unreg = bridge_call(config, "anchor.locate", {
        "document_id": "doc-contract", "anchor_id": "a-0000000000000000",
        "text": t0})
    code_shape = __import__("re").compile(r"^[\w:.;-]+$")
    codes = [str(res_nc.get("code")), str(res_unknown.get("code")),
             str(res_badid.get("code")), str(res_unreg.get("code")),
             str(res_miss.get("code")), str(res_conf.get("code"))]
    record("C10_bridge_fail_closed_negatives",
           rc_nc == 3 and "anchor_failed:f50_state_root_not_configured"
           in str(res_nc.get("code"))
           and rc_unknown == 3 and "method_not_connected:anchor.explode"
           in str(res_unknown.get("code"))
           and rc_badid == 3 and "f50_document_id_invalid"
           in str(res_badid.get("code"))
           and rc_unreg == 3 and "f50_anchor_not_registered"
           in str(res_unreg.get("code"))
           and all(code_shape.match(c) for c in codes),
           f"缺状态根 exit{rc_nc}；未知方法 exit{rc_unknown}；坏 id "
           f"exit{rc_badid}；未登记锚 exit{rc_unreg}；错误码纯码不携材料"
           f"内容（quote/文本不出现在任何错误码）")

    # ---------------------------------------- C11 确定性（两根对账＋跨 profile）
    state2 = state.parent / f"juscite-f50f51-state-{profile}-det2"
    state3 = state.parent / f"juscite-f50f51-state-{profile}-det3"
    seq2 = _mini_sequence({"anchor_state_root": str(state2)}, corpus)
    seq3 = _mini_sequence({"anchor_state_root": str(state3)}, corpus)
    dig2 = [canonical_digest(item) for item in seq2]
    dig3 = [canonical_digest(item) for item in seq3]
    cross_key = "mini_sequence_digest"
    cross_val = hashlib.sha256("\n".join(dig2).encode("utf-8")).hexdigest()
    first_run = cross_key not in _CROSS_PROFILE
    cross_ok = _CROSS_PROFILE.setdefault(cross_key, cross_val) == cross_val
    record("C11_determinism_two_roots_cross_profile",
           dig2 == dig3 and all(item.get("rc") == 0 for item in seq2)
           and seq2[0].get("anchor_id") == anchor_a
           and seq2[1].get("anchor_id") == anchor_b
           and cross_ok,
           f"同序列两状态根（剥时间戳）逐响应摘要相等；anchor_id 与主根"
           f"一致（{anchor_a}/{anchor_b}）；跨 profile 同摘要={cross_ok}"
           f"{'（首跑落锚）' if first_run else ''}")

    # ---------------------------------------- C12 语料只读＋AST 纪律
    digest_after = corpus_identity_digest(corpus)
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    allowed = {"__future__", "hashlib", "json", "os", "re", "threading",
               "datetime", "pathlib"}
    banned_calls = {"get_close_matches", "SequenceMatcher", "fuzz"}
    calls = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            name = getattr(fn, "id", None) or getattr(fn, "attr", None)
            if name:
                calls.add(name)
    record("C12_corpus_readonly_ast_discipline",
           digest_after == digest_before
           and imports <= allowed
           and not (imports & {"random", "urllib", "socket", "http",
                               "requests", "difflib"})
           and not (calls & banned_calls),
           f"跑前后语料 sha 相同＝{digest_after == digest_before}；"
           f"document_anchor 导入闭集 {sorted(imports)}⊆确定性白名单；"
           f"无随机/网络/模糊匹配面（不就近匹配＝结构性缺席，非阈值 0）")

    ok = all(c["ok"] for c in checks)
    verdict = "RECON_OK" if ok else "RECON_FAIL"
    result = {
        "obligations": [
            "06:F50 定位一律引用原文重锚定、禁偏移换算：插入后按原文重锚"
            "仍定位正确；零/多命中不以偏移强改",
            "06:F51 引用前逐字核验（NOT FOUND 禁呈现，不就近匹配）：引用"
            "逐字定位成功才改；NOT_FOUND 拒自动修改并给人工入口",
        ],
        "unit": "W2b-U13",
        "profile": profile,
        "started_utc": started,
        "finished_utc": now_iso(),
        "verdict": verdict,
        "counterexamples": {
            "same_shape_multi_hit": "同形 quote 命中 2 处→AMBIGUOUS 零位置"
                                   "字段（偏移换算值可得仍不给）",
            "near_shape_zero_hit": ["一字之差（三十→45）",
                                    "ASCII 大小写折叠（大小写不折叠）",
                                    "全半角逗号（360,000.00→360，000.00）"],
        },
        "corpus": {"root": str(corpus),
                   "identity_digest": digest_before,
                   "readonly_unchanged": digest_after == digest_before,
                   "materials": "全合成（裁决#1）"},
        "state_root": str(state),
        "anchor_ids": {"contract": anchor_a, "memo_b": anchor_b,
                       "memo_c": anchor_c},
        "manual_queue_size": len(entries),
        "checks": checks,
        "metrics": metrics,
    }
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    md = [f"# F50 引用原文重锚定＋F51 引用前逐字核验 recon（{profile}）",
          "",
          f"- verdict: **{verdict}**（{sum(c['ok'] for c in checks)}/"
          f"{len(checks)} checks）",
          f"- unit: W2b-U13 · profile: {profile}",
          "- 反例集：同形多命中（AMBIGUOUS 零位置字段，偏移换算值可得仍"
          "不给）／近形零命中（一字之差、大小写折叠、全半角逗号全部 "
          "NOT_FOUND 零位置字段）",
          f"- 语料: 全合成 · 只读锚 {digest_before[:16]}…",
          f"- state: `{state}`",
          "",
          "| check | 结果 |", "|---|---|"]
    md += [f"| {c['check']} | {'PASS' if c['ok'] else 'FAIL'} |"
           for c in checks]
    for evidence in (evidence_f50, evidence_f51):
        evidence.mkdir(parents=True, exist_ok=True)
        (evidence / "f50_f51_reanchor_verbatim_recon.json").write_text(
            payload + "\n", encoding="utf-8", newline="\n")
        (evidence / "f50_f51_reanchor_verbatim_recon.md").write_text(
            "\n".join(md) + "\n", encoding="utf-8", newline="\n")
    print(f"\n[{profile}] {verdict}  ({sum(c['ok'] for c in checks)}/"
          f"{len(checks)} checks)  证据 → {evidence_f50}（+F51 同跑批）",
          flush=True)
    return 0 if ok else 2


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", action="append",
                    choices=["desktop", "selfhost"], default=None)
    ap.add_argument("--corpus", metavar="DIR", default=None,
                    help="合成语料目录（默认 %%TEMP%%\\juscite-f50f51-corpus）")
    ap.add_argument("--state", metavar="DIR", default=None,
                    help="显式状态根（默认按 profile 分 TEMP 子目录）")
    args = ap.parse_args()
    profiles = args.profile or ["desktop"]
    corpus = Path(args.corpus) if args.corpus else \
        TEMP / "juscite-f50f51-corpus"
    if not ensure_corpus(corpus):
        eprint("[ENV] 合成语料生成失败")
        return 3
    if args.state is not None and len(profiles) > 1:
        eprint("[ENV] 多 profile 共用显式状态根会互相污染，拒绝")
        return 3
    exit_code = 0
    for profile in profiles:
        rc = run_profile(profile, args, corpus)
        exit_code = exit_code or rc
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
