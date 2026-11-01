# -*- coding: utf-8 -*-
"""RE-21 增补·技能安装安全层产品面（2026-10-30；规格=docs/RE规格库/
RE-21-技能安装-增补-安全层.md，MingJuris 737ef85 机制净室——零复制其
代码与文案，全部行为级等量自写）。

四柱（规格 §1.2）：技能是「模型照着执行、动的是用户工具和当事人文件」
的指令文本，安装按装软件对待——装之前凭什么拒（清单声明+内容扫描+许可
闸）、装之后凭什么拦（SHA-256 加载重验）、拦了凭什么查（安装史+审计）。

通道归属（规格 §3.0 裁定）：本面=**安全层安装链**（声明式包 skill.json+
sha256）。catzip 第 1 轮面（SKILL.md frontmatter/宽松 skill.json、
%APPDATA% 平铺布局、user 作用域装卸）维持既有装卸不进入本链；既有 catzip
已装 user 技能迁入版本层的方式=待主控（规格 §3.0 迁移待办①），本面不动
catzip 已过闸结论。catzip 形 zip（frontmatter 无 permissions/sha256 声
明）在本通道=无声明即零权限+无哈希即拒装。

复用既有冻结面（规格 §3.1 落点总则，绝不复制第二实现）：
- F95 precheck_zip＝zip 边界唯一权威（路径/权限位/重复条目/解压预算——
  一票否决）；本面另叠安全层三上限（zip 5MB/解压累计 20MB/200 文件，
  规格对拍 #15 同三上限）。
- F27 injection.scan 仍是注入扫描唯一权威（kind="skill" 走审核管线）；
  本面七信号扫描是**装前内容信号**（warnings 随包 traveling 不就地生
  效），与注入扫描分母不同不互替。
- F96 证据四态 STALE 同构：加载重验=旧核不覆盖新内容（对拍 #12）。

六命令（legal_entry 冻结组 SKILL_SECURITY_METHODS）：
- skill.secure.inspect  只读预检：F95 预检+三上限+清单闭集校验（一次全
  报）+入口 sha 断言+七信号扫描+许可闸；全部发现一次返回，不落状态。
- skill.secure.install  安装链：预检全过→暂存→入口 sha 断言（不符=拒
  装+零残留）→版本层落位 packages/<id>/<version>/（同版本替换、多版本
  并存）→records/ 落安装记录（卸载不删行=安装史）→warnings 非空 ⇒
  enabled=0 落库+告知文案（扫描是信号不是健康证明，开关必须由人打开）。
- skill.secure.list     包列表（installed/enabled/hired 三态分离；过滤
  已卸载——卸载后不可见）。
- skill.secure.read     加载重验：读入口前按记录 sha256 重哈希，磁盘被
  改=拒载（s21_entry_tampered，提示重装语义）；已卸载=拒。
- skill.secure.set_active  装停分离的用户开关（「我不想它跑」≠「删掉
  它」）；停用即时生效（本面无加载缓存，读态即现态）。
- skill.secure.uninstall   置 uninstalled_at+enabled=0（行保留）；删包
  目录前校验 install_path 必须在包根内（防损坏记录把卸载变成任意递归
  删除，对拍 #17）。

清单闭集（规格 §2.1，拒改不修复；预检面一次全报）：
必填字段 id/name/version/description/entry/permissions/compatibility/
source/sha256/license；id=小写字母数字连字符点（可作目录名）；version=
x.y.z（可带 -prerelease）；entry=包内相对路径（绝对/反斜杠/盘符/../空
段/首尾空白/NUL 全拒）且后缀仅 .md/.markdown/.txt；permissions 九权限闭
集（未知权限拒绝不静默丢弃）；sha256=64 位小写 hex；source.kind 闭集
local/directory/archive/registry（url/author 可选非空才收）；
compatibility.app 版本范围仅 >=x.y.z/^x.y.z/x.y.z/*（不可解析=不满足=
拒装，宁拒不猜；app 版本未知跳过该检查；0.x 的 caret 钉住 minor）。

许可证闸（规格 §2.5）：来源登记逐源钉 license_status+核查注；restricted/
unknown 不内置（can_bundle）、非 compatible 不装（can_install）、
connector 类登记项不作为普通技能运行（can_run=False——G6 连接器名单只
留档不接线，2026-10-30 裁定）。vendor 禁入清单沿用 RE-21 既有：CC
BY-NC 系/许可未知/仅 README 声称而无 LICENSE 文件=不内置不复制正文。
本面 SOURCES 为合成登记样本（真实来源登记随广场审核管线扩展）。

fail-closed：typed error（SkillSecurityError 的 str 只有 s21_* 错误码，
绝不携材料内容；F95 码以 s21_precheck_failed: 前缀透传）。零执行 zip
内容（安装过程只解包校验不运行）；无模型、无网络、无随机；%APPDATA% 零
触碰（状态根由 config 注入）。config：skill_security_state_root（本面；
未配置=fail-closed）＋skill_security_app_version（可选；缺省=版本未知
→跳过兼容检查）。
"""
from __future__ import annotations

import json
import os
import re
import shutil
import stat
from datetime import datetime, timezone
from pathlib import Path

from skill_catalog import (SkillCatalogError, canonical_bytes, open_zip_bytes,
                           precheck_zip, sha256_hex)

SCHEMA = "juscite-s21-skill-security/1"

# legal_entry 冻结方法组（唯一入口；组外方法绝不落到本面）。
SKILL_SECURITY_METHODS = frozenset({
    "skill.secure.inspect",
    "skill.secure.install",
    "skill.secure.list",
    "skill.secure.read",
    "skill.secure.set_active",
    "skill.secure.uninstall",
})

# 安全层三上限（规格 §2.4/对拍 #15：zip 5MB/解压累计 20MB/200 文件——
# zip bomb 靠解压累计字节抓，叠在 F95 预检预算之上更紧）。
MAX_PACKAGE_ZIP_BYTES = 5 * 1024 * 1024
MAX_UNPACKED_BYTES = 20 * 1024 * 1024
MAX_PACKAGE_FILES = 200

