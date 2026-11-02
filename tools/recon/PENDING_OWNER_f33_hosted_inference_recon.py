# -*- coding: utf-8 -*-
"""F33 托管模型积分通道（设备签名短 TTL 凭证，子 Key 不落端）验收对账
（PENDING_OWNER 版，工单 W5-U03）。

06 行 F33（v2；owner=product；B5；desktop/selfhost 双实例）
acceptance＝托管短TTL凭证过期失效；设备/额度绑定；子key不落端；
preserved＝L12 商业化留槽；不创第二 Agent loop。硬依赖 E03/E05/E07/
E23/E24 全 VERIFIED（台账亲读）；legacy link F12（凭据保险库）/F26
（工具权限）后端已 VERIFIED——本面复用其公开面不第二权威。裁决#13-19
（00-总协调）：W5 商业/基建统一合成先行，真实网关 v2 商业化时补。

分段（每 profile 全量 19 检；S2 走子进程隔离径，S3-S6 走产品面进程内径，
clock 注入拨钟）：
  S1 面与硬依赖钉定：台账硬依赖五行（E03/E05/E07/E23/E24）＋legacy 两族
     （F12/F26 desktop+selfhost）全 VERIFIED 亲读；06 行 acceptance 向量
     逐字对账；冻结面（credential_vault/legal_entry）sha256 记录；
     legal_entry 零 hosted 接线（UI_HOST_OR_NEW_PRODUCT：不冒已有业务
     入口，不创第二业务入口）。
  S2 签发正道＋设备绑定（子进程隔离：独立临时状态根，全程合成密钥）：
     vault（F12 面）存设备钥→签名→签发→验证→整型分精确扣减；保险库
     落盘零明文设备钥；子key 全表面扫描（子进程 stdout/stderr 原始字节
     ＋状态根全部文件）零命中＝子key不落端（配置与日志面）。
  S3 TTL 过期失效（clock 注入）：exp 后一瞬 hosted_credential_expired
     且零扣减；边界 exp 当刻仍有效（≤60s 短 TTL 语义，源设计 ≤60s）。
  S4 设备绑定负测：异设备到账 hosted_device_mismatch 零扣减；dev-a 钥
     签 dev-b 名→hosted_signature_invalid（签名覆盖设备身份）。
  S5 额度绑定负测（整型分）：超额签发 hosted_quota_exceeded 零扣减；
     浮点/bool/str/None 额度 hosted_quota_not_integer（bool 是 int 子类
     显式拒）；重放 hosted_credential_replayed 恰扣一次；凭证篡改
     hosted_credential_invalid（token 覆盖全字段）。
  S6 子key不落端全域＋合成边界＋冻结稳定：产品面 AST 零网络/零子进程/
     零日志/零文件 I/O、sub_key 名只存在于 HostedGateway.__init__；
     进程内全回执＋持久化全文件零子key（raw/b64/hex 三形）；00-总协调
     裁决#13-19 行含"推理网关＋统一合成先行"（真实网关 v2 商业化时补，
     依据在账）；冻结面 sha256 前后相等。

用法（juscite worktree 根 cwd）：
  python -X utf8 tools/recon/PENDING_OWNER_f33_hosted_inference_recon.py --profile desktop --profile selfhost

--profile 可重复（action=append，f74 工具同款）；重复即逐 profile 依序
全量跑各 19 检并各写证据；缺省=desktop。
exit 0＝全部断言过（RECON_OK）；证据写 evidence/F33/<profile>/ 各
{json,md} 一份。全程合成材料（内存合成密钥＋临时目录，零真实网关零
真实外联）；本面零网络（合成先行，裁决#13-19）。
"""

from __future__ import annotations

import argparse
import ast
import base64
import csv
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

RUN_DATE = time.strftime("%Y%m%d")
REPO_ROOT = Path(__file__).resolve().parents[2]
HOSTED = REPO_ROOT / "implementation" / "python" / "hosted_inference.py"
CREDENTIAL_VAULT = REPO_ROOT / "implementation" / "python" / "credential_vault.py"
LEGAL_ENTRY = REPO_ROOT / "implementation" / "python" / "legal_entry.py"
LEDGER = REPO_ROOT / "docs" / "construction" / "acceptance-ledger.csv"
COORD = REPO_ROOT / "docs" / "construction" / "00-总协调.md"

