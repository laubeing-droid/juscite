#!/usr/bin/env python3
"""E26 两处 BLOCKED 真机人工复验——收口校验器（W4-U30）。

裁决#22（00-总协调.md §6.1 #22）：E26 驱动方式 = T10 屏幕裁剪＋人工清单，不新建自动化驱动。
本工具**只校验证据齐备与结论一致性，不驱动 UI**——真机人工复验无法机替。

W3-U28（docs/construction/evidence/E26/desktop/e26-b3-result.md）留了两处 BLOCKED：
  ①E26-2 「新建任务」「编写法律任务」两按钮 Tab 直达子断言（可达性探针三因叠加）；
  ②E26-6 IME 组合态四子步（CUA/事件/SendInput 三通道均不可达实证）。
另附标题栏明暗往返不还原＝产品缺陷候选（patch 019 已交付修复，活体复测留人工窗口）。

人工执行（按 docs/construction/e26-b3-checklist.md）：
  §0  前置与启动（Start-JusBench.ps1；红线：绝不碰 %APPDATA%\\JusBench）；
  §1  取证一律 e26_capture.ps1（T10 屏幕裁剪＋像素统计；判定口径 unique_colors≥100
      且 top_color_share<99% 为非空白）；
  §4-E26-2 步骤 2/3 —— 纯键盘 Tab 走查头部「新建任务」「编写法律任务」两按钮；
  §4-E26-6 步骤 1-4 —— 微软拼音组合态四子步；
  第 3 节（可选）—— 标题栏明暗往返复测，必须在**带 patch 019 的构建**上执行
      （主检出 oc28 只应用了 001-011，不含 019；带 019 的一次性检出重建命令见下）。

带 019 的一次性检出重建（全程不碰主检出 001-011 应用态）：
  git clone -c core.autocrlf=false -c core.symlinks=true <oc28> %TEMP%\\e26-tb-verify
  cd  %TEMP%\\e26-tb-verify && git checkout 026b106bc5d41b679ffc413264229c340871e4d3
  git apply <juscite>\\implementation\\patches\\{001,002,003,004,005,006,007,008,010,011}-*.patch
  git apply <juscite>\\implementation\\patches\\019-fix-titlebar-theme-roundtrip.patch
  启动：Start-JusBench.ps1 -Repository %TEMP%\\e26-tb-verify -Run

结果文件：docs/construction/evidence/E26/desktop/e26-recheck-result.md（模板见 PENDING 输出）。
退出码：0 = 六子步复验证据齐备且结论一致（第 3 节可选，存在则同样校验）；
        1 = 结果文件存在但证据/结论不一致；
        2 = PENDING_OWNER：人工复验未完成（本波无人力窗口时的如实留档状态，不假 PASS）。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

RESULT_NAME = "e26-recheck-result.md"

# (section key, sub-item id, 义务出处) —— 六个必验子步
REQUIRED_ITEMS = [
    ("1", "E26-2a", "「新建任务」按钮 Tab 直达（清单 §4-E26-2 步骤 2）"),
    ("1", "E26-2b", "「编写法律任务」按钮 Tab 直达（清单 §4-E26-2 步骤 3）"),
    ("2", "E26-6a", "中文标点经 IME 直出全角（清单 §4-E26-6 步骤 1）"),
    ("2", "E26-6b", "Shift+Space 全/半角切换输入（清单 §4-E26-6 步骤 2）"),
    ("2", "E26-6c", "组合态 Enter 只确认候选不发送（editor.tsx:267 守卫的运行时验证）"),
    ("2", "E26-6d", "组合态 Esc 取消组合（清单 §4-E26-6 步骤 4）"),
]
OPTIONAL_ITEM = ("3", "E26-5b", "标题栏明暗往返还原复测（patch 019 生效构建上执行；可选）")

ENV_KEYS = ["product-commit", "display", "locale", "ime"]
VERDICT_RE = re.compile(r"^verdict:\s*(PASS|FAIL)\s*$", re.M)
EVIDENCE_RE = re.compile(r"^evidence:\s*(\S+)\s*$", re.M)
NOTE_RE = re.compile(r"^note:\s*(.+)$", re.M)
STATS_RE = re.compile(
    r"^stats:\s*RESULT\s+file=(?P<file>\S+)\s+size=(?P<w>\d+)x(?P<h>\d+)\s+"
    r"unique_colors=(?P<colors>\d+)\s+pixels=(?P<pixels>\d+)\s+top_color_share=(?P<share>[\d.]+)%\s*$",
    re.M,
)
SUBJECT_RE = re.compile(r"^###\s+(E26-\w+)\s*$", re.M)


def parse_items(text: str) -> dict[str, str]:
    """Split the result file into per-sub-item blocks keyed by ### heading."""
    heads = list(SUBJECT_RE.finditer(text))
    blocks: dict[str, str] = {}
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        blocks[m.group(1)] = text[m.end() : end]
    return blocks


