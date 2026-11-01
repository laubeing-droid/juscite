"""E07 live-service inbox/claim reconciliation: 轮次/中断/重启恢复零重发（W1-U06）.

e07-product-coordinator.md §7 遗留段的活服务实测：临时 LH/OpenCode 状态根＋合成
workspace 拉起 oc28 服务（复刻 T07 CLI serve 拓扑，XDG 四根全在临时目录，绝不写
%APPDATA%\\Juscite）→ 合成目标账 preflight READY → F-9 守卫径建会话 →
DeepSeek BYOK 合成材料轮次 → uncertain TransportError（杀服务）→ reconcile 四态
实测（ENQUEUED/CLAIMED_PENDING/CLAIMED_COMPLETE/NOT_ADMITTED ＋
resubmitRequiresNewMessageId 语义，服务端同 id 异内容=HTTP 409）→ 服务完整重启
→ recover() 全程零重发、停止不自动复活 → 版本记实值（F-4 dev 双轨）与显式 DB
落点断言。

机制依据（oc28 v2.0.28 实核）：
- POST /api/session/{sid}/prompt = "durably admit one session input and
  schedule agent-loop execution unless resume is false"（protocol session.ts
  session.prompt description）——resume:false 即确定性「已入队未投递」；
- core session/session.ts:175 `if (input.resume !== false) wake`；
- 同 id 重放（同 session 同类型）＝幂等返回原入队项：matches() 只比对
  session+type（core inbox.ts:70-73），不比对内容、不产生第二条入队——
  resubmitRequiresNewMessageId=True 的服务端语义（换内容必须换 id）；
- id 撞上已投递的非 user/synthetic 行（如 assistant 消息 id）→
  LifecycleConflict → PromptConflictError → HTTP 409 ConflictError
  （core inbox.ts promotedFromMessage；server handlers/session.ts:325-333）；
- 消息列表默认 desc（新→旧）且分页（protocol message.ts
  SessionMessagesQuery order/cursor）——锚定扫描必须显式 order=asc 并跟随
  cursor.next（W1-U06 活服务抓出的产品缺陷，e07_coordinator._fetch_messages
  已修）；
- 消息历史含 idle 标记（core session/message-updater.ts:69），回读为准绳，
  不依赖 SSE（事件流挥发契约，e05-harness-recon.md §5.5/§6.3）。

红线：材料全合成；harness 检出 git 只读；oc28 只读（serve 从源码跑，全部状态落
临时根）；产品 %APPDATA%\\Juscite 只读（复制 opencode.json 供 BYOK provider，
前后快照比对证明零写入）；服务凭据/密码不打印不入 git（临时根随跑随删）。

用法：
  python -X utf8 tools/e07_live_recon.py [--oc28 <path>] [--harness-root <path>]
      [--keep]（保留临时根供取证）

退出码：0 = LIVE_RECON_OK；1 = LIVE_RECON_FAIL；3 = LIVE_RECON_BLOCKED
  （bun/oc28/harness 分支/产品配置缺失、模型轮次机械边界不可用）。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "python"))

from opencode_http import Client, TransportError  # noqa: E402
from bridge_errors import SessionRejected  # noqa: E402
from e07_coordinator import (  # noqa: E402
    BridgeGoalLedger, Coordinator, CoordinatorBlocked, RecoveryStore,
    create_public_session, pause_banner,
)
import legal_entry  # noqa: E402

DEFAULT_OC28 = Path(r"D:\Codex\1.法律工作区\jusbench工作区\oc28")
DEFAULT_HARNESS_ROOT = Path(r"D:\Codex\1.法律工作区\legal-harness工作区\legal-harness-repo")
DEFAULT_BUN = Path.home() / ".bun" / "bun.exe"
EXPECT_BRANCH = "v8-e05-opencode-target"
EXPECT_HEAD = "1de352e5"

DEV_VERSION = "2.0.0-local-e07u06"       # F-4：dev 版记实值（打包 pin=2.0.28）
PROVIDER_ID = "deepseek-byok"            # 总账 §3.1 ③ 用户裁决：DeepSeek BYOK
MODEL_ID = "deepseek-chat"

SCOPE = {"kind": "matter", "matterId": "m-e07-live"}
MATTER = "m-e07-live"

GOAL_CONTENT_KEYS = ("confirmedScope", "hardConstraints", "preferences",
                     "unitTiming", "sourceDecisionRef")

SYNTH_MATERIAL = (
    "【合成对账材料·非真实案件】\n"
    "卖方：合成卖方甲（测试数据）。买方：合成买方乙（测试数据）。\n"
    "合同总价款：人民币 98,765.43 元。\n"
    "付款期限：验收合格后 30 日内一次性支付。\n"
    "违约金：买方逾期付款的，按日万分之五计付违约金。\n"
)
TURN1_PROMPT = (
    "这是律引 E07 活服务对账测试（全合成材料，非真实案件）。材料如下：\n"
    + SYNTH_MATERIAL +
    "请只用两行回答，不要展开分析，不要调用任何工具：\n"
    "第一行：合同总价款与付款期限；第二行：逾期付款违约金计算标准。\n"
)
PENDING_PROMPT = (
    "这是律引 E07 对账测试的占位轮次（全合成）。请写一段约四百字的纯文字"
    "说明（内容随意，围绕\"为什么消息系统需要持久入队与回读对账\"展开），"
    "不要调用任何工具，不要分点，连续写完。\n"
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


class Recon:
    def __init__(self, oc28: Path, harness_root: Path, keep: bool):
        self.oc28 = oc28
        self.harness_root = harness_root
        self.keep = keep
        self.checks: list[dict] = []
        self.temp = None
        self.service = None

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
        print(json.dumps({"status": "LIVE_RECON_BLOCKED", "reason": reason},
                         ensure_ascii=False))
        raise SystemExit(3)

    # -- service lifecycle（T07 start_lvyin_service.ps1 拓扑，XDG 全指临时根）---

    def launch(self, name="service_boot", old_pid=None) -> dict:
        roots = self.temp
        env = {k: v for k, v in os.environ.items()}
        env["XDG_STATE_HOME"] = str(roots["state_root"])
        env["XDG_DATA_HOME"] = str(roots["data_root"])
        env["XDG_CONFIG_HOME"] = str(roots["config_root"])
        env["XDG_CACHE_HOME"] = str(roots["cache_root"])
        env["OPENCODE_DISABLE_MODELS_FETCH"] = "1"   # models.dev 目录禁轮询（T07/T08）
        env["OPENCODE_CHANNEL"] = "local"
        env["OPENCODE_VERSION"] = DEV_VERSION
        argv = [str(self.bun), "run", "--cwd", "packages/cli",
                "--define=OPENCODE_VERSION=process.env.OPENCODE_VERSION",
                "src/index.ts", "serve", "--service",
                "--hostname", "127.0.0.1", "--port", str(self.port)]
        log = open(roots["service_log"], "ab")
        self.service = subprocess.Popen(argv, cwd=str(self.oc28), env=env,
                                        stdout=log, stderr=subprocess.STDOUT)
        return self.wait_ready(name, old_pid)

    def wait_ready(self, name, old_pid=None) -> dict:
        """等服务就绪。重启场景（old_pid 给定）须等到注册文件换新实例才可信。"""
        reg_path = self.temp["state_root"] / "opencode" / "service-local.json"
        deadline = time.monotonic() + 240.0
        reg = version = None
        while time.monotonic() < deadline:
            if self.service is not None and self.service.poll() is not None:
                self.blocked(name + "_process_exited",
                             exit_code=self.service.returncode,
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
                    value = info.get("data", info) if isinstance(
                        info, dict) else {}
                    version = value.get("version") if isinstance(
                        value, dict) else None
                    if version is not None:
                        break
                except TransportError:
                    pass
            time.sleep(1.0)
        if reg is None or version is None:
            self.blocked(name + "_ready_timeout",
                         log=str(self.temp["service_log"]))
        ok = (reg.get("url", "").endswith(":{}".format(self.port))
              and bool(reg.get("password")) and reg.get("pid")
              and version == DEV_VERSION)
        self.step(name, ok, url_port=self.port, pid=reg.get("pid"),
                  version=version, dev_version=(version != "2.0.28"))
        return reg

    def build_client(self, registration: dict, timeout: float = 60.0) -> Client:
        import base64
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
        self.step("service_killed_port_closed", closed and dead,
                  pid=reg["pid"], port=self.port)
        return reg

    # -- instrumented production pieces（计数即证据：零重发/不自动复活）-------

    @staticmethod
    def make_coordinator(ledger, client, store):
        return Coordinator(ledger, client, store, turn_timeout=240.0,
                           poll_interval=0.5)

    # ------------------------------------------------------------------ run

    def run(self, bun: Path) -> int:
        self.bun = bun
        self.temp = roots = {
            "base": Path(tempfile.mkdtemp(prefix="e07-live-")),
        }
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
        roots["recovery"] = roots["base"] / "e07-recovery.json"
        roots["service_log"] = roots["base"] / "service.log"
        try:
            return self._run_phases(roots)
        finally:
            self._teardown()

    def _teardown(self):
        if self.service is not None and self.service.poll() is None:
            try:
                self.kill_service()
            except Exception:
                subprocess.run(["taskkill", "/F", "/T",
                                "/PID", str(self.service.pid)],
                               capture_output=True, timeout=60)
        if self.temp is not None and not self.keep:
            shutil.rmtree(self.temp["base"], ignore_errors=True)
        elif self.temp is not None:
            print(json.dumps({"kept_temp_root": str(self.temp["base"])},
                             ensure_ascii=False), flush=True)

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

    def _run_phases(self, roots) -> int:
        # ---- 阶段 0：前置与只读快照 ---------------------------------------
        before = self.snapshot_appdata()
        product_config = Path(os.environ["APPDATA"]) / "Juscite" / \
            "config" / "opencode" / "opencode.json"
        if not product_config.exists():
            self.blocked("product_config_missing", path=str(product_config))
        # BYOK provider 配置只读复制进临时根（密钥不出本机、不打印、不入 git）
        opencode_config_dir = roots["config_root"] / "opencode"
        opencode_config_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(product_config, opencode_config_dir / "opencode.json")
        (roots["workspace"] / "materials" /
         "合成材料-E07活服务对账.txt").write_text(SYNTH_MATERIAL, encoding="utf-8")
        self.port = free_port()
        self.step("topology_temp_roots", all(
            str(roots[key]).startswith(str(roots["base"]))
            for key in ("state_root", "data_root", "config_root", "cache_root")),
            base=str(roots["base"]), port=self.port)

        # ---- 阶段 1：活服务拉起＋版本记实值＋显式落点 ----------------------
        reg = self.launch()
        client = self.build_client(reg)
        db_files = list((roots["data_root"] / "opencode").glob("*.db*"))
        self.step("explicit_db_landing", bool(db_files),
                  files=[f.name for f in db_files])

        # harness 目标账（临时 LH 根；桥同径 public_entry --goal-json）
        for path in (str(self.harness_root / "src"),
                     str(self.harness_root / "tools/workflow-tools")):
            if path not in sys.path:
                sys.path.insert(0, path)
        from legal_harness.state.matter_store import MatterStore
        MatterStore(roots["lh_state"]).create_matter(MATTER,
                                                     "cas://profile-e07-live")

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
            "goalId": "g-e07-live", "revision": 1,
            "confirmedScope": "追回合成货款98765.43元及利息（全合成活服务材料）",
            "hardConstraints": [
                {"id": "hc-1", "kind": "min_recovery", "value": "98765.43",
                 "description": "最低实收（合成）"}],
            "preferences": [],
            "unitTiming": {"unit": "CNY", "asOf": "2026-10-15"},
            "sourceDecisionRef": None, "supersedesRevision": None,
        }
        ledger = CountingLedger(BridgeGoalLedger(ledger_config))
        store = RecoveryStore(roots["recovery"])
        counting_client = CountingClient(reg["url"],
                                         headers=client.headers,
                                         timeout=60.0)
        coordinator = self.make_coordinator(ledger, counting_client, store)

        legal_entry.call("harness.save_goal", {
            "actor_id": "e07-live-lawyer", "scope": SCOPE,
            "key": key("live-sg-1"), "goal": goal_payload}, ledger_config)
        legal_entry.call("harness.decide_goal_plan", {
            "actor_id": "e07-live-lawyer", "scope": SCOPE,
            "key": key("live-dp-1"),
            "decision": {"goalId": "g-e07-live", "planId": "plan-live",
                         "planRevision": "1", "decision": "approved"}},
            ledger_config)
        legal_entry.call("harness.adopt_goal_task", {
            "actor_id": "e07-live-lawyer", "scope": SCOPE,
            "key": key("live-at-1"),
            "adoption": {"goalId": "g-e07-live", "taskId": "task-live",
                         "action": "adopt",
                         "basis": {"factRevision": "fact-1",
                                   "lawRevision": "law-1"}}}, ledger_config)
        plan = coordinator.preflight(SCOPE, task_id="task-live")
        self.step("goal_ledger_preflight_ready",
                  plan["decision"] == "READY", decision=plan["decision"])

        # ---- 阶段 2：F-9 守卫先行（fail-closed 在 transport 之前）----------
        dead_port_config = {
            "opencode_registration": str(self._dead_registration(roots)),
            "opencode_timeout": 5,
        }
        conflicting_payload = {
            "id": "ses_e07_live_deadport", "title": "律引 E07（合成）",
            "location": {"directory": str(roots["workspace"])},
            # 规则词汇：action=治理名（shell），resource=操作对象模式（T13 实测形状）
            "permissions": [{"effect": "allow", "action": "shell",
                             "resource": "*"}],
        }
        guard_policies = [{"effect": "deny", "action": "tool.use",
                           "resource": "shell:*"}]
        try:
            create_public_session(conflicting_payload, dead_port_config,
                                  policies=guard_policies)
            self.step("f9_guard_before_transport", False, code="no-reject")
        except SessionRejected as exc:
            self.step("f9_guard_before_transport",
                      "session_allow_conflicts_policy_deny" in str(exc),
                      code=str(exc)[:80])
        except TransportError as exc:
            # 守卫若在 transport 之后才生效，死端口会先炸 transport——即为 FAIL
            self.step("f9_guard_before_transport", False,
                      code="guard_after_transport:" + exc.code)

        # ---- 阶段 3：F-9 守卫径建活会话 ------------------------------------
        session_id = "ses_e07_live_" + str(int(time.time()))
        created = create_public_session({
            "id": session_id, "title": "律引 E07 活服务对账（合成）",
            "location": {"directory": str(roots["workspace"])},
            "model": {"id": MODEL_ID, "providerID": PROVIDER_ID},
        }, {"opencode_registration": str(
                roots["state_root"] / "opencode" / "service-local.json"),
            "opencode_timeout": 60}, policies=guard_policies)
        session_view = client.session(session_id)
        value = session_view.get("data", session_view) if isinstance(
            session_view, dict) else {}
        created_value = created.get("data", created) if isinstance(
            created, dict) else {}
        self.step("live_session_created",
                  created_value.get("id") == session_id
                  and session_id.startswith("ses_")
                  and value.get("title") == "律引 E07 活服务对账（合成）",
                  session_id=session_id)

        # ---- 阶段 4：live 轮次（一次 prompt＋消息回读等完成）---------------
        turn1 = coordinator.advance_turn(SCOPE, session_id, TURN1_PROMPT,
                                         task_id="task-live")
        if turn1["state"] != "COMPLETE":
            self.blocked("model_round_not_complete", state=turn1["state"],
                         assistant_chars=turn1.get("assistantChars"))
        self.step("advance_turn_complete",
                  bool(turn1.get("assistantText")) and
                  (turn1["turn"].get("state") == "COMPLETE"),
                  message_id=turn1["turn"]["messageId"],
                  assistant_chars=turn1["turn"].get("assistantChars"))
        turn1_id = turn1["turn"]["messageId"]

        claim = coordinator.reconcile(session_id, turn1_id)
        self.step("claim_complete_live",
                  claim["claimState"] == "CLAIMED_COMPLETE"
                  and bool(claim.get("assistantText"))
                  and claim["resubmitRequiresNewMessageId"] is False,
                  messageId=turn1_id)

        # ---- 阶段 5：ENQUEUED（resume:false 持久入队不调度）＋409 语义 -----
        parked_id = "msg_e07_live_parked"
        admitted = client.prompt(session_id, {
            "id": parked_id, "text": "（合成）占位入队：不应被执行", "resume": False})
        admitted_value = admitted.get("data", admitted) if isinstance(
            admitted, dict) else {}
        inbox_ids = self._inbox_ids(client, session_id)
        self.step("enqueued_admitted_not_delivered",
                  admitted_value.get("id") == parked_id
                  and parked_id in inbox_ids,
                  inbox_ids=sorted(i for i in inbox_ids if i.startswith("msg_")))
        claim = coordinator.reconcile(session_id, parked_id)
        self.step("claim_enqueued_live",
                  claim["claimState"] == "ENQUEUED", messageId=parked_id)
        # 同 id 重放（同 session 同类型）：幂等返回原入队项，不产生第二条入队、
        # 原文不被改写——这正是 resubmitRequiresNewMessageId=True 的服务端语义
        # （matches() 只比对 session+type，inbox.ts:70-73）。
        replay = client.prompt(session_id, {
            "id": parked_id, "text": "（合成）同 id 异内容重放：不应生效",
            "resume": False})
        replay_value = replay.get("data", replay) if isinstance(
            replay, dict) else {}
        parked_rows = [i for i in self._inbox_items(client, session_id)
                       if i.get("id") == parked_id]
        self.step("same_id_readmission_idempotent",
                  replay_value.get("id") == parked_id
                  and len(parked_rows) == 1
                  and parked_rows[0].get("payload", {}).get("text")
                  == "（合成）占位入队：不应被执行",
                  inbox_rows=len(parked_rows))
        # 409 语义：id 撞上已投递的 assistant 行（非 user/synthetic）→
        # LifecycleConflict → PromptConflictError → HTTP 409（确定失败）。
        history = self._history(client, session_id)
        assistant_id = next((m.get("id") for m in history
                             if m.get("type") == "assistant"), None)
        try:
            client.prompt(session_id, {
                "id": assistant_id, "text": "（合成）撞已投递 assistant 行 id"})
            self.step("id_collision_conflict_409", False, code="no-conflict")
        except TransportError as exc:
            self.step("id_collision_conflict_409",
                      exc.code == "http_409" and exc.uncertain is False,
                      code=exc.code, uncertain=exc.uncertain,
                      collide_with=assistant_id)
        client.request("DELETE", "/api/session/{}/inbox/{}".format(
            session_id, parked_id))
        inbox_ids = self._inbox_ids(client, session_id)
        self.step("enqueued_cancelled", parked_id not in inbox_ids,
                  inbox_count=len(inbox_ids))

        # ---- 阶段 6：CLAIMED_PENDING（投递后、assistant 未完成窗口）--------
        pending_id = self._probe_pending(coordinator, counting_client,
                                         session_id)

        # ---- 阶段 7：NOT_ADMITTED（从未入队：可证不补发同 id）--------------
        never_id = "msg_e07_live_never_sent"
        claim = coordinator.reconcile(session_id, never_id)
        self.step("claim_not_admitted_live",
                  claim["claimState"] == "NOT_ADMITTED"
                  and claim["resubmitRequiresNewMessageId"] is True,
                  messageId=never_id)

        # ---- 阶段 8：uncertain 中断（杀服务）→ 写前记录 SUBMITTING ----------
        killed_reg = self.kill_service()
        crashed_id = None
        try:
            coordinator.advance_turn(SCOPE, session_id,
                                     "（合成）本轮应在传输层失败："
                                     + SYNTH_MATERIAL, task_id="task-live")
            self.step("advance_crash_uncertain", False, code="no-error")
        except TransportError as exc:
            crashed_id = self._last_submitting_id(store)
            self.step("advance_crash_uncertain",
                      exc.code == "transport_failure" and crashed_id,
                      code=exc.code, message_id=crashed_id)
        self.step("writeahead_state_submitting",
                  self._turn_state(store, crashed_id) == "SUBMITTING",
                  message_id=crashed_id)
        self.step("crash_prompt_attempted_once",
                  counting_client.prompt_ids.count(crashed_id) == 1,
                  attempts=counting_client.prompt_ids.count(crashed_id))

        # ---- 阶段 9：停止不自动复活（recover 不重发不复活，UNREACHABLE）----
        before_prompts = list(counting_client.prompt_ids)
        before_resumes = list(ledger.methods)
        outcome = coordinator.recover()
        self.step("recover_unreachable_no_revive",
                  outcome["state"] == "UNREACHABLE"
                  and outcome.get("code") == "transport_failure"
                  and counting_client.prompt_ids == before_prompts
                  and ledger.methods == before_resumes,
                  state=outcome["state"], code=outcome.get("code"),
                  prompts_during=len(counting_client.prompt_ids) -
                  len(before_prompts))

        # ---- 阶段 10：服务完整重启 → 会话持久 → recover 零重发 ------------
        self.service = None
        reg2 = self.launch("service_restart", old_pid=killed_reg["pid"])
        client2 = self.build_client(reg2)
        counting_client2 = CountingClient(reg2["url"],
                                          headers=client2.headers, timeout=60.0)
        coordinator2 = self.make_coordinator(ledger, counting_client2, store)
        session_view = client2.session(session_id)
        value = session_view.get("data", session_view) if isinstance(
            session_view, dict) else {}
        self.step("session_survives_full_restart",
                  value.get("id") == session_id
                  and value.get("title") == "律引 E07 活服务对账（合成）")

        outcome = coordinator2.recover()
        history_ids = self._history_ids(client2, session_id)
        self.step("recover_not_admitted_zero_resend",
                  outcome["state"] == "NOT_ADMITTED"
                  and crashed_id not in history_ids
                  and crashed_id not in self._inbox_ids(client2, session_id)
                  and self._turn_state(store, crashed_id) == "NOT_ADMITTED",
                  message_id=crashed_id,
                  claim=outcome.get("claim", {}).get("claimState"))

        # ---- 阶段 11：恢复后重做=显式新 id，且每 id 恰一次 -----------------
        redo = coordinator2.advance_turn(SCOPE, session_id,
                                         "（合成）恢复后重做轮次：材料同前——"
                                         + SYNTH_MATERIAL +
                                         "请只用一行回答合同总价款。",
                                         task_id="task-live")
        if redo["state"] != "COMPLETE":
            self.blocked("model_round_not_complete", state=redo["state"])
        redo_id = redo["turn"]["messageId"]
        self.step("redo_turn_new_id_completes",
                  redo_id != crashed_id and redo["state"] == "COMPLETE",
                  crashed_id=crashed_id, redo_id=redo_id)

        history_ids = self._history_ids(client2, session_id)
        counts = {mid: history_ids.count(mid) for mid in
                  (turn1_id, pending_id, crashed_id, redo_id, parked_id,
                   never_id)}
        expected = {turn1_id: 1, pending_id: 1, crashed_id: 0, redo_id: 1,
                    parked_id: 0, never_id: 0}
        self.step("zero_resend_history_counts", counts == expected, **{
            "count_" + mid: counts[mid] for mid in sorted(counts)})
        # 尝试侧（POST 次数）与历史侧（入账次数）分开断言：崩溃 id 恰一次尝试、
        # 零次入账；其余每个 id 恰一次尝试恰一次入账。
        attempts = {mid: counting_client.prompt_ids.count(mid)
                    + counting_client2.prompt_ids.count(mid)
                    for mid in (turn1_id, pending_id, crashed_id, redo_id)}
        attempt_expect = {turn1_id: 1, pending_id: 1, crashed_id: 1,
                          redo_id: 1}
        self.step("one_prompt_attempt_per_id",
                  attempts == attempt_expect, **{
                      "attempts_" + mid: attempts[mid]
                      for mid in sorted(attempts)})

        # ---- 阶段 12：暂停不自动复活；显式 resume 是唯一通道（活账）--------
        paused = coordinator2.pause_goal(SCOPE, "g-e07-live", "BUDGET_LIMIT",
                                         "500.00", detail="合成预算触发")
        entry = paused.get("pauseEntry", {})
        account = legal_entry.call("harness.get_goal",
                                   {"scope": SCOPE, "goal_id": "g-e07-live"},
                                   ledger_config)
        banner = pause_banner(account.get("openPause"))
        self.step("live_pause_written",
                  entry.get("state") == "paused"
                  and banner.get("paused") is True
                  and "一键续跑" in banner.get("display", ""),
                  boundary=entry.get("boundary"))
        try:
            coordinator2.advance_turn(SCOPE, session_id,
                                      "（合成）暂停期不应推进", task_id="task-live")
            self.step("paused_blocks_advance", False, code="no-block")
        except CoordinatorBlocked as exc:
            self.step("paused_blocks_advance",
                      exc.code == "preflight_paused"
                      and counting_client2.prompt_ids.count(redo_id) == 1,
                      code=exc.code,
                      prompts_after_pause=len(counting_client2.prompt_ids))
        resumed = coordinator2.user_resume_goal(SCOPE, "g-e07-live")
        self.step("explicit_resume_only_channel",
                  resumed.get("pauseEntry", {}).get("state") == "resumed"
                  and ledger.methods.count("harness.resume_goal") == 1)

        # ---- 阶段 13：版本/持久化/卫生断言 ---------------------------------
        version, dev = coordinator2.service_version()
        self.step("version_recorded_dev_dual_track",
                  version == DEV_VERSION and dev is True, version=version,
                  pin="2.0.28")
        reg_final = json.loads((roots["state_root"] / "opencode" /
                                "service-local.json").read_text(encoding="utf-8"))
        self.step("registration_explicit_state_root",
                  reg_final.get("version") == DEV_VERSION
                  and reg_final.get("pid") == reg2["pid"],
                  path=str(roots["state_root"] / "opencode" /
                           "service-local.json"))
        db_files = sorted(f.name for f in
                          (roots["data_root"] / "opencode").glob("*.db*"))
        self.step("explicit_db_after_activity", bool(db_files), files=db_files)
        state = json.loads(roots["recovery"].read_text(encoding="utf-8"))
        leaked = self._goal_keys_in(state)
        self.step("recovery_store_metadata_only",
                  state.get("schema") == "e07-recovery/1"
                  and state.get("session_ref") == session_id
                  and not leaked, schema=state.get("schema"),
                  goal_content_keys=leaked)
        after = self.snapshot_appdata()
        self.step("appdata_juscite_read_only", after == before,
                  watched=sorted(before))
        return 0

    # -- helpers -------------------------------------------------------------

    def _dead_registration(self, roots) -> Path:
        path = roots["base"] / "dead-registration.json"
        path.write_text(json.dumps(
            {"url": "http://127.0.0.1:1", "password": "synthetic-dead"}),
            encoding="utf-8")
        return path

    @staticmethod
    def _inbox_ids(client, session_id) -> list:
        return [item.get("id") for item in
                Recon._inbox_items(client, session_id)]

    @staticmethod
    def _inbox_items(client, session_id) -> list:
        inbox = client.inbox(session_id)
        return [item for item in
                (inbox.get("data", []) if isinstance(inbox, dict) else [])
                if isinstance(item, dict)]

    @staticmethod
    def _history(client, session_id) -> list:
        """全量消息时间线（order=asc＋cursor 分页，同生产 _fetch_messages 契约）。"""
        messages: list = []
        path = "/api/session/{}/message?order=asc".format(_quote(session_id))
        while path:
            listing = client.request("GET", path)
            if not isinstance(listing, dict):
                return messages
            messages.extend(listing.get("data", []))
            cursor = (listing.get("cursor") or {}).get("next")
            path = "/api/session/{}/message?cursor={}".format(
                _quote(session_id), _quote(str(cursor))) if cursor else None
        return messages

    @classmethod
    def _history_ids(cls, client, session_id) -> list:
        return [m.get("id") for m in cls._history(client, session_id)
                if isinstance(m, dict)]

    def _probe_pending(self, coordinator, client, session_id) -> str:
        """CLAIMED_PENDING 实测：投递后 assistant 未完成的窗口内对账。"""
        for attempt in range(1, 4):
            probe_id = "msg_e07_live_pending_{}".format(attempt)
            client.prompt(session_id, {
                "id": probe_id, "text": PENDING_PROMPT})
            deadline = time.monotonic() + 30.0
            while time.monotonic() < deadline:
                if probe_id in self._history_ids(client, session_id):
                    break
                time.sleep(0.1)
            else:
                continue
            claim = coordinator.reconcile(session_id, probe_id)
            if claim["claimState"] == "CLAIMED_PENDING":
                self.step("claim_pending_live", True, messageId=probe_id,
                          attempt=attempt)
                # 等该轮跑完再进入后续阶段（保持会话空闲态）
                done = time.monotonic() + 240.0
                while time.monotonic() < done:
                    if coordinator._inspect_history(
                            session_id, probe_id)["state"] == "COMPLETE":
                        break
                    time.sleep(0.5)
                else:
                    self.blocked("model_round_not_complete",
                                 probe=probe_id)
                claim = coordinator.reconcile(session_id, probe_id)
                self.step("pending_settles_complete",
                          claim["claimState"] == "CLAIMED_COMPLETE",
                          messageId=probe_id)
                return probe_id
        self.step("claim_pending_live", False, attempts=3,
                  note="window not hit in 3 attempts")
        raise AssertionError("claim_pending_live")

    @staticmethod
    def _turn_state(store, message_id):
        for turn in store.load()["turns"]:
            if turn.get("messageId") == message_id:
                return turn.get("state")
        return None

    @classmethod
    def _last_submitting_id(cls, store):
        for turn in reversed(store.load()["turns"]):
            if turn.get("state") == "SUBMITTING":
                return turn.get("messageId")
        return None

    @staticmethod
    def _goal_keys_in(node) -> list:
        found = []
        if isinstance(node, dict):
            for key, value in node.items():
                if key in GOAL_CONTENT_KEYS:
                    found.append(key)
                found.extend(Recon._goal_keys_in(value))
        elif isinstance(node, list):
            for item in node:
                found.extend(Recon._goal_keys_in(item))
        return found


def _quote(session_id: str) -> str:
    from urllib.parse import quote
    return quote(session_id, safe="")


class CountingClient(Client):
    """生产 Client 的计数包装：prompt 逐 id 计数＝零重发/不盲重试的活证据。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.prompt_ids: list = []

    def prompt(self, sid, request):
        self.prompt_ids.append(request.get("id"))
        return super().prompt(sid, request)


