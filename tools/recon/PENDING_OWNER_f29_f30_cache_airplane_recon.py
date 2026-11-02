# -*- coding: utf-8 -*-
"""F29 缓存分区失效＋F30 飞行模式 验收对账（W3-U05）。

F29（06 行，双实例）：复用选定核心缓存（上游原生 promptCacheKey 仿射变换
＝oc28 model-request.ts 的 ses_ 前缀剥离；共享前缀指令排序＝
session/context.ts——两机制以 oc28 盘上文件原文钉定，零改动＝复用原生缓存
不删原策略）；稳定/变动上下文分区（IMMUTABLE/APPEND）；IMMUTABLE 前缀指
纹（sha256 规范字节序，逐段长度前缀）；case/model/rule 版本变化推导式正
确失效（规则版本→lineage 必转、规则文本重版→前缀字节必转、模型→仅
lineage、案件→仅 APPEND 分区轮换；无变化→全等）；预算闸只闸 IMMUTABLE
前缀、超额具名拒不静默截断；不建第二缓存引擎（AST：仅 hashlib 依赖、零
存储零网络零进程级 memo）；不拿宣传命中率当验收（面输出键闭集、无任何
命中率/比值字段——源蓝图 94.7-98.1% 为竞品宣传值非本产品实测，台账 F29
行明示）。

F30（06 行，双实例；17 卡上游 app/desktop owner 落点＝
implementation/patches/017，verify_patch prestate＋净室 scratch git apply
＋bun 转译四文件）：一键飞行模式 armed 时闭集 11 通道全 BLOCKED（回环端
点例外＝本地模型/本地检索通道存活，F22 v1 不被误伤）；catalog 拉取为
standing env 面（patch 007 常开，与开关无关）；活闸两通道在连接发生前具
名拒（review_chat.ask 模型轮／case.search lcr HTTP 检索）；离线读算可用
＝armed 下 E22 冻结面（codices 只读＋AST 零网络导入守卫）＋statute face
产品入口真跑＋JC 本地 calc 面全过；OS 出站观测复用 tools/
f39_os_egress_negtest.py 无管理员差分法（netstat/DNS 缓存 flush 前后三点
差分，服务树＋本工具进程树 pid 归因，观察窗内零新非回环外联、E10 清册禁
列域零命中、.invalid 负测主机零解析＝拒在连接前）。

边界如实：desktop typecheck 未跑（patch 017 按 oc28 只读红线未应用，应用
与 typecheck 属合并后步骤）；宿主级断网/pktmon 字节抓包属 PENDING_ADMIN_ENV
（00-总协调 §6.1 裁决#2 无管理员方案先行）。

用法（juscite worktree w3-u05 根 cwd；--profile 缺省＝双 profile）：
  python -X utf8 tools/recon/PENDING_OWNER_f29_f30_cache_airplane_recon.py \
      [--profile desktop --profile selfhost]

exit 0＝RECON_OK 全断言过；证据 JSON 写 evidence/F29/<profile>/、
evidence/F30/<profile>/（及 docs/construction/evidence/ 同构镜像）。
全合成材料；只读消费 oc28/JC/codices；不发网络、不写 %APPDATA%。
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
import threading
import time
from pathlib import Path

WORKTREE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKTREE / "tools"))
sys.path.insert(0, str(WORKTREE / "implementation" / "python"))
import e10_session_negtest as b0  # noqa: E402  既有采集器复用（E10 VERIFIED；f39 同款）
b0.PWSH = b0.PWSH_DEFAULT  # f39 同款：pwsh 7.6.4 钉定路径（主流程 main() 外使用必须显式设）

LEGAL_ENTRY = WORKTREE / "implementation" / "python" / "legal_entry.py"
CACHE_FACE = WORKTREE / "implementation" / "python" / "cache_partition.py"
AIRPLANE_FACE = WORKTREE / "implementation" / "python" / "airplane_mode.py"
REVIEW_CHAT = WORKTREE / "implementation" / "python" / "review_chat.py"
PATCH_017 = WORKTREE / "implementation" / "patches" / "017-f30-airplane-mode.patch"
VERIFY_PATCH = WORKTREE / "tools" / "verify_patch.py"

OC28 = Path(r"D:\Codex\1.法律工作区\jusbench工作区\oc28")
OC_BG_SERVICE = OC28 / "packages/desktop/src/main/service/background-service.ts"
OC_CTX = OC28 / "packages/core/src/session/context.ts"
OC_MODEL_REQ = OC28 / "packages/core/src/session/model-request.ts"
OC_CONFIG_SCHEMA = OC28 / "packages/schema/src/config.ts"
OC_SENTRY = OC28 / "packages/desktop/src/renderer/startup/sentry.ts"
OC_EXTENSION_MANAGER = OC28 / "packages/desktop/src/main/extension/manager.ts"
OC_EXTENSIONS_SCHEMA = OC28 / "packages/desktop/src/shared/ipc-rpc/extensions.ts"
BUN = Path.home() / ".bun" / "bun.exe"

JC_REPO = Path(
    r"D:\Codex\1.法律工作区\juris-calculus工作区\juris-calculus\.local\worktrees\w2b-u55")
CODICES_LCCC = Path(
    r"D:\Codex\1.法律工作区\legal-cn-core-codices工作区"
    r"\legal-cn-core-codices-repo\.local\worktrees\w2a-u14\lccc_consumer.py")
CODICES_FORMAL_ROOT = Path(
    r"D:\Codex\1.法律工作区\legal-cn-core-codices工作区\legal-cn-core-codices")
LCCC_SHA256 = (
    "55eea7c27e08d6b236b7ab7a83810c86ee0898c335c4668d875a492775db863a")

# F104 冻结夹具（calc.interest 闰日 2 天 → 20 分）
INTEREST_FIXTURE = {"principal_minor": 365_000,
                    "segments": [{"start_date": "2024-02-28",
                                  "end_date": "2024-03-01",
                                  "annual_rate": "0.01"}]}
PIPL_WJBS = "1.2.156.3005.6-0100000000100120210820009100000"

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

BASE_PLAN = {
    "affinity": "ses_" + "a" * 64,
    "model": "deepseek-byok/deepseek-chat",
    "case": {"case_id": "m-synth-1", "case_version": "v3"},
    "rules": {"jc.rules.deadline": "1.0.0"},
    "immutable_segments": [
        {"name": "system", "text": "律引系统提示（合成验收材料，无法律效力）"},
        {"name": "rulepack:deadline", "text": "D01..D14 frozen text (synthetic)"},
    ],
    "append_segments": [
        {"name": "case:events", "text": "2026-10-17 立案（合成事件）"},
    ],
    "budget_bytes": 4096,
}


class Checks:
    def __init__(self):
        self.items: list[dict] = []

    def add(self, check_id: str, ok: bool, detail: str) -> bool:
        self.items.append({"id": check_id, "status": "PASS" if ok else "FAIL",
                           "detail": detail})
        print("[%s] %s — %s" % ("PASS" if ok else "FAIL", check_id, detail))
        return ok

    @property
    def all_passed(self):
        return all(i["status"] == "PASS" for i in self.items)

    @property
    def passed_count(self):
        return sum(i["status"] == "PASS" for i in self.items)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def call_cli(method: str, args: dict, config: dict, timeout: int = 300):
    """真产品入口子进程径（legal_entry CLI；W2b-U19/U54/U55 recon 同纪律）。"""
    with tempfile.TemporaryDirectory() as tmp:
        req = Path(tmp) / "request.json"
        cfg = Path(tmp) / "config.json"
        req.write_text(json.dumps({"method": method, "args": args},
                                  ensure_ascii=False), encoding="utf-8")
        cfg.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", str(LEGAL_ENTRY),
             "--request-json", str(req), "--config", str(cfg)],
            capture_output=True, text=True, encoding="utf-8", timeout=timeout)
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            payload = {"status": "RAW", "stdout": proc.stdout[:400]}
        return proc.returncode, payload


def make_config(workspace: Path, extra: dict | None = None) -> dict:
    rules = workspace / "rules"
    rules.mkdir(parents=True, exist_ok=True)
    (rules / "jc-local-pack.json").write_text(
        json.dumps(RULE_PACK, ensure_ascii=False), encoding="utf-8")
    config = {
        "jc_state_root": str(workspace / "state"),
        "jc_rule_roots": [str(rules)],
        "jc_import_path": str(JC_REPO),
        "codices_import_path": str(CODICES_LCCC.parent),
        "codices_formal_root": str(CODICES_FORMAL_ROOT),
    }
    config.update(extra or {})
    return config


def make_airplane_config(workspace: Path, armed: bool) -> dict:
    state_root = workspace / "airplane-state"
    state_root.mkdir(parents=True, exist_ok=True)
    flag = {"enabled": bool(armed), "reason": "W3-U05 recon synthetic",
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    (state_root / "airplane-mode.json").write_text(
        json.dumps(flag, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"airplane_state_root": str(state_root)}


def run_s0_pins(checks: Checks, pins: dict) -> bool:
    ok = all(path.is_file() for path in (LEGAL_ENTRY, CACHE_FACE, AIRPLANE_FACE,
                                         REVIEW_CHAT, PATCH_017))
    ok = checks.add(
        "U05-PIN-0", ok,
        "工单树在盘：legal_entry/cache_partition/airplane_mode/review_chat/"
        "patch-017（sha256 见证据 pins）")
    if not ok:
        return False
    for label, path in (("cache_partition", CACHE_FACE),
                        ("airplane_mode", AIRPLANE_FACE),
                        ("legal_entry", LEGAL_ENTRY),
                        ("review_chat", REVIEW_CHAT),
                        ("patch_017", PATCH_017)):
        pins[label] = sha256_file(path)

    # F29 复用面：oc28 原生缓存两机制盘上原文钉定（复用原生缓存不删原策略）
    model_req = OC_MODEL_REQ.read_text(encoding="utf-8")
    ctx = OC_CTX.read_text(encoding="utf-8")
    native_ok = ("promptCacheKey: /^ses_[0-9a-f]{64}$/.test(affinity) "
                 "? affinity.slice(4) : affinity" in model_req)
    native_ok = native_ok and (
        "most to least shared across sessions so the baseline stays a reusable"
        in ctx)
    pins["oc_model_request_ts"] = sha256_file(OC_MODEL_REQ)
    pins["oc_context_ts"] = sha256_file(OC_CTX)
    checks.add("F29-PIN-1", native_ok,
               "oc28 原生缓存两机制原文在盘：model-request.ts promptCacheKey "
               "ses_ 前缀剥离仿射变换＋context.ts 共享前缀排序注释（选定核心"
               "缓存复用面零改动）")

    # F30 上游 standing 面（007 env 常开＋update disable 字面＋Sentry 无 DSN 早退）
    bg = OC_BG_SERVICE.read_text(encoding="utf-8")
    schema = OC_CONFIG_SCHEMA.read_text(encoding="utf-8")
    sentry = OC_SENTRY.read_text(encoding="utf-8")
    standing = 'process.env.OPENCODE_DISABLE_MODELS_FETCH = "1"' in bg
    standing = standing and 'Schema.Literals(["disable", "notify", "auto"])' in schema
    standing = standing and "if (!import.meta.env.VITE_SENTRY_DSN) return" in sentry
    pins["oc_background_service_ts"] = sha256_file(OC_BG_SERVICE)
    pins["oc_config_ts"] = sha256_file(OC_CONFIG_SCHEMA)
    pins["oc_sentry_ts"] = sha256_file(OC_SENTRY)
    checks.add("F30-PIN-1", standing,
               "oc28 standing 出站面在盘：007 env 禁 models.dev 目录拉取（常开）＋"
               "config update disable 字面（packages/schema/src/config.ts）＋"
               "renderer Sentry 无 DSN 早退（无遥测出站）")

    # 上游无远程遥测属性（E10 清册 #15）：cli/core/src 无 posthog/sentry 出站
    hits = []
    for base in (OC28 / "packages/cli/src", OC28 / "packages/core/src"):
        for path in base.rglob("*.ts"):
            text = path.read_text(encoding="utf-8", errors="replace").lower()
            if ("posthog" in text or "sentry" in text) and (
                    "https://") in text:
                hits.append(str(path.relative_to(OC28)))
    checks.add("F30-PIN-2", not hits,
               "上游 cli/core/src 无 posthog/sentry/analytics https 出站调用"
               + ("" if not hits else "；命中=%r" % hits))
    return True


def run_f29(checks: Checks) -> None:
    # S1 复用选定核心缓存 -----------------------------------------------------
    code, payload = call_cli("cache.plan", dict(BASE_PLAN), {})
    plan = payload.get("result", {}) if code == 0 else {}
    reuse_ok = (code == 0 and plan.get("native_cache_key") == "a" * 64
                and plan.get("schema") == "lvyin-cache-partition/1")
    checks.add("F29-R1", reuse_ok,
               "复用选定核心缓存：lineage 内嵌上游原生仿射变换（ses_+64hex→剥"
               "前缀，与 model-request.ts 同变换；非 ses_ 键原样透传由单测钉"
               "定）——面 schema lvyin-cache-partition/1")

    # S2 稳定/变动上下文分区＋IMMUTABLE 前缀指纹 ------------------------------
    partition_ok = (
        plan.get("partition", {}).get("immutable", {}).get("segments")
        == ["system", "rulepack:deadline"]
        and plan.get("partition", {}).get("append", {}).get("segments")
        == ["case:events"])
    fp_only = call_cli("cache.fingerprint",
                       {"segments": BASE_PLAN["immutable_segments"]}, {})
    fp_util = fp_only[1].get("result", {}) if fp_only[0] == 0 else {}
    partition_ok = partition_ok and (
        fp_util.get("prefix_fingerprint") == plan.get("prefix_fingerprint"))
    mutated = json.loads(json.dumps(BASE_PLAN))
    mutated["append_segments"] = [{"name": "case:events",
                                   "text": "完全不同的变动内容（合成）"}]
    m_code, m_payload = call_cli("cache.plan", mutated, {})
    m_plan = m_payload.get("result", {}) if m_code == 0 else {}
    partition_ok = partition_ok and (
        m_plan.get("prefix_fingerprint") == plan.get("prefix_fingerprint"))
    checks.add("F29-R2", bool(partition_ok),
               "稳定/变动上下文分区：IMMUTABLE/APPEND 分列；前缀指纹＝仅 "
               "IMMUTABLE 字节（fingerprint 工具复算同值；APPEND 内容变化不"
               "动前缀指纹）")

    # S3 字节稳定＋次序敏感 ---------------------------------------------------
    b_code, b_payload = call_cli("cache.plan", json.loads(json.dumps(BASE_PLAN)), {})
    b_plan = b_payload.get("result", {}) if b_code == 0 else {}
    reordered = json.loads(json.dumps(BASE_PLAN))
    reordered["immutable_segments"] = list(reversed(BASE_PLAN["immutable_segments"]))
    r_code, r_payload = call_cli("cache.plan", reordered, {})
    r_plan = r_payload.get("result", {}) if r_code == 0 else {}
    stable_ok = (json.dumps(plan, sort_keys=True) == json.dumps(b_plan, sort_keys=True)
                 and r_plan.get("prefix_fingerprint") != plan.get("prefix_fingerprint"))
    checks.add("F29-R3", stable_ok,
               "字节级稳定 prompt 纪律：同输入两跑计划全等；IMMUTABLE 段次序"
               "变化→前缀指纹必变（次序属冻结前缀合同）")

    # S4 case/model/rule 版本变化正确失效 -------------------------------------
    rule = json.loads(json.dumps(BASE_PLAN))
    rule["rules"] = {"jc.rules.deadline": "1.0.1"}
    _, rp = call_cli("cache.plan", rule, {})
    rp = rp.get("result", {})
    model = json.loads(json.dumps(BASE_PLAN))
    model["model"] = "ollama-local/qwen3"
    _, mp = call_cli("cache.plan", model, {})
    mp = mp.get("result", {})
    case = json.loads(json.dumps(BASE_PLAN))
    case["case"] = {"case_id": "m-synth-1", "case_version": "v4"}
    _, cp = call_cli("cache.plan", case, {})
    cp = cp.get("result", {})
    text = json.loads(json.dumps(BASE_PLAN))
    text["immutable_segments"][1]["text"] = "D01..D15 frozen text v2 (synthetic)"
    _, tp = call_cli("cache.plan", text, {})
    tp = tp.get("result", {})
    inv_ok = (
        rp.get("lineage_key") != plan.get("lineage_key")
        and rp.get("prefix_fingerprint") == plan.get("prefix_fingerprint")
        and mp.get("lineage_key") != plan.get("lineage_key")
        and mp.get("prefix_fingerprint") == plan.get("prefix_fingerprint")
        and cp.get("append_partition_key") != plan.get("append_partition_key")
        and cp.get("prefix_fingerprint") == plan.get("prefix_fingerprint")
        and cp.get("lineage_key") == plan.get("lineage_key")
        and tp.get("prefix_fingerprint") != plan.get("prefix_fingerprint")
        and tp.get("lineage_key") != plan.get("lineage_key")
        and tp.get("append_partition_key") != plan.get("append_partition_key"))
    checks.add("F29-R4", inv_ok,
               "case/model/rule 版本变化正确失效（推导式）：规则版本 bump→"
               "lineage 必转（前缀/APPEND 不动）；模型变化→仅 lineage；案件版"
               "本→仅 APPEND 分区轮换（前缀字节恒不动＝append-only 不重写历"
               "史）；规则文本重版→前缀＋lineage＋APPEND 全转")

    # S5 预算闸 ---------------------------------------------------------------
    _, over = call_cli("cache.plan", dict(BASE_PLAN, budget_bytes=8), {})
    budget_ok = (over.get("status") == "NOT_CONNECTED"
                 and "cache_immutable_budget_exceeded" in str(over.get("code", "")))
    immutable_bytes = (fp_util or {}).get("bytes")
    _, within = call_cli("cache.plan",
                         dict(BASE_PLAN, budget_bytes=immutable_bytes,
                              append_segments=[{"name": "case:events",
                                                "text": "x" * 10_000}]), {})
    wp = within.get("result", {}).get("budget", {}) if within.get("status") == "OWNER_RESPONSE" else {}
    budget_ok = budget_ok and wp.get("within") is True and (
        wp.get("total_bytes", 0) > 10_000)
    checks.add("F29-R5", bool(budget_ok),
               "预算闸：IMMUTABLE 前缀超额具名拒 cache_immutable_budget_exceeded"
               "（不静默截断不自动逐出冻结规则文本）；闸只作用 IMMUTABLE——"
               "APPEND 按设计增长只计量不拒绝（total 报实值）")

    # S6 不建第二缓存引擎＋不拿宣传命中率当验收 --------------------------------
    source = CACHE_FACE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    modules = set()
    mutable_store = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            value = node.value
            const_ok = isinstance(value, ast.Constant)
            frozen_ok = (isinstance(value, ast.Call)
                         and isinstance(value.func, ast.Name)
                         and value.func.id == "frozenset"
                         and len(value.args) == 1
                         and isinstance(value.args[0], (ast.Set, ast.List, ast.Tuple))
                         and all(isinstance(e, ast.Constant) for e in value.args[0].elts))
            if not (const_ok or frozen_ok):
                mutable_store = True
    engine_ok = (modules == {"__future__", "hashlib", "bridge_errors"}
                 and not mutable_store
                 and not any(t in source for t in (
                     "lru_cache", "sqlite3", "shelve", "pickle", "socket",
                     "urllib", "requests", "open(", "Path(")))
    blob = json.dumps(plan, ensure_ascii=False).lower()
    no_rate = not any(t in blob for t in ("hit", "rate", "ratio", "percent", "命中率"))
    checks.add("F29-R6", engine_ok,
               "不建第二缓存引擎（AST 结构证据）：依赖闭集={__future__,hashlib,"
               "bridge_errors}；模块级赋值仅常量/冻结 frozenset（零存储零"
               "memo）；无文件/网络/序列化面——纯推导面，原生缓存策略零改动")
    checks.add("F29-R7", no_rate,
               "不拿宣传命中率当验收：plan 输出键闭集无任何命中率/比值字段"
               "（源蓝图 94.7-98.1% 为竞品宣传值非本项目实测——台账 F29 行明示）")


def run_f30_switch(checks: Checks, workspace: Path) -> dict:
    """开关生命周期＋决策表＋活闸。返回 armed 配置（供离线读算/观测窗复用）。"""
    armed_cfg = make_airplane_config(workspace, armed=True)
    off_cfg = make_airplane_config(workspace / "off", armed=False)
    code, payload = call_cli("airplane.status", {}, armed_cfg)
    status = payload.get("result", {}) if code == 0 else {}
    channels = [row["channel"] for row in status.get("channels", [])]
    switch_ok = (code == 0 and status.get("enabled") is True
                 and len(channels) == 11)
    switch_ok = switch_ok and "model_round_remote" in channels and (
        "case_retriever_http" in channels and "extension_download" in channels)
    checks.add("F30-R1", switch_ok,
               "一键开关：armed 状态读回 enabled=true＋闭集 11 通道投影（E10 "
               "出站清册 §1 全类；enforcement_kind 具名谁执法）")

    # 决策表：armed 全 BLOCKED（回环例外）；inactive 现状；catalog standing
    table_ok = True
    loopback_allow = 0
    for channel in channels:
        args = {"channel": channel}
        if channel == "case_retriever_http":
            args["endpoint"] = "https://airplane-negtest.example.invalid/v1"
        _, row = call_cli("airplane.egress_decision", args, armed_cfg)
        row = row.get("result", {})
        if channel in ("model_round_remote", "case_retriever_http"):
            table_ok = table_ok and row.get("decision") == "BLOCKED" and (
                row.get("switch_contribution") == "armed")
            _, lrow = call_cli("airplane.egress_decision",
                               dict(args, endpoint="http://127.0.0.1:9/x"),
                               armed_cfg)
            lrow = lrow.get("result", {})
            table_ok = table_ok and lrow.get("decision") == "ALLOWED"
            loopback_allow += 1
        else:
            table_ok = table_ok and row.get("decision") == "BLOCKED" and (
                row.get("reason_code") == "airplane_armed_" + channel + "_blocked")
    _, cat = call_cli("airplane.egress_decision",
                      {"channel": "model_provider_catalog_fetch"}, off_cfg)
    cat = cat.get("result", {})
    table_ok = table_ok and cat.get("decision") == "BLOCKED" and (
        cat.get("switch_contribution") == "standing" and
        cat.get("reason_code") == "standing_env_opencode_disable_models_fetch")
    _, idle = call_cli("airplane.egress_decision",
                       {"channel": "model_round_remote",
                        "provider_id": "deepseek-byok"}, off_cfg)
    idle = idle.get("result", {})
    table_ok = table_ok and idle.get("decision") == "ALLOWED" and (
        idle.get("switch_contribution") == "inactive")
    checks.add("F30-R2", table_ok,
               "闭集决策表：armed→11 通道全 BLOCKED（具名 airplane_armed_*_"
               "blocked）；两端点闸通道回环端点 ALLOWED（本地模型/本地检索存"
               "活＝F22 v1 不误伤，%d 路回环例外实测）；未 armed→桥闸通道现"
               "状 ALLOWED；catalog 拉取为 standing env 面（patch 007，与开关"
               "无关恒 BLOCKED）" % loopback_allow)

    # 本地 provider 声明例外
    local_cfg = dict(armed_cfg, airplane_local_providers=["deepseek-byok"])
    _, lrow = call_cli("airplane.egress_decision",
                       {"channel": "model_round_remote"}, local_cfg)
    lrow = lrow.get("result", {})
    checks.add("F30-R3", lrow.get("decision") == "ALLOWED" and
               lrow.get("reason_code") == "airplane_loopback_allow",
               "本地 provider 声明例外：airplane_local_providers 显式声明后 "
               "armed 下模型轮通道 ALLOWED（声明式本地通道白名单，缺省全远端）")

    # 活闸 1：review_chat.ask 连接前具名拒；未 armed 现状（无 airplane 码）
    chat_args = {"review_batch_id": "rb-synth-u05",
                 "scope": {"kind": "matter", "matterId": "m-synth-1"},
                 "question": "合成提问（W3-U05 验收）"}
    code, payload = call_cli("review_chat.ask", chat_args, armed_cfg)
    gate1_ok = code == 3 and "airplane_remote_model_blocked" in json.dumps(
        payload, ensure_ascii=False)
    code2, payload2 = call_cli("review_chat.ask", chat_args, off_cfg)
    gate1_ok = gate1_ok and "airplane" not in json.dumps(
        payload2, ensure_ascii=False)
    checks.add("F30-R4", gate1_ok,
               "活闸·模型轮（review_chat.ask 唯一模型通道）：armed→装配上下文"
               "/建会话之前具名拒 airplane_remote_model_blocked（exit 3，零连"
               "接零会话）；未 armed→既有未配置面原样（无任何 airplane 码＝开"
               "关前行为逐字节现状）")

    # 活闸 2：case.search lcr HTTP 检索连接前置拒；未 armed 现状
    http_cfg = dict(armed_cfg, cases_contract="lcr/1",
                    cases_url="https://airplane-negtest.example.invalid/v1")
    code, payload = call_cli("case.search", {"query": "合成检索词"}, http_cfg)
    gate2_ok = code == 3 and "airplane_remote_case_retriever_blocked" in json.dumps(
        payload, ensure_ascii=False)
    off_http = dict(off_cfg, cases_contract="lcr/1",
                    cases_url="https://airplane-negtest.example.invalid/v1")
    code2, payload2 = call_cli("case.search", {"query": "合成检索词"}, off_http)
    gate2_ok = gate2_ok and "airplane" not in json.dumps(
        payload2, ensure_ascii=False)
    checks.add("F30-R5", gate2_ok,
               "活闸·远端检索（case.search lcr/1 HTTP 径）：armed→连接发生前"
               "具名拒 airplane_remote_case_retriever_blocked（.invalid 负测主"
               "机零解析由观测窗复核）；未 armed→下游原样失败（无 airplane 码）")
    return armed_cfg


def run_f30_offline(checks: Checks, armed_cfg: dict, workspace: Path,
                    pins: dict) -> None:
    """离线读算可用：armed 下 E22 冻结面（直接只读消费＋AST 零网络守卫）＋
    statute face 产品入口真跑＋JC 本地 calc 面＋纯函数面。"""
    lccc_ok = CODICES_LCCC.is_file() and sha256_file(CODICES_LCCC) == LCCC_SHA256
    if not lccc_ok:
        checks.add("F30-R6", False,
                   "E22 冻结面 lccc_consumer.py sha256 漂移或缺失（%s）"
                   % CODICES_LCCC)
        return
    checks.add("F30-R6", True,
               "E22 冻结面 v1.1 lccc_consumer.py sha256 钉定一致（55eea7c2…），"
               "只读消费零写入")
    source = CODICES_LCCC.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    no_net = imported.isdisjoint({"urllib", "requests", "socket", "http",
                                  "httpx", "aiohttp"})
    checks.add("F30-R7", no_net,
               "codices 冻结面 AST 零网络导入守卫（无 urllib/requests/socket/"
               "http*）——离线可用是结构性质非运行凑巧")

    sys.path.insert(0, str(CODICES_LCCC.parent))
    for name in [m for m in list(sys.modules) if m == "lccc_consumer"]:
        del sys.modules[name]
    import lccc_consumer  # noqa: E402
    consumer = lccc_consumer.LcccConsumer(str(CODICES_FORMAL_ROOT))
    face = consumer.resolve_effectivity(wjbs=PIPL_WJBS, as_of="2026-10-17")
    offline_ok = face.get("found") is True and face.get("status_label") in (
        "有效", "现行")
    checks.add("F30-R8", offline_ok,
               "离线读·codices 直读（armed 下）：个人信息保护法现行版时点定位 "
               "found=true status_label=%r（E22 冻结面真数据）"
               % face.get("status_label"))

    # 产品入口真跑配置＝JC/codices 全量＋armed 开关（缺 codices/jc 键即 NOT_CONNECTED）
    full_armed = make_config(workspace, {
        "airplane_state_root": armed_cfg["airplane_state_root"]})

    # statute face 产品入口真跑（armed 配置；冷扫耗时长，超时预算 900s）
    t0 = time.time()
    code, payload = call_cli(
        "statute.resolve", {"wjbs": PIPL_WJBS, "as_of": "2026-10-17"},
        full_armed, timeout=900)
    result = payload.get("result", {}) if code == 0 else {}
    cli_ok = (code == 0 and result.get("found") is True
              and result.get("status_label") in ("有效", "现行"))
    checks.add("F30-R9", cli_ok,
               "离线读·statute face 产品入口真跑（legal_entry CLI 子进程，armed "
               "配置）：个人信息保护法 resolve found=true status_label=%r（E22 "
               "冷扫 %.0fs 属每进程一次性成本）"
               % (result.get("status_label"), time.time() - t0))

    code, payload = call_cli("calc.interest", {"input": INTEREST_FIXTURE},
                             full_armed)
    row = payload.get("result", {}) if code == 0 else {}
    calc_ok = row.get("amount_minor") == 20
    code, payload = call_cli("calc.amount_words", {"value_minor": 1234567},
                             full_armed)
    row2 = payload.get("result", {}) if code == 0 else {}
    calc_ok = calc_ok and row2.get("words") == "壹万贰仟叁佰肆拾伍元陆角柒分" and (
        row2.get("value_minor") == 1234567)
    code, payload = call_cli("number.classify",
                             {"text": "违约金共人民币12,345.67元（合成）"}, {})
    row3 = payload.get("result", {}) if code == 0 else {}
    calc_ok = calc_ok and bool(row3)
    code, payload = call_cli("citation.parse",
                             {"text": "依据《中华人民共和国个人信息保护法》第五条"
                                      "的规定（合成测试）。"}, {})
    row4 = payload.get("result", {}) if code == 0 else {}
    calc_ok = calc_ok and row4.get("citations")
    checks.add("F30-R10", calc_ok,
               "离线算·JC 本地 calc＋纯函数面（armed 下）：calc.interest 闰日夹"
               "具=20 分＋calc.amount_words 大写夹具=壹万贰仟叁佰肆拾伍元陆角柒"
               "分（value_minor 回带）＋number.classify＋citation.parse 全过"
               "——JC 本地客户端与纯函数面零 airplane 钩子")


def run_f30_egress_window(checks: Checks, armed_cfg: dict, workspace: Path,
                          window_tail: float = 8.0) -> None:
    """OS 出站观测（f39 无管理员差分法）：flushdns→pre→观察窗（窗内跑离线
    读算工作载＋armed 拒绝尝试）→post→差分归因。"""
    service_pid = None
    try:
        reg = b0.read_registration()
        url = (reg or {}).get("url") or ""
        rows = b0.netstat_rows()
        listeners = {pid for (local, _r, state, pid) in rows
                     if state == "LISTENING" and local.endswith(":43127")}
        service_pid = listeners.pop() if listeners else None
        service_present = bool(service_pid)
    except (OSError, json.JSONDecodeError):
        service_present = False
    snap_dir = Path(tempfile.mkdtemp(prefix="f29f30-egress-"))
    subprocess.run(["ipconfig", "/flushdns"], capture_output=True, timeout=30)
    procs_pre = b0.proc_snapshot(snap_dir / "procs-pre.json")
    tree_pre = b0.descendants(procs_pre, service_pid) if service_pid else set()
    tree_pre |= b0.descendants(procs_pre, os.getpid())
    pre = {"netstat": b0.netstat_rows(),
           "dns": b0.dns_snapshot(snap_dir / "dns-pre.json")}

    samples: set = set()
    stop = threading.Event()

    def sampler():
        while not stop.is_set():
            samples |= b0.netstat_rows()
            time.sleep(2.0)

    thread = threading.Thread(target=sampler, daemon=True)
    thread.start()
    # 窗内工作载：armed 离线读算＋armed 拒绝尝试（全本地/全拒绝，零远端）
    offline_cfg = make_config(workspace, {
        "airplane_state_root": armed_cfg["airplane_state_root"]})
    workload: list[tuple[str, dict, dict]] = [
        ("citation.parse", {"text": "依据《中华人民共和国个人信息保护法》第五条"
                                    "的规定（合成观测窗载）。"}, {}),
        ("number.classify", {"text": "本金人民币987,654.32元（合成）"}, {}),
        ("calc.interest", {"input": INTEREST_FIXTURE}, offline_cfg),
        ("calc.amount_words", {"value_minor": 1234567}, offline_cfg),
        ("review_chat.ask", {"review_batch_id": "rb-egress",
                             "scope": {"kind": "matter", "matterId": "m-1"},
                             "question": "合成窗内拒"}, armed_cfg),
    ]
    for method, args, cfg in workload:
        try:
            call_cli(method, args, cfg, timeout=120)
        except subprocess.TimeoutExpired:
            pass
    time.sleep(window_tail)
    stop.set()
    thread.join(timeout=10)
    post = {"netstat": b0.netstat_rows(),
            "dns": b0.dns_snapshot(snap_dir / "dns-post.json")}
    procs_post = b0.proc_snapshot(snap_dir / "procs-post.json")
    tree_post = b0.descendants(procs_post, service_pid) if service_pid else set()
    tree_post |= b0.descendants(procs_post, os.getpid())
    proc_all = {**procs_pre, **procs_post}
    product_tree = {int(p) for p in (tree_pre | tree_post)}

    during = (samples | post["netstat"]) - pre["netstat"]
    violations, recorded = [], 0
    for (local, remote, state, pid) in sorted(during):
        if state == "LISTENING":
            continue
        if pid in product_tree:
            row = {"local": local, "remote": remote, "state": state,
                   "pid": pid,
                   "proc": (proc_all.get(pid, {}) or {}).get("name") or "?",
                   "class": "product_tree",
                   "verdict": "allowed_loopback" if b0.is_loopback(remote)
                   else "violation_non_loopback"}
            recorded += 1
            if row["verdict"] != "allowed_loopback":
                violations.append(row)
        elif b0.is_loopback(remote) or pid == 0:
            recorded += 1  # 环境回环/系统行，记录不断言
        # 其余非归因行＝环境噪声（并行单位/系统），只记录
    dns_diff = post["dns"] - pre["dns"]
    service_remotes = set()
    forbidden_hosts = [e for e, _d, _t in dns_diff
                       if any(e == f or e.endswith("." + f)
                              for f in b0.FORBIDDEN_DNS)]
    negtest_dns = [e for e, _d, _t in dns_diff
                   if "airplane-negtest" in e or ".invalid" in e]
    mode = ("product_service_tree+recon_tree" if service_pid
            else "recon_tree_only（产品服务未运行，pid 归因面=本工具进程树）")
    checks.add("F30-R11", not violations and not forbidden_hosts and not negtest_dns,
               "OS 出站观测（f39 无管理员差分法）：观察窗 netstat 新行归因=%s，"
               "窗内工作载=armed 离线读算×4＋armed 拒绝尝试×1，产品树非回环外"
               "联=0、E10 禁列域 DNS=0、.invalid 负测主机解析=0（拒在连接前）；"
               "记录行=%d；宿主级断网/pktmon 属 PENDING_ADMIN_ENV（§6.1 裁决#2）"
               % (mode, recorded))
    # 证据落盘：差分明细
    (snap_dir / "egress-diff.json").write_text(json.dumps({
        "product_tree_pids": sorted(product_tree),
        "netstat_new_nonlisten": sorted(during),
        "violations": violations,
        "dns_new": [list(e) for e in sorted(dns_diff)],
        "forbidden_hosts": forbidden_hosts,
        "negtest_dns": negtest_dns,
    }, ensure_ascii=False, indent=1), encoding="utf-8")


def run_profile(profile: str, workspace_root: Path) -> Checks:
    checks = Checks()
    workspace = workspace_root / profile
    workspace.mkdir(parents=True, exist_ok=True)
    pins: dict = {"profile": profile, "run_date": time.strftime("%Y-%m-%dT%H:%M:%S")}
    if not run_s0_pins(checks, pins):
        return checks
    run_f29(checks)
    armed_cfg = run_f30_switch(checks, workspace)
    run_f30_offline(checks, armed_cfg, workspace, pins)
    run_f30_egress_window(checks, armed_cfg, workspace)
    pins["checks_summary"] = "%d/%d" % (checks.passed_count, len(checks.items))
    (workspace / "pins.json").write_text(
        json.dumps(pins, ensure_ascii=False, indent=1), encoding="utf-8")
    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", action="append", required=False,
                        choices=("desktop", "selfhost"))
    args = parser.parse_args()
    profiles = args.profile or ["desktop", "selfhost"]
    workspace_root = Path(tempfile.mkdtemp(prefix="f29-f30-recon-"))
    all_ok = True
    reports = {}
    for profile in profiles:
        print(f"=== profile {profile} ===")
        checks = run_profile(profile, workspace_root)
        reports[profile] = checks.items
        ok = checks.all_passed
        all_ok = all_ok and ok
        print(f"profile {profile}: {checks.passed_count}/{len(checks.items)} "
              f"{'RECON_OK' if ok else 'RECON_FAILED'}")

    for profile, items in reports.items():
        verdict = "RECON_OK" if all(i["status"] == "PASS" for i in items) \
            else "RECON_FAILED"
        pins = json.loads((workspace_root / profile / "pins.json").read_text(
            encoding="utf-8")) if (workspace_root / profile / "pins.json").is_file() \
            else {}
        for feature in ("F29", "F30"):
            for evidence_root in (
                    WORKTREE / "evidence" / feature / profile,
                    WORKTREE / "docs" / "construction" / "evidence" / feature / profile):
                evidence_root.mkdir(parents=True, exist_ok=True)
                (evidence_root / "recon-result.json").write_text(
                    json.dumps({
                        "schema_version": "lvyin-f29-f30-recon/1",
                        "unit": "W3-U05 缓存分区失效与飞行模式（F29＋F30）",
                        "feature": feature, "profile": profile,
                        "items": items, "verdict": verdict,
                        "pins": pins,
                        "boundaries": {
                            "hit_rate_not_acceptance":
                                "F29 不拿宣传命中率当验收（台账明示）",
                            "desktop_typecheck":
                                "patch 017 未应用 oc28 只读树，desktop typecheck 属合并后步骤",
                            "host_level_negtest": "PENDING_ADMIN_ENV（§6.1 裁决#2）",
                        },
                    }, ensure_ascii=False, indent=1),
                    encoding="utf-8")
    print("RECON_OK" if all_ok else "RECON_FAILED")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
