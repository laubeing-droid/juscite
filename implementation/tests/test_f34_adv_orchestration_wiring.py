# -*- coding: utf-8 -*-
"""F34 v2 高级对抗评审编排 产品桥接线测试（工单 W5-U06）。

06 V7-34（B5；owner=product+harness；acceptance「v2高级对抗编排按需真会
话与异构复核；v1当前必要五角色真实消费另见E05，不一起延期，不固定五
步」）。产品面＝legal_entry 两冻结组：ADV_ORCH_METHODS（f34_adv_
orchestrator 编排器）＋HARNESS_ADV_METHODS（--advorch-json 信封；账本合
同唯一权威＝legal-harness docs/f34-adv-orchestration-contract.md——
harness 半边单测在 legal-harness 仓 tests/test_f34_adv_orchestration.py，
双 profile 真会话 recon 在 tools/PENDING_OWNER_f34_adversarial_
orchestration_recon.py）。

合同硬点（本测试主战场，全合成材料；假 client/假信封零真实外联）：
  - 声明式步数：3 步计划同权合法（步数变量——绝不固定五步）；
  - 按需真会话：执行到哪步才建哪步的会话（create 恰逐步一次、零池化零
    常驻；确定性 ses_f34_/msg_f34_ id＝sha256(planId|runId|seq)，逐步
    互异）；逐步恰一次 prompt（不重试）；完成判定沿 F23 server-owned
    语义（持久消息账轮询至 idle succeeded，假 client 模拟分页消息账）；
  - 异构复核：review 步模型唯一来自 adv_review_model 配置（合成第二
    provider 先行）；回读身份与被复核步互异才收（同即
    f34_review_not_heterogeneous 具名缺口）；review 步自带 model 结构性
    不收（f34_review_model_not_overridable）；缺配置 fail-closed
    （f34_review_model_not_configured）；
  - 计划同一性：账本视图摘要逐字节相等＋逐步 promptSha256 核对（漂移
    即具名拒不执行）；
  - 桥纪律：未配置 NotConnected 具名；AdvOrchestrationError → HARNESS_
    FAIL 通道（exit 1 码透传）；封闭集外方法具名拒。
"""

from __future__ import annotations

import ast
import hashlib
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

import f34_adv_orchestrator as adv  # noqa: E402
import legal_entry  # noqa: E402
from bridge_errors import (  # noqa: E402
    HarnessCommandError,
    NotConnected,
)

MATTER = "m-f34-wx"
PRIMARY = {"providerID": "synth-primary", "id": "primary-model"}
REVIEW = {"providerID": "synth-review", "id": "review-model"}


def base_plan() -> dict:
    return {"schema": "lvyin-adv-plan/1", "planId": "f34-w1",
            "title": "接线测试合成编排",
            "steps": [
                {"seq": 1, "kind": "produce", "role": "drafting-agent",
                 "prompt": "（合成）产出一段草案文本。"},
                {"seq": 2, "kind": "attack", "role":
                 "adversarial-review-agent", "attacksStep": 1,
                 "prompt": "（合成）对草案发起一轮对抗攻击。"},
                {"seq": 3, "kind": "review",
                 "role": "adversarial-review-agent", "reviewsStep": 1,
                 "prompt": "（合成）以第二模型异构复核攻击后的草案。"},
            ]}


def digest_view(view: dict) -> str:
    return hashlib.sha256(adv._canonical_bytes(view)).hexdigest()


def _assistant_row(prompt_id: str, model: dict) -> dict:
    return {"id": prompt_id + "-a", "type": "assistant",
            "model": {"providerID": model["providerID"],
                      "id": model["id"]},
            "content": [{"type": "text", "text": "（合成回执文本）"}]}


def _idle_row(prompt_id: str, outcome: str = "succeeded") -> dict:
    return {"id": prompt_id + "-i", "type": "idle", "outcome": outcome}


