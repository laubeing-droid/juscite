"""E07 product-side coordinator reconciliation against the live harness entry.

对账对象：harness 分支 v8-e05-opencode-target（tip 1de352e5——E08 双库已并入，
master 929d0802 零动）的 public_entry --goal-json 封闭径 —— 与产品桥（legal_entry → 子进程
public_entry）完全同一条链。全部合成材料：临时状态根、合成 matter/goal/actor
字符串；harness 检出零字节改动（只运行其代码，git 只读命令核对分支）。

用法：
  python -X utf8 tools/e07_goal_ledger_recon.py [--harness-root <path>]

退出码：0 = RECON_OK；1 = RECON_FAIL；3 = RECON_BLOCKED（根缺失/分支不对）。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "python"))

import legal_entry  # noqa: E402
from e07_coordinator import (  # noqa: E402
    BridgeGoalLedger, Coordinator, CoordinatorBlocked, pause_banner,
)
from legal_entry import HarnessCommandError, NotConnected  # noqa: E402

DEFAULT_HARNESS_ROOT = Path(
    r"D:\Codex\1.法律工作区\legal-harness工作区\legal-harness-repo")
EXPECT_BRANCH = "v8-e05-opencode-target"
EXPECT_HEAD = "1de352e5"

SCOPE = {"kind": "matter", "matterId": "m-e07-recon"}
MATTER = "m-e07-recon"


class BoomClient:
    """Any prompt attempt on a paused/stale goal is a reconciliation failure."""

    def prompt(self, *args, **kwargs):
        raise AssertionError("coordinator prompted while preflight must refuse")


def key(request_id, target=None, expected=None):
    return {"requestId": request_id, "targetId": target,
            "expectedRevision": expected, "inputRefs": []}


def goal_payload(revision=1, supersedes=None, **overrides):
    payload = {
        "schemaVersion": "1.0.0-draft", "matterId": MATTER, "goalId": "g-recon",
        "revision": revision,
        "confirmedScope": "追回合成货款85000元及利息（全合成对账材料）",
        "hardConstraints": [
            {"id": "hc-1", "kind": "min_recovery", "value": "85000",
             "description": "最低实收（合成）"},
            {"id": "hc-2", "kind": "no_installment", "value": "true"},
        ],
        "preferences": [
            {"id": "pf-1", "kind": "relationship", "description": "保留供货关系（合成）"},
        ],
        "unitTiming": {"unit": "CNY", "asOf": "2026-10-15"},
        "sourceDecisionRef": None,
        "supersedesRevision": supersedes,
    }
    payload.update(overrides)
    return payload


class Recon:
    def __init__(self, harness_root: Path):
        self.harness_root = harness_root
        self.checks = []

    def step(self, name, ok, **facts):
        entry = {"check": name, "status": "PASS" if ok else "FAIL", **facts}
        self.checks.append(entry)
        print(json.dumps(entry, ensure_ascii=False), flush=True)
        if not ok:
            raise AssertionError(name)

    def expect_error(self, name, call, code_part):
        try:
            call()
        except HarnessCommandError as exc:
            self.step(name, code_part in str(exc), code=str(exc))
            return
        raise AssertionError(name + ": no typed error raised")

    def run(self) -> int:
        temporary = tempfile.TemporaryDirectory()
        state_root = Path(temporary.name) / "state"
        state_root.mkdir(parents=True)
        registration = Path(temporary.name) / "service-local.json"
        registration.write_text(json.dumps(
            {"url": "http://127.0.0.1:1", "password": "synthetic-recon"}),
            encoding="utf-8")
        # Seed the synthetic matter exactly like harness tests/test_e07_goal_ledger.py
        # (MatterStore.create_matter); harness repo bytes stay untouched.
        for path in (str(self.harness_root / "src"),
                     str(self.harness_root / "tools/workflow-tools")):
            sys.path.insert(0, path)
        from legal_harness.state.matter_store import MatterStore
        MatterStore(state_root).create_matter(MATTER, "cas://profile-recon-synth")

        config = {
            "harness_public_entry":
                str(self.harness_root / "tools/workflow-tools/harness/public_entry.py"),
            "harness_target": "opencode",
            "harness_state_root": str(state_root),
            "harness_service_registration": str(registration),
            "harness_timeout": 90,
        }
        ledger = BridgeGoalLedger(config)
        coordinator = Coordinator(ledger, BoomClient(),
                                  type("S", (), {"load": lambda self: {
                                      "turns": [], "session_ref": None},
                                      "record_turn": lambda self, t: None,
                                      "command_id": lambda self, p: "recon-" + p,
                                      "unresolved_turn": lambda self: None})())

        # --- 生命周期：save → get → decide → adopt → basis CURRENT ----------
        saved = legal_entry.call("harness.save_goal", {
            "actor_id": "recon-lawyer", "scope": SCOPE, "key": key("recon-sg-1"),
            "goal": goal_payload()}, config)
        self.step("save_goal_v1", saved.get("revision") == 1
                  and saved.get("status") == "active", revision=saved.get("revision"))

        account = legal_entry.call("harness.get_goal",
                                   {"scope": SCOPE, "goal_id": "g-recon"}, config)
        self.step("get_goal_active_no_pause",
                  account.get("status") == "active"
                  and account.get("openPause") is None)

        decision = legal_entry.call("harness.decide_goal_plan", {
            "actor_id": "recon-lawyer", "scope": SCOPE, "key": key("recon-dp-1"),
            "decision": {"goalId": "g-recon", "planId": "plan-recon",
                         "planRevision": "1", "decision": "approved"}}, config)
        self.step("decide_goal_plan_approved", bool(decision.get("receiptRef")))

        adoption = legal_entry.call("harness.adopt_goal_task", {
            "actor_id": "recon-lawyer", "scope": SCOPE, "key": key("recon-at-1"),
            "adoption": {"goalId": "g-recon", "taskId": "task-recon", "action": "adopt",
                         "basis": {"factRevision": "fact-1", "lawRevision": "law-1"}}},
            config)
        self.step("adopt_goal_task_pins_basis",
                  adoption.get("goalBasis", {}).get("goalRevision") == "1")

        basis = legal_entry.call("harness.read_goal_basis", {
            "scope": SCOPE,
            "query": {"goalId": "g-recon", "taskId": "task-recon"}}, config)
        self.step("read_goal_basis_current",
                  basis.get("status") == "CURRENT")

        plan = coordinator.preflight(SCOPE, task_id="task-recon")
        self.step("preflight_ready", plan["decision"] == "READY")

        # --- 机械边界暂停：闭集 + triggerValue + 可回读 + UI 数据源 ---------
        paused = coordinator.pause_goal(SCOPE, "g-recon", "BUDGET_LIMIT", "500.00",
                                        detail="合成预算触发")
        entry = paused.get("pauseEntry", {})
        self.step("pause_goal_written", entry.get("state") == "paused"
                  and entry.get("boundary") == "BUDGET_LIMIT"
                  and entry.get("triggerValue") == "500.00")

        account = legal_entry.call("harness.get_goal",
                                   {"scope": SCOPE, "goal_id": "g-recon"}, config)
        banner = pause_banner(account.get("openPause"))
        self.step("open_pause_banner_renders",
                  banner.get("paused") is True
                  and "已暂停" in banner.get("display", "")
                  and "一键续跑" in banner.get("display", "")
                  and banner["resume"]["method"] == "harness.resume_goal")

        plan = coordinator.preflight(SCOPE, task_id="task-recon")
        self.step("preflight_paused_no_advance", plan["decision"] == "PAUSED")
        try:
            coordinator.advance_turn(SCOPE, "ses_recon", "合成推进")
            ok, code = False, "no-block"
        except CoordinatorBlocked as exc:
            ok, code = exc.code == "preflight_paused", exc.code
        self.step("advance_refused_while_paused", ok, code=code)

        pauses = legal_entry.call("harness.list_goal_pauses",
                                  {"scope": SCOPE, "goal_id": "g-recon"}, config)
        self.step("list_goal_pauses_readable",
                  len(pauses.get("items", [])) == 1
                  and pauses.get("openPause", {}).get("boundary") == "BUDGET_LIMIT")

        self.expect_error("double_pause_refused", lambda: coordinator.pause_goal(
            SCOPE, "g-recon", "TIME_LIMIT", "3600"), "goal_already_paused")
        self.expect_error("boundary_closed_set", lambda: legal_entry.call(
            "harness.pause_goal", {
                "actor_id": "recon-lawyer", "scope": SCOPE,
                "key": key("recon-bad-b"),
                "pause": {"goalId": "g-recon", "boundary": "SHELL_ESCAPE",
                          "triggerValue": "x"}}, config),
            "goal_pause_boundary_invalid")

        # --- 显式续跑：唯一通道；重复 resume 不复活 --------------------------
        resumed = coordinator.user_resume_goal(SCOPE, "g-recon", pause_idx=1)
        self.step("resume_explicit",
                  resumed.get("pauseEntry", {}).get("state") == "resumed")
        replay = coordinator.user_resume_goal(SCOPE, "g-recon", pause_idx=1)
        self.step("resume_same_request_replays",
                  replay.get("pauseEntry", {}).get("state") == "resumed")
        self.expect_error("resume_new_request_refused", lambda: legal_entry.call(
            "harness.resume_goal", {
                "actor_id": "recon-lawyer", "scope": SCOPE,
                "key": key("recon-rm-2"), "resume": {"goalId": "g-recon"}}, config),
            "goal_not_paused")

        # --- 范围变更 → goal-only 变更使已采用 basis STALE（交回人）---------
        revised = legal_entry.call("harness.save_goal", {
            "actor_id": "recon-lawyer", "scope": SCOPE,
            "key": key("recon-sg-2", "g-recon", 1),
            "goal": goal_payload(revision=2, supersedes=1,
                                 confirmedScope="追回合成货款及违约金")}, config)
        self.step("save_goal_v2_scope_change", revised.get("revision") == 2)

        basis = legal_entry.call("harness.read_goal_basis", {
            "scope": SCOPE,
            "query": {"goalId": "g-recon", "taskId": "task-recon"}}, config)
        self.step("goal_only_change_makes_basis_stale",
                  basis.get("status") == "STALE_REQUIRES_REVIEW")
        plan = coordinator.preflight(SCOPE, task_id="task-recon")
        self.step("stale_returns_to_human",
                  plan["decision"] == "STALE_RETURN_TO_HUMAN")

        # --- 撤销：穿越暂停拒绝 → 恢复后撤销 → 终态 ------------------------
        coordinator.pause_goal(SCOPE, "g-recon", "NO_PROGRESS", "rounds=3")
        self.expect_error("revoke_through_pause_refused", lambda: legal_entry.call(
            "harness.revoke_goal", {
                "actor_id": "recon-lawyer", "scope": SCOPE,
                "key": key("recon-rv-1"), "goal_id": "g-recon"}, config),
            "goal_pause_open")
        coordinator.user_resume_goal(SCOPE, "g-recon")
        revoked = legal_entry.call("harness.revoke_goal", {
            "actor_id": "recon-lawyer", "scope": SCOPE,
            "key": key("recon-rv-2"), "goal_id": "g-recon"}, config)
        self.step("revoke_after_resume", bool(revoked.get("receiptRef")))
        account = legal_entry.call("harness.get_goal",
                                   {"scope": SCOPE, "goal_id": "g-recon"}, config)
        self.step("revoked_is_terminal",
                  account.get("status") == "revoked")
        plan = coordinator.preflight(SCOPE)
        self.step("preflight_revoked_blocks", plan["decision"] == "REVOKED")

        listing = legal_entry.call("harness.list_goals", {"scope": SCOPE}, config)
        self.step("list_goals_reads_chain",
                  listing.get("items", [{}])[0].get("status") == "revoked")

        # --- 桥 fail-closed：白名单外 harness 方法不接 ----------------------
        try:
            legal_entry.call("harness.save_fact", {"scope": SCOPE}, config)
            ok, code = False, "connected"
        except NotConnected as exc:
            ok, code = "method_not_connected" in str(exc), str(exc)
        self.step("bridge_whitelist_fail_closed", ok, code=code)

        # --- 同径 parity：桥结果 == 直接 public_entry 结果 -------------------
        bridge_view = legal_entry.call("harness.get_goal",
                                       {"scope": SCOPE, "goal_id": "g-recon"}, config)
        direct = self.direct_entry(config, "harness.get_goal",
                                   {"scope": SCOPE, "goal_id": "g-recon"})
        self.step("bridge_direct_same_closed_path",
                  bridge_view == direct.get("result"),
                  bridgeGoalRef=bridge_view.get("goalRef", {}).get("digest", "")[:12])
        return 0

    def direct_entry(self, config, method, params):
        """Independent public_entry invocation (no bridge) for path parity."""
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json",
                                         delete=False) as handle:
            json.dump({"method": method, "params": params}, handle, ensure_ascii=False)
            path = handle.name
        argv = [sys.executable, "-X", "utf8", config["harness_public_entry"],
                "--goal-json", path, "--target", "opencode"]
        env = {k: v for k, v in os.environ.items()}
        env["LH_LEGAL_STATE_ROOT"] = config["harness_state_root"]
        env["LH_OPENCODE_SERVICE_REGISTRATION"] = config["harness_service_registration"]
        try:
            proc = subprocess.run(argv, capture_output=True, text=True,
                                  encoding="utf-8", env=env, timeout=90)
            return json.loads(proc.stdout)
        finally:
            os.unlink(path)


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
    parser.add_argument("--harness-root", type=Path, default=DEFAULT_HARNESS_ROOT)
    args = parser.parse_args()
    ok, note = verify_branch(args.harness_root)
    print(json.dumps({"check": "harness_branch", "status":
                      "PASS" if ok else "BLOCKED", "note": note},
                     ensure_ascii=False), flush=True)
    if not ok:
        print(json.dumps({"status": "RECON_BLOCKED", "reason": note},
                         ensure_ascii=False))
        return 3
    recon = Recon(args.harness_root)
    try:
        recon.run()
    except AssertionError as exc:
        print(json.dumps({"status": "RECON_FAIL", "reason": str(exc),
                          "checks": len(recon.checks)}, ensure_ascii=False))
        return 1
    print(json.dumps({"status": "RECON_OK", "checks": len(recon.checks)},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
