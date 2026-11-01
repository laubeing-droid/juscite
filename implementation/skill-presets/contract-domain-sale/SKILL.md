---
name: 买卖交易审阅
description: 律引预装技能（RE-12）：买卖合同域专项——交付验收、所有权与风险转移、质量检验与价款支付的逐条审阅
---

# 买卖交易审阅（律引预装·RE-12）

本包是合同审查家族的域专项件：在主审查技能（`contract-review`）的
四步流程与十列模板之上，就本域合同做条款清单、审查重点与法源锚的
定向补充。本技能不替代律师判断，不自动签收任何法律结论。

## 适用合同类型判定

满足任一特征即适用本包：

- 一方转移标的物所有权、另一方支付价款的典型买卖安排；
- 供货/采购/销售类合同（含分批供货框架协议）；
- 以物抵债、互易等以所有权移转为目的的准买卖交易。

不匹配时改用 `contract-domain-general` 通用入口，或按主审查技能的
十大维度做通用审。

## 域核心条款清单

- 标的与质量（名称、型号、标准、检验期）
- 交付（地点、方式、运费、签收）
- 所有权与风险转移（时点、保留条款）
- 价款与支付（数额、节点、逾期利息）
- 瑕疵担保与退换（异议期、方式、费用）
- 违约责任（迟延/拒收/质量不符）

## 域专项审查重点

- 检验期与异议期是否过短或缺失——逾期未异议视为合格的约定要显著提示；
- 风险转移时点与交付方式是否咬合（需运输的货交承运人时点）；
- 所有权保留条款与抵押/质押等担保安排是否冲突；
- 质量标准须可检可验：无标准的写明按何种国家/行业标准。

## 域法源锚（静态引用·效力待核）

- 《民法典》合同编买卖合同章（第 595 条起）——标的物交付、风险负担、检验期限、所有权保留等规则；
- 以上为静态引用，现行效力核验属引证核验件，未核前标注待核。

## 域风险清单骨架

高频风险点（逐条核对，命中即入列并按四件套登记）：

- 质量标准缺失或仅有「合格」字样无可检标准；
- 异议期极短（如到货 3 日）而质量问题潜伏期长；
- 验收合格与付款节点脱钩，付款先于检验完成；
- 运费与毁损灭失风险负担未约定或互相矛盾。

## 审查列模板

```lvyin-review-columns
{"columns": [{"id": "delivery", "name": "交付验收", "prompt": "核对交付地点方式、签收与检验异议期安排", "format": "text", "version": "1", "gold": {"kind": "text"}}, {"id": "risk_transfer", "name": "风险转移", "prompt": "核对毁损灭失风险转移时点与交付方式是否咬合", "format": "text", "version": "1", "gold": {"kind": "text"}}, {"id": "quality", "name": "质量检验", "prompt": "核对质量标准、检验方法与退换货路径", "format": "text", "version": "1", "gold": {"kind": "text"}}, {"id": "payment", "name": "价款支付", "prompt": "摘录价款（整数分）、支付节点与逾期后果", "format": "text", "version": "1", "gold": {"kind": "text"}}, {"id": "breach", "name": "违约责任", "prompt": "核对迟延/拒收/质量不符的责任与计算方式", "format": "text", "version": "1", "gold": {"kind": "text"}}], "rows": [{"id": "row-1"}]}
```

## 执行合同（F96）

```lvyin-skill-contract
{"as_of": "2026-09-30", "evidence": {"mode": "four_state"}, "sources": [], "failure": {"on_gate_fail": "named_refusal_not_pass", "on_missing_data": "named_gap_no_fabrication"}, "evals": [{"id": "ev-domsale-batch", "kind": "review_instantiate", "matter_id": "m-f96-preset-dom-sale", "batch_id": "brt-f96-preset-dom-sale", "expect": {"column_ids": ["breach", "delivery", "payment", "quality", "risk_transfer"]}}, {"id": "ev-domsale-refusal", "kind": "refusal", "scenario": "corporate_investigation_no_data_source", "expect": {"outcome": "refused"}}]}
```

## 失败与缺口纪律

- 守门不过：具名拒（NOT_PASS），绝不以未核状态签 PASS。
- 缺数据（如登记公示信息无数据源接入）：具名缺口待核，绝不编造。
