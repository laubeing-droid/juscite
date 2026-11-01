// 法律面板族注册点（r12 波3，设计 §一 L2「树内只留注册点」+ §八 原则3）。
// 本文件是法律 UI 出树后唯一留在 ui 包内的挂载胶水：把上游 ui 内部件注入 @juscite/legal 的
// legalUiKit 窄适配层。上游换样式系统/换组件库 → 只改本文件，面板族（packages/juscite-legal）零动。
// 由 App.tsx 静态导入（模块加载即注册，先于任何面板渲染）；插桩清单见 contracts/pin-points-wave3.md。
import { Button } from "@/components/ui/button.js";
import { Input } from "@/components/ui/input.js";
import { Switch } from "@/components/ui/switch.js";
import { DiffViewer } from "@/components/ui/diff-viewer.js";
import { MessageResponse } from "@/components/ai-elements/message.js";
import { PdfPreviewContent } from "@/previewPanePdfContent.js";
import { collectDroppedFiles } from "@/lib/bridgeMaterialAttachments.js";
import { useServices } from "@/hooks/useServices.js";
import { configureLegalUiKit } from "@juscite/legal/ui-kit";

configureLegalUiKit({
  Button,
  Input,
  DiffViewer,
  MessageResponse,
  PdfPreviewContent,
  collectDroppedFiles,
  useServices,
  Switch,
});
