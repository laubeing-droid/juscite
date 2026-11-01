# -*- coding: utf-8 -*-
"""F126 多设备同步产品编排面（W5-U11；06 F126「多设备同步（WebDAV 端到
端加密）」；owner=harness+product 的 product 半边；裁决#13-19 WebDAV 合
成先行）。

分工（谁发起谁控制——产品发起，harness 只记账守门）：
* 本面＝传输与编排：端到端 bundle/manifest 的上传下载（WebDAV，纯
  stdlib 客户端＋合成服务）、离线重试的驱动；账本与和解真源全在
  harness 同步账（七方法封闭注册，见 legal-harness 仓 w5-u11 分支）。
* 密钥纪律：sync key 只经调用方显式 config（f126_sync_key_hex）传入、
  只随 owner API（harness_call 注入）进 harness——E06 环境合同不动，
  public_entry 密钥通道不接线（F10 同构边界）；未配置＝typed
  f126_sync_key_not_configured 拒，绝不静默明文同步。
* 端点纪律：webdav_endpoint 只来自显式 config；未配置＝typed
  f126_endpoint_not_configured 拒（P11 禁编 URL）。
* 传输不可达＝typed f126_remote_unreachable（离线形态的具名信号）；
  本面不缓存重试队列——离线重试由调用方按业务节奏重发同 bundle
  （bundle 幂等：内容寻址名＋harness 逐 entry IDEMPOTENT）。
* 服务端只见不透明信封：bundle/manifest 文件名＝信封字节 sha256 /
  device_id；两 manifest 各端各自发布（manifests/<device>.bin），无
  清单合并写冲突（多主不双写同一清单）。

harness_call 注入点（calendar_sync/submission_package 同构）：缺省＝
in-process 封闭注册直连（harness_import_path config 驱动 sys.path，
resolve_provider_method 封闭分发——密钥不经 JSON 文件/argv）；测试/
recon 可注入桩。
"""
from __future__ import annotations

import base64
import hashlib
import os
import sys

SYNC_METHODS = frozenset({
    "sync.push",
    "sync.pull",
    "sync.state",
    "sync.object_read",
    "sync.journal_replay",
})


class DeviceSyncError(RuntimeError):
    """具名错误（f126_* 码），绝不携材料内容。"""


def _harness(method: str, args: dict, harness_call) -> dict:
    result = harness_call(method, args)
    if not isinstance(result, dict):
        raise DeviceSyncError("f126_harness_receipt_invalid:" + method)
    return result


def _require(args: dict, field: str):
    value = args.get(field)
    if value is None:
        raise DeviceSyncError("f126_field_missing:" + field)
    return value


def _sync_key(config: dict) -> str:
    key_hex = config.get("f126_sync_key_hex")
    if not key_hex:
        raise DeviceSyncError("f126_sync_key_not_configured")
    return str(key_hex)


def _client(config: dict):
    endpoint = config.get("webdav_endpoint")
    if not endpoint:
        raise DeviceSyncError("f126_endpoint_not_configured")
    from webdav_client import WebDavClient
    auth = config.get("webdav_auth")
    return WebDavClient(str(endpoint), auth=tuple(auth) if auth else None)


def default_harness_call(config: dict):
    """缺省 harness 通道：in-process 封闭注册直连（owner API——sync 密钥
    只经此通道，不经 public_entry JSON/argv；harness_import_path config
    驱动 sys.path，与 cases_import_path 同构）。"""
    import_path = config.get("harness_import_path")
    if not import_path or not os.path.isdir(str(import_path)):
        raise DeviceSyncError("f126_harness_import_path_missing")
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))
    try:
        from legal_harness.business.provider_registry import (
            MethodNotWhitelisted,
            resolve_provider_method,
        )
        from legal_harness.business.units import HarnessUnits
        from legal_harness.state.matter_store import MatterStore
    except ImportError as exc:
        raise DeviceSyncError(
            "f126_harness_not_importable:" + type(exc).__name__) from None
    state_root = config.get("harness_state_root")
    if not state_root:
        raise DeviceSyncError("f126_harness_state_root_not_configured")
    atrest_hex = config.get("harness_atrest_key_hex")
    atrest_key = bytes.fromhex(str(atrest_hex)) if atrest_hex else None
    store = MatterStore(str(state_root), atrest_key=atrest_key)
    units = HarnessUnits(store)

    def call(method: str, args: dict) -> dict:
        try:
            bound = resolve_provider_method(method, units)
        except MethodNotWhitelisted as error:
            raise DeviceSyncError(str(error)) from None
        return bound(**args)

    return call


def device_sync_call(method: str, args: dict, config: dict,
                     harness_call=None) -> dict:
    """F126 产品面唯一入口（legal_entry SYNC_METHODS 冻结组分派）。"""
    if harness_call is None:
        harness_call = default_harness_call(config)
    if method == "sync.push":
        return _push(args, config, harness_call)
    if method == "sync.pull":
        return _pull(args, config, harness_call)
    if method == "sync.state":
        return _harness("harness.sync_state_read", {
            "scope": _require(args, "scope")}, harness_call)
    if method == "sync.object_read":
        return _harness("harness.sync_object_read", {
            "scope": _require(args, "scope"),
            "object_id": _require(args, "object_id")}, harness_call)
    if method == "sync.journal_replay":
        return _harness("harness.sync_journal_replay", {
            "scope": _require(args, "scope")}, harness_call)
    raise DeviceSyncError("f126_method_not_connected:" + method)


