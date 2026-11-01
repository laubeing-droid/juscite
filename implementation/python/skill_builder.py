# -*- coding: utf-8 -*-
"""F101 agent/skill-builder（聊天造自定义件）候选/预检/采用合同面（W5-U10）。

义务 06:V7-101（17 卡；F101-desktop/F101-selfhost 双实例；owner=product；
UI_HOST_OR_NEW_PRODUCT；phase B5；source_rationale「生态成熟后的元层」）
验收向量（逐字）：「自建skill/agent生成候选，经预检和用户采用再执行，无
自动扩权」。17 卡实施序：「优先保原生能力→仅选型必要差异→新增产品合同/
权限/持久化→原生UI触发→真实回读；不创第二Agent loop，非选型历史子要求
保持」。

落点（本面＝候选/预检/采用合同面；不建运行时新执行通道——17 卡红线
「不创第二 Agent loop」；「生态成熟后的元层」v2 元层只做合同面）：

- skill.builder.propose（候选生成对话轮入账）：聊天对话轮（dialog.turns，
  角色闭集 user/assistant，首轮必须 user——模型自发造件＝
  f101_origin_user_missing typed 拒）＋生成的候选文档（document，合成候
  选注入＝结构断言全程离线可跑；真实模型轮次为对话层的增强路径，不是
  本面的门，本面零模型零网络）。kind 闭集 {skill, agent}：
    skill  → 恰一文件 SKILL.md（staged 于 candidates/<id>/SKILL.md；
             id 规则同上游原生通道＝父目录名）；
    agent  → 单段安全文件名 <name>.md（frontmatter 键闭集镜像 oc28
             packages/schema/src/config/agent.ts Info：description/mode/
             permissions 等；正文＝system 声明）。
  候选 id＝「<kind>-<文档sha256 前 8>」内容寻址（确定性、跨 profile 可
  比、幂等重提案不重复）。留痕零内容：对话原文绝不落盘（只入
  dialog_sha256/turn_count/角色序列）。
- skill.builder.precheck（预检）：候选必须先预检才能被采用——
    skill  → 既有 F96 执行合同守门真校验（legal_entry 冻结面
             skill.gate.validate 同一实现，零第二合同权威；候选无
             lvyin-skill-contract 合同＝永不可被门禁执行，预检即具名拒
             f101_precheck_contract_failed:<f96 码>）；
    agent  → 结构闭集复检＋无自动扩权闸：自建 agent 候选 permissions
             只准收窄（effect 闭集 ask/deny），任何 allow 规则＝
             f101_agent_permission_allow typed 拒（权限扩张不是候选可自
             授的字段；权限求值权威在上游 permission 面与 policies
             veto——只能收紧不能放行，本面同构）。
  预检 PASS 回执钉定候选文档 sha256（预检/采用后字节变＝
  f101_candidate_modified——复用 F96 STALE「旧核不覆盖新内容」语义：预
  检回执绝不覆盖新字节，必须重新预检再采用）。
- skill.builder.adopt（用户采用）：adoption.by 必须逐字 "user"——对话/
  模型通道自采用＝f101_adopt_requires_user typed 拒（无自动扩权红线：
  候选态永不直执行，采用是用户独占动作）。未预检＝f101_precheck_required；
  预检后字节变＝f101_candidate_modified。采用效果：
    skill  → 经既有 F94/F95 公开分发链真安装（确定性 zip →
             skill.zip.install，渠道恒 public；零第二目录权威；安装回
             执落 record）；
    agent  → 声明文件物化到 adopted/agents/<name>.md（产品持久化合同
             面＝17 卡「新增产品合同/权限/持久化」；本面零运行时零
             loop，宿主消费属 UI/host 接线后续面）。
- skill.builder.read（真实回读）：候选记录列表/单条（逐条 digest 复核，
  篡改 typed 拒 f101_record_digest_mismatch）。

红线（结构性）：本面零执行——无 run/execute 方法；既有门禁执行/计算/实
例化/路由各面的方法字面量在本模块全文本零出现（wiring/recon 逐字钉定）；
零进程零网络（子进程/套接字/URL 库零导入）。候选态不可达任何执行面：路
由唯一候选源＝F94 目录活动面（F98），候选未安装＝路由不可达（f98_explicit_
unknown 同频旁证）；执行唯一通道＝F96 门禁对已安装技能。全程零模型零网
络零随机零时钟（记录无 wall time，跨 profile 可复跑对账）；金额不涉及；
无 DAG 无编排。

fail-closed：typed error（SkillBuilderError 的 str 只有 f101_* 错误码，
绝不携对话/文档内容）；未配置 skill_builder_state_root＝typed 拒；未配
置 skill_catalog_state_root（F94 同域键，skill 采用径分发链所需）＝
F94 面 typed 拒透传；F96/F94/F95 面 typed 码归一 f101_*:<原码> 透传。
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from pathlib import Path

from bridge_errors import NotConnected
from skill_semantics import read_skill, SkillSemanticsError

SCHEMA = "juscite-f101-skill-builder/1"

# legal_entry 冻结方法组（唯一入口；组外方法绝不落到本面）。
SKILL_BUILDER_METHODS = frozenset({
    "skill.builder.propose",
    "skill.builder.precheck",
    "skill.builder.adopt",
    "skill.builder.read",
})

# 既有公开面（本面仅有的桥出调用；零执行面——AST/字面量钉定）。
M_GATE_VALIDATE = "skill.gate.validate"   # F96 合同校验（预检复用）
M_ZIP_INSTALL = "skill.zip.install"       # F95 分发链直装（采用复用）

KINDS = frozenset({"skill", "agent"})

ROLES = frozenset({"user", "assistant"})

SKILL_FILENAME = "SKILL.md"

STATUS_STAGED = "staged"
STATUS_ADOPTED = "adopted"

RECORDS_FILENAME = "candidates.jsonl"

# agent 候选 frontmatter 键闭集（镜像 oc28 ConfigAgent.Info 字段＋原生
# agentKeys 的 variant；本面只声明合同，不解析原生 legacy 迁移面）。
AGENT_FM_KEYS = frozenset({
    "description", "mode", "model", "request", "system", "hidden", "color",
    "steps", "disabled", "permissions",
})
AGENT_MODES = frozenset({"subagent", "primary", "all"})
AGENT_EFFECTS = frozenset({"allow", "ask", "deny"})
_PERMISSION_RULE_FIELDS = frozenset({"action", "resource", "effect"})
_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

_ID_SAFE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_RESERVED_AGENT_FILENAME = SKILL_FILENAME

FM_LINE_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*):[ \t]*(.*)$")
FM_OPEN_RE = re.compile(r"\A---[ \t]*\r?\n")
FM_CLOSE_RE = re.compile(r"^---[ \t]*\r?\n?", re.M)


class SkillBuilderError(ValueError):
    """Typed F101 face failure; str() is a code, never dialog/document content."""


def _fail(code: str) -> SkillBuilderError:
    return SkillBuilderError(code)


def _require(args: dict, fields: frozenset, code: str) -> None:
    """DTO 闭集校验：必带字段缺一即拒、闭集外字段即拒（无旁路）。"""
    if not isinstance(args, dict) or set(args) != set(fields):
        raise NotConnected(code)


# ---------------------------------------------------------------------- #
# 状态根与留痕（记录零对话/文档原文；逐条 digest 可复核）
# ---------------------------------------------------------------------- #


def _state_root(config: dict) -> Path:
    root = config.get("skill_builder_state_root")
    if not isinstance(root, str) or not root:
        raise _fail("f101_state_root_not_configured")
    return Path(root)


def _canonical(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))


def _digest_of(body: dict) -> str:
    return hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()


def _records_path(root: Path) -> Path:
    return root / RECORDS_FILENAME


def _load_records(root: Path) -> "list[dict]":
    path = _records_path(root)
    if not path.is_file():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            raise _fail("f101_record_invalid") from None
        _verify_record(record)
        records.append(record)
    return records


def _verify_record(record: dict) -> None:
    if not isinstance(record, dict) or record.get("schema") != SCHEMA \
            or not isinstance(record.get("digest"), str):
        raise _fail("f101_record_invalid")
    body = {k: v for k, v in record.items() if k != "digest"}
    if _digest_of(body) != record["digest"]:
        raise _fail("f101_record_digest_mismatch:" + str(
            record.get("candidate_id")))


def _save_records(root: Path, records: "list[dict]") -> None:
    root.mkdir(parents=True, exist_ok=True)
    lines = [_canonical(record) for record in records]
    _records_path(root).write_text(
        "".join(line + "\n" for line in lines), encoding="utf-8")


def _upsert_record(root: Path, candidate_id: str, mutate) -> dict:
    records = _load_records(root)
    target = None
    for record in records:
        if record.get("candidate_id") == candidate_id:
            target = record
            break
    if target is None:
        raise _fail("f101_candidate_missing:" + candidate_id)
    mutate(target)
    body = {k: v for k, v in target.items() if k != "digest"}
    target["digest"] = _digest_of(body)
    _save_records(root, records)
    return target


def _record_of(root: Path, candidate_id) -> dict:
    if not isinstance(candidate_id, str) or not candidate_id:
        raise _fail("f101_candidate_id_invalid")
    for record in _load_records(root):
        if record["candidate_id"] == candidate_id:
            return record
    raise _fail("f101_candidate_missing:" + candidate_id)


# ---------------------------------------------------------------------- #
# 候选文档结构（确定性解析；零模型）
# ---------------------------------------------------------------------- #


def _doc_fields(document, kind: str) -> "tuple[str, str]":
    if not isinstance(document, dict) \
            or set(document) != {"filename", "text"}:
        raise _fail("f101_document_invalid")
    filename = document.get("filename")
    text = document.get("text")
    if not isinstance(filename, str) or not isinstance(text, str) or not text:
        raise _fail("f101_document_invalid")
    if kind == "skill":
        if filename != SKILL_FILENAME:
            raise _fail("f101_document_filename_invalid:" + SKILL_FILENAME)
    else:
        if filename == _RESERVED_AGENT_FILENAME or not filename.endswith(
                ".md") or not _ID_SAFE_RE.match(filename[:-3]):
            raise _fail("f101_document_filename_invalid")
    return filename, text


def _agent_frontmatter_of(text: str) -> dict:
    """agent 候选 frontmatter 闭集解析（平键＋permissions 单行 JSON 流列
    ——JSON 是合法 YAML flow，原生解析器同收；本面零 YAML 依赖）。"""
    if FM_OPEN_RE.match(text) is None:
        raise _fail("f101_agent_frontmatter_invalid")
    closed = FM_CLOSE_RE.search(text, 4)
    if closed is None:
        raise _fail("f101_agent_frontmatter_invalid")
    header = text[4:closed.start()]
    entries = {}
    for line in header.splitlines():
        pair = FM_LINE_RE.match(line.strip())
        if pair is None:
            raise _fail("f101_agent_frontmatter_invalid")
        key, raw = pair.group(1), pair.group(2).strip()
        if key in entries:
            raise _fail("f101_agent_frontmatter_invalid")
        entries[key] = raw
    unknown = sorted(set(entries) - AGENT_FM_KEYS)
    if unknown:
        raise _fail("f101_agent_frontmatter_key_unknown:" + ",".join(unknown))
    if not entries.get("description"):
        raise _fail("f101_document_description_missing")
    data = {"description": entries["description"]}
    if "mode" in entries:
        if entries["mode"] not in AGENT_MODES:
            raise _fail("f101_agent_mode_unknown:" + entries["mode"])
        data["mode"] = entries["mode"]
    if "steps" in entries:
        if not entries["steps"].isdigit() or int(entries["steps"]) < 1:
            raise _fail("f101_agent_steps_invalid")
        data["steps"] = int(entries["steps"])
    if "color" in entries:
        if not _COLOR_RE.match(entries["color"]):
            raise _fail("f101_agent_color_invalid")
        data["color"] = entries["color"]
    if "permissions" in entries:
        try:
            rules = json.loads(entries["permissions"])
        except json.JSONDecodeError:
            raise _fail("f101_agent_permissions_invalid") from None
        if not isinstance(rules, list):
            raise _fail("f101_agent_permissions_invalid")
        parsed = []
        for rule in rules:
            if not isinstance(rule, dict) \
                    or set(rule) != _PERMISSION_RULE_FIELDS \
                    or not isinstance(rule["action"], str) or not rule["action"] \
                    or not isinstance(rule["resource"], str) or not rule["resource"] \
                    or rule["effect"] not in AGENT_EFFECTS:
                raise _fail("f101_agent_permissions_invalid")
            parsed.append({"action": rule["action"],
                           "resource": rule["resource"],
                           "effect": rule["effect"]})
        data["permissions"] = parsed
    body = text[closed.end():]
    if not body.strip():
        raise _fail("f101_agent_body_missing")
    return data


def _dialog_of(dialog) -> dict:
    """对话轮闭集：首轮必须 user（候选由用户发起；模型自发造件具名拒）。
    留痕零内容：只取 sha/轮数/角色序列。"""
    if not isinstance(dialog, dict) or set(dialog) != {"turns"}:
        raise _fail("f101_dialog_invalid")
    turns = dialog.get("turns")
    if not isinstance(turns, list) or not turns:
        raise _fail("f101_dialog_invalid")
    roles = []
    for turn in turns:
        if not isinstance(turn, dict) or set(turn) != {"role", "text"} \
                or turn.get("role") not in ROLES \
                or not isinstance(turn.get("text"), str) or not turn["text"]:
            raise _fail("f101_dialog_invalid")
        roles.append(turn["role"])
    if roles[0] != "user":
        raise _fail("f101_origin_user_missing")
    return {"dialog_sha256": hashlib.sha256(_canonical(dialog).encode(
                "utf-8")).hexdigest(),
            "turn_count": len(turns), "roles": roles}


def _candidate_id(kind: str, doc_bytes: bytes) -> str:
    return "%s-%s" % (kind, hashlib.sha256(doc_bytes).hexdigest()[:8])


def _discard_staged(staged: Path) -> None:
    """解析败清理：删残件＋删空候选目录与空根（不留半程残件）。"""
    staged.unlink(missing_ok=True)
    try:
        staged.parent.rmdir()
        staged.parent.parent.rmdir()  # candidates 根（仅当空时成功）
    except OSError:
        pass


def _stage_paths(root: Path, candidate_id: str, filename: str):
    directory = root / "candidates" / candidate_id
    return directory, directory / filename


# ---------------------------------------------------------------------- #
# propose：候选生成对话轮入账（合成候选注入＝结构断言离线可跑）
# ---------------------------------------------------------------------- #


def builder_propose(args: dict, config: dict) -> dict:
    root = _state_root(config)
    kind = args.get("kind")
    if kind not in KINDS:
        raise _fail("f101_kind_unknown:" + str(kind))
    dialog = _dialog_of(args.get("dialog"))
    filename, text = _doc_fields(args.get("document"), kind)
    doc_bytes = text.encode("utf-8")
    candidate_id = _candidate_id(kind, doc_bytes)
    directory, staged = _stage_paths(root, candidate_id, filename)
    existing = None
    for record in _load_records(root):
        if record["candidate_id"] == candidate_id:
            existing = record
            break
    if existing is not None:
        # 内容寻址幂等：同字节重提案返回既有候选（零重复记录）。
        return {"schema": SCHEMA, "face": "propose", "candidate_id":
                candidate_id, "kind": kind, "status": existing["status"],
                "document_sha256": existing["document_sha256"],
                "staged_path": str(staged), "idempotent": True}
    if kind == "skill":
        staged.parent.mkdir(parents=True, exist_ok=True)
        staged.write_bytes(doc_bytes)
        try:
            parsed = read_skill(str(staged))
        except SkillSemanticsError as exc:
            _discard_staged(staged)  # 解析败＝不留半程残件（含空目录）
            raise _fail("f101_document_parse_failed:" + str(exc)) from None
        if not parsed.get("description"):
            _discard_staged(staged)
            raise _fail("f101_document_description_missing")
        face = {"id": parsed["id"], "name": parsed["name"]}
    else:
        staged.parent.mkdir(parents=True, exist_ok=True)
        staged.write_bytes(doc_bytes)
        try:
            parsed = _agent_frontmatter_of(text)
        except SkillBuilderError:
            _discard_staged(staged)  # 解析败＝不留半程残件（含空目录）
            raise
        face = {"id": filename[:-3], "description": parsed["description"]}
    record = {
        "schema": SCHEMA, "face": "propose", "candidate_id": candidate_id,
        "kind": kind, "filename": filename,
        "document_sha256": hashlib.sha256(doc_bytes).hexdigest(),
        "bytes": len(doc_bytes), "staged_path": str(staged),
        "origin": dialog, "face_summary": face, "status": STATUS_STAGED,
        "precheck": None, "adoption": None,
    }
    record["digest"] = _digest_of(record)
    records = _load_records(root)
    records.append(record)
    _save_records(root, records)
    return {"schema": SCHEMA, "face": "propose", "candidate_id":
            candidate_id, "kind": kind, "status": STATUS_STAGED,
            "document_sha256": record["document_sha256"],
            "staged_path": str(staged), "idempotent": False}


# ---------------------------------------------------------------------- #
# precheck：F96 门禁复用（skill）＋无自动扩权闸（agent）
# ---------------------------------------------------------------------- #


def _bridge_call(method: str, args: dict, config: dict) -> dict:
    """既有公开面分派 seam（默认＝legal_entry.call 同进程径）。"""
    import legal_entry
    return legal_entry.call(method, args, config)


def _precheck_skill(record: dict, config: dict) -> dict:
    """候选 skill 预检＝既有 F96 执行合同守门真校验（零第二合同权威）。
    候选没有可被门禁的合同＝永不执行，预检即具名拒。"""
    outcome = {"ok": True, "result": None, "code": None}
    try:
        outcome["result"] = _bridge_call(M_GATE_VALIDATE, {
            "skill_path": record["staged_path"],
            "skill_id": record["candidate_id"]}, config)
    except NotConnected as exc:
        outcome = {"ok": False, "result": None, "code": str(exc)}
    checks = [{"id": "f96_gate_validate",
               "passed": outcome["ok"],
               "detail": ("contract_sha256=" + (outcome["result"] or {})
                          .get("contractSha256", "")[:16])
               if outcome["ok"] else "f96_failed:" + (outcome["code"] or "")}]
    if not outcome["ok"]:
        raise _fail("f101_precheck_contract_failed:" + (outcome["code"]
                                                        or ""))
    return {"result": "PASS", "checks": checks,
            "document_sha256": record["document_sha256"],
            "contract_sha256": outcome["result"]["contractSha256"],
            "as_of": outcome["result"].get("as_of")}


def _precheck_agent(record: dict, config: dict) -> dict:
    """候选 agent 预检＝结构闭集复检＋无自动扩权闸：permissions 只准收窄
    （ask/deny），allow 规则＝typed 拒（权限扩张不是候选可自授的字段）。
    零运行时零 loop（17 卡红线）。"""
    text = Path(record["staged_path"]).read_text(encoding="utf-8")
    parsed = _agent_frontmatter_of(text)
    allow = [r for r in parsed.get("permissions", [])
             if r["effect"] == "allow"]
    checks = [{"id": "frontmatter_closed_set", "passed": True,
               "detail": "keys_ok"},
              {"id": "no_auto_escalation",
               "passed": not allow,
               "detail": "allow_rules=%d" % len(allow)}]
    if allow:
        raise _fail("f101_agent_permission_allow:%d" % len(allow))
    return {"result": "PASS", "checks": checks,
            "document_sha256": record["document_sha256"],
            "contract_sha256": None, "as_of": None}


def builder_precheck(args: dict, config: dict) -> dict:
    root = _state_root(config)
    record = _record_of(root, args.get("candidate_id"))
    staged = Path(record["staged_path"])
    if not staged.is_file():
        raise _fail("f101_candidate_missing:" + record["candidate_id"])
    doc_bytes = staged.read_bytes()
    if hashlib.sha256(doc_bytes).hexdigest() != record["document_sha256"]:
        raise _fail("f101_candidate_modified:" + record["candidate_id"])
    if record["kind"] == "skill":
        receipt = _precheck_skill(record, config)
    else:
        receipt = _precheck_agent(record, config)

    def _mutate(target: dict):
        target["precheck"] = receipt
        # status 保持 staged：预检不改变候选态，采用才改变。

    target = _upsert_record(root, record["candidate_id"], _mutate)
    return {"schema": SCHEMA, "face": "precheck", "candidate_id":
            target["candidate_id"], "kind": target["kind"],
            "result": receipt["result"], "checks": receipt["checks"],
            "document_sha256": receipt["document_sha256"],
            "contract_sha256": receipt["contract_sha256"],
            "as_of": receipt["as_of"]}


# ---------------------------------------------------------------------- #
# adopt：用户采用（非用户通道具名拒；候选态永不直执行）
# ---------------------------------------------------------------------- #


def _deterministic_zip(entry_name: str, blob: bytes) -> bytes:
    """确定性 zip（定时间戳＋单一条目；同 skill_catalog.pack 先例）。"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        info = zipfile.ZipInfo(entry_name, date_time=(1980, 1, 1, 0, 0, 0))
        info.external_attr = 0o600 << 16
        zf.writestr(info, blob)
    return buf.getvalue()


