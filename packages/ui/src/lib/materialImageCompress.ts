// 【功能 #6 材料上传解析】图片上传前本地压缩 + textFallback 副本（RE-6 §3 UI 结构；对拍 6）。
// 行为锚点：超上限（默认 5MB / 4096px）按 webp 逐级质量(0.86→0.32)×尺寸(×0.75)重编码直到合规，
// 记录 wasCompressed；另生成 ≤1280px / 512KB 的 textFallback 副本供文本模型。浏览器实现走
// canvas，纯函数部分（尝试序列规划）独立导出供 Node 单测（vitest 无 DOM 环境亦可验证阶梯数学）。

export const IMAGE_UPLOAD_MAX_BYTES = 5 * 1024 * 1024;
export const IMAGE_UPLOAD_MAX_EDGE_PX = 4096;
/** 质量阶梯：逐级下降（竞品 image-attachment-upload 行为等量，数值同策略自实现）。 */
export const IMAGE_QUALITY_LADDER = [0.86, 0.72, 0.58, 0.44, 0.32] as const;
/** 单轮全阶梯仍超限时，尺寸整体 ×0.75 再走一轮。 */
export const IMAGE_SCALE_STEP = 0.75;
export const TEXT_FALLBACK_MAX_EDGE_PX = 1280;
export const TEXT_FALLBACK_MAX_BYTES = 512 * 1024;
/** 防御性轮数上限：正常 2-3 轮内收敛；到顶仍未合规就交最后一次产物（不无限循环）。 */
const MAX_ROUNDS = 6;

export interface CompressionAttempt {
  quality: number;
  scale: number;
}

export interface ImageLimits {
  maxBytes?: number;
  maxEdgePx?: number;
}

/**
 * 纯函数：给定原始尺寸/体积与上限，产出「质量×尺寸」尝试序列（同输入恒定输出）。
 * 首轮 scale 只在被边长超限时 <1；此后每轮 ×IMAGE_SCALE_STEP。空数组=无需压缩。
 */
export function planImageCompressionSteps(
  input: { width: number; height: number; bytes: number },
  limits?: ImageLimits,
): CompressionAttempt[] {
  const maxBytes = limits?.maxBytes ?? IMAGE_UPLOAD_MAX_BYTES;
  const maxEdgePx = limits?.maxEdgePx ?? IMAGE_UPLOAD_MAX_EDGE_PX;
  const edge = Math.max(input.width, input.height);
  const overBytes = input.bytes > maxBytes;
  const overEdge = edge > maxEdgePx;
  if (!overBytes && !overEdge) return [];
  let scale = overEdge ? maxEdgePx / edge : 1;
  const steps: CompressionAttempt[] = [];
  for (let round = 0; round < MAX_ROUNDS; round += 1) {
    for (const quality of IMAGE_QUALITY_LADDER) {
      steps.push({ quality, scale });
    }
    scale *= IMAGE_SCALE_STEP;
  }
  return steps;
}

export interface ImageCompressionOutcome {
  blob: Blob;
  width: number;
  height: number;
  wasCompressed: boolean;
  /** 最终产物 MIME（压缩产物=webp；未压缩=原件类型）。 */
  mimeType: string;
}

function drawToBlob(source: ImageBitmap, width: number, height: number, type: string, quality: number): Promise<Blob | null> {
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  if (!ctx) return Promise.resolve(null);
  ctx.drawImage(source, 0, 0, width, height);
  return new Promise((resolve) => {
    canvas.toBlob((blob) => resolve(blob), type, quality);
  });
}

/**
 * 图片压缩主路径：解码→（超限才）逐级重编码 webp。解码失败/无 canvas 返 null，
 * 调用方按原件直传（fail-open 到原件，压缩只是优化不是门禁——门禁在桥 MIME/体量面）。
 */
export async function compressImageForUpload(
  file: Blob,
  limits?: ImageLimits,
): Promise<ImageCompressionOutcome | null> {
  let bitmap: ImageBitmap;
  try {
    bitmap = await createImageBitmap(file);
  } catch {
    return null;
  }
  try {
    const steps = planImageCompressionSteps(
      { width: bitmap.width, height: bitmap.height, bytes: file.size },
      limits,
    );
    if (steps.length === 0) {
      return { blob: file, width: bitmap.width, height: bitmap.height, wasCompressed: false, mimeType: file.type || "image/png" };
    }
    let last: { blob: Blob; width: number; height: number } | null = null;
    for (const step of steps) {
      const width = Math.max(1, Math.round(bitmap.width * step.scale));
      const height = Math.max(1, Math.round(bitmap.height * step.scale));
      const blob = await drawToBlob(bitmap, width, height, "image/webp", step.quality);
      if (!blob) continue;
      last = { blob, width, height };
      if (blob.size <= (limits?.maxBytes ?? IMAGE_UPLOAD_MAX_BYTES)) {
        return { blob, width, height, wasCompressed: true, mimeType: "image/webp" };
      }
    }
    if (!last) return null;
    return { blob: last.blob, width: last.width, height: last.height, wasCompressed: true, mimeType: "image/webp" };
  } finally {
    bitmap.close();
  }
}

/**
 * textFallback 副本（对拍 6 后半）：≤1280px/512KB 的降载 jpeg。已在限内→返原件
 * （调用方据此跳过副本上传）；解码失败→null（跳过副本，不阻塞主件）。
 */
export async function makeImageTextFallback(file: Blob): Promise<Blob | null> {
  let bitmap: ImageBitmap;
  try {
    bitmap = await createImageBitmap(file);
  } catch {
    return null;
  }
  try {
    if (
      Math.max(bitmap.width, bitmap.height) <= TEXT_FALLBACK_MAX_EDGE_PX &&
      file.size <= TEXT_FALLBACK_MAX_BYTES
    ) {
      return file;
    }
    const scale = Math.min(1, TEXT_FALLBACK_MAX_EDGE_PX / Math.max(bitmap.width, bitmap.height));
    const width = Math.max(1, Math.round(bitmap.width * scale));
    const height = Math.max(1, Math.round(bitmap.height * scale));
    for (const quality of [0.72, 0.6, 0.5]) {
      const blob = await drawToBlob(bitmap, width, height, "image/jpeg", quality);
      if (!blob) continue;
      if (blob.size <= TEXT_FALLBACK_MAX_BYTES) return blob;
    }
    return null;
  } finally {
    bitmap.close();
  }
}