# 九权限闭集（规格 §2.1；未知权限拒绝而非静默丢弃）。
PERMISSIONS = frozenset({
    "read-matter-files", "call-model", "write-artifact", "network",
    "query-legal-database", "require-credentials", "mcp", "shell",
    "delete-files",
})

# 许可证状态四态（规格 §1.1/:7 行为等量；来源登记逐源钉死）。
LICENSE_STATUSES = frozenset({"compatible", "restricted", "needs_review",
                              "unknown"})

SOURCE_KINDS = frozenset({"local", "directory", "archive", "registry"})

# 必填字段闭集（规格 §2.1 清单形状；缺失逐项报且一次全报）。
REQUIRED_FIELDS = (
    "id", "name", "version", "description", "entry", "permissions",
    "compatibility", "source", "sha256", "license",
)

ENTRY_SUFFIXES = (".md", ".markdown", ".txt")

MANIFEST_NAME = "skill.json"
MANIFEST_ENTRY_MD = "SKILL.md"  # catzip 形入口锚定件（迁移面用）

_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*(?:\.[a-z0-9]+(?:-[a-z0-9]+)*)*$")
_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:-[A-Za-z0-9.]+)?$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_HOST_RE = re.compile(r"https?://([^/\s\"'<>\\]+)", re.IGNORECASE)

# ── 七信号扫描正则族（规格 §2.2/§3.5：信号语义等量、正则与文案自写）──
# 信号→建议权限：shell→shell；network→network；write→write-artifact；
# delete→delete-files；env/密钥→require-credentials；mcp→mcp；
# credential→require-credentials。base=call-model 必给。
SIGNAL_PATTERNS = {
    "shell": (
        r"\b(?:bash|zsh|sh|cmd\.exe|powershell|pwsh)\b"
        r"|\b(?:child_process|subprocess)\b"
        r"|\b(?:spawn|exec|execSync|exec_sync|system)\s*\("
        r"|\bos\.system\b|\brm\s+-[rf]{1,2}\b"
    ),
    "network": (
        r"\b(?:curl|wget|nc|netcat)\b"
        r"|\b(?:fetch|requests)\.(?:get|post|put|delete)\s*\("
        r"|\baxios\b|\burllib\b|\bwebsocket\b|\bhttp\.get\s*\("
    ),
    "write": (
        r"\bopen\s*\([^)]*['\"][wa]"
        r"|\b(?:write_file|writeFile|writeFileSync|fwrite)\b"
        r"|\bsaveAs\s*\("
    ),
    "delete": (
        r"\b(?:delete|remove|unlink|rmdir|shred)\s*\("
        r"|\bos\.remove\b|\brm\s+-[rf]{1,2}\b|\bdel\s+/[sq]\b"
    ),
    "env": (
        r"\bprocess\.env\b|\bos\.environ\b|\bgetenv\s*\("
        r"|\b\.env\b|\bAPI[_-]?KEY\b|\bSECRET\b|\bPASSWORD\b"
    ),
    "mcp": r"\bMCP\b|\bmodel\s+context\s+protocol\b",
    "credential": (
        r"\b(?:bearer|authorization)\s*:"
        r"|\blogin\s+token\b|\baccess[_-]?token\b"
        r"|\bprivate[_-]?key\b|\bid_rsa\b|\bcredential\b"
    ),
}
# 信号顺序稳定（warnings 顺序确定性）。
SIGNAL_ORDER = ("shell", "network", "write", "delete", "env", "mcp",
                "credential")
SIGNAL_PERMISSIONS = {
    "shell": "shell", "network": "network", "write": "write-artifact",
    "delete": "delete-files", "env": "require-credentials", "mcp": "mcp",
    "credential": "require-credentials",
}
# shell/删文件/env 三信号=不可自动启用（规格 §2.2）。
UNSAFE_AUTO_ENABLE = frozenset({"shell", "delete", "env"})

SIGNAL_LABELS = {
    "shell": "shell 或子进程调用",
    "network": "网络访问",
    "write": "写文件",
    "delete": "删文件",
    "env": "读取环境变量或密钥字段",
    "mcp": "MCP 调用字样",
    "credential": "凭证字样",
}

# 来源登记（合成样本；license_status 逐源钉死+核查注——规格 §2.5「来源
# 登记逐源钉许可状态并附核查注」等量。键=清单 source.url（registry/direc
# tory/archive 归一为可查来源标识）；真实来源随广场审核管线扩展登记）。
# G6 连接器登记项：kind=connector，只留档不接线（can_run 恒 False）。
SOURCES = {
    "https://synth.example/sources/apache-skill": {
        "kind": "registry", "license": "Apache-2.0",
        "license_status": "compatible", "installable": True,
        "note": "合成样本：仓内带 LICENSE 文件，核验通过",
    },
    "https://synth.example/sources/cc-by-nc-skill": {
        "kind": "registry", "license": "CC-BY-NC-4.0",
        "license_status": "restricted", "installable": True,
        "note": "合成样本：非商业许可，只录元数据不复制正文",
    },
    "https://synth.example/sources/readme-only-skill": {
        "kind": "directory", "license": "MIT（仅 README 声称）",
        "license_status": "needs_review", "installable": False,
        "note": "合成样本：仓库缺 LICENSE 文件，仅 README 单方声称——待核，不 vendor",
    },
    "https://synth.example/sources/no-license-skill": {
        "kind": "archive", "license": None,
        "license_status": "unknown", "installable": False,
        "note": "合成样本：无任何许可声明——不内置",
    },
    "https://synth.example/connectors/g6-demo": {
        "kind": "connector", "license": "Proprietary",
        "license_status": "needs_review", "installable": False,
        "connector": True, "wired": False,
        "note": "G6 连接器登记项（合成样本）：只留档不接线，不作为普通技能运行",
    },
}

