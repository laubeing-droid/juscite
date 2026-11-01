# -*- coding: utf-8 -*-
"""F99 技能市场双边生态（创作者/审核管线/排行/付费墙）产品面（W5-U09）。

义务 06:V7-99（17 卡 F99；F99-desktop/F99-selfhost 双实例；owner=product；
phase=B5；python_entry_ids=UI_HOST_OR_NEW_PRODUCT「原生 OpenCode UI/host
或发行商业新义务；不要求新增法律 Python 服务，不冒已有业务入口」）：
「创作者/审核/分发/排行流程采用后真生效，恶意包不能入活动目录」。

落点＝独立商业新模块（不冒既有业务入口；UI 仅调用/展示，本面不建 UI）。
全部消费已 VERIFIED 技能链，零第二权威：
- F94 skill_catalog＝分发唯一权威（store 内容寻址＋skills/ 活动面）。
  本面分发产物＝市场目录确定性 bundle（F94 pack 同格式：内嵌 manifest
  .json＋逐文件 sha256），经 F94 bundle 源真安装——渠道恒 public（广场；
  controlled 受控根无市场入口）。
- F95 预检＝包格式唯一权威（路径/权限/来源/预算一票否决；submit 复用
  同一 precheck_zip/derive_manifest_from_files，绝不复制第二实现）。
- F96 skill_gate＝执行合同唯一权威（审核清单要求每技能恰一块
  lvyin-skill-contract 且 validate 过；合同缺失/不过＝具名未过审形态）。
- F27 injection.scan（kind="skill"）＝技能文本注入扫描唯一权威（审核清
  单同频复用；发现只记 family/rule，零内容回显）。

四流（采用后真生效）：
- 创作者（market.submit）：声名 creator＋来源 {zip_path, sha256, url}＋
  price_minor（整数分；0=免费）。zip 字节 sha 全等＋F95 预检＋≥1 可加载
  技能才收件；登记即 submitted——**提交面结构性无批准出口**（不存在任
  何自动过审通道）。
- 审核管线（market.review_decide）：fail-closed——approved 只能走全清单
  （字节完整性复核→脚本零容忍→逐技能 F27 注入扫描→逐技能 F96 合同
  validate）全过才落账；任一违例＝具名 findings（f99_review_* 错误码，
  零内容）且 approved typed 拒。rejected 必带闭集 reason_code。同件重复
  决定幂等返回，异决定/异人冲突具名拒。reviewer/creator 身份＝调用方
  如实声明原样记录（本面绝不冒充真实身份、绝不代签名——沿 F53 author
  纪律：机器动作唯一署名 lvyin-marketplace 只用于分发目录工件，决定必
  须有可解析的真实引用）。
- 分发（market.adopt）：**真实决定引用**（decision_ref.review_id 必须
  解析到本账 approved 审核行且绑定同一 submission/同一 zip sha——缺失/
  错绑/未过审一律 typed 拒）。通过后：市场目录树＝按 adopt 事件序对已
  采用提交包重放挂载（同挂载路径后到覆盖＝同 id 技能内容寻址升级），
  重建确定性 bundle 经 F94 bundle 源真安装——活动面 skills/ 真实落盘，
  skill.catalog.verify/read 即时可证。同一 zip sha 重复采用＝幂等返回
  不重复计数。付费技能未经合成购买记录＝f99_paywall_required。
- 排行（market.rankings）：**本地真实采用事件派生**（adopt 事件逐技能
  计数，(-count,id) 确定性排序）；服务面如实标注 synthetic_local——真
  实商业排行服务随 v2 商业化补（§6.1 裁决#13-19）。
- 付费墙（market.purchase / market.entitlement）：**合成服务面**（裁决
  #13-19 商业服务端合成先行，真实支付轨道 v2 补）：购买记录原样标注
  service_surface=synthetic，金额一律整数分（禁浮点——float/bool 具名
  拒；购买价必须与提交声名价全等），绝不发生真实扣款。

账本：events.jsonl 单一 append-only 事件账（review/adopt/purchase；seq
单调＋逐行 digest 复核，篡改 typed 拒 f99_ledger_digest_mismatch）；提
交件 submissions/<id>/{package.zip,submission.json}＝审核队列工件（非
活动目录；市场目录树永远从这些真实字节重放，件失/字节变＝响亮拒不静
默跳过）。market.list＝审计投影。

fail-closed：typed error（SkillMarketplaceError 的 str 只有 f99_* 前缀
错误码，绝不携材料内容；F94/F95 码以 f99_submit_failed:/f99_catalog_
failed: 前缀透传）。无模型、无网络、无随机（导入闭集无 socket/urllib/
subprocess；bundle 定时间戳；事件序号确定性）。金额整数分；%APPDATA%
零触碰（状态根由 config 注入）。config：skill_marketplace_state_root
（本面）＋skill_catalog_state_root（F94 同域键，adopt 安装目标，缺失
f99_catalog_root_not_configured）。
"""
from __future__ import annotations