def builder_adopt(args: dict, config: dict) -> dict:
    root = _state_root(config)
    adoption = args.get("adoption")
    if not isinstance(adoption, dict) or set(adoption) != {"by", "note"} \
            or not isinstance(adoption.get("by"), str) \
            or not isinstance(adoption.get("note"), str):
        raise _fail("f101_adoption_invalid")
    if adoption["by"] != "user":
        # 无自动扩权红线：采用是用户独占动作，对话/模型通道自采用具名拒。
        raise _fail("f101_adopt_requires_user:" + adoption["by"])
    record = _record_of(root, args.get("candidate_id"))
    staged = Path(record["staged_path"])
    if not staged.is_file():
        raise _fail("f101_candidate_missing:" + record["candidate_id"])
    doc_bytes = staged.read_bytes()
    if hashlib.sha256(doc_bytes).hexdigest() != record["document_sha256"]:
        raise _fail("f101_candidate_modified:" + record["candidate_id"])
    precheck = record.get("precheck")
    if not isinstance(precheck, dict) or precheck.get("result") != "PASS":
        raise _fail("f101_precheck_required:" + record["candidate_id"])
    # 预检后字节变＝f101_candidate_modified（F96 STALE「旧核不覆盖新内
    # 容」同构：预检回执绝不覆盖新字节，必须重新预检）。
    if record["kind"] == "skill":
        zip_bytes = _deterministic_zip(
            record["candidate_id"] + "/" + record["filename"], doc_bytes)
        zip_sha = hashlib.sha256(zip_bytes).hexdigest()
        zips = root / "zips"
        zips.mkdir(parents=True, exist_ok=True)
        zip_path = zips / (record["candidate_id"] + ".zip")
        zip_path.write_bytes(zip_bytes)
        try:
            installed = _bridge_call(M_ZIP_INSTALL, {
                "zip_path": str(zip_path), "sha256": zip_sha,
                "url": "skill-builder://candidate/"
                       + record["candidate_id"]}, config)
        except NotConnected as exc:
            raise _fail("f101_bridge_failed:" + str(exc)) from None
        skills = [s.get("id") for s in installed.get("skills") or []]
        if installed.get("status") != "INSTALLED" \
                or record["candidate_id"] not in skills:
            raise _fail("f101_install_receipt_invalid")
        adoption_receipt = {
            "by": "user", "note_sha256": hashlib.sha256(
                adoption["note"].encode("utf-8")).hexdigest(),
            "channel": "skill.zip.install",
            "zip_sha256": zip_sha,
            "install": {"status": installed["status"],
                        "install_id": installed.get("install_id"),
                        "manifest_sha256": installed.get("manifest_sha256"),
                        "skills": sorted(skills)},
        }

        def _mutate(target: dict):
            target["adoption"] = adoption_receipt
            target["status"] = STATUS_ADOPTED

        target = _upsert_record(root, record["candidate_id"], _mutate)
        return {"schema": SCHEMA, "face": "adopt", "candidate_id":
                target["candidate_id"], "kind": target["kind"],
                "status": target["status"], "adoption": adoption_receipt}
    # agent 候选：声明物化到持久化合同面（零运行时零 loop；宿主消费属
    # UI/host 接线后续面）。记录零内容：note 只入 sha。
    adopted_dir = root / "adopted" / "agents"
    adopted_dir.mkdir(parents=True, exist_ok=True)
    artifact = adopted_dir / record["filename"]
    artifact.write_bytes(doc_bytes)
    adoption_receipt = {
        "by": "user", "note_sha256": hashlib.sha256(
            adoption["note"].encode("utf-8")).hexdigest(),
        "channel": "adopted_declaration",
        "artifact": str(artifact),
        "document_sha256": record["document_sha256"],
    }

    def _mutate(target: dict):
        target["adoption"] = adoption_receipt
        target["status"] = STATUS_ADOPTED

    target = _upsert_record(root, record["candidate_id"], _mutate)
    return {"schema": SCHEMA, "face": "adopt", "candidate_id":
            target["candidate_id"], "kind": target["kind"],
            "status": target["status"], "adoption": adoption_receipt}


