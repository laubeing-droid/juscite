#!/usr/bin/env python3
"""律引桌面壳真机试跑（M3 壳施工交付，v4 §1.3 换宿主后产物模式）。

用法（worktree 根或任意目录均可）：
    python scripts/launch_desktop_trial.py

做三件事：
  1. 校验 desktop 构建产物与本地 Electron 二进制在位（缺则给出构建命令退出）；
  2. 只读探测 oc28 serve 注册文件（%APPDATA%\\Juscite\\state\\opencode\\service-local.json），
     打印提示；不自动拉起 oc28（留用户裁决）；
  3. 以 packages/desktop 为 cwd 拉起 Electron，产物模式（清掉 ELECTRON_RENDERER_URL，
     main 进程 loadFile out/renderer/index.html；桥进程由 desktopHostProcess 自行 spawn）。

为何不用 Git Bash 直启 electron：中文路径 cwd 下 Git Bash 派生进程有乱码/参数错位坑
（工作区 AGENTS.md 环境节），Python subprocess 走 CreateProcessW 全程 Unicode。
红线：本脚本对 %APPDATA% 只读（Juscite 注册文件），绝不触碰 %APPDATA%\\JusBench。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DESKTOP_DIR = REPO_ROOT / "packages" / "desktop"
ELECTRON_EXE = DESKTOP_DIR / "node_modules" / "electron" / "dist" / "electron.exe"
REQUIRED_ARTIFACTS = [
    DESKTOP_DIR / "out" / "main" / "index.js",
    DESKTOP_DIR / "out" / "renderer" / "index.html",
    DESKTOP_DIR / "out" / "preload" / "index.cjs",
]
OC28_REGISTRATION = (
    Path(os.environ.get("APPDATA", "")) / "Juscite" / "state" / "opencode" / "service-local.json"
)


def main() -> int:
    if not ELECTRON_EXE.exists():
        print(f"[launch] 找不到本地 Electron 二进制：{ELECTRON_EXE}")
        print("先在 worktree 根执行：pnpm install")
        return 1
    missing = [str(p.relative_to(REPO_ROOT)) for p in REQUIRED_ARTIFACTS if not p.exists()]
    if missing:
        print("[launch] desktop 构建产物缺失：")
        for item in missing:
            print(f"  - {item}")
        print("先在 worktree 根执行：pnpm --filter @zcode/desktop build")
        return 1

    if OC28_REGISTRATION.exists():
        try:
            reg = json.loads(OC28_REGISTRATION.read_text(encoding="utf-8"))
            print(f"[launch] oc28 注册文件在位：{reg.get('url', '(url 缺失)')}")
        except (OSError, ValueError):
            print("[launch] oc28 注册文件存在但不可解析；桌面壳会自行探测并提示。")
    else:
        print(
            f"[launch] oc28 未注册（{OC28_REGISTRATION}）；"
            "对话功能将 fail-closed，需手动启动 oc28 serve。"
        )

    env = {
        key: value
        for key, value in os.environ.items()
        if key not in ("ELECTRON_RUN_AS_NODE", "ELECTRON_RENDERER_URL")
    }
    port = env.get("JUSCITE_BRIDGE_PORT", "3030")
    print(f"[launch] 拉起 Electron（bridge ws://127.0.0.1:{port}/ws，产物模式 out/renderer）…")
    completed = subprocess.run([str(ELECTRON_EXE), "."], cwd=str(DESKTOP_DIR), env=env)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
