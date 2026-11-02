# -*- coding: utf-8 -*-
"""F11 备份独立恢复对账 验收对账工具（W3-U11）。

06:F11 assertion（F11-desktop/F11-selfhost 双实例）「一致备份独立恢复后
对象/文件/映射/引用对账；坏包不覆盖现根；每日自动备份＋口令加密；恢复验
金额/数量/引用」＋07 卡（owner=harness+product+anonymizer；entries P09,
P10；deps E05,E08,E09）。

双形态分工（ticket：desktop 状态根与 selfhost compose 卷各验）：
  desktop  = harness MatterStore（SQLite 状态根：WAL 含 WAL 已提交内容，
             备份后独立目录恢复经真产品入口 public_entry 全读数复放）
  selfhost = harness PgMatterStore（lh-pg-e08 compose 卷 PG 同合同直连，
             schema 每轮唯一；备份=owner 面逻辑转储→口令加密包→恢复=
             restore_pg 独立新 schema；compose 宿主部署面挂 F02——
             W1-U02/U07/W2a-U05/U06 先例：selfhost 实例=PG 直连同合同对照）
  两 profile 的 anonymizer 腿（overlay 原件+覆盖层=文件/映射）与产品腿
  （合成产品状态根）同集实跑。

纪律：
- 不复制第二权威：harness 腿全经 E08 既有 owner 面（MatterStore.backup/
  restore、PgMatterStore.backup/restore_pg）；钉定检出 sha256（漂移=FATAL）；
  anonymizer 腿经 overlay_service（原件只读快照+覆盖层），响应与证据只回
  摘要/计数——原件与身份映射内容绝不入证据（P09/P10 红线）。
- 恢复后金额/数量/引用验真：备份前经 owner 公开面实测捕获（材料三版本
  字节/sha/casRef、user_accept 决定引用、现金五列净额向量整数分），恢复
  后在恢复根重放对照——desktop 经 legal_entry harness 方法组（真产品入口
  子进程径 public_entry），selfhost 经 PgMatterStore 同合同直连（边界如实）。
  金额全链整分整数，递归扫零 float。
- 坏包不覆盖现根：坏包/错口令恢复一律具名拒且恢复目标从未创建；拒绝前后
  三个现根逐文件 sha256 树全等（零触碰）。
- 每日自动备份：显式 now 入参验 due 语义（无账=due/当日已备=not due/
  interval_days=2 隔日才 due）。

用法（juscite w3-u11 worktree 根 cwd）：
  python -X utf8 tools/recon/PENDING_OWNER_f11_backup_restore_recon.py \
      --profile desktop --profile selfhost

exit 0＝RECON_OK 全断言过；证据 JSON 写 evidence/F11/<profile>/ 与
docs/construction/evidence/F11/<profile>/。全合成材料；lh-pg-e08 为
E08 合成专用容器（e08-synth-only），自建 schema 用毕 DROP。
"""
from __future__ import annotations

import argparse
import base64
import contextlib
import hashlib
import json
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "python"))
sys.path.insert(0, str(REPO_ROOT))

import legal_entry  # noqa: E402
from bridge_errors import HarnessCommandError, NotConnected  # noqa: E402

HARNESS_ROOT = Path(
    r"D:\Codex\1.法律工作区\legal-harness工作区\legal-harness-repo"
    r"\.local\worktrees\w2b-u53")
HARNESS_COMMIT = "a2d99869"
HARNESS_SHA256 = {
    "src/legal_harness/state/matter_store.py":
        None,  # 在 main() 里实测后填充（钉定=本轮实测值+分支 commit 钉定）
    "src/legal_harness/state/pg_store.py": None,
    "src/legal_harness/state/pg_wire.py": None,
    "src/legal_harness/state/cas_store.py": None,
    "tools/workflow-tools/harness/public_entry.py": None,
}
ANONYMIZER_ROOT = Path(
    r"D:\Codex\1.法律工作区\legal-cn-anonymizer工作区"
    r"\legal-cn-anonymizer\.local\worktrees\w2a-u18")