import io
import json
import os
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from injection_defense import scan_text
from skill_catalog import (SkillCatalogError, canonical_bytes,
                           catalog_call, derive_manifest_from_files,
                           open_zip_bytes, precheck_zip, sha256_hex)
from skill_gate import SkillGateError, validate_skill
from skill_semantics import SkillSemanticsError

SCHEMA = "juscite-f99-skill-marketplace/1"
STATE_SUBDIR = "skill-marketplace"
MARKET_CATALOG_ID = "lvyin-marketplace"

# legal_entry 冻结方法组（唯一入口；组外方法绝不落到本面）。
SKILL_MARKETPLACE_METHODS = frozenset({
    "market.submit",
    "market.review_decide",
    "market.adopt",
    "market.rankings",
    "market.purchase",
    "market.entitlement",
    "market.list",
})

REVIEW_DECISIONS = ("approved", "rejected")
# rejected 决定闭集理由（approved 无需 reason——清单本身即理由）。
REJECT_REASONS = ("policy_duplicate", "policy_scope", "creator_withdraw",
                  "checklist_findings")

_EVENTS_FILE = "events.jsonl"
_SUBMISSIONS_DIR = "submissions"
_BUNDLE_DIR = "bundles"
_HEX = "0123456789abcdef"
_SUBMISSION_FIELDS = frozenset(
    {"creator", "zip_path", "sha256", "url", "price_minor"})
_REVIEW_FIELDS = frozenset(
    {"submission_id", "reviewer", "decision", "reason_code"})
_ADOPT_FIELDS = frozenset({"submission_id", "decision_ref"})
_DECISION_REF_FIELDS = frozenset({"review_id"})
_PURCHASE_FIELDS = frozenset({"submission_id", "buyer", "price_minor"})
_ENTITLEMENT_FIELDS = frozenset({"submission_id"})
_LIST_FIELDS = frozenset({"submission_id"})
_RANKINGS_FIELDS: frozenset = frozenset()


class SkillMarketplaceError(ValueError):
    """Typed F99 face failure; str() is a code, never material content."""


def _fail(code: str) -> SkillMarketplaceError:
    return SkillMarketplaceError(code)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _text(value, code: str) -> str:
    if not isinstance(value, str) or not value:
        raise _fail(code)
    return value


def _closed_args(args, fields: frozenset, code: str) -> None:
    if not isinstance(args, dict) or set(args) != set(fields):
        raise _fail(code)


def _price(value, code: str) -> int:
    """金额一律整数分：float/bool/负数具名拒（禁浮点，禁凭空金额）。"""
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise _fail(code)
    return value


def _is_sha256(value) -> bool:
    return isinstance(value, str) and len(value) == 64 \
        and all(c in _HEX for c in value)


# --------------------------------------------------------------------------
# 状态根与事件账（append-only＋逐行 digest 复核）
# --------------------------------------------------------------------------

def _market_dir(config: dict) -> Path:
    root = config.get("skill_marketplace_state_root")
    if not isinstance(root, str) or not root:
        raise _fail("f99_state_root_not_configured")
    return Path(root) / STATE_SUBDIR


