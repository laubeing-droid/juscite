# -*- coding: utf-8 -*-
r"""F34 v2 高级对抗评审编排产品面（工单 W5-U06）。

06 V7-34（B5；owner=product+harness）acceptance：「v2高级对抗编排按需真
会话与异构复核；v1当前必要五角色真实消费另见E05，不一起延期，不固定五
步」。05:87「五身份按能力缺口按需，不每案五人流水线；高级评审F34仍v2，
当前必要角色真实消费必须v1接」。裁决#13-19（00-总协调.md:254）：第二家
模型合成先行——异构复核用合成第二 provider（不同应答形态离线注入），
真实第二家 API 商业化时补。

职责（产品侧；harness 记账面经 legal_entry 的 --advorch-json 封闭信封
消费，账本合同唯一权威＝legal-harness docs/f34-adv-orchestration-
contract.md；会话 transport 经 e07_coordinator.service_client 同一面）：

1. 声明式计划（不固定五步）：步数变量 1..64、seq 连续 1..N；kind 闭集
   produce/attack/review；review 步不带 model（异构性归配置面）；
   attack/review 引用只许指向更早步号。角色闭集唯一权威＝harness
   role_contracts.ROLE_CONTRACT_HASHES（登记时由账本断言；本面镜像闭集
   校验只为省无效往返，漂移以账本具名拒为准）。
2. 按需真会话执行：执行到哪步才建哪步的真实子会话（确定性 ses_f34_ id
   ＝sha256(planId|runId|seq)，同运行内可复现、跨运行互异）；逐步恰一
   次 prompt（调用方持久 msg_f34_ id，不重试）；完成判定沿 F23
   server-owned 已 VERIFIED 语义——轮询持久消息账至 idle 行（outcome=
   succeeded），SSE 挥发不作证据；transcript＝消息账回读行集 canonical
   字节 sha256；模型身份自 assistant 行 model 字段转录（缺即具名拒不
   猜）。
3. 异构复核：review 步模型唯一来自配置 adv_review_model（合成第二
   provider 先行；缺配置 fail-closed f34_review_model_not_configured）；
   产品侧核对回读身份与被复核步互异（f34_review_not_heterogeneous 具名
   拒）——harness 账本级同码断言互不替代。
4. 账本：计划/回执唯一权威在 harness adv_plans/adv_step_records 两账；
   本模块零计划持久化——adv.run 以「账本视图摘要逐字节相等＋逐步
   promptSha256 核对」锚定所执行计划与登记计划同一。

红线：全程合成材料；金额零入场；oc28 只读（serve 拓扑归 recon）；
%APPDATA%\JusBench 零触碰；确定性解析零模型猜。
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from bridge_errors import NotConnected


class AdvOrchestrationError(RuntimeError):
    """Typed f34_* 具名拒/具名缺口（只携工程标识，不携材料/密钥内容）。"""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


ADV_PLAN_SCHEMA = "lvyin-adv-plan/1"
ADV_PLAN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
ADV_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
ADV_KINDS = ("produce", "attack", "review")
ADV_PLAN_MAX_STEPS = 64
ADV_PROMPT_MAX = 8192
# 角色闭集消费面镜像（漂移以 harness 账本 role_contracts 具名拒为准）。
ADV_ROLES_MIRROR = frozenset({
    "case-conductor", "intake-evidence-agent", "legal-research-agent",
    "drafting-agent", "adversarial-review-agent",
})
_ADV_STEP_FIELDS = frozenset({
    "seq", "kind", "role", "model", "prompt", "reviewsStep", "attacksStep",
})
_ADV_MODEL_FIELDS = frozenset({"providerID", "id"})


def _actor(config: dict) -> str:
    return config.get("harness_actor_id") or "lvyin-product"


def _key(request_id: str) -> dict:
    return {"requestId": request_id, "targetId": None,
            "expectedRevision": None, "inputRefs": []}


def _harness(method: str, params: dict, config: dict,
             harness_call=None) -> dict:
    """账本唯一通道（零复制第二权威）。harness_call 注入点：缺省＝
    legal_entry.call → --advorch-json 信封子进程全链；selfhost recon 注
    入封闭注册直连（signed_export 同构）。信封参数＝units 方法签名
    kwargs（snake_case＋actor_id＋key）；账本具名拒（f34_plan_conflict/
    f34_review_model_same/…）typed 透传不吞。"""
    if harness_call is not None:
        record = harness_call(method, params)
        if isinstance(record, dict) and "result" in record:
            return record["result"]
        return record
    from legal_entry import call as _entry_call
    return _entry_call(method, params, config)


def _require_model(value, code: str) -> dict:
    if not isinstance(value, dict) or set(value) != _ADV_MODEL_FIELDS:
        raise AdvOrchestrationError(code)
    if not isinstance(value["providerID"], str) or not value["providerID"]:
        raise AdvOrchestrationError(code)
    if not isinstance(value["id"], str) or not value["id"]:
        raise AdvOrchestrationError(code)
    return {"providerID": value["providerID"], "id": value["id"]}


def plan_view(plan: dict) -> dict:
    """产品面计划闭集校验＋账本视图投影（prompt→promptSha256）。账本级
    结构断言在 harness（唯一权威）；本面校验失败即具名拒，不送无效往返。"""
    if not isinstance(plan, dict) or plan.get("schema") != ADV_PLAN_SCHEMA:
        raise AdvOrchestrationError("f34_plan_schema_unknown")
    plan_id = plan.get("planId")
    if not isinstance(plan_id, str) or not ADV_PLAN_ID_RE.match(plan_id):
        raise AdvOrchestrationError("f34_plan_id_invalid")
    title = plan.get("title")
    if title is not None and (not isinstance(title, str) or len(title) > 256):
        raise AdvOrchestrationError("f34_plan_title_invalid")
    steps = plan.get("steps")
    if not isinstance(steps, list) or not (
            1 <= len(steps) <= ADV_PLAN_MAX_STEPS):
        raise AdvOrchestrationError("f34_steps_invalid")
    view_steps = []
    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict) or set(step) - _ADV_STEP_FIELDS:
            raise AdvOrchestrationError("f34_step_fields_not_closed")
        seq = step.get("seq")
        if not isinstance(seq, int) or isinstance(seq, bool) or seq != index:
            raise AdvOrchestrationError("f34_step_seq_gap")
        kind = step.get("kind")
        if kind not in ADV_KINDS:
            raise AdvOrchestrationError("f34_step_kind_unknown")
        role = step.get("role")
        if role not in ADV_ROLES_MIRROR:
            raise AdvOrchestrationError(f"f34_role_unknown:{role}")
        prompt = step.get("prompt")
        if not isinstance(prompt, str) or not (
                1 <= len(prompt) <= ADV_PROMPT_MAX):
            raise AdvOrchestrationError("f34_prompt_invalid")
        model = step.get("model")
        if model is not None:
            model = _require_model(model, "f34_step_model_invalid")
        reviews = step.get("reviewsStep")
        attacks = step.get("attacksStep")
        if kind == "review":
            # 异构性归配置面：review 步自带 model 结构性不收。
            if model is not None:
                raise AdvOrchestrationError("f34_review_model_not_overridable")
            if not isinstance(reviews, int) or isinstance(reviews, bool) \
                    or reviews < 1 or reviews >= seq:
                raise AdvOrchestrationError("f34_review_ref_invalid")
            if attacks is not None:
                raise AdvOrchestrationError("f34_review_ref_invalid")
        elif kind == "attack":
            if not isinstance(attacks, int) or isinstance(attacks, bool) \
                    or attacks < 1 or attacks >= seq:
                raise AdvOrchestrationError("f34_attack_ref_invalid")
            if reviews is not None:
                raise AdvOrchestrationError("f34_attack_ref_invalid")
        else:
            if reviews is not None or attacks is not None:
                raise AdvOrchestrationError("f34_produce_with_ref")
        view_steps.append({
            "seq": seq, "kind": kind, "role": role,
            "model": model,
            "promptSha256": hashlib.sha256(
                prompt.encode("utf-8")).hexdigest(),
            "reviewsStep": reviews, "attacksStep": attacks,
        })
    view = {"schema": ADV_PLAN_SCHEMA, "planId": plan_id,
            "steps": view_steps}
    if title is not None:
        view["title"] = title
    return view


def _client(config: dict):
    """会话 transport＝e07_coordinator 同一面（注册文件/env 凭据；
    F-9 守门在 create_public_session，本模块走编排专用 create——同一
    client 实例，权限语义由产品 profile 决定）。"""
    from e07_coordinator import service_client
    return service_client(config)


def _workspace(config: dict) -> str:
    workspace = config.get("adv_workspace")
    if not isinstance(workspace, str) or not workspace:
        raise NotConnected("adv_workspace_not_configured")
    path = Path(workspace)
    if not path.is_absolute():
        raise AdvOrchestrationError("f34_workspace_not_absolute")
    if not path.is_dir():
        raise AdvOrchestrationError("f34_workspace_missing")
    return str(path)


def _fetch_history(client, session_id: str) -> list:
    """持久消息账全量（order=asc＋cursor.next 分页链；F23 recon 同契约）。"""
    from urllib.parse import quote
    rows: list = []
    path = "/api/session/{}/message?order=asc".format(quote(session_id, safe=""))
    while path:
        listing = client.request("GET", path)
        if not isinstance(listing, dict):
            break
        data = listing.get("data")
        if isinstance(data, list):
            rows.extend(data)
        cursor = (listing.get("cursor") or {}).get("next")
        path = ("/api/session/{}/message?cursor={}".format(
            quote(session_id, safe=""), quote(str(cursor), safe=""))
            if cursor else None)
    return rows


def _rows_after(rows: list, message_id: str, kind: str) -> list:
    started = False
    out = []
    for row in rows:
        if row.get("id") == message_id:
            started = True
            continue
        if started and row.get("type") == kind:
            out.append(row)
    return out


def _await_idle(client, session_id: str, prompt_id: str,
                timeout_s: float) -> list:
    """F23 server-owned 语义：入队后完成归服务端持有，客户端轮询持久
    消息账至本轮之后出现 idle 行；outcome 必须 succeeded（failed/
    interrupted＝具名缺口，不假完成）。SSE 挥发不作证据。"""
    import time
    deadline = time.monotonic() + timeout_s
    history: list = []
    while time.monotonic() < deadline:
        history = _fetch_history(client, session_id)
        idles = _rows_after(history, prompt_id, "idle")
        if idles:
            outcome = idles[-1].get("outcome")
            if outcome != "succeeded":
                raise AdvOrchestrationError(
                    f"f34_step_not_succeeded:{outcome}")
            return history
        time.sleep(0.5)
    raise AdvOrchestrationError("f34_step_timeout")


def _model_identity(history: list, prompt_id: str) -> dict:
    """模型身份自 assistant 行 model 字段转录（缺即具名拒不猜）。"""
    for row in _rows_after(history, prompt_id, "assistant"):
        model = row.get("model")
        if isinstance(model, dict) and model.get("providerID") \
                and model.get("id"):
            return {"providerID": str(model["providerID"]),
                    "id": str(model["id"])}
    raise AdvOrchestrationError("f34_model_identity_missing")


def _canonical_bytes(payload) -> bytes:
    """canonical JSON 字节（ensure_ascii=False＋sort_keys＋紧凑分隔符；
    仓内 mcp_connector.py:67 同规范）。"""
    return json.dumps(payload, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _transcript_digest(history: list) -> tuple:
    """transcript 摘要＝消息账回读行集 canonical 字节 sha256（正文不入
    账，摘要钉定本次回读事实；与 e05「回读为准绳」同源）。"""
    blob = _canonical_bytes(history)
    return hashlib.sha256(blob).hexdigest(), len(history)


def _run_step(client, config: dict, plan_id: str, run_id: str,
              step: dict, prompt_text: str) -> dict:
    """按需真会话执行单步：到步才建会话→恰一次 prompt→轮询 idle→回读
    为准绳（身份/transcript 摘要）。会话/消息 id 确定性（同运行可复现，
    跨运行互异）；失败全具名，零假回执。"""
    seq = step["seq"]
    if step["kind"] == "review":
        binding = config.get("adv_review_model")
        if not isinstance(binding, dict):
            raise AdvOrchestrationError("f34_review_model_not_configured")
        binding = _require_model(binding, "f34_review_model_not_configured")
    else:
        binding = step.get("model") or config.get("adv_primary_model")
        binding = _require_model(binding, "f34_primary_model_not_configured")
    workspace = _workspace(config)
    tag = hashlib.sha256(
        f"{plan_id}|{run_id}|{seq}".encode("utf-8")).hexdigest()[:24]
    session_id = "ses_f34_" + tag
    prompt_id = "msg_f34_" + tag
    client.create({"id": session_id,
                   "title": f"律引对抗编排 {plan_id} 第{seq}步（合成）",
                   "location": {"directory": workspace},
                   "model": {"providerID": binding["providerID"],
                             "id": binding["id"]}})
    # 恰一次 prompt（不重试）；超时/传输错＝TransportError 语义上抛
    # （OUTCOME_UNKNOWN 保真），业务缺口＝AdvOrchestrationError 具名。
    client.prompt(session_id, {"id": prompt_id, "text": prompt_text})
    timeout = float(config.get("adv_step_timeout", 120))
    history = _await_idle(client, session_id, prompt_id, timeout)
    identity = _model_identity(history, prompt_id)
    transcript_sha, row_count = _transcript_digest(history)
    return {"seq": seq, "kind": step["kind"], "role": step["role"],
            "sessionId": session_id, "promptMessageId": prompt_id,
            "model": identity,
            "transcriptSha256": transcript_sha,
            "messageCount": row_count,
            "reviewedStepSeq": step.get("reviewsStep"),
            "attacksStep": step.get("attacksStep"),
            "createdJustInTime": True}


def adv_run(args: dict, config: dict, harness_call=None) -> dict:
    """adv.run：声明式计划按需真会话逐步执行＋异构复核＋逐步账本回执。
    所执行计划与登记计划同一性锚定：账本视图摘要逐字节相等（视图含逐
    步 promptSha256——指示正文经摘要钉定；本面镜像闭集校验防无效往返，
    漂移以账本具名拒为准；本模块零计划持久化——两账唯一权威在
    harness）。"""
    plan_id = args.get("planId")
    if not isinstance(plan_id, str) or not ADV_PLAN_ID_RE.match(plan_id):
        raise AdvOrchestrationError("f34_plan_id_invalid")
    run_id = args.get("runId")
    if run_id is None:
        import uuid
        run_id = uuid.uuid4().hex[:12]
    if not isinstance(run_id, str) or not ADV_RUN_ID_RE.match(run_id):
        raise AdvOrchestrationError("f34_run_id_invalid")
    plan = args.get("plan")
    view = plan_view(plan)
    if view["planId"] != plan_id:
        raise AdvOrchestrationError("f34_plan_id_mismatch")
    scope = {"kind": "matter", "matterId": args.get("matterId")}
    ledger_plan = _harness("harness.adv_plan_read",
                           {"scope": scope, "plan_id": plan_id},
                           config, harness_call)
    if ledger_plan.get("planSha256") != _digest_view(view):
        raise AdvOrchestrationError("f34_plan_digest_mismatch")
    client = _client(config)
    executed: list = []
    identities: dict = {}
    gaps: list = []
    ledger_receipts: list = []
    for step in view["steps"]:
        seq = step["seq"]
        prompt_text = plan["steps"][seq - 1]["prompt"]
        try:
            record = _run_step(client, config, plan_id, run_id, step,
                               prompt_text)
        except AdvOrchestrationError as exc:
            gaps.append({"seq": seq, "code": str(exc)})
            break
        identities[seq] = record["model"]
        if step["kind"] == "review":
            reviewed_seq = step["reviewsStep"]
            reviewed = identities.get(reviewed_seq)
            if reviewed is not None and reviewed == record["model"]:
                # 产品侧异构断言（账本级同码断言互不替代）。
                gaps.append({"seq": seq,
                             "code": "f34_review_not_heterogeneous"})
                break
        try:
            receipt = _harness(
                "harness.adv_step_record",
                {"actor_id": _actor(config), "scope": scope,
                 "key": _key(f"adv-{plan_id}-{run_id}-{seq}"),
                 "plan_id": plan_id, "run_id": run_id,
                 "seq": seq, "kind": record["kind"],
                 "role": record["role"],
                 "session_id": record["sessionId"],
                 "prompt_message_id": record["promptMessageId"],
                 "model_provider": record["model"]["providerID"],
                 "model_id": record["model"]["id"],
                 "transcript_sha256": record["transcriptSha256"],
                 "message_count": record["messageCount"],
                 "reviewed_step_seq": record["reviewedStepSeq"]},
                config, harness_call)
        except AdvOrchestrationError as exc:
            gaps.append({"seq": seq,
                         "code": "f34_ledger_refused:" + str(exc)})
            break
        ledger_receipts.append({"seq": seq, "changeSeq":
                                receipt.get("changeSeq")})
        executed.append(record)
    return {"planId": plan_id, "runId": run_id,
            "planSha256": _digest_view(view),
            "steps": executed, "gaps": gaps,
            "ledgerReceipts": ledger_receipts,
            "sessionReuse": False,
            "note": "会话逐步按需创建（零常驻/零池化——按需真会话）"}


def _digest_view(view: dict) -> str:
    return hashlib.sha256(_canonical_bytes(view)).hexdigest()


def adv_call(method: str, args: dict, config: dict,
             harness_call=None) -> dict:
    """ADV_ORCH_METHODS 封闭分派（legal_entry 唯一调用点；harness_call
    注入点＝selfhost recon 直连同封闭注册——signed_export 同构）。"""
    scope = {"kind": "matter", "matterId": args.get("matterId")}
    if method == "adv.plan_register":
        view = plan_view(args.get("plan"))
        receipt = _harness("harness.adv_plan_register",
                           {"actor_id": _actor(config), "scope": scope,
                            "key": _key("adv-plan-" + view["planId"]
                                        + "-" + _digest_view(view)[:8]),
                            "plan": view},
                           config, harness_call)
        return {"planId": view["planId"],
                "planSha256": receipt.get("planSha256",
                                          _digest_view(view)),
                "stepsCount": receipt.get("stepsCount",
                                          len(view["steps"])),
                "created": receipt.get("created"),
                "changeSeq": receipt.get("changeSeq"),
                "ledgerReceipt": receipt.get("receipt")}
    if method == "adv.plan_read":
        return _harness("harness.adv_plan_read",
                        {"scope": scope,
                         "plan_id": args.get("planId")},
                        config, harness_call)
    if method == "adv.plan_list":
        return _harness("harness.adv_plan_list",
                        {"scope": scope}, config, harness_call)
    if method == "adv.steps_read":
        params = {"scope": scope, "plan_id": args.get("planId")}
        if args.get("runId") is not None:
            params["run_id"] = args.get("runId")
        return _harness("harness.adv_steps_read", params,
                        config, harness_call)
    if method == "adv.run":
        return adv_run(args, config, harness_call)
    raise NotConnected("method_not_connected:" + method)