class CountingLedger:
    """目标账代理计数：resume_goal 只允许显式一键续跑那一次。"""

    def __init__(self, inner):
        self.inner = inner
        self.methods: list = []

    def call(self, method, params):
        self.methods.append(method)
        return self.inner.call(method, params)


def verify_branch(root: Path) -> tuple[bool, str]:
    def git(*args):
        return subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                              text=True, encoding="utf-8", timeout=30)
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
    parser.add_argument("--keep", action="store_true",
                        help="保留临时根供取证")
    args = parser.parse_args()
    ok, note = verify_branch(args.harness_root)
    print(json.dumps({"check": "harness_branch", "status":
                      "PASS" if ok else "BLOCKED", "note": note},
                     ensure_ascii=False), flush=True)
    if not ok:
        print(json.dumps({"status": "LIVE_RECON_BLOCKED", "reason": note},
                         ensure_ascii=False))
        return 3
    if not args.oc28.is_dir():
        print(json.dumps({"status": "LIVE_RECON_BLOCKED",
                          "reason": "oc28_missing:" + str(args.oc28)},
                         ensure_ascii=False))
        return 3
    bun = args.bun if args.bun.exists() else Path(
        shutil.which("bun") or "")
    if not bun.exists():
        print(json.dumps({"status": "LIVE_RECON_BLOCKED",
                          "reason": "bun_not_found"}, ensure_ascii=False))
        return 3
    recon = Recon(args.oc28, args.harness_root, args.keep)
    try:
        code = recon.run(bun)
    except AssertionError as exc:
        print(json.dumps({"status": "LIVE_RECON_FAIL", "reason": str(exc),
                          "checks": len(recon.checks)}, ensure_ascii=False))
        return 1
    print(json.dumps({"status": "LIVE_RECON_OK", "checks": len(recon.checks)},
                     ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
