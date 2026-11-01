---
name: 知产许可审阅
description: 律引预装技能（RE-12）：知识产权许可合同域专项——许可范围、许可费、改进成果与分许可的逐条审阅
---

# 知产许可审阅（律引预装·RE-12）

本包是合同审查家族的域专项件：在主审查技能（`contract-review`）的
四步流程与十列模板之上，就本域合同做条款清单、审查重点与法源锚的
定向补充。本技能不替代律师判断，不自动签收任何法律结论。

## 适用合同类型判定

满足任一特征即适用本包：

- 专利/商标/著作权/软件/技术秘密的使用许可安排；
- 软件授权、开源商用许可、内容版权授权；
- 许可与技术开发、转让组合的混合安排。

不匹配时改用 `contract-domain-general` 通用入口，或按主审查技能的
十大维度做通用审。

## 域核心条款清单

- 许可标的（权利种类、注册号/版本）
- 许可范围（地域、期限、方式、排他性）
- 许可费（计费基数、阶梯、逾期）
- 使用规范与标识（标注、审计）
- 改进成果与反馈（归属、回授）
- 分许可与转让（许可、限制）

## 域专项审查重点

- 许可权利种类逐项列明：复制/发行/信息网络传播/改编等不混称；
- 排他性表述与既有许可冲突核查（无登记公示渠道，标注待核）；
- 计费基数与审计权配套（无审计权的计费条款标注失衡）；
- 改进成果回授条款的双向性与对价；
- 许可终止后的库存处理与过渡使用安排。

## 域法源锚（静态引用·效力待核）

- 《民法典》技术合同章技术许可部分及《专利法》《商标法》《著作权法》许可条款；
- 以上为静态引用，现行效力核验属引证核验件，未核前标注待核。

## 域风险清单骨架

高频风险点（逐条核对，命中即入列并按四件套登记）：

- 许可范围用语含混（「相关知识产权」式兜底）；
- 权利链条断裂：许可方无权许可上游权利（权属链条标注待核）；
- 被许可产品召回/下架时的费用返还机制缺失；
- 开源组件合规义务未传导（传染性条款标注转专项）。

## 审查列模板

```lvyin-review-columns
{"columns": [{"id": "license_scope", "name": "许可范围", "prompt": "核对权利种类、地域期限方式与排他性表述", "format": "text", "version": "1", "gold": {"kind": "text"}}, {"id": "royalty", "name": "许可费", "prompt": "摘录计费基数、费率与逾期责任（整数分）", "format": "text", "version": "1", "gold": {"kind": "text"}}, {"id": "improvement", "name": "改进成果", "prompt": "核对改进与反馈的归属、回授与对价", "format": "text", "version": "1", "gold": {"kind": "text"}}, {"id": "sublicense", "name": "分许可", "prompt": "核对分许可与转让的许可条件及限制", "format": "text", "version": "1", "gold": {"kind": "text"}}], "rows": [{"id": "row-1"}]}
```

## 执行合同（F96）

```lvyin-skill-contract
{"as_of": "2026-09-30", "evidence": {"mode": "four_state"}, "sources": [], "failure": {"on_gate_fail": "named_refusal_not_pass", "on_missing_data": "named_gap_no_fabrication"}, "evals": [{"id": "ev-domiplic-batch", "kind": "review_instantiate", "matter_id": "m-f96-preset-dom-iplic", "batch_id": "brt-f96-preset-dom-iplic", "expect": {"column_ids": ["improvement", "license_scope", "royalty", "sublicense"]}}, {"id": "ev-domiplic-refusal", "kind": "refusal", "scenario": "corporate_investigation_no_data_source", "expect": {"outcome": "refused"}}]}
```

## 失败与缺口纪律

- 守门不过：具名拒（NOT_PASS），绝不以未核状态签 PASS。
- 缺数据（如登记公示信息无数据源接入）：具名缺口待核，绝不编造。