_STATE_FILES_DIR = "packages"     # 包文件树：<root>/packages/<id>/<version>/
_STATE_RECORDS_DIR = "records"    # 安装记录树（卸载不删行=安装史）
_HISTORY_NAME = "history.jsonl"
_STAGING_PREFIX = ".staging-"


class SkillSecurityError(ValueError):
    """Typed S21 face failure; str() is a code, never material content."""


def _fail(code: str) -> SkillSecurityError:
    return SkillSecurityError(code)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------
# 清单闭集校验（拒改不修复；一次全报）
# --------------------------------------------------------------------------

def safe_entry_path(value) -> bool:
    """entry 必须包内相对路径（规格 §2.1：绝对/反斜杠/盘符/../空段/首尾
    空白/NUL 全拒）。安全=True；后缀白名单另查。"""
    if not isinstance(value, str):
        return False
    if value != value.strip() or not value:
        return False
    if "\\" in value or "\0" in value:
        return False
    if value.startswith("/") or re.match(r"^[A-Za-z]:", value):
        return False
    segments = value.split("/")
    return all(seg not in ("", ".", "..") for seg in segments)


def parse_version_range(raw) -> tuple | None:
    """compatibility.app 版本范围仅四语法：>=x.y.z / ^x.y.z / x.y.z / *。
    → (op, (maj, min, pat))；不可解析返回 None（=按不满足处理，宁拒不
    猜）。0.x 的 caret 钉住 minor（npm 语义）。"""
    if raw == "*":
        return ("*", None)
    if not isinstance(raw, str):
        return None
    m = re.match(r"^>=(\d+)\.(\d+)\.(\d+)$", raw)
    if m:
        return (">=", tuple(int(g) for g in m.groups()))
    m = re.match(r"^\^(\d+)\.(\d+)\.(\d+)$", raw)
    if m:
        return ("^", tuple(int(g) for g in m.groups()))
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)$", raw)
    if m:
        return ("=", tuple(int(g) for g in m.groups()))
    return None


def _version_tuple(raw) -> tuple | None:
    if not isinstance(raw, str):
        return None
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)(?:-[A-Za-z0-9.]+)?$", raw)
    if not m:
        return None
    return tuple(int(g) for g in m.groups())


def range_satisfies(parsed, app_version) -> bool:
    """app_version=x.y.z 字符串；解析失败的版本号本身=不满足（宁拒不
    猜）。0.x caret：^0.2.3 ⇒ >=0.2.3 且 <0.3.0（钉 minor）；^1.2.3 ⇒
    <2.0.0。"""
    app = _version_tuple(app_version)
    if parsed is None or app is None:
        return False
    op, base = parsed
    if op == "*":
        return True
    if op == ">=":
        return app >= base
    if op == "=":
        return app == base
    # caret：主版本 0 时上界钉 minor，否则钉 major
    upper = (0, base[1] + 1, 0) if base[0] == 0 else (base[0] + 1, 0, 0)
    return base <= app < upper


def validate_declared_manifest(obj, *, app_version=None) -> list:
    """skill.json 闭集校验：返回 issue 码列表（一次全报；空=过）。
    拒改不修复——任何字段问题只报不猜默认值。"""
    issues: list = []
    if not isinstance(obj, dict):
        return ["s21_manifest_not_object"]
    for field in REQUIRED_FIELDS:
        if field not in obj:
            issues.append("s21_field_missing:" + field)
    if "id" in obj and (not isinstance(obj.get("id"), str)
                        or not _ID_RE.match(obj["id"])):
        issues.append("s21_id_invalid")
    if "version" in obj and (
            not isinstance(obj.get("version"), str)
            or not _VERSION_RE.match(obj["version"])):
        issues.append("s21_version_invalid")
    if "entry" in obj:
        entry = obj.get("entry")
        if not safe_entry_path(entry) or not str(entry).lower().endswith(
                ENTRY_SUFFIXES):
            issues.append("s21_entry_invalid")
    if "permissions" in obj:
        perms = obj.get("permissions")
        if not isinstance(perms, list) or not perms \
                or not all(isinstance(p, str) for p in perms):
            issues.append("s21_permissions_invalid")
        else:
            unknown = sorted(set(perms) - PERMISSIONS)
            if unknown:
                # 未知权限拒绝而非静默丢弃（丢弃=装了没人读过的声明）
                issues.append("s21_permission_unknown")
    if "sha256" in obj and (
            not isinstance(obj.get("sha256"), str)
            or not _SHA256_RE.match(obj["sha256"])):
        issues.append("s21_sha256_invalid")
    if "compatibility" in obj:
        compat = obj.get("compatibility")
        if not isinstance(compat, dict) or "app" not in compat:
            issues.append("s21_compatibility_invalid")
        elif parse_version_range(compat.get("app")) is None:
            issues.append("s21_compatibility_unparseable")
    if "source" in obj:
        source = obj.get("source")
        if not isinstance(source, dict) \
                or source.get("kind") not in SOURCE_KINDS:
            issues.append("s21_source_invalid")
        else:
            for opt in ("url", "author"):
                if opt in source and (
                        not isinstance(source[opt], str)
                        or not source[opt].strip()):
                    issues.append("s21_source_invalid")
                    break
    for field in ("name", "description", "license"):
        if field in obj and (not isinstance(obj.get(field), str)
                             or not obj[field].strip()):
            issues.append("s21_" + field + "_invalid")
    # 兼容范围与当前 app 版本不符=拒装（app 版本未知=跳过该检查）；不可解
    # 析的范围按不满足处理（宁拒不猜——四语法之外不猜语义）。
    if app_version is not None and "compatibility" in obj \
            and isinstance(obj.get("compatibility"), dict):
        parsed = parse_version_range(obj["compatibility"].get("app"))
        if parsed is None or not range_satisfies(parsed, app_version):
            issues.append("s21_compatibility_unsatisfied")
    return issues


# --------------------------------------------------------------------------
# 七信号内容扫描（装前信号，warnings 随包 traveling 不就地生效）
# --------------------------------------------------------------------------

