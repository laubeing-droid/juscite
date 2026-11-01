"""E10 出口金丝雀校验器（律引 JusBench，单号 T06，初版：静态+文件级）。

三件事：
1. generate —— 生成含唯一金丝雀标记（JUSCITE-CANARY-<12hex>）的合成材料（假案号/假姓名/假金额），
   只写入指定目录（默认系统临时目录 %TEMP%\\juscite-e10），不进任何真实目录；
2. scan     —— 递归扫描给定目录找金丝雀标记泄漏。逐文件按字节搜索（ASCII token 在 SQLite/日志/JSON
   中均以原样字节落盘，故二进制库文件如 opencode.db 也在扫描面内；>128MB 跳过）。
   命中减去 --allow 白名单（文件或目录）后仍有剩余 => FAIL，exit 1；
3. --selftest —— 临时目录模拟"泄漏在白名单内 / 白名单外 / 无泄漏"三场景断言判定正确，exit 0。

纪律：不联网；不写 %APPDATA%；金丝雀材料只落系统临时目录或调用方显式指定的目录。
真实 OS 级负测（DNS/IP/socket、真实出口字节）属 B2，本工具不冒称。
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import secrets
import sys
import tempfile
from pathlib import Path

TOKEN_RE = re.compile(r"^JUSCITE-CANARY-[0-9a-f]{12}$")
DEFAULT_OUT = os.path.join(tempfile.gettempdir(), "juscite-e10")
MAX_SCAN_BYTES = 128 * 1024 * 1024


def new_token() -> str:
    return "JUSCITE-CANARY-" + secrets.token_hex(6)


def material_files(token: str) -> dict[str, str]:
    """合成金丝雀材料：全虚构，token 注水。案号/姓名/金额均为合成，不指向任何真实实体。"""
    case_no = f"(2026)京0105民初{token[:24]}号"
    name = "律某引"
    amount = "人民币 12345.67 元（金丝雀合成金额）"
    body = (
        f"# 律引 E10 合成金丝雀材料（全虚构，仅测试出站通道）\n\n"
        f"金丝雀标记：{token}\n\n"
        f"- 假案号：{case_no}\n"
        f"- 假当事人：{name}\n"
        f"- 假标的：{amount}\n"
        f"- 假到期日：2026-01-01（金丝雀合成日期）\n"
    )
    prompt = (
        f"请阅读以下合成材料并总结争议焦点。{token} {case_no} 当事人{name}，标的{amount}。\n"
        "本材料全部为金丝雀合成内容。\n"
    )
    mcp_payload = json.dumps(
        {
            "tool": "canary_echo",
            "token": token,
            "case_no": case_no,
            "party": name,
            "note": "E10 合成金丝雀 MCP 载荷，全虚构",
        },
        ensure_ascii=False,
        indent=2,
    )
    return {
        "material.md": body,
        "session_input.txt": prompt,
        "mcp_payload.json": mcp_payload,
    }


def cmd_generate(out_dir: str) -> int:
    token = new_token()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for filename, content in material_files(token).items():
        path = out / filename
        path.write_text(content, encoding="utf-8")
        written.append(str(path))
    manifest = {"token": token, "files": written, "out_dir": str(out)}
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False))
    return 0


def _is_allowed(hit: Path, allow: list[Path]) -> bool:
    hit = hit.resolve()
    for base in allow:
        base = base.resolve()
        if hit == base or base in hit.parents:
            return True
    return False


def cmd_scan(directory: str, token: str, allow: list[str], emit_json: bool) -> int:
    if not TOKEN_RE.match(token):
        print(f"FAIL: 非法 token 形态: {token!r}（应为 JUSCITE-CANARY-<12hex>）", file=sys.stderr)
        return 2
    root = Path(directory)
    if not root.is_dir():
        print(f"FAIL: 目录不存在: {directory}", file=sys.stderr)
        return 2
    allow_paths = [Path(a) for a in allow]
    needle = token.encode("ascii")
    hits: list[dict] = []
    skipped: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        for filename in filenames:
            path = Path(dirpath) / filename
            try:
                if path.stat().st_size > MAX_SCAN_BYTES:
                    skipped.append(str(path))
                    continue
                with open(path, "rb") as handle:
                    if needle in handle.read():
                        hits.append({"file": str(path), "allowed": _is_allowed(path, allow_paths)})
            except OSError:
                skipped.append(str(path))
    unexpected = [h for h in hits if not h["allowed"]]
    report = {
        "dir": str(root),
        "token": token,
        "hits": hits,
        "unexpected": [h["file"] for h in unexpected],
        "allowed_hits": [h["file"] for h in hits if h["allowed"]],
        "skipped": skipped,
        "verdict": "PASS" if not unexpected else "FAIL",
    }
    print(json.dumps(report, ensure_ascii=False, indent=2) if emit_json else
          f"命中 {len(hits)} 处（白名单内 {len(hits) - len(unexpected)}，白名单外 {len(unexpected)}，跳过 {len(skipped)}）\n"
          + "".join(f"  [白名单内] {h['file']}\n" for h in hits if h["allowed"])
          + "".join(f"  [白名单外] {h['file']}\n" for h in unexpected)
          + (f"判定: {report['verdict']}\n"))
    return 0 if not unexpected else 1


def selftest() -> int:
    failures: list[str] = []

    def check(label: str, ok: bool) -> None:
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
        if not ok:
            failures.append(label)

    root = Path(tempfile.mkdtemp(prefix="juscite-e10-selftest-"))
    try:
        # 场景 0：generate 落点与 token 形态
        gen_dir = root / "gen"
        rc_gen = cmd_generate(str(gen_dir))
        manifest = json.loads((gen_dir / "manifest.json").read_text(encoding="utf-8"))
        check("generate exit 0", rc_gen == 0)
        check("token 形态合法", bool(TOKEN_RE.match(manifest["token"])))
        check("材料写入指定临时目录", all(Path(f).is_file() for f in manifest["files"]))
        check("材料含假案号与假姓名", "律某引" in (gen_dir / "material.md").read_text(encoding="utf-8"))
        token = manifest["token"]

        # 场景 1：无泄漏 => exit 0
        clean = root / "clean"
        (clean / "sub").mkdir(parents=True)
        (clean / "sub" / "note.log").write_text("普通内容，无标记", encoding="utf-8")
        check("无泄漏判定 PASS(exit 0)", cmd_scan(str(clean), token, [], True) == 0)

        # 场景 2：泄漏全在白名单内 => exit 0
        allowed = root / "allowed"
        (allowed / "whitelisted").mkdir(parents=True)
        (allowed / "whitelisted" / "session.db").write_text(f"正文……{token}……", encoding="utf-8")
        (allowed / "unexpected.log").write_text("无关内容", encoding="utf-8")
        check("泄漏仅在白名单内判定 PASS(exit 0)",
              cmd_scan(str(allowed), token, [str(allowed / "whitelisted")], True) == 0)

        # 场景 3：白名单外泄漏 => exit 1
        leaked = root / "leaked"
        (leaked / "whitelisted").mkdir(parents=True)
        (leaked / "whitelisted" / "session.db").write_text(f"正文……{token}……", encoding="utf-8")
        (leaked / "stray.log").write_text(f"crash: {token}", encoding="utf-8")
        check("白名单外泄漏判定 FAIL(exit 1)",
              cmd_scan(str(leaked), token, [str(leaked / "whitelisted")], True) == 1)

        # 场景 4：泄漏文件本身整体列为白名单 => exit 0
        check("整文件白名单判定 PASS(exit 0)",
              cmd_scan(str(leaked), token, [str(leaked / "stray.log"), str(leaked / "whitelisted")], True) == 0)

        # 场景 5：非法 token => exit 2（预期的 stderr 报错就地静音，避免自证输出混淆）
        with open(os.devnull, "w") as devnull, contextlib.redirect_stderr(devnull):
            rc_invalid = cmd_scan(str(clean), "JUSCITE-CANARY-zzz", [], True)
        check("非法 token 拒绝(exit 2)", rc_invalid == 2)
    finally:
        pass  # 临时树留待系统清理，不冒删除风险

    print(f"selftest: {'PASS (exit 0)' if not failures else 'FAILED: ' + '; '.join(failures)}")
    return 0 if not failures else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="E10 出口金丝雀校验器（初版：静态+文件级）")
    parser.add_argument("--selftest", action="store_true", help="临时目录自证判定逻辑，exit 0")
    sub = parser.add_subparsers(dest="command")

    gen = sub.add_parser("generate", help="生成合成金丝雀材料（只写指定目录）")
    gen.add_argument("--out", default=DEFAULT_OUT, help=f"输出目录（默认 {DEFAULT_OUT}）")

    scan = sub.add_parser("scan", help="扫描目录找金丝雀标记泄漏")
    scan.add_argument("--dir", required=True, help="被扫描目录（如 %APPDATA%\\Juscite）")
    scan.add_argument("--token", required=True, help="generate 输出的金丝雀标记")
    scan.add_argument("--allow", action="append", default=[], help="白名单文件或目录，可重复")
    scan.add_argument("--json", action="store_true", help="JSON 输出")

    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.command == "generate":
        return cmd_generate(args.out)
    if args.command == "scan":
        return cmd_scan(args.dir, args.token, args.allow, args.json)
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
