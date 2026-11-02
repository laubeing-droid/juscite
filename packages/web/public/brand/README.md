# 律引 / Juscite 锁定标志

Owner 与班长已锁定的引用锚点（citation anchor）。本目录是入库源，不再使用獬豸（xiezhi）草稿，也不使用天平 / 盾形占位。

## 色

| 色板 | 色值 | 用途 |
| --- | --- | --- |
| 墨 | `#111111` | 纯黑白字标与单色锚点 |
| 白 | `#FFFFFF` | 底 |
| 藏青 | `#1B2A4A` | 藏青 + 金 色板的主体 |
| 金 | `#C9A45C` | 只用于锚点笔尖，一处 |

## 字体

字标文字声明 OFL 字体，不把字形转曲：

- 中文「律引」：Noto Sans CJK SC Bold（`font-weight: 700`）
- 拉丁「Juscite」：Inter Medium（`font-weight: 500`）

SVG 字标里的锚点是嵌入的栅格，用来保住剪影，不是另一套手绘。

## 文件

| 文件 | 内容 |
| --- | --- |
| `wordmark-bw.png` / `wordmark-bw.svg` | 黑白字标，`#111` on white |
| `wordmark-navy-gold.png` / `wordmark-navy-gold.svg` | 藏青字标 + 金尖 |
| `icon-bw.png` / `icon-navy-gold.png` | 白底上的单独锚点 |
| `mark-bw.png` / `mark-navy-gold.png` / `mark-white-gold.png` | 透明底锚点（黑 / 藏青+金 / 白+金） |
| `app-icon.png` | 藏青圆角方，白标 + 金尖 |

`packages/web/public/favicon.svg` 与 `favicon.ico` 从 `mark-navy-gold.png` 裁切后铺在白底上，供 16–32px 标签图标。形状仍是这枚锚点。

启动壳与标题栏徽标（深色底板）使用 `mark-white-gold.png` 的同一枚锚点。共享组件另存一份同字节文件在 `packages/ui/src/assets/brand/mark-white-gold.png`，供桌面与 Web 打包，不另画一枚。界面其余布局，包括仍在用的几何 Z 标，不在这次锁定范围内。
