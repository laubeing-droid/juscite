# -*- coding: utf-8 -*-
"""F01＋F21 核心服务闭包与干净启动触发回读对账（工单 W3-U01，08§2 B3 全
v1 行触发回读首批）。

对账对象（台账 acceptance-ledger F01-desktop / F21-desktop /
F21-selfhost 三行；17 卡 F01/F21；06 V7-01/V7-21）：

  F01＝干净 Windows 启动独立选定核心 profile 与 Python 服务、真实业务结果
  回读、关窗/退出服务分义、状态持久、保 Python 单写者及显式 cwd（17 卡
  F01 落点＝implementation/patches/001;002＋上游 app/desktop——本单只验收
  该既有落点的运行行为，零新增补丁、oc28 零改动）。
  F21＝固定 OpenCode v2.0.28 原生服务/client、专属 service/data 根、显式
  事件持久化/版本校验、真实会话 inbox/继续/分叉/中断/角色结果，不并行双
  核。s0_smoke 已证创建/持久/停止/恢复（00-总协调 §2.1）；**分叉与中断断
  言本单补**（分叉端点＝oc28 packages/protocol/src/groups/session.ts:313
  POST /api/session/:id/fork{before?}；中断＝同文件 :746 POST interrupt，
  interrupted:true/false）。

双 profile：
  desktop＝产品隔离根 %APPDATA%\\Juscite{state,data,config,cache}＋固定
  端口 43127＋注册 state/opencode/service-local.json（S0/T07 产品拓扑）；
  服务未监听时由本驱动按产品拓扑**干净启动**（显式 cwd＝oc28、
  OPENCODE_DISABLE_MODELS_FETCH=1），验收后**显式退出→重启→回读**，收尾
  保持服务在位（与既有常驻形态一致）。
  selfhost＝专属临时 service/data/config 根（%TEMP%，F21"专属根"）＋独立
  端口；BYOK 配置自产品 config **只读复制**（U48 先例，key 不打印不入
  git）；全程证明产品根零触碰（产品 DB/注册/配置前后一致）。

断言分组（每 profile 同构）：
  A 干净启动与核心 profile 独立选定（拓扑/注册/版本双轨 F-4/隔离根）
  B 真实业务结果回读＋会话继续（DeepSeek BYOK 真轮次，合成材料事实核对；
    第二轮无附件仅凭会话上下文作答＝继续）
  C 会话分叉（全量 fork 与 before 边界 fork；子代血统 fork.sessionID=父；
    子会话可用——s0_smoke 未覆盖，本单补）
  D 真实中断（在飞轮次 interrupt=true→文本冻结→会话可继续——s0_smoke 仅
    空闲会话 transport 探测，本单补真实在飞中断）
  E 关窗/退出服务分义＋状态持久＋单写者＋显式 cwd（断连≠停/无壳独立存
    活/单监听单进程＋端口排他=不并行双核/taskkill 显式退出＝真停/停机窗
    口 DB 落盘事件与角色行/重启后逐字回读）
  F 纪律（Python 3.12 规则记录、合成材料边界、事件持久化观察面）

轮次定位纪律：服务端消息 id 由事件派生（oc28 message-updater.ts
fromEvent），caller id 不作匹配键——每轮 prompt 嵌入唯一定位标记
[#w3u01t1] 等，按 user 消息文本定位轮次起点（确定性，不猜 id）。

红线：全程合成材料；%APPDATA%\\JusBench（v6 遗留）零触碰——本驱动所有
读写根均为 Juscite 产品根或 %TEMP%，结构断言拒绝任何含 "JusBench" 的路
径；产品 DB 只以**字节复制件**打开（原件只 copy 不 open）；金额 Decimal
不涉本面；不 push 不 PR。

用法：
  python -X utf8 tools/PENDING_OWNER_f01_f21_desktop_closure_recon.py ^
      --profile desktop --profile selfhost [--workspace DIR]

发行形态（W3-U34，F01-desktop「完整 v1 发行」闭包；08§2 B3 后段）：
  --release-cli <安装目录>/resources/opencode-cli.exe 时 desktop profile 切
  发行形态：服务由 NSIS 安装物（W3-U22 冻结 sha256 13feaf18…，e01 §9）的打
  包壳拉起（bundled CLI，版本=构建期常量 0.0.0-dev-21102——env 不可改，
  F-4 双轨记录实值不冒 pin）；注册文件按 channel 择真（release=service.json，
  dev=service-local.json，陈旧跨通道副本为实测事实，活 pid 权威定胜负）；
  DB 文件名随 channel（release=opencode.db）；E6 重启经发行 CLI 二进制原路
  重启；E2 壳采样加计发行壳进程名。不给 --release-cli 时行为与 W3-U01 dev
  形态逐字节同路径。--oc28 指向发行形态部署/一次性检出（本单=026b106
  detached 一次性检出）；--unit/--evidence-suffix 只改证据标注与文件名。

退出码：0＝全部 profile RECON_OK；2＝RECON_FAIL；3＝环境缺失。
证据：evidence/F01/desktop/、evidence/F21/{desktop,selfhost}/（JSON＋MD）。
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sqlite3
import sys
import threading
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "python"))

from opencode_http import Client, TransportError  # noqa: E402

PIN = "2.0.28"
DEV_MARK_PREFIX = "2.0.28-local-"      # T07 包装器族显式版本标记
DEV_DEFAULT_PREFIX = "2.0.0-local-"    # F-4 dev 缺省版本族
# F-4 双轨第三族＝发行通道 bundled CLI 构建期常量（W3-U22/e01 §9.1 冻结事实；
# env 不可改——declare const 编译期内联）。记录实值不冒 pin。
RELEASE_BUNDLED_CLI_VERSION = "0.0.0-dev-21102"
DEV_REG_NAME = "service-local.json"    # dev channel 注册（源码跑恒 local）
RELEASE_REG_NAME = "service.json"      # release channel 注册（latest/dev/…）
RELEASE_SHELL_DEFAULT = "OpenCode Dev.exe"   # e01 §9.2 #5 productName
OC28_DEFAULT = Path(r"D:\Codex\1.法律工作区\jusbench工作区\oc28")
PRODUCT_ROOT = Path(os.environ.get("APPDATA", "")) / "Juscite"
DESKTOP_PORT = 43127
SESSION_PREFIX = {"desktop": "ses_w3u01d_", "selfhost": "ses_w3u01s_"}
MSG_PREFIX = {"desktop": "msg_w3u01d_", "selfhost": "msg_w3u01s_"}
TURN_WINDOW = 240.0
DELIVER_WINDOW = 90.0

MATERIAL_REL = Path("materials") / "合成材料-合同摘要.txt"
# 合成材料钉定事实（回答核对 token；容许千分位逗号差异）
FACT_AMOUNT = "123456.78"
FACT_PENALTY = ("万分之五", "0.05%", "0.05％")
FACT_TERM = "30日"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def norm(text: str) -> str:
    return (text or "").replace(",", "").replace("，", "").replace(" ", "")


class Recon:
    def __init__(self, profile: str):
        self.profile = profile
        self.checks: list = []
        self.meta: dict = {}

    def check(self, name: str, ok, **facts) -> bool:
        entry = {"check": name, "status": "PASS" if ok else "FAIL", **facts}
        self.checks.append(entry)
        print(json.dumps(entry, ensure_ascii=False), flush=True)
        return bool(ok)

    def observe(self, name: str, **facts) -> None:
        entry = {"check": name, "status": "INFO", **facts}
        self.checks.append(entry)
        print(json.dumps(entry, ensure_ascii=False), flush=True)

    @property
    def failed(self) -> int:
        return sum(1 for c in self.checks if c["status"] == "FAIL")


# ------------------------------------------------------------------ #
# 进程/端口/注册原语（子进程输出按字节捕获再解码，中文控制台不炸）
# ------------------------------------------------------------------ #

def run_cmd(argv: list, timeout: float = 30, cwd: str | None = None) -> str:
    proc = subprocess.run(argv, capture_output=True, timeout=timeout, cwd=cwd)
    return proc.stdout.decode("utf-8", errors="replace") + \
        proc.stderr.decode("utf-8", errors="replace")


def listener_pids(port: int) -> list:
    out = run_cmd(["netstat", "-ano"])
    pids = set()
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[3] == "LISTENING" and \
                parts[1].endswith(":%d" % port):
            pids.add(parts[4])
    return sorted(pids)


def port_responsive(url: str, headers: dict, timeout: float = 5) -> bool:
    try:
        Client(url, headers=headers, timeout=timeout).request("GET", "/api/info")
        return True
    except (TransportError, ValueError):
        return False


def connect_closed(port: int) -> bool:
    """真连一次服务端口再立刻断开（关窗分义①：断连对服务必须是 no-op）。"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5)
    try:
        sock.connect(("127.0.0.1", port))
        return True
    finally:
        sock.close()


