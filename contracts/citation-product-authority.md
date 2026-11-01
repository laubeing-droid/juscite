# 引证产品权威

锁定（2026-11-01 Asia/Shanghai，工程上线优化专班）：产品引证只认轻量核 `citation_verify_lite`。

`CITATION_PRODUCT_AUTHORITY: citation_verify_lite`

## 白名单例外

产品引证 HTTP 不进 `legal_entry.py` 冻结方法白名单。路径是：

面板 → 桥 `POST /api/verify/citation`、`POST /api/verify/document`、`GET /api/verify/citation/config`、`GET /api/verify/citation/history` → `tools/bridge/citation_verify_service.mjs` 子进程 → `implementation/python/citation_verify_lite.py`

引证产品路径不经 legal_entry 白名单。架构图里「冻结白名单入口」不含引证核验；引证是桥到轻量核的直连。见 `docs/architecture.md` 与 `contracts/pin-points.json` pin 23。

同一解析器还供两条产品消费，引擎文件名同样只能是 `citation_verify_lite.py`：

- G6 法条腿：`tools/bridge/g6_connector_mcp.mjs` 调用 `citation.verify_document`
- 随包：`packages/desktop/scripts/materialize-bridge-bundle.mjs` 的 `CITATION_ENGINE_FILE`

`BRIDGE_CITATION_ENGINE` 可以改轻量核的位置，不能改权威。文件名不是 `citation_verify_lite.py` 时，解析器返回空，不回退到内置轻量核，也不去跑别的核。文件名正确但路径不存在时，仍按随包 / 开发布局查找轻量核。

## 什么不算产品权威

下面这些还在仓库里，是冻结面或侦察，不是产品引证权威。ci_gate 的引证步不会因为它们通过而变绿：

- `implementation/python/legal_entry.py` 的 `CITATION_METHODS`（`citation.parse` / `citation.verify` / `citation.verify_document`）仍分发到 `citation_verifier.citation_call`
- `implementation/python/citation_verifier.py`（F70；数据面走 E22 `statute_validity`，不是 lawbook 轻量包）
- `tools/PENDING_OWNER_f70_citation_verifier_recon.py`（手工侦察，不在 ci_gate 步骤表）
- 直接 import `citation_verifier` 的冻结模块：`extraction_gate.py`、`f88_dualset_ci.py`、`abstain_operational.py`、`tabular_review.py`、`cross_exam.py`，以及对应 recon / `implementation/tests`

同名方法不是同一个产品接口。产品客户端走桥上的 `/api/verify/*`。`legal_entry.call("citation.verify", ...)` 不是产品引证。

## 降级计划（待人拍板，本文件不改那些模块的行为）

本轮不改 `legal_entry.py` / `citation_verifier.py` 的运行行为，不删 F70 侦察脚本，也不新做第二个产品引擎。

人拍板之后再动代码，建议按这个顺序：

1. 把冻结入口上的 `citation.*` 标成非产品、仅侦察，避免和桥上的轻量方法组看起来等价。改注释、改方法前缀，还是在返回信封上加非产品标记，都会碰到现有调用方，所以先由人定手法。
2. 点名仍直接调用 `citation_verifier` 的冻结模块（上一节）。侦察可以留。不能再把它们写成产品核验权威。`legal_entry.py` 里 F88 注释写着 “never a second verification authority”，绑的是 F70 冻结核，不是产品轻量核；这句话不能用来证明产品只有一个核。
3. 不要把桥或 G6 改去启动 `citation_verifier`。不要把 F70 recon 加进 ci_gate 充当引证绿灯。
4. 验收仍是 `node tools/bridge/ci_gate.mjs citation-authority` 退出码 0。不动 `lawbook-packs`。

## 门禁

`tools/bridge/ci_gate.mjs` 的 `citation` 步（`fast` / `persist` / `full` / `upgrade`）先跑混用闸，再跑 `tools/bridge/citation_verify_synthetic.mjs`（只探针轻量核）。只复跑闸：

```
node tools/bridge/ci_gate.mjs citation-authority
```

闸会红：产品路径文件出现第二核、pin 23 丢了或不再描述这条直连、架构例外句被改回去、解析器接受非轻量核文件名、门禁自己去跑 F70 recon。