def _push(args: dict, config: dict, harness_call) -> dict:
    """本端写打包→上传 bundle（内容寻址名）→发布本端 manifest。

    manifest 只列本端在账 bundle（harness 未知 id 具名拒＝不造清单）；
    各端各自发布清单，无合并写冲突（对端 pull 时并集发现）。传输失败
    ＝typed f126_remote_unreachable（离线形态），bundle/账本原样保留，
    重试＝同 requestId 幂等（harness command_tx 回放＋服务端同名覆盖）。
    """
    scope = _require(args, "scope")
    device_id = _require(args, "device_id")
    sync_key = _sync_key(config)
    client = _client(config)
    built = _harness("harness.sync_bundle_build", {
        "actor_id": _require(args, "actor_id"),
        "scope": scope, "key": _require(args, "key"),
        "device_id": device_id,
        "entries": _require(args, "entries"), "sync_key": sync_key,
    }, harness_call)
    envelope = base64.b64decode(built["envelopeB64"])
    envelope_sha = hashlib.sha256(envelope).hexdigest()
    # 落盘名双摘要：bundleId（载荷确定性摘要，pull 按前缀取）＋信封字节
    # sha256（内容寻址，F10 地址绑定同构）。
    bundle_name = ("bundles/" + built["bundleId"] + "." + envelope_sha
                   + ".bin")
    client.put(bundle_name, envelope)
    state = _harness("harness.sync_state_read", {"scope": scope},
                     harness_call)
    sealed = _harness("harness.sync_manifest_seal", {
        "actor_id": _require(args, "actor_id"), "scope": scope,
        "key": {"requestId": "manifest-" + str(args["key"]["requestId"]),
                "targetId": None, "expectedRevision": None,
                "inputRefs": []},
        "device_id": device_id, "bundle_ids": state["knownBundleIds"],
        "sync_key": sync_key,
    }, harness_call)
    manifest_envelope = base64.b64decode(sealed["envelopeB64"])
    client.put("manifests/" + str(device_id) + ".bin", manifest_envelope)
    return {"bundleId": built["bundleId"], "bundleName": bundle_name,
            "entryCount": built["entryCount"],
            "revisionTop": built["revisionTop"],
            "manifestId": sealed["manifestId"],
            "manifestBundleCount": sealed["bundleCount"],
            "uploaded": True}


def _pull(args: dict, config: dict, harness_call) -> dict:
    """回连增量对账：列各端 manifest → 开封并集 → 差本端已知集＝缺失
    增量 → 逐 bundle 下载接入（harness 确定性和解）。本端 manifest 自
    身跳过（自家 bundle 无需回拉）。"""
    scope = _require(args, "scope")
    device_id = _require(args, "device_id")
    sync_key = _sync_key(config)
    client = _client(config)
    names = client.propfind_names("manifests/")
    remote_devices = [name[:-4] if name.endswith(".bin") else name
                      for name in names
                      if name.endswith(".bin")
                      and name != str(device_id) + ".bin"]
    state = _harness("harness.sync_state_read", {"scope": scope},
                     harness_call)
    known = set(state["knownBundleIds"])
    fetched, ingested = [], []
    for remote_device in sorted(remote_devices):
        status, manifest_bytes = client.get(
            "manifests/" + remote_device + ".bin")
        if status == 404:
            continue
        manifest = _harness("harness.sync_manifest_open", {
            "envelope_b64": base64.b64encode(manifest_bytes).decode("ascii"),
            "sync_key": sync_key}, harness_call)
        if str(manifest.get("matterId")) != str(scope.get("matterId")):
            raise DeviceSyncError(
                "f126_manifest_matter_mismatch:" + str(remote_device))
        missing = [bundle_id for bundle_id in manifest["bundleIds"]
                   if bundle_id not in known]
        for bundle_id in missing:
            name = _bundle_remote_name(client, bundle_id)
            if name is None:
                continue
            status, envelope = client.get(name)
            if status == 404:
                continue
            result = _harness("harness.sync_bundle_ingest", {
                "actor_id": _require(args, "actor_id"), "scope": scope,
                "key": {"requestId": "ingest-" + bundle_id[:16],
                        "targetId": None, "expectedRevision": None,
                        "inputRefs": []},
                "device_id": device_id,
                "envelope_b64": base64.b64encode(envelope).decode("ascii"),
                "sync_key": sync_key}, harness_call)
            known.add(bundle_id)
            fetched.append(bundle_id)
            ingested.append({"bundleId": result["bundleId"],
                             "peerDevice": result["peerDevice"],
                             "decisionCount": result["decisionCount"],
                             "conflictCount": result["conflictCount"]})
    after = _harness("harness.sync_state_read", {"scope": scope},
                     harness_call)
    return {"remoteDevices": remote_devices, "ingested": ingested,
            "ingestedCount": len(ingested),
            "fetchedBundleIds": fetched,
            "knownBundleCount": len(after["knownBundleIds"]),
            "stateAfter": after}


def _bundle_remote_name(client, bundle_id: str) -> str | None:
    """bundle 落盘名带 bundleId 前缀（bundles/<bundleId>.<信封sha>.bin）：
    pull 按 PROPFIND 列举前缀精确匹配（载荷摘要 bundle_id 与信封内容寻
    址 sha 是两个不同的摘要——落盘名双摘要桥接两者）。"""
    names = client.propfind_names("bundles/")
    prefix = bundle_id + "."
    for name in names:
        if name.startswith(prefix):
            return "bundles/" + name
    return None
