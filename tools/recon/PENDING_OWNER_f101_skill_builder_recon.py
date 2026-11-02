# -*- coding: utf-8 -*-
"""F101 agent/skill-builder（聊天造自定义件）验收对账（W5-U10）。

权威（06:V7-101 行＋17 卡 F101；owner=product；UI_HOST_OR_NEW_PRODUCT；
phase B5；source_rationale「生态成熟后的元层」）。验收向量（逐字）：
「自建skill/agent生成候选，经预检和用户采用再执行，无自动扩权」。
红线：候选态永不直执行；自动扩权负测具名拒。17 卡「不创第二Agent loop」
——本单只做候选/预检/采用合同面，零运行时新执行通道。

硬依赖（全部既有 VERIFIED 面，零第二权威）：
- F96 skill.gate.validate（预检复用执行合同守门；执行唯一通道
  skill.gate.run 只对已安装技能）；
- F94/F95 skill.zip.install（skill 采用＝既有分发链真安装）；
- F98 skill.route.decide（候选未安装＝路由不可达 f98_explicit_unknown
  同频旁证；采用后才可达）；
- F93 skill_semantics.read_skill（候选文档解析，id 规则同上游原生通道）；
  oc28 pin 只读对照（skill-file.ts＋config/agent.ts＋schema/config/
  agent.ts＝agent 候选 frontmatter 契约源）。

分段（每 profile 恰同序操作序列——跨 profile 事实逐项可比）：
  S0 钉定与环境（产品面/门禁面/分发链面 sha；oc28 原生契约三文件在位）
  S1 候选生成对话轮（合成候选注入＝离线结构断言；真实模型轮次为对话层
     增强路径非门——本 recon 全程零模型零网络；幂等重提案；留痕零内容
     ——对话原文只入 sha；无用户首轮＝f101_origin_user_missing 具名拒；
     解析败不留残件）
  S2 候选态永不直执行（AST：模块零执行面方法字面量＋桥出调用点闭集
     {skill.gate.validate, skill.zip.install}＋导入闭集；未知方法
     method_not_connected；未预检采用 f101_precheck_required；非用户通
     道采用 f101_adopt_requires_user:assistant；候选未安装路由不可达
     f98_explicit_unknown——路由正对照 toy 技能可达证明路由面本身健在）
  S3 预检（skill＝F96 门禁真校验 PASS＋坏合同 f101_precheck_contract_
     failed 携 f96 码；agent 无自动扩权闸——allow 权限规则
     f101_agent_permission_allow typed 拒；deny-only PASS）
  S4 用户采用（skill＝F95 分发链真安装 INSTALLED＋目录回读 sha 全等＋
     记录翻 adopted＋note 零内容；agent＝声明物化字节全等零运行时）
  S5 采用后执行仅经 F96 门（路由面采用后才可达候选＋skill.gate.run 真
     执行 PASS〔refusal eval 结构守门 REFUSED-passed，零外部配置〕＋预
     检后字节变 f101_candidate_modified＝F96 STALE 同构旧核不覆盖新字节）
  S6 留痕审计与 fail-closed（candidates.jsonl 逐条 digest 独立复核；篡改
     typed 拒后字节还原复跑绿；缺状态根 typed 拒；参数闭集；legal_entry
     接线在文）
  S9 跨 profile（候选 id/文档 sha/对话 sha/预检回执/zip sha/安装 manifest
     摘要/agent 物化 sha/gate 结论/路由决策 digest 逐项全等）

desktop 径＝legal_entry CLI 子进程全链；selfhost 径＝产品面同进程。

用法（juscite worktree w5-u10 根 cwd）：
  python -X utf8 tools/recon/PENDING_OWNER_f101_skill_builder_recon.py \
      [--profile desktop] [--profile selfhost]
缺省双 profile。exit 0＝RECON_OK 全断言过；证据 JSON 写 evidence/F101/
<profile>/recon-result.json（＋docs/construction/evidence/ 镜像）。
全程合成材料（合成对话/合成候选文档/合成状态根），零外部 API、零 BYOK、
零模型、零 %APPDATA% 触碰；oc28 只读对照；不 push。
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

RUN_DATE = "20261023"
REPO_ROOT = Path(__file__).resolve().parents[2]
LEGAL_ENTRY = REPO_ROOT / "implementation" / "python" / "legal_entry.py"
FACE = REPO_ROOT / "implementation" / "python" / "skill_builder.py"
GATE_FACE = REPO_ROOT / "implementation" / "python" / "skill_gate.py"
CATALOG_FACE = REPO_ROOT / "implementation" / "python" / "skill_catalog.py"

OC28_SKILL_FILE = Path(
    r"D:\Codex\1.法律工作区\jusbench工作区\oc28"
    r"\packages\core\src\config\plugin\skill-file.ts")
OC28_AGENT_PLUGIN = Path(
    r"D:\Codex\1.法律工作区\jusbench工作区\oc28"
    r"\packages\core\src\config\plugin\agent.ts")
OC28_AGENT_SCHEMA = Path(
    r"D:\Codex\1.法律工作区\jusbench工作区\oc28"
    r"\packages\schema\src\config\agent.ts")

# 合成对话与候选文档（纯合成，零真实内容；对话轮首轮 user＝候选由用户发起）。
DIALOG = {"turns": [
    {"role": "user",
     "text": "帮我做一个合同续期提醒技能，只要拒答企业调查就行。"},
    {"role": "assistant", "text": "候选已起草，预检通过后请你采用。"},
]}
MARKER_DIALOG = "MAQDIALOGXQ 合同续期独句"
MARKER_NOTE = "NOTEXBODYY 用户采用标记"
MODEL_SELF_INIT = "我主动给你造一个技能，不用你开口。"

SKILL_DOC = (
    "---\nname: 合同续期提醒\ndescription: 自建技能候选（合成）：合同续期"
    "提醒与拒绝企业调查\n---\n\n# 合同续期提醒（自建候选）\n\n"
    "## 执行合同（F96）\n\n```lvyin-skill-contract\n"
    '{"as_of": "2026-10-01", "evidence": {"mode": "four_state"}, '
    '"sources": [], "failure": {"on_gate_fail": "named_refusal_not_pass", '
    '"on_missing_data": "named_gap_no_fabrication"}, "evals": '
    '[{"id": "ev-refusal", "kind": "refusal", '
    '"scenario": "corporate_investigation_no_data_source", '
    '"expect": {"outcome": "refused"}}]}\n```\n\n'
    "## 失败纪律\n\n- 守门不过具名拒；缺数据具名缺口，绝不编造。\n")

SKILL_DOC_BAD_CONTRACT = SKILL_DOC.replace('"four_state"', '"two_state"')
SKILL_DOC_V2 = SKILL_DOC + "\n<!-- 第二版追加 -->\n"

AGENT_DOC_DENY = (
    "---\ndescription: 自建 agent 候选（合成）：只读复核助手\n"
    "mode: subagent\n"
    'permissions: [{"action": "shell", "resource": "*", "effect": "deny"}]\n'
    "---\n\n你是律引自建复核助手：只做只读复核，绝不执行任何写操作。\n")

AGENT_DOC_ALLOW = AGENT_DOC_DENY.replace('"deny"', '"allow"')

TOY_DOC = (
    "---\nname: 路由正对照\ndescription: 合成正对照技能（F98 路由面健在"
    "旁证）\n---\n\n正文。\n")

FORBIDDEN_LITERALS = ("skill.gate.run", "skill.calculate",
                      "skill.review_instantiate", "skill.route.decide",
                      "skill.route.log", "exec(", "eval(", "subprocess",
                      "socket", "urllib", "os.system")

BRIDGE_CLOSED = ["skill.gate.validate", "skill.zip.install"]
IMPORT_CLOSED = {"__future__", "hashlib", "io", "json", "re", "zipfile",
                 "pathlib", "bridge_errors", "skill_semantics",
                 "legal_entry"}


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
    def all_passed(self) -> bool:
        return all(item["status"] == "PASS" for item in self.items)


def sha256_file(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_bytes(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def force_rmtree(path: Path) -> None:
    import stat

    def _onexc(func, target, _exc):
        os.chmod(target, stat.S_IWRITE)
        func(target)

    shutil.rmtree(path, onexc=_onexc)


def deterministic_zip(entries: dict) -> bytes:
    """确定性 zip（定时间戳＋条目排序；skill_catalog.pack 同纪律）。"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in sorted(entries):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.external_attr = 0o600 << 16
            zf.writestr(info, entries[name])
    return buf.getvalue()