def scan_entry_text(text: str, *, declared_permissions=()) -> dict:
    """对入口文本跑七信号正则+http(s) 主机名抽取去重（规格 §2.2/§3.5）。
    返回 {signals, hostnames, permissions_suggested, unsafe_auto_enable,
    warnings}——warnings 为人话码表（零内容回显：不回带命中文本）。"""
    if not isinstance(text, str):
        text = ""
    declared = set(declared_permissions or ())
    signals = []
    for name in SIGNAL_ORDER:
        pattern = SIGNAL_PATTERNS[name]
        if re.search(pattern, text, re.IGNORECASE):
            signals.append(name)
    hostnames = sorted({m.group(1).lower()
                        for m in _HOST_RE.finditer(text)})
    suggested = {"call-model"}
    for name in signals:
        suggested.add(SIGNAL_PERMISSIONS[name])
    warnings = []
    for name in signals:
        warnings.append({
            "code": "s21_signal_" + name,
            "message": "入口文本出现" + SIGNAL_LABELS[name] + "信号",
        })
    # 声明-内容缺口具名（规格 §2.2：内容 shell 但未声明 shell 权限=专门
    # 一条警告——策略层信任的就是声明）。
    if "shell" in signals and "shell" not in declared:
        warnings.append({
            "code": "s21_gap_shell_undeclared",
            "message": "内容出现 shell 调用但清单未声明 shell 权限（声明与内容不一致）",
        })
    return {
        "signals": signals,
        "hostnames": hostnames,
        "permissions_suggested": sorted(suggested),
        "unsafe_auto_enable": any(s in UNSAFE_AUTO_ENABLE for s in signals),
        "warnings": warnings,
    }


# --------------------------------------------------------------------------
# 许可证闸（规格 §2.5：三闸+来源登记制；G6 连接器只留档不接线）
# --------------------------------------------------------------------------

def can_bundle_skill(source_ref: str) -> bool:
    """restricted/unknown 许可不内置（合成来源登记钉死）。未登记=unknown。"""
    entry = SOURCES.get(source_ref)
    status = entry["license_status"] if entry else "unknown"
    return status not in ("restricted", "unknown")


def can_install_skill(source_ref: str) -> bool:
    """installable 且 license_status=compatible 才可装；未登记=拒。"""
    entry = SOURCES.get(source_ref)
    if not entry:
        return False
    return bool(entry.get("installable")) \
        and entry["license_status"] == "compatible"


def can_run_skill(source_ref: str) -> bool:
    """connector 类登记项不作为普通技能运行（G6 连接器名单只留档）。"""
    entry = SOURCES.get(source_ref)
    if not entry:
        return False
    return not entry.get("connector")


# --------------------------------------------------------------------------
# 状态根（包文件树/安装记录树/事件账）
# --------------------------------------------------------------------------

def _state_root(config: dict) -> Path:
    root = config.get("skill_security_state_root")
    if not isinstance(root, str) or not root:
        raise _fail("s21_state_root_not_configured")
    return Path(root)


def _app_version(config: dict):
    raw = config.get("skill_security_app_version")
    return raw if isinstance(raw, str) and _version_tuple(raw) else None


def _history_path(root: Path) -> Path:
    return root / _HISTORY_NAME


def _history_entries(root: Path) -> list:
    path = _history_path(root)
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out


def _append_history(root: Path, entry: dict):
    path = _history_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(canonical_bytes(entry).decode("utf-8") + "\n")


def _package_dir(root: Path, package_id: str, version: str) -> Path:
    return root / _STATE_FILES_DIR / package_id / version


def _record_path(root: Path, package_id: str, version: str) -> Path:
    return root / _STATE_RECORDS_DIR / package_id / (version + ".json")


