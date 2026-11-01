import { Suspense, lazy } from "react";
import type { PdfViewerLabels, PdfViewerSource } from "@/components/ui/pdf-viewer.js";

// react-pdf（含 pdf.js 与 worker）体积较大，懒加载让它只在首次打开 PDF 预览时进入 bundle，
// 不拖慢没有用到 PDF 的会话的启动。
const PdfViewer = lazy(() =>
  import("@/components/ui/pdf-viewer.js").then((module) => ({
    default: module.PdfViewer,
  })),
);

interface PdfPreviewContentProps {
  source: PdfViewerSource;
  labels: PdfViewerLabels;
  onPageChange?: (page: number) => void; // 功能 #20（B35）透传
}

export function PdfPreviewContent({ source, labels, onPageChange }: PdfPreviewContentProps) {
  return (
    <Suspense
      fallback={<div className="p-3 text-ui-base text-foreground-subtle">{labels.loading}</div>}
    >
      <PdfViewer source={source} labels={labels} onPageChange={onPageChange} className="h-full" />
    </Suspense>
  );
}