def process_info(pid: str) -> dict:
    out = run_cmd(["powershell", "-NoProfile", "-Command",
                   "Get-CimInstance Win32_Process -Filter 'ProcessId=%s' | "
                   "Select-Object Name,ParentProcessId | ConvertTo-Json" % pid],
                  timeout=60)
    try:
        data = json.loads(out)
        if isinstance(data, list):
            data = data[0] if data else {}
    except json.JSONDecodeError:
        data = {}
    return {"name": data.get("Name"),
            "parentPid": str(data.get("ParentProcessId", ""))}


def process_gone(pid: str) -> bool:
    out = run_cmd(["tasklist", "/FI", "PID eq %s" % pid, "/NH"])
    return pid not in out


def electron_shell_count() -> int:
    """真桌面壳进程数（electron.exe 精确名）——关窗分义②的"无壳"侧。
    首轮实测两族误匹配不入判定：命令行含 Juscite 的宿主自噪声、以及并行
    单元的 electron-builder.exe（构建工具非运行壳）。"""
    out = run_cmd(["powershell", "-NoProfile", "-Command",
                   "(Get-CimInstance Win32_Process | Where-Object { "
                   "$_.Name -eq 'electron.exe' } | Measure-Object).Count"],
                  timeout=60)
    digits = re.findall(r"(\d+)", out.strip().splitlines()[-1] if out.strip() else "")
    return int(digits[-1]) if digits else -1


def _release_shell_count(shell_name: str) -> int:
    """发行壳进程数（NSIS productName 精确名，W3-U34）。electron.exe 计数
    对打包壳失真（打包后进程名随 productName），发行形态一并采样。"""
    out = run_cmd(["powershell", "-NoProfile", "-Command",
                   "(Get-CimInstance Win32_Process | Where-Object { "
                   "$_.Name -eq '%s' } | Measure-Object).Count" % shell_name],
                  timeout=60)
    digits = re.findall(r"(\d+)", out.strip().splitlines()[-1] if out.strip() else "")
    return int(digits[-1]) if digits else -1


def stop_service(pid: str) -> dict:
    run_cmd(["taskkill", "/F", "/T", "/PID", pid])
    deadline = time.time() + 20
    gone = False
    while time.time() < deadline:
        if process_gone(pid):
            gone = True
            break
        time.sleep(1)
    return {"processGone": gone}


# ------------------------------------------------------------------ #
# 服务生命周期（产品拓扑复刻：显式 cwd＋XDG 根＋禁 models.dev 轮询）
# ------------------------------------------------------------------ #

def build_service_env(state: Path, data: Path, config: Path, cache: Path,
                      version_mark: str) -> dict:
    env = dict(os.environ)
    env.update({
        "XDG_STATE_HOME": str(state),
        "XDG_DATA_HOME": str(data),
        "XDG_CONFIG_HOME": str(config),
        "XDG_CACHE_HOME": str(cache),
        "OPENCODE_DISABLE_MODELS_FETCH": "1",   # oc28 server-process.ts:113
        "OPENCODE_CHANNEL": "local",
        "OPENCODE_VERSION": version_mark,
    })
    return env


def spawn_service(oc28: Path, bun: Path, port: int, env: dict, log_path: Path):
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = open(log_path, "ab")
    try:
        return subprocess.Popen(
            [str(bun), "run", "--cwd", "packages/cli",
             "--define=OPENCODE_VERSION=process.env.OPENCODE_VERSION",
             "src/index.ts", "serve", "--service",
             "--hostname", "127.0.0.1", "--port", str(port)],
            cwd=str(oc28), env=env, stdout=log, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW)
    finally:
        log.close()


def wait_registration(candidates: list, timeout: float = 150,
                      expect_pid: str | None = None):
    """等注册文件可读且 /api/info 可用；expect_pid 给定时以 /api/info 的
    pid 为活进程权威（注册文件由服务自写、重写可能滞后，首轮/四轮实测
    两类竞态：陈旧注册先到、并行单元改写注册）。
    candidates＝按优先序的注册文件候选（W3-U34：跨通道陈旧副本为实测
    事实——release 轮里 dev 旧 service-local.json 指向已停 pid——以能答
    /api/info 且 pid 匹配者为活注册）。返回（胜出路径, reg, headers,
    client, info）。"""
    deadline = time.time() + timeout
    last_error = None
    while time.time() < deadline:
        for reg_path in candidates:
            if not reg_path.exists():
                continue
            try:
                reg = json.loads(reg_path.read_text(encoding="utf-8"))
                headers = auth_of(reg)
                client = Client(reg["url"], headers=headers, timeout=10)
                info = client.request("GET", "/api/info")
                info_value = info.get("data", info) if isinstance(info, dict) else {}
                live_pid = str(info_value.get("pid", ""))
                if expect_pid is not None and live_pid != expect_pid:
                    last_error = "live_pid_pending:%s!=%s(reg=%s@%s)" % (
                        live_pid, expect_pid, reg.get("pid"), reg_path.name)
                    continue
                if expect_pid is not None and str(reg.get("pid")) != live_pid:
                    # 注册文件自写滞后于监听（实测）——等它追平活 pid 再返回。
                    last_error = "registration_rewrite_pending:%s!=%s" % (
                        reg.get("pid"), live_pid)
                    continue
                return reg_path, reg, headers, client, info
            except (json.JSONDecodeError, KeyError, TransportError, ValueError) as exc:
                last_error = repr(exc)[:200]
        time.sleep(2)
    raise RuntimeError("service_registration_timeout:%s" % (last_error or candidates))


def auth_of(reg: dict) -> dict:
    return {"Authorization": "Basic " + base64.b64encode(
        ("opencode:" + reg["password"]).encode()).decode("ascii")}


# ------------------------------------------------------------------ #
# 会话原语（轮次按嵌入标记定位，不依赖服务端消息 id）
# ------------------------------------------------------------------ #

def q(sid: str) -> str:
    return quote(sid, safe="")


def fetch_messages(client: Client, sid: str) -> list:
    messages: list = []
    path = "/api/session/%s/message?order=asc" % q(sid)
    while path:
        listing = client.request("GET", path)
        if not isinstance(listing, dict):
            break
        messages.extend(listing.get("data", []))
        cursor = (listing.get("cursor") or {}).get("next")
        path = ("/api/session/%s/message?cursor=%s" % (q(sid), q(str(cursor)))
                if cursor else None)
    return messages


def message_text(message: dict) -> str:
    """user 消息文本在顶层 text 字段（v2 live 实测）；assistant 在
    content/parts 的 text 部件——两形态都取。"""
    if isinstance(message.get("text"), str):
        return message["text"]
    parts = []
    for part in message.get("content") or message.get("parts") or []:
        if isinstance(part, dict) and part.get("type") == "text" and part.get("text"):
            parts.append(part["text"])
    return "\n".join(parts)


def role_transcript(messages: list) -> list:
    out = []
    for m in messages:
        if m.get("type") in ("user", "assistant"):
            out.append((m.get("type"), message_text(m)))
    return out


