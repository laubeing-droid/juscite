---
name: 股权投资审阅
description: 律引预装技能（RE-12）：股权转让与投资合同域专项——标的股权、估值对价、陈述保证与交割条件的逐条审阅
---

# 股权投资审阅（律引预装·RE-12）

本包是合同审查家族的域专项件：在主审查技能（`contract-review`）的
四步流程与十列模板之上，就本域合同做条款清单、审查重点与法源锚的
定向补充。本技能不替代律师判断，不自动签收任何法律结论。

## 适用合同类型判定

满足任一特征即适用本包：

- 股权/份额转让、增资认购等权益变动安排；
- 财务投资人对非上市公司的投资（含对赌安排）；
- 并购重组中以股权为标的的交易文件。

不匹配时改用 `contract-domain-general` 通用入口，或按主审查技能的
十大维度做通用审。

## 域核心条款清单

- 标的股权（比例、出资、权利负担）
- 估值与对价（定价依据、支付节奏、调价）
- 陈述与保证（主体、财务、合规、诉讼）
- 交割条件与过渡期（先决条件、期间承诺）
- 治理安排（董事席位、否决事项、退出）
- 业绩承诺与回购（触发、计算、上限）

## 域专项审查重点

- 出资瑕疵与未实缴部分的责任承担（转让人/受让人划分）；
- 业绩承诺的可计算性：触发条件、补偿公式、封顶与反稀释；
- 交割先决条件逐项可判定（审批、第三方同意、无重大不利变化）；
- 过渡期损益归属与分红的安排；
- 回购权行使期限与行权程序（过期失权的标注）。

## 域法源锚（静态引用·效力待核）

- 《公司法》及最高人民法院相关司法解释——股权转让、出资责任与公司治理等规则；
- 以上为静态引用，现行效力核验属引证核验件，未核前标注待核。

## 域风险清单骨架

高频风险点（逐条核对，命中即入列并按四件套登记）：

- 标的股权存在质押/冻结未披露（工商与协议核对）；
- 对赌义务主体与程序合法性存疑的安排（标注转专项）；
- 陈述保证无存续期与赔偿上限（风险敞口不对称）；
- 交割条件含不可判定的主观标准。

## 审查列模板

```lvyin-review-columns
{"columns": [{"id": "target_equity", "name": "标的股权", "prompt": "核对比例、出资实缴与权利负担披露", "format": "text", "version": "1", "gold": {"kind": "text"}}, {"id": "valuation", "name": "估值对价", "prompt": "摘录定价依据、对价（整数分）与支付节奏", "format": "text", "version": "1", "gold": {"kind": "text"}}, {"id": "reps", "name": "陈述保证", "prompt": "核对保证范围、存续期与赔偿上限", "format": "text", "version": "1", "gold": {"kind": "text"}}, {"id": "closing", "name": "交割条件", "prompt": "核对先决条件可判定性与过渡期安排", "format": "text", "version": "1", "gold": {"kind": "text"}}, {"id": "governance", "name": "治理安排", "prompt": "核对董事席位、否决事项与退出机制", "format": "text", "version": "1", "gold": {"kind": "text"}}], "rows": [{"id": "row-1"}]}
```

## 执行合同（F96）

```lvyin-skill-contract
{"as_of": "2026-09-30", "evidence": {"mode": "four_state"}, "sources": [], "failure": {"on_gate_fail": "named_refusal_not_pass", "on_missing_data": "named_gap_no_fabrication"}, "evals": [{"id": "ev-domequity-batch", "kind": "review_instantiate", "matter_id": "m-f96-preset-dom-equity", "batch_id": "brt-f96-preset-dom-equity", "expect": {"column_ids": ["closing", "governance", "reps", "target_equity", "valuation"]}}, {"id": "ev-domequity-refusal", "kind": "refusal", "scenario": "corporate_investigation_no_data_source", "expect": {"outcome": "refused"}}]}
```

## 失败与缺口纪律

- 守门不过：具名拒（NOT_PASS），绝不以未核状态签 PASS。
- 缺数据（如登记公示信息无数据源接入）：具名缺口待核，绝不编造。
