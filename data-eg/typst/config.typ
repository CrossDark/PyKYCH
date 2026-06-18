// PyKYCH 共享 Typst 配置文件
// 此文件会被所有 Typst 文章自动导入（如存在）。
//
// 用法：在你的 Typst 文章中使用
//   #import "config.typ": template
//   #show: template
//
// 你可以根据需要修改此文件，添加自定义模板、函数和样式。

// 如果你安装了 tufted 包，可以取消下面的注释以使用 tufted 模板：
// #import "@preview/tufted:0.1.1"
// #let template = tufted.tufted-web.with(
//   title: "PyKYCH",
// )

// 默认：简单模板（不依赖外部包）
#let template = doc

// 自定义函数示例
#let note(body) = {
  block(
    fill: rgb("#f0f7ff"),
    inset: 8pt,
    radius: 4pt,
    stroke: 1pt + rgb("#3b82f6"),
    body
  )
}

#let warning(body) = {
  block(
    fill: rgb("#fff8f0"),
    inset: 8pt,
    radius: 4pt,
    stroke: 1pt + rgb("#f59e0b"),
    body
  )
}
