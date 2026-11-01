"""F102 商标/电商取证八平台——合成先行确定性取证链公开面（W5-U05）。

06 行 V7-102/F102 acceptance：八平台范围冻结真实采集出处/时间/凭证；
失败不假造证据。owner=product；python_entry=UI_HOST_OR_NEW_PRODUCT
（不接入 legal_entry、不冒已有业务入口、不创第二 Agent loop）；
prerequisites E10,E11,E12,E17,E21,E24；legacy_semantic_links F65（浏览
器 CDP 遥控）/F96（技能执行合同）——两者 B5 未施工，本面只记名不消费。
00-总协调 §6.1 裁决#13-19（00-总协调.md:254）：W5 商业/基建（含八平台）
统一合成先行，真实平台采集 v2 商业化时补——本波唯一执行态。

八平台范围闭集冻结（来源钉定：LexLex skills/trademark-evidence-collection
『默认全平台搜索』八平台清单——竞品情报 2026-10-11 取证件；authority/06
V7-102 行『CNIPA+淘宝京东等八平台』；登录要求沿源件参考表冻结）。

合成先行结构（W5-U03 F33 同族：唯一通道＝注入 transport，本面零网络）：

- 平台适配器缺席即结构性不可达：transport=None →
  F102_ADAPTER_ABSENT。真实平台端点禁编 URL（W4-U40 纪律），端点属
  商业化适配器工单——客户端未建不可能自采，零 URL 字面量。
- 本地受控合成采集目标（SyntheticCaptureTarget）：进程内确定性合成页
  （平台内容高常量钉定，覆盖单页/两片拼接/多片拼接三路径），唯一入口
  measure/fetch_slice；登录闸（客户端预检零请求＋目标侧同闸防线）、
  WAF 闸（检索面：同平台两次检索间隔 < MIN_INTERVAL_S 拦截——源件反
  爬攻略：CNIPA 频繁请求触发 WAF、平台间 2-3 秒间隔）。
- 确定性取证链（截图拼接 PDF）：测量（小视口）→定尺寸（视口上限
  10000px）→逐片截图（>10000px 两片拼接、>20000px 多片拼接、重叠裁
  切）→拼接整幅→按页切分＋页号标记带→最小确定性 PDF（DeviceGray
  8bit FlateDecode，无 /ID 无时间戳，E12 纪律）→页清单金标（页号/
  出处 bbox/页号带 bbox，E12 bbox 纪律版本沿袭）。
- E17 EvidenceAttempt 语义（W4-U40 先例逐字沿用）：有凭据（真实回执）
  才记取得——仅 EVIDENCE_SEALED 携 trajectory/credential/pdf_sha256/
  page_manifest；一切失败路径（适配器缺席/未登录/间隔预检/WAF 拦截/
  回执残缺/传输异常）四值恒 None，绝不返回部分或合成证据 PDF（失败
  不假造证据）。
- 出处/时间/凭证绑定：source=回执 provider（合成目标具名 synthetic，
  usable_as_real_platform_evidence=false）；retrieved_at 出自回执（注
  入时钟，非墙钟）；seal=sha256(canonical JSON)（同回执两跑同字节同
  seal）；trajectory 逐片 sha256 绑回执栅格字节。

红线：零网络零子进程零文件 I/O（AST 闭集见 recon/test）；金额不入场；
确定性零模型；真实平台采集＝v2 商业化时补（RECOVERY_POINT 具名）。
"""
from __future__ import annotations

import hashlib
import json
import time
import zlib

SCHEMA = "juscite-f102-platform-evidence/1"

# 页清单金标版本（沿 E12 bbox 金标纪律：页号/页眉/内容带 bbox 入账）。
PAGE_BBOX_GOLD_VERSION = "juscite-f102-page-bbox/1+e12-discipline"

# 真实平台采集回收点（裁决#13-19 合成先行；具名留此，商业化时补）。
RECOVERY_POINT = ("真实平台采集 v2 商业化时补：真实端点出自平台参考件与"
                  "授权方文档冻结常量（禁编 URL）、E24 授权闸先行、真实账"
                  "号/session 与 WAF 对策随适配器工单；本波合成先行（00-"
                  "总协调 §6.1 裁决#13-19）。")