# ---------------------------------------------------------------------- #
# read：真实回读（UI 只调用/展示）
# ---------------------------------------------------------------------- #


def builder_read(args: dict, config: dict) -> dict:
    root = _state_root(config)
    candidate_id = args.get("candidate_id")
    if candidate_id is None:
        records = _load_records(root)
        return {"schema": SCHEMA, "face": "read", "count": len(records),
                "candidates": [{k: record[k] for k in
                                ("candidate_id", "kind", "filename",
                                 "document_sha256", "status")}
                               for record in records]}
    record = _record_of(root, candidate_id)
    return {"schema": SCHEMA, "face": "read", "count": 1,
            "candidates": [record]}


# ---------------------------------------------------------------------- #
# 入口
# ---------------------------------------------------------------------- #


def builder_call(method: str, args: dict, config: dict) -> dict:
    if not isinstance(args, dict):
        raise NotConnected("f101_params_invalid")
    if method == "skill.builder.propose":
        _require(args, {"kind", "dialog", "document"},
                 "f101_propose_params_invalid")
        return builder_propose(args, config)
    if method == "skill.builder.precheck":
        _require(args, {"candidate_id"}, "f101_precheck_params_invalid")
        return builder_precheck(args, config)
    if method == "skill.builder.adopt":
        _require(args, {"candidate_id", "adoption"},
                 "f101_adopt_params_invalid")
        return builder_adopt(args, config)
    if method == "skill.builder.read":
        _require(args, {"candidate_id"}, "f101_read_params_invalid")
        return builder_read(args, config)
    raise NotConnected("method_not_connected:" + method)