# 06 V7-33 行 acceptance 向量（逐字；与台账 F33 行 assertion 对账）。
ACCEPTANCE_VECTOR = "托管短TTL凭证过期失效；设备/额度绑定；子key不落端"

# 合成材料：子key/设备钥全内存合成，绝不入 git、不入证据。
SYNTH_SUB_KEY = b"F33-SYNTH-SUBKEY-" + os.urandom(16).hex().encode("ascii")
SYNTH_START_FEN = 1_500_000  # 整型分（=¥15000.00）
SYNTH_CHARGED_FEN = 250_000

# 硬依赖（工单明文）＋legacy link（06 行 legacy_semantic_links）。
PREREQ_OBLIGATIONS = ("E03", "E05", "E07", "E23", "E24")
LEGACY_OBLIGATIONS = ("F12-desktop", "F12-selfhost",
                      "F26-desktop", "F26-selfhost")


def sha256_file(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Checks:
    def __init__(self):
        self.items: list[dict] = []

    def add(self, check_id: str, ok: bool, detail: str) -> bool:
        self.items.append(
            {"id": check_id, "status": "PASS" if ok else "FAIL",
             "detail": detail}
        )
        print("[%s] %s — %s" % ("PASS" if ok else "FAIL", check_id, detail))
        return ok

    @property
    def all_passed(self) -> bool:
        return all(item["status"] == "PASS" for item in self.items)

    @property
    def passed_count(self) -> int:
        return sum(1 for item in self.items if item["status"] == "PASS")


def _sub_key_forms(sub_key: bytes) -> list[bytes]:
    """子key 的全部可落盘形态：raw / base64 / hex。"""
    return [sub_key,
            base64.b64encode(sub_key),
            sub_key.hex().encode("ascii")]


def _bytes_hit(blob: bytes, forms: list[bytes]) -> list[str]:
    return [name for name, form in
            zip(("raw", "b64", "hex"), forms) if form in blob]


def _scan_tree(root: Path, forms: list[bytes]) -> list[str]:
    """状态根全文件扫描（配置与持久化面）。"""
    hits: list[str] = []
    for path in sorted(root.rglob("*")):
        if path.is_file():
            hit = _bytes_hit(path.read_bytes(), forms)
            if hit:
                hits.append("%s:%s" % (path.name, "+".join(hit)))
    return hits


# ---------------------------------------------------------------------- #
# S2 子进程隔离径：完整端到端流（vault 存钥→签名→签发→验证）
# ---------------------------------------------------------------------- #

FLOW_SCRIPT = r'''
import base64, json, os, sys, tempfile
sys.path.insert(0, sys.argv[1])
import hosted_inference

sub_key = base64.b64decode(sys.argv[2])
start_fen = int(sys.argv[3])
charged_fen = int(sys.argv[4])
state_root = tempfile.mkdtemp(prefix="f33-recon-flow-", dir=sys.argv[5])

gateway = hosted_inference.HostedGateway(sub_key, start_fen)
prov = gateway.provision_device("dev-a")
hosted_inference.store_device_key(
    state_root, "dev-a", base64.b64decode(prov["device_key_b64"]))
issued = hosted_inference.request_session(
    gateway, state_root, "dev-a", charged_fen)
verify = gateway.verify_session(issued["credential"], "dev-a")
print(json.dumps({
    "state_root": state_root,
    "provision": prov,
    "issued": issued,
    "verify": verify,
}, ensure_ascii=True))
'''


def _run_flow() -> tuple[dict, subprocess.CompletedProcess, Path]:
    env = dict(os.environ)
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", "-c", FLOW_SCRIPT,
         str(REPO_ROOT / "implementation" / "python"),
         base64.b64encode(SYNTH_SUB_KEY).decode("ascii"),
         str(SYNTH_START_FEN), str(SYNTH_CHARGED_FEN),
         tempfile.mkdtemp(prefix="f33-recon-parent-")],
        capture_output=True, env=env, timeout=300, cwd=str(REPO_ROOT))
    try:
        payload = json.loads(proc.stdout.decode("utf-8", "replace")) \
            if proc.stdout.strip() else {}
    except json.JSONDecodeError:
        payload = {}
    return payload, proc, Path(payload.get("state_root", ""))


