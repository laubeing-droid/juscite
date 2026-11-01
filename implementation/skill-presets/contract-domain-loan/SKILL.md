---
name: 借贷审阅
description: 律引预装技能（RE-12）：借款合同域专项——本金利率、利息计算、担保安排与逾期处置的逐条审阅
---

# 借贷审阅（律引预装·RE-12）

本包是合同审查家族的域专项件：在主审查技能（`contract-review`）的
四步流程与十列模板之上，就本域合同做条款清单、审查重点与法源锚的
定向补充。本技能不替代律师判断，不自动签收任何法律结论。

## 适用合同类型判定

满足任一特征即适用本包：

- 借款人到期返还本金并支付利息的借贷安排；
- 企业间资金拆借、民间借贷（含借据补充协议）；
- 展期、借新还旧等存量债务重组安排。

不匹配时改用 `contract-domain-general` 通用入口，或按主审查技能的
十大维度做通用审。

## 域核心条款清单

- 本金与交付（数额、支付凭证、砍头息）
- 利率与利息（标准、计算方式、起止日）
- 期限与还款（分期表、提前还款、展期）
- 担保安排（人保/物保、登记、实现顺序）
- 逾期处置（违约金、复利、加速到期）

## 域专项审查重点

- 利率标准与计息方式必须可复算：利率上限随监管口径变动，静态引用一律待核；
- 砍头息形态（预扣利息、保证金抵扣本金）逐项识别；
- 物保与人保并存时的实现顺序约定；
- 逾期违约金与利息合计是否显著过高（与裁判尺度提示同构，标注倾向）；
- 还款冲抵顺序（本金/利息/费用）未约定的标注。

## 域法源锚（静态引用·效力待核）

- 《民法典》借款合同章（第 667 条起）——利息不得预先扣除、借款期限与逾期利息等规则；
- 以上为静态引用，利率上限等监管口径现行效力核验属引证核验件，未核前标注待核。

## 域风险清单骨架

高频风险点（逐条核对，命中即入列并按四件套登记）：

- 利息预先在本金中扣除（以扣除后实付为本金）；
- 利率约定超越当期保护上限且无调整机制；
- 担保未办理登记导致物权未设立；
- 加速到期条件不可判定（如「经营恶化」无量化标准）。

## 审查列模板

```lvyin-review-columns
{"columns": [{"id": "principal", "name": "本金交付", "prompt": "核对本金数额（整数分）、交付凭证与砍头息形态", "format": "text", "version": "1", "gold": {"kind": "text"}}, {"id": "interest", "name": "利息计算", "prompt": "摘录利率标准、计息方式与起止日，标注可复算性", "format": "text", "version": "1", "gold": {"kind": "text"}}, {"id": "security", "name": "担保安排", "prompt": "核对人保/物保、登记状态与实现顺序", "format": "text", "version": "1", "gold": {"kind": "text"}}, {"id": "default", "name": "逾期处置", "prompt": "核对违约金、加速到期条件与冲抵顺序", "format": "text", "version": "1", "gold": {"kind": "text"}}], "rows": [{"id": "row-1"}]}
```

## 执行合同（F96）

```lvyin-skill-contract
{"as_of": "2026-09-30", "evidence": {"mode": "four_state"}, "sources": [], "failure": {"on_gate_fail": "named_refusal_not_pass", "on_missing_data": "named_gap_no_fabrication"}, "evals": [{"id": "ev-domloan-batch", "kind": "review_instantiate", "matter_id": "m-f96-preset-dom-loan", "batch_id": "brt-f96-preset-dom-loan", "expect": {"column_ids": ["default", "interest", "principal", "security"]}}, {"id": "ev-domloan-refusal", "kind": "refusal", "scenario": "corporate_investigation_no_data_source", "expect": {"outcome": "refused"}}]}
```

## 失败与缺口纪律

- 守门不过：具名拒（NOT_PASS），绝不以未核状态签 PASS。
- 缺数据（如登记公示信息无数据源接入）：具名缺口待核，绝不编造。