def _submission_dir(market: Path, submission_id) -> Path:
    if not isinstance(submission_id, str) or not submission_id:
        raise _fail("f99_submission_id_invalid")
    path = market / _SUBMISSIONS_DIR / submission_id
    if path.parent != market / _SUBMISSIONS_DIR \
            or not path.name.startswith("sub-"):
        raise _fail("f99_submission_id_invalid")
    return path


def _read_events(market: Path) -> list:
    path = market / _EVENTS_FILE
    if not path.is_file():
        return []
    records = []
    expect_seq = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except ValueError:
            raise _fail("f99_ledger_corrupt") from None
        if not isinstance(record, dict) or "digest" not in record:
            raise _fail("f99_ledger_corrupt")
        digest = record.pop("digest")
        if sha256_hex(canonical_bytes(record)) != digest:
            raise _fail("f99_ledger_digest_mismatch")
        expect_seq += 1
        if record.get("seq") != expect_seq:
            raise _fail("f99_ledger_seq_broken")
        records.append(record)
    return records


def _append_event(market: Path, kind: str, prefix: str, fields: dict) -> dict:
    events = _read_events(market)
    seq = (events[-1]["seq"] + 1) if events else 1
    record = {"seq": seq, "kind": kind, "id": "%s-%04d" % (prefix, seq),
              **fields}
    record["digest"] = sha256_hex(canonical_bytes(record))
    with (market / _EVENTS_FILE).open("a", encoding="utf-8") as fh:
        fh.write(canonical_bytes(record).decode("utf-8") + "\n")
    return record


def _find_event(events: list, kind: str, event_id: str):
    return next((e for e in events
                 if e["kind"] == kind and e["id"] == event_id), None)


# --------------------------------------------------------------------------
# 提交件读取（字节完整性复核＝审核与采用前的重验锚）
# --------------------------------------------------------------------------

def _load_submission(market: Path, submission_id) -> dict:
    path = _submission_dir(market, submission_id)
    record = path / "submission.json"
    package = path / "package.zip"
    if not record.is_file() or not package.is_file():
        raise _fail("f99_submission_not_found")
    data = json.loads(record.read_text(encoding="utf-8"))
    if sha256_hex(package.read_bytes()) != data.get("zip_sha256"):
        raise _fail("f99_submission_tampered")
    return data


def _load_package(market: Path, submission: dict) -> dict:
    """重开提交包：字节 sha 复核＋F95 预检重跑＋目录推导重跑（同一字节
    同一结果——审核与采用永远对真实字节负责，不对登记摘要负责）。"""
    package = _submission_dir(market, submission["submission_id"]) \
        / "package.zip"
    data = package.read_bytes()
    if sha256_hex(data) != submission["zip_sha256"]:
        raise _fail("f99_submission_tampered")
    stem = submission.get("source_stem")
    catalog_id = stem if isinstance(stem, str) and stem \
        and _safe_stem(stem) else "skills"
    zin = open_zip_bytes(data)
    with zin:
        pre = precheck_zip(zin)
    derived = derive_manifest_from_files(
        pre["files"], catalog_id=catalog_id, channel="public", kind="zip",
        zip_sha256=submission["zip_sha256"])
    return {"precheck": pre, "manifest": derived["manifest"],
            "mount": derived["mount"]}


def _safe_stem(stem: str) -> bool:
    from skill_catalog import _safe_rel_path
    return bool(stem) and _safe_rel_path(stem) is not None


# --------------------------------------------------------------------------
# 审核清单（确定性四检；findings 只记错误码与工程标识，零内容回显）
# --------------------------------------------------------------------------

