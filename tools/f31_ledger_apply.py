# -*- coding: utf-8 -*-
"""W4-U33 台账字节外科：恰 F31-desktop/F31-selfhost 两行落账（W2b-U60/W3-U37 先例）。

QUOTE_MINIMAL 往返先验（全文件解析再序列化逐字节等）通过后才施改；
改后回读 18 列全等校验。余 296 行逐字节不动，BOM/CRLF 保持。
"""
import csv
import io
import sys
from pathlib import Path

LEDGER = Path(__file__).resolve().parents[1] / "docs" / "construction" / "acceptance-ledger.csv"

ACTUAL_COMMON = (
    "W4-U33 实跑（2026-10-20）：验收命令 python -X utf8 "
    "tools/PENDING_OWNER_f31_mcp_exposure_recon.py --profile desktop --profile selfhost"
    "（worktree 根 cwd）＝双 profile 各 18 检 RECON_OK exit 0。"
    "S 段（产品面静态 6 检）：S6 桥纪律（legal_entry 子进程 mcp.register 往返 exit 0＋"
    "mcp.nonsense exit 3 NOT_CONNECTED）＋S1 编译确定性（两跑 canonical sha 相等；"
    "direct codemode:false／codemode true／deferred disabled:true＋codemode:true／"
    "hidden 结构性缺位）＋S2 hidden 三层（integration.use mcp:f31hidden 注册表摘除 veto＋"
    "tool.use f31hidden_*:* 运行期强制 deny veto＋权限尾置 f31hidden_* deny whollyDisabled）＋"
    "S3 凭据隔离静态面（plan/registry/回执零明文·物化文件受控正对照在场）＋"
    "S4 invoke_policy 四档×双面真值表＋法律 profile execute_enabled=False → "
    "codemode 调用面 closed_by_execute_wholly_disabled（E02/T05 在案语义）＋"
    "S5 response_guard 恶意载荷三族分类（permission_directive/tool_definition_injection/"
    "instruction_override）＋规则集指纹不变＋干净载荷零族。"
)

ACTUAL_DESKTOP = ACTUAL_COMMON + (
    "P 段（desktop 活体 12 检，隔离服务独立端口 43207＋临时 XDG 四根＋boot location="
    "合成工作区·与 43127 活服务共存零触碰·OPENCODE_DISABLE_MODELS_FETCH=1）："
    "P1 服务自起＋MCP 双面握手（direct stdio＋remote HTTP 双 initialize）＋GET /api/mcp 初态"
    "（f31direct=connected/f31code=connected/f31deferred=disabled/f31hidden 缺席恰 3 server）＋"
    "P2 发现面基线（假 provider 回环截获模型请求体 tools 数组＝模型可见面 ground truth："
    "f31direct_whisper 独立定义在场·f31code_/f31deferred_/f31hidden_ 独立定义缺席·"
    "execute（CodeMode）在场）＋P3 direct 调用面（按名 tool_call→stdio server 真 tools/call→"
    "结果回流·has_credential 只回 boolean 凭据值绝不回显）＋P4 codemode 负向（按名直调"
    "→No tool named·server 零 tools/call）＋P5 codemode 正向（tools.f31code.echo code 经 "
    "Code Mode execute 包装→server 真 tools/call→F31CODE-ECHO 结果回流）＋"
    "P6 deferred 默认态（disabled→零工具→按名拒）＋P7a 运行期 connect 通道（POST "
    "/api/experimental/mcp/f31deferred/connect→connected＋server 真 initialize/tools/list）＋"
    "P7b 模型面拾取边界（结构性如实入账：3 试 execute 包装＋1 次重连＋多轮模型面均不拾取"
    "晚连接工具；错误层证据 CodeMode 'Unknown tool'＋registry 'No tool named' 两层归档"
    "captures/·发现面不变式=definitions 激活前后均无 f31deferred_）＋"
    "P7c 按需激活模型面生效通道＝编译翻档 deferred→codemode→重物化→服务重启消费"
    "（重启后三 server connected→execute 包装调用 server 真 tools/call）＋"
    "P8 hidden 双面（旁路 PUT 放行如实记录＋发现面仍无 f31hidden_ 定义＋oracle "
    "f31hidden_whisper=deny——tool.use veto＋权限尾置 deny 合围不依赖 PUT 被拒）＋"
    "P9 远端响应不扩权（恶意载荷=伪 tools 定义＋权限指令＋伪规则集经 f31code 工具结果回流"
    "在场；回流前后请求体 tools 名集逐字不变＋session permissions 字段逐字不变＋oracle "
    "webfetch deny/f31direct_whisper allow 双向保持[非恒拒守卫]＋response_guard "
    "data_only_no_privilege_effect 三族命中——F-8/T13 权限语义教训的活体负测）＋"
    "P10 法律 profile 会话（尾置全禁）：请求体零 f31_* 零 execute＋oracle execute/"
    "f31code_echo 双 deny（execute:* 全禁→CodeMode 整体不下发·codemode 档调用面随之关闭）＋"
    "P11 凭据隔离扫描（E10 金丝雀面合成·JUSCITE-CANARY-*×3）：假 provider 全部捕获体"
    "（模型可见面）零命中＋服务日志零命中＋header 凭据只达 server 通道（在场 boolean 正向证据"
    "·值不回流）＋隔离根扫描零违规（白名单=物化配置＋mcp-state 台账位＋S3 正对照）＋"
    "产品根 %APPDATA%\\Juscite 零命中＋v6 遗留根 %APPDATA%\\JusBench 只读核对零命中＋"
    "扫描器非空转对照（受控件命中）＋P12 清理复原（会话删除·服务停·端口无监听）。"
    "边界如实：deferred 按需激活=双通道（①原生 connect 激活原生 MCP 层·模型面拾取边界在案；"
    "②编译翻档＋重启消费=P7c 实测）；hidden 旁路 PUT 放行态如实记录；法律 profile codemode "
    "档调用面关闭在案。全程合成材料·oc28 主检出零触碰零补丁·%APPDATA%\\JusBench 零触碰·"
    "不 push。pytest 全套 968 passed＋146 subtests 0 败·registry validate PASS 分母 298。"
)

