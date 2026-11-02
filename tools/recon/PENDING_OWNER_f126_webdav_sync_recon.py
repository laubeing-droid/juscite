#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""W5-U11 / F126 多设备同步（WebDAV 端到端加密）验收对账（RECON）。

06 F126（owner=harness+product；P02,P03,P04；V7-126 行）acceptance 逐字：
「加密同步冲突/离线/回退可对账；两端不双主覆盖」。裁决#13-19（00-总协
调.md:254）WebDAV 合成先行：loopback 本地合成 WebDAV 服务（纯 stdlib，
implementation/python/webdav_server.py）；E2E 加密封装复用 F10 at-rest
线格式先例（W4-U32 VERIFIED，台账 F10-desktop 行——atrest_crypto seal/
open 同族信封，AAD 域分隔）。preserved「B 形态自托管已答大半」——
selfhost 面沿 F02/F08 形态（basic auth 自托管服务形态），不重复建。

对账腿（每 profile 独立 %TEMP% 状态根与服务器存储根；全程合成材料；
零外发——服务器只绑 127.0.0.1）：

* P 腿（产品编排，in-process，harness_call 注入＝封闭注册 owner API）：
  - P1 合成 WebDAV 起服（loopback 随机端口；selfhost=basic auth 形态）
  - P2 push 端到端：bundle/manifest 信封上传，服务端零明文
  - P3 pull 收敛：对端增量拉取后 canonical 一致
  - P4 冲突确定性：双端并发写（同基同 revision 异内容）→ 两端独立
    和解收敛同一 canonical（规则 f126_rule_lamport_device_lexicographic）
  - P5 不静默覆盖（红线负测）：败方内容两端候选账具名保真＋CAS 字节
    可回读；服务端全量文件零明文子串命中
  - P6 离线具名：服务停机 → push = f126_remote_unreachable typed 拒
  - P7 回连增量：服务恢复 → 重试幂等（同 bundleId 同落盘名）→ 对端
    只拉缺失集（ingestedCount=缺失数，非全量）
  - P8 回退可回放对账：旧备份形态 state root 回连 → 对端新写快进采用
    ＋旧 canonical superseded 候选保真 → sync_journal_replay 三端全 OK
  - P9 桥读面：public_entry --sync-json（无钥读）子进程 dispatch 正常
  - P10 profile 面：selfhost＝错凭据 401 typed 拒＋对凭据可用（自托管
    basic auth 形态）；desktop＝无鉴权单机形态可用
* H 腿（harness 仓 w5-u11 分支账本面，子进程径）：
  - H1 schema v30 五表；H2 冲突规则名/conflict_id 两端同构；H3 密钥
    typed 拒闭集；H4 日志哈希链复算＋回放一致

边界如实（不入 PASS 断言，只入证据边界节）：targets.opencode 拟新增
经评估无需改动——sync 七方法落 HarnessUnits/provider_registry 共享核，
两 target 经既有 composition 同达；密钥通道不接 public_entry（F10 同构
边界，keyed 四方法走 in-process owner API）；真实 WebDAV 设施 v2 商业
化时补（裁决#13-19）。

用法（juscite w5-u11 worktree 根 cwd）：
  python -X utf8 tools/recon/PENDING_OWNER_f126_webdav_sync_recon.py \
      --profile desktop --profile selfhost
exit 0 = RECON_OK；exit 1 = FAIL；exit 2 = 环境预态不满足。
证据落 evidence/F126/<profile>/f126-webdav-sync-recon{,-suffix}.{json,md}。
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
UNIT_DEFAULT = "W5-U11"
PROFILE_DEVICE_NAMES = {
    "desktop": ("device-desktop-a", "device-desktop-b"),
    "selfhost": ("device-selfhost-a", "device-selfhost-b"),
}


def _workspace_root() -> Path:
    """jusbench工作区 的父级（1.法律工作区）——主检出与 worktree 通用。"""
    for parent in REPO_ROOT.parents:
        if parent.name == "jusbench工作区":
            return parent.parent
    raise RuntimeError("预态：未定位 jusbench工作区（cwd 须在 juscite 仓内）")


