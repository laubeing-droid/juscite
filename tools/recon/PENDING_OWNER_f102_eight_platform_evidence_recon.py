# -*- coding: utf-8 -*-
"""F102 商标/电商取证八平台（合成先行）验收对账（PENDING_OWNER 版，
工单 W5-U05）。

06 行 V7-102/F102（v2；owner=product；UI_HOST_OR_NEW_PRODUCT；B5；
desktop/selfhost 双实例）acceptance＝八平台范围冻结真实采集出处/时间/
凭证；失败不假造证据。legacy_semantic_links F65（浏览器 CDP 遥控）/
F96（技能执行合同）。00-总协调 §6.1 裁决#13-19（00-总协调.md:254）：
W5 七项商业/基建（含八平台）统一合成先行，真实平台采集 v2 商业化时
补——本波唯一执行态；E17 EvidenceAttempt 语义沿 W4-U40 先例（有真实
回执才记取得，失败路径轨迹/凭证恒 None）。

分段（每 profile 全量 24 检；全程进程内合成目标＋注入假时钟，零真实
外联零 %APPDATA%）：
  S1 面与硬依赖钉定：台账 prerequisites 五行（E11/E12/E17/E21/E24）
     VERIFIED 亲读＋E10 行如实记录（IMPLEMENTING＝宿主级管理员轮收口
     挂 W5-U01 具名回收点，本面零网络零外联不消费 E10 扫描面——S6A
     AST 零网络直接证明该面）；acceptance 向量逐字对账；legacy links
     （F65/F96）行在案与状态如实记录（F65 NOT_RUN/F96 VERIFIED，本面
     只记名不消费）；legal_entry 零接线（UI_HOST_OR_NEW_PRODUCT 不冒
     已有业务入口）；八平台清单与 LexLex 源件冻结对表（竞品情报 2026-
     10-11 取证件，sha256 记录）。
  S2 八平台闭集冻结：闭集恰 8 成员（id/名称/类别/登录要求）＋默认采
     集序（电商→社交→百度→CNIPA 收尾）；闭集外平台具名拒零证据；模
     块零 URL 字面量（真实端点禁编 URL，W4-U40 纪律）。
  S3 合成采集目标端到端正道：全 8 平台 EVIDENCE_SEALED（出处=合成目
     标具名 provider＋synthetic=True＋usable_as_real_platform_evidence
     =false；retrieved_at 出自回执；seal 可重算；trajectory 绑回执栅
     格 sha）；三拼接路径（单片/两片/多片）齐跑；拼接保真（整幅可由
     目标逐行真值重组）＋页眉/页号带墨迹对金标 bbox（E12 纪律）＋页
     号 1..N 连续；PDF 结构（页对象数=页清单数、trailer 无 /ID 无时
     间戳无 /Info、%%EOF）＋同参数两跑同字节同 seal。
  S4 失败不假造证据（E17 EvidenceAttempt 语义）：适配器缺席（结构性
     不可达——真实端点禁编 URL 客户端未建）；登录客户端预检（零请求
     发出）；间隔预检（零请求发出）；目标侧 WAF 拦截回执（检索面）→
     F102_WAF_INTERCEPT；回执残缺→F102_RECEIPT_INVALID；管线中段传输
     异常→F102_CAPTURE_FAILED 零部分 PDF；全账不变量＝值字段只在
     EVIDENCE_SEALED 非空；RECOVERY_POINT 具名（真实平台采集 v2 商业
     化时补）。
  S6 纪律全域＋合成边界＋冻结稳定：产品面 AST 导入闭集恰
     {__future__,hashlib,json,time,zlib} 零网络/子进程/文件 I/O；合成
     回执出处具名全域在账；00-总协调 裁决#13-19 行含『八平台＋统一合
     成先行』；冻结面 sha256 前后相等。

用法（juscite worktree 根 cwd）：
  python -X utf8 tools/recon/PENDING_OWNER_f102_eight_platform_evidence_recon.py --profile desktop --profile selfhost

--profile 可重复（action=append，f33/f74 工具同款）；重复即逐 profile
依序全量跑各 24 检并各写证据；缺省=desktop。
exit 0＝全部断言过（RECON_OK）；证据写 evidence/F102/<profile>/ 各
{json,md} 一份。全程合成材料（进程内合成目标＋注入假时钟＋临时目录，
零真实外联零 %APPDATA% 零 oc28 触碰）。
"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

RUN_DATE = time.strftime("%Y%m%d")
REPO_ROOT = Path(__file__).resolve().parents[2]
PRODUCT = REPO_ROOT / "implementation" / "python" / "platform_evidence.py"
LEGAL_ENTRY = REPO_ROOT / "implementation" / "python" / "legal_entry.py"
LEDGER = REPO_ROOT / "docs" / "construction" / "acceptance-ledger.csv"
COORD = REPO_ROOT / "docs" / "construction" / "00-总协调.md"


def _find_lexlex_skill() -> Path:
    """向上定位竞品情报取证件（主树/worktree 深度不同均可达）。"""
    marker = (Path("竞品情报") / "2026-10-11" / "evidence" / "LexLex-inno"
              / r"%USERPROFILE\.legalclaw" / "skills"
              / "trademark-evidence-collection" / "SKILL.md")
    for base in [REPO_ROOT] + list(REPO_ROOT.parents):
        candidate = base / marker
        if candidate.is_file():
            return candidate
    return REPO_ROOT / marker


LEXLEX_SKILL = _find_lexlex_skill()

# 06 V7-102 行 acceptance 向量（逐字；与台账 F102 两行 assertion 对账）。
ACCEPTANCE_VECTOR = "八平台范围冻结真实采集出处/时间/凭证；失败不假造证据"

# 台账行（工单明文 prerequisites＋legacy_semantic_links）。
PREREQ_VERIFIED = ("E11", "E12", "E17", "E21", "E24")
PREREQ_RECORDED = ("E10",)  # 宿主级管理员轮挂 W5-U01 回收点，IMPLEMENTING 如实记录
LEGACY_ROWS = ("F65-desktop", "F65-selfhost",
               "F96-desktop", "F96-selfhost")

sys.path.insert(0, str(REPO_ROOT / "implementation" / "python"))
for _name in ("platform_evidence",):
    sys.modules.pop(_name, None)
import platform_evidence as pe  # noqa: E402

SYNTH_SESSION = "synthetic-session-token-not-real"
CLOCK_START = 1000.0


def sha256_file(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Checks:
    def __init__(self):
        self.items: list = []

    def add(self, check_id: str, ok: bool, detail: str) -> bool:
        self.items.append(
            {"id": check_id, "status": "PASS" if ok else "FAIL",
             "detail": detail})
        print("[%s] %s — %s" % ("PASS" if ok else "FAIL", check_id, detail))
        return ok

    @property
    def all_passed(self) -> bool:
        return all(item["status"] == "PASS" for item in self.items)

    @property
    def passed_count(self) -> int:
        return sum(1 for item in self.items if item["status"] == "PASS")


class World:
    """进程内合成世界：合成目标＋注入假时钟＋取证会话。"""

    def __init__(self, start: float = CLOCK_START):
        self.now = start
        self.target = pe.SyntheticCaptureTarget(lambda: self.now)
        self.session = pe.PlatformEvidenceSession(
            self.target, lambda: self.now)

    def tick(self, seconds: float = 5.0) -> None:
        self.now += seconds

    def capture(self, platform: str, keyword: str = "大华",
                session_token=None) -> dict:
        """session_token 逐字透传（不自动补 session——负测需真实缺省）。"""
        return self.session.capture(platform, keyword,
                                    session_token=session_token)


def _value_fields_none(attempt: dict) -> bool:
    return all(attempt.get(key) is None for key in (
        "trajectory", "credential", "pdf_sha256", "page_manifest",
        "pdf_bytes", "retrieved_at"))


def _capture_all(world: World, keyword: str = "大华") -> dict:
    attempts = {}
    for pid in pe.DEFAULT_CAPTURE_ORDER:
        token = SYNTH_SESSION if pe.platform_requires_login(pid) else None
        attempts[pid] = world.capture(pid, keyword,
                                      session_token=token)
        world.tick()
    return attempts


def _ledger_rows() -> dict:
    with open(LEDGER, encoding="utf-8-sig", newline="") as handle:
        return {row[0]: row for row in csv.reader(handle)}


# ---------------------------------------------------------------------- #
# S1 面与硬依赖钉定
# ---------------------------------------------------------------------- #

def section_s1(checks: Checks, rows: dict) -> dict:
    verified = {ob: (rows.get(ob) or [""] * 18)[15]
                for ob in PREREQ_VERIFIED}
    checks.add(
        "S1A_prereq_rows_verified_and_e10_recorded",
        all(status == "VERIFIED" for status in verified.values())
        and rows.get("E10", [""] * 18)[15] == "IMPLEMENTING",
        "台账亲读：prerequisites E11/E12/E17/E21/E24 全 VERIFIED（06 行 "
        "construction_prerequisites 中已闭合五行）——实测 %s；E10 行如实"
        "记录=IMPLEMENTING（宿主级管理员轮收口挂 W5-U01 具名回收点，本波"
        "不提供管理员通道主控裁决在案；本面零网络零外联不消费 E10 扫描面"
        "——S6A AST 零网络直接证明该面，B5 后续行不阻本行先例 W4-U58）"
        % " ".join("%s=%s" % kv for kv in sorted(verified.items())))
    assertion_d = rows.get("F102-desktop", [""] * 18)[2]
    assertion_s = rows.get("F102-selfhost", [""] * 18)[2]
    checks.add(
        "S1B_acceptance_vector_verbatim",
        assertion_d == ACCEPTANCE_VECTOR and assertion_s
        == ACCEPTANCE_VECTOR,
        "06 V7-102 acceptance 向量逐字对账（台账 F102-desktop/"
        "F102-selfhost assertion 列）＝%s" % ACCEPTANCE_VECTOR)
    legacy = {ob: (rows.get(ob) or [""] * 18)[15] for ob in LEGACY_ROWS}
    checks.add(
        "S1C_legacy_links_present_recorded",
        all(rows.get(ob) is not None for ob in LEGACY_ROWS)
        and legacy["F65-desktop"] == "NOT_RUN"
        and legacy["F65-selfhost"] == "NOT_RUN",
        "legacy_semantic_links 行在案＋状态如实记录（F65 浏览器 CDP 遥控"
        "=%s/%s＝B5 未施工本面只记名不消费；F96 技能执行合同=%s/%s；零"
        "消费由 S6A 导入闭集证明）"
        % (legacy["F65-desktop"], legacy["F65-selfhost"],
           legacy["F96-desktop"], legacy["F96-selfhost"]))
    text = LEGAL_ENTRY.read_text(encoding="utf-8")
    refs = [marker for marker in ("platform_evidence", "f102")
            if marker in text.lower()]
    checks.add(
        "S1D_legal_entry_zero_wiring",
        not refs,
        "legal_entry 零 F102 接线（UI_HOST_OR_NEW_PRODUCT：不冒已有业务"
        "入口、不创第二业务入口、不创第二 Agent loop）；命中=%s"
        % (refs or "无"))
    names = [entry[1] for entry in pe.EIGHT_PLATFORMS]
    source_sha = None
    source_ok = False
    # 源件名称匹配核心（源件 cnipa 行为『国家知识产权局 (CNIPA)』半角
    # 括号写法——按核心词对表，冻结面全角写法为产品侧规范化）。
    source_names = {entry[0]: entry[1].replace("（CNIPA）", "")
                    for entry in pe.EIGHT_PLATFORMS}
    if LEXLEX_SKILL.is_file():
        source_text = LEXLEX_SKILL.read_text(encoding="utf-8")
        source_sha = sha256_file(LEXLEX_SKILL)
        source_ok = all(name in source_text
                        for name in source_names.values()) \
            and "CNIPA" in source_text
    checks.add(
        "S1E_source_freeze_eight_platforms",
        source_ok,
        "八平台清单与 LexLex 源件冻结对表（trademark-evidence-collection "
        "SKILL.md『默认全平台搜索』清单，sha256=%s…）：8/8 平台核心名命中"
        "＋闭集成员=%s（『八平台』量词出处=authority/06 V7-102 行『CNIPA+"
        "淘宝京东等八平台』；源件为逐项枚举八项）"
        % ((source_sha or "MISSING")[:8], "、".join(names)))
    return {"platform_evidence.py": sha256_file(PRODUCT),
            "legal_entry.py": sha256_file(LEGAL_ENTRY)}


# ---------------------------------------------------------------------- #
# S2 八平台闭集冻结
# ---------------------------------------------------------------------- #

EXPECTED_PLATFORMS = (
    ("cnipa", "国家知识产权局（CNIPA）", "official_trademark_office", True),
    ("baidu", "百度", "search_engine", False),
    ("taobao", "淘宝", "ecommerce", False),
    ("tmall", "天猫", "ecommerce", False),
    ("jd", "京东", "ecommerce", True),
    ("pdd", "拼多多", "ecommerce", True),
    ("douyin", "抖音", "social_media", True),
    ("xhs", "小红书", "social_media", True),
)


def section_s2(checks: Checks) -> None:
    checks.add(
        "S2A_closed_set_exactly_eight_members",
        pe.EIGHT_PLATFORMS == EXPECTED_PLATFORMS,
        "八平台范围闭集冻结为合成常量（裁决#13-19）：恰 8 成员 id/名称/"
        "类别/登录要求逐位相等（CNIPA/百度/淘宝/天猫/京东/拼多多/抖音/"
        "小红书；登录要求沿源件参考表）")
    checks.add(
        "S2B_default_capture_order_frozen",
        pe.DEFAULT_CAPTURE_ORDER == ("taobao", "tmall", "jd", "pdd",
                                     "douyin", "xhs", "baidu", "cnipa"),
        "默认采集序冻结（源件反爬攻略：电商平台→社交媒体→百度→CNIPA 收"
        "尾——CNIPA SSO 手动登录易触发 WAF 放最后）＝%s"
        % ",".join(pe.DEFAULT_CAPTURE_ORDER))
    world = World()
    attempt = world.capture("wechat")
    closed_ok = attempt["status"] == "F102_PLATFORM_UNKNOWN" \
        and _value_fields_none(attempt)
    checks.add(
        "S2C_unknown_platform_named_reject_no_evidence",
        closed_ok,
        "闭集外平台具名拒（wechat→typed F102_PLATFORM_UNKNOWN；E17 语义"
        "轨迹/凭证/证据恒 None）")
    source = PRODUCT.read_text(encoding="utf-8")
    url_markers = [marker for marker in ("http://", "https://", "www.",
                                         ".com/", ".cn/")
                   if marker in source]
    checks.add(
        "S2D_module_zero_url_literals",
        not url_markers,
        "产品模块零 URL 字面量（真实平台端点禁编 URL——W4-U40 纪律，端点"
        "属商业化适配器工单随 RECOVERY_POINT）；命中=%s"
        % (url_markers or "无"))


# ---------------------------------------------------------------------- #
# S3 合成采集目标端到端正道
# ---------------------------------------------------------------------- #

def section_s3(checks: Checks) -> None:
    world = World()
    attempts = _capture_all(world)
    sealed = all(a["status"] == "EVIDENCE_SEALED"
                 for a in attempts.values())
    bindings_ok = sealed
    if sealed:
        for pid, a in attempts.items():
            if not a["synthetic"] or a["usable_as_real_platform_evidence"]:
                bindings_ok = False
            if a["source"]["provider"] != pe.SYNTHETIC_PROVIDER_ID:
                bindings_ok = False
            if a["credential"]["provider"] != pe.SYNTHETIC_PROVIDER_ID:
                bindings_ok = False
            if len(a["credential"]["seal"]) != 64:
                bindings_ok = False
            if a["pdf_sha256"] != hashlib.sha256(a["pdf_bytes"]) \
                    .hexdigest():
                bindings_ok = False
            if not a["trajectory"] or not a["page_manifest"]:
                bindings_ok = False
    checks.add(
        "S3A_all_eight_sealed_with_bindings",
        bindings_ok,
        "全 8 平台（默认采集序、注入假时钟间隔 %ds）EVIDENCE_SEALED：出"
        "处=合成目标具名 provider=%s＋synthetic=True＋"
        "usable_as_real_platform_evidence=false；retrieved_at 出自回执"
        "（非墙钟）；seal 64hex；pdf_sha256=PDF 字节重算相等；trajectory/"
        "page_manifest 非空（出处/时间/凭证绑定——合成先行形态，真实平"
        "台采集商业化时补）" % (pe.MIN_INTERVAL_S,
                                pe.SYNTHETIC_PROVIDER_ID))
    slices = {pid: len(attempts[pid]["trajectory"]) for pid in attempts}
    paths_ok = (slices["baidu"] == 1 and slices["jd"] == 2
                and slices["cnipa"] == 3
                and all(slices[pid] >= 1 for pid in slices))
    checks.add(
        "S3B_three_stitch_paths_covered",
        paths_ok,
        "三拼接路径齐跑（源件管线：≤10000px 单片/10000-20000px 两片底对"
        "齐重叠裁切/>20000px 多片顺序＋末片底对齐）——逐平台片数=%s"
        % json.dumps(slices, ensure_ascii=False))
    fidelity_ok = True
    gold_ok = True
    target = world.target
    for pid in ("baidu", "jd", "cnipa"):
        scaled = pe.content_height_scaled_of(pid)
        rebuild = b"".join(target.row_at(pid, "大华", y)
                           for y in range(scaled))
        manifest, rasters = pe._split_pages(rebuild)
        if [p["page_raster_sha256"] for p in manifest] != \
                [p["page_raster_sha256"]
                 for p in attempts[pid]["page_manifest"]]:
            fidelity_ok = False
        attempt = attempts[pid]
        if [p["page_no"] for p in attempt["page_manifest"]] != \
                list(range(1, len(attempt["page_manifest"]) + 1)):
            gold_ok = False
        for page in attempt["page_manifest"]:
            if page["gold_version"] != pe.PAGE_BBOX_GOLD_VERSION:
                gold_ok = False
            bx0, by0, bx1, by1 = page["number_band_bbox"]
            page_index = page["page_no"] - 1
            raw = rasters[page_index][0]
            width = rasters[page_index][1]
            band = raw[by0 * width:by1 * width]
            margin = raw[(by0 - 1) * width:by0 * width]
            if band != b"\x00" * len(band) or margin != b"\xff" * width:
                gold_ok = False
        if rebuild[:pe.HEADER_ROWS * pe.RASTER_W] != \
                b"\x00" * (pe.HEADER_ROWS * pe.RASTER_W):
            fidelity_ok = False
    checks.add(
        "S3C_stitch_fidelity_and_page_bbox_gold",
        fidelity_ok and gold_ok,
        "拼接保真＋页号 bbox 金标（E12 纪律版本沿袭 %s）：整幅可由目标逐"
        "行真值重组（重叠裁切正确性，baidu/jd/cnipa 三路径 sha 全等）；"
        "页眉标记带（黑）＋下缘白行在位；逐页页号 1..N 连续＋gold_version"
        " 在账＋页号标记带金标 bbox 行全黑＋上缘留白行全白"
        % pe.PAGE_BBOX_GOLD_VERSION)
    det_a = World()
    det_b = World()
    run_a = det_a.capture("cnipa", session_token=SYNTH_SESSION)
    run_b = det_b.capture("cnipa", session_token=SYNTH_SESSION)
    attempt_a = attempts["cnipa"]
    pdf = attempt_a["pdf_bytes"]
    trailer_at = pdf.find(b"trailer\n<<")
    trailer = pdf[trailer_at:pdf.find(b"startxref", trailer_at)]
    structure_ok = (
        pdf.startswith(b"%PDF-1.4")
        and pdf.count(b"/Type /Page ") == len(attempt_a["page_manifest"])
        and b"/Root 1 0 R" in trailer
        and all(banned not in trailer for banned in
                (b"/ID", b"/CreationDate", b"/ModDate", b"/Info"))
        and b"/CreationDate" not in pdf[:trailer_at]
        and pdf.rstrip().endswith(b"%%EOF"))
    determinism_ok = (
        run_a["status"] == "EVIDENCE_SEALED"
        and run_b["status"] == "EVIDENCE_SEALED"
        and run_a["pdf_bytes"] == run_b["pdf_bytes"]
        and run_a["credential"]["seal"] == run_b["credential"]["seal"])
    checks.add(
        "S3D_pdf_structure_and_determinism",
        structure_ok and determinism_ok,
        "最小确定性 PDF（DeviceGray FlateDecode，E12 纪律：无 /ID 无时间"
        "戳无 /Info；trailer 结构面核验非压缩流字节）＋同参数独立两跑 "
        "PDF 逐字节同＋seal 同（SAME_SEED_SAME_BYTES）；页对象数=%d=页清"
        "单数" % len(attempt_a["page_manifest"]))


# ---------------------------------------------------------------------- #
# S4 失败不假造证据（E17 EvidenceAttempt 语义）
# ---------------------------------------------------------------------- #

def section_s4(checks: Checks) -> list:
    failures: list = []
    world = World()
    world.session.transport = None
    absent = world.capture("taobao")
    failures.append(absent)
    checks.add(
        "S4A_adapter_absent_structurally_unreachable",
        absent["status"] == "F102_ADAPTER_ABSENT"
        and _value_fields_none(absent),
        "平台适配器缺席＝结构性不可达（typed F102_ADAPTER_ABSENT；真实端"
        "点禁编 URL 客户端未建不可能自采——W4-U40 同构；E17 值恒 None）")

    world2 = World()
    ok_first = world2.capture("taobao")
    counters_before = (world2.target.measure_count,
                       world2.target.fetch_count)
    login = world2.capture("jd", session_token=None)
    counters_after = (world2.target.measure_count,
                      world2.target.fetch_count)
    failures.append(login)
    checks.add(
        "S4B_login_precheck_zero_fetch",
        ok_first["status"] == "EVIDENCE_SEALED"
        and login["status"] == "F102_LOGIN_REQUIRED"
        and _value_fields_none(login)
        and counters_before == counters_after,
        "需登录平台无 session＝客户端预检具名拒（F102_LOGIN_REQUIRED，源"
        "件反爬攻略：不空手请求）——零请求发出（目标计数前后相等 %s=%s）"
        "＋目标侧同闸防线可达（S4D 族直连在测）"
        % (counters_before, counters_after))

    pace = world2.capture("tmall")
    counters_pace = (world2.target.measure_count,
                     world2.target.fetch_count)
    failures.append(pace)
    checks.add(
        "S4C_pacing_precheck_zero_fetch",
        pace["status"] == "F102_PACING_VIOLATED"
        and _value_fields_none(pace)
        and counters_after == counters_pace,
        "同刻连发＝客户端间隔预检具名拒（F102_PACING_VIOLATED，反爬攻略"
        "间隔 %ds）——零请求发出（目标计数 %s 不动）"
        % (pe.MIN_INTERVAL_S, counters_pace))

    world3 = World()
    direct1 = world3.target.measure("tmall", "大华", None)
    world3.tick(1)
    direct2 = world3.target.measure("tmall", "大华", None)
    waf_gate_ok = not direct1.get("blocked") \
        and direct2.get("blocked") \
        and direct2.get("reason") == "waf_rate_limit"

    class WafTransport:
        def __init__(self, inner):
            self.inner = inner

        def measure(self, *args, **kwargs):
            return {"provider": pe.SYNTHETIC_PROVIDER_ID, "kind": "measure",
                    "synthetic": True, "blocked": True,
                    "reason": "waf_rate_limit"}

        def fetch_slice(self, *args, **kwargs):
            return self.inner.fetch_slice(*args, **kwargs)

    sess_waf = pe.PlatformEvidenceSession(
        WafTransport(pe.SyntheticCaptureTarget(lambda: world3.now)),
        lambda: world3.now)
    waf = sess_waf.capture("taobao", "大华")
    failures.append(waf)
    checks.add(
        "S4D_waf_intercept_blocked_receipt_no_evidence",
        waf_gate_ok and waf["status"] == "F102_WAF_INTERCEPT"
        and _value_fields_none(waf),
        "目标侧 WAF 闸（检索面：同平台两次检索间隔 < %ds→waf_rate_limit"
        " 回执；源件反爬攻略 CNIPA 频繁请求触发 WAF）＋被拦回执进管线→"
        "typed F102_WAF_INTERCEPT 值恒 None（被拦不造假证据）"
        % pe.MIN_INTERVAL_S)

    class BadTransport:
        def measure(self, *args, **kwargs):
            return {"kind": "measure", "synthetic": True,
                    "retrieved_at": "2026-10-22T00:00:00Z",
                    "content_height": 3580}  # 缺 provider

        def fetch_slice(self, *args, **kwargs):
            raise AssertionError("unreachable")

    sess_bad = pe.PlatformEvidenceSession(BadTransport(),
                                          lambda: world3.now)
    invalid = sess_bad.capture("baidu", "大华")
    failures.append(invalid)

    class HalfTransport:
        def __init__(self, inner):
            self.inner = inner
            self.calls = 0

        def measure(self, *args, **kwargs):
            return self.inner.measure(*args, **kwargs)

        def fetch_slice(self, *args, **kwargs):
            self.calls += 1
            if self.calls >= 2:
                raise OSError("synthetic-transport-failure")
            return self.inner.fetch_slice(*args, **kwargs)

    sess_half = pe.PlatformEvidenceSession(
        HalfTransport(pe.SyntheticCaptureTarget(lambda: world3.now)),
        lambda: world3.now)
    failed = sess_half.capture("jd", "大华", session_token=SYNTH_SESSION)
    failures.append(failed)
    checks.add(
        "S4E_receipt_invalid_and_midpipeline_failure_no_partial",
        invalid["status"] == "F102_RECEIPT_INVALID"
        and _value_fields_none(invalid)
        and failed["status"] == "F102_CAPTURE_FAILED"
        and _value_fields_none(failed),
        "回执残缺（缺 provider）→typed F102_RECEIPT_INVALID；管线中段传"
        "输异常（两片路径第二片 OSError）→typed F102_CAPTURE_FAILED——"
        "两者值恒 None 零部分 PDF（失败不假造证据：绝不生成部分/合成证据"
        "条目）")

    world4 = World()
    sequence = [
        world4.capture("wechat"),
        world4.capture("taobao", ""),
    ]
    world4.tick()
    sequence.append(world4.capture("jd", session_token=None))  # 未登录
    sequence.append(world4.capture("baidu", "大华"))           # 正道
    sealed_seen = [a for a in sequence
                   if a["status"] == "EVIDENCE_SEALED"]
    invariant_ok = all(_value_fields_none(a) for a in sequence
                       if a["status"] != "EVIDENCE_SEALED") \
        and all(a["trajectory"] is not None and a["credential"] is not None
                and a["pdf_sha256"] is not None
                and a["page_manifest"] is not None
                for a in sealed_seen)
    failures.extend(a for a in sequence
                    if a["status"] != "EVIDENCE_SEALED")
    checks.add(
        "S4F_e17_values_bearing_only_sealed_invariant",
        invariant_ok and len(sealed_seen) == 1,
        "E17 EvidenceAttempt 全账不变量（W4-U40 先例逐字沿用）：值字段"
        "（trajectory/credential/pdf_sha256/page_manifest/pdf_bytes/"
        "retrieved_at）只在 EVIDENCE_SEALED 非空——混序五连采实测（闭集"
        "外/关键词缺/未登录/正道）=%s"
        % ",".join(a["status"] for a in sequence))
    recovery = pe.RECOVERY_POINT
    checks.add(
        "S4G_recovery_point_named",
        "v2 商业化时补" in recovery and "禁编 URL" in recovery
        and "E24" in recovery,
        "真实平台采集回收点具名（模块 RECOVERY_POINT 常量）：%s"
        % recovery)
    return failures


# ---------------------------------------------------------------------- #
# S6 纪律全域＋合成边界＋冻结稳定
# ---------------------------------------------------------------------- #

def product_face_facts(path: str) -> dict:
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    allowed = {"__future__", "hashlib", "json", "time", "zlib"}
    imports: set = set()
    calls: list = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0]
                           for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            calls.append(node.func.id)
    return {"imports": imports, "calls": calls}


def section_s6(checks: Checks, faces_before: dict) -> None:
    facts = product_face_facts(str(PRODUCT))
    allowed = {"__future__", "hashlib", "json", "time", "zlib"}
    banned_calls = [name for name in ("print", "open") if name in
                    facts["calls"]]
    checks.add(
        "S6A_ast_import_closed_set_zero_io",
        facts["imports"] <= allowed and not banned_calls,
        "产品面 AST：导入闭集恰 {%s}（越界=%s）＋零 print/open 调用（%"
        "s）——零网络零子进程零文件 I/O（合成先行零真实外联；E10 扫描面"
        "不适用之直接证明）"
        % (",".join(sorted(allowed)),
           facts["imports"] - allowed or "无",
           "命中=" + ",".join(banned_calls) if banned_calls else "零命中"))
    world = World()
    measure = world.target.measure("baidu", "大华", None)
    world.tick(1)
    slice_receipt = world.target.fetch_slice("baidu", "大华", None, 1, 0,
                                             10)
    receipts_named = (
        measure.get("provider") == pe.SYNTHETIC_PROVIDER_ID
        and measure.get("synthetic") is True
        and measure.get("usable_as_real_platform_evidence") is False
        and slice_receipt.get("provider") == pe.SYNTHETIC_PROVIDER_ID
        and slice_receipt.get("synthetic") is True
        and slice_receipt.get("usable_as_real_platform_evidence") is False)
    checks.add(
        "S6B_synthetic_named_in_all_receipts",
        receipts_named,
        "合成回执出处具名全域在账（measure/slice 回执 provider=%s＋"
        "synthetic=True＋usable_as_real_platform_evidence=false——合成材"
        "料红线：不冒真实平台采集）" % pe.SYNTHETIC_PROVIDER_ID)
    coord_lines = [line for line
                   in COORD.read_text(encoding="utf-8").splitlines()
                   if "13-19" in line]
    coord_ok = bool(coord_lines) and all(
        "八平台" in line and "统一合成先行" in line
        for line in coord_lines)
    checks.add(
        "S6C_adjudication_13_19_synthetic_first_in_ledger",
        coord_ok,
        "00-总协调 裁决#13-19 行在账且含『八平台＋统一合成先行』（真实"
        "平台采集 v2 商业化时补——本单合成先行依据，行数=%d）"
        % len(coord_lines))
    faces_after = {"platform_evidence.py": sha256_file(PRODUCT),
                   "legal_entry.py": sha256_file(LEGAL_ENTRY)}
    checks.add(
        "S6D_frozen_faces_byte_stable_through_run",
        faces_after == faces_before,
        "冻结面全程字节稳定（sha256 前后相等）：platform_evidence.py=%s…"
        "／legal_entry.py=%s…"
        % (faces_after["platform_evidence.py"][:8],
           faces_after["legal_entry.py"][:8]))


# ---------------------------------------------------------------------- #
# 主流程
# ---------------------------------------------------------------------- #

def _md(evidence: dict) -> str:
    lines = [
        "# F102 商标/电商取证八平台 recon（%s）" % evidence["profile"],
        "",
        "- command: `%s`" % evidence["command"],
        "- cwd: `%s`" % evidence["cwd"],
        "- subject_commit: `%s`" % evidence["subject_commit"],
        "- overall: **%s**（%d/%d）" % (evidence["overall"],
                                        evidence["passed"],
                                        evidence["total"]),
        "- authority: %s" % evidence["authority_row"],
        "- recovery_point: %s" % evidence["recovery_point"],
        "- synthetic: %s；%s" % (
            evidence["synthetic_materials"]["target"],
            evidence["synthetic_materials"]["network"]),
        "",
        "| check | status | detail |",
        "|---|---|---|",
    ]
    for item in evidence["checks"]:
        lines.append("| %s | %s | %s |" % (item["id"], item["status"],
                                           item["detail"]
                                           .replace("|", "\\|")))
    return "\n".join(lines) + "\n"


def run_profile(args, profile: str) -> int:
    """单 profile 全量 24 检＋证据落盘（evidence/F102/<profile>/）。"""
    checks = Checks()
    rows = _ledger_rows()
    faces_before = {"platform_evidence.py": sha256_file(PRODUCT),
                    "legal_entry.py": sha256_file(LEGAL_ENTRY)}
    section_s1(checks, rows)
    section_s2(checks)
    section_s3(checks)
    failures = section_s4(checks)
    section_s6(checks, faces_before)

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
        "authority_row": "06 V7-102 F102（v2；owner=product；"
                         "UI_HOST_OR_NEW_PRODUCT；B5）acceptance="
                         + ACCEPTANCE_VECTOR
                         + "；prerequisites E10,E11,E12,E17,E21,E24；"
                         "legacy links F65/F96 记名不消费；裁决#13-19 "
                         "（00-总协调.md:254）八平台统一合成先行，真实平"
                         "台采集 v2 商业化时补",
        "recovery_point": pe.RECOVERY_POINT,
        "synthetic_materials": {
            "target": "进程内合成采集目标（SyntheticCaptureTarget，seed="
                      "20261022 钉定；出处具名 provider=%s）"
                      % pe.SYNTHETIC_PROVIDER_ID,
            "network": "零网络零子进程零真实外联（注入 transport＋注入假"
                       "时钟，全程进程内）",
            "keyword": "合成关键词『大华』（合成材料）",
        },
        "failure_attempts_observed": [a["status"] for a in failures],
        "checks": checks.items,
        "passed": checks.passed_count,
        "total": len(checks.items),
        "overall": "PASS" if checks.all_passed else "FAIL",
    }
    out_dir = REPO_ROOT / args.evidence_root / profile
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "f102-eight-platform-evidence-recon.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=1),
        encoding="utf-8")
    (out_dir / "f102-eight-platform-evidence-recon.md").write_text(
        _md(evidence), encoding="utf-8")
    print("---")
    print("RECON_%s %d/%d checks — profile=%s" % (
        "OK" if checks.all_passed else "FAIL",
        checks.passed_count, len(checks.items), profile))
    return 0 if checks.all_passed else 1


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("desktop", "selfhost"),
                        action="append", default=None)
    parser.add_argument("--evidence-root", default="evidence/F102")
    args = parser.parse_args()
    profiles = args.profile or ["desktop"]
    for required in (PRODUCT, LEGAL_ENTRY, LEDGER, COORD):
        if not required.is_file():
            print("FATAL: 预态缺失 %s" % required)
            return 2
    codes = [run_profile(args, profile) for profile in profiles]
    return 0 if all(code == 0 for code in codes) else 1


if __name__ == "__main__":
    raise SystemExit(main())