def _review_checklist(market: Path, submission: dict) -> list:
    findings = []
    loaded = _load_package(market, submission)
    pre, manifest, mount = (loaded["precheck"], loaded["manifest"],
                            loaded["mount"])
    if pre["scripts"]:
        findings.append({"check": "script_policy",
                         "code": "f99_review_script_policy",
                         "scripts": pre["scripts"]})
    by_mount = {f["path"]: f for f in manifest["files"]}
    with tempfile.TemporaryDirectory(prefix="f99-review-") as tmp:
        for rel in sorted(mount):
            target = Path(tmp) / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(pre["files"][mount[rel]])
        for skill in manifest["skills"]:
            sid = skill["id"]
            if sid + "/SKILL.md" in by_mount:
                entry = Path(tmp) / sid / "SKILL.md"
            elif sid + ".md" in by_mount:
                entry = Path(tmp) / (sid + ".md")
            else:
                findings.append({"check": "contract_gate", "skill": sid,
                                 "code": "f99_review_contract_missing"})
                continue
            text = entry.read_text(encoding="utf-8")
            scan = scan_text(text, kind="skill")
            if not scan["clean"]:
                findings.append({
                    "check": "injection_scan", "skill": sid,
                    "code": "f99_review_injection_findings",
                    "families": scan["families"],
                    "rules": sorted({f["rule"]
                                     for f in scan["findings"]})})
            try:
                receipt = validate_skill({"skill_path": str(entry),
                                          "skill_id": sid})
            except (SkillGateError, SkillSemanticsError) as exc:
                findings.append({"check": "contract_gate", "skill": sid,
                                 "code": "f99_review_contract_invalid",
                                 "gate_code": str(exc)})
                continue
            if not receipt.get("as_of"):
                findings.append({"check": "contract_gate", "skill": sid,
                                 "code": "f99_review_contract_invalid"})
    return findings


# --------------------------------------------------------------------------
# 市场目录树与确定性 bundle（F94 pack 同格式；真实字节重放）
# --------------------------------------------------------------------------

def _market_tree(market: Path, events: list, submission: dict) -> dict:
    """合并目录树＝按 adopt 事件序重放已采用提交包的挂载布局（同挂载路
    径后到覆盖＝同 id 技能内容寻址升级），本次采用提交最后落位。一切来
    自提交包真实字节；事件与提交件绑定漂移＝响亮拒。"""
    def apply(sub: dict) -> None:
        loaded = _load_package(market, sub)
        for mount_rel, source_rel in loaded["mount"].items():
            tree[mount_rel] = loaded["precheck"]["files"][source_rel]

    tree: dict = {}
    for event in events:
        if event["kind"] != "adopt":
            continue
        prior = _load_submission(market, event["submission_id"])
        if prior["zip_sha256"] != event["zip_sha256"]:
            raise _fail("f99_ledger_submission_mismatch")
        apply(prior)
    apply(submission)
    return tree


def _build_bundle(market: Path, tree: dict) -> dict:
    """确定性 bundle（F94 pack 同格式）：manifest.json＋文件，定时间戳＋
    排序条目——同输入字节级同产物，跨 profile 摘要相等。"""
    derived = derive_manifest_from_files(
        tree, catalog_id=MARKET_CATALOG_ID, channel="public",
        kind="marketplace_bundle")
    manifest = derived["manifest"]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        entry = zipfile.ZipInfo("manifest.json",
                                date_time=(1980, 1, 1, 0, 0, 0))
        entry.external_attr = 0o600 << 16
        zf.writestr(entry, canonical_bytes(manifest))
        for f in sorted(manifest["files"], key=lambda x: x["path"]):
            zi = zipfile.ZipInfo(f["path"], date_time=(1980, 1, 1, 0, 0, 0))
            zi.external_attr = 0o600 << 16
            zf.writestr(zi, tree[f["path"]])
    data = buf.getvalue()
    bundles = market / _BUNDLE_DIR
    bundles.mkdir(parents=True, exist_ok=True)
    digest = sha256_hex(data)
    out = bundles / (digest + ".zip")
    if not out.is_file():
        tmp = out.with_name(out.name + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, out)
    if sha256_hex(out.read_bytes()) != digest:
        raise _fail("f99_bundle_corrupt")
    return {"bundle_path": str(out), "bundle_sha256": digest,
            "manifest_sha256": sha256_hex(canonical_bytes(manifest))}


# --------------------------------------------------------------------------
# 公开方法面
# --------------------------------------------------------------------------