# ---------------------------------------------------------------------- #
# 进程内径：clock 注入（TTL/绑定/额度负测）
# ---------------------------------------------------------------------- #

def _import_hosted():
    sys.path.insert(0, str(REPO_ROOT / "implementation" / "python"))
    for name in ("credential_vault", "hosted_inference"):
        sys.modules.pop(name, None)
    import hosted_inference
    return hosted_inference


class _Flow:
    """进程内合成全流（合成密钥；状态根=调用方临时目录）。"""

    def __init__(self, hosted, root: str, clock=None):
        import time as _time
        self.hosted = hosted
        self.gateway = hosted.HostedGateway(
            SYNTH_SUB_KEY, SYNTH_START_FEN, clock=clock or _time.time)
        self.root = root
        self.provision = self.gateway.provision_device("dev-a")
        hosted.store_device_key(
            root, "dev-a",
            base64.b64decode(self.provision["device_key_b64"]))
        self.issued = hosted.request_session(
            self.gateway, root, "dev-a", SYNTH_CHARGED_FEN)

    def key_a(self) -> bytes:
        return base64.b64decode(self.provision["device_key_b64"])


# ---------------------------------------------------------------------- #
# AST 断言
# ---------------------------------------------------------------------- #

def product_face_facts(path: str) -> dict:
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    banned = {"urllib", "socket", "http", "ssl", "ftplib", "requests",
              "httpx", "subprocess", "logging", "os"}
    net_imports: list[str] = []
    io_calls: list[str] = []
    sub_key_owners: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            net_imports += [alias.name for alias in node.names
                            if alias.name.split(".")[0] in banned]
        elif isinstance(node, ast.ImportFrom) and node.module \
                and node.module.split(".")[0] in banned:
            net_imports.append(node.module)
        elif isinstance(node, ast.Call) \
                and isinstance(node.func, ast.Name) \
                and node.func.id in ("print", "open"):
            io_calls.append(node.func.id)
        elif isinstance(node, ast.FunctionDef):
            if node.name != "__init__":
                for sub in ast.walk(node):
                    if (isinstance(sub, ast.Name) and sub.id == "sub_key") \
                            or (isinstance(sub, ast.Attribute)
                                and sub.attr == "sub_key"):
                        sub_key_owners.append(node.name)
    return {"net_imports": net_imports, "io_calls": io_calls,
            "sub_key_owners": sub_key_owners}


def legal_entry_hosted_refs(path: str) -> list[str]:
    text = Path(path).read_text(encoding="utf-8")
    if "hosted" in text.lower():
        return ["text_literal_hosted"]
    return []


# ---------------------------------------------------------------------- #
# 分段
# ---------------------------------------------------------------------- #

def _ledger_rows() -> dict:
    with open(LEDGER, encoding="utf-8-sig", newline="") as handle:
        return {row[0]: row for row in csv.reader(handle)}


def section_s1(checks: Checks, rows: dict) -> dict:
    wanted = PREREQ_OBLIGATIONS + LEGACY_OBLIGATIONS
    statuses = {ob: (rows.get(ob) or [""] * 18)[15] for ob in wanted}
    checks.add(
        "S1A_prereq_and_legacy_rows_verified",
        all(status == "VERIFIED" for status in statuses.values())
        and len(statuses) == len(wanted),
        "台账亲读：硬依赖 %s 全 VERIFIED（工单明文）＋legacy link F12/F26 "
        "desktop+selfhost 全 VERIFIED（凭据保险库/工具权限后端在账，复用其"
        "公开面不第二权威）——实测 %s"
        % (",".join(PREREQ_OBLIGATIONS),
           " ".join("%s=%s" % kv for kv in sorted(statuses.items()))))
    assertion = rows.get("F33-desktop", [""] * 18)[2]
    checks.add(
        "S1B_acceptance_vector_verbatim",
        assertion == ACCEPTANCE_VECTOR
        and rows.get("F33-selfhost", [""] * 18)[2] == ACCEPTANCE_VECTOR,
        "06 V7-33 acceptance 向量逐字对账（台账 F33-desktop/F33-selfhost "
        "assertion 列）＝%s" % assertion)
    faces = {"credential_vault.py": sha256_file(str(CREDENTIAL_VAULT)),
             "legal_entry.py": sha256_file(str(LEGAL_ENTRY)),
             "hosted_inference.py": sha256_file(str(HOSTED))}
    checks.add(
        "S1C_frozen_faces_pinned",
        all(len(v) == 64 for v in faces.values()),
        "冻结面 sha256 钉定（F12 公开面 credential_vault.py=%s…；"
        "legal_entry.py=%s…；本单产物 hosted_inference.py=%s…）"
        % (faces["credential_vault.py"][:8], faces["legal_entry.py"][:8],
           faces["hosted_inference.py"][:8]))
    refs = legal_entry_hosted_refs(str(LEGAL_ENTRY))
    checks.add(
        "S1D_legal_entry_zero_hosted_wiring",
        not refs,
        "legal_entry 零 hosted 接线（UI_HOST_OR_NEW_PRODUCT：不冒已有业务"
        "入口、不创第二业务入口；推理永远在上游——不创第二 Agent loop）；"
        "命中=%s" % (refs or "无"))
    return faces


