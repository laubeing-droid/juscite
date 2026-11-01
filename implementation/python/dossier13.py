"""F144-v2 企业尽调技能包 13 件全量（W5-U15 合成施工）。

台账 F144-v2 行（B5 composite 段，t26-registry-split 拆分规则）：断言逐字
出自 06 source_stage 拍板文「…13 件套全量 v2」（06 acceptance 无 v2 段）。
13 件清单唯一权威＝竞品情报 zhiexa-skill-market.md §1「启信宝 13 件套」
（03-功能分母 F144 引「智合 enterpriseSearch+启信宝 13 件套（zhiexa-
skill-market §1，安装量第一梯队 23511）」；06 source_stage 2026-10-13
用户拍板 MCP 连接器接入不自采）。十三件中文名逐字照抄该权威清单，顺
序亦逐字保持；本面不发明任何件名、不裁剪、不增删（全量＝13/13 闭集）。

本面＝技能包消费面（F144 尽调技能包消费面归 W5——W4-U40 边界注记），
唯一数据通道＝既有 enterprise_connector 公开面（W4-U40 冻结）：
- 提供商闭集单一权威：PROVIDER_CATEGORIES 自 enterprise_connector 导入
  （qcc_mcp/tyc_mcp 类别名零 URL——连接器端点由用户 MCP 配置提供，本
  面零第二闭集、零 URL 字面量）；
- 凭证/seal 单一权威：件投影的 credential 逐字承连接器转录产物（出处
  provider＋时间 retrieved_at＋额度 quota_remaining＋载荷 sha256 水印
  ＋确定性 seal），本面零第二 seal 权威、零重算（声明面单一来源）；
- 企业数据原文不落账（载荷只留 sha256＋字段计数——连接器结构性纪律，
  件投影逐字承之，档案原文扫描零企业名）。

W4-U40 九条负测纪律全继承（本面为消费面，逐条结构化落实，recon/测试
AST 级＋运行级双验）：
① 提供商闭集零 URL（单一权威导入，闭集外具名拒）；② 缺 token→
PAID_TOKEN_NOT_CONFIGURED 不自采不编数据（data/credential 恒 None 非
{}，连接器逐字上浮）；③ token 在位仍 SESSION_ABSENT（桥注入
session_factory 恒 None＝真实调用路径结构性不可达，客户端未建不可能自
采）；④ 回执转录绑定 出处/时间/额度＋sha256 水印＋确定性 seal（逐字承
连接器凭证）；⑤ 失败三路（QUERY_FAILED/RECEIPT_INVALID×2）data/
credential 恒 None 绝不编占位企业字段；⑥ url/cookie 等旁路字段件面顶
层具名拒＋名称/统一社会信用代码恰一查询键；⑦ AST 双验＝导入闭集零网
络模块＋字符串常量零 URL＋recon 自身同检；⑧ 状态根产物零 URL 零
token 值；⑨ 幂等回流（同 dossier_id 同输入重放逐键相等/异输入具名
conflict/回读投影相等）。

边界如实：真实 MCP 连接器授权调用的实测属 F144-desktop/selfhost 回收
点（授权后补联测，W5-U19 守账），不并入本单；原生 UI 触发面属产品宿主
后续工单不前造；F94 技能目录分发链（zip/git 安装）不在本单（本面为产
品内技能包消费面，非 F94 目录实例）。

确定性纪律：件目录/run 输入全部显式比较；recorded_at 仅溯源展示不入幂
等键（幂等键＝输入 digest）；本模块零网络依赖（导入闭集见 recon AST
断言）；无金额字段（额度 quota_remaining 为整数计数非货币）。
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from enterprise_connector import PROVIDER_CATEGORIES, diligence_query

SCHEMA = "juscite-f144-v2-dossier13/1"

# 13 件闭集（件 id＝本面稳定工程标识；中文名＝权威清单逐字，零改写）。
# 权威出处：竞品情报 2026-10-11/notes/zhiexa-skill-market.md §1
# 「启信宝 13 件套」（03-功能分母 F144／06 source_stage 引）。
DOSSIER13_PIECES = (
    ("priority-ranking", "企业优先级排序"),
    ("panorama-report", "全景尽调报告"),
    ("company-risk-quick-scan", "公司风险速查"),
    ("affiliate-risk-transmission", "关联企业传导风险"),
    ("pre-admission-check", "前置准入核验"),
    ("judicial-operation-risk-checkup", "司法与经营风险体检"),
    ("counterparty-verification", "合作前主体核验"),
    ("domestic-affiliation", "国内企业关联关系"),
    ("multi-hop-relation", "多次关系寻源"),
    ("customer-admission-screening", "客户准入快速筛查"),
    ("bidding-radar", "招投标情报雷达"),
    ("negative-publicity-scan", "负面舆情扫描"),
    ("key-region-search", "重点区域企业检索"),
)
PIECE_IDS = tuple(pid for pid, _name in DOSSIER13_PIECES)
PIECE_NAMES = tuple(name for _pid, name in DOSSIER13_PIECES)

# 查询键名闭集（值不落账；档案只记键名——键值入连接器输入 digest）。
QUERY_KEY_FIELDS = ("company_name", "credit_code")

ARG_WHITELIST = ("dossier_id", "matter_id", "piece_id", "providers",
                 "company_name", "credit_code")


class Dossier13Error(ValueError):
    """typed 错误：str(self) 只有 d13_* 错误码，企业数据原文/token 值/
    URL 永不进错误码。"""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))


def _require_str(value, code: str, *, max_len: int) -> str:
    if not isinstance(value, str) or not value or len(value) > max_len:
        raise Dossier13Error(code)
    return value


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1,
                              sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# 件目录面（13/13 全量闭集；零数据零 URL 零自采）
# ---------------------------------------------------------------------------

def pack_read() -> dict:
    """技能包目录投影：13 件全量闭集（逐字件名＋顺序保持）。

    零企业数据、零查询触发、零 URL 披露；提供商闭集只以类别名列出
    （单一权威自 enterprise_connector 导入）。
    """
    source_note = ("zhiexa-skill-market.md §1 启信宝 13 件套"
                   "（03-功能分母 F144；06 source_stage 13 件套全量 v2）")
    return {
        "schema": SCHEMA,
        "pack": "enterprise-due-diligence-skill-pack",
        "form": "skill_pack_no_self_collection",
        "piece_count": len(DOSSIER13_PIECES),
        "full_set": True,
        "pieces": [{"piece_id": pid, "name": name,
                    "source": source_note}
                   for pid, name in DOSSIER13_PIECES],
        "providers": list(PROVIDER_CATEGORIES),
        "provider_form": "mcp_connector_no_self_collection",
        "self_collection": "none",
        "url_disclosure": "none",
    }


# ---------------------------------------------------------------------------
# 件执行面（唯一数据通道＝enterprise_connector.diligence_query）
# ---------------------------------------------------------------------------

def _validate_args(args: dict) -> dict:
    if not isinstance(args, dict):
        raise Dossier13Error("d13_args_invalid")
    unknown = sorted(set(args) - set(ARG_WHITELIST))
    if unknown:
        # 负测纪律⑥件面同频：url/cookie 等旁路字段具名拒（无隐式通道）。
        raise Dossier13Error("d13_field_forbidden:" + unknown[0])
    dossier_id = _require_str(args.get("dossier_id"),
                              "d13_dossier_id_required", max_len=128)
    matter_id = _require_str(args.get("matter_id"),
                             "d13_matter_id_required", max_len=128)
    piece_id = _require_str(args.get("piece_id"), "d13_piece_id_required",
                            max_len=128)
    if piece_id not in PIECE_IDS:
        raise Dossier13Error("d13_piece_unknown:" + piece_id)
    providers = args.get("providers")
    if not isinstance(providers, list) or not providers:
        raise Dossier13Error("d13_providers_required")
    seen = []
    for p in providers:
        if p not in PROVIDER_CATEGORIES:
            # 负测纪律①：闭集外提供商具名拒（单一权威闭集）。
            raise Dossier13Error("d13_provider_unknown:" + str(p))
        if p in seen:
            raise Dossier13Error("d13_provider_duplicate:" + str(p))
        seen.append(p)
    company_name = args.get("company_name")
    credit_code = args.get("credit_code")
    if (company_name is None) == (credit_code is None):
        # 负测纪律⑥：名称/统一社会信用代码恰一查询键。
        raise Dossier13Error("d13_query_key_exactly_one_required")
    if company_name is not None:
        _require_str(company_name, "d13_company_name_invalid", max_len=256)
    if credit_code is not None:
        _require_str(credit_code, "d13_credit_code_invalid", max_len=256)
    return {"dossier_id": dossier_id, "matter_id": matter_id,
            "piece_id": piece_id, "providers": list(providers),
            "company_name": company_name, "credit_code": credit_code}


def _dossier_path(state_root: Path, dossier_id: str) -> Path:
    return Path(state_root) / "dossiers" / (dossier_id + ".json")


def run_dossier(state_root, args: dict, *, session_factory=None) -> dict:
    """按件执行尽调并落档案投影（幂等键＝输入 digest）。

    session_factory 语义与连接器面逐字同构：None（产品桥常态，连接器未
    配置）→ token 在位也只会得到 SESSION_ABSENT 具名缺口——真实调用路
    径结构性不可达（纪律③）。唯一数据通道＝enterprise_connector
    .diligence_query：凭证/失败投影逐字承连接器产物，本面零第二权威。
    """
    root = Path(state_root)
    v = _validate_args(args)
    items = [{"provider": p,
              "company_name": v["company_name"],
              "credit_code": v["credit_code"]}
             for p in v["providers"]]
    query_key = "company_name" if v["company_name"] is not None \
        else "credit_code"
    conn_args = {"query_id": v["dossier_id"], "matter_id": v["matter_id"],
                 "items": items}
    digest = _sha256_text(_canonical(conn_args))
    path = _dossier_path(root, v["dossier_id"])
    if path.is_file():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing.get("input_digest") == digest:
            return dict(existing["dossier"])
        raise Dossier13Error("d13_dossier_conflict")

    receipt = diligence_query(root, conn_args,
                              session_factory=session_factory)
    piece_name = dict(DOSSIER13_PIECES)[v["piece_id"]]
    counts = {status: 0 for status in (
        "DILIGENCE_RECORDED", "RECEIPT_INVALID", "QUERY_FAILED",
        "SESSION_ABSENT", "TOKEN_NOT_CONFIGURED")}
    for seg in receipt["items"]:
        counts[seg["status"]] += 1
    dossier = {
        "schema": SCHEMA,
        "form": "skill_pack_no_self_collection",
        "piece_id": v["piece_id"],
        "piece_name": piece_name,
        "dossier_id": v["dossier_id"],
        "matter_id": v["matter_id"],
        "query_key": query_key,
        "segments": receipt["items"],
        "counts": {status.lower(): counts[status] for status in counts},
        "sessions_established": receipt["sessions_established"],
        "input_digest": digest,
        "recorded_at": _now(),
    }
    _atomic_write_json(path, {"schema": SCHEMA,
                              "dossier_id": v["dossier_id"],
                              "input_digest": digest,
                              "dossier": dossier})
    return dossier


def read_dossier(state_root, args: dict) -> dict:
    """档案回读（只读；存在性以外不做任何推导）。"""
    if not isinstance(args, dict):
        raise Dossier13Error("d13_args_invalid")
    unknown = sorted(set(args) - {"dossier_id"})
    if unknown:
        raise Dossier13Error("d13_field_forbidden:" + unknown[0])
    dossier_id = _require_str(args.get("dossier_id"),
                              "d13_dossier_id_required", max_len=128)
    path = _dossier_path(Path(state_root), dossier_id)
    if not path.is_file():
        raise Dossier13Error("d13_dossier_not_found")
    return dict(json.loads(path.read_text(encoding="utf-8"))["dossier"])
