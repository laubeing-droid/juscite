# -*- coding: utf-8 -*-
"""F31 MCP 连接器＋四档暴露策略产品面（工单 W4-U33）。

06 F31 assertion：MCP 四暴露策略真实约束发现/调用；凭据隔离，远端响应
不得扩权。owner=product（UI_HOST_OR_NEW_PRODUCT：在既有 owner 公开面落
地，不复制第二权威；不创第二 Agent loop）。

四档语义（源=03 功能分母引 XTLaw v25 tool_exposure：deferred/direct/
codemode/hidden；档位划分保持原样，编译落点按 oc28 v2.0.28 原生面）：
  direct    server codemode:false，工具以独立定义进模型请求发现面，按名
            直调（权限闸照走）。
  codemode  server codemode:true（原生默认），工具不出独立定义，经 Code
            Mode 目录发现、仅经 execute 包装调用；execute:* 被禁的
            profile（法律 profile 全禁在案，E02/T05）下调用面关闭并具名。
  deferred  server disabled:true，默认不连接→零工具→发现/调用双面无；
            按需激活走原生 connect 通道（PUT connect「overriding a
            disabled configuration until restart」），激活后按其配置形状
            （codemode:true→execute 包装）生效。
  hidden    结构性缺位（编译产物 servers 无该 server）＋ integration.use
            mcp:<name> veto（注册表摘除）＋ tool.use veto（运行期调用
            强制 deny）＋ 权限尾置 deny（whollyDisabled 双面不可见）。

凭据隔离：登记与编译产物只持 ref；明文只在 materialize 显式解析时写入
目标服务配置文件（原生凭据通道：local=environment / remote=headers），
本面任何回执/日志/错误码不含凭据值。远端响应不扩权：response_guard 把
响应载荷恒判为数据面（无信任开关通道），权限规则集唯一来源=本地
config/agent/session，指纹由调用方与活服务实测比对。

确定性纪律：compile/materialize/invoke_policy/guard 全部纯函数——无时
钟、无随机、无网络；同输入两跑字节级同输出。错误全部 typed（McpFaceError
的 str 只有 mcp_* 码）；凭据值与材料内容永不进入错误码。
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

REGISTRY_SCHEMA = "lvyin-mcp-connector/1"
PLAN_SCHEMA = "lvyin-mcp-exposure/1"

# legal_entry 冻结方法组（组外方法绝不落到本面）。
MCP_CONNECTOR_METHODS = frozenset({
    "mcp.register",
    "mcp.compile",
    "mcp.materialize",
    "mcp.response_guard",
    "mcp.invoke_policy",
})

EXPOSURE_TIERS = ("direct", "deferred", "codemode", "hidden")
_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_REF_RE = re.compile(r"^.{1,256}$")
_CRED_KEY = "$f31_credential_ref"


class McpFaceError(ValueError):
    """Typed face failure; str() is an mcp_* code only."""

    def __init__(self, code: str):
        super().__init__(code)


def _canonical(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _fingerprint(obj) -> str:
    return hashlib.sha256(_canonical(obj)).hexdigest()


def _fail(code: str) -> None:
    raise McpFaceError(code)


# ---------------------------------------------------------------------- #
# 登记台账（mcp_state_root 持久化；只存 ref，绝不存凭据值）
# ---------------------------------------------------------------------- #

def registry_path(state_root) -> Path:
    return Path(state_root) / "mcp-connectors" / "registry.json"


def register(state_root, registry: dict) -> dict:
    """登记台账落盘（幂等：同内容重写同字节）。返回回执不含任何凭据值。"""
    _validate_registry(registry)
    path = registry_path(state_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(registry, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    existing = None
    if path.exists():
        try:
            existing = path.read_text(encoding="utf-8")
        except OSError:
            existing = None
    if existing != payload:
        path.write_text(payload, encoding="utf-8", newline="\n")
    return {
        "schema": REGISTRY_SCHEMA,
        "path": str(path),
        "sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        "connectors": [c["name"] for c in registry.get("connectors", [])],
    }


def load_registry(state_root) -> dict:
    path = registry_path(state_root)
    try:
        registry = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        _fail("mcp_registry_unreadable")
    _validate_registry(registry)
    return registry


# ---------------------------------------------------------------------- #
# 四档真值表（单一权威：compile 的 exposure_matrix 由它逐档生成）
# ---------------------------------------------------------------------- #

def invoke_policy(tier: str, *, execute_enabled: bool) -> dict:
    """单档双面期望（发现面/调用面）。确定性纯函数。"""
    if tier not in EXPOSURE_TIERS:
        _fail("mcp_tier_unknown:" + tier)
    if tier == "direct":
        return {
            "tier": "direct",
            "discovery": {"direct_definition": True, "codemode_catalog": False,
                          "note": "独立定义随模型请求 tools 下发"},
            "call": {"by_name": "permitted", "via": "native_direct",
                     "requires": [], "note": "按名直调，权限闸照走"},
            "activation": "immediate",
        }
    if tier == "deferred":
        return {
            "tier": "deferred",
            "discovery": {"direct_definition": False, "codemode_catalog": False,
                          "note": "默认 disabled 不连接→零工具→不进发现面"},
            "call": {"by_name": "refused_no_tool_named",
                     "via": "none_until_on_demand_connect",
                     "requires": [],
                     "note": "按需激活双通道：①原生 connect API 激活原生 MCP 层"
                             "（disabled 覆盖 until restart；oc28 v2.0.28 实测边界="
                             "模型面工具清单不拾取晚连接工具，重试/重连/多轮均不进）；"
                             "②编译翻档＋服务重启消费＝模型面生效通道，激活后按其"
                             "配置形状（codemode:true→execute 包装）生效"},
            "activation": "on_demand_native_connect_plus_recompile_restart",
        }
    if tier == "codemode":
        if execute_enabled:
            call = {"by_name": "refused_no_tool_named", "via": "codemode_execute_wrapper",
                    "requires": ["execute_enabled"],
                    "note": "仅经 Code Mode execute 包装调用"}
        else:
            call = {"by_name": "closed_by_execute_wholly_disabled",
                    "via": "none", "requires": ["execute_enabled"],
                    "note": "execute:* 全禁（法律 profile 在案）→CodeMode 整体"
                            "不下发，codemode 档调用面关闭"}
        return {
            "tier": "codemode",
            "discovery": {"direct_definition": False, "codemode_catalog": True,
                          "note": "不出独立定义，仅 Code Mode 目录"},
            "call": call,
            "activation": "immediate",
        }
    return {
        "tier": "hidden",
        "discovery": {"direct_definition": False, "codemode_catalog": False,
                      "note": "结构性缺位＋veto 摘除＋权限尾置 deny→双面不可见"},
        "call": {"by_name": "closed_by_veto_and_deny", "via": "none",
                 "requires": [],
                 "note": "tool.use veto 强制 deny＋权限尾置 deny（whollyDisabled）"},
        "activation": "never",
    }


# ---------------------------------------------------------------------- #
# 编译器：登记 → oc28 v2.0.28 原生面工件（plan 不含凭据明文）
# ---------------------------------------------------------------------- #

def _validate_registry(registry: dict) -> None:
    if not isinstance(registry, dict) or registry.get("schema") != REGISTRY_SCHEMA:
        _fail("mcp_registry_schema_invalid")
    connectors = registry.get("connectors")
    if not isinstance(connectors, list) or not connectors:
        _fail("mcp_registry_empty")
    seen = set()
    for conn in connectors:
        if not isinstance(conn, dict):
            _fail("mcp_connector_shape_invalid")
        name = conn.get("name")
        if not isinstance(name, str) or not _NAME_RE.match(name):
            _fail("mcp_connector_name_invalid")
        if name in seen:
            _fail("mcp_connector_name_duplicate:" + name)
        seen.add(name)
        tier = conn.get("tier")
        if tier not in EXPOSURE_TIERS:
            _fail("mcp_tier_unknown:" + str(tier))
        transport = conn.get("transport")
        if transport not in ("local", "remote"):
            _fail("mcp_transport_invalid")
        if transport == "local":
            command = conn.get("command")
            if not isinstance(command, list) or not command or \
                    not all(isinstance(part, str) and part for part in command):
                _fail("mcp_local_command_invalid")
        else:
            url = conn.get("url")
            if not isinstance(url, str) or not url.startswith(("http://", "https://")):
                _fail("mcp_remote_url_invalid")
        cred = conn.get("credential")
        if cred is not None:
            if not isinstance(cred, dict):
                _fail("mcp_credential_shape_invalid")
            ref = cred.get("ref")
            if not isinstance(ref, str) or not _REF_RE.match(ref):
                _fail("mcp_credential_ref_invalid")
            channel = cred.get("env") if transport == "local" else cred.get("header")
            if not isinstance(channel, str) or not _NAME_RE.match(channel):
                _fail("mcp_credential_channel_invalid")


def _server_config(conn: dict) -> dict:
    """单连接器 → 原生 ServerConfig 形（凭据以 ref 占位，明文由 materialize 解析）。"""
    config: dict = {}
    if conn["transport"] == "local":
        config["type"] = "local"
        config["command"] = list(conn["command"])
        if isinstance(conn.get("cwd"), str) and conn["cwd"]:
            config["cwd"] = conn["cwd"]
    else:
        config["type"] = "remote"
        config["url"] = conn["url"]
    cred = conn.get("credential")
    if cred:
        if conn["transport"] == "local":
            config["environment"] = {cred["env"]: {_CRED_KEY: cred["ref"]}}
        else:
            config["headers"] = {cred["header"]: {_CRED_KEY: cred["ref"]}}
    tier = conn["tier"]
    # hidden 不进 servers（结构性缺位，由调用方保证不落到这里）。
    if tier == "direct":
        config["codemode"] = False
    else:
        # codemode/deferred 都按 codemode 形状登记（deferred 激活后即此形状）。
        config["codemode"] = True
    if tier == "deferred":
        config["disabled"] = True
    return config


def compile_connectors(registry: dict) -> dict:
    """登记 → 编译产物 plan。纯函数；同输入两跑逐字节同（canonical sha 相等）。"""
    _validate_registry(registry)
    servers: dict = {}
    permissions: list = []
    policies: list = []
    matrix: list = []
    on_demand: dict = {}
    credential_refs: dict = {}
    unexposed: list = []
    for conn in registry["connectors"]:
        name, tier = conn["name"], conn["tier"]
        if tier == "hidden":
            unexposed.append({"name": name, "tier": tier,
                              "reason": "structural_absence_plus_veto_plus_deny"})
            permissions.append({"action": name + "_*", "resource": "*", "effect": "deny"})
            policies.append({"action": "integration.use", "resource": "mcp:" + name,
                             "effect": "deny"})
            policies.append({"action": "tool.use", "resource": name + "_*:*",
                             "effect": "deny"})
        else:
            servers[name] = _server_config(conn)
        if conn.get("credential"):
            cred = conn["credential"]
            credential_refs[name] = {
                "ref": cred["ref"],
                "channel": "environment" if conn["transport"] == "local" else "headers",
                "key": cred.get("env") or cred.get("header"),
            }
        matrix.append({**invoke_policy(tier, execute_enabled=True), "name": name})
        if tier == "deferred":
            on_demand[name] = {
                "channel": "native_connect_api_plus_recompile_restart",
                "endpoint": "/api/experimental/mcp/" + name + "/connect",
                "persist_until": "restart",
                "note": "原生 connect 激活原生 MCP 层（模型面拾取边界见 invoke_policy"
                        "注记）；模型面生效=编译翻档＋服务重启消费",
            }
    return {
        "schema": PLAN_SCHEMA,
        "compiled_from_sha256": _fingerprint(registry),
        "servers": servers,
        "permissions": permissions,
        "policies": policies,
        "exposure_matrix": matrix,
        "deferred_on_demand": on_demand,
        "credential_refs": credential_refs,
        "unexposed": unexposed,
    }


# ---------------------------------------------------------------------- #
# 物化：plan + secrets → 服务全局配置文件（凭据明文唯一落点）
# ---------------------------------------------------------------------- #

def _resolve_credentials(node, secrets: dict, missing: list) -> None:
    if isinstance(node, dict):
        for key, value in list(node.items()):
            if isinstance(value, dict) and len(value) == 1 and _CRED_KEY in value:
                ref = value[_CRED_KEY]
                if ref not in secrets or not isinstance(secrets[ref], str) or not secrets[ref]:
                    missing.append(ref)
                else:
                    node[key] = secrets[ref]
            else:
                _resolve_credentials(value, secrets, missing)
    elif isinstance(node, list):
        for index, item in enumerate(node):
            if isinstance(item, dict) and len(item) == 1 and _CRED_KEY in item:
                ref = item[_CRED_KEY]
                if ref not in secrets or not isinstance(secrets[ref], str) or not secrets[ref]:
                    missing.append(ref)
                else:
                    node[index] = secrets[ref]
            else:
                _resolve_credentials(item, secrets, missing)


def materialize(plan: dict, secrets: dict, target_path) -> dict:
    """编译产物 → 服务全局 opencode.json（凭据明文唯一合法落点）。

    回执只含路径/摘要/键清单，绝不含凭据值；缺 secret = typed 拒，绝不
    静默写占位符（缺设施≠降级）。
    """
    if not isinstance(plan, dict) or plan.get("schema") != PLAN_SCHEMA:
        _fail("mcp_plan_schema_invalid")
    if not isinstance(secrets, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in secrets.items()):
        _fail("mcp_secrets_shape_invalid")
    servers = json.loads(json.dumps(plan["servers"], ensure_ascii=False))  # 深拷贝
    missing: list = []
    _resolve_credentials(servers, secrets, missing)
    if missing:
        _fail("mcp_credential_unresolved:" + ",".join(sorted(set(missing))))
    document = {
        "$schema": "https://opencode.ai/config.json",
        "mcp": {"servers": servers},
        "permissions": plan.get("permissions", []),
        "experimental": {"policies": plan.get("policies", [])},
    }
    payload = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
    path = Path(target_path)
    if not path.is_absolute():
        _fail("mcp_target_path_not_absolute")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8", newline="\n")
    return {
        "path": str(path),
        "sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        "bytes": len(payload.encode("utf-8")),
        "servers_written": sorted(servers),
        "secrets_materialized": sorted({
            node[_CRED_KEY]
            for name, cfg in plan["servers"].items()
            for node in _iter_credential_nodes(cfg)
        }),
    }


def _iter_credential_nodes(node):
    if isinstance(node, dict):
        if len(node) == 1 and _CRED_KEY in node:
            yield node
            return
        for value in node.values():
            yield from _iter_credential_nodes(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_credential_nodes(item)


# ---------------------------------------------------------------------- #
# 远端响应守卫：响应载荷恒为数据面（无信任开关通道）
# ---------------------------------------------------------------------- #

_PERMISSION_DIRECTIVE_RE = re.compile(
    r"(grant|授予|授权|allow|deny|effect).{0,40}(permission|权限|规则|ruleset)|"
    r"(permission|权限).{0,40}(grant|授予|授权|allow|deny)",
    re.IGNORECASE)
_TOOL_DEFINITION_MARKS = ('"inputSchema"', '"outputSchema"', "inputSchema")
_OVERRIDE_MARKS = (
    "ignore previous", "system prompt", "新指令", "忽略之前", "忽略以上",
    "管理员", "administrator", "system:", "开发者模式",
)


def response_guard(ruleset, payload_text: str) -> dict:
    """远端 MCP 响应载荷分类＋权限规则集不变式。

    恒判 data_only：本面不存在把响应内容并入权限规则集的通道（规则集唯一
    来源=本地 config/agent/session），守卫原样返回调用方规则集指纹供活体
    比对。签名刻意只收 (ruleset, payload_text)——没有可把载荷升格为可信
    的开关。
    """
    if not isinstance(payload_text, str):
        _fail("mcp_payload_not_text")
    families = []
    if _PERMISSION_DIRECTIVE_RE.search(payload_text) or '"effect"' in payload_text and '"allow"' in payload_text:
        families.append("permission_directive")
    if any(mark in payload_text for mark in _TOOL_DEFINITION_MARKS):
        families.append("tool_definition_injection")
    lowered = payload_text.lower()
    if any(mark in lowered for mark in _OVERRIDE_MARKS):
        families.append("instruction_override")
    return {
        "verdict": "data_only_no_privilege_effect",
        "families_detected": families,
        "ruleset_fingerprint": _fingerprint(ruleset),
        "ruleset_effective": ruleset,
    }


# ---------------------------------------------------------------------- #
# legal_entry 桥入口
# ---------------------------------------------------------------------- #

def face_call(method: str, args: dict, config: dict) -> dict:
    if method == "mcp.register":
        state_root = config.get("mcp_state_root")
        if not state_root:
            _fail("mcp_state_root_not_configured")
        return register(state_root, args.get("registry") or {})
    if method == "mcp.compile":
        return compile_connectors(args.get("registry") or {})
    if method == "mcp.materialize":
        return materialize(args.get("plan") or {}, args.get("secrets") or {},
                           args.get("target_path"))
    if method == "mcp.response_guard":
        if "ruleset" not in args or "payload_text" not in args:
            _fail("mcp_guard_args_invalid")
        return response_guard(args["ruleset"], args["payload_text"])
    if method == "mcp.invoke_policy":
        tier = args.get("tier")
        execute_enabled = bool(args.get("execute_enabled", True))
        return invoke_policy(tier, execute_enabled=execute_enabled)
    _fail("mcp_method_not_in_frozen_list:" + method)