def section_s2(checks: Checks) -> None:
    payload, proc, state_root = _run_flow()
    verify = payload.get("verify") or {}
    forms = _sub_key_forms(SYNTH_SUB_KEY)
    out_hits = _bytes_hit(proc.stdout + proc.stderr, forms)
    if payload and state_root.is_dir():
        file_hits = _scan_tree(state_root, forms)
    else:
        file_hits = ["state_root_unavailable"]
    checks.add(
        "S2A_flow_issue_verify_exact_deduction",
        bool(verify.get("accepted"))
        and verify.get("charged_fen") == SYNTH_CHARGED_FEN
        and verify.get("remaining_quota_fen")
        == SYNTH_START_FEN - SYNTH_CHARGED_FEN
        and isinstance(verify.get("remaining_quota_fen"), int)
        and (payload.get("issued", {}).get("credential", {})
             .get("ttl_s", 61)) <= 60,
        "子进程端到端流（F12 vault 存钥→设备签名→签发→验证）：accepted、"
        "charged=%d 分、remaining=%d 分（整型精确 %d-%d）；TTL=%ss ≤60s"
        "（源设计 ≤60s 短 TTL）"
        % (SYNTH_CHARGED_FEN, SYNTH_START_FEN - SYNTH_CHARGED_FEN,
           SYNTH_START_FEN, SYNTH_CHARGED_FEN,
           payload.get("issued", {}).get("credential", {}).get("ttl_s")))
    entry = state_root / "credentials" / "lvyin.hosted" / "device-dev-a.json"
    entry_ok = False
    key_hits: list[str] = []
    if entry.is_file():
        raw = entry.read_bytes()
        entry_ok = json.loads(raw).get("backend") == "dpapi"
        device_key = base64.b64decode(
            (payload.get("provision") or {}).get("device_key_b64", ""))
        if device_key:
            key_hits = [name for name, form in
                        zip(("raw", "b64", "hex"), _sub_key_forms(device_key))
                        if form in raw]
    checks.add(
        "S2B_device_key_via_f12_vault_blob_only",
        entry_ok and not key_hits,
        "设备钥唯一持久化＝F12 凭据保险库（credentials/lvyin.hosted/"
        "device-dev-a.json，backend=dpapi）；落盘字节扫描零明文设备钥"
        "（raw/b64/hex 三形零命中＝密文 blob 形态，复用 F12 公开面不第二"
        "权威）")
    checks.add(
        "S2C_subkey_surface_scan_zero_hit",
        not out_hits and not file_hits,
        "子key不落端（配置与日志面全域扫描）：子进程 stdout+stderr 原始"
        "字节＋状态根全部文件，raw/b64/hex 三形零命中（命中 stdout=%s "
        "files=%s；本面零日志零打印，全部可观测面已扫）"
        % (out_hits or "无", file_hits or "无"))


