"""F61 微信生态采集（按 ID 分批收口）——批次编排与出处账公开面（W3-U13）。

06 行 F61 验收向量：按已授权 ID 批次采集与出处保存；敏感材料过闸；不走
Cookie 逆向。05:234：微信以用户授权导出或合规工具按 ID 分批，不偷
Cookie/全聊天。裁决#6（战役 24 项外部阻塞）：微信批次＝合成先行（幂等
回流/不改期限负测），授权后补联测；裁决#8-12 负测先行纪律：禁编 URL/
失败不造假。

本面是批次编排与账面（授权账→批次采集→出处保存→投影回读），材料化与
过闸经桥注入回调消费 anonymizer 既有公开面（material.deidentify＝P10
既有 pipeline；attachment.gate＝F38/F44 附件闸），不复制第二权威：

- 授权账（authorize）：只认显式登记的已授权 external_id 集合（append-only，
  幂等重放）。scope 闭集 v1 只有 local_authorized_export（用户授权导出）；
  任何在线/爬取/逆向形态不具名不存在即不存在——不预造形态。
- 批次采集（batch）：逐件处理授权导出材料（text→材料化；pdf_attachment→
  过闸）。字段闭集外的 item 字段一律 typed 拒（url/cookie/token 等
  采集旁路字段结构性无处落）——负测先行：本面没有也不会有网络通道。
- 未授权 ID：条目 status=UNKNOWN_NOT_AUTHORIZED，出处/采集值/闸引用
  三值恒 None（UNKNOWN 不是 0——缺授权是未知态，不造空采集计数）。
- 出处保存（provenance）：每条目绑定导出件 sha256（采集原件出处）与
  采集产物 sha256（材料化/过闸产物出处）＋闸裁决引用；批次账一次写定。
- 幂等回流：同 batch_id 同输入重放＝同回执（不双记）；异输入＝具名
  conflict 拒。
- 敏感红线：条目投影只带计数/哈希/状态/具名理由——导出原文、脱敏映射、
  附件 surface、原件路径绝不回传（material/attachment 面同红线）。

确定性纪律：external_id/export 路径/sha 全部显式比较；无时钟入账语义
（recorded_at 仅溯源展示，幂等键=输入 digest）；本模块零网络依赖
（导入闭集见 test_f61 / recon C01 AST 断言）。
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = "juscite-f61-wechat-collection/1"
BATCH_SCHEMA = "juscite-f61-wechat-collection-batch/1"

# 授权范围闭集（v1）：用户授权本地导出。裁决#6 授权后补联测前，真实
# 在线通道不具名不存在；新增 scope 须扩此闭集并入账，不得隐式放行。
AUTHORIZATION_SCOPES = ("local_authorized_export",)

# 批次条目状态闭集。
ITEM_STATUSES = (
    "COLLECTED",                 # text 导出件材料化完成（sanitized sha 绑定）
    "AUTHORIZED_GATE",           # 附件导出件过闸授权（bound sha 绑定）
    "GATE_REQUIRED",             # 附件件待人审（prepare 面；未决非失败）
    "GATE_REFUSED",              # 附件件闸具名拒（低置信/证据缺失等）
    "SOURCE_MISMATCH",           # 导出件 sha 声明不符（出处断裂 fail-closed）
    "UNKNOWN_NOT_AUTHORIZED",    # 未授权 ID：值恒 None（UNKNOWN 不是 0）
)

# 值字段（出处/采集产物/闸引用）只允许在这些状态非空；其余状态必须为
# None——未决/未知/拒绝态绝不填 0 或空对象冒充采集结果。
VALUE_BEARING_STATUSES = ("COLLECTED", "AUTHORIZED_GATE")

ITEM_FIELD_WHITELIST = ("external_id", "kind", "export_path",
                        "export_sha256", "ocr_doc_id", "human_decision")
BATCH_FIELD_WHITELIST = ("batch_id", "matter_id", "items", "ocr_run_id")
EXPORT_KINDS = ("text", "pdf_attachment")


class CollectionError(ValueError):
    """typed 错误：str(self) 只有错误码，材料内容永不进入错误码。"""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _require_str(value, code: str, *, max_len: int = 4096) -> str:
    if not isinstance(value, str) or not value or len(value) > max_len:
        raise CollectionError(code)
    return value


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1,
                              sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# 授权账
# ---------------------------------------------------------------------------

def _authorization_path(state_root: Path) -> Path:
    return Path(state_root) / "authorization.json"


def load_authorization(state_root: Path) -> dict:
    path = _authorization_path(state_root)
    if not path.is_file():
        return {"schema": SCHEMA, "authorizations": []}
    return _load_json(path)


def authorized_id_set(state_root: Path) -> set[str]:
    ledger = load_authorization(state_root)
    ids: set[str] = set()
    for entry in ledger["authorizations"]:
        ids.update(entry["external_ids"])
    return ids


def authorize_ids(state_root, args: dict) -> dict:
    """登记已授权采集的 external_id 集合（append-only＋幂等重放）。

    同 external_ids 集合（排序后逐项相等）重复登记＝幂等返回既有记录；
    集合有交集但不相等＝追加新授权记录（授权人/时间不同批）。
    """
    root = Path(state_root)
    ids_raw = args.get("external_ids")
    if not isinstance(ids_raw, list) or not ids_raw:
        raise CollectionError("f61_external_ids_required")
    ids: list[str] = []
    for raw in ids_raw:
        eid = _require_str(raw, "f61_external_id_invalid", max_len=128)
        if eid not in ids:
            ids.append(eid)
    scope = args.get("scope") or AUTHORIZATION_SCOPES[0]
    if scope not in AUTHORIZATION_SCOPES:
        raise CollectionError("f61_scope_unknown:" + str(scope))
    authorized_by = _require_str(args.get("authorized_by"),
                                 "f61_authorized_by_required", max_len=256)

    key = "|".join(sorted(ids))
    ledger = load_authorization(root)
    for entry in ledger["authorizations"]:
        if "|".join(sorted(entry["external_ids"])) == key:
            return {
                "authorization": dict(entry),
                "idempotent_replay": True,
                "authorized_ids_total": len(authorized_id_set(root)),
            }
    record = {
        "auth_id": "f61auth-" + _sha256_bytes(
            (key + "|" + scope + "|" + authorized_by).encode("utf-8"))[:16],
        "external_ids": sorted(ids),
        "scope": scope,
        "authorized_by": authorized_by,
        "recorded_at": _now(),
    }
    ledger["authorizations"].append(record)
    _atomic_write_json(_authorization_path(root), ledger)
    return {
        "authorization": record,
        "idempotent_replay": False,
        "authorized_ids_total": len(authorized_id_set(root)),
    }


# ---------------------------------------------------------------------------
# 批次采集
# ---------------------------------------------------------------------------

def _batch_path(state_root: Path, batch_id: str) -> Path:
    return Path(state_root) / "batches" / (batch_id + ".json")


def _item_input_digest(item: dict) -> str:
    canon = json.dumps(item, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"))
    return _sha256_bytes(canon.encode("utf-8"))


def batch_input_digest(args: dict) -> str:
    canon = json.dumps({
        "batch_id": args.get("batch_id"),
        "matter_id": args.get("matter_id"),
        "ocr_run_id": args.get("ocr_run_id"),
        "items": [dict(sorted(i.items())) for i in args.get("items") or []],
    }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return _sha256_bytes(canon.encode("utf-8"))


def _unknown_item(eid: str) -> dict:
    # UNKNOWN 值 None 非 0：三个值位结构性 None，绝不填 0/空对象。
    return {"external_id": eid, "status": "UNKNOWN_NOT_AUTHORIZED",
            "reason": "external_id_not_authorized", "export": None,
            "collected": None, "gate": None, "review_required": None}


def _read_export(export_path: str, declared_sha) -> tuple[bytes, dict]:
    path = Path(export_path)
    if not path.is_file():
        raise CollectionError("f61_export_unreadable")
    data = path.read_bytes()
    digest = _sha256_bytes(data)
    if declared_sha is not None:
        if not isinstance(declared_sha, str) or len(declared_sha) != 64:
            raise CollectionError("f61_export_sha_invalid")
        if declared_sha != digest:
            raise CollectionError("f61_export_sha_mismatch")
    return data, {"sha256": digest, "bytes": len(data)}


def run_batch(state_root, args: dict, *, materialize_text, gate_pdf) -> dict:
    """按已授权 ID 批次采集：授权闸→出处校验→材料化/过闸→出处账。

    materialize_text(text)＝桥注入 material.deidentify 回调（P10 既有
    pipeline）；gate_pdf(request)＝桥注入 attachment.gate 回调（F38/F44
    既有闸）。本函数不 import anonymizer——编排面与权威面经桥解耦。
    """
    root = Path(state_root)
    unknown_fields = sorted(set(args) - set(BATCH_FIELD_WHITELIST))
    if unknown_fields:
        # 采集旁路字段（url/cookie/token…）在顶层也无处置位。
        raise CollectionError("f61_field_forbidden:" + unknown_fields[0])
    batch_id = _require_str(args.get("batch_id"), "f61_batch_id_required",
                            max_len=128)
    matter_id = _require_str(args.get("matter_id"), "f61_matter_id_required",
                             max_len=128)
    items_raw = args.get("items")
    if not isinstance(items_raw, list) or not items_raw:
        raise CollectionError("f61_items_required")
    ocr_run_id = args.get("ocr_run_id")

    # 幂等回流：批次账一次写定——重放校验输入 digest。
    digest = batch_input_digest(args)
    path = _batch_path(root, batch_id)
    if path.is_file():
        existing = _load_json(path)
        if existing.get("input_digest") == digest:
            return dict(existing["receipt"])
        raise CollectionError("f61_batch_conflict")

    authorized = authorized_id_set(root)
    projections: list[dict] = []
    for raw in items_raw:
        if not isinstance(raw, dict):
            raise CollectionError("f61_item_invalid")
        unknown_item_fields = sorted(set(raw) - set(ITEM_FIELD_WHITELIST))
        if unknown_item_fields:
            # 负测先行：url/cookie 等旁路字段具名拒——不存在隐式采集通道。
            raise CollectionError(
                "f61_field_forbidden:" + unknown_item_fields[0])
        eid = _require_str(raw.get("external_id"),
                           "f61_external_id_invalid", max_len=128)
        kind = raw.get("kind")
        if kind not in EXPORT_KINDS:
            raise CollectionError("f61_kind_unknown:" + str(kind))
        export_path = _require_str(raw.get("export_path"),
                                   "f61_export_path_required")
        declared_sha = raw.get("export_sha256")

        if eid not in authorized:
            projections.append(_unknown_item(eid))
            continue
        try:
            data, export_provenance = _read_export(export_path, declared_sha)
        except CollectionError as exc:
            if exc.code == "f61_export_sha_mismatch":
                projections.append(
                    {"external_id": eid, "status": "SOURCE_MISMATCH",
                     "reason": exc.code, "export": None, "collected": None,
                     "gate": None, "review_required": None})
                continue
            raise

        if kind == "text":
            result = materialize_text(data.decode("utf-8"))
            sanitized = result.get("sanitized_text")
            if not isinstance(sanitized, str):
                raise CollectionError("f61_materialize_failed")
            counts = result.get("counts") or {}
            projections.append({
                "external_id": eid, "status": "COLLECTED", "reason": None,
                "export": export_provenance,
                "collected": {
                    "kind": "sanitized_text",
                    "sha256": _sha256_bytes(sanitized.encode("utf-8")),
                    "occurrence_total": counts.get("occurrence_total"),
                },
                "gate": None,
                "review_required": bool(result.get("review_required")),
            })
            continue

        # pdf_attachment → 敏感材料过闸（F38/F44 既有公开面）。
        if not ocr_run_id:
            raise CollectionError("f61_ocr_run_id_required")
        # OCR 证据文档引用：导出件以 external_id 命名落出处；闸内 OCR
        # 语料文档（F40 run 的 doc_id）由调用方声明绑定（ocr_doc_id），
        # 缺省＝external_id 本身。声明关系随批次账入账（input digest 含
        # 全字段），出处以导出件 sha 为准。
        ocr_doc_id = raw.get("ocr_doc_id") or eid
        ocr_doc_id = _require_str(ocr_doc_id, "f61_ocr_doc_id_invalid",
                                  max_len=128)
        request = {"matter_id": matter_id, "attachment_id": eid,
                   "source_pdf": export_path,
                   "ocr": {"run_id": ocr_run_id, "doc_id": ocr_doc_id}}
        # 人审范围决定由律师面（F38/F44 闸既有签名回执）上游传入透传；
        # 决定内容（签名/盒坐标）不入批次投影与批次账——批次只记状态。
        if raw.get("human_decision") is not None:
            if not isinstance(raw["human_decision"], dict):
                raise CollectionError("f61_human_decision_invalid")
            request["human_decision"] = raw["human_decision"]
        verdict = gate_pdf(request)
        gate_verdict = verdict.get("verdict")
        reasons = list(verdict.get("reasons") or [])
        if gate_verdict == "AUTHORIZED":
            bound = verdict.get("bound_sha256")
            if not isinstance(bound, str) or not bound:
                raise CollectionError("f61_gate_verdict_incomplete")
            projections.append({
                "external_id": eid, "status": "AUTHORIZED_GATE",
                "reason": None, "export": export_provenance,
                "collected": {"kind": "authorized_attachment",
                              "sha256": bound},
                "gate": {"verdict": gate_verdict, "reasons": reasons,
                         "bound_sha256": bound},
                "review_required": False,
            })
        elif reasons[:1] == ["review_required_no_human_decision"]:
            # prepare 面：待人审是未决不是失败——值 None，建议计数如实。
            projections.append({
                "external_id": eid, "status": "GATE_REQUIRED",
                "reason": reasons[0], "export": export_provenance,
                "collected": None, "gate": None,
                "review_required": True,
                "detections_count": verdict.get("detections_count"),
            })
        else:
            projections.append({
                "external_id": eid, "status": "GATE_REFUSED",
                "reason": reasons[0] if reasons else "gate_refused",
                "export": export_provenance, "collected": None,
                "gate": {"verdict": gate_verdict, "reasons": reasons,
                         "bound_sha256": None},
                "review_required": None,
            })

    counts = {status: 0 for status in ITEM_STATUSES}
    for entry in projections:
        counts[entry["status"]] += 1
    receipt = {
        "schema": BATCH_SCHEMA,
        "batch_id": batch_id, "matter_id": matter_id,
        "items": projections,
        "counts": {
            "total": len(projections),
            "collected": counts["COLLECTED"],
            "authorized_gate": counts["AUTHORIZED_GATE"],
            "gate_required": counts["GATE_REQUIRED"],
            "gate_refused": counts["GATE_REFUSED"],
            "source_mismatch": counts["SOURCE_MISMATCH"],
            "unknown_not_authorized": counts["UNKNOWN_NOT_AUTHORIZED"],
        },
        "authorization_digest": _sha256_bytes(
            _authorization_path(root).read_bytes())
        if _authorization_path(root).is_file() else None,
        "input_digest": digest,
        "recorded_at": _now(),
    }
    _atomic_write_json(path, {"schema": BATCH_SCHEMA,
                              "batch_id": batch_id,
                              "input_digest": digest,
                              "receipt": receipt})
    return receipt


def read_batch(state_root, args: dict) -> dict:
    """批次投影回读（只读；存在性以外不做任何推导）。"""
    root = Path(state_root)
    batch_id = _require_str(args.get("batch_id"), "f61_batch_id_required",
                            max_len=128)
    path = _batch_path(root, batch_id)
    if not path.is_file():
        raise CollectionError("f61_batch_not_found")
    return dict(_load_json(path)["receipt"])
