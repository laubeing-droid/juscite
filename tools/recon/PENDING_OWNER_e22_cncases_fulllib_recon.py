# -*- coding: utf-8 -*-
"""E22 B4 段 recon：cncases 全库负测复验（工单 W4-U03，00-总协调 §6.1 裁决#8-12）。

职责（只复验已裁负测，不新造授权面）：
  ① 授权状态探测：LCCC_EXTERNAL_SOURCES_AUTHORIZED 环境变量（lccc_consumer.py
     冻结面读取的唯一授权源；缺省＝全未授权 fail-closed）。
  ② 未授权（本波默认态）→ 负测复验全套：
     - 未授权容量恒 UNKNOWN／值 None（None≠0，不造数）；
     - 即便伪造授权形态，冻结面也只回 NOT_IMPLEMENTED_PENDING_W4／None——
       实测入口属 W4 授权后工单，面内零预造端点；
     - 冻结面与本 recon 自身 AST 级零 URL 字面量、零网络/子进程导入（禁编 URL）；
     - 外部容量缺口恰 1 条（EXTERNAL_CAPACITY_UNKNOWN / cases.external.cncases）；
     - B1 基线钉定值不动（30201 文档／2062246 内容块／10342 案例／缺口 13723，
       宣传 1.4 亿不分母）；数据演进时必须重过基线工具并更新台账钉定值，
       本 recon 拒绝静默跟随。
  ③ 已授权（环境变量含 cncases）→ 真实全库范围索引容量增量实测。冻结面 v1.0
     无实测入口（NOT_IMPLEMENTED_PENDING_W4）；此时本工具响亮失败
     （b4_authorized_measurement_entry_absent，exit 1），绝不编数——真实实测
     须先落 codices 仓分支实现（该仓 pytest 门禁）＋用户授权，两前置缺一即拒。

用法（juscite worktree 根 cwd，无参）：
  python -X utf8 tools/PENDING_OWNER_e22_cncases_fulllib_recon.py
    [--codices-repo <含 lccc_consumer.py 的 codices 检出>]
    [--evidence-dir docs/construction/evidence/E22/desktop]

exit 0＝未授权负测复验全过（B4 维持具名缺口，E22 如实 IMPLEMENTING）；
exit 1＝断言失败或已授权但实测入口缺席；exit 2＝环境不完整。
只读消费；零网络；零写入正式目录。
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import os
import sys
import time

RUN_DATE = time.strftime("%Y%m%d")

# 冻结面 v1.0（codices 分支 jusbench/w2a-u12-e22-baseline，W2a-U12 冻结；
# W2a-U14 亲验工作树零改动 sha eb11ee5b…；漂移即响亮拒）
FROZEN_FACE_SHA256 = (
    "eb11ee5be548dbfed6e8b3f0052d11f28abb0cd010e1ef6236fb1e2fecf245d9"
)

# B1 基线钉定（E22 台账 + 工单 W4-U03：30201 文档/2062246 内容块/10342 案例/缺口 13723）
BASELINE_DOCS_ROWS = 30201
BASELINE_CONTENT_ROWS = 2062246
BASELINE_CASES_ROWS = 10342
BASELINE_GAP_TOTAL = 13723

NETWORK_IMPORT_TOKENS = {"urllib", "requests", "socket", "http", "subprocess", "ftplib", "telnetlib", "smtplib"}
# URL 判别式拆写（本文件自身也是被检对象，不得含完整 URL 字面量）
URL_SCHEME_PARTS = ("http", "https", "ftp", "ws", "wss", "file")
URL_SCHEME_MARK = ":" + "/" + "/"


class Checks:
    def __init__(self):
        self.items: list[dict] = []

    def add(self, check_id: str, ok: bool, detail: str) -> bool:
        self.items.append(
            {"id": check_id, "status": "PASS" if ok else "FAIL", "detail": detail}
        )
        print("[%s] %s — %s" % ("PASS" if ok else "FAIL", check_id, detail))
        return ok

    @property
    def all_passed(self) -> bool:
        return all(item["status"] == "PASS" for item in self.items)


def _find_lccc_workspace() -> str | None:
    """沿脚本祖先找 legal-cn-core-codices工作区（对主检出/工单 worktree 都成立）。"""
    current = os.path.dirname(os.path.abspath(__file__))
    for _ in range(10):
        candidate = os.path.join(current, "legal-cn-core-codices工作区")
        if os.path.isdir(candidate):
            return candidate
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent
    return None


def load_public_face(codices_repo: str):
    path = os.path.join(codices_repo, "lccc_consumer.py")
    if not os.path.isfile(path):
        raise FileNotFoundError(
            "lccc_consumer.py 不在 %s（公开面入口，随 codices 分支 "
            "jusbench/w2a-u12-e22-baseline；合并后在仓根）" % codices_repo
        )
    spec = importlib.util.spec_from_file_location("lccc_consumer", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, path


def ast_string_constants(source: str) -> list[str]:
    tree = ast.parse(source)
    values: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            values.append(node.value)
        elif isinstance(node, ast.JoinedStr):
            for value in node.values:
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    values.append(value.value)
    return values


def ast_import_roots(source: str) -> set[str]:
    tree = ast.parse(source)
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:
                roots.add(node.module.split(".")[0])
    return roots


def no_url_no_network(check_id_prefix: str, label: str, source: str, checks: Checks) -> None:
    constants = ast_string_constants(source)
    url_hits = [c for c in constants if any(part + URL_SCHEME_MARK in c.lower()
                                            for part in URL_SCHEME_PARTS)]
    checks.add(
        check_id_prefix + "_no_url_literals_ast",
        not url_hits,
        "%s AST 字符串常量 %d 个，含 URL 字面量 %d 个（禁编 URL）"
        % (label, len(constants), len(url_hits)),
    )
    imports = ast_import_roots(source)
    net_hits = sorted(imports & NETWORK_IMPORT_TOKENS)
    checks.add(
        check_id_prefix + "_no_network_imports_ast",
        not net_hits,
        "%s 导入根 %s；网络/子进程 token %s"
        % (label, sorted(imports), net_hits or "无"),
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    workspace = _find_lccc_workspace()
    if workspace is None:
        print("FAIL: 未在祖先目录找到 legal-cn-core-codices工作区")
        return 2
    default_root = os.path.join(workspace, "legal-cn-core-codices")
    parser.add_argument("--formal-root", default=default_root,
                        help="codices 正式发布目录（默认 %s）" % default_root)
    parser.add_argument("--codices-repo", default=None,
                        help="含 lccc_consumer.py 的 codices 检出（默认先试主检出再试 w2a-u12-e22 worktree）")
    parser.add_argument("--evidence-dir", default=None,
                        help="证据输出目录（默认 docs/construction/evidence/E22/desktop）")
    args = parser.parse_args(argv)

    repo_root = os.path.normpath(os.path.join(
        os.path.dirname(os.path.abspath(__file__)), ".."))
    candidates = [args.codices_repo] if args.codices_repo else [
        os.path.join(workspace, "legal-cn-core-codices-repo"),
        os.path.join(workspace, "legal-cn-core-codices-repo",
                     ".local", "worktrees", "w2a-u12-e22"),
    ]
    face_path = None
    for candidate in candidates:
        if candidate and os.path.isfile(os.path.join(candidate, "lccc_consumer.py")):
            face_path = os.path.join(candidate, "lccc_consumer.py")
            break
    if face_path is None:
        print("FAIL: 未找到 lccc_consumer.py（公开面入口）——检查 codices 分支检出")
        return 2
    evidence_dir = args.evidence_dir or os.path.join(
        repo_root, "docs", "construction", "evidence", "E22", "desktop")

    lccc, _ = load_public_face(os.path.dirname(face_path))
    consumer = lccc.LcccConsumer(args.formal_root)

    print("E22 B4 cncases 全库 recon（裁决#8-12 负测先行） formal=%s entry=%s"
          % (args.formal_root, face_path))
    checks = Checks()

    with open(face_path, "r", encoding="utf-8") as handle:
        face_source = handle.read()
    with open(os.path.abspath(__file__), "r", encoding="utf-8") as handle:
        recon_source = handle.read()

    # 0) 冻结面完整性：sha256 漂移即拒（不经授权面改动静默放行）
    face_sha = hashlib.sha256(face_source.encode("utf-8")).hexdigest()
    checks.add(
        "N0_face_frozen_sha256",
        face_sha == FROZEN_FACE_SHA256,
        "lccc_consumer.py sha256=%s（钉定 %s…）"
        % (face_sha, FROZEN_FACE_SHA256[:16]),
    )

    # 1) 授权状态探测（唯一授权源＝冻结面读取的环境变量；缺省 fail-closed）
    env_raw = os.environ.get("LCCC_EXTERNAL_SOURCES_AUTHORIZED")
    authorized_sources = {s.strip() for s in (env_raw or "").split(";") if s.strip()}
    authorized = "cncases" in authorized_sources
    print("授权探测：LCCC_EXTERNAL_SOURCES_AUTHORIZED=%r → cncases 授权=%s"
          % (env_raw, authorized))

    # 2) 未授权形态实测（无论当前授权态，先还原未授权环境复验负测）
    saved = env_raw
    os.environ.pop("LCCC_EXTERNAL_SOURCES_AUTHORIZED", None)
    try:
        cap_unauth = consumer.cases_external_capacity()
        checks.add(
            "N1_unauthorized_unknown_none_not_zero",
            cap_unauth["status"] == "UNKNOWN"
            and cap_unauth["value"] is None
            and cap_unauth["reason"] == "external_source_not_authorized",
            "未授权 → status=%s value=%r reason=%s（None≠0，不造数）"
            % (cap_unauth["status"], cap_unauth["value"], cap_unauth["reason"]),
        )
        os.environ["LCCC_EXTERNAL_SOURCES_AUTHORIZED"] = "cncases"
        cap_auth = consumer.cases_external_capacity()
        checks.add(
            "N2_authorized_no_fabricated_number",
            cap_auth["value"] is None
            and cap_auth["status"] == "NOT_IMPLEMENTED_PENDING_W4"
            and cap_auth["reason"] == "authorized_but_measurement_pending_w4",
            "授权形态 → status=%s value=%r（实测入口属 W4 授权后工单，零预造端点）"
            % (cap_auth["status"], cap_auth["value"]),
        )
    finally:
        if saved is None:
            os.environ.pop("LCCC_EXTERNAL_SOURCES_AUTHORIZED", None)
        else:
            os.environ["LCCC_EXTERNAL_SOURCES_AUTHORIZED"] = saved

    # 3) 禁编 URL／零网络（AST 级，面与本工具双双自检）
    no_url_no_network("N3", "冻结面 lccc_consumer.py", face_source, checks)
    no_url_no_network("N4", "本 recon 工具", recon_source, checks)

    # 4) 外部容量缺口恰 1 条（未知保缺口，不给 0 不编数）
    gaps = consumer.unknown_gaps(run_date=RUN_DATE)
    ext = [g for g in gaps if g["gap_kind"] == "EXTERNAL_CAPACITY_UNKNOWN"]
    checks.add(
        "N5_external_capacity_gap_single",
        len(ext) == 1
        and ext[0]["identifier"] == "cases.external.cncases"
        and bool(ext[0]["reason"]),
        "EXTERNAL_CAPACITY_UNKNOWN 恰 %d 条（identifier=%s）"
        % (len(ext), ext[0]["identifier"] if ext else "缺失"),
    )

    # 5) B1 基线钉定不动（拒绝静默跟随数据演进）
    inventory = consumer.baseline_inventory()
    docs_rows = inventory["documents"]["rows"]
    content_rows = inventory["contents"]["rows"]
    cases_rows = inventory["cases"]["rows"]
    gap_total = len(gaps)
    checks.add(
        "N6_baseline_pinned_unchanged",
        docs_rows == BASELINE_DOCS_ROWS
        and content_rows == BASELINE_CONTENT_ROWS
        and cases_rows == BASELINE_CASES_ROWS
        and gap_total == BASELINE_GAP_TOTAL,
        "基线钉定：文档 %d/%d 内容块 %d/%d 案例 %d/%d 缺口 %d/%d"
        % (docs_rows, BASELINE_DOCS_ROWS, content_rows, BASELINE_CONTENT_ROWS,
           cases_rows, BASELINE_CASES_ROWS, gap_total, BASELINE_GAP_TOTAL),
    )

    verdict = {
        "run_date": RUN_DATE,
        "formal_root": args.formal_root,
        "public_entry_path": face_path,
        "face_sha256": face_sha,
        "command": "python -X utf8 tools/PENDING_OWNER_e22_cncases_fulllib_recon.py",
        "authorization_probe": {
            "env_var": "LCCC_EXTERNAL_SOURCES_AUTHORIZED",
            "env_value_present": env_raw is not None,
            "cncases_authorized": authorized,
            "note": "授权唯一落点＝该环境变量（冻结面读取）；缺省全未授权 fail-closed",
        },
        "mode": "authorized_fulllib_measurement" if authorized
                else "unauthorized_negative_recheck",
        "inventory_pin": {
            "documents_rows": docs_rows,
            "contents_rows": content_rows,
            "cases_rows": cases_rows,
            "gap_total": gap_total,
        },
        "checks": checks.items,
        "passed": sum(1 for c in checks.items if c["status"] == "PASS"),
        "total": len(checks.items),
        "overall": "PASS" if checks.all_passed else "FAIL",
    }

    if authorized:
        # 已授权态：冻结面 v1.0 无实测入口——绝不编数，响亮失败等待 codices 侧实现
        verdict["b4_authorized_measurement_entry_absent"] = (
            "冻结面 cases_external_capacity 授权态=NOT_IMPLEMENTED_PENDING_W4："
            "真实全库范围索引容量增量实测须先落 codices 仓分支实现（过该仓 pytest "
            "门禁）＋用户授权两前置；本工具不编数，exit 1 fail-closed"
        )
        outcome_ok = False
    else:
        outcome_ok = checks.all_passed

    os.makedirs(evidence_dir, exist_ok=True)
    evidence_path = os.path.join(evidence_dir, "e22-cncases-fulllib-recon.json")
    with open(evidence_path, "w", encoding="utf-8") as handle:
        json.dump(verdict, handle, ensure_ascii=False, indent=1)

    print("证据 → %s；mode=%s overall=%s（%d/%d）"
          % (evidence_path, verdict["mode"], verdict["overall"],
             verdict["passed"], verdict["total"]))
    if authorized:
        print("FAIL: cncases 已授权但冻结面无实测入口（b4_authorized_measurement_entry_absent）"
              "——不编数；须 codices 仓分支实现＋真实授权后补实测")
        return 1
    return 0 if outcome_ok else 1


if __name__ == "__main__":
    sys.exit(main())