def _atomic_write(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _valid_id_version(package_id, version) -> bool:
    """id/version 形状前置校验（与清单闭集同款正则）：目录名成分不合法=
    typed 拒——杜绝用路径成分伪造记录/包路径（卸载路径守卫的第一道）。"""
    return (isinstance(package_id, str) and isinstance(version, str)
            and _ID_RE.match(package_id) is not None
            and _VERSION_RE.match(version) is not None)


def _read_record(root: Path, package_id: str, version: str) -> dict | None:
    if not _valid_id_version(package_id, version):
        raise _fail("s21_params_invalid")
    path = _record_path(root, package_id, version)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _rmtree(path: Path):
    for child in sorted(path.rglob("*"), reverse=True):
        if child.is_dir():
            child.rmdir()
        else:
            child.chmod(stat.S_IWRITE)
            child.unlink()
    path.rmdir()


def _source_ref(manifest: dict) -> str:
    """来源登记键=清单 source.url（registry/directory/archive 归一为可查
    来源标识；无 url 或未登记=空串——未登记来源按 unknown 不装）。"""
    source = manifest.get("source") or {}
    url = source.get("url")
    if isinstance(url, str) and url in SOURCES:
        return url
    return ""


# --------------------------------------------------------------------------
# zip 读取与安全层预检（F95 权威复用+三上限+清单闭集+入口 sha+扫描+许可闸）
# --------------------------------------------------------------------------

def _load_zip_files(zip_path, declared_sha) -> tuple:
    """读 zip 字节：来源 sha 必须声明且与实际字节全等（F95 来源预检同
    语义）；F95 precheck 一票否决；安全层三上限叠加。→ (files, zip_sha)。
    失败一律 typed（F95 码以 s21_precheck_failed: 透传）。"""
    if not isinstance(zip_path, str) or not zip_path \
            or not isinstance(declared_sha, str) \
            or not _SHA256_RE.match(declared_sha):
        raise _fail("s21_zip_source_required")
    archive = Path(zip_path)
    if not archive.is_file():
        raise _fail("s21_zip_unreadable")
    data = archive.read_bytes()
    if len(data) > MAX_PACKAGE_ZIP_BYTES:
        raise _fail("s21_package_budget_exceeded")
    actual = sha256_hex(data)
    if actual != declared_sha:
        raise _fail("s21_zip_source_mismatch")
    zin = open_zip_bytes(data)
    with zin:
        try:
            pre = precheck_zip(zin)
        except SkillCatalogError as exc:
            raise _fail("s21_precheck_failed:" + str(exc)) from None
    files = pre["files"]
    if len(files) > MAX_PACKAGE_FILES:
        raise _fail("s21_package_budget_exceeded")
    if pre["total_bytes"] > MAX_UNPACKED_BYTES:
        raise _fail("s21_package_budget_exceeded")
    return files, actual


def _precheck_declared(files: dict, zip_sha: str, app_version) -> dict:
    """清单闭集+入口存在性+入口 sha 断言+扫描+许可闸——全部发现一次返回
    （inspect 面=结果；install 面=任一发现即拒装）。"""
    raw = files.get(MANIFEST_NAME)
    if raw is None:
        return {"ok": False, "issues": ["s21_manifest_missing"],
                "manifest": None, "entry_sha_mismatch": False,
                "scan": None, "license": None}
    try:
        manifest = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        # 坏 JSON=一条 issue 不抛异常（规格 §2.1）
        return {"ok": False, "issues": ["s21_manifest_json"],
                "manifest": None, "entry_sha_mismatch": False,
                "scan": None, "license": None}
    issues = validate_declared_manifest(manifest,
                                        app_version=app_version)
    entry_bytes = None
    sha_mismatch = False
    scan = None
    license_info = None
    if not issues:
        entry = manifest["entry"]
        entry_bytes = files.get(entry)
        if entry_bytes is None:
            issues.append("s21_entry_missing")
        else:
            actual = sha256_hex(entry_bytes)
            if actual != manifest["sha256"]:
                # 入口哈希不符=拒装+报声明值与实际值（对拍 #10）
                sha_mismatch = True
                issues.append("s21_entry_sha_mismatch")
        ref = _source_ref(manifest)
        license_info = {
            "source_ref": ref or None,
            "registered": ref in SOURCES,
            "can_bundle": can_bundle_skill(ref),
            "can_install": can_install_skill(ref),
            "can_run": can_run_skill(ref),
        }
        if not license_info["can_install"]:
            # 未登记来源或非 compatible=不装（fail-closed：装之前凭什么拒）
            issues.append("s21_license_not_installable")
        try:
            text = entry_bytes.decode("utf-8") if entry_bytes is not None \
                else ""
        except UnicodeDecodeError:
            text = ""
        scan = scan_entry_text(text,
                               declared_permissions=manifest["permissions"])
    return {"ok": not issues, "issues": issues, "manifest": manifest,
            "entry_sha_mismatch": sha_mismatch, "scan": scan,
            "license": license_info, "zip_sha256": zip_sha}


# --------------------------------------------------------------------------
# 公开方法面（legal_entry 冻结组 SKILL_SECURITY_METHODS）
# --------------------------------------------------------------------------

def secure_inspect(args: dict, config: dict) -> dict:
    """只读预检：不落任何状态；全部发现一次返回（一次全报）。"""
    files, zip_sha = _load_zip_files(args.get("zip_path"),
                                     args.get("sha256"))
    pre = _precheck_declared(files, zip_sha, _app_version(config))
    out = {
        "status": "OK" if pre["ok"] else "REFUSED",
        "zip_sha256": zip_sha,
        "file_count": len(files),
        "issues": pre["issues"],
        "license": pre["license"],
    }
    if pre["manifest"] is not None:
        manifest = pre["manifest"]
        out["skill"] = {
            "id": manifest.get("id"), "name": manifest.get("name"),
            "version": manifest.get("version"),
            "permissions": manifest.get("permissions"),
        }
    if pre["scan"] is not None:
        out["scan"] = pre["scan"]
        if not pre["scan"]["signals"]:
            # 扫描零提示≠安全（文案自写，规格 §3.5 免责语义）
            out["scan_note"] = "扫描仅匹配已知模式，未发现信号不等于安全"
    return out


def secure_install(args: dict, config: dict) -> dict:
    root = _state_root(config)
    files, zip_sha = _load_zip_files(args.get("zip_path"),
                                     args.get("sha256"))
    pre = _precheck_declared(files, zip_sha, _app_version(config))
    if not pre["ok"]:
        raise _fail("s21_install_refused")
    manifest = pre["manifest"]
    scan = pre["scan"]
    package_id = manifest["id"]
    version = manifest["version"]
    root.mkdir(parents=True, exist_ok=True)
    history = _history_entries(root)
    seq = len(history) + 1
    staging = root / (_STAGING_PREFIX + f"{seq:04d}")
    if staging.exists():
        _rmtree(staging)
    # 暂存→校验→落位：失败安装零残留（暂存目录必清，半解包状态不可被
    # 运行时加载——规格 §2.3）。
    try:
        staging.mkdir(parents=True)
        for rel, blob in sorted(files.items()):
            if rel == MANIFEST_NAME:
                continue  # 清单原样入记录，不作为包文件重复落盘
            target = staging / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(blob)
        # 安装入口断言（暂存内再核一次：移入正式目录前字节必须与清单全等）
        entry_file = staging / manifest["entry"]
        if not entry_file.is_file() \
                or sha256_hex(entry_file.read_bytes()) != manifest["sha256"]:
            raise _fail("s21_entry_sha_mismatch")
        target_dir = _package_dir(root, package_id, version)
        trash = None
        if target_dir.exists():
            # 同版本重装=替换不重复（先挪走旧目录再换位）
            trash = root / _STATE_FILES_DIR / package_id \
                / (version + f".trash-{seq:04d}")
            if trash.exists():
                _rmtree(trash)
            os.rename(target_dir, trash)
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        os.rename(staging, target_dir)
        if trash is not None:
            _rmtree(trash)
    except Exception:
        if staging.exists():
            _rmtree(staging)  # 零残留
        raise
    warnings = scan["warnings"]
    record = {
        "schema": SCHEMA,
        "package_id": package_id,
        "version": version,
        "name": manifest["name"],
        "description": manifest["description"],
        "license": manifest["license"],
        "source": manifest["source"],
        "entry": manifest["entry"],
        "entry_sha256": manifest["sha256"],
        "permissions": manifest["permissions"],
        "compatibility": manifest["compatibility"],
        "zip_sha256": zip_sha,
        "warnings": warnings,
        "signals": scan["signals"],
        "hostnames": scan["hostnames"],
        "unsafe_auto_enable": scan["unsafe_auto_enable"],
        # warnings 非空 ⇒ enabled=0 落库（扫描是信号不是健康证明，开关
        # 必须由人打开——规格 §2.2；对拍 #7）
        "enabled": 0 if warnings else 1,
        "hired": False,
        "uninstalled_at": None,
        "install_seq": seq,
        "installed_at": _now(),
    }
    _atomic_write(_record_path(root, package_id, version),
                  canonical_bytes(record))
    _append_history(root, {
        "seq": seq, "action": "install", "package_id": package_id,
        "version": version, "entry_sha256": manifest["sha256"],
        "zip_sha256": zip_sha, "warnings": len(warnings),
        "enabled": record["enabled"], "at": record["installed_at"],
    })
    # 安装告知文案两分支（规格 §2.2 对拍 #7：装停分离要告知）
    if warnings:
        message = ("已安装但默认停用：扫描发现 " + str(len(warnings))
                   + " 条信号，请人工核验后在技能管理中启用")
    else:
        message = "已安装并启用（扫描未发现已知信号；扫描仅匹配已知模式，不等于安全）"
    return {"status": "INSTALLED", "package_id": package_id,
            "version": version, "enabled": record["enabled"],
            "warnings": warnings, "message": message,
            "install_path": str(target_dir)}


def secure_list(args: dict, config: dict) -> dict:
    root = _state_root(config)
    records_dir = root / _STATE_RECORDS_DIR
    packages = []
    if records_dir.is_dir():
        for pid_dir in sorted(records_dir.iterdir()):
            if not pid_dir.is_dir():
                continue
            for rec_file in sorted(pid_dir.glob("*.json")):
                record = json.loads(rec_file.read_text(encoding="utf-8"))
                if record.get("uninstalled_at") is not None:
                    continue  # 卸载后不可见（对拍 #13）
                packages.append({
                    "package_id": record["package_id"],
                    "version": record["version"],
                    "name": record["name"],
                    # 三态分离（对拍 #36）：installed=文件在盘+哈希在档；
                    # enabled=用户愿意它跑；hired=上专家花名册——不塌缩。
                    "installed": True,
                    "enabled": bool(record["enabled"]),
                    "hired": bool(record.get("hired")),
                    "warnings": len(record.get("warnings") or []),
                    "uninstalled": False,
                })
    return {"status": "OK", "packages": packages,
            "history_count": len(_history_entries(root))}


def secure_read(args: dict, config: dict) -> dict:
    """加载面：读入口前按记录 sha256 重哈希（加载重验）——安装后被改过的
    文件是另一个技能，旧核不覆盖新内容（F96 STALE 同构）。"""
    root = _state_root(config)
    package_id = args.get("package_id")
    version = args.get("version")
    if not isinstance(package_id, str) or not package_id \
            or not isinstance(version, str) or not version:
        raise _fail("s21_params_invalid")
    record = _read_record(root, package_id, version)
    if record is None:
        raise _fail("s21_not_installed")
    if record.get("uninstalled_at") is not None:
        raise _fail("s21_not_installed")  # 已卸载不可加载（对拍 #13）
    entry_file = _package_dir(root, package_id, version) / record["entry"]
    if not entry_file.is_file():
        raise _fail("s21_entry_tampered")
    raw = entry_file.read_bytes()
    if sha256_hex(raw) != record["entry_sha256"]:
        # 磁盘被改=拒绝加载并提示重装（对拍 #12）
        raise _fail("s21_entry_tampered")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise _fail("s21_entry_tampered") from None
    return {"status": "OK", "package_id": package_id, "version": version,
            "enabled": bool(record["enabled"]),
            "hired": bool(record.get("hired")),
            "permissions": record["permissions"],
            "entry": record["entry"], "text": text}


def secure_set_active(args: dict, config: dict) -> dict:
    """装停分离的用户开关（「我不想它跑」≠「删掉它」）；停用即时生效
    （本面无加载缓存，读态即现态）。hired 独立不受影响（三态分离）。"""
    root = _state_root(config)
    package_id = args.get("package_id")
    version = args.get("version")
    enabled = args.get("enabled")
    if not isinstance(package_id, str) or not package_id \
            or not isinstance(version, str) or not version \
            or not isinstance(enabled, bool):
        raise _fail("s21_params_invalid")
    record = _read_record(root, package_id, version)
    if record is None or record.get("uninstalled_at") is not None:
        raise _fail("s21_not_installed")
    # 启用是人工动作（用户显式翻开关=人审）；「不可自动启用」约束在安装
    # 链——warnings 非空恒落 enabled=0，只有本命令能翻开。
    record["enabled"] = 1 if enabled else 0
    _atomic_write(_record_path(root, package_id, version),
                  canonical_bytes(record))
    _append_history(root, {
        "seq": len(_history_entries(root)) + 1,
        "action": "enable" if enabled else "disable",
        "package_id": package_id, "version": version, "at": _now(),
    })
    return {"status": "OK", "package_id": package_id, "version": version,
            "enabled": enabled}


def secure_uninstall(args: dict, config: dict) -> dict:
    """卸载：置 uninstalled_at+enabled=0 不删记录行（包表即安装史——装
    过什么、从哪来、什么时候，移除后仍可查，对拍 #35）；删包目录前校验
    install_path 必须在包根内（防损坏记录把卸载变成任意递归删除）。"""
    root = _state_root(config)
    package_id = args.get("package_id")
    version = args.get("version")
    if not isinstance(package_id, str) or not package_id \
            or not isinstance(version, str) or not version:
        raise _fail("s21_params_invalid")
    record = _read_record(root, package_id, version)
    if record is None or record.get("uninstalled_at") is not None:
        raise _fail("s21_not_installed")
    package_root = (root / _STATE_FILES_DIR).resolve()
    target = _package_dir(root, package_id, version).resolve()
    # 目录名来自受控记录（id/version 过闭集正则后才落盘），此处再校验一
    # 次 resolved 前缀——库行损坏时不把卸载变成任意递归删除（对拍 #17）。
    if target != package_root and package_root not in target.parents:
        raise _fail("s21_uninstall_path_unsafe")
    removed = False
    if target.is_dir():
        _rmtree(target)
        removed = True
    record["enabled"] = 0
    record["uninstalled_at"] = _now()
    _atomic_write(_record_path(root, package_id, version),
                  canonical_bytes(record))
    _append_history(root, {
        "seq": len(_history_entries(root)) + 1, "action": "uninstall",
        "package_id": package_id, "version": version,
        "directory_removed": removed, "at": record["uninstalled_at"],
    })
    return {"status": "UNINSTALLED", "package_id": package_id,
            "version": version, "visible": False}


def security_call(method: str, args: dict, config: dict) -> dict:
    if not isinstance(args, dict):
        raise _fail("s21_params_invalid")
    if method == "skill.secure.inspect":
        return secure_inspect(args, config)
    if method == "skill.secure.install":
        return secure_install(args, config)
    if method == "skill.secure.list":
        return secure_list(args, config)
    if method == "skill.secure.read":
        return secure_read(args, config)
    if method == "skill.secure.set_active":
        return secure_set_active(args, config)
    if method == "skill.secure.uninstall":
        return secure_uninstall(args, config)
    raise _fail("s21_method_unknown")


# --------------------------------------------------------------------------
# 一次性迁移：catzip 已装 user 技能 → 版本层 packages/<id>/<version>/
# （RE-21 增补 §3.0 迁移待办①，2026-10-31 主控裁决=一次性脚本迁移；非
# legal_entry 冻结方法组面——只由 implementation/python/migrate_catzip_
# skills.py 一次性脚本调用，运行时通道不暴露本函数）。
# --------------------------------------------------------------------------

MIGRATION_SCHEMA = "juscite-s21-catzip-migration/1"
MIGRATED_VERSION = "0.0.0-catzip"   # catzip 无版本声明→合成占位版本（x.y.z-prerelease 合形）
MIGRATED_FROM = "catzip"

_FRONTMATTER_KV_RE = re.compile(r"^(name|description):\s*(.+?)\s*$")


def _catzip_identify(skill_dir: Path) -> tuple:
    """catzip 双格式 manifest 识别（识别序与 tools/bridge/skills_service.mjs
    identifySkill 同构：根 SKILL.md frontmatter 优先、缺则根 skill.json）。
    → (name, description)；无法识别=typed 拒（s21_migrate_manifest_unreadable）。
    本函数只为迁移取 name/description 两字段，不复制 catzip 装卸行为。"""
    md = skill_dir / MANIFEST_ENTRY_MD
    js = skill_dir / "skill.json"
    if md.is_file():
        try:
            text = md.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            raise _fail("s21_migrate_manifest_unreadable") from None
        m = re.match(r"^---\r?\n([\s\S]*?)\r?\n---", text)
        if m:
            fields = {}
            for line in m.group(1).splitlines():
                kv = _FRONTMATTER_KV_RE.match(line)
                if kv:
                    fields[kv.group(1)] = kv.group(2).strip("\"'")
            if fields.get("name"):
                return fields["name"], fields.get("description", "")
        if js.is_file():
            try:
                data = json.loads(js.read_text(encoding="utf-8"))
            except (ValueError, UnicodeDecodeError):
                raise _fail("s21_migrate_manifest_unreadable") from None
            if isinstance(data, dict) and isinstance(data.get("name"), str) \
                    and data["name"]:
                return data["name"], str(data.get("description") or "")
        raise _fail("s21_migrate_manifest_unreadable")
    if js.is_file():
        try:
            data = json.loads(js.read_text(encoding="utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise _fail("s21_migrate_manifest_unreadable") from None
        if isinstance(data, dict) and isinstance(data.get("name"), str) \
                and data["name"]:
            return data["name"], str(data.get("description") or "")
    raise _fail("s21_migrate_manifest_unreadable")


def _migrated_package_id(name: str) -> str:
    """catzip 名（[A-Za-z0-9][A-Za-z0-9._-]{0,63}）→ 安全层 id（小写点分闭
    集）：小写化+下划线归连字符。归一后仍不合 id 闭集=typed 拒。"""
    pid = name.strip().lower().replace("_", "-")
    if not _ID_RE.match(pid):
        raise _fail("s21_migrate_id_invalid")
    return pid


def _collect_dir_files(skill_dir: Path) -> dict:
    """收集待迁移文件（相对路径→字节；POSIX 分隔符）。路径形状逐个闸（绝
    对/反斜杠原始形态/../空段=typed 拒——catzip 落盘件本过 zip-slip 闸，此
    处再验=迁移不信任旧布局）；叠安全层三上限（文件数/解压累计）。"""
    files = {}
    total = 0
    for child in sorted(skill_dir.rglob("*")):
        if child.is_dir():
            continue
        rel = child.relative_to(skill_dir).as_posix()
        if not safe_entry_path(rel):
            raise _fail("s21_migrate_path_unsafe")
        blob = child.read_bytes()
        total += len(blob)
        files[rel] = blob
    if len(files) > MAX_PACKAGE_FILES or total > MAX_UNPACKED_BYTES:
        raise _fail("s21_package_budget_exceeded")
    if not files:
        raise _fail("s21_migrate_entry_missing")
    return files


def migrate_catzip_skills(catzip_root, config: dict, *, apply: bool = True) -> dict:
    """一次性迁移面：catzip 已装 user 技能目录（%APPDATA%\\Juscite\\bridge\\
    skills\\<name>\\ 平铺）→ 本面版本层 packages/<id>/<version>/ + records/
    安装记录 + history 事件账（RE-21 增补 §3.0 裁定+迁移待办①落定）。

    语义（规格 §3.6/§3.0，2026-10-31 定稿）：
    - 迁移=数据布局迁移，不是安全层安装：不补造 manifest（permissions=[]
      零声明=零权限，策略面按无声明 deny 级拦），记录带 migrated_from/catzip
      溯源字段与合成版本 0.0.0-catzip。
    - 迁移时对入口正文跑七信号扫描，warnings 非空 ⇒ enabled=0（装停分离语义
      跨迁移保持；catzip 侧 setEnabled 是进程内态从不落盘，无可继承的启停
      历史——不迁移不补造）。
    - 逐件隔离：一件失败不拦其余（失败件带 typed 码进报告，源目录不动）；
      成功件=暂存→入口 sha 断言→落位→记录→移除源目录（真迁移，防双面双见）。
    - 幂等边界：版本层已有同 id+版本记录而源目录又在场=冲突件 typed 拒
      （迁移后经 catzip 面重装的同名件须人工裁决，不静默覆盖）。
    - apply=False=干跑：零写入，报告标 planned。
    """
    root = _state_root(config)
    src = Path(catzip_root) if isinstance(catzip_root, str) else catzip_root
    if not isinstance(catzip_root, (str, Path)):
        raise _fail("s21_params_invalid")
    report = {
        "schema": MIGRATION_SCHEMA, "apply": bool(apply),
        "catzip_root": str(src), "state_root": str(root),
        "at": _now(), "migrated": [], "planned": [], "failed": [],
    }
    if not src.is_dir():
        # 源根不存在=没有可迁移件（如从未装过 catzip 技能的机器）：零件成功
        report["source_root_present"] = False
        return report
    report["source_root_present"] = True
    for skill_dir in sorted(p for p in src.iterdir() if p.is_dir()):
        item = {"dir": skill_dir.name}
        try:
            name, description = _catzip_identify(skill_dir)
            package_id = _migrated_package_id(name)
            item.update({"name": name, "package_id": package_id,
                         "version": MIGRATED_VERSION})
            entry = skill_dir / MANIFEST_ENTRY_MD
            if not entry.is_file():
                # 入口锚定件缺失=无法建 sha 记录（fail-closed：宁拒不猜）
                raise _fail("s21_migrate_entry_missing")
            existing = _read_record(root, package_id, MIGRATED_VERSION)
            if existing is not None:
                raise _fail("s21_migrate_conflict")
            files = _collect_dir_files(skill_dir)
            entry_bytes = files[MANIFEST_ENTRY_MD]
            entry_sha = sha256_hex(entry_bytes)
            try:
                text = entry_bytes.decode("utf-8")
            except UnicodeDecodeError:
                raise _fail("s21_migrate_manifest_unreadable") from None
            scan = scan_entry_text(text, declared_permissions=())
            item.update({
                "entry": MANIFEST_ENTRY_MD, "entry_sha256": entry_sha,
                "file_count": len(files),
                "signals": scan["signals"],
                "warnings": len(scan["warnings"]),
                "enabled": 0 if scan["warnings"] else 1,
            })
            if not apply:
                report["planned"].append(item)
                continue
            # 暂存→断言→落位（失败零残留，同安装链）
            root.mkdir(parents=True, exist_ok=True)
            seq = len(_history_entries(root)) + 1
            staging = root / (_STAGING_PREFIX + f"m{seq:04d}")
            if staging.exists():
                _rmtree(staging)
            try:
                staging.mkdir(parents=True)
                for rel, blob in sorted(files.items()):
                    target = staging / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(blob)
                if sha256_hex((staging / MANIFEST_ENTRY_MD)
                              .read_bytes()) != entry_sha:
                    raise _fail("s21_entry_sha_mismatch")
                target_dir = _package_dir(root, package_id, MIGRATED_VERSION)
                if target_dir.exists():
                    raise _fail("s21_migrate_conflict")
                target_dir.parent.mkdir(parents=True, exist_ok=True)
                os.rename(staging, target_dir)
            except Exception:
                if staging.exists():
                    _rmtree(staging)
                raise
            record = {
                "schema": SCHEMA,
                "package_id": package_id,
                "version": MIGRATED_VERSION,
                "name": name,
                "description": description,
                "license": "unknown",
                "source": {"kind": "local"},
                "entry": MANIFEST_ENTRY_MD,
                "entry_sha256": entry_sha,
                "permissions": [],
                "compatibility": {"app": "*"},
                "zip_sha256": None,
                "warnings": scan["warnings"],
                "signals": scan["signals"],
                "hostnames": scan["hostnames"],
                "unsafe_auto_enable": scan["unsafe_auto_enable"],
                "enabled": 0 if scan["warnings"] else 1,
                "hired": False,
                "uninstalled_at": None,
                "install_seq": seq,
                "installed_at": _now(),
                # 迁移溯源（零声明包与声明式包的区分凭据）
                "migrated_from": MIGRATED_FROM,
                "migrated_dir": skill_dir.name,
                "migrated_at": _now(),
            }
            _atomic_write(_record_path(root, package_id, MIGRATED_VERSION),
                          canonical_bytes(record))
            _append_history(root, {
                "seq": seq, "action": "migrate", "package_id": package_id,
                "version": MIGRATED_VERSION, "entry_sha256": entry_sha,
                "migrated_from": MIGRATED_FROM, "warnings": len(scan["warnings"]),
                "enabled": record["enabled"], "at": record["installed_at"],
            })
            _rmtree(skill_dir)  # 真迁移：版本层落定后移除平铺源目录
            item["install_path"] = str(_package_dir(root, package_id,
                                                    MIGRATED_VERSION))
            report["migrated"].append(item)
        except SkillSecurityError as exc:
            item["code"] = str(exc)
            report["failed"].append(item)  # 源目录不动，人工按报告处置
    return report
