# -*- coding: utf-8 -*-
"""W5-U09 台账字节外科：恰 F99-desktop/F99-selfhost 两行落账（W4-U33/W2b-U60 先例）。

行级字节外科（W4-U36 行含裸引号使全文件 QUOTE_MINIMAL 往返失稳——非本单
引入，如实记录）：按纯换行物理行切分，仅重写两目标行（csv QUOTE_MINIMAL
序列化＋CRLF 收尾同形），其余行字节原样保留；BOM 保持。改后回读 18 列全
等＋目标行语义校验＋未触行字节断言。
"""
import csv
import io
from pathlib import Path

LEDGER = Path(__file__).resolve().parents[1] / "docs" / "construction" / "acceptance-ledger.csv"

ACTUAL_COMMON = (
    "W5-U09 实跑（2026-10-23）：验收命令 python -X utf8 "
    "tools/PENDING_OWNER_f99_marketplace_recon.py --profile desktop --profile selfhost"
    "（worktree 根 cwd）＝双 profile 各 35 检 RECON_OK exit 0＋跨 profile 4 检。"
    "落点＝独立商业新模块 implementation/python/skill_marketplace.py（06:V7-99 "
    "python_entry_ids=UI_HOST_OR_NEW_PRODUCT＝发行商业新义务，不冒已有业务入口；"
    "UI 仅调用/展示不前造）＋legal_entry 冻结方法组 SKILL_MARKETPLACE_METHODS "
    "七方法（submit/review_decide/adopt/rankings/purchase/entitlement/list·config "
    "skill_marketplace_state_root＋skill_catalog_state_root=F94 同域键·fail-closed "
    "同基线）。S0 钉定：产品面 sha＋F94/F95/F96/F27 依赖面锚在文＋oc28 skill-file.ts "
    "只读对照＋legal_entry 接线在文。S1 创作者流：合成 zip 过 F95 预检（skill.zip."
    "inspect OK＝格式权威一致）→market.submit 登记 submitted（提交面结构性无批准出"
    "口：list 投影 unreviewed）；浮点价 f99_price_invalid 具名拒（金额整数分禁浮点）。"
    "S2 审核管线 fail-closed：干净提交 approved 需全清单过（字节完整性复核→脚本零容"
    "忍→逐技能 F27 injection.scan(kind=skill)→逐技能 F96 合同 validate，findings=[]）＋"
    "同件重复同决定幂等＋异决定/异审核员 f99_review_conflict 具名拒。"
)

ACTUAL_DESKTOP = ACTUAL_COMMON + (
    "S3 分发/采用真生效：adopt 携真实决定引用（decision_ref.review_id 必须解析到本"
    "账 approved 行；伪造引用 f99_decision_ref_missing／跨件错绑 f99_decision_ref_"
    "mismatch 具名拒＝F53 author 纪律）→市场目录树按采用事件重放提交包真实字节→确"
    "定性 bundle（F94 pack 同格式：内嵌 manifest.json＋逐文件 sha256＋定时间戳）经 "
    "F94 bundle 源真安装（public 广场）→skill.catalog.verify OK＋read 投影非空（上游 "
    "toModelOutput 同形）＋活动面 skills/ 落盘 4 项；同一 zip sha 重复采用幂等不重复"
    "计数。S4 排行流：本地真实采用事件派生（adopt 事件逐技能计数，(-count,id) 确定性"
    "排序），采用即入榜、升级采用计数 2 且活动面同切换（read name=二代，verify OK）；"
    "service_surface=synthetic_local 如实标注（裁决#13-19：真实商业排行服务随 v2 商业"
    "化补）。S5 付费墙合成服务面：付费技能未经购买 adopt typed 拒 f99_paywall_"
    "required→合成购买（价必须与声名价全等/浮点具名拒；回执 service_surface=synthetic＋"
    "minor_unit=cny_cent 整数分，零真实支付轨道）→放行且回执携 purchase_id→"
    "entitlement 回读翻 true。S6 账本纪律：events.jsonl 单一 append-only 事件账逐行 "
    "digest 复核（篡改 f99_ledger_digest_mismatch typed 拒）＋审计投影逐件相符。"
    "S8 红线负测（全部合法工作后的真实活动目录上验）：三个构造性恶意样本（提示注入文"
    "本/夹带脚本/无 F96 合同）各＝F95 预检 OK（过预检即拒的前提成立）→审核 approved "
    "具名拒（f99_review_injection_findings/f99_review_script_policy/f99_review_contract_"
    "invalid）→审核员落账 rejected 携具名 findings→采用 f99_adopt_review_not_approved "
    "typed 拒→F94 渠道根（store/skills/active/history）字节快照逐字节全等零落盘（快照"
    "条目 22）。S9 跨 profile：7 件合成 zip sha＋安装 manifest 摘要 26f685eb4cc55354…＋"
    "技能集＋审核纪律 findings＋排行逐项全等（合成 zip 定时间戳＝确定性）。边界如实："
    "排行/付费墙为本地合成服务面（裁决#13-19），真实商业化设施 v2 补；原生市场 UI 面"
    "不在本单；controlled 受控根无市场入口（F94 渠道分根语义保持）。全程合成材料·"
    "oc28 零触碰零补丁·%APPDATA%\\JusBench 零触碰·模块导入闭集无 socket/urllib/"
    "subprocess/random＝不触网结构面·不 push。"
)

