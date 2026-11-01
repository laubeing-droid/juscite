---
name: 担保审阅
description: 律引预装技能（RE-12）：担保合同域专项——担保范围、登记公示、担保实现与保证期间的逐条审阅
---

# 担保审阅（律引预装·RE-12）

本包是合同审查家族的域专项件：在主审查技能（`contract-review`）的
四步流程与十列模板之上，就本域合同做条款清单、审查重点与法源锚的
定向补充。本技能不替代律师判断，不自动签收任何法律结论。

## 适用合同类型判定

满足任一特征即适用本包：

- 为保证债权实现而设立的抵押/质押/保证/留置安排；
- 独立保函、差额补足、流动性支持等增信文件（效力形态标注）；
- 反担保与共同担保的组合安排。

不匹配时改用 `contract-domain-general` 通用入口，或按主审查技能的
十大维度做通用审。

## 域核心条款清单

- 被担保债权（范围、最高额、期间）
- 担保物与权利（权属、价值、瑕疵）
- 登记与公示（类型、义务人、时限）
- 担保实现（条件、程序、顺位）
- 保证方式与期间（一般/连带、期间起算）
- 从属与独立条款（从属性、独立担保）

## 域专项审查重点

- 登记义务与时限：未登记的不动产抵押/动产抵押对抗问题分别标注；
- 保证方式未写明时的默认处理规则（静态规则待核）；
- 保证期间与主债务履行期限的起算咬合；
- 混合担保中债务人自物保与他人物保的实现顺序；
- 独立保函等非典型增信的效力形态单独标注转专项。

## 域法源锚（静态引用·效力待核）

- 《民法典》担保物权章（第 386 条起）＋保证合同章（第 681 条起）——担保物权设立、实现与保证期间等规则；
- 以上为静态引用，现行效力核验属引证核验件，未核前标注待核。

## 域风险清单骨架

高频风险点（逐条核对，命中即入列并按四件套登记）：

- 担保物所有权不属于担保人（处分权缺失）；
- 应登记未登记导致担保物权未设立；
- 保证期间约定为「至债务清偿完毕」（期间不明的标注）；
- 担保范围概括式表述（实现费用是否含入存争议）。

## 审查列模板

```lvyin-review-columns
{"columns": [{"id": "secured_scope", "name": "担保范围", "prompt": "核对被担保债权范围与最高额约定", "format": "text", "version": "1", "gold": {"kind": "text"}}, {"id": "registration", "name": "登记公示", "prompt": "核对登记类型、义务人与时限安排", "format": "text", "version": "1", "gold": {"kind": "text"}}, {"id": "enforcement", "name": "担保实现", "prompt": "核对实现条件、程序与顺位约定", "format": "text", "version": "1", "gold": {"kind": "text"}}, {"id": "guarantee_period", "name": "保证期间", "prompt": "核对保证方式、期间起算与从属条款", "format": "text", "version": "1", "gold": {"kind": "text"}}], "rows": [{"id": "row-1"}]}
```

## 执行合同（F96）

```lvyin-skill-contract
{"as_of": "2026-09-30", "evidence": {"mode": "four_state"}, "sources": [], "failure": {"on_gate_fail": "named_refusal_not_pass", "on_missing_data": "named_gap_no_fabrication"}, "evals": [{"id": "ev-domsecur-batch", "kind": "review_instantiate", "matter_id": "m-f96-preset-dom-secur", "batch_id": "brt-f96-preset-dom-secur", "expect": {"column_ids": ["enforcement", "guarantee_period", "registration", "secured_scope"]}}, {"id": "ev-domsecur-refusal", "kind": "refusal", "scenario": "corporate_investigation_no_data_source", "expect": {"outcome": "refused"}}]}
```

## 失败与缺口纪律

- 守门不过：具名拒（NOT_PASS），绝不以未核状态签 PASS。
- 缺数据（如登记公示信息无数据源接入）：具名缺口待核，绝不编造。
