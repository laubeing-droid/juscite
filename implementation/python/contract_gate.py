# -*- coding: utf-8 -*-
"""RE-37 合同起草·评分门（起草→rubric 评审→量化过关才出稿闭环）——
产品侧合同装配+量化评分门公开面（施工波 2026-10-30 单元 #37）。

对齐对象：识律 law-bench（FindDataTechnology/寻数，MIT License——机制
等量细读允许、引证注明许可；本模块零竞品文案照抄：填槽/诊断/retag 三段
提示词与 rubric 规则文本全部自写，槽名体系/节序/类目序为自家体系）。
机制等量件（RE-37 §2 八大机制件）：

  A 条款库三源（base 母版/tagged 场景/custom 自定）13 字段语义 +
    幂等 upsert（base/tagged 按 (source_path, section, body_hash) 冲突
    即更新且不改 manual；custom 按 id 平插、source_path 恒空）+ 受控
    词表治理（register_tag_dim reuse-or-create 防维蔓延）+ 逐维
    tag_review 准入门（custom assembly-ready ⇔ tags 每个非 ``_`` 前缀
    维 approved；base/tagged 主干不受门管）。
  B 装配器 per-section override with extension：每节恰一条 body，
    custom(stance)>tagged(scenario)>base 兜底；母版外 section 扩展
    插入排在附则前；同源同节 tiebreak manual>槽数多>body 长>id 小，
    触发节进 diagnostics.heuristic_sections；渲染前 coherence 三条门
    fail-closed（母版节不丢/无重复节/槽必有指令）。
  C 填槽：全量 {{槽}} 经 drafter 填充，fill_cache 六元组键
    sha1(type|scenario|sorted(slots)|model|temperature|task_desc)
    （槽序归一化、task_desc 入键）命中即跳过 LLM；解析容错（围栏/
    杂讯/坏 JSON→空填充不崩）；render_filled 未填槽保留占位符并上报
    unfilled 清单。
  D rubric 评分门：rubrics+rubric_criteria 两档来源（baseline 只读，
    写操作 typed 拒；local 可写）；criteria 三字段 id/title/
    match_criteria（「PASS if…/FAIL if…」评分标准即评分提示词，零手写
    评分 prompt）；命名 contract_<type>_v<N>，default_rubric 取最高
    版本否则字典序末；all-pass 二值（全过 1.0 否则 0.0，无部分得分），
    n_passed 为轮次比较主信号；每条规则一个独立 judge 调用（并发默认
    8、钳 [1,16]、按规则数封顶）；上下文分立（合同正文恒在、task_desc
    有才附）；瞬态错误（429/503 类）退避重试 3 次且不得计 FAIL（重试
    耗尽→error 入该条 reasoning、verdict=fail、跑继续）；评估快照
    语义（rubric 名+criteria+合同文本+task_desc 快照落账，不随后续
    rubric 编辑失效）。
  E 自愈管线 generate→fill→evaluate→check→[improve→generate]*→store
    （自研循环面实现，零 LangGraph）：路由 all_pass 或 iteration≥
    max_iterations（默认 3，=1 禁循环）同走 store；check 按
    (n_passed, score) 留历史最佳；improve 两类动作分权——
    exclude_custom_clause_ids 仅本轮装配排除（共享条款库永不被循环
    改写）+ recommendations 仅记录供人复核（循环永不执行）；坏 LLM/
    解析失败→空动作循环照跑；排除 id 跨轮累积去重；每轮 actions_taken
    留痕。
  F 条款库治理慢回路：learn 聚合（本 run+同类型历史 50 次 reject 建议
    累计≥阈值默认 3→bulk_review 标 rejected；只动 custom、幂等、单条款
    失败 fail-safe 跳过）；tag 迭代两段（suggest 只读建议→人工审批→
    apply 串行锁+存原始 tags+应用+重评+降分自动回滚）；离线分析器+
    执行器（高频 exclude/建议 reject/score-排除相关性→推荐清单，阈值
    3/2；执行按 confidence 档默认仅 high、dry-run 预览+JSONL 操作日志）。
  G A-B compare：固定区域（type/rubric/task）只变 prompt（≥2 才跑）；
    drafter-only 隔离（每稿单次直调 drafter，不进生产自愈管线）；
    rubric 未知/空在任何 LLM 调用前 fail-fast；顺序确定性（prompt-
    major/draft-minor）；draft_text 入库复现、默认不返回、run_draft
    懒取；矩阵 n=1 二值 verdict / n>1 通过率 k/N+首个可用 reasoning。

交付语义（RE-37 §4.3 第 2 轮复核钉定，等量+有意增强）：
  all_pass 与耗尽（达 max_iterations）**同末态出稿**、不阻塞交付——
  交付物强制带 gate_status=passed|exhausted；exhausted 交付具名
  「未过关」（差几条账+逐条判定随行），**只有 passed 交付可表述为
  已过关出稿**（耗尽出稿≠过关出稿，质量主张分立，防达标幻觉）。

RE-12 衔接面（起草≠审查，五条对账，RE-37 §4.4）：
  1 方向与产出分立：本面输入=起草需求→产出=新草稿+门内逐条判定
    （verdict pass/fail）；#12 输入=既有合同文本→产出=风险审查意见
    （critical/high/medium/low 四级+十大维度+四件套）。两套判定语汇
    分立，字段不复用不互译（测试钉死零混用）。
  2 门≠审查：rubric all-pass=起草质量门（该类型法律要点齐不齐），
    不是法律风险审查——门内过关的稿子不得表述为「已审查/无风险」；
    #12 复核=另一技能另一检查单，由用户发起。
  3 产出衔接单向：门内最佳稿可送 #12 复核（review_handoff 只带
    文本摘要锚+「非审查结论」注记，不带任何判定字段）；审查发现
    不回写条款库——慢回路只消费自家评分门结果。
  4 确定性切分共享：装配 body 的 ``## 节名`` 标题行与 #12 条款行
    基座同用确定性标题状态机切分（split_sections，零模型猜测）。
  5 法源面分立：law_refs=装配期静态归集（标注「效力未核」）；实时
    效力核验归 #14 引证核验，起草门只标注不裁决。

与竞品的后端差异（如实记录）：竞品表族落 Postgres+ensure_schema；本面
落产品既有文件账（状态根 JSON，原子写+进程内锁，同输入两跑同字节、
账面零时钟——created_at/updated_at 为调用方可选字段缺省空串，序号即
序）。竞品 MCP/REST 双面在自家收敛为 legal_entry method 面一档（20 件
对齐面+条款库/治理面）。评分门 v1 边界件（施工波 2026-10-31 单元 #37
边界单，RE-37 §7 五项「本版不做」中的四件落地）：
  - multi-judge 增强档（B31-B32/T19）：evaluate/pipeline 收 n_judges
    （默认 1=单 judge v1 形），≥2 时逐条规则多数投票（consensus=pass
    当且仅当 pass 票>fail 票，平票 fail-closed 归 fail）、confidence=
    胜方票/n_judges、unanimous/majority/tie 分记、consensus reasoning
    取首个与共识同判 judge；low_confidence＝**干净定义**——任一条
    confidence<0.67 即低信，对任意面板规模统一适用（不复制竞品
    「n_judges<3 才判、3-judge 面板恒 False」特异式，T19 钉定）；
    score=1.0 须 all_pass 且非低信；全 judge 调用皆败＝typed 拒
    （B58 空态族补齐）。
  - dashboard 只读聚合（B56/T31）：评估账总运行数/all_pass 数/平均
    通过率/按类型最高通过率（类型自 rubric 名 contract_<type>_v<N>
    确定解析，非合同 rubric 只入总量不入分型）。
  - 母版再生（B57/T32）：LLM seam 面等量（竞品子进程 --force 换自家
    进程内 seam 调用）——按 SECTION_ORDER 逐节生成 base 条款，槽必须
    全在本体闭集（未知槽＝failed 账+typed 拒）；force=False 且已有
    自动 base＝typed 拒；替换只动非 manual base（manual curated 保留，
    B3 纪律），tagged/custom 零触碰；masters 账逐次 completed/failed
    留痕（非零结果=failed 不装样子）。
  - 导出 markdown/docx/pdf/both（B15）：docx=纯 Python 确定性生成
    （F45/F119 同构：xml.etree 最小包+zip 时间戳钉定 1980-01-01，同输入
    两跑同字节）；pdf=docx 经 LibreOffice headless 渲染（F58 纪律：
    Windows 用 soffice.com、UserInstallation 隔离于状态根、失败清半
    成品 typed 拒；config 键 libreoffice_soffice 与 F54/F58 同源；PDF
    字节含渲染器时间戳**不主张**逐字节确定，如实记录）。
v1 维持边界：rubric 小集合起步（买卖/租赁/劳动/借款/服务与 RE-12 域序
一致，41 类不铺）；运营 UI 面不做（method 面先行）；零 JC 依赖（rubric
规则一律为门内 LLM 评审标准，不进 JC 规则包，§1.4 红线）。

竞品吸收增补节落地（Harvey LAB 准则口径学，RE-37 文末增补节 2026-10-31；
细读件=竞品情报/2026-10-30-升级差分波/2026-10-31-harvey-lab-audit-
rubric口径分析.md，源头仓 harvey-lab-audit @6ef7e2ac **无 LICENSE**
（无许可源纪律：只取机制形状等量转写，零内容移植零文案照抄；US 法域
实体内容零采用））：
  - A37-H1 判据双分支：rubric 校验器拒绝单分支判据——match_criteria
    必须同时含「PASS if」与「FAIL if」条件，缺一即 typed 拒
    （cg37_criterion_single_branch）；judge 提示词固定骨架写明「语义
    实质判定而非逐字匹配＋FAIL 条件独立检验（PASS 条件命中不算过、
    FAIL 条件未触发才过）」。
  - A37-H2 判定锚定三件套：judge 逐条输出结构化三字段
    location/quote/reasoning——「原文引句」须为产出物文本子串、「位置」
    须命中产出物节名枚举（split_sections 确定性切分），机械校验不过
    即该条判 invalid 不计 pass（verdict 强制 fail+anchor_status 具名，
    verdict 值域仍钉 {pass,fail} 不扩）。
  - A37-H3 粒度对标：自研 rubric 每类准则数 ∈ [25,60]（越界须显式豁免
    账 granularity_exemption 随 rubric 行落账并在 list/get 投影）；
    拆分轴（节×槽×必答要素）登记于 granularity_axes 字段。
    （A37-H4 封存序+修正账不在本单范围——开工单未列名，RE-37 增补节
    在册待后续单。）

LLM 注入面：模型调用一律经调用方注入的 seam（config["contract_gate_
llm"]={"model": str, "complete": fn(system, user)->str, "judge_model":
str?}，进程内传入——会话技能循环面/单测注入；CLI/JSON 通道无 seam＝
LLM 依赖方法 typed 拒 cg37_llm_seam_not_configured，确定性方法不受
影响）。seam 抛出的瞬态错误（TransientLLMError 或消息含 RateLimit/
429/ServiceUnavailable/503）按 D 组退避纪律处理。自家本就本地闭环：
评分调用无遥测外呼面（结构性强于竞品的 opt-out 纪律）。

已知限制转纪律（竞品 §11 五条吸收）：judge 结构性误读→上下文分立+
不追单次分（看 n_passed 趋势与矩阵通过率）；all-pass 放大噪声→n_passed
为诊断量；draft_text 体积懒取；drafter-only 对比结论≠生产管线表现
（compare 结果不作生产管线承诺）。
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import threading
import xml.etree.ElementTree as ET
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date as _date
from pathlib import Path

SCHEMA = "juscite-cg37-contract-gate/1"
STATE_SUBDIR = "contract_gate"
CONFIG_STATE_ROOT = "contract_gate_state_root"
CONFIG_LLM = "contract_gate_llm"
CONFIG_AUTO_REJECT_THRESHOLD = "contract_gate_auto_reject_threshold"

# ── 自家槽名体系（v1 canonical 槽，RE-37 §7「不抄竞品槽名清单」）──
# kind 闭集与 F56 同族（text/date/amount/number）；金额十进制串禁浮点、
# 日期真日历＝槽值落库前确定性机检（比竞品「金额用数字」提示词约束更硬
# 一层，有意增强，RE-37 §4.2）。
SLOT_KINDS = ("text", "date", "amount", "number")
SLOT_ONTOLOGY: dict[str, dict] = {
    "甲方名称": {"label": "甲方名称", "kind": "text", "required": True,
                 "description": "合同甲方（我方或委托方）的全称",
                 "example": "示例商贸有限公司"},
    "乙方名称": {"label": "乙方名称", "kind": "text", "required": True,
                 "description": "合同乙方的全称",
                 "example": "示例制造有限公司"},
    "标的描述": {"label": "标的描述", "kind": "text", "required": True,
                 "description": "交易标的的名称、型号与范围",
                 "example": "某型号设备 10 台及配套附件"},
    "合同金额": {"label": "合同金额（元）", "kind": "amount", "required": True,
                 "description": "合同总价，十进制数字串（不含货币符号）",
                 "example": "128000.00"},
    "签署日期": {"label": "签署日期", "kind": "date", "required": False,
                 "description": "合同签署日期，YYYY-MM-DD",
                 "example": "2026-10-30"},
    "履行期限": {"label": "履行期限", "kind": "text", "required": False,
                 "description": "履行起止或期限表述",
                 "example": "自签署之日起 60 日内"},
    "争议解决方式": {"label": "争议解决方式", "kind": "text", "required": False,
                     "description": "诉讼或仲裁及其管辖/机构约定",
                     "example": "提交示例仲裁委员会仲裁"},
}
REQUIRED_SLOT_NAMES = tuple(sorted(
    name for name, spec in SLOT_ONTOLOGY.items() if spec["required"]))
# 槽别名→canonical（入库规范化用；RE-37 §2.1 body 规范化机制件）。
SLOT_ALIASES = {
    "甲方": "甲方名称", "乙方": "乙方名称", "金额": "合同金额",
    "签订日期": "签署日期", "标的": "标的描述",
}
SLOT_PATTERN = re.compile(r"\{\{([^{}]{1,64})\}\}")
_AMOUNT_RE = re.compile(r"^-?(\d{1,3}(,\d{3})+|\d+)(\.\d+)?$")
_NUMBER_RE = re.compile(r"^-?\d+(\.\d+)?$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

# ── 自家节序（v1 五类共用骨架；扩展节排在附则前，RE-37 §2.2）──
SECTION_ORDER = (
    "标的与质量", "价款与支付", "履行与交付", "违约责任",
    "其他约定", "附则",
)
_EXT_RANK = float(SECTION_ORDER.index("附则")) - 0.5

# ── 自家法源类目序（law_refs 归集排序用；未知类目排末尾）──
LAW_REF_CATEGORIES = ("法律", "行政法规", "司法解释", "部门规章", "其他")

# 三源闭集与受控词表字面量（universal=source/stance 两维为代码字面量，
# scenario 为每类型受控维——运行时态经 tag_dims 装载/治理，同竞品口径）。
SOURCES = ("base", "tagged", "custom")
STANCE_VALUES = ("pro_a", "pro_b", "balanced")
REVIEW_STATUSES = ("pending", "approved", "rejected")
METADATA_PREFIX = "_"
RUBRIC_SOURCES = ("baseline", "local")
DEFAULT_RUBRIC_RE = re.compile(r"^contract_(.+)_v(\d+)$")

# 评分门并发与退避（RE-37 §2.5；退避秒数可经 args 覆盖＝测试合成纪律，
# 生产缺省同竞品 8s×(attempt+1)）。
JUDGE_WORKERS_DEFAULT = 8
JUDGE_WORKERS_CEILING = 16
JUDGE_ATTEMPTS = 3
JUDGE_BACKOFF_SECONDS = 8.0
TRANSIENT_MARKS = ("RateLimit", "429", "ServiceUnavailable", "503")

MAX_ITERATIONS_DEFAULT = 3
LEARN_HISTORY_LIMIT = 50
AUTO_REJECT_THRESHOLD_DEFAULT = 3
ANALYZE_THRESHOLD_EXCLUDE = 3
ANALYZE_THRESHOLD_REJECT = 2
COMPARE_DRAFTS_CEILING = 8

# ── Harvey 口径学增补（A37-H1/H2/H3；RE-37 增补节 2026-10-31）──
DUAL_BRANCH_REQUIRED = ("PASS IF", "FAIL IF")  # 判据双分支字面（大写化匹配）
GRANULARITY_MIN = 25   # 自研 rubric 每类准则数下界（命题级拆条目标区间）
GRANULARITY_MAX = 60
GRANULARITY_AXES = ("节", "槽", "必答要素")  # 拆分轴登记默认值
# ── multi-judge 增强档（B31-B32/T19；干净 low_confidence 定义）──
JUDGE_PANEL_CEILING = 8
LOW_CONFIDENCE_THRESHOLD = 0.67  # 任一条 confidence<0.67 即低信（全面板
#                                 规模统一适用——不复制竞品 n_judges<3
#                                 特异式，T19 钉定）
# ── 导出（B15：markdown/docx/pdf/both）──
OUTPUT_FORMATS = ("markdown", "docx", "pdf", "both")
SOFFICE_TIMEOUT_DEFAULT = 300
_ZIP_DATE = (1980, 1, 1, 0, 0, 0)  # docx zip 时间戳钉定（F45/F119 同构）
_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_DOCX_FIXED_PARTS = {
    "[Content_Types].xml":
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/'
        'content-types"><Default Extension="rels" ContentType="application/'
        'vnd.openxmlformats-package.relationships+xml"/><Default '
        'Extension="xml" ContentType="application/xml"/><Override '
        'PartName="/word/document.xml" ContentType="application/vnd.'
        'openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>",
    "_rels/.rels":
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/'
        '2006/relationships"><Relationship Id="rId1" Type="http://schemas.'
        'openxmlformats.org/officeDocument/2006/relationships/officeDocument"'
        ' Target="word/document.xml"/></Relationships>',
}

_LOCK = threading.RLock()


class ContractGateError(ValueError):
    """Typed RE-37 face failure; str() is a cg37_* code, never content."""

    error_code = "cg37_invalid"


class CoherenceError(ContractGateError):
    """装配一致性门失败（渲染前 fail-closed，具名列失败检查项）。"""

    error_code = "cg37_coherence_failed"


class BaselineReadOnlyError(ContractGateError):
    """baseline 档 rubric 写操作 typed 拒（两档来源纪律）。"""

    error_code = "cg37_baseline_readonly"


class TransientLLMError(RuntimeError):
    """seam 抛出的瞬态错误（429/503 类）——退避重试且不得计 FAIL。"""


def _fail(code: str) -> ContractGateError:
    return ContractGateError(code)


# ---------------------------------------------------------------------------
# 存储基座（文件账：原子写+进程内锁；同输入两跑同字节、零时钟入产物）
# ---------------------------------------------------------------------------

def _dump(payload) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _read_json(path: Path):
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _root(state_root) -> Path:
    root = Path(state_root) / STATE_SUBDIR
    root.mkdir(parents=True, exist_ok=True)
    return root


def _md5(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def _sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _next_seq(directory: Path) -> int:
    seq = 0
    if directory.is_dir():
        for entry in directory.iterdir():
            stem = entry.name.split(".")[0]
            if stem.isdigit():
                seq = max(seq, int(stem))
    return seq + 1


def _write_seq_json(directory: Path, seq: int, payload: dict) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    _atomic_write(directory / f"{seq:06d}.json", _dump(payload))


def _load_seq_jsons(directory: Path) -> list[dict]:
    rows: list[dict] = []
    if not directory.is_dir():
        return rows
    for entry in sorted(directory.iterdir()):
        if entry.suffix != ".json" or not entry.stem.isdigit():
            continue
        row = _read_json(entry)
        if row is not None:
            rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# 槽本体：规范化/机检/指令（B4/B13；确定性，零模型）
# ---------------------------------------------------------------------------

def normalize_body(body: str) -> str:
    """body 槽名规范化：槽内空白剥除＋别名→canonical（本体驱动）。"""

    def _canon(match: "re.Match[str]") -> str:
        name = match.group(1).strip()
        return "{{" + SLOT_ALIASES.get(name, name) + "}}"

    return SLOT_PATTERN.sub(_canon, body or "")


def normalize_slot_name(name: str) -> str:
    name = (name or "").strip()
    return SLOT_ALIASES.get(name, name)


def slots_in(body: str) -> list[str]:
    """body 内槽名清单（规范化后、文档序去重保持首现序）。"""
    seen: list[str] = []
    for match in SLOT_PATTERN.finditer(body or ""):
        name = normalize_slot_name(match.group(1))
        if name and name not in seen:
            seen.append(name)
    return seen


def check_slot_value(name: str, value) -> None:
    """槽值确定性机检（落库前，RE-37 §4.2 有意增强）：
    金额=十进制/千位逗号串禁浮点；日期=YYYY-MM-DD 真日历；文本=非空
    单值无控制字符。不过＝typed 拒（LLM 只产候选值，机检不过具名拒）。"""
    if not isinstance(value, str) or not value.strip():
        raise _fail(f"cg37_slot_value_invalid:{name}:not_a_nonempty_string")
    if _CONTROL_CHARS_RE.search(value):
        raise _fail(f"cg37_slot_value_invalid:{name}:control_chars")
    spec = SLOT_ONTOLOGY.get(name)
    kind = spec["kind"] if spec else "text"
    if kind == "amount" and not _AMOUNT_RE.match(value):
        raise _fail(f"cg37_slot_value_invalid:{name}:amount_not_decimal")
    if kind == "number" and not _NUMBER_RE.match(value):
        raise _fail(f"cg37_slot_value_invalid:{name}:not_a_number_string")
    if kind == "date":
        if not _DATE_RE.match(value):
            raise _fail(f"cg37_slot_value_invalid:{name}:date_not_ymd")
        try:
            _date.fromisoformat(value)
        except ValueError:
            raise _fail(f"cg37_slot_value_invalid:{name}:date_not_real") from None


def instruction_for_slot(name: str) -> dict | None:
    """槽本体回退指令（body 有槽但无人声明时补，保 coherence 第③条）。"""
    spec = SLOT_ONTOLOGY.get(name)
    if spec is None:
        return None
    return {"name": name, "label": spec["label"], "kind": spec["kind"],
            "description": spec["description"], "example": spec["example"],
            "required": bool(spec["required"])}


def default_slot_instructions() -> list[dict]:
    """canonical 槽指令（自家 v1 七槽；竞品 12 槽清单不抄）。"""
    return [instruction_for_slot(name) for name in sorted(SLOT_ONTOLOGY)]


def split_sections(markdown_text: str) -> list[str]:
    """确定性节切分（## 标题状态机，零模型）——RE-12 §4.4-4 共享基座：
    装配节序与 #12 条款行基座同用标题行切分，两侧切分口径一致。"""
    sections: list[str] = []
    for line in (markdown_text or "").splitlines():
        if line.startswith("## "):
            title = line[3:].strip()
            if title and title not in sections:
                sections.append(title)
    return sections