def find_user_position(messages: list, marker: str) -> int | None:
    """最后一条含定位标记的 user 消息下标（确定性轮次定位）。"""
    position = None
    for index, m in enumerate(messages):
        if m.get("type") == "user" and marker in message_text(m):
            position = index
    return position


def submit_turn(client: Client, sid: str, mid: str, text: str,
                model: dict, files=None) -> None:
    body = {"id": mid, "text": text, "model": dict(model)}
    if files:
        body["files"] = files
    client.prompt(sid, body)


def await_answer(client: Client, sid: str, marker: str,
                 timeout: float = TURN_WINDOW):
    """定位标记 user 消息之后到 idle 为止的 assistant 文本（e07 同径）。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            messages = fetch_messages(client, sid)
        except TransportError:
            time.sleep(1)
            continue
        position = find_user_position(messages, marker)
        if position is not None:
            texts = []
            for m in messages[position + 1:]:
                if m.get("type") == "idle":
                    break
                if m.get("type") != "assistant":
                    continue
                texts.append(message_text(m))
            joined = "\n".join(x for x in texts if x)
            if joined.strip():
                return joined
        time.sleep(2)
    return None


def fork_session(client: Client, sid: str, before=None) -> dict:
    body = {} if before is None else {"before": before}
    resp = client.request("POST", "/api/session/%s/fork" % q(sid), body)
    data = resp.get("data", resp) if isinstance(resp, dict) else {}
    return data or {}


# ------------------------------------------------------------------ #
# DB 落盘取证（只对复制件开库；原件只做字节复制）
# ------------------------------------------------------------------ #

def copy_db(data_root: Path, workdir: Path,
            filename: str = "opencode-local.db") -> Path:
    """DB 复制件取证（原件只 copy 不 open）。文件名随 channel：
    dev(local)=opencode-local.db；release=opencode.db（database-path.ts）。"""
    src = data_root / "opencode" / filename
    target_dir = workdir / "db-copy"
    target_dir.mkdir(parents=True, exist_ok=True)
    for suffix in ("", "-wal", "-shm"):
        s = Path(str(src) + suffix)
        if s.exists():
            shutil.copy2(s, target_dir / (src.name + suffix))
    return target_dir / src.name


def db_facts(db_copy: Path, parent_sid: str, child_ids: list) -> dict:
    con = sqlite3.connect(str(db_copy))  # 复制件允许 WAL 恢复；原件零打开
    try:
        facts = {}
        row = con.execute(
            "select id, directory, title, model, parent_id, fork_session_id, "
            "fork_boundary from session_v2 where id=?",
            (parent_sid,)).fetchone()
        facts["sessionRow"] = None if row is None else {
            "id": row[0], "directory": row[1], "title": row[2],
            "model": (row[3] or "")[:200] if isinstance(row[3], str) else row[3],
            "parentId": row[4], "forkSessionId": row[5], "forkBoundary": row[6]}
        rows = con.execute(
            "select type, count(*) from session_message where session_id=? "
            "group by type", (parent_sid,)).fetchall()
        facts["messageTypes"] = {k: v for k, v in rows}
        seqs = [r[0] for r in con.execute(
            "select seq from session_message where session_id=? order by rowid",
            (parent_sid,)).fetchall()]
        facts["messageSeqMonotonic"] = seqs == sorted(seqs)
        children = {}
        for cid in child_ids:
            crow = con.execute(
                "select fork_session_id, fork_boundary from session_v2 where id=?",
                (cid,)).fetchone()
            children[cid] = None if crow is None else {
                "forkSessionId": crow[0], "forkBoundary": crow[1]}
        facts["children"] = children
        facts["eventRows"] = con.execute("select count(*) from event").fetchone()[0]
        facts["eventSequenceAggregates"] = con.execute(
            "select count(*) from event_sequence").fetchone()[0]
        facts["migrationsApplied"] = con.execute(
            "select count(*) from migration").fetchone()[0]
        facts["inboxRowsParent"] = con.execute(
            "select count(*) from session_inbox where session_id=?",
            (parent_sid,)).fetchone()[0]
        return facts
    finally:
        con.close()


# ------------------------------------------------------------------ #
# 产品根基线（selfhost 隔离证明；desktop 自身即产品根不做差分）
# ------------------------------------------------------------------ #

def _stat_of(p: Path):
    return {"size": p.stat().st_size, "mtimeNs": p.stat().st_mtime_ns} \
        if p.exists() else None


def _sha_of(p: Path):
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None


def product_baseline() -> dict:
    db = PRODUCT_ROOT / "data" / "opencode" / "opencode-local.db"
    config = PRODUCT_ROOT / "config" / "opencode" / "opencode.json"
    reg = PRODUCT_ROOT / "state" / "opencode" / "service-local.json"
    return {"db": _stat_of(db), "configSha": _sha_of(config), "reg": _stat_of(reg)}


def product_delta(baseline: dict) -> dict:
    db = PRODUCT_ROOT / "data" / "opencode" / "opencode-local.db"
    config = PRODUCT_ROOT / "config" / "opencode" / "opencode.json"
    reg = PRODUCT_ROOT / "state" / "opencode" / "service-local.json"
    db_same = _stat_of(db) == baseline.get("db")
    reg_same = _stat_of(reg) == baseline.get("reg")
    cfg_same = _sha_of(config) == baseline.get("configSha")
    return {"dbUnchanged": db_same, "registrationUnchanged": reg_same,
            "configShaUnchanged": cfg_same,
            "ok": db_same and reg_same and cfg_same,
            "rule": "selfhost 专属根隔离：产品根三面（DB/注册/配置）零变化"}


# ------------------------------------------------------------------ #
# 真实中断流（D 组）
# ------------------------------------------------------------------ #

def _turn_text(messages: list, marker: str) -> str | None:
    """定位标记轮次的 assistant 文本（未投递=None；已投递未出文本=\"\"）。"""
    position = find_user_position(messages, marker)
    if position is None:
        return None
    texts = []
    for m in messages[position + 1:]:
        if m.get("type") == "idle":
            break
        if m.get("type") == "assistant":
            t = message_text(m)
            if t:
                texts.append(t)
    return "\n".join(texts)


def _turn_end_state(messages: list, marker: str) -> dict:
    """定位轮次的终态：assistant finish＋其后首个 idle outcome（持久证据）。"""
    position = find_user_position(messages, marker)
    if position is None:
        return {}
    finish = None
    outcome = None
    for m in messages[position + 1:]:
        if m.get("type") == "assistant" and finish is None:
            finish = m.get("finish")
        if m.get("type") == "idle":
            outcome = m.get("outcome")
            break
    return {"finish": finish, "idleOutcome": outcome}


def _sse_delta_watcher(url: str, headers: dict, sid: str, holder: dict):
    """SSE /api/event 订阅：首个含本会话 id 的 session.text.delta 事件置位
    holder["delta"]（真·流式在飞信号——REST 列表只在完成时浮出消息）。"""
    from urllib.parse import urlsplit
    try:
        u = urlsplit(url)
        sock = socket.create_connection((u.hostname, u.port), timeout=15)
        auth = ""
        for value in headers.get("Authorization", "").split():
            auth = value
        req = ("GET /api/event HTTP/1.1\r\nHost: %s:%s\r\n"
               "Authorization: Basic %s\r\nAccept: text/event-stream\r\n\r\n"
               % (u.hostname, u.port, auth))
        sock.sendall(req.encode())
        buf = b""
        sock.settimeout(15)
        while not holder.get("stop"):
            try:
                chunk = sock.recv(65536)
            except socket.timeout:
                break
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                text = line.decode("utf-8", "replace").strip()
                if not text.startswith("data:"):
                    continue
                try:
                    event = json.loads(text[5:].strip())
                except json.JSONDecodeError:
                    continue
                if isinstance(event, dict) and \
                        event.get("type") == "session.text.delta" and \
                        sid in json.dumps(event):
                    holder["delta"] = True
                    holder["sample"] = json.dumps(event, ensure_ascii=False)[:200]
                    return
    except OSError as exc:
        holder["error"] = repr(exc)[:120]