HARNESS_REPO = _workspace_root() / "legal-harness工作区" / "legal-harness-repo"


class ReconFail(Exception):
    pass


def resolve_harness_worktree() -> Path:
    hwt = HARNESS_REPO / ".local" / "worktrees" / "w5-u11"
    if not (hwt / "src" / "legal_harness" / "business" / "units.py").is_file():
        raise ReconFail(f"预态：harness w5-u11 worktree 缺 units.py：{hwt}")
    if "sync_bundle_build" not in (
            hwt / "src" / "legal_harness" / "business"
            / "provider_registry.py").read_text(encoding="utf-8"):
        raise ReconFail(f"预态：harness w5-u11 worktree 无 sync 面：{hwt}")
    return hwt


# ---------------------------------------------------------------- H 腿脚本
HARNESS_SCRIPT = r'''
import base64, hashlib, json, os, tempfile
from pathlib import Path

checks = []
def ck(cid, ok, detail=""):
    checks.append({"id": cid, "ok": bool(ok), "detail": str(detail)[:400]})

from legal_harness.business.provider_registry import HARNESS_PROVIDER_METHODS
from legal_harness.business.units import UnitsError, HarnessUnits, _F126_RULE
from legal_harness.state.matter_store import MatterStore, SCHEMA_VERSION

MATTER = "m-f126-h"
SCOPE = {"kind": "matter", "matterId": MATTER}
KEY = os.urandom(32).hex()

def entry(oid, text):
    return {"objectId": oid, "kind": "fact",
            "payloadB64": base64.b64encode(text.encode("utf-8")).decode()}

def ckey(rid):
    return {"requestId": rid, "targetId": None, "expectedRevision": None,
            "inputRefs": []}

root = Path(tempfile.mkdtemp(prefix="f126-recon-h-"))
sa = MatterStore(root / "a"); sa.create_matter(MATTER, "cas://p")
sb = MatterStore(root / "b"); sb.create_matter(MATTER, "cas://p")
ua, ub = HarnessUnits(sa), HarnessUnits(sb)

ck("H1_schema_v30", SCHEMA_VERSION == 30
   and HARNESS_PROVIDER_METHODS.get("harness.sync_bundle_build")
   == "sync_bundle_build", str(SCHEMA_VERSION))

base = ua.sync_bundle_build("act-a", SCOPE, ckey("h-b0"), "device-a",
                            [entry("fact/base", "基线（合成）")], KEY)
ub.sync_bundle_ingest("act-b", SCOPE, ckey("h-i0"), "device-b",
                      base["envelopeB64"], KEY)
wa = ua.sync_bundle_build("act-a", SCOPE, ckey("h-b1"), "device-a",
                          [entry("fact/base", "A 端并发写（合成）")], KEY)
wb = ub.sync_bundle_build("act-b", SCOPE, ckey("h-b2"), "device-b",
                          [entry("fact/base", "B 端并发写（合成）")], KEY)
ua.sync_bundle_ingest("act-a", SCOPE, ckey("h-i1"), "device-a",
                      wb["envelopeB64"], KEY)
ub.sync_bundle_ingest("act-b", SCOPE, ckey("h-i2"), "device-b",
                      wa["envelopeB64"], KEY)
va = ua.sync_object_read(SCOPE, "fact/base")
vb = ub.sync_object_read(SCOPE, "fact/base")
same = (va["canonicalSha"] == vb["canonicalSha"]
        and va["candidates"] and vb["candidates"]
        and va["candidates"][0]["conflictId"] == vb["candidates"][0]["conflictId"]
        and va["candidates"][0]["rule"] == _F126_RULE)
ck("H2_conflict_rule_named", same,
   f"a={va['canonicalSha'][:8]} b={vb['canonicalSha'][:8]}")

for bad_key, want in ((None, "f126_sync_key_required"),
                      ("short", "f126_sync_key_invalid")):
    try:
        ub.sync_bundle_ingest("act-b", SCOPE, ckey("h-k"), "device-b",
                              base["envelopeB64"], bad_key)
        ck("H3_typed_" + want, False, "未拒")
    except UnitsError as exc:
        ck("H3_typed_" + want, exc.code == want, exc.code)

ra = ua.sync_journal_replay(SCOPE)
rb = ub.sync_journal_replay(SCOPE)
ck("H4_journal_replay", ra["replayOk"] and rb["replayOk"]
   and ra["chainOk"] and rb["chainOk"], str(ra)[:120])

print(json.dumps({"ok": all(c["ok"] for c in checks), "checks": checks}))
'''


