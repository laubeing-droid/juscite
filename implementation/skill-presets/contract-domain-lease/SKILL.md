---
name: 租赁专项审阅
description: 律引预装技能（RE-12）：租赁合同域专项——租赁物交付、租金押金、维修责任与提前解约的逐条审阅
---

# 租赁专项审阅（律引预装·RE-12）

本包是合同审查家族的域专项件：在主审查技能（`contract-review`）的
四步流程与十列模板之上，就本域合同做条款清单、审查重点与法源锚的
定向补充。本技能不替代律师判断，不自动签收任何法律结论。

## 适用合同类型判定

满足任一特征即适用本包：

- 出租人交付租赁物供承租人使用收益、按期收租的安排；
- 房屋/场地/设备租赁（含转租许可条款）；
- 车位、广告位等以使用收益为内容的租赁型协议。

不匹配时改用 `contract-domain-general` 通用入口，或按主审查技能的
十大维度做通用审。

## 域核心条款清单

- 租赁物状况（现状、清单、附属设施）
- 租期与续租（起止、续签、优先承租）
- 租金与押金（数额、调整机制、押金返还条件）
- 使用与维修（用途限制、维修义务划分）
- 转租与改建（许可、责任承担）
- 提前解约与腾退（条件、通知、交接）

## 域专项审查重点

- 押金返还条件是否明确——「无违约」式概括条件易生争议，逐项列明扣减情形；
- 维修义务划分与费用承担是否对称（自然损耗与人为损坏分列）；
- 租金调整机制（递增率、市场比价）与调整触发条件是否可执行；
- 装修与添附的归属和补偿在解约时如何处理，未约定的标注待补。

## 域法源锚（静态引用·效力待核）

- 《民法典》租赁合同章（第 703 条起）——租期上限、维修义务、转租、买卖不破租赁、优先购买等规则；
- 以上为静态引用，现行效力核验属引证核验件，未核前标注待核。

## 域风险清单骨架

高频风险点（逐条核对，命中即入列并按四件套登记）：

- 租期超过法定上限的约定（超出部分效力存疑）；
- 押金扣减条件概括化，返还争议高发；
- 单方任意解除权仅授予一方且无对价；
- 腾退与物品留存处置程序缺失。

## 审查列模板

```lvyin-review-columns
{"columns": [{"id": "premises", "name": "租赁物交付", "prompt": "核对交付现状清单与附属设施记录", "format": "text", "version": "1", "gold": {"kind": "text"}}, {"id": "rent_deposit", "name": "租金押金", "prompt": "摘录租金（整数分）、调整机制与押金返还条件", "format": "text", "version": "1", "gold": {"kind": "text"}}, {"id": "maintenance", "name": "维修责任", "prompt": "核对自然损耗与人为损坏的义务划分与费用承担", "format": "text", "version": "1", "gold": {"kind": "text"}}, {"id": "early_end", "name": "提前解约", "prompt": "核对解除条件、通知期与腾退交接程序", "format": "text", "version": "1", "gold": {"kind": "text"}}, {"id": "deposit_refund", "name": "押金返还", "prompt": "核对返还时限、扣减情形清单与争议处理", "format": "text", "version": "1", "gold": {"kind": "text"}}], "rows": [{"id": "row-1"}]}
```

## 执行合同（F96）

```lvyin-skill-contract
{"as_of": "2026-09-30", "evidence": {"mode": "four_state"}, "sources": [], "failure": {"on_gate_fail": "named_refusal_not_pass", "on_missing_data": "named_gap_no_fabrication"}, "evals": [{"id": "ev-domlease-batch", "kind": "review_instantiate", "matter_id": "m-f96-preset-dom-lease", "batch_id": "brt-f96-preset-dom-lease", "expect": {"column_ids": ["deposit_refund", "early_end", "maintenance", "premises", "rent_deposit"]}}, {"id": "ev-domlease-refusal", "kind": "refusal", "scenario": "corporate_investigation_no_data_source", "expect": {"outcome": "refused"}}]}
```

## 失败与缺口纪律

- 守门不过：具名拒（NOT_PASS），绝不以未核状态签 PASS。
- 缺数据（如登记公示信息无数据源接入）：具名缺口待核，绝不编造。
