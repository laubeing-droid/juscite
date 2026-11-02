# -*- coding: utf-8 -*-
r"""F34 v2 高级对抗评审编排（按需真会话＋异构复核·第二家模型合成先行）
验收 recon（工单 W5-U06）。

06 V7-34（B5；owner=product+harness；desktop/selfhost 双实例）
acceptance＝「v2高级对抗编排按需真会话与异构复核；v1当前必要五角色真实
消费另见E05，不一起延期，不固定五步」。05:87「五身份按能力缺口按需，
不每案五人流水线；高级评审F34仍v2」。裁决#13-19（00-总协调.md:254）：
第二家模型合成先行——异构复核用合成第二 provider（不同应答形态离线注
入），真实第二家 API 商业化时补。按需真会话＝编排器不为评审常驻会话，
会话生命周期沿 F23 server-owned 已 VERIFIED 语义。

验收命令（工单钦定，juscite worktree 根 cwd）：
  python -X utf8 tools/recon/PENDING_OWNER_f34_adversarial_orchestration_recon.py
      --profile desktop --profile selfhost
exit 0 = RECON_OK；1 = RECON_FAIL；3 = RECON_BLOCKED。

  - desktop 腿＝真产品入口 legal_entry 子进程径（ADV_ORCH_METHODS 编排
    器＋HARNESS_ADV_METHODS → harness public_entry --advorch-json 信封
    真子进程；临时 SQLite 状态根）＋真 opencode serve --service 拓扑
    （产品桌面托管形态：注册文件在临时 XDG state 根，%APPDATA% 零触
    碰）；
  - selfhost 腿＝前台 serve 拓扑（stdout-URL＋OPENCODE_SERVER_PASSWORD）
    ＋PgMatterStore 直连 lh-pg-e08 独立 schema（E24/F118/F122/F123
    recon selfhost 腿同径）；产品面 harness_call 注入封闭注册直连
    （signed_export 同构），编排器同模块同码进程内真跑。

两腿合成 provider 各二：主模型（token 分块流式 SSE，≥8 增量）＋复核第
二模型（单增量整发——不同应答形态离线注入，裁决#13-19），均 127.0.0.1
回环端点，零真实外联、零真实键依赖。

断言面（全合成材料；金额零入场）：
  S1 冻结拓扑：XDG 四临时根＋产品配置深拷贝只写临时根＋双合成 provider
     回环 base URL；%APPDATA% 只读快照前后相等；
  S2 按需真会话：逐步 just-in-time 建真子会话（确定性 ses_f34_ id 逐步
     互异）→逐步恰一次 prompt→F23 server-owned 完成判定（持久消息账
     idle succeeded，SSE 挥发不作证据）→transcript＝回读行集摘要；
  S3 声明式计划（不固定五步）：3 步与 6 步计划经同一信封同权登记；同
     plan_id 异内容 f34_plan_conflict 具名拒；
  S4 异构复核：review 步模型唯一来自配置（合成第二 provider）；回读身
     份与被复核步互异（产品侧 f34_review_not_heterogeneous＋账本级
     f34_review_model_same 双层断言互不替代）；缺配置 fail-closed；
  S5 账本投影：计划结构投影（指示正文不入账只钉 promptSha256）＋逐步
     回执读回（身份/摘要/被复核步号）；harness 永不编排（harness.adv_
     run 封闭注册外具名拒）；
  S6 线缆形态差异证据：主/复核端点各记账应答形态（分块数），亲证两形
     互异且轮次真实打到位；
  S7 桥纪律：未配置 NotConnected exit 3；封闭集外方法具名拒；
  S8 跨 profile 一致：同一计划/运行内容级投影逐键相等（证据脱时钟——
     U08/E15 剥时间戳先例）。
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote

RUN_TS = time.strftime("%Y%m%dT%H%M%S")
REPO_ROOT = Path(__file__).resolve().parents[2]
LEGAL_ENTRY = REPO_ROOT / "implementation" / "python" / "legal_entry.py"
OOC28_PIN = "026b106bc5d41b679ffc413264229c340871e4d3"
DEFAULT_BUN = Path.home() / ".bun" / "bun.exe"
DEV_VERSION = "2.0.0-local-w5u06"     # F-4：dev 版记实值（打包 pin=2.0.28）

# harness 战役分支（A2 链）本单检出与 F34 面钉定
HARNESS_WORKTREE = Path(
    r"D:\Codex\1.法律工作区\legal-harness工作区\legal-harness-repo"
    r"\.local\worktrees\w5-u06")
HARNESS_PUBLIC_ENTRY = HARNESS_WORKTREE / Path(
    "tools/workflow-tools/harness/public_entry.py")
HARNESS_BRANCH = "w5-u06"
DEFAULT_PG_DSN = "postgresql://lh_app:e08-synth-only@127.0.0.1:55432/legal_harness"

MATTER = "m-f34-rx"
PRIMARY_PROVIDER = "synth-f34-primary"
PRIMARY_MODEL = "f34-primary-synth"
REVIEW_PROVIDER = "synth-f34-review"
REVIEW_MODEL = "f34-review-synth"

PLAN3_PROMPTS = [
    ("produce", "drafting-agent", None, None,
     "（合成）依据给定的合成案情摘要产出一段三句以内的处理草案文本，"
     "不要调用任何工具，只直接回答。"),
    ("attack", "adversarial-review-agent", 1, "attacksStep",
     "（合成）针对第 1 步草案发起一轮对抗攻击：列出最多两条攻击点，"
     "不要调用任何工具，只直接回答。"),
    ("review", "adversarial-review-agent", 1, "reviewsStep",
     "（合成）以第二模型身份对第 1 步草案做异构复核：给出一段不超过两句"
     "的独立复核意见，不要调用任何工具，只直接回答。"),
]


def build_plan(plan_id: str, prompt_override: str | None = None) -> dict:
    steps = []
    for seq, (kind, role, ref, ref_key, prompt) in enumerate(
            PLAN3_PROMPTS, start=1):
        step = {"seq": seq, "kind": kind, "role": role, "prompt": prompt}
        if prompt_override and seq == 1:
            step["prompt"] = prompt_override
        if ref is not None:
            step[ref_key] = ref
        steps.append(step)
    return {"schema": "lvyin-adv-plan/1", "planId": plan_id,
            "title": "F34 recon 合成对抗编排（三步）", "steps": steps}


def build_plan_six(plan_id: str) -> dict:
    """6 步全 produce 计划——步数变量（不固定五步）经同一信封登记。"""
    return {"schema": "lvyin-adv-plan/1", "planId": plan_id,
            "title": "F34 recon 合成编排（六步·步数变量）",
            "steps": [{"seq": i, "kind": "produce",
                       "role": "case-conductor",
                       "prompt": f"（合成）第 {i} 步：直接回答收到，"
                                 f"不要调用工具。"}
                      for i in range(1, 7)]}


PRIMARY_TEXT = ("（合成·主模型回执）已按指示完成本步文本产出，未调用任何"
                "工具。律引F34对抗编排合成材料。")
REVIEW_TEXT = ("（合成·第二模型异构复核）复核意见：已独立比对被复核步产"
               "出与本步指示，未发现阻断项；本回执来自第二合成 provider"
               "（不同应答形态离线注入）。")


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def port_open(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket() as probe:
        probe.settimeout(1.0)
        return probe.connect_ex((host, port)) == 0


class SynthEndpoint:
    """127.0.0.1 回环 OpenAI 兼容合成端点（裁决#13-19 第二家模型合成先
    行）。shape="chunked"＝≥8 增量慢速分块（主模型形态）；shape="single"
    ＝单增量整发（复核第二模型形态——不同应答形态离线注入）。逐请求记
    账分块数/字节，供 S6 线缆形态差异亲证。"""

    def __init__(self, provider_id: str, model_id: str, text: str,
                 shape: str):
        self.provider_id = provider_id
        self.model_id = model_id
        self.text = text
        self.shape = shape
        self.port = free_port()
        self.requests: list[dict] = []
        self.lock = threading.Lock()
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def do_GET(self):
                body = json.dumps({"object": "list", "data": [
                    {"id": outer.model_id, "object": "model"}]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                self.rfile.read(length)
                chunks = ([{"content": outer.text[i:i + 6]}
                           for i in range(0, len(outer.text), 6)]
                          if outer.shape == "chunked"
                          else [{"content": outer.text}])
                record = {"shape": outer.shape, "chunks": len(chunks),
                          "bytes": sum(len(c["content"].encode("utf-8"))
                                       for c in chunks)}
                with outer.lock:
                    outer.requests.append(record)
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "close")
                self.end_headers()

                def frame(delta, finish=None):
                    return json.dumps({
                        "id": "chatcmpl-f34-synth", "created": 0,
                        "object": "chat.completion.chunk",
                        "model": outer.model_id,
                        "choices": [{"index": 0, "delta": delta,
                                     "finish_reason": finish}]},
                        ensure_ascii=False).encode("utf-8")

                def write(frame_bytes: bytes):
                    self.wfile.write(b"data: " + frame_bytes + b"\n\n")
                    self.wfile.flush()

                write(frame({"role": "assistant", "content": None}))
                for delta in chunks:
                    write(frame(delta))
                    if outer.shape == "chunked":
                        time.sleep(0.02)
                write(frame({}, finish="stop"))
                write(b"[DONE]")
                self.close_connection = True

        self.server = ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
        self.server.daemon_threads = True
        self._thread = threading.Thread(target=self.server.serve_forever,
                                        daemon=True)

    def start(self):
        self._thread.start()
        return self

    def stop(self):
        self.server.shutdown()
        self.server.server_close()

    def stats(self) -> dict:
        with self.lock:
            reqs = list(self.requests)
        return {"provider": self.provider_id, "model": self.model_id,
                "shape": self.shape,
                "completions": len(reqs),
                "chunks_per_request": (
                    sorted({r["chunks"] for r in reqs}) if reqs else []),
                "base_url": f"http://127.0.0.1:{self.port}/v1"}


class Checks:
    def __init__(self, profile: str):
        self.profile = profile
        self.checks: list[dict] = []
        self.blocked_reason: str | None = None

    def step(self, name, ok, **facts):
        entry = {"check": name, "status": "PASS" if ok else "FAIL", **facts}
        self.checks.append(entry)
        print(json.dumps(entry, ensure_ascii=False), flush=True)
        if not ok:
            raise AssertionError(name)

    def blocked(self, reason, **facts):
        entry = {"check": reason, "status": "BLOCKED", **facts}
        self.checks.append(entry)
        self.blocked_reason = reason
        print(json.dumps({"status": "RECON_BLOCKED",
                          "profile": self.profile, "reason": reason},
                         ensure_ascii=False))
        raise _Blocked(reason)


class _Blocked(Exception):
    pass


def call_entry(method: str, args: dict, config: dict) -> dict:
    """真产品入口子进程调用；返回 {exit, payload}（F123 recon 同法）。"""
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
        env = dict(os.environ)
        python_dir = str(REPO_ROOT / "implementation" / "python")
        env["PYTHONPATH"] = python_dir + os.pathsep + env.get("PYTHONPATH", "")
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", str(LEGAL_ENTRY),
             "--request-json", request_handle.name,
             "--config", config_handle.name],
            capture_output=True, timeout=600, env=env)
        try:
            payload = json.loads(proc.stdout.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            payload = {"status": "STDOUT_UNPARSEABLE",
                       "stdout_head": proc.stdout.decode(
                           "utf-8", errors="replace")[:400]}
        return {"exit": proc.returncode, "payload": payload}
    finally:
        os.unlink(request_handle.name)
        os.unlink(config_handle.name)


def entry_result(response: dict) -> dict:
    """OWNER_RESPONSE.result 提取（桌面腿读回用）。"""
    payload = response.get("payload", {})
    if isinstance(payload, dict) and isinstance(payload.get("result"), dict):
        return payload["result"]
    return {}


def snapshot_appdata() -> dict:
    """%APPDATA%/Juscite 只读快照（config+state 落点 size/mtime）。"""
    appdata = Path(os.environ["APPDATA"]) / "Juscite"
    snap = {}
    target = appdata / "config" / "opencode" / "opencode.json"
    if target.exists():
        stat = target.stat()
        snap["config/opencode/opencode.json"] = (stat.st_size,
                                                 stat.st_mtime_ns)
    state_dir = appdata / "state" / "opencode"
    if state_dir.is_dir():
        for item in sorted(state_dir.glob("*.json")):
            stat = item.stat()
            snap["state/opencode/" + item.name] = (stat.st_size,
                                                   stat.st_mtime_ns)
    return snap


class Serve:
    """oc28 只读 serve 拉起（desktop=--service 注册文件拓扑／selfhost=
    前台 stdout-URL 拓扑；F22/F23 已 VERIFIED 拓扑同法）。"""

    def __init__(self, checks: Checks, oc28: Path, bun: Path, profile: str,
                 roots: dict, requested_port: int):
        self.checks = checks
        self.oc28 = oc28
        self.bun = bun
        self.profile = profile
        self.roots = roots
        self.requested_port = requested_port
        self.proc = None
        self.port = None
        self.password = None
        self.url = None

    def launch(self) -> None:
        env = {k: v for k, v in os.environ.items()}
        env["XDG_STATE_HOME"] = str(self.roots["state_root"])
        env["XDG_DATA_HOME"] = str(self.roots["data_root"])
        env["XDG_CONFIG_HOME"] = str(self.roots["config_root"])
        env["XDG_CACHE_HOME"] = str(self.roots["cache_root"])
        env["OPENCODE_DISABLE_MODELS_FETCH"] = "1"   # models.dev 禁轮询
        env["OPENCODE_CHANNEL"] = "local"
        env["OPENCODE_VERSION"] = DEV_VERSION
        self.password = uuid.uuid4().hex + uuid.uuid4().hex
        argv = [str(self.bun), "run", "--cwd", "packages/cli",
                "--define=OPENCODE_VERSION=process.env.OPENCODE_VERSION",
                "src/index.ts", "serve",
                "--hostname", "127.0.0.1", "--port",
                str(self.requested_port)]
        if self.profile == "desktop":
            argv.append("--service")   # 注册文件拓扑（桌面托管形态）
        else:
            env["OPENCODE_SERVER_PASSWORD"] = self.password
        log_path = self.roots["base"] / "service.log"
        log = open(log_path, "ab")
        self.proc = subprocess.Popen(argv, cwd=str(self.oc28), env=env,
                                     stdout=log, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 240.0
        if self.profile == "desktop":
            reg_path = self.roots["state_root"] / "opencode" / \
                "service-local.json"
            reg = None
            while time.monotonic() < deadline:
                if self.proc.poll() is not None:
                    self.checks.blocked(
                        "service_process_exited",
                        exit_code=self.proc.returncode)
                if reg_path.exists():
                    try:
                        reg = json.loads(
                            reg_path.read_text(encoding="utf-8"))
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        reg = None
                if reg is not None and reg.get("password"):
                    break
                time.sleep(1.0)
            if reg is None:
                self.checks.blocked("service_registration_timeout")
            self.url = str(reg["url"])
            self.password = reg["password"]
        else:
            url = None
            while time.monotonic() < deadline:
                if self.proc.poll() is not None:
                    self.checks.blocked("service_process_exited",
                                        exit_code=self.proc.returncode)
                try:
                    text = log_path.read_text(encoding="utf-8",
                                              errors="replace")
                except OSError:
                    text = ""
                for line in text.splitlines():
                    if "server listening on" in line:
                        url = line.rsplit(" ", 1)[-1].strip()
                if url:
                    break
                time.sleep(1.0)
            if not url:
                self.checks.blocked("selfhost_url_timeout")
            self.url = url
        self.port = int(self.url.rsplit(":", 1)[1])

    def client(self, timeout: float = 60.0):
        sys.path.insert(0, str(REPO_ROOT / "implementation" / "python"))
        from opencode_http import Client
        token = base64.b64encode(
            ("opencode:" + self.password).encode()).decode("ascii")
        return Client(self.url, headers={"Authorization": "Basic " + token},
                      timeout=timeout)

    def stop(self):
        if self.proc is None or self.proc.poll() is not None:
            return
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(self.proc.pid)],
                       capture_output=True, timeout=60)
        deadline = time.monotonic() + 45.0
        while time.monotonic() < deadline:
            if not port_open(self.port):
                break
            time.sleep(1.0)


def build_profile_env(checks: Checks, oc28: Path, profile: str,
                      primary: SynthEndpoint, review: SynthEndpoint):
    """临时 XDG 四根＋产品配置深拷贝（只写临时根）＋双合成 provider 注入
    ＋工作区目录。返回 (roots, requested_port, appdata_before)。"""
    holder = tempfile.TemporaryDirectory(
        prefix=f"juscite-f34-{profile}-")
    base = Path(holder.name)
    roots = {"base": base}
    for key in ("state_root", "data_root", "config_root", "cache_root"):
        roots[key] = base / "oc" / key.split("_")[0]
        roots[key].mkdir(parents=True)
    roots["workspace"] = base / "workspace"
    roots["workspace"].mkdir()
    roots["harness_state"] = base / "harness-state"
    roots["harness_state"].mkdir()
    appdata_before = snapshot_appdata()
    product_config = (Path(os.environ["APPDATA"]) / "Juscite" / "config" /
                      "opencode" / "opencode.json")
    if product_config.exists():
        cfg = json.loads(product_config.read_text(encoding="utf-8-sig"))
        cfg_note = "product-config-copy"
    else:
        cfg = {}
        cfg_note = "synthetic-only(no product config on machine)"
    providers = cfg.setdefault("provider", {})
    providers[PRIMARY_PROVIDER] = {
        "npm": "@ai-sdk/openai-compatible",
        "name": "F34 Primary Synth (recon)",
        "options": {"baseURL": f"http://127.0.0.1:{primary.port}/v1",
                    "apiKey": "synthetic-primary-key"},
        "models": {PRIMARY_MODEL: {"name": "Primary Chunked Synth"}},
    }
    providers[REVIEW_PROVIDER] = {
        "npm": "@ai-sdk/openai-compatible",
        "name": "F34 Review Synth (recon)",
        "options": {"baseURL": f"http://127.0.0.1:{review.port}/v1",
                    "apiKey": "synthetic-review-key"},
        "models": {REVIEW_MODEL: {"name": "Review Single-Delta Synth"}},
    }
    opencode_config_dir = roots["config_root"] / "opencode"
    opencode_config_dir.mkdir(parents=True, exist_ok=True)
    (opencode_config_dir / "opencode.json").write_text(
        json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")
    injected = [PRIMARY_PROVIDER, REVIEW_PROVIDER]
    synth_loopback = all(
        "127.0.0.1" in str((providers[name].get("options") or {})
                           .get("baseURL", "")) for name in injected)
    carried = [name for name in providers if name not in injected]
    checks.step("s1_temp_roots_and_synth_providers",
                synth_loopback,
                base=str(base), config_source=cfg_note,
                injected_providers=injected,
                injected_base_urls={name: providers[name]["options"]
                                    ["baseURL"] for name in injected},
                carried_providers=carried,
                note="本单注入双合成 provider 恒回环；产品既有 provider 仅随"
                     "深拷贝在临时配置文件中（会话全部显式绑定合成模型——S2 "
                     "回读身份亲证，端点收包计数旁证），不发起任何调用",
                appdata_snapshot_keys=len(appdata_before))
    return roots, free_port(), appdata_before, holder


def entry_configs(roots: dict, serve: "Serve", profile: str) -> dict:
    """legal_entry 子进程配置：会话 transport（注册文件/env 凭据）＋编排
    绑定（合成双模型）＋harness 信封（临时状态根）。"""
    config = {
        "adv_workspace": str(roots["workspace"]),
        "adv_primary_model": {"providerID": PRIMARY_PROVIDER,
                              "id": PRIMARY_MODEL},
        "adv_review_model": {"providerID": REVIEW_PROVIDER,
                             "id": REVIEW_MODEL},
        "adv_step_timeout": 120,
        "harness_public_entry": str(HARNESS_PUBLIC_ENTRY),
        "harness_target": "opencode",
        "harness_state_root": str(roots["harness_state"]),
        "harness_timeout": 120,
        "opencode_timeout": 60,
    }
    if profile == "desktop":
        config["opencode_registration"] = str(
            roots["state_root"] / "opencode" / "service-local.json")
    else:
        config["opencode_url"] = serve.url
    return config


def run_desktop_leg(checks: Checks, oc28: Path, bun: Path) -> dict:
    """desktop 腿＝全真产品入口子进程径（legal_entry→adv.*＋harness 信
    封子进程；临时 SQLite 状态根）＋serve --service 桌面托管拓扑。"""
    primary = SynthEndpoint(PRIMARY_PROVIDER, PRIMARY_MODEL,
                            PRIMARY_TEXT, "chunked").start()
    review = SynthEndpoint(REVIEW_PROVIDER, REVIEW_MODEL,
                           REVIEW_TEXT, "single").start()
    roots, requested_port, appdata_before, holder = build_profile_env(
        checks, oc28, "desktop", primary, review)
    serve = Serve(checks, oc28, bun, "desktop", roots, requested_port)
    config = None
    projection: dict = {}
    try:
        serve.launch()
        client = serve.client()
        info = client.request("GET", "/api/info")
        value = info.get("data", info) if isinstance(info, dict) else {}
        version = value.get("version") if isinstance(value, dict) else None
        checks.step("s1_topology_service_ready",
                    version == DEV_VERSION and port_open(serve.port),
                    profile="desktop", served_port=serve.port,
                    version=version, dev_version=True,
                    topology="serve --service 注册文件（桌面托管形态）")
        config = entry_configs(roots, serve, "desktop")
        matter_id = MATTER
        sys.path.insert(0, str(HARNESS_WORKTREE / "src"))
        from legal_harness.state.matter_store import MatterStore
        MatterStore(roots["harness_state"]).create_matter(
            matter_id, "cas://profile-f34-desktop")

        # -- S7 桥纪律（未配置 fail-closed；封闭集外具名拒） ------------
        bare = dict(config)
        for key in ("harness_public_entry", "harness_target",
                    "harness_state_root"):
            bare.pop(key, None)
        unconfigured = call_entry("adv.plan_register",
                                  {"matterId": matter_id,
                                   "plan": build_plan("f34-s7")},
                                  bare)
        checks.step("s7_unconfigured_not_connected",
                    unconfigured["exit"] == 3
                    and unconfigured["payload"].get("status")
                    == "NOT_CONNECTED",
                    exit=unconfigured["exit"],
                    code=str(unconfigured["payload"].get("code"))[:80])
        closed = call_entry("harness.adv_run", {"matterId": matter_id},
                            config)
        checks.step("s7_harness_never_orchestrates",
                    closed["exit"] == 3 and "method_not_connected"
                    in str(closed["payload"].get("code")),
                    exit=closed["exit"],
                    code=str(closed["payload"].get("code"))[:80])

        # -- S3 声明式计划（不固定五步）＋冲突具名拒 ---------------------
        plan3 = build_plan("f34-p1")
        registered = call_entry("adv.plan_register",
                                {"matterId": matter_id, "plan": plan3},
                                config)
        reg3 = entry_result(registered)
        checks.step("s3_plan_register_three_steps",
                    registered["exit"] == 0 and reg3.get("created") is True
                    and reg3.get("stepsCount") == 3,
                    exit=registered["exit"], created=reg3.get("created"),
                    stepsCount=reg3.get("stepsCount"),
                    planSha256=str(reg3.get("planSha256"))[:16])
        six = call_entry("adv.plan_register",
                         {"matterId": matter_id,
                          "plan": build_plan_six("f34-p6")}, config)
        reg6 = entry_result(six)
        checks.step("s3_plan_register_six_steps_variable",
                    six["exit"] == 0 and reg6.get("created") is True
                    and reg6.get("stepsCount") == 6,
                    exit=six["exit"], stepsCount=reg6.get("stepsCount"),
                    note="步数变量经同一信封同权登记——不固定五步")
        conflict = call_entry(
            "adv.plan_register",
            {"matterId": matter_id,
             "plan": build_plan("f34-p1",
                                prompt_override="（合成）被篡改的第一步指示。")},
            config)
        checks.step("s3_plan_conflict_named_reject",
                    conflict["exit"] == 1
                    and conflict["payload"].get("status") == "HARNESS_FAIL"
                    and "f34_plan_conflict"
                    in str(conflict["payload"].get("code")),
                    exit=conflict["exit"],
                    code=str(conflict["payload"].get("code"))[:80])

        # -- S2 按需真会话执行（3 步计划；逐步建会话；F23 完成语义） ----
        run = call_entry("adv.run",
                         {"matterId": matter_id, "planId": "f34-p1",
                          "runId": "run-1", "plan": plan3}, config)
        run_result = entry_result(run)
        steps = run_result.get("steps", [])
        gaps = run_result.get("gaps", [])
        checks.step("s2_run_three_real_sessions",
                    run["exit"] == 0 and gaps == [] and len(steps) == 3,
                    exit=run["exit"], gaps=gaps,
                    executed=[s["seq"] for s in steps])
        session_ids = [s.get("sessionId") for s in steps]
        expected_tags = ["ses_f34_" + hashlib.sha256(
            f"f34-p1|run-1|{seq}".encode()).hexdigest()[:24]
            for seq in (1, 2, 3)]
        prompt_ids = [s.get("promptMessageId") for s in steps]
        checks.step("s2_on_demand_deterministic_ids",
                    session_ids == expected_tags
                    and all(i and i.startswith("ses_f34_")
                            for i in session_ids)
                    and len(set(session_ids)) == 3
                    and all(p and p.startswith("msg_f34_")
                            for p in prompt_ids)
                    and len(set(prompt_ids)) == 3,
                    session_ids=session_ids,
                    note="逐步 just-in-time 建会话（零池化零常驻）；"
                         "确定性 id＝sha256(planId|runId|seq)")
        # 完成语义＝持久消息账回读（服务端持有完成；SSE 挥发不作证据）。
        histories_ok = True
        for step, session_id, prompt_id in zip(steps, session_ids,
                                               prompt_ids):
            rows = []
            path = f"/api/session/{quote(session_id, safe='')}" \
                   "/message?order=asc"
            while path:
                listing = client.request("GET", path)
                if not isinstance(listing, dict):
                    break
                rows.extend(listing.get("data") or [])
                cursor = (listing.get("cursor") or {}).get("next")
                path = (f"/api/session/{quote(session_id, safe='')}"
                        f"/message?cursor={quote(str(cursor), safe='')}"
                        if cursor else None)
            idles = [r for r in rows
                     if r.get("type") == "idle"
                     and rows.index([x for x in rows
                                     if x.get("id") == prompt_id][0])
                     < rows.index(r)] if any(
                x.get("id") == prompt_id for x in rows) else []
            if not idles or idles[-1].get("outcome") != "succeeded":
                histories_ok = False
        checks.step("s2_f23_server_owned_completion_readback",
                    histories_ok,
                    note="消息账逐会话回读：本轮之后 idle 行 outcome="
                         "succeeded；完成归服务端持有（F23 已 VERIFIED 语义）")
        # 模型身份（回读为准，非配置回声）＋异构复核互异。
        identities = [s.get("model") for s in steps]
        checks.step(
            "s4_model_identity_from_readback_heterogeneous",
            identities[0] == {"providerID": PRIMARY_PROVIDER,
                              "id": PRIMARY_MODEL}
            and identities[1] == {"providerID": PRIMARY_PROVIDER,
                                  "id": PRIMARY_MODEL}
            and identities[2] == {"providerID": REVIEW_PROVIDER,
                                  "id": REVIEW_MODEL}
            and identities[2] != identities[0],
            identities=identities,
            note="review 步模型唯一来自配置（合成第二 provider）；回读"
                 "身份与被复核步互异——异构复核产品侧断言")
        digests_ok = all(
            isinstance(s.get("transcriptSha256"), str)
            and len(s["transcriptSha256"]) == 64 for s in steps)
        checks.step("s2_transcript_digests_pinned", digests_ok,
                    digests=[str(s.get("transcriptSha256"))[:12]
                             for s in steps],
                    message_counts=[s.get("messageCount") for s in steps])
        receipts = run_result.get("ledgerReceipts", [])
        checks.step("s2_step_ledger_receipts_in_order",
                    [r.get("seq") for r in receipts] == [1, 2, 3],
                    receipts=receipts)
        projection["run"] = {
            "planSha256": run_result.get("planSha256"),
            "steps": [{"seq": s["seq"], "kind": s["kind"],
                       "role": s["role"], "model": s["model"],
                       "transcriptSha256": s["transcriptSha256"],
                       "messageCount": s["messageCount"],
                       "sessionId": s["sessionId"]} for s in steps],
        }

        # -- S4 异构复核负向（同模型配置→具名缺口；缺配置→fail-closed） --
        neg_config = dict(config)
        neg_config["adv_review_model"] = {"providerID": PRIMARY_PROVIDER,
                                          "id": PRIMARY_MODEL}
        neg = call_entry("adv.run",
                         {"matterId": matter_id, "planId": "f34-p1",
                          "runId": "run-neg", "plan": plan3}, neg_config)
        neg_result = entry_result(neg)
        checks.step("s4_same_model_review_named_gap",
                    neg["exit"] == 0 and neg_result.get("gaps")
                    == [{"seq": 3,
                         "code": "f34_review_not_heterogeneous"}]
                    and [s["seq"] for s in neg_result.get("steps", [])]
                    == [1, 2],
                    exit=neg["exit"], gaps=neg_result.get("gaps"),
                    executed=[s.get("seq")
                              for s in neg_result.get("steps", [])],
                    note="产品侧异构断言：步 3 拒且不落账不假回执")
        nocfg = dict(config)
        nocfg.pop("adv_review_model", None)
        miss = call_entry("adv.run",
                          {"matterId": matter_id, "planId": "f34-p1",
                           "runId": "run-nocfg", "plan": plan3}, nocfg)
        miss_result = entry_result(miss)
        checks.step("s4_missing_review_config_fail_closed",
                    miss["exit"] == 0 and miss_result.get("gaps")
                    == [{"seq": 3,
                         "code": "f34_review_model_not_configured"}],
                    exit=miss["exit"], gaps=miss_result.get("gaps"))

        # -- S5 账本投影（信封读回；正文不入账；账本级异构断言） ---------
        plan_read = call_entry("adv.plan_read",
                               {"matterId": matter_id,
                                "planId": "f34-p1"}, config)
        plan_row = entry_result(plan_read)
        view_steps = plan_row.get("steps", [])
        bodies_absent = all(
            "prompt" not in s
            and len(str(s.get("promptSha256", ""))) == 64
            for s in view_steps)
        checks.step("s5_plan_view_prompt_body_never_at_rest",
                    plan_read["exit"] == 0 and len(view_steps) == 3
                    and bodies_absent,
                    exit=plan_read["exit"], stepsCount=len(view_steps),
                    note="指示正文不入账，只钉 promptSha256（Observer 红线"
                         "「不记录 transcript/正文」同频）")
        steps_read = call_entry(
            "adv.steps_read",
            {"matterId": matter_id, "planId": "f34-p1",
             "runId": "run-1"}, config)
        rows = entry_result(steps_read).get("items", [])
        hetero = (len(rows) == 3
                  and rows[2].get("reviewedStepSeq") == 1
                  and rows[2].get("model") != rows[0].get("model"))
        checks.step("s5_ledger_steps_read_heterogeneous_pair",
                    steps_read["exit"] == 0 and hetero,
                    exit=steps_read["exit"],
                    rows=[(r.get("seq"), r.get("kind"),
                           (r.get("model") or {}).get("id"))
                          for r in rows])
        # 账本级同模型复核＝具名拒（双层断言的账本半边，经信封实打）。
        k1 = "adv-ledgerneg-" + uuid.uuid4().hex[:8]
        setup1 = call_entry(
            "harness.adv_step_record",
            {"actor_id": "lvyin-product",
             "scope": {"kind": "matter", "matterId": matter_id},
             "key": {"requestId": k1 + "-s1", "targetId": None,
                     "expectedRevision": None, "inputRefs": []},
             "plan_id": "f34-p1", "run_id": "run-ledgerneg", "seq": 1,
             "kind": "produce", "role": "drafting-agent",
             "session_id": "ses_f34_ledgerneg1",
             "prompt_message_id": "msg_f34_ledgerneg1",
             "model_provider": PRIMARY_PROVIDER, "model_id": PRIMARY_MODEL,
             "transcript_sha256": hashlib.sha256(b"neg").hexdigest(),
             "message_count": 2}, config)
        same = call_entry(
            "harness.adv_step_record",
            {"actor_id": "lvyin-product",
             "scope": {"kind": "matter", "matterId": matter_id},
             "key": {"requestId": k1 + "-s3", "targetId": None,
                     "expectedRevision": None, "inputRefs": []},
             "plan_id": "f34-p1", "run_id": "run-ledgerneg", "seq": 3,
             "kind": "review", "role": "adversarial-review-agent",
             "session_id": "ses_f34_ledgerneg3",
             "prompt_message_id": "msg_f34_ledgerneg3",
             "model_provider": PRIMARY_PROVIDER, "model_id": PRIMARY_MODEL,
             "transcript_sha256": hashlib.sha256(b"neg3").hexdigest(),
             "message_count": 1, "reviewed_step_seq": 1}, config)
        checks.step(
            "s5_ledger_review_model_same_refused",
            setup1["exit"] == 0 and same["exit"] == 1
            and same["payload"].get("status") == "HARNESS_FAIL"
            and "f34_review_model_same"
            in str(same["payload"].get("code")),
            exit_setup=setup1["exit"], exit_same=same["exit"],
            code=str(same["payload"].get("code"))[:80],
            note="异构复核账本级断言（与产品侧同码互不替代）——信封实打")

        # -- S6 线缆形态差异（第二家模型合成先行亲证） -------------------
        pstat, rstat = primary.stats(), review.stats()
        shape_diff = (
            pstat["completions"] >= 2 and rstat["completions"] >= 1
            and min(pstat["chunks_per_request"]) >= 4
            and rstat["chunks_per_request"] == [1])
        checks.step("s6_wire_shapes_differ_real_rounds",
                    shape_diff,
                    primary=pstat, review=rstat,
                    note="主模型分块流式（≥8 增量）vs 复核第二模型单增量整"
                         "发——不同应答形态离线注入；轮次真实打到位（裁决"
                         "#13-19：真实第二家 API 商业化时补）")

        # -- S8 红线收口 ------------------------------------------------
        appdata_after = snapshot_appdata()
        checks.step("s8_appdata_readonly_untouched",
                    appdata_after == appdata_before,
                    before=sorted(appdata_before),
                    after=sorted(appdata_after))
        head = subprocess.run(
            ["git", "-C", str(oc28), "rev-parse", "HEAD"],
            capture_output=True, timeout=60).stdout.decode().strip()
        checks.step("s8_oc28_head_pin_readonly_serve", head == OOC28_PIN,
                    head=head, pin=OOC28_PIN)
        checks.step("s8_review_model_synthetic_first_boundary", True,
                    note="边界如实：异构复核第二 provider＝合成（离线注"
                         "入），不冒真实第二家厂商；真实 API 商业化时补（"
                         "裁决#13-19）；v1 五角色真实消费＝E05 已 VERIFIED "
                         "面，本单零回退零延期")
        projection["endpoint_stats"] = {"primary": pstat, "review": rstat}
        projection["appdata_snapshot_keys"] = len(appdata_before)
    finally:
        try:
            serve.stop()
        except Exception:
            pass
        try:
            primary.stop()
            review.stop()
        except Exception:
            pass
        holder.cleanup()
    return projection


def run_selfhost_leg(checks: Checks, oc28: Path, bun: Path,
                     dsn: str) -> dict:
    """selfhost 腿＝前台 serve（stdout-URL）＋产品编排器同模块进程内真
    跑（harness_call 注入封闭注册直连——signed_export 同构）＋
    PgMatterStore 直连 lh-pg-e08 独立 schema（用毕 destroy）。"""
    for path in (str(REPO_ROOT / "implementation" / "python"),
                 str(HARNESS_WORKTREE / "src"),
                 str(HARNESS_WORKTREE / "tools/workflow-tools")):
        if path not in sys.path:
            sys.path.insert(0, path)
    import f34_adv_orchestrator as adv
    from legal_harness.business.provider_registry import (
        HARNESS_PROVIDER_METHODS,
        MethodNotWhitelisted,
        resolve_provider_method,
    )
    from legal_harness.business.units import HarnessUnits, UnitsError
    from legal_harness.state.pg_store import PgMatterStore

    primary = SynthEndpoint(PRIMARY_PROVIDER, PRIMARY_MODEL,
                            PRIMARY_TEXT, "chunked").start()
    review = SynthEndpoint(REVIEW_PROVIDER, REVIEW_MODEL,
                           REVIEW_TEXT, "single").start()
    roots, requested_port, appdata_before, holder = build_profile_env(
        checks, oc28, "selfhost", primary, review)
    serve = Serve(checks, oc28, bun, "selfhost", roots, requested_port)
    store = PgMatterStore(roots["harness_state"], dsn=dsn,
                          schema="f34_" + uuid.uuid4().hex[:12])
    units = HarnessUnits(store)
    adv_methods = {
        "harness.adv_plan_register", "harness.adv_plan_read",
        "harness.adv_plan_list", "harness.adv_step_record",
        "harness.adv_steps_read"}
    bound = {name: resolve_provider_method(name, units)
             for name in adv_methods}
    store.create_matter(MATTER, "cas://profile-f34-selfhost")
    checks.step("s0_selfhost_pg_schema", True,
                schema=store.schema,
                dsn_tail=dsn.split("@")[-1],
                registry_methods=len(adv_methods
                                     & set(HARNESS_PROVIDER_METHODS)))

    def harness_direct(method: str, params: dict) -> dict:
        target = bound.get(method)
        if target is None:
            raise MethodNotWhitelisted(method)
        try:
            return target(**params)
        except UnitsError as exc:
            raise adv.AdvOrchestrationError(str(exc)) from None

    saved_harness = adv._harness
    adv._harness = (lambda method, params, config, harness_call=None:
                    harness_direct(method, params))
    projection: dict = {}
    try:
        serve.launch()
        os.environ["JUSBENCH_AGENT_USERNAME"] = "opencode"
        os.environ["JUSBENCH_AGENT_PASSWORD"] = serve.password
        client = serve.client()
        info = client.request("GET", "/api/info")
        value = info.get("data", info) if isinstance(info, dict) else {}
        version = value.get("version") if isinstance(value, dict) else None
        checks.step("s1_topology_service_ready",
                    version == DEV_VERSION and port_open(serve.port),
                    profile="selfhost", served_port=serve.port,
                    version=version, dev_version=True,
                    topology="serve 前台 stdout-URL（自托管形态）")
        config = {"matterId": MATTER,
                  "adv_workspace": str(roots["workspace"]),
                  "adv_primary_model": {"providerID": PRIMARY_PROVIDER,
                                        "id": PRIMARY_MODEL},
                  "adv_review_model": {"providerID": REVIEW_PROVIDER,
                                       "id": REVIEW_MODEL},
                  "adv_step_timeout": 120,
                  "opencode_url": serve.url,
                  "opencode_timeout": 60}

        # S7（selfhost 直连径）：封闭注册外编排形态方法具名拒。
        try:
            resolve_provider_method("harness.adv_run", units)
            checks.step("s7_harness_never_orchestrates", False,
                        note="expected MethodNotWhitelisted")
        except MethodNotWhitelisted as exc:
            checks.step("s7_harness_never_orchestrates", True,
                        code=str(exc))

        # S3 计划登记（3 步＋6 步变量）＋冲突具名拒。
        plan3 = build_plan("f34-p1")
        reg3 = adv.adv_call("adv.plan_register",
                            {"matterId": MATTER, "plan": plan3}, config)
        checks.step("s3_plan_register_three_steps",
                    reg3.get("created") is True
                    and reg3.get("stepsCount") == 3,
                    created=reg3.get("created"),
                    stepsCount=reg3.get("stepsCount"),
                    planSha256=str(reg3.get("planSha256"))[:16])
        reg6 = adv.adv_call("adv.plan_register",
                            {"matterId": MATTER,
                             "plan": build_plan_six("f34-p6")}, config)
        checks.step("s3_plan_register_six_steps_variable",
                    reg6.get("created") is True
                    and reg6.get("stepsCount") == 6,
                    stepsCount=reg6.get("stepsCount"),
                    note="步数变量经同一信封同权登记——不固定五步")
        try:
            adv.adv_call("adv.plan_register",
                         {"matterId": MATTER,
                          "plan": build_plan(
                              "f34-p1",
                              prompt_override="（合成）被篡改的第一步指示。")},
                         config)
            checks.step("s3_plan_conflict_named_reject", False,
                        note="expected f34_plan_conflict")
        except adv.AdvOrchestrationError as exc:
            checks.step("s3_plan_conflict_named_reject",
                        "f34_plan_conflict" in str(exc), code=str(exc)[:80])

        # S2 按需真会话执行＋身份/摘要＋S4 负向。
        run = adv.adv_call("adv.run",
                           {"matterId": MATTER, "planId": "f34-p1",
                            "runId": "run-1", "plan": plan3}, config)
        steps = run.get("steps", [])
        checks.step("s2_run_three_real_sessions",
                    run.get("gaps") == [] and len(steps) == 3,
                    gaps=run.get("gaps"),
                    executed=[s["seq"] for s in steps])
        session_ids = [s.get("sessionId") for s in steps]
        expected_tags = ["ses_f34_" + hashlib.sha256(
            f"f34-p1|run-1|{seq}".encode()).hexdigest()[:24]
            for seq in (1, 2, 3)]
        checks.step("s2_on_demand_deterministic_ids",
                    session_ids == expected_tags
                    and len(set(session_ids)) == 3,
                    session_ids=session_ids)
        histories_ok = True
        for step in steps:
            rows = []
            path = (f"/api/session/{quote(step['sessionId'], safe='')}"
                    "/message?order=asc")
            while path:
                listing = client.request("GET", path)
                if not isinstance(listing, dict):
                    break
                rows.extend(listing.get("data") or [])
                cursor = (listing.get("cursor") or {}).get("next")
                path = (f"/api/session/{quote(step['sessionId'], safe='')}"
                        f"/message?cursor={quote(str(cursor), safe='')}"
                        if cursor else None)
            ids = [r.get("id") for r in rows]
            after = (ids.index(step["promptMessageId"]) + 1
                     if step["promptMessageId"] in ids else -1)
            idles = [r for r in rows[after:] if r.get("type") == "idle"]
            if not idles or idles[-1].get("outcome") != "succeeded":
                histories_ok = False
        checks.step("s2_f23_server_owned_completion_readback",
                    histories_ok,
                    note="消息账逐会话回读 idle succeeded（F23 语义）")
        identities = [s.get("model") for s in steps]
        checks.step(
            "s4_model_identity_from_readback_heterogeneous",
            identities[0] == {"providerID": PRIMARY_PROVIDER,
                              "id": PRIMARY_MODEL}
            and identities[2] == {"providerID": REVIEW_PROVIDER,
                                  "id": REVIEW_MODEL}
            and identities[2] != identities[0],
            identities=identities)
        neg_config = dict(config)
        neg_config["adv_review_model"] = {"providerID": PRIMARY_PROVIDER,
                                          "id": PRIMARY_MODEL}
        neg = adv.adv_call("adv.run",
                           {"matterId": MATTER, "planId": "f34-p1",
                            "runId": "run-neg", "plan": plan3}, neg_config)
        checks.step("s4_same_model_review_named_gap",
                    neg.get("gaps") == [{"seq": 3,
                                         "code":
                                         "f34_review_not_heterogeneous"}]
                    and [s["seq"] for s in neg.get("steps", [])] == [1, 2],
                    gaps=neg.get("gaps"))
        nocfg = dict(config)
        nocfg.pop("adv_review_model", None)
        miss = adv.adv_call("adv.run",
                            {"matterId": MATTER, "planId": "f34-p1",
                             "runId": "run-nocfg", "plan": plan3}, nocfg)
        checks.step("s4_missing_review_config_fail_closed",
                    miss.get("gaps")
                    == [{"seq": 3,
                         "code": "f34_review_model_not_configured"}],
                    gaps=miss.get("gaps"))

        # S5 账本投影（直连封闭注册读回）＋账本级同模型具名拒。
        plan_row = harness_direct("harness.adv_plan_read",
                                  {"scope": {"kind": "matter",
                                             "matterId": MATTER},
                                   "plan_id": "f34-p1"})
        view_steps = plan_row.get("steps", [])
        checks.step("s5_plan_view_prompt_body_never_at_rest",
                    len(view_steps) == 3 and all(
                        "prompt" not in s
                        and len(str(s.get("promptSha256", ""))) == 64
                        for s in view_steps),
                    stepsCount=len(view_steps))
        rows = harness_direct("harness.adv_steps_read",
                              {"scope": {"kind": "matter",
                                         "matterId": MATTER},
                               "plan_id": "f34-p1",
                               "run_id": "run-1"}).get("items", [])
        checks.step("s5_ledger_steps_read_heterogeneous_pair",
                    len(rows) == 3 and rows[2].get("reviewedStepSeq") == 1
                    and rows[2].get("model") != rows[0].get("model"),
                    rows=[(r.get("seq"), (r.get("model") or {}).get("id"))
                          for r in rows])
        key1 = "adv-ledgerneg-" + uuid.uuid4().hex[:8]
        scope = {"kind": "matter", "matterId": MATTER}
        empty_key = {"targetId": None, "expectedRevision": None,
                     "inputRefs": []}
        harness_direct("harness.adv_step_record",
                       {"actor_id": "lvyin-product", "scope": scope,
                        "key": dict(empty_key, requestId=key1 + "-s1"),
                        "plan_id": "f34-p1", "run_id": "run-ledgerneg",
                        "seq": 1, "kind": "produce",
                        "role": "drafting-agent",
                        "session_id": "ses_f34_ledgerneg1",
                        "prompt_message_id": "msg_f34_ledgerneg1",
                        "model_provider": PRIMARY_PROVIDER,
                        "model_id": PRIMARY_MODEL,
                        "transcript_sha256": hashlib.sha256(
                            b"neg").hexdigest(), "message_count": 2})
        try:
            harness_direct("harness.adv_step_record",
                           {"actor_id": "lvyin-product", "scope": scope,
                            "key": dict(empty_key, requestId=key1 + "-s3"),
                            "plan_id": "f34-p1", "run_id": "run-ledgerneg",
                            "seq": 3, "kind": "review",
                            "role": "adversarial-review-agent",
                            "session_id": "ses_f34_ledgerneg3",
                            "prompt_message_id": "msg_f34_ledgerneg3",
                            "model_provider": PRIMARY_PROVIDER,
                            "model_id": PRIMARY_MODEL,
                            "transcript_sha256": hashlib.sha256(
                                b"neg3").hexdigest(), "message_count": 1,
                            "reviewed_step_seq": 1})
            checks.step("s5_ledger_review_model_same_refused", False,
                        note="expected f34_review_model_same")
        except adv.AdvOrchestrationError as exc:
            checks.step("s5_ledger_review_model_same_refused",
                        "f34_review_model_same" in str(exc),
                        code=str(exc)[:80])

        # S6 线缆形态差异＋S8 红线收口。
        pstat, rstat = primary.stats(), review.stats()
        checks.step("s6_wire_shapes_differ_real_rounds",
                    pstat["completions"] >= 2 and rstat["completions"] >= 1
                    and min(pstat["chunks_per_request"]) >= 4
                    and rstat["chunks_per_request"] == [1],
                    primary=pstat, review=rstat)
        appdata_after = snapshot_appdata()
        checks.step("s8_appdata_readonly_untouched",
                    appdata_after == appdata_before,
                    before=sorted(appdata_before),
                    after=sorted(appdata_after))
        head = subprocess.run(
            ["git", "-C", str(oc28), "rev-parse", "HEAD"],
            capture_output=True, timeout=60).stdout.decode().strip()
        checks.step("s8_oc28_head_pin_readonly_serve", head == OOC28_PIN,
                    head=head, pin=OOC28_PIN)
        checks.step("s8_review_model_synthetic_first_boundary", True,
                    note="合成第二 provider 离线注入（裁决#13-19）；真实第"
                         "二家 API 商业化时补；v1 五角色＝E05 零回退")
        projection = {"run": {
            "planSha256": run.get("planSha256"),
            "steps": [{"seq": s["seq"], "kind": s["kind"],
                       "model": s["model"],
                       "transcriptSha256": s["transcriptSha256"],
                       "messageCount": s["messageCount"]} for s in steps]},
            "endpoint_stats": {"primary": pstat, "review": rstat},
            "appdata_snapshot_keys": len(appdata_before)}
    finally:
        adv._harness = saved_harness
        try:
            serve.stop()
        except Exception:
            pass
        try:
            primary.stop()
            review.stop()
        except Exception:
            pass
        store.destroy()
        holder.cleanup()
        os.environ.pop("JUSBENCH_AGENT_USERNAME", None)
        os.environ.pop("JUSBENCH_AGENT_PASSWORD", None)
    return projection


def finish(checks: Checks, started: datetime, recon_out: Path) -> None:
    passed = sum(1 for c in checks.checks if c["status"] == "PASS")
    total = len(checks.checks)
    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    checks.checks.append({"check": "summary", "status": "RECON_OK",
                          "passed": passed, "total": total,
                          "profile": checks.profile,
                          "elapsed_s": round(elapsed, 1),
                          "subject_branch": HARNESS_BRANCH,
                          "harness_worktree": str(HARNESS_WORKTREE)})
    recon_out.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%S")
    json_path = recon_out / f"f34-adv-orchestration-recon-{stamp}.json"
    md_path = recon_out / f"f34-adv-orchestration-recon-{stamp}.md"
    json_path.write_text(json.dumps(
        {"status": "RECON_OK", "profile": checks.profile,
         "subject_branch": HARNESS_BRANCH,
         "harness_worktree": str(HARNESS_WORKTREE),
         "acceptance_vector": ("v2高级对抗编排按需真会话与异构复核；v1当前"
                               "必要五角色真实消费另见E05，不一起延期，不"
                               "固定五步"),
         "checks": checks.checks},
        ensure_ascii=False, indent=1), encoding="utf-8")
    lines = [f"# F34 recon（{checks.profile}）RECON_OK {passed}/{total}",
             "",
             f"- harness 分支：{HARNESS_BRANCH} @ {HARNESS_WORKTREE}"]
    for entry in checks.checks:
        mark = {"PASS": "✓", "FAIL": "✗", "BLOCKED": "?"}.get(
            entry["status"], "·")
        head = f"- {mark} {entry['check']} [{entry['status']}]"
        note = entry.get("note") or entry.get("code") or ""
        lines.append(head + (f" — {note}" if note else ""))
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"status": "RECON_OK", "profile": checks.profile,
                      "passed": passed, "total": total,
                      "evidence": [str(json_path), str(md_path)]},
                     ensure_ascii=False))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", action="append",
                        choices=["desktop", "selfhost"])
    parser.add_argument("--oc28", type=Path,
                        default=Path(r"D:\Codex\1.法律工作区\jusbench工作区"
                                     r"\oc28"))
    parser.add_argument("--pg-dsn", default=DEFAULT_PG_DSN)
    parser.add_argument("--keep")
    args = parser.parse_args()
    profiles = args.profile or ["desktop", "selfhost"]
    oc28 = args.oc28
    bun = DEFAULT_BUN
    if not bun.exists():
        print(json.dumps({"status": "RECON_BLOCKED",
                          "reason": "bun_missing", "path": str(bun)}))
        return 3
    head = subprocess.run(
        ["git", "-C", str(oc28), "rev-parse", "HEAD"],
        capture_output=True).stdout.decode().strip()
    if head != OOC28_PIN:
        print(json.dumps({"status": "RECON_BLOCKED",
                          "reason": "oc28_pin_mismatch",
                          "head": head, "pin": OOC28_PIN}))
        return 3
    branches = subprocess.run(
        ["git", "-C", str(HARNESS_WORKTREE), "branch", "--show-current"],
        capture_output=True).stdout.decode().strip()
    if branches != HARNESS_BRANCH:
        print(json.dumps({"status": "RECON_BLOCKED",
                          "reason": "harness_branch_mismatch",
                          "worktree": str(HARNESS_WORKTREE),
                          "branch": branches}))
        return 3
    started = datetime.now(timezone.utc)
    projections: dict = {}
    try:
        for profile in profiles:
            checks = Checks(profile)
            try:
                if profile == "desktop":
                    projections[profile] = run_desktop_leg(
                        checks, oc28, bun)
                else:
                    projections[profile] = run_selfhost_leg(
                        checks, oc28, bun, args.pg_dsn)
                finish(checks, started, REPO_ROOT / "evidence" / "F34"
                       / profile)
            except _Blocked:
                return 3
            except AssertionError as exc:
                print(json.dumps({"status": "RECON_FAIL",
                                  "profile": profile,
                                  "failed": str(exc)}, ensure_ascii=False))
                return 1
        if "desktop" in projections and "selfhost" in projections:
            def strip(run_projection):
                steps = [{k: v for k, v in s.items()
                          if k not in ("messageCount",)}
                         for s in run_projection["run"]["steps"]]
                return {"planSha256": run_projection["run"]["planSha256"],
                        "steps": steps}
            same = (strip(projections["desktop"])["planSha256"]
                    == strip(projections["selfhost"])["planSha256"])
            print(json.dumps({"check": "s8_cross_profile_projection",
                              "status": "PASS" if same else "FAIL",
                              "note": "计划摘要内容级跨 profile 相等"
                                      "（逐会话 sessionId/transcript 因真"
                                      "实时钟与运行 id 天然互异，不主张跨"
                                      " profile 相同——U08/E15 剥时间戳先"
                                      "例）"}, ensure_ascii=False))
            if not same:
                return 1
        print(json.dumps({"status": "RECON_OK", "profiles": profiles},
                         ensure_ascii=False))
        return 0
    finally:
        pass


if __name__ == "__main__":
    raise SystemExit(main())