def submit(args: dict, config: dict) -> dict:
    """创作者流：F95 预检收件＋登记 submitted（结构性无批准出口）。"""
    _closed_args(args, _SUBMISSION_FIELDS, "f99_submit_params_invalid")
    market = _market_dir(config)
    creator = _text(args["creator"], "f99_creator_required")
    url = _text(args["url"], "f99_source_invalid")
    zip_path = _text(args["zip_path"], "f99_source_invalid")
    sha_declared = args["sha256"]
    if not _is_sha256(sha_declared):
        raise _fail("f99_source_invalid")
    price = _price(args["price_minor"], "f99_price_invalid")
    package = Path(zip_path)
    if not package.is_file():
        raise _fail("f99_zip_unreadable")
    data = package.read_bytes()
    if sha256_hex(data) != sha_declared:
        raise _fail("f99_zip_source_mismatch")
    try:
        zin = open_zip_bytes(data)
        with zin:
            pre = precheck_zip(zin)
        derived = derive_manifest_from_files(
            pre["files"], catalog_id=package.stem
            if _safe_stem(package.stem) else "skills",
            channel="public", kind="zip", zip_sha256=sha_declared)
    except SkillCatalogError as exc:
        raise _fail("f99_submit_failed:" + str(exc)) from None
    submissions = market / _SUBMISSIONS_DIR
    submissions.mkdir(parents=True, exist_ok=True)
    seq = len([p for p in submissions.iterdir() if p.is_dir()]) + 1
    submission_id = "sub-%04d" % seq
    record = {
        "schema": SCHEMA,
        "submission_id": submission_id,
        "creator": creator,
        "source_url": url,
        "zip_sha256": sha_declared,
        "price_minor": price,
        "paid": price > 0,
        "source_stem": package.stem,
        "skills": [{"id": s["id"], "name": s["name"]}
                   for s in derived["manifest"]["skills"]],
        "scripts": pre["scripts"],
        "entry_count": len(pre["files"]),
        "total_bytes": pre["total_bytes"],
        "status": "submitted",
        "submitted_at": _now(),
    }
    sub_dir = submissions / submission_id
    sub_dir.mkdir()
    (sub_dir / "package.zip").write_bytes(data)
    (sub_dir / "submission.json").write_text(
        canonical_bytes(record).decode("utf-8"), encoding="utf-8")
    return {"status": "SUBMITTED", "submission": record}


def review_decide(args: dict, config: dict) -> dict:
    """审核流：approved 必须全清单过；rejected 必带闭集理由；同件重复
    决定幂等返回、异决定冲突具名拒。"""
    _closed_args(args, _REVIEW_FIELDS, "f99_review_params_invalid")
    market = _market_dir(config)
    reviewer = _text(args["reviewer"], "f99_reviewer_required")
    decision = args["decision"]
    if decision not in REVIEW_DECISIONS:
        raise _fail("f99_review_decision_invalid")
    reason = args["reason_code"]
    if decision == "rejected":
        if reason not in REJECT_REASONS:
            raise _fail("f99_review_reason_invalid")
    elif reason is not None:
        raise _fail("f99_review_reason_invalid")
    submission = _load_submission(market, args["submission_id"])
    events = _read_events(market)
    prior = next((e for e in events if e["kind"] == "review"
                  and e["submission_id"] == submission["submission_id"]),
                 None)
    if prior is not None:
        if (prior["decision"] == decision
                and prior["reason_code"] == reason
                and prior["reviewer"] == reviewer):
            return {"status": "REVIEW_EXISTS", "review": prior,
                    "idempotent": True}
        raise _fail("f99_review_conflict")
    findings = _review_checklist(market, submission)
    if decision == "approved" and findings:
        raise _fail("f99_review_check_failed:" + findings[0]["code"])
    record = _append_event(market, "review", "rev", {
        "submission_id": submission["submission_id"],
        "zip_sha256": submission["zip_sha256"],
        "manifest_skills": [s["id"] for s in submission["skills"]],
        "decision": decision,
        "reviewer": reviewer,
        "reason_code": reason,
        "findings": findings,
        "reviewed_at": _now(),
    })
    return {"status": "REVIEW_RECORDED", "review": record,
            "idempotent": False}


