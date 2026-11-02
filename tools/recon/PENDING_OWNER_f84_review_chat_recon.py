# -*- coding: utf-8 -*-
"""F84 review 内嵌聊天验收对账（PENDING_OWNER 版，工单 W2b-U48）。

权威（06 F84 assertion「review聊天只读当前可见真实格和引用；改格必须走写
权限」＋08§2 B2-b 审查UI链＋总账 §3.1 裁决③「模型＝DeepSeek BYOK（key
已配入产品隔离配置，不入 git）」）：聊天上下文＝tabular.read×
review_status×支持戳引用的只读白名单投影（绝不携带原件/身份映射）；
聊天侧零写通道（改格唯一走 F25 review_batch_human_edit＋F92 行级权限面
——W2b-U40 已交付，本对账以 F25 通道实证写权限面）；模型轮次走产品服务
（隔离拉起＋BYOK 配置只读复制，key 不打印不入 git），模型不可用＝具名
不伪输出。

分段（每 profile 同集 7 检）：
  C01 上下文闭集投影：tabular.read×review_status×支持戳引用 白名单合并
      （readOnly=true；逐格键闭集＝白名单；行/格序与投影同序）
  C02 引用＋出处指针：戳内引用逐条（citationText/status/verifiedScoped/
      quoteInArticle＋doc/page/textSha256）；合成 marker 扫描＝状态根预埋
      原件页文本/身份映射文件不漏进上下文（零原件零身份映射）
  C03 模型不可用具名不伪输出：无 opencode 通道＝review_chat_model_
      not_configured 具名拒（exit 3），无任何伪造回答
  C04 模型轮次走已配 DeepSeek BYOK（裁决③）：真轮次——回答非空、
      上下文随轮回传与装配同份（echo 对账）、sessionRef 在隔离服务可回
      读（轮次确经产品服务）、模型面字段具名 deepseek
  C05 聊天零写通道（动态）：ask 前后批面逐格逐键不变（零 generation 推
      进零回执新增）＋伪造写方法 method_not_connected 具名拒
  C06 改格仅经写权限通道：harness.review_batch_human_edit（F25）改格 →
      gen+1/source=human → 聊天上下文随账反映（只读投影跟随账本）；
      聊天侧从未写（C05/C06 合读＝账只被写通道动过一次）
  C07 闭集负例：DTO 闭集外字段/必带缺项具名拒；selfhost 另附 C07b＝
      seam 注入未知复核状态具名拒（in-process 注入径）

双 profile：
  desktop＝产品桥子进程全链（legal_entry CLI→[review_chat→tabular.*→
  harness public_entry 子进程]→SQLite MatterStore）——每次调用即新进程；
  selfhost＝PgMatterStore 直连容器 lh-pg-e08（provider registry 面）＋
  产品面同进程调用（review_chat/tabular seam 指向 PG 绑定方法）。

真机 Electron CDP 会话（desktop；U31/U07 先例）：scratch clone4
（026b106＋001-016＋scratch CDP 注入不入补丁）五断言：
  S01 聊天面板开＋只读提示在＋「未接入」回退消失（config 就位）
  S02 UI 提问→产品桥→隔离服务 DeepSeek 真轮次→回答渲染＋上下文行渲染
      （行数==格数）
  S03 上下文纯度 DOM 断言：格值/引用在 DOM；原件 marker 不在 DOM 全文
  S04 撤模型通道（config 改写即生效）→ typed 码呈现不伪回答
  S05 零写通道：seam 只有 ask；聊天面板零写按钮

用法（juscite worktree w2b-u48 根 cwd）：
  python -X utf8 tools/recon/PENDING_OWNER_f84_review_chat_recon.py \
      --profile desktop --profile selfhost

exit 0＝双 profile 全检过＋CDP 五断言全过（RECON_OK）；证据 JSON 写
evidence/F84/<profile>/。BYOK 配置只读复制（产品 %APPDATA%\\Juscite 只读
——config 快照前后对照；临时 lvyin config 会话后删净）；不触碰 oc28
主检出与 %APPDATA%\\JusBench；全程合成材料。
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest.mock
import urllib.request
from pathlib import Path

RUN_DATE = time.strftime("%Y%m%d")
REPO_ROOT = Path(__file__).resolve().parents[2]
LEGAL_ENTRY = REPO_ROOT / "implementation" / "python" / "legal_entry.py"
MATTER = "m-f84chat-recon"
SCOPE = {"kind": "matter", "matterId": MATTER}
BATCH = "brt-f84chat"

DEFAULT_HARNESS_ROOT = (
    r"D:\Codex\1.法律工作区\legal-harness工作区\legal-harness-repo"
    r"\.local\worktrees\w2b-u31"
)
DEFAULT_OC28 = Path(r"D:\Codex\1.法律工作区\jusbench工作区\oc28")
DEFAULT_CLONE = Path(os.environ.get("TEMP", r"C:\Users\being\AppData\Local"
                                    r"\Temp")) / "oc28-chain" / "clone4"
DEFAULT_BUN = Path.home() / ".bun" / "bun.exe"
DEV_VERSION = "2.0.0-local-f84u48"   # 隔离 dev 服务版记实值（打包 pin=2.0.28）

FACE_SHA = "a" * 64
PAGE_SHA = "b" * 64
# 合成 marker：若任何原件文本/路径/身份映射漏进上下文即被扫描抓出（戳内
# 预埋，扫描端断言缺席）。
SYNTH_ORIGINAL_MARKER = "SYNTH_ORIGINAL_PAGE_9f8e7d6c"
SYNTH_IDENTITY_MARKER = "SYNTH_IDENTITY_5a4b3c2d"

COLUMNS = [
    {"id": "amount", "name": "合同金额", "format": "decimal-string",
     "version": "1", "gold": {"kind": "number", "expect": "123456.78"}},
    {"id": "cited", "name": "法律依据", "format": "text", "version": "1",
     "gold": {"kind": "text"}},
]
ROW_COUNT = 2

QUESTION = "row-1 的合同金额是多少？只依据投影回答。"

# 上下文读取与服务客户端由 profile runner 注入（desktop=同进程产品面读，
# 其 harness 读仍走子进程全链；selfhost=同进程 seam 读）。
CONTEXT_READER: dict = {"fn": None}
SERVICE_CLIENT: dict = {"fn": None}


def command_key(request_id: str) -> dict:
    return {"requestId": "f84chat-" + request_id, "targetId": None,
            "expectedRevision": None, "inputRefs": []}


def synth_stamp() -> dict:
    """合成核验戳（形态与 U05 面一致；引用全合成——非真实法条）。"""
    return {
        "gate": {
            "via": "extraction.gate(W2b-U02)",
            "face": "citation.verify(W2a-U14 VERIFIED)→lccc_consumer",
            "faceSha256": FACE_SHA, "asOf": RUN_DATE, "runSeq": 1,
            "extractionBatchId": "exb-synth-f84", "candidateId": "cand_0001",
            "gateStatus": "CITATION_VERIFIED", "rejectionReasons": [],
        },
        "citations": [{
            "citationText": "《合成数据安全法》第七条",
            "status": "现行", "verifiedScoped": True,
            "quoteInArticle": True,
        }],
        "provenance": {"source": "material_extraction",
                       "doc": "synth_doc_f84",
                       "page": 3, "textSha256": PAGE_SHA},
    }


def plant_marker_files(state_root: Path) -> None:
    """把原件/身份 marker 预埋进 harness 状态根（桥唯一知道的根）：
    若聊天桥有任何原件文本/身份映射读取径，marker 必漏进上下文被 C02/S03
    扫描抓出；缺席＝桥只经投影读账（动态证明零原件零映射）。"""
    materials = state_root / "materials" / "synth_doc_f84"
    materials.mkdir(parents=True, exist_ok=True)
    (materials / "page-3.txt").write_text(
        "【合成原件页文本】%s\n金额 123,456.78 元\n" % SYNTH_ORIGINAL_MARKER,
        encoding="utf-8")
    identity = state_root / "identity"
    identity.mkdir(exist_ok=True)
    (identity / "mapping.json").write_text(
        json.dumps({"synth-doc-f84": SYNTH_IDENTITY_MARKER},
                   ensure_ascii=False),
        encoding="utf-8")


class Checks:
    def __init__(self):
        self.items: list[dict] = []

    def add(self, check_id: str, ok: bool, detail: str) -> bool:
        self.items.append(
            {"id": check_id, "status": "PASS" if ok else "FAIL",
             "detail": detail})
        print("[%s] %s — %s" % ("PASS" if ok else "FAIL", check_id, detail),
              flush=True)
        return ok

    @property
    def all_passed(self) -> bool:
        return all(item["status"] == "PASS" for item in self.items)

    @property
    def passed_count(self) -> int:
        return sum(1 for item in self.items if item["status"] == "PASS")


def call_entry(method: str, args: dict, config: dict) -> dict:
    """真产品入口子进程调用（legal_entry CLI）；返回 {exit, payload, code,
    result}。"""
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
        return {"exit": proc.returncode, "payload": payload,
                "code": payload.get("code") if isinstance(payload, dict)
                else None,
                "result": payload.get("result") if isinstance(payload, dict)
                else None}
    finally:
        os.unlink(request_handle.name)
        os.unlink(config_handle.name)


# ---------------------------------------------------------------------- #
# 公共流程（两 profile 同集 C01-C07；call 为 profile 注入的调用抽象：
# 成功返回 result dict，失败返回带 exit/code 的 dict）
# ---------------------------------------------------------------------- #


def prepare_batch(call, state_root: Path | None = None) -> None:
    if state_root is not None:
        plant_marker_files(state_root)
    created = call("harness.review_batch_create", {
        "actor_id": "lawyer-1", "scope": SCOPE, "key": command_key("rb1"),
        "batch": {"id": BATCH, "title": "F84 审查聊天（W2b-U48 合成）",
                  "columns": [{"id": c["id"], "name": c["name"]}
                              for c in COLUMNS],
                  "rows": [{"id": "row-%d" % i,
                            "cells": {"amount": None, "cited": None}}
                           for i in range(1, ROW_COUNT + 1)]}})
    if created.get("status") != "active":
        raise SystemExit("FATAL: 建批失败：%s" % created)
    call("harness.review_columns_define", {
        "actor_id": "lawyer-1", "scope": SCOPE, "key": command_key("rc1"),
        "batch_id": BATCH, "columns": COLUMNS})
    # 机器值进 row-1（claim→submit，F25 底座）；row-2 保持空格（pending）。
    claimed = call("harness.review_batch_claim", {
        "actor_id": "worker-1", "scope": SCOPE, "key": command_key("cl1"),
        "batch_id": BATCH, "row_id": "row-1", "lease_ttl_seconds": 600})
    cells = (claimed.get("snapshot") or {}).get("cells") or {}
    call("harness.review_batch_submit", {
        "actor_id": "worker-1", "scope": SCOPE, "key": command_key("su1"),
        "batch_id": BATCH, "row_id": "row-1",
        "lease_token": claimed["lease"]["token"],
        "cells": [
            {"cellId": "amount", "value": "123,456.78 元",
             "generation": cells["amount"]["generation"]},
            {"cellId": "cited", "value": "《合成数据安全法》第七条",
             "generation": cells["cited"]["generation"]},
        ]})
    # 支持戳（合成；provenance 内埋 marker 供 C02 扫描）＋复核回执。
    call("harness.review_support_record", {
        "actor_id": "lawyer-1", "scope": SCOPE, "key": command_key("st1"),
        "batch_id": BATCH, "row_id": "row-1", "cell_id": "amount",
        "entry": synth_stamp()})
    call("harness.review_receipt_record", {
        "actor_id": "lawyer-1", "scope": SCOPE, "key": command_key("rr1"),
        "batch_id": BATCH, "row_id": "row-1", "cell_id": "amount",
        "receipt": {"reviewer": "lawyer-1", "decision": "confirmed",
                    "decisionRef": "note-f84-1"}})


def snapshot_state(call) -> str:
    batch = call("harness.review_batch_read",
                 {"scope": SCOPE, "batch_id": BATCH})
    status = call("tabular.review_status",
                  {"review_batch_id": BATCH, "scope": SCOPE})
    return json.dumps({"batch": batch, "status": status},
                      sort_keys=True, ensure_ascii=False)


def common_flow(checks: Checks, call, state_root: Path) -> None:
    prepare_batch(call, state_root)

    # --- C01 上下文闭集投影 -----------------------------------------------
    context = CONTEXT_READER["fn"](call)
    cells = [cell for row in context.get("rows", [])
             for cell in row.get("cells", [])]
    whitelist = {"cellId", "columnName", "value", "cellGeneration",
                 "cellSource", "supportStatus", "reviewStatus", "goldMatch",
                 "goldMatchReason", "citations"}
    amount = next(cell for cell in cells if cell.get("cellId") == "amount")
    checks.add(
        "C01_context_whitelist_projection",
        context.get("readOnly") is True
        and len(cells) == ROW_COUNT * len(COLUMNS)
        and all(set(cell) == whitelist for cell in cells)
        and amount.get("value") == "123,456.78 元"
        and amount.get("reviewStatus") == "REVIEWED_CONFIRMED"
        and amount.get("supportStatus") == "SUPPORTED_CITATION_LEVEL"
        and amount.get("cellSource") == "machine",
        "上下文 readOnly=true；%d 格逐格键闭集＝白名单；值/复核/支持随投影"
        "（行格序与 tabular.read 同序）" % len(cells))

    # --- C02 引用＋出处指针＋marker 扫描（零原件/零身份映射）----------------
    citations = amount.get("citations", [])
    text = json.dumps(context, ensure_ascii=False)
    checks.add(
        "C02_citations_pointers_no_originals",
        len(citations) == 1
        and citations[0].get("citationText") == "《合成数据安全法》第七条"
        and citations[0].get("doc") == "synth_doc_f84"
        and citations[0].get("page") == 3
        and citations[0].get("textSha256") == PAGE_SHA
        and set(citations[0]) == {"citationText", "status", "verifiedScoped",
                                  "quoteInArticle", "doc", "page",
                                  "textSha256"}
        and SYNTH_ORIGINAL_MARKER not in text
        and SYNTH_IDENTITY_MARKER not in text
        and "originalPath" not in text and "pageText" not in text
        and "identityMapping" not in text,
        "引用逐条白名单（citationText/status/verifiedScoped/quoteInArticle"
        "＋doc/page/textSha256 指针）；marker 扫描：状态根预埋的原件页文本"
        "与身份映射文件未漏进上下文（桥只经投影读账——零字节零映射）")

    # --- C03 模型不可用具名不伪输出 ----------------------------------------
    no_model = call("review_chat.ask",
                    {"review_batch_id": BATCH, "scope": SCOPE,
                     "question": QUESTION},
                    config_override={"opencode_registration": None})
    checks.add(
        "C03_model_unavailable_named_not_fabricated",
        no_model.get("exit") == 3
        and "review_chat_model_not_configured" in str(no_model.get("code"))
        and no_model.get("result") is None,
        "撤模型通道后 exit 3 具名 review_chat_model_not_configured；无任何"
        "伪造回答体（result=None）")

    # --- C04 模型轮次走已配 DeepSeek BYOK（裁决③）--------------------------
    # call 抽象约定：成功返回 result dict（无 exit 键），失败带 exit/code。
    answer = call("review_chat.ask",
                  {"review_batch_id": BATCH, "scope": SCOPE,
                   "question": QUESTION})
    answer_ok = "exit" not in answer
    result = answer if answer_ok else {}
    echo = result.get("context") or {}
    session_ref = result.get("sessionRef") or ""
    session_live = False
    if session_ref and SERVICE_CLIENT["fn"] is not None:
        try:
            session_live = bool(SERVICE_CLIENT["fn"].session(session_ref))
        except Exception:
            session_live = False
    reply = result.get("reply") or ""
    diag = {
        "failed": not answer_ok,
        "code": str(answer.get("code")),
        "payloadHead": json.dumps(answer.get("payload"),
                                  ensure_ascii=False)[:160] if not answer_ok
        else "",
        "replyHead": reply[:40],
        "state": result.get("state"),
        "note": (result.get("note") or "")[:60],
        "sessionLive": session_live,
        "echoMatch": json.dumps(echo, sort_keys=True, ensure_ascii=False)
        == json.dumps(context, sort_keys=True, ensure_ascii=False),
    }
    checks.add(
        "C04_ask_real_turn_deepseek_byok",
        answer_ok
        and isinstance(reply, str) and len(reply) > 0
        and result.get("readOnly") is True
        and "deepseek" in str(result.get("model"))
        and echo.get("reviewBatchId") == BATCH
        and diag["echoMatch"]
        and session_live
        and session_ref.startswith("ses_f84chat_"),
        "真轮次经隔离产品服务（BYOK 配置只读复制，key 不打印不入 git）；回"
        "答非空；上下文 echo 与装配逐键同份；sessionRef 在隔离服务回读在案"
        "（session=%s…）；回答含金额原值=%s；diag=%s"
        % (session_ref[:24], ("123,456.78" in reply
                              or "123456.78" in reply),
           json.dumps(diag, ensure_ascii=False)))

    # --- C05 聊天零写通道（动态）-------------------------------------------
    before = snapshot_state(call)
    answer2 = call("review_chat.ask",
                   {"review_batch_id": BATCH, "scope": SCOPE,
                    "question": "row-1 的法律依据引用了什么？"})
    after = snapshot_state(call)
    forged = call("review_chat.edit_cell",
                  {"review_batch_id": BATCH, "scope": SCOPE,
                   "row_id": "row-1", "cell_id": "amount", "value": "1 元"})
    checks.add(
        "C05_chat_zero_write_channel",
        "exit" not in answer2 and before == after
        and forged.get("exit") == 3
        and "method_not_connected:review_chat.edit_cell"
        in str(forged.get("code")),
        "两次 ask 前后批面逐格逐键不变（零 generation 推进零回执新增）；伪"
        "造写方法 review_chat.edit_cell＝method_not_connected 具名拒（组外"
        "不落地）")

    # --- C06 改格仅经写权限通道（聊天上下文随账）----------------------------
    row = call("harness.review_batch_read",
               {"scope": SCOPE, "batch_id": BATCH, "row_id": "row-2"})
    gen0 = ((row.get("row") or {}).get("cells") or {})[
        "amount"]["generation"]
    edited = call("harness.review_batch_human_edit", {
        "actor_id": "lawyer-1", "scope": SCOPE,
        "key": command_key("he1"), "batch_id": BATCH, "row_id": "row-2",
        "cells": [{"cellId": "amount", "value": "77,777.00 元（人改）",
                   "generation": gen0}]})
    context2 = CONTEXT_READER["fn"](call)
    row2_cells = [cell for row_ in context2.get("rows", [])
                  for cell in row_.get("cells", [])]
    row2_amount = next(cell for cell in row2_cells
                       if cell.get("value") == "77,777.00 元（人改）")
    checks.add(
        "C06_edit_via_write_channel_only",
        "exit" not in edited
        and row2_amount.get("cellGeneration") == gen0 + 1
        and row2_amount.get("cellSource") == "human"
        and row2_amount.get("reviewStatus") == "NOT_REVIEWED",
        "人改唯一走 harness.review_batch_human_edit（F25 写权限通道）→ "
        "gen%d→%s/source=human；聊天上下文随账反映新值（只读投影跟随账本，"
        "聊天侧未写）" % (gen0, row2_amount.get("cellGeneration")))

    # --- C07 闭集负例（两 profile 同形）-------------------------------------
    extra_field = call("review_chat.ask",
                       {"review_batch_id": BATCH, "scope": SCOPE,
                        "question": QUESTION, "row_id": "row-1"},
                       config_override={"opencode_registration": None})
    no_question = call("review_chat.ask",
                       {"review_batch_id": BATCH, "scope": SCOPE},
                       config_override={"opencode_registration": None})
    checks.add(
        "C07_dto_closed_set_named_reject",
        extra_field.get("exit") == 3
        and str(extra_field.get("code")).startswith(
            "review_chat_ask_args_invalid")
        and no_question.get("exit") == 3
        and str(no_question.get("code")).startswith(
            "review_chat_ask_args_invalid"),
        "DTO 闭集外字段/必带缺项＝exit 3 具名 review_chat_ask_args_invalid"
        "（无旁路）")


# ---------------------------------------------------------------------- #
# 隔离产品服务（e07_live_recon 拓扑：临时 XDG 根＋BYOK 配置只读复制）
# ---------------------------------------------------------------------- #


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def port_open(port: int) -> bool:
    with socket.socket() as probe:
        probe.settimeout(1.0)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def pid_alive(pid: int) -> bool:
    proc = subprocess.run(["tasklist", "/FI", "PID eq {}".format(pid)],
                          capture_output=True, text=True, timeout=30)
    return str(pid) in proc.stdout


class LiveService:
    """隔离 OpenCode 产品服务（临时根；DeepSeek BYOK 配置只读复制）。"""

    def __init__(self, oc28: Path, bun: Path, product_config: Path):
        self.oc28 = oc28
        self.bun = bun
        self.product_config = product_config
        self.base = Path(tempfile.mkdtemp(prefix="f84chat-svc-"))
        self.roots = {
            "state_root": self.base / "oc" / "state",
            "data_root": self.base / "oc" / "data",
            "config_root": self.base / "oc" / "config",
            "cache_root": self.base / "oc" / "cache",
        }
        for key in self.roots:
            self.roots[key].mkdir(parents=True)
        self.port = free_port()
        self.proc = None
        self.registration: dict | None = None
        self.client = None
        self.appdata_snapshot_before = self._snapshot_appdata()

    @staticmethod
    def _snapshot_appdata() -> dict:
        appdata = Path(os.environ["APPDATA"]) / "Juscite"
        snap = {}
        target = appdata / "config" / "opencode" / "opencode.json"
        if target.exists():
            stat = target.stat()
            snap[str(target)] = (stat.st_size, stat.st_mtime_ns)
        return snap

    def launch(self) -> dict:
        # BYOK provider 配置只读复制进临时根（密钥不出本机、不打印、不入 git）。
        config_dir = self.roots["config_root"] / "opencode"
        config_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(self.product_config, config_dir / "opencode.json")
        env = dict(os.environ)
        env["XDG_STATE_HOME"] = str(self.roots["state_root"])
        env["XDG_DATA_HOME"] = str(self.roots["data_root"])
        env["XDG_CONFIG_HOME"] = str(self.roots["config_root"])
        env["XDG_CACHE_HOME"] = str(self.roots["cache_root"])
        env["OPENCODE_DISABLE_MODELS_FETCH"] = "1"
        env["OPENCODE_CHANNEL"] = "local"
        env["OPENCODE_VERSION"] = DEV_VERSION
        log = open(self.base / "service.log", "ab")
        self.proc = subprocess.Popen(
            [str(self.bun), "run", "--cwd", "packages/cli",
             "--define=OPENCODE_VERSION=process.env.OPENCODE_VERSION",
             "src/index.ts", "serve", "--service",
             "--hostname", "127.0.0.1", "--port", str(self.port)],
            cwd=str(self.oc28), env=env, stdout=log, stderr=subprocess.STDOUT)
        reg_path = self.roots["state_root"] / "opencode" / "service-local.json"
        deadline = time.monotonic() + 240.0
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                raise SystemExit("FATAL: 隔离服务进程退出（exit=%s，log=%s）"
                                 % (self.proc.returncode,
                                    self.base / "service.log"))
            reg = None
            if reg_path.exists():
                try:
                    reg = json.loads(reg_path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    reg = None
            if reg is not None:
                try:
                    client = self._client(reg)
                    info = client.request("GET", "/api/info")
                    value = info.get("data", info) if isinstance(info, dict) \
                        else {}
                    if isinstance(value, dict) and value.get("version"):
                        self.registration = reg
                        self.client = client
                        return reg
                except Exception:
                    pass
            time.sleep(1.0)
        raise SystemExit("FATAL: 隔离服务 240s 未就绪（log=%s）"
                         % (self.base / "service.log"))

    def _client(self, reg: dict):
        from opencode_http import Client
        token = base64.b64encode(
            ("opencode:" + reg["password"]).encode()).decode("ascii")
        return Client(reg["url"],
                      headers={"Authorization": "Basic " + token},
                      timeout=120.0)

    def verify_untouched_appdata(self, checks: Checks) -> None:
        after = self._snapshot_appdata()
        checks.add(
            "S00_appdata_readonly_snapshot",
            self.appdata_snapshot_before == after,
            "产品 %APPDATA%\\Juscite 的 opencode.json 前后快照一致（只读复"
            "制，零改动；%APPDATA%\\JusBench 全程零触碰）")

    def shutdown(self) -> None:
        reg_path = self.roots["state_root"] / "opencode" / "service-local.json"
        try:
            reg = json.loads(reg_path.read_text(encoding="utf-8"))
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(reg["pid"])],
                           capture_output=True, timeout=60)
            deadline = time.monotonic() + 45.0
            while time.monotonic() < deadline:
                if not port_open(self.port) and not pid_alive(reg["pid"]):
                    break
                time.sleep(1.0)
        except Exception:
            if self.proc is not None and self.proc.poll() is None:
                subprocess.run(["taskkill", "/F", "/T",
                                "/PID", str(self.proc.pid)],
                               capture_output=True, timeout=60)
        shutil.rmtree(self.base, ignore_errors=True)


# ---------------------------------------------------------------------- #
# 真机 Electron CDP 会话（desktop；clone4＝026b106＋001-016＋scratch CDP）
# ---------------------------------------------------------------------- #


class Cdp:
    """极小 CDP 客户端（Runtime.evaluate / Page.captureScreenshot）。"""

    def __init__(self, ws_url: str):
        import websocket  # websocket-client
        self.conn = websocket.create_connection(ws_url, timeout=60)
        self.seq = 0

    def call(self, method: str, params: dict | None = None) -> dict:
        self.seq += 1
        self.conn.send(json.dumps({"id": self.seq, "method": method,
                                   "params": params or {}}))
        while True:
            message = json.loads(self.conn.recv())
            if message.get("id") == self.seq:
                return message

    def evaluate(self, expression: str, await_promise: bool = False):
        result = self.call("Runtime.evaluate", {
            "expression": expression, "returnByValue": True,
            "awaitPromise": await_promise})
        value = result.get("result", {}).get("result", {})
        if value.get("type") == "undefined":
            return None
        return value.get("value")

    def screenshot(self, path: str) -> None:
        shot = self.call("Page.captureScreenshot",
                         {"format": "png"})["result"]["data"]
        Path(path).write_bytes(base64.b64decode(shot))


def wait_cdp_port(port: int, timeout: float = 300.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(
                    "http://127.0.0.1:%d/json" % port, timeout=2) as response:
                targets = json.loads(response.read().decode("utf-8"))
                pages = [t for t in targets if t.get("type") == "page"]
                if pages:
                    return pages[0]
        except Exception:
            time.sleep(1.0)
    raise SystemExit("FATAL: CDP 端口 %d 超时未就绪" % port)


def js_wait(selector: str, timeout_ms: int = 20000) -> str:
    return (
        "new Promise(resolve => {const t0=Date.now();"
        "const tick=()=>{const el=document.querySelector('%s');"
        "if(el)resolve(true);else if(Date.now()-t0>%d)resolve(false);"
        "else setTimeout(tick,120)};tick()})" % (selector, timeout_ms))


def js_attr(selector: str, attr: str) -> str:
    return (
        "(() => {const el=document.querySelector('%s');"
        "return el ? el.getAttribute('%s') : null;})()" % (selector, attr))


def js_set_input(selector: str, value: str) -> str:
    return (
        "(() => {const el=document.querySelector('%s');"
        "if(!el) return 'input-not-found';"
        "const setter=Object.getOwnPropertyDescriptor("
        "window.HTMLInputElement.prototype,'value').set;"
        "setter.call(el,%s);"
        "el.dispatchEvent(new Event('input',{bubbles:true}));"
        "return 'set';})()" % (selector, json.dumps(value)))


def cdp_session(checks: Checks, clone: Path, bun: Path, worktree: Path,
                harness_root: Path, service_reg: Path, cdp_port: int,
                evidence_dir: Path) -> None:
    """真机 Electron 会话五断言（S01-S05）。config 写 %APPDATA%\\Juscite
    （U31 先例：临时 config 会话后删净；%APPDATA%\\JusBench 零触碰）。"""
    temporary = tempfile.TemporaryDirectory(prefix="f84chat-cdp-")
    state_root = Path(temporary.name) / "state"
    state_root.mkdir(parents=True)
    user_data = Path(os.environ["APPDATA"]) / "Juscite"
    chat_config = user_data / "config" / "lvyin" / "review-chat.json"
    chat_config.parent.mkdir(parents=True, exist_ok=True)

    def write_chat_config(with_model: bool) -> None:
        config = {
            "python": sys.executable,
            "bridge_entry": str(worktree / "implementation" / "python"
                                / "legal_entry.py"),
            "review_batch_id": BATCH,
            "review_matter_id": MATTER,
            "harness_public_entry": str(
                harness_root
                / "tools/workflow-tools/harness/public_entry.py"),
            "harness_target": "opencode",
            "harness_state_root": str(state_root),
            "harness_python": sys.executable,
        }
        if with_model:
            config["opencode_registration"] = str(service_reg)
        chat_config.write_text(json.dumps(config, ensure_ascii=False,
                                          indent=1), encoding="utf-8")

    sys.path.insert(0, str(harness_root / "src"))
    from legal_harness.state.matter_store import MatterStore
    MatterStore(state_root).create_matter(MATTER, "cas://profile-f84-cdp")

    def harness_call(method: str, params: dict) -> dict:
        handle = tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", suffix=".json", delete=False)
        try:
            json.dump({"method": method, "params": params}, handle,
                      ensure_ascii=False)
            handle.close()
            env = dict(os.environ)
            env["LH_LEGAL_STATE_ROOT"] = str(state_root)
            proc = subprocess.run(
                [sys.executable, "-X", "utf8",
                 str(harness_root
                     / "tools/workflow-tools/harness/public_entry.py"),
                 "--reviewbatch-json", handle.name, "--target", "opencode"],
                capture_output=True, text=True, encoding="utf-8", env=env,
                timeout=180, cwd=str(harness_root))
            payload = json.loads(proc.stdout)
            if proc.returncode != 0 or not isinstance(payload, dict) \
                    or "result" not in payload:
                raise SystemExit("FATAL: CDP 状态准备失败：%s → %s"
                                 % (method, payload))
            return payload["result"]
        finally:
            os.unlink(handle.name)

    prepare_batch(lambda method, args, config_override=None:
                  harness_call(method, args), state_root)
    write_chat_config(with_model=True)
    print("[cdp] state=%s config=%s" % (state_root, chat_config), flush=True)

    env = dict(os.environ)
    env["LVYIN_CDP_PORT"] = str(cdp_port)
    # dev.ts 内部 Bun.spawn(["bun", ...]) 从 PATH 找 bun——bun 目录前置。
    env["PATH"] = str(bun.parent) + os.pathsep + env.get("PATH", "")
    electron = None
    if not port_open(cdp_port):
        electron = subprocess.Popen(
            [str(bun), "run", "dev:desktop"], cwd=str(clone), env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    readback: dict = {"cdpPort": cdp_port, "batch": BATCH, "matter": MATTER}
    try:
        page = wait_cdp_port(cdp_port)
        cdp = Cdp(page["webSocketDebuggerUrl"])
        time.sleep(3)   # 等 seam 注入；渲染层水合另按轮询等待（冷启动可达分钟级）

        # S01 面板打开＋只读提示＋fail-closed 回退消失（轮询等水合）
        opened = "toggle-not-found"
        deadline = time.time() + 90.0
        while time.time() < deadline:
            opened = cdp.evaluate("""(() => {
          const buttons = [...document.querySelectorAll('button')];
          const toggle = buttons.find(b => b.textContent &&
            (b.textContent.includes('审查聊天') ||
             b.textContent.includes('收起审查聊天')));
          if (!toggle) return 'toggle-not-found';
          if (!toggle.textContent.includes('收起审查聊天')) toggle.click();
          return 'opened';
        })()""")
            if opened == "opened":
                break
            time.sleep(2.0)
        rendered = cdp.evaluate(
            js_wait('[data-testid="review-chat-surface"]'),
            await_promise=True)
        readonly_note = cdp.evaluate(
            "!!document.querySelector("
            "'[data-testid=\"review-chat-readonly-note\"]')")
        not_connected = cdp.evaluate(
            "!!document.querySelector("
            "'[data-testid=\"review-chat-not-connected\"]')")
        readback["S01_panel"] = {
            "opened": opened, "rendered": rendered,
            "readonlyNote": readonly_note, "notConnected": not_connected}
        checks.add(
            "S01_chat_panel_readonly_note",
            opened == "opened" and rendered is True and readonly_note
            and not not_connected,
            "审查聊天面板开；只读纪律提示在（改格必走写权限通道文案）；未接"
            "入回退消失（config 就位）")

        # S02 UI 提问→真轮次→回答＋上下文行渲染（Python 侧轮询：模型轮次
        # 可达分钟级，不长阻塞 CDP socket；复用活实例时按 session 属性等
        # 「新」回答——每次 ask 都建新 session，旧回答不算数）
        pre_session = cdp.evaluate(
            "(()=>{const el=document.querySelector("
            "'[data-testid=\"review-chat-answer\"]');"
            "return el?el.getAttribute('data-chat-session'):null;})()")
        cdp.evaluate(js_set_input('[data-testid="review-chat-question"]',
                                  QUESTION))
        cdp.evaluate(
            "document.querySelector('[data-testid=\"review-chat-ask\"]')"
            ".click()")
        deadline = time.time() + 180.0
        answered = False
        while time.time() < deadline:
            session_attr = cdp.evaluate(
                "(()=>{const el=document.querySelector("
                "'[data-testid=\"review-chat-answer\"]');"
                "return el?el.getAttribute('data-chat-session'):null;})()")
            if session_attr and session_attr != pre_session:
                answered = True
                break
            time.sleep(2.0)
        time.sleep(1.5)
        state = cdp.evaluate(
            js_attr('[data-testid="review-chat-answer"]', "data-chat-state"))
        reply = cdp.evaluate(
            "(()=>{const el=document.querySelector("
            "'[data-testid=\"review-chat-reply\"]');"
            "return el?el.textContent:null;})()")
        line_count = cdp.evaluate(
            "document.querySelectorAll('[data-chat-context-line]').length")
        readback["S02_ask"] = {
            "answered": answered, "state": state,
            "replyHead": (reply or "")[:60], "contextLines": line_count}
        checks.add(
            "S02_ask_real_turn_rendered",
            answered is True and state == "COMPLETE"
            and isinstance(reply, str) and len(reply) > 0
            and line_count == ROW_COUNT * len(COLUMNS),
            "UI 提问→产品桥→隔离服务 DeepSeek 真轮次 COMPLETE；回答渲染非"
            "空；上下文行 %s==格数（随轮只读投影渲染）" % line_count)

        # S03 上下文纯度 DOM 断言
        body_text = cdp.evaluate("document.body.innerText") or ""
        checks.add(
            "S03_context_purity_dom",
            "123,456.78 元" in body_text
            and "《合成数据安全法》第七条" in body_text
            and SYNTH_ORIGINAL_MARKER not in body_text
            and SYNTH_IDENTITY_MARKER not in body_text,
            "格值与引用在 DOM；原件 marker/身份 marker 不在 DOM 全文（渲染"
            "侧零原件零映射）")

        # S04 撤模型通道（config 改写即生效）→ typed 码不伪回答（error 元素
        # 常驻——轮询到 typed 码文本本身才算）
        write_chat_config(with_model=False)
        cdp.evaluate(js_set_input('[data-testid="review-chat-question"]',
                                  "再问一次：row-1 的值？"))
        cdp.evaluate(
            "document.querySelector('[data-testid=\"review-chat-ask\"]')"
            ".click()")
        deadline = time.time() + 90.0
        error_seen = False
        error_text = ""
        while time.time() < deadline:
            error_text = cdp.evaluate(
                "(()=>{const el=document.querySelector("
                "'[data-testid=\"review-chat-error\"]');"
                "return el?el.textContent:'';})()") or ""
            if "review_chat_model_not_configured" in error_text:
                error_seen = True
                break
            time.sleep(2.0)
        time.sleep(1.0)
        error_text = cdp.evaluate(
            "(()=>{const el=document.querySelector("
            "'[data-testid=\"review-chat-error\"]');"
            "return el?el.textContent:'';})()") or ""
        readback["S04_unconfigured"] = {
            "errorSeen": error_seen, "errorText": error_text[:80]}
        checks.add(
            "S04_model_removed_typed_not_fabricated",
            error_seen is True
            and "review_chat_model_not_configured" in error_text
            and "不伪造" in error_text,
            "撤模型通道（config 改写即生效）后 typed 码 "
            "review_chat_model_not_configured 响亮呈现＋「不伪造」提示；无"
            "编造回答")

        # S05 零写通道：seam 只有 ask＋聊天面板零写按钮
        seam_keys = cdp.evaluate("Object.keys(window.lvyinReviewChat || {})")
        chat_write_buttons = cdp.evaluate(
            "document.querySelectorAll("
            "'[data-testid=\"review-chat-surface\"] [data-review-action]')"
            ".length")
        chat_inputs = cdp.evaluate(
            "document.querySelectorAll("
            "'[data-testid=\"review-chat-surface\"] input').length")
        readback["S05_zero_write"] = {
            "seamKeys": seam_keys, "writeButtons": chat_write_buttons,
            "inputs": chat_inputs}
        checks.add(
            "S05_seam_ask_only_zero_write_buttons",
            seam_keys == ["ask"] and chat_write_buttons == 0
            and chat_inputs == 1,
            "seam 面=Object.keys [ask]（零写方法）；聊天面板零写按钮、唯"
            "一输入=提问框（F84 红线即面即守）")

        cdp.screenshot(str(evidence_dir
                           / "f84-review-chat-electron.png"))
    finally:
        if electron is not None and electron.poll() is None:
            subprocess.run(["taskkill", "/F", "/T", "/PID",
                            str(electron.pid)],
                           capture_output=True, timeout=60)
        try:
            chat_config.unlink()
        except FileNotFoundError:
            pass
        temporary.cleanup()
    (evidence_dir / "f84-review-chat-cdp-readback.json").write_text(
        json.dumps(readback, ensure_ascii=False, indent=1),
        encoding="utf-8")
    print("[cdp] readback=%s" % (evidence_dir
                                 / "f84-review-chat-cdp-readback.json"),
          flush=True)


# ---------------------------------------------------------------------- #
# profile runners
# ---------------------------------------------------------------------- #


class Recon:
    def __init__(self, harness_root: Path, service_registration: Path):
        self.harness_root = harness_root
        self.service_registration = service_registration
        self.checks = Checks()

    def base_config(self, state_root: Path) -> dict:
        registration = state_root.parent / "bridge-harness-registration.json"
        registration.write_text(json.dumps(
            {"url": "http://127.0.0.1:1", "password": "synthetic-recon"}),
            encoding="utf-8")
        return {
            "harness_public_entry": str(
                self.harness_root
                / "tools/workflow-tools/harness/public_entry.py"),
            "harness_target": "opencode",
            "harness_state_root": str(state_root),
            "harness_service_registration": str(registration),
            "harness_timeout": 180,
            "harness_python": sys.executable,
            "opencode_registration": str(self.service_registration),
        }

    # -- desktop: full product-bridge subprocess chain --------------------
    def run_desktop(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="juscite-f84chat-d-")
        base = Path(temporary.name)
        state_root = base / "state"
        state_root.mkdir(parents=True)
        config = self.base_config(state_root)
        for path in (str(self.harness_root / "src"),):
            if path not in sys.path:
                sys.path.insert(0, path)
        from legal_harness.state.matter_store import MatterStore
        MatterStore(state_root).create_matter(MATTER,
                                              "cas://profile-f84chat-d")

        def call(method, args, config_override=None):
            merged = dict(config)
            if config_override:
                for key, value in config_override.items():
                    if value is None:
                        merged.pop(key, None)
                    else:
                        merged[key] = value
            outcome = call_entry(method, args, merged)
            if outcome["exit"] == 0:
                if outcome["result"] is not None:
                    return outcome["result"]
                # exit 0 但结果解析失败＝协议面破损——如实具名（不静默）。
                raise SystemExit(
                    "FATAL: %s exit 0 但结果缺失（payload=%s）"
                    % (method, json.dumps(outcome["payload"],
                                          ensure_ascii=False)[:400]))
            return {"exit": outcome["exit"], "payload": outcome["payload"],
                    "code": outcome["code"], "result": outcome["result"]}

        # desktop 的上下文读取＝同进程产品面（其 harness 读经
        # legal_entry.call→public_entry 子进程同链；纯 context 读不设独立
        # 公开方法——唯一公开方法＝ask，投影随 ask 回执回传＝C04 echo）。
        import review_chat

        def context_reader(_call):
            return review_chat.review_chat_context(
                {"review_batch_id": BATCH, "scope": SCOPE}, config)

        CONTEXT_READER["fn"] = context_reader
        print("[profile desktop] SQLite via product bridge subprocess "
              "(legal_entry CLI→harness public_entry)", flush=True)
        common_flow(self.checks, call, state_root)

    # -- selfhost: PgMatterStore direct + in-process product faces --------
    def run_selfhost(self, dsn: str) -> None:
        import uuid as _uuid

        for path in (str(self.harness_root / "src"),
                     str(self.harness_root / "tools/workflow-tools"),
                     str(self.harness_root), str(self.harness_root / "tests"),
                     str(REPO_ROOT / "implementation/python")):
            if path not in sys.path:
                sys.path.insert(0, path)
        from legal_harness.business.provider_registry import (
            resolve_provider_method,
        )
        from legal_harness.business.units import HarnessUnits
        from legal_harness.state.pg_store import PgMatterStore

        temporary = tempfile.TemporaryDirectory(prefix="juscite-f84chat-s-")
        base = Path(temporary.name)
        store = PgMatterStore(
            base / "state", dsn=dsn,
            schema="f84chat_" + _uuid.uuid4().hex[:12])
        units = HarnessUnits(store)
        names = (
            "harness.review_batch_create", "harness.review_batch_claim",
            "harness.review_batch_submit", "harness.review_batch_human_edit",
            "harness.review_batch_release", "harness.review_batch_read",
            "harness.review_columns_define", "harness.review_columns_read",
            "harness.review_support_record",
            "harness.review_support_invalidate",
            "harness.review_support_read",
            "harness.review_receipt_record",
            "harness.review_receipt_read",
            "harness.review_cell_rerun", "harness.review_cell_history")
        bound = {name: resolve_provider_method(name, units)
                 for name in names}
        store.create_matter(MATTER, "cas://profile-f84chat-pg")
        import tabular_review
        import tabular_review_ops
        import review_chat
        from bridge_errors import NotConnected as NotConnected_

        def _seam(method, args, cfg):
            if method in bound:
                return bound[method](**args)
            if method == "tabular.read":
                return tabular_review.tabular_read(args, cfg)
            if method == "tabular.review_status":
                return tabular_review_ops.review_status(args, cfg)
            raise NotConnected_("method_not_connected:" + method)

        patchers = [
            unittest.mock.patch.object(review_chat, "_harness_call", _seam),
            unittest.mock.patch.object(tabular_review, "_harness_call",
                                       _seam),
            unittest.mock.patch.object(tabular_review_ops, "_harness_call",
                                       _seam),
        ]
        for patcher in patchers:
            patcher.start()

        def call(method, args, config_override=None):
            # model 通道撤除（C03/C07）＝chat 配置无 opencode 键 → 产品面
            # service_client 具名拒（真径，不伪造结果）。
            chat_config = {}
            if not (config_override
                    and config_override.get("opencode_registration") is None):
                chat_config["opencode_registration"] = str(
                    self.service_registration)
            if method.startswith("harness."):
                if method not in bound:
                    return {"exit": 3, "code":
                            "method_not_connected:" + method,
                            "result": None}
                try:
                    return bound[method](**args)
                except Exception as exc:  # harness 面码原样上浮（不吞不改）
                    return {"exit": 1, "code": str(exc), "result": None}
            if method == "tabular.read":
                return tabular_review.tabular_read(args, {})
            if method == "tabular.review_status":
                return tabular_review_ops.review_status(args, {})
            # review_chat.*（桥形态对齐：冻结方法组外＝NOT_CONNECTED 具名）
            import legal_entry
            if method not in legal_entry.REVIEW_CHAT_METHODS:
                return {"exit": 3,
                        "code": "method_not_connected:" + method,
                        "result": None}
            try:
                return review_chat.review_chat_call(method, args,
                                                    chat_config)
            except NotConnected_ as exc:
                return {"exit": 3, "code": str(exc), "result": None}
            except Exception as exc:  # 同进程径原样上浮
                return {"exit": 1, "code": str(exc), "result": None}

        def context_reader(_call):
            return review_chat.review_chat_context(
                {"review_batch_id": BATCH, "scope": SCOPE},
                {"opencode_registration": str(self.service_registration)})

        CONTEXT_READER["fn"] = context_reader
        # 隔离服务客户端（C04 sessionRef 回读用）。
        reg = json.loads(Path(self.service_registration).read_text(
            encoding="utf-8"))
        from opencode_http import Client
        token = base64.b64encode(
            ("opencode:" + reg["password"]).encode()).decode("ascii")
        SERVICE_CLIENT["fn"] = Client(
            reg["url"], headers={"Authorization": "Basic " + token},
            timeout=60.0)
        print("[profile selfhost] PgMatterStore direct (provider registry "
              "face) + in-process product faces", flush=True)
        try:
            common_flow(self.checks, call, base / "state")
            # C07b-selfhost 附加：seam 注入未知复核状态具名拒。
            status = {
                "batchId": BATCH,
                "projections": [
                    {"rowId": "row-1", "cellId": "amount",
                     "reviewStatus": "REVIEWED_AUTOSIGNED",
                     "entryCount": 1},
                    {"rowId": "row-1", "cellId": "cited",
                     "reviewStatus": "NOT_REVIEWED", "entryCount": 0},
                    {"rowId": "row-2", "cellId": "amount",
                     "reviewStatus": "NOT_REVIEWED", "entryCount": 0},
                    {"rowId": "row-2", "cellId": "cited",
                     "reviewStatus": "NOT_REVIEWED", "entryCount": 0},
                ],
                "counts": {}, "face": "synthetic",
            }

            def _seam_bad_status(method, args, cfg):
                if method == "tabular.review_status":
                    return status
                return _seam(method, args, cfg)

            patcher = unittest.mock.patch.object(
                review_chat, "_harness_call", _seam_bad_status)
            patcher.start()
            try:
                review_chat.review_chat_context(
                    {"review_batch_id": BATCH, "scope": SCOPE}, {})
                ok, code = False, "no_raise"
            except NotConnected_ as exc:
                ok, code = True, str(exc)
            self.checks.add(
                "C07b_status_closed_set_injected_reject",
                ok and code.startswith("review_chat_status_invalid"),
                "seam 注入闭集外复核状态 REVIEWED_AUTOSIGNED＝具名拒 "
                "review_chat_status_invalid（响亮失败不静默渲染）")
            patcher.stop()
        finally:
            for patcher in patchers:
                patcher.stop()
            store.destroy()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.path.insert(0, str(REPO_ROOT / "implementation/python"))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", action="append",
                        choices=("desktop", "selfhost"), dest="profiles",
                        help="发行形态（可重复；不给则双形态全跑）")
    parser.add_argument("--harness-root", default=DEFAULT_HARNESS_ROOT)
    parser.add_argument(
        "--pg-dsn",
        default="postgresql://lh_app:e08-synth-only@127.0.0.1:55432/"
                "legal_harness",
        help="selfhost PgMatterStore 直连 DSN（默认＝本机合成容器 "
             "lh-pg-e08；合成专用凭据）")
    parser.add_argument("--oc28", default=str(DEFAULT_OC28))
    parser.add_argument("--clone", default=str(DEFAULT_CLONE))
    parser.add_argument("--bun", default=str(DEFAULT_BUN))
    parser.add_argument("--cdp-port", type=int, default=8319)
    parser.add_argument("--skip-cdp", action="store_true",
                        help="只跑双 profile（真机 CDP 会话另跑）")
    parser.add_argument("--evidence-root", default="evidence/F84")
    args = parser.parse_args()
    profiles = args.profiles or ["desktop", "selfhost"]

    harness_root = Path(args.harness_root)
    if not (harness_root
            / "tools/workflow-tools/harness/public_entry.py").is_file():
        print("FATAL: harness 公开入口不在 %s（w2b-u31 worktree）"
              % harness_root)
        return 2
    product_config = (Path(os.environ["APPDATA"]) / "Juscite" / "config"
                      / "opencode" / "opencode.json")
    if not product_config.is_file():
        print("FATAL: 产品 BYOK 配置缺失（%s）——裁决③模型通道不可用，"
              "C04 真轮次无法如实执行" % product_config)
        return 2

    service = LiveService(Path(args.oc28), Path(args.bun), product_config)
    reg = service.launch()
    print("[service] isolated product service at %s (pid=%s)"
          % (reg["url"], reg.get("pid")), flush=True)
    SERVICE_CLIENT["fn"] = service.client
    # 注册文件路径＝隔离服务 state 根下 service-local.json（供桌面 config
    # 与桥 opencode_registration 消费）。
    service_reg_path = (service.roots["state_root"] / "opencode"
                        / "service-local.json")
    recon = Recon(harness_root, service_reg_path)
    per_profile: dict = {}
    all_ok = True
    try:
        for profile in profiles:
            recon.checks = Checks()
            CONTEXT_READER["fn"] = None
            SERVICE_CLIENT["fn"] = service.client
            if profile == "desktop":
                recon.run_desktop()
            else:
                recon.run_selfhost(args.pg_dsn)
            commit = subprocess.run(
                ["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                cwd=str(REPO_ROOT)).stdout.strip()
            harness_commit = subprocess.run(
                ["git", "rev-parse", "HEAD"], capture_output=True,
                text=True,
                cwd=str(harness_root)).stdout.strip()
            evidence = {
                "run_date": RUN_DATE,
                "profile": profile,
                "command": "python -X utf8 " + " ".join(sys.argv[1:]),
                "cwd": str(REPO_ROOT),
                "subject_commit": commit,
                "harness_commit": harness_commit,
                "service": {"url": reg["url"], "pid": reg.get("pid"),
                            "byok_config_copied_readonly": True},
                "checks": recon.checks.items,
                "passed": recon.checks.passed_count,
                "total": len(recon.checks.items),
                "overall": "PASS" if recon.checks.all_passed else "FAIL",
            }
            out_dir = REPO_ROOT / args.evidence_root / profile
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / ("f84-review-chat-recon-%s.json"
                        % time.strftime("%Y%m%dT%H%M%S%z"))).write_text(
                json.dumps(evidence, ensure_ascii=False, indent=1),
                encoding="utf-8")
            per_profile[profile] = evidence
            all_ok = all_ok and recon.checks.all_passed
            print("---")
            print("profile=%s: %d/%d checks" % (
                profile, recon.checks.passed_count,
                len(recon.checks.items)))
        # 真机 Electron CDP 会话（desktop 覆盖面；工单验收断言之一）
        if not args.skip_cdp:
            evidence_dir = REPO_ROOT / args.evidence_root / "desktop"
            evidence_dir.mkdir(parents=True, exist_ok=True)
            cdp_checks = Checks()
            cdp_session(cdp_checks, Path(args.clone), Path(args.bun),
                        REPO_ROOT, harness_root, service_reg_path,
                        args.cdp_port, evidence_dir)
            service.verify_untouched_appdata(cdp_checks)
            (evidence_dir / ("f84-review-chat-cdp-%s.json"
                             % time.strftime("%Y%m%dT%H%M%S%z"))).write_text(
                json.dumps({
                    "run_date": RUN_DATE,
                    "command": "python -X utf8 " + " ".join(sys.argv[1:]),
                    "checks": cdp_checks.items,
                    "passed": cdp_checks.passed_count,
                    "total": len(cdp_checks.items),
                    "overall": "PASS" if cdp_checks.all_passed else "FAIL",
                }, ensure_ascii=False, indent=1), encoding="utf-8")
            print("---")
            print("cdp: %d/%d checks" % (cdp_checks.passed_count,
                                         len(cdp_checks.items)))
            all_ok = all_ok and cdp_checks.all_passed
    finally:
        service.shutdown()
    print(json.dumps({"status": "RECON_OK" if all_ok else "RECON_FAIL",
                      "profiles": list(per_profile)}, ensure_ascii=False))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