def png_stats(path: Path) -> tuple[int, int, float] | None:
    """Recompute (unique_colors, pixels, top_color_share%) from the PNG, if PIL is available."""
    try:
        from PIL import Image  # noqa: PLC0415 — optional dependency, degrade honestly
    except ImportError:
        return None
    with Image.open(path) as im:
        rgb = im.convert("RGB")
        counts: dict[tuple[int, int, int], int] = {}
        total = 0
        for px in rgb.getdata():
            counts[px] = counts.get(px, 0) + 1
            total += 1
    top = max(counts.values())
    return len(counts), total, 100.0 * top / total


def check_item(item_id: str, block: str, evidence_dir: Path, lines: list[str]) -> bool:
    ok = True
    v = VERDICT_RE.search(block)
    if not v:
        lines.append(f"FAIL {item_id}: 缺 verdict（只许 PASS/FAIL——人工复验的目的就是定案，不许 BLOCKED）")
        return False
    lines.append(f"OK   {item_id}: verdict={v.group(1)}")
    if v.group(1) not in ("PASS", "FAIL"):
        ok = False

    ev = EVIDENCE_RE.search(block)
    stats = STATS_RE.search(block)
    if not ev:
        lines.append(f"FAIL {item_id}: 缺 evidence（PNG 文件名）")
        ok = False
    if not stats:
        lines.append(f"FAIL {item_id}: 缺 stats（e26_capture.ps1 的 RESULT 行原样粘贴）")
        ok = False
    if not ev or not stats:
        return False

    png = evidence_dir / ev.group(1)
    if not png.is_file():
        lines.append(f"FAIL {item_id}: 证据 PNG 不存在：{png}")
        ok = False
    elif Path(stats.group("file")).name != ev.group(1):
        # e26_capture.ps1 的 RESULT 行 file= 是全路径；evidence= 记文件名，按 basename 对齐。
        lines.append(f"FAIL {item_id}: stats file={stats.group('file')} 与 evidence={ev.group(1)} 不一致")
        ok = False

    colors = int(stats.group("colors"))
    share = float(stats.group("share"))
    if colors < 100 or share >= 99.0:
        lines.append(
            f"FAIL {item_id}: 像素统计不满足清单 §1 非空白口径（unique_colors={colors} 需≥100，"
            f"top_color_share={share}% 需<99%）——疑似空白帧"
        )
        ok = False

    note = NOTE_RE.search(block)
    if not note or not note.group(1).strip():
        lines.append(f"FAIL {item_id}: 缺 note（人工判读一句为清单硬性要求）")
        ok = False

    if png.is_file():
        recomputed = png_stats(png)
        if recomputed is None:
            lines.append(f"WARN {item_id}: PIL 不可用，跳过 PNG 像素复核（claims 以人工粘贴 stats 为准）")
        else:
            r_colors, r_pixels, r_share = recomputed
            if abs(r_colors - colors) > max(2, colors // 100) or abs(r_share - share) > 2.0:
                lines.append(
                    f"FAIL {item_id}: PNG 实算 unique_colors={r_colors} top_color_share={r_share:.2f}% "
                    f"与 stats 声明（{colors} / {share}%）不符——证据与结论不一致"
                )
                ok = False
            else:
                lines.append(
                    f"OK   {item_id}: PNG 像素复核一致（实算 {r_colors} 色 / {r_share:.2f}%）"
                )
    return ok


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--evidence-dir", default="docs/construction/evidence/E26/desktop", help="证据目录（默认相对 cwd）")
    args = ap.parse_args(argv)
    evidence_dir = Path(args.evidence_dir)
    result_path = evidence_dir / RESULT_NAME

    lines: list[str] = []
    if not result_path.is_file():
        print(f"PENDING_OWNER：未找到人工复验结果文件 {result_path}")
        print()
        print("两处 BLOCKED 仍为 BLOCKED（如实留档，不假 PASS）。人工窗口执行要目：")
        print("  ① E26-2 两按钮 Tab 直达：清单 docs/construction/e26-b3-checklist.md §4-E26-2 步骤 2/3")
        print("    （§0 启动；全程键盘；记录每步 Tab 次数与焦点环所见）")
        print("  ② E26-6 IME 组合态四子步：清单 §4-E26-6 步骤 1-4（微软拼音中文模式）")
        print("  ③（可选）标题栏明暗往返复测：需带 patch 019 的构建（重建命令见本文件 docstring）")
        print("  取证：一律 §1 e26_capture.ps1（pwsh 7.6.4；判定口径 unique_colors≥100 且 top<99%）")
        print("  红线：绝不碰 %APPDATA%\\JusBench；合成材料；证据缺失=BLOCKED，不 PASS")
        print()
        print(f"完成后把结果按下列模板写入 {result_path}（路径相对产品仓/worktree 根）：")
        print(TEMPLATE.strip())
        return 2

    text = result_path.read_text(encoding="utf-8")
    ok = True

    head = text.split("###", 1)[0]
    env: dict[str, str] = {}
    for key in ENV_KEYS:
        m = re.search(rf"^{key}:\s*(\S.*?)\s*$", head, re.M)
        if not m:
            lines.append(f"FAIL env: 结果文件头部缺必填环境行「{key}:」")
            ok = False
        else:
            env[key] = m.group(1)
    if "product-commit" in env and not re.fullmatch(r"[0-9a-f]{40}", env["product-commit"]):
        lines.append(f"FAIL env: product-commit 不是 40 位十六进制（实测 {env['product-commit']}）")
        ok = False
    for key, precedent in (("display", "1920x1080"), ("locale", "zh-Hans-CN")):
        if key in env and env[key] != precedent:
            lines.append(f"WARN env: {key}={env[key]} 与先例环境 {precedent} 不同（记录在案，不判失败）")

    blocks = parse_items(text)
    seen: dict[str, str] = {}
    for _, item_id, desc in REQUIRED_ITEMS:
        block = blocks.get(item_id)
        lines.append(f"-- {item_id}: {desc}")
        if block is None:
            lines.append(f"FAIL {item_id}: 结果文件缺「### {item_id}」小节")
            ok = False
            continue
        ok = check_item(item_id, block, evidence_dir, lines) and ok
        ev = EVIDENCE_RE.search(block)
        if ev:
            if ev.group(1) in seen:
                lines.append(f"FAIL {item_id}: 证据 PNG {ev.group(1)} 已被 {seen[ev.group(1)]} 使用——一帧不能证两态")
                ok = False
            seen[ev.group(1)] = item_id

    _, opt_id, opt_desc = OPTIONAL_ITEM
    if opt_id in blocks:
        lines.append(f"-- {opt_id}（可选）: {opt_desc}")
        ok_opt = check_item(opt_id, blocks[opt_id], evidence_dir, lines)
        # 可选节存在即校验其内部一致性；其证据不得与必验项重复，但不影响 exit 0 的达成条件？
        # 影响：既然人工做了，就必须做对——纳入一致性要求。
        ok = ok_opt and ok
        ev = EVIDENCE_RE.search(blocks[opt_id])
        if ev and ev.group(1) in seen:
            lines.append(f"FAIL {opt_id}: 证据 PNG {ev.group(1)} 与 {seen[ev.group(1)]} 重复")
            ok = False
    else:
        lines.append(f"NOTE {opt_id}: 第 3 节标题栏复测未执行（可选；patch 019 活体复测仍留待后续人工窗口）")

    for line in lines:
        print(line)
    print()
    if ok:
        print("RESULT: PASS —— 六子步复验证据齐备且结论一致（两处 BLOCKED 可定案销账）")
        return 0
    print("RESULT: FAIL —— 结果文件存在但证据/结论不一致（见上方 FAIL 行）")
    return 1


TEMPLATE = """
## 0. 验收环境
product-commit: <验收会话产品构建的 git commit（40 位）>
display: 1920x1080
locale: zh-Hans-CN
ime: <实际输入法，如 微软拼音>

## 1. E26-2 按钮键盘直达
### E26-2a
verdict: PASS|FAIL
evidence: e26_recheck_<tag>_<hhmmss>.png
stats: RESULT file=e26_recheck_<tag>_<hhmmss>.png size=1296x808 unique_colors=1234 pixels=1046208 top_color_share=61.50%
note: <Tab 次数与焦点环所见；FAIL 时写实际现象>

### E26-2b
（同构四行）

## 2. E26-6 IME 组合态
### E26-6a
（同构四行）
### E26-6b
### E26-6c
（note 必须写：组合态按 Enter 后时间线消息数，应为 0；再按一次才发送）
### E26-6d

## 3. 标题栏明暗往返复测（可选；须带 patch 019 构建）
### E26-5b
verdict: PASS|FAIL
evidence: <往返后 system 档整窗 PNG>
stats: <RESULT 行>
note: <系统→浅色→深色→系统 往返后页签条带是否还原；对照初始 system 档帧>
"""


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