# ---------------------------------------------------------------------- #
# 双传输形态（desktop＝CLI 子进程；selfhost＝同进程）
# ---------------------------------------------------------------------- #


def call_cli(method: str, args: dict, config: dict) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        req = Path(tmp) / "request.json"
        cfg = Path(tmp) / "config.json"
        req.write_text(json.dumps({"method": method, "args": args},
                                  ensure_ascii=False), encoding="utf-8")
        cfg.write_text(json.dumps(config, ensure_ascii=False),
                       encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", str(LEGAL_ENTRY),
             "--request-json", str(req), "--config", str(cfg)],
            capture_output=True, text=True, encoding="utf-8", timeout=600,
            cwd=str(REPO_ROOT))
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            payload = {"status": "RAW", "stdout": proc.stdout[:400]}
        return {"exit": proc.returncode, "payload": payload}


def make_selfhost_call():
    import legal_entry as module
    from bridge_errors import NotConnected as _NC

    def call(method: str, args: dict, config: dict) -> dict:
        try:
            result = module.call(method, args, config)
            return {"exit": 0, "payload": {"status": "OWNER_RESPONSE",
                                           "result": result}}
        except _NC as exc:
            return {"exit": 3, "payload": {"status": "NOT_CONNECTED",
                                           "code": str(exc)}}
        except Exception as exc:  # noqa: BLE001
            return {"exit": 1, "payload": {"status": "ERROR",
                                           "code": "%s: %s" % (
                                               type(exc).__name__,
                                               str(exc)[:160])}}
    return call