def _interrupt_flow(client: Client, sid: str, profile: str, material: Path,
                    model: dict, recon: Recon, nonce: str, url: str,
                    headers: dict) -> dict:
    """在飞中断（SSE 触发）：订阅 /api/event，本会话首个 session.text.delta
    （真·流式在飞）即 interrupt——execution 已注册且正在生成，interrupted=
    true 是端点合同定义的在飞中断证明；辅以文本冻结＋终态非自然成功。
    SSE 不可用时回退完成感知轮询并如实记录触发路径。live 实测两约束：
    REST 列表只在完成时浮出 assistant 消息；首 token 延迟 0.5-5s 抖动使
    盲定时不可靠。"""
    attempts = []
    for attempt, upto in enumerate((800, 1500), start=1):
        marker = "[#w3u01i%d]" % attempt
        mid = "%si%d_%s" % (MSG_PREFIX[profile], attempt, nonce)
        holder = {"stop": False, "delta": False}
        watcher = threading.Thread(target=_sse_delta_watcher,
                                   args=(url, headers, sid, holder), daemon=True)
        watcher.start()
        time.sleep(1.0)   # SSE 连接建立
        trigger = "sse-delta"
        submit_turn(client, sid, mid,
                    "这是律引中断断言用长输出负载（合成验收，非真实案件）%s。"
                    "请逐行列出从 1 到 %d 的每个整数：每行恰一个数字，从 1 开始"
                    "连续到 %d，不省略、不解释、不加任何其他文字。"
                    % (marker, upto, upto),
                    model)
        deadline = time.time() + DELIVER_WINDOW
        while time.time() < deadline and not holder["delta"]:
            time.sleep(0.1)
        if holder["delta"]:
            resp = client.interrupt(sid)
            if isinstance(resp, dict):
                interrupted = bool(resp.get(
                    "interrupted",
                    (resp.get("data") or {}).get("interrupted")))
        else:
            # SSE 未捕获（订阅失败/事件形态变化）——回退：完成感知轮询。
            trigger = "poll-fallback"
            admitted_at = None
            interrupted = False
            while time.time() < deadline:
                try:
                    messages = fetch_messages(client, sid)
                except TransportError:
                    time.sleep(0.2)
                    continue
                if find_user_position(messages, marker) is not None:
                    if admitted_at is None:
                        admitted_at = time.time()
                    if _turn_text(messages, marker) is not None:
                        break
                    if time.time() - admitted_at >= 1.0:
                        resp = client.interrupt(sid)
                        if isinstance(resp, dict):
                            interrupted = bool(resp.get(
                                "interrupted",
                                (resp.get("data") or {}).get("interrupted")))
                        break
                time.sleep(0.15)
        holder["stop"] = True
        time.sleep(2.0)
        text_after = _turn_text(fetch_messages(client, sid), marker)
        time.sleep(3.0)
        text_frozen = _turn_text(fetch_messages(client, sid), marker)
        turn_end = _turn_end_state(fetch_messages(client, sid), marker)
        attempts.append({"attempt": attempt, "marker": marker,
                         "enumerationUpto": upto,
                         "trigger": trigger,
                         "sseError": holder.get("error"),
                         "interrupted": interrupted,
                         "charsAfter2s": None if text_after is None else len(text_after),
                         "charsFrozen5s": None if text_frozen is None else len(text_frozen),
                         "textStable": text_after == text_frozen,
                         "turnEnd": turn_end})
        if interrupted:
            break
        time.sleep(1.0)   # 上一轮收尾沉降后再起下一尝试
    last = attempts[-1] if attempts else {}
    recon.check("D1_interrupt_inflight_true",
                bool(last.get("interrupted")),
                attempts=attempts,
                rule="oc28 session.interrupt：interrupted=true＝端点合同定义的"
                     "「在飞执行被中断」（SSE 首个流式 delta 触发，失败回退完成"
                     "感知轮询并如实记录 trigger 路径）")
    recon.check("D2_turn_stops_after_interrupt",
                bool(last) and last.get("textStable") is True
                and (last.get("turnEnd") or {}).get("idleOutcome") != "succeeded",
                charsAfter2s=last.get("charsAfter2s"),
                charsFrozen5s=last.get("charsFrozen5s"),
                turnEnd=last.get("turnEnd"),
                rule="中断后该轮次文本冻结且终态非自然成功（idleOutcome≠succeeded）"
                     "＝轮次真的被停了")
    inbox = client.inbox(sid)
    inbox_value = inbox if isinstance(inbox, dict) else {}
    recon.observe("D3_inbox_after_interrupt",
                  inboxKeys=sorted(inbox_value.keys()),
                  queuedItems=len(inbox_value.get("data", []) or []),
                  note="resume=false：已入队提示保持 parked（观察面）")
    marker_next = "[#w3u01after_i]"
    submit_turn(client, sid, "%safter_i_%s" % (MSG_PREFIX[profile], nonce),
                "中断探测结束%s。只回答四个字：已可继续。" % marker_next, model)
    answer = await_answer(client, sid, marker_next)
    recon.check("D4_session_usable_after_interrupt",
                bool(answer and "已可继续" in answer),
                answerHead=(answer or "")[:60],
                rule="中断后同会话下一轮次正常完成＝会话可用性保持")
    return last


# ------------------------------------------------------------------ #
# 单 profile 全流程
# ------------------------------------------------------------------ #