# ---------------------------------------------------------------------------
# A 组：条款库三源 + 受控词表 + tag_review 准入门
# ---------------------------------------------------------------------------

CLAUSE_FIELDS = (
    "id", "contract_type", "section", "body", "slot_instructions",
    "law_refs", "source_path", "source_doc_title", "body_hash",
    "created_at", "updated_at", "manual", "tags", "tag_review",
)

_TYPE_RE = re.compile(r"^[A-Za-z0-9\u4e00-\u9fff][A-Za-z0-9\u4e00-\u9fff._-]{0,63}$")
_SECTION_RE = re.compile(r"^\S.{0,63}$")


def _clauses_root(root: Path) -> Path:
    return root / "clauses"


def _load_clauses(root: Path) -> dict:
    data = _read_json(_clauses_root(root) / "clauses.json")
    if data is None:
        return {"seq": 0, "clauses": []}
    return data


def _save_clauses(root: Path, data: dict) -> None:
    directory = _clauses_root(root)
    directory.mkdir(parents=True, exist_ok=True)
    _atomic_write(directory / "clauses.json", _dump(data))


def _clause_view(clause: dict) -> dict:
    return {key: clause.get(key) for key in CLAUSE_FIELDS}


def _validate_instructions(instructions) -> list[dict]:
    """槽指令声明校验＋槽名规范化（B4：body 与槽指令名同经本体规范）。"""
    if instructions is None:
        return []
    if not isinstance(instructions, list):
        raise _fail("cg37_slot_instructions_invalid")
    cleaned: list[dict] = []
    for ins in instructions:
        if not isinstance(ins, dict) or not isinstance(ins.get("name"), str) \
                or not ins["name"].strip():
            raise _fail("cg37_slot_instructions_invalid")
        name = normalize_slot_name(ins["name"])
        ontology = SLOT_ONTOLOGY.get(name)
        cleaned.append({
            "name": name,
            "label": ins.get("label")
                or (ontology["label"] if ontology else name),
            "kind": ins.get("kind")
                or (ontology["kind"] if ontology else "text"),
            "description": ins.get("description") or "",
            "example": ins.get("example") or "",
            "required": bool(ins.get("required", False)),
        })
    return cleaned


def _validate_law_refs(law_refs) -> list[dict]:
    if law_refs is None:
        return []
    if not isinstance(law_refs, list):
        raise _fail("cg37_law_refs_invalid")
    cleaned: list[dict] = []
    for ref in law_refs:
        if isinstance(ref, str):
            cleaned.append({"name": ref, "category": "其他"})
        elif isinstance(ref, dict) and isinstance(ref.get("name"), str) \
                and ref["name"].strip():
            category = ref.get("category")
            cleaned.append({"name": ref["name"],
                            "category": category if isinstance(category, str)
                            and category else "其他"})
        else:
            raise _fail("cg37_law_refs_invalid")
    return cleaned


# ── 受控词表治理（tag_dims：register_tag_dim reuse-or-create 防维蔓延）──

def _tag_dims_root(root: Path) -> Path:
    return root / "tag_dims"


def _load_tag_dims(root: Path) -> dict:
    data = _read_json(_tag_dims_root(root) / "tag_dims.json")
    if data is None:
        return {"universal": {"source": list(SOURCES),
                              "stance": list(STANCE_VALUES)},
                "types": {}}
    return data


def _save_tag_dims(root: Path, data: dict) -> None:
    directory = _tag_dims_root(root)
    directory.mkdir(parents=True, exist_ok=True)
    _atomic_write(directory / "tag_dims.json", _dump(data))


def register_tag_dim(state_root, contract_type: str | None, dim: str,
                     values: list[str]) -> dict:
    """词表治理闸：reuse-or-create——已存在的维合并取值不重复建。

    dim 维度名；contract_type=None→universal 维（跨类型共享），否则该
    类型的类型专属维（scenario 等）。seeder/装配/手工录入全走此闸。"""
    if not isinstance(dim, str) or not dim.strip() \
            or dim.startswith(METADATA_PREFIX):
        raise _fail("cg37_tag_dim_invalid")
    if dim in ("source", "stance") and contract_type is not None:
        raise _fail("cg37_tag_dim_invalid:universal_dim_not_per_type")
    if not isinstance(values, list) \
            or not all(isinstance(v, str) and v.strip() for v in values):
        raise _fail("cg37_tag_dim_values_invalid")
    with _LOCK:
        root = _root(state_root)
        data = _load_tag_dims(root)
        scope = data["universal"] if contract_type is None \
            else data["types"].setdefault(
                _require_type_name(contract_type), {})
        existing = scope.get(dim) or []
        is_new_dim = dim not in scope
        merged = list(dict.fromkeys(existing + [v for v in values if v]))
        created = is_new_dim or len(merged) != len(existing)
        scope[dim] = merged
        _save_tag_dims(root, data)
        return {"dim": dim, "scope": "universal" if contract_type is None
                else contract_type, "values": merged, "created": created}


def _require_type_name(contract_type) -> str:
    if not isinstance(contract_type, str) \
            or not _TYPE_RE.match(contract_type):
        raise _fail("cg37_contract_type_invalid")
    return contract_type


def _govern_tags(root: Path, contract_type: str, tags: dict) -> None:
    """tags 入库经词表闸：scenario 等维值 reuse-or-create 登记；stance
    值域校验；``_`` 前缀键=导入溯源元数据直通不入维。"""
    dims = _load_tag_dims(root)
    type_scope = dims["types"].setdefault(contract_type, {})
    for key, value in sorted(tags.items()):
        if key.startswith(METADATA_PREFIX):
            continue
        if key == "source" or key == "stance":
            continue  # universal 字面量维，值域在入参校验
        if not isinstance(value, str):
            raise _fail(f"cg37_tag_value_invalid:{key}")
        if key not in type_scope:
            type_scope[key] = []
        if value not in type_scope[key]:
            type_scope[key].append(value)
    _save_tag_dims(root, dims)


# ── tag_review：逐维三态准入门（B7-B9）──

def _review_dims(tags: dict | None) -> list[str]:
    return [key for key in (tags or {})
            if not key.startswith(METADATA_PREFIX)]


def is_assembly_ready(clause: dict) -> bool:
    """assembly-ready ⇔ tags 每个非 ``_`` 前缀维 tag_review=='approved'。
    base/tagged 主干不受此门管（调用处只对 custom 过门）。"""
    review = clause.get("tag_review") or {}
    return all(review.get(dim) == "approved"
               for dim in _review_dims(clause.get("tags")))


def review_tag(state_root, clause_id: int, dim: str, status: str) -> dict:
    """逐维 review（per-dim）：设单维状态；元数据前缀维＝typed 拒。"""
    if status not in REVIEW_STATUSES:
        raise _fail("cg37_review_status_invalid")
    if dim.startswith(METADATA_PREFIX):
        raise _fail("cg37_review_dim_is_metadata")
    with _LOCK:
        root = _root(state_root)
        data = _load_clauses(root)
        clause = _find_clause(data, clause_id)
        clause["tag_review"] = dict(clause.get("tag_review") or {})
        clause["tag_review"][dim] = status
        _save_clauses(root, data)
        return _clause_view(clause)


def bulk_review(state_root, clause_id: int, status: str) -> dict:
    """整条 bulk_review（合并写）：真维全设值、``_`` 前缀键原样保留。"""
    if status not in REVIEW_STATUSES:
        raise _fail("cg37_review_status_invalid")
    with _LOCK:
        root = _root(state_root)
        data = _load_clauses(root)
        clause = _find_clause(data, clause_id)
        review = dict(clause.get("tag_review") or {})
        for dim in _review_dims(clause.get("tags")):
            review[dim] = status
        clause["tag_review"] = review
        _save_clauses(root, data)
        return _clause_view(clause)


def _find_clause(data: dict, clause_id) -> dict:
    if not isinstance(clause_id, int) or isinstance(clause_id, bool):
        raise _fail("cg37_clause_id_invalid")
    for clause in data["clauses"]:
        if clause["id"] == clause_id:
            return clause
    raise _fail(f"cg37_clause_not_found:{clause_id}")


def get_clause(state_root, clause_id: int) -> dict:
    with _LOCK:
        data = _load_clauses(_root(state_root))
        return _clause_view(_find_clause(data, clause_id))


def upsert_clause(state_root, args: dict) -> dict:
    """条款三源 upsert（B1-B4）。

    - source ∈ base/tagged/custom（显式声明，fail-closed 不猜测）；
      custom 的 source_path 恒空（给了＝typed 拒）。
    - base/tagged 按 (source_path, section, body_hash) 幂等冲突更新
      （冲突更新不改 manual、不改 created_at）；custom 按 id 平插。
    - body 与槽指令名入库经槽本体规范化；body_hash 仅当规范化改变了
      body 才重推导 md5，否则保留调用方传入 hash（测试 sentinel 兼容）。
    - tags 经词表闸治理；custom 的每个真维 tag_review 起始 pending
      （准入门+审查队列）；base/tagged 不受门管。"""
    if not isinstance(args, dict):
        raise _fail("cg37_params_invalid")
    contract_type = _require_type_name(args.get("contract_type"))
    source = args.get("source")
    if source not in SOURCES:
        raise _fail("cg37_clause_source_invalid")
    section = args.get("section")
    if not isinstance(section, str) or not _SECTION_RE.match(section.strip()) \
            or not section.strip():
        raise _fail("cg37_section_invalid")
    raw_body = args.get("body")
    if not isinstance(raw_body, str) or not raw_body.strip():
        raise _fail("cg37_clause_body_invalid")
    body = normalize_body(raw_body)
    instructions = _validate_instructions(args.get("slot_instructions"))
    law_refs = _validate_law_refs(args.get("law_refs"))
    source_path = args.get("source_path")
    if source == "custom":
        if source_path:
            raise _fail("cg37_custom_source_path_forbidden")
    elif not isinstance(source_path, str) or not source_path.strip():
        raise _fail("cg37_source_path_required")
    source_doc_title = args.get("source_doc_title")
    if source_doc_title is not None \
            and not isinstance(source_doc_title, str):
        raise _fail("cg37_source_doc_title_invalid")
    manual = args.get("manual", False)
    if not isinstance(manual, bool):
        raise _fail("cg37_manual_invalid")
    created_at = args.get("created_at", "")
    updated_at = args.get("updated_at", "")
    for stamp in (created_at, updated_at):
        if not isinstance(stamp, str):
            raise _fail("cg37_clause_stamp_invalid")
    caller_hash = args.get("body_hash")
    if caller_hash is not None and not isinstance(caller_hash, str):
        raise _fail("cg37_body_hash_invalid")
    body_hash = caller_hash if (caller_hash and body == raw_body) \
        else _md5(body)
    raw_tags = args.get("tags") or {}
    if not isinstance(raw_tags, dict):
        raise _fail("cg37_tags_invalid")
    tags = dict(raw_tags)
    tags["source"] = source
    stance = tags.get("stance")
    if stance is not None and stance not in STANCE_VALUES:
        raise _fail("cg37_stance_invalid")
    with _LOCK:
        root = _root(state_root)
        _govern_tags(root, contract_type, tags)
        data = _load_clauses(root)
        existing = None
        if source in ("base", "tagged"):
            for clause in data["clauses"]:
                if clause["contract_type"] == contract_type \
                        and clause["tags"].get("source") == source \
                        and clause["section"] == section.strip() \
                        and clause["source_path"] == source_path \
                        and clause["body_hash"] == body_hash:
                    existing = clause
                    break
        if existing is not None:
            existing.update({
                "body": body, "slot_instructions": instructions,
                "law_refs": law_refs,
                "source_doc_title": source_doc_title,
                "updated_at": updated_at,
                "tags": tags,
                "tag_review": dict(existing.get("tag_review") or {}),
            })  # manual/created_at/id 不被冲突更新打回（B3）
            _save_clauses(root, data)
            view = _clause_view(existing)
            view["upserted"] = "updated"
            return view
        data["seq"] += 1
        clause = {
            "id": data["seq"], "contract_type": contract_type,
            "section": section.strip(), "body": body,
            "slot_instructions": instructions, "law_refs": law_refs,
            "source_path": source_path if source != "custom" else None,
            "source_doc_title": source_doc_title, "body_hash": body_hash,
            "created_at": created_at, "updated_at": updated_at,
            "manual": manual, "tags": tags,
            "tag_review": {dim: "pending" for dim in _review_dims(tags)}
            if source == "custom" else {},
        }
        data["clauses"].append(clause)
        _save_clauses(root, data)
        view = _clause_view(clause)
        view["upserted"] = "inserted"
        return view


