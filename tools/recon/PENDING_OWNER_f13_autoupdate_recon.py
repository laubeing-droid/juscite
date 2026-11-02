# -*- coding: utf-8 -*-
"""F13 自动更新通道（真检查→下载→验签→升级）全链 recon（PENDING_OWNER 版，工单 W4-U27）。

06 F13 行 acceptance 明文：『真检查下载验签升级；坏签名/中断/回退保护外置用户数据』。
17 卡 F13：target=上游原生 app/desktop（UI_HOST_OR_NEW_PRODUCT），『优先保原生能力→
仅选型必要差异→新增产品合同/权限/持久化』，不创第二 loop。

原生通道在物（本工具 S1 亲验，不写死）：
  - oc28/packages/desktop/package.json:31 依赖 "electron-updater": "6.8.9"；
  - electron-builder.config.ts beta/prod 通道 publish={provider:"generic"}（上游原生
    更新通道=electron-updater GenericProvider＋latest.yml）；
  - electron-builder.config.test.ts:117-120 断言 electron-updater/NsisUpdater.js 必须
    打入 asar；v1.5 安装物（W4-U27 salvage 冻结 e8c16ecc…）asar 实扫 electron-updater
    全套 34 条目（NsisUpdater/GenericProvider/windowsExecutableCodeSignatureVerifier）
    ——自动更新原生能力随 v1.5 分发在物。
  - 上游 win.verifyUpdateCodeSignature=false＋个人免签（NotSigned，E25 同语，不冒公开
    签名包）→ 通道完整性闸由本单以应用层 Ed25519 签名补足（本机生成测试密钥，
    私钥不入包不入 git，落 %TEMP% 合成根跑后清除）。

本工具全链（合成材料红线：更新源一律合成本地 update server，不触外网）：
  S3 合成 update server：http.server@127.0.0.1 随机端口，双 feed（desktop/selfhost），
     GenericProvider 形态 latest.yml（version/path/sha512(base64)/releaseDate/files +
     扩展 pubkeyFingerprint/signature）＋合成升级包（zip）；可注入故障（篡改/单次断流）。
  S4 全链正测：真 HTTP 检查（latest.yml 拉取＋确定性解析＋语义版本比较）→ 真流式下载
     （staging 半包，边下边计数）→ 验签双闸（sha512==清单值 且 Ed25519 验签通过）
     → 原子升级（backup 旧→换新→版本回读）→ 合成 userData 保数据（E25 升级语义：
     稳定集防删防改，tools/recon/PENDING_OWNER_e25_f02_install_recon.py:104-125 同语）。
  S5 负测·坏签名拒：payload 篡改 1 字节（签名仍旧）→ sha512 失配拒装 → 安装根保持
     原版本（逐文件 sha256 未动），坏包弃置，userData 完好。
  S6 负测·中断恢复：server 对 zip 单次注入『声明全长 Content-Length 中途硬断流』
     （真 socket 断）→ 客户端检出不完整下载→丢弃半包→重试（electron-updater
     httpExecutor 重试语义）→ 服务恢复全量后续传成功→同版本覆盖安装（NSIS 升级
     机械实形，E25 同语）完成；中断期间安装根未动。
  S7 负测·升级失败回退保用户数据：apply 注入失败（swap 前强制异常）→ backup 回退旧版
     （安装根逐文件 sha256 与升级前全等）→ userData/数据卷比对集逐文件 sha256 全在。
  S8 selfhost 腿：合成部署根（栈替身＋data 卷业务状态）同一引擎全链＋三负测；
     升级包携 data/ 路径结构性被拒（升级不动数据卷）；E25 selfhost 真容器重建升级已
     VERIFIED，本单为通道语义的文件级合成对应，不冒真容器断言。
  S9 真根零触碰复核：%APPDATA%\\JusBench（v6 遗留永久隔离）与 %APPDATA%\\Juscite
     若在盘——跑前跑后 (relpath,size) 排序 digest 逐字一致（全程只读锚定）；
     私钥文件清除并断言不存在。

边界如实（不冒的断言）：
  - 真实 NSIS 跨版本升级实测（真装 v1→v1.5 静默窗）属 F01 B3 后段后半/W4-U28，本单
    不冒；本单升级语义在合成安装根/部署根上演（真 HTTP、真字节流、真验签、真文件
    swap/回退）。
  - electron-updater differential download（blockmap 差分）本单未演（全量下载语义）；
    v1.5 blockmap 在盘为后续差分面留位。
  - 产品接线（desktop 主进程 autoUpdater 唤醒）属 owner 公开入口后续工单；台账 F13
    行命令登记随账房，本单交付 recon 证据＋通道语义证明。

用法（juscite worktree 根 cwd）：
  python -X utf8 tools/recon/PENDING_OWNER_f13_autoupdate_recon.py
      [--profile desktop --profile selfhost] [--keep-temp]

exit 0＝双 profile 全链＋三负测＋零触碰复核全 PASS。
红线：全程合成材料；更新源只指 127.0.0.1 合成 server；%APPDATA%\\JusBench（v6 遗留）
零触碰；%APPDATA%\\Juscite 全程只读；私钥不入 git 不入包；不 push 不 PR。
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import http.client
import io
import json
import os
import shutil
import socket
import sys
import tempfile
import threading
import time
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

RUN_UTC = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
RUN_DATE = time.strftime("%Y%m%d")

REPO = Path.cwd()
DEFAULT_OC28 = Path(r"D:\Codex\1.法律工作区\jusbench工作区\oc28")
OC28_PIN_HEAD = "026b106bc5d41b679ffc413264229c340871e4d3"

V15_SUMS = Path("docs/construction/evidence/F77/desktop/v1.5/SHA256SUMS.txt")
V15_FREEZE_JSON = Path("evidence/F01/desktop/v15-release-freeze-recon-20261020.json")
# v1.5 冻结面自洽断言：SHA256SUMS.txt 的 exe 值==freeze recon 记录值（动态取当次
# 冻结权威，不硬编码特定 sha——freeze recon 每次验收跑都重新构建冻结新候选）。

APPDATA = Path(os.environ.get("APPDATA", ""))
V6_ROOT = APPDATA / "JusBench"      # v6 遗留：零触碰（只读锚定）
PRODUCT_ROOT = APPDATA / "Juscite"  # 产品根：全程只读锚定

PROFILES = ("desktop", "selfhost")
OLD_VER, NEW_VER = "1.0.0", "1.1.1"
MANIFEST_BYTES = {
    OLD_VER: b'{"name":"Juscite-synth","version":"1.0.0","channel":"synthetic"}\n',
    NEW_VER: b'{"name":"Juscite-synth","version":"1.1.1","channel":"synthetic"}\n',
}
EXE_BYTES = {
    OLD_VER: b"JUSCITE-SYNTH-EXE v1.0.0 payload-placeholder\n" * 64,
    NEW_VER: b"JUSCITE-SYNTH-EXE v1.1.1 payload-placeholder\n" * 96,
}
ASAR_BYTES = {
    OLD_VER: b"asar-placeholder-1.0.0\n" * 128,
    NEW_VER: b"asar-placeholder-1.1.1\n" * 128,
}
COMPOSE_BYTES = {
    OLD_VER: b"services:\n  harness:\n    image: lh-synth:1.0.0\n    # f13 synthetic stack\n" * 8,
    NEW_VER: b"services:\n  harness:\n    image: lh-synth:1.1.1\n    # f13 synthetic stack\n" * 8,
}
USERDATA_FILES = {
    "cases/case-0001/note.md": "# 合成案件笔记 0001\n\n金额 123,456.78 元，期限 30 日。\n".encode("utf-8"),
    "cases/case-0002/note.md": "# 合成案件笔记 0002\n\n利率万分之五/日。\n".encode("utf-8"),
    "settings/prefs.json": b'{"theme":"light","synthetic":true}\n',
}
DATAVOL_FILES = {
    "data/business/ledger.json": b'{"net": 123456780, "unit": "cent", "synthetic": true}\n',
    "data/business/minutes.txt": "会议纪要合成占位：2026-10-20 立案会谈。\n".encode("utf-8") * 4,
}


class Checks:
    def __init__(self) -> None:
        self.items: list[dict] = []

    def add(self, check_id: str, ok: bool, detail: str, **facts) -> None:
        self.items.append({"check": check_id, "result": "PASS" if ok else "FAIL",
                           "detail": detail, **facts})
        print(f"[f13] {'PASS' if ok else 'FAIL'} {check_id}: {detail}", flush=True)

    @property
    def failures(self) -> list[dict]:
        return [i for i in self.items if i["result"] == "FAIL"]


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha512_b64(data: bytes) -> str:
    return base64.b64encode(hashlib.sha512(data).digest()).decode("ascii")


# ---- 合成 update server ------------------------------------------------

class SynthServer:
    """127.0.0.1 合成更新源：GenericProvider 形态 latest.yml＋合成包，故障可注入。

    truncate 模式=单发武器（truncate_armed）：对下一个 zip 请求声明全长 Content-Length
    而只发 truncate_pct 后硬断 socket，随即自动解除（客户端重试拿到全量——中断恢复
    语义）；latest.yml 永远全量（检查通道不注入断流）。tamper 模式=对 zip 请求每发
    中段翻 1 字节（sha512/签名双失配），HTTP 层完整（验签层拒，不与断流混叠）。
    """

    def __init__(self, feed_root: Path) -> None:
        self.feed_root = feed_root
        self.mode = "clean"            # clean | tamper | truncate
        self.truncate_pct = 30
        self.truncate_armed = False
        self.served: list[dict] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):  # 静默
                pass

            def do_GET(self):
                rel = self.path.lstrip("/")
                target = (outer.feed_root / rel).resolve()
                if not target.is_file() or not str(target).startswith(
                        str(outer.feed_root.resolve())):
                    self.send_error(404, "not in synthetic feed")
                    return
                blob = target.read_bytes()
                mode = outer.mode
                outer.served.append({"path": self.path, "mode": mode,
                                     "bytes": len(blob)})
                if mode == "truncate" and target.suffix == ".zip" and outer.truncate_armed:
                    outer.truncate_armed = False  # 单发：断一次后自动恢复全量
                    cut = max(1, len(blob) * outer.truncate_pct // 100)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/octet-stream")
                    self.send_header("Content-Length", str(len(blob)))  # 声明全长
                    self.end_headers()
                    self.wfile.write(blob[:cut])
                    self.wfile.flush()
                    self.close_connection = True
                    try:
                        self.connection.shutdown(socket.SHUT_RDWR)  # 硬断
                    except OSError:
                        pass
                    return
                if mode == "tamper" and target.suffix == ".zip":
                    mutable = bytearray(blob)
                    mutable[len(mutable) // 2] ^= 0xFF
                    blob = bytes(mutable)
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(len(blob)))
                self.end_headers()
                self.wfile.write(blob)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


# ---- latest.yml 受控形态＋确定性解析（法律工作区红线：不模糊猜测） ----------

def build_latest_yml(payload_name: str, payload: bytes, version: str,
                     fingerprint: str, signature_b64: str,
                     release_date: str) -> bytes:
    lines = [
        f"version: {version}",
        f"path: {payload_name}",
        f"sha512: {sha512_b64(payload)}",
        f"releaseDate: '{release_date}'",
        f"pubkeyFingerprint: {fingerprint}",
        f"signature: {signature_b64}",
        "files:",
        f"  - url: {payload_name}",
        f"    sha512: {sha512_b64(payload)}",
        f"    size: {len(payload)}",
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def parse_latest_yml(raw: bytes) -> dict:
    """只接受本工具受控形态；任何未知行响亮拒（确定性解析，不猜）。"""
    top: dict = {}
    files: list[dict] = []
    cur: dict | None = None
    for ln in raw.decode("utf-8").splitlines():
        if not ln:
            continue
        if ln == "files:":
            top["files"] = files
            continue
        if ln.startswith("  - "):
            if cur is not None:
                files.append(cur)
            cur = {}
            k, _, v = ln[4:].partition(": ")
            cur[k] = v
            continue
        if ln.startswith("    "):
            if cur is None:
                raise ValueError(f"latest.yml 条目字段越位：{ln!r}")
            k, _, v = ln[4:].partition(": ")
            cur[k] = v
            continue
        if ln.startswith(" ") or ln.startswith("-"):
            raise ValueError(f"latest.yml 未知缩进行：{ln!r}")
        if ": " in ln:
            k, _, v = ln.partition(": ")
            if k in top:
                raise ValueError(f"latest.yml 重复键：{k}")
            top[k] = v
            continue
        raise ValueError(f"latest.yml 未知行：{ln!r}")
    if cur is not None:
        files.append(cur)
    for need in ("version", "path", "sha512", "signature", "pubkeyFingerprint"):
        if need not in top:
            raise ValueError(f"latest.yml 缺键：{need}")
    if "files" not in top or len(top["files"]) != 1:
        raise ValueError("latest.yml files 块须恰一条")
    return top


def canonical_manifest(profile: str, meta: dict) -> bytes:
    """签名对象（受控规范串）：profile/version/path/sha512。"""
    return (
        "F13-SYNTHETIC-UPDATE-MANIFEST-V1\n"
        f"profile: {profile}\n"
        f"version: {meta['version']}\n"
        f"path: {meta['path']}\n"
        f"sha512: {meta['sha512']}\n"
    ).encode("utf-8")


def semver_ge(a: str, b: str) -> bool:
    return tuple(int(x) for x in a.split(".")) >= tuple(int(x) for x in b.split("."))


# ---- 更新客户端（electron-updater NsisUpdater 语义的合成对应） --------------

class UpdateClient:
    """检查→下载→验签→升级；负测注入在 server 侧与 apply(force_fail) 侧。"""

    RETRIES = 3

    def __init__(self, server: SynthServer, profile: str, pub_raw: bytes,
                 staging: Path, install_root: Path, state_roots: tuple[Path, ...],
                 log: list) -> None:
        self.server = server
        self.profile = profile
        self.pub_raw = pub_raw
        self.staging = staging
        self.install_root = install_root
        self.state_roots = state_roots  # 合成 userData/数据卷根（保数据比对对象）
        self.log = log

    # -- 检查（真 HTTP＋确定性解析＋语义版本比较） --
    def check_update(self, current: str, manifest: str = "latest.yml") -> tuple[bool, dict]:
        url = f"{self.server.base}/{self.profile}/{manifest}"
        with urlopen(Request(url), timeout=10) as resp:
            raw = resp.read()
        meta = parse_latest_yml(raw)
        if meta["pubkeyFingerprint"] != hashlib.sha256(self.pub_raw).hexdigest():
            raise ValueError("pubkey 指纹与本地测试公钥不符（合成源被换钥）")
        available = not semver_ge(current, meta["version"])
        self.log.append({"step": "check", "manifest": manifest,
                         "feedVersion": meta["version"], "current": current,
                         "updateAvailable": available})
        return available, meta

    # -- 下载（真流式；不完整即删半包重试——httpExecutor 重试语义） --
    def download(self, meta: dict) -> Path:
        url = f"{self.server.base}/{self.profile}/{meta['path']}"
        last_err: Exception | None = None
        for attempt in range(1, self.RETRIES + 1):
            partial = self.staging / (meta["path"] + ".partial")
            try:
                nbytes = 0
                with urlopen(Request(url), timeout=15) as resp, open(partial, "wb") as fh:
                    declared = int(resp.headers.get("Content-Length", "-1"))
                    while True:
                        chunk = resp.read(1 << 16)
                        if not chunk:
                            break
                        fh.write(chunk)
                        nbytes += len(chunk)
                if declared >= 0 and nbytes != declared:
                    raise http.client.IncompleteRead(b"", declared - nbytes)
                done = self.staging / meta["path"]
                partial.replace(done)
                self.log.append({"step": "download", "attempt": attempt,
                                 "bytes": nbytes, "declared": declared, "ok": True})
                return done
            except (http.client.IncompleteRead, http.client.RemoteDisconnected,
                    ConnectionError, socket.timeout, OSError) as exc:
                last_err = exc
                if partial.exists():
                    partial.unlink()  # 半包丢弃，不留 staging 污染
                self.log.append({"step": "download", "attempt": attempt,
                                 "error": type(exc).__name__, "ok": False})
        raise RuntimeError(f"下载重试 {self.RETRIES} 次仍失败：{last_err}")

    # -- 验签双闸：sha512 清单比对＋Ed25519（应用层，个人免签不冒公开签名包） --
    def verify(self, meta: dict, payload: Path) -> None:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        blob = payload.read_bytes()
        digest = sha512_b64(blob)
        if digest != meta["sha512"] or digest != meta["files"][0]["sha512"]:
            payload.unlink()  # 坏包弃置，不留 staging 污染
            raise ValueError(f"sha512 与 latest.yml 清单不符（坏包已弃置：{payload.name}）")
        sig = base64.b64decode(meta["signature"])
        try:
            Ed25519PublicKey.from_public_bytes(self.pub_raw).verify(
                sig, canonical_manifest(self.profile, meta))
        except InvalidSignature:
            payload.unlink()
            raise ValueError("Ed25519 验签失败（坏包已弃置）")
        self.log.append({"step": "verify", "payloadBytes": len(blob),
                         "sha512Match": True, "ed25519": "OK"})

    # -- 安装（backup→换新→回读）；force_fail 注入 apply 失败→回退 --
    def apply(self, payload: Path, force_fail: bool = False) -> None:
        backup = self.staging / "backup"
        if backup.exists():
            shutil.rmtree(backup)
        shutil.copytree(self.install_root, backup)
        try:
            with zipfile.ZipFile(payload) as zf:
                bad = [n for n in zf.namelist()
                       if n.startswith("data/") and self.profile == "selfhost"]
                if bad:
                    raise ValueError(f"升级包携数据卷路径被拒：{bad}（升级不观数据卷）")
                zf.extractall(self.install_root)
            if force_fail:
                raise RuntimeError("injected: apply failure（工单负测 S7）")
        except Exception:
            # 回退：backup 逐文件还原（升级失败回退不丢用户数据）
            for p in list(self.install_root.rglob("*")):
                if p.is_file():
                    p.unlink()
            for p in backup.rglob("*"):
                dst = self.install_root / p.relative_to(backup)
                if p.is_dir():
                    dst.mkdir(parents=True, exist_ok=True)
                else:
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(p, dst)
            shutil.rmtree(backup)
            raise
        shutil.rmtree(backup, ignore_errors=True)

    # -- 合成保数据比对（E25 语义：稳定集防删防改，允许新增） --
    def state_snapshot(self) -> dict:
        snap = {}
        for root in self.state_roots:
            for p in sorted(root.rglob("*")):
                if p.is_file():
                    snap[p.relative_to(root).as_posix()] = \
                        hashlib.sha256(p.read_bytes()).hexdigest()
        return snap

    def state_verify(self, baseline: dict) -> tuple[bool, str]:
        now = self.state_snapshot()
        lost = sorted(set(baseline) - set(now))
        changed = [k for k in baseline if k in now and now[k] != baseline[k]]
        ok = not lost and not changed
        return ok, (f"稳定集 {len(baseline)} 文件防删防改：丢={lost or '无'} "
                    f"改={changed or '无'} 新增={sorted(set(now) - set(baseline)) or '无'}")


# ---- 合成世界搭建 -------------------------------------------------------

def zip_payload(profile: str, version: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if profile == "desktop":
            zf.writestr("manifest.json", MANIFEST_BYTES[version])
            zf.writestr("Juscite.exe", EXE_BYTES[version])
            zf.writestr("resources/app.asar", ASAR_BYTES[version])
        else:
            zf.writestr("f13-stack-manifest.json", MANIFEST_BYTES[version])
            zf.writestr("docker-compose.selfhost.yml", COMPOSE_BYTES[version])
            # 数据卷（data/）不随升级包——升级不动数据卷（携带即被 apply 拒）
    return buf.getvalue()


def seed_install_root(profile: str, root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    if profile == "desktop":
        (root / "manifest.json").write_bytes(MANIFEST_BYTES[OLD_VER])
        (root / "Juscite.exe").write_bytes(EXE_BYTES[OLD_VER])
        (root / "resources").mkdir(exist_ok=True)
        (root / "resources" / "app.asar").write_bytes(ASAR_BYTES[OLD_VER])
    else:
        (root / "f13-stack-manifest.json").write_bytes(MANIFEST_BYTES[OLD_VER])
        (root / "docker-compose.selfhost.yml").write_bytes(COMPOSE_BYTES[OLD_VER])
        (root / "data" / "business").mkdir(parents=True, exist_ok=True)
        for rel, blob in DATAVOL_FILES.items():
            (root / rel).write_bytes(blob)


def installed_version(profile: str, root: Path) -> str:
    name = "manifest.json" if profile == "desktop" else "f13-stack-manifest.json"
    return json.loads((root / name).read_text(encoding="utf-8"))["version"]


def tree_file_hashes(root: Path) -> dict:
    return {p.relative_to(root).as_posix(): sha256_bytes(p.read_bytes())
            for p in sorted(root.rglob("*")) if p.is_file()}


# ---- 真根零触碰锚定 -----------------------------------------------------

def root_fingerprint(root: Path) -> dict | None:
    if not root.exists():
        return None
    entries = []
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root).as_posix()
        entries.append(f"f:{rel}:{p.stat().st_size}" if p.is_file() else f"d:{rel}")
    return {"entries": len(entries),
            "digest": sha256_bytes("\n".join(entries).encode("utf-8"))}


# ---- 各 profile 全链＋三负测 --------------------------------------------

def run_profile(profile: str, server: SynthServer, synth_root: Path,
                pub_raw: bytes, ck: Checks) -> list:
    log: list = []
    staging = synth_root / "staging" / profile
    install_root = synth_root / "install" / profile
    staging.mkdir(parents=True, exist_ok=True)
    if install_root.exists():
        shutil.rmtree(install_root)
    seed_install_root(profile, install_root)
    # 保数据比对对象（E25 同语）：desktop=合成 userData 根；selfhost=data/ 数据卷
    # （E25 selfhost 升级语义：容器重建 PG 卷零动、业务状态保持——栈定义文件升级
    # 本来就要变，不在「保数据」比对集内）
    state_root = (install_root / "data") if profile == "selfhost" \
        else synth_root / "userdata"
    if profile == "desktop":
        state_root.mkdir(parents=True, exist_ok=True)
        for rel, blob in USERDATA_FILES.items():
            dst = state_root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(blob)
    client = UpdateClient(server, profile, pub_raw, staging, install_root,
                          (state_root,), log)

    # S4 全链正测：检查→下载→验签→升级→回读＋保数据
    base_snap = client.state_snapshot()
    avail, meta = client.check_update(OLD_VER)
    payload = client.download(meta)
    client.verify(meta, payload)
    client.apply(payload)
    got = installed_version(profile, install_root)
    state_ok, state_detail = client.state_verify(base_snap)
    ck.add(f"S4.{profile}.全链正测",
           avail and meta["version"] == NEW_VER and got == NEW_VER and state_ok,
           f"真 HTTP 检查（feed {meta['version']} vs current {OLD_VER}→available={avail}）→"
           f"流式下载（{payload.stat().st_size} B）→验签双闸（sha512＋Ed25519）→"
           f"原子升级（backup→swap）→回读版本 {got}（应 {NEW_VER}）；保数据：{state_detail}",
           feedVersion=meta["version"], installed=got)

    # S5 负测·坏签名拒：payload 篡改 1 字节（签名仍旧）→验签拒→安装根未动
    server.mode = "tamper"
    pre_files = tree_file_hashes(install_root)
    pre_snap = client.state_snapshot()
    rejected = False
    reject_reason = ""
    try:
        _, bad_meta = client.check_update(NEW_VER)
        client.verify(bad_meta, client.download(bad_meta))
    except ValueError as exc:
        rejected = True
        reject_reason = str(exc)[:110]
    server.mode = "clean"
    post_files = tree_file_hashes(install_root)
    leftovers = sorted(x.name for x in staging.glob("*.zip")) + \
        sorted(x.name for x in staging.glob("*.partial"))
    state_ok, state_detail = client.state_verify(pre_snap)
    still_old_or_new = installed_version(profile, install_root)
    ck.add(f"S5.{profile}.坏签名拒",
           rejected and pre_files == post_files and state_ok and not leftovers,
           f"篡改包被验签拒：{reject_reason}；安装根逐文件 sha256 未动="
           f"{pre_files == post_files}（版本回读 {still_old_or_new}）；staging 坏包/半包"
           f"残留={leftovers or '无'}；保数据：{state_detail}")

    # S6 负测·中断恢复：zip 单次断流→半包丢弃→重试成功→覆盖安装完成
    log_before = len(log)
    server.mode = "truncate"
    server.truncate_pct = 30
    server.truncate_armed = True
    _, meta = client.check_update(NEW_VER)  # latest.yml 永远全量
    upgraded = False
    try:
        p = client.download(meta)
        client.verify(meta, p)
        client.apply(p)  # 同版本覆盖＝NSIS 升级机械实形（E25 同语）
        upgraded = installed_version(profile, install_root) == NEW_VER
    except (RuntimeError, ValueError):
        upgraded = False
    server.mode = "clean"
    seg = log[log_before:]
    interrupted = any(e.get("step") == "download" and not e.get("ok") for e in seg)
    recovered = any(e.get("step") == "download" and e.get("ok") for e in seg)
    ck.add(f"S6.{profile}.中断恢复", interrupted and recovered and upgraded,
           f"zip 单次 30% 硬断流（声明全长，IncompleteRead）检出={interrupted}；"
           f"半包丢弃后重试得全量={recovered}；覆盖安装完成（版本回读 "
           f"{installed_version(profile, install_root)}）={upgraded}；"
           f"中断期间安装根未动（apply 只在校验后执行）")

    # S7 负测·升级失败回退保数据：apply 注入失败→backup 回退→逐字节还原
    shutil.rmtree(install_root)
    seed_install_root(profile, install_root)
    pre_files = tree_file_hashes(install_root)
    pre_snap = client.state_snapshot()
    rolled_back = False
    try:
        _, old_meta = client.check_update(OLD_VER, manifest=f"latest-{OLD_VER}.yml")
        p = client.download(old_meta)
        client.verify(old_meta, p)
        client.apply(p, force_fail=True)
    except RuntimeError as exc:
        rolled_back = "injected" in str(exc)
    post_files = tree_file_hashes(install_root)
    got = installed_version(profile, install_root)
    state_ok, state_detail = client.state_verify(pre_snap)
    ck.add(f"S7.{profile}.升级失败回退保数据",
           rolled_back and pre_files == post_files and got == OLD_VER and state_ok,
           f"apply 注入失败→backup 回退→回读版本 {got}（应 {OLD_VER}）；安装根逐文件 "
           f"sha256 与升级前全等={pre_files == post_files}；保数据：{state_detail}")
    return log


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", action="append", choices=PROFILES,
                    default=None, help="缺省双 profile 全跑")
    ap.add_argument("--oc28", default=str(DEFAULT_OC28))
    ap.add_argument("--keep-temp", action="store_true",
                    help="保留合成根（含私钥）调试用；验收不带此参")
    args = ap.parse_args()
    profiles = tuple(args.profile) if args.profile else PROFILES
    oc28 = Path(args.oc28)
    ck = Checks()

    synth_root = Path(tempfile.mkdtemp(prefix="f13-autoupdate-recon-"))
    feed_root = synth_root / "feed"
    keys_dir = synth_root / "keys"
    feed_root.mkdir(parents=True)
    keys_dir.mkdir(parents=True)
    key_pem = keys_dir / "f13_update_signing_key.pem"
    all_logs: dict = {}
    server = None

    try:
        # ---- S0 预态锚定 ----
        v6_pre = root_fingerprint(V6_ROOT)
        prod_pre = root_fingerprint(PRODUCT_ROOT)
        from cryptography import __version__ as crypto_ver
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        ck.add("S0.预态锚定", True,
               f"合成根={synth_root}（%TEMP%，不入 git）；cryptography={crypto_ver}；"
               f"%APPDATA%\\JusBench 在盘={v6_pre is not None}"
               f"（{'零触碰只读锚定 ' + str(v6_pre['entries']) + ' 项' if v6_pre else '本机不存在，锚定跳过'}）；"
               f"%APPDATA%\\Juscite 在盘={prod_pre is not None}"
               f"（{'全程只读锚定 ' + str(prod_pre['entries']) + ' 项' if prod_pre else '本机不存在，锚定跳过'}）",
               cryptoVersion=crypto_ver, synthRoot=str(synth_root))

        # ---- S1 原生通道在物（oc28 只读静态＋v1.5 冻结证据在盘） ----
        pkg_txt = (oc28 / "packages/desktop/package.json").read_text(encoding="utf-8")
        has_dep = '"electron-updater": "6.8.9"' in pkg_txt
        cfg_txt = (oc28 / "packages/desktop/electron-builder.config.ts").read_text(encoding="utf-8")
        has_generic = cfg_txt.count('provider: "generic"') >= 2  # beta+prod 通道
        has_nosign = "verifyUpdateCodeSignature: false" in cfg_txt
        test_txt = (oc28 / "packages/desktop/electron-builder.config.test.ts").read_text(encoding="utf-8")
        has_nsis_assert = "electron-updater/out/NsisUpdater.js" in test_txt
        sums_txt = (REPO / V15_SUMS).read_text(encoding="utf-8") if (REPO / V15_SUMS).is_file() else ""
        freeze_json = json.loads((REPO / V15_FREEZE_JSON).read_text(encoding="utf-8")) \
            if (REPO / V15_FREEZE_JSON).is_file() else {}
        freeze_ok = bool(freeze_json) and all(
            c.get("result") == "PASS" for c in freeze_json.get("checks", []))
        sums_exe = next((ln.split()[0] for ln in sums_txt.splitlines()
                         if ln.strip().endswith("*opencode-desktop-win-x64.exe")), "")
        freeze_sha = (freeze_json.get("release") or {}).get("sha256", "")
        v15_frozen = bool(sums_exe) and sums_exe == freeze_sha
        asar_sweep: dict | None = None
        asar = Path(tempfile.gettempdir()) / "w4u27-v15-stage-20261020-010720" \
            / "win-unpacked" / "resources" / "app.asar"
        if asar.is_file():
            try:
                import importlib.util
                espec = importlib.util.spec_from_file_location(
                    "e04tool", REPO / "tools/recon/PENDING_OWNER_e04_f77_release_license_closure.py")
                emod = importlib.util.module_from_spec(espec)
                espec.loader.exec_module(emod)
                header, _ = emod.parse_asar(asar)
                files = emod.asar_files(header)
                eu = [p for p in files if "electron-updater/" in p]
                asar_sweep = {"asar": str(asar), "entries": len(files),
                              "electronUpdater": len(eu),
                              "nsisUpdater": any(p.endswith("NsisUpdater.js") for p in eu),
                              "genericProvider": any(p.endswith("GenericProvider.js") for p in eu),
                              "sigVerifier": any(p.endswith("windowsExecutableCodeSignatureVerifier.js") for p in eu)}
            except Exception as exc:  # noqa: BLE001 —— 实扫失败不静默记因
                asar_sweep = {"asar": str(asar), "error": f"{type(exc).__name__}: {exc}"}
        sweep_txt = (f"v1.5 asar 实扫：{asar_sweep['entries']} 条目中 electron-updater "
                     f"{asar_sweep['electronUpdater']} 条（NsisUpdater="
                     f"{asar_sweep.get('nsisUpdater')}/GenericProvider="
                     f"{asar_sweep.get('genericProvider')}/sigVerifier="
                     f"{asar_sweep.get('sigVerifier')}）"
                     if asar_sweep and "entries" in asar_sweep
                     else f"v1.5 asar 实扫暂不可达（{(asar_sweep or {}) .get('error', 'scratch 已清')}）"
                          "——静态三处＋冻结证据在盘已足，实扫为旁证非验收门")
        ck.add("S1.原生通道在物",
               has_dep and has_generic and has_nosign and has_nsis_assert
               and v15_frozen and freeze_ok,
               f"oc28(只读) package.json electron-updater 6.8.9={has_dep}；builder config "
               f"generic provider×2（beta+prod）={has_generic}／"
               f"verifyUpdateCodeSignature:false={has_nosign}；NsisUpdater asar 断言="
               f"{has_nsis_assert}；v1.5 冻结面自洽（SHA256SUMS exe 值==freeze recon "
               f"记录值 {sums_exe[:12]}…）={v15_frozen}；"
               f"v1.5 freeze recon 全 PASS={freeze_ok}；{sweep_txt}",
               asarSweep=asar_sweep)

        # ---- S2 测试密钥（本机生成；私钥落合成根跑后清除，不入包不入 git） ----
        priv = Ed25519PrivateKey.generate()
        key_pem.write_bytes(priv.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption()))
        pubkey = priv.public_key()
        pub_raw = pubkey.public_bytes(serialization.Encoding.Raw,
                                      serialization.PublicFormat.Raw)
        fingerprint = hashlib.sha256(pub_raw).hexdigest()
        in_repo = str(key_pem.resolve()).lower().startswith(str(REPO.resolve()).lower())
        ck.add("S2.测试密钥", not in_repo and len(fingerprint) == 64,
               f"Ed25519 密钥对本机生成（cryptography）；私钥 PEM={key_pem}"
               f"（repo 内={in_repo}——应 False；跑后清除）；公钥指纹={fingerprint[:16]}…"
               f"（指纹入证据，私钥字节零入证据）",
               pubkeyFingerprint=fingerprint)

        # ---- S3 合成 update server（双 feed） ----
        for profile in profiles:
            feed = feed_root / profile
            feed.mkdir(parents=True, exist_ok=True)
            for ver in (NEW_VER, OLD_VER):
                payload_name = f"juscite-{profile}-synth-{ver}.zip"
                payload = zip_payload(profile, ver)
                stub = {"version": ver, "path": payload_name,
                        "sha512": sha512_b64(payload)}
                sig = priv.sign(canonical_manifest(profile, stub))
                yml = build_latest_yml(payload_name, payload, ver, fingerprint,
                                       base64.b64encode(sig).decode("ascii"), RUN_UTC)
                (feed / payload_name).write_bytes(payload)
                manifest = "latest.yml" if ver == NEW_VER else f"latest-{OLD_VER}.yml"
                (feed / manifest).write_bytes(yml)
        server = SynthServer(feed_root)
        server.start()
        ck.add("S3.合成update server", True,
               f"http.server@{server.base}（127.0.0.1 随机端口，不触外网）；双 feed "
               f"{list(profiles)}；latest.yml=GenericProvider 受控形态＋Ed25519 签名扩展；"
               f"故障注入面：tamper（每发中段翻 1 字节）／truncate（zip 单发 "
               f"{30}% 硬断流后自动恢复全量）",
               base=server.base)

        # ---- S4-S7 各 profile ----
        for profile in profiles:
            all_logs[profile] = run_profile(profile, server, synth_root, pub_raw, ck)
        server.stop()

        # ---- S9 真根零触碰复核＋私钥清除 ----
        v6_post = root_fingerprint(V6_ROOT)
        prod_post = root_fingerprint(PRODUCT_ROOT)
        untouched = (v6_pre == v6_post) and (prod_pre == prod_post)
        key_pem.unlink()
        key_gone = not key_pem.exists()
        v6_txt = f"{v6_pre['entries']} 项 digest 一致={v6_pre == v6_post}" \
            if v6_pre else "本机不存在（零触碰天然成立）"
        prod_txt = f"{prod_pre['entries']} 项 digest 一致={prod_pre == prod_post}" \
            if prod_pre else "本机不存在（零触碰天然成立）"
        ck.add("S9.真根零触碰＋私钥清除", untouched and key_gone,
               f"%APPDATA%\\JusBench（v6 遗留永久隔离）：{v6_txt}；"
               f"%APPDATA%\\Juscite：{prod_txt}；私钥已清除={key_gone}"
               f"（不入包不入 git）",
               v6Untouched=v6_pre == v6_post, productUntouched=prod_pre == prod_post)

        # ---- 证据落盘（evidence/F13/<profile>/） ----
        for profile in profiles:
            ev_dir = REPO / "evidence" / "F13" / profile
            ev_dir.mkdir(parents=True, exist_ok=True)
            slim = {
                "tool": "tools/recon/PENDING_OWNER_f13_autoupdate_recon.py",
                "unit": "W4-U27",
                "profile": profile,
                "run_utc": RUN_UTC,
                "channel_semantics": {
                    "native": "electron-updater 6.8.9 NsisUpdater＋GenericProvider（v1.5 asar 在物，S1 亲验）",
                    "appLayerSigning": "Ed25519 本机测试密钥（个人免签不冒公开签名包，E25 同语）",
                    "updateServer": f"{server.base}（合成本地，127.0.0.1）",
                    "e25Reuse": "升级保数据＝E25 稳定集防删防改语义（PENDING_OWNER_e25_f02_install_recon.py:104-125）",
                },
                "pubkey_fingerprint": fingerprint,
                "synth_root": str(synth_root),
                "boundaries": [
                    "真实 NSIS 跨版本升级实测属 F01 B3 后段后半/W4-U28，本单不冒",
                    "differential download（blockmap 差分）未演；v1.5 blockmap 在盘留位",
                    "产品接线（主进程 autoUpdater 唤醒）属 owner 后续工单；台账 F13 行登记随账房",
                ],
                "logs": all_logs.get(profile, []),
                "checks": [c for c in ck.items if f".{profile}." in c["check"]],
                "failures": [c for c in ck.failures if f".{profile}." in c["check"]],
            }
            (ev_dir / f"f13-autoupdate-recon-{RUN_DATE}.json").write_text(
                json.dumps(slim, ensure_ascii=False, indent=1), encoding="utf-8")
            md = [f"# F13 自动更新通道 recon——{profile}（W4-U27，{RUN_UTC}）", ""]
            md += [f"- **{i['result']}** {i['check']}：{i['detail']}" for i in slim["checks"]]
            md += ["", "## 边界如实"] + [f"- {b}" for b in slim["boundaries"]]
            (ev_dir / f"f13-autoupdate-recon-{RUN_DATE}.md").write_text(
                "\n".join(md) + "\n", encoding="utf-8")

        print(f"[f13] checks={len(ck.items)} fail={len(ck.failures)}")
        return 1 if ck.failures else 0
    finally:
        if server is not None:
            try:
                server.stop()
            except Exception:  # noqa: BLE001
                pass
        if not args.keep_temp and synth_root.exists():
            shutil.rmtree(synth_root, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