def run_profile(profile: str, args, recon: Recon) -> int:
    oc28: Path = Path(args.oc28)
    bun = Path(args.bun) if args.bun else _find_bun()
    release_cli = Path(args.release_cli) if getattr(args, "release_cli", None) else None
    release_mode = profile == "desktop" and release_cli is not None
    baseline = product_baseline() if profile == "selfhost" else {}

    if profile == "desktop":
        roots = {k: PRODUCT_ROOT / k for k in ("state", "data", "config", "cache")}
        port = DESKTOP_PORT
        # 注册文件按 channel 择真（W3-U34：跨通道陈旧副本为实测事实）。
        reg_names = ([RELEASE_REG_NAME, DEV_REG_NAME] if release_mode
                     else [DEV_REG_NAME])
        reg_candidates = [roots["state"] / "opencode" / n for n in reg_names]
        reg_path = reg_candidates[0]
        version_mark = "2.0.28-local-w3u01"
        workdir = Path(tempfile.mkdtemp(prefix="w3u01-desktop-"))
        db_filename = "opencode.db" if release_mode else "opencode-local.db"
    else:
        base = Path(tempfile.mkdtemp(prefix="w3u01-selfhost-"))
        roots = {k: base / k for k in ("state", "data", "config", "cache")}
        for p in roots.values():
            p.mkdir(parents=True, exist_ok=True)
        port = _free_port()
        reg_path = roots["state"] / "opencode" / DEV_REG_NAME
        reg_candidates = [reg_path]
        version_mark = "2.0.28-local-w3u01-selfhost"
        db_filename = "opencode-local.db"   # dev spawn 恒 local channel
        workdir = base / "recon"
        workdir.mkdir(parents=True, exist_ok=True)
        # BYOK 配置只读复制进专属 config 根（U48 先例：key 不打印不入 git）
        src_cfg = PRODUCT_ROOT / "config" / "opencode" / "opencode.json"
        dst_cfg = roots["config"] / "opencode" / "opencode.json"
        dst_cfg.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src_cfg, dst_cfg)
        recon.observe("S1_byok_config_readonly_copy",
                      source=str(src_cfg), target=str(dst_cfg),
                      sourceSha256=_sha_of(src_cfg), targetSha256=_sha_of(dst_cfg),
                      keyPrinted=False,
                      note="字节等同复制；产品原件只读，U48 先例")
    expected_url = "http://127.0.0.1:%d" % port
    workspace = Path(args.workspace).resolve()
    material = workspace / MATERIAL_REL

    recon.meta.update({
        "profile": profile, "startedUtc": now_iso(),
        "oc28": str(oc28), "workspace": str(workspace),
        "expectedUrl": expected_url,
        "pythonVersion": ".".join(map(str, sys.version_info[:3])),
        "releaseMode": release_mode,
        "releaseCli": str(release_cli) if release_cli else None,
    })

    # ================= A 干净启动与核心 profile ======================== #
    already = listener_pids(port)
    started_by_recon = not already
    if started_by_recon and release_mode:
        # 发行形态的 desktop 服务必须由打包壳拉起（bundled CLI）；缺口即
        # 前提不成立（壳未起/服务未就绪）——响亮阻断，绝不静默落回 dev spawn。
        print("RECON_BLOCKED: release mode requires the packaged shell's "
              "service listening on %d (launch %s first); --release-cli=%s"
              % (port, RELEASE_SHELL_DEFAULT, release_cli))
        return 3
    if started_by_recon:
        if not bun.exists():
            print("RECON_BLOCKED: bun missing: %s" % bun)
            return 3
        if not (oc28 / "packages" / "cli" / "src" / "index.ts").exists():
            print("RECON_BLOCKED: oc28 missing: %s" % oc28)
            return 3
        env = build_service_env(roots["state"], roots["data"], roots["config"],
                                roots["cache"], version_mark)
        proc = spawn_service(oc28, bun, port, env, workdir / "service.log")
        explicit_cwd = str(oc28)
    else:
        proc = None
        explicit_cwd = None
    reg_path, reg, headers, client, info = wait_registration(
        reg_candidates, expect_pid=(str(proc.pid) if proc is not None else None))
    info_value = info.get("data", info) if isinstance(info, dict) else {}
    version = info_value.get("version")
    url = reg.get("url")
    pid = str(reg.get("pid", ""))
    reg_channel = ("release" if reg_path.name == RELEASE_REG_NAME else "dev")

    recon.check("A1_service_clean_start",
                port_responsive(url, headers),
                startedByRecon=started_by_recon,
                cleanStart=started_by_recon, pid=pid,
                explicitCwd=explicit_cwd,
                modelsFetchDisabled=True if started_by_recon else None,
                versionMark=version_mark if started_by_recon else None,
                registrationChannel=reg_channel,
                serviceSource=("packaged-shell(bundled CLI)" if release_mode
                               else "headless-standalone"),
                mode="packaged-shell-topped（NSIS 安装物打包壳拉起）" if release_mode
                     else "headless-standalone（无桌面壳参与，产品拓扑复刻）")
    recon.check("A2_registration_matches",
                url == expected_url and pid == str(reg.get("pid"))
                and listener_pids(port) == [pid],
                regPath=str(reg_path), url=url, regPid=reg.get("pid"),
                listenerPids=listener_pids(port))

    config_path = roots["config"] / "opencode" / "opencode.json"
    cfg = json.loads(config_path.read_text(encoding="utf-8-sig")) \
        if config_path.exists() else {}
    providers = cfg.get("provider") or {}
    byok = providers.get("deepseek-byok") or {}
    perms = ((cfg.get("agents") or {}).get("legal-review") or {}).get("permissions") or []
    policies = (cfg.get("experimental") or {}).get("policies") or []
    deny_first = bool(perms) and perms[0].get("effect") == "deny"
    has_key = bool((byok.get("options") or {}).get("apiKey"))
    recon.check("A3_core_profile_selected",
                "deepseek-chat" in (byok.get("models") or {})
                and cfg.get("default_agent") == "legal-review"
                and deny_first
                and any(str(p.get("resource", "")).startswith("shell")
                        for p in policies if p.get("effect") == "deny")
                and has_key,
                configPath=str(config_path),
                providers=sorted(providers.keys()),
                defaultAgent=cfg.get("default_agent"),
                denyFirstPermission=deny_first,
                policyDenyCount=sum(1 for p in policies if p.get("effect") == "deny"),
                byokModels=sorted((byok.get("models") or {}).keys()),
                apiKeyPrinted=False)

    if release_mode:
        # F-4 双轨第三族：发行通道 bundled CLI 构建期常量（W3-U22/e01 §9.1
        # 冻结事实 0.0.0-dev-21102）。与冻结值不符＝漂移信号，响亮 FAIL 记
        # 双值，绝不冒 pin。打包壳 app 版本仍是 2.0.28 pin（另一面）。
        version_ok = version == RELEASE_BUNDLED_CLI_VERSION
        recon.check("A4_version_dual_track", version_ok,
                    version=version, pin=PIN,
                    releaseBundledCliFrozen=RELEASE_BUNDLED_CLI_VERSION,
                    dev=False, channel=reg_channel,
                    rule="F-4 双轨（发行形态）：服务实值=打包 bundled CLI 构建期"
                         "常量，须与 W3-U22 冻结事实相等（漂移即信号）；记录实值"
                         "不冒 2.0.28 pin")
    else:
        version_ok = isinstance(version, str) and (
            version == PIN or version.startswith(DEV_DEFAULT_PREFIX)
            or version.startswith(DEV_MARK_PREFIX))
        recon.check("A4_version_dual_track", version_ok,
                    version=version, pin=PIN,
                    dev=(isinstance(version, str) and version != PIN),
                    rule="F-4 双轨：打包 pin 2.0.28 或 dev 2.0.x-local-*；记录实值")

    roots_ok = all("jusbench" not in str(p).lower() for p in roots.values()) \
        and "jusbench" not in str(workspace).lower()
    recon.check("A5_roots_isolation_no_v6_touch", roots_ok,
                roots={k: str(v) for k, v in roots.items()},
                workspace=str(workspace),
                note="%APPDATA%\\JusBench（v6 遗留）零引用零触碰")

    model = {"id": "deepseek-chat", "providerID": "deepseek-byok"}

    # ================= B 真实业务结果回读＋继续 ======================== #
    # caller message id＝持久唯一键（PromptConflictError 实证）——每运行 nonce
    # 唯一化，跨运行绝不复用。
    nonce = str(int(time.time()))
    sid = SESSION_PREFIX[profile] + nonce
    title = "律引 W3-U01 核心闭包（%s·合成）" % profile
    created = client.create({
        "id": sid, "title": title,
        "location": {"directory": str(workspace)},
        "model": dict(model)})
    created_value = created.get("data", created) if isinstance(created, dict) else {}
    got = client.session(sid)
    got_value = got.get("data", got) if isinstance(got, dict) else {}
    recon.check("B1_session_create_location_bound",
                created_value.get("id") == sid and got_value.get("id") == sid
                and got_value.get("title") == title,
                sessionId=sid, title=got_value.get("title"))

    marker1 = "[#w3u01t1]"
    submit_turn(client, sid, "%st1_%s" % (MSG_PREFIX[profile], nonce),
                "这是律引 W3-U01 验收（合成材料，非真实案件）%s。读附件材料后"
                "用两行回答：第一行合同总价款与付款期限；第二行逾期付款违约金"
                "计算标准。不要展开分析。" % marker1,
                model, files=[{"uri": material.as_uri(), "name": material.name}])
    answer1 = await_answer(client, sid, marker1)
    transcript1 = role_transcript(fetch_messages(client, sid))
    user_echo = any(kind == "user" and marker1 in text for kind, text in transcript1)
    recon.check("B2_real_business_result_roles",
                bool(answer1) and FACT_AMOUNT in norm(answer1)
                and any(p in answer1 for p in FACT_PENALTY)
                and FACT_TERM in norm(answer1) and user_echo,
                sessionId=sid,
                answerHead=(answer1 or "")[:200],
                amountTokenHit=bool(answer1) and FACT_AMOUNT in norm(answer1),
                penaltyTokenHit=bool(answer1) and any(p in answer1 for p in FACT_PENALTY),
                termTokenHit=bool(answer1) and FACT_TERM in norm(answer1),
                roleSequence=[k for k, _ in transcript1][:8])

    marker2 = "[#w3u01t2]"
    submit_turn(client, sid, "%st2_%s" % (MSG_PREFIX[profile], nonce),
                "只依据本会话第一轮已读的材料回答%s：合同总价款数额是多少？"
                "只回答数额本身，不要其他内容。" % marker2, model)
    answer2 = await_answer(client, sid, marker2)
    recon.check("B3_continue_in_session",
                bool(answer2) and FACT_AMOUNT in norm(answer2),
                answerHead=(answer2 or "")[:160],
                continueRule="无附件第二轮仅凭会话上下文答出第一轮材料事实")

    # ================= C 会话分叉（s0_smoke 未覆盖，本单补）============ #
    child_full = fork_session(client, sid)
    child_full_id = child_full.get("id")
    lineage_ok = False
    child_full_info = {}
    if child_full_id and child_full_id != sid:
        raw = client.session(child_full_id)
        child_full_info = raw.get("data", raw) if isinstance(raw, dict) else {}
        fork_field = child_full_info.get("fork") or {}
        parent_ref = fork_field.get("sessionID") or child_full_info.get("parentID")
        lineage_ok = parent_ref == sid
    recon.check("C1_fork_full_copy",
                bool(child_full_id) and child_full_id != sid
                and bool(child_full_info) and lineage_ok
                and "(fork" in (child_full_info.get("title") or ""),
                parentId=sid, childId=child_full_id,
                childTitle=child_full_info.get("title"),
                lineageField=("fork.sessionID"
                              if (child_full_info.get("fork") or {}).get("sessionID")
                              else ("parentID" if child_full_info.get("parentID")
                                    else "none")))

    parent_messages = fetch_messages(client, sid)
    user_ids = [m.get("id") for m in parent_messages if m.get("type") == "user"]
    boundary_before = user_ids[1] if len(user_ids) >= 2 else \
        (user_ids[0] if user_ids else None)
    child_cut = fork_session(client, sid, before=boundary_before) \
        if boundary_before else {}
    child_cut_id = child_cut.get("id")
    count_full = len(fetch_messages(client, child_full_id)) if child_full_id else -1
    count_cut = len(fetch_messages(client, child_cut_id)) if child_cut_id else -1
    count_parent = len(parent_messages)
    recon.check("C2_fork_before_boundary",
                bool(child_cut_id) and child_cut_id != child_full_id
                and 1 <= count_cut < count_full <= count_parent + 2,
                parentId=sid, beforeMessageId=boundary_before,
                childCutId=child_cut_id,
                parentMessageCount=count_parent,
                childFullMessageCount=count_full,
                childCutMessageCount=count_cut,
                rule="oc28 session.fork：before=边界消息，子代只复制边界前投影历史")

    marker3 = "[#w3u01c]"
    submit_turn(client, child_full_id, "%sc_%s" % (MSG_PREFIX[profile], nonce),
                "这是分叉子会话连通性探针（合成）%s。只回答两个字：确认。" % marker3,
                model)
    answer3 = await_answer(client, child_full_id, marker3)
    recon.check("C3_forked_child_usable", bool(answer3 and answer3.strip()),
                childId=child_full_id, answerHead=(answer3 or "")[:80])

    # ================= D 真实中断（s0_smoke 未覆盖，本单补）============ #
    _interrupt_flow(client, sid, profile, material, model, recon, nonce,
                    url, headers)

    # ================= E 关窗/退出分义＋持久＋单写者＋显式 cwd ========== #
    e1_ok = False
    try:
        e1_ok = connect_closed(port) and port_responsive(url, headers) \
            and bool(client.session(sid))
    except (OSError, TransportError):
        e1_ok = False
    recon.check("E1_disconnect_is_noop", e1_ok,
                port=port, rule="关窗分义①：UI 断连对服务必须是 no-op，会话保持")

    proc_info = process_info(pid)
    if profile == "desktop":
        # F01 关窗分义②专属断言。共享宿主上并行单元可能正驱动自家 electron
        # 壳（实测竞态）——30s 静窗重试采样，仍不静即如实 FAIL。
        # W3-U34 发行形态：electron.exe 计数对打包壳失真（打包壳进程名=
        # productName "OpenCode Dev.exe"），一并采样入判定。
        def _shell_samples():
            samples = []
            deadline = time.time() + 30
            while True:
                count = electron_shell_count()
                if release_mode:
                    count += _release_shell_count(args.release_shell)
                samples.append(count)
                if samples[-1] == 0 or time.time() >= deadline:
                    break
                time.sleep(5)
            return samples

        samples = _shell_samples()
        shell_count = samples[-1]
        recon.check("E2_service_independent_of_shell",
                    port_responsive(url, headers) and shell_count == 0,
                    servicePid=pid, serviceName=proc_info.get("name"),
                    serviceParentPid=proc_info.get("parentPid"),
                    electronShellSamples=samples,
                    releaseShellName=args.release_shell if release_mode else None,
                    concurrentActorSuspected=shell_count > 0,
                    rule="关窗分义②：无 electron 桌面壳进程在场（发行形态加计"
                         "打包壳进程名），服务独立存活并继续服务（命令行含 "
                         "Juscite 的宿主自噪声不入判定；并行单元的壳在场＝前提"
                         "不可测，如实 FAIL）")
    else:
        recon.observe("E2_shell_independence_desktop_only",
                      note="F01 关窗分义②为 desktop 专属断言；F21-selfhost 行无此"
                           "assertion，跳过（服务级分义由 E1/E4 覆盖）")

    pids = listener_pids(port)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    bind_error = None
    try:
        sock.bind(("127.0.0.1", port))
        bind_error = "bound_ok_unexpected"
    except OSError as exc:
        bind_error = "refused(winerror=%s)" % getattr(exc, "winerror", exc)
    finally:
        try:
            sock.close()
        except OSError:
            pass
    recon.check("E3_single_writer_single_core",
                len(pids) == 1 and pids == [pid],
                listenerPids=pids, registrationPid=pid,
                parallelCoreBind=bind_error,
                rule="单写者拓扑：同根同端口恰一个服务进程；第二核端口排他拒绝")

    snapshot_pre = role_transcript(fetch_messages(client, sid))
    title_pre = got_value.get("title")

    stop = stop_service(pid)
    # 注册 pid 之外若还有监听者（并行单元抢占/注册滞后形态），一并显式退出——
    # "退出＝端口无监听"的断言对象是这个端口上的全部服务进程（活 pid 权威）。
    for extra in [p for p in listener_pids(port) if p != pid]:
        stop_service(extra)
    listeners_after = listener_pids(port)
    connect_refused = False
    try:
        connect_closed(port)
    except OSError:
        connect_refused = True
    recon.check("E4_explicit_exit_stops_service",
                stop["processGone"] and not listeners_after and connect_refused,
                pid=pid, processGone=stop["processGone"],
                listenersAfter=listeners_after, connectRefused=connect_refused,
                registrationRetained=reg_path.exists(),
                rule="退出分义：显式退出（taskkill）＝服务真停，端口无监听")

    db_copy = copy_db(roots["data"], workdir, filename=db_filename)
    child_ids = [c for c in (child_full_id, child_cut_id) if c]
    facts = db_facts(db_copy, sid, child_ids)
    session_row = facts.get("sessionRow") or {}
    types = facts.get("messageTypes") or {}
    model_cell = json.dumps(session_row.get("model"), ensure_ascii=False) \
        if session_row.get("model") is not None else ""
    children_facts = facts.get("children") or {}
    lineage_db = bool(children_facts) and all(
        (v or {}).get("forkSessionId") == sid and (v or {}).get("forkBoundary")
        for v in children_facts.values())
    def _norm_dir(p) -> str:
        return str(p or "").replace("\\", "/").rstrip("/").lower()

    recon.check("E5_events_persisted_on_disk",
                session_row.get("id") == sid
                and _norm_dir(session_row.get("directory")) == _norm_dir(workspace)
                and "deepseek" in model_cell
                and types.get("user", 0) >= 3 and types.get("assistant", 0) >= 3
                and facts.get("messageSeqMonotonic") and lineage_db
                and (facts.get("migrationsApplied") or 0) >= 1,
                sessionRow={k: session_row.get(k) for k in
                            ("id", "directory", "title", "forkSessionId")},
                messageTypes=types,
                messageSeqMonotonic=facts.get("messageSeqMonotonic"),
                childrenDbLineage=lineage_db,
                eventRows=facts.get("eventRows"),
                eventSequenceAggregates=facts.get("eventSequenceAggregates"),
                migrationsApplied=facts.get("migrationsApplied"),
                inboxRowsParent=facts.get("inboxRowsParent"),
                dbCopy=str(db_copy),
                rule="停机窗口取证：会话/消息角色行/分叉血统/迁移版本均落专属 "
                     "data 根（原件只复制零打开；事件表行数如实记录）")

    if release_mode:
        # 发行形态重启＝经发行 CLI 二进制原路重启（打包壳同款 spawn：
        # serve --service --hostname --port；channel/版本为二进制构建期
        # 常量——env 不可改，注册/DB 文件名随其 channel 原样落位）。
        env2 = dict(os.environ)
        env2.update({
            "XDG_STATE_HOME": str(roots["state"]),
            "XDG_DATA_HOME": str(roots["data"]),
            "XDG_CONFIG_HOME": str(roots["config"]),
            "XDG_CACHE_HOME": str(roots["cache"]),
            "OPENCODE_DISABLE_MODELS_FETCH": "1",
        })
        restart_log = open(workdir / "service-restart.log", "ab")
        try:
            proc2 = subprocess.Popen(
                [str(release_cli), "serve", "--service",
                 "--hostname", "127.0.0.1", "--port", str(port)],
                cwd=str(release_cli.parent), env=env2, stdout=restart_log,
                stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW)
        finally:
            restart_log.close()
        restart_mode = "release-cli-binary"
    else:
        env2 = build_service_env(roots["state"], roots["data"], roots["config"],
                                 roots["cache"], version_mark)
        proc2 = spawn_service(oc28, bun, port, env2, workdir / "service-restart.log")
        restart_mode = "dev-bun-source"
    reg_path2, reg2, headers2, client2, info2 = wait_registration(
        reg_candidates, expect_pid=str(proc2.pid))
    info2_value = info2.get("data", info2) if isinstance(info2, dict) else {}
    pid2 = str(info2_value.get("pid") or reg2.get("pid"))
    # 注册文件由服务自写、重写可能滞后于监听（实测）——10s 内等它追平活 pid，
    # 不追平也如实记录（不影响持久化断言本体）。
    reg_lag = None
    reg_deadline = time.time() + 10
    while time.time() < reg_deadline:
        try:
            reg_now = json.loads(reg_path2.read_text(encoding="utf-8"))
            if str(reg_now.get("pid")) == pid2:
                reg_lag = False
                break
        except (json.JSONDecodeError, OSError):
            pass
        reg_lag = True
        time.sleep(1)
    got2 = client2.session(sid)
    got2_value = got2.get("data", got2) if isinstance(got2, dict) else {}
    transcript_post = role_transcript(fetch_messages(client2, sid))
    child_ok = False
    if child_full_id:
        raw = client2.session(child_full_id)
        cv = raw.get("data", raw) if isinstance(raw, dict) else {}
        child_ok = ((cv.get("fork") or {}).get("sessionID") == sid)
    recon.check("E6_restart_persistence_readback",
                got2_value.get("title") == title_pre
                and transcript_post == snapshot_pre
                and child_ok and pid2 != pid,
                pidBefore=pid, pidAfter=pid2, registrationLag=reg_lag,
                restartMode=restart_mode,
                registrationChannel=("release" if reg_path2.name == RELEASE_REG_NAME
                                     else "dev"),
                titleEqual=got2_value.get("title") == title_pre,
                transcriptEqual=transcript_post == snapshot_pre,
                transcriptMessages=len(transcript_post),
                childLineageIntact=child_ok,
                rule="状态持久：显式退出→重启后标题/逐字转写/分叉血统完整回读"
                     "（发行形态经发行 CLI 二进制原路重启；pidAfter=活进程 info "
                     "pid 权威）")

    recon.check("E7_explicit_cwd_single_writer_discipline",
                (explicit_cwd == str(oc28)) if started_by_recon else True,
                explicitCwdPassed=explicit_cwd or "既有服务（复用，未由本驱动启动）",
                driverDbAccess="copy-then-open（原件零打开，只读取证）",
                driverWriteRoots=[str(workspace), str(workdir)],
                pythonVersion=recon.meta["pythonVersion"],
                rule="保 Python 单写者及显式 cwd：驱动状态只经服务 HTTP 写入；"
                     "DB 仅复制件只读取证；干净启动子进程 cwd 显式钉定 oc28")

    # ================= F 纪律 ========================================== #
    recon.observe("F1_no_parallel_dual_core",
                  bindExclusion=bind_error,
                  registrations=sorted(p.name for p in
                                       (roots["state"] / "opencode").glob("service-*.json"))
                  if (roots["state"] / "opencode").exists() else [],
                  rule="不并行双核：端口排他＋单注册文件")
    recon.observe("F2_real_listener_not_headless_sdk",
                  httpInfo=url + "/api/info",
                  rule="冻结选择＝OpenCode 原生服务（真实 HTTP listener）；"
                       "「SDK 无 listener 当 browser 服务」为被否备胎（08§0）")
    recon.observe("F3_synthetic_only",
                  workspace=str(workspace), materialExisted=material.exists(),
                  sessionPrefix=SESSION_PREFIX[profile],
                  note="全程合成材料；证据会话 id 前缀钉定")
    recon.observe("F4_python_version_rule",
                  python=recon.meta["pythonVersion"],
                  rule="F01：Python 3.13 先验不过用 3.12——当前 3.12.x；"
                       "部署规则零改动（本单零补丁）")

    # ---- 收尾：desktop 保持服务在位；selfhost 停临时服务＋产品根差分 ---- #
    if profile == "desktop":
        recon.meta["final"] = {"serviceLeftRunning": True, "pid": pid2, "url": url}
    else:
        # 活监听 pid 权威收口（注册 pid 可能滞后/陈旧，实测）。
        for live in listener_pids(port):
            stop_service(live)
        still = listener_pids(port)
        delta = product_delta(baseline)
        # 产品根隔离的精确证明（共享宿主上 stat 差分对并行单元活动有竞态，
        # 实测被 concurrent service lifecycle 打脏）：本 profile 的会话在产品
        # DB 必须零行、在专属临时 DB 已由 E5 证实在根；产品 config sha 不变。
        # W3-U34：产品 DB 文件名随 channel（dev=opencode-local.db，
        # release=opencode.db）——两文件在盘都查（本 profile 会话前缀闭集）。
        prod_rows = {}
        for db_name in ("opencode-local.db", "opencode.db"):
            if not (PRODUCT_ROOT / "data" / "opencode" / db_name).exists():
                continue
            try:
                prod_copy = copy_db(PRODUCT_ROOT / "data", workdir / "prod-db-copy",
                                    filename=db_name)
                con = sqlite3.connect(str(prod_copy))
                try:
                    prod_rows[db_name] = con.execute(
                        "select count(*) from session_v2 where id GLOB "
                        "'ses_w3u01s[0-9]*'"
                    ).fetchone()[0]
                finally:
                    con.close()
            except sqlite3.Error as exc:
                prod_rows[db_name] = "unreadable:%r" % exc
        isolated = all(v == 0 for v in prod_rows.values()) and prod_rows \
            and delta.get("configShaUnchanged") is True
        recon.check("E8_selfhost_final_stop_and_dedicated_root_isolation",
                    not still and isolated,
                    listenersStill=still,
                    productDbSelfhostSessionRows=prod_rows,
                    productConfigShaUnchanged=delta.get("configShaUnchanged"),
                    concurrentChurnFacts={"dbStatUnchanged": delta.get("dbUnchanged"),
                                          "registrationUnchanged": delta.get(
                                              "registrationUnchanged")},
                    concurrentChurnNote="共享宿主上并行单元会起停 43127 产品服务，"
                                        "产品 DB/注册的 stat 差分不归因本 profile"
                                        "（行级会话隔离才是本流程的隔离证明）",
                    rule="selfhost 专属根隔离：selfhost 会话只落专属临时根"
                         "（产品 DB 零行＋产品 config sha 不变＋临时服务已停）")
        recon.meta["final"] = {"serviceStopped": not still,
                               "tempRootPrefix": "w3u01-selfhost-*"}
    recon.meta["finishedUtc"] = now_iso()
    return 0 if recon.failed == 0 else 2