def _run_py(script: str, cwd: Path, env_extra: dict) -> dict:
    env = dict(os.environ)
    env.update(env_extra)
    env.setdefault("PYTHONUTF8", "1")
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", "-c", script],
        cwd=str(cwd), capture_output=True, text=True, encoding="utf-8",
        errors="replace", env=env, timeout=600)
    if not (proc.stdout or "").strip():
        raise ReconFail(
            f"子进程无 stdout：exit={proc.returncode} "
            f"stderr={(proc.stderr or '')[-800:]}")
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise ReconFail(
            f"子进程 stdout 非 JSON：{proc.stdout[:400]}… "
            f"stderr={(proc.stderr or '')[-400:]}") from None
    return payload


# ---------------------------------------------------------------- P 腿
def run_product_leg(profile: str, hwt: Path, checks: list) -> dict:
    def ck(cid, ok, detail=""):
        checks.append({"id": cid, "ok": bool(ok), "detail": str(detail)[:400]})

    sys.path.insert(0, str(hwt / "src"))
    sys.path.insert(0, str(REPO_ROOT / "implementation" / "python"))
    from legal_harness.business.provider_registry import (
        MethodNotWhitelisted, resolve_provider_method)
    from legal_harness.business.units import HarnessUnits
    from legal_harness.state import atrest_crypto
    from legal_harness.state.matter_store import MatterStore
    from webdav_server import SyntheticWebDavServer

    device_a, device_b = PROFILE_DEVICE_NAMES[profile]
    matter_id = f"m-f126-{profile}"
    scope = {"kind": "matter", "matterId": matter_id}
    sync_key = os.urandom(32).hex()
    synth_a = "F126 合成材料 A：和解协议价款 654,321.00 元（desktop/selfhost 合成）。"
    synth_b = "F126 合成材料 B：补充条款自 2026-06-01 起算（合成）。"

    def ckey(rid):
        return {"requestId": rid, "targetId": None,
                "expectedRevision": None, "inputRefs": []}

    def entry(oid, text):
        return {"objectId": oid, "kind": "fact",
                "payloadB64": base64.b64encode(
                    text.encode("utf-8")).decode("ascii")}

    tmp = Path(tempfile.mkdtemp(prefix=f"f126-recon-p-{profile}-"))
    storage = tmp / "dav-storage"

    servers: list = []

    # P1 合成 WebDAV 起服（desktop=无鉴权单机形态；selfhost=basic auth）
    auth = ("lvyin", "synthetic-pass") if profile == "selfhost" else None
    server = SyntheticWebDavServer(storage, space="lvyin-sync", auth=auth)
    server.start()
    servers.append(server)
    endpoint = server.endpoint
    ck("P1_dav_synthetic_started",
       endpoint.startswith("http://127.0.0.1:"),
       endpoint.rsplit("/", 1)[-1])

    def harness_for(state_root: Path):
        store = MatterStore(state_root)
        units = HarnessUnits(store)
        store.create_matter(matter_id, "cas://profile-f126")

        def call(method, args):
            try:
                bound = resolve_provider_method(method, units)
            except MethodNotWhitelisted as error:
                raise RuntimeError(str(error)) from None
            return bound(**args)

        return {"store": store, "units": units, "call": call}

    root_a, root_b = tmp / "state-a", tmp / "state-b"
    dev = {device_a: harness_for(root_a), device_b: harness_for(root_b)}

    def sync(device_id, method, args):
        # 产品编排走 device_sync.device_sync_call 本体（harness_call 注入
        # ＝封闭注册 owner API；传输/编排代码与桌面部署同一路径）。
        from device_sync import device_sync_call
        config = {"webdav_endpoint": endpoint, "webdav_auth": auth,
                  "f126_sync_key_hex": sync_key}
        return device_sync_call(method, dict(args, device_id=device_id),
                                config, harness_call=dev[device_id]["call"])

    try:
        # 基线互同步：A 写基线 → push → B pull。
        base = dev[device_a]["units"].sync_bundle_build(
            "actor-a", scope, ckey("p-base"), device_a,
            [entry("fact/base", "基线条款 v0（合成）")], sync_key)
        sealed = dev[device_a]["units"].sync_manifest_seal(
            "actor-a", scope, ckey("p-mf"), device_a,
            [base["bundleId"]], sync_key)
        from webdav_client import WebDavClient
        client = WebDavClient(endpoint, auth=auth)
        client.put("bundles/" + base["bundleId"] + "."
                   + hashlib_sha(base64.b64decode(base["envelopeB64"]))
                   + ".bin", base64.b64decode(base["envelopeB64"]))
        client.put("manifests/" + device_a + ".bin",
                   base64.b64decode(sealed["envelopeB64"]))
        pulled = sync(device_b, "sync.pull", {
            "scope": scope, "actor_id": "actor-b"})
        ck("P2_push_pull_e2e", pulled["ingestedCount"] == 1
           and pulled["ingested"][0]["bundleId"] == base["bundleId"],
           str(pulled["ingested"])[:120])

        # P3/P4 双端并发写：同基同 revision 异内容 → 交叉 pull 收敛。
        write_a = sync(device_a, "sync.push", {
            "scope": scope, "actor_id": "actor-a", "key": ckey("p-wa"),
            "entries": [entry("fact/terms", synth_a)]})
        write_b = sync(device_b, "sync.push", {
            "scope": scope, "actor_id": "actor-b", "key": ckey("p-wb"),
            "entries": [entry("fact/terms", synth_b)]})
        pull_a = sync(device_a, "sync.pull", {
            "scope": scope, "actor_id": "actor-a"})
        pull_b = sync(device_b, "sync.pull", {
            "scope": scope, "actor_id": "actor-b"})
        view_a = dev[device_a]["units"].sync_object_read(scope, "fact/terms")
        view_b = dev[device_b]["units"].sync_object_read(scope, "fact/terms")
        ck("P3_conflict_converged",
           view_a["canonicalSha"] == view_b["canonicalSha"]
           and view_a["revision"] == view_b["revision"]
           and view_a["writerDevice"] == view_b["writerDevice"],
           f"pull_a={pull_a['ingestedCount']} pull_b={pull_b['ingestedCount']}")
        ck("P4_conflict_named",
           len(view_a["candidates"]) == 1 and len(view_b["candidates"]) == 1
           and (view_a["candidates"][0]["conflictId"]
                == view_b["candidates"][0]["conflictId"])
           and view_a["candidates"][0]["rule"]
           == "f126_rule_lamport_device_lexicographic",
           str(view_a["candidates"])[:160])

        # P5 不静默覆盖：败方字节两端 CAS 可回读＋服务端全量零明文。
        import hashlib as _hashlib
        loser_sha = view_a["candidates"][0]["candidateSha"]
        loser_payload = None
        for text in (synth_a, synth_b):
            payload = _entry_payload(entry("fact/terms", text))
            if _hashlib.sha256(payload).hexdigest() == loser_sha:
                loser_payload = payload
        ok_p5 = (loser_payload is not None
                 and dev[device_a]["store"].cas.read_bytes(loser_sha)
                 == loser_payload
                 and dev[device_b]["store"].cas.read_bytes(loser_sha)
                 == loser_payload)
        ck("P5_no_silent_overwrite", ok_p5,
           f"loser={loser_sha[:8] if loser_sha else None}")

        blobs = [path for path in storage.rglob("*") if path.is_file()]
        plaintext_hits = []
        envelope_misses = []
        for path in blobs:
            raw = path.read_bytes()
            if path.suffix == ".bin" and not atrest_crypto.is_envelope(raw):
                envelope_misses.append(path.name)
            for text in (synth_a, synth_b, "基线条款 v0",
                         "654,321.00", "2026-06-01"):
                if text.encode("utf-8") in raw:
                    plaintext_hits.append(path.name)
                    break
        ck("P5b_server_zero_plaintext",
           bool(blobs) and not plaintext_hits and not envelope_misses,
           f"blobs={len(blobs)} hits={plaintext_hits} "
           f"non_envelope={envelope_misses}")

        # P6 离线具名：停机 → push typed 拒（f126_remote_unreachable）。
        # 推的是已 build 的同一 bundle（同 requestId 同内容——重试语义）。
        offline_entries = [entry("fact/offline", "离线期本地写（合成）")]
        offline_build = dev[device_a]["units"].sync_bundle_build(
            "actor-a", scope, ckey("p-off"), device_a,
            offline_entries, sync_key)
        server.stop()
        from webdav_client import WebDavClientError
        try:
            sync(device_a, "sync.push", {
                "scope": scope, "actor_id": "actor-a",
                "key": ckey("p-off"),
                "entries": offline_entries})
            ck("P6_offline_named_refused", False, "离线未拒")
        except WebDavClientError as exc:
            ck("P6_offline_named_refused",
               "f126_remote_unreachable" in str(exc), str(exc))

        # P7 回连增量：重启（新端口）→ 同 requestId 重试幂等 → 对端只拉
        # 缺失集。离线期 A 又多写一条（离线写累积）。
        dev[device_a]["units"].sync_bundle_build(
            "actor-a", scope, ckey("p-off2"), device_a,
            [entry("fact/offline2", "离线期第二条（合成）")], sync_key)
        server2 = SyntheticWebDavServer(storage, space="lvyin-sync",
                                        auth=auth)
        server2.start()
        servers.append(server2)
        endpoint2 = server2.endpoint
        from device_sync import device_sync_call as _dsc

        def sync2(device_id, method, args):
            config = {"webdav_endpoint": endpoint2, "webdav_auth": auth,
                      "f126_sync_key_hex": sync_key}
            return _dsc(method, dict(args, device_id=device_id), config,
                        harness_call=dev[device_id]["call"])

        retried = sync2(device_a, "sync.push", {
            "scope": scope, "actor_id": "actor-a", "key": ckey("p-off"),
            "entries": [entry("fact/offline", "离线期本地写（合成）")]})
        retried_b = sync2(device_a, "sync.push", {
            "scope": scope, "actor_id": "actor-a", "key": ckey("p-off2"),
            "entries": [entry("fact/offline2", "离线期第二条（合成）")]})
        ck("P7a_retry_idempotent",
           retried["bundleId"] == offline_build["bundleId"]
           and retried_b["bundleId"] != offline_build["bundleId"],
           f"retried={retried['bundleId'][:8]}")
        state_b_before = dev[device_b]["units"].sync_state_read(scope)
        pulled_b = sync2(device_b, "sync.pull", {
            "scope": scope, "actor_id": "actor-b"})
        state_b_after = dev[device_b]["units"].sync_state_read(scope)
        ck("P7b_incremental_only_missing",
           pulled_b["ingestedCount"] == 2
           and state_b_after["bundlesIngested"]
           == state_b_before["bundlesIngested"] + 2
           and state_b_after["lamport"] == state_b_after["lamport"],
           f"pulled={pulled_b['ingestedCount']} "
           f"known={len(state_b_after['knownBundleIds'])}")

        # P8 回退可回放对账：旧备份形态 root → 回连快进采用＋superseded
        # 候选＋三端日志回放全 OK。
        root_c = tmp / "state-c-rollback"
        dev_c = harness_for(root_c)
        stale = dev_c["units"].sync_bundle_build(
            "actor-a", scope, ckey("p-rb"), device_a,
            [entry("fact/terms", "回退前旧条款（旧备份合成）")], sync_key)
        stale_sha = stale["entries"][0]["sha256"]

        def sync_c(method, args):
            config = {"webdav_endpoint": endpoint2, "webdav_auth": auth,
                      "f126_sync_key_hex": sync_key}
            return _dsc(method, dict(args, device_id=device_a), config,
                        harness_call=dev_c["call"])

        pulled_c = sync_c("sync.pull", {"scope": scope,
                                        "actor_id": "actor-a"})
        view_c = dev_c["units"].sync_object_read(scope, "fact/terms")
        replay_c = dev_c["units"].sync_journal_replay(scope)
        replay_a = dev[device_a]["units"].sync_journal_replay(scope)
        replay_b = dev[device_b]["units"].sync_journal_replay(scope)
        ck("P8_rollback_replayable",
           pulled_c["ingestedCount"] >= 1
           and view_c["candidates"]
           and any(c["candidateSha"] == stale_sha
                   for c in view_c["candidates"])
           and replay_c["replayOk"] and replay_a["replayOk"]
           and replay_b["replayOk"],
           f"c_pulled={pulled_c['ingestedCount']} "
           f"cands={len(view_c['candidates'])}")

        # P10 profile 面：selfhost 错凭据 401 typed 拒；desktop 无鉴权可用。
        if profile == "selfhost":
            bad = WebDavClient(endpoint2, auth=("lvyin", "wrong"))
            try:
                bad.get("manifests/")
                ck("P10_selfhost_auth_enforced", False, "错凭据未拒")
            except WebDavClientError as exc:
                ck("P10_selfhost_auth_enforced",
                   "f126_dav_http_status:401" in str(exc), str(exc))
            good_names = WebDavClient(
                endpoint2, auth=auth).propfind_names("manifests/")
            ck("P10b_selfhost_auth_accepts",
               device_a + ".bin" in good_names
               and device_b + ".bin" in good_names, str(good_names)[:120])
        else:
            names = WebDavClient(endpoint2).propfind_names("manifests/")
            ck("P10_desktop_noauth_usable",
               device_a + ".bin" in names, str(names)[:120])

        # P9 桥读面：public_entry --sync-json（无钥读）子进程 dispatch。
        request = {"method": "harness.sync_state_read", "params": {
            "scope": scope}}
        request_file = tmp / "sync-state-req.json"
        request_file.write_text(json.dumps(request, ensure_ascii=False),
                                encoding="utf-8")
        env = dict(os.environ)
        env["LH_LEGAL_STATE_ROOT"] = str(root_a)
        env["PYTHONUTF8"] = "1"
        proc = subprocess.run(
            [sys.executable, "-X", "utf8",
             str(hwt / "tools" / "workflow-tools" / "harness"
                 / "public_entry.py"),
             "--sync-json", str(request_file), "--target", "workbuddy"],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", env=env, timeout=300, cwd=str(hwt))
        bridge_ok = False
        detail = f"exit={proc.returncode} out={(proc.stdout or '')[:160]}"
        if proc.returncode == 0 and proc.stdout.strip():
            try:
                payload = json.loads(proc.stdout)
                bridge_ok = (payload.get("surface") == "sync"
                             and payload.get("method")
                             == "harness.sync_state_read"
                             and isinstance(payload.get("result"), dict)
                             and payload["result"].get("matterId")
                             == matter_id)
            except json.JSONDecodeError:
                pass
        ck("P9_bridge_syncjson_read", bridge_ok, detail)
        ck("P12_manifests_per_device",
           sorted(path.name for path in
                  (storage / "lvyin-sync" / "manifests").iterdir())
           == sorted([device_a + ".bin", device_b + ".bin"]),
           "per-device manifests")
    finally:
        for live in servers:
            live.stop()
    return {"storage_root": str(storage), "state_roots": [str(root_a),
                                                          str(root_b)]}


def hashlib_sha(data: bytes) -> str:
    import hashlib
    return hashlib.sha256(data).hexdigest()


def _entry_payload(entry: dict) -> bytes:
    return base64.b64decode(entry["payloadB64"])


# ---------------------------------------------------------------- 编排
def run_profile(profile: str, hwt: Path, unit: str, suffix: str) -> dict:
    started = time.strftime("%Y-%m-%dT%H:%M:%S")
    checks: list[dict] = []
    product_meta = run_product_leg(profile, hwt, checks)
    h_payload = _run_py(HARNESS_SCRIPT, hwt, {"PYTHONPATH": str(hwt / "src")})
    checks.extend(h_payload["checks"])
    failed = [c for c in checks if not c["ok"]]
    verdict = "RECON_OK" if not failed else "RECON_FAIL"
    harness_head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(hwt), capture_output=True,
        text=True, encoding="utf-8").stdout.strip()
    result = {
        "unit": unit,
        "feature": ("F126-desktop" if profile == "desktop"
                    else "F126-selfhost"),
        "profile": profile,
        "verdict": verdict,
        "started_at": started,
        "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "counts": {"total": len(checks), "passed": len(checks) - len(failed),
                   "failed": len(failed)},
        "checks": checks,
        "failed_checks": [c["id"] for c in failed],
        "subjects": {
            "harness_worktree": str(hwt),
            "harness_head": harness_head,
            "product_worktree": str(REPO_ROOT),
        },
        "product_meta": product_meta,
        "boundaries": [
            "targets.opencode 拟新增经评估无需改动：sync 七方法落 "
            "HarnessUnits/provider_registry 共享核，两 target 经既有 "
            "composition 同达（units 由 ApplicationService 统一构建）",
            "密钥通道：sync key 只经 owner API（in-process 封闭注册）进 "
            "harness——E06 环境合同不动，public_entry 密钥通道不接线"
            "（F10 同构边界）；keyed 四方法不走 --sync-json 子进程",
            "裁决#13-19 合成先行：WebDAV=loopback 纯 stdlib 合成服务"
            "（webdav_server.py），真实设施 v2 商业化时补；selfhost 面"
            "沿 F02/F08 形态（basic auth 自托管形态），不重复建",
            "传输重试状态（哪些 bundle 已上传）归产品编排/调用方；"
            "harness 只记账（build/ingest 台账＋对账日志），零网络 I/O",
        ],
    }
    evidence_dir = REPO_ROOT / "evidence" / "F126" / profile
    evidence_dir.mkdir(parents=True, exist_ok=True)
    base = "f126-webdav-sync-recon" + (f"-{suffix}" if suffix else "")
    (evidence_dir / f"{base}.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    (evidence_dir / f"{base}.md").write_text(
        "\n".join(_render_md(result)), encoding="utf-8")
    return result


