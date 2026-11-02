# -*- coding: utf-8 -*-
"""F100 专家分身/专家商店 验收对账（W5-U04）。

06:F100（owner=manuals+product，B5，desktop;selfhost 双实例）acceptance
「专家内容授权/来源/适用范围准确；分身不冒真人实时意见」＋17 卡落点
「Harness manuals/playbook 公开消费＋受控内容包；原生技能UI」＋17 卡步
骤「固定内容 hash/权限→公开读取→实际任务消费→来源回执和验证；不公开
私域蒸馏」＋裁决#13-19（00-总协调.md:254 专家内容统一合成先行）＋裁决
#7（00-总协调.md:252 合成样本先行/Observer 不启用）＋工作区根 AGENTS.md
真安全边界 3（安装包不带 manuals 与 persona 内容）。

分段（全局一次＋每 profile 两腿）：
  S0 钉定（expert_store/legal_entry/接线测试在盘；manuals 检出只读消
     费基线＝HEAD 记录＋工作树干净（本单零字节依赖 manuals 内部，不钉
     具体 commit，只钉「扫描时所见面即仓面」）；persona 缺席形态）
  S1 授权/来源/适用范围闭环（expert.define：卡片 digest 客端独立重算；
     幂等重定义；修订 supersede＋历史回读；authorized_excerpt 授权/署
     名缺一不入店；synthetic_original 挂署名自相矛盾拒；未知 authorship
     形（冒充真人署名形）进不了授权闭集；适用范围声明是准入要件；
     private 内容不入包；grounding 只认 pinned_pack（live/realtime 形
     具名拒）；declaresRealTime=True 具名拒）
  S2 公开读取＋授权 fail-closed（store_list/store_read：public 恒可见
     ／firm 显式授权／private 永不可授权；货架输出字节级零条目正文；
     货架 cardRef.digest 与 define 钉定值逐字绑定一致）
  S3 实际任务消费（consult：4 主题金标 recall@1=1.0；两跑命中逐字节同
     ＝确定性；nonLive 不冒真人声明恒携；grounding=pinned_pack＋
     packVersion＋cardDigest；零词面重叠查询＝f100_out_of_scope_abstain
     具名弃答×3；应答回显适用范围声明）
  S4 来源回执和验证（回执落盘 consult-log.jsonl；verify_receipt 全量
     重算 PASS；未知回执具名拒；篡改回执账具名拒（临时副本）；篡改包
     正文→读取/消费/验签三面具名拒（临时副本）；命中 sourceRefs 搭
     digest 与盘上合成源文档 sha256 逐字相等＝回执可回溯源）
  S6 红线（全局：expert_store import 闭集零网络/manuals/lcr；EXPERT
     _METHODS 冻结五方法无 publish/enable/distill/observe 写面；既有公
     开消费通道在位＝MANUAL_METHODS 恰读侧四方法＋HARNESS_PLAYBOOK
     _METHODS 恰三方法（不复制第二权威）；persona/observer 具名拒不
     复活；implementation/ 实物树 × manuals/persona 仓全文件 sha256 零
     重叠＝安装包不带两者内容）
  X  双 profile 归一化 digest 相等（治理面与宿主形态无关）

用法（juscite worktree 根 cwd）：
  python -X utf8 tools/recon/PENDING_OWNER_f100_expert_content_recon.py \
      --profile desktop --profile selfhost

exit 0＝RECON_OK 全断言过；证据 JSON 写 evidence/F100/<profile>/ 与
docs/construction/evidence/F100/<profile>/。全合成材料（合成专家卡/合
成署名/合成源文档，标注工程验证样本，无法条引文，无真人内容）；不发
网络；零 %APPDATA% 触碰；manuals/persona 仓只读消费（零字节改动，S6
树扫描前后 git status 复核）。
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LEGAL_ENTRY = REPO_ROOT / "implementation" / "python" / "legal_entry.py"
EXPERT_STORE = REPO_ROOT / "implementation" / "python" / "expert_store.py"
WIRING_TEST = REPO_ROOT / "implementation" / "tests" \
    / "test_f100_expert_store_wiring.py"

EXPERT_FIVE = ["expert.define", "expert.store_list", "expert.store_read",
               "expert.consult", "expert.verify_receipt"]
MANUAL_QUARTET = frozenset({
    "manual.open", "manual.search", "manual.read", "manual.version"})
PLAYBOOK_TRIO = frozenset({
    "harness.select_playbook", "harness.read_playbook",
    "harness.record_deviation"})

NETWORK_MODULES = {"socket", "ssl", "urllib", "urllib.request", "urllib.parse",
                   "http", "http.client", "requests", "httpx", "ftplib",
                   "smtplib", "poplib", "imaplib", "telnetlib", "xmlrpc",
                   "websocket"}
ENGINE_ALLOWED_IMPORTS = {"__future__", "datetime", "hashlib", "json",
                          "math", "os", "re", "typing"}

SYN_MARK = ("本条为工程合成验收材料（SYNTHETIC），无任何真实法条引文、"
            "无真实案情、无真人内容。")

# 四个互斥合成主题（工程验证样本；全部虚构、无法条引文）。
SYN_TOPICS = {
    "t1": ("押金结算退还", "押金 结算 租赁 物业交割 退还",
           "租赁押金结算应在物业交割后按清单核验扣除项，剩余押金限期退还，"
           "异议须留痕。"),
    "t2": ("仲裁时效管理", "仲裁 时效 劳动关系 申请期限",
           "劳动关系争议申请仲裁的时效台账要点：起算、中止、中断事由逐项"
           "留痕，逾期风险主动提示。"),
    "t3": ("知识产权许可审查", "知识产权 许可 侵权 合同条款",
           "知识产权许可合同条款审查要点：许可范围、分许可限制、侵权责任"
           "分担与终止后义务。"),
    "t4": ("工期签证台账", "工期 签证 施工 监理 计日",
           "建设工程工期签证与监理计日记录管理：事件发生后限期书面签证，"
           "顺延申请附证据链。"),
}
OUT_OF_SCOPE_QUERIES = ["天气预报 今天穿什么", "菜谱 红烧肉 做法",
                        "股票 行情 涨跌"]


def sha256_file(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_json(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def client_card_digest(card_meta: dict) -> str:
    """客端独立重算卡片快照 hash（canonical JSON 全字段 sha256，含正文
    ——与引擎卡片视图同形：displayName/grounding/attribution/
    applicableScopes/items 五段）。"""
    view = {k: card_meta[k] for k in ("displayName", "grounding",
                                      "attribution", "applicableScopes",
                                      "items")}
    return sha256_hex(canonical_json(view))


def sha256_hex(data: bytes) -> str:
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
        return sum(1 for i in self.items if i["status"] == "PASS")


# ------------------------------------------------------------ 合成材料 --

def synth_body(tid: str, n: int) -> str:
    name, _q, point = SYN_TOPICS[tid]
    return ("# 合成经验条目·%s·%d（工程验证样本）\n%s\n%s\n"
            % (name, n, point, SYN_MARK))


def synth_sources(tmp: Path) -> dict:
    """12 份合成源文档落盘（4 主题×3 条），返回 {(tid,n): sha256}——
    专家卡条目 sourceRefs.digest 绑定盘上字节（来源回执可回溯）。"""
    digests = {}
    src_dir = tmp / "sources"
    src_dir.mkdir(parents=True, exist_ok=True)
    for tid in SYN_TOPICS:
        for n in (1, 2, 3):
            path = src_dir / ("syn-%s-%d.md" % (tid, n))
            path.write_text("合成源文档 syn-%s-%d（工程验证样本，无法条"
                            "引文）\n%s\n" % (tid, n, synth_body(tid, n)),
                            encoding="utf-8")
            digests[(tid, n)] = sha256_file(path)
    return digests


def card_args(expert_id="exp-syn-1", *, display="合成专家·甲（工程验证样本）",
              scope="public", source_digests=None):
    """合成专家卡：4 主题×3 条目（同一 scope），grounding/attribution
    合法缺省（synthetic_original＋pinned_pack）；条目 sourceRefs 携盘上
    合成源文档 sha256。"""
    items = []
    idx = 0
    for tid in SYN_TOPICS:
        for n in (1, 2, 3):
            idx += 1
            digest = (source_digests or {}).get((tid, n))
            ref = {"owner": "synthetic", "kind": "syn-doc",
                   "id": "syn-%s-%d" % (tid, n)}
            if digest:
                ref["digest"] = digest
            items.append({
                "title": "合成经验条目·%s·%d（工程验证样本）"
                         % (SYN_TOPICS[tid][0], n),
                "body": synth_body(tid, n),
                "readScope": scope,
                "sourceRefs": [ref],
                "topics": [SYN_TOPICS[tid][0]],
            })
    return {"expertId": expert_id, "displayName": display,
            "grounding": {"kind": "pinned_pack", "declaresRealTime": False},
            "attribution": {"authorship": "synthetic_original"},
            "applicableScopes": ["工程合成验收场景"],
            "items": items}


# ------------------------------------------------------------ 检出解析 --

def resolve_workspace_sibling(*parts: str) -> Path | None:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if parent.name == "jusbench工作区":
            guess = parent.parent.joinpath(*parts)
            return guess if guess.is_dir() else None
    return None


def manuals_checkout(override: str | None) -> Path:
    if override:
        return Path(override)
    env = os.environ.get("JUSCITE_MANUALS_CHECKOUT")
    if env:
        return Path(env)
    got = resolve_workspace_sibling("legal-cn-manuals工作区",
                                    "legal-cn-manuals-repo")
    if got is None:
        raise SystemExit("PENDING_ENV manuals checkout not resolved "
                         "(--manuals-checkout / JUSCITE_MANUALS_CHECKOUT)")
    return got


def persona_checkout(override: str | None) -> Path | None:
    if override:
        return Path(override)
    env = os.environ.get("JUSCITE_PERSONA_CHECKOUT")
    if env:
        return Path(env)
    return resolve_workspace_sibling("legal-cn-persona工作区",
                                     "legal-cn-persona-repo")


# ------------------------------------------------------------ S0 钉定 --

def s0_pins(checks: Checks, manuals_root: Path, persona_root: Path | None):
    present = all(p.is_file() for p in (LEGAL_ENTRY, EXPERT_STORE,
                                        WIRING_TEST))
    checks.add("c01_f100_surfaces_present", present,
               "expert_store.py＋legal_entry.py＋接线测试在本 worktree 在盘")
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(manuals_root),
                          capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain"],
                           cwd=str(manuals_root),
                           capture_output=True, text=True).stdout.strip()
    checks.add("c02_manuals_checkout_readonly_baseline",
               dirty == "",
               "manuals 检出 HEAD %s 工作树干净（只读消费基线；本单零字节"
               "依赖 manuals 内部＝不钉具体 commit，只钉扫描时所见面即仓"
               "面；HEAD 记录入证据）" % head[:12])
    if persona_root is None:
        ok, detail = True, "persona 仓缺失（可选件缺席形态）"
    else:
        names = sorted(str(p.relative_to(persona_root)) for p in
                       persona_root.rglob("*")
                       if p.is_file() and ".git" not in p.parts)
        ok = set(names) <= {".gitignore", "README.md"}
        detail = ("persona 仓 README-only（缺席形态）" if ok
                  else "persona 仓形态漂移：%s" % names[:5])
    checks.add("c03_persona_absence_form", ok, detail)


# ------------------------------------------------------------ 产品桥 CLI --

def call_cli(method: str, args: dict, config: dict, tmp: Path):
    """真产品入口子进程径（legal_entry CLI，同 E23/F64/F73 纪律）。"""
    req = tmp / ("request-%s.json" % method.replace(".", "-"))
    cfg = tmp / "config.json"
    req.write_text(json.dumps({"method": method, "args": args},
                              ensure_ascii=False), encoding="utf-8")
    cfg.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", str(LEGAL_ENTRY),
         "--request-json", str(req), "--config", str(cfg)],
        capture_output=True, text=True, timeout=180)
    payload = None
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            payload = json.loads(line)
    return proc.returncode, payload


def ok_result(payload):
    if payload and payload.get("status") == "OWNER_RESPONSE":
        return payload.get("result")
    return None


def refuse_code(payload) -> str:
    """NOT_CONNECTED 载荷里的 typed 码（expert 组前缀 expert_failed: 后段）。"""
    code = (payload or {}).get("code") or ""
    return code.split("expert_failed:", 1)[1] \
        if code.startswith("expert_failed:") else code


# ------------------------------------------------------------ profile 腿 --

def run_profile(profile: str, checks: Checks, manuals_root: Path,
                persona_root: Path | None, tmp: Path) -> dict:
    tag = "[%s]" % profile
    obs: dict = {}
    state_root = tmp / "state"
    cfg = {"expert_state_root": str(state_root)}
    source_digests = synth_sources(tmp)
    obs["sourceDocs"] = {"%s-%d" % k: v for k, v in
                         sorted(source_digests.items())}

    def define(args):
        return call_cli("expert.define", args, cfg, tmp)

    def consult(args):
        return call_cli("expert.consult", args, cfg, tmp)

    def refuse(method, args, use_cfg=None):
        rc, payload = call_cli(method, args, use_cfg or cfg, tmp)
        return rc, refuse_code(payload), payload

    # ---- S1 授权/来源/适用范围闭环（expert.define 面）----
    args = card_args(source_digests=source_digests)
    rc, payload = define(args)
    defined = ok_result(payload)
    client_digest = client_card_digest(args)
    checks.add("s1_01_card_digest_client_recomputed%s" % tag,
               rc == 0 and defined and defined["cardDigest"] == client_digest,
               "define exit=%d；卡片快照 sha256 客端独立重算逐字相等（固定"
               "内容 hash 钉定）" % rc)
    obs["cardDigest"] = (defined or {}).get("cardDigest")
    obs["revision"] = (defined or {}).get("revision")

    rc2, payload2 = define(card_args(source_digests=source_digests))
    again = ok_result(payload2)
    checks.add("s1_02_redefine_idempotent%s" % tag,
               rc2 == 0 and again and again["revised"] is False
               and again["revision"] == defined["revision"]
               and again["cardDigest"] == client_digest,
               "同内容重定义幂等（同 revision 同 digest，revised=False）")

    changed = card_args(source_digests=source_digests)
    changed["items"][0]["title"] += "（修订）"
    rc3, payload3 = define(changed)
    revised = ok_result(payload3)
    checks.add("s1_03_supersede_keeps_history%s" % tag,
               rc3 == 0 and revised and revised["revised"] is True
               and revised["revision"] == 2
               and revised["superseded"] == {
                   "revision": 1, "cardDigest": client_digest},
               "内容变更→revision 2＋superseded 携 v1（追加只增不改）")
    rc_h, payload_h = call_cli("expert.store_read",
                               {"expertId": "exp-syn-1", "version": 1},
                               cfg, tmp)
    history = ok_result(payload_h)
    checks.add("s1_04_history_version_readable%s" % tag,
               rc_h == 0 and history
               and history["cardRef"]["digest"] == client_digest
               and history["cardRef"]["version"] == "1",
               "v1 历史可回读且 digest 仍钉原快照")

    base_items = card_args()["items"]
    ae_base = {"expertId": "exp-ae", "displayName": "x",
               "grounding": {"kind": "pinned_pack"},
               "applicableScopes": ["s"], "items": base_items}
    missing_codes = []
    for attribution in ({"authorship": "authorized_excerpt"},
                        {"authorship": "authorized_excerpt",
                         "attributedTo": "某人"},
                        {"authorship": "authorized_excerpt",
                         "authorizationRef": "ref-1"}):
        rc_m, code_m, _ = refuse("expert.define",
                                 dict(ae_base, attribution=attribution))
        missing_codes.append((rc_m, code_m))
    checks.add("s1_05_authorized_excerpt_needs_attribution_and_ref%s" % tag,
               all(rc == 3 and code == "f100_authorization_missing"
                   for rc, code in missing_codes),
               "authorized_excerpt 授权/署名缺一不入店（%s）"
               % [c for _, c in missing_codes])
    ok_ae = dict(ae_base, attribution={
        "authorship": "authorized_excerpt",
        "attributedTo": "合成署名·乙（工程验证样本）",
        "authorizationRef": "syn-authz-ref-001"})
    rc_ae, code_ae, _ = refuse("expert.define", ok_ae)
    checks.add("s1_06_authorized_excerpt_complete_admitted%s" % tag,
               rc_ae == 0 and code_ae == "",
               "署名＋授权凭据齐备（合成样本值）即入店＝授权面准确可表达")

    rc_c, code_c, _ = refuse("expert.define", dict(
        ae_base, attribution={"authorship": "synthetic_original",
                              "attributedTo": "合成署名·丙（工程验证样本）"}))
    checks.add("s1_07_synthetic_original_attribution_conflict%s" % tag,
               rc_c == 3 and code_c == "f100_attribution_conflict",
               "synthetic_original 挂署名＝自相矛盾具名拒（不冒真人）")

    rc_u, code_u, _ = refuse("expert.define", dict(
        ae_base, attribution={"authorship": "claimed_real_expert",
                              "attributedTo": "真人",
                              "authorizationRef": "r"}))
    checks.add("s1_08_unknown_authorship_outside_closed_set%s" % tag,
               rc_u == 3 and code_u == "f100_authorization_invalid",
               "未知 authorship 形（冒充真人署名形）进不了授权闭集")

    rc_s, code_s, _ = refuse("expert.define", dict(
        ae_base, attribution={"authorship": "synthetic_original"},
        applicableScopes=[]))
    checks.add("s1_09_scope_declaration_required%s" % tag,
               rc_s == 3 and code_s == "f100_scope_declaration_required",
               "适用范围声明是卡片准入要件（缺失不入店＝适用范围准确）")

    priv = card_args(expert_id="exp-priv", source_digests=source_digests)
    priv["items"][0]["readScope"] = "private"
    rc_p, code_p, _ = refuse("expert.define", priv)
    checks.add("s1_10_private_content_not_bindable%s" % tag,
               rc_p == 3 and code_p == "f100_private_content_not_bindable",
               "private 内容结构性不入包（私域不进商店可分发对象＝不公开"
               "私域蒸馏的包面）")

    live_codes = []
    for kind in ("live", "realtime_opinions", "online_feed",
                 "pinned_pack_live"):
        rc_g, code_g, _ = refuse("expert.define", dict(
            ae_base, attribution={"authorship": "synthetic_original"},
            grounding={"kind": kind}))
        live_codes.append((rc_g, code_g))
    checks.add("s1_11_grounding_closed_set_refuses_live%s" % tag,
               all(rc == 3 and code.startswith("f100_grounding_kind_refused:")
                   for rc, code in live_codes),
               "grounding 闭集只认 pinned_pack；live/realtime 形全部具名拒"
               "（%s）" % [c for _, c in live_codes])
    rc_r, code_r, _ = refuse("expert.define", dict(
        ae_base, attribution={"authorship": "synthetic_original"},
        grounding={"kind": "pinned_pack", "declaresRealTime": True}))
    checks.add("s1_12_declares_realtime_true_refused%s" % tag,
               rc_r == 3 and code_r == "f100_realtime_claim_refused",
               "declaresRealTime=True 具名拒（分身不冒真人实时意见的结构"
               "准入面）")

    # ---- S2 公开读取＋授权 fail-closed（货架面）----
    rc_f, payload_f = define(card_args("exp-firm", display="所内专家·乙"
                                       "（工程验证样本）", scope="firm",
                                       source_digests=source_digests))
    firm_defined = ok_result(payload_f)
    checks.add("s2_01_public_visible_firm_hidden%s" % tag,
               rc_f == 0 and firm_defined
               and firm_defined["cardScope"] == "firm",
               "firm 卡定义成功且 cardScope=firm")
    pub_list = ok_result(call_cli("expert.store_list", {}, cfg, tmp)[1])
    firm_list = ok_result(call_cli(
        "expert.store_list", {"authorizedReadScopes": ["firm"]}, cfg, tmp)[1])
    ids_pub = [c["expertId"] for c in (pub_list or {}).get("cards", [])]
    ids_firm = [c["expertId"] for c in (firm_list or {}).get("cards", [])]
    checks.add("s2_02_store_list_authorization_gate%s" % tag,
               "exp-syn-1" in ids_pub and "exp-firm" not in ids_pub
               and "exp-firm" in ids_firm and "exp-syn-1" in ids_firm,
               "store_list：public 恒可见且无 firm 卡（%s）；firm 显式授"
               "权后可见（%s）" % (ids_pub, ids_firm))
    obs["storeListIds"] = {"public": ids_pub, "firm": ids_firm}

    rc_rd, code_rd, _ = refuse("expert.store_read", {"expertId": "exp-firm"})
    rc_rc, code_rc, _ = refuse("expert.consult",
                               {"expertId": "exp-firm",
                                "query": "许可 合同 条款"})
    checks.add("s2_03_firm_gated_read_and_consult%s" % tag,
               rc_rd == 3 and code_rd == "f100_scope_mismatch"
               and rc_rc == 3 and code_rc == "f100_scope_mismatch",
               "未授权 firm 卡：store_read/consult 双双具名拒（授权在消费"
               "边界 fail-closed）")
    rc_pa, code_pa, _ = refuse("expert.store_list",
                               {"authorizedReadScopes": ["private"]})
    checks.add("s2_04_private_never_authorizable%s" % tag,
               rc_pa == 3
               and code_pa == "f100_scope_mismatch:"
                              "private_never_authorizable",
               "private 进授权集＝具名拒（private 永不可授权）")

    shelf_blob = json.dumps(pub_list, ensure_ascii=False) + json.dumps(
        ok_result(call_cli("expert.store_read",
                           {"expertId": "exp-syn-1"}, cfg, tmp)[1]),
        ensure_ascii=False)
    leaks = [SYN_TOPICS[t][2][:20] for t in SYN_TOPICS
             if SYN_TOPICS[t][2][:20] in shelf_blob]
    checks.add("s2_05_shelf_zero_bodies%s" % tag, not leaks,
               "store_list/store_read 输出字节级零条目正文（元数据只读货"
               "架；泄漏=%s）" % leaks)

    read = ok_result(call_cli("expert.store_read",
                              {"expertId": "exp-syn-1"}, cfg, tmp)[1])
    checks.add("s2_06_shelf_digest_binding_consistent%s" % tag,
               read and read["cardRef"]["digest"] == revised["cardDigest"]
               and read["cardRef"]["version"] == "2",
               "货架 cardRef.digest 与最新钉定值（v2）逐字相等（公开读取仍"
               "绑固定内容 hash；v1 历史绑定已由 s1_04 断言）")

    # ---- S3 实际任务消费（consult 面）----
    rankings = {}
    recall_ok = True
    byte_identical = True
    for tid in SYN_TOPICS:
        out1 = ok_result(consult({"expertId": "exp-syn-1",
                                  "query": SYN_TOPICS[tid][1],
                                  "topK": 1})[1])
        golden = {"it-%d" % (list(SYN_TOPICS).index(tid) * 3 + k)
                  for k in (1, 2, 3)}
        hits1 = (out1 or {}).get("hits", [])
        if not hits1 or hits1[0]["itemRef"]["itemId"] not in golden:
            recall_ok = False
        out2 = ok_result(consult({"expertId": "exp-syn-1",
                                  "query": SYN_TOPICS[tid][1],
                                  "topK": 1})[1])
        if json.dumps((out1 or {}).get("hits"), ensure_ascii=False,
                      sort_keys=True) != json.dumps(
                (out2 or {}).get("hits"), ensure_ascii=False, sort_keys=True):
            byte_identical = False
        rankings[tid] = [h["itemRef"]["itemId"] for h in hits1]
    checks.add("s3_01_golden_recall_at_1%s" % tag, recall_ok,
               "4 主题金标 recall@1=1.0（top1 恒落主题条目集；主题内 3 条"
               "近重复，逐字条目号不作金标）")
    checks.add("s3_02_two_runs_byte_identical%s" % tag, byte_identical,
               "同查询两跑命中逐字节相同＝确定性词面评分（零模型零随机）")
    obs["rankings"] = rankings

    consult_t2 = ok_result(consult({"expertId": "exp-syn-1",
                                    "query": SYN_TOPICS["t2"][1],
                                    "topK": 2})[1])
    nonlive = (consult_t2 or {}).get("nonLive", {})
    checks.add("s3_03_nonlive_declaration_verbatim%s" % tag,
               nonlive.get("declaresRealTime") is False
               and "不代表任何真人的实时意见" in nonlive.get("statement", ""),
               "应答恒携不冒真人实时意见声明（declaresRealTime=False＋"
               "statement 逐字含「不代表任何真人的实时意见」）")
    grounding = (consult_t2 or {}).get("grounding", {})
    checks.add("s3_04_grounding_pinned_pack%s" % tag,
               grounding.get("kind") == "pinned_pack"
               and grounding.get("packVersion") == 2
               and grounding.get("cardDigest") == revised["cardDigest"],
               "应答 grounding=pinned_pack＋packVersion=2＋cardDigest 与钉"
               "定值逐字相等（分身只据钉定包快照应答）")
    checks.add("s3_05_applicable_scopes_echoed%s" % tag,
               (consult_t2 or {}).get("applicableScopes")
               == ["工程合成验收场景"],
               "应答回显卡片适用范围声明（消费面始终可见边界）")

    abstain_codes = []
    for query in OUT_OF_SCOPE_QUERIES:
        rc_a2, code_a2, _ = refuse("expert.consult",
                                   {"expertId": "exp-syn-1",
                                    "query": query})
        abstain_codes.append((rc_a2, code_a2))
    checks.add("s3_06_out_of_scope_named_abstain%s" % tag,
               all(rc == 3 and code == "f100_out_of_scope_abstain"
                   for rc, code in abstain_codes),
               "零词面重叠查询×3 全部 f100_out_of_scope_abstain 具名弃答"
               "（分身不越界编造＝适用范围准确的结构面）")

    # ---- S4 来源回执和验证 ----
    log_path = state_root / "consult-log.jsonl"
    log_lines = [json.loads(l) for l in
                 log_path.read_text(encoding="utf-8").splitlines() if l]
    rid = consult_t2["receiptId"]
    line = next((e for e in log_lines if e.get("receiptId") == rid), None)
    checks.add("s4_01_receipt_persisted%s" % tag,
               line is not None
               and line.get("kind") == "expert-consult-receipt"
               and line.get("cardDigest") == revised["cardDigest"]
               and line.get("hitCount") == len(consult_t2["hits"]),
               "consult 回执落盘 consult-log.jsonl（receiptId/cardDigest/"
               "hitCount 与响应一致）")
    verdict = ok_result(call_cli("expert.verify_receipt",
                                 {"receiptId": rid}, cfg, tmp)[1])
    checks.add("s4_02_verify_receipt_pass%s" % tag,
               verdict and verdict["verdict"] == "PASS"
               and verdict["cardDigest"] == revised["cardDigest"]
               and verdict["items"] == [h["itemRef"]
                                        for h in consult_t2["hits"]],
               "verify_receipt 全量重算 PASS（逐命中 itemRef 与响应一致）")
    rc_unk, code_unk, _ = refuse("expert.verify_receipt",
                                 {"receiptId": "deadbeefdeadbeef"})
    checks.add("s4_03_unknown_receipt_named_refusal%s" % tag,
               rc_unk == 3 and code_unk == "f100_receipt_not_found",
               "未知回执具名拒不假 PASS")

    # 篡改/漂移负测（各自独立临时副本状态根，不动正本；s4_05 用全新
    # 副本——回执账未被污染，卡片漂移才能到达验签的 card 检查层）。
    tam_root = tmp / "tamper"
    tam_root.mkdir(parents=True, exist_ok=True)
    for name in ("experts.jsonl", "consult-log.jsonl"):
        (tam_root / name).write_text(
            (state_root / name).read_text(encoding="utf-8"),
            encoding="utf-8")
    tam_cfg = {"expert_state_root": str(tam_root)}
    tam_log = tam_root / "consult-log.jsonl"
    lines = tam_log.read_text(encoding="utf-8").splitlines()
    target = next(i for i, l in enumerate(lines)
                  if json.loads(l).get("receiptId") == rid)
    bad = json.loads(lines[target])
    bad["cardDigest"] = "0" * 64
    lines[target] = json.dumps(bad, ensure_ascii=False, sort_keys=True)
    tam_log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    rc_t, code_t, _ = refuse_cfg(tam_cfg, "expert.verify_receipt",
                                 {"receiptId": rid}, tmp)
    checks.add("s4_04_tampered_receipt_named_refusal%s" % tag,
               rc_t == 3 and code_t == "f100_receipt_tampered",
               "篡改回执账一行→receiptId 重算不符具名拒（验证路径不假 "
               "PASS；临时副本负测）")

    tam2_root = tmp / "tamper2"
    tam2_root.mkdir(parents=True, exist_ok=True)
    for name in ("experts.jsonl", "consult-log.jsonl"):
        (tam2_root / name).write_text(
            (state_root / name).read_text(encoding="utf-8"),
            encoding="utf-8")
    card_path = tam2_root / "experts.jsonl"
    rows = [json.loads(l) for l in
            card_path.read_text(encoding="utf-8").splitlines() if l]
    # 恰篡改被引 revision（v2）的行——回执钉的是 v2，篡改历史行不构成
    # 对该回执的漂移（追加只增不改下历史行仍是合法可回读版本）。
    trow = next(r for r in rows
                if r["expertId"] == "exp-syn-1" and r["revision"] == 2)
    trow["card"]["items"][0]["body"] += "篡改一字（SYNTHETIC tamper probe）"
    card_path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True)
                  for r in rows) + "\n", encoding="utf-8")
    tam2_cfg = {"expert_state_root": str(tam2_root)}
    rc_b, code_b, _ = refuse_cfg(tam2_cfg, "expert.store_read",
                                 {"expertId": "exp-syn-1"}, tmp)
    rc_c3, code_c3, _ = refuse_cfg(tam2_cfg, "expert.consult",
                                   {"expertId": "exp-syn-1",
                                    "query": SYN_TOPICS["t2"][1]}, tmp)
    rc_v3, code_v3, _ = refuse_cfg(tam2_cfg, "expert.verify_receipt",
                                   {"receiptId": rid}, tmp)
    checks.add("s4_05_card_tamper_refusals_all_faces%s" % tag,
               rc_b == 3 and code_b == "f100_card_digest_mismatch"
               and rc_c3 == 3 and code_c3 == "f100_card_digest_mismatch"
               and rc_v3 == 3
               and code_v3 == "f100_receipt_verify_failed:card_digest_drift",
               "篡改包正文→读取/消费/验签三面具名拒（含正文快照 hash 漂移"
               "现形；临时副本负测）")

    hit_refs = consult_t2["hits"][0]["sourceRefs"]

    def ref_digest_ok(ref):
        parts = ref["id"].split("-")  # syn-<tid>-<n>
        return ref.get("digest") == source_digests.get(
            (parts[1], int(parts[2])))

    digests_ok = all(ref_digest_ok(r) for r in hit_refs)
    checks.add("s4_06_source_refs_traceable%s" % tag,
               bool(hit_refs) and digests_ok,
               "命中 sourceRefs.digest 与盘上合成源文档 sha256 逐字相等"
               "（来源回执可回溯源文档）")
    obs["receipt"] = {"verdict": (verdict or {}).get("verdict"),
                      "hitCount": (verdict or {}).get("hitCount")}
    return obs


def refuse_cfg(cfg, method, args, tmp):
    rc, payload = call_cli(method, args, cfg, tmp)
    return rc, refuse_code(payload), payload


# ------------------------------------------------------------ S6 红线 --

def s6_redlines(checks: Checks, manuals_root: Path,
                persona_root: Path | None, tmp: Path):
    imports = set()
    for node in ast.walk(ast.parse(
            EXPERT_STORE.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            imports.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            imports.add((node.module or "").split(".")[0])
    bad = sorted((imports - ENGINE_ALLOWED_IMPORTS)
                 | (imports & NETWORK_MODULES))
    checks.add("s6_01_engine_import_closure", not bad,
               "expert_store import 闭集=%s（零 legal_cn_manuals＝manuals "
               "零引擎代码铁律侧·零 lcr/playbook＝不复制第二权威·零网络＝"
               "实时渠道在本面结构性不存在）" % sorted(imports))

    le_source = LEGAL_ENTRY.read_text(encoding="utf-8")
    groups = {}
    for node in ast.walk(ast.parse(le_source)):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name) \
                and node.targets[0].id.endswith("_METHODS"):
            names = []
            if isinstance(node.value, ast.Call):
                for elt in node.value.args:
                    if isinstance(elt, (ast.Set, ast.List, ast.Tuple)):
                        names = [e.value for e in elt.elts
                                 if isinstance(e, ast.Constant)]
            groups[node.targets[0].id] = names
    expert_group = list(groups.get("EXPERT_METHODS") or ())
    banned = ("publish", "enable", "distill", "observe", "install")
    checks.add("s6_02_expert_methods_frozen_no_write_face",
               sorted(expert_group) == sorted(EXPERT_FIVE)
               and not any(b in m for m in expert_group for b in banned),
               "EXPERT_METHODS 恰冻结五方法 %s（无 publish/enable/distill/"
               "observe 写面）" % sorted(expert_group))
    manual_tokens = {m for names in groups.values() for m in names
                     if m.startswith("manual.")}
    playbook_group = set(groups.get("HARNESS_PLAYBOOK_METHODS") or ())
    checks.add("s6_03_existing_public_channels_present",
               manual_tokens == MANUAL_QUARTET
               and playbook_group == PLAYBOOK_TRIO,
               "既有公开消费通道在位＝MANUAL_METHODS 恰读侧四方法＋"
               "HARNESS_PLAYBOOK_METHODS 恰三方法（专家面不复制第二权威）")

    impl_hashes = {}
    for path in sorted((REPO_ROOT / "implementation").rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            impl_hashes.setdefault(sha256_file(path),
                                   str(path.relative_to(REPO_ROOT)))
    manuals_hashes = {}
    for path in sorted(manuals_root.rglob("*")):
        if path.is_file() and ".git" not in path.parts:
            manuals_hashes.setdefault(sha256_file(path),
                                      str(path.relative_to(manuals_root)))
    overlap_m = sorted(set(impl_hashes) & set(manuals_hashes))
    checks.add("s6_04_install_surface_zero_manuals_overlap", not overlap_m,
               "implementation/ 实物树 %d 文件 × manuals 仓 %d 文件 sha256 "
               "零重叠（安装包不带 manuals 内容）"
               % (len(impl_hashes), len(manuals_hashes)))
    if persona_root is not None:
        persona_hashes = {sha256_file(p) for p in persona_root.rglob("*")
                          if p.is_file() and ".git" not in p.parts}
        overlap_p = sorted(set(impl_hashes) & persona_hashes)
        persona_note = "README-only"
    else:
        overlap_p = []
        persona_note = "缺席"
    checks.add("s6_05_install_surface_zero_persona_overlap", not overlap_p,
               "implementation/ 实物树 × persona 仓（%s）sha256 零重叠"
               "（安装包不带 persona 内容）" % persona_note)
    # 仓面零字节改动复核（S6 树扫描只读）。
    dirty = subprocess.run(["git", "status", "--porcelain"],
                           cwd=str(manuals_root),
                           capture_output=True, text=True).stdout.strip()
    checks.add("s6_06_manuals_readonly_after_scan", dirty == "",
               "manuals 检出树扫描前后 git status 零改动（只读消费复核）")


# ------------------------------------------------------------ main --

def normalized_digest(obs: dict) -> str:
    return sha256_text(json.dumps(obs, ensure_ascii=False, sort_keys=True))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", action="append", default=[],
                    choices=["desktop", "selfhost"])
    ap.add_argument("--manuals-checkout", default=None)
    ap.add_argument("--persona-checkout", default=None)
    args = ap.parse_args()
    profiles = args.profile or ["desktop", "selfhost"]

    checks = Checks()
    manuals_root = manuals_checkout(args.manuals_checkout)
    persona_root = persona_checkout(args.persona_checkout)
    s0_pins(checks, manuals_root, persona_root)
    if not checks.all_passed:
        print("RECON_FAILED pin drift — exit 2")
        return 2

    profile_results = {}
    with tempfile.TemporaryDirectory(prefix="f100-expert-recon-") as tmp:
        tmp_root = Path(tmp)
        for profile in profiles:
            profile_results[profile] = run_profile(
                profile, checks, manuals_root, persona_root,
                tmp_root / profile)
        s6_redlines(checks, manuals_root, persona_root, tmp_root)
    if len(profiles) > 1:
        digests = {p: normalized_digest(obs)
                   for p, obs in profile_results.items()}
        distinct = sorted(set(digests.values()))
        checks.add("x01_cross_profile_normalized_digest_equal",
                   len(distinct) == 1,
                   "双 profile 归一化 digest %s（治理面与宿主形态无关）"
                   % [d[:12] for d in distinct])
    else:
        checks.add("x01_cross_profile_normalized_digest_equal", False,
                   "单 profile 跑（--profile %s）：无跨 profile 断言；"
                   "验收形态=双 profile 全跑" % profiles[0])

    verdict = "RECON_OK" if checks.all_passed else "RECON_FAILED"
    try:
        subject_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT),
            capture_output=True, text=True).stdout.strip()
    except OSError:
        subject_commit = None
    result = {
        "recon": "f100-expert-content",
        "obligation": "F100",
        "unit": "W5-U04",
        "verdict": verdict,
        "acceptance": "专家内容授权/来源/适用范围准确；分身不冒真人实时意见",
        "rulings": {
            "ruling_7": "00-总协调.md:252 合成样本先行；Observer 不启用",
            "ruling_13_19": "00-总协调.md:254 W5 专家内容统一合成先行，"
                            "真实设施 v2 商业化时补",
        },
        "red_lines": {
            "three_tier_distribution":
                "安装包不带 manuals/persona 内容（s6_04/s6_05 实物树 "
                "sha256 零重叠）；private 内容不入包不进商店（s1_10）＋"
                "private 永不可授权（s2_04）＝不公开私域蒸馏",
            "controlled_channel":
                "专家面零 manuals/playbook import（s6_01）；公开消费只经"
                "既有冻结通道（s6_03）",
            "nonlive":
                "分身不冒真人实时意见＝结构面：grounding 闭集只认 "
                "pinned_pack（s1_11）＋declaresRealTime=True 具名拒"
                "（s1_12）＋应答恒携不冒真人声明（s3_03）",
        },
        "manuals_baseline": {"checkout": str(manuals_root),
                             "form": "只读消费基线（HEAD 记录＋工作树干净）"},
        "persona_absence": {"checkout": str(persona_root)
                            if persona_root else None,
                            "form": "README-only（可选件缺省形态）"},
        "subject_commit": subject_commit,
        "profile_digests": {p: normalized_digest(obs)
                            for p, obs in profile_results.items()},
        "checks": checks.items,
        "passed": checks.passed_count, "total": len(checks.items),
    }
    for base in (REPO_ROOT / "evidence" / "F100",
                 REPO_ROOT / "docs" / "construction" / "evidence" / "F100"):
        for profile in profiles:
            out_dir = base / profile
            out_dir.mkdir(parents=True, exist_ok=True)
            payload = dict(result)
            payload["profile"] = profile
            payload["profile_result"] = profile_results[profile]
            (out_dir / "f100-expert-content-recon.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=1,
                           sort_keys=True), encoding="utf-8")
    print("%s %d/%d checks — exit %d" %
          (verdict, checks.passed_count, len(checks.items),
           0 if checks.all_passed else 1))
    return 0 if checks.all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