# ---------------------------------------------------------------------------
# 八平台范围闭集（冻结常量；顺序=闭集登记序，与采集序分离）
# id, 名称, 类别, 需登录（沿源件参考表）
# ---------------------------------------------------------------------------
EIGHT_PLATFORMS = (
    ("cnipa", "国家知识产权局（CNIPA）", "official_trademark_office", True),
    ("baidu", "百度", "search_engine", False),
    ("taobao", "淘宝", "ecommerce", False),
    ("tmall", "天猫", "ecommerce", False),
    ("jd", "京东", "ecommerce", True),
    ("pdd", "拼多多", "ecommerce", True),
    ("douyin", "抖音", "social_media", True),
    ("xhs", "小红书", "social_media", True),
)

# 默认采集序（源件反爬攻略：电商平台→社交媒体→百度→CNIPA 收尾——
# CNIPA 需 SSO 手动登录且易触发 WAF，放最后）。
DEFAULT_CAPTURE_ORDER = (
    "taobao", "tmall", "jd", "pdd", "douyin", "xhs", "baidu", "cnipa")

# 合成页内容高（逻辑 px；覆盖三路径：≤10000 单片 / >10000 两片 /
# >20000 多片；baidu 3580 沿源件示例值，CNIPA 详情页超 20000 沿源件
# 描述）。合成世界常量，非真实测量。
PLATFORM_CONTENT_HEIGHT = {
    "baidu": 3580, "tmall": 5200, "taobao": 6400, "pdd": 11200,
    "jd": 12480, "xhs": 21500, "douyin": 24000, "cnipa": 26800,
}

# 采集策略常量（沿源件管线冻结）。
VIEWPORT_H_CEILING = 10000   # 视口高度上限（源件硬限制）
MEASURE_VIEWPORT_H = 900     # 测量用小视口
MULTI_SLICE_THRESHOLD = 20000  # 超此高度走多片顺序拼接
MIN_INTERVAL_S = 2           # 平台/取片最小间隔（源件反爬攻略 2-3 秒）
RASTER_SCALE = 8             # 合成栅格降采样（逻辑 px / 8 = 栅格行）
RASTER_W = 256               # 栅格宽（32B 摘要 ×8）
PAGE_H = 339                 # PDF 页高（栅格行；A4 纵横比 @RASTER_W）
HEADER_ROWS = 8              # 页眉标记带高（栅格行）
NUMBER_BAND_H = 6            # 页号标记带高（栅格行）

SYNTHETIC_PROVIDER_ID = "synthetic-local-target"

# 条目状态闭集；值字段只允许在 EVIDENCE_SEALED 非空，其余恒 None。
ENTRY_STATUSES = (
    "EVIDENCE_SEALED",
    "F102_ADAPTER_ABSENT",     # 平台适配器未接线（禁编 URL，不可能自采）
    "F102_PLATFORM_UNKNOWN",   # 平台不在八平台闭集
    "F102_KEYWORD_REQUIRED",   # 关键词缺失/非串
    "F102_LOGIN_REQUIRED",     # 需登录平台无 session（客户端预检＋目标侧防线）
    "F102_PACING_VIOLATED",    # 客户端间隔预检（零请求发出）
    "F102_WAF_INTERCEPT",      # 目标侧 WAF 拦截回执
    "F102_RECEIPT_INVALID",    # 回执残缺/类型不符
    "F102_CAPTURE_FAILED",     # 传输异常（失败不编轨迹）
)
VALUE_BEARING_STATUSES = ("EVIDENCE_SEALED",)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))


def _fail(platform, keyword, status: str, detail: str) -> dict:
    """失败条目：E17 语义——值字段恒 None，绝不带部分证据。"""
    if status not in ENTRY_STATUSES or status in VALUE_BEARING_STATUSES:
        raise ValueError("f102_status_not_failure")
    return {"schema": SCHEMA, "platform": platform, "keyword": keyword,
            "status": status, "detail": detail,
            "synthetic": True,
            "usable_as_real_platform_evidence": False,
            "trajectory": None, "credential": None,
            "pdf_sha256": None, "page_manifest": None,
            "retrieved_at": None, "pdf_bytes": None}


def platform_by_id(platform_id):
    for entry in EIGHT_PLATFORMS:
        if entry[0] == platform_id:
            return entry
    return None