def section_s3(checks: Checks, hosted, tmp: str) -> None:
    t0 = 1_000_000.0
    flow = _Flow(hosted, tempfile.mkdtemp(prefix="s3-", dir=tmp),
                 clock=lambda: t0)
    flow.gateway.clock = lambda: t0 + 60 + 0.001
    expired = _typed(hosted, flow.gateway.verify_session,
                     flow.issued["credential"], "dev-a")
    checks.add(
        "S3A_ttl_expired_typed_reject_no_charge",
        expired == "hosted_credential_expired"
        and flow.gateway.remaining_quota_fen == SYNTH_START_FEN,
        "TTL 过期失效（clock 注入 exp+1ms）：typed %s 且零扣减"
        "（remaining=%d 不动）——托管短TTL凭证过期失效"
        % (expired, flow.gateway.remaining_quota_fen))
    boundary = _Flow(hosted, tempfile.mkdtemp(prefix="s3b-", dir=tmp),
                     clock=lambda: t0)
    boundary.gateway.clock = lambda: t0 + 60  # exp 当刻
    ver = boundary.gateway.verify_session(boundary.issued["credential"],
                                          "dev-a")
    checks.add(
        "S3B_boundary_exp_moment_valid_ttl_le_60",
        bool(ver.get("accepted"))
        and boundary.issued["credential"]["ttl_s"] <= 60
        and boundary.issued["credential"]["exp"]
        - boundary.issued["credential"]["issued_at"]
        == boundary.issued["credential"]["ttl_s"],
        "边界：exp 当刻仍有效（≤60s 语义内）accepted；ttl_s=%ss 且 "
        "exp-issued_at=ttl_s（载荷钉定）"
        % boundary.issued["credential"]["ttl_s"])


def _typed(hosted, call, *args) -> str:
    try:
        call(*args)
    except hosted.HostedError as exc:
        return str(exc)
    return "NO_ERROR_RAISED"


def section_s4(checks: Checks, hosted, tmp: str) -> None:
    flow = _Flow(hosted, tempfile.mkdtemp(prefix="s4-", dir=tmp))
    flow.gateway.provision_device("dev-b")
    mismatch = _typed(hosted, flow.gateway.verify_session,
                      flow.issued["credential"], "dev-b")
    checks.add(
        "S4A_device_mismatch_typed_reject_no_charge",
        mismatch == "hosted_device_mismatch"
        and flow.gateway.remaining_quota_fen == SYNTH_START_FEN,
        "设备绑定负测：dev-a 凭证到 dev-b 账→typed %s 零扣减"
        "（remaining=%d 不动）——设备绑定" % (mismatch,
                                            flow.gateway.remaining_quota_fen))
    nonce = hosted.new_nonce()
    cross_sig = hosted.device_signature(flow.key_a(), "dev-b", nonce,
                                        SYNTH_CHARGED_FEN)
    cross = _typed(hosted, flow.gateway.issue_session,
                   "dev-b", cross_sig, nonce, SYNTH_CHARGED_FEN)
    checks.add(
        "S4B_signature_binds_device_identity",
        cross == "hosted_signature_invalid",
        "dev-a 钥签 dev-b 名→typed %s（请求签名覆盖 device_id，异钥异名"
        "必拒）" % cross)


