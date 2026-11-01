# 技能广场 · A 轨上架清单（community-listing · 批次 a-track-20261030）

> 定位（决策台账 2026-10-29「概念确立·办案线」）：广场＝长尾补货渠道，**降位不撤**；A 轨＝**原样上架**。
> 原样上架的含义：本目录只登记第三方源 pin（repo@commit）与许可/对口标注，**不复制任何第三方内容字节进产品树**；
> 用户按 pin 取原源安装。机器可读清单＝同目录 `community-listing.json`（本 README 是其人读视图，两处不一致以 json 为准并在下轮修 README）。
>
> 本目录**不是安装源**：无 `catalog.json` 渠道声明，按 F94 契约（`implementation/python/skill_catalog.py:76` CATALOG_MARKER，
> 缺声明＝f94_source_channel_undeclared fail-closed）即非源。安装走 #21 既有面：
> - F94 git_local：`source={kind:git_local, repo:<本地克隆>, commit:<40-hex>}`，要求源仓根自带 catalog.json——第三方原仓无此文件，安装前需打包侧装配渠道声明（后续施工，本单不做，只加内容不加架构）；
> - F95 zip：社区 zip 预检＋`source{url,sha256}` 字节全等（`implementation/python/skill_catalog.py:43-47`）。
>
> 红线随单：①AGPL 件＝标注不搬码（可视化）；②监测类叠 #22 定时任务，不建监测中心；③本轮零 JC 件——期限/利息对口 #17 一律
> 过渡档九计算器（JC 完整档＝修订中挂起），第三方规则候选不进 JC（决策台账 2026-10-29「JC 撤出」行＋「JC 规则来源纪律」行）；
> ④对口判以 竞品情报/2026-10-29-规格波 两源深挖台账 v2 为准，台账无条目的源按 蒸馏移交/00-总登记.md＋决策台账裁决登记；
> ⑤功能账/决策台账本轮由落账员统一改，本目录不改账。

## 一、六组上架清单

