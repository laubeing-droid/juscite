"""F94 技能目录分发链＋F95 cat-xierluo zip 直装兼容（W3-U17）：产品侧
skill-catalog 公开面（document-adapter 家族新面）。

义务 06:F94 断言（F94-desktop/F94-selfhost）：「pin commit/hash 的社区技能
目录可离线安装和回滚；商用内容不混广场」。17 卡落点＝Harness
manuals/playbook 公开消费＋受控内容包。§6.1 裁决#7：manuals/persona 受控
内容**合成样本先行**、不公开蒸馏。
义务 06:F95 断言（F95-desktop/F95-selfhost）：「zip 预检路径/权限/来源，
格式兼容真安装运行；不信任任意脚本」。

格式权威（oc28 pin 026b106bc5d41b679ffc413264229c340871e4d3 只读对照）：
- 技能＝含 SKILL.md 的目录（或技能源根下的裸 *.md），frontmatter 闭集
  {name, description, metadata, disable-model-invocation}（upstream
  packages/schema/src/skill.ts Info＋config/plugin/skill-file.ts Frontmatter）。
- 运行消费投影＝upstream packages/core/src/skill.ts toModelOutput 逐字节
  同形（<skill_content name=…>＋正文＋base directory＋采样文件列表）。
  本面 read 返回同形投影＝「真安装运行」的消费合同；原生 loader 经 config
  skills 目录源直接可加载 materialized 的 skills/ 布局。

分发链（F94，channel 闭集 public/controlled）：
- git_local 源＝独立仓钉 commit（必须 40 hex 全 sha）：git archive 离线
  取树（源仓只读零改动），仓根 catalog.json 必须声明 {catalog_id,
  channel}——受控包声明 controlled，社区目录声明 public。
- 安装＝内容寻址全量替换：manifest（schema juscite-f94-skill-catalog/1，
  逐文件 sha256）→ store/<manifest_sha256>/（不可变）→ materialize 到
  skills/（活动面）。同 pin 重装落同一 store（零重复）。
- 回滚＝沿 history 只回退到上一个 install（首个 install 无前可回，typed
  拒）；store 内容寻址使回滚零重建。
- pack/bundle＝桌面离线捆绑：pack 产出确定性 zip（manifest.json＋文件），
  另一状态根 bundle 源安装零网络，manifest_sha256 与源安装相等（同一 pin
  穿越传输路径不变）。
- 商用内容不混广场：manifest.channel 必须＝安装目标 channel（bundle/zip
  携声明，git_local 由仓内 catalog.json 声明）；受控包装进 public 槽＝
  f94_channel_mismatch typed 拒；zip（社区发布件）只准 public。渠道根物理
  分离，面上无任何跨渠道搬运方法。

zip 直装（F95，cat-xierluo 发布格式）：
- 预检（inspect＝只检不装；install 先检后装，一票否决零部分解压）：
  路径（upstream isSafeRelativePath 同族：绝对/反斜杠/NUL/?/#/URL 形/驱
  动器/保留设备名/…段全拒＋深度上限）、条目类型（符号链接等非普通文件
  拒）、权限位（setuid/setgid/sticky 拒；可执行位如实列出）、重复条目、
  解压预算（条目数/总量/单文件/压缩比上限——zip 炸弹 fail-closed）。
- 来源：source {url, sha256} 必须声明且与 zip 实际字节全等（缺失/
  不匹配 typed 拒）＝来源预检。
- 格式兼容真安装运行：zip 内 ≥1 个可加载技能（SKILL.md 按上游规则可解）
  才收；全零或全坏＝f95_zip_format_incompatible；安装后 read 投影＝
  upstream toModelOutput 同形。
- 不信任任意脚本：安装过程零执行 zip 内容（脚本文件为惰性数据如实列入
  receipt.scripts；本面 zip 路径零 subprocess，git 子进程仅用于 git_local
  源的钉定 commit 解析）。

fail-closed：未配置状态根、来源未声明/不匹配、任何预检违例、渠道不匹
配、frontmatter 上游不可加载、空目录、store 漂移——一律 typed error
（f94_*/f95_* 错误码），绝不装出半个目录、绝不假成功。错误码不携内容。
确定性：无模型、无网络、无随机（原子替换用顺序号不用 uuid）；pack 的
zip 定时间戳，同输入字节级同产物；manifest 摘要跨 profile 相等。
"""
from __future__ import annotations

import hashlib
import json
import ntpath
import os
import re
import stat
import subprocess
import tarfile
import zipfile
import io
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = "juscite-f94-skill-catalog/1"
STATE_SUBDIR = "skill-catalog"
CHANNELS = ("public", "controlled")
CATALOG_MARKER = "catalog.json"          # git_local 源的渠道声明（fail-closed 必带）
BUNDLE_MANIFEST = "manifest.json"        # pack 产物内的清单条目名