def adopt(args: dict, config: dict) -> dict:
    """分发流：真实决定引用→付费墙→市场目录树重放→确定性 bundle 经
    F94 bundle 源真安装（public 广场）→采用事件落账。"""
    _closed_args(args, _ADOPT_FIELDS, "f99_adopt_params_invalid")
    market = _market_dir(config)
    catalog_root = config.get("skill_catalog_state_root")
    if not isinstance(catalog_root, str) or not catalog_root:
        raise _fail("f99_catalog_root_not_configured")
    ref = args["decision_ref"]
    if not isinstance(ref, dict) or set(ref) != set(_DECISION_REF_FIELDS) \
            or not isinstance(ref["review_id"], str) or not ref["review_id"]:
        raise _fail("f99_decision_ref_invalid")
    submission = _load_submission(market, args["submission_id"])
    events = _read_events(market)
    review = _find_event(events, "review", ref["review_id"])
    if review is None:
        raise _fail("f99_decision_ref_missing")
    if review["submission_id"] != submission["submission_id"]:
        raise _fail("f99_decision_ref_mismatch")
    if review["zip_sha256"] != submission["zip_sha256"]:
        raise _fail("f99_review_submission_mismatch")
    if review["decision"] != "approved":
        raise _fail("f99_adopt_review_not_approved")
    prior = next((e for e in events if e["kind"] == "adopt"
                  and e["zip_sha256"] == submission["zip_sha256"]), None)
    if prior is not None:
        return {"status": "ADOPTED", "adoption": prior, "idempotent": True}
    purchase_id = None
    if submission["price_minor"] > 0:
        purchase = next((e for e in events if e["kind"] == "purchase"
                         and e["submission_id"]
                         == submission["submission_id"]), None)
        if purchase is None:
            raise _fail("f99_paywall_required")
        purchase_id = purchase["id"]
    bundle = _build_bundle(market,
                            _market_tree(market, events, submission))
    try:
        receipt = catalog_call(
            "skill.catalog.install",
            {"channel": "public",
             "source": {"kind": "bundle", "path": bundle["bundle_path"],
                        "sha256": bundle["bundle_sha256"]}},
            {"skill_catalog_state_root": catalog_root})
    except SkillCatalogError as exc:
        raise _fail("f99_catalog_failed:" + str(exc)) from None
    if receipt.get("status") != "INSTALLED":
        raise _fail("f99_catalog_failed:install_status_"
                    + str(receipt.get("status")))
    record = _append_event(market, "adopt", "adp", {
        "submission_id": submission["submission_id"],
        "decision_ref": {"review_id": review["id"]},
        "purchase_id": purchase_id,
        "zip_sha256": submission["zip_sha256"],
        "bundle_sha256": bundle["bundle_sha256"],
        "manifest_sha256": receipt["manifest_sha256"],
        "install_id": receipt["install_id"],
        "catalog_id": receipt["catalog_id"],
        "skills": sorted(s["id"] for s in submission["skills"]),
        "adopted_at": _now(),
    })
    return {"status": "ADOPTED", "adoption": record, "idempotent": False,
            "install": {"install_id": receipt["install_id"],
                        "manifest_sha256": receipt["manifest_sha256"],
                        "skills": receipt["skills"],
                        "file_count": receipt["file_count"],
                        "total_bytes": receipt["total_bytes"]}}


def rankings(args: dict, config: dict) -> dict:
    """排行流：本地真实采用事件派生（合成服务面；真实商业排行服务随 v2
    商业化补——§6.1 裁决#13-19 如实标注不冒真实设施）。"""
    _closed_args(args, _RANKINGS_FIELDS, "f99_rankings_params_invalid")
    market = _market_dir(config)
    events = _read_events(market)
    counts: dict = {}
    for event in events:
        if event["kind"] != "adopt":
            continue
        for sid in event["skills"]:
            counts[sid] = counts.get(sid, 0) + 1
    entries = [{"skill_id": sid, "adoption_count": counts[sid]}
               for sid in sorted(counts, key=lambda s: (-counts[s], s))]
    return {"status": "OK", "service_surface": "synthetic_local",
            "service_basis": "local_adoption_events",
            "real_service": "deferred_v2_commercialization",
            "adoption_events": sum(1 for e in events
                                   if e["kind"] == "adopt"),
            "entries": entries}