def _render_md(result: dict) -> list[str]:
    lines = [
        f"# F126 WebDAV 多设备同步 recon（{result['profile']}）— "
        f"{result['verdict']}",
        "",
        f"- unit: {result['unit']}（{result['feature']}）",
        f"- counts: {result['counts']['passed']}/{result['counts']['total']} "
        f"passed, {result['counts']['failed']} failed",
        f"- window: {result['started_at']} → {result['finished_at']}",
        f"- harness head: {result['subjects'].get('harness_head', '')}",
        "",
        "| # | check | ok | detail |",
        "|---|-------|----|--------|",
    ]
    for i, check in enumerate(result["checks"], 1):
        lines.append(f"| {i} | {check['id']} | "
                     f"{'PASS' if check['ok'] else 'FAIL'} "
                     f"| {check['detail']} |")
    lines += ["", "## 边界（如实，不入 PASS 断言）"]
    lines += [f"- {b}" for b in result["boundaries"]]
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", action="append", default=[],
                        choices=["desktop", "selfhost"],
                        help="验收 profile（可重复）")
    parser.add_argument("--unit", default=UNIT_DEFAULT)
    parser.add_argument("--evidence-suffix", default="")
    args = parser.parse_args()
    profiles = args.profile or ["desktop", "selfhost"]
    try:
        hwt = resolve_harness_worktree()
    except ReconFail as exc:
        print(f"F126_RECON_BLOCKED: {exc}", file=sys.stderr)
        return 2
    overall = []
    for profile in profiles:
        result = run_profile(profile, hwt, args.unit, args.evidence_suffix)
        overall.append(result)
        print(f"[{profile}] {result['verdict']} "
              f"{result['counts']['passed']}/{result['counts']['total']} "
              f"failed={result['failed_checks']}")
    if any(r["verdict"] != "RECON_OK" for r in overall):
        print("F126_RECON_FAIL")
        return 1
    print(f"F126_RECON_OK profiles={','.join(profiles)} "
          f"checks={sum(r['counts']['total'] for r in overall)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
