// F82 复核/单格重跑/人工改格三面（W2b-U31）：纯投影模块，零依赖（不加 import）。
//
// 同源纪律：审查表唯一来源＝产品 Python 桥出的两份投影——
// legal_entry tabular.read（列三元组：列名/金标/值＋支持状态，W2b-U05）
// 与 tabular.review_status（复核状态投影，W2b-U31）。本模块只做机械合并
// 投影，不重算金标、不重判支持/复核状态——前端重判＝第二权威＝漂移根源。
//
// 状态闭集（与 harness 面同集）：
//   supportStatus: SUPPORTED_CITATION_LEVEL / UNSUPPORTED_REJECTED /
//     STALE_CELL_ADVANCED / INVALIDATED / NO_STAMP
//   reviewStatus:  REVIEWED_CONFIRMED / REVIEWED_REJECTED / NOT_REVIEWED
// 闭集外值＝响亮失败（不静默渲染未知状态）。
//
// F84 红线在本面即守：改格必经写权限方法——本模块零写通道；一切写动作
// （复核回执/重跑/人工改格）只经 window.lvyinReview seam→产品桥→harness
// 公开面，UI 不建第二写通道。

export type SupportStatus =
  | "SUPPORTED_CITATION_LEVEL"
  | "UNSUPPORTED_REJECTED"
  | "STALE_CELL_ADVANCED"
  | "INVALIDATED"
  | "NO_STAMP"

export type ReviewStatus =
  | "REVIEWED_CONFIRMED"
  | "REVIEWED_REJECTED"
  | "NOT_REVIEWED"

export type ReviewGold = {
  kind?: string
  expect?: unknown
  note?: string
}

export type ReadCell = {
  columnId: string
  columnName?: string
  gold?: ReviewGold | null
  value?: unknown
  cellGeneration?: number
  cellSource?: string
  supportStatus?: string
  goldMatch?: boolean | null
  goldMatchReason?: string | null
}

export type ReadRow = {
  rowId: string
  rowState?: string
  cells: ReadCell[]
}

export type TabularReadDoc = {
  reviewBatchId?: string
  batchStatus?: string
  columnContractDefined?: boolean
  columns?: { id: string; name?: string }[]
  rows?: ReadRow[]
  supportCounts?: Record<string, number>
}

export type StatusProjection = {
  rowId: string
  cellId: string
  reviewStatus: string
  entryCount?: number
}

export type ReviewStatusDoc = {
  batchId?: string
  projections?: StatusProjection[]
  counts?: Record<string, number>
}

export type ReviewCell = Omit<ReadCell, "supportStatus"> & {
  supportStatus: SupportStatus
  reviewStatus: ReviewStatus
  reviewEntryCount: number
}

export type ReviewRow = {
  rowId: string
  rowState?: string
  cells: ReviewCell[]
}

export type ReviewTable = {
  batchId: string
  batchStatus?: string
  rows: ReviewRow[]
  supportCounts: Record<string, number>
  reviewCounts: Record<string, number>
}

export const SUPPORT_STATUSES: readonly SupportStatus[] = [
  "SUPPORTED_CITATION_LEVEL",
  "UNSUPPORTED_REJECTED",
  "STALE_CELL_ADVANCED",
  "INVALIDATED",
  "NO_STAMP",
]

export const REVIEW_STATUSES: readonly ReviewStatus[] = [
  "REVIEWED_CONFIRMED",
  "REVIEWED_REJECTED",
  "NOT_REVIEWED",
]

export const SUPPORT_LABELS: Record<SupportStatus, string> = {
  SUPPORTED_CITATION_LEVEL: "支持（引用级）",
  UNSUPPORTED_REJECTED: "不支持（拒因具名）",
  STALE_CELL_ADVANCED: "旧世代（格已推进）",
  INVALIDATED: "已失效",
  NO_STAMP: "无戳",
}

export const REVIEW_LABELS: Record<ReviewStatus, string> = {
  REVIEWED_CONFIRMED: "复核认可",
  REVIEWED_REJECTED: "复核不认可",
  NOT_REVIEWED: "未复核",
}

export class ReviewSurfaceError extends Error {
  code: string
  constructor(code: string) {
    super(code)
    this.code = code
  }
}

function asSupportStatus(value: unknown): SupportStatus {
  if (typeof value === "string" && (SUPPORT_STATUSES as readonly string[]).includes(value)) {
    return value as SupportStatus
  }
  throw new ReviewSurfaceError("f82_support_status_invalid:" + String(value))
}

function asReviewStatus(value: unknown): ReviewStatus {
  if (typeof value === "string" && (REVIEW_STATUSES as readonly string[]).includes(value)) {
    return value as ReviewStatus
  }
  throw new ReviewSurfaceError("f82_review_status_invalid:" + String(value))
}

/** 合并投影：tabular.read（列三元组＋支持状态）× tabular.review_status
 * （复核状态）。两端格集合不一致＝同源破损＝响亮报错，不静默跳过。 */
export function mergeTable(read: TabularReadDoc, status: ReviewStatusDoc): ReviewTable {
  if (!read || !Array.isArray(read.rows)) {
    throw new ReviewSurfaceError("f82_read_doc_invalid")
  }
  if (!status || !Array.isArray(status.projections)) {
    throw new ReviewSurfaceError("f82_status_doc_invalid")
  }
  const statusIndex = new Map<string, StatusProjection>()
  for (const projection of status.projections) {
    const key = projection.rowId + ":" + projection.cellId
    if (statusIndex.has(key)) {
      throw new ReviewSurfaceError("f82_status_duplicate:" + key)
    }
    statusIndex.set(key, projection)
  }
  const rows: ReviewRow[] = []
  const supportCounts: Record<string, number> = { ...read.supportCounts }
  for (const row of read.rows) {
    if (!row || typeof row.rowId !== "string" || !Array.isArray(row.cells)) {
      throw new ReviewSurfaceError("f82_read_row_invalid")
    }
    const cells: ReviewCell[] = []
    for (const cell of row.cells) {
      if (!cell || typeof cell.columnId !== "string") {
        throw new ReviewSurfaceError("f82_read_cell_invalid")
      }
      const key = row.rowId + ":" + cell.columnId
      const projection = statusIndex.get(key)
      if (!projection) {
        // 复核投影按批全覆盖：缺格＝两投影格集合不一致＝响亮失败。
        throw new ReviewSurfaceError("f82_status_missing:" + key)
      }
      statusIndex.delete(key)
      cells.push({
        ...cell,
        supportStatus: asSupportStatus(cell.supportStatus ?? "NO_STAMP"),
        reviewStatus: asReviewStatus(projection.reviewStatus),
        reviewEntryCount: projection.entryCount ?? 0,
      })
    }
    rows.push({ rowId: row.rowId, rowState: row.rowState, cells })
  }
  if (statusIndex.size > 0) {
    throw new ReviewSurfaceError(
      "f82_status_extra:" + [...statusIndex.keys()].sort().join(","),
    )
  }
  return {
    batchId: read.reviewBatchId ?? status.batchId ?? "",
    batchStatus: read.batchStatus,
    rows,
    supportCounts,
    reviewCounts: { ...status.counts },
  }
}

/** 人改携带世代的确定性取值：取投影格当前 cellGeneration（缺省拒绝——
 * 携带值必须可归因，不以 undefined 强改）。 */
export function carriedGeneration(cell: ReviewCell): number {
  if (typeof cell.cellGeneration !== "number") {
    throw new ReviewSurfaceError("f82_generation_missing:" + cell.columnId)
  }
  return cell.cellGeneration
}