ACTUAL_SELFHOST = ACTUAL_DESKTOP.replace(
    "S8 红线负测（全部合法工作后的真实活动目录上验）",
    "S8 红线负测（selfhost＝产品面同进程径；全部合法工作后的真实活动目录上验）")

SUBJECT = ("juscite=w5-u09（本单分支 worktree，收口 commit 见 UnitResult）；"
           "产品面=implementation/python/skill_marketplace.py＋legal_entry "
           "冻结方法组 SKILL_MARKETPLACE_METHODS 七方法；硬依赖（全部只读消"
           "费已 VERIFIED 面，零改动）=F94 skill_catalog（bundle 源安装/渠道"
           "分根）＋F95 precheck（zip 预检）＋F96 skill_gate（执行合同）＋"
           "F27 injection_defense（注入扫描）；config=skill_marketplace_state_"
           "root＋skill_catalog_state_root（F94 同域键）")

_BOM = bytes([0xEF, 0xBB, 0xBF])


def build_row(old: list, profile: str) -> list:
    row = list(old)
    row[8] = ("python -X utf8 tools/PENDING_OWNER_f99_marketplace_recon.py "
              "--profile desktop --profile selfhost")
    row[9] = "juscite worktree w5-u09 根（.local/worktrees/w5-u09）"
    row[10] = SUBJECT
    row[11] = ("双 profile 各 35 检 RECON_OK exit 0＋跨 profile 4 检；"
               "pytest 全套 1273 passed＋10 skipped 0 败；registry validate "
               "PASS 分母 299")
    row[12] = "0"
    row[13] = ACTUAL_DESKTOP if profile == "desktop" else ACTUAL_SELFHOST
    row[15] = "VERIFIED"
    row[16] = ("边界如实：①排行/付费墙＝本地合成服务面（§6.1 裁决#13-19 商业服务端"
               "合成先行），真实支付轨道与商业排行服务随 v2 商业化补，本面不冒真实"
               "设施（service_surface=synthetic/synthetic_local 显式标注）；②原生市"
               "场 UI 仅调用/展示不前造（17 卡 UI_HOST_OR_NEW_PRODUCT）；③controlled "
               "受控根无市场入口（F94 渠道物理分根：商用内容不混广场语义保持）；④市"
               "场目录分发＝F94 bundle 源真安装，采用幂等按 zip sha，升级采用＝同 id "
               "技能内容寻址覆盖；⑤审核清单 v1 四检（完整性/脚本零容忍/F27 注入扫描/"
               "F96 合同 validate）为产品政策闭集，扩展属面演进不属缺陷。合成材料；"
               "不 push")
    return row


def main() -> int:
    raw = LEDGER.read_bytes()
    bom = raw[:3] == _BOM
    text = raw.decode("utf-8-sig")
    # 纯物理行切分（不用 splitlines——其会把 U+2028 等也当换行致漂移）。
    # CRLF 文件：split 后每个行元素自带行尾 CR（末行除外）。
    lines = text.split("\n")
    targets = {}
    for i, line in enumerate(lines):
        if line.startswith("F99-desktop,"):
            targets["desktop"] = i
        elif line.startswith("F99-selfhost,"):
            targets["selfhost"] = i
    if set(targets) != {"desktop", "selfhost"}:
        print("ROW DRIFT: F99 两行不在账")
        return 2
    for key, i in targets.items():
        row = next(csv.reader(io.StringIO(lines[i], newline="")))
        if len(row) != 18:
            print("COLUMN DRIFT: 目标行 %d 列" % len(row))
            return 2
        if row[15] != "NOT_RUN":
            print("STATUS DRIFT: %s status=%s（非 NOT_RUN，拒改）"
                  % (key, row[15]))
            return 2
        new_row = build_row(row, key)
        buf = io.StringIO()
        csv.writer(buf, lineterminator="").writerow(new_row)
        lines[i] = buf.getvalue() + "\r"
    out_text = "\n".join(lines)
    # 回读校验：目标行 18 列语义＋其余物理行字节不动＋总行数不动。
    check_lines = out_text.split("\n")
    assert len(check_lines) == len(lines), "行数漂移"
    touched = 0
    for i, (before, after) in enumerate(zip(lines, check_lines)):
        if i in targets.values():
            touched += 1
            row = next(csv.reader(io.StringIO(after, newline="")))
            assert len(row) == 18 and row[15] == "VERIFIED" \
                and row[12] == "0", "目标行回读校验失败"
        else:
            assert before == after, "未触行字节变动 line %d" % (i + 1)
    assert touched == 2, "触碰行数异常"
    LEDGER.write_bytes((_BOM if bom else b"") + out_text.encode("utf-8"))
    print("ledger updated: F99-desktop/F99-selfhost → VERIFIED"
          "（恰 2 行·余行字节不动·BOM 保持）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
