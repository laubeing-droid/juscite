#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""W2b-U60 A1 裁决落账 recon：word 宿主半边三行翻 EXCLUDED＋E13 永久结转注记。

权威链：
 - docs/construction/00-总协调.md:249 §6.1a A1（2026-10-18 用户裁决：Word 不
   安装；E13/F46-word/F52-word/F57-word 的 word 宿主半边永久结转，原回收点
   W2-S1/W4-S2 作废；WPS 半边 VERIFIED 有效）；
 - 主控升级裁决（本单施工中 escalation 回执，(a) 修正版）：A1「按 EXCLUDED
   处理」为明文，W3-U30 保守落码（E28 S3D 钉 NOT_RUN）系落码时序差非裁决矛
   盾；授权本单随分支修订 registry.py（裁决性 EXCLUDED 第三类）＋E28 S3D
   （NOT_RUN/裁决性 EXCLUDED 二态如实）＋E27 S6（同规则）＋对应单测；
   F57-word 归 W4 规划员不在本单。

用法：
  无参＝复验模式（验收命令，juscite main 树或本单 worktree 根 cwd）：
    python -X utf8 tools/recon/PENDING_OWNER_a1_word_rows_exclusion_recon.py
    ⇒ 全检 PASS 输出 RECON_OK exit 0；任一 FAIL 输出 RECON_FAIL exit 2。
  --apply＝施工模式（本单施工期一次性落账）：仅当台账仍处基线态（逐行
    sha256 清单全对）时执行恰 4 行变更；已落账态拒绝重复写 exit 2。

检查面：
  C0 文件形状：BOM＋恰 299 个 CRLF 行段＋末尾 CRLF＋无裸 LF/CR；
  C1 基线逐行 sha256 清单：295 非目标行对基线@666559d 逐字节不动；
  C2 恰 4 目标行新内容：F17-word/F46-word/F52-word status=EXCLUDED 且
     failure_reason 以「裁决性 EXCLUDED」开头引 A1；E13 status 维持
     IMPLEMENTING（不假 VERIFIED）且 failure_reason 增补 A1 永久结转＋
     模板视觉段 W4 指针；
  C3 CSV 结构：298 实例 18 列 id 唯一；F57-word 仍 NOT_RUN（W4 范围零越
     界）；census EXCLUDED=27（裁剪行 24＋裁决性 3）/IMPLEMENTING=15/
     NOT_RUN=91/VERIFIED=165；
  C4 E13 B2-b 段 VERIFIED 基础在账（F47-desktop/selfhost、F46-wps、
     F52-wps、F53-desktop/selfhost 六行）；
  C5 内含复验 python -X utf8 tools/acceptance/registry.py validate＝
     PASS exit 0。