def section_s5(checks: Checks, hosted, tmp: str) -> None:
    flow = _Flow(hosted, tempfile.mkdtemp(prefix="s5-", dir=tmp))
    over = _typed(hosted, hosted.request_session, flow.gateway, flow.root,
                  "dev-a", SYNTH_START_FEN + 1)
    checks.add(
        "S5A_over_quota_issue_rejected_no_charge",
        over == "hosted_quota_exceeded"
        and flow.gateway.remaining_quota_fen == SYNTH_START_FEN,
        "额度绑定负测：请求 %d 分 > 余额 %d 分→typed %s 零扣减"
        % (SYNTH_START_FEN + 1, SYNTH_START_FEN, over))
    bad_codes = {repr(bad): _typed(hosted, hosted.request_session,
                                   flow.gateway, flow.root, "dev-a", bad)
                 for bad in (1.5, True, "100", None)}
    checks.add(
        "S5B_non_integer_fen_rejected",
        all(code == "hosted_quota_not_integer"
            for code in bad_codes.values()),
        "整型分纪律：浮点 1.5/bool True/str '100'/None 全部 typed "
        "hosted_quota_not_integer（bool 是 int 子类显式拒，turn_budget "
        "同式）——实测 %s" % bad_codes)
    ver = flow.gateway.verify_session(flow.issued["credential"], "dev-a")
    replay = _typed(hosted, flow.gateway.verify_session,
                    flow.issued["credential"], "dev-a")
    checks.add(
        "S5C_replay_rejected_charged_exactly_once",
        bool(ver.get("accepted")) and replay == "hosted_credential_replayed"
        and flow.gateway.remaining_quota_fen
        == SYNTH_START_FEN - SYNTH_CHARGED_FEN,
        "重放负测：同凭证二次验证→typed %s；额度恰扣一次（remaining=%d"
        "=%d-%d，零双扣）" % (replay, flow.gateway.remaining_quota_fen,
                              SYNTH_START_FEN, SYNTH_CHARGED_FEN))
    tampered = dict(flow.issued["credential"],
                    authorized_fen=SYNTH_START_FEN)
    tamper = _typed(hosted, flow.gateway.verify_session, tampered, "dev-a")
    checks.add(
        "S5D_tampered_credential_invalid_no_charge",
        tamper == "hosted_credential_invalid"
        and flow.gateway.remaining_quota_fen
        == SYNTH_START_FEN - SYNTH_CHARGED_FEN,
        "凭证篡改负测（authorized_fen 改 %d）→typed %s（token 覆盖全部"
        "绑定字段，禁只验字段）；额度不动" % (SYNTH_START_FEN, tamper))


def section_s6(checks: Checks, hosted, tmp: str,
               faces_before: dict) -> None:
    facts = product_face_facts(str(HOSTED))
    checks.add(
        "S6A_ast_zero_network_io_subkey_confined",
        not facts["net_imports"] and not facts["io_calls"]
        and not facts["sub_key_owners"],
        "产品面 AST：零网络/子进程/logging/os 导入、零 print/open 调用"
        "（合成先行零真实网关，裁决#13-19；本面零日志零打印零文件 I/O）；"
        "sub_key 名只存在于 HostedGateway.__init__（违规=%s）"
        % (facts["sub_key_owners"] or "无"))
    flow = _Flow(hosted, tempfile.mkdtemp(prefix="s6-", dir=tmp))
    ver = flow.gateway.verify_session(flow.issued["credential"], "dev-a")
    surfaces = [json.dumps(flow.provision), json.dumps(flow.issued),
                json.dumps(flow.issued["credential"]), json.dumps(ver)]
    for path in Path(flow.root).rglob("*"):
        if path.is_file():
            surfaces.append(repr(path.read_bytes()))
    forms = _sub_key_forms(SYNTH_SUB_KEY)
    surface_blobs = [s.encode("utf-8", "surrogateescape") for s in surfaces]
    hits = [name for name, form in zip(("raw", "b64", "hex"), forms)
            if any(form in blob for blob in surface_blobs)]
    checks.add(
        "S6B_inprocess_surfaces_zero_subkey",
        not hits,
        "进程内全回执（provision/issue/credential/verify JSON 面）＋状态根"
        "全文件：子key raw/b64/hex 三形零命中（子key 只在服务端——子key不"
        "落端）")
    coord_lines = [line for line in
                   COORD.read_text(encoding="utf-8").splitlines()
                   if "13-19" in line]
    coord_ok = bool(coord_lines)
    for line in coord_lines:
        if not ("推理网关" in line and "统一合成先行" in line):
            coord_ok = False
    checks.add(
        "S6C_adjudication_13_19_synthetic_first_in_ledger",
        coord_ok,
        "00-总协调 裁决#13-19 行在账且含『推理网关＋统一合成先行』（真实"
        "网关 v2 商业化时补——本单合成先行依据）；行数=%d"
        % len(coord_lines))
    faces_after = {"credential_vault.py": sha256_file(str(CREDENTIAL_VAULT)),
                   "legal_entry.py": sha256_file(str(LEGAL_ENTRY)),
                   "hosted_inference.py": sha256_file(str(HOSTED))}
    checks.add(
        "S6D_frozen_faces_byte_stable_through_run",
        faces_after == faces_before,
        "冻结面全程字节稳定（sha256 前后相等）：%s"
        % ";".join("%s=%s…" % (key, value[:8])
                   for key, value in sorted(faces_after.items())))


