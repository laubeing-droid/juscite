# -*- coding: utf-8 -*-
"""RE-21 增补 §3.0 迁移待办①·一次性迁移脚本（2026-10-31 主控裁决落定）。

把 catzip 第 1 轮面已装 user 技能（%APPDATA%\\Juscite\\bridge\\skills\\<name>\\
平铺布局）迁入安全层版本层 packages/<id>/<version>/（+records/ 安装记录+
history 事件账）。迁移语义/逐件隔离/幂等冲突码见 skill_security.
migrate_catzip_skills docstring 与 RE-21 增补 §3.0/§3.6（规格级定稿）。

一次性：跑完即归档，不进 legal_entry 冻结方法组、不进桥运行时通道；
重跑幂等（源目录已移除=自然零候选；版本层同名记录+源目录在场=冲突件
typed 拒不覆盖）。全程零网络零模型；只触 --catzip-root 与 --state-root
两根内（fail-closed：state_root 未配置即拒）。

用法：
  python -X utf8 implementation/python/migrate_catzip_skills.py \
      --state-root <安全层状态根> [--catzip-root <catzip 技能根>] \
      [--report <报告输出路径>] [--dry-run]

退出码：0=无失败件（含零候选）；1=存在失败件（逐件码在报告 failed[]）。
报告=JSON（默认 <state-root>/catzip-migration-report.json；干跑也落报告，
apply:false）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from skill_security import migrate_catzip_skills  # noqa: E402

DEFAULT_CATZIP_ROOT = Path(os.environ.get("APPDATA", str(
    Path.home() / "AppData" / "Roaming"))) / "Juscite" / "bridge" / "skills"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="一次性迁移：catzip 已装 user 技能 → 安全层版本层")
    parser.add_argument("--catzip-root", default=str(DEFAULT_CATZIP_ROOT),
                        help="catzip 技能根（默认 %%APPDATA%%\\Juscite\\bridge\\skills）")
    parser.add_argument("--state-root",
                        default=os.environ.get(
                            "JUSCITE_SKILL_SECURITY_STATE_ROOT", ""),
                        help="安全层状态根（必填；或环境变量 "
                             "JUSCITE_SKILL_SECURITY_STATE_ROOT）")
    parser.add_argument("--report", default="",
                        help="迁移报告 JSON 输出路径（默认 <state-root>/"
                             "catzip-migration-report.json）")
    parser.add_argument("--dry-run", action="store_true",
                        help="干跑：零写入，只出 planned 报告")
    args = parser.parse_args()
    if not args.state_root:
        print("s21_state_root_not_configured：--state-root 或 "
              "JUSCITE_SKILL_SECURITY_STATE_ROOT 必填（fail-closed）",
              file=sys.stderr)
        return 2
    config = {"skill_security_state_root": args.state_root}
    report = migrate_catzip_skills(args.catzip_root, config,
                                   apply=not args.dry_run)
    report_path = Path(args.report) if args.report else Path(
        args.state_root) / "catzip-migration-report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_bytes(json.dumps(report, ensure_ascii=False,
                                       indent=2).encode("utf-8"))
    mode = "干跑（零写入）" if report["apply"] is False else "已应用"
    print(f"[migrate-catzip] {mode}：候选根={report['catzip_root']} "
          f"（源根{'在场' if report.get('source_root_present') else '不在场=零候选'}）")
    for item in report.get("planned", []):
        print(f"[migrate-catzip] 拟迁移 {item['dir']} → "
              f"{item['package_id']}@{item['version']} "
              f"（signals={item['signals']}/enabled={item['enabled']}）")
    for item in report["migrated"]:
        print(f"[migrate-catzip] 已迁移 {item['dir']} → "
              f"{item['package_id']}@{item['version']} "
              f"（signals={item['signals']}/enabled={item['enabled']}）")
    for item in report["failed"]:
        print(f"[migrate-catzip] 失败 {item['dir']}：{item.get('code')}（源目录未动）")
    print(f"[migrate-catzip] 报告={report_path} "
          f"migrated={len(report['migrated'])} "
          f"planned={len(report.get('planned', []))} "
          f"failed={len(report['failed'])}")
    return 0 if not report["failed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