def purchase(args: dict, config: dict) -> dict:
    """付费墙合成服务面：登记合成购买（整数分；零真实支付轨道）。"""
    _closed_args(args, _PURCHASE_FIELDS, "f99_purchase_params_invalid")
    market = _market_dir(config)
    buyer = _text(args["buyer"], "f99_buyer_required")
    price = _price(args["price_minor"], "f99_price_invalid")
    submission = _load_submission(market, args["submission_id"])
    if price == 0 or submission["price_minor"] == 0:
        raise _fail("f99_purchase_not_required")
    if price != submission["price_minor"]:
        raise _fail("f99_price_mismatch")
    events = _read_events(market)
    prior = next((e for e in events if e["kind"] == "purchase"
                  and e["submission_id"] == submission["submission_id"]
                  and e["buyer"] == buyer), None)
    if prior is not None:
        return {"status": "PURCHASED", "purchase": prior,
                "idempotent": True}
    record = _append_event(market, "purchase", "pur", {
        "submission_id": submission["submission_id"],
        "zip_sha256": submission["zip_sha256"],
        "buyer": buyer,
        "price_minor": price,
        "service_surface": "synthetic",
        "minor_unit": "cny_cent",
        "purchased_at": _now(),
    })
    return {"status": "PURCHASED", "purchase": record, "idempotent": False}


def entitlement(args: dict, config: dict) -> dict:
    _closed_args(args, _ENTITLEMENT_FIELDS,
                 "f99_entitlement_params_invalid")
    market = _market_dir(config)
    submission = _load_submission(market, args["submission_id"])
    events = _read_events(market)
    record = next((e for e in events if e["kind"] == "purchase"
                   and e["submission_id"] == submission["submission_id"]),
                  None)
    return {"status": "OK", "submission_id": submission["submission_id"],
            "price_minor": submission["price_minor"],
            "entitled": record is not None
            or submission["price_minor"] == 0,
            "purchase_id": record["id"] if record else None,
            "service_surface": "synthetic"}


def market_list(args: dict, config: dict) -> dict:
    """审计投影：提交件（含派生审核状态）＋事件账。"""
    _closed_args(args, _LIST_FIELDS, "f99_list_params_invalid")
    market = _market_dir(config)
    events = _read_events(market)
    submissions_root = market / _SUBMISSIONS_DIR
    wanted = args["submission_id"]
    out = []
    if wanted is not None:
        _submission_dir(market, wanted)
    ids: list = []
    if submissions_root.is_dir():
        ids = sorted(p.name for p in submissions_root.iterdir()
                     if p.is_dir())
    if wanted is not None:
        if wanted not in ids:
            raise _fail("f99_submission_not_found")
        ids = [wanted]
    for sid in ids:
        record = _load_submission(market, sid)
        reviews = [e for e in events if e["kind"] == "review"
                   and e["submission_id"] == sid]
        adoptions = [e for e in events if e["kind"] == "adopt"
                     and e["submission_id"] == sid]
        record["review_state"] = (reviews[-1]["decision"] if reviews
                                  else "unreviewed")
        record["adopted"] = bool(adoptions)
        out.append(record)
    return {"status": "OK", "submissions": out,
            "event_count": len(events), "events": events}


def marketplace_call(method: str, args: dict, config: dict) -> dict:
    if not isinstance(args, dict):
        raise _fail("f99_params_invalid")
    if method == "market.submit":
        return submit(args, config)
    if method == "market.review_decide":
        return review_decide(args, config)
    if method == "market.adopt":
        return adopt(args, config)
    if method == "market.rankings":
        return rankings(args, config)
    if method == "market.purchase":
        return purchase(args, config)
    if method == "market.entitlement":
        return entitlement(args, config)
    if method == "market.list":
        return market_list(args, config)
    raise _fail("f99_method_unknown")