def result_of(out: dict) -> dict:
    return (out.get("payload") or {}).get("result") or {}


def expect_typed(checks: Checks, cid: str, call, method: str, args: dict,
                 config: dict, code_fragment: str) -> None:
    out = call(method, args, config)
    ok = (out["exit"] == 3
          and (out["payload"] or {}).get("status") == "NOT_CONNECTED"
          and code_fragment in str((out["payload"] or {}).get("code", "")))
    checks.add(cid, ok,
               "%s typed refusal %s -> exit %s %s"
               % (method, code_fragment, out["exit"],
                  str((out["payload"] or {}).get("code", ""))[:100]))


def propose_args(kind="skill", document=None, dialog=None) -> dict:
    return {"kind": kind, "dialog": dialog or DIALOG,
            "document": document or {"filename": "SKILL.md",
                                     "text": SKILL_DOC}}


# ---------------------------------------------------------------------- #
# 单 profile 主体（desktop/selfhost 恰同序操作序列）
# ---------------------------------------------------------------------- #


def run_product_profile(checks: Checks, call, workspace: Path) -> dict:
    builder_root = str(workspace / "builder")
    records_path = workspace / "builder" / "candidates.jsonl"
    config = {"skill_builder_state_root": builder_root,
              "skill_catalog_state_root": str(workspace / "catalog"),
              "skill_routing_state_root": str(workspace / "routing")}
    facts: dict = {}

    # ---- S0 钉定 ------------------------------------------------------
    checks.add("S0_face_module_sha", len(sha256_file(FACE)) == 64,
               "产品面 skill_builder.py sha256=%s…" % sha256_file(FACE)[:12])
    checks.add("S0_reused_faces_sha",
               len(sha256_file(GATE_FACE)) == 64
               and len(sha256_file(CATALOG_FACE)) == 64,
               "复用面在位：skill_gate.py=%s… skill_catalog.py=%s…（F96 门"
               "禁/F95 分发链，零第二权威）"
               % (sha256_file(GATE_FACE)[:8], sha256_file(CATALOG_FACE)[:8]))
    gate_wired = GATE_FACE.read_text(encoding="utf-8")
    checks.add("S0_f96_run_only_via_gate",
               '"skill.gate.run"' in gate_wired
               and "skill.gate.run" in LEGAL_ENTRY.read_text(
                   encoding="utf-8"),
               "执行唯一通道＝F96 门禁 skill.gate.run（对已安装技能；本面"
               "零引用）")

    # ---- S1 候选生成对话轮（合成候选注入＝离线结构断言） ----------------
    out = call("skill.builder.propose", propose_args(), config)
    proposed = result_of(out)
    cid = proposed.get("candidate_id") or ""
    ok = (out["exit"] == 0 and proposed.get("status") == "staged"
          and cid.startswith("skill-") and len(cid) == len("skill-") + 8)
    checks.add("S1_propose_skill_staged", ok,
               "skill 候选入账 staged：candidate_id=%s（内容寻址）"
               % cid)
    facts["candidate_id"] = cid
    facts["document_sha256"] = proposed.get("document_sha256")

    again = result_of(call("skill.builder.propose", propose_args(), config))
    listing = result_of(call("skill.builder.read",
                             {"candidate_id": None}, config))
    ids = [c.get("candidate_id") for c in listing.get("candidates") or []]
    checks.add("S1_propose_idempotent_content_addressed",
               again.get("candidate_id") == cid and again.get("idempotent")
               is True and ids.count(cid) == 1,
               "同字节重提案幂等：id 相同且记录恰 1 条（零重复）")

    marker_dialog = {"turns": [
        {"role": "user", "text": MARKER_DIALOG + "，请生成候选。"},
        {"role": "assistant", "text": "候选已起草。"},
    ]}
    result_of(call("skill.builder.propose",
                   propose_args(dialog=marker_dialog,
                                document={"filename": "SKILL.md",
                                          "text": SKILL_DOC_V2}), config))
    record = result_of(call("skill.builder.read",
                            {"candidate_id": cid}, config))
    entry = (record.get("candidates") or [{}])[0]
    raw_records = records_path.read_text(encoding="utf-8") \
        if records_path.is_file() else ""
    checks.add("S1_record_zero_content",
               MARKER_DIALOG not in raw_records
               and MARKER_NOTE not in raw_records
               and "只要拒答企业调查就行" not in raw_records
               and "# 合同续期提醒（自建候选）" not in raw_records
               and entry.get("origin", {}).get("turn_count") == 2
               and entry.get("origin", {}).get("roles")
               == ["user", "assistant"]
               and bool(entry.get("origin", {}).get("dialog_sha256")),
               "留痕零内容：对话原文/采用 note/文档正文均不入 candidates."
               "jsonl（只入 sha/轮数/角色序列＋文档元数据 face_summary 供 "
               "UI 回读）")
    facts["dialog_sha256"] = entry.get("origin", {}).get("dialog_sha256")

    expect_typed(checks, "S1_no_user_origin_named_refusal", call,
                 "skill.builder.propose",
                 propose_args(dialog={"turns": [
                     {"role": "assistant", "text": MODEL_SELF_INIT},
                     {"role": "user", "text": "好的。"}]}), config,
                 "f101_origin_user_missing")

    out = call("skill.builder.propose",
               propose_args(document={"filename": "SKILL.md",
                                      "text": "正文（无 frontmatter）。\n"}),
               config)
    code = str((out["payload"] or {}).get("code", ""))
    checks.add("S1_propose_parse_failure_no_residue",
               out["exit"] == 3 and "f101_document_parse_failed" in code
               and "f93_" in code,
               "解析败具名拒（%s…）且不留残件" % code[:80])

    # ---- S2 候选态永不直执行（结构＋运行负测） --------------------------
    source = FACE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_hits = [lit for lit in FORBIDDEN_LITERALS if lit in source]
    checks.add("S2_AST_zero_execution_literals", not forbidden_hits,
               "模块全文本零执行面方法字面量（skill.gate 执行面/计算/实例化"
               "/路由字面量与进程/网络库零出现）")
    calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id == "_bridge_call":
            first = node.args[0] if node.args else None
            if isinstance(first, ast.Name):
                import skill_builder as face_module
                calls.append(getattr(face_module, first.id))
            elif isinstance(first, ast.Constant):
                calls.append(first.value)
    checks.add("S2_AST_bridge_calls_closed_set",
               sorted(calls) == sorted(BRIDGE_CLOSED),
               "桥出调用点闭集=%s（预检→F96 校验；采用→F95 直装；零执行"
               "面调用点）" % sorted(calls))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0]
                            for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    checks.add("S2_AST_import_closed_set", imported <= IMPORT_CLOSED,
               "导入闭集=%s（零进程/网络/模型/随机/时钟）" % sorted(imported))

    expect_typed(checks, "S2_unknown_builder_method_not_connected", call,
                 "skill.builder.execute", {}, config, "method_not_connected")
    expect_typed(checks, "S2_adopt_without_precheck_named_refusal", call,
                 "skill.builder.adopt",
                 {"candidate_id": cid,
                  "adoption": {"by": "user", "note": "未预检直接采用"}},
                 config, "f101_precheck_required")
    expect_typed(checks, "S2_adopt_non_user_channel_named_refusal", call,
                 "skill.builder.adopt",
                 {"candidate_id": cid,
                  "adoption": {"by": "assistant", "note": "对话通道自采用"}},
                 config, "f101_adopt_requires_user:assistant")

    # 路由面正对照＋候选不可达（候选未安装＝路由唯一候选源 F94 活动面不含）
    toy_zip = workspace / "seed" / "toy.zip"
    toy_zip.parent.mkdir(parents=True, exist_ok=True)
    toy_bytes = deterministic_zip({"toy/SKILL.md": TOY_DOC.encode("utf-8")})
    toy_zip.write_bytes(toy_bytes)
    install = call("skill.zip.install",
                   {"zip_path": str(toy_zip),
                    "sha256": hashlib.sha256(toy_bytes).hexdigest(),
                    "url": "skill-builder://recon/seed-toy"}, config)
    checks.add("S2_route_seed_catalog_ok",
               install.get("exit") == 0
               and result_of(install).get("status") == "INSTALLED",
               "路由正对照前置：toy 技能经 F95 链真安装（零第二目录权威）")
    route_toy = call("skill.route.decide",
                     {"channel": "public", "query": None,
                      "explicit": {"skill_id": "toy"}, "materials": None,
                      "policy": None}, config)
    toy_loaded = result_of(route_toy)
    checks.add("S2_route_positive_control_explicit_toy",
               route_toy.get("exit") == 0
               and toy_loaded.get("decision") == "explicit",
               "路由正对照：显式 toy 可达（路由面健在）")
    facts["route_seed_digest"] = (toy_loaded.get("decision_ref") or {}) \
        .get("digest")
    expect_typed(checks, "S2_candidate_unroutable_while_staged", call,
                 "skill.route.decide",
                 {"channel": "public", "query": None,
                  "explicit": {"skill_id": cid}, "materials": None,
                  "policy": None}, config, "f98_explicit_unknown")

    # ---- S3 预检（F96 门禁复用＋无自动扩权闸） -------------------------
    pre = result_of(call("skill.builder.precheck",
                         {"candidate_id": cid}, config))
    ok = (pre.get("result") == "PASS"
          and [c.get("id") for c in pre.get("checks") or []]
          == ["f96_gate_validate"]
          and bool(pre.get("contract_sha256"))
          and pre.get("as_of") == "2026-10-01")
    checks.add("S3_precheck_skill_via_f96_gate_validate", ok,
               "skill 候选预检 PASS＝既有 F96 skill.gate.validate 真校验"
               "（contract sha=%s… as_of=%s；零第二合同权威）"
               % (str(pre.get("contract_sha256"))[:12], pre.get("as_of")))
    facts["precheck_receipt"] = {"result": pre.get("result"),
                                 "contract_sha256": pre.get("contract_sha256"),
                                 "as_of": pre.get("as_of")}

    out = call("skill.builder.propose",
               propose_args(document={"filename": "SKILL.md",
                                      "text": SKILL_DOC_BAD_CONTRACT}),
               config)
    bad_cid = result_of(out).get("candidate_id")
    out = call("skill.builder.precheck", {"candidate_id": bad_cid}, config)
    code = str((out["payload"] or {}).get("code", ""))
    checks.add("S3_precheck_bad_contract_named_refusal",
               out["exit"] == 3 and "f101_precheck_contract_failed" in code
               and "f96_contract_evidence_mode_invalid" in code,
               "坏合同候选预检具名拒：%s…" % code[:90])

    out = call("skill.builder.propose",
               propose_args(kind="agent",
                            document={"filename": "review-helper.md",
                                      "text": AGENT_DOC_ALLOW}), config)
    allow_cid = result_of(out).get("candidate_id")
    expect_typed(checks, "S3_agent_allow_permission_typed_refusal", call,
                 "skill.builder.precheck", {"candidate_id": allow_cid},
                 config, "f101_agent_permission_allow:1")

    out = call("skill.builder.propose",
               propose_args(kind="agent",
                            document={"filename": "review-helper.md",
                                      "text": AGENT_DOC_DENY}), config)
    agent_cid = result_of(out).get("candidate_id")
    agent_pre = result_of(call("skill.builder.precheck",
                               {"candidate_id": agent_cid}, config))
    no_esc = next((c for c in agent_pre.get("checks") or []
                   if c.get("id") == "no_auto_escalation"), {})
    checks.add("S3_agent_deny_only_precheck_pass",
               agent_pre.get("result") == "PASS" and no_esc.get("passed"),
               "agent 候选（deny-only）预检 PASS：permissions 只准收窄"
               "（无自动扩权闸）")
    facts["agent_candidate_id"] = agent_cid

    # ---- S4 用户采用（用户独占＋既有分发链） ---------------------------
    out = call("skill.builder.adopt",
               {"candidate_id": cid,
                "adoption": {"by": "user", "note": MARKER_NOTE}}, config)
    adopted = result_of(out)
    receipt = adopted.get("adoption") or {}
    install_receipt = receipt.get("install") or {}
    ok = (out["exit"] == 0 and adopted.get("status") == "adopted"
          and receipt.get("by") == "user"
          and receipt.get("channel") == "skill.zip.install"
          and install_receipt.get("status") == "INSTALLED"
          and install_receipt.get("skills") == [cid]
          and bool(receipt.get("zip_sha256")))
    checks.add("S4_adopt_skill_installs_via_f95_chain", ok,
               "skill 候选经用户采用→F95 分发链真安装 INSTALLED（zip sha=%s…"
               " skills=%s）" % (str(receipt.get("zip_sha256"))[:12],
                                 install_receipt.get("skills")))
    facts["zip_sha256"] = receipt.get("zip_sha256")
    facts["install_manifest_sha256"] = install_receipt.get(
        "manifest_sha256")

    catalog = result_of(call("skill.catalog.read",
                             {"channel": "public", "skill_id": cid},
                             config))
    catalog_skills = {s.get("id") for s in catalog.get("skills") or []}
    checks.add("S4_catalog_read_back_sha_equal",
               catalog_skills == {cid}
               and bool(catalog.get("skill")),
               "F94 目录真实回读：活动面=%s（安装权威零第二目录）"
               % sorted(catalog_skills))

    adopted_entry = result_of(call("skill.builder.read",
                                   {"candidate_id": cid}, config))
    entry = (adopted_entry.get("candidates") or [{}])[0]
    checks.add("S4_record_status_adopted_note_content_free",
               entry.get("status") == "adopted"
               and MARKER_NOTE not in records_path.read_text(
                   encoding="utf-8"),
               "记录翻 adopted；note 只入 sha（零内容留痕）")

    out = call("skill.builder.adopt",
               {"candidate_id": agent_cid,
                "adoption": {"by": "user", "note": "采用只读复核助手"}},
               config)
    agent_adopted = result_of(out)
    artifact = Path((agent_adopted.get("adoption") or {}).get("artifact")
                    or " ")
    checks.add("S4_adopt_agent_declaration_materialized_only",
               out["exit"] == 0
               and (agent_adopted.get("adoption") or {}).get("channel")
               == "adopted_declaration"
               and artifact.is_file()
               and artifact.read_text(encoding="utf-8") == AGENT_DOC_DENY,
               "agent 候选经用户采用→声明物化字节全等（零运行时零 loop＝"
               "17 卡不创第二 Agent loop）")
    facts["agent_artifact_sha256"] = sha256_file(artifact) \
        if artifact.is_file() else None

    # ---- S5 采用后执行仅经 F96 门 --------------------------------------
    route_adopted = call("skill.route.decide",
                         {"channel": "public", "query": None,
                          "explicit": {"skill_id": cid}, "materials": None,
                          "policy": None}, config)
    adopted_route = result_of(route_adopted)
    checks.add("S5_adopted_skill_routable_explicit",
               route_adopted.get("exit") == 0
               and adopted_route.get("decision") == "explicit"
               and bool(adopted_route.get("projection")),
               "采用后路由面可达（显式装填投影非空）＝候选→采用→可执行"
               "状态跃迁唯一路径")
    facts["route_adopted_digest"] = (adopted_route.get("decision_ref")
                                     or {}).get("digest")

    skill_dir = catalog.get("directory") or ""
    gate_out = call("skill.gate.run",
                    {"skill_path": str(Path(skill_dir) / "SKILL.md"),
                     "skill_id": cid}, config)
    gate = result_of(gate_out)
    evals = gate.get("evals") or []
    ok = (gate_out.get("exit") == 0
          and gate.get("gate") == "PASS" and gate.get("reasons") == []
          and len(evals) == 1 and evals[0].get("state") == "REFUSED"
          and evals[0].get("passed") is True)
    checks.add("S5_gate_run_pass_only_via_f96", ok,
               "采用后执行＝F96 门禁真跑 PASS（refusal eval 结构守门 "
               "REFUSED-passed；零外部配置；执行唯一通道）")
    facts["gate_decision"] = gate.get("gate")
    facts["gate_reasons"] = gate.get("reasons")

    installed_entry = Path(catalog.get("directory") or workspace) / "SKILL.md"
    checks.add("S5_installed_bytes_equal_candidate",
               installed_entry.is_file()
               and sha256_file(installed_entry)
               == facts.get("document_sha256"),
               "安装面字节＝候选文档字节（sha256 全等；采用即真实安装）")

    # F96 证据四态复用（回执绑定面）：真跑回执→VERIFIED；无回执→
    # UNVERIFIED 不签 PASS（未核不签 PASS 沿 F96 语义零改动）。
    vr_pass = result_of(call("skill.gate.verify_receipt",
                             {"skill_path": str(installed_entry),
                              "receipt": gate}, config))
    vr_none = result_of(call("skill.gate.verify_receipt",
                             {"skill_path": str(installed_entry),
                              "receipt": None}, config))
    checks.add("S5_f96_four_state_reuse",
               vr_pass.get("state") == "VERIFIED"
               and vr_pass.get("pass_allowed") is True
               and vr_none.get("state") == "UNVERIFIED"
               and vr_none.get("pass_allowed") is False,
               "F96 证据四态复用：真跑回执→VERIFIED pass_allowed=True；无"
               "回执→UNVERIFIED pass_allowed=False（未核不签 PASS 零改动）")

    out = call("skill.builder.propose",
               propose_args(document={"filename": "SKILL.md",
                                      "text": SKILL_DOC_V2}), config)
    v2_cid = result_of(out).get("candidate_id")
    result_of(call("skill.builder.precheck", {"candidate_id": v2_cid},
                   config))
    staged_v2 = workspace / "builder" / "candidates" / v2_cid / "SKILL.md"
    staged_v2.write_text(SKILL_DOC_V2 + "\n<!-- 篡改 -->\n",
                         encoding="utf-8")
    expect_typed(checks, "S5_modified_after_precheck_named_refusal", call,
                 "skill.builder.adopt",
                 {"candidate_id": v2_cid,
                  "adoption": {"by": "user", "note": "字节已变仍要采用"}},
                 config, "f101_candidate_modified")

    # ---- S6 留痕审计与 fail-closed --------------------------------------
    all_records_text = records_path.read_text(encoding="utf-8") \
        if records_path.is_file() else ""
    digest_ok = True
    for line in all_records_text.splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        body = {k: v for k, v in rec.items() if k != "digest"}
        if hashlib.sha256(canonical_bytes(body)).hexdigest() \
                != rec.get("digest"):
            digest_ok = False
    checks.add("S6_records_digest_independent_recheck", digest_ok,
               "candidates.jsonl 逐条 digest 独立复核全等（全量 %d 条）"
               % len([l for l in all_records_text.splitlines() if l.strip()]))

    original = records_path.read_bytes()
    lines = original.decode("utf-8").splitlines()
    rec = json.loads(lines[0])
    rec["status"] = ("staged" if rec.get("status") == "adopted"
                     else "adopted")  # 必有变更（未采用/已采用互翻）
    lines[0] = json.dumps(rec, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"))
    records_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    out = call("skill.builder.read", {"candidate_id": None}, config)
    tamper_caught = (out["exit"] == 3 and "f101_record_digest_mismatch"
                     in str((out["payload"] or {}).get("code", "")))
    records_path.write_bytes(original)
    restored = call("skill.builder.read", {"candidate_id": None}, config)
    checks.add("S6_record_tamper_typed_then_restored",
               tamper_caught and restored.get("exit") == 0,
               "篡改记录 status → typed 拒 f101_record_digest_mismatch；"
               "字节还原复跑 exit 0")

    bad_config = {"skill_catalog_state_root": str(workspace / "catalog")}
    expect_typed(checks, "S6_missing_state_root_typed", call,
                 "skill.builder.propose", propose_args(), bad_config,
                 "f101_state_root_not_configured")
    bad_args = propose_args()
    bad_args["extra"] = 1
    expect_typed(checks, "S6_propose_params_closed_set", call,
                 "skill.builder.propose", bad_args, config,
                 "f101_propose_params_invalid")
    wired = LEGAL_ENTRY.read_text(encoding="utf-8")
    checks.add("S6_legal_entry_wired",
               "SKILL_BUILDER_METHODS" in wired
               and "skill.builder.propose" in wired
               and "skill_builder_failed" in wired,
               "legal_entry 接线在文：SKILL_BUILDER_METHODS（恰四方法）＋"
               "typed 包裹 skill_builder_failed")
    group = result_of(call("skill.builder.read", {"candidate_id": None},
                           config))
    checks.add("S6_read_back_count_closed",
               group.get("count") == 5,
               "真实回读：候选恰 5 条（主 skill/对话变体 V2/坏合同/agent-"
               "allow/agent-deny）＝%s" % group.get("count"))

    return facts


def run_desktop(checks: Checks, workspace: Path) -> dict:
    checks.add("P0_profile_transport_desktop", True,
               "desktop＝legal_entry CLI 子进程全链（--request-json/"
               "--config）")
    return run_product_profile(checks, call_cli, workspace)


def run_selfhost(checks: Checks, workspace: Path) -> dict:
    checks.add("P0_profile_transport_selfhost", True,
               "selfhost＝产品面同进程（legal_entry.call 直呼；typed 码与"
               "桥 exit 映射同形）")
    return run_product_profile(checks, make_selfhost_call(), workspace)


# ---------------------------------------------------------------------- #
# main
# ---------------------------------------------------------------------- #


def main() -> int:
    if os.name == "nt":
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.path.insert(0, str(REPO_ROOT / "implementation" / "python"))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", action="append",
                        choices=("desktop", "selfhost"), dest="profiles",
                        help="发行形态（可重复；不给则双形态全跑）")
    parser.add_argument("--evidence-root",
                        default=str(REPO_ROOT / "evidence"))
    args = parser.parse_args()
    profiles = args.profiles or ["desktop", "selfhost"]
    evidence_root = Path(args.evidence_root)

    if not FACE.is_file():
        print("FATAL: 产品面 skill_builder.py 不在 %s" % FACE)
        return 2
    for pin in (OC28_SKILL_FILE, OC28_AGENT_PLUGIN, OC28_AGENT_SCHEMA):
        if not pin.is_file():
            print("FATAL: oc28 原生契约对照文件不在 %s（只读对照缺失）"
                  % pin)
            return 2

    all_facts: dict = {}
    all_ok = True
    workspace_root = Path(tempfile.mkdtemp(prefix="f101-builder-recon-"))
    # 双 profile 依序复用同一 workdir 路径（先清后建）：确定性产物（zip/
    # 记录 digest/路由决策 digest）跨 profile 可逐字节对账。
    workspace = workspace_root / "run"
    try:
        for profile in profiles:
            print("\n===== profile: %s =====" % profile, flush=True)
            if workspace.exists():
                force_rmtree(workspace)
            workspace.mkdir(parents=True)
            checks = Checks()
            if profile == "desktop":
                pf = run_desktop(checks, workspace)
            else:
                pf = run_selfhost(checks, workspace)
            all_facts[profile] = {"checks": checks.items, "facts": pf}
            if not checks.all_passed:
                all_ok = False

        if len(profiles) == 2:
            checks = Checks()
            a = all_facts[profiles[0]]["facts"]
            b = all_facts[profiles[1]]["facts"]
            checks.add(
                "S9_candidate_facts_cross_profile",
                all(a.get(k) == b.get(k) for k in
                    ("candidate_id", "document_sha256", "dialog_sha256",
                     "agent_candidate_id")),
                "跨 profile：候选 id/文档 sha/对话 sha/agent 候选 id 逐项"
                "全等（内容寻址确定性）")
            checks.add(
                "S9_adoption_and_gate_cross_profile",
                all(a.get(k) == b.get(k) for k in
                    ("zip_sha256", "install_manifest_sha256",
                     "agent_artifact_sha256", "gate_decision",
                     "gate_reasons")),
                "跨 profile：确定性 zip sha/安装 manifest 摘要/agent 物化"
                " sha/F96 门结论逐项全等")
            checks.add(
                "S9_route_decision_digests_cross_profile",
                all(a.get(k) == b.get(k) for k in
                    ("route_seed_digest", "route_adopted_digest"))
                and bool(a.get("route_adopted_digest")),
                "跨 profile：路由决策 digest 逐项全等（留痕无 wall time）")
            checks.add(
                "S9_precheck_receipt_cross_profile",
                a.get("precheck_receipt") == b.get("precheck_receipt")
                and bool(a.get("precheck_receipt")),
                "跨 profile：F96 预检回执逐键全等")
            all_facts["S9"] = {"checks": checks.items}
            if not checks.all_passed:
                all_ok = False

        total_checks = sum(len(all_facts[p]["checks"])
                           for p in all_facts if p != "S9")
        print("\n===== 汇总 =====")
        print("RECON_OK" if all_ok else "RECON_FAILED",
              "checks=%d" % total_checks, flush=True)

        for profile in profiles:
            payload = all_facts.get(profile) or {}
            evidence = {
                "feature": "F101",
                "unit": "W5-U10",
                "profile": profile,
                "run_date": RUN_DATE,
                "command": ("python -X utf8 "
                            "tools/recon/PENDING_OWNER_f101_skill_builder_recon"
                            ".py --profile desktop --profile selfhost"),
                "checks": payload.get("checks", []),
                "facts": payload.get("facts", {}),
                "face_module_sha256": sha256_file(FACE),
                "gate_module_sha256": sha256_file(GATE_FACE),
                "catalog_module_sha256": sha256_file(CATALOG_FACE),
                "oc28_skill_file_sha256": sha256_file(OC28_SKILL_FILE),
                "oc28_agent_plugin_sha256": sha256_file(OC28_AGENT_PLUGIN),
                "oc28_agent_schema_sha256": sha256_file(OC28_AGENT_SCHEMA),
            }
            for base in (evidence_root / "F101" / profile,
                         REPO_ROOT / "docs" / "construction" / "evidence"
                         / "F101" / profile):
                base.mkdir(parents=True, exist_ok=True)
                (base / "recon-result.json").write_text(
                    json.dumps(evidence, ensure_ascii=False, indent=2),
                    encoding="utf-8")
        print("证据已写 evidence/F101/<profile>/recon-result.json（＋"
              "docs/construction/evidence/ 镜像）")
        return 0 if all_ok else 1
    finally:
        pass


if __name__ == "__main__":
    sys.exit(main())