ACTUAL_SELFHOST = ACTUAL_DESKTOP.replace(
    "P 段（desktop 活体 12 检，隔离服务独立端口 43207",
    "P 段（selfhost 活体 12 检，隔离服务独立端口 43209")


def build_row(old: list, profile: str, subject: str) -> list:
    row = list(old)
    row[8] = ("python -X utf8 tools/PENDING_OWNER_f31_mcp_exposure_recon.py "
              "--profile desktop --profile selfhost")
    row[9] = "juscite worktree w4-u33 根（.local/worktrees/w4-u33）"
    row[10] = subject
    row[11] = ("双 profile 各 18 检 RECON_OK exit 0（S 段产品面静态 6 检＋P 段活体 12 检）；"
               "pytest 全套 0 败；registry validate PASS 分母 298")
    row[12] = "0"
    row[13] = ACTUAL_DESKTOP if profile == "desktop" else ACTUAL_SELFHOST
    row[15] = "VERIFIED"
    row[16] = ("边界如实：①deferred 按需激活=双通道——原生 connect API 只达原生 MCP 层"
               "（oc28 v2.0.28 实测边界：模型面工具清单不拾取晚连接工具，3 试＋重连＋多轮"
               "不进·错误层两层归档）；模型面生效=编译翻档＋服务重启消费（P7c 实测），"
               "上游拾取缺陷若修复则原生通道即全通（产品面语义不变）；②hidden 旁路 PUT "
               "runtime 放行如实记录（发现/调用双面由 tool.use veto＋权限尾置 deny 合围，"
               "不依赖 PUT 被拒——注册表摘除 veto 是启动期层）；③法律 profile execute:* "
               "全禁在案→codemode 档调用面关闭（P10 活体复验），四档策略对 execute 面"
               "的依赖如实呈报；④产品级 MCP 中心（连接器市场/多用户）随多用户开（06 行 "
               "保留说明·本单为产品面治理层＋原生面接线非中心 UI）。oc28 零触碰零补丁；"
               "%APPDATA%\\JusBench 零触碰；合成材料；不 push")
    return row


def main() -> int:
    raw = LEDGER.read_bytes()
    text = raw.decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(text, newline="")))
    # QUOTE_MINIMAL 往返先验
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerows(rows)
    if buf.getvalue() != text:
        print("ROUND-TRIP MISMATCH：QUOTE_MINIMAL 往返不等，拒改")
        return 2
    targets = {"F31-desktop": 56, "F31-selfhost": 57}
    for name, index in targets.items():
        if rows[index][0] != name:
            print(f"ROW INDEX DRIFT: rows[{index}][0]={rows[index][0]!r}")
            return 2
    subject = ("juscite=w4-u33（本单分支 worktree，收口 commit 见 UnitResult）；"
               "oc28=026b106 主检出只读零触碰（bun run 源码 CLI serve 拓扑·"
               "OPENCODE_VERSION=2.0.0-local-w4u33<profile>·F-4 双轨记录实值非打包 pin）；"
               "隔离根=.local/tmp/f31-<profile>-*（临时 XDG 四根·不入 git）；"
               "产品面=implementation/python/mcp_connector.py＋legal_entry 冻结方法组 "
               "MCP_CONNECTOR_METHODS 五方法（register/compile/materialize/response_guard/"
               "invoke_policy·config mcp_state_root·fail-closed 同基线）；"
               "oc28 原生消费面=mcp.servers（codemode/disabled/headers/environment）＋"
               "experimental.policies（integration.use/tool.use veto）＋全局 permissions "
               "尾置 deny＋/api/experimental/mcp/:server/connect|PUT")
    rows[56] = build_row(rows[56], "desktop", subject)
    rows[57] = build_row(rows[57], "selfhost", subject)
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerows(rows)
    out = buf.getvalue()
    LEDGER.write_bytes(b"\xef\xbb\xbf" + out.encode("utf-8"))
    # 回读校验
    check = list(csv.reader(io.StringIO(
        LEDGER.read_bytes().decode("utf-8-sig"), newline="")))
    assert check[56][0] == "F31-desktop" and check[56][15] == "VERIFIED"
    assert check[57][0] == "F31-selfhost" and check[57][15] == "VERIFIED"
    assert all(len(r) == 18 for r in check), "column count drift"
    print("ledger updated: F31-desktop/F31-selfhost → VERIFIED（恰 2 行·余行字节不动）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
