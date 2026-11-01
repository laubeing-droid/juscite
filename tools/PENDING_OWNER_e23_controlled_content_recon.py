# -*- coding: utf-8 -*-
"""E23 受控内容与观察闭环 B1 段 验收对账（W3-U19）。

07 E23 assertion（台账单实例行）「现有受控内容消费，不公开蒸馏；
Observer建议待用户，不自动改路由prompt/规则发布启用」＋05:238「运行时
只做既有受控消费；社区技能广场不收私域蒸馏产物。Observer只读脱敏观测
→PENDING_USER_DECISION建议→用户工程评估→owner施工→独立验证→另行决定
启用，不自动改prompt/规则/身份/路由/发布/回滚」＋裁决#7（00-总协调
§6.1#7：manuals/persona 内容包合成样本先行；Observer 不启用）。

落点：legal_entry 冻结方法组 manual.*（manual.open/search/read/version，
与 manuals 仓 legal_cn_manuals.consumer 读侧白名单一一对应——运行时只做
既有受控消费，不造第二消费者）；persona.*/observer.* 具名 not_connected。

分段：
  S0 钉定（manuals 仓 master@a93c14e 六文件 sha256，漂移即 FATAL；
     persona 仓缺省形态=README-only 如实记录）
  S1 合成受控内容消费闭环（合成包经真实信任管线五闸 preview→import 落
     临时 packs 根，产品桥 legal_entry CLI 子进程径 manual.version→open
     →search→read 全链；正文逐字节回读；两跑确定性）
  S2 不公开蒸馏（private 记录永不出走读侧白名单：search 双模式排除＋
     read 具名拒 scope_mismatch；消费面离线 AST；桥面封闭=consumer 公开
     方法恰四读；写入限于 packs 根自家交付日志）
  S3 Observer 不启用（observer.*/persona.*/manual.observe 三路具名拒；
     implementation/python 零 observer 面；裁决#7 状态入证据）
  S4 不自动改路由 prompt/规则发布启用（合成路由 prompt 配置消费前后
     字节不变；_manual_call AST 零文件写面；全部 *_METHODS 方法名无
     publish/enable/distill/observe/prompt；规则包治理组=只读三方法
     且桥无写口——F112 既有定论复验）
  S5 persona 可选件缺席形态（仓 README-only，manuals 消费闭环在 persona
     缺席下完整走通＝可选件性质行为级；B5 段如实挂 v2 波记录）
  S6 双 profile 输出一致（归一化 digest 与宿主形态无关）

用法（juscite worktree 根 cwd）：
  python -X utf8 tools/PENDING_OWNER_e23_controlled_content_recon.py \
      --profile desktop --profile selfhost

exit 0＝RECON_OK 全断言过；证据 JSON 写 evidence/E23/<profile>/ 与
docs/construction/evidence/E23/<profile>/。全合成材料（合成包正文为
标注合成的方法条目，无法条引文）；不发网络；零 %APPDATA% 触碰。
manuals 仓只读消费（钉定 checkout），零字节改动。
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LEGAL_ENTRY = REPO_ROOT / "implementation" / "python" / "legal_entry.py"
PRODUCT_PY = REPO_ROOT / "implementation" / "python"

MANUALS_REPO_DEFAULT = None  # 运行时按 jusbench工作区 兄弟目录解析
MANUALS_SHA256 = {
    "src/legal_cn_manuals/consumer.py":
        "fead81957eacc6a04d23b46c40cb0e890a4b23963b030bb1ed2501aeeb1cec6f",
    "src/legal_cn_manuals/import_service.py":
        "2d4371e9340a2b9aa62427f30cb87fbc9ca3de11ba3863a49eca97d08e292b82",
    "src/legal_cn_manuals/store.py":
        "766a2033ec6c46a090fd7b70da44b9e297d90037d80c77eff5135ecd0c9fa872",
    "src/legal_cn_manuals/trust.py":
        "e33bb1a82b64fd3d14c32d45d0cc69fa55e1027b5bd7e55b52b90ea278ad9952",
    "src/legal_cn_manuals/contracts.py":
        "3b54d258dd7b8710476f070aef70776f777c28b567941ad2e5009dcee0796067",
    "src/legal_cn_manuals/errors.py":
        "2a67f440f3e97f10aa18ac7e54cf38cc604ad3e21e7de8ed62b50c32387f6c62",
}
MANUALS_HEAD_EXPECTED = "a93c14e80146ed08042502d1d418dbc81b51b535"
MANUALS_CONTRACT = "lh-distill-ingest/1"
PERSONA_REPO_DEFAULT = None

# 合成包记录（与 manuals tests/conftest build_pack 同公式同键集；正文为
# 显式合成材料，无真实法条引文，无 quoteSpans → 引文闸不触发）。
SYN_PACK_ID = "e23-syn-controlled"
SYN_PUBLICATION = "1.0.0"
SYN_CLASSIFICATION_A = {"causeIds": ["e23_synth_cause_a"], "procedureStages": [],
                        "roles": ["case-conductor"], "topics": ["e23-synth"],
                        "methodTypes": ["internal_check"]}
SYN_CLASSIFICATION_B = {"causeIds": ["e23_synth_cause_b"], "procedureStages": [],
                        "roles": ["drafting-agent"], "topics": ["e23-synth"],
                        "methodTypes": ["external_draft"]}
SYN_RECORDS = [
    {"id": "e23-mtd-001", "kind": "method", "metaState": "active",
     "title": "合成方法条目一·合同审查步骤（工程验证用，无法律效力）",
     "body": "# 合成方法条目一（SYNTHETIC）\n\n这是受控内容消费闭环的工程"
             "合成样本：第一步核对要件清单，第二步核对签署形式。无任何真实"
             "法条引文。\n",
     "routeKeys": ["civil_commercial"], "readScope": "firm",
     "trustStatus": "verified", "lastVerified": "2026-09-01",
     "classification": SYN_CLASSIFICATION_A,
     "businessPath": "合成·合同审查"},
    {"id": "e23-mtd-002", "kind": "method", "metaState": "active",
     "title": "合成方法条目二·阅卷顺序（工程验证用，无法律效力）",
     "body": "# 合成方法条目二（SYNTHETIC）\n\n这是第二条工程合成样本：先"
             "程序材料后实体材料。无任何真实法条引文。\n",
     "routeKeys": ["criminal"], "readScope": "firm",
     "trustStatus": "verified", "lastVerified": "2026-09-01",
     "classification": SYN_CLASSIFICATION_B,
     "businessPath": "合成·阅卷"},
    {"id": "e23-mtd-003", "kind": "method", "metaState": "held",
     "title": "合成方法条目三·held 可见性（工程验证用，无法律效力）",
     "body": "# 合成方法条目三（SYNTHETIC held）\n\nheld 状态可见性工程样本。\n",
     "routeKeys": ["civil_commercial"], "readScope": "firm",
     "trustStatus": "candidate", "lastVerified": None},
    {"id": "e23-mtd-004", "kind": "knowledge_note", "metaState": "active",
     "title": "合成私有条目·private 不出读侧白名单（工程验证用）",
     "body": "# 合成私有条目（SYNTHETIC private）\n\nprivate 探针样本："
             "任何形式的检索都不应命中，读取必须具名拒。\n",
     "routeKeys": [], "readScope": "private",
     "trustStatus": "candidate", "lastVerified": None},
]

NETWORK_MODULES = {"socket", "ssl", "urllib", "urllib.request", "urllib.parse",
                   "http", "http.client", "requests", "httpx", "ftplib",
                   "smtplib", "poplib", "imaplib", "telnetlib", "xmlrpc",
                   "websocket"}
WRITE_ATTRS = {"write", "write_text", "write_bytes", "replace", "rename",
               "remove", "unlink", "rmtree", "mkdir", "makedirs", "chmod"}
BANNED_METHOD_TOKENS = ("publish", "enable", "distill", "observe", "prompt")


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


def sha256_file(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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


# ---------------------------------------------------------------- S0 pins --

def s0_pins(checks: Checks, manuals_root: Path, persona_root: Path | None):
    for rel, want in sorted(MANUALS_SHA256.items()):
        got = sha256_file(manuals_root / rel)
        checks.add("c01_manuals_pin[%s]" % Path(rel).stem, got == want,
                   "sha256 %s… %s" % (got[:12], "MATCH" if got == want
                                      else "DRIFT(want %s…)" % want[:12]))
    head = None
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=str(manuals_root),
            capture_output=True, text=True, timeout=30).stdout.strip()
    except Exception:
        head = None
    if head:
        checks.add("c01b_manuals_head", head == MANUALS_HEAD_EXPECTED,
                   "manuals HEAD %s（钉定文件为准，HEAD 为辅助记录）" % head[:12])
    entries = sorted(p.name for p in persona_root.iterdir()
                     if not p.name.startswith(".git")) \
        if persona_root else []
    readme_only = entries == ["README.md"]
    checks.add("c02_persona_repo_absence_form", readme_only,
               "persona 仓内容条目=%s（git 元数据除外；README-only＝可选件"
               "缺省形态，无内容无消费者，不造脚本）" % (entries or ["<missing>"]))


# ------------------------------------------------- synthetic pack builder --

def _canonical(record: dict) -> str:
    return json.dumps(record, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"))


def build_synthetic_pack(dest: Path) -> Path:
    """构建 lh-distill-ingest/1 合成包（公式=manuals tests/conftest 共享公
    式；错误会在信任管线五闸具名炸出，不静默）。"""
    (dest / "bodies").mkdir(parents=True, exist_ok=True)
    payload: dict[str, str] = {}
    rows = []
    for spec in SYN_RECORDS:
        body_rel = "bodies/%s.md" % spec["id"]
        body_bytes = spec["body"].encode("utf-8")
        (dest / body_rel).write_bytes(body_bytes)
        body_sha = hashlib.sha256(body_bytes).hexdigest()
        payload[body_rel] = body_sha
        row = {
            "id": spec["id"], "kind": spec["kind"],
            "metaState": spec["metaState"], "title": spec["title"],
            "bodyPath": body_rel,
            "sourceRefs": [{"sourceId": "src-e23-synth-001",
                            "originKind": "book",
                            "locator": "合成 第1-3行"}],
            "routeKeys": spec["routeKeys"], "readScope": spec["readScope"],
            "trustStatus": spec["trustStatus"],
            "lastVerified": spec["lastVerified"],
        }
        if spec.get("businessPath"):
            row["businessPath"] = spec["businessPath"]
        digest_input = {**row, "bodyDigest": body_sha}
        row["recordDigest"] = hashlib.sha256(
            _canonical(digest_input).encode("utf-8")).hexdigest()
        rows.append(row)
    records_bytes = ("\n".join(json.dumps(r, ensure_ascii=False,
                                         sort_keys=True) for r in rows)
                     + "\n").encode("utf-8")
    (dest / "records.jsonl").write_bytes(records_bytes)
    payload["records.jsonl"] = hashlib.sha256(records_bytes).hexdigest()
    src_rows = [{"sourceId": "src-e23-synth-001", "origin": "book",
                 "identity": "合成来源《E23 工程合成样本集》2026",
                 "originalAvailable": True}]
    sources_bytes = ("\n".join(json.dumps(s, ensure_ascii=False,
                                          sort_keys=True) for s in src_rows)
                     + "\n").encode("utf-8")
    (dest / "sources.jsonl").write_bytes(sources_bytes)
    payload["sources.jsonl"] = hashlib.sha256(sources_bytes).hexdigest()
    cls_rows = [{"id": s["id"], "classification": s["classification"]}
                for s in SYN_RECORDS if s.get("classification")]
    cls_bytes = ("\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True)
                           for r in cls_rows) + "\n").encode("utf-8")
    (dest / "classification.jsonl").write_bytes(cls_bytes)
    payload["classification.jsonl"] = hashlib.sha256(cls_bytes).hexdigest()
    joined = "".join("%s\n%s\n" % (rel, payload[rel])
                     for rel in sorted(payload)).encode("utf-8")
    digest = hashlib.sha256(joined).hexdigest()
    manifest = {
        "manifestVersion": MANUALS_CONTRACT, "packId": SYN_PACK_ID,
        "publicationVersion": SYN_PUBLICATION,
        "priorPublicationVersion": None, "recordCount": len(rows),
        "recordsFile": "records.jsonl", "payloadDigest": digest,
        "piiScanRef": {"owner": "manuals", "kind": "pii-scan", "id": "scan-1",
                       "version": "1", "matterId": None, "digest": digest},
        "routeKeyUsage": {},
        "authority": {"producer": "distill-books",
                      "recipeVersion": "synthetic/1"},
    }
    (dest / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=1),
        encoding="utf-8")
    (dest / "files.json").write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=1),
        encoding="utf-8")
    (dest / "pii-scan-report.json").write_text(json.dumps(
        {"tool": "synthetic-anonymizer", "toolVersion": "1.0.0",
         "ruleVersion": "synthetic-rules/1", "status": "complete",
         "expectedFiles": sorted(payload.keys()),
         "actualScannedFiles": sorted(payload.keys()),
         "payloadDigest": digest, "alertCount": 0, "alerts": []},
        ensure_ascii=False, sort_keys=True, indent=1), encoding="utf-8")
    return dest


# ----------------------------------------------------- manuals trust import --

def import_pack_via_trust_pipeline(manuals_root: Path, packs_root: Path,
                                   staging_src: Path):
    """真实信任管线落包（预览五闸→import）；packs 根=临时目录，零真实仓
    写入。返回（现行指针, import 回执）。"""
    src_dir = manuals_root / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))
    for name in [m for m in list(sys.modules)
                 if m == "legal_cn_manuals" or m.startswith("legal_cn_manuals.")]:
        del sys.modules[name]
    from legal_cn_manuals.import_service import ManualsImportService
    from legal_cn_manuals.store import PackStore
    pack_dir = build_synthetic_pack(staging_src)
    store = PackStore(str(packs_root))
    service = ManualsImportService(store)
    source_ref = {"owner": "manuals", "kind": "manual-import-source",
                  "id": "file://" + str(pack_dir), "version": "1",
                  "matterId": None, "digest": None}
    alloc_ref = {"owner": "manuals", "kind": "allocation-manifest",
                 "id": "file://" + str(pack_dir / "manifest.json"),
                 "version": "1", "matterId": None, "digest": None}
    key = {"requestId": "req-e23-preview", "targetId": None,
           "expectedRevision": None, "inputRefs": []}
    preview = service.preview_import(scope={"kind": "system"}, key=key,
                                     source_ref=source_ref,
                                     allocation_manifest_ref=alloc_ref)
    trust_ref = {"owner": "manuals", "kind": "content-trust",
                 "id": preview["trustReceipt"]["packId"] + "@"
                       + preview["trustReceipt"]["publicationVersion"],
                 "version": "1", "matterId": None,
                 "digest": preview["trustReceipt"]["payloadDigest"]}
    result = service.import_pack(
        scope={"kind": "system"},
        key={"requestId": "req-e23-import", "targetId": None,
             "expectedRevision": None, "inputRefs": []},
        preview_ref=preview["previewRef"], trust_receipt_ref=trust_ref)
    pointer = store.read_current(SYN_PACK_ID)
    snap = store.read_snapshot(SYN_PACK_ID, int(pointer["snapshotVersion"]))
    return pointer, result, snap["entries"]


# --------------------------------------------------------- product bridge --

def call_cli(method: str, args: dict, config: dict, tmp: Path):
    """真产品入口子进程径（legal_entry CLI，同 F64/F104/F112 纪律）。"""
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


def bridge_config(manuals_root: Path, packs_root: Path) -> dict:
    return {"manuals_contract": MANUALS_CONTRACT,
            "manuals_import_path": str(manuals_root / "src"),
            "manuals_packs_root": str(packs_root)}


def strip_volatile(node):
    """归一化：剥离时间戳类字段后做确定性对比（issuedAt/observed_at）。"""
    if isinstance(node, dict):
        return {k: strip_volatile(v) for k, v in sorted(node.items())
                if k not in ("issuedAt", "observed_at")}
    if isinstance(node, list):
        return [strip_volatile(v) for v in node]
    return node


def tree_snapshot(root: Path) -> dict:
    out = {}
    for path in sorted(Path(root).rglob("*")):
        if path.is_file():
            out[str(path.relative_to(root)).replace("\\", "/")] = \
                sha256_file(path)
    return out


# ------------------------------------------------------------ AST helpers --

def _method_names_from_frozenset(tree) -> dict:
    out = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name) \
                and node.targets[0].id.endswith("_METHODS"):
            names = []
            if isinstance(node.value, ast.Call):
                for elt in node.value.args:
                    if isinstance(elt, (ast.Set, ast.List, ast.Tuple)):
                        names = [e.value for e in elt.elts
                                 if isinstance(e, ast.Constant)]
            out[node.targets[0].id] = names
    return out


def _func_source_lines(source: str, func_name: str):
    tree = ast.parse(source)
    lines = source.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and node.name == func_name:
            return "\n".join(lines[node.lineno - 1:node.end_lineno])
    return None


# ------------------------------------------------------------ per profile --

def run_profile(profile: str, checks: Checks, manuals_root: Path,
                persona_root: Path | None, tmp_root: Path) -> dict:
    config = bridge_config(manuals_root, tmp_root / "packs")
    staging = tmp_root / "staging-src"
    staging.mkdir(parents=True, exist_ok=True)
    (tmp_root / "packs").mkdir(parents=True, exist_ok=True)

    # S1 合成包经真实信任管线落临时 packs 根
    pointer, import_result, entries = import_pack_via_trust_pipeline(
        manuals_root, tmp_root / "packs", staging)
    checks.add("c03_synth_pack_import_trust_pipeline[%s]" % profile,
               bool(pointer) and pointer["publicationVersion"] == SYN_PUBLICATION
               and import_result.get("replayed") is False,
               "五闸过·现行 %s@%s payload %s…（预览五闸→import 回执 "
               "replayed=false）" % (SYN_PACK_ID, SYN_PUBLICATION,
                                    str(pointer["payloadDigest"])[:12]))
    pack_ref = {"owner": "manuals", "kind": "manual-pack",
                "id": SYN_PACK_ID, "version": str(pointer["snapshotVersion"]),
                "matterId": None, "digest": pointer["payloadDigest"]}
    scope = {"kind": "system"}

    # 合成路由 prompt 配置（S4 行为级对照物；消费动作不得触碰）
    route_prompt = tmp_root / "route-prompt-config.json"
    route_prompt.write_text(json.dumps(
        {"route": "e23-synth", "prompt": "SYNTHETIC routing prompt",
         "rules_enabled": []}, ensure_ascii=False, sort_keys=True),
        encoding="utf-8")
    route_before = sha256_file(route_prompt)

    pre_tree = tree_snapshot(tmp_root / "packs")

    # S1 消费闭环：version → open → search(默认) → search(includeHeld) → read
    code, version = call_cli("manual.version", {"scope": scope,
            "pack_id": SYN_PACK_ID, "version": None}, config, tmp_root)
    manifest_digest = sha256_file(
        tmp_root / "packs" / SYN_PACK_ID / SYN_PUBLICATION / "manifest.json")
    ok_version = code == 0 and version["result"]["manifestRef"]["digest"] \
        == manifest_digest
    checks.add("c04_manual_version_via_bridge[%s]" % profile, ok_version,
               "exit %d·manifest digest %s… 与盘上逐字节一致" %
               (code, manifest_digest[:12]))

    code, opened = call_cli("manual.open", {"scope": scope,
            "pack_id": SYN_PACK_ID, "version": SYN_PUBLICATION},
            config, tmp_root)
    ok_open = code == 0 and opened["result"]["packRef"]["digest"] \
        == pointer["payloadDigest"]
    checks.add("c05_manual_open_via_bridge[%s]" % profile, ok_open,
               "exit %d·packRef digest %s… = 现行指针 payloadDigest" %
               (code, str(pointer["payloadDigest"])[:12]))

    code, search = call_cli("manual.search", {"scope": scope,
            "packRef": pack_ref, "query": "", "routeKeys":
            ["civil_commercial"], "includeHeld": False, "cursor": None,
            "filters": None}, config, tmp_root)
    hit_ids = [i["id"].split("/", 1)[1] for i in search["result"]["items"]] \
        if code == 0 else []
    checks.add("c06_manual_search_route_scope[%s]" % profile,
               code == 0 and hit_ids == ["e23-mtd-001"],
               "exit %d·civil_commercial 命中=%s（held/private 排除）" %
               (code, hit_ids))

    code, search_held = call_cli("manual.search", {"scope": scope,
            "packRef": pack_ref, "query": "合成方法条目", "routeKeys": [],
            "includeHeld": True, "cursor": None, "filters": None},
            config, tmp_root)
    held_ids = sorted(i["id"].split("/", 1)[1]
                      for i in search_held["result"]["items"]) \
        if code == 0 else []
    checks.add("c07_manual_search_include_held[%s]" % profile,
               code == 0 and held_ids ==
               ["e23-mtd-001", "e23-mtd-002", "e23-mtd-003"],
               "exit %d·includeHeld 命中=%s（private 仍排除）" %
               (code, held_ids))

    record_ref = {"owner": "manuals", "kind": "manual-record",
                  "id": "%s/e23-mtd-001" % SYN_PACK_ID,
                  "version": str(pointer["snapshotVersion"]),
                  "matterId": None,
                  "digest": entries["e23-mtd-001"]["recordDigest"]}
    code, read = call_cli("manual.read", {"scope": scope,
            "record_ref": record_ref}, config, tmp_root)
    body_ok = code == 0 and read["result"]["body"] \
        == SYN_RECORDS[0]["body"]
    trust_ok = body_ok and read["result"]["trust"]["status"] == "verified" \
        and read["result"]["trust"]["lastVerified"] == "2026-09-01"
    receipt = read["result"]["receipt"] if code == 0 else {}
    receipt_ok = body_ok and receipt.get("scope") == scope \
        and receipt.get("inputRefs") == [record_ref] \
        and receipt["outputRefs"][0]["kind"] == "manual-body"
    usage = read["result"].get("usage", {})
    checks.add("c08_manual_read_body_exact[%s]" % profile,
               body_ok and trust_ok and receipt_ok
               and usage.get("packId") == SYN_PACK_ID,
               "exit %d·正文逐字节·trust verified·回执(ref/scope/in/out)·"
               "usage 契约全过" % code)

    read_norm = sha256_text(json.dumps(strip_volatile(read),
                                       ensure_ascii=False, sort_keys=True))
    code2, read2 = call_cli("manual.read", {"scope": scope,
            "record_ref": record_ref}, config, tmp_root)
    read2_norm = sha256_text(json.dumps(strip_volatile(read2),
                                        ensure_ascii=False, sort_keys=True))
    checks.add("c09_consumption_deterministic_two_runs[%s]" % profile,
               code2 == 0 and read_norm == read2_norm,
               "两跑归一化 digest %s… 相等（剥离 issuedAt 后逐键同）" %
               read_norm[:12])

    # S2 不公开蒸馏
    private_in_hits = "e23-mtd-004" in held_ids or "e23-mtd-004" in hit_ids
    checks.add("c10_private_never_in_read_side[%s]" % profile,
               not private_in_hits,
               "private 探针记录在默认/含 held 两种检索形态均零命中")
    code_p, payload_p = call_cli("manual.read", {"scope": scope,
            "record_ref": {**record_ref, "id":
                           "%s/e23-mtd-004" % SYN_PACK_ID,
                           "digest": entries["e23-mtd-004"]["recordDigest"]}},
            config, tmp_root)
    pcode = (payload_p or {}).get("code", "")
    checks.add("c11_private_read_refused_named[%s]" % profile,
               code_p == 3 and "scope_mismatch" in pcode
               and "private" not in json.dumps(payload_p, ensure_ascii=False),
               "exit %d·具名拒 %s（错误面零内容泄漏）" % (code_p, pcode))

    offline_bad = []
    for rel in MANUALS_SHA256:
        tree = ast.parse((manuals_root / rel).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                root_mod = name.split(".")[0]
                if name in NETWORK_MODULES or root_mod in NETWORK_MODULES:
                    offline_bad.append("%s:%s" % (Path(rel).name, name))
    checks.add("c12_consumption_face_offline[%s]" % profile,
               not offline_bad,
               "六钉定模块导入闭包零网络面（%s）" %
               ("clean" if not offline_bad else offline_bad))

    sys.path.insert(0, str(manuals_root / "src"))
    for name in [m for m in list(sys.modules)
                 if m == "legal_cn_manuals" or m.startswith("legal_cn_manuals.")]:
        del sys.modules[name]
    from legal_cn_manuals.consumer import ManualsConsumer
    consumer_methods = sorted(
        name for name, member in vars(ManualsConsumer).items()
        if callable(member) and not name.startswith("_"))
    bridge_methods = sorted(m.split(".", 1)[1] for m in [
        "manual.open", "manual.read", "manual.search", "manual.version"])
    checks.add("c13_bridge_surface_closed_eq_consumer[%s]" % profile,
               consumer_methods == bridge_methods,
               "consumer 公开方法 %s == 桥冻结四读" % consumer_methods)

    post_tree = tree_snapshot(tmp_root / "packs")
    changed = sorted(k for k in set(pre_tree) | set(post_tree)
                     if pre_tree.get(k) != post_tree.get(k))
    delivery_only = changed and all(
        k.endswith("consumer/delivery_log.jsonl") for k in changed)
    body_files = [k for k in post_tree if "/bodies/" in k]
    bodies_confined = all(k.startswith(
        "%s/%s/bodies/" % (SYN_PACK_ID, SYN_PUBLICATION))
        for k in body_files)
    checks.add("c14_packs_root_write_confined[%s]" % profile,
               bool(delivery_only) and bodies_confined,
               "消费全程 packs 根变更=%s（仅 C16 读取回执追加）；正文仅存于"
               "发布目录 bodies/" % changed)

    # S3 Observer 不启用（裁决#7）
    code_o, payload_o = call_cli("observer.enable", {}, config, tmp_root)
    checks.add("c15_observer_cli_named_refusal[%s]" % profile,
               code_o == 3 and (payload_o or {}).get("code")
               == "observer_not_enabled_pending_user_decision",
               "exit %d·observer.enable → observer_not_enabled_pending_"
               "user_decision（任何配置不可启用）" % code_o)
    code_pp, payload_pp = call_cli("persona.consume", {}, config, tmp_root)
    checks.add("c16_persona_cli_named_refusal[%s]" % profile,
               code_pp == 3 and (payload_pp or {}).get("code")
               == "persona_optional_component_not_wired",
               "exit %d·persona.consume → persona_optional_component_"
               "not_wired（可选件缺席具名，不造消费者）" % code_pp)
    code_m, payload_m = call_cli("manual.observe", {}, config, tmp_root)
    checks.add("c17_manual_observe_not_in_frozen_set[%s]" % profile,
               code_m == 3 and (payload_m or {}).get("code")
               == "method_not_connected:manual.observe",
               "exit %d·manual.observe → %s（读侧四方法闭集外）" %
               (code_m, (payload_m or {}).get("code")))
    # 具名拒常量是 E23 裁定面本身（裁决#7 的产品侧落点），放行；
    # 除此之外 implementation/python 零 observer 面。
    observer_allow = {"observer_not_enabled_pending_user_decision",
                      "observer."}
    observer_hits = []
    for py in sorted(PRODUCT_PY.glob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and "observer" in node.id.lower():
                observer_hits.append(py.name + ":" + node.id)
            if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                    and "observer" in node.value.lower() \
                    and node.value not in observer_allow:
                observer_hits.append(py.name + ":str:" + node.value[:40])
    observer_hits = sorted(set(observer_hits))
    checks.add("c18_no_observer_surface_in_product[%s]" % profile,
               not observer_hits,
               "implementation/python 全目录 AST 零 observer 标识符%s" %
               ("" if not observer_hits else "（命中 %s）" % observer_hits))
    checks.add("c19_adjudication7_recorded[%s]" % profile, True,
               "裁决#7 入证据：Observer=PENDING_USER_DECISION·enabled="
               "false·来源=00-总协调.md §6.1#7（另行决定启用前不施工不启用）")

    # S4 不自动改路由 prompt/规则发布启用
    route_after = sha256_file(route_prompt)
    checks.add("c20_route_prompt_config_untouched[%s]" % profile,
               route_before == route_after,
               "合成路由 prompt 配置消费前后 sha256 %s… 不变" %
               route_before[:12])
    manual_fn = _func_source_lines(
        LEGAL_ENTRY.read_text(encoding="utf-8"), "_manual_call")
    write_hits = []
    for node in ast.walk(ast.parse(manual_fn)):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute) \
                    and node.func.attr in WRITE_ATTRS:
                write_hits.append(node.func.attr)
            if isinstance(node.func, ast.Name) and node.func.id == "open":
                write_hits.append("open()")
    checks.add("c21_manual_call_has_no_write_face[%s]" % profile,
               not write_hits,
               "_manual_call AST 零文件写调用（%s）" %
               ("clean" if not write_hits else write_hits))
    tree = ast.parse(LEGAL_ENTRY.read_text(encoding="utf-8"))
    groups = _method_names_from_frozenset(tree)
    banned = sorted(
        m for names in groups.values() for m in names
        if any(tok in m.lower() for tok in BANNED_METHOD_TOKENS))
    checks.add("c22_frozen_methods_no_publish_enable_distill_observe_prompt"
               "[%s]" % profile, not banned,
               "全部 %d 个 *_METHODS 方法名正则扫 publish/enable/distill/"
               "observe/prompt 零命中" % len(groups))
    governance = groups.get("RULE_PACK_GOVERNANCE_METHODS", [])
    source_text = LEGAL_ENTRY.read_text(encoding="utf-8")
    # 注释可跨行（「本桥无\n# 写口」，续行含「# 」前缀），归并后再查。
    no_write_port = "本桥无写口" in re.sub(r"\n# ?", "", source_text)
    checks.add("c23_rule_pack_governance_read_only[%s]" % profile,
               sorted(governance) == ["calc.rule_pack_delta",
                                      "calc.rule_pack_ledger",
                                      "calc.rule_pack_replay"]
               and no_write_port,
               "规则包治理组=只读三方法%s 且「本桥无写口」注释在源"
               "（F112 定论复验）" % sorted(governance))
    manuals_refs = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "ManualsConsumer":
            manuals_refs.append(node.lineno)
        if isinstance(node, ast.ImportFrom) and node.module \
                and node.module.startswith("legal_cn_manuals"):
            manuals_refs.append(node.lineno)
    manual_fn_node = [n for n in ast.walk(tree)
                      if isinstance(n, ast.FunctionDef)
                      and n.name == "_manual_call"]
    in_manual_call = manual_fn_node and all(
        manual_fn_node[0].lineno <= ln <= manual_fn_node[0].end_lineno
        for ln in manuals_refs)
    checks.add("c24_manuals_import_confined_to_read_bridge[%s]" % profile,
               bool(manuals_refs) and in_manual_call,
               "ManualsConsumer 引用仅存在于 _manual_call（行 %s）＝"
               "manual.* 到规则/路由面零数据通道" % manuals_refs)

    # S5 persona 缺席形态（行为级：上述全链在 persona 缺席下走通）
    checks.add("c25_persona_absence_loop_completes[%s]" % profile,
               ok_version and ok_open and body_ok,
               "persona 仓 README-only 缺席下 manuals 消费闭环完整走通"
               "（可选件性质；消费面零 persona 内容）")
    checks.add("c26_b5_hang_record[%s]" % profile, True,
               "B5 段如实挂 v2 波：真实 persona 内容消费/蒸馏商业服务/"
               "Observer 用户裁决后施工——本单不动台账行状态（主控落账）")

    return {"profile": profile,
            "synthetic_pack": {"packId": SYN_PACK_ID,
                               "publication": SYN_PUBLICATION,
                               "payloadDigest": pointer["payloadDigest"],
                               "records": [r["id"] for r in SYN_RECORDS]},
            "routePromptSha256Before": route_before,
            "routePromptSha256After": route_after,
            "versionResult": strip_volatile(version) or {}}


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
        print("RECON_FAILED pin drift / persona absence form changed — exit 2")
        return 2

    profile_results = {}
    with tempfile.TemporaryDirectory(prefix="e23-recon-") as tmp:
        tmp_root = Path(tmp)
        for profile in profiles:
            profile_results[profile] = run_profile(
                profile, checks, manuals_root, persona_root,
                tmp_root / profile)
    norm = {p: sha256_text(json.dumps(strip_volatile(
                {k: v for k, v in res.items() if k != "profile"}),
                sort_keys=True))
            for p, res in profile_results.items()}
    distinct = sorted(set(norm.values()))
    if len(profiles) > 1:
        checks.add("c27_cross_profile_normalized_digest_equal",
                   len(distinct) == 1,
                   "双 profile 归一化 digest %s（治理面与宿主形态无关）" %
                   [d[:12] for d in distinct])
    else:
        checks.add("c27_cross_profile_normalized_digest_equal", False,
                   "单 profile 跑（--profile %s）：无跨 profile 断言；"
                   "验收形态=双 profile 全跑" % profiles[0])

    verdict = "RECON_OK" if checks.all_passed else "RECON_FAILED"
    result = {
        "recon": "e23-controlled-content-b1",
        "obligation": "E23",
        "phase_note": "B1 段收口（台账单实例行）；B5 段如实挂 v2 波",
        "verdict": verdict,
        "adjudication7_observer": {
            "decision": "PENDING_USER_DECISION", "enabled": False,
            "source": "00-总协调.md §6.1 #7（Observer 不启用）"},
        "b5_pending": ["真实 persona 内容消费", "蒸馏商业服务",
                       "Observer 用户裁决后施工与启用决定"],
        "manuals_pin": {"head": MANUALS_HEAD_EXPECTED,
                        "files": MANUALS_SHA256,
                        "checkout": str(manuals_root)},
        "persona_absence": {"checkout": str(persona_root)
                            if persona_root else None,
                            "form": "README-only（可选件缺省形态）"},
        "profile_digests": norm,
        "checks": checks.items,
        "passed": checks.passed_count, "total": len(checks.items),
    }
    for base in (REPO_ROOT / "evidence" / "E23",
                 REPO_ROOT / "docs" / "construction" / "evidence" / "E23"):
        for profile in profiles:
            out_dir = base / profile
            out_dir.mkdir(parents=True, exist_ok=True)
            payload = dict(result)
            payload["profile"] = profile
            payload["profile_result"] = profile_results[profile]
            (out_dir / "e23-recon-result.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=1,
                           sort_keys=True), encoding="utf-8")
    print("%s %d/%d checks — exit %d" %
          (verdict, checks.passed_count, len(checks.items),
           0 if checks.all_passed else 1))
    return 0 if checks.all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
