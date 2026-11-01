---
name: 劳动用工审阅
description: 律引预装技能（RE-12）：劳动合同域专项——合同期限、岗位报酬、社保与离职竞业的逐条审阅
---

# 劳动用工审阅（律引预装·RE-12）

本包是合同审查家族的域专项件：在主审查技能（`contract-review`）的
四步流程与十列模板之上，就本域合同做条款清单、审查重点与法源锚的
定向补充。本技能不替代律师判断，不自动签收任何法律结论。

## 适用合同类型判定

满足任一特征即适用本包：

- 建立劳动关系、明确双方权利义务的劳动合同；
- 试用期、服务期、竞业限制等附属协议；
- 劳务派遣、非全日制等特殊用工形态的类劳动合同。

不匹配时改用 `contract-domain-general` 通用入口，或按主审查技能的
十大维度做通用审。

## 域核心条款清单

- 合同期限与试用期（期限匹配、次数）
- 工作内容与地点（岗位、调整权）
- 劳动报酬（构成、发放日、加班基数）
- 工作时间与休假（工时制、假期）
- 社保与福利（险种、基数、补充福利）
- 离职与竞业（预告期、限制范围补偿）

## 域专项审查重点

- 试用期与合同期限的法定匹配关系及次数限制（静态规则待核）；
- 加班费计算基数与工资构成的对应关系；
- 调岗调薪条款的合理性边界（单方调整权须有限度）；
- 竞业限制的人员范围、期限、地域与经济补偿缺一即标注；
- 规章制度衔接条款（以何版本、如何公示）单独成项。

## 域法源锚（静态引用·效力待核）

- 《劳动合同法》（2012 修正）——订立、试用期、报酬、解除与经济补偿、竞业限制等规则；
- 以上为静态引用，现行效力核验属引证核验件，未核前标注待核。

## 域风险清单骨架

高频风险点（逐条核对，命中即入列并按四件套登记）：

- 试用期超出法定匹配期限或重复约定；
- 押金/证件扣押等违法条款；
- 竞业限制无补偿约定或范围过宽；
- 社保缴纳基数与实际工资不符（合规风险标注）。

## 审查列模板

```lvyin-review-columns
{"columns": [{"id": "term", "name": "合同期限", "prompt": "核对期限类型、试用期匹配与续订安排", "format": "text", "version": "1", "gold": {"kind": "text"}}, {"id": "duties", "name": "岗位职责", "prompt": "核对岗位、地点与调整机制边界", "format": "text", "version": "1", "gold": {"kind": "text"}}, {"id": "pay", "name": "劳动报酬", "prompt": "摘录工资构成（整数分）、发放日与加班基数", "format": "text", "version": "1", "gold": {"kind": "text"}}, {"id": "social", "name": "社保福利", "prompt": "核对险种基数与补充福利安排", "format": "text", "version": "1", "gold": {"kind": "text"}}, {"id": "exit", "name": "离职竞业", "prompt": "核对预告期、竞业范围期限与补偿约定", "format": "text", "version": "1", "gold": {"kind": "text"}}], "rows": [{"id": "row-1"}]}
```

## 执行合同（F96）

```lvyin-skill-contract
{"as_of": "2026-09-30", "evidence": {"mode": "four_state"}, "sources": [], "failure": {"on_gate_fail": "named_refusal_not_pass", "on_missing_data": "named_gap_no_fabrication"}, "evals": [{"id": "ev-domlabor-batch", "kind": "review_instantiate", "matter_id": "m-f96-preset-dom-labor", "batch_id": "brt-f96-preset-dom-labor", "expect": {"column_ids": ["duties", "exit", "pay", "social", "term"]}}, {"id": "ev-domlabor-refusal", "kind": "refusal", "scenario": "corporate_investigation_no_data_source", "expect": {"outcome": "refused"}}]}
```

## 失败与缺口纪律

- 守门不过：具名拒（NOT_PASS），绝不以未核状态签 PASS。
- 缺数据（如登记公示信息无数据源接入）：具名缺口待核，绝不编造。