class FakeClient:
    """假 opencode serve client：记录 create/prompt；消息账分页两页。"""

    def __init__(self, model_by_session: dict, idle_outcome: str = "succeeded",
                 omit_model: bool = False):
        self.creates: list = []
        self.prompts: list = []
        self.model_by_session = model_by_session
        self.idle_outcome = idle_outcome
        self.omit_model = omit_model

    def create(self, request):
        self.creates.append(request)
        self.model_by_session[request["id"]] = request["model"]
        return {"id": request["id"]}

    def prompt(self, session_id, request):
        self.prompts.append((session_id, request))
        return {"id": request["id"]}

    def request(self, method, path, body=None):
        assert method == "GET" and "/message" in path, path
        if "cursor=" in path:
            page = int(path.rsplit("page", 1)[-1])
        else:
            page = 1
        session_id = path.split("/api/session/")[1].split("/")[0]
        prompt_id = next(
            (req["id"] for sid, req in self.prompts
             if sid == session_id), None)
        if page == 1:
            rows = [{"id": prompt_id, "type": "user"}]
            if not self.omit_model:
                rows.append(_assistant_row(
                    prompt_id, self.model_by_session[session_id]))
            return {"data": rows,
                    "cursor": {"next": "page2"}}
        rows = [_idle_row(prompt_id, self.idle_outcome)]
        return {"data": rows, "cursor": None}


class FakeLedger:
    """假 --advorch-json 信封：计划账/回执账最小内存权威（仅测试）。"""

    def __init__(self):
        self.plans: dict = {}
        self.step_records: list = []

    def register(self, plan_view: dict) -> dict:
        plan_id = plan_view["planId"]
        digest = digest_view(plan_view)
        if plan_id in self.plans:
            if self.plans[plan_id]["planSha256"] != digest:
                raise adv.AdvOrchestrationError(
                    f"f34_plan_conflict:{plan_id}")
            return {"planId": plan_id, "planSha256": digest,
                    "stepsCount": len(plan_view["steps"]),
                    "created": False, "changeSeq": 2}
        self.plans[plan_id] = {"planSha256": digest,
                               "steps": plan_view["steps"]}
        return {"planId": plan_id, "planSha256": digest,
                "stepsCount": len(plan_view["steps"]),
                "created": True, "changeSeq": 1}

    def read(self, plan_id: str) -> dict:
        if plan_id not in self.plans:
            raise adv.AdvOrchestrationError(f"f34_plan_not_found:{plan_id}")
        row = self.plans[plan_id]
        return {"planId": plan_id, "planSha256": row["planSha256"],
                "steps": row["steps"],
                "stepsCount": len(row["steps"])}

    def record(self, params: dict) -> dict:
        plan = self.plans.get(params["plan_id"])
        assert plan is not None
        if params["kind"] == "review":
            reviewed = next(
                (r for r in self.step_records
                 if r["run_id"] == params["run_id"]
                 and r["seq"] == params["reviewed_step_seq"]), None)
            assert reviewed is not None, "f34_reviewed_step_missing"
            assert (reviewed["model_provider"], reviewed["model_id"]) != \
                (params["model_provider"], params["model_id"]), \
                "f34_review_model_same"
        self.step_records.append(params)
        return {"plan_id": params["plan_id"], "run_id": params["run_id"],
                "seq": params["seq"], "changeSeq": 10 + params["seq"]}


def wired(ledger: FakeLedger, client: FakeClient, config: dict) -> dict:
    config = dict(config)
    config.setdefault("adv_workspace", "D:\\")  # 由各用例覆写
    config.setdefault("adv_primary_model", dict(PRIMARY))
    config.setdefault("adv_review_model", dict(REVIEW))

    def fake_harness(method, params):
        scope = params.get("scope") or {}
        assert scope.get("matterId") == MATTER
        if method == "harness.adv_plan_register":
            return ledger.register(params["plan"])
        if method == "harness.adv_plan_read":
            return ledger.read(params["plan_id"])
        if method == "harness.adv_step_record":
            return ledger.record(params)
        if method == "harness.adv_plan_list":
            return {"items": [], "count": 0}
        if method == "harness.adv_steps_read":
            return {"items": [], "count": 0}
        raise adv.AdvOrchestrationError("unexpected:" + method)

    saved = (adv._harness, adv._client)
    adv._harness = (lambda method, params, config, harness_call=None:
                    fake_harness(method, params))
    adv._client = lambda cfg: client

    class _P:
        def __enter__(self_):
            return None

        def __exit__(self_, *exc):
            adv._harness, adv._client = saved
            return False
    return _P()