# zip 预检预算（解压炸弹 fail-closed；外部输入边界防御）
MAX_ZIP_ENTRIES = 4096
MAX_ZIP_TOTAL_BYTES = 256 * 1024 * 1024
MAX_ZIP_FILE_BYTES = 64 * 1024 * 1024
MAX_ZIP_DEPTH = 16
ZIP_BOMB_RATIO = 200                     # 仅当未压缩总量 > 1 MiB 时适用
ZIP_BOMB_MIN_UNCOMPRESSED = 1024 * 1024

# 惰性脚本清单（如实列出＝不执行；运行时执行面归权限模型，非本面）
SCRIPT_EXTS = {
    ".py", ".sh", ".ps1", ".bat", ".cmd", ".com", ".scr", ".vbs", ".js",
    ".mjs", ".cjs", ".ts", ".exe", ".dll", ".so", ".dylib",
}

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SAFE_SEG_RE = re.compile(
    r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\..*)?$", re.IGNORECASE)
_FM_OPEN_RE = re.compile(r"^---\r?\n")
_FM_LINE_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*)$")
_FM_COMPLEX_RE = re.compile(r"^[\[{>|*&]")
_FRONTMATTER_KEYS = ("name", "description", "metadata",
                     "disable-model-invocation")


class SkillCatalogError(ValueError):
    """Typed F94/F95 face failure; str() is a code, never material content."""

    error_code = "f94_invalid"


def _fail(code: str) -> SkillCatalogError:
    return SkillCatalogError(code)


# --------------------------------------------------------------------------
# 确定性序列化／摘要
# --------------------------------------------------------------------------