def list_clauses(state_root, args: dict) -> dict:
    """条款清单（过滤投影：类型/源/场景/立场/节）。"""
    if not isinstance(args, dict):
        raise _fail("cg37_params_invalid")
    with _LOCK:
        data = _load_clauses(_root(state_root))
    clauses = data["clauses"]
    contract_type = args.get("contract_type")
    if contract_type is not None:
        clauses = [c for c in clauses
                   if c["contract_type"] == _require_type_name(contract_type)]
    source = args.get("source")
    if source is not None:
        if source not in SOURCES:
            raise _fail("cg37_clause_source_invalid")
        clauses = [c for c in clauses if c["tags"].get("source") == source]
    scenario = args.get("scenario")
    if scenario is not None:
        clauses = [c for c in clauses
                   if (c["tags"] or {}).get("scenario") == scenario]
    stance = args.get("stance")
    if stance is not None:
        clauses = [c for c in clauses
                   if (c["tags"] or {}).get("stance") == stance]
    section = args.get("section")
    if section is not None:
        clauses = [c for c in clauses if c["section"] == section]
    return {"schema": SCHEMA, "clauses": [_clause_view(c) for c in clauses],
            "count": len(clauses)}


def delete_auto_clauses(state_root, args: dict) -> dict:
    """清理自动条款（manual=false）；人工 curated 条款保留（B3）。"""
    if not isinstance(args, dict):
        raise _fail("cg37_params_invalid")
    with _LOCK:
        root = _root(state_root)
        data = _load_clauses(root)
        kept: list[dict] = []
        removed: list[int] = []
        for clause in data["clauses"]:
            if args.get("contract_type") is not None \
                    and clause["contract_type"] != args["contract_type"]:
                kept.append(clause)
                continue
            if clause.get("manual"):
                kept.append(clause)
            else:
                removed.append(clause["id"])
        data["clauses"] = kept
        _save_clauses(root, data)
        return {"schema": SCHEMA, "removed": removed, "count": len(removed)}


def review_queue(state_root, args: dict) -> dict:
    """pending 队列：任一真维 tag_review=='pending' 的 custom 条款。"""
    if not isinstance(args, dict):
        raise _fail("cg37_params_invalid")
    with _LOCK:
        data = _load_clauses(_root(state_root))
    queue = []
    for clause in data["clauses"]:
        review = clause.get("tag_review") or {}
        pending = sorted(dim for dim in _review_dims(clause.get("tags"))
                         if review.get(dim) == "pending")
        if pending:
            queue.append({"clause_id": clause["id"],
                          "section": clause["section"],
                          "pending_dims": pending})
    return {"schema": SCHEMA, "queue": queue, "count": len(queue)}


# ---------------------------------------------------------------------------
# B 组：装配器（per-section override with extension）+ coherence 门
# ---------------------------------------------------------------------------

def _section_sort_key(section: str) -> tuple[float, str]:
    if section in SECTION_ORDER:
        return (float(SECTION_ORDER.index(section)), "")
    return (_EXT_RANK, section)


def _pick_variant(clauses: list[dict]) -> dict:
    """同源同节 tiebreak：manual > 槽数多 > body 长 > id 小（B11）。"""
    return min(clauses, key=lambda c: (
        0 if c.get("manual") else 1,
        -len(slots_in(c.get("body") or "")),
        -len((c.get("body") or "").strip()),
        c["id"]))


def _resolve_sections(base: list[dict], tagged: list[dict],
                      custom: list[dict]) -> tuple[list[dict], list[str], set]:
    """逐节解析 custom>tagged>base；返回 (resolved, heuristic_sections,
    base_sections)。resolved 按节序排列（扩展节排附则前）。"""
    groups: dict[str, dict[str, list[dict]]] = {}
    for src, clauses in (("base", base), ("tagged", tagged),
                         ("custom", custom)):
        for clause in clauses:
            groups.setdefault(clause["section"],
                              {"base": [], "tagged": [], "custom": []})[src] \
                .append(clause)
    base_sections = {c["section"] for c in base}
    resolved: list[dict] = []
    heuristic: list[str] = []
    for section, group in groups.items():
        for src in ("custom", "tagged", "base"):  # 优先级高→低
            if group[src]:
                resolved.append(_pick_variant(group[src]))
                if len(group[src]) > 1:
                    heuristic.append(section)
                break
    resolved.sort(key=lambda c: _section_sort_key(c["section"]))
    return resolved, heuristic, base_sections


def _select_clauses(state_root, contract_type: str, scenario, stance,
                    custom_clause_ids) -> tuple[list[dict], list[dict], list]:
    """候选收集：base 全量母版；tagged 按 scenario 过滤；custom 按 stance
    或显式 custom_clause_ids 过滤且只取 assembly-ready（B10 候选过滤）。"""
    with _LOCK:
        data = _load_clauses(_root(state_root))
    all_clauses = [c for c in data["clauses"]
                   if c["contract_type"] == contract_type]
    base = [c for c in all_clauses if c["tags"].get("source") == "base"]
    if not base:
        raise _fail(f"cg37_contract_type_not_found:{contract_type}")
    tagged = [c for c in all_clauses
              if c["tags"].get("source") == "tagged"
              and scenario and c["tags"].get("scenario") == scenario]
    if custom_clause_ids:
        by_id = {c["id"]: c for c in all_clauses}
        custom = []
        for cid in custom_clause_ids:
            clause = by_id.get(cid)
            if clause is not None and clause["tags"].get("source") == "custom" \
                    and is_assembly_ready(clause) \
                    and (stance is None
                         or clause["tags"].get("stance") == stance):
                custom.append(clause)
    elif stance:
        custom = [c for c in all_clauses
                  if c["tags"].get("source") == "custom"
                  and c["tags"].get("stance") == stance
                  and is_assembly_ready(c)]
    else:
        custom = []
    return base, tagged, custom


def _build_instructions(resolved: list[dict]) -> list[dict]:
    """槽指令并集：canonical ∪ 各条款声明 ∪ 本体回退（按名去重，B13）。"""
    instructions: list[dict] = []
    names: set[str] = set()
    for ins in default_slot_instructions():
        if ins["name"] not in names:
            names.add(ins["name"])
            instructions.append(dict(ins))
    for clause in resolved:
        for ins in clause.get("slot_instructions") or []:
            if ins.get("name") and ins["name"] not in names:
                names.add(ins["name"])
                instructions.append(dict(ins))
    body_slots: set[str] = set()
    for clause in resolved:
        body_slots.update(slots_in(clause.get("body") or ""))
    for slot in sorted(body_slots):
        if slot not in names:
            ins = instruction_for_slot(slot)
            if ins is not None:
                names.add(slot)
                instructions.append(ins)
    return instructions


def _build_law_refs(resolved: list[dict]) -> list[dict]:
    """law_refs 归集：按名去重并集，按（类目序,名）排序（B13）；
    装配期静态归集——效力未核标注随行（RE-12 §4.4-5：只标注不裁决）。"""
    by_name: dict[str, dict] = {}
    for clause in resolved:
        for ref in clause.get("law_refs") or []:
            name = ref.get("name")
            if name and name not in by_name:
                by_name[name] = dict(ref)
    ordered = sorted(by_name.values(), key=lambda r: (
        LAW_REF_CATEGORIES.index(r["category"])
        if r.get("category") in LAW_REF_CATEGORIES
        else len(LAW_REF_CATEGORIES),
        r.get("name", "")))
    return [{**ref, "note": "装配期静态归集，效力未核（实时核验归引证核验）"}
            for ref in ordered]


def validate_coherence(resolved: list[dict], body: str,
                       instructions: list[dict],
                       base_sections: set | None = None) -> None:
    """coherence 三条门（渲染前 fail-closed，B12）：①母版节不丢（覆盖是
    替换不是删除）②resolved 无重复节 ③body 每个 {{槽}} 都有配套指令。
    任一不过抛 CoherenceError 具名列失败检查项、拒绝渲染。"""
    errors: list[str] = []
    resolved_sections = [c["section"] for c in resolved]
    if base_sections is not None:
        missing = sorted(base_sections - set(resolved_sections))
        if missing:
            errors.append(f"missing_master_sections:{missing}")
    seen: set[str] = set()
    dups: set[str] = set()
    for section in resolved_sections:
        if section in seen:
            dups.add(section)
        seen.add(section)
    if dups:
        errors.append(f"duplicate_sections:{sorted(dups)}")
    instr_names = {i["name"] for i in instructions}
    body_slots = set(slots_in(body))
    uninstr = sorted(body_slots - instr_names)
    if uninstr:
        errors.append(f"uninstructed_slots:{uninstr}")
    if errors:
        raise CoherenceError("cg37_coherence_failed:" + ";".join(errors))


# ---------------------------------------------------------------------------
# 导出（B15，边界件）：markdown/docx/pdf/both。docx=纯 Python 确定性生成
# （F45/F119 同构：xml.etree 最小包+zip 时间戳钉定，同输入两跑同字节）；
# pdf=docx 经 LibreOffice headless 渲染（F58 纪律：Windows 用 soffice.com、
# UserInstallation 隔离于状态根、失败清半成品 typed 拒；PDF 字节含渲染器
# 时间戳不主张逐字节确定，如实记录）。
# ---------------------------------------------------------------------------

def _exports_root(root: Path) -> Path:
    return root / "exports"


def _w(tag: str) -> str:
    """WordprocessingML 限定名（{uri}tag 形，w: 命名空间）。"""
    return f"{{{_W_NS}}}{tag}"


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _docx_para(text: str, *, bold: bool = False,
               center: bool = False) -> "ET.Element":
    para = ET.Element(_w("p"))
    ppr = ET.SubElement(para, _w("pPr"))
    if center:
        ET.SubElement(ET.SubElement(ppr, _w("jc")), _w("val")).text = \
            "center"
    run = ET.SubElement(para, _w("r"))
    if bold:
        ET.SubElement(run, _w("rPr")).append(ET.Element(_w("b")))
    wt = ET.SubElement(run, _w("t"))
    wt.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    wt.text = text
    return para