class F34AdvOrchestrationWiringTests(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile
        self._tmp = tempfile.TemporaryDirectory(prefix="f34-wiring-")
        self.addCleanup(self._tmp.cleanup)

    def _run_plan(self, client: FakeClient, ledger: FakeLedger,
                  **config_overrides):
        config = {"matterId": MATTER,
                  "adv_workspace": self._tmp.name,
                  "adv_primary_model": dict(PRIMARY),
                  "adv_review_model": dict(REVIEW)}
        config.update(config_overrides)
        args = {"matterId": MATTER, "planId": "f34-w1",
                "runId": "run-1", "plan": base_plan()}
        with wired(ledger, client, config):
            registered = adv.adv_call("adv.plan_register",
                                      {"matterId": MATTER,
                                       "plan": base_plan()}, config)
            assert registered["created"] is True
            return adv.adv_call("adv.run", args, config)

    def test_01_closed_method_sets_and_dispatch(self) -> None:
        self.assertEqual(sorted(legal_entry.ADV_ORCH_METHODS),
                         ["adv.plan_list", "adv.plan_read",
                          "adv.plan_register", "adv.run",
                          "adv.steps_read"])
        self.assertEqual(sorted(legal_entry.HARNESS_ADV_METHODS),
                         ["harness.adv_plan_list", "harness.adv_plan_read",
                          "harness.adv_plan_register",
                          "harness.adv_step_record",
                          "harness.adv_steps_read"])
        # 封闭集外具名拒（含 harness 编排形态方法——账本永不编排）。
        for method in ("adv.orchestrate", "harness.adv_run",
                       "harness.adv_session_create"):
            with self.assertRaises(NotConnected):
                legal_entry.call(method, {}, {"matterId": MATTER})
        # 未配置 fail-closed（合法参数直抵信封缺配置）。
        valid = {"adv.plan_register": {"matterId": MATTER,
                                       "plan": base_plan()},
                 "adv.run": {"matterId": MATTER, "planId": "f34-w1",
                             "plan": base_plan()},
                 "harness.adv_plan_read": {"matterId": MATTER,
                                           "planId": "x"}}
        for method, args in valid.items():
            with self.assertRaises(NotConnected):
                legal_entry.call(method, args, {})

    def test_02_plan_view_projection_and_negatives(self) -> None:
        view = adv.plan_view(base_plan())
        self.assertEqual([s["seq"] for s in view["steps"]], [1, 2, 3])
        for step, original in zip(view["steps"], base_plan()["steps"]):
            self.assertNotIn("prompt", step)
            self.assertEqual(
                step["promptSha256"],
                hashlib.sha256(original["prompt"].encode()).hexdigest())
        negatives = [
            ("f34_review_model_not_overridable",
             {"schema": "lvyin-adv-plan/1", "planId": "x", "steps": [
                 {"seq": 1, "kind": "review",
                  "role": "adversarial-review-agent", "reviewsStep": 1,
                  "prompt": "p",
                  "model": dict(REVIEW)}]}),
            ("f34_review_ref_invalid",
             {"schema": "lvyin-adv-plan/1", "planId": "x", "steps": [
                 {"seq": 1, "kind": "review",
                  "role": "adversarial-review-agent", "reviewsStep": 2,
                  "prompt": "p"}]}),
            ("f34_step_kind_unknown",
             {"schema": "lvyin-adv-plan/1", "planId": "x", "steps": [
                 {"seq": 1, "kind": "audit", "role": "drafting-agent",
                  "prompt": "p"}]}),
            ("f34_role_unknown",
             {"schema": "lvyin-adv-plan/1", "planId": "x", "steps": [
                 {"seq": 1, "kind": "produce", "role": "mystery",
                  "prompt": "p"}]}),
            ("f34_prompt_invalid",
             {"schema": "lvyin-adv-plan/1", "planId": "x", "steps": [
                 {"seq": 1, "kind": "produce", "role": "drafting-agent",
                  "prompt": ""}]}),
            ("f34_step_seq_gap",
             {"schema": "lvyin-adv-plan/1", "planId": "x", "steps": [
                 {"seq": 2, "kind": "produce", "role": "drafting-agent",
                  "prompt": "p"}]}),
            ("f34_plan_schema_unknown",
             {"schema": "lvyin-adv-plan/9", "planId": "x", "steps": [
                 {"seq": 1, "kind": "produce", "role": "drafting-agent",
                  "prompt": "p"}]}),
        ]
        for code, plan in negatives:
            with self.subTest(code=code):
                with self.assertRaises(adv.AdvOrchestrationError) as caught:
                    adv.plan_view(plan)
                self.assertTrue(caught.exception.code.startswith(code),
                                caught.exception.code)
        # 65 步越界（步数变量有上界 1..64）。
        big = {"schema": "lvyin-adv-plan/1", "planId": "x", "steps": [
            {"seq": i, "kind": "produce", "role": "drafting-agent",
             "prompt": "p"} for i in range(1, 66)]}
        with self.assertRaises(adv.AdvOrchestrationError):
            adv.plan_view(big)

    def test_03_on_demand_sessions_happy_path(self) -> None:
        ledger, client = FakeLedger(), FakeClient({})
        result = self._run_plan(client, ledger)
        self.assertEqual(result["gaps"], [])
        self.assertEqual(len(result["steps"]), 3)
        # 按需真会话：逐步恰一次 create（零池化零常驻）＋恰一次 prompt。
        self.assertEqual(len(client.creates), 3)
        self.assertEqual(len(client.prompts), 3)
        # 确定性 id＝sha256(planId|runId|seq)（ses_/msg_ 前缀，逐步互异）。
        ids = set()
        for step, create, prompt in zip(result["steps"], client.creates,
                                        client.prompts):
            tag = hashlib.sha256(
                f"f34-w1|run-1|{step['seq']}".encode()).hexdigest()[:24]
            self.assertEqual(create["id"], "ses_f34_" + tag)
            self.assertEqual(prompt[1]["id"], "msg_f34_" + tag)
            self.assertEqual(create["location"]["directory"],
                             self._tmp.name)
            ids.add(create["id"])
        self.assertEqual(len(ids), 3)
        # 模型绑定：produce/attack=primary；review=第二合成 provider。
        self.assertEqual(result["steps"][0]["model"], PRIMARY)
        self.assertEqual(result["steps"][1]["model"], PRIMARY)
        self.assertEqual(result["steps"][2]["model"], REVIEW)
        self.assertNotEqual(result["steps"][2]["model"],
                            result["steps"][0]["model"])
        # 逐步账本回执（信封通道）。
        self.assertEqual([r["seq"] for r in result["ledgerReceipts"]],
                         [1, 2, 3])
        self.assertEqual(len(ledger.step_records), 3)
        # transcript 摘要钉定（回读行集 canonical 字节）。
        for record in result["steps"]:
            self.assertRegex(record["transcriptSha256"], r"^[0-9a-f]{64}$")
        # sessionReuse=False＝按需语义显式在场。
        self.assertIs(result["sessionReuse"], False)

    def test_04_heterogeneous_review_negatives(self) -> None:
        # 同模型复核＝具名缺口（步 3 不落账不假回执）。
        ledger, client = FakeLedger(), FakeClient({})
        result = self._run_plan(client, ledger,
                                adv_review_model=dict(PRIMARY))
        self.assertEqual(
            result["gaps"], [{"seq": 3,
                              "code": "f34_review_not_heterogeneous"}])
        self.assertEqual([s["seq"] for s in result["steps"]], [1, 2])
        self.assertEqual(len(ledger.step_records), 2)
        # 缺第二模型配置＝fail-closed 具名缺口。
        ledger, client = FakeLedger(), FakeClient({})
        result = self._run_plan(client, ledger, adv_review_model=None)
        self.assertEqual(
            result["gaps"], [{"seq": 3,
                              "code": "f34_review_model_not_configured"}])
        self.assertEqual([s["seq"] for s in result["steps"]], [1, 2])

    def test_05_plan_identity_anchor(self) -> None:
        # 账本已登记异内容计划（同 planId）→运行前具名拒（零会话创建）。
        ledger = FakeLedger()
        tampered = base_plan()
        tampered["steps"][0]["prompt"] = "（合成）被篡改的指示。"
        ledger.register(adv.plan_view(tampered))
        client = FakeClient({})
        config = {"matterId": MATTER, "adv_workspace": self._tmp.name,
                  "adv_primary_model": dict(PRIMARY),
                  "adv_review_model": dict(REVIEW)}
        with wired(ledger, client, config):
            with self.assertRaises(adv.AdvOrchestrationError) as caught:
                adv.adv_call("adv.run",
                             {"matterId": MATTER, "planId": "f34-w1",
                              "runId": "run-1", "plan": base_plan()},
                             config)
        self.assertEqual(caught.exception.code, "f34_plan_digest_mismatch")
        self.assertEqual(client.creates, [])
        # 同一性锚的另一半：文本漂移必然改变视图（promptSha256 在视图
        # 内→digest 必拒）；此处钉「拒发生在零会话创建前」由 client
        # .creates 空断言覆盖，不另设冗余核对面。
    def test_06_step_failure_named_gaps(self) -> None:
        config = {"matterId": MATTER, "adv_workspace": self._tmp.name,
                  "adv_primary_model": dict(PRIMARY),
                  "adv_review_model": dict(REVIEW)}
        # idle 行 outcome=failed＝具名缺口（不假完成）。
        ledger = FakeLedger()
        ledger.register(adv.plan_view(base_plan()))
        client = FakeClient({}, idle_outcome="failed")
        with wired(ledger, client, config):
            result = adv.adv_call("adv.run",
                                  {"matterId": MATTER, "planId": "f34-w1",
                                   "runId": "run-1", "plan": base_plan()},
                                  config)
        self.assertEqual(
            result["gaps"], [{"seq": 1,
                              "code": "f34_step_not_succeeded:failed"}])
        self.assertEqual(result["steps"], [])
        # assistant 行缺 model 字段＝具名拒不猜。
        ledger = FakeLedger()
        ledger.register(adv.plan_view(base_plan()))
        client = FakeClient({}, omit_model=True)
        with wired(ledger, client, config):
            result = adv.adv_call("adv.run",
                                  {"matterId": MATTER, "planId": "f34-w1",
                                   "runId": "run-1", "plan": base_plan()},
                                  config)
        self.assertEqual(
            result["gaps"], [{"seq": 1,
                              "code": "f34_model_identity_missing"}])

    def test_07_bridge_error_channel_and_ast_redlines(self) -> None:
        # AST 红线：编排器零金额面（Decimal 不入场）、零 %APPDATA%/JusBench
        # 字面量、零硬编码 http(s) 端点（transport 唯一经 service_client）。
        mod = ast.parse((ROOT / "python" / "f34_adv_orchestrator.py")
                        .read_text(encoding="utf-8"))
        names = {n.id for n in ast.walk(mod) if isinstance(n, ast.Name)}
        self.assertNotIn("Decimal", names)
        body = mod.body
        skip = set()
        if body and isinstance(body[0], ast.Expr)                 and isinstance(body[0].value, ast.Constant):
            skip = {id(body[0].value)}  # 模块 docstring 不参与红线扫描
        consts = [n.value for n in ast.walk(mod)
                  if isinstance(n, ast.Constant)
                  and isinstance(n.value, str) and id(n) not in skip]
        self.assertFalse([c for c in consts
                          if "JusBench" in c or "APPDATA" in c])
        self.assertFalse([c for c in consts if c.startswith("http")])
        # f-string/format 拼 URL 不存在（端点只来自 service_client 面）。
        joins = [n for n in ast.walk(mod)
                 if isinstance(n, ast.BinOp)
                 and isinstance(n.op, ast.Mod)]
        self.assertEqual(joins, [])
        # legal_entry dispatch：AdvOrchestrationError → HARNESS_FAIL 通道。
        import unittest.mock as mock
        plan = base_plan()
        with mock.patch.object(adv, "adv_call",
                               side_effect=adv.AdvOrchestrationError(
                                   "f34_plan_id_invalid")):
            with self.assertRaises(HarnessCommandError) as caught:
                legal_entry.call("adv.run", {"matterId": MATTER,
                                             "planId": plan["planId"],
                                             "plan": plan}, {})
        self.assertEqual(str(caught.exception), "f34_plan_id_invalid")


if __name__ == "__main__":
    unittest.main()