| # | 组 | 源（repo @ commit，均 2026-10-30 实测钉定） | 许可（实测） | 技能数 | 对口（依据） | 标注 |
|---|---|---|---|---|---|---|
| 1 | dsh 13 域 | `kingselyjoe/dsh-legal-work-bench` @ `6cccce5914569c623dcfd8b71f1a86d08a6b9c6b`（2026-08-17） | LICENSE＝MIT 正文＋NOTICE 附录（致敬 claude-for-legal-ZH Apache-2.0、自述内容独立重写）；GitHub 识别＝Other/NOASSERTION | 25（`preset/skills/00-24` 各一 SKILL.md：00 画像＋13 领域＋04/05 双闸门＋16 审计链＋17-21 五托管工作流＋22 案件管理＋23 门禁审批＋24 内容联动） | #12 域技能包族／#32-36 非诉五件（监测工作流参照）；监测类（5 托管工作流）叠 #22 上技能即得、不建监测中心（决策台账 2026-10-29 ⑩；移交登记 T1-2「法务域唯一剩源」） | 两源台账 v2 无此源条目（yuanli/zhihe 均未收录），对口按移交登记＋决策台账；作者商业化说明自称开源版 24 技能（与树实测 25 出入，如实登记不裁）；付费层不在该仓不涉；配套仓 dsh-legal-ip 不在本批名单未上架 |
| 2 | 尽调包 | `huangzesen/legal-dd-assistant-benchmark` @ `d9ec0e9965eadbdb71935ac742426ea96f45eeb3`（2026-05-18） | MIT | 1（仓根 SKILL.md；整仓 16 文件＝rubric/金标/scenarios/规则手册/评分骨架） | #32 整理与尽调（移交登记 T1-3「直喂 #32 尽调」） | 两源台账 v2 无此源条目；基准形态（规则遵循评测），作 #32 对拍照料 |
| 3 | 晨报 | `elephantyoung/legal-morning-brief` @ `b3ade9118b11eb7f343fc3f3e04a136128ea0198`（2026-08-15） | 仓根未声明（GitHub API license=None）；随包 zip 内含 MIT LICENSE（elephantyoung, 2026）——双态如实标注 | 1（zip 内 `skills/legal-morning-brief/SKILL.md`＋3 references＋agents/openai.yaml；仓＝README＋zip 共 2 文件、18KB） | #22 定时任务·技能族叠加（决策台账 2026-10-29 ③⑩；移交登记点名批 2） | 监测类叠 #22 不建中心；两源台账 v2 无此源条目 |
| 4 | 期限 | `SimbaCD/legal-period-manager-skills` @ `aed17eaff2ca81c9512a1ce2fcf145cfd44abc03`（2026-05-08；本地克隆＝`竞品情报/2026-10-29-规格波/repos/period-manager`） | MIT（LICENSE:1-3 实读，Copyright 2026 Simin） | 4（`skills/{诉讼,执行,劳动仲裁,待办}管家/`） | #17 九计算器·期限族（决策台账 2026-10-29 ④「计算侧已覆盖，法律依据表作对拍口径」；`#17-对拍口径-期限与利息.md` §2.1 已对拍；yuanli 台账 v2 du-四管系（:53-56）＝同文族源头、:180 期间管家三源） | **格式注意**：四件入口为小写 `skill.md`，#21 发现契约按字符串等值 `SKILL.md`（`skill_catalog.py:241`）判目录技能——原样字节下不可载（会 f94_catalog_empty），原样保留仅标注；A 轨不改正名；期限数值＝竞品口径只登记条名不裁真伪、不进 JC、过渡档九计算器（JC 完整档＝修订中挂起） |
| 5 | 利息 | `kkaann7744/legal-interest-calculator-skill` @ `52fc01dffd60b5fde568b5eccc2b2508da4cfe71`（2026-10-05；本地克隆＝`竞品情报/2026-10-29-规格波/repos/interest-calc`） | MIT（LICENSE:1-3 实读，Copyright 2026 kkaann7744） | 1（`skills/legal-interest-calculator/SKILL.md`，frontmatter name/description 闭集键实测在） | #17 利息模块（决策台账 2026-10-29 ⑤：LPR 动态分段/首尾日四口径/360-365-366/迟延履行加倍/独立核验器；`#17-对拍口径-期限与利息.md` §2.2 已对拍；zhihe 台账 v2 同口部件 zhihe-001 见其 :21 行） | 过渡档九计算器；第三方规则候选不进 JC（JC 完整档＝修订中挂起） |
| 6 | 可视化 | `MiaoQichuan/new-litigation-visualization` @ `58f70a83350a421dc1571c357efaefb262a82c4b`（2026-10-28；本地克隆＝`竞品情报/2026-10-29-规格波/repos/new-litigation-visualization`） | **AGPL-3.0**（本地克隆 LICENSE 实读＝GNU AGPL v3；git log 实证 58f70a8「release: v3.0.0 · 改为 AGPL-3.0」2026-10-28 改牌——yuanli 台账 v2:107 记 MIT 属 2026-09-17 旧快照，许可以现 pin 为准） | 7（`plugins/mqc-nlv/skills/` 七 SKILL.md：时间轴/法律关系/大事记/庭审对抗/法律图表/法律课件/诉讼图重画）；另有 `plugins/mqc-nlv-dsh`（DSH 插件形态、同七技能随包，AGPL-3.0-only 自述） | #4 案件时间线／#19 轻量知识图谱 深化＝B 轨（决策台账 2026-10-29 ②）；yuanli 台账 v2:107＝可视化线第一对口 | **AGPL 标注不搬码**：净室机制等量、文案自写、严禁复制代码与文案；B 轨深化由规格波单元另行施工，本单只上架原样件（用户按 pin 自取原源，我方不分发其字节）；DSH 插件形态非 #21 直装面，仅登记 |

## 二、计数对账（2026-10-30 实测）

- 上架组＝**6**；登记技能＝**39**（25＋1＋1＋4＋1＋7；可视化 DSH 插件内的同七技能系同物插件形态，不重复计）。
- 按 #21 F94/F95 契约**原样可载＝35**：期限 4 件因小写 `skill.md` 不满足字符串等值发现契约（`skill_catalog.py:241`），如实标注不可载、原样保留。
- held／retirements 交叉核对（报数前查账）：`route3-2049-skills-final-v1/workbench/held_records.jsonl`＝3,063 行、`retirements.json`＝903 条（与《技能管线双出口_方向指针_20261029.md》§四账面一致），六源名（dsh-legal-work-bench/legal-dd-assistant-benchmark/legal-morning-brief/legal-period-manager-skills/legal-interest-calculator-skill/new-litigation-visualization）逐一 grep＝**零命中**——A 轨六源与蒸馏 held/退役账无重叠、无双计。
- 与 B 轨关系：可视化（#4/#19）、晨报（#22）、期限/利息（#17）的内置深化件由规格波各单元另行施工；A 轨只上架原样第三方源，不替代、不重复。

## 三、边界与诚实声明

- 六源的法律内容正确性（期限数值/利息口径/领域规则）一律 **UNKNOWN**：本轮未做官方法源独立核验，竞品口径只登记不裁真伪。
- dsh-legal-work-bench／legal-dd-assistant-benchmark／legal-morning-brief 三源**本机无克隆**，pin 经 GitHub API（commits/trees，2026-10-30，走本机代理）实测钉定；后续若入 F94/F95 安装轨，需先落本地克隆并按 README §安装说明装配渠道声明。
- 本清单是广场库存视图，不是功能真源：我方功能以 `docs/产品功能账.md` 为准（#21 技能安装 :31、#22 定时任务 :32、#17 九计算器 :27、#4 :14、#19 :29、#32 :42）。