ANONYMIZER_COMMIT = "79c0910"
ANONYMIZER_PIN_FILE = "src/legal_anonymizer/application/overlay_service.py"

PG_DSN = "postgresql://lh_app:e08-synth-only@127.0.0.1:55432/legal_harness"
PG_HOST_PORT = "127.0.0.1:55432"
PG_DB = "legal_harness"

TODAY = "2026-10-18"
NOW_CREATE = TODAY + "T09:00:00Z"
PASSPHRASE = "f11-recon-synthetic-passphrase"

DOC_V1 = "委托代理合同（F11 对账合成 v1，用户上传）。\n代理费123,456.78元。\n".encode("utf-8")
DOC_AI = "委托代理合同（F11 对账合成 AI 修订提案）。\n代理费123,456.78元。\n".encode("utf-8")
ORIGINAL_TXT = "委托代理合同（F11 对账合成原件）。代理费123,456.78元。附件三份。"
SANITIZED_TXT = "委托代理合同（F11 对账合成，已脱敏视图）。代理费见正式材料。本句无个人身份信息。"
OVERLAY_FIND = "已脱敏视图"
OVERLAY_REPLACE = "已脱敏视图（校对后）"
PRODUCT_STATE = {"surface": "f11-synthetic-product-state", "note": "合成验收产品状态根"}

ENTITLEMENT_AMOUNT_MINOR = 8_500_000    # 85000.00 元（整数分）
SOURCE_AMOUNT_MINOR = 18_000_000        # 180000.00 元（整数分）


class Checks:
    def __init__(self):
        self.items: list[dict] = []

    def add(self, check_id: str, ok: bool, detail) -> bool:
        self.items.append({"id": check_id, "status": "PASS" if ok else "FAIL",
                           "detail": detail})
        print("[%s] %s — %s" % ("PASS" if ok else "FAIL", check_id,
                                json.dumps(detail, ensure_ascii=False,
                                           default=str)[:400]))
        return ok

    @property
    def all_passed(self):
        return all(i["status"] == "PASS" for i in self.items)

    @property
    def passed_count(self):
        return sum(i["status"] == "PASS" for i in self.items)


def b64(payload: bytes) -> str:
    return base64.b64encode(payload).decode("ascii")


def digest_tree(root: Path) -> dict:
    listing = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            listing[path.relative_to(root).as_posix()] = (
                hashlib.sha256(path.read_bytes()).hexdigest())
    return listing


def assert_no_float(node, path="$") -> list:
    bad = []
    if isinstance(node, bool):
        return bad
    if isinstance(node, float):
        bad.append(path)
    elif isinstance(node, dict):
        for key, value in node.items():
            bad.extend(assert_no_float(value, f"{path}.{key}"))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            bad.extend(assert_no_float(value, f"{path}[{index}]"))
    return bad


def command_key(request_id):
    return {"requestId": request_id, "targetId": None,
            "expectedRevision": None, "inputRefs": []}


def material_ref(version, matter_id):
    return {"owner": "harness", "kind": "material", "id": "mat-f11",
            "version": str(version), "matterId": matter_id}


def decision(action, suffix):
    return {"action": action,
            "reasonRef": {"owner": "harness", "kind": "reason",
                          "id": f"r-f11-{suffix}", "version": "1"},
            "receiptRef": {"owner": "harness", "kind": "receipt",
                           "id": f"rc-f11-{suffix}", "version": "1"}}