def platform_requires_login(platform_id) -> bool:
    entry = platform_by_id(platform_id)
    return bool(entry and entry[3])


def session_ok(session_token) -> bool:
    return isinstance(session_token, str) and bool(session_token) \
        and len(session_token) <= 128


# ---------------------------------------------------------------------------
# 本地受控合成采集目标（进程内确定性；唯一采集入口）
# ---------------------------------------------------------------------------

class SyntheticCaptureTarget:
    """合成采集目标：确定性合成页＋登录闸＋WAF 闸。

    时钟注入（clock: () -> float 秒），零墙钟零网络零子进程；每回执
    携 synthetic=True 与 provider=SYNTHETIC_PROVIDER_ID——出处具名合
    成，usable_as_real_platform_evidence=false。
    """

    def __init__(self, clock, seed: int = 20261022):
        if not callable(clock):
            raise ValueError("f102_clock_not_callable")
        self.clock = clock
        self.seed = seed
        self._last_measure_at: dict = {}
        self.fetch_count = 0
        self.measure_count = 0

    def _receipt_head(self, kind: str) -> dict:
        return {"provider": SYNTHETIC_PROVIDER_ID, "kind": kind,
                "synthetic": True,
                "usable_as_real_platform_evidence": False}

    def _blocked(self, kind: str, reason: str) -> dict:
        head = self._receipt_head(kind)
        head.update({"blocked": True, "reason": reason})
        return head

    def measure(self, platform: str, keyword: str, session_token) -> dict:
        self.measure_count += 1
        head = self._receipt_head("measure")
        if platform not in PLATFORM_CONTENT_HEIGHT:
            return self._blocked("measure", "platform_unknown")
        if platform_requires_login(platform) and not self._session_ok(
                session_token):
            return self._blocked("measure", "login_required")
        # WAF 闸（源件反爬攻略：检索频繁请求触发 WAF、平台间 2-3 秒
        # 间隔）——闸在检索面（measure）；同页取片不重复检索不触发。
        now = self.clock()
        last = self._last_measure_at.get(platform)
        if last is not None and now - last < MIN_INTERVAL_S:
            return self._blocked("measure", "waf_rate_limit")
        self._last_measure_at[platform] = now
        head.update({"platform": platform, "keyword": keyword,
                     "viewport_h": MEASURE_VIEWPORT_H,
                     "content_height": PLATFORM_CONTENT_HEIGHT[platform],
                     "retrieved_at": _iso(now)})
        return head

    def fetch_slice(self, platform: str, keyword: str, session_token,
                    slice_no: int, scroll_y: int, height: int) -> dict:
        self.fetch_count += 1
        head = self._receipt_head("slice")
        if platform not in PLATFORM_CONTENT_HEIGHT:
            return self._blocked("slice", "platform_unknown")
        if platform_requires_login(platform) and not self._session_ok(
                session_token):
            return self._blocked("slice", "login_required")
        rows = self._rows(platform, keyword, scroll_y, height)
        head.update({"platform": platform, "keyword": keyword,
                     "slice_no": slice_no, "scroll_y": scroll_y,
                     "width": RASTER_W, "height": height,
                     "raster": rows,
                     "retrieved_at": _iso(self.clock())})
        return head

    def row_at(self, platform: str, keyword: str, y: int) -> bytes:
        """单行真值（含页眉带变换；拼接保真对表用）。"""
        if y < HEADER_ROWS:
            return b"\x00" * RASTER_W
        if y == HEADER_ROWS:
            return b"\xff" * RASTER_W
        return self._row(platform, keyword, y)

    # -- 内部 --

    @staticmethod
    def _session_ok(session_token) -> bool:
        return session_ok(session_token)

    def _row(self, platform: str, keyword: str, y: int) -> bytes:
        digest = hashlib.sha256(
            ("%s|%s|%s|%d" % (self.seed, platform, keyword, y))
            .encode("utf-8")).digest()
        return digest * (RASTER_W // len(digest))

    def _rows(self, platform: str, keyword: str,
              scroll_y: int, height: int) -> bytes:
        if not isinstance(scroll_y, int) or isinstance(scroll_y, bool) \
                or scroll_y < 0 or not isinstance(height, int) \
                or isinstance(height, bool) or height <= 0:
            return b""
        return b"".join(
            self.row_at(platform, keyword, y)
            for y in range(scroll_y, scroll_y + height))


def _iso(t: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(int(t)))


def _ceil_div(a: int, b: int) -> int:
    return -(-a // b)


# ---------------------------------------------------------------------------
# 拼接计划（纯函数；栅格行空间算术，逻辑 px 策略先行）
# ---------------------------------------------------------------------------

def slice_plan(content_height_scaled: int) -> list:
    """返回 [(slice_no(1基), scroll_y), ...]（栅格行空间）。

    ≤视口上限单片；两倍上限内两片（底对齐，重叠裁切）；更大多片
    （顺序步进＋末片底对齐）。
    """
    vp = VIEWPORT_H_CEILING // RASTER_SCALE
    if content_height_scaled <= vp:
        return [(1, 0)]
    if content_height_scaled <= MULTI_SLICE_THRESHOLD // RASTER_SCALE:
        return [(1, 0), (2, content_height_scaled - vp)]
    full, count = vp, _ceil_div(content_height_scaled, vp)
    plan = [(i + 1, i * full) for i in range(count - 1)]
    plan.append((count, content_height_scaled - full))
    return plan


def content_height_scaled_of(platform: str) -> int:
    return _ceil_div(PLATFORM_CONTENT_HEIGHT[platform], RASTER_SCALE)


def stitch_slices(plan: list, receipts: list,
                  expected_total: int) -> bytes:
    """按覆盖推进拼接（重叠裁切）；返回整幅栅格。确定性。

    覆盖推进：covered=已覆盖行数；每片跳过与前片重叠的顶部行
    （skip=max(0, covered-scroll_y)），追加其余；末态须恰等于整幅行数。
    """
    covered = 0
    parts: list = []
    for (slice_no, scroll_y), receipt in zip(plan, receipts):
        raster = receipt["raster"]
        height = receipt["height"]
        skip = max(0, covered - scroll_y)
        parts.append(raster[skip * RASTER_W:])
        covered = scroll_y + height
    if covered != expected_total:
        raise ValueError("f102_coverage_mismatch")
    return b"".join(parts)


# ---------------------------------------------------------------------------
# 确定性 PDF（DeviceGray 8bit FlateDecode；无 /ID 无时间戳——E12 纪律）
# ---------------------------------------------------------------------------

def pdf_bytes(page_rasters: list) -> bytes:
    n_pages = len(page_rasters)
    n_objs = 2 + 3 * n_pages
    kids = " ".join("%d 0 R" % (3 + 3 * i) for i in range(n_pages))
    bodies: dict = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: ("<< /Type /Pages /Count %d /Kids [%s] >>"
            % (n_pages, kids)).encode(),
    }
    for i, (raw, width, height) in enumerate(page_rasters):
        comp = zlib.compress(raw, 9)
        page_num, img_num, cont_num = 3 + 3 * i, 4 + 3 * i, 5 + 3 * i
        bodies[page_num] = (
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] "
            "/Resources << /XObject << /Im%d %d 0 R >> >> "
            "/Contents %d 0 R >>"
            % (width, height, i, img_num, cont_num)).encode()
        bodies[img_num] = (
            "<< /Type /XObject /Subtype /Image /Width %d /Height %d "
            "/ColorSpace /DeviceGray /BitsPerComponent 8 "
            "/Filter /FlateDecode /Length %d >>\nstream\n"
            % (width, height, len(comp))).encode() + comp + b"\nendstream"
        content = ("q %d 0 0 %d 0 0 cm /Im%d Do Q"
                   % (width, height, i)).encode()
        bodies[cont_num] = ("<< /Length %d >>\nstream\n"
                            % len(content)).encode() + content \
            + b"\nendstream"
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets: dict = {}
    for num in range(1, n_objs + 1):
        offsets[num] = len(out)
        out += ("%d 0 obj\n" % num).encode() + bodies[num] + b"\nendobj\n"
    xref_pos = len(out)
    out += ("xref\n0 %d\n" % (n_objs + 1)).encode()
    out += b"0000000000 65535 f \n"
    for num in range(1, n_objs + 1):
        out += ("%010d 00000 n \n" % offsets[num]).encode()
    out += ("trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n"
            % (n_objs + 1, xref_pos)).encode() + b"%%EOF\n"
    return bytes(out)


