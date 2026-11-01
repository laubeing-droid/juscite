"""E05 产品侧结果消费与五身份映射：活服务对账（W3-U24）.

义务段＝acceptance-ledger E05 行 failure_reason 余段「产品侧结果消费与五身份映射
留后续批次」（harness 侧活链 T12 已 VERIFIED：ticket/lease/三事件/CAS/三角/receipt）。
本工具把 T12 测试内联的临时 broker 落成产品面（implementation/python/
e05_result_broker.py）后做活服务实测：

  临时 XDG 四根＋临时 LH 状态根拉起 oc28 服务（绝不写 %APPDATA%\\Juscite）→
  合成目标账 preflight READY（E07 桥径）→ 进程内 targets/opencode 组合根
  （LH_OPENCODE_SERVICE_REGISTRATION 指临时注册文件）→ 合成 manifest 注册 →
  legal_research RUN_TO_COMPLETE 开跑（graph 四节点=四身份）→ 逐 dispatch 消费：
  专建 child session＋逐角色 prompt＋真 DeepSeek 轮次→回读取证三事件→
  transcript CAS→node result→漂移负向（child_session 变更必拒）→
  runtime_accept_canonical 三角闭合→绑定账行→绑定回读逐项核对
  （session↔goal/ticket/run/result）。

机制依据：
- 事件词汇/绑定执法全在 harness（opencode_v1/adapter.py verify_raw_events 闭字段
  集/sequence/ticket_hash/role_id==agent_type/时间窗/单调/同一 ses_ 会话；
  evidence.py 三角+success_child_session_changed）；产品面只装配与记账。
- 回读为准绳（message 回读含持久 idle 消息；SSE 挥发契约不作证据，
  e05-harness-recon.md §5.5/§6.3）。
- 五身份封闭集＝src/legal_harness/contracts/role_contracts.py ROLE_CONTRACT_HASHES
  键集，本工具对 harness 在盘值逐项核对（漂移即 FAIL）。

红线：材料全合成；harness 检出 git 只读；oc28 只读（serve 从源码跑，状态落临时根）；
%APPDATA%\\Juscite 只读（BYOK 配置只读复制进临时根，前后快照比对零写入）；
服务凭据/lease 本体不打印不入账（lease 只以 sha256 呈现）；不重试变异调用。

用法：
  python -X utf8 tools/PENDING_OWNER_e05_result_consumption_recon.py
      [--oc28 <path>] [--harness-root <path>] [--evidence-dir <path>] [--keep]

退出码：0 = E05_RECON_OK；1 = E05_RECON_FAIL；3 = E05_RECON_BLOCKED
（bun/oc28/harness 分支/产品配置缺失、模型轮次机械边界不可用）。
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
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch
from urllib.parse import quote

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "python"))

from opencode_http import Client, TransportError  # noqa: E402
from e05_result_broker import (  # noqa: E402
    FIVE_ROLE_IDS, E05BrokerError, ResultBindingStore, consume_dispatch,
    verify_consumption,
)
from e07_coordinator import BridgeGoalLedger, Coordinator  # noqa: E402
import legal_entry  # noqa: E402

DEFAULT_OC28 = Path(r"D:\Codex\1.法律工作区\jusbench工作区\oc28")
DEFAULT_HARNESS_ROOT = Path(r"D:\Codex\1.法律工作区\legal-harness工作区\legal-harness-repo")
DEFAULT_BUN = Path.home() / ".bun" / "bun.exe"
EXPECT_BRANCH = "v8-e05-opencode-target"
EXPECT_HEAD = "1de352e5"

DEV_VERSION = "2.0.0-local-e05u24"      # F-4：dev 版记实值（打包 pin=2.0.28）
PROVIDER_ID = "deepseek-byok"            # 总账 §3.1 ③ 用户裁决：DeepSeek BYOK
MODEL_ID = "deepseek-chat"

SCOPE = {"kind": "matter", "matterId": "m-e05-live"}
MATTER = "m-e05-live"
MATTER_PROFILE_REF = "cas://profile-e05-live"  # 同一 profile：goal 建档=run 开跑
GOAL_ID = "g-e05-live"
TASK_ID = "task-live"
MARKER = "E05-BROKER-LIVE-SYNTH-ACK"
MODEL = {"id": MODEL_ID, "providerID": PROVIDER_ID}
EXPECT_TEAM = (
    "case-conductor",          # issue_frame
    "intake-evidence-agent",   # material_coverage
    "legal-research-agent",    # unresolved_law
    "adversarial-review-agent",  # substance_qc
)

SYNTH_MATERIAL = (
    "【合成对账材料·非真实案件】\n"
    "卖方：合成卖方甲（测试数据）。买方：合成买方乙（测试数据）。\n"
    "合同总价款：人民币 12,345.67 元。\n"
    "付款期限：验收合格后 15 日内一次性支付。\n"
)


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


def _payload(body):
    """解服务 {data: ...} 信封（s0_smoke 回读形状）。"""
    return body.get("data", body) if isinstance(body, dict) else body


def _quote(session_id: str) -> str:
    return quote(session_id, safe="")


class ServiceTransport:
    """broker 传输面适配：opencode_http.Client → create/readback/prompt/messages。

    会话目录绑定合成工作区（装配面职责）；prompt 一次不重试；messages 全量
    分页（order=asc＋cursor.next，W1-U06 分页契约），transcript＝回读原始字节。
    """

    def __init__(self, client: Client, workspace: Path):
        self.client = client
        self.workspace = workspace

    def create_session(self, session_id, title, model=None):
        body = self.client.request("POST", "/api/session", {
            "id": session_id, "title": title,
            "location": {"directory": str(self.workspace.resolve())},
            "model": model or MODEL,
        })
        if _payload(body) is None:
            raise E05BrokerError("e05_session_create_failed", session_id=session_id)
        return self.session_readback(session_id)

    def session_readback(self, session_id):
        body = self.client.request(
            "GET", "/api/session/" + _quote(session_id))
        value = _payload(body)
        if not isinstance(value, dict):
            raise E05BrokerError("e05_session_readback_invalid",
                                 session_id=session_id)
        return value

    def prompt(self, session_id, message_id, text, model=None):
        payload = {"id": message_id, "text": text}
        if model:
            payload["model"] = model
        self.client.request("POST", "/api/session/{}/prompt".format(
            _quote(session_id)), payload)
        return {"id": message_id}

    def messages(self, session_id):
        """全量分页消息时间线；返回 (list, transcript 原始字节拼接)。"""
        listing: list = []
        raw_parts: list[bytes] = []
        path = "/api/session/{}/message?order=asc".format(_quote(session_id))
        while path:
            body, raw = self.client.request_raw("GET", path)
            value = _payload(body)
            if isinstance(value, list):
                listing.extend(value)
            raw_parts.append(raw)
            cursor = (body.get("cursor") or {}).get("next") \
                if isinstance(body, dict) else None
            path = "/api/session/{}/message?cursor={}".format(
                _quote(session_id), _quote(str(cursor))) if cursor else None
        return listing, b"".join(raw_parts)


class HarnessRuntimeFacade:
    """broker runtime 面适配：进程内 targets/opencode 组合根 service。"""

    def __init__(self, service):
        self.service = service

    def next_dispatch(self, run_id):
        return self.service.next_dispatch(run_id)

    def nodes(self, run_id):
        return self.service.store.nodes(run_id)

    def run_view(self, run_id):
        return self.service.store.run(run_id)

    def dispatch_view(self, dispatch_id):
        return self.service.store.dispatch(dispatch_id)

    def record_transcript(self, dispatch_id, lease, transcript: bytes):
        return self.service.runtime_record_transcript(dispatch_id, lease,
                                                      transcript)

    def seal_artifact(self, data: bytes) -> str:
        return str(self.service.store.cas.put_bytes(data)["sha256"])

    def normalize_events(self, bundle, dispatch_view):
        return self.service.runtime_adapter.verify_and_normalize(
            bundle, dispatch_view=dispatch_view)

    def accept_canonical(self, dispatch_id, lease, canonical_events,
                         verified_events, result):
        return self.service.runtime_accept_canonical(
            dispatch_id, lease, canonical_events, verified_events, result)

    def list_dispatches(self, run_id, matter_id):
        return self.service.list_dispatches(run_id, matter_id=matter_id)


def baseline_request(**changes) -> dict:
    """20 字段封闭公共请求（harness tests/helpers/runtime_fixture 同款）。"""
    value: dict = {
        "schema_version": "1.0", "task_id": "task-1", "matter_id": "matter-1",
        "task_type": "legal", "work_mode": "FULL_CASE", "output_type": "fact_inventory",
        "interaction_mode": "GUIDED", "objective": "test", "matter_profile_ref": "cas://matter",
        "materials_manifest_ref": "cas://materials", "target_scope": None,
        "base_artifact_ref": None, "resume_run_id": None, "parent_output_contract_ref": None,
        "document_contract_ref": None, "benchmark_execution_ref": None,
        "deadline_at": None, "delivery_reserve_minutes": None,
        "tool_operation": None, "tool_input_ref": None,
    }
    value.update(changes)
    return value


class Recon:
    def __init__(self, oc28: Path, harness_root: Path, keep: bool,
                 evidence_dir: Path | None):
        self.oc28 = oc28
        self.harness_root = harness_root
        self.keep = keep
        self.evidence_dir = evidence_dir
        self.checks: list[dict] = []
        self.evidence: dict = {}
        self.temp = None
        self.service_proc = None
        self.secret_strings: list[str] = []

    # -- check plumbing ------------------------------------------------------

    def step(self, name, ok, **facts):
        entry = {"check": name, "status": "PASS" if ok else "FAIL", **facts}
        self.checks.append(entry)
        print(json.dumps(entry, ensure_ascii=False), flush=True)
        if not ok:
            raise AssertionError(name)

    def blocked(self, reason, **facts):
        print(json.dumps({"check": reason, "status": "BLOCKED", **facts},
                         ensure_ascii=False), flush=True)
        print(json.dumps({"status": "E05_RECON_BLOCKED", "reason": reason},
                         ensure_ascii=False))
        raise SystemExit(3)

    # -- service lifecycle（T07 start_lvyin_service.ps1 拓扑，XDG 全临时根）---

    def launch(self, name="service_boot", old_pid=None) -> dict:
        roots = self.temp
        env = {k: v for k, v in os.environ.items()}
        env["XDG_STATE_HOME"] = str(roots["state_root"])
        env["XDG_DATA_HOME"] = str(roots["data_root"])
        env["XDG_CONFIG_HOME"] = str(roots["config_root"])
        env["XDG_CACHE_HOME"] = str(roots["cache_root"])
        env["OPENCODE_DISABLE_MODELS_FETCH"] = "1"
        env["OPENCODE_CHANNEL"] = "local"
        env["OPENCODE_VERSION"] = DEV_VERSION
        argv = [str(self.bun), "run", "--cwd", "packages/cli",
                "--define=OPENCODE_VERSION=process.env.OPENCODE_VERSION",
                "src/index.ts", "serve", "--service",
                "--hostname", "127.0.0.1", "--port", str(self.port)]
        log = open(roots["service_log"], "ab")
        self.service_proc = subprocess.Popen(argv, cwd=str(self.oc28), env=env,
                                             stdout=log,
                                             stderr=subprocess.STDOUT)
        return self.wait_ready(name, old_pid)

    def wait_ready(self, name, old_pid=None) -> dict:
        reg_path = self.temp["state_root"] / "opencode" / "service-local.json"
        deadline = time.monotonic() + 240.0
        reg = version = None
        while time.monotonic() < deadline:
            if self.service_proc is not None and self.service_proc.poll() is not None:
                self.blocked(name + "_process_exited",
                             exit_code=self.service_proc.returncode,
                             log=str(self.temp["service_log"]))
            reg = None
            if reg_path.exists():
                try:
                    reg = json.loads(reg_path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    reg = None
            if reg is not None and (old_pid is None
                                    or reg.get("pid") != old_pid):
                try:
                    client = self.build_client(reg)
                    info = client.request("GET", "/api/info")
                    value = _payload(info)
                    version = value.get("version") if isinstance(value, dict) else None
                    if version is not None:
                        break
                except TransportError:
                    pass
            time.sleep(1.0)
        if reg is None or version is None:
            self.blocked(name + "_ready_timeout",
                         log=str(self.temp["service_log"]))
        self.secret_strings.append(str(reg.get("password")))
        ok = (reg.get("url", "").endswith(":{}".format(self.port))
              and bool(reg.get("password")) and reg.get("pid")
              and version == DEV_VERSION)
        self.step(name, ok, url_port=self.port, pid=reg.get("pid"),
                  version=version, dev_version=(version != "2.0.28"))
        return reg

    def build_client(self, registration: dict, timeout: float = 60.0) -> Client:
        token = base64.b64encode(
            ("opencode:" + registration["password"]).encode()).decode("ascii")
        return Client(registration["url"],
                      headers={"Authorization": "Basic " + token},
                      timeout=timeout)

    def kill_service(self):
        reg = json.loads((self.temp["state_root"] / "opencode" /
                          "service-local.json").read_text(encoding="utf-8"))
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(reg["pid"])],
                       capture_output=True, timeout=60)
        deadline = time.monotonic() + 45.0
        closed, dead = False, False
        while time.monotonic() < deadline:
            closed = not port_open(self.port)
            dead = not pid_alive(reg["pid"])
            if closed and dead:
                break
            time.sleep(1.0)
        self.step("service_stopped_clean", closed and dead,
                  pid=reg["pid"], port=self.port)

    # -- %APPDATA% 只读证明：前后快照 --------------------------------------

    @staticmethod
    def snapshot_appdata() -> dict:
        appdata = Path(os.environ["APPDATA"]) / "Juscite"
        snap = {}
        for rel in ("config/opencode/opencode.json",):
            target = appdata / rel
            if target.exists():
                stat = target.stat()
                snap[rel] = (stat.st_size, stat.st_mtime_ns)
        state_dir = appdata / "state" / "opencode"
        if state_dir.is_dir():
            for item in sorted(state_dir.glob("*.json")):
                stat = item.stat()
                snap["state/opencode/" + item.name] = (stat.st_size,
                                                       stat.st_mtime_ns)
        return snap

    # ------------------------------------------------------------------ run

    def run(self, bun: Path) -> int:
        self.bun = bun
        self.temp = roots = {"base": Path(tempfile.mkdtemp(prefix="e05-live-"))}
        roots["state_root"] = roots["base"] / "oc" / "state"
        roots["data_root"] = roots["base"] / "oc" / "data"
        roots["config_root"] = roots["base"] / "oc" / "config"
        roots["cache_root"] = roots["base"] / "oc" / "cache"
        for key in ("state_root", "data_root", "config_root", "cache_root"):
            roots[key].mkdir(parents=True)
        roots["lh_state"] = roots["base"] / "lh-state"
        roots["lh_state"].mkdir()
        roots["workspace"] = roots["base"] / "workspace"
        (roots["workspace"] / "materials").mkdir(parents=True)
        roots["bindings"] = roots["base"] / "e05-bindings.json"
        roots["service_log"] = roots["base"] / "service.log"
        try:
            code = self._run_phases(roots)
        except Exception:
            self._teardown(keep=True)
            raise
        self._teardown()
        return code

    def _teardown(self, keep: bool = False):
        if self.service_proc is not None and self.service_proc.poll() is None:
            try:
                subprocess.run(["taskkill", "/F", "/T",
                                "/PID", str(self.service_proc.pid)],
                               capture_output=True, timeout=60)
            except Exception:
                pass
        if self.temp is not None and not (self.keep or keep):
            shutil.rmtree(self.temp["base"], ignore_errors=True)
        elif self.temp is not None:
            print(json.dumps({"kept_temp_root": str(self.temp["base"])},
                             ensure_ascii=False), flush=True)

    def _run_phases(self, roots) -> int:
        # ---- 阶段 0：前置、只读快照、合成材料 ------------------------------
        before = self.snapshot_appdata()
        product_config = Path(os.environ["APPDATA"]) / "Juscite" / \
            "config" / "opencode" / "opencode.json"
        if not product_config.exists():
            self.blocked("product_config_missing", path=str(product_config))
        opencode_config_dir = roots["config_root"] / "opencode"
        opencode_config_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(product_config, opencode_config_dir / "opencode.json")
        material = roots["workspace"] / "materials" / "合成材料-E05活服务对账.txt"
        material.write_text(SYNTH_MATERIAL, encoding="utf-8")
        self.port = free_port()
        self.step("topology_temp_roots", all(
            str(roots[key]).startswith(str(roots["base"]))
            for key in ("state_root", "data_root", "config_root", "cache_root")),
            base=str(roots["base"]), port=self.port)

        # ---- 阶段 1：活服务拉起＋显式落点 ----------------------------------
        reg = self.launch()
        client = self.build_client(reg)
        db_files = list((roots["data_root"] / "opencode").glob("*.db*"))
        self.step("explicit_db_landing", bool(db_files),
                  files=[f.name for f in db_files])
        self.step("explicit_registration_state_root",
                  reg.get("version") == DEV_VERSION,
                  path=str(roots["state_root"] / "opencode" / "service-local.json"))
        transport = ServiceTransport(client, roots["workspace"])

        # ---- 阶段 2：合成目标账（E07 桥径）＋preflight READY ---------------
        for path in (str(self.harness_root / "src"),
                     str(self.harness_root / "tools/workflow-tools")):
            if path not in sys.path:
                sys.path.insert(0, path)
        from legal_harness.state.matter_store import MatterStore
        MatterStore(roots["lh_state"]).create_matter(MATTER,
                                                     MATTER_PROFILE_REF)

        def key(request_id, target=None, expected=None):
            return {"requestId": request_id, "targetId": target,
                    "expectedRevision": expected, "inputRefs": []}

        ledger_config = {
            "harness_public_entry": str(
                self.harness_root / "tools/workflow-tools/harness/public_entry.py"),
            "harness_target": "opencode",
            "harness_state_root": str(roots["lh_state"]),
            "harness_service_registration": str(
                roots["state_root"] / "opencode" / "service-local.json"),
            "harness_timeout": 90,
        }
        goal_payload = {
            "schemaVersion": "1.0.0-draft", "matterId": MATTER,
            "goalId": GOAL_ID, "revision": 1,
            "confirmedScope": "合成货款追收预审（E05 产品侧结果消费活对账，全合成）",
            "hardConstraints": [
                {"id": "hc-1", "kind": "min_recovery", "value": "12345.67",
                 "description": "最低实收（合成）"}],
            "preferences": [],
            "unitTiming": {"unit": "CNY", "asOf": "2026-10-19"},
            "sourceDecisionRef": None, "supersedesRevision": None,
        }
        ledger = BridgeGoalLedger(ledger_config)
        legal_entry.call("harness.save_goal", {
            "actor_id": "e05-live-lawyer", "scope": SCOPE,
            "key": key("e05-sg-1"), "goal": goal_payload}, ledger_config)
        legal_entry.call("harness.decide_goal_plan", {
            "actor_id": "e05-live-lawyer", "scope": SCOPE,
            "key": key("e05-dp-1"),
            "decision": {"goalId": GOAL_ID, "planId": "plan-e05-live",
                         "planRevision": "1", "decision": "approved"}},
            ledger_config)
        legal_entry.call("harness.adopt_goal_task", {
            "actor_id": "e05-live-lawyer", "scope": SCOPE,
            "key": key("e05-at-1"),
            "adoption": {"goalId": GOAL_ID, "taskId": TASK_ID,
                         "action": "adopt",
                         "basis": {"factRevision": "fact-1",
                                   "lawRevision": "law-1"}}}, ledger_config)
        coordinator = Coordinator(BridgeGoalLedger(ledger_config), client,
                                  _UnusedStore(), turn_timeout=30.0)
        plan = coordinator.preflight(SCOPE, task_id=TASK_ID)
        self.step("goal_ledger_preflight_ready",
                  plan["decision"] == "READY", decision=plan["decision"])

        # ---- 阶段 3：进程内组合根＋manifest＋开跑（四节点=四身份）----------
        from targets.opencode import composition as oc_composition
        from legal_harness.contracts.role_contracts import ROLE_CONTRACT_HASHES
        service_root = {
            "LH_LEGAL_STATE_ROOT": str(roots["lh_state"]),
            "LH_OPENCODE_SERVICE_REGISTRATION": str(
                roots["state_root"] / "opencode" / "service-local.json"),
        }
        with patch.dict("os.environ", service_root):
            service = oc_composition.build_application()
        runtime = HarnessRuntimeFacade(service)

        self.step("five_role_ids_match_harness_contracts",
                  FIVE_ROLE_IDS == frozenset(ROLE_CONTRACT_HASHES)
                  and len(FIVE_ROLE_IDS) == 5,
                  harness_roles=sorted(ROLE_CONTRACT_HASHES))

        from tests.helpers.sanitized_fixture import (
            complete_digital_manifest, sanitized_bundle,
        )
        manifest_ctx = sanitized_bundle(
            service.store, matter_id=MATTER,
            manifest=complete_digital_manifest(document_id=MATTER))
        manifest_ref = manifest_ctx.__enter__()
        try:
            started = service.start(baseline_request(
                matter_id=MATTER, task_id=TASK_ID,
                matter_profile_ref=MATTER_PROFILE_REF,
                objective="e05 产品侧结果消费活对账（全合成材料）",
                materials_manifest_ref=manifest_ref,
                output_type="legal_research",
                interaction_mode="RUN_TO_COMPLETE",
            ))
            self.step("run_started_host_subsession",
                      started.get("status") == "ACCEPTED"
                      and started.get("execution_mode") == "host_subsession"
                      and started.get("host_probe", {}).get("runtime_kind") == "opencode",
                      execution_mode=started.get("execution_mode"))
            receipt = started.get("start_receipt") or {}
            run_id = str(receipt["run_id"])
            team = tuple(receipt.get("team") or [])
            self.step("run_team_four_identities", team == EXPECT_TEAM,
                      team=list(team), nodes=len(receipt.get("nodes") or []))
            self.evidence["run"] = {"run_id": run_id, "team": list(team)}

            # ---- 阶段 4：逐 dispatch 消费（真轮次＋漂移负向＋首笔重放负向）--
            store = ResultBindingStore(roots["bindings"])
            consumed: list[dict] = []
            for seq, expect_role in enumerate(EXPECT_TEAM):
                dispatch = runtime.next_dispatch(run_id)
                if dispatch.get("status") != "ACCEPTED":
                    self.blocked("next_dispatch_not_accepted",
                                 seq=seq, status=str(dispatch.get("status")))
                role_id = str(dispatch["ticket"]["role_id"])
                self.step("dispatch_{}_role".format(seq),
                          role_id == expect_role,
                          node=str(dispatch["ticket"]["node_id"]),
                          role_id=role_id)
                entry = consume_dispatch(
                    transport=transport, runtime=runtime, dispatch=dispatch,
                    goal_id=GOAL_ID, goal_task_id=TASK_ID, marker=MARKER,
                    model=MODEL, replay_probe=(seq == 0))
                stored = store.record(entry)
                consumed.append(stored)
                self.step("consumed_{}_{}".format(seq, expect_role),
                          stored["session_id"].startswith("ses_e05b_")
                          and stored["node_state"] == "RESULT_ACCEPTED"
                          and stored["role_id"] == expect_role,
                          session_id=stored["session_id"][:24] + "…",
                          receipt_id=stored["receipt_id"],
                          ticket_hash=stored["ticket_hash"][:16] + "…",
                          result_hash=stored["result_hash"][:16] + "…",
                          transcript_hash=stored["transcript_hash"][:16] + "…",
                          lease_sha256=stored["capability_lease_sha256"][:16] + "…")
            self.step("four_dispatches_four_distinct_sessions",
                      len({entry["session_id"] for entry in consumed}) == 4
                      and len(consumed) == 4)

            # ---- 阶段 5：绑定回读（session↔goal/ticket/run/result 逐项）----
            account = legal_entry.call("harness.get_goal",
                                       {"scope": SCOPE, "goal_id": GOAL_ID},
                                       ledger_config)
            bindings = store.read_by_run(run_id)
            self.step("binding_readback_run_complete",
                      len(bindings) == 4,
                      bindings=len(bindings))
            for index, entry in enumerate(bindings):
                node = next(n for n in runtime.nodes(run_id)
                            if str(n["node_id"]) == entry["node_id"])
                verify_kwargs = dict(
                    dispatch_view=runtime.dispatch_view(entry["dispatch_id"]),
                    node=node,
                    session_view=transport.session_readback(entry["session_id"]),
                    goal_view=account)
                verify_consumption(entry, **verify_kwargs)
                self.step("readback_{}_{}".format(
                    index, entry["role_id"]), True,
                    facets="ticket/role/state/result/session/goal")
            by_session = store.read_by_session(bindings[2]["session_id"])
            self.step("binding_readback_by_session",
                      by_session is not None
                      and by_session["dispatch_id"] == bindings[2]["dispatch_id"],
                      session_id=bindings[2]["session_id"][:24] + "…")
            goal_view = account.get("goal") if isinstance(account, dict) else None
            goal_id_seen = (goal_view or {}).get("goalId") if isinstance(
                goal_view, dict) else None
            self.step("goal_bound_to_consumptions",
                      goal_id_seen == GOAL_ID
                      and all(entry["goal_id"] == GOAL_ID for entry in bindings)
                      and account.get("openPause") is None,
                      goal_id=goal_id_seen)

            listing = runtime.list_dispatches(run_id, MATTER)
            listed = {str(row["dispatch_id"]): str(row["role_id"])
                      for row in listing.get("dispatches", listing.get("items", []))}
            self.step("list_dispatches_public_readback",
                      set(listed) == {entry["dispatch_id"] for entry in bindings}
                      and set(listed.values()) == set(EXPECT_TEAM),
                      count=len(listed))

            # ---- 阶段 6：产品面负向（封闭集外/重复绑定）--------------------
            try:
                consume_dispatch(
                    transport=transport, runtime=runtime,
                    dispatch={"status": "ACCEPTED",
                              "dispatch_id": "dispatch-synth",
                              "ticket_hash": "0" * 64,
                              "capability_lease": "x",
                              "ticket": {"run_id": run_id, "node_id": "n",
                                         "role_id": "generic-helper",
                                         "matter_id": MATTER}})
                self.step("unknown_role_refused", False, code="no-refuse")
            except E05BrokerError as exc:
                self.step("unknown_role_refused",
                          exc.code == "e05_role_not_in_five_identities",
                          code=exc.code)
            try:
                store.record(dict(bindings[0]))
                self.step("duplicate_binding_refused", False, code="no-refuse")
            except E05BrokerError as exc:
                self.step("duplicate_binding_refused",
                          exc.code == "e05_binding_duplicate_session",
                          code=exc.code)
        finally:
            manifest_ctx.__exit__(None, None, None)

        # ---- 阶段 7：卫生断言 ----------------------------------------------
        self.kill_service()
        after = self.snapshot_appdata()
        self.step("appdata_juscite_read_only", after == before,
                  watched=sorted(before))
        self.step("no_secret_in_output",
                  not any(secret and secret in json.dumps(
                      self.checks, ensure_ascii=False)
                      for secret in self.secret_strings),
                  scanned_outputs=len(self.checks))
        self._write_evidence(run_id, bindings)
        return 0

    def _write_evidence(self, run_id: str, bindings: list[dict]):
        if self.evidence_dir is None:
            return
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema": "e05-result-consumption-recon/1",
            "generated_at": datetime.now(UTC).isoformat(),
            "expect": {"branch": EXPECT_BRANCH, "head": EXPECT_HEAD,
                       "team": list(EXPECT_TEAM)},
            "run_id": run_id,
            "bindings": bindings,
            "checks": [c for c in self.checks if c.get("status") == "PASS"],
        }
        target = self.evidence_dir / "e05-result-consumption-recon.json"
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                          encoding="utf-8")
        print(json.dumps({"evidence_written": str(target),
                          "bindings": len(bindings)}, ensure_ascii=False),
              flush=True)


class _UnusedStore:
    """preflight 不触恢复存储——Coordinator 形参占位（零方法被调）。"""

    def load(self):
        return {"turns": []}


def verify_branch(root: Path) -> tuple[bool, str]:
    def git(*args):
        return subprocess.run(["git", "-C", str(root), *args],
                              capture_output=True, text=True,
                              encoding="utf-8", timeout=30)
    if not (root / "tools/workflow-tools/harness/public_entry.py").exists():
        return False, "harness_root_missing:" + str(root)
    branch = git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    head = git("rev-parse", "HEAD").stdout.strip()
    if head.startswith(EXPECT_HEAD) and branch == EXPECT_BRANCH:
        return True, "branch={} head={}".format(branch, head[:8])
    return False, "branch_mismatch:{}@{} expected:{}@{}".format(
        branch, head[:8], EXPECT_BRANCH, EXPECT_HEAD)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--oc28", type=Path, default=DEFAULT_OC28)
    parser.add_argument("--harness-root", type=Path,
                        default=DEFAULT_HARNESS_ROOT)
    parser.add_argument("--bun", type=Path, default=DEFAULT_BUN)
    parser.add_argument("--evidence-dir", type=Path,
                        default=REPO_ROOT / "evidence" / "E05")
    parser.add_argument("--keep", action="store_true",
                        help="保留临时根供取证")
    args = parser.parse_args()
    ok, note = verify_branch(args.harness_root)
    print(json.dumps({"check": "harness_branch",
                      "status": "PASS" if ok else "BLOCKED", "note": note},
                     ensure_ascii=False), flush=True)
    if not ok:
        print(json.dumps({"status": "E05_RECON_BLOCKED", "reason": note},
                         ensure_ascii=False))
        return 3
    if not args.oc28.is_dir():
        print(json.dumps({"status": "E05_RECON_BLOCKED",
                          "reason": "oc28_missing:" + str(args.oc28)},
                         ensure_ascii=False))
        return 3
    bun = args.bun if args.bun.exists() else Path(
        shutil.which("bun") or "")
    if not bun.exists():
        print(json.dumps({"status": "E05_RECON_BLOCKED",
                          "reason": "bun_not_found"}, ensure_ascii=False))
        return 3
    # harness tests 包可导入（sanitized_fixture）——T12 同款路径装配
    for path in (str(args.harness_root),):
        if path not in sys.path:
            sys.path.insert(0, path)
    recon = Recon(args.oc28, args.harness_root, args.keep, args.evidence_dir)
    try:
        code = recon.run(bun)
    except AssertionError as exc:
        print(json.dumps({"status": "E05_RECON_FAIL", "reason": str(exc),
                          "checks": len(recon.checks)}, ensure_ascii=False))
        return 1
    print(json.dumps({"status": "E05_RECON_OK", "checks": len(recon.checks)},
                     ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
