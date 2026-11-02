#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""W4-U39 A1 裁决性 EXCLUDED 永久结转 recon（第三批·记账收口）：恰 F57-word
一行翻 EXCLUDED＋E28 runner word 结转词面随实际演进（三行→四行）。

权威链：
 - docs/construction/00-总协调.md §6.1a A1（2026-10-18 用户裁决：Word 不安
   装）逐名清单含 F57-word：E13/F46-word/F52-word/F57-word 的 word 宿主半边
   永久结转（原回收点 W2-S1/W4-S2 作废）；W4 规划相关行按 EXCLUDED 处理；
 - W2b-U60 先批（2026-10-20 账房合并）翻 F17-word/F46-word/F52-word 三行并
   明示「F57-word 仍 NOT_RUN（W4 范围零越界）」留本单（其工具 C3 原文）；
 - registry 裁决性类别已支持（tools/acceptance/registry.py:41-46,83-85：
   failure_reason 以「裁决性 EXCLUDED」开头＋裁决号，validate 单独计数不入
   砍行等式）——本单零 registry 代码改动；
 - E28 runner word 结转词面随实际演进（W3-U37「S4C 词面随实际」演进门先
   例）：WORD_CARRYOVER_IDS 三行→四行＋S3D 词面「三行」→「四行」＋docstring
   NOT_RUN 计数 91→90/B4 段 54→53；S5 移交清单与 B3 前缀表不越界不动。

用法：
  无参＝复验模式（验收命令，本单 worktree 根 cwd）：
    python -X utf8 tools/recon/PENDING_OWNER_f57word_a1_exclusion_recon.py
    ⇒ 全检 PASS 输出 RECON_OK exit 0；任一 FAIL 输出 RECON_FAIL exit 2。
  --apply＝施工模式（本单施工期一次性落账）：仅当台账仍处基线态
    （文件 sha256==基线@dd7dda7）时执行恰 1 行变更；已落账态拒绝重复写
    exit 2。

六检（镜像 W2b-U60 recon 六检结构）：
  C0 BOM：文件以 UTF-8 BOM 开头且全文件合法 UTF-8；
  C1 CRLF 段字节外科：恰 299 个 CRLF 行段＋末尾 CRLF＋无裸 LF/CR；恰段 107
     （1 基行号，F57-word）为变更段，余 298 段按序拼接 sha256==基线@dd7dda7
     钉死值（逐字节不动）；
  C2 恰 1 行变更且新内容钉死：变更行 obligation_id=F57-word，status=EXCLUDED
     且 failure_reason 以「裁决性 EXCLUDED」开头引 A1＋Word 缺失实证引 E13
     行 failure_reason 在案复核探针＋同规则延伸性质（全文与本单落账逐字相
     等，字节==钉死 b64）；余 16 列与基线行逐字段相等；
  C3 结构零越界面：298 实例 18 列 id 唯一（id 集零增删由 C1/C2 段级钉死推
     出）；census EXCLUDED=28（裁剪行 24＋裁决性 4）/IMPLEMENTING=12/
     NOT_RUN=90/VERIFIED=168；
  C4 E28 runner word 结转词面随实际演进：活导入 runner 模块——
     WORD_CARRYOVER_IDS 恰四行（含 F57-word）；S3D 对当前台账活跑 PASS 且
     词面「四行」；section_s0＋section_s3 全检 PASS（裁决 IMPLEMENTING 续）；
  C5 S5 不越界＋registry validate PASS：section_s5 移交 expect 恰五项
     （E19/E20/E22/E25/E26）且源面无 F57-word 入 S5；B3_NOT_RUN_EXPECTED_
     PREFIX 维持基线六前缀（F57-word 属 B4 不入 B3 表）；内含复验
     python -X utf8 tools/acceptance/registry.py validate＝PASS exit 0。