# ---------------------------------------------------------------------------
# 取证链（E17 EvidenceAttempt 语义）
# ---------------------------------------------------------------------------

class PlatformEvidenceSession:
    """取证会话：注入 transport（唯一通道）＋时钟；跨平台间隔预检。"""

    def __init__(self, transport, clock):
        self.transport = transport
        self.clock = clock
        self.last_activity = None
        self.fetch_calls = 0

    def _pace_ok(self) -> bool:
        if self.last_activity is None:
            return True
        return self.clock() - self.last_activity >= MIN_INTERVAL_S

    def _note_activity(self) -> None:
        self.last_activity = self.clock()

    def capture(self, platform, keyword, session_token=None) -> dict:
        """全链：校验→测量→逐片→拼接→切页→PDF→封存。

        返回 attempt dict；EVIDENCE_SEALED 时另携 pdf_bytes 键（栅格
        PDF 字节）；一切失败路径 pdf_bytes=None 且值字段恒 None。
        """
        entry = platform_by_id(platform)
        if entry is None:
            return _fail(platform, keyword, "F102_PLATFORM_UNKNOWN",
                         "平台不在八平台闭集（冻结常量，裁决#13-19）")
        if not isinstance(keyword, str) or not keyword or len(keyword) > 64:
            return _fail(platform, keyword, "F102_KEYWORD_REQUIRED",
                         "关键词缺失/非串/超长")
        if self.transport is None:
            return _fail(platform, keyword, "F102_ADAPTER_ABSENT",
                         "平台适配器未接线（真实端点禁编 URL，"
                         "商业化适配器工单随 RECOVERY_POINT）")
        # 登录闸客户端预检（源件反爬攻略：需登录平台不空手请求；
        # 目标侧同闸为防线）——零请求发出。
        if entry[3] and not session_ok(session_token):
            return _fail(platform, keyword, "F102_LOGIN_REQUIRED",
                         "需登录平台无 session（客户端预检零请求；"
                         "目标侧同闸为防线）")
        if not self._pace_ok():
            return _fail(platform, keyword, "F102_PACING_VIOLATED",
                         "距上次回执间隔 < %ds（反爬攻略间隔预检，"
                         "零请求发出）" % MIN_INTERVAL_S)
        try:
            return self._pipeline(platform, keyword, session_token)
        except _Blocked as blocked:
            return _fail(platform, keyword,
                         "F102_LOGIN_REQUIRED" if blocked.reason
                         == "login_required" else "F102_WAF_INTERCEPT",
                         "目标侧拦截：%s" % blocked.reason)
        except _ReceiptInvalid as invalid:
            return _fail(platform, keyword, "F102_RECEIPT_INVALID",
                         "回执残缺/类型不符：%s" % invalid.reason)
        except Exception as exc:  # 传输异常——失败不编轨迹
            return _fail(platform, keyword, "F102_CAPTURE_FAILED",
                         "传输异常：%s" % type(exc).__name__)

    # -- 内部管线 --

    def _pipeline(self, platform, keyword, session_token) -> dict:
        measure = self.transport.measure(platform, keyword, session_token)
        _blocked_or_invalid(measure, "measure")
        if not _is_int(measure.get("content_height")) \
                or not 0 < measure["content_height"] <= 100000:
            raise _ReceiptInvalid("content_height_invalid")
        scaled = _ceil_div(measure["content_height"], RASTER_SCALE)
        if scaled != content_height_scaled_of(platform):
            raise _ReceiptInvalid("content_height_not_in_synthetic_world")
        plan = slice_plan(scaled)
        vp = VIEWPORT_H_CEILING // RASTER_SCALE
        receipts: list = []
        for slice_no, scroll_y in plan:
            expected_h = min(vp, scaled - scroll_y)
            self.fetch_calls += 1
            receipt = self.transport.fetch_slice(
                platform, keyword, session_token, slice_no, scroll_y,
                expected_h)
            _blocked_or_invalid(receipt, "slice")
            if receipt.get("slice_no") != slice_no \
                    or receipt.get("scroll_y") != scroll_y \
                    or receipt.get("width") != RASTER_W \
                    or receipt.get("height") != expected_h \
                    or not isinstance(receipt.get("raster"), bytes) \
                    or len(receipt["raster"]) != RASTER_W * expected_h:
                raise _ReceiptInvalid("slice_shape_mismatch")
            receipts.append(receipt)
        stitched = stitch_slices(plan, receipts, scaled)
        page_manifest, page_rasters = _split_pages(stitched)
        pdf = pdf_bytes(page_rasters)
        pdf_sha = _sha(pdf)
        pages_digest = _sha(_canonical(page_manifest).encode("utf-8"))
        first_at = receipts[0]["retrieved_at"]
        seal = _sha(_canonical({
            "provider": measure["provider"],
            "retrieved_at": first_at,
            "pdf_sha256": pdf_sha,
            "pages": pages_digest,
        }).encode("utf-8"))
        self._note_activity()
        attempt = {
            "schema": SCHEMA, "platform": platform, "keyword": keyword,
            "status": "EVIDENCE_SEALED", "detail": None,
            "synthetic": True,
            "usable_as_real_platform_evidence": False,
            "source": {"provider": measure["provider"],
                       "target": SYNTHETIC_PROVIDER_ID,
                       "seed": getattr(self.transport, "seed", None)},
            "retrieved_at": first_at,
            "trajectory": [
                {"slice_no": receipt["slice_no"],
                 "scroll_y": receipt["scroll_y"],
                 "height": receipt["height"],
                 "retrieved_at": receipt["retrieved_at"],
                 "raster_sha256": _sha(receipt["raster"])}
                for receipt in receipts],
            "credential": {"provider": measure["provider"],
                           "retrieved_at": first_at,
                           "pdf_sha256": pdf_sha,
                           "pages_digest": pages_digest,
                           "algorithm": "sha256-canonical-json",
                           "seal": seal},
            "pdf_sha256": pdf_sha,
            "page_manifest": page_manifest,
            "pdf_bytes": pdf,
        }
        return attempt


