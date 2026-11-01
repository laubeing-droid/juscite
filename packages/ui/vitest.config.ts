import { createRequire } from "node:module";
import { dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

// 与 packages/desktop/vite.config.ts 的 resolveInstalledPackageRoot 同一手法：
// 用 Node 解析 react / react-dom 的真实安装根，而不是写死 .pnpm store 目录。
// 根 .npmrc 为 node-linker=hoisted 时没有
// node_modules/.pnpm/react@…/node_modules/react 这条路径，硬编码别名会让
// ci_gate stepVitest 找不到模块。isolated linker 下则是符号链 id 与实体 id
// 拆成两份 React（#43：@juscite/legal 面板源经 vitest 变换的 `import "react"`
// 与 @testing-library/react 的 react-dom 各绑一份实例，useState 全崩）。
// require.resolve 在两种 node-linker 下都落到同一物理包根，升版也不用改目录名。
const uiConfigRequire = createRequire(import.meta.url);

function resolveInstalledPackageRoot(packageName: string): string {
  return dirname(uiConfigRequire.resolve(`${packageName}/package.json`));
}

const reactReal = resolveInstalledPackageRoot("react");
const reactDomReal = resolveInstalledPackageRoot("react-dom");

export default defineConfig({
  resolve: {
    alias: [
      { find: "@", replacement: fileURLToPath(new URL("./src", import.meta.url)) },
      { find: /^react$/, replacement: reactReal },
      { find: /^react-dom$/, replacement: reactDomReal },
    ],
  },
});
