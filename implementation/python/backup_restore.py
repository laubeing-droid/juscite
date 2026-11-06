"""F11 备份恢复（backup_sets+restore_jobs，每日自动+口令加密）——产品侧
备份编排公开面（W3-U11；06:F11 desktop/selfhost 双实例，B0-B3）。

义务 06:F11 断言：「一致备份独立恢复后对象/文件/映射/引用对账；坏包不
覆盖现根；每日自动备份＋口令加密；恢复验金额/数量/引用」。

纪律（结构性 fail-closed，逐条对应断言）：
- 不复制第二权威：各 owner 状态只经其 owner 公开面进出。harness 腿消费
  E08 既有 MatterStore.backup()/restore()（SQLite）与 PgMatterStore.
  backup()/restore_pg()（PG 同合同子类，e08-dual-backend-contract）——本面
  绝不自实现第二套存储快照/恢复逻辑；anonymizer 腿与产品腿为通用文件树
  目标（逐文件 sha256 清单），原件与身份映射字节只以密文进包，本面任何
  响应只回计数/摘要（sha256），绝不回原件/映射内容（material.* 同红线）。
- 一致备份：harness 腿的一致性由 owner 面保证（SQLite sqlite3 backup API
  快照含 WAL 已提交内容；PG 单连接逐表逻辑转储），备份前 owner 面先过
  integrity_check，不过=f11_source_integrity_failed 拒；包内每工件/每文件
  带 sha256，恢复前逐一复验。
- 坏包不覆盖现根：restore 先完整验包（magic/头/Fernet MAC/逐成员 sha256）
  全部通过后才落位；落位只进「独立目录」（restore_root/<target_id>，必须
  不存在；已存在非空=f11_restore_target_not_empty）；恢复目标与任一声明
  现根重叠=f11_restore_target_overlaps_live_root（好包也绝不写现根）；
  验包失败或落位失败删除全部暂存与本次已建目标，现根零触碰。
- 口令加密：包体=头（明文：schema/backup_id/created_at/KDF 参数）
  + Fernet 密文（内层 zip：manifest+全部工件/文件字节）。口令经
  PBKDF2-HMAC-SHA256（200_000 次，stdlib hashlib）派生 Fernet 密钥
  （cryptography.Fernet：AES-128-CBC+HMAC-SHA256，encrypt-then-MAC）。
  口令错误与包损坏同报 f11_package_unreadable（不提供口令猜测 oracle）；
  cryptography 缺席=f11_crypto_unavailable 拒绝——绝不静默降级明文包。
  加密后扫描包字节不含任一暂存明文文件原字节（命中=f11_plaintext_leak
  拒并删包），加密完成后暂存明文即删。
- 每日自动备份：backup.schedule 按 interval_days（默认 1）与最近成功
  backup_set 的日期计算 due（显式 now 入参=验收确定性；生产由宿主每日
  调用同一入口——宿主级接线属 E25 发行面消费本工具，不前造）。
- 恢复验金额/数量/引用：本面 reconcile 做结构对账（恢复根存在；文件树
  目标 live==manifest==restored 逐摘要；恢复库 owner 面 integrity_check），
  金额/对象/引用语义验真由验收对账工具（tools/PENDING_OWNER_f11_backup_
  restore_recon.py）经真产品入口在恢复根上重放公开面读数（材料字节/
  决定引用/现金五列净额向量整数分）对照备份前实测——金额只以整分整数
  比对，本面与桥全链零浮点。

账（backup_sets+restore_jobs，均在 backup_state_root 下 append-only
jsonl）：sets/backup-sets.jsonl 一行一次成功备份；jobs/restore-jobs.jsonl
一行一次恢复（kind=restore）或一次结构对账（kind=reconcile）。备份 id
缺省含时间戳+随机尾（备份工件非确定性断言面）；重放同 id 由文件系统
f11_backup_id_conflict 具名拒。

fail-closed：未配置状态根/口令/目标、未知目标 kind、create 时目标根不
存在、包格式/摘要/MAC 不符、恢复目标不空或与现根重叠、cryptography
缺席——一律 typed error（f11_* 错误码，str() 只有机码，绝不携材料/映射
内容）。包格式 lvyin-backup/1：magic LVTBAK1\\n + 单行 JSON 头 +
Fernet token。响应只回计数/摘要/路径，不回任何受保护文件内容。
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import sys
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path

SCHEMA = "juscite-f11-backup-restore/1"
PACKAGE_SCHEMA = "lvyin-backup/1"
PACKAGE_MAGIC = b"LVTBAK1\n"
PACKAGE_SUFFIX = ".lvybak"
KDF_ALG = "pbkdf2-hmac-sha256"
KDF_ITERATIONS = 200_000
CIPHER = "fernet/aes128-cbc+hmac-sha256"
TARGET_KINDS = ("harness_store", "dir")
SET_LEDGER = "sets/backup-sets.jsonl"
JOB_LEDGER = "jobs/restore-jobs.jsonl"
_STAGING = "staging"
_PACKAGES = "packages"

_DATE_FMT = "%Y-%m-%d"
_TS_FMT = "%Y-%m-%dT%H:%M:%SZ"
_ID_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._")


class BackupError(ValueError):
    """Typed F11 face failure; str() is a code, never material content."""

    error_code = "f11_invalid"


def _fail(code: str) -> BackupError:
    return BackupError(code)


# --------------------------------------------------------------------------
# 小工具
# --------------------------------------------------------------------------

def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _check_id(value, code: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 96 \
            or not set(value) <= _ID_CHARS:
        raise _fail(code)
    return value


def _parse_now(value) -> datetime:
    """显式时钟入参（验收确定性）；缺省=真实 UTC now。"""
    if value is None:
        return datetime.now(timezone.utc)
    if not isinstance(value, str):
        raise _fail("f11_now_invalid")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        raise _fail("f11_now_invalid") from None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _digest_tree(root: Path) -> dict:
    """相对路径→{sha256,size}（排序确定）。"""
    listing: dict = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            rel = path.relative_to(root).as_posix()
            listing[rel] = {"sha256": _sha256_file(path),
                            "size": path.stat().st_size}
    return listing


def _append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _read_jsonl(path: Path) -> list:
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _set_rows(state_root: Path, backup_id: str | None = None) -> list:
    rows = [r for r in _read_jsonl(state_root / SET_LEDGER)
            if r.get("kind") == "backup_set"]
    if backup_id is not None:
        rows = [r for r in rows if r.get("backup_id") == backup_id]
    return rows


def _resolve_root(raw) -> Path:
    if not isinstance(raw, str) or not raw:
        raise _fail("f11_root_invalid")
    return Path(raw)


def _path_covers(parent: Path, child: Path) -> bool:
    parent = Path(os.path.normcase(str(parent.resolve())))
    child = Path(os.path.normcase(str(child.resolve())))
    return child == parent or parent in child.parents


def _safe_rel_parts(rel: object) -> tuple[str, ...]:
    """包内成员路径：相对、无空段、无 . / ..、无盘符与分隔符混用。

    清单来自解密后的包，仍是不可信输入。`Path(root) / rel` 在 rel 为绝对
    路径或含 `..` 时会写到 root 之外，所以恢复落盘前必须先拒。
    """
    if not isinstance(rel, str) or not rel or len(rel) > 512:
        raise _fail("f11_member_path_invalid")
    if rel.startswith(("/", "\\")) or "\\" in rel or ":" in rel or "\x00" in rel:
        raise _fail("f11_member_path_invalid")
    parts = tuple(rel.split("/"))
    if any(part in ("", ".", "..") for part in parts):
        raise _fail("f11_member_path_invalid")
    if any(any(ord(ch) < 32 for ch in part) for part in parts):
        raise _fail("f11_member_path_invalid")
    return parts


def _contained_destination(root: Path, rel: str) -> Path:
    """把已校验的相对路径贴到 root 上，并再确认解析后仍在 root 内。"""
    dest = root.joinpath(*_safe_rel_parts(rel))
    if not _path_covers(root, dest):
        raise _fail("f11_member_path_invalid")
    return dest


# --------------------------------------------------------------------------
# owner 公开面导入（harness E08 既有 backup/restore；只消费不自实现）
# --------------------------------------------------------------------------

def _harness_faces(config: dict):
    import_path = config.get("harness_import_path")
    if not isinstance(import_path, str) or not import_path:
        raise _fail("f11_harness_import_path_not_configured")
    src = Path(import_path) / "src"
    if not (src / "legal_harness" / "state" / "matter_store.py").is_file():
        raise _fail("f11_harness_import_path_missing")
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    from legal_harness.state.matter_store import MatterStore  # noqa: E402
    from legal_harness.state.pg_store import PgMatterStore  # noqa: E402
    return MatterStore, PgMatterStore


def _open_store(target: dict, config: dict, *, root: Path | None = None,
                schema: str | None = None):
    """按目标声明打开 harness owner store（desktop=SQLite 状态根；
    selfhost=PG compose 卷同合同——dsn/schema 由目标声明携带）。"""
    MatterStore, PgMatterStore = _harness_faces(config)
    base = root if root is not None else _resolve_root(target["root"])
    dsn = target.get("dsn")
    if dsn:
        return PgMatterStore(base, dsn=str(dsn),
                             schema=str(schema or target.get("schema") or "public"))
    return MatterStore(base)


# --------------------------------------------------------------------------
# 口令加密（PBKDF2-HMAC-SHA256 → Fernet）
# --------------------------------------------------------------------------

def _require_crypto() -> None:
    try:
        import cryptography  # noqa: F401
        from cryptography.fernet import Fernet  # noqa: F401
    except Exception:  # noqa: BLE001 — 缺席/坏装一律具名拒不降级
        raise _fail("f11_crypto_unavailable") from None


def _fernet(passphrase: str, salt: bytes):
    from cryptography.fernet import Fernet
    if not isinstance(passphrase, str) or not passphrase:
        raise _fail("f11_passphrase_required")
    derived = hashlib.pbkdf2_hmac(
        "sha256", passphrase.encode("utf-8"), salt, KDF_ITERATIONS)
    return Fernet(base64.urlsafe_b64encode(derived))


# --------------------------------------------------------------------------
# 配置解析
# --------------------------------------------------------------------------

def _state_root(config: dict) -> Path:
    raw = config.get("backup_state_root")
    if not isinstance(raw, str) or not raw:
        raise _fail("f11_backup_state_root_not_configured")
    root = Path(raw)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _targets(config: dict, *, require_roots: bool) -> list:
    raw = config.get("backup_targets")
    if not isinstance(raw, list) or not raw:
        raise _fail("f11_backup_targets_not_configured")
    seen, targets = set(), []
    for item in raw:
        if not isinstance(item, dict):
            raise _fail("f11_target_invalid")
        target_id = _check_id(item.get("id"), "f11_target_id_invalid")
        kind = item.get("kind")
        if kind not in TARGET_KINDS:
            raise _fail("f11_target_kind_unknown")
        if target_id in seen:
            raise _fail("f11_target_id_duplicate")
        seen.add(target_id)
        root = _resolve_root(item.get("root"))
        if require_roots and not root.is_dir():
            raise _fail("f11_target_root_missing")
        target = {"id": target_id, "kind": kind, "root": str(root)}
        if kind == "harness_store" and item.get("dsn"):
            target["dsn"] = str(item["dsn"])
            target["schema"] = str(item.get("schema") or "public")
        targets.append(target)
    return targets


def _passphrase(config: dict) -> str:
    value = config.get("backup_passphrase")
    if not isinstance(value, str) or not value:
        raise _fail("f11_passphrase_required")
    return value


# --------------------------------------------------------------------------
# backup.create —— 一致备份＋口令加密落包＋登记 backup_set 行
# --------------------------------------------------------------------------

def backup_create(args: dict, config: dict) -> dict:
    now = _parse_now((args or {}).get("now"))
    state_root = _state_root(config)
    targets = _targets(config, require_roots=True)
    passphrase = _passphrase(config)
    _require_crypto()
    backup_id = "bk-" + now.strftime("%Y%m%dT%H%M%SZ") + "-" \
        + uuid.uuid4().hex[:8]

    staging = state_root / _STAGING / backup_id
    if staging.exists():
        raise _fail("f11_backup_id_conflict")
    staging.mkdir(parents=True)

    try:
        manifest_targets = []
        for target in targets:
            if target["kind"] == "harness_store":
                store = _open_store(target, config)
                artifact = staging / f"harness-{target['id']}.zip"
                report = store.backup(artifact)
                if not report.get("integrity", {}).get("ok", False):
                    raise _fail("f11_source_integrity_failed")
                manifest_targets.append({
                    "id": target["id"], "kind": target["kind"],
                    "artifact": {
                        "name": artifact.name,
                        "sha256": report["sha256"],
                        "size": artifact.stat().st_size,
                    },
                })
            else:
                copy_dir = staging / target["id"]
                shutil.copytree(_resolve_root(target["root"]), copy_dir)
                files = _digest_tree(copy_dir)
                manifest_targets.append({
                    "id": target["id"], "kind": target["kind"],
                    "files": files,
                    "file_count": len(files),
                    "bytes_total": sum(f["size"] for f in files.values()),
                })

        manifest = {
            "schema": PACKAGE_SCHEMA, "backup_id": backup_id,
            "created_at": now.strftime(_TS_FMT),
            "targets": manifest_targets,
        }
        inner = BytesIO()
        with zipfile.ZipFile(inner, "w", compression=zipfile.ZIP_DEFLATED) \
                as archive:
            archive.writestr(
                "manifest.json",
                json.dumps(manifest, ensure_ascii=False, sort_keys=True))
            for target in manifest_targets:
                if target["kind"] == "harness_store":
                    archive.write(
                        staging / target["artifact"]["name"],
                        f"{target['id']}/{target['artifact']['name']}")
                else:
                    base = staging / target["id"]
                    for rel in sorted(target["files"]):
                        archive.write(
                            _contained_destination(base, rel),
                            f"{target['id']}/{rel}")

        salt = os.urandom(16)
        token = _fernet(passphrase, salt).encrypt(inner.getvalue())
        header = {
            "schema": PACKAGE_SCHEMA, "backup_id": backup_id,
            "created_at": manifest["created_at"],
            "kdf": {"alg": KDF_ALG, "iterations": KDF_ITERATIONS,
                    "salt_b64": base64.b64encode(salt).decode("ascii")},
            "cipher": CIPHER,
        }
        package_path = state_root / _PACKAGES / (backup_id + PACKAGE_SUFFIX)
        package_path.parent.mkdir(parents=True, exist_ok=True)
        payload = PACKAGE_MAGIC + json.dumps(
            header, ensure_ascii=False, sort_keys=True).encode("utf-8") \
            + b"\n" + token
        temporary = package_path.with_name(package_path.name + ".tmp")
        temporary.write_bytes(payload)
        os.replace(temporary, package_path)

        # 明文泄漏后置断言：任一暂存明文原字节不得出现于包字节（口令加密到位）。
        packaged = package_path.read_bytes()
        for plain_path in sorted(staging.rglob("*")):
            if plain_path.is_file():
                plain = plain_path.read_bytes()
                if len(plain) >= 32 and plain in packaged:
                    package_path.unlink()
                    raise _fail("f11_plaintext_leak")

        row = {
            "kind": "backup_set", "backup_id": backup_id,
            "created_at": manifest["created_at"],
            "local_date": now.strftime(_DATE_FMT),
            "targets": [{"id": t["id"], "kind": t["kind"]}
                        for t in manifest_targets],
            "package": {"name": package_path.name,
                        "sha256": _sha256_file(package_path),
                        "size": package_path.stat().st_size},
            "file_count": sum(t.get("file_count", 0)
                              for t in manifest_targets),
        }
        _append_jsonl(state_root / SET_LEDGER, row)
        return row
    finally:
        shutil.rmtree(staging, ignore_errors=True)


# --------------------------------------------------------------------------
# backup.restore —— 独立目录恢复（先全量验包后落位；坏包零写现根）
# --------------------------------------------------------------------------

def _read_package(package_path: Path, passphrase: str):
    """读包＝先完整验（magic/头/MAC/内层 zip/逐成员 sha256），失败一律
    typed 拒——任何目标在此函数返回前都不会被写。"""
    if not package_path.is_file():
        raise _fail("f11_package_missing")
    raw = package_path.read_bytes()
    if not raw.startswith(PACKAGE_MAGIC):
        raise _fail("f11_package_format_invalid")
    try:
        newline = raw.index(b"\n", len(PACKAGE_MAGIC))
        header = json.loads(raw[len(PACKAGE_MAGIC):newline].decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise _fail("f11_package_format_invalid") from None
    if header.get("schema") != PACKAGE_SCHEMA \
            or header.get("cipher") != CIPHER \
            or header.get("kdf", {}).get("alg") != KDF_ALG:
        raise _fail("f11_package_format_invalid")
    try:
        salt = base64.b64decode(header["kdf"]["salt_b64"], validate=True)
        token = raw[newline + 1:]
        inner = _fernet(passphrase, salt).decrypt(token)
    except BackupError:
        raise
    except Exception:  # noqa: BLE001 — 口令错误与包损坏同码（无猜测 oracle）
        raise _fail("f11_package_unreadable") from None
    try:
        with zipfile.ZipFile(BytesIO(inner)) as archive:
            manifest = json.loads(
                archive.read("manifest.json").decode("utf-8"))
            members = {name: archive.read(name)
                       for name in archive.namelist()
                       if name != "manifest.json"}
    except (zipfile.BadZipFile, ValueError, KeyError):
        raise _fail("f11_package_unreadable") from None
    if manifest.get("backup_id") != header.get("backup_id") \
            or manifest.get("schema") != PACKAGE_SCHEMA:
        raise _fail("f11_package_format_invalid")
    for target in manifest["targets"]:
        if target["kind"] == "harness_store":
            artifact_name = (target.get("artifact") or {}).get("name")
            if not isinstance(artifact_name, str) or "/" in artifact_name \
                    or "\\" in artifact_name:
                raise _fail("f11_member_path_invalid")
            _safe_rel_parts(artifact_name)
            member = f"{target['id']}/{artifact_name}"
            data = members.get(member)
            if data is None \
                    or _sha256_bytes(data) != target["artifact"]["sha256"]:
                raise _fail("f11_member_digest_mismatch")
        else:
            files = target.get("files")
            if not isinstance(files, dict):
                raise _fail("f11_member_path_invalid")
            for rel, want in files.items():
                # 路径先于摘要：越界成员不等同于「摘要不符」，也不进入落盘。
                _safe_rel_parts(rel)
                data = members.get(f"{target['id']}/{rel}")
                if data is None or _sha256_bytes(data) != want["sha256"] \
                        or len(data) != want["size"]:
                    raise _fail("f11_member_digest_mismatch")
    return header, manifest, members


def backup_restore(args: dict, config: dict) -> dict:
    args = args or {}
    state_root = _state_root(config)
    targets = _targets(config, require_roots=False)
    passphrase = _passphrase(config)
    backup_id = _check_id(args.get("backup_id"), "f11_backup_id_invalid")
    restore_root_arg = args.get("restore_root")
    if not isinstance(restore_root_arg, str) or not restore_root_arg:
        raise _fail("f11_restore_root_required")
    restore_root = Path(restore_root_arg)
    if _path_covers(restore_root, state_root):
        raise _fail("f11_restore_root_inside_state_root")
    if not _set_rows(state_root, backup_id):
        raise _fail("f11_backup_set_unknown")
    package_path = state_root / _PACKAGES / (backup_id + PACKAGE_SUFFIX)

    header, manifest, members = _read_package(package_path, passphrase)

    # 现根保护（结构级）：恢复目标=root/<tid> 必须不存在；与任一声明现根
    # 重叠（含相等/父子）一律拒——好包也绝不写现根。
    restore_root.mkdir(parents=True, exist_ok=True)
    planned: list[tuple[dict, Path]] = []
    for target in manifest["targets"]:
        declared = next((t for t in targets if t["id"] == target["id"]), None)
        if declared is None:
            raise _fail("f11_target_unknown_in_package")
        destination = restore_root / target["id"]
        for live in targets:
            live_root = Path(live["root"])
            if _path_covers(live_root, destination) \
                    or _path_covers(destination, live_root):
                raise _fail("f11_restore_target_overlaps_live_root")
        if destination.exists() and any(destination.iterdir()):
            raise _fail("f11_restore_target_not_empty")
        planned.append((target, destination))

    job_id = "rj-" + uuid.uuid4().hex[:12]
    staging = state_root / _STAGING / job_id
    staging.mkdir(parents=True)
    created: list[Path] = []
    try:
        results = []
        for target, destination in planned:
            if target["kind"] == "dir":
                staging_dir = staging / target["id"]
                staging_dir.mkdir()
                for rel in sorted(target["files"]):
                    member_path = _contained_destination(staging_dir, rel)
                    member_path.parent.mkdir(parents=True, exist_ok=True)
                    member_path.write_bytes(members[f"{target['id']}/{rel}"])
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(staging_dir), str(destination))
                created.append(destination)
                results.append({"id": target["id"], "kind": target["kind"],
                                "restored_root": str(destination),
                                "files": len(target["files"])})
            else:
                declared = next(
                    t for t in targets if t["id"] == target["id"])
                artifact_name = target["artifact"]["name"]
                artifact = _contained_destination(staging, artifact_name)
                artifact.write_bytes(
                    members[f"{target['id']}/{artifact_name}"])
                destination.parent.mkdir(parents=True, exist_ok=True)
                schema_used = None
                if declared.get("dsn"):
                    schema_used = (str(declared["schema"]) + "__r"
                                   + uuid.uuid4().hex[:8])[:63]
                    _, PgMatterStore = _harness_faces(config)
                    store = PgMatterStore.restore_pg(
                        artifact, destination, dsn=declared["dsn"],
                        schema=schema_used)
                else:
                    MatterStore, _ = _harness_faces(config)
                    store = MatterStore.restore(artifact, destination)
                created.append(destination)
                results.append({
                    "id": target["id"], "kind": target["kind"],
                    "restored_root": str(destination),
                    "integrity_ok": bool(store.integrity_check()["ok"]),
                    **({"restore_schema": schema_used}
                       if schema_used else {})})
        row = {
            "kind": "restore", "restore_job_id": job_id,
            "backup_id": backup_id,
            "package_sha256": _sha256_file(package_path),
            "restored_at": _parse_now(args.get("now")).strftime(_TS_FMT),
            "targets": results,
        }
        _append_jsonl(state_root / JOB_LEDGER, row)
        return row
    except BaseException:
        # 落位失败＝本次已建目标一并清除；现根从未在写入名单里。
        for destination in created:
            shutil.rmtree(destination, ignore_errors=True)
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)


# --------------------------------------------------------------------------
# backup.reconcile —— 结构对账（恢复根存在；文件树 live==manifest==
# restored 逐摘要；恢复库 owner 面 integrity_check）
# --------------------------------------------------------------------------

def backup_reconcile(args: dict, config: dict) -> dict:
    args = args or {}
    state_root = _state_root(config)
    targets = _targets(config, require_roots=False)
    backup_id = _check_id(args.get("backup_id"), "f11_backup_id_invalid")
    restore_root_arg = args.get("restore_root")
    if not isinstance(restore_root_arg, str) or not restore_root_arg:
        raise _fail("f11_restore_root_required")
    restore_root = Path(restore_root_arg)
    if not _set_rows(state_root, backup_id):
        raise _fail("f11_backup_set_unknown")
    restore_jobs = [r for r in _read_jsonl(state_root / JOB_LEDGER)
                    if r.get("kind") == "restore"
                    and r.get("backup_id") == backup_id]
    if not restore_jobs:
        raise _fail("f11_reconcile_requires_restore")
    job = restore_jobs[-1]
    package_path = state_root / _PACKAGES / (backup_id + PACKAGE_SUFFIX)
    _header, manifest, _members = _read_package(package_path,
                                                _passphrase(config))

    findings = []
    for target in manifest["targets"]:
        tid = target["id"]
        restored_root = restore_root / tid
        declared = next((t for t in targets if t["id"] == tid), None)
        if declared is None or not restored_root.is_dir():
            findings.append({"check": "f11_restored_root_present",
                             "target": tid, "status": "FAIL",
                             "detail": "missing"})
            continue
        findings.append({"check": "f11_restored_root_present",
                         "target": tid, "status": "PASS",
                         "detail": "restored_root_present"})
        if target["kind"] == "dir":
            restored = _digest_tree(restored_root)
            want = target["files"]
            live_root = Path(declared["root"])
            live = _digest_tree(live_root) if live_root.is_dir() else None
            if restored == want and live == want:
                findings.append({
                    "check": "f11_files_live_manifest_restored_equal",
                    "target": tid, "status": "PASS",
                    "detail": {"files": len(want),
                               "bytes": sum(f["size"]
                                            for f in want.values())}})
            else:
                findings.append({
                    "check": "f11_files_live_manifest_restored_equal",
                    "target": tid, "status": "FAIL",
                    "detail": {
                        "restored_only": sorted(set(restored) - set(want)),
                        "missing": sorted(set(want) - set(restored)),
                        "changed": sorted(
                            rel for rel in set(want) & set(restored)
                            if restored[rel]["sha256"] != want[rel]["sha256"]),
                        "live_root_missing": live is None}})
        else:
            job_target = next((t for t in job["targets"]
                               if t["id"] == tid), {})
            store = _open_store(
                declared, config, root=restored_root,
                schema=job_target.get("restore_schema"))
            report = store.integrity_check()
            findings.append({
                "check": "f11_restored_store_integrity", "target": tid,
                "status": "PASS" if report.get("ok") else "FAIL",
                "detail": {"ok": bool(report.get("ok")),
                           "artifact_sha256": target["artifact"]["sha256"]}})
    verdict = "RECON_OK" if all(f["status"] == "PASS" for f in findings) \
        else "RECON_FAILED"
    row = {
        "kind": "reconcile", "backup_id": backup_id,
        "restore_job_id": job.get("restore_job_id"),
        "verdict": verdict, "findings": findings,
        "reconciled_at": _parse_now(args.get("now")).strftime(_TS_FMT),
    }
    _append_jsonl(state_root / JOB_LEDGER, row)
    return row


# --------------------------------------------------------------------------
# backup.sets / backup.schedule
# --------------------------------------------------------------------------

def backup_sets(args: dict, config: dict) -> dict:
    state_root = _state_root(config)
    return {"schema": SCHEMA,
            "sets": _read_jsonl(state_root / SET_LEDGER),
            "jobs": _read_jsonl(state_root / JOB_LEDGER)}


def backup_schedule(args: dict, config: dict) -> dict:
    now = _parse_now((args or {}).get("now"))
    state_root = _state_root(config)
    schedule = config.get("backup_schedule")
    interval = schedule.get("interval_days", 1) \
        if isinstance(schedule, dict) else 1
    if not isinstance(interval, int) or isinstance(interval, bool) or interval < 1:
        raise _fail("f11_schedule_interval_invalid")
    _targets(config, require_roots=False)  # 声明面有效性口径与 create 一致
    sets = _set_rows(state_root)
    last = max((r["local_date"] for r in sets), default=None)
    today = now.strftime(_DATE_FMT)
    if last is None:
        due = True
        next_due = today
    else:
        last_day = datetime.strptime(last, _DATE_FMT).date()
        today_day = datetime.strptime(today, _DATE_FMT).date()
        due = (today_day - last_day).days >= interval
        next_due = str(max(today_day,
                           last_day + timedelta(days=interval)))
    return {"schema": SCHEMA, "due": due, "today": today,
            "last_backup_date": last, "interval_days": interval,
            "next_due_date": next_due}


_DISPATCH = {
    "backup.create": backup_create,
    "backup.restore": backup_restore,
    "backup.reconcile": backup_reconcile,
    "backup.sets": backup_sets,
    "backup.schedule": backup_schedule,
}


def backup_call(method: str, args, config: dict) -> dict:
    handler = _DISPATCH.get(method)
    if handler is None:
        raise _fail("f11_method_unknown")
    if args is not None and not isinstance(args, dict):
        raise _fail("f11_params_invalid")
    return handler(args or {}, config)