def render_contract_docx(title: str, body_text: str) -> bytes:
    """合同 docx 字节（确定性）：标题居中加粗段＋逐行段落——「## 节名」
    行渲染为加粗节标题段，其余非空行为正文段；A4 纵向 sectPr。"""
    document = ET.Element(_w("document"))
    body = ET.SubElement(document, _w("body"))
    body.append(_docx_para(title, bold=True, center=True))
    for line in (body_text or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("## "):
            body.append(_docx_para(stripped[3:].strip(), bold=True))
        else:
            body.append(_docx_para(stripped))
    sect = ET.SubElement(body, _w("sectPr"))
    ET.SubElement(sect, _w("pgSz"), w="11906", h="16838")
    ET.SubElement(sect, _w("pgMar"), top="1440", right="1440",
                  bottom="1440", left="1440", header="0", footer="0",
                  gutter="0")
    ET.register_namespace("w", _W_NS)
    xml_bytes = (b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                 b"\r\n" + ET.tostring(document, encoding="utf-8",
                                       xml_declaration=False))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for name in sorted(_DOCX_FIXED_PARTS):
            info = zipfile.ZipInfo(name, date_time=_ZIP_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            dst.writestr(info, _DOCX_FIXED_PARTS[name].encode("utf-8"))
        info = zipfile.ZipInfo("word/document.xml", date_time=_ZIP_DATE)
        info.compress_type = zipfile.ZIP_DEFLATED
        dst.writestr(info, xml_bytes)
    return out.getvalue()


def _render_pdf(binary: Path, state_root: Path, docx_path: Path,
                out_dir: Path, timeout_s: int) -> Path:
    """docx→pdf（LibreOffice headless，F58 纪律同构）：UserInstallation
    隔离于状态根；失败/超时/空产物＝清 staging 半成品＋typed 拒。"""
    staging = out_dir / "staging"
    staging.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(docx_path, staging / "input.docx")
    profile = (Path(state_root) / "contract_gate" / "lo-profile").resolve()
    profile.mkdir(parents=True, exist_ok=True)
    argv = [str(binary), "--headless", "--norestore", "--nolockcheck",
            "-env:UserInstallation=" + profile.as_uri(),
            "--convert-to", "pdf",
            "--outdir", str(staging), str(staging / "input.docx")]
    try:
        proc = subprocess.run(argv, capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              timeout=timeout_s)
    except subprocess.TimeoutExpired:
        shutil.rmtree(staging, ignore_errors=True)
        raise _fail("cg37_render_timeout") from None
    except OSError as exc:
        shutil.rmtree(staging, ignore_errors=True)
        raise _fail(f"cg37_render_failed:{type(exc).__name__}") from None
    produced = staging / "input.pdf"
    if proc.returncode != 0 or not produced.is_file():
        shutil.rmtree(staging, ignore_errors=True)
        raise _fail(f"cg37_render_failed:exit{proc.returncode}")
    if produced.stat().st_size == 0:
        shutil.rmtree(staging, ignore_errors=True)
        raise _fail("cg37_empty_render_output")
    target = out_dir / "contract.pdf"
    shutil.move(str(produced), str(target))
    shutil.rmtree(staging, ignore_errors=True)
    return target


def _export_contract_files(state_root, config: dict, title: str,
                           body_text: str, output_format: str) -> dict:
    """按格式落导出件（exports/<seq>/ append-only）：docx 恒真渲染；
    pdf/both 需 config libreoffice_soffice（F54/F58 同源键）——未配置/
    渲染失败＝typed 拒且**清空本次导出目录**（盘上不留半成品）。"""
    fmt_docx = output_format in ("docx", "pdf", "both")
    fmt_pdf = output_format in ("pdf", "both")
    if fmt_pdf:
        raw = config.get("libreoffice_soffice") if config else None
        binary = None
        if isinstance(raw, str) and raw:
            path = Path(raw)
            if os.name == "nt" and path.name.lower() == "soffice.exe":
                com = path.with_name("soffice.com")
                if com.is_file():
                    path = com
            binary = path if path.is_file() else None
        if binary is None:
            raise _fail("cg37_soffice_not_configured")
    with _LOCK:
        root = _root(state_root)
        seq = _next_seq(_exports_root(root))
        out_dir = _exports_root(root) / f"{seq:06d}"
        out_dir.mkdir(parents=True, exist_ok=False)
    try:
        paths: dict[str, object] = {}
        if fmt_docx:
            docx_bytes = render_contract_docx(title, body_text)
            docx_path = out_dir / "contract.docx"
            docx_path.write_bytes(docx_bytes)
            paths["docx_path"] = str(docx_path)
            paths["docx_sha256"] = _sha256_bytes(docx_bytes)
        if fmt_pdf:
            timeout_s = int((config or {}).get(
                "conversion_timeout_s", SOFFICE_TIMEOUT_DEFAULT))
            pdf_path = _render_pdf(binary, Path(state_root), docx_path,
                                   out_dir, timeout_s)
            paths["pdf_path"] = str(pdf_path)
        return paths
    except Exception:
        shutil.rmtree(out_dir, ignore_errors=True)  # 不留半成品
        raise


def assemble_contract(state_root, contract_type: str, *, scenario=None,
                      stance=None, custom_clause_ids=None,
                      output_format: str = "markdown",
                      config: dict | None = None) -> dict:
    """装配（B10-B15）：逐节覆盖+扩展 → 指令并集 → law_refs 归集 →
    coherence 门 → 装配态产出（每个槽为可填占位符，**不预填**）。

    导出四格式（B15 边界件）：markdown（body_text 原样）/docx/pdf/both
    （落 exports/<seq>/ 导出件，pdf 需 config libreoffice_soffice）。
    产出体 {title, body_text, slots, instructions, law_refs,
    diagnostics{heuristic_sections}, docx_path?, docx_sha256?, pdf_path?}。"""
    if output_format not in OUTPUT_FORMATS:
        raise _fail(f"cg37_format_not_supported:{output_format}")
    base, tagged, custom = _select_clauses(
        state_root, contract_type, scenario, stance, custom_clause_ids)
    resolved, heuristic, base_sections = _resolve_sections(
        base, tagged, custom)
    parts: list[str] = []
    for clause in resolved:
        body = (clause.get("body") or "").strip()
        if body:
            parts.append(f"## {clause['section']}\n\n{body}")
    body_text = "\n\n".join(parts).strip()
    instructions = _build_instructions(resolved)
    validate_coherence(resolved, body_text, instructions, base_sections)
    law_refs = _build_law_refs(resolved)
    slots = sorted({slot for clause in resolved
                    for slot in slots_in(clause.get("body") or "")})
    title = f"{contract_type}合同（装配稿）"
    payload = {"schema": SCHEMA, "title": title, "format": output_format,
               "body_text": body_text, "slots": slots,
               "instructions": instructions, "law_refs": law_refs,
               "diagnostics": {"heuristic_sections": heuristic}}
    if output_format != "markdown":
        payload.update(_export_contract_files(
            state_root, config, title, body_text, output_format))
    return payload


# ---------------------------------------------------------------------------
# D 组（上）：rubric 库——两表语义/两档来源/版本命名/CRUD
# ---------------------------------------------------------------------------

_RUBRIC_NAME_RE = re.compile(r"^[A-Za-z0-9\u4e00-\u9fff][A-Za-z0-9\u4e00-\u9fff._-]{0,127}$")


def _rubrics_root(root: Path) -> Path:
    return root / "rubrics"


def _load_rubric(root: Path, name: str) -> dict | None:
    return _read_json(_rubrics_root(root) / f"{name}.json")


def _save_rubric(root: Path, rubric: dict) -> None:
    directory = _rubrics_root(root)
    directory.mkdir(parents=True, exist_ok=True)
    _atomic_write(directory / f"{rubric['name']}.json", _dump(rubric))


def _require_rubric(root: Path, name: str) -> dict:
    rubric = _load_rubric(root, name)
    if rubric is None:
        raise _fail(f"cg37_rubric_not_found:{name}")
    return rubric


def load_criteria(root: Path, name: str) -> list[dict]:
    """评审器消费形（B21）：criteria 按 ordinal 排序；rubric 无 criteria
    抛 ValueError（cg37_rubric_empty_criteria）、名字未知抛 KeyError 形
    typed 拒（cg37_rubric_not_found）。"""
    rubric = _require_rubric(root, name)
    criteria = rubric.get("criteria") or []
    if not criteria:
        raise _fail(f"cg37_rubric_empty_criteria:{name}")
    return sorted(criteria, key=lambda c: c["ordinal"])


def default_rubric(state_root, contract_type: str) -> str:
    """default_rubric（B23）：版本化名取最高 v<N>；无版本化名取
    contract_<type>_* 字典序最后；没有则 NotFoundError 形 typed 拒。"""
    _require_type_name(contract_type)
    with _LOCK:
        root = _root(state_root)
        names = sorted(entry.stem for entry
                       in _rubrics_root(root).glob("*.json"))
    prefix = f"contract_{contract_type}_"
    best_version = None
    best_plain = None
    for name in names:
        if not name.startswith(prefix):
            continue
        match = DEFAULT_RUBRIC_RE.match(name)
        if match:
            version = int(match.group(2))
            if best_version is None or version > best_version:
                best_version = version
        elif best_plain is None or name > best_plain:
            best_plain = name
    if best_version is not None:
        return f"{prefix}v{best_version}"
    if best_plain is not None:
        return best_plain
    raise _fail(f"cg37_rubric_not_found:default:{contract_type}")


def _require_dual_branch(criterion_id: str, match_criteria: str) -> None:
    """A37-H1 判据双分支（RE-37 增补节）：每条 match_criteria 必须同时含
    PASS 条件与 FAIL 条件（「PASS if…/FAIL if…」双分支形状，Harvey LAB
    7 包 363 条 100% 双分支的口径学），缺一即 typed 具名拒。"""
    upper = (match_criteria or "").upper()
    if not all(mark in upper for mark in DUAL_BRANCH_REQUIRED):
        raise _fail(f"cg37_criterion_single_branch:{criterion_id}")


def _validate_criteria_list(criteria) -> list[dict]:
    if not isinstance(criteria, list) or not criteria:
        raise _fail("cg37_criteria_invalid")
    seen: set[str] = set()
    cleaned: list[dict] = []
    for item in criteria:
        if not isinstance(item, dict) \
                or not isinstance(item.get("id"), str) \
                or not item["id"].strip() \
                or item["id"] in seen:
            raise _fail("cg37_criteria_invalid")
        seen.add(item["id"])
        title = item.get("title")
        match_criteria = item.get("match_criteria")
        if not isinstance(title, str) or not title.strip() \
                or not isinstance(match_criteria, str) \
                or not match_criteria.strip():
            raise _fail("cg37_criteria_invalid")
        _require_dual_branch(item["id"], match_criteria)
        cleaned.append({"id": item["id"], "title": title,
                        "match_criteria": match_criteria})
    return cleaned


def _check_granularity(count: int, exemption) -> None:
    """A37-H3 粒度对标（RE-37 增补节）：自研 rubric 每类准则数 ∈ [25,60]
    （命题级拆条目标区间，Harvey LAB 32-64 条/包口径）；越界须显式豁免
    账（非空字符串理由，随 rubric 行落账）。"""
    if GRANULARITY_MIN <= count <= GRANULARITY_MAX:
        return
    if isinstance(exemption, str) and exemption.strip():
        return
    raise _fail(f"cg37_granularity_out_of_range:{count}:"
                f"[{GRANULARITY_MIN},{GRANULARITY_MAX}]")


def rubric_create(state_root, args: dict) -> dict:
    """rubric_create：新建（baseline 档=种子导入路径，创建后只读；
    local 档=本地可写）。criteria 三字段 id/title/match_criteria，
    ordinal 追加序 1..N。重名＝typed 拒。A37-H1 双分支逐条校验；
    A37-H3 粒度区间校验（越界须 granularity_exemption 显式豁免账，
    拆分轴登记 granularity_axes）。"""
    if not isinstance(args, dict):
        raise _fail("cg37_params_invalid")
    name = args.get("name")
    if not isinstance(name, str) or not _RUBRIC_NAME_RE.match(name):
        raise _fail("cg37_rubric_name_invalid")
    source = args.get("source", "local")
    if source not in RUBRIC_SOURCES:
        raise _fail("cg37_rubric_source_invalid")
    description = args.get("description", "")
    if not isinstance(description, str):
        raise _fail("cg37_rubric_description_invalid")
    criteria = _validate_criteria_list(args.get("criteria"))
    exemption = args.get("granularity_exemption")
    if exemption is not None and not (isinstance(exemption, str)
                                      and exemption.strip()):
        raise _fail("cg37_granularity_exemption_invalid")
    _check_granularity(len(criteria), exemption)
    axes = args.get("granularity_axes", list(GRANULARITY_AXES))
    if not isinstance(axes, list) \
            or not all(isinstance(a, str) and a.strip() for a in axes):
        raise _fail("cg37_granularity_axes_invalid")
    with _LOCK:
        root = _root(state_root)
        if _load_rubric(root, name) is not None:
            raise _fail(f"cg37_rubric_exists:{name}")
        rubric = {"schema": SCHEMA, "name": name, "context": None,
                  "source": source, "description": description,
                  "granularity_axes": axes,
                  "granularity_exemption": exemption or "",
                  "criteria": [{**c, "ordinal": i + 1}
                               for i, c in enumerate(criteria)]}
        _save_rubric(root, rubric)
        return rubric_view(rubric)


def rubric_view(rubric: dict) -> dict:
    return {"schema": SCHEMA, "name": rubric["name"],
            "source": rubric["source"],
            "description": rubric.get("description") or "",
            "granularity_axes": rubric.get("granularity_axes")
            or list(GRANULARITY_AXES),
            "granularity_exemption": rubric.get("granularity_exemption")
            or "",
            "criteria_count": len(rubric.get("criteria") or []),
            "criteria": [dict(c) for c in
                         sorted(rubric.get("criteria") or [],
                                key=lambda c: c["ordinal"])]}


def _require_writable(rubric: dict) -> None:
    """两档来源纪律（B22/T11）：baseline 只读——任何写操作 typed 拒。"""
    if rubric.get("source") == "baseline":
        raise BaselineReadOnlyError(
            f"cg37_baseline_readonly:{rubric['name']}")


def rubric_update(state_root, args: dict) -> dict:
    if not isinstance(args, dict):
        raise _fail("cg37_params_invalid")
    name = args.get("name")
    if not isinstance(name, str):
        raise _fail("cg37_rubric_name_invalid")
    description = args.get("description")
    if description is not None and not isinstance(description, str):
        raise _fail("cg37_rubric_description_invalid")
    with _LOCK:
        root = _root(state_root)
        rubric = _require_rubric(root, name)
        _require_writable(rubric)
        if description is not None:
            rubric["description"] = description
        _save_rubric(root, rubric)
        return rubric_view(rubric)


def rubric_delete(state_root, args: dict) -> dict:
    if not isinstance(args, dict):
        raise _fail("cg37_params_invalid")
    name = args.get("name")
    if not isinstance(name, str):
        raise _fail("cg37_rubric_name_invalid")
    with _LOCK:
        root = _root(state_root)
        rubric = _require_rubric(root, name)
        _require_writable(rubric)
        (_rubrics_root(root) / f"{name}.json").unlink()
        return {"schema": SCHEMA, "deleted": name}


def _require_criterion(rubric: dict, criterion_id: str) -> dict:
    for criterion in rubric["criteria"]:
        if criterion["id"] == criterion_id:
            return criterion
    raise _fail(f"cg37_criterion_not_found:{rubric['name']}:{criterion_id}")


def _renumber(rubric: dict) -> None:
    for i, criterion in enumerate(
            sorted(rubric["criteria"], key=lambda c: c["ordinal"])):
        criterion["ordinal"] = i + 1


def criterion_add(state_root, args: dict) -> dict:
    """criterion_add：末尾追加（ordinal=N+1）。"""
    if not isinstance(args, dict):
        raise _fail("cg37_params_invalid")
    name = args.get("rubric")
    if not isinstance(name, str):
        raise _fail("cg37_rubric_name_invalid")
    cleaned = _validate_criteria_list([args])
    with _LOCK:
        root = _root(state_root)
        rubric = _require_rubric(root, name)
        _require_writable(rubric)
        if any(c["id"] == cleaned[0]["id"] for c in rubric["criteria"]):
            raise _fail(f"cg37_criterion_exists:{name}:{cleaned[0]['id']}")
        _check_granularity(len(rubric["criteria"]) + 1,
                           rubric.get("granularity_exemption"))
        rubric["criteria"].append(
            {**cleaned[0],
             "ordinal": len(rubric["criteria"]) + 1})
        _save_rubric(root, rubric)
        return rubric_view(rubric)


def criterion_update(state_root, args: dict) -> dict:
    if not isinstance(args, dict):
        raise _fail("cg37_params_invalid")
    name = args.get("rubric")
    criterion_id = args.get("id")
    if not isinstance(name, str) or not isinstance(criterion_id, str):
        raise _fail("cg37_params_invalid")
    with _LOCK:
        root = _root(state_root)
        rubric = _require_rubric(root, name)
        _require_writable(rubric)
        criterion = _require_criterion(rubric, criterion_id)
        for field in ("title", "match_criteria"):
            if args.get(field) is not None:
                if not isinstance(args[field], str) or not args[field].strip():
                    raise _fail("cg37_criteria_invalid")
                if field == "match_criteria":
                    _require_dual_branch(criterion_id, args[field])
                criterion[field] = args[field]
        _save_rubric(root, rubric)
        return rubric_view(rubric)


def criterion_delete(state_root, args: dict) -> dict:
    """criterion_delete：删除后幸存者重编号（B33）。"""
    if not isinstance(args, dict):
        raise _fail("cg37_params_invalid")
    name = args.get("rubric")
    criterion_id = args.get("id")
    if not isinstance(name, str) or not isinstance(criterion_id, str):
        raise _fail("cg37_params_invalid")
    with _LOCK:
        root = _root(state_root)
        rubric = _require_rubric(root, name)
        _require_writable(rubric)
        criterion = _require_criterion(rubric, criterion_id)
        rubric["criteria"].remove(criterion)
        if not rubric["criteria"]:
            raise _fail(f"cg37_rubric_empty_criteria:{name}")
        _check_granularity(len(rubric["criteria"]),
                           rubric.get("granularity_exemption"))
        _renumber(rubric)
        _save_rubric(root, rubric)
        return rubric_view(rubric)


def criterion_reorder(state_root, args: dict) -> dict:
    """criterion_reorder：须传全序（缺/多任一＝校验拒），按全序重编号。"""
    if not isinstance(args, dict):
        raise _fail("cg37_params_invalid")
    name = args.get("rubric")
    order = args.get("order")
    if not isinstance(name, str) or not isinstance(order, list) \
            or not all(isinstance(x, str) for x in order):
        raise _fail("cg37_params_invalid")
    with _LOCK:
        root = _root(state_root)
        rubric = _require_rubric(root, name)
        _require_writable(rubric)
        existing = {c["id"] for c in rubric["criteria"]}
        if set(order) != existing or len(order) != len(existing):
            raise _fail("cg37_reorder_not_full_order")
        by_id = {c["id"]: c for c in rubric["criteria"]}
        rubric["criteria"] = [{**by_id[cid], "ordinal": i + 1}
                              for i, cid in enumerate(order)]
        _save_rubric(root, rubric)
        return rubric_view(rubric)


def rubric_list(state_root, args: dict) -> dict:
    if not isinstance(args, dict):
        raise _fail("cg37_params_invalid")
    with _LOCK:
        root = _root(state_root)
        rubrics = [_read_json(entry) for entry
                   in sorted(_rubrics_root(root).glob("*.json"))]
    rows = [{"name": r["name"], "source": r["source"],
             "description": r.get("description") or "",
             "granularity_exemption": r.get("granularity_exemption") or "",
             "criteria_count": len(r.get("criteria") or [])}
            for r in rubrics if r is not None]
    return {"schema": SCHEMA, "rubrics": rows, "count": len(rows)}


def rubric_get(state_root, args: dict) -> dict:
    if not isinstance(args, dict):
        raise _fail("cg37_params_invalid")
    name = args.get("name")
    if not isinstance(name, str):
        raise _fail("cg37_rubric_name_invalid")
    with _LOCK:
        root = _root(state_root)
        rubric = _require_rubric(root, name)
        if not rubric.get("criteria"):
            raise _fail(f"cg37_rubric_empty_criteria:{name}")
        return rubric_view(rubric)


# ---------------------------------------------------------------------------
# LLM 注入面 + D 组（下）：评分门（all-pass 二值/独立 judge/退避/快照）
# ---------------------------------------------------------------------------

def _resolve_llm(config: dict) -> dict:
    seam = config.get(CONFIG_LLM)
    if not isinstance(seam, dict) \
            or not callable(seam.get("complete")) \
            or not isinstance(seam.get("model"), str):
        raise _llm_not_connected()
    return seam


def _llm_not_connected():
    from bridge_errors import NotConnected
    return NotConnected("cg37_llm_seam_not_configured")


def _is_transient(exc: BaseException) -> bool:
    if isinstance(exc, TransientLLMError):
        return True
    text = str(exc)
    return any(mark in text for mark in TRANSIENT_MARKS)


def _parse_json_object(raw: str) -> dict:
    """解析容错（B19 同族）：剥代码围栏→裸对象截取→json.loads；
    坏输出→空 dict 不崩。"""
    text = (raw or "").strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    if not text.startswith("{"):
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1 and end > start:
            text = text[start:end + 1]
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def build_fill_prompt(contract_type: str, scenario, instructions: list,
                      task_desc) -> tuple[str, str]:
    """填槽提示词（B18 契约，自写文案）：角色+槽清单+场景/需求上下文+
    严格 JSON 输出契约。金额按自家机检口径要求十进制数字串（非竞品
    「金额用数字」——有意增强）。返回 (system, user)。"""
    lines = "\n".join(
        f"- {i['name']}（{i.get('label') or i['name']}，{i.get('kind')}）："
        f"{i.get('description') or ''} 示例：{i.get('example') or ''}"
        for i in instructions)
    scene = f"{scenario}场景下的" if scenario else ""
    task_line = ""
    if task_desc:
        task_line = (f"\n\n起草需求（标的等槽值必须符合此需求）：\n{task_desc}")
    system = ("你是合同条款填槽助手，只输出严格 JSON 对象，不输出任何"
              "解释或围栏外的文字。")
    user = (f"请为一份{scene}{contract_type}合同填写槽值。槽清单：\n"
            f"{lines}{task_line}\n\n"
            "填写要求：每个槽给出一个具体值（金额类槽用十进制数字串，"
            "不用货币符号也不用科学计数法；日期类槽用 YYYY-MM-DD 且必须是"
            "真实日历日；标的类槽值须贴合场景与起草需求；各槽值互相一致）。"
            '仅输出严格 JSON：{"槽名": "值"}。')
    return system, user


def fill_slots(state_root, config: dict, contract_type: str, scenario,
               slots: list[str], instructions: list, *, task_desc=None,
               temperature: float = 0.0, llm: dict | None = None) -> dict:
    """填槽（B16-B20）：fill_cache 六元组键命中即跳过 LLM；槽序归一化、
    task_desc 入键。LLM 只产候选值——机检不过 typed 拒（§4.2 有意增强）。
    返回 {fill_values, fill_cache_id, hit, model, temperature}。"""
    if llm is None:
        llm = _resolve_llm(config)
    slots_sorted = ",".join(sorted(slots))
    key = _sha1(f"{contract_type}|{scenario}|{slots_sorted}"
                f"|{llm['model']}|{temperature}|{task_desc or ''}")
    fills_dir = _root(state_root) / "fills"
    cached = _read_json(fills_dir / f"{key}.json")
    if cached is not None:
        return {"fill_values": cached["fill_values"],
                "fill_cache_id": key, "hit": True,
                "model": cached.get("model"),
                "temperature": cached.get("temperature")}
    system, user = build_fill_prompt(contract_type, scenario,
                                     instructions, task_desc)
    raw = llm["complete"](system, user)
    values = {name: value for name, value
              in _parse_json_object(raw).items() if name in slots}
    for name in sorted(values):
        if name in slots:
            check_slot_value(name, values[name])
    fills_dir.mkdir(parents=True, exist_ok=True)
    _atomic_write(fills_dir / f"{key}.json", _dump({
        "id": key, "contract_type": contract_type, "scenario": scenario,
        "slots_hash": _sha1(slots_sorted),
        "fill_values": values, "temperature": temperature,
        "model": llm["model"]}))
    return {"fill_values": values, "fill_cache_id": key, "hit": False,
            "model": llm["model"], "temperature": temperature}


def render_filled(body_text: str, fill_values: dict) -> tuple[str, list[str]]:
    """逐槽替换；值为空/缺失的槽保留原占位符并上报 unfilled 清单（B20）。"""
    unfilled: list[str] = []

    def _replace(match: "re.Match[str]") -> str:
        name = normalize_slot_name(match.group(1))
        value = fill_values.get(name)
        if value is None or value == "":
            unfilled.append(name)
            return match.group(0)
        return str(value)

    return SLOT_PATTERN.sub(_replace, body_text or ""), unfilled


def build_judge_prompt(criterion: dict, contract_text: str,
                       task_desc) -> tuple[str, str]:
    """judge 评分提示词（B21/B26+A37-H1/H2 固定骨架，自写文案）：评分
    标准=规则 match_criteria 的 PASS/FAIL 判据（零手写评分 prompt——
    guidance 即评分提示词）；固定骨架三句＝语义实质判定而非逐字匹配＋
    FAIL 条件独立检验（PASS 条件命中不算过、FAIL 条件未触发才过）＋
    锚定三件套输出契约（location 自节名枚举、quote 为正文原样子串）；
    上下文分立：合同正文恒在，task_desc 有才附。返回 (system, user)。"""
    task_line = ""
    if task_desc:
        task_line = f"\n\n起草需求（判定时作上下文）：\n{task_desc}"
    sections = "、".join(split_sections(contract_text)) or "（无节名）"
    system = ("你是合同起草质量评审员。对给定评审项严格按判据给出二值"
              "结论与锚定三件套，只输出严格 JSON：{\"verdict\": \"pass\""
              " 或 \"fail\", \"location\": \"结论所依据的节名（必须从"
              "节名枚举中选一个）\", \"quote\": \"支撑判定的合同正文"
              "原文引句\", \"reasoning\": \"一句话判定理由\"}，不输出"
              "解释。判定纪律：按语义实质判定而非逐字匹配；PASS 条件"
              "命中不算过，FAIL 条件未触发才过（双向检验）；引句必须是"
              "合同正文的原样子串。")
    user = (f"评审项：{criterion['title']}\n判据（PASS if…/FAIL if…）：\n"
            f"{criterion['match_criteria']}\n\n节名枚举：{sections}\n\n"
            f"合同正文：\n{contract_text}{task_line}")
    return system, user


def _anchor_status(verdict: str, location, quote,
                   contract_text: str) -> str:
    """A37-H2 锚定机械校验（确定性，零模型）：quote 须为产出物文本非空
    子串、location 须命中产出物节名枚举（split_sections）；pass 判定
    锚不过＝invalid 不计 pass（verdict 强制 fail，值域仍钉 {pass,fail}）；
    fail 判定锚不过维持 fail（本就不计 pass），anchor_status 具名留审计。"""
    sections = split_sections(contract_text)
    if not isinstance(quote, str) or not quote.strip() \
            or quote not in contract_text:
        return "invalid:quote_not_substring"
    if not isinstance(location, str) or location not in sections:
        return "invalid:location_not_in_sections"
    return "ok"


def _judge_one(criterion: dict, contract_text: str, task_desc,
               llm: dict, backoff_seconds: float) -> dict:
    """单条规则独立 judge（B25-B28+A37-H2）：3 次尝试；瞬态（429/503 类）
    退避 8s×(attempt+1) 重试且不得计 FAIL；重试耗尽或非瞬态错误→error
    入该条 reasoning、verdict=fail、跑继续；坏输出/三件套缺件→fail+
    具名 error；pass 判定锚定机械校验不过→verdict 强制 fail+
    anchor_status 具名。"""
    system, user = build_judge_prompt(criterion, contract_text, task_desc)
    error = ""
    for attempt in range(JUDGE_ATTEMPTS):
        try:
            raw = llm["complete"](system, user)
            data = _parse_json_object(raw)
            verdict = data.get("verdict")
            reasoning = data.get("reasoning")
            location = data.get("location")
            quote = data.get("quote")
            if verdict not in ("pass", "fail") \
                    or not isinstance(reasoning, str) \
                    or not isinstance(location, str) \
                    or not isinstance(quote, str):
                return {"id": criterion["id"], "title": criterion["title"],
                        "verdict": "fail", "location": location or "",
                        "quote": quote or "", "anchor_status":
                        "invalid:trio_missing",
                        "reasoning": "[error: judge_output_unparsable]"}
            status = _anchor_status(verdict, location, quote, contract_text)
            if verdict == "pass" and status != "ok":
                verdict = "fail"  # 引句非子串即判 invalid 不计 pass（A37-H2）
            return {"id": criterion["id"], "title": criterion["title"],
                    "verdict": verdict, "location": location, "quote": quote,
                    "anchor_status": status, "reasoning": reasoning}
        except Exception as exc:  # 单 judge 失败不沉船（B28）
            error = f"{type(exc).__name__}: {exc}"[:200]
            if _is_transient(exc) and attempt < JUDGE_ATTEMPTS - 1:
                import time
                time.sleep(backoff_seconds * (attempt + 1))
                continue
            break
    return {"id": criterion["id"], "title": criterion["title"],
            "verdict": "fail", "location": "", "quote": "",
            "anchor_status": "invalid:error",
            "reasoning": f"[error: {error}]"}


def _resolve_workers(requested, n_rules: int) -> int:
    if requested is None:
        requested = JUDGE_WORKERS_DEFAULT
    if not isinstance(requested, int) or isinstance(requested, bool):
        raise _fail("cg37_max_workers_invalid")
    return max(1, min(requested, JUDGE_WORKERS_CEILING, n_rules))


def _evals_root(root: Path) -> Path:
    return root / "evals"


def _consensus(judge_results: list[dict], n_judges: int) -> dict:
    """multi-judge 逐条多数投票（B31，自研干净口径）：consensus=pass 当且
    仅当 pass 票>fail 票（平票 fail-closed 归 fail）；confidence=胜方票/
    n_judges；unanimous/majority/tie 分记（平票单记 tie，不冒充多数）；
    consensus reasoning/锚定三件套取首个与共识同判 judge。verdict 值域
    仍钉 {pass,fail}（RE-12 衔接断言①）。"""
    votes_pass = sum(1 for r in judge_results if r["verdict"] == "pass")
    votes_fail = n_judges - votes_pass
    verdict = "pass" if votes_pass > votes_fail else "fail"
    kind = ("unanimous" if min(votes_pass, votes_fail) == 0
            else "tie" if votes_pass == votes_fail else "majority")
    confidence = (votes_pass if verdict == "pass" else votes_fail) / n_judges
    member = next((r for r in judge_results if r["verdict"] == verdict),
                  judge_results[0])
    return {"id": member["id"], "title": member["title"],
            "verdict": verdict, "location": member["location"],
            "quote": member["quote"], "anchor_status": member["anchor_status"],
            "reasoning": member["reasoning"],
            "votes": {"pass": votes_pass, "fail": votes_fail},
            "confidence": confidence, "kind": kind}


def evaluate_contract(state_root, config: dict, contract_text: str,
                      rubric_name: str, *, task_desc=None, llm: dict | None,
                      max_workers=None, backoff_seconds=JUDGE_BACKOFF_SECONDS,
                      compare_run_id=None, prompt_name=None,
                      variant_label=None, n_judges=1) -> dict:
    """评分门（B24-B32）：每条规则一个独立 judge 并发评审（默认 8、钳
    [1,16]、按规则数封顶）→ all-pass 二值聚合（全过 1.0 否则 0.0，无部分
    得分）→ 评估账落库（**快照语义**：rubric 名+criteria+合同文本+
    task_desc 快照随行，记录不随后续 rubric 编辑/删除失效）。

    multi-judge 增强档（B31-B32/T19，边界件）：n_judges≥2 时 N 个 judge
    各跑全套、逐条规则多数投票（_consensus）；low_confidence＝干净定义：
    任一条 confidence<0.67 即低信，对任意面板规模统一适用（**不复制**
    竞品「n_judges<3 才判、3-judge 面板恒 False」特异式）；score=1.0 须
    all_pass 且非低信；全 judge 调用皆败＝typed 拒（B58 空态族）。"""
    if not isinstance(contract_text, str) or not contract_text.strip():
        raise _fail("cg37_contract_text_invalid")
    if not isinstance(n_judges, int) or isinstance(n_judges, bool) \
            or not 1 <= n_judges <= JUDGE_PANEL_CEILING:
        raise _fail("cg37_n_judges_invalid")
    if llm is None:
        llm = _resolve_llm(config)
    with _LOCK:
        root = _root(state_root)
        criteria = load_criteria(root, rubric_name)
    workers = _resolve_workers(max_workers, len(criteria))
    judge_model = llm.get("judge_model") or llm["model"]

    def _judge_panel(criterion: dict) -> list[dict]:
        return [_judge_one(criterion, contract_text, task_desc, llm,
                           backoff_seconds) for _ in range(n_judges)]

    with ThreadPoolExecutor(max_workers=workers) as pool:
        groups = list(pool.map(_judge_panel, criteria))
    if all(r["reasoning"].startswith("[error:")
           for group in groups for r in group):
        raise _fail("cg37_all_judges_failed")  # 全 judge 败（B58 空态族）
    results = [_consensus(group, n_judges) for group in groups]
    n_total = len(results)
    n_passed = sum(1 for r in results if r["verdict"] == "pass")
    all_pass = n_passed == n_total
    low_confidence = any(r["confidence"] < LOW_CONFIDENCE_THRESHOLD
                         for r in results)
    summary = (f"{n_passed}/{n_total} 项通过，全部通过。"
               if all_pass
               else f"{n_passed}/{n_total} 项通过，差 {n_total - n_passed} 条未过。")
    if low_confidence:
        min_conf = min(r["confidence"] for r in results)
        summary += f"（{n_judges}-judge 面板低信：最低置信 {min_conf:.3f}）"
    with _LOCK:
        seq = _next_seq(_evals_root(root))
        run = {
            "schema": SCHEMA, "run_id": seq, "rubric": rubric_name,
            "criteria_snapshot": [dict(c) for c in criteria],
            "contract_text": contract_text, "task_desc": task_desc,
            "judge_model": judge_model, "criteria_results": results,
            "score": 1.0 if all_pass and not low_confidence else 0.0,
            "max_score": 1.0,
            "all_pass": all_pass, "n_criteria": n_total,
            "n_passed": n_passed, "summary": summary,
            "n_judges": n_judges, "low_confidence": low_confidence,
            "compare_run_id": compare_run_id, "prompt_name": prompt_name,
            "variant_label": variant_label,
        }
        _write_seq_json(_evals_root(root), seq, run)
    return _eval_view(run)


def _eval_view(run: dict, *, with_text: bool = True) -> dict:
    view = {key: run.get(key) for key in (
        "schema", "run_id", "rubric", "criteria_snapshot", "task_desc",
        "judge_model", "criteria_results", "score", "max_score",
        "all_pass", "n_criteria", "n_passed", "summary",
        "n_judges", "low_confidence",
        "compare_run_id", "prompt_name", "variant_label")}
    if with_text:
        view["contract_text"] = run.get("contract_text")
    return view


def run_list(state_root, args: dict) -> dict:
    """评估账清单（B54 list 面；正文体积大默认不带）。"""
    if not isinstance(args, dict):
        raise _fail("cg37_params_invalid")
    with _LOCK:
        rows = _load_seq_jsons(_evals_root(_root(state_root)))
    return {"schema": SCHEMA, "runs": [_eval_view(r, with_text=False)
                                       for r in rows], "count": len(rows)}


def run_get(state_root, args: dict) -> dict:
    if not isinstance(args, dict):
        raise _fail("cg37_params_invalid")
    run_id = args.get("run_id")
    if not isinstance(run_id, int) or isinstance(run_id, bool):
        raise _fail("cg37_run_id_invalid")
    with _LOCK:
        rows = _load_seq_jsons(_evals_root(_root(state_root)))
    for row in rows:
        if row.get("run_id") == run_id:
            return _eval_view(row)
    raise _fail(f"cg37_run_not_found:{run_id}")


def _contract_type_of_rubric(rubric_name: str) -> str | None:
    """rubric 名 → 合同类型（contract_<type>_v<N> 确定解析；版本化名优先，
    其余 contract_ 前缀去前缀；非合同 rubric＝None 不入分型）。"""
    match = DEFAULT_RUBRIC_RE.match(rubric_name or "")
    if match:
        return match.group(1)
    if rubric_name and rubric_name.startswith("contract_"):
        return rubric_name[len("contract_"):]
    return None


def dashboard(state_root, args: dict) -> dict:
    """dashboard 只读聚合（B56/T31，边界件）：总运行数/all_pass 数/平均
    通过率/按类型最高通过率（类型自 rubric 名确定解析；非合同 rubric 只入
    总量不入分型——fail-closed 不猜）。零写面，纯评估账投影。"""
    if not isinstance(args, dict):
        raise _fail("cg37_params_invalid")
    with _LOCK:
        rows = _load_seq_jsons(_evals_root(_root(state_root)))
    runs_total = len(rows)
    runs_all_pass = sum(1 for r in rows if r.get("all_pass"))
    avg_pass_rate = (sum((r.get("n_passed") or 0) / (r.get("n_criteria") or 1)
                         for r in rows) / runs_total) if rows else 0.0
    by_type: dict[str, dict] = {}
    for row in rows:  # 行序=run_id 序，best 取首达最高（确定性）
        contract_type = _contract_type_of_rubric(row.get("rubric") or "")
        if contract_type is None:
            continue  # 非合同 rubric 不入分型（不猜类型）
        n_criteria = row.get("n_criteria") or 1
        pass_rate = (row.get("n_passed") or 0) / n_criteria
        bucket = by_type.setdefault(
            contract_type, {"runs": 0, "all_pass": 0, "best_pass_rate": 0.0,
                            "best_rubric": row.get("rubric")})
        bucket["runs"] += 1
        if row.get("all_pass"):
            bucket["all_pass"] += 1
        if pass_rate > bucket["best_pass_rate"]:
            bucket["best_pass_rate"] = pass_rate
            bucket["best_rubric"] = row.get("rubric")
    return {"schema": SCHEMA, "runs_total": runs_total,
            "runs_all_pass": runs_all_pass,
            "avg_pass_rate": avg_pass_rate, "best_by_type": by_type}


# ---------------------------------------------------------------------------
# 母版再生（B57/T32，边界件）：LLM seam 面等量——竞品子进程 --force 换
# 自家进程内 seam 调用；逐节生成 base 条款，masters 账 completed/failed
# 留痕（非零结果=failed 不装样子）。
# ---------------------------------------------------------------------------

MASTER_REGEN_SOURCE_PATH = "cg37-regen"


def _masters_root(root: Path) -> Path:
    return root / "masters"


def build_master_prompt(contract_type: str, section: str) -> tuple[str, str]:
    """母版再生提示词（自写文案）：逐节起草 base 条款 body；槽只能用
    槽本体 canonical 名（闭集枚举随提示词给出）；严格 JSON 单键输出。"""
    slot_names = "、".join(sorted(SLOT_ONTOLOGY))
    system = ("你是合同母版条款起草助手，只输出严格 JSON 对象，不输出任何"
              "解释或围栏外的文字。")
    user = (f"请为 {contract_type} 合同母版起草「{section}」一节的条款"
            f"正文。要求：一段完整中文条款文本（不写节标题、不用 "
            "Markdown）；需要留待填空处只允许使用以下槽位记号（双花括号"
            f"包裹 canonical 槽名）：{slot_names}；不使用列表外的任何槽"
            "位；条文具体可执行。仅输出严格 JSON："
            '{"body": "条款正文"}。')
    return system, user


def master_regenerate(state_root, config: dict, args: dict) -> dict:
    """母版再生（B57 边界件）：按 SECTION_ORDER 逐节经 LLM seam 生成
    base 条款并整批替换该类型的自动 base——manual curated 保留（B3）、
    tagged/custom 零触碰；任一节失败＝masters 账 failed + typed 拒，
    条款库零改动（不装样子）；全部成功后装配 coherence 自检不过同样
    failed+typed 拒。force=False 且已存在自动 base＝typed 拒（对标
    竞品 --force 语义：覆写须显式）。"""
    if not isinstance(args, dict):
        raise _fail("cg37_params_invalid")
    contract_type = _require_type_name(args.get("contract_type"))
    force = args.get("force", False)
    if not isinstance(force, bool):
        raise _fail("cg37_force_invalid")
    llm = _resolve_llm(config)
    with _LOCK:
        root = _root(state_root)
        data = _load_clauses(root)
        auto_base = [c for c in data["clauses"]
                     if c["contract_type"] == contract_type
                     and c["tags"].get("source") == "base"
                     and not c.get("manual")]
        if auto_base and not force:
            raise _fail(f"cg37_master_exists_needs_force:{contract_type}")
        seq = _next_seq(_masters_root(root))
        row = {"schema": SCHEMA, "master_run_id": seq,
               "contract_type": contract_type, "status": "running",
               "sections": [], "error_message": ""}
        _write_seq_json(_masters_root(root), seq, row)
    try:
        for section in SECTION_ORDER:
            system, user = build_master_prompt(contract_type, section)
            body = _parse_json_object(llm["complete"](system, user)) \
                .get("body")
            if not isinstance(body, str) or not body.strip():
                raise _fail(f"cg37_master_body_invalid:{section}")
            body = normalize_body(body)
            unknown = sorted(s for s in slots_in(body)
                             if s not in SLOT_ONTOLOGY)
            if unknown:
                raise _fail(
                    f"cg37_master_slot_unknown:{section}:"
                    + ",".join(unknown))
            row["sections"].append({"section": section, "body": body,
                                    "body_hash": _md5(body)})
        replaced = False
        with _LOCK:
            data = _load_clauses(root)
            backup = {"seq": data["seq"],
                      "clauses": [dict(c) for c in data["clauses"]]}
            data["clauses"] = [c for c in data["clauses"]
                               if not (c["contract_type"] == contract_type
                                       and c["tags"].get("source") == "base"
                                       and not c.get("manual"))]
            for item in row["sections"]:
                data["seq"] += 1
                data["clauses"].append({
                    "id": data["seq"], "contract_type": contract_type,
                    "section": item["section"], "body": item["body"],
                    "slot_instructions": [], "law_refs": [],
                    "source_path": f"{MASTER_REGEN_SOURCE_PATH}/"
                                   f"{contract_type}",
                    "source_doc_title": "LLM 母版再生（评分门边界件）",
                    "body_hash": item["body_hash"], "created_at": "",
                    "updated_at": "", "manual": False,
                    "tags": {"source": "base"}, "tag_review": {}})
            _save_clauses(root, data)
            replaced = True
        try:
            assemble_contract(state_root, contract_type)  # coherence 自检
        except Exception:
            with _LOCK:  # 自检不过＝回滚条款账（失败路径零改动）
                _save_clauses(root, backup)
                replaced = False
            raise
        row["status"] = "completed"
        row["replaced_auto_base"] = [c["id"] for c in auto_base]
        with _LOCK:
            _write_seq_json(_masters_root(root), seq, row)
    except Exception as exc:
        row["status"] = "failed"
        row["error_message"] = f"{type(exc).__name__}: {exc}"[:300]
        with _LOCK:
            _write_seq_json(_masters_root(root), seq, row)
        raise
    return row


# ---------------------------------------------------------------------------
# E 组：自愈管线 generate→fill→evaluate→check→[improve→generate]*→store
# ---------------------------------------------------------------------------

def build_improve_prompt(contract_type: str, scenario, stance,
                         failing: list[dict], customs: list[dict]) \
        -> tuple[str, str]:
    """自愈诊断提示词（B37 契约，自写文案）：失败项清单（verdict+title+
    reasoning 截 200 字）+候选 custom 清单（id/section/body 截 120 字）+
    两问（本轮排除哪些让母版接管/哪些建议全局 reject 供人复核）+严格
    JSON 双键输出契约。"""
    fails = "\n".join(
        f"- [{c.get('verdict')}] {c.get('title', '')}："
        f"{(c.get('reasoning') or '')[:200]}"
        for c in failing) or "（无）"
    clist = "\n".join(
        f"- id={c['id']} section={c.get('section')} "
        f"body={(c.get('body') or '')[:120]}"
        for c in customs) or "（无 custom 条款命中）"
    system = ("你是合同自愈诊断助手，只输出严格 JSON 对象，不输出任何"
              "解释或围栏外的文字。")
    user = (f"一份{scenario or ''}{contract_type}合同（立场 stance={stance}）"
            f"评分未全通过。未通过的评审项：\n{fails}\n\n"
            f"当前立场命中、装配可用的 custom 条款（可能盖掉更完整的母版"
            f"条款）：\n{clist}\n\n请回答两问：\n"
            "1. exclude_custom_clause_ids：本轮装配应排除哪些 custom 条款"
            "（让母版接管对应节）？给 id 列表。\n"
            "2. recommendations：哪些 custom 条款建议全局 reject（仅供"
            "人工复核，不会自动执行）？给对象列表，每项含 clause_id、"
            "action=\"reject\"、reason。\n\n"
            '仅输出严格 JSON：{"exclude_custom_clause_ids": [id,...], '
            '"recommendations": [{"clause_id": id, "action": "reject", '
            '"reason": "..."}]}；无动作则两项均为空列表。')
    return system, user


def diagnose_failures(contract_type: str, scenario, stance,
                      failing_criteria: list[dict], customs: list[dict],
                      llm: dict) -> dict:
    """improve 诊断（B36-B38，永不抛）：输入失败项+候选 custom→两类动作；
    坏 LLM/解析失败→空动作（循环照跑）；排除 id 仅取正整数字串。"""
    if not failing_criteria or not customs:
        return {"exclude_custom_clause_ids": [],
                "recommendations": []}
    try:
        system, user = build_improve_prompt(
            contract_type, scenario, stance, failing_criteria, customs)
        data = _parse_json_object(llm["complete"](system, user))
    except Exception:
        return {"exclude_custom_clause_ids": [], "recommendations": []}
    excluded = data.get("exclude_custom_clause_ids")
    if not isinstance(excluded, list):
        excluded = []
    cleaned_excl: list[int] = []
    for item in excluded:
        if isinstance(item, bool):
            continue
        if isinstance(item, int):
            cleaned_excl.append(item)
        elif isinstance(item, str) and item.strip().isdigit():
            cleaned_excl.append(int(item))
    recs = data.get("recommendations")
    if not isinstance(recs, list):
        recs = []
    cleaned_recs = [dict(r) for r in recs
                    if isinstance(r, dict) and r.get("clause_id") is not None
                    and r.get("action") == "reject"]
    return {"exclude_custom_clause_ids": cleaned_excl,
            "recommendations": cleaned_recs}


def _pipeline_root(root: Path) -> Path:
    return root / "pipeline"


def _save_pipeline_run(root: Path, run: dict) -> None:
    _write_seq_json(_pipeline_root(root), run["pipeline_run_id"], run)


def _load_pipeline_runs(root: Path) -> list[dict]:
    return _load_seq_jsons(_pipeline_root(root))


def get_pipeline_run(state_root, pipeline_run_id: int) -> dict:
    if not isinstance(pipeline_run_id, int) or isinstance(pipeline_run_id, bool):
        raise _fail("cg37_run_id_invalid")
    with _LOCK:
        for row in _load_pipeline_runs(_root(state_root)):
            if row.get("pipeline_run_id") == pipeline_run_id:
                return row
    raise _fail(f"cg37_pipeline_run_not_found:{pipeline_run_id}")


def _rank(eval_result: dict) -> tuple[int, float]:
    """check 留最佳排序键：(n_passed, score)——二值分下 n_passed 是轮次
    优劣主信号（B35）。"""
    return (int(eval_result.get("n_passed") or 0),
            float(eval_result.get("score") or 0.0))


def _delivery(best: dict) -> dict:
    """交付裁决（RE-37 §4.3 第 2 轮复核钉定）：all_pass 与耗尽**同末态
    出稿**不阻塞交付；gate_status=passed|exhausted 强制随行；exhausted
    具名「未过关」+差几条账+逐条判定；只有 passed 可表述为已过关。
    review_handoff＝单向送审锚（只带文本摘要+「非审查结论」注记，零
    判定字段——RE-12 §4.4-3 起草≠审查纪律）。"""
    ev = best["eval_result"]
    all_pass = bool(ev.get("all_pass"))
    gate_status = "passed" if all_pass else "exhausted"
    missed = [c["title"] for c in ev.get("criteria_results", [])
              if c.get("verdict") != "pass"]
    if all_pass:
        note = "评分门过关出稿（可表述为已过关）"
    else:
        note = (f"未过关（评分门耗尽出稿，差 "
                f"{ev['n_criteria'] - ev['n_passed']} 条："
                + "、".join(missed) + "）——不得表述为已过关")
    return {
        "gate_status": gate_status,
        "note": note,
        "n_passed": ev.get("n_passed"), "n_criteria": ev.get("n_criteria"),
        "score": ev.get("score"), "all_pass": all_pass,
        "missed_criteria": missed,
        "criteria_results": ev.get("criteria_results", []),
        "filled_text": best.get("filled_text"),
        "best_iteration": best.get("iteration"),
        "eval_run_id": best.get("eval_run_id"),
        "review_handoff": {
            "text_sha256": _sha256(best.get("filled_text") or ""),
            "note": "起草门产出，非审查结论（复核走合同审查技能，另发起）",
        },
    }


def run_pipeline(state_root, config: dict, args: dict) -> dict:
    """自愈管线（B34-B39，自研循环面，零 LangGraph）：
    generate→fill→evaluate→check→[improve→generate]*→store；路由
    all_pass 或 iteration≥max_iterations（默认 3，=1 禁循环）同走 store
    ——两末态同径出稿（gate_status 随行落账）。循环对条款库只读（共享
    条款永不被循环改写）；排除仅作用本轮（经 custom_clause_ids 参数）。
    run 行状态机 pending→running→completed|failed（B40 作业语义，同步
    执行态记录；失败 error_message 落行后 typed 异常原样上抛）。"""
    if not isinstance(args, dict):
        raise _fail("cg37_params_invalid")
    contract_type = _require_type_name(args.get("contract_type"))
    scenario = args.get("scenario")
    if scenario is not None and not isinstance(scenario, str):
        raise _fail("cg37_scenario_invalid")
    stance = args.get("stance")
    if stance is not None and stance not in STANCE_VALUES:
        raise _fail("cg37_stance_invalid")
    task_desc = args.get("task_desc")
    if task_desc is not None and not isinstance(task_desc, str):
        raise _fail("cg37_task_desc_invalid")
    max_iterations = args.get("max_iterations", MAX_ITERATIONS_DEFAULT)
    if not isinstance(max_iterations, int) or isinstance(max_iterations, bool) \
            or max_iterations < 1:
        raise _fail("cg37_max_iterations_invalid")
    temperature = args.get("temperature", 0.0)
    if not isinstance(temperature, (int, float)) or isinstance(temperature, bool):
        raise _fail("cg37_temperature_invalid")
    explicit_ids = args.get("custom_clause_ids")
    if explicit_ids is not None \
            and (not isinstance(explicit_ids, list)
                 or not all(isinstance(i, int) and not isinstance(i, bool)
                            for i in explicit_ids)):
        raise _fail("cg37_custom_clause_ids_invalid")
    auto_learn = bool(args.get("auto_learn", False))
    llm = _resolve_llm(config)
    root = _root(state_root)
    with _LOCK:
        rubric_name = args.get("rubric") or default_rubric(
            state_root, contract_type)
        load_criteria(root, rubric_name)  # 空 criteria fail-fast
        pipeline_run_id = _next_seq(_pipeline_root(root))
        run = {
            "schema": SCHEMA, "pipeline_run_id": pipeline_run_id,
            "status": "pending",
            "request": {"contract_type": contract_type,
                        "scenario": scenario, "stance": stance,
                        "task_desc": task_desc, "rubric": rubric_name,
                        "max_iterations": max_iterations,
                        "temperature": temperature},
            "iterations": [], "actions_taken": [], "recommendations": [],
            "excluded_ids": [], "best": None, "delivery": None,
            "learn_applied": None,
        }
        _save_pipeline_run(root, run)
        run["status"] = "running"  # 作业状态机 pending→running→completed|failed
        _save_pipeline_run(root, run)
    try:
        best: dict | None = None
        excluded_ids: list[int] = []
        recommendations: list[dict] = []
        actions_taken: list[dict] = []
        iteration = 0
        while True:
            iteration += 1
            # 本轮装配的 custom 命中集（排除仅作用本轮＝RE-37 §2.6 分权：
            # 显式集−排除集；未给显式集时＝立场命中 assembly-ready 全集−
            # 排除集，语义同竞品 improve_node 的 full_ids−excluded）。
            with _LOCK:
                data = _load_clauses(root)
            if explicit_ids is not None:
                effective_ids = [cid for cid in explicit_ids
                                 if cid not in excluded_ids]
            elif stance:
                full_ids = [c["id"] for c in data["clauses"]
                            if c["contract_type"] == contract_type
                            and c["tags"].get("source") == "custom"
                            and c["tags"].get("stance") == stance
                            and is_assembly_ready(c)]
                effective_ids = [i for i in full_ids
                                 if i not in excluded_ids]
            else:
                effective_ids = None  # 无立场＝装配本就不取 custom
            assembled = assemble_contract(
                state_root, contract_type, scenario=scenario, stance=stance,
                custom_clause_ids=effective_ids)
            fill = fill_slots(
                state_root, config, contract_type, scenario,
                assembled["slots"], assembled["instructions"],
                task_desc=task_desc, temperature=temperature, llm=llm)
            filled_text, unfilled = render_filled(
                assembled["body_text"], fill["fill_values"])
            ev = evaluate_contract(
                state_root, config, filled_text, rubric_name,
                task_desc=task_desc, llm=llm,
                max_workers=args.get("max_workers"),
                n_judges=args.get("n_judges", 1))
            with _LOCK:
                run["iterations"].append({
                    "iteration": iteration, "eval_run_id": ev["run_id"],
                    "n_passed": ev["n_passed"], "n_criteria": ev["n_criteria"],
                    "all_pass": ev["all_pass"], "unfilled_slots": unfilled,
                    "fill_cache_id": fill["fill_cache_id"],
                    "fill_hit": fill["hit"]})
            if best is None or _rank(ev) > _rank(best["eval_result"]):
                best = {"iteration": iteration,
                        "filled_text": filled_text,
                        "fill_values": fill["fill_values"],
                        "eval_result": ev, "eval_run_id": ev["run_id"],
                        "fill_cache_id": fill["fill_cache_id"]}
            if ev["all_pass"] or iteration >= max_iterations:
                break
            # 诊断候选＝当前立场命中、装配可用的 custom 全集（同竞品
            # _current_customs 口径：排除只作用于下一轮装配命中集）。
            customs_now = [c for c in data["clauses"]
                           if c["contract_type"] == contract_type
                           and c["tags"].get("source") == "custom"
                           and (stance is None
                                or c["tags"].get("stance") == stance)
                           and is_assembly_ready(c)]
            failing = [c for c in ev["criteria_results"]
                       if c.get("verdict") != "pass"]
            diag = diagnose_failures(
                contract_type, scenario, stance, failing, customs_now, llm)
            excluded_ids = list(dict.fromkeys(
                excluded_ids + diag["exclude_custom_clause_ids"]))
            recommendations = recommendations + diag["recommendations"]
            actions_taken.append({
                "iteration": iteration,
                "failing": [f["title"] for f in failing],
                "excluded": diag["exclude_custom_clause_ids"],
                "recommendations": diag["recommendations"]})
        with _LOCK:
            run["best"] = {"iteration": best["iteration"],
                           "filled_text": best["filled_text"],
                           "fill_values": best["fill_values"],
                           "eval_run_id": best["eval_run_id"],
                           "fill_cache_id": best["fill_cache_id"],
                           "score": best["eval_result"]["score"],
                           "n_passed": best["eval_result"]["n_passed"],
                           "n_criteria": best["eval_result"]["n_criteria"],
                           "all_pass": best["eval_result"]["all_pass"]}
            run["actions_taken"] = actions_taken
            run["recommendations"] = recommendations
            run["excluded_ids"] = excluded_ids
            run["delivery"] = _delivery(best)
            run["status"] = "completed"
            _save_pipeline_run(root, run)
    except Exception as exc:
        with _LOCK:
            run["status"] = "failed"
            run["error_message"] = f"{type(exc).__name__}: {exc}"[:300]
            _save_pipeline_run(root, run)
        raise
    if auto_learn:
        learn_result = learn_from_run(state_root, config, pipeline_run_id)
        with _LOCK:
            run["learn_applied"] = learn_result["learn_applied"]
            _save_pipeline_run(root, run)
    return _pipeline_view(run)


def _pipeline_view(run: dict) -> dict:
    return {key: run.get(key) for key in (
        "schema", "pipeline_run_id", "status", "request", "iterations",
        "actions_taken", "recommendations", "excluded_ids", "best",
        "delivery", "learn_applied", "error_message")}


def pipeline_list(state_root, args: dict) -> dict:
    if not isinstance(args, dict):
        raise _fail("cg37_params_invalid")
    with _LOCK:
        rows = _load_pipeline_runs(_root(state_root))
    contract_type = args.get("contract_type")
    if contract_type is not None:
        rows = [r for r in rows if r.get("request", {}).get("contract_type")
                == contract_type]
    limit = args.get("limit", LEARN_HISTORY_LIMIT)
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        raise _fail("cg37_limit_invalid")
    views = [{**_pipeline_view(r),
              "best": r.get("best"),
              "delivery": {k: v for k, v in (r.get("delivery") or {}).items()
                           if k != "filled_text"}}
             for r in rows[-limit:]]
    return {"schema": SCHEMA, "runs": views, "count": len(views)}


# ---------------------------------------------------------------------------
# F 组：条款库治理慢回路（learn 自动 reject + tag 迭代 + 离线分析/执行）
# ---------------------------------------------------------------------------

def _reject_recommendations(run: dict) -> list[dict]:
    return [r for r in (run.get("recommendations") or [])
            if isinstance(r, dict) and r.get("action") == "reject"]


def learn_from_run(state_root, config: dict, pipeline_run_id: int) -> dict:
    """learn 节点（B41-B43）：聚合本 run＋同类型历史 50 次 pipeline_runs
    的 reject 建议，某 custom 条款累计≥阈值（默认 3，config 可调）→
    bulk_review 标 rejected（未来装配不再命中）。只动 custom，base/tagged
    永不动；幂等（重复 reject 同结果）；单条款失败 fail-safe 跳过不崩。"""
    threshold = config.get(CONFIG_AUTO_REJECT_THRESHOLD,
                           AUTO_REJECT_THRESHOLD_DEFAULT)
    if not isinstance(threshold, int) or isinstance(threshold, bool) \
            or threshold < 1:
        threshold = AUTO_REJECT_THRESHOLD_DEFAULT
    with _LOCK:
        root = _root(state_root)
        current = get_pipeline_run(state_root, pipeline_run_id)
        contract_type = current["request"]["contract_type"]
        history = [r for r in _load_pipeline_runs(root)
                   if r.get("pipeline_run_id") != pipeline_run_id
                   and r.get("request", {}).get("contract_type")
                   == contract_type][-LEARN_HISTORY_LIMIT:]
        counts: dict[int, int] = {}
        for run in [current] + history:
            for rec in _reject_recommendations(run):
                cid = rec.get("clause_id")
                if isinstance(cid, int) and not isinstance(cid, bool):
                    counts[cid] = counts.get(cid, 0) + 1
        applied: list[dict] = []
        clauses = {c["id"]: c for c in _load_clauses(root)["clauses"]}
        for cid in sorted(counts):
            total = counts[cid]
            if total < threshold:
                continue
            clause = clauses.get(cid)
            if clause is None or clause["tags"].get("source") != "custom":
                continue  # 只 reject custom；base/tagged 永不动
            try:
                bulk_review(state_root, cid, "rejected")
                applied.append({"clause_id": cid, "total_count": total,
                                "threshold": threshold})
            except ContractGateError:
                continue  # fail-safe：单条款失败不沉船
        with _LOCK:
            run_row = None
            for row in _load_pipeline_runs(root):
                if row.get("pipeline_run_id") == pipeline_run_id:
                    run_row = row
                    break
            if run_row is not None:
                run_row["learn_applied"] = applied
                _save_pipeline_run(root, run_row)
        return {"schema": SCHEMA, "pipeline_run_id": pipeline_run_id,
                "threshold": threshold,
                "learn_applied": applied}


# ── tag 迭代两段：suggest（只读建议）→ apply（串行+重评+降分回滚）──

def _retag_root(root: Path) -> Path:
    return root / "governance" / "retag"


def build_retag_prompt(contract_type: str, clauses: list[dict]) \
        -> tuple[str, str]:
    """retag 建议提示词（B44 契约，自写文案）：分析失败条款当前标签
    （scenario 匹配/stance 一致等）是否合理→建议清单供人审批。"""
    clist = "\n".join(
        f"- id={c['id']} section={c.get('section')} "
        f"tags={json.dumps(c.get('tags') or {}, ensure_ascii=False)}"
        for c in clauses) or "（无）"
    system = ("你是条款库标签治理助手，只输出严格 JSON 数组，不输出任何"
              "解释或围栏外的文字。")
    user = (f"以下 {contract_type} 合同评分门自愈中涉事（被本轮排除或被"
            f"建议 reject）的 custom 条款：\n{clist}\n\n"
            "请逐条分析其当前标签是否合理（scenario 是否贴合条款内容、"
            "stance 是否与条款倾向一致），不合理的给出建议标签。仅输出"
            '严格 JSON 数组：[{"clause_id": id, "section": "节名", '
            '"current_tags": {...}, "suggested_tags": {...}, "reason": '
            '"一句话理由"}]；无可建议则输出空数组。')
    return system, user


def retag_suggest(state_root, config: dict, args: dict) -> dict:
    """suggest_retag（B44）：只读建议——LLM 分析失败条款 tags 合理性，
    产出建议清单落 governance 账（status=pending 供人工审批）；可并发
    （零写条款库）。"""
    if not isinstance(args, dict):
        raise _fail("cg37_params_invalid")
    run_id = args.get("pipeline_run_id")
    if not isinstance(run_id, int) or isinstance(run_id, bool):
        raise _fail("cg37_run_id_invalid")
    llm = _resolve_llm(config)
    with _LOCK:
        root = _root(state_root)
        run = get_pipeline_run(state_root, run_id)
        clause_ids = set(run.get("excluded_ids") or [])
        for rec in _reject_recommendations(run):
            cid = rec.get("clause_id")
            if isinstance(cid, int):
                clause_ids.add(cid)
        data = _load_clauses(root)
        failed_clauses = [c for c in data["clauses"]
                          if c["id"] in clause_ids
                          and c["tags"].get("source") == "custom"]
        contract_type = run["request"]["contract_type"]
    system, user = build_retag_prompt(contract_type, failed_clauses)
    suggestions: list[dict] = []
    try:
        raw = llm["complete"](system, user)
        text = (raw or "").strip()
        fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
        if fence:
            text = fence.group(1).strip()
        if not text.startswith("["):
            start, end = text.find("["), text.rfind("]")
            if start != -1 and end != -1 and end > start:
                text = text[start:end + 1]
        parsed = json.loads(text)
        if isinstance(parsed, list):
            suggestions = [s for s in parsed if isinstance(s, dict)
                           and s.get("clause_id") is not None]
    except (json.JSONDecodeError, ValueError, TypeError):
        suggestions = []
    with _LOCK:
        seq = _next_seq(_retag_root(root))
        record = {"schema": SCHEMA, "retag_id": seq,
                  "pipeline_run_id": run_id,
                  "request": run["request"], "status": "pending",
                  "suggestions": suggestions,
                  "originals": None, "reval": None}
        _write_seq_json(_retag_root(root), seq, record)
    return record


_RETAG_APPLY_LOCK = threading.Lock()


def retag_apply(state_root, config: dict, args: dict) -> dict:
    """retag apply（B45）：人工审批后应用——**串行闸**（进程内专用锁，
    同态竞品 advisory lock：suggest 可并发/apply 必须串行）→存原始
    tags→应用（经词表治理闸）→重评（原请求重跑管线，max_iterations=1
    控本）→分数下降自动回滚→释放闸。"""
    if not isinstance(args, dict):
        raise _fail("cg37_params_invalid")
    retag_id = args.get("retag_id")
    if not isinstance(retag_id, int) or isinstance(retag_id, bool):
        raise _fail("cg37_retag_id_invalid")
    llm = _resolve_llm(config)
    with _RETAG_APPLY_LOCK:
        with _LOCK:
            root = _root(state_root)
            record = None
            for row in _load_seq_jsons(_retag_root(root)):
                if row.get("retag_id") == retag_id:
                    record = row
                    break
            if record is None:
                raise _fail(f"cg37_retag_not_found:{retag_id}")
            if record["status"] != "pending":
                raise _fail(f"cg37_retag_not_pending:{retag_id}")
            data = _load_clauses(root)
            by_id = {c["id"]: c for c in data["clauses"]}
            originals: dict[int, dict] = {}
            applied_tags: list[dict] = []
            for suggestion in record["suggestions"]:
                cid = suggestion.get("clause_id")
                suggested = suggestion.get("suggested_tags")
                if cid not in by_id or not isinstance(suggested, dict):
                    continue
                clause = by_id[cid]
                originals[cid] = {"tags": dict(clause["tags"]),
                                  "tag_review": dict(clause.get("tag_review")
                                                     or {})}
                new_tags = {k: v for k, v in suggested.items()
                            if isinstance(v, str)}
                new_tags["source"] = clause["tags"]["source"]
                clause["tags"] = new_tags
                clause["tag_review"] = {
                    dim: "pending" for dim in _review_dims(new_tags)}
                applied_tags.append({"clause_id": cid,
                                     "suggested_tags": new_tags})
            record["originals"] = originals
            record["applied_tags"] = applied_tags
            record["status"] = "applied"
            if applied_tags:
                contract_type = record["request"]["contract_type"]
                _govern_tags(root, contract_type, {
                    k: v for c in applied_tags for k, v in
                    c["suggested_tags"].items()})
                _save_clauses(root, data)
            _write_seq_json(_retag_root(root), retag_id, record)
        try:
            reval = run_pipeline(state_root, config, {
                **record["request"], "max_iterations": 1})
            baseline = get_pipeline_run(
                state_root, record["pipeline_run_id"])
            base_passed = baseline["best"]["n_passed"]
            new_passed = reval["best"]["n_passed"]
            rolled_back = new_passed < base_passed
        except ContractGateError:
            rolled_back = True
            reval = None
        if rolled_back:
            with _LOCK:
                data = _load_clauses(root)
                by_id = {c["id"]: c for c in data["clauses"]}
                for cid_str, original in originals.items():
                    cid = int(cid_str) if isinstance(cid_str, str) else cid_str
                    if cid in by_id:
                        by_id[cid]["tags"] = original["tags"]
                        by_id[cid]["tag_review"] = original["tag_review"]
                _save_clauses(root, data)
                record["status"] = "rolled_back"
                record["reval"] = ({"pipeline_run_id": reval["pipeline_run_id"],
                                    "n_passed": reval["best"]["n_passed"]}
                                   if reval else None)
                _write_seq_json(_retag_root(root), retag_id, record)
        else:
            with _LOCK:
                record["reval"] = ({
                    "pipeline_run_id": reval["pipeline_run_id"],
                    "n_passed": reval["best"]["n_passed"]} if reval else None)
                _write_seq_json(_retag_root(root), retag_id, record)
    return record


def iteration_analyze(state_root, args: dict) -> dict:
    """离线分析器（B46）：从 pipeline_runs 统计高频 exclude／建议 reject
    ／score-排除相关性→推荐清单（threshold_exclude=3/threshold_reject=2；
    confidence 分档：high=reject 达阈且排除组均分更低、medium=reject 达阈
    、low=仅 exclude 达阈——确定性分档，自定口径）。"""
    if not isinstance(args, dict):
        raise _fail("cg37_params_invalid")
    contract_type = _require_type_name(args.get("contract_type"))
    with _LOCK:
        root = _root(state_root)
        runs = [r for r in _load_pipeline_runs(root)
                if r.get("request", {}).get("contract_type")
                == contract_type]
    exclude_counts: dict[int, int] = {}
    reject_counts: dict[int, int] = {}
    with_excl_scores: dict[int, list[int]] = {}
    without_excl_scores: dict[int, list[int]] = {}
    clause_ids: set[int] = set()
    for run in runs:
        excluded = set(run.get("excluded_ids") or [])
        best = run.get("best") or {}
        n_passed = int(best.get("n_passed") or 0)
        for action in run.get("actions_taken") or []:
            for cid in action.get("excluded") or []:
                exclude_counts[cid] = exclude_counts.get(cid, 0) + 1
                clause_ids.add(cid)
        for rec in _reject_recommendations(run):
            cid = rec.get("clause_id")
            if isinstance(cid, int) and not isinstance(cid, bool):
                reject_counts[cid] = reject_counts.get(cid, 0) + 1
                clause_ids.add(cid)
        for cid in clause_ids:
            bucket = with_excl_scores if cid in excluded \
                else without_excl_scores
            bucket.setdefault(cid, []).append(n_passed)
    recommendations = []
    for cid in sorted(clause_ids):
        excl_n = exclude_counts.get(cid, 0)
        rej_n = reject_counts.get(cid, 0)
        with_scores = with_excl_scores.get(cid, [])
        without_scores = without_excl_scores.get(cid, [])
        mean_with = (sum(with_scores) / len(with_scores)
                     if with_scores else None)
        mean_without = (sum(without_scores) / len(without_scores)
                        if without_scores else None)
        correlation = None
        if mean_with is not None and mean_without is not None:
            correlation = ("negative" if mean_with > mean_without
                           else "positive" if mean_with < mean_without
                           else "flat")
        confidence = None
        action = None
        if rej_n >= ANALYZE_THRESHOLD_REJECT:
            action = "reject"
            confidence = "high" if correlation == "negative" else "medium"
        elif excl_n >= ANALYZE_THRESHOLD_EXCLUDE:
            action = "reject"
            confidence = "low"
        if action:
            recommendations.append({
                "clause_id": cid, "action": action,
                "exclude_count": excl_n, "reject_count": rej_n,
                "score_correlation_excluded_vs_rest": correlation,
                "confidence": confidence})
    return {"schema": SCHEMA, "contract_type": contract_type,
            "thresholds": {"exclude": ANALYZE_THRESHOLD_EXCLUDE,
                           "reject": ANALYZE_THRESHOLD_REJECT},
            "run_count": len(runs), "recommendations": recommendations}


def _ops_log_path(root: Path) -> Path:
    return root / "governance" / "iteration_ops.jsonl"


def iteration_apply(state_root, args: dict) -> dict:
    """离线执行器（B46）：按 confidence 档批量应用 reject（默认仅 high；
    medium=high+medium、low=全档）；dry_run=true 预览不落账（默认）；
    操作 JSONL 日志逐动作留痕。只动 custom（分权同 learn）。"""
    if not isinstance(args, dict):
        raise _fail("cg37_params_invalid")
    contract_type = _require_type_name(args.get("contract_type"))
    confidence = args.get("confidence", "high")
    if confidence not in ("high", "medium", "low"):
        raise _fail("cg37_confidence_invalid")
    dry_run = args.get("dry_run", True)
    if not isinstance(dry_run, bool):
        raise _fail("cg37_dry_run_invalid")
    tiers = {"high": ("high",), "medium": ("high", "medium"),
             "low": ("high", "medium", "low")}
    analysis = iteration_analyze(state_root, {"contract_type": contract_type})
    with _LOCK:
        root = _root(state_root)
        clauses = {c["id"]: c for c in _load_clauses(root)["clauses"]}
        actions: list[dict] = []
        for rec in analysis["recommendations"]:
            if rec["confidence"] not in tiers[confidence]:
                continue
            cid = rec["clause_id"]
            clause = clauses.get(cid)
            if clause is None or clause["tags"].get("source") != "custom":
                actions.append({"clause_id": cid, "action": "skip_not_custom",
                                "dry_run": dry_run})
                continue
            actions.append({"clause_id": cid, "action": "reject",
                            "confidence": rec["confidence"],
                            "basis": {"exclude_count": rec["exclude_count"],
                                      "reject_count": rec["reject_count"]},
                            "dry_run": dry_run})
        if not dry_run:
            for action in actions:
                if action["action"] == "reject":
                    bulk_review(state_root, action["clause_id"], "rejected")
            log = _ops_log_path(root)
            log.parent.mkdir(parents=True, exist_ok=True)
            with open(log, "a", encoding="utf-8") as handle:
                for action in actions:
                    handle.write(json.dumps(
                        {"schema": SCHEMA, "contract_type": contract_type,
                         **action}, ensure_ascii=False) + "\n")
    return {"schema": SCHEMA, "contract_type": contract_type,
            "confidence_tier": confidence, "dry_run": dry_run,
            "actions": actions}


# ---------------------------------------------------------------------------
# G 组：A-B compare（固定区域只变 prompt + drafter-only 隔离 + 确定性顺序）
# ---------------------------------------------------------------------------

_PROMPT_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def _prompts_root(root: Path) -> Path:
    return root / "prompts"


def drafter_create(state_root, args: dict) -> dict:
    """prompt 库登记（compare 被测对象；B47 前置）。"""
    if not isinstance(args, dict):
        raise _fail("cg37_params_invalid")
    name = args.get("name")
    content = args.get("content")
    contract_type = args.get("contract_type")
    prompt_type = args.get("prompt_type", "drafter")
    if not isinstance(name, str) or not _PROMPT_NAME_RE.match(name) \
            or not isinstance(content, str) or not content.strip() \
            or not isinstance(contract_type, str) \
            or not _TYPE_RE.match(contract_type) \
            or not isinstance(prompt_type, str) or not prompt_type.strip():
        raise _fail("cg37_prompt_invalid")
    with _LOCK:
        root = _root(state_root)
        directory = _prompts_root(root)
        if (directory / f"{name}.json").is_file():
            raise _fail(f"cg37_prompt_exists:{name}")
        record = {"schema": SCHEMA, "name": name, "content": content,
                  "contract_type": contract_type, "prompt_type": prompt_type}
        directory.mkdir(parents=True, exist_ok=True)
        _atomic_write(directory / f"{name}.json", _dump(record))
        return record


def _load_prompt(root: Path, name: str) -> dict:
    record = _read_json(_prompts_root(root) / f"{name}.json")
    if record is None:
        raise _fail(f"cg37_prompt_not_found:{name}")
    return record


def drafter_list(state_root, args: dict) -> dict:
    if not isinstance(args, dict):
        raise _fail("cg37_params_invalid")
    with _LOCK:
        root = _root(state_root)
        records = [_read_json(e) for e
                   in sorted(_prompts_root(root).glob("*.json"))]
    rows = [{k: r[k] for k in ("name", "contract_type", "prompt_type")}
            for r in records if r is not None]
    return {"schema": SCHEMA, "prompts": rows, "count": len(rows)}


def drafter_get(state_root, args: dict) -> dict:
    if not isinstance(args, dict):
        raise _fail("cg37_params_invalid")
    name = args.get("name")
    if not isinstance(name, str):
        raise _fail("cg37_prompt_invalid")
    with _LOCK:
        return _load_prompt(_root(state_root), name)


def drafter_delete(state_root, args: dict) -> dict:
    if not isinstance(args, dict):
        raise _fail("cg37_params_invalid")
    name = args.get("name")
    if not isinstance(name, str):
        raise _fail("cg37_prompt_invalid")
    with _LOCK:
        root = _root(state_root)
        _load_prompt(root, name)
        (_prompts_root(root) / f"{name}.json").unlink()
        return {"schema": SCHEMA, "deleted": name}


def _compare_root(root: Path) -> Path:
    return root / "compare"


def compare_run(state_root, config: dict, args: dict) -> dict:
    """A-B compare（B47-B52）：固定区域（contract_type+rubric+task）只变
    prompt；prompt 名≥2 才跑；n_drafts≥1、并发钳 [1,8] 默认 1。

    - fail-fast：rubric 未知/空 criteria 在**任何 LLM 调用前**具名拒。
    - drafter-only 隔离：每稿=单次直调 drafter（prompt content 作
      system、起草需求+装配模板参考块作 user），**不进生产自愈管线**
      （对比的是 prompt 本身的单次起草质量——结论≠生产管线表现，
      限定词随行）。
    - 顺序确定性：prompt-major/draft-minor 逐稿评审落账（任意并发下
      行序与并发 1 一致）。
    - draft_text 入库供复现；compare_get 默认不返回（体积大），run_draft
      懒取。"""
    if not isinstance(args, dict):
        raise _fail("cg37_params_invalid")
    contract_type = _require_type_name(args.get("contract_type"))
    prompt_names = args.get("prompts")
    if not isinstance(prompt_names, list) \
            or not all(isinstance(p, str) for p in prompt_names) \
            or len(prompt_names) < 2:
        raise _fail("cg37_compare_needs_two_prompts")
    n_drafts = args.get("n_drafts", 1)
    if not isinstance(n_drafts, int) or isinstance(n_drafts, bool) \
            or n_drafts < 1:
        raise _fail("cg37_compare_drafts_invalid")
    max_workers = args.get("max_workers", 1)
    if not isinstance(max_workers, int) or isinstance(max_workers, bool):
        raise _fail("cg37_max_workers_invalid")
    max_workers = max(1, min(max_workers, COMPARE_DRAFTS_CEILING))
    task_desc = args.get("task_desc")
    if task_desc is not None and not isinstance(task_desc, str):
        raise _fail("cg37_task_desc_invalid")
    llm = _resolve_llm(config)
    with _LOCK:
        root = _root(state_root)
        rubric_name = args.get("rubric") or default_rubric(
            state_root, contract_type)
        load_criteria(root, rubric_name)  # fail-fast（B49）
        prompts = [_load_prompt(root, name) for name in prompt_names]
        reference = assemble_contract(state_root, contract_type)
        compare_run_id = _next_seq(_compare_root(root))
        run = {"schema": SCHEMA, "compare_run_id": compare_run_id,
               "contract_type": contract_type, "rubric": rubric_name,
               "task_desc": task_desc,
               "prompts": list(prompt_names), "n_drafts": n_drafts,
               "mode": "drafter-only", "drafts": []}
        _write_seq_json(_compare_root(root), compare_run_id, run)
    user_template = (
        f"请按系统提示词的约定，直接起草一份 {contract_type} 合同全文。"
        f"起草需求：{task_desc or '（无特别需求）'}\n\n装配模板参考块"
        f"（结构与槽位参考，非逐字照抄）：\n{reference['body_text']}")
    jobs = [(prompt, index) for prompt in prompts
            for index in range(n_drafts)]
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        draft_texts = list(pool.map(
            lambda job: llm["complete"](job[0]["content"], user_template),
            jobs))
    for (prompt, _index), draft_text in zip(jobs, draft_texts):
        ev = evaluate_contract(
            state_root, config, draft_text, rubric_name,
            task_desc=task_desc, llm=llm, compare_run_id=compare_run_id,
            prompt_name=prompt["name"],
            variant_label=f"{prompt['name']}#{len(run['drafts']) + 1}")
        run["drafts"].append({
            "prompt_name": prompt["name"],
            "draft_index": len([d for d in run["drafts"]
                                if d["prompt_name"] == prompt["name"]]) + 1,
            "draft_text": draft_text, "eval_run_id": ev["run_id"],
            "n_passed": ev["n_passed"], "n_criteria": ev["n_criteria"],
            "all_pass": ev["all_pass"],
            "criteria_results": ev["criteria_results"]})
    with _LOCK:
        _write_seq_json(_compare_root(root), compare_run_id, run)
    return _compare_view(run)


def _compare_matrix(run: dict) -> dict:
    """矩阵（B52）：规则×prompt；n=1 单元格={verdict, reasoning} 二值；
    n>1={pass_rate k/N, n_pass, n, reasoning}（通过率降单次随机；reasoning
    取首个可用让视图直接显示「为什么」）。"""
    criteria_order: list[str] = []
    for draft in run["drafts"]:
        for result in draft.get("criteria_results") or []:
            if result["id"] not in criteria_order:
                criteria_order.append(result["id"])
    by_prompt: dict[str, list[dict]] = {}
    for draft in run["drafts"]:
        by_prompt.setdefault(draft["prompt_name"], []).append(draft)
    matrix: dict[str, dict] = {}
    for prompt_name, drafts in by_prompt.items():
        cells: dict[str, dict] = {}
        for criterion_id in criteria_order:
            results = [next((r for r in d.get("criteria_results") or []
                             if r["id"] == criterion_id), None)
                       for d in drafts]
            passed = [r for r in results if r and r["verdict"] == "pass"]
            reasoning = next((r["reasoning"] for r in results if r), "")
            if len(drafts) == 1:
                cells[criterion_id] = {
                    "verdict": results[0]["verdict"] if results[0]
                    else "fail",
                    "reasoning": reasoning}
            else:
                cells[criterion_id] = {
                    "pass_rate": len(passed) / len(drafts),
                    "n_pass": len(passed), "n": len(drafts),
                    "reasoning": reasoning}
        matrix[prompt_name] = cells
    return {"criteria_order": criteria_order, "cells": matrix}


def _compare_view(run: dict, *, with_drafts: bool = False) -> dict:
    view = {key: run.get(key) for key in (
        "schema", "compare_run_id", "contract_type", "rubric",
        "task_desc", "prompts", "n_drafts", "mode")}
    drafts = [{k: d[k] for k in ("prompt_name", "draft_index",
                                 "eval_run_id", "n_passed", "n_criteria",
                                 "all_pass",
                                 *(("draft_text",) if with_drafts else ()))}
              for d in run.get("drafts", [])]
    view["drafts"] = drafts
    view["matrix"] = _compare_matrix(run)
    return view


def compare_get(state_root, args: dict) -> dict:
    if not isinstance(args, dict):
        raise _fail("cg37_params_invalid")
    run_id = args.get("compare_run_id")
    if not isinstance(run_id, int) or isinstance(run_id, bool):
        raise _fail("cg37_run_id_invalid")
    with _LOCK:
        for row in _load_seq_jsons(_compare_root(_root(state_root))):
            if row.get("compare_run_id") == run_id:
                return _compare_view(row)
    raise _fail(f"cg37_compare_run_not_found:{run_id}")


def compare_list(state_root, args: dict) -> dict:
    if not isinstance(args, dict):
        raise _fail("cg37_params_invalid")
    with _LOCK:
        rows = _load_seq_jsons(_compare_root(_root(state_root)))
    listed = [{"compare_run_id": r.get("compare_run_id"),
               "contract_type": r.get("contract_type"),
               "rubric": r.get("rubric"),
               "prompts": r.get("prompts"), "n_drafts": r.get("n_drafts")}
              for r in rows]
    return {"schema": SCHEMA, "runs": listed, "count": len(listed)}


def compare_matrix(state_root, args: dict) -> dict:
    if not isinstance(args, dict):
        raise _fail("cg37_params_invalid")
    run_id = args.get("compare_run_id")
    if not isinstance(run_id, int) or isinstance(run_id, bool):
        raise _fail("cg37_run_id_invalid")
    with _LOCK:
        for row in _load_seq_jsons(_compare_root(_root(state_root))):
            if row.get("compare_run_id") == run_id:
                return {"schema": SCHEMA,
                        "compare_run_id": run_id,
                        **_compare_matrix(row)}
    raise _fail(f"cg37_compare_run_not_found:{run_id}")


def run_draft(state_root, args: dict) -> dict:
    """run_draft（B51）：draft_text 懒取（入库供复现、默认不随 compare_get
    返回）。"""
    if not isinstance(args, dict):
        raise _fail("cg37_params_invalid")
    run_id = args.get("compare_run_id")
    prompt_name = args.get("prompt_name")
    draft_index = args.get("draft_index", 1)
    if not isinstance(run_id, int) or isinstance(run_id, bool) \
            or not isinstance(prompt_name, str) \
            or not isinstance(draft_index, int) or isinstance(draft_index, bool):
        raise _fail("cg37_params_invalid")
    with _LOCK:
        for row in _load_seq_jsons(_compare_root(_root(state_root))):
            if row.get("compare_run_id") != run_id:
                continue
            for draft in row.get("drafts", []):
                if draft["prompt_name"] == prompt_name \
                        and draft["draft_index"] == draft_index:
                    return {"schema": SCHEMA,
                            "compare_run_id": run_id,
                            "prompt_name": prompt_name,
                            "draft_index": draft_index,
                            "draft_text": draft["draft_text"]}
            raise _fail(
                f"cg37_draft_not_found:{prompt_name}:{draft_index}")
    raise _fail(f"cg37_compare_run_not_found:{run_id}")


# ---------------------------------------------------------------------------
# legal_entry 唯一分发
# ---------------------------------------------------------------------------

CONTRACT_GATE_METHODS = frozenset({
    # 条款库与标签（A 组）
    "contract_gate.clause_upsert", "contract_gate.clause_list",
    "contract_gate.clause_get", "contract_gate.clause_delete_auto",
    "contract_gate.clause_review_tag", "contract_gate.clause_bulk_review",
    "contract_gate.review_queue", "contract_gate.tag_dim_register",
    "contract_gate.assemble",
    # rubric CRUD（D 组；与竞品 MCP 20 件面中的 rubric_list/get/create/
    # update/delete + criterion_add/update/delete/reorder 对齐）
    "contract_gate.rubric_list", "contract_gate.rubric_get",
    "contract_gate.rubric_create", "contract_gate.rubric_update",
    "contract_gate.rubric_delete", "contract_gate.criterion_add",
    "contract_gate.criterion_update", "contract_gate.criterion_delete",
    "contract_gate.criterion_reorder",
    # 评分门与评估账（contract_evaluate + run_list/run_get 对齐；
    # 边界件：dashboard 只读聚合 B56）
    "contract_gate.evaluate", "contract_gate.run_list",
    "contract_gate.run_get", "contract_gate.dashboard",
    # 自愈管线（pipeline_run/list/get 对齐；作业状态机随行）
    "contract_gate.pipeline", "contract_gate.pipeline_list",
    "contract_gate.pipeline_get",
    # A-B compare（compare_run/list/get/matrix + run_draft 对齐）
    "contract_gate.compare_run", "contract_gate.compare_list",
    "contract_gate.compare_get", "contract_gate.compare_matrix",
    "contract_gate.run_draft", "contract_gate.drafter_create",
    "contract_gate.drafter_list", "contract_gate.drafter_get",
    "contract_gate.drafter_delete",
    # 条款库治理慢回路（F 组）
    "contract_gate.learn", "contract_gate.iteration_analyze",
    "contract_gate.iteration_apply", "contract_gate.retag_suggest",
    "contract_gate.retag_apply",
    # 母版再生（B57 边界件，LLM seam 面）
    "contract_gate.master_regenerate",
})


def contract_gate_call(method: str, args, config: dict) -> dict:
    """legal_entry contract_gate.* 唯一分发（fail-closed 同基线）。

    配置级缺状态根＝NOT_CONNECTED（同全桥纪律）；LLM 依赖方法
    （evaluate/pipeline/compare_run/retag_*/master_regenerate）缺
    seam＝NOT_CONNECTED（cg37_llm_seam_not_configured——seam 只能进程
    内注入，CLI/JSON 通道不携带可调用面）；业务级 typed 拒＝
    ContractGateError（cg37_* 码）。"""
    from bridge_errors import NotConnected
    state_root = config.get(CONFIG_STATE_ROOT)
    if not state_root:
        raise NotConnected("cg37_state_root_not_configured")
    if method == "contract_gate.clause_upsert":
        return upsert_clause(state_root, args)
    if method == "contract_gate.clause_list":
        return list_clauses(state_root, args)
    if method == "contract_gate.clause_get":
        return get_clause(state_root, args.get("clause_id")
                          if isinstance(args, dict) else None)
    if method == "contract_gate.clause_delete_auto":
        return delete_auto_clauses(state_root, args)
    if method == "contract_gate.clause_review_tag":
        if not isinstance(args, dict):
            raise _fail("cg37_params_invalid")
        return review_tag(state_root, args.get("clause_id"),
                          args.get("dim"), args.get("status"))
    if method == "contract_gate.clause_bulk_review":
        if not isinstance(args, dict):
            raise _fail("cg37_params_invalid")
        return bulk_review(state_root, args.get("clause_id"),
                           args.get("status"))
    if method == "contract_gate.review_queue":
        return review_queue(state_root, args)
    if method == "contract_gate.tag_dim_register":
        if not isinstance(args, dict):
            raise _fail("cg37_params_invalid")
        return register_tag_dim(state_root, args.get("contract_type"),
                                args.get("dim"), args.get("values"))
    if method == "contract_gate.assemble":
        if not isinstance(args, dict):
            raise _fail("cg37_params_invalid")
        return assemble_contract(
            state_root, args.get("contract_type"),
            scenario=args.get("scenario"), stance=args.get("stance"),
            custom_clause_ids=args.get("custom_clause_ids"),
            output_format=args.get("format", "markdown"), config=config)
    if method == "contract_gate.rubric_list":
        return rubric_list(state_root, args)
    if method == "contract_gate.rubric_get":
        return rubric_get(state_root, args)
    if method == "contract_gate.rubric_create":
        return rubric_create(state_root, args)
    if method == "contract_gate.rubric_update":
        return rubric_update(state_root, args)
    if method == "contract_gate.rubric_delete":
        return rubric_delete(state_root, args)
    if method == "contract_gate.criterion_add":
        return criterion_add(state_root, args)
    if method == "contract_gate.criterion_update":
        return criterion_update(state_root, args)
    if method == "contract_gate.criterion_delete":
        return criterion_delete(state_root, args)
    if method == "contract_gate.criterion_reorder":
        return criterion_reorder(state_root, args)
    if method == "contract_gate.evaluate":
        if not isinstance(args, dict):
            raise _fail("cg37_params_invalid")
        rubric_name = args.get("rubric") or default_rubric(
            state_root, args.get("contract_type"))
        return evaluate_contract(
            state_root, config, args.get("contract_text"), rubric_name,
            task_desc=args.get("task_desc"),
            llm=_resolve_llm(config),
            max_workers=args.get("max_workers"),
            n_judges=args.get("n_judges", 1))
    if method == "contract_gate.run_list":
        return run_list(state_root, args)
    if method == "contract_gate.run_get":
        return run_get(state_root, args)
    if method == "contract_gate.dashboard":
        return dashboard(state_root, args)
    if method == "contract_gate.pipeline":
        return run_pipeline(state_root, config, args)
    if method == "contract_gate.pipeline_list":
        return pipeline_list(state_root, args)
    if method == "contract_gate.pipeline_get":
        return get_pipeline_run(
            state_root, args.get("pipeline_run_id")
            if isinstance(args, dict) else None)
    if method == "contract_gate.compare_run":
        return compare_run(state_root, config, args)
    if method == "contract_gate.compare_list":
        return compare_list(state_root, args)
    if method == "contract_gate.compare_get":
        return compare_get(state_root, args)
    if method == "contract_gate.compare_matrix":
        return compare_matrix(state_root, args)
    if method == "contract_gate.run_draft":
        return run_draft(state_root, args)
    if method == "contract_gate.drafter_create":
        return drafter_create(state_root, args)
    if method == "contract_gate.drafter_list":
        return drafter_list(state_root, args)
    if method == "contract_gate.drafter_get":
        return drafter_get(state_root, args)
    if method == "contract_gate.drafter_delete":
        return drafter_delete(state_root, args)
    if method == "contract_gate.learn":
        if not isinstance(args, dict):
            raise _fail("cg37_params_invalid")
        return learn_from_run(state_root, config,
                              args.get("pipeline_run_id"))
    if method == "contract_gate.iteration_analyze":
        return iteration_analyze(state_root, args)
    if method == "contract_gate.iteration_apply":
        return iteration_apply(state_root, args)
    if method == "contract_gate.retag_suggest":
        return retag_suggest(state_root, config, args)
    if method == "contract_gate.retag_apply":
        return retag_apply(state_root, config, args)
    if method == "contract_gate.master_regenerate":
        return master_regenerate(state_root, config, args)
    raise _fail("cg37_method_unknown:" + method)