全程只读（--apply 除外）；测试一律合成材料；oc28 与 %APPDATA%\JusBench
零触碰；不 push 不 PR。
"""

from __future__ import annotations

import ast
import base64
import csv
import hashlib
import importlib.util
import inspect
import io
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LEDGER_PATH = REPO_ROOT / "docs" / "construction" / "acceptance-ledger.csv"
REGISTRY_PATH = REPO_ROOT / "tools" / "acceptance" / "registry.py"
E28_RUNNER_PATH = REPO_ROOT / "tools" / "PENDING_OWNER_e28_stage_acceptance.py"

# 基线＝本单建支点 main@dd7dda7（W3-U37 合并后，F57-word 尚 NOT_RUN 态）。
BASELINE_COMMIT = "dd7dda7"
TARGET_ID = "F57-word"

# ---- 基线常量（由基线@dd7dda7 台账确定性生成，非手抄）------------------
_BASELINE_FILE_SHA256 = "aeb187ce5a762d0d0012ce9a634d8110c68641d86d30e1fc97ab5f432931b794"
# 297 非目标行段（0 基段 106 为目标段）按原序拼接的 sha256——段级字节外科钉死。
_NON_TARGET_CONCAT_SHA256 = (
    "6e21f4a3792109b4a6254721d542c08d0d1094179553a40b6c27a7d77b34c3c1")
_ORIG_ROW_B64 = ("RjU3LXdvcmQsRjU3LHF1aWNrX2FjdGlvbuivu+WPluWunumZhemAieWMui/k"
                 "uIrkuIvmlofkuJTlj5fmnYPpmZDvvJvkuI3ph43lpI3mj5DkuqTnvJbovpEs"
                 "ZGVza3RvcDtzZWxmaG9zdCx3b3JkLGRvY3VtZW50LWFkYXB0ZXIsIkUxMixF"
                 "MTMsRTE1IiwsUEVORElOR19PV05FUl9JTVBMRU1FTlRBVElPTixQRU5ESU5H"
                 "X09XTkVSX0lNUExFTUVOVEFUSU9OLOmqjOaUtuaXtuWHhuehrmNvbW1pdC9w"
                 "YWNrYWdl77yb5pys6L2u6Z2Z5oCBcmVmc+S4jeivgeaYjmNsZWFuLCwsLGV2"
                 "aWRlbmNlL0Y1Ny93b3JkLyxOT1RfUlVOLCxCNA==")
_NEW_ROW_B64 = ("RjU3LXdvcmQsRjU3LHF1aWNrX2FjdGlvbuivu+WPluWunumZhemAieWMui/k"
                "uIrkuIvmlofkuJTlj5fmnYPpmZDvvJvkuI3ph43lpI3mj5DkuqTnvJbovpEsZ"
                "GVza3RvcDtzZWxmaG9zdCx3b3JkLGRvY3VtZW50LWFkYXB0ZXIsIkUxMixFMT"
                "MsRTE1IiwsUEVORElOR19PV05FUl9JTVBMRU1FTlRBVElPTixQRU5ESU5HX09"
                "XTkVSX0lNUExFTUVOVEFUSU9OLOmqjOaUtuaXtuWHhuehrmNvbW1pdC9wYWNr"
                "YWdl77yb5pys6L2u6Z2Z5oCBcmVmc+S4jeivgeaYjmNsZWFuLCwsLGV2aWRlb"
                "mNlL0Y1Ny93b3JkLyxFWENMVURFRCzoo4HlhrPmgKcgRVhDTFVERUTvvIhBMe"
                "+8mldvcmQg5LiN5a6J6KOF77yMMjAyNi0xMC0xOO+8m+WOnyBXMi1TMS9XNC1"
                "TMiDlm57mlLbngrnkvZzlup/vvInvvJtBMSDpgJDlkI3muIXljZXliJflkI3m"
                "nKzooYzvvIh3b3JkIOWuv+S4u+WNiui+ueawuOS5hee7k+i9rMK3VzQg6KeE5"
                "YiS55u45YWz6KGM5oyJIEVYQ0xVREVEIOWkhOeQhu+8icK3cGhhc2U9QjQg5b"
                "GeIFc0IOazou+8m1dvcmQg57y65aSx5a6e6K+B5byVIEUxMyDooYwgZmFpbHV"
                "yZV9yZWFzb24g5Zyo5qGI5aSN5qC45o6i6ZKI77yISEtDVSBXb3JkLkFwcGxp"
                "Y2F0aW9uIFByb2dJRCDmgqznqbrlo7PvvItXSU5XT1JELkVYRSDlhajnm5jpm"
                "7blkb3kuK3vvInvvJvmnKzooYzml6AgV1BTIOWNiui+ueWunuS+i++8iDA2IO"
                "ihjCBGNTfjgIxXb3JkIOmdouadvyBxdWlja19hY3Rpb25z44CNYWNjZXB0YW5"
                "jZSDku4UgV29yZCDlrr/kuLvCt+WNleWunuS+i++8ie+8m+aMiSBXMmItVTYw"
                "IOWQjOinhOWImeW7tuS8uOiQvei0pu+8iOijgeWGs+aApyBFWENMVURFRCDns"
                "bvCt+esrOS4ieaJueiusOi0puaUtuWPo8K35bel5Y2VIFc0LVUzOcK36LSm5o"
                "i/6aqM5pS25LiN6K6k5Y+v6YCA5ZueIE5PVF9SVU7vvIksQjQ=")
_EXPECTED_FILE_SHA256 = "d8bbb1f2586839013cd0b4719ce44ff6b432b4c84d3d5230335767ba59076fe5"
_TARGET_SEG_IDX = 106  # 0 基段号＝1 基行号 107

# 裁决性 EXCLUDED 类前缀（与 tools/acceptance/registry.py、E28 runner 同键）。
ADJUDICATED_EXCLUDED_PREFIX = "裁决性 EXCLUDED"
# F57-word 行 failure_reason 落账全文（起点必须为前缀，registry 据此分类）。
F57_WORD_REASON = (
    "裁决性 EXCLUDED（A1：Word 不安装，2026-10-18；原 W2-S1/W4-S2 回收点作废）；"
    "A1 逐名清单列名本行（word 宿主半边永久结转·W4 规划相关行按 EXCLUDED 处理）·"
    "phase=B4 属 W4 波；Word 缺失实证引 E13 行 failure_reason 在案复核探针"
    "（HKCU Word.Application ProgID 悬空壳＋WINWORD.EXE 全盘零命中）；"
    "本行无 WPS 半边实例（06 行 F57「Word 面板 quick_actions」acceptance 仅 "
    "Word 宿主·单实例）；按 W2b-U60 同规则延伸落账（裁决性 EXCLUDED 类·"
    "第三批记账收口·工单 W4-U39·账房验收不认可退回 NOT_RUN）"
)

STATUS_IDX = 15        # LEDGER_FIELDS 中 status 列
FAILURE_REASON_IDX = 16  # LEDGER_FIELDS 中 failure_reason 列

# C4/C5 期望（E28 runner 演进后词面；B3 前缀表与 S5 移交清单＝不越界基线值）。
EXPECTED_WORD_CARRYOVER_IDS = ("F17-word", "F46-word", "F52-word", "F57-word")
EXPECTED_B3_PREFIX = ("F14", "F17-word", "F19", "F46-word", "F52-word", "E28")
EXPECTED_S5_HANDOVER_IDS = ("E19", "E20", "E22", "E25", "E26")


class ReconFail(Exception):
    """任一检查 FAIL；CLI 层输出 RECON_FAIL exit 2。"""


def _row_bytes(fields: list[str]) -> bytes:
    """单行 CSV 序列化（QUOTE_MINIMAL，无行尾符）——与台账产物同规则。"""
    buf = io.StringIO()
    csv.writer(buf, lineterminator="").writerow(fields)
    return buf.getvalue().encode("utf-8")


def _split_segments(raw: bytes) -> list[bytes]:
    """按 CRLF 切行段；校验形状（C1）。返回恰 299 段。"""
    if b"\n" in raw.replace(b"\r\n", b"") or b"\r" in raw.replace(b"\r\n", b""):
        raise ReconFail("C1：存在裸 LF/CR（CRLF 保持被破坏）")
    if not raw.endswith(b"\r\n"):
        raise ReconFail("C1：文件未以 CRLF 结尾")
    segments = raw.split(b"\r\n")
    if segments[-1] != b"":
        raise ReconFail("C1：CRLF 切分尾段非空")
    segments = segments[:-1]
    if len(segments) != 299:
        raise ReconFail(f"C1：行段数 {len(segments)} != 299")
    return segments


def _segments_identifiers(segments: list[bytes]) -> dict[str, int]:
    """行段 obligation_id 索引（首列，CSV 感知引号；BOM 仅在表头段）。"""
    ids: dict[str, int] = {}
    for idx, seg in enumerate(segments):
        first = next(csv.reader([seg.decode("utf-8-sig")]), [""])[0]
        if first:
            if first in ids:
                raise ReconFail(f"C3：obligation_id 重复：{first}")
            ids[first] = idx
    return ids


def _check_c1_byte_surgery(segments: list[bytes], target_idx: int) -> None:
    """余 298 段按序拼接 sha256==基线钉死值；目标段==基线原字节或新字节。"""
    nontarget = b"".join(segments[:target_idx] + segments[target_idx + 1:])
    if hashlib.sha256(nontarget).hexdigest() != _NON_TARGET_CONCAT_SHA256:
        raise ReconFail(
            "C1：297 非目标行段拼接 sha256≠基线@%s 钉死值（非目标行被改动）"
            % BASELINE_COMMIT)


def _check_c2_target_row(segments: list[bytes], target_idx: int) -> None:
    new_row = base64.b64decode(_NEW_ROW_B64)
    orig_row = base64.b64decode(_ORIG_ROW_B64)
    seg = segments[target_idx]
    if seg not in (orig_row, new_row):
        raise ReconFail("C2：目标段≠基线原字节亦≠本单落账钉死字节")
    if seg == orig_row:
        raise ReconFail("C2：目标段仍为基线原字节（F57-word 未落账）")
    fields = next(csv.reader([seg.decode("utf-8")]))
    orig_fields = next(csv.reader([orig_row.decode("utf-8")]))
    if fields[0] != TARGET_ID:
        raise ReconFail(f"C2：变更行 id={fields[0]!r} != {TARGET_ID}")
    if fields[STATUS_IDX] != "EXCLUDED":
        raise ReconFail(
            f"C2：status={fields[STATUS_IDX]!r} != EXCLUDED")
    fr = fields[FAILURE_REASON_IDX]
    if not fr.startswith(ADJUDICATED_EXCLUDED_PREFIX):
        raise ReconFail("C2：failure_reason 非「裁决性 EXCLUDED」开头")
    for token, label in (
            ("A1", "裁决号 A1"),
            ("Word 不安装", "A1 裁决词"),
            ("E13", "E13 探针指针"),
            ("ProgID 悬空壳", "Word 缺失实证"),
            ("WINWORD.EXE", "Word 缺失实证"),
            ("同规则延伸", "同规则延伸性质"),
            ("永久结转", "永久结转"),
            ("逐名清单列名本行", "A1 逐名清单"),
            ("W4-U39", "本单工单号")):
        if token not in fr:
            raise ReconFail(f"C2：failure_reason 缺 {label}")
    if fr != F57_WORD_REASON:
        raise ReconFail("C2：failure_reason 与本单落账全文不符")
    kept = [i for i in range(18) if i not in (STATUS_IDX, FAILURE_REASON_IDX)]
    if [fields[i] for i in kept] != [orig_fields[i] for i in kept]:
        raise ReconFail("C2：余 16 列与基线行不逐字段相等（越界改列）")


def _check_c3_structure(segments: list[bytes]) -> str:
    text = b"\r\n".join(segments) + b"\r\n"
    rows = list(csv.DictReader(io.StringIO(text.decode("utf-8-sig"), newline="")))
    if len(rows) != 298:
        raise ReconFail(f"C3：数据行 {len(rows)} != 298")
    if any(len(r) != 18 for r in rows):
        raise ReconFail("C3：存在列数≠18 的行")
    census: dict[str, int] = {}
    cut_class = adjudicated = 0
    for r in rows:
        census[r["status"]] = census.get(r["status"], 0) + 1
        if r["status"] == "EXCLUDED":
            fr = r.get("failure_reason", "")
            if fr == "裁剪行":
                cut_class += 1
            elif fr.startswith(ADJUDICATED_EXCLUDED_PREFIX):
                adjudicated += 1
    want = {"EXCLUDED": 28, "IMPLEMENTING": 12, "NOT_RUN": 90, "VERIFIED": 168}
    if census != want:
        raise ReconFail(f"C3：census {census} != {want}")
    if (cut_class, adjudicated) != (24, 4):
        raise ReconFail(
            f"C3：EXCLUDED 分类（裁剪行 {cut_class}＋裁决性 {adjudicated}）!=（24＋4）")
    return ("census: EXCLUDED=28（裁剪行 24＋裁决性 4）IMPLEMENTING=12 "
            "NOT_RUN=90 VERIFIED=168（总数 298·id 集零增删由 C1/C2 段级钉死推出）")


def _load_e28_runner():
    spec = importlib.util.spec_from_file_location(
        "juscite_e28_runner_w4u39", str(E28_RUNNER_PATH))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _check_c4_e28_surface(module) -> str:
    if sorted(module.WORD_CARRYOVER_IDS) != list(EXPECTED_WORD_CARRYOVER_IDS):
        raise ReconFail(
            "C4：WORD_CARRYOVER_IDS=%s != 演进后四行 %s"
            % (sorted(module.WORD_CARRYOVER_IDS),
               list(EXPECTED_WORD_CARRYOVER_IDS)))
    source = E28_RUNNER_PATH.read_text(encoding="utf-8")
    if "word 宿主三行" in source:
        raise ReconFail("C4：源面残留「word 宿主三行」旧词面")
    if "word 宿主四行" not in source:
        raise ReconFail("C4：源面缺「word 宿主四行」演进词面")
    checks = module.Checks()
    denom = json.loads(module.DENOMINATOR_JSON.read_text(encoding="utf-8"))
    rows06 = module.read_csv(module.ROWS06_CSV)
    rows07 = module.read_csv(module.ROWS07_CSV)
    ledger = module.read_csv(module.LEDGER_CSV)
    census = module.section_s0(checks, module.load_registry(), denom,
                               rows06, rows07, ledger)
    s3 = module.section_s3(checks, ledger, census)
    failed = [i for i in checks.items if i["status"] != "PASS"]
    if failed:
        raise ReconFail(
            "C4：runner section_s0＋section_s3 活跑有 FAIL：%s"
            % [(i["id"], i["detail"][:120]) for i in failed[:3]])
    s3d = [i for i in checks.items if i["id"] == "S3D_word_carryover_a1_honest"]
    if not s3d or s3d[0]["status"] != "PASS" or "四行" not in s3d[0]["detail"]:
        raise ReconFail("C4：S3D 活跑非 PASS 或词面非「四行」")
    if s3.get("verdict") != "IMPLEMENTING":
        raise ReconFail(f"C4：阶段裁决 {s3.get('verdict')!r} != IMPLEMENTING")
    return ("活导入 runner：WORD_CARRYOVER_IDS=四行（含 F57-word）；"
            "section_s0＋section_s3 共 %d 检全 PASS；S3D 四行词面 PASS；"
            "阶段裁决=IMPLEMENTING（续）" % len(checks.items))


def _s5_expect_keys(module) -> set[str]:
    tree = ast.parse(inspect.getsource(module.section_s5))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "expect"
                for t in node.targets):
            if isinstance(node.value, ast.Dict):
                return {k.value for k in node.value.keys
                        if isinstance(k, ast.Constant)}
    raise ReconFail("C5：section_s5 源面未找到 expect 清单（结构漂移）")


def _check_c5_s5_no_overreach_and_registry(module) -> str:
    s5_keys = _s5_expect_keys(module)
    if s5_keys != set(EXPECTED_S5_HANDOVER_IDS):
        raise ReconFail(
            "C5：S5 移交 expect %s != 基线五项 %s（不越界被破坏）"
            % (sorted(s5_keys), list(EXPECTED_S5_HANDOVER_IDS)))
    if module.B3_NOT_RUN_EXPECTED_PREFIX != EXPECTED_B3_PREFIX:
        raise ReconFail(
            "C5：B3_NOT_RUN_EXPECTED_PREFIX=%s != 基线六前缀 %s"
            % (module.B3_NOT_RUN_EXPECTED_PREFIX, EXPECTED_B3_PREFIX))
    s5src = inspect.getsource(module.section_s5)
    if TARGET_ID in s5src:
        raise ReconFail("C5：F57-word 混入 S5 移交清单（越界）")
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", str(REGISTRY_PATH), "validate"],
        cwd=str(REPO_ROOT), capture_output=True, text=True,
        encoding="utf-8", errors="replace")
    tail = (proc.stdout or "").strip().splitlines()
    detail = tail[-1] if tail else f"exit={proc.returncode} 无 stdout"
    if proc.returncode != 0 or "PASS" not in (proc.stdout or ""):
        raise ReconFail(
            f"C5：registry validate exit={proc.returncode} 非 PASS——"
            f"{detail}；stderr={(proc.stderr or '').strip()[:400]}")
    return ("S5 移交 expect 恰五项 %s＋B3 前缀表不动（F57-word 属 B4 不入 "
            "B3 表）；registry validate：%s（exit 0）"
            % (sorted(s5_keys), detail))


def run_verify() -> int:
    raw = LEDGER_PATH.read_bytes()
    checks: list[tuple[str, bool, str]] = []
    try:
        if not raw.startswith(b"\xef\xbb\xbf"):
            raise ReconFail("C0：台账缺 UTF-8 BOM")
        raw.decode("utf-8-sig")
        checks.append(("C0_bom_utf8", True, "UTF-8 BOM＋全文件合法 UTF-8"))
        segments = _split_segments(raw)
        ids = _segments_identifiers(segments)
        if TARGET_ID not in ids:
            raise ReconFail(f"C2：{TARGET_ID} 不在台账")
        target_idx = ids[TARGET_ID]
        if target_idx != _TARGET_SEG_IDX:
            raise ReconFail(
                f"C1：目标段号漂移 {target_idx} != {_TARGET_SEG_IDX}")
        _check_c1_byte_surgery(segments, target_idx)
        checks.append((
            "C1_crlf_segment_byte_surgery", True,
            "恰 299 CRLF 段＋末尾 CRLF＋无裸 LF/CR；段 107（F57-word）为变更"
            f"段，余 298 段按序逐字节==基线@{BASELINE_COMMIT}（拼接 sha256 钉死）"))
        _check_c2_target_row(segments, target_idx)
        checks.append((
            "C2_exactly_one_row_changed_content_pinned", True,
            "恰 1 行变更＝F57-word：status=EXCLUDED＋failure_reason 裁决性 "
            "EXCLUDED 引 A1＋E13 在案复核探针＋同规则延伸（字节==钉死 b64·"
            "余 16 列与基线逐字段相等）"))
        digest = hashlib.sha256(
            b"\r\n".join(segments) + b"\r\n").hexdigest()
        if digest != _EXPECTED_FILE_SHA256:
            raise ReconFail(
                f"C3：全文件 sha256={digest} != 落账后钉死值 {_EXPECTED_FILE_SHA256}")
        detail_c3 = _check_c3_structure(segments)
        checks.append(("C3_structure_census", True,
                       f"{detail_c3}；文件 sha256={digest[:16]}…"))
        module = _load_e28_runner()
        detail_c4 = _check_c4_e28_surface(module)
        checks.append((
            "C4_e28_runner_word_surface_evolved", True,
            detail_c4 + "（W3-U37 词面随实际演进门先例）"))
        detail_c5 = _check_c5_s5_no_overreach_and_registry(module)
        checks.append(("C5_s5_no_overreach_registry_validate", True, detail_c5))
    except ReconFail as exc:
        message = str(exc)
        checks.append(("FAILED_CHECK", False, message))
        print("RECON_FAIL")
        for cid, ok, detail in checks:
            print(f"[{'PASS' if ok else 'FAIL'}] {cid} — {detail}")
        return 2
    print(f"W4-U39 F57-word A1 裁决性 EXCLUDED recon（基线@{BASELINE_COMMIT}，"
          f"台账 sha256={hashlib.sha256(raw).hexdigest()[:16]}…）")
    for cid, ok, detail in checks:
        print(f"[PASS] {cid} — {detail}")
    print("RECON_OK")
    return 0


def run_apply() -> int:
    raw = LEDGER_PATH.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest == _EXPECTED_FILE_SHA256:
        print("APPLY_REFUSED：台账已是落账后态（幂等拒写；请用无参复验模式）")
        return 2
    if digest != _BASELINE_FILE_SHA256:
        print(f"APPLY_REFUSED：台账非基线@{BASELINE_COMMIT} 态"
              f"（sha256={digest}），拒绝落账")
        return 2
    segments = raw.split(b"\r\n")[:-1]
    new_row = base64.b64decode(_NEW_ROW_B64)
    expected = segments[:_TARGET_SEG_IDX] + [new_row] + segments[_TARGET_SEG_IDX + 1:]
    expected_raw = b"\r\n".join(expected) + b"\r\n"
    if hashlib.sha256(expected_raw).hexdigest() != _EXPECTED_FILE_SHA256:
        print("APPLY_REFUSED：重建字节与落账后钉死 sha256 不符（内部态漂移）")
        return 2
    LEDGER_PATH.write_bytes(expected_raw)
    print(f"APPLIED：恰 1 行落账（{TARGET_ID} 翻裁决性 EXCLUDED·段字节外科）；"
          f"复验请无参运行本工具")
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    args = list(sys.argv[1:] if argv is None else argv)
    if args == ["--apply"]:
        return run_apply()
    if args:
        print("用法：python -X utf8 tools/recon/PENDING_OWNER_f57word_a1_exclusion_recon.py "
              "[--apply]", file=sys.stderr)
        return 2
    return run_verify()


if __name__ == "__main__":
    sys.exit(main())
