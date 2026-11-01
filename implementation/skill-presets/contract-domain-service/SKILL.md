---
name: 服务交易审阅
description: 律引预装技能（RE-12）：服务类合同域专项——服务范围、验收标准、服务费用与成果权属的逐条审阅
---

# 服务交易审阅（律引预装·RE-12）

本包是合同审查家族的域专项件：在主审查技能（`contract-review`）的
四步流程与十列模板之上，就本域合同做条款清单、审查重点与法源锚的
定向补充。本技能不替代律师判断，不自动签收任何法律结论。

## 适用合同类型判定

满足任一特征即适用本包：

- 一方以技能/劳务完成事项、交付成果或提供服务的合同；
- 咨询、代理、维护、外包等持续性服务安排；
- 承揽、委托等以工作成果或事务处理为内容的类服务合同。

不匹配时改用 `contract-domain-general` 通用入口，或按主审查技能的
十大维度做通用审。

## 域核心条款清单

- 服务范围（事项清单、边界、排除项）
- 履行方式与人员（地点、驻场、转包）
- 验收（标准、程序、期限、视为验收）
- 费用与结算（数额、里程碑、发票）
- 成果权属与资料返还
- 变更与终止（范围变更、单方解除）

## 域专项审查重点

- 服务范围边界是否可判定：用「等相关服务」式兜底的标注待明确；
- 验收标准与费用节点是否咬合（先验后付/里程碑比例）；
- 「视为验收」条款的触发条件与合理期限；
- 服务过程中产生成果的权属与既有知识产权的归属分列；
- 单方解除权的补偿计算方式。

## 域法源锚（静态引用·效力待核）

- 按服务性质择近适用：《民法典》承揽合同章（第 770 条起）或委托合同章（第 919 条起）；
- 以上为静态引用，现行效力核验属引证核验件，未核前标注待核。

## 域风险清单骨架

高频风险点（逐条核对，命中即入列并按四件套登记）：

- 验收标准缺失或不可测（主观满意式表述）；
- 服务范围兜底式表述导致范围争议；
- 费用与服务成果脱钩，全款先付无节点；
- 转包/分包未经同意的责任安排缺失。

## 审查列模板

```lvyin-review-columns
{"columns": [{"id": "scope", "name": "服务范围", "prompt": "核对事项清单、边界与排除项是否可判定", "format": "text", "version": "1", "gold": {"kind": "text"}}, {"id": "acceptance", "name": "验收标准", "prompt": "核对验收标准、程序期限与视为验收条件", "format": "text", "version": "1", "gold": {"kind": "text"}}, {"id": "fee", "name": "服务费用", "prompt": "摘录费用（整数分）、里程碑节点与发票安排", "format": "text", "version": "1", "gold": {"kind": "text"}}, {"id": "ownership", "name": "成果权属", "prompt": "核对服务成果与背景知识产权的归属", "format": "text", "version": "1", "gold": {"kind": "text"}}], "rows": [{"id": "row-1"}]}
```

## 执行合同（F96）

```lvyin-skill-contract
{"as_of": "2026-09-30", "evidence": {"mode": "four_state"}, "sources": [], "failure": {"on_gate_fail": "named_refusal_not_pass", "on_missing_data": "named_gap_no_fabrication"}, "evals": [{"id": "ev-domservice-batch", "kind": "review_instantiate", "matter_id": "m-f96-preset-dom-service", "batch_id": "brt-f96-preset-dom-service", "expect": {"column_ids": ["acceptance", "fee", "ownership", "scope"]}}, {"id": "ev-domservice-refusal", "kind": "refusal", "scenario": "corporate_investigation_no_data_source", "expect": {"outcome": "refused"}}]}
```

## 失败与缺口纪律

- 守门不过：具名拒（NOT_PASS），绝不以未核状态签 PASS。
- 缺数据（如登记公示信息无数据源接入）：具名缺口待核，绝不编造。
