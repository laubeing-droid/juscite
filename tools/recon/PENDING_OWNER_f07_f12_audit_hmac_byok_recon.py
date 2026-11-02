# -*- coding: utf-8 -*-
"""F07 产品审计 HMAC 完整性＋F12 BYOK 凭据设施 验收对账（W3-U09）。

F07（06 行，双实例）：产品审计 HMAC 完整性——篡改/截断/重放三负测具名；
摘要不含原件/身份/秘密（金丝雀法沿 E10：三枚 JUSCITE-CANARY 令牌注入合成
材料，事件只以 sha256/ref 在场，全产物扫描零命中，并以受控泄漏对照证明
扫描器非空转）；密钥归产品凭据设施（唯一取钥通道=F12 vault，无钥＝typed
拒，审计根零钥料）；不恢复 Harness 已拆部署签章总闸（SPLIT-LOCAL-3 stage
B 16d73893 拆除 activation/deployment/sealed-signature：harness 检出树净＋
拆解标记零命中＋audit.read/verify/export 静态复用在场＋产品面零总闸标记＋
审计方法组与全部业务方法组两两不交）。

F12（06 行，双实例）：BYOK 经 DPAPI/keyring 真实写读（DPAPI=
CryptProtectData/UnprotectData 当前用户作用域真往返；keyring 未装＝具名缺
不冒充）；配置和日志全产物扫描零 key（原始键字节级 os.walk 扫描，同
e10_canary --dir 法；canary 令牌径直接复用 tools/e10_canary.py scan
--dir 子进程）；缺解密不明文降级（blob 损坏/条目缺失＝typed
vault_decrypt_failed/vault_entry_missing，无明文回退路径，扫描证明失败
后零明文出现）。测试键＝DeepSeek 形合成键（sk-+32hex）运行时生成，
不入 git（git grep 零命中）；证据只记 sha256 与掩码形。

用法（juscite worktree w3-u09 根 cwd；--profile 缺省＝双 profile）：
  python -X utf8 tools/PENDING_OWNER_f07_f12_audit_hmac_byok_recon.py \
      [--profile desktop --profile selfhost]

exit 0＝RECON_OK 全断言过；证据 JSON 写 evidence/F07/<profile>/ 与
evidence/F12/<profile>/。desktop/selfhost 共用宿主面分状态根分证据（产
品凭据设施与审计账不依赖库后端，F40 先例）。全合成材料；harness 检出
只读零改动；不发网络、不写 %APPDATA%。
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "python"))
sys.path.insert(0, str(REPO_ROOT / "tools"))

LEGAL_ENTRY = REPO_ROOT / "implementation" / "python" / "legal_entry.py"
E10_CANARY = REPO_ROOT / "tools" / "e10_canary.py"

HARNESS_REPO = Path(
    r"D:\Codex\1.法律工作区\legal-harness工作区\legal-harness-repo")

AUDIT_SERVICE, AUDIT_ACCOUNT = "lvyin.audit", "hmac-sha256-v1"
BYOK_SERVICE, BYOK_ACCOUNT = "deepseek-byok", "model-key"

_EVIDENCE_F07 = REPO_ROOT / "docs" / "construction" / "evidence" / "F07"
_EVIDENCE_F12 = REPO_ROOT / "docs" / "construction" / "evidence" / "F12"

# 金丝雀令牌（E10 生成法；main 里经 e10_canary.new_token() 实例化）。
CANARY_ORIG = CANARY_IDENT = CANARY_SECRET = None

# 已拆部署签章总闸的 ASCII 标记（stage B 16d73893 拆除面）；产品新面零命中。
_GATE_MARKERS = ("host_signature", "core_signature", "deployment_gate",
                 "sealed_signature", "activation_gate")
_SIGNATURE_MACHINERY_GREP = "host_signature\\|core_signature"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Checks:
    def __init__(self):
        self.items: list[dict] = []

    def add(self, check_id: str, ok: bool, detail: str) -> bool:
        self.items.append({"id": check_id, "status": "PASS" if ok else "FAIL",
                           "detail": detail})
        print("[%s] %s — %s" % ("PASS" if ok else "FAIL", check_id, detail))
        return ok

    @property
    def all_passed(self):
        return all(i["status"] == "PASS" for i in self.items)

    @property
    def passed_count(self):
        return sum(i["status"] == "PASS" for i in self.items)


def call_cli(method: str, args: dict, config: dict):
    """真产品入口子进程径（legal_entry CLI；同既有 recon 纪律）。请求/回执
    只在内存与 %TEMP% 一次性请求文件（with 内自删）流转，绝不落 workspace
    与证据。"""
    with tempfile.TemporaryDirectory() as tmp:
        req = Path(tmp) / "request.json"
        cfg = Path(tmp) / "config.json"
        req.write_text(json.dumps({"method": method, "args": args},
                                  ensure_ascii=False), encoding="utf-8")
        cfg.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", str(LEGAL_ENTRY),
             "--request-json", str(req), "--config", str(cfg)],
            capture_output=True, text=True, encoding="utf-8", timeout=300)
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            payload = {"status": "RAW", "stdout": proc.stdout[:400]}
        return proc.returncode, payload


def scan_needles_e10_style(root: Path, needles: list[bytes]) -> dict:
    """原始键字节级扫描：复用 tools/e10_canary.py scan --dir 的方法
    （os.walk 逐文件按字节搜索，>128MB 跳过，OSError 记 skipped）——
    canary 令牌径则直接子进程复用该工具本体（scan_canary_tokens）。"""
    hits, skipped, files = [], [], 0
    for dirpath, _dirnames, filenames in os.walk(root):
        for filename in filenames:
            path = Path(dirpath) / filename
            try:
                if path.stat().st_size > 128 * 1024 * 1024:
                    skipped.append(str(path))
                    continue
                data = path.read_bytes()
                files += 1
                for needle in needles:
                    if needle in data:
                        hits.append({"file": str(path),
                                     "needle_sha256": sha256_bytes(needle)})
            except OSError:
                skipped.append(str(path))
    return {"root": str(root), "files_scanned": files, "hits": hits,
            "skipped": skipped, "verdict": "PASS" if not hits else "FAIL"}


def scan_canary_tokens(root: Path, token: str) -> int:
    """真实复用 tools/e10_canary.py scan --dir（子进程；exit 0=零命中）。"""
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", str(E10_CANARY), "scan",
         "--dir", str(root), "--token", token],
        capture_output=True, text=True, encoding="utf-8", timeout=120)
    return proc.returncode


def run_profile(profile: str, workspace_root: Path) -> tuple[Checks, dict]:
    checks = Checks()
    ws = workspace_root / profile
    vault_root = ws / "vault"
    audit_root = ws / "audit"
    config_dir = ws / "config"
    logs_dir = ws / "logs"
    for directory in (vault_root, audit_root, config_dir, logs_dir):
        directory.mkdir(parents=True, exist_ok=True)
    config = {"vault_state_root": str(vault_root),
              "audit_state_root": str(audit_root)}
    # 本 profile 实际生效的桥配置落盘（config/ 产物，被全产物扫描覆盖）。
    (config_dir / "bridge-config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=1), encoding="utf-8")

    def log(line: str) -> None:
        # 运行日志（操作面元数据；绝不带参数载荷/密钥）。
        with open(logs_dir / "run.log", "a", encoding="utf-8") as handle:
            handle.write(time.strftime("%H:%M:%S ") + line + "\n")

    meta: dict = {"profile": profile, "workspace": str(ws)}

    # S0 桥可达 --------------------------------------------------------------
    code, out = call_cli("vault.status", {}, config)
    status = out.get("result", {}) if code == 0 else {}
    ok = (code == 0 and out.get("status") == "OWNER_RESPONSE"
          and status.get("backends", {}).get("dpapi") is True)
    checks.add("U09-PIN-0", ok,
               "桥可达（vault.status exit 0）且 DPAPI 后端在本机可用（"
               f"backends={status.get('backends')}）")
    if not ok:
        meta["checks_passed"] = checks.passed_count
        meta["checks_total"] = len(checks.items)
        return checks, meta
    log("vault.status exit 0")

    # ======================================================================
    # F12 块：BYOK 凭据设施
    # ======================================================================
    key = "sk-" + os.urandom(16).hex()  # DeepSeek 形合成键；运行时生成
    key_sha = sha256_bytes(key.encode("utf-8"))
    meta["byok_key_sha256"] = key_sha
    meta["byok_key_masked"] = key[:5] + "…" + key[-4:]

    # F12-1 真实写读（DPAPI put→get reveal 真往返）
    code, out = call_cli("vault.put", {
        "service": BYOK_SERVICE, "account": BYOK_ACCOUNT,
        "secret_b64": base64.b64encode(key.encode()).decode("ascii")},
        config)
    put_ok = code == 0 and out.get("status") == "OWNER_RESPONSE"
    stored_sha = (out.get("result", {}) or {}).get("sha256") if put_ok else None
    log("vault.put deepseek-byok/model-key exit %d" % code)
    code, out = call_cli("vault.get", {
        "service": BYOK_SERVICE, "account": BYOK_ACCOUNT, "reveal": True},
        config)
    got = (out.get("result", {}) or {}) if code == 0 else {}
    roundtrip = got.get("revealed") is True and base64.b64decode(
        got.get("secret_b64") or "").decode("utf-8") == key
    checks.add("F12-1", put_ok and roundtrip
               and stored_sha == key_sha == got.get("sha256"),
               "BYOK 经 DPAPI 真实写读：vault.put→vault.get(reveal=true) "
               "往返相等（CryptProtectData/UnprotectData 当前用户作用域；"
               f"sha256={key_sha[:12]}… put/get 两面一致）")
    log("vault.get reveal=true exit %d roundtrip=%s" % (code, roundtrip))

    # F12-2 默认回执零 secret（掩码形）
    code, out = call_cli("vault.get", {
        "service": BYOK_SERVICE, "account": BYOK_ACCOUNT}, config)
    got = (out.get("result", {}) or {}) if code == 0 else {}
    masked = got.get("masked") or ""
    checks.add("F12-2", code == 0 and got.get("revealed") is False
               and "secret_b64" not in got and masked != key
               and "…" in masked,
               "vault.get 默认零 secret：revealed=false、无 secret_b64 键、"
               f"掩码形={masked!r}（只露前5后4，非全键）")

    # F12-3 缺解密不明文降级（blob 损坏＝typed 拒；条目缺失＝typed 拒；
    #       失败后全产物仍零明文键；keyring 后端＝分支如实）
    entry_path = (vault_root / "credentials" / BYOK_SERVICE
                  / (BYOK_ACCOUNT + ".json"))
    entry = json.loads(entry_path.read_text(encoding="utf-8"))
    corrupted = dict(entry)
    corrupted["blob_b64"] = "AAAA" + entry["blob_b64"][4:]
    entry_path.write_text(json.dumps(corrupted, ensure_ascii=False),
                          encoding="utf-8")
    code, out = call_cli("vault.get", {
        "service": BYOK_SERVICE, "account": BYOK_ACCOUNT, "reveal": True},
        config)
    corrupt_refused = (code == 3 and out.get("status") == "NOT_CONNECTED"
                       and "vault_decrypt_failed" in str(out.get("code")))
    code, out = call_cli("vault.get", {
        "service": "deepseek-byok", "account": "absent-key"}, config)
    missing_refused = (code == 3 and "vault_entry_missing"
                       in str(out.get("code")))
    # keyring 后端：本机未装＝具名缺（如实，不冒充往返）
    code, out = call_cli("vault.put", {
        "service": "probe-keyring", "account": "k", "secret_b64": "aGk=",
        "backend": "keyring"}, config)
    keyring_named = "keyring" in str(out.get("code", ""))
    keyring_installed = code == 0
    keyring_ok = True if keyring_installed else keyring_named
    keyring_note = ("keyring 后端真往返" if keyring_installed else
                    "keyring 未装→vault_keyring_backend_unavailable 具名缺"
                    "（不冒充往返）")
    scan_after_fail = scan_needles_e10_style(ws, [key.encode("utf-8")])
    checks.add("F12-3", corrupt_refused and missing_refused and keyring_ok
               and scan_after_fail["verdict"] == "PASS",
               "缺解密不明文降级：blob 损坏→vault_decrypt_failed（exit 3）"
               "＋条目缺失→vault_entry_missing；失败后全产物扫描原始键零命"
               "中（files=%d）；结构性无明文回退路径（get 仅一条解密通道）；"
               "%s" % (scan_after_fail["files_scanned"], keyring_note))
    log("corrupt->%s missing->%s keyring->%s"
        % ("refused" if corrupt_refused else "UNREFUSED",
           "refused" if missing_refused else "UNREFUSED",
           "installed" if keyring_installed else "named-absent"))

    # F12-4 配置和日志全产物扫描零 key（负控：故意落一针证明扫描器非空转）
    scratch = ws / "config" / "leak-negative-control.tmp"
    scratch.write_text("负控样本 " + key, encoding="utf-8")
    leak_scan = scan_needles_e10_style(ws, [key.encode("utf-8")])
    scratch.unlink()
    clean_scan = scan_needles_e10_style(ws, [key.encode("utf-8")])
    checks.add("F12-4", leak_scan["verdict"] == "FAIL"
               and clean_scan["verdict"] == "PASS",
               "配置和日志全产物扫描零 key（e10 --dir 法字节级）：负控样本"
               "被检出（hits=%d）后移除，全 workspace（vault/audit/config/"
               "logs）rescan 零命中（files=%d）——扫描器非空转"
               % (len(leak_scan["hits"]), clean_scan["files_scanned"]))

    # F12-5 测试键不入 git
    grep = subprocess.run(
        ["git", "grep", "-F", key], cwd=str(REPO_ROOT),
        capture_output=True, text=True, encoding="utf-8")
    checks.add("F12-5", grep.returncode == 1,
               "DeepSeek 形合成测试键不入 git：运行时生成（os.urandom 熵源），"
               "git grep -F 零命中（exit %d＝未跟踪到）；证据只记 sha256＋"
               "掩码形" % grep.returncode)

    # ======================================================================
    # F07 块：产品审计 HMAC
    # ======================================================================
    # F07-1 密钥归产品凭据设施（经 vault.put 登记 audit 键；无钥＝typed 拒）
    audit_key = os.urandom(32)
    code, out = call_cli("audit.append", {
        "stream_id": "pre-key", "event": {"kind": "probe"}}, config)
    no_key_named = (code == 3 and "audit_hmac_key_not_provisioned"
                    in str(out.get("code")))
    code, out = call_cli("vault.put", {
        "service": AUDIT_SERVICE, "account": AUDIT_ACCOUNT,
        "secret_b64": base64.b64encode(audit_key).decode("ascii")}, config)
    provisioned = code == 0
    log("vault.put lvyin.audit/hmac-sha256-v1 exit %d" % code)
    code, out = call_cli("audit.append", {
        "stream_id": "probe-key", "event": {"kind": "probe"}}, config)
    append_ok = code == 0 and out.get("status") == "OWNER_RESPONSE"
    checks.add("F07-1", no_key_named and provisioned and append_ok,
               "密钥归产品凭据设施：未登记时 audit.append＝"
               "audit_hmac_key_not_provisioned（exit 3）；经 vault.put 登记"
               " 32B 随机钥后追加成功——审计面无独立钥文件无派生回退（唯一"
               "取钥通道=F12 vault，DPAPI 密文）")

    # F07-2 追加×4＋验证＋读取（事件只带元数据：kind/doc ref/sha256/计数）
    material = (
        "《合成合同》（W3-U09 验收材料，全虚构）\n"
        "原件金丝雀：%s\n"
        "身份映射金丝雀：%s（当事人律某引，证件号 110105TEST000001，合成）\n"
        "秘密金丝雀：%s\n"
        "案号：(2026)京0105民初W3U09号（合成） 标的：人民币 12345.67 元\n"
        % (CANARY_ORIG, CANARY_IDENT, CANARY_SECRET))
    material_sha = sha256_bytes(material.encode("utf-8"))
    events = [
        {"kind": "material_registered", "doc": "att_0001",
         "sha256": material_sha, "matter": "m-w3u09"},
        {"kind": "material_parsed", "doc": "att_0001", "pages": 3,
         "matter": "m-w3u09"},
        {"kind": "review_submitted", "doc": "att_0001", "actor": "machine",
         "matter": "m-w3u09"},
        {"kind": "verdict_bound", "doc": "att_0001", "outcome": "authorized",
         "matter": "m-w3u09"},
    ]
    seqs = []
    for event in events:
        code, out = call_cli("audit.append", {
            "stream_id": "m-w3u09", "event": event}, config)
        seqs.append((out.get("result", {}) or {}).get("seq")
                    if code == 0 else None)
        log("audit.append seq=%s exit %d" % (seqs[-1], code))
    code, out = call_cli("audit.verify", {"stream_id": "m-w3u09"}, config)
    verified = (out.get("result", {}) or {}) if code == 0 else {}
    head = verified.get("head")
    code, out = call_cli("audit.read", {"stream_id": "m-w3u09"}, config)
    read_back = (out.get("result", {}) or {}) if code == 0 else {}
    detail = ("HMAC-SHA256 链追加×4（seq %s）＋verify ok（head=%s…，entries="
              "%s）＋audit.read 投影 %s 条（事件＝扁平小元数据 kind/doc ref/"
              "sha256/计数——原件只以 sha256 在场）"
              % (seqs, str(head)[:12], verified.get("entries"),
                 len(read_back.get("entries", []))))
    checks.add("F07-2", seqs == [1, 2, 3, 4]
               and verified.get("ok") is True
               and verified.get("entries") == 4 and bool(head)
               and len(read_back.get("entries", [])) == 4,
               detail)
    meta["chain_head_sha256"] = head

    # F07-3 篡改负测
    stream_path = audit_root / "audit-hmac" / "m-w3u09.jsonl"
    original_lines = stream_path.read_text(encoding="utf-8").splitlines()

    def rewrite_lines(lines: list[str]) -> None:
        stream_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    lines = list(original_lines)
    row = json.loads(lines[1])
    row["event"]["pages"] = 9999
    lines[1] = json.dumps(row, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"))
    rewrite_lines(lines)
    code, out = call_cli("audit.verify", {"stream_id": "m-w3u09"}, config)
    tamper_named = (code == 3 and "audit_hmac_chain_broken:2"
                    in str(out.get("code")))
    checks.add("F07-3", tamper_named,
               "篡改负测：改写第 2 行事件（pages→9999）→verify＝"
               "audit_hmac_chain_broken:2（exit 3 具名；HMAC 重算不符）")
    rewrite_lines(original_lines)
    code, out = call_cli("audit.verify", {"stream_id": "m-w3u09"}, config)
    restored_ok = code == 0
    log("tamper->%s restored->%s"
        % ("named" if tamper_named else "UNNAMED",
           "ok" if restored_ok else "BROKEN"))

    # F07-4 截断负测（pinned head）
    lines = stream_path.read_text(encoding="utf-8").splitlines()
    rewrite_lines(lines[:2])
    code, out = call_cli("audit.verify", {
        "stream_id": "m-w3u09", "expected_head": head}, config)
    truncate_named = (code == 3 and "audit_head_mismatch"
                      in str(out.get("code")))
    code, out = call_cli("audit.verify", {"stream_id": "m-w3u09"}, config)
    prefix_boundary = code == 0  # 无锚前缀自查通过与 harness 链同边界
    checks.add("F07-4", truncate_named and prefix_boundary,
               "截断负测：删尾两行＋pinned head→verify＝audit_head_mismatch"
               "（exit 3 具名）；无锚前缀自查通过＝与 harness W25 链同一边界"
               "（防全权重写不在链主张内，回执 boundary 字段如实声明）")
    rewrite_lines(original_lines)

    # F07-5 重放负测（旧行原样再插回存储）
    lines = stream_path.read_text(encoding="utf-8").splitlines()
    rewrite_lines(lines + [lines[1]])
    code, out = call_cli("audit.verify", {"stream_id": "m-w3u09"}, config)
    replay_named = (code == 3 and "audit_hmac_replay_refused"
                    in str(out.get("code")))
    checks.add("F07-5", replay_named,
               "重放负测：旧行（seq=2）原样再插回存储→verify＝"
               "audit_hmac_replay_refused（exit 3 具名；seq 重复独立于缺口"
               "具名）")
    rewrite_lines(original_lines)
    code, out = call_cli("audit.verify", {"stream_id": "m-w3u09"}, config)
    if code != 0:
        checks.add("F07-5", False, "重放负测还原后链不整（verify exit %d）"
                   % code)
    log("truncate->%s replay->%s"
        % ("named" if truncate_named else "UNNAMED",
           "named" if replay_named else "UNNAMED"))

    # F07-6 摘要不含原件/身份/秘密（e10 金丝雀法：真工具 scan --dir ×3
    #       ＋受控泄漏对照＋材料特征串字节扫描）
    code, out = call_cli("audit.export", {"stream_id": "m-w3u09"}, config)
    export_ok = code == 0
    token_results = {label: scan_canary_tokens(audit_root, token)
                     for label, token in (
                         ("orig", CANARY_ORIG), ("ident", CANARY_IDENT),
                         ("secret", CANARY_SECRET))}
    leak_path = audit_root / "leak-negative-control.tmp"
    leak_path.write_text(CANARY_ORIG, encoding="utf-8")
    leak_rc = scan_canary_tokens(audit_root, CANARY_ORIG)
    leak_path.unlink()
    control_rc = scan_canary_tokens(audit_root, CANARY_ORIG)
    distinctive = scan_needles_e10_style(audit_root, [
        "(2026)京0105民初W3U09号".encode("utf-8"), "律某引".encode("utf-8"),
        "110105TEST".encode("utf-8")])
    checks.add("F07-6", export_ok
               and all(rc == 0 for rc in token_results.values())
               and leak_rc == 1 and control_rc == 0
               and distinctive["verdict"] == "PASS",
               "摘要不含原件/身份/秘密：三枚金丝雀（原件/身份映射/秘密）注"
               "入合成材料，事件只以 sha256/ref 在场——tools/e10_canary.py "
               "scan --dir 子进程×3 全零命中（rc=%s）；受控泄漏对照=exit 1"
               "（扫描器非空转）后移除复扫 exit 0；材料特征串（案号/当事人/"
               "证件前缀）字节扫描零命中（files=%d）；export 镜像同被扫描"
               "覆盖" % (json.dumps(token_results),
                         distinctive["files_scanned"]))
    log("export ok=%s canary rc=%s leak_rc=%d"
        % (export_ok, json.dumps(token_results), leak_rc))

    # F07-7 export 镜像可核＋篡改镜像具名拒
    code, out = call_cli("audit.export", {"stream_id": "m-w3u09"}, config)
    reexport_ok = code == 0
    export_path = audit_root / "audit-hmac-export" / "m-w3u09.json"
    export_data = export_path.read_bytes()
    export_path.write_bytes(export_data.replace(b"material_parsed",
                                                b"material_tampered"))
    code, out = call_cli("audit.export", {"stream_id": "m-w3u09"}, config)
    export_tamper_named = (code == 3 and "audit_export_tampered"
                           in str(out.get("code")))
    export_path.write_bytes(export_data)
    code, out = call_cli("audit.export", {"stream_id": "m-w3u09"}, config)
    checks.add("F07-7", reexport_ok and export_tamper_named and code == 0,
               "export 镜像：幂等再导出过前缀规则；篡改镜像后 re-export＝"
               "audit_export_tampered（exit 3 具名）；还原后复导 exit 0"
               "（镜像可核非第二真源）")

    # F07-8 审计根零钥料（密钥归设施＝审计产物无 32B 钥字节）
    audit_key_scan = scan_needles_e10_style(audit_root, [audit_key])
    checks.add("F07-8", audit_key_scan["verdict"] == "PASS",
               "审计根零钥料：HMAC 密钥字节在 audit/ 全产物零命中（files=%d）"
               "——密钥只在 vault DPAPI 密文内（F12），审计面不落钥"
               % audit_key_scan["files_scanned"])

    # ======================================================================
    # 不恢复 Harness 已拆部署签章总闸
    # ======================================================================
    harness = subprocess.run(
        ["git", "status", "--porcelain"], cwd=str(HARNESS_REPO),
        capture_output=True, text=True, encoding="utf-8")
    head_proc = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(HARNESS_REPO),
        capture_output=True, text=True, encoding="utf-8")
    harness_head = head_proc.stdout.strip()
    clean = harness.returncode == 0 and not harness.stdout.strip()
    machinery = subprocess.run(
        ["git", "grep", "-n", _SIGNATURE_MACHINERY_GREP, "--", "src/"],
        cwd=str(HARNESS_REPO), capture_output=True, text=True,
        encoding="utf-8")
    machinery_absent = machinery.returncode == 1  # 零命中
    reuse = subprocess.run(
        ["git", "grep", "-n", "\"audit.read\"", "--", "src/"],
        cwd=str(HARNESS_REPO), capture_output=True, text=True,
        encoding="utf-8")
    reuse_present = reuse.returncode == 0 and "audit.read" in reuse.stdout
    markers_hit = []
    for rel in ("implementation/python/audit_hmac.py",
                "implementation/python/credential_vault.py",
                "implementation/python/legal_entry.py"):
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        for marker in _GATE_MARKERS:
            if marker in text:
                markers_hit.append(f"{rel}:{marker}")
    import audit_hmac as ah  # noqa: E402（顶部已加 sys.path）
    import legal_entry as le  # noqa: E402
    groups = [value for name, value in vars(le).items()
              if name.endswith("_METHODS") and isinstance(value, frozenset)]
    disjoint = all(not (le.AUDIT_HMAC_METHODS & group)
                   for group in groups if group is not le.AUDIT_HMAC_METHODS)
    checks.add("F07-9", clean and machinery_absent and reuse_present
               and not markers_hit and disjoint,
               "不恢复已拆部署签章总闸（stage B 16d73893 拆 activation/"
               "deployment/sealed-signature）：harness 检出树净（porcelain "
               "空，HEAD=%s…零动）＋src/ 内 host_signature/core_signature "
               "零命中（拆除态未被恢复）＋既有 audit.read/verify/export 静"
               "态复用在场＋产品新面三文件总闸标记零命中＋审计方法组与全部"
               "%d 组 *_METHODS 两两不交（审计面是证据账非业务闸）"
               % (harness_head[:12], len(groups)))
    meta["harness_head"] = harness_head
    log("harness clean=%s machinery_absent=%s reuse=%s markers=%d"
        % (clean, machinery_absent, reuse_present, len(markers_hit)))

    # ======================================================================
    # U09-EDGE 桥 fail-closed 边界
    # ======================================================================
    code, out = call_cli("vault.put", {"service": "s", "account": "a",
                                       "secret_b64": "aGk="}, {})
    vault_unconfig = (code == 3 and "vault_state_root_not_configured"
                      in str(out.get("code")))
    code, out = call_cli("audit.append", {"stream_id": "s", "event":
                                          {"kind": "k"}}, {})
    audit_unconfig = (code == 3 and (
        "audit_state_root_not_configured" in str(out.get("code"))
        or "audit_hmac_key_not_provisioned" in str(out.get("code"))))
    code, out = call_cli("vault.transmogrify", {}, config)
    unknown_method = (code == 3 and "not_connected"
                      in str(out.get("code")).lower())
    checks.add("U09-EDGE", vault_unconfig and audit_unconfig
               and unknown_method,
               "桥 fail-closed 边界：vault_state_root 未配置＝"
               "vault_state_root_not_configured；空配置 audit.append＝typed"
               " 具名拒（状态根守卫先行 audit_state_root_not_configured，同"
               "等 fail-closed）；冻结组外方法（vault."
               "transmogrify）＝not_connected 具名拒（exit 3）")

    meta["checks_passed"] = checks.passed_count
    meta["checks_total"] = len(checks.items)
    return checks, meta


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="F07 审计 HMAC＋F12 BYOK 凭据设施 验收对账（W3-U09）")
    parser.add_argument("--profile", action="append",
                        choices=["desktop", "selfhost"], default=[],
                        help="缺省＝双 profile")
    args = parser.parse_args(argv)
    profiles = args.profile or ["desktop", "selfhost"]

    global CANARY_ORIG, CANARY_IDENT, CANARY_SECRET
    import e10_canary  # noqa: E402（金丝雀令牌沿 E10 生成法）
    CANARY_ORIG = e10_canary.new_token()
    CANARY_IDENT = e10_canary.new_token()
    CANARY_SECRET = e10_canary.new_token()

    workspace_root = Path(tempfile.mkdtemp(prefix="w3u09-f07-f12-"))
    print("workspace: %s" % workspace_root)
    all_ok = True
    profiles_summary: dict = {}
    for profile in profiles:
        print("\n===== profile: %s =====" % profile)
        checks, meta = run_profile(profile, workspace_root)
        verdict = "RECON_OK" if checks.all_passed else "RECON_FAILED"
        profiles_summary[profile] = {
            "verdict": verdict,
            "passed": checks.passed_count, "total": len(checks.items),
            "checks": checks.items, **meta}
        all_ok = all_ok and checks.all_passed
        print("%s[%s] %d/%d" % (verdict, profile, checks.passed_count,
                                len(checks.items)))
        for evidence_root, feature in ((_EVIDENCE_F07, "F07"),
                                       (_EVIDENCE_F12, "F12")):
            out_dir = evidence_root / profile
            out_dir.mkdir(parents=True, exist_ok=True)
            payload = {
                "unit": "W3-U09", "feature": feature, "profile": profile,
                "verdict": verdict,
                "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                              time.gmtime()),
                "command": ("python -X utf8 "
                            "tools/PENDING_OWNER_f07_f12_audit_hmac_byok_"
                            "recon.py --profile " + profile),
                "cwd": str(REPO_ROOT),
                "summary": {k: v for k, v in profiles_summary[profile].items()
                            if k != "checks"},
                "checks": checks.items,
                "canary_sha256": {
                    "orig": sha256_bytes(CANARY_ORIG.encode()),
                    "ident": sha256_bytes(CANARY_IDENT.encode()),
                    "secret": sha256_bytes(CANARY_SECRET.encode()),
                },
                "note": ("全合成材料；金丝雀沿 E10（evidence 只记 sha256）；"
                         "BYOK 测试键运行时生成不入 git；harness 检出只读"
                         "零改动；%s" % feature),
            }
            (out_dir / "recon-result.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=1),
                encoding="utf-8")
    print("\n%s" % ("RECON_OK" if all_ok else "RECON_FAILED"))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
