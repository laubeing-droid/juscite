# lawbook-packs · 法条手册内置包（RE-13 §3.1）

本目录=桥侧 lawbook-packs 包根（多包聚合，等量 E6；子目录各为一包）。随产品分发的基础快照
（免费）；全量包/效力变更月更属后续订阅线（本期只留 pack.meta 接口形状，无服务端）。
⚠ 本 README 放包根而非 base/ 内——打包管线重建 base/ 时整目录重写，勿把非产物文件放 base/ 下。

- 内容：常用核心法律+司法解释共 32 部 43 行（多版本行 8），包体约 1.7MB（目标 ≤2MB）。
- 文本来源：公有领域（著作权法第 5 条）。种子=在盘 LawRefBook/Laws 快照（只读引用，commit 5057151），
  打包期由 `tools/bridge/lawbook_pack_build.mjs` 确定性生成；重打（会整目录重写 base/，产出确定性同 sha256，仅 update 时间戳刷新）：
  `node tools/bridge/lawbook_pack_build.mjs --laws-root <Laws克隆路径>`。
- 效力口径（运行时推导，不硬编码列）：
  - 已废止 = valid_to 非空且 valid_to ≤ 今日（含当天）；暂未施行 = valid_from 非空且 > 今日；
    valid_from 缺失/空串/不可解析 = 已施行；today = UTC+8 日历日（固定 Asia/Shanghai）。
  - 修订链 = 同名多版本按公布日排序，旧版 valid_to=新版生效日（生效日三分支：正文提取≥公布日取正文值，
    <公布日取公布日，无提取取公布日；仅对入链多版本回填，单版本无提取留空不回填）；司法解释不入链。
  - 跨法废止 = 新法正文"《…》…（同时）废止"书名号组抽取，防呆：同名排除/被废法须早于生效日已发布/
    去"中华人民共和国"前缀/无生效日警告跳过。
- 诚实边界：逐条与官方库人工核对效力日期未做（材料不出域，无出库通道）；日期取自源 md 与上述确定性
  管线，缺失→留空按已施行（fail-closed 语义）；内容正确性不在 RE-13 验收范围（RE-13 §5）。
- 完整性：pack.meta 四字段（name/hash=pack.sqlite3 sha256/update/filesize）；桥首载校验 sha256 对账 +
  `PRAGMA quick_check` + 抽一条解析自检，任一失败→面板"法条包不可用"占位，不静默用残包。