def _find_bun() -> Path:
    for cand in (Path.home() / ".bun" / "bun.exe",
                 Path.home() / ".bun" / "bin" / "bun.exe"):
        if cand.exists():
            return cand
    return Path("bun")


def _free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


# ------------------------------------------------------------------ #
# 证据落盘
# ------------------------------------------------------------------ #

def write_evidence(recon: Recon, args, code: int) -> list:
    if recon.profile == "desktop":
        targets = [REPO_ROOT / "evidence" / "F01" / "desktop",
                   REPO_ROOT / "evidence" / "F21" / "desktop"]
    else:
        targets = [REPO_ROOT / "evidence" / "F21" / "selfhost"]
    oc28_head = run_cmd(["git", "rev-parse", "HEAD"],
                        cwd=str(args.oc28), timeout=10).strip() if \
        (Path(args.oc28) / ".git").exists() else None
    repo_head = run_cmd(["git", "rev-parse", "HEAD"],
                        cwd=str(REPO_ROOT), timeout=10).strip()
    doc = {
        "unit": args.unit, "tool": Path(__file__).name,
        "obligations": {"desktop": ["F01-desktop", "F21-desktop"],
                        "selfhost": ["F21-selfhost"]}[recon.profile],
        "profile": recon.profile, "exitCode": code,
        "verdict": "RECON_OK" if code == 0 else "RECON_FAIL",
        "checks": recon.checks, "failed": recon.failed,
        "meta": {**recon.meta, "oc28Head": oc28_head, "repoHead": repo_head},
        "boundary": {
            "gui_window_close": "真机 GUI 关窗交互属 E26 B3 清单"
                                "（e26-b3-checklist）；本面为服务级分义：断连 "
                                "no-op＋无壳存活＋显式退出真停",
            "packaged_pin": ("发行形态（W3-U34）：服务实值=打包 bundled CLI 构"
                             "建期常量 %s（W3-U22/e01 §9.1 冻结事实，记录实值"
                             "不冒 pin）；打包壳 app 版本=2.0.28 pin 另面"
                             % RELEASE_BUNDLED_CLI_VERSION)
                            if recon.meta.get("releaseMode")
                            else "本机为源码 dev 形态（F-4 双轨记录实值）；打包 "
                                 "2.0.28 PIN 属发行形态验收（B3 后段安装升级恢复）",
            "harness_role_binding": "harness ticket/lease/transcript 角色绑定"
                                    "＝E05（T11/T12 已 VERIFIED）；本面只覆盖"
                                    "服务级角色结果（user/assistant 转写）",
            "oc28_readonly": "oc28 检出零改动；发行形态 --oc28 指向一次性检出"
                             "（026b106 detached），主检出零触碰（W3-U34）"
                             if recon.meta.get("releaseMode") else
                             "oc28 检出零改动；本单零新增补丁（17 卡 F01 落点"
                             "001;002＋上游 app/desktop 为既有交付态）",
        },
    }
    written = []
    for target in targets:
        target.mkdir(parents=True, exist_ok=True)
        stem = "f01-f21-closure-recon" if recon.profile == "desktop" \
            else "f21-closure-recon"
        if getattr(args, "evidence_suffix", ""):
            stem += "-" + args.evidence_suffix
        j = target / (stem + ".json")
        j.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
        written.append(str(j))
        md = target / (stem + ".md")
        md.write_text(_render_md(doc), encoding="utf-8")
        written.append(str(md))
    return written