全程只读（--apply 除外）；测试一律合成材料；oc28 与 %APPDATA%\JusBench
零触碰；不 push 不 PR。
"""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LEDGER_PATH = REPO_ROOT / "docs" / "construction" / "acceptance-ledger.csv"
REGISTRY_PATH = REPO_ROOT / "tools" / "acceptance" / "registry.py"

# 基线＝本单建支点 main@666559d（升级裁决前最后一合并）。
BASELINE_COMMIT = "666559d"

# 裁决性 EXCLUDED 类前缀（与 tools/acceptance/registry.py 同键；主控升级裁决）。
ADJUDICATED_EXCLUDED_PREFIX = "裁决性 EXCLUDED"
ADJUDICATED_REASON_CORE = (
    "裁决性 EXCLUDED（A1：Word 不安装，2026-10-18；原 W2-S1/W4-S2 回收点作废）"
)

# 三行 failure_reason 全文（起点必须为 ADJUDICATED_EXCLUDED_PREFIX，registry
# 据此分类；F46/F52 引 E13 行在案探针实证；F17 为 A1 逐名清单外按同规则延伸，
# 工单明示延伸性质）。
WORD_ROW_REASONS = {
    "F17-word": ADJUDICATED_REASON_CORE + (
        "；A1 逐名清单未列本行·按同规则延伸处理（F17-wps 半边已 W2b-U50 "
        "VERIFIED·本行为 F17 的 word 宿主半边同族·工单 W2b-U60 明示延伸性质·"
        "账房验收不认可退回 NOT_RUN）"
    ),
    "F46-word": ADJUDICATED_REASON_CORE + (
        "；Word 缺失实证引 E13 行 failure_reason 在案复核探针（HKCU "
        "Word.Application ProgID 悬空壳＋WINWORD.EXE 全盘零命中）；WPS 半边 "
        "VERIFIED 有效不随本行结转（工单 W2b-U60 落账）"
    ),
    "F52-word": ADJUDICATED_REASON_CORE + (
        "；Word 缺失实证引 E13 行 failure_reason 在案复核探针（HKCU "
        "Word.Application ProgID 悬空壳＋WINWORD.EXE 全盘零命中）；WPS 半边 "
        "VERIFIED 有效不随本行结转（工单 W2b-U60 落账）"
    ),
}
WORD_ROW_IDS = ("F17-word", "F46-word", "F52-word")
E13_ID = "E13"

# E13 行 failure_reason 增补（工单③：维持 IMPLEMENTING 不假 VERIFIED；由现引
# 裁决#4 处增补引 A1 永久结转＋模板视觉段 W4 指针）。
E13_ANCHOR = (
    "→裁决#4 word 宿主行挂 W4-S2 维持·E13 如实 IMPLEMENTING 待 v2 波 "
    "word/WPS 宿主补面"
)
E13_INSERT = (
    "；A1（2026-10-18 用户裁决 Word 不安装）增补：E13 word 宿主半边永久结转·"
    "前述裁决#4 挂 W4-S2 回收点随之作废·模板结构视觉段归 F56/B4→W4 规划员"
    "（工单 W2b-U60 落账·status 维持 IMPLEMENTING 不假 VERIFIED）"
)

# E13 B2-b 段 VERIFIED 基础六行（工单要点：W2b-U11/U36/U49 已 VERIFIED 有据）。
E13_B2B_BASIS_IDS = (
    "F47-desktop", "F47-selfhost",
    "F46-wps", "F52-wps",
    "F53-desktop", "F53-selfhost",
)

# ---- 基线常量（由基线@666559d 台账确定性生成，非手抄）------------------
_BASELINE_SHA256 = "7f22a5cf3bd314a3dcb15ae1eb49630ea51364ae59c3b92b3c676dfdf6b91ab5"
# 295 非目标行（1 基行号 → 该行段 sha256；行段＝按 b"\r\n" 切分的原字节）。
_LINE_SHA256: dict[int, str] = {"1":"0affcd579283d82c3b969a44d1c8d7246f5839ef64c0cbfe50d512c3e24cc8d9","2":"96a8fdce9ca42212f53a873f6149cef364cec39e5a206f75e7d5c81089838130","3":"8543a0c5d161e4b2325f9587093ad1d6080bab4af8c75d5d26277421ce5b2fac","4":"11d49b78d8af39ea46b6433f5d56c9958f6528b0560735430c63651ad459cc5a","5":"4a76c79a965761a71a1740b981f712dc466db312c0307ea50f33972cb44ad202","6":"cab19aaa300f0c3a745489dea201b2092825b325d910da35d47f48874d08181e","7":"e5b8044020aa84cbcb2db1f5ea7f9b92989e0558eeda477016b06570c8724cd4","8":"9a469d22a7269fca3cba155f7336149cef4a6ddff6894af0f4213eb205ea637a","9":"145a24f65ca150e3d2c824e6c7bd07a3e52f20b324d80e33b3fac0db4436c4f2","10":"d00b64ea8fb5e4594b038214dfbbd447fdf1e5e1763ce902663ddc1b61ea3526","11":"02410a49f6a87a45bf77c3e1b7b3923d7acb519b9ac399caf924806ad01cde2b","12":"8922386d8c11550bfd3e6f2a516cf1348c0eeae530d0b6da3a944c0bf96fcec6","13":"9c00dc03f8c3a5e1c3a7ced43bff1346ab22f927ddc57f4ef32daa6fa2f0c5a6","14":"c0187ece36da4f837fb6428dfe3a68b16e4cfa39d6f245ae5386b028939b68f8","15":"c86b9852daef8c47264d1979734985d3d7653f2a04195c4adc3cc75d1fa4ddc0","16":"4ca7fb8a6dd8a02a96efc9c7856de1131cf89de94285940474667edc34f937a1","17":"16ac4e6586af8c61267b5830b0da8027412ac4de533f501e4c4a5a456156ed75","18":"0a20e212b15d30852ecbbea9e0f4e7454f98efe2d818a7a0b6a42386cc671d4e","19":"47293bfaf46e1580e2eef3badd2591ba12fc42370a53d3c45c295d4049b643f6","20":"9db5a7417913fd86b4c7ae070dd7e6e656a7c4ad9ad331f769d2d5142ef128bc","21":"024463469fa020ced6eea1eae72ea653969d25260d2dfd238638c1d2737de403","22":"9390ec1b77c16b353f814c04f388b687f0c28b9d8d61129967cfa4757f714d03","23":"e725a0333a670709b2b2d0b369f4993529a325e4b1eb8bec5ebb01c79af6b78e","24":"f65aa194c3231c35826a85547268e9dfecc5e7da06832205b2c911ee742c50cf","25":"4e3bd582b7dc58362583076c4cca21be1b7bf8d7a5d3ba9752741b83f998ba7a","26":"d3a7b36c24a9977a02128639cf8421db9826b6a6e025c8813119d92ae94907de","27":"226ff5b677241519f06f131f5e49f4984781268ab0b0f940fba59ee81d0f506c","28":"b7da6b7bb559c431084515ae92ac85c81ba361779ab426a9d7c7d09eb6aea9bd","29":"44730c1d39f83e6b35f6a106cb6d17b5fb8a165c1c6a9875e5a05002bd5b6a3a","31":"544fbddea2a272b61cd64b2fe1050c96549df9653689be4998f69b537c352c66","32":"b18bdb691103018c96b7dabd1389c732ab22bdcb935738f46526c968ec2f8aa4","33":"4116f70141f000cfb3bfedca7f23a9a33b0758c9c8e0ac0b9be18ef424802e85","34":"a715af263837c544e07404ac8e9f9b60021ffbe1ce8bc8e18538a35ae5dbe74c","35":"ab248ff0a0d42ddde028f807a3768101f9ee059daaf86a86239878f085e781fe","36":"fb97cef66c81b2558a502ffd4b268271e58ff7588c24c9fa2cd1a25ad05c1a29","37":"8fc9cc0a1a0cfbc32ee58628ad1a77ce7726776562a27ca7b96b44e125fe46ad","38":"375adb6cb8199bfb9799e332fafcc18fa4306672328fca5af011390fe7cca98a","39":"ede138f1927e9606a93d08b5e4fb2a69bc674c5118ee3c8b9ad243894f947bcf","40":"8d8ebf50a49741e44e2d05e42cb32a9c9636751805cae202ed4aa2a98e43a798","41":"bf07b644a500935c4c1fac32c0f2a45ce5ab30f4d15d1d81d3117c5553c73274","42":"3b25795fe05251c59901a2c1b2446060dc40a906300eb3cfa639ba9edca5dc05","43":"f079528590fac1d52022c16ae2d2c1968abaf7a5138e30e290b801491441b485","44":"83d477a95eff0e84ce6167f350b69a0f1567daecf36db08258946ae0e2d17557","45":"1927aa8606f94ad9bb0868a8c61903bddc12753f9e41756adc94869a3d6ade53","46":"95773860e1c8f97a37304ec4187395453e25f9f34ff629b9899c4c7378274270","47":"579a443d6a4e7f46cc02ef22a27d893800e6242e3238746b3a6d8aa30529eca1","48":"a23df473f9bc6ec97a0b1f5961333c1edc7a4ad5cc8048a2626074b8445e0738","49":"ccc9057c612f5359e00ea832b9b1df74d53209b052676b4c5f8a729cdb17c92d","50":"b13bc8459a7a6c180463963e1716d288575acda959a1f5d0090e2c3d1dcb9d72","51":"a7ce5d4ee2033acfd6d31975e78c9fa481afffdabd152a3b9ecfe517cda1588e","52":"8a131a3ce00769dafeb5a1ad9d829a0c0eaa8e9df5e7dbdc5b950b17f6c1143b","53":"0d21a05b708de0c5e10d6d5411657ddc32af7c69a3df0f55c1bd7b00a052b88a","54":"99aa2786a3b81eb2b43f4bc57bd2dad7c38a05d868f9b01db3f519ef4596dd86","55":"6bd0d7871034fe847267042320f56e5ad06266084a22f69d7c4c69e80cacac38","56":"e2bb1ee5da9939706d149b2d3254628d137da286c48851994eea5865009129f4","57":"e7b0e444a1eca2f2cbce8146c0ed90758367ab7c762a35ab39aa7e750f831594","58":"3157b7e34c9f0155e930bbe80b1b2b0640b09a16279f47b0297be8b1a1f02b87","59":"9b84fceff724da338237d32ac65fce907da511aee804e70aefe05b25ee6fbdc9","60":"6c22542336d616286f002d5b02f3d9e53da358430fd225d535dfc6cbb64d08d5","61":"c781fbba4134c1a294d93e5e056312522b3e8bbb5eb2b9c4be614652f1637d1c","62":"1aeb03178fd99eb17db232e28bd1025f6966e4417a864d03d1973fd04ab892b0","63":"913a5436456b220586a1d7f867e1b3ac77d59272bfe9d5aefe9c2d237bee6084","64":"aa8b87425f5c12e031147303d2039149f32e7942f1bb39e99e7a1ca61c64b522","65":"aa6ab822d31b5559b9c61958d54b6f90f74501239f271a3432276ae90c21677c","66":"6a2060cebcfe12ccb79b4fa70089c67d6b365898c1dc6b89853bccba0d95ac64","67":"5da579bad61c9fe9684d814f1e4b8b194158185c340b76fa051b51fb3b5b03ce","68":"28bbff874e5875adeb9e5debdcd76c9682da295c20f4a08a9b53b13c83b8c379","69":"9df3a225fb1eae268728c88212e28667f1b3afa2dabb49df3ea41df50691461f","70":"0d3d5c4faf222a3a4d62d90288aac0a0a1f6f9eb9b435756ba2c2123b674698c","71":"e284dfe1ca4915a7e0ff4e67ed765ca7795820e84a9737ec556094118958281d","72":"b846fc89cdb52a8475c61c5938dbbe2b98d00b8ad11baa0d0356b40878967648","73":"af9f2bedeec7368926982e2506a56a343de2ad09200f24a6fc2c823e8557da50","74":"4f0acc046dd1a2598b876a6aa68e12f44a322f07c0ad96ba0304c004183394c7","75":"97740a5ab19c00f5bd669b30d54e0ff4040fc9ee065d947b193e0bee18b62d53","76":"5b6ac715c22f5e208952db90046ebaad00d6c834ff9431b65f496cf6d1c0f2a3","77":"165bd6fc96083c8604ec954436abffc8eb07be1d615c43787b36fe100130fe74","78":"0975ee76f20f9a9c44ab9f5dedb664c55691ae74fb7e82bf3faf2eef747fe0fa","79":"465a9251a1592909cbd9012113ad60580ef51d7674c1107b0acdd7b56136060e","80":"b2b5729c29ce8b052094aea8fb537c92eb9073d49f3cd6929d07dd52320f1893","81":"f828d0d8df342691f6023e9ebc3934d8f97b34dae089914822a81154cfb54065","82":"b7d178eef6503e03f6550b6d477d0463d7a88223d4194979aa61be74ab1277de","83":"c415f4d2605ee16140574fa3c0190ce85dc5055bc31d2cedadc329df0ac6ebc7","84":"a3850fa56ec4cbe2b97f2abdec1386bef45c237016c886cbb73441ab8b5b5c2f","86":"f61e3e7235365d5363fa426fd47ff06657c083462e842cc10f9f3cb705118d57","87":"c4bfa034a76adb99c6e850a6758b8c133413b970b820473e049c844e61828144","88":"b8b9f21d0c1ddc823127c8168b29db8baa10314c51d66374f0f495883534c507","89":"299e7da8a8a3cea66144a348e7f195129f774adbe2449bd2bc4ec29b51d01e40","90":"040a05aa35feb31c41e08d12caacc8b12f1785952e4c577e95248285333107d8","91":"176c37ffa596fc7bee1805f38aefb7ec6806e557e0ee8ada3f57973bfac0e265","92":"240fd5c201b2dab2d2b3932ab75e05cf3f8622e8a9bfffe682a0f3e97939bca9","93":"159a3f2b36450cc1df0164f62cc2e67a5a52f6722adb0e61c30009b5dc101a2b","94":"666b6e6bc16affb135c6394eb392e6c21fe25314855840a51b2de98d76422fc4","95":"ecad267fdbe308419a61ef3a9754465198178fd61d29e672b1f4ba5a88f310b3","96":"9f941466283e8f81a3d784f61df53e5aa70353f3841830f2949f2fcaa981234d","98":"c44b1b914a3732d158ecd4df068ab467de0a2e13f9a4a82272560aee75dadc53","99":"98f0fbe887bc33facf806f2e957908cd43ec26ade67690d4c3333a32700faac0","100":"f45e0a11ae3d51af0480c18265e2a93206466d065253e41d5b8fc12a9f2be5c7","101":"2c4565cfa58a683930eb381c256f394f59cceae56bac5527c86b6441b5e3239b","102":"0b10993375acb3eb30c0c4ace6cea69fb454c090c4970acb923914da46ef3902","103":"52139477e7ad554bb9e1631ff76899dd4bf3f359333acb2f1cd3197351305fb1","104":"b9d751d67721c362ba6f7237031a61454b4ffb8b7ba50ffaf36c3a2f0ceff440","105":"85224598f330943c3129fd4d08e7389ac666f7bd3fe7c64e63330d9f7e5eaedb","106":"4789f171750088aa30fb16b6d4e4cc9edd0114beb3f83716d2dec448ac897abc","107":"14419e87599fab8cd2b32cae570e512712c7ca1a44bddb136e8747c166073e85","108":"46b68e1e99656b277ea79fce3967aeaf1a9aab0ea3e11710b9b72592c2b1b6a7","109":"df6a8c1ab4a01245113d271e824d71b5382ef0ed50eeb7448e824418a002d1bd","110":"b4f6e13b562f7091807629a10be35d9cc713d9d811eb78d202912fabcf572f2b","111":"d522a0f264a599470aeef4b04eda3ce7cc22f74f670d784f1cbf89338a3007a7","112":"37cd7e35a25ccfd26a09d0509872136d7550d5444fbb87ba266093d34dadc049","113":"1a72630fe6e42537a1d027287819cbf79c82f005df2a339483781aa7a8a5956d","114":"fe3c967daebc324bd9acaae628b67cf127672973e3d3250f9d5246a44fd0980b","115":"6441695e9f497b3e346cc653d7e62d4477b1ea07ac4e05d40c2e11b2062f5e94","116":"df78fae55ab8a916295566038dc90b184019f5d14cf38f252ca643a1ab82ece4","117":"564436eba79ff05cf9295a7e74aef3b5a2ffd54c213343a9f3c189da2e20d34e","118":"693806e705942119326ea6c27a00bd4385e5144ac93a83ca2f39e310dcc5e6b6","119":"1781e7ef4193c71f451b71ddc5290448ee480368055e1388c06d0bb805c589fb","120":"0fab6908e777120adf1dcd0f41c8cb3fa5488a392d190942664c4ef52b75abbe","121":"ddde6146fb21f6bc1b0b8ff5932cb095090cfae7f59fcde004601524233b6f85","122":"b8b88c2bbcd3ebf37817c77efb466726f81a83e1a30c1abe1728782e2337f997","123":"f4b23774e35799397cb0273ab58c449d50730b6dd492ae0f15ba7a91a9e0bc5f","124":"0d29a5485a6c923a8d0dfc8e752c197791438bd61ccde03cee1b2311ff92ba12","125":"f36c479d0f99515704ecf8b148cd01e35baf37f73ae7d86677f0ae2653f0757c","126":"259bc250b9ef43f41e2a137da1cdeb396b4c018bd871f2d75ff505ad7fe80eee","127":"b83d1521cdb8dfca5d4edb7075b9b77c0f4e017a233e7908ebe0eecc54cbdfa0","128":"248f44fa29f39d55fd7d4b49cc4ad0fe162cd2985be7d7d5955ce19d5c7cf4f0","129":"29f91fe543f0042da4ebab181172908d6f776938e9d9ff0c3046ed621ad6c670","130":"0c3e2835da5f4cdacade7870b6be26fd894d938e0e0d73a70ec0c7ca4fac9f1d","131":"18a5d812f2fde541cae6795c58cfc79ddbcd68177c45091dfc41fe68f40be761","132":"131aefc36e1be432ab8d7d777acd66d3e44aa78781d9f284525271f19a7c4097","133":"1b6c621195a44f6c931a5966b0f5643feb21ad85049351ec69b970b9145f392c","134":"e39015fec99ea682b619d5495a1ad2255dc1e619cf9fb89ede92fa8de905ed66","135":"7819907554c248458956993653487444d11f748ca89a22b7d2319bd9eba711e0","136":"b199ad944de1ae24318422416746826daf47fd2f3b87c567a22808d949d121c9","137":"b35210fc66420adeb32e8130c9f1968a149f0bbfbf41ae8f36c4b034d24d5648","138":"71a40185734cb9bf2ca2b970c06460f9b9bbfdd02b12a3399cedd68b7b49c2b2","139":"62bb2ed7dcc3d4bb71d85b4032407991bbf6d822b20675db00329994205d0e67","140":"8591964a24b42bb81d0373b47be4f0f37d2d89d3e080fff7ed41b02d21f0c6ab","141":"bb3618f0dbe018602d062b3e50b50124c528b2c10d6c4d46837c2108232231c7","142":"215e1a30dcf9fa4dfa43c6147bcd701f84fb5561ab41ec781d18f31eb4f5cfd8","143":"e47bfb0770c82d881899849a725509542b0fee8b6a70f925f3e031dae2b4f04c","144":"c0868d7b60e109233b7232edc9aa077cc4c68a438fcf64b63285c1e73e8ae8bf","145":"6b146eea94a8fc2c00099cd177108c63b7429027cefa05bab2cb5844ae601783","146":"21e2edec914a1049835db70801018f313c0722d6fc5a43af4bd6aa92a9653640","147":"2abbc38c6412a77354200b1d20eebccf303686b1500659d7407eb388aef41ddd","148":"823513b0b3f0f7dde19c38e70f2be8520e49d59950a33a1b2529b0f389c1b081","149":"40d2154b94170824236e480fa775563f46a6ea28af660b80c198bf430abc134f","150":"e7a4ea6f7beef72faa3ef3760dfc4a09be3d7cb3f8fe55a62b5d7a7c2ff9e369","151":"eb160d2ab7ae9a8d76eab8c699391d52ca6186620ced1d8c05f0098c40225247","152":"4eba3ee1840aaffcdeef50c0401d4d7b6299e7de32f8bc9f52a0137b804b553b","153":"6bfecd06f801c58f3d86d750171aa02eb3e2c111d72e398c67dc17e392227031","154":"5a8b4213c67ea2b438acd90174220f4ba3db45d2c4e73d8c2d4595fd1ab26385","155":"922dd3ec1affb7a7a463d416e10fce0519c070a163ba0be821180085f399a943","156":"dbc1c2036520f09f2d90029b4b3462000596a053071ed19f5a74b4408cbd2c3c","157":"41b00a49cd1b22116271ca4dd780e5112f81ae105d61fe10a2ada16233420b43","158":"670b31761841079d80e9e6505bcc2b9308175a1fd1d226a7e554298c2815d24d","159":"0b31ec1942db7c62e681e23c519f413017ce12e74ac34e17332dfb062ec07ffc","160":"0502d6fb8a0a831be4f28459cf95fd05877efaa043d1da15876db566fe1a8bce","161":"86522863c43bfe9e90a427222328e138cbd686bb6213fdf14793f7b04e8d67b9","162":"3cf7daad4362c039ca91dc7bccac8d7dbf70b11714ae5261d5c51af72e2dc651","163":"cddad77df97a9c5bbd7b057ae110534aa052c89a86976445edd504b408cdde29","164":"53b6b67e82830f3a68db58d40df249cbd8d607b12686e3eaa3b420a07a25ea8c","165":"f592c2269a8efbcf04ff6a7b7237223ccc09413c727dbd8c6bcb1f6571e82888","166":"85dba8fdc8a3b28b2f291b955507ace2e80c2c83baa9063f7084a2431ae734d6","167":"12d547082f6a26df4995a854f0a1d7a780db04c5c6e8e258f28ac49bbd77c30a","168":"f2edf3ac0f2bb334908a7b38689e4bff1663cd89ed818bebc4d49d52c565f466","169":"766499dcaf301a1d33c1d09aa35f49b28a2cc0162bf27c2b73707928990ff348","170":"f00957ff531ea97f90d4f225fce9a5f4e56a7e712f5f7e990ddf3725e6b87006","171":"a763661e06e0fb74773daf2f7a3c20f821b7297640c3f2cd4b19f05fbaa7ddf3","172":"05f79aa47fed0c5b79961365aa6dc8c95ee98109ba35de63290275474bd836d0","173":"2418372503d4b98c15e45b641acea0294662f03944178d6e7dc3c0c90b0e7ec4","174":"c4568ff6ebcb156b9c4ee2d44c421145ed0adfa5594e0d76de6038d7d619e8e1","175":"c1197788a26b548830321da02cff9697cb239b59277cfa40929df22bd8023429","176":"623ed4eac9e2ba25f86d2534d0f04c80fa3425792f9394b0da1563ebf64eb0e5","177":"a5870a0b3482f398c27037795f71a3f15ec1871b73ff86ed1bbca77626229760","178":"e37b4940719b34845998db074de6ea8825dd952392d450194e84807ce5444f3f","179":"484b7afb3d301dc7cad4bc176d7a6502c636213d8af5fada39f7bea8b1b368c8","180":"9cf6a716ee89775259a9e3acbcbd7b88678a1cea2669ded3cfb816bcf2ce0834","181":"584f8a154555c74f19222580536e514fa8dda90eeb1d0e62e79d6df8b0721c9d","182":"9b79201476a7e3e2af48cb9e75acce536ce7b18198cd23be206af1c1d2e6f793","183":"0207ec8e8cf7b0c49f2a7b25b15f39bc11906bb3bf477c40c3b7b585b9e59605","184":"66efe97559825d77b1a52e4a28742ce80cd0e3672aea98dbc5cc206471e0c906","185":"9e12c030e07d44a419aefca24320923f92f013a5a6417451722c55bdfd84e4fd","186":"aba544791f870decf88da5806f08788d7001cc78bede985a07f8c6885b139aea","187":"a863c3c6f4af729ee625b3d5656cc6e5821937d91898e2d426ffcbbc70d308a1","188":"1589412222447c22d0b71151392852a0bc28ddf0d52e947958175806528175ed","189":"804292b80441414fdd90f38f38dabe3b3e3cbeb1468d8d6ad3502d20a19309c1","190":"54ebbe189fdbc4bae7b5abad1454b2c0006eb337f563912dbdd87b664614f7ec","191":"42045d9138a88282f6d208c2c0018d7f4297ae6144dc6e40a10a7e0a35f522b2","192":"c71371f1e87889f115f02965d5a2cb8c2a5b9b0232a4608d62e9271158637330","193":"f2038fdf4108e253d13f2e9849a4e98a4b7a73327f5f18f5935724e5546b8f24","194":"025810339778f33456c8b27f4cc6a9e71ef76ba6cc504ae549c0c7653f9198f4","195":"60e17c89f1fb9f22ac81ea5fb8c35dbcfb9500ba5cfa9638d49a2bb2480a2791","196":"40b0d0b95bfe9f81a2c1c184b269940241012d4c5ebd3fe6ad1b2293f7540aa7","197":"4e02a0e369d5e6256df310275fb0e27fdfb5e9b800b520fc65169c3e58823639","198":"1262e4e7c00e1e4e7bd86cea979ab73f8b3a3978a65960385fa7a9b7ffacac58","199":"ec4bc798c7cfeed5ce82b36f5861f0e9a4a71d19d92acd02c68aeb22fe7f5454","200":"b50860eb6f8ca3dd7f3559de45d4d56edcf6c9034bd3ffdf18dc816d63480285","201":"357d4560f4297b289924cff51003df4326bcc57e87a9b14656c40bf7f8404d7b","202":"eebdef3fbd3a8d67ba940e4c7853372d8266e12997a45166917092f52fb6ddac","203":"6c6e065b6a8684504905a33e579386b95e266ebf2221425c30cdf88063465e25","204":"c753d88f59ad2953a28a11043befa6050c13e6f055e706b4602b7e216c30deda","205":"69a5c44c718c6ac24d00b95972403780d3e9c0b474651d6cb1fe4adc464049aa","206":"e1757b6a5963c622f80c9b2404914855e095c585001562c3fabbc3178cdbbce2","207":"351e840184d54255e6e3c4e0a27af92d3782d006a01657cfe80ed0cf82c6398f","208":"8f6081c6f42baff1906dde7060141881fb2f5a9582ab940a58d6e0686f91e4f4","209":"b28933163f3d5e985eb27cc6b40be82f87c71280a1c3a07cc25795e8b10f0aea","210":"dcbc8657edf31c3b7c6c2b4cbc8d2c2d330aef637cfb02f0f4bb4097bba79bc3","211":"fbc803cbb049e98858fb92419266270f6214e533ee6ad1d75738193e6c419f1d","212":"92e7fecd53775c2b426fcafbf8271ec162ef91f78c567e3af77720536baf1fdf","213":"4ec1dbbbbdd9e90b53134f10032f3ba58b0c4978102501965b47dd34396da5cd","214":"b81193565e0d28e56380c403b6382940edd57e72a2bc0670ee5d18438eea7172","215":"ef355d33cf4ea6271deb656a41656b3db442c84691eb82c1f8be911ed4927201","216":"5cd8d7152811a053c354e6c29998b8e8b0fb7c78f6005cba7875f9ed474d0e66","217":"250655aed7c29258a0e0cbc444df43e61f822df246c4a7df3f4e1a8af9a05815","218":"0ba70bab174031fa9ce2d8446f162ab35e1d527560d8a6f1ee9a860dcb110349","219":"3ba43bd7a53078318f279937c84bde7b432b35dfb8f14858dce86bdf1a8dd201","220":"a27a29e4511ef4d4a7c19d9f8773ad6d39c48a153e0e97fe9d9551038b2b34ed","221":"24ca191567f29938be0c37c01586060a7eb812f4e50c1d9849f5d2b8e450b0be","222":"5efdfb62cf3075f0e65e49ce33ec4929ed75a6763bb27744ba082eba3568dfcf","223":"6077c6641926ebd7f2ce07e942c4a33c12f5c2347152edaaaa731344c0e10709","224":"a4c135c15e7d2944fb543914ad2b28b78444f010c4c9c723a712f4854dcf9622","225":"33ffad46d60f528ba6076dabaa6eee58e62ec858bdc6972d87c7cfaf0cdc1bc5","226":"45497fe9eb3f353af9a1036822832938492e659f986e84111ee6da53ee627e3d","227":"5d292830b9d3a02c7336517878710bc1d9df47011955f5cac486440fca3643c8","228":"1c7a81354216833385b6e76037192b61193c5c1cce20971f39b8fe207ee6ac05","229":"b21fc27fe3f075f456d6344909de2c23237785083ce5834e32382f0d97cb0b27","230":"e3ce917a2a950e2f18466ca4a62f0ab9b97a2e6f7aecdb1ee7c5c1a1d584f4ed","231":"7f9032be3d965858b72dd02be53a2d2255d9fc561058195b14786b9c8b7a4a2a","232":"8e60ab7305ea4c89a27cdfffc0e30afbf5b59b4d1638e23250aa93f3f426d47a","233":"da0ebc4de7773a663c1dd6648bed05b2975b2c4f016bdebd1a2221b6411501df","234":"43257a79376e501f787f3e6c32ab1d1e0ffe302639e27d3b31c75517f1c781f0","235":"4b7ccb7a342cef5ab344375b4d8172c8c71150d7cd587dd5248c46c3a899314d","236":"de529368ba719b0fbc59a5f34441bb49a5d8678f05a0c572b198f38a2c10b52d","237":"4e51668a18252ba02c20c671cfb21a33f6fd4f56db5ac8209d3961bc9e323369","238":"944f6fe6908b0518a1cabf9ca1e3d9accc225e2adae74d03e780a7cec48fc92c","239":"73df8e8c873bc8afa65ea7e3b3e4adf55ae52e33cb7c1271288acedfbe4154ca","240":"57e066e3435342ffcb949d64d9890b712275d6465d9f2959664dc38f337be688","241":"352818783455004d2d59facd91d300fef9398775251cbb0007b82716de0ce8e8","242":"d1bb1f892a904ff2a76c1c5004306507e8ba2ada96c216022012ae6f68e1281b","243":"7ddd2cf3909859bbdfd41d1982f656e0b331b600d3fa042f9b42a4fa00f347df","244":"3117f7e358c26fb825e2f85516668a4545026e693b3dba070537c7a99b37a8b9","245":"bd2cbc131b1e13f521a5172c787bc95244d3b1d26af6f91806e1e88bdcfa27f9","246":"d5593f7509c259fffb5cb1479aca0d90413aeec4538e1497e5af48276aa14459","247":"e898992c1e083652abbea99e92de8bf386b7346b6aaba9f311fbf6ad4ffe4639","248":"2f43f6e16a8aa8e7f652786b25ee30b52d3275802c0fcfaac6926edd702c4293","249":"4f7aa1d780344de183d005043d766f7261b2e72d81c74ddac2b7e9ef9e7c38cb","250":"c567ea30636794d1b7438a83e21ca65f2373d6ee7e9df617df3c8b28b9e3d82a","251":"5dd0ac3186238d0038874467c072c61e5256efb5ae60ed851dcda87571e7898e","252":"7361e5bfcbd24c4fd67843e3eede17798e0d293facb263ed6652c685f16dcd7a","253":"a3cf5e0e1584923631103ded984d13d3ca7931e7e6ae0ede8ed9132ad3211784","254":"7f783e81d4b28b26654f4078496595062883a2880efa53191ae983b682bcb817","255":"1842a9415dd5a1b698e7c0eacd882a59631160b118f81bad3ffb0fdf09d025cb","256":"39407df22a4a1a304e5486464b8c4397a8e738bd26dac59491afab96a5c437a5","257":"bd8a9fbbccf6e3b40cb43b7c67f9820b4bebf243f90f6a48d697a4143970f62b","258":"aafc18ce1fb98aea7134febc740e90a72d329f6f56ad6ac83d5ba67d469e18e4","259":"3b634c4a03a1a3211dce549b7c2c79d3ce4cfa105a252a0c40f15d1f13789764","260":"e3db472f91adf98ca192a5c2059488440e1c4acba1a47b09d5a2d3fcfb6be92a","261":"7c755ecfb37d9915f274104bdbc6f50a9d58b0f164b7e35b61afcce9cb7881c8","262":"ea6f387e67c115ece0e6475fae33a50e73e770f070340b7106a6c3e5af22a887","263":"400fe38ef8d72110062124d696bf4af7fc8dfaa1f68fec71f8feda234b97e695","264":"ae2f5511e1d1268fd8ca2056a3d6073a0cfacc6242c34d5a88bf81204ab4a6c0","265":"3cb44291371fb5b161c1d7677868122c4f35fcc3b56fe17265c5703d00624665","266":"076ca42edf25287a9a959f9c1e686c12d95de21092db5ead95556c26ba51a15c","267":"c1aba0e038da365a2044749285b337224b1e0f01ab270200b6110db0fd0c69c7","268":"5d8f3a9f24a566f2acb24c06053f5c4416db4b2070f0e73900d24d5169e50ff5","269":"f3fe6ca098ed032c768f42be9cf5bbb4e3e68636c605fcf8342628e2d1bbfad2","270":"7c00e2a25617dde6a870ab8811a061b6bc4377f054b78adf687e41c41983a28b","271":"731b60ea4f1db2a448ded14d378dfd70692b54deb7519d3fc273cb2000d2a069","272":"67f00f9e8e46b314a9eaebea7540651e5a4f1f3859e2db1d315287149ab1aee7","273":"44abac644ad70a924da02a2bb0d8b52684ba5af94154c41b671089386fb4ad66","274":"4ac35b482c636c89a5940db0628200be503a5962513ede17cd62d058309375dc","275":"a993167f1c2a00d2f582f0ac3aecdaa86f1446ea42d2860e0ed4d5781144b7fc","276":"6436515dc253face2af33dd301493d5f094bc5338ed1d19dda70d296b7a9a2dd","277":"9467940be77e01b7cb01f122078f7b2b5fe6dae768f8c105ea0bce7c3d0804fd","278":"4834f75a21bd618809cde624806f369b56aa7dcdff4f59c04f4a9f694d190f36","279":"65d28805f176dd7ab22dc373a85557dc40673f3dcd59b709ad1cd770d2e9ad2b","280":"d4c79bd617b565fcf3722a2fb2eeab06e3aa94d2bc26f98188b71328d304c86f","281":"fdd85ddc17a6526e6d49fc5c5c46ca8ba46891e57190d6621ec8419fb9b92e7c","282":"ce69cd1f36e5cc7e79c9983287f0562f5624611a5e8b6062168a6a14d53289e5","283":"74f2052ddccfafdc82c02533a3e79adf31f4d7af71e0f730bd7217aca4b67938","285":"82189cf38b29d90021a3f4e8760378f9c7bc1c2931e9a23e9cb0cca279c91bff","286":"e8406189890c5a11373fad5b71029bc142f0c96718fde5c46e14b0571ec611c2","287":"c6e7d3986c0014a9bee79c892e8d3ba10908ec30c3a60965e543fc0149c99bc8","288":"fa5f97bd1a501321bed70d083442c1fad0b4a0b8769f4613fc9b063d611d76fa","289":"1c3614acbe9fd0c75dd0a479b487621ed27c6b00d3afe2b2678393a6c4c18f3a","290":"3033f6da8411a781e4269ad3cbb6b1ec39842e17ac488a19708d43aba359b387","291":"41b389d677ec4adf7ca65e0146fbe1fe9b28ba5cfe73ab4b31db462fccd897bf","292":"244d9bb58ec67bc40245e99cfff9b2abbb35b2f7105762d2a863d9d1af913f53","293":"9c82c2e239684826551b1231f59044c37c50fdb9fd111d81f11eedb8b91fe827","294":"974eeb8857e3cb20914310e692c6eedbefb124ef1f94421a5721bc0489106fae","295":"4e144636127ec23898df324e7f79e327a2df9a55b0abea81d3e0fc45f699d18a","296":"5c7478f68e358b10d59b11d52456569d16dbe1039734c44f3b483cdb48add334","297":"da93cef1e134e28c04ae10dd593dd98a98de676f2515a025f3b1e5f16d2fc8ca","298":"25d1194b25c4f91a0f8d6f7fe1630a9deb249a948d5e8e5538ee6aba6389aa1b","299":"461b5537059a192a8fb7a2a581936575cf96f7e42d3261ba2b1521adc47ed963"}
# 4 目标行基线原字节（b64；行号见 _TARGET_LINES）。
_ORIG_ROWS_B64: dict[str, str] = {"F17-word":"RjE3LXdvcmQsRjE3LOeUqOaIt+W3suWGu+e7k09wZW5Db2Rl5Y6f55SfVUnmnI3liqHpl63ljIXvvJvljp9SZWFjdC9UaXBUYXDkv53nlZnmnaXmupDmioDmnK/mj4/ov7DvvIzmlLlTb2xpZOS4uuW3suWGu+e7k+aKgOacr+agiO+8jOS/neeVmeWKn+iDveivreS5ieS4jeensOWOn+WKn+iDveWIoOWHj++8m+azleW+i1dvcmRXUFPnvJbovpHni6znq4vvvIzkuI3nrKzkuoxET0NY57yW6L6R5ZmoLGRlc2t0b3A7c2VsZmhvc3Qsd29yZCxwcm9kdWN0LCJFMDIsRTAzLEUyNiIsLFBFTkRJTkdfT1dORVJfSU1QTEVNRU5UQVRJT04sUEVORElOR19PV05FUl9JTVBMRU1FTlRBVElPTizpqozmlLbml7blh4bnoa5jb21taXQvcGFja2FnZe+8m+acrOi9rumdmeaAgXJlZnPkuI3or4HmmI5jbGVhbiwsLCxldmlkZW5jZS9GMTcvd29yZC8sTk9UX1JVTiwsQjAtQjM=","F46-word":"RjQ2LXdvcmQsRjQ2LOS4pOWuv+S4u+WIhuWIq+eUn+aIkOWOn+eUn+S/ruiuouOAgemDqOWIhuaOpeWPly/mi5Lnu50v6YeN6L295Zue5rWB77ybY2Fub25pY2Fs5LuF5o6l5Y+X5oCB77yM5aSN5p2C6KGoL+mhteecieiEmi/ln58v6ISa5rOoL+eOsOWtmOS/ruiuouecn+WunuaWh+S7tumqjCxkZXNrdG9wO3NlbGZob3N0LHdvcmQscHJvZHVjdCtoYXJuZXNzLCJFMTIsRTEzLEUxNSIsLFBFTkRJTkdfT1dORVJfSU1QTEVNRU5UQVRJT04sUEVORElOR19PV05FUl9JTVBMRU1FTlRBVElPTizpqozmlLbml7blh4bnoa5jb21taXQvcGFja2FnZe+8m+acrOi9rumdmeaAgXJlZnPkuI3or4HmmI5jbGVhbiwsLCxldmlkZW5jZS9GNDYvd29yZC8sTk9UX1JVTiwsQjAtQjM=","F52-word":"RjUyLXdvcmQsRjUyLFdvcmTkuI5XUFPnnJ/lrp7mjqXlj5flkI7lm57or7vmlrBDQVMvdmVyc2lvbu+8jOacquaOpeWPl+S4jeaUuWNhbm9uaWNhbO+8m+ebuOWFs+e0ouW8lWJhc2lz5aSx5pWI77yM5Lq65pS55LiN6KaG55uWLGRlc2t0b3A7c2VsZmhvc3Qsd29yZCxwcm9kdWN0K2hhcm5lc3MsIkUxMixFMTMsRTE1IiwsUEVORElOR19PV05FUl9JTVBMRU1FTlRBVElPTixQRU5ESU5HX09XTkVSX0lNUExFTUVOVEFUSU9OLOmqjOaUtuaXtuWHhuehrmNvbW1pdC9wYWNrYWdl77yb5pys6L2u6Z2Z5oCBcmVmc+S4jeivgeaYjmNsZWFuLCwsLGV2aWRlbmNlL0Y1Mi93b3JkLyxOT1RfUlVOLCxCMC1CMw==","E13":"RTEzLCxwcm9wb3NhbC9iYXNlL2Nhbm9uaWNhbOWFseS6q++8m1dvcmRXUFPlkITlpI3mnYLmlofku7bkv67orqLpg6jliIbmjqXlj5flm57mtYHjgIHmqKHmnb/nu5PmnoTop4bop4njgIHkurrlrqHlkI7mraPlvI/lhaXotKYsLCxwcm9kdWN0K2hhcm5lc3MsIkUwNSxFMTEsRTEyIiwscHl0aG9uIC1YIHV0ZjggdG9vbHMvUEVORElOR19PV05FUl9lMTNfZTE0X2NvbXBvc2l0ZV9yZWNvbi5wee+8iOaWsOW7uuWkjeWQiOW3peWFt8K36YCQ6KGM5aSN6LeRIFcyYiDlt7IgVkVSSUZJRUQg6Z2iIHJlY29uIOWFqOmbhiAxMyDooYzlubbpgJDooYznmbvorrAgY29tbWFuZC9jd2Qvc3ViamVjdC9leGl0wrfor4Hmja7oh6rotrPlpI3liLYgZXZpZGVuY2UvRTEzfEUxNC88cHJvZmlsZT4vwrfnvLrpnaLlpoLlrp7lhbflkI3kuI3ooaUgUEFTU++8ie+8m0UxMyDpk74gNyDooYzvvJ1GNDcvRjQ4L0Y0OS9GNDYtd3BzK0Y1Mi13cHMvRjE3LXdwcy9GNTArRjUxL0Y1MyxqdXNjaXRlIOS4u+S7k+agke+8iOWQiOW5tiBXMy1VMjUg5ZCOIGN3ZMK36LSm5oi/5aSN6LeR77yJ77yL5YiG5pSvIHdvcmt0cmVlIC5sb2NhbC93b3JrdHJlZXMvdzMtdTI177yI5bel5Y2VIGNhbm9uaWNhbCDlrp7ot5EgaGVhZCA0Y2I5MDI2wrcyMDI2LTEwLTE4VDEwOjEyIOmdmem7mOacuuWZqO+8iSxqdXNjaXRlIOWIhuaUryB3My11MjXvvIjmlLblj6MgY29tbWl0IDBkM2YzMGTCt+S4u+WQiOW5tiBjb21taXQg6KeBIFVuaXRSZXN1bHTvvInvvJtXMmItVTA1L1UxMS9VMTIvVTE0L1UxNS9VMTYvVTM2L1U0OSDlt7IgVkVSSUZJRUQg6Z2iIHJlY29uIOWFqOmbhuWPquivu+Wkjei3kSxFMTQg6ZO+IDYg6KGM5YWoIFBBU1PvvJ1SRUNPTl9PS++8m0UxMyDpk77lpoLlrp7vvIh3cHMg5a6/5Li75ryC56e76KGMIEZBSUxfTkFNRUQg5Zyo5qGI5LiN6KGlIFBBU1PvvIksMizlt6XljZUgY2Fub25pY2Fs77yIMjAyNi0xMC0xOFQxMDoxMiBoZWFkIDRjYjkwMjbvvInvvJpFMTQg6ZO+IDYg6KGM5YWoIFBBU1MgUkVDT05fT0vvvIhGNzAgMzc4LjcvNDM4LjhzwrdGODcgMjI0LjdzwrdGODIgMzA1LjlzwrdGMjUgNDQuN3PCt0Y4OCAyMS4yc++8ie+8m0UxMyDpk74gNi83IFBBU1PvvItGNDYtd3BzK0Y1Mi13cHMgZXhpdD0yIEZBSUxfTkFNRUTvvIhjMTYg6Ieq5bu65aSN5p2C5Lu25Z+f5L+d55yfIGZsZENoYXJfaW4gMTIgdnMgYmVmb3JlIDbCt1dQUyDlrr/kuLvmvILnp7vlnKjmoYjvvJpXMmItVTQ5IEEvQiDmjqLpkojlt7Llrp7or4EgbWFpbkBlOWExZmQ0IOWOn+W3peWFt+WQjOi0pcK35Y+w6LSm6KGM5LiN5Yqo77yJ77ybcnVuLTHvvIgwOTo0MO+8iUY3MCDlj4zot5EgNjAwcyDotoXml7bvvJ3lubbooYzotJ/ovb3kvKrlvbHvvIjlkIznqpcgYnVuIGluc3RhbGwgMjEzMiDljIUrdHNnb8OXNCDno4Hnm5jkuonlpLrCt+W3peWFt+ehrOe8lueggSA2MDBzL+WtkOi/m+eoi++8iWNhbm9uaWNhbCDpnZnpu5jmnLrlmajnnJ/ot5EgUEFTUyDmtojop6PCt+S4pOi9ruWvueeFp+eVmeivgeOAgui0puaIv+WQiOW5tuWQjuS4u+S7k+agkeWkjei3ke+8iDIwMjYtMTAtMTlUMDc6MzUg5oC7IDExMzAuOHMgMTMg6KGM77yJ77yaRTEzIFJFQ09OX05BTUVEX0ZBSUxVUkVTIDYvN++8iEY0NyAxNi44L0Y0OCA3LjYvRjQ5IDM2LjQvRjQ2LXdwcytGNTItd3BzIGV4aXQ9MiBGQUlMX05BTUVEIDkzLjJzIOWQjOi0peebuC9GMTctd3BzIDI2LjEvRjUwK0Y1MSAxNy4wL0Y1MyA4LjfvvInvvItFMTQgUkVDT05fT0sgNi8277yIRjcwIDI3Ni4wLzI3NC45wrdGODcgMTQ4LjbCt0Y4MiAxODMuM8K3RjI1IDI4LjfCt0Y4OCAxMy4x77yJ4oCU4oCU5LiOIGNhbm9uaWNhbCDpgJDooYzlkIznm7gsZXZpZGVuY2UvRTEzL2Rlc2t0b3AvO2V2aWRlbmNlL0UxMy9zZWxmaG9zdC87ZXZpZGVuY2UvRTEzL2UxMy1jb21wb3NpdGUtcmVjb24tMjAyNjEwMThUMTAxMjI3KzA4MDAuanNvbjtldmlkZW5jZS9FMTQvZGVza3RvcC87ZXZpZGVuY2UvRTE0L3NlbGZob3N0LztldmlkZW5jZS9FMTQvZTE0LWNvbXBvc2l0ZS1yZWNvbi0yMDI2MTAxOFQxMDEyMjcrMDgwMC5qc29uO2RvY3MvY29uc3RydWN0aW9uL2V2aWRlbmNlL0UxMy9jaXRhdGlvbi1zdXJmYWNlLXBhdGNoLyxJTVBMRU1FTlRJTkcsIkUxMyDmlLblj6PogZrlkIjlvJXmlofkuI3ph43pqozkuI3pobbmm7/vvJtGODIt5aSN5qC4L+mHjei3kS/kurrmlLnvvIh3MmItdTMxIHJldmlldy1vcHMg6Z2i77yJ5LiN5Zyo5bel5Y2V5Lik6ZO+5p6a5Li+5LiN56ew6KaG55uW77ybRjQ2LXdwcytGNTItd3BzIOWUr+S4gOi0peebuO+8nVdQUyDlrr/kuLvmvILnp7vlnKjmoYjvvIhXMmItVTQ5IEEvQiDlrp7or4Hljp/lt6XlhbflkIzotKXCt+mihOWtmOeOr+Wig+mdnuWbnuW9ksK35Y+w6LSm6KGM5LiN5Yqo77yJ77yLV29yZCDljYrovrnnvLrkuK0gMjAyNi0xMC0xOCDlpI3moLjmjqLpkojokL3nm5jvvIhIS0NVIFdvcmQuQXBwbGljYXRpb24gUHJvZ0lEIOaCrOepuuWjs8K3Q0xTSUQgMDAwMjA5RkYgTG9jYWxTZXJ2ZXIzMiDlkIjlubbop4blm77lhajnvLrluK3vvItXSU5XT1JELkVYRSDlhajnm5jpm7blkb3kuK3vvItDbGlja1RvUnVuIOaXoOazqOWGjO+8m+WvueeFpyBLV1BTLkFwcGxpY2F0aW9uIOWcqOWGjO+8ieKGkuijgeWGsyM0IHdvcmQg5a6/5Li76KGM5oyCIFc0LVMyIOe7tOaMgcK3RTEzIOWmguWuniBJTVBMRU1FTlRJTkcg5b6FIHYyIOazoiB3b3JkL1dQUyDlrr/kuLvooaXpnaLvvJswMTcg5byV55So5Y6f55Sf5ZGI546w6Z2iIHBhdGNoIOW3suW4pu+8iG9jMjgg5Li75qOA5Ye66Zu26Kem56KwIDAxMi0wMTYg5Lqk5LuY5oCB77yJ5L2G6Leo5Y2V5YWD57y66Zm35Zyo5qGI77ya5bey5bm2IG1haW4g55qEIDAxNS1mNTMoVTQ5KSDkuI4gMDE2LWY4NChVNDgpIOWFseS6q+aWh+S7tuWQjOmSieS6kuaSnu+8iDAwMS0wMTQrMDE1IOagiOS4iiAwMTYgYXBwbHktY2hlY2sg6LSlwrflkIzkuInmlofku7YgbGVnYWwtd29ya2JlbmNoLnRzeC9tYWluIGluZGV4LnRzL3swMTQsMDE1LDAxNn0g5peg57qv5bqP77yJ4oaS5aSE572u5b2S6LSmL+S4u+aOp++8iOivgeaNriBldmlkZW5jZS9FMTQvY2l0YXRpb24tc3VyZmFjZS1wYXRjaC/vvIkiLEIwLUI0"}
_TARGET_LINES: dict[str, int] = {"F17-word":30,"F46-word":85,"F52-word":97,"E13":284}

STATUS_IDX = 15        # LEDGER_FIELDS 中 status 列
FAILURE_REASON_IDX = 16  # LEDGER_FIELDS 中 failure_reason 列


class ReconFail(Exception):
    """任一检查 FAIL；CLI 层输出 RECON_FAIL exit 2。"""


def _row_bytes(fields: list[str]) -> bytes:
    """单行 CSV 序列化（QUOTE_MINIMAL，无行尾符）——与台账产物同规则。"""
    buf = io.StringIO()
    csv.writer(buf, lineterminator="").writerow(fields)
    return buf.getvalue().encode("utf-8")


def _expected_word_row(orig_fields: list[str], oid: str) -> list[str]:
    if orig_fields[STATUS_IDX] != "NOT_RUN" or orig_fields[FAILURE_REASON_IDX]:
        raise ReconFail(f"{oid}：基线态非 NOT_RUN/空 failure_reason，拒绝落账")
    fields = list(orig_fields)
    fields[STATUS_IDX] = "EXCLUDED"
    fields[FAILURE_REASON_IDX] = WORD_ROW_REASONS[oid]
    return fields


def _expected_e13_row(orig_fields: list[str]) -> list[str]:
    if orig_fields[STATUS_IDX] != "IMPLEMENTING":
        raise ReconFail("E13：基线态非 IMPLEMENTING，拒绝落账")
    fr = orig_fields[FAILURE_REASON_IDX]
    if E13_ANCHOR not in fr or "A1（2026-10-18" in fr:
        raise ReconFail("E13：基线锚点缺失或已含 A1 注记，拒绝落账")
    fields = list(orig_fields)
    fields[FAILURE_REASON_IDX] = fr.replace(E13_ANCHOR, E13_ANCHOR + E13_INSERT)
    return fields


def _split_segments(raw: bytes) -> list[bytes]:
    """按 CRLF 切行段；校验形状（C0）。返回恰 299 段。"""
    if not raw.startswith(b"\xef\xbb\xbf"):
        raise ReconFail("C0：台账缺 UTF-8 BOM")
    if b"\n" in raw.replace(b"\r\n", b"") or b"\r" in raw.replace(b"\r\n", b""):
        raise ReconFail("C0：存在裸 LF/CR（CRLF 保持被破坏）")
    if not raw.endswith(b"\r\n"):
        raise ReconFail("C0：文件未以 CRLF 结尾")
    segments = raw.split(b"\r\n")
    if segments[-1] != b"" :
        raise ReconFail("C0：CRLF 切分尾段非空")
    segments = segments[:-1]
    if len(segments) != 299:
        raise ReconFail(f"C0：行段数 {len(segments)} != 299")
    return segments


def _segments_identifiers(segments: list[bytes]) -> dict[str, int]:
    """行段 obligation_id 索引（首列，CSV 感知引号；BOM 仅在表头段）。"""
    ids: dict[str, int] = {}
    for idx, seg in enumerate(segments):
        text = seg.decode("utf-8-sig")
        first = next(csv.reader([text]), [""])[0]
        if first:
            if first in ids:
                raise ReconFail(f"C3：obligation_id 重复：{first}")
            ids[first] = idx
    return ids


def _expected_segments_after_apply(segments: list[bytes]) -> list[bytes]:
    """基线行段 → 落账后行段（恰 4 目标行变换，余逐字节原样）。"""
    ids = _segments_identifiers(segments)
    out = list(segments)
    for oid in WORD_ROW_IDS:
        orig = base64.b64decode(_ORIG_ROWS_B64[oid])
        if segments[ids[oid]] != orig:
            raise ReconFail(f"{oid}：当前行段≠基线原字节（--apply 仅自基线态）")
        fields = next(csv.reader([orig.decode("utf-8")]))
        out[ids[oid]] = _row_bytes(_expected_word_row(fields, oid))
    orig13 = base64.b64decode(_ORIG_ROWS_B64[E13_ID])
    if segments[ids[E13_ID]] != orig13:
        raise ReconFail("E13：当前行段≠基线原字节（--apply 仅自基线态）")
    fields13 = next(csv.reader([orig13.decode("utf-8")]))
    out[ids[E13_ID]] = _row_bytes(_expected_e13_row(fields13))
    return out


def _check_c1_baseline_lines(segments: list[bytes], ids: dict[str, int],
                             label: str) -> None:
    """295 非目标行逐字节对基线 sha256 清单。"""
    target_idxs = {ids[o] for o in WORD_ROW_IDS} | {ids[E13_ID]}
    bad = []
    for idx, seg in enumerate(segments):
        if idx in target_idxs:
            continue
        want = _LINE_SHA256.get(str(idx + 1))
        if want is None:
            bad.append(f"行{idx + 1}:清单缺行号")
        elif hashlib.sha256(seg).hexdigest() != want:
            bad.append(f"行{idx + 1}:sha 不符")
        if len(bad) >= 5:
            break
    if bad:
        raise ReconFail(f"C1[{label}]：非目标行被改动——{bad}")


def _check_c2_target_rows(segments: list[bytes], ids: dict[str, int]) -> None:
    for oid in WORD_ROW_IDS:
        seg = segments[ids[oid]]
        fields = next(csv.reader([seg.decode("utf-8")]))
        if fields[STATUS_IDX] != "EXCLUDED":
            raise ReconFail(f"C2：{oid} status={fields[STATUS_IDX]!r} != EXCLUDED")
        fr = fields[FAILURE_REASON_IDX]
        if not fr.startswith(ADJUDICATED_EXCLUDED_PREFIX):
            raise ReconFail(f"C2：{oid} failure_reason 非「裁决性 EXCLUDED」开头")
        if "A1" not in fr:
            raise ReconFail(f"C2：{oid} failure_reason 未引 A1")
        if fr != WORD_ROW_REASONS[oid]:
            raise ReconFail(f"C2：{oid} failure_reason 与本单落账全文不符")
    seg13 = segments[ids[E13_ID]]
    fields13 = next(csv.reader([seg13.decode("utf-8")]))
    if fields13[STATUS_IDX] != "IMPLEMENTING":
        raise ReconFail(
            f"C2：E13 status={fields13[STATUS_IDX]!r}（须维持 IMPLEMENTING 不假 VERIFIED）")
    fr13 = fields13[FAILURE_REASON_IDX]
    if E13_INSERT not in fr13:
        raise ReconFail("C2：E13 failure_reason 缺 A1 永久结转增补注记")
    for token in ("A1", "永久结转", "W4", "F56"):
        if token not in fr13:
            raise ReconFail(f"C2：E13 注记缺 {token} 指针")


def _check_c3_structure(segments: list[bytes]) -> str:
    text = b"\r\n".join(segments) + b"\r\n"
    rows = list(csv.DictReader(io.StringIO(text.decode("utf-8-sig"), newline="")))
    if len(rows) != 298:
        raise ReconFail(f"C3：数据行 {len(rows)} != 298")
    if any(len(r) != 18 for r in rows):
        raise ReconFail("C3：存在列数≠18 的行")
    by_id = {r["obligation_id"]: r for r in rows}
    f57 = by_id.get("F57-word")
    if f57 is None or f57["status"] != "NOT_RUN":
        raise ReconFail("C3：F57-word 非 NOT_RUN（W4 规划范围，本单不得越界）")
    census: dict[str, int] = {}
    cut_class = adjudicated = 0
    for r in rows:
        census[r["status"]] = census.get(r["status"], 0) + 1
        if r["status"] == "EXCLUDED":
            fr = r.get("failure_reason", "")
            if fr == "裁剪行":
                cut_class += 1
            elif fr.startswith(ADJUDICATED_EXCLUDED_PREFIX):
                adjudicated += 1
    want = {"EXCLUDED": 27, "IMPLEMENTING": 15, "NOT_RUN": 91, "VERIFIED": 165}
    if census != want:
        raise ReconFail(f"C3：census {census} != {want}")
    if (cut_class, adjudicated) != (24, 3):
        raise ReconFail(
            f"C3：EXCLUDED 分类（裁剪行 {cut_class}＋裁决性 {adjudicated}）!=（24＋3）")
    return ("census: EXCLUDED=27（裁剪行 24＋裁决性 3）IMPLEMENTING=15 "
            "NOT_RUN=91 VERIFIED=165（总数 298）")


def _check_c4_e13_basis(rows_by_id: dict[str, dict]) -> None:
    unready = [oid for oid in E13_B2B_BASIS_IDS
               if (rows_by_id.get(oid) or {}).get("status") != "VERIFIED"]
    if unready:
        raise ReconFail(f"C4：E13 B2-b 基础行非 VERIFIED：{unready}")


def _check_c5_registry_validate() -> str:
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", str(REGISTRY_PATH), "validate"],
        cwd=str(REPO_ROOT), capture_output=True, text=True,
        encoding="utf-8", errors="replace")
    tail = (proc.stdout or "").strip().splitlines()
    detail = tail[-1] if tail else f"exit={proc.returncode} 无 stdout"
    if proc.returncode != 0 or "PASS" not in (proc.stdout or ""):
        raise ReconFail(
            f"C5：registry validate exit={proc.returncode} 非 PASS——"
            f"{detail}；stderr={(proc.stderr or '').strip()[:400]}")
    return f"registry validate：{detail}（exit 0）"


def run_verify() -> int:
    raw = LEDGER_PATH.read_bytes()
    checks: list[tuple[str, bool, str]] = []
    try:
        segments = _split_segments(raw)
        checks.append(("C0_file_shape_crlf_bom", True,
                       "BOM＋299 CRLF 行段＋末尾 CRLF＋无裸 LF/CR"))
        ids = _segments_identifiers(segments)
        missing = [o for o in (*WORD_ROW_IDS, E13_ID) if o not in ids]
        if missing:
            raise ReconFail(f"C2：目标行不在台账：{missing}")
        _check_c1_baseline_lines(segments, ids, "verify")
        checks.append((
            "C1_baseline_295_lines_byte_identical", True,
            f"295 非目标行逐字节==基线@{BASELINE_COMMIT}（逐行 sha256 清单）"))
        _check_c2_target_rows(segments, ids)
        checks.append((
            "C2_four_target_rows_a1_adjudicated", True,
            "F17-word/F46-word/F52-word=EXCLUDED（裁决性 EXCLUDED 引 A1）；"
            "E13 维持 IMPLEMENTING＋A1 永久结转注记＋W4/F56 指针"))
        digest = hashlib.sha256(
            b"\r\n".join(segments) + b"\r\n").hexdigest()
        detail_c3 = _check_c3_structure(segments)
        checks.append(("C3_structure_census_f57_untouched", True,
                       f"{detail_c3}；文件 sha256={digest[:16]}…"))
        text = b"\r\n".join(segments) + b"\r\n"
        rows = list(csv.DictReader(io.StringIO(text.decode("utf-8-sig"),
                                              newline="")))
        _check_c4_e13_basis({r["obligation_id"]: r for r in rows})
        checks.append((
            "C4_e13_b2b_basis_verified", True,
            "E13 B2-b 基础六行 VERIFIED 在账（F47×2/F46-wps/F52-wps/F53×2）"))
        detail_c5 = _check_c5_registry_validate()
        checks.append(("C5_registry_validate_pass", True, detail_c5))
    except ReconFail as exc:
        message = str(exc)
        checks.append(("FAILED_CHECK", False, message))
        print("RECON_FAIL")
        for cid, ok, detail in checks:
            print(f"[{'PASS' if ok else 'FAIL'}] {cid} — {detail}")
        return 2
    print(f"W2b-U60 A1 裁决落账 recon（基线@{BASELINE_COMMIT}，"
          f"台账 sha256={hashlib.sha256(raw).hexdigest()[:16]}…）")
    for cid, ok, detail in checks:
        print(f"[PASS] {cid} — {detail}")
    print("RECON_OK")
    return 0


def run_apply() -> int:
    raw = LEDGER_PATH.read_bytes()
    try:
        segments = _split_segments(raw)
        ids = _segments_identifiers(segments)
        _check_c1_baseline_lines(segments, ids, "apply")
        expected = _expected_segments_after_apply(segments)
    except ReconFail as exc:
        print(f"APPLY_REFUSED：{exc}")
        return 2
    if bytes(b"\r\n".join(expected) + b"\r\n") == raw:
        print("APPLY_REFUSED：台账已是落账后态（幂等拒写；请用无参复验模式）")
        return 2
    LEDGER_PATH.write_bytes(b"\r\n".join(expected) + b"\r\n")
    print(f"APPLIED：恰 4 行落账（{', '.join(WORD_ROW_IDS)} 翻裁决性 EXCLUDED＋"
          f"{E13_ID} A1 永久结转注记）；复验请无参运行本工具")
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    args = list(sys.argv[1:] if argv is None else argv)
    if args == ["--apply"]:
        return run_apply()
    if args:
        print("用法：python -X utf8 tools/recon/PENDING_OWNER_a1_word_rows_exclusion_recon.py "
              "[--apply]", file=sys.stderr)
        return 2
    return run_verify()


if __name__ == "__main__":
    sys.exit(main())