class _Blocked(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class _ReceiptInvalid(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _blocked_or_invalid(receipt, kind: str) -> None:
    if not isinstance(receipt, dict):
        raise _ReceiptInvalid("receipt_not_object")
    provider = receipt.get("provider")
    if not isinstance(provider, str) or not provider:
        raise _ReceiptInvalid("provider_missing")
    if receipt.get("kind") != kind:
        raise _ReceiptInvalid("kind_mismatch")
    if receipt.get("blocked"):
        reason = receipt.get("reason")
        raise _Blocked(str(reason))
    if receipt.get("synthetic") is not True:
        raise _ReceiptInvalid("synthetic_flag_missing")
    retrieved_at = receipt.get("retrieved_at")
    if not isinstance(retrieved_at, str) or not retrieved_at:
        raise _ReceiptInvalid("retrieved_at_missing")


def _split_pages(stitched: bytes) -> tuple:
    """整幅栅格切页＋页号标记带＋页清单金标（E12 bbox 纪律）。"""
    total = len(stitched) // RASTER_W
    manifest: list = []
    rasters: list = []
    y0 = 0
    page_no = 0
    while y0 < total:
        page_no += 1
        y1 = min(y0 + PAGE_H, total)
        height = y1 - y0
        page = bytearray(stitched[y0 * RASTER_W:y1 * RASTER_W])
        # 页号标记带（黑）＋上缘留白行（白）——bbox 入金标。
        band_top = height - NUMBER_BAND_H - 3
        margin_row = (band_top - 1) * RASTER_W
        band_rows = band_top * RASTER_W
        page[margin_row:margin_row + RASTER_W] = b"\xff" * RASTER_W
        page[band_rows:band_rows + NUMBER_BAND_H * RASTER_W] = \
            b"\x00" * (NUMBER_BAND_H * RASTER_W)
        page_bytes = bytes(page)
        manifest.append({
            "page_no": page_no,
            "gold_version": PAGE_BBOX_GOLD_VERSION,
            "source_bbox": [0, y0, RASTER_W, y1],
            "page_raster_sha256": _sha(page_bytes),
            "number_band_bbox": [0, band_top, RASTER_W,
                                 band_top + NUMBER_BAND_H],
        })
        rasters.append((page_bytes, RASTER_W, height))
        y0 = y1
    return manifest, rasters