def _render_md(doc: dict) -> str:
    lines = ["# %s · F01/F21 核心服务闭包对账（%s profile）" % (
        doc["unit"], doc["profile"]), ""]
    lines.append("- 判定：%s（%d checks，%d FAIL）" % (
        doc["verdict"], len(doc["checks"]), doc["failed"]))
    lines.append("- 义务实例：%s" % "、".join(doc["obligations"]))
    lines.append("- oc28 HEAD：`%s`；本仓 HEAD：`%s`" % (
        doc["meta"].get("oc28Head"), doc["meta"].get("repoHead")))
    lines.append("- Python：%s（F01 规则：3.13 先验不过用 3.12；部署规则零改动）"
                 % doc["meta"].get("pythonVersion"))
    lines.append("- 开始：%s　结束：%s" % (doc["meta"].get("startedUtc"),
                                          doc["meta"].get("finishedUtc")))
    lines.append("")
    lines.append("| check | 状态 | 关键事实 |")
    lines.append("|---|---|---|")
    for c in doc["checks"]:
        facts = {k: v for k, v in c.items() if k not in ("check", "status")}
        text = json.dumps(facts, ensure_ascii=False, default=str)
        if len(text) > 180:
            text = text[:177] + "..."
        lines.append("| %s | %s | %s |" % (c["check"], c["status"],
                                           text.replace("|", "\\|")))
    lines.append("")
    lines.append("## 边界（如实）")
    for k, v in doc["boundary"].items():
        lines.append("- %s：%s" % (k, v))
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------ #
# 入口
# ------------------------------------------------------------------ #

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", action="append",
                        choices=("desktop", "selfhost"), dest="profiles")
    parser.add_argument("--workspace",
                        default=os.path.join(tempfile.gettempdir(), "w3_synth_ws"))
    parser.add_argument("--oc28", default=str(OC28_DEFAULT))
    parser.add_argument("--bun", default=None)
    parser.add_argument("--release-cli", default=None,
                        help="发行形态：安装目录\\resources\\opencode-cli.exe；"
                             "给定时 desktop profile 切发行形态（注册双通道择真"
                             "＋A4 bundled CLI 冻结版＋E6 发行 CLI 重启）")
    parser.add_argument("--release-shell", default=RELEASE_SHELL_DEFAULT,
                        help="发行形态打包壳进程名（E2 采样加计）")
    parser.add_argument("--unit", default="W3-U01",
                        help="证据标注工单号（默认 W3-U01）")
    parser.add_argument("--evidence-suffix", default="",
                        help="证据文件名后缀（如 release-w3u34；canonical "
                             "W3-U01 文件名不动）")
    args = parser.parse_args()
    profiles = args.profiles or ["desktop", "selfhost"]

    workspace = Path(args.workspace)
    if not (workspace / MATERIAL_REL).exists():
        print("RECON_BLOCKED: synthetic material missing:",
              workspace / MATERIAL_REL)
        return 3

    failures = 0
    for profile in profiles:
        recon = Recon(profile)
        code = 2
        try:
            code = run_profile(profile, args, recon)
        except Exception as error:  # noqa: BLE001 - 按 profile 如实报告
            print("RECON_FAIL[%s]: %r" % (profile, error), flush=True)
            recon.checks.append({"check": "recon_driver", "status": "FAIL",
                                 "error": repr(error)[:400]})
            code = 2
        written = write_evidence(recon, args, code)
        verdict = "RECON_OK" if code == 0 else "RECON_FAIL"
        print("[%s] %s (%d checks, %d FAIL, exit %d) evidence=%s" % (
            profile, verdict, len(recon.checks), recon.failed, code,
            "; ".join(written)), flush=True)
        if code != 0:
            failures += 1
    return 0 if failures == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