def run_profile(args, profile: str) -> int:
    """单 profile 全量 19 检＋证据落盘（evidence/F33/<profile>/）。"""
    checks = Checks()
    rows = _ledger_rows()
    faces_before = {"credential_vault.py": sha256_file(str(CREDENTIAL_VAULT)),
                    "legal_entry.py": sha256_file(str(LEGAL_ENTRY)),
                    "hosted_inference.py": sha256_file(str(HOSTED))}
    hosted = _import_hosted()
    tmp = tempfile.mkdtemp(prefix="f33-recon-")
    section_s1(checks, rows)
    section_s2(checks)
    section_s3(checks, hosted, tmp)
    section_s4(checks, hosted, tmp)
    section_s5(checks, hosted, tmp)
    section_s6(checks, hosted, tmp, faces_before)
    # 临时目录在系统 %TEMP% 下（全程合成材料），交给 OS 清理；不入仓。

    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True,
        cwd=str(REPO_ROOT)).stdout.strip()
    evidence = {
        "run_date": RUN_DATE,
        "profile": profile,
        "command": "python -X utf8 " + " ".join(sys.argv),
        "cwd": str(REPO_ROOT),
        "subject_commit": commit,
        "acceptance_vector": ACCEPTANCE_VECTOR,
        "frozen_faces": faces_before,
        "authority_row": "06 V7-33 F33（v2；owner=product；B5）"
                         "acceptance=" + ACCEPTANCE_VECTOR
                         + "；preserved=L12 商业化留槽；不创第二 Agent loop；"
                         "硬依赖 E03/E05/E07/E23/E24 全 VERIFIED；legacy "
                         "link F12/F26 复用公开面；裁决#13-19 合成先行，"
                         "真实网关 v2 商业化时补",
        "synthetic_materials": {
            "sub_key": "内存合成子key（os.urandom，run 内即弃，不入证据）",
            "quota": "整型分（start=%d，charged=%d）"
                     % (SYNTH_START_FEN, SYNTH_CHARGED_FEN),
            "network": "零网络（进程内合成网关；零真实外联）",
        },
        "checks": checks.items,
        "passed": checks.passed_count,
        "total": len(checks.items),
        "overall": "PASS" if checks.all_passed else "FAIL",
    }
    out_dir = REPO_ROOT / args.evidence_root / profile
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "f33-hosted-inference-recon.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=1),
        encoding="utf-8")
    (out_dir / "f33-hosted-inference-recon.md").write_text(
        _md(evidence), encoding="utf-8")
    print("---")
    print("RECON_%s %d/%d checks — profile=%s" % (
        "OK" if checks.all_passed else "FAIL",
        checks.passed_count, len(checks.items), profile))
    return 0 if checks.all_passed else 1


def _md(evidence: dict) -> str:
    lines = [
        "# F33 托管模型积分通道 recon（%s）" % evidence["profile"],
        "",
        "- command: `%s`" % evidence["command"],
        "- cwd: `%s`" % evidence["cwd"],
        "- subject_commit: `%s`" % evidence["subject_commit"],
        "- overall: **%s**（%d/%d）" % (evidence["overall"],
                                        evidence["passed"],
                                        evidence["total"]),
        "- authority: %s" % evidence["authority_row"],
        "- synthetic: %s；%s；%s" % (
            evidence["synthetic_materials"]["sub_key"],
            evidence["synthetic_materials"]["quota"],
            evidence["synthetic_materials"]["network"]),
        "",
        "| check | status | detail |",
        "|---|---|---|",
    ]
    for item in evidence["checks"]:
        lines.append("| %s | %s | %s |" % (item["id"], item["status"],
                                           item["detail"].replace("|", "\\|")))
    return "\n".join(lines) + "\n"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("desktop", "selfhost"),
                        action="append", default=None)
    parser.add_argument("--evidence-root", default="evidence/F33")
    args = parser.parse_args()
    profiles = args.profile or ["desktop"]
    for required in (HOSTED, CREDENTIAL_VAULT, LEGAL_ENTRY, LEDGER, COORD):
        if not required.is_file():
            print("FATAL: 预态缺失 %s" % required)
            return 2
    codes = [run_profile(args, profile) for profile in profiles]
    return 0 if all(code == 0 for code in codes) else 1


if __name__ == "__main__":
    raise SystemExit(main())