def canonical_bytes(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --------------------------------------------------------------------------
# SKILL.md frontmatter（上游可加载性镜像）
# --------------------------------------------------------------------------

def _fm_scalar(raw: str):
    """→ (value|None, scalar_ok, is_null)。镜像上游可观察契约：带引号标量
    /裸标量＝可加载；空值（YAML null）/块标量/流集合＝name/description 上
    游 decode 失败→Skipped。"""
    if raw == "":
        return None, True, True
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ("'", '"'):
        return raw[1:-1], True, False
    if _FM_COMPLEX_RE.match(raw):
        return None, False, False
    return raw, True, False


def parse_skill_markdown(text: str):
    """镜像 upstream config/plugin/skill-file.ts parse() 可观察契约。

    返回 {"name": str|None, "description": str|None, "content": str}
    （name 缺省由调用方取 id）；返回 None＝上游会 Skipped（YAML 不可解或
    frontmatter schema decode 失败）——此类文件本面拒绝入目录
    （fail-closed：钉住上游加载不了的技能＝装样子）。"""
    if not _FM_OPEN_RE.match(text):
        return {"name": None, "description": None, "content": text}
    rest = text[_FM_OPEN_RE.match(text).end():]
    close = re.search(r"^---[ \t]*\r?$", rest, re.M)
    if close is None:
        # gray-matter：无闭合定界符→无 frontmatter 提取，整文即正文
        return {"name": None, "description": None, "content": text}
    fm_text, content = rest[:close.start()], rest[close.end():]
    data: dict = {}
    for line in fm_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if line[:1] in (" ", "\t"):
            continue  # 嵌套块（metadata 等）不透明，容忍
        m = _FM_LINE_RE.match(line)
        if m is None:
            return None  # 列表项/散文→非映射→上游 Skipped
        key, raw = m.group(1), m.group(2).strip()
        value, scalar_ok, is_null = _fm_scalar(raw)
        if key in ("name", "description"):
            if not scalar_ok or is_null:
                return None
            data[key] = value
        # metadata / disable-model-invocation / 未知键：上游容忍，照容忍
    return {"name": data.get("name"), "description": data.get("description"),
            "content": content}


def _safe_segment(seg: str) -> bool:
    return (bool(seg) and seg not in (".", "..") and "/" not in seg
            and "\\" not in seg and "\0" not in seg
            and not _SAFE_SEG_RE.match(seg))


def _safe_rel_path(name: str):
    """zip/tar 条目路径预检（upstream isSafeRelativePath 同族＋Windows 加
    固）。安全返回 posix 相对路径，否则 None。"""
    if not name or "\\" in name or "\0" in name or "?" in name or "#" in name:
        return None
    if any(ord(ch) < 0x20 for ch in name):
        return None  # 控制字符（安装边界加固，严格于上游）
    if name.startswith("/") or ntpath.isabs(name):
        return None
    if re.match(r"^[A-Za-z][A-Za-z0-9+.\-]*:", name):
        return None  # 驱动器形（C:x）与 URL 形（含 http:）一并拒——上游
        # isSafeRelativePath 拒 win32 绝对与 URL.canParse；此处取严格并集
    segments = name.split("/")
    for seg in segments:
        if not _safe_segment(seg):
            return None
    if len(segments) > MAX_ZIP_DEPTH:
        return None
    return name


# --------------------------------------------------------------------------
# 技能推导（源树 → manifest）
# --------------------------------------------------------------------------

def derive_manifest_from_files(files: dict, *, catalog_id: str, channel: str,
                               kind: str, commit=None, zip_sha256=None,
                               source_label: str = "") -> dict:
    """files: {posix 相对路径: bytes}（相对技能源根）。推导 manifest＋挂载
    映射：根级裸 *.md（SKILL.md 除外）＝单文件技能（id＝文件名去后缀）；
    含 SKILL.md 的目录＝目录技能（id＝目录名，basenames 歧义即拒）。每个
    技能文件必须上游可加载（parse_skill_markdown 非 None）。

    返回 {"manifest": manifest, "mount": {挂载路径: 源相对路径}}——挂载路
    径＝安装面 skills/ 内布局（manifest.files[].path），源相对路径＝传输
    细节不入 manifest（摘要跨传输路径稳定）。"""
    if channel not in CHANNELS:
        raise _fail("f94_channel_invalid")
    if not catalog_id or not _safe_segment(catalog_id):
        raise _fail("f94_catalog_id_invalid")
    skills: dict = {}
    flat: list = []
    mount: dict = {}

    def _parse_entry(rel: str) -> dict:
        try:
            text = files[rel].decode("utf-8")
        except UnicodeDecodeError:
            raise _fail("f94_skill_frontmatter_invalid") from None
        parsed = parse_skill_markdown(text)
        if parsed is None:
            raise _fail("f94_skill_frontmatter_invalid")
        return parsed

    for rel in sorted(files):
        parts = rel.split("/")
        if parts[-1] == "SKILL.md":
            sid = parts[-2] if len(parts) >= 2 else catalog_id
            if not _safe_segment(sid) or sid in skills:
                raise _fail("f94_skill_id_ambiguous")
            parsed = _parse_entry(rel)
            skills[sid] = {"id": sid, "name": parsed["name"] or sid,
                           "description": parsed["description"],
                           "entry_kind": "dir", "root": "/".join(parts[:-1])}
    for rel in sorted(files):
        parts = rel.split("/")
        if len(parts) == 1 and parts[0].endswith(".md") \
                and parts[0] != "SKILL.md":
            sid = parts[0][:-3]
            if not _safe_segment(sid) or sid in skills:
                raise _fail("f94_skill_id_ambiguous")
            parsed = _parse_entry(rel)
            skills[sid] = {"id": sid, "name": parsed["name"] or sid,
                           "description": parsed["description"],
                           "entry_kind": "root_md", "root": rel}
    if not skills:
        raise _fail("f94_catalog_empty")
    for sid in sorted(skills):
        sk = skills[sid]
        prefix = sk["root"] + "/" if sk["entry_kind"] == "dir" else ""
        file_count = 0
        for rel in sorted(files):
            if sk["entry_kind"] == "dir":
                if not rel.startswith(prefix) or rel == sk["root"]:
                    continue
                mount_rel = sid + "/" + rel[len(prefix):]
            else:
                if rel != sk["root"]:
                    continue
                mount_rel = sid + ".md"
            flat.append({"path": mount_rel, "sha256": sha256_hex(files[rel]),
                         "bytes": len(files[rel])})
            mount[mount_rel] = rel
            file_count += 1
    manifest = {
        "schema": SCHEMA,
        "catalog_id": catalog_id,
        "channel": channel,
        "kind": kind,
        "skills": [{"id": sid, "name": skills[sid]["name"],
                    **({"description": skills[sid]["description"]}
                       if skills[sid]["description"] is not None else {}),
                    "file_count": sum(1 for f in flat
                                      if f["path"].split("/")[0] ==
                                      sid + (".md" if skills[sid]
                                             ["entry_kind"] == "root_md"
                                             else ""))}
                   for sid in sorted(skills)],
        "files": flat,
    }
    if commit is not None:
        manifest["commit"] = commit
    if zip_sha256 is not None:
        manifest["zip_sha256"] = zip_sha256
    if source_label:
        manifest["source_label"] = source_label
    return {"manifest": manifest, "mount": mount}


# --------------------------------------------------------------------------
# zip 预检（F95：路径/权限/来源/预算）＋ zip 内容读取
# --------------------------------------------------------------------------

def precheck_zip(zin: zipfile.ZipFile) -> dict:
    """一票否决预检；返回 {files: {rel: bytes}, dirs, executable, scripts,
    total_bytes}。违例 raise typed。zip 内容仅作为数据读取，绝不执行。"""
    infos = zin.infolist()
    if len(infos) > MAX_ZIP_ENTRIES:
        raise _fail("f95_zip_budget_exceeded")
    seen: set = set()
    dir_prefixes: set = set()
    files: dict = {}
    executable: list = []
    scripts: list = []
    total = 0
    for info in infos:
        raw = info.filename
        is_dir = info.is_dir()
        name = raw[:-1] if is_dir else raw
        if is_dir:
            if not name:  # 根目录条目
                continue
            if _safe_rel_path(name) is None:
                raise _fail("f95_zip_path_unsafe")
            mode_dir = info.external_attr >> 16
            if mode_dir and stat.S_IFMT(mode_dir) not in (stat.S_IFDIR, 0):
                raise _fail("f95_zip_entry_not_regular")
            dir_prefixes.add(name + "/")
            continue
        rel = _safe_rel_path(name)
        if rel is None:
            raise _fail("f95_zip_path_unsafe")
        if rel in seen:
            raise _fail("f95_zip_entry_duplicate")
        seen.add(rel)
        mode = info.external_attr >> 16
        if mode:
            fmt = stat.S_IFMT(mode)
            if is_dir:
                # 目录条目带常规权限位是 Unix 工具常态（0o40755…），放行
                if fmt not in (stat.S_IFDIR, 0):
                    raise _fail("f95_zip_entry_not_regular")
            else:
                if fmt not in (stat.S_IFREG, 0):
                    raise _fail("f95_zip_entry_not_regular")
                if mode & 0o7000:
                    raise _fail("f95_zip_permission_bits")
                if mode & 0o111:
                    executable.append(rel)
        if info.file_size > MAX_ZIP_FILE_BYTES:
            raise _fail("f95_zip_budget_exceeded")
        total += info.file_size
        if total > MAX_ZIP_TOTAL_BYTES:
            raise _fail("f95_zip_budget_exceeded")
        data = zin.read(info)
        if info.compress_size and info.file_size > ZIP_BOMB_MIN_UNCOMPRESSED \
                and info.file_size / info.compress_size > ZIP_BOMB_RATIO:
            raise _fail("f95_zip_budget_exceeded")
        files[rel] = data
        ext = os.path.splitext(rel)[1].lower()
        if ext in SCRIPT_EXTS:
            scripts.append(rel)
    # 文件/目录前缀冲突（"a" 文件与 "a/b" 文件同名路径冲突）
    for rel in files:
        prefix = ""
        for seg in rel.split("/")[:-1]:
            prefix = prefix + seg if not prefix else prefix + "/" + seg
            if prefix in files:
                raise _fail("f95_zip_entry_duplicate")
    return {"files": files, "dirs": sorted(dir_prefixes),
            "executable": sorted(executable), "scripts": sorted(scripts),
            "total_bytes": total}


def open_zip_bytes(data: bytes) -> zipfile.ZipFile:
    try:
        return zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise _fail("f95_zip_unreadable") from None


# --------------------------------------------------------------------------
# 三种源的读取（git_local 钉 commit / bundle 携清单 / zip 社区发布件）
# --------------------------------------------------------------------------

def _git(repo: Path, *args: str) -> bytes:
    if not repo.is_dir():
        raise _fail("f94_repo_not_found")
    try:
        proc = subprocess.run(["git", "-C", str(repo), *args],
                              capture_output=True, timeout=120)
    except OSError:
        raise _fail("f94_repo_not_git") from None
    if proc.returncode != 0:
        raise _fail("f94_commit_not_found")
    return proc.stdout


def _read_source_git(source: dict, channel: str) -> dict:
    repo_raw = source.get("repo")
    commit = source.get("commit")
    if not isinstance(repo_raw, str) or not repo_raw \
            or not isinstance(commit, str) or not _SHA_RE.match(commit):
        raise _fail("f94_source_invalid")
    repo = Path(repo_raw)
    resolved = _git(repo, "rev-parse", "--verify", "--quiet",
                    commit + "^{commit}").decode().strip()
    if resolved != commit:
        raise _fail("f94_commit_not_found")
    tar_bytes = _git(repo, "archive", commit)
    files: dict = {}
    with tarfile.open(fileobj=io.BytesIO(tar_bytes)) as tar:
        for member in tar.getmembers():
            if not member.isreg():
                continue  # git archive 亦可能携带子目录条目；符号链接等拒绝
            name = member.name
            if name.startswith("./"):
                name = name[2:]
            rel = _safe_rel_path(name)
            if rel is None:
                raise _fail("f95_zip_path_unsafe")
            files[rel] = tar.extractfile(member).read()
    marker = files.get(CATALOG_MARKER)
    if marker is None:
        raise _fail("f94_source_channel_undeclared")
    try:
        declared = json.loads(marker.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise _fail("f94_source_channel_undeclared") from None
    if not isinstance(declared, dict) \
            or declared.get("channel") not in CHANNELS \
            or not isinstance(declared.get("catalog_id"), str):
        raise _fail("f94_source_channel_undeclared")
    if declared["channel"] != channel:
        raise _fail("f94_channel_mismatch")
    derived = derive_manifest_from_files(
        files, catalog_id=declared["catalog_id"], channel=channel,
        kind="git_local", commit=commit)
    derived["manifest"]["source_declared_channel"] = declared["channel"]
    derived["files"] = files
    return derived


def _read_source_bundle(source: dict, channel: str) -> dict:
    path_raw = source.get("path")
    declared_sha = source.get("sha256")
    if not isinstance(path_raw, str) or not path_raw \
            or not isinstance(declared_sha, str) \
            or not re.match(r"^[0-9a-f]{64}$", declared_sha):
        raise _fail("f94_source_invalid")
    bundle = Path(path_raw)
    if not bundle.is_file():
        raise _fail("f94_bundle_not_found")
    data = bundle.read_bytes()
    if sha256_hex(data) != declared_sha:
        raise _fail("f95_zip_source_mismatch")
    zin = open_zip_bytes(data)
    with zin:
        pre = precheck_zip(zin)
        files = dict(pre["files"])
    inner_raw = files.pop(BUNDLE_MANIFEST, None)
    if inner_raw is None:
        raise _fail("f94_bundle_invalid")
    try:
        inner = json.loads(inner_raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise _fail("f94_bundle_invalid") from None
    if not isinstance(inner, dict) or inner.get("schema") != SCHEMA \
            or inner.get("channel") not in CHANNELS \
            or not isinstance(inner.get("files"), list):
        raise _fail("f94_bundle_invalid")
    if inner["channel"] != channel:
        raise _fail("f94_channel_mismatch")
    expected = {f["path"]: f["sha256"] for f in inner["files"]}
    if set(expected) != set(files):
        raise _fail("f94_bundle_invalid")
    for path, want in expected.items():
        if sha256_hex(files[path]) != want:
            raise _fail("f94_bundle_invalid")
    # manifest 以包内原样字节为准（＝原 pin），摘要与源安装相等；
    # bundle 内文件即按挂载路径携带（pack 产物），mount＝恒等映射
    return {"manifest": json.loads(inner_raw.decode("utf-8")),
            "files": files,
            "mount": {p: p for p in files},
            "bundle_sha256": declared_sha}


def _read_source_zip(source: dict, channel: str) -> dict:
    if channel != "public":
        raise _fail("f95_zip_channel_public_only")
    path_raw = source.get("path")
    declared_sha = source.get("sha256")
    url = source.get("url")
    if not isinstance(path_raw, str) or not path_raw \
            or not isinstance(declared_sha, str) \
            or not re.match(r"^[0-9a-f]{64}$", declared_sha) \
            or not isinstance(url, str) or not url:
        raise _fail("f95_zip_source_required")
    zip_path = Path(path_raw)
    if not zip_path.is_file():
        raise _fail("f95_zip_unreadable")
    data = zip_path.read_bytes()
    actual = sha256_hex(data)
    if actual != declared_sha:
        raise _fail("f95_zip_source_mismatch")
    zin = open_zip_bytes(data)
    with zin:
        pre = precheck_zip(zin)
    files = pre["files"]
    stem = zip_path.stem
    catalog_id = stem if _safe_segment(stem) else "skills"
    try:
        derived = derive_manifest_from_files(
            files, catalog_id=catalog_id, channel="public", kind="zip",
            zip_sha256=actual)
    except SkillCatalogError as exc:
        if str(exc) == "f94_catalog_empty":
            raise _fail("f95_zip_format_incompatible") from None
        raise
    derived["files"] = files
    derived["precheck"] = pre
    return derived


SOURCE_KINDS = {
    "git_local": _read_source_git,
    "bundle": _read_source_bundle,
    "zip": _read_source_zip,
}


def inspect_zip(zip_path: str, declared_sha) -> dict:
    """F95 预检只读面：不落状态。来源 sha 必须声明并核对。"""
    if not isinstance(zip_path, str) or not zip_path \
            or not isinstance(declared_sha, str) \
            or not re.match(r"^[0-9a-f]{64}$", declared_sha):
        raise _fail("f95_zip_source_required")
    zip_file = Path(zip_path)
    if not zip_file.is_file():
        raise _fail("f95_zip_unreadable")
    data = zip_file.read_bytes()
    actual = sha256_hex(data)
    if actual != declared_sha:
        raise _fail("f95_zip_source_mismatch")
    zin = open_zip_bytes(data)
    with zin:
        pre = precheck_zip(zin)
    files = pre["files"]
    stem = zip_file.stem
    catalog_id = stem if _safe_segment(stem) else "skills"
    try:
        derived = derive_manifest_from_files(
            files, catalog_id=catalog_id,
            channel="public", kind="zip", zip_sha256=actual)
        skill_list = derived["manifest"]["skills"]
    except SkillCatalogError as exc:
        if str(exc) == "f94_catalog_empty":
            raise _fail("f95_zip_format_incompatible") from None
        raise
    return {"status": "OK", "zip_sha256": actual, "entry_count": len(files),
            "total_bytes": pre["total_bytes"],
            "skills": skill_list, "scripts": pre["scripts"],
            "executable": pre["executable"],
            "executed": [],  # 预检/安装永不执行 zip 内容
            "violations": []}


# --------------------------------------------------------------------------
# 状态根（store 内容寻址 / skills 活动面 / active.json / history.jsonl）
# --------------------------------------------------------------------------

def _channel_dir(state_root: Path, channel: str) -> Path:
    if channel not in CHANNELS:
        raise _fail("f94_channel_invalid")
    return Path(state_root) / STATE_SUBDIR / channel


def _load_json(path: Path):
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _atomic_write(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _write_tree(root: Path, files: dict):
    for rel in sorted(files):
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(files[rel])


def _materialize(store_dir: Path, files: dict, channel_dir: Path, seq: int):
    """skills/ 活动面全量替换（先建 tmp，再换位；旧面留 trash 随后删）。"""
    skills = channel_dir / "skills"
    tmp = channel_dir / f"skills.tmp-{seq:04d}"
    if tmp.exists():
        _rmtree(tmp)
    _write_tree(tmp, files)
    trash = None
    if skills.exists():
        trash = channel_dir / f"skills.trash-{seq:04d}"
        if trash.exists():
            _rmtree(trash)
        os.rename(skills, trash)
    os.rename(tmp, skills)
    if trash is not None:
        _rmtree(trash)


def _rmtree(path: Path):
    for child in sorted(path.rglob("*"), reverse=True):
        if child.is_dir():
            child.rmdir()
        else:
            child.chmod(stat.S_IWRITE)
            child.unlink()
    path.rmdir()


def _history_path(channel_dir: Path) -> Path:
    return channel_dir / "history.jsonl"


def _history_entries(channel_dir: Path) -> list:
    path = _history_path(channel_dir)
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out


def _append_history(channel_dir: Path, entry: dict):
    with _history_path(channel_dir).open("a", encoding="utf-8") as fh:
        fh.write(canonical_bytes(entry).decode("utf-8") + "\n")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _install_from_manifest(state_root: Path, channel: str, manifest: dict,
                           files: dict, mount: dict, kind: str,
                           extra_receipt: dict) -> dict:
    channel_dir = _channel_dir(state_root, channel)
    digest = sha256_hex(canonical_bytes(manifest))
    # store/materialize 一律按 manifest 挂载布局（mount: 挂载路径→源路径）
    tree = {rel: files[src] for rel, src in mount.items()}
    store = channel_dir / "store" / digest
    marker = store / "manifest.json"
    if marker.is_file():
        # 内容寻址命中：树必须与 manifest 逐文件全等（漂移＝被篡改，typed 拒）
        for rel, want in ((f["path"], f["sha256"])
                          for f in manifest["files"]):
            blob = store / rel
            if not blob.is_file() or sha256_hex(blob.read_bytes()) != want:
                raise _fail("f94_store_corrupt")
    else:
        _write_tree(store, tree)
        _atomic_write(marker, canonical_bytes(manifest))
    history = _history_entries(channel_dir)
    seq = len(history) + 1
    install_id = f"inst-{seq:04d}"
    receipt = {
        "install_id": install_id,
        "install_seq": seq,
        "action": "install",
        "kind": kind,
        "channel": channel,
        "catalog_id": manifest["catalog_id"],
        "manifest_sha256": digest,
        "commit": manifest.get("commit"),
        "file_count": len(manifest["files"]),
        "total_bytes": sum(f["bytes"] for f in manifest["files"]),
        "skills": manifest["skills"],
        "installed_at": _now(),
        **extra_receipt,
    }
    _materialize(store, tree, channel_dir, seq)
    _append_history(channel_dir, receipt)
    _atomic_write(channel_dir / "active.json", canonical_bytes(receipt))
    return receipt


# --------------------------------------------------------------------------
# 公开方法面（legal_entry 冻结组 SKILL_CATALOG_METHODS / SKILL_ZIP_METHODS）
# --------------------------------------------------------------------------

def catalog_install(args: dict, config: dict) -> dict:
    state_root = config.get("skill_catalog_state_root")
    if not state_root:
        raise _fail("f94_state_root_not_configured")
    channel = args.get("channel")
    if channel not in CHANNELS:
        raise _fail("f94_channel_invalid")
    source = args.get("source")
    if not isinstance(source, dict) or source.get("kind") not in SOURCE_KINDS:
        raise _fail("f94_source_invalid")
    kind = source["kind"]
    if kind == "zip" and channel != "public":
        raise _fail("f95_zip_channel_public_only")
    expected = args.get("expected_manifest_sha256")
    if expected is not None and (not isinstance(expected, str)
                                 or not re.match(r"^[0-9a-f]{64}$", expected)):
        raise _fail("f94_source_invalid")
    loaded = SOURCE_KINDS[kind](source, channel)
    manifest = loaded["manifest"]
    manifest.pop("source_declared_channel", None)
    digest = sha256_hex(canonical_bytes(manifest))
    if expected is not None and expected != digest:
        raise _fail("f94_manifest_mismatch")
    extra = {}
    if kind == "bundle":
        extra["bundle_sha256"] = loaded["bundle_sha256"]
    if kind == "zip":
        extra["zip_source_url"] = source.get("url")
        extra["zip_sha256"] = manifest.get("zip_sha256")
        extra["scripts"] = loaded["precheck"]["scripts"]
    receipt = _install_from_manifest(Path(state_root), channel, manifest,
                                     loaded["files"], loaded["mount"], kind,
                                     extra)
    return {"status": "INSTALLED", **receipt}


def catalog_rollback(args: dict, config: dict) -> dict:
    state_root = config.get("skill_catalog_state_root")
    if not state_root:
        raise _fail("f94_state_root_not_configured")
    channel = args.get("channel")
    if channel not in CHANNELS:
        raise _fail("f94_channel_invalid")
    channel_dir = _channel_dir(Path(state_root), channel)
    history = _history_entries(channel_dir)
    active = _load_json(channel_dir / "active.json")
    if not history or not active:
        raise _fail("f94_active_missing")
    installs = [h for h in history if h.get("action") == "install"]
    # 回溯位置＝活动面所反映的 install（回滚条目之后沿用其 restored 位置，
    # 不乒乓）：A→B→回滚(A)→再回滚＝无前可回，typed 拒。
    position = active["install_seq"] if active.get("action") == "install" \
        else active.get("restored_install_seq")
    previous = [h for h in installs if h["install_seq"] < position]
    if not previous:
        raise _fail("f94_rollback_no_previous")
    target = max(previous, key=lambda h: h["install_seq"])
    digest = target["manifest_sha256"]
    store = channel_dir / "store" / digest
    marker = store / "manifest.json"
    manifest = _load_json(marker) if marker.is_file() else None
    if manifest is None:
        raise _fail("f94_store_corrupt")
    files = {f["path"]: (store / f["path"]).read_bytes()
             for f in manifest["files"]}
    seq = len(history) + 1
    receipt = {
        "install_id": f"inst-{seq:04d}",
        "install_seq": seq,
        "action": "rollback",
        "kind": target["kind"],
        "channel": channel,
        "catalog_id": target["catalog_id"],
        "manifest_sha256": digest,
        "commit": target.get("commit"),
        "restored_install_id": target["install_id"],
        "restored_install_seq": target["install_seq"],
        "file_count": target["file_count"],
        "total_bytes": target["total_bytes"],
        "skills": target["skills"],
        "installed_at": _now(),
    }
    _materialize(store, files, channel_dir, seq)
    _append_history(channel_dir, receipt)
    _atomic_write(channel_dir / "active.json", canonical_bytes(receipt))
    return {"status": "ROLLED_BACK", **receipt}


def catalog_verify(args: dict, config: dict) -> dict:
    state_root = config.get("skill_catalog_state_root")
    if not state_root:
        raise _fail("f94_state_root_not_configured")
    channel = args.get("channel")
    if channel not in CHANNELS:
        raise _fail("f94_channel_invalid")
    channel_dir = _channel_dir(Path(state_root), channel)
    active = _load_json(channel_dir / "active.json")
    if not active:
        raise _fail("f94_active_missing")
    manifest = _load_json(channel_dir / "store" / active["manifest_sha256"]
                          / "manifest.json")
    if manifest is None:
        raise _fail("f94_store_corrupt")
    skills_dir = channel_dir / "skills"
    actual: dict = {}
    if skills_dir.is_dir():
        for path in sorted(skills_dir.rglob("*")):
            if path.is_file():
                rel = path.relative_to(skills_dir).as_posix()
                actual[rel] = sha256_hex(path.read_bytes())
    expected = {f["path"]: f["sha256"] for f in manifest["files"]}
    changed = sorted(p for p in expected
                     if p in actual and actual[p] != expected[p])
    missing = sorted(p for p in expected if p not in actual)
    extra = sorted(p for p in actual if p not in expected)
    ok = not (changed or missing or extra)
    return {"status": "OK" if ok else "TAMPERED", "channel": channel,
            "install_id": active["install_id"],
            "manifest_sha256": active["manifest_sha256"],
            "ok_count": len(expected) - len(changed) - len(missing),
            "changed": changed, "missing": missing, "extra": extra}


def runtime_projection(name: str, content: str, directory: str,
                       files: list) -> str:
    """upstream packages/core/src/skill.ts toModelOutput 逐字节同形。"""
    return "\n".join([
        f'<skill_content name="{name}">',
        f"# Skill: {name}",
        "",
        content.strip(),
        "",
        f"Base directory for this skill: {directory}",
        "Relative paths in this skill (e.g., scripts/, reference/) are "
        "relative to this base directory.",
        "Note: file list is sampled.",
        "",
        "<skill_files>",
        *(f"<file>{f}</file>" for f in files),
        "</skill_files>",
        "</skill_content>",
    ])


def catalog_read(args: dict, config: dict) -> dict:
    state_root = config.get("skill_catalog_state_root")
    if not state_root:
        raise _fail("f94_state_root_not_configured")
    channel = args.get("channel")
    if channel not in CHANNELS:
        raise _fail("f94_channel_invalid")
    channel_dir = _channel_dir(Path(state_root), channel)
    active = _load_json(channel_dir / "active.json")
    history = _history_entries(channel_dir)
    result = {
        "channel": channel,
        "active": active,
        "history_count": len(history),
        "skills": active["skills"] if active else [],
    }
    skill_id = args.get("skill_id")
    if skill_id is not None:
        if not isinstance(skill_id, str) or not skill_id:
            raise _fail("f94_skill_id_invalid")
        if not active:
            raise _fail("f94_active_missing")
        match = next((s for s in active["skills"] if s["id"] == skill_id),
                     None)
        if match is None:
            raise _fail("f94_skill_not_installed")
        manifest = _load_json(channel_dir / "store"
                              / active["manifest_sha256"] / "manifest.json")
        if manifest is None:
            raise _fail("f94_store_corrupt")
        paths = {f["path"] for f in manifest["files"]}
        skills_dir = channel_dir / "skills"
        if skill_id + "/SKILL.md" in paths:      # 目录技能
            skill_dir = skills_dir / skill_id
            entry_rel = skill_id + "/SKILL.md"
            raw = (skill_dir / "SKILL.md").read_bytes()
        elif skill_id + ".md" in paths:          # 根级单文件技能
            skill_dir = skills_dir
            entry_rel = skill_id + ".md"
            raw = (skills_dir / (skill_id + ".md")).read_bytes()
        else:
            raise _fail("f94_store_corrupt")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise _fail("f94_store_corrupt") from None
        parsed = parse_skill_markdown(text)
        if parsed is None:
            raise _fail("f94_store_corrupt")
        others = sorted(
            f["path"] for f in manifest["files"]
            if f["path"] != entry_rel
            and f["path"].startswith(skill_id + "/"))
        files_abs = [str((skills_dir / p).resolve()) for p in others][:10]
        result["skill"] = match
        result["directory"] = str(skill_dir.resolve())
        result["projection"] = runtime_projection(
            match["name"], parsed["content"], str(skill_dir.resolve()),
            files_abs)
    return result


def catalog_pack(args: dict, config: dict) -> dict:
    """F94 桌面离线捆绑：活动安装 → 确定性 bundle zip（manifest.json＋文
    件，定时间戳，条目排序）。同状态重复 pack 逐字节同产物（sha 相等即
    幂等复用）。"""
    state_root = config.get("skill_catalog_state_root")
    if not state_root:
        raise _fail("f94_state_root_not_configured")
    channel = args.get("channel")
    if channel not in CHANNELS:
        raise _fail("f94_channel_invalid")
    channel_dir = _channel_dir(Path(state_root), channel)
    active = _load_json(channel_dir / "active.json")
    if not active:
        raise _fail("f94_active_missing")
    digest = active["manifest_sha256"]
    store = channel_dir / "store" / digest
    manifest = _load_json(store / "manifest.json")
    if manifest is None:
        raise _fail("f94_store_corrupt")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        entry = zipfile.ZipInfo(BUNDLE_MANIFEST, date_time=(1980, 1, 1, 0, 0, 0))
        entry.external_attr = 0o600 << 16
        zf.writestr(entry, canonical_bytes(manifest))
        for f in sorted(manifest["files"], key=lambda x: x["path"]):
            blob = (store / f["path"]).read_bytes()
            if sha256_hex(blob) != f["sha256"]:
                raise _fail("f94_store_corrupt")
            zi = zipfile.ZipInfo(f["path"], date_time=(1980, 1, 1, 0, 0, 0))
            zi.external_attr = 0o600 << 16
            zf.writestr(zi, blob)
    data = buf.getvalue()
    bundles = channel_dir / "bundles"
    bundles.mkdir(parents=True, exist_ok=True)
    out = bundles / (digest + ".zip")
    if not out.is_file():
        _atomic_write(out, data)
    written = out.read_bytes()
    if sha256_hex(written) != sha256_hex(data):
        raise _fail("f94_store_corrupt")
    return {"status": "PACKED", "channel": channel, "file": out.name,
            "sha256": sha256_hex(written), "bytes": len(written),
            "manifest_sha256": digest, "catalog_id": manifest["catalog_id"],
            "commit": manifest.get("commit")}


def catalog_call(method: str, args: dict, config: dict) -> dict:
    if not isinstance(args, dict):
        raise _fail("f94_params_invalid")
    if method == "skill.catalog.install":
        return catalog_install(args, config)
    if method == "skill.catalog.rollback":
        return catalog_rollback(args, config)
    if method == "skill.catalog.verify":
        return catalog_verify(args, config)
    if method == "skill.catalog.read":
        return catalog_read(args, config)
    if method == "skill.catalog.pack":
        return catalog_pack(args, config)
    if method == "skill.zip.install":
        # cat-xierluo 社区 zip 直装：zip_path/sha256/url 顶层形参与
        # skill.zip.inspect 一致；渠道恒 public（f95_zip_channel_public_only）
        source = {"kind": "zip", "path": args.get("zip_path"),
                  "sha256": args.get("sha256"), "url": args.get("url")}
        return catalog_install({"channel": "public", "source": source},
                               config)
    if method == "skill.zip.inspect":
        return inspect_zip(args.get("zip_path"), args.get("sha256"))
    raise _fail("f94_method_unknown")
