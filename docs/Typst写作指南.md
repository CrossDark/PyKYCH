# Typst 写作指南

本指南介绍如何在 PyKYCH 上使用 Typst 标记语言撰写文章，以及如何利用内置模板获得专业的中文排版效果。

## 目录

- [什么是 Typst](#什么是-typst)
- [快速开始](#快速开始)
- [模板系统](#模板系统)
  - [article 模板（推荐）](#article-模板推荐)
  - [simple 模板](#simple-模板)
  - [模板参数速查](#模板参数速查)
- [写作语法](#写作语法)
  - [标题](#标题)
  - [文本格式](#文本格式)
  - [代码](#代码)
  - [数学公式](#数学公式)
  - [表格](#表格)
  - [引用块](#引用块)
  - [列表](#列表)
  - [链接与图片](#链接与图片)
  - [脚注](#脚注)
- [提示块（Admonitions）](#提示块admonitions)
- [中文字体系统](#中文字体系统)
- [HTML 与 PDF 双输出](#html-与-pdf-双输出)
- [跨文章引用](#跨文章引用)
- [最佳实践](#最佳实践)
- [常见问题](#常见问题)

---

## 什么是 Typst

[Typst](https://typst.app) 是一个现代化的标记语言与排版系统，专为科学和技术写作设计。相比 Markdown，Typst 提供了：

- **原生数学公式** — 无需借助 LaTeX 或 MathJax
- **精确排版控制** — 页面布局、字体、间距完全可控
- **代码高亮** — 内置多语言语法高亮
- **自动化功能** — 目录生成、编号、交叉引用
- **中文支持** — `text(lang: "zh")` 启用中文标点压缩和换行规则

在 PyKYCH 中，Typst 文章会被自动编译为 HTML 展示，同时提供 PDF 下载链接。

---

## 快速开始

### 第一步：创建 Typst 文章

在 PyKYCH 后台选择 **"新建 Typst 文章"**，进入编辑器。

### 第二步：编写最小示例

```typst
#import "config.typ": article

#show: article.with(
  title: "你好，Typst！",
  author: "你的名字",
  date: "2024-06-19",
)

= 欢迎

这是我的第一篇 Typst 文章。Typst 让排版变得简单而优雅。

== 为什么选择 Typst

- 语法直观，学习曲线平缓
- 数学公式渲染一流
- 中英文混排效果出色
```

### 第三步：保存并预览

保存后，PyKYCH 会自动将 Typst 源码编译为 HTML 网页。你也可以点击页面上的 **"📥 下载 PDF"** 按钮获取 PDF 版本。

---

## 模板系统

PyKYCH 内置了两个模板，定义在共享配置文件 `config.typ` 中。每篇文章通过 `#import "config.typ"` 引入并使用 `#show:` 规则激活模板。

### article 模板（推荐）

`article` 模板提供完整的文章排版，包括标题头部、标签、目录和页脚。

```typst
#import "config.typ": article

#show: article.with(
  title:      "文章标题",
  subtitle:   "副标题（可选）",
  author:     "作者名（可选）",
  date:       "2024-06-19",
  tags:       ("标签1", "标签2"),
  show-toc:   true,      // 开启目录
  paper-size: "a4",      // PDF 纸张尺寸
  font-size:  12pt,      // 正文字号
)

= 第一节

正文内容...
```

**极简用法**（不设置元信息，直接从一级标题开始）：

```typst
#import "config.typ": article
#show: article

= 我的文章

直接写正文...
```

### simple 模板

`simple` 模板不显示文章头部和尾部装饰，适合嵌入型页面或简洁笔记。

```typst
#import "config.typ": simple

#show: simple

= 简洁笔记

无头部、无尾注，纯粹的排版。
```

### 模板参数速查

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `title` | `none` / 字符串 | `none` | 文章标题，居中大字显示 |
| `subtitle` | `none` / 字符串 | `none` | 副标题，标题下方斜体显示 |
| `author` | `none` / 字符串 | `none` | 作者名，显示为 ✍️ 作者 |
| `date` | `none` / 字符串 | `none` | 发布日期，显示为 📅 日期 |
| `tags` | 字符串数组 | `()` | 标签列表，渲染为蓝色药丸标签 |
| `show-toc` | 布尔值 | `false` | 是否在正文前显示目录 |
| `toc-title` | 内容 | `[目录]` | 目录区域的标题文本 |
| `paper-size` | 字符串 | `"a4"` | PDF 纸张尺寸（仅 PDF 输出生效） |
| `font-size` | 长度 | `12pt` | 正文基础字号 |

---

## 写作语法

### 标题

Typst 使用 `=` 号标记标题层级，与 Markdown 的 `#` 类似：

```typst
= 一级标题

== 二级标题

=== 三级标题

==== 四级标题
```

模板已为前三级标题设置了优化的字号和间距：
- **一级**：1.75em，粗体，无衬线字体
- **二级**：1.35em，半粗体，无衬线字体
- **三级**：1.15em，半粗体，无衬线字体

> 如果未通过 `title` 参数指定文章标题，模板会使用文档中第一个一级标题作为文章标题。

### 文本格式

```typst
*粗体文字*
_斜体文字_
#strong[粗体（语义化）]
#emph[着重（语义化）]
#underline[下划线]
#strike[删除线]
~上标~
_下标
#super[上标（语义化）]
#sub[下标（语义化）]
```

### 代码

**行内代码：**

```typst
使用 `print("hello")` 函数输出字符串。
```

**代码块（带语言高亮）：**

````typst
```python
def fibonacci(n: int) -> list[int]:
    """生成斐波那契数列"""
    a, b = 0, 1
    result = []
    for _ in range(n):
        result.append(a)
        a, b = b, a + b
    return result
```
````

模板会为代码块应用浅灰背景、圆角边框和等宽中文字体（Sarasa Mono SC）。

### 数学公式

Typst 的数学模式与 LaTeX 类似，但语法更简洁。

**行内公式：**

```typst
勾股定理：$a^2 + b^2 = c^2$
质能方程：$E = m c^2$
```

**块级公式（独立成行、居中）：**

```typst
$ sum_(k=1)^n k = (n(n+1)) / 2 $
```

**多行公式：**

```typst
$ f(x) = cases(
  1,  x > 0,
  0,  x = 0,
  -1, x < 0,
) $
```

**矩阵：**

```typst
$ mat(
  1, 0, 0;
  0, 1, 0;
  0, 0, 1;
) $
```

> 数学公式在 HTML 输出中通过 KaTeX 渲染，PDF 输出使用 Typst 原生数学引擎。

### 表格

```typst
#table(
  columns: 3,
  table.header(
    [*项目*], [*数量*], [*单价*],
  ),
  [苹果], [10], [¥5.00],
  [香蕉], [20], [¥3.50],
  [橙子], [15], [¥4.00],
)
```

- `columns` 指定列数
- `table.header` 定义表头行（自动加粗）
- `[*文字*]` 在单元格内加粗

模板会自动缩小表格字号至 0.92em 并使用无衬线字体。

### 引用块

```typst
#quote(block: true)[
  设计不仅仅是它看起来像什么和感觉如何。
  设计是它如何工作。
]
```

模板为引用块添加了左侧蓝色强调线和浅灰背景。

### 列表

**无序列表：**

```typst
- 项目一
- 项目二
  - 嵌套项目
  - 另一个嵌套
```

**有序列表：**

```typst
+ 第一步
+ 第二步
+ 第三步
```

**定义列表：**

```typst
/ 术语: 解释说明文字
/ 另一个术语: 对应的解释
```

### 链接与图片

**超链接：**

```typst
#link("https://typst.app")[Typst 官网]
```

**图片（引用辅助文件中的图片）：**

```typst
#image("imgs/photo.png", width: 80%)

#figure(
  image("imgs/diagram.svg", width: 100%),
  caption: [系统架构示意图],
)
```

> 图片文件需要通过 PyKYCH 的"辅助文件"功能上传。在文章编辑界面中，将图片上传为辅助文件，然后在 Typst 源码中通过相对路径引用。

### 脚注

```typst
Typst 是一个优秀的排版系统。#footnote[详见 Typst 官方文档]
```

---

## 提示块（Admonitions）

模板提供了四种彩色提示块，用于突出显示不同重要程度的信息。

### note — 信息提示

```typst
#import "config.typ": article, note

#note[这是一条常规提示信息，用于补充说明或强调要点。]
```

渲染为蓝色边框 + 浅蓝背景 + 📝 图标。

### tip — 技巧提示

```typst
#import "config.typ": article, tip

#tip[使用 `show-toc: true` 可以为长文章自动生成目录。]
```

渲染为绿色边框 + 浅绿背景 + 💡 图标。

### warning — 警告

```typst
#import "config.typ": article, warning

#warning[此操作将删除所有数据，请确认后再执行。]
```

渲染为黄色边框 + 浅黄背景 + ⚠️ 图标。

### danger — 危险警告

```typst
#import "config.typ": article, danger

#danger[生产环境请勿执行此操作，可能导致服务中断。]
```

渲染为红色边框 + 浅红背景 + 🚫 图标。

> **注意**：使用提示块时，需要在 `#import` 语句中额外导入对应函数名，如 `#import "config.typ": article, note, tip`。

---

## 中文字体系统

模板内置了三级字体回退链，确保在不同操作系统上都能获得良好的中文排版效果。

### 衬线体（正文）

| 优先级 | 字体名 | 适用系统 |
|--------|--------|----------|
| 1 | Noto Serif CJK SC | 跨平台（推荐安装） |
| 2 | Source Han Serif SC | 跨平台（思源宋体） |
| 3 | Songti SC | macOS 宋体 |
| 4 | SimSun | Windows 宋体 |
| 5 | STSong | macOS 华文宋体 |

### 无衬线体（标题 / 表格）

| 优先级 | 字体名 | 适用系统 |
|--------|--------|----------|
| 1 | Sarasa Gothic SC | 跨平台（更纱黑体，推荐） |
| 2 | Noto Sans CJK SC | 跨平台 |
| 3 | Source Han Sans SC | 跨平台（思源黑体） |
| 4 | PingFang SC | macOS 苹方 |
| 5 | Heiti SC | macOS 黑体 |
| 6 | STHeiti | macOS 华文黑体 |

### 等宽体（代码）

| 优先级 | 字体名 | 适用系统 |
|--------|--------|----------|
| 1 | Sarasa Mono SC | 跨平台（更纱等宽黑体，推荐） |
| 2 | Noto Sans Mono CJK SC | 跨平台 |
| 3 | WenQuanYi Zen Hei Mono | Linux 文泉驿 |
| 4 | STFangsong | macOS 华文仿宋 |

Typst 会按优先级自动选取系统中第一个可用的字体。如果链中所有字体都不可用，则回退到系统默认字体。

### 推荐安装字体

在 macOS 上，推荐通过 Homebrew 安装：

```bash
brew install --cask font-sarasa-gothic
brew install --cask font-noto-serif-cjk-sc
brew install --cask font-noto-sans-cjk-sc
```

---

## HTML 与 PDF 双输出

PyKYCH 的 Typst 编译系统同时支持 HTML 网页展示和 PDF 文件下载。模板内部通过 `context { if target == "html" { ... } }` 对两种输出做了适配：

| 特性 | HTML 输出 | PDF 输出 |
|------|-----------|----------|
| 页面边距 | 无（适合网页嵌入） | A4 纸张 + 2.2cm 边距 |
| 页码 | 不显示 | 自动编号 + 页眉标题 |
| 字体 | 系统字体 + CSS fallback | 嵌入字体子集 |
| 数学公式 | KaTeX 渲染 | Typst 原生渲染 |
| 目录 | 显示（如启用） | 显示 + 可点击跳转 |

### 在网页上获取 PDF

每篇 Typst 文章的详情页顶部都有 PDF 下载栏：

```
📄 本文由 Typst 编译生成    [📥 下载 PDF]
```

也可以直接访问 `https://你的网站/typst/文章slug/pdf` 下载。

---

## 最佳实践

### 1. 文章结构

建议每篇文章遵循清晰的层级结构：

```typst
= 文章标题（一级）
== 背景介绍（二级）
== 核心内容（二级）
=== 要点一（三级）
=== 要点二（三级）
== 总结（二级）
```

### 2. 代码展示

- 始终为代码块指定语言以获得语法高亮
- 行内代码用于提及函数名或变量：`get_user()` 函数
- 较长的代码片段使用代码块

### 3. 数学公式

- 简单公式用行内模式：$x^2 + y^2 = z^2$
- 重要公式用块级模式单独成行
- 使用 `\` 转义 Typst 关键字

### 4. 图片管理

- 将图片通过辅助文件功能上传
- 推荐使用 SVG 格式（矢量无损缩放）
- 为图片添加 `#figure` 包裹和 `caption` 说明

### 5. 长文章优化

对超过 3000 字的文章，建议：

```typst
#show: article.with(
  title: "长文章标题",
  show-toc: true,    // 开启目录导航
)
```

### 6. 辅助文件

Typst 文章可以附带辅助文件（如 `.typ` 子模块、图片、数据文件）。在 PyKYCH 的文章编辑界面中：

1. 切换到"辅助文件"标签
2. 上传你的文件（支持 `.typ`、`.png`、`.svg` 等）
3. 在主文件中通过相对路径引用：

```typst
// 导入辅助 Typst 模块
#import "lib/utils.typ": my-function

// 引用辅助图片
#image("imgs/screenshot.png")
```

---

## 跨文章引用

PyKYCH 支持在 Typst 文章中通过 `site:` 语法引用网站上的其他 Typst 文章。这让你可以：

- **创建可复用的工具库**：写一篇包含函数和变量的"库文章"，在其他文章中导入使用
- **模块化内容**：将长文章拆分为多个独立模块，按需组合
- **内容复用**：在多篇文章中共享相同的模板、样式或数据

### 基本语法

使用 `#import "site:slug"` 导入其他文章，或使用 `#include "site:slug"` 直接包含其内容：

```typst
// 导入工具库文章（slug 为 "typst-utils"）
#import "site:typst-utils": add, PI, format-date

// 在正文中使用导入的函数
圆的面积：$ A = PI * r^2 $
#add(3, 4)  // 输出 7
```

```typst
// 直接包含另一篇文章的内容
#include "site:shared-footer"
```

### 工作原理

当 PyKYCH 编译你的文章时，会自动：

1. **识别** `site:slug` 引用
2. **获取**被引用文章的内容和所有辅助文件
3. **递归解析**嵌套的跨文章引用（A 引用 B，B 引用 C）
4. **替换为实际文件路径**，构建完整的 Typst 工作区
5. **编译**所有内容为 HTML / PDF

> 循环引用（A → B → A）会被自动检测并跳过，防止无限递归。

### 示例：创建工具库

**步骤 1**：创建一篇 Typst 文章（slug: `math-lib`），包含可复用的函数：

```typst
// math-lib 文章内容
#let PI = 3.1415926535

#let add(x, y) = x + y
#let multiply(x, y) = x * y
#let square(x) = x * x

#let circle-area(r) = PI * square(r)
#let sphere-volume(r) = 4/3 * PI * r * r * r
```

**步骤 2**：在另一篇文章中导入使用：

```typst
#import "config.typ": article
#import "site:math-lib": circle-area, sphere-volume, PI

#show: article.with(
  title: "几何计算器",
  author: "你的名字",
)

= 圆的计算

给定半径 $r = 5$：
- 面积：$ A = #circle-area(5) $
- 圆周率值：$#PI$

= 球体计算

给定半径 $r = 3$：
- 体积：$ V = #sphere-volume(3) $
```

### 示例：模块化长文章

将大型文档拆分到多篇文章中：

```typst
// 主文章 (slug: complete-guide)
#import "config.typ": article
#show: article

= 完整指南

== 第一章
#include "site:guide-ch1"

== 第二章
#include "site:guide-ch2"

== 附录
#import "site:guide-appendix": data-table
#data-table
```

### 注意事项

1. **被引用文章必须是 Typst 类型**：`site:` 语法只能引用 Typst 文章，不能引用 Markdown、Wikidot 等类型
2. **缓存自动失效**：当被引用的文章更新后，引用它的文章会自动重新编译（缓存失效）
3. **避免循环引用**：A 引用 B、B 又引用 A 会导致循环，系统会自动跳过已访问的文章
4. **命名空间隔离**：每个被引用文章放在独立子目录中，其内部的相对导入（如 `#import "lib/utils.typ"`）正常工作
5. **共享配置可用**：每个被引用文章的子目录会自动包含 `config.typ`，因此可以使用所有内置模板和函数

---

## 常见问题

### Q: 为什么我的中文显示为方框或乱码？

A: 请确保系统安装了推荐的中文字体。macOS 用户可运行 `brew install --cask font-sarasa-gothic`，Linux 用户可安装 `fonts-noto-cjk`。

### Q: 编译报错 "unknown variable: note"？

A: 你只导入了 `article`，但使用了 `note` 函数。修改 import 语句：
```typst
#import "config.typ": article, note, tip, warning, danger
```

### Q: 如何在文章中嵌入原始 HTML？

A: Typst 本身不直接支持嵌入 HTML。Typt 专注于语义化标记，编译后的样式由模板统一控制。如需自定义样式，请使用 PyKYCH 的 CSS 主题系统。

### Q: PDF 下载后排版与网页不一致？

A: PDF 和 HTML 使用不同的渲染引擎（Typst 原生 vs 浏览器），在以下方面可能略有差异：
- 分页位置
- 字体渲染细节
- 某些布局函数（HTML 导出仍处于开发阶段）

### Q: 如何安装 Typst CLI？

A: 如果服务器尚未安装 Typst CLI：

```bash
# macOS
brew install typst

# Linux (通过 cargo)
cargo install typst-cli
```

### Q: 跨文章引用提示 "file not found" 错误？

A: 请检查：
1. 被引用的文章 slug 是否正确（大小写敏感）
2. 被引用的文章是否存在且是 Typst 类型
3. 被引用的文章是否使用了循环引用（A → B → A）
4. 确认文章没有被删除或修改 slug

# 或从 GitHub Releases 下载二进制文件
# https://github.com/typst/typst/releases
```

安装后，PyKYCH 会自动检测并使用 Typst CLI 进行编译。

### Q: 模板不满足需求怎么办？

A: 你可以直接编辑 `data/typst/config.typ` 文件来定制模板。修改包括：
- 调整 `base-typography` 中的排版参数
- 修改 `article` 模板的头部和尾部样式
- 添加自定义函数和 show rules

修改后所有 Typst 文章会自动使用新模板。

---

## 参考资源

- [Typst 官方文档](https://typst.app/docs/)
- [Typst 语法参考](https://typst.app/docs/reference/syntax/)
- [Typst GitHub 仓库](https://github.com/typst/typst)
- [PyKYCH 主题开发指南](主题开发指南.md)