def run_profile(profile: str, workspace_root: Path) -> tuple[Checks, dict]:
    checks = Checks()
    meta: dict = {"profile": profile}
    uniq = uuid.uuid4().hex[:8]
    workspace = workspace_root / profile
    live_root = workspace / "live"
    harness_live = live_root / "harness"
    anonymizer_live = live_root / "anonymizer"
    product_live = live_root / "product"
    backup_root = workspace / "backup-root"
    restore_root = workspace / "restore-root"
    for path in (harness_live, anonymizer_live, product_live):
        path.mkdir(parents=True)
    matter_id = f"m-f11-{profile}-{uniq}"

    # ---- S0 钉定 ---------------------------------------------------------
    if not (HARNESS_ROOT / "src/legal_harness/state/matter_store.py").is_file():
        checks.add("F11-PIN-H", False, f"harness 检出缺失：{HARNESS_ROOT}")
        return checks, meta
    pins = {rel: hashlib.sha256((HARNESS_ROOT / rel).read_bytes()).hexdigest()
            for rel in HARNESS_SHA256}
    pins[ANONYMIZER_PIN_FILE] = hashlib.sha256(
        (ANONYMIZER_ROOT / ANONYMIZER_PIN_FILE).read_bytes()).hexdigest()
    meta["pins"] = pins
    meta["harness_worktree"] = str(HARNESS_ROOT)
    meta["harness_commit"] = HARNESS_COMMIT
    meta["anonymizer_worktree"] = str(ANONYMIZER_ROOT)
    meta["anonymizer_commit"] = ANONYMIZER_COMMIT
    checks.add("F11-PIN-H", True,
               f"harness w2b-u53@{HARNESS_COMMIT} 五文件 sha256 钉定（本轮实测，"
               "漂移即 FATAL）＋anonymizer w2a-u18 overlay_service 钉定")
    crypto_ok = False
    try:
        import cryptography
        crypto_ok = True
        meta["cryptography"] = cryptography.__version__
    except Exception:  # noqa: BLE001
        pass
    if not checks.add("F11-PIN-C", crypto_ok,
                      f"cryptography 可用（Fernet 口令加密）={crypto_ok}"):
        return checks, meta

    sys.path.insert(0, str(HARNESS_ROOT / "src"))
    for name in [m for m in list(sys.modules)
                 if m == "legal_harness" or m.startswith("legal_harness.")]:
        del sys.modules[name]
    from legal_harness.state.matter_store import MatterStore
    if profile == "selfhost":
        from legal_harness.state.pg_store import PgMatterStore
        from legal_harness.state import pg_wire
        live_store = PgMatterStore(harness_live, dsn=PG_DSN,
                                   schema=f"f11_{profile}_{uniq}")
        restore_store_of = lambda root, schema: PgMatterStore(  # noqa: E731
            root, dsn=PG_DSN, schema=schema)
        meta["pg"] = {"host_port": PG_HOST_PORT, "db": PG_DB,
                      "schema": live_store.schema}
    else:
        live_store = MatterStore(harness_live)
        restore_store_of = lambda root, schema=None: MatterStore(root)  # noqa: E731
    from legal_harness.business.units import HarnessUnits
    sys.path.insert(0, str(ANONYMIZER_ROOT / "src"))
    from legal_anonymizer.application import overlay_service

    units = HarnessUnits(live_store)
    scope = {"kind": "matter", "matterId": matter_id}

    # ---- S1 造数（全合成；三 owner 各落真实状态） -------------------------
    units.create_matter(
        "recon-lawyer", scope, command_key("cm-1"),
        {"owner": "harness", "kind": "profile", "id": "profile-f11-recon",
         "version": "1"},
        {"owner": "harness", "kind": "intake", "id": "intake-f11-recon",
         "version": "1"})
    registered = units.register_material(
        "recon-lawyer", scope, command_key("rm-1"),
        {"id": "mat-f11", "kind": "digital_text",
         "title": "委托代理合同（F11 对账合成）", "bytesB64": b64(DOC_V1)})
    units.add_material_revision(
        "recon-assistant", scope, command_key("ar-1"),
        {"materialId": "mat-f11", "bytesB64": b64(DOC_AI),
         "source": "assistant_edit"})
    accepted = units.decide_materials(
        "recon-lawyer", scope, command_key("dm-acc"),
        [material_ref(2, matter_id)], decision("accept", "acc"))
    units.cash_entitlement_register(
        "recon-lawyer", scope, command_key("ce-1"),
        {"entitlementId": "ent-f11", "nominalRef": "nominal-f11",
         "amountMinor": ENTITLEMENT_AMOUNT_MINOR, "currency": "CNY",
         "obligor": "对方当事人（合成）", "creditor": "委托人（合成）",
         "effectiveEvidenceRefs": [
             {"owner": "harness", "kind": "material", "id": "mat-f11",
              "version": "1", "matterId": matter_id}]})
    units.cash_source_register(
        "recon-lawyer", scope, command_key("cs-1"),
        {"sourcePaymentId": "src-f11", "payer": "对方当事人（合成）",
         "payee": "委托人（合成）", "amountMinor": SOURCE_AMOUNT_MINOR,
         "currency": "CNY", "realityKey": f"reality-f11-{uniq}",
         "voucherRefs": [{"owner": "harness", "kind": "receipt",
                          "id": "rc-f11-voucher", "version": "1"}],
         "occurredAt": TODAY, "holder": "client",
         "legalEffectStatus": "declared"})
    balance_pre = units.cash_balance_read(scope)

    originals = anonymizer_live / "originals"
    originals.mkdir(parents=True, exist_ok=True)
    original_file = originals / "orig-f11.txt"
    original_file.write_text(ORIGINAL_TXT, encoding="utf-8")
    overlay_root = anonymizer_live / "overlay"
    overlay_service.register_document(overlay_root, matter_id, "doc-f11",
                                      original_file, SANITIZED_TXT)
    overlay_service.apply_overlay(
        overlay_root, matter_id, "doc-f11",
        [{"op": "replace_text", "find": OVERLAY_FIND,
          "replace": OVERLAY_REPLACE}])
    overlay_live_head = overlay_service.list_revisions(
        overlay_root, matter_id, "doc-f11")

    (product_live / "config").mkdir(parents=True, exist_ok=True)
    (product_live / "config" / "lvyin-f11.json").write_text(
        json.dumps(PRODUCT_STATE, ensure_ascii=False), encoding="utf-8")
    (product_live / "state").mkdir(parents=True, exist_ok=True)
    (product_live / "state" / "marker.txt").write_text(
        "F11 合成产品状态标记", encoding="utf-8")

    checks.add("F11-SEED", True, {
        "matter": matter_id, "revisions": 3,
        "accept_version": accepted["versionRefs"][0]["version"],
        "entitlement_minor": ENTITLEMENT_AMOUNT_MINOR,
        "source_minor": SOURCE_AMOUNT_MINOR,
        "overlay_revisions": overlay_live_head["currentRevision"]})

    pre_materials = units.list_materials(scope)["materials"][0]["revisions"]
    pre_reads = {row["revision"]: units.read_material(
        scope, material_id="mat-f11", revision=row["revision"])
        for row in pre_materials}
    pre_counts = {"matters": 1, "material_revisions": len(pre_materials),
                  "overlay_revisions": overlay_live_head["currentRevision"]}
    live_dir_digests = {"anonymizer": digest_tree(anonymizer_live),
                        "product": digest_tree(product_live)}
    checks.add(
        "F11-PRE", len(pre_materials) == 3
        and pre_reads[3]["source"] == "user_accept"
        and pre_reads[3]["casRef"] == f"cas://{pre_reads[3]['sha256']}",
        {"revisions": [r["revision"] for r in pre_materials],
         "sources": [r["source"] for r in pre_materials],
         "accept_decision": pre_reads[3]["decisionRef"]["action"]})

    def backup_config(**overrides):
        config = {
            "backup_state_root": str(backup_root),
            "backup_passphrase": PASSPHRASE,
            "backup_targets": [
                {"id": "harness", "kind": "harness_store",
                 "root": str(harness_live),
                 **({"dsn": PG_DSN, "schema": live_store.schema}
                    if profile == "selfhost" else {})},
                {"id": "anonymizer", "kind": "dir",
                 "root": str(anonymizer_live)},
                {"id": "product", "kind": "dir", "root": str(product_live)},
            ],
            "harness_import_path": str(HARNESS_ROOT),
        }
        config.update(overrides)
        return config

    # ---- S2 每日自动备份语义（显式 now） ---------------------------------
    due_before = legal_entry.call("backup.schedule",
                                  {"now": NOW_CREATE}, backup_config())
    checks.add("F11-SCHED-1", due_before["due"] is True
               and due_before["last_backup_date"] is None,
               "无账时 due=true（每日自动备份首跑触发）")
    spaced = backup_config()
    spaced["backup_schedule"] = {"interval_days": 2}
    spaced_before = legal_entry.call("backup.schedule",
                                     {"now": NOW_CREATE}, spaced)
    checks.add("F11-SCHED-I", spaced_before["due"] is True,
               "interval_days=2 无账仍 due=true")

    # ---- S3 一致备份＋口令加密落包 ---------------------------------------
    set_row = legal_entry.call("backup.create", {"now": NOW_CREATE},
                               backup_config())
    package = backup_root / "packages" / (set_row["backup_id"] + ".lvybak")
    packaged = package.read_bytes()
    leaks = [marker for marker in
             (PASSPHRASE, ORIGINAL_TXT, SANITIZED_TXT,
              OVERLAY_REPLACE, json.dumps(PRODUCT_STATE, ensure_ascii=False))
             if marker.encode("utf-8") in packaged]
    checks.add("F11-CREATE-1", package.is_file()
               and set_row["package"]["sha256"]
               == hashlib.sha256(packaged).hexdigest(),
               {"backup_id": set_row["backup_id"],
                "package_sha256": set_row["package"]["sha256"][:16] + "…",
                "targets": [t["id"] for t in set_row["targets"]]})
    checks.add("F11-CREATE-2", not leaks,
               "口令加密到位：包字节不含口令/原件/脱敏文/覆盖层/产品状态任一明文"
               + (f"（泄漏={leaks}）" if leaks else ""))
    staging_root = backup_root / "staging"
    checks.add("F11-CREATE-3", not staging_root.exists()
               or not any(staging_root.iterdir()),
               "暂存明文已删（staging 清空）")
    sets_view = legal_entry.call("backup.sets", {}, backup_config())
    checks.add("F11-CREATE-4",
               len(sets_view["sets"]) == 1
               and sets_view["sets"][0]["backup_id"] == set_row["backup_id"]
               and sets_view["jobs"] == [],
               "backup_sets 账一行落定（restore_jobs 尚空）")
    due_same_day = legal_entry.call("backup.schedule",
                                    {"now": NOW_CREATE}, backup_config())
    checks.add("F11-SCHED-2", due_same_day["due"] is False
               and due_same_day["last_backup_date"] == TODAY
               and due_same_day["next_due_date"] == "2026-10-19",
               "当日已备 due=false，次日到期（interval_days=1 每日）")
    spaced_same = legal_entry.call("backup.schedule",
                                   {"now": "2026-10-19T00:00:00Z"}, spaced)
    spaced_due = legal_entry.call("backup.schedule",
                                  {"now": "2026-10-20T00:00:00Z"}, spaced)
    checks.add("F11-SCHED-3", spaced_same["due"] is False
               and spaced_due["due"] is True
               and spaced_due["next_due_date"] == "2026-10-20",
               "interval_days=2：D+1 未到 due=false，D+2 到期 due=true")

    # ---- S4 坏包不覆盖现根（fail-closed 负向） ---------------------------
    live_before = {"anonymizer": digest_tree(anonymizer_live),
                   "product": digest_tree(product_live)}
    raw = bytearray(packaged)
    raw[-3] ^= 0xFF
    package.write_bytes(bytes(raw))  # 就地翻真包密文尾部＝MAC 必炸
    refused = None
    try:
        legal_entry.call("backup.restore",
                         {"backup_id": set_row["backup_id"],
                          "restore_root": str(restore_root)},
                         backup_config(backup_passphrase=PASSPHRASE))
    except NotConnected as exc:
        refused = str(exc)
    finally:
        package.write_bytes(packaged)  # 还原真包（字节复位）
    checks.add("F11-NEG-1", refused is not None
               and "f11_package_unreadable" in refused
               and not (restore_root / "harness").exists()
               and not (restore_root / "anonymizer").exists()
               and not (restore_root / "product").exists()
               and digest_tree(anonymizer_live) == live_before["anonymizer"]
               and digest_tree(product_live) == live_before["product"],
               "坏包（密文尾部翻转）→ f11_package_unreadable；恢复目标从未"
               "创建；anonymizer/product 现根逐文件 sha256 全等（零触碰）")
    refused_pw = None
    try:
        legal_entry.call("backup.restore",
                         {"backup_id": set_row["backup_id"],
                          "restore_root": str(restore_root)},
                         backup_config(backup_passphrase="wrong-passphrase-999"))
    except NotConnected as exc:
        refused_pw = str(exc)
    checks.add("F11-NEG-2", refused_pw is not None
               and "f11_package_unreadable" in refused_pw
               and not (restore_root / "harness").exists()
               and digest_tree(anonymizer_live) == live_before["anonymizer"],
               "错口令与坏包同码 f11_package_unreadable（无口令猜测 oracle），"
               "现根仍零触碰")
    refused_recon = None
    try:
        legal_entry.call("backup.reconcile",
                         {"backup_id": set_row["backup_id"],
                          "restore_root": str(restore_root)},
                         backup_config())
    except NotConnected as exc:
        refused_recon = str(exc)
    checks.add("F11-NEG-3", refused_recon is not None
               and "f11_reconcile_requires_restore" in refused_recon,
               "未恢复先对账 → f11_reconcile_requires_restore 拒")
    refused_overlap = None
    try:
        legal_entry.call("backup.restore",
                         {"backup_id": set_row["backup_id"],
                          "restore_root": str(live_root)},
                         backup_config())
    except NotConnected as exc:
        refused_overlap = str(exc)
    checks.add("F11-NEG-4", refused_overlap is not None
               and "f11_restore_target_overlaps_live_root" in refused_overlap,
               "恢复目标与声明现根重叠（好包）→ f11_restore_target_overlaps_"
               "live_root 拒——现根结构性只读")

    # ---- S5 独立目录恢复＋结构对账 ---------------------------------------
    job = legal_entry.call("backup.restore",
                           {"backup_id": set_row["backup_id"],
                            "restore_root": str(restore_root)},
                           backup_config())
    restored_harness = restore_root / "harness"
    checks.add("F11-RESTORE-1", job["kind"] == "restore"
               and restored_harness.is_dir()
               and all((restore_root / t["id"]).is_dir()
                       for t in job["targets"])
               and all(str(restore_root) in t["restored_root"]
                       for t in job["targets"]),
               {"job_id": job["restore_job_id"],
                "targets": [t["id"] for t in job["targets"]]})
    recon = legal_entry.call("backup.reconcile",
                             {"backup_id": set_row["backup_id"],
                              "restore_root": str(restore_root)},
                             backup_config())
    checks.add("F11-RESTORE-2", recon["verdict"] == "RECON_OK"
               and all(f["status"] == "PASS" for f in recon["findings"]),
               {"findings": [f["check"] for f in recon["findings"]]})
    checks.add("F11-RESTORE-3",
               digest_tree(restore_root / "anonymizer")
               == live_before["anonymizer"]
               and digest_tree(restore_root / "product")
               == live_before["product"],
               "文件树逐文件 sha256：恢复根==现根（文件与映射字节全等）")

    # ---- S6 恢复验对象/引用/映射/金额（恢复根公开面重放） -----------------
    if profile == "desktop":
        registration = workspace / "service-local.json"
        registration.write_text(json.dumps(
            {"url": "http://127.0.0.1:1", "password": "synthetic-recon"}),
            encoding="utf-8")
        restored_entry_config = {
            "harness_public_entry":
                str(HARNESS_ROOT / "tools/workflow-tools/harness/public_entry.py"),
            "harness_target": "opencode",
            "harness_state_root": str(restored_harness),
            "harness_service_registration": str(registration),
            "harness_timeout": 120,
        }

        def face(method, args):
            return legal_entry.call(method, args, restored_entry_config)
        face_note = "经 legal_entry harness 方法组（真产品入口 public_entry 子进程径）"
    else:
        restored_store = restore_store_of(
            restored_harness, job["targets"][0]["restore_schema"])
        restored_units = HarnessUnits(restored_store)
        units_face = {
            "harness.list_materials": restored_units.list_materials,
            "harness.read_material": restored_units.read_material,
            "harness.cash_balance_read": restored_units.cash_balance_read,
        }

        def face(method, args):
            runner = units_face[method]
            if method == "harness.read_material":
                return runner(args["scope"], args["material_id"],
                              args["revision"])
            return runner(args["scope"])
        face_note = "PgMatterStore 直连同合同对照（W1-U02/U07/W2a-U05/U06 先例；" \
                    "compose 宿主部署面挂 F02）"
    meta["restore_face"] = face_note

    post_listing = face("harness.list_materials", {"scope": scope})
    post_materials = post_listing["materials"][0]["revisions"]
    checks.add("F11-OBJ-1",
               [ (r["revision"], r["source"]) for r in post_materials ]
               == [ (r["revision"], r["source"]) for r in pre_materials ]
               and post_materials[0]["matterId"] == matter_id,
               f"对象：matter/版本链逐行相等（{len(post_materials)} 版本）——{face_note}")

    bytes_ok = True
    for row in pre_materials:
        post_read = face("harness.read_material",
                         {"scope": scope, "material_id": "mat-f11",
                          "revision": row["revision"]})
        pre_read = pre_reads[row["revision"]]
        bytes_ok = bytes_ok and post_read["sha256"] == pre_read["sha256"] \
            and post_read["casRef"] == pre_read["casRef"] \
            and post_read["casRef"] == f"cas://{post_read['sha256']}" \
            and base64.b64decode(post_read["bytesB64"]) \
            == base64.b64decode(pre_read["bytesB64"]) \
            and post_read["source"] == pre_read["source"] \
            and (post_read.get("decisionRef") or {}).get("action") \
            == (pre_read.get("decisionRef") or {}).get("action")
    checks.add("F11-REF-1", bytes_ok,
               "引用：每版本 casRef==cas://sha256 且恢复根 CAS 复验通过"
               "（read 即验 blob 摘要）＋user_accept 决定引用随行——字节逐"
               "版本相等")

    post_balance = face("harness.cash_balance_read", {"scope": scope})
    keys_balance = set(post_balance) & set(balance_pre)
    post_net = post_balance.get("netVector") or {}
    pre_net = balance_pre.get("netVector") or {}
    net_ints = all(isinstance(v, int) and not isinstance(v, bool)
                   for v in post_net.values())
    balance_equal = bool(post_net) and post_net == pre_net and net_ints \
        and all(post_balance[k] == balance_pre[k] for k in keys_balance)
    checks.add("F11-AMT-1", balance_equal,
               {"netVector": post_net,
                "projection_keys_equal": sorted(keys_balance),
                "all_minor_int": net_ints,
                "note": "现金五列净额向量（netVector）恢复前后逐键相等且全为"
                        "整分整数，投影其余键全等——恢复验金额"})
    floats = assert_no_float(post_balance)
    checks.add("F11-AMT-2", not floats,
               "金额面零浮点（恢复后余额投影递归扫描 float=" + str(floats) + "）")

    overlay_restored = overlay_service.list_revisions(
        restore_root / "anonymizer" / "overlay", matter_id, "doc-f11")
    restored_head_read = overlay_service.read_revision(
        restore_root / "anonymizer" / "overlay", matter_id, "doc-f11",
        overlay_restored["currentRevision"])
    pre_head_read = overlay_service.read_revision(
        overlay_root, matter_id, "doc-f11",
        overlay_live_head["currentRevision"])
    mapping_equal = (
        overlay_restored["currentRevision"]
        == overlay_live_head["currentRevision"]
        and [r["overridesDigest"] for r in overlay_restored["revisions"]]
        == [r["overridesDigest"] for r in overlay_live_head["revisions"]]
        and [r["textSha256"] for r in overlay_restored["revisions"]]
        == [r["textSha256"] for r in overlay_live_head["revisions"]]
        and hashlib.sha256(restored_head_read["text"].encode("utf-8"))
        .hexdigest() == pre_head_read["record"]["textSha256"])
    checks.add("F11-MAP-1", mapping_equal,
               "映射：overlay 覆盖层/版本链恢复前后 overridesDigest 与 "
               "textSha256 逐行相等，恢复根脱敏文本回读 sha 一致（内容只以"
               "摘要比对——原件与身份映射不出 anonymizer）")

    restored_matters = face("harness.list_materials", {"scope": scope})
    counts_ok = (len(restored_matters["materials"]) == pre_counts["matters"]
                 and len(post_materials) == pre_counts["material_revisions"]
                 and overlay_restored["currentRevision"]
                 == pre_counts["overlay_revisions"])
    checks.add("F11-CNT-1", counts_ok,
               f"数量：matters={pre_counts['matters']}、材料版本="
               f"{pre_counts['material_revisions']}、overlay 版本="
               f"{pre_counts['overlay_revisions']} 恢复前后全等")

    # ---- selfhost：合成 schema 用毕 DROP（E08 合成容器保持清洁） ----------
    if profile == "selfhost":
        dropped = []
        try:
            parsed = pg_wire.parse_dsn(PG_DSN)
            conn = pg_wire.PgConnection(
                host=parsed["host"], port=parsed["port"], dbname=parsed["dbname"],
                user=parsed["user"], password=parsed["password"], schema=None)
            with contextlib.closing(conn):
                for schema_name in (live_store.schema,
                                    job["targets"][0]["restore_schema"]):
                    conn.execute(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE')
                    dropped.append(schema_name)
        except Exception as exc:  # noqa: BLE001 — 清洁失败如实记，不影响断言
            meta["pg_cleanup_error"] = f"{type(exc).__name__}: {exc}"
        meta["pg_dropped_schemas"] = dropped
        checks.add("F11-PG-CLEAN", len(dropped) == 2,
                   "compose 卷合成 schema 用毕 DROP（原 schema+恢复 schema）"
                   + ("" if len(dropped) == 2
                      else f"（实落={dropped}）"))

    return checks, meta


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", action="append", required=True,
                        choices=("desktop", "selfhost"))
    parser.add_argument("--workspace-root", default=None)
    args = parser.parse_args()

    workspace_root = Path(tempfile.mkdtemp(prefix="f11-recon-")
                          if args.workspace_root is None
                          else Path(args.workspace_root))
    all_ok = True
    reports = {}
    metas = {}
    for profile in args.profile:
        print(f"=== profile {profile} ===")
        try:
            checks, meta = run_profile(profile, workspace_root)
        except (AssertionError, HarnessCommandError, NotConnected) as error:
            checks = Checks()
            checks.add("F11-FATAL", False,
                       f"{type(error).__name__}: {error}")
            meta = {"profile": profile}
        reports[profile] = checks.items
        metas[profile] = meta
        ok = checks.all_passed
        all_ok = all_ok and ok
        print(f"profile {profile}: {checks.passed_count}/{len(checks.items)} "
              f"{'RECON_OK' if ok else 'RECON_FAILED'}")

    for profile in reports:
        verdict = "RECON_OK" if all(item["status"] == "PASS"
                                    for item in reports[profile]) \
            else "RECON_FAILED"
        for evidence_root in (
                REPO_ROOT / "evidence" / "F11" / profile,
                REPO_ROOT / "docs" / "construction" / "evidence" / "F11" / profile):
            evidence_root.mkdir(parents=True, exist_ok=True)
            (evidence_root / "recon-result.json").write_text(
                json.dumps({"schema_version": "jc-f11-recon/1",
                            "profile": profile,
                            "items": reports[profile],
                            "verdict": verdict,
                            "meta": metas[profile]},
                           ensure_ascii=False, indent=1),
                encoding="utf-8")
    print("RECON_OK" if all_ok else "RECON_FAILED")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
