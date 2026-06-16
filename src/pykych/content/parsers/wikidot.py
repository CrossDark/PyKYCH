"""
Wikidot 语法解析器 — 将 Wikidot 标记语言转换为 HTML。

支持的语法：
  标题:    + h1 / ++ h2 / +++ h3 / ++++ h4
  粗体:    **text**
  斜体:    //text//
  下划线:  __text__
  删除线:  --text--
  上标:    ^^text^^
  下标:    ,,text,,
  行内代码: {{text}}
  块元素:  [[code]] [[/code]]  [[div]] [[/div]]  [[table]] [[/table]]
           [[span class="..."]] [[/span]]
           [[collapsible show="..." hide="..."]] [[/collapsible]]
  对齐:    [[=]] / [[>]] / [[==]]  [[/=]] / [[/>]] / [[/==]]
  字号:    [[size ...]] [[/size]]
  颜色:    [[color ...]] [[/color]]
  换行:    [[br]]
  锚点:    [[# name]]
  转义:    @@text@@
  引用:    > text
  列表:    * 无序 / # 有序
  链接:    [[[url | text]]]  [[[/slug | text]]]
  提示框:  !!! note / !!! warning / !!! danger / !!! info / !!! tip
  图片:    [[image src]]
"""

import re
from typing import Dict, List
from html import escape as html_escape


# ── 预编译正则 ──────────────────────────────────────────────

RE_CODE_BLOCK = re.compile(
    r"\[\[code(?:\s+type\s*=\s*['\"]([^'\"]+)['\"])?\]\]"
    r"(.*?)\[\[/code\]\]",
    re.DOTALL | re.IGNORECASE,
)
RE_DIV_BLOCK = re.compile(
    r'\[\[div\s+class="([^"]*)"\]\](.*?)\[\[/div\]\]',
    re.DOTALL | re.IGNORECASE,
)
RE_TABLE_BLOCK = re.compile(
    r"\[\[table\]\](.*?)\[\[/table\]\]", re.DOTALL | re.IGNORECASE
)

# 新增：span, collapsible, size, color, 对齐
RE_SPAN_CLASS = re.compile(
    r'\[\[span\s+class="([^"]*)"\]\](.*?)\[\[/span\]\]',
    re.DOTALL | re.IGNORECASE,
)
RE_SPAN_STYLE = re.compile(
    r"\[\[span\s+style=\"([^\"]*)\"\]\](.*?)\[\[/span\]\]",
    re.DOTALL | re.IGNORECASE,
)
RE_COLLAPSIBLE = re.compile(
    r'\[\[collapsible\s+show="([^"]*)"\s+hide="([^"]*)"\]\]'
    r"(.*?)\[\[/collapsible\]\]",
    re.DOTALL | re.IGNORECASE,
)
RE_SIZE = re.compile(
    r"\[\[size\s+([^\]]+)\]\](.*?)\[\[/size\]\]",
    re.DOTALL | re.IGNORECASE,
)
RE_COLOR = re.compile(
    r"\[\[color\s+([^\]]+)\]\](.*?)\[\[/color\]\]",
    re.DOTALL | re.IGNORECASE,
)

# 对齐块
RE_CENTER = re.compile(
    r"\[\[=\]\](.*?)\[\[/=\]\]", re.DOTALL
)
RE_RIGHT = re.compile(
    r"\[\[>\]\](.*?)\[\[/>\]\]", re.DOTALL
)
RE_JUSTIFY = re.compile(
    r"\[\[==\]\](.*?)\[\[/==\]\]", re.DOTALL
)

# 上标 / 下标
RE_SUPERSCRIPT = re.compile(r"\^\^(.+?)\^\^")
RE_SUBSCRIPT = re.compile(r",,(.+?),,")

# 换行 / 锚点 / 转义
RE_LINE_BREAK = re.compile(r"\[\[br\]\]", re.IGNORECASE)
RE_ANCHOR = re.compile(r"\[\[#\s+([^\]]+)\]\]")
RE_ESCAPE = re.compile(r"@@(.+?)@@", re.DOTALL)

RE_BOLD = re.compile(r"\*\*(.+?)\*\*")
RE_ITALIC = re.compile(r"(?<!\\)//(.+?)(?<!\\)//")
RE_UNDERLINE = re.compile(r"__(.+?)__")
RE_STRIKETHROUGH = re.compile(r"--(.+?)--")
RE_INLINE_CODE = re.compile(r"\{\{(.+?)\}\}")

RE_WIKI_LINK = re.compile(r"\[\[\[([^\]]+?)(?:\s*\|\s*([^\]]+?))?\]\]\]")
RE_IMAGE = re.compile(r"\[\[image\s+([^\]]+?)\]\]", re.IGNORECASE)

RE_H4 = re.compile(r"^\+\+\+\+(?!\+)\s+(.+)$", re.MULTILINE)
RE_H3 = re.compile(r"^\+\+\+(?!\+)\s+(.+)$", re.MULTILINE)
RE_H2 = re.compile(r"^\+\+(?!\+)\s+(.+)$", re.MULTILINE)
RE_H1 = re.compile(r"^\+(?!\+)\s+(.+)$", re.MULTILINE)

RE_BLOCKQUOTE = re.compile(r"^(&gt;|\>)\s?(.*)$", re.MULTILINE)

RE_UNORDERED_LIST_ITEM = re.compile(r"^(\s*)\*\s+(.+)$", re.MULTILINE)
RE_ORDERED_LIST_ITEM = re.compile(r"^(\s*)#\s+(.+)$", re.MULTILINE)

RE_HR = re.compile(r"^-{4,}$", re.MULTILINE)

RE_ADMONITION = re.compile(
    r"^!!!\s+(note|warning|danger|info|tip)\s*\n(.*?)(?=\n!!!|\n\[\[|\Z)",
    re.DOTALL | re.MULTILINE,
)

RE_HTML_BLOCK = re.compile(
    r'(<(?:pre|table|ul|ol|blockquote|div|details|summary)\b.*?</(?:pre|table|ul|ol|blockquote|div|details|summary)>)',
    re.DOTALL,
)

# 字号映射
_SIZE_MAP: Dict[str, str] = {
    "smaller": "0.75rem",
    "xx-small": "0.6rem",
    "x-small": "0.75rem",
    "small": "0.875rem",
    "medium": "1rem",
    "large": "1.25rem",
    "x-large": "1.5rem",
    "xx-large": "2rem",
    "larger": "1.5rem",
}

# 颜色名映射
_COLOR_NAMES: Dict[str, str] = {
    "red": "#ef4444",
    "green": "#10b981",
    "blue": "#3b82f6",
    "yellow": "#f59e0b",
    "orange": "#f97316",
    "purple": "#8b5cf6",
    "pink": "#ec4899",
    "gray": "#6b7280",
    "grey": "#6b7280",
    "black": "#111827",
    "white": "#ffffff",
    "cyan": "#06b6d4",
    "teal": "#14b8a6",
    "indigo": "#6366f1",
}


class WikidotParser:
    """Wikidot 语法解析器，使用共享占位符字典确保递归解析时占位符可正常替换。"""

    def __init__(self):
        self._blocks: Dict[str, str] = {}
        self._counter = 0

    def _store_block(self, html: str) -> str:
        ph = f"%%BLOCK_{self._counter}%%"
        self._counter += 1
        self._blocks[ph] = html
        return ph

    def parse(self, source: str) -> str:
        self._blocks.clear()
        self._counter = 0
        return self._convert(source)

    def _convert(self, source: str) -> str:
        # 1. 提取并保护块级元素（按优先级排序）
        # 1a. 转义块 — 最早处理，用占位符保护，内部不做任何解析
        source = RE_ESCAPE.sub(
            lambda m: self._store_block(html_escape(m.group(1))),
            source,
        )

        # 1b. 代码块（支持 type 属性）
        source = RE_CODE_BLOCK.sub(
            lambda m: self._store_block(
                _render_code(m.group(2), m.group(1))
            ),
            source,
        )
        # 1c. 可折叠块
        source = RE_COLLAPSIBLE.sub(
            lambda m: self._store_block(
                _render_collapsible(self, m.group(1), m.group(2), m.group(3))
            ),
            source,
        )
        # 1d. 表格
        source = RE_TABLE_BLOCK.sub(
            lambda m: self._store_block(_render_table(self, m.group(1))), source
        )
        # 1e. div 容器
        source = RE_DIV_BLOCK.sub(
            lambda m: self._store_block(_render_div(self, m.group(1), m.group(2))),
            source,
        )
        # 1f. span（块级处理以支持嵌套内联）
        source = RE_SPAN_CLASS.sub(
            lambda m: self._store_block(
                f'<span class="{m.group(1)}">{self._convert(m.group(2))}</span>'
            ),
            source,
        )
        source = RE_SPAN_STYLE.sub(
            lambda m: self._store_block(
                f'<span style="{m.group(1)}">{self._convert(m.group(2))}</span>'
            ),
            source,
        )
        # 1g. 字号 / 颜色
        source = RE_SIZE.sub(
            lambda m: self._store_block(_render_size(self, m.group(1), m.group(2))),
            source,
        )
        source = RE_COLOR.sub(
            lambda m: self._store_block(_render_color(self, m.group(1), m.group(2))),
            source,
        )
        # 1h. 对齐
        source = RE_CENTER.sub(
            lambda m: self._store_block(
                f'<div style="text-align:center">{self._convert(m.group(1))}</div>'
            ),
            source,
        )
        source = RE_RIGHT.sub(
            lambda m: self._store_block(
                f'<div style="text-align:right">{self._convert(m.group(1))}</div>'
            ),
            source,
        )
        source = RE_JUSTIFY.sub(
            lambda m: self._store_block(
                f'<div style="text-align:justify">{self._convert(m.group(1))}</div>'
            ),
            source,
        )

        # 2. 内联格式（在块级保护之后）
        source = RE_BOLD.sub(r"<strong>\1</strong>", source)
        source = RE_ITALIC.sub(r"<em>\1</em>", source)
        source = RE_UNDERLINE.sub(r"<u>\1</u>", source)
        source = RE_STRIKETHROUGH.sub(r"<s>\1</s>", source)
        source = RE_SUPERSCRIPT.sub(r"<sup>\1</sup>", source)
        source = RE_SUBSCRIPT.sub(r"<sub>\1</sub>", source)
        source = RE_INLINE_CODE.sub(r"<code>\1</code>", source)

        # 3. 链接和图片
        source = RE_WIKI_LINK.sub(_link_replacer, source)
        source = RE_IMAGE.sub(r'<img src="\1" alt="" class="wiki-image" />', source)

        # 4. 标题
        source = RE_H4.sub(r"<h4>\1</h4>", source)
        source = RE_H3.sub(r"<h3>\1</h3>", source)
        source = RE_H2.sub(r"<h2>\1</h2>", source)
        source = RE_H1.sub(r"<h1>\1</h1>", source)

        # 5. 水平线
        source = RE_HR.sub(r"<hr />", source)

        # 6. 换行和锚点
        source = RE_LINE_BREAK.sub(r"<br />", source)
        source = RE_ANCHOR.sub(r'<a name="\1"></a>', source)

        # 7. 提示框
        source = RE_ADMONITION.sub(lambda m: _admonition_replacer(self, m), source)

        # 8. 引用块
        source = _render_blockquotes(source)

        # 9. 列表
        source = _render_lists(source)

        # 10. 恢复占位符（共享字典，递归调用也在这里恢复）
        for ph, html in self._blocks.items():
            source = source.replace(ph, html)

        # 11. 段落包装
        source = _wrap_paragraphs(source)

        return source


# ── 模块级单例 ──────────────────────────────────────────────

_parser = WikidotParser()


def parse_wikidot(source: str) -> str:
    return _parser.parse(source)


# ── 块级渲染函数 ────────────────────────────────────────────


def _render_code(code: str, lang: str | None = None) -> str:
    escaped = html_escape(code.strip())
    cls = f' class="language-{lang}"' if lang else ""
    return f"<pre><code{cls}>{escaped}</code></pre>"


def _render_collapsible(parser: WikidotParser, show: str, hide: str, content: str) -> str:
    inner = parser._convert(content)
    return (
        f'<details class="wiki-collapsible">'
        f'<summary><span class="collapsible-show">{show}</span>'
        f'<span class="collapsible-hide">{hide}</span></summary>'
        f'<div class="collapsible-content">{inner}</div>'
        f"</details>"
    )


def _render_size(parser: WikidotParser, size: str, content: str) -> str:
    size_key = size.strip().lower()
    css_size = _SIZE_MAP.get(size_key, size_key)
    inner = _inline_only(content)
    return f'<span style="font-size:{css_size}">{inner}</span>'


def _render_color(parser: WikidotParser, color: str, content: str) -> str:
    color_key = color.strip().lower()
    css_color = _COLOR_NAMES.get(color_key, color_key)
    inner = _inline_only(content)
    return f'<span style="color:{css_color}">{inner}</span>'


def _render_div(parser: WikidotParser, cls: str, content: str) -> str:
    inner = parser._convert(content)
    return f'<div class="{cls}">{inner}</div>'


def _render_table(parser: WikidotParser, raw: str) -> str:
    lines = raw.strip().splitlines()
    if not lines:
        return ""
    rows_html = []
    is_first = True
    for line in lines:
        line = line.strip()
        if not line:
            continue
        cells = []
        for cell in line.split("|"):
            cell = cell.strip()
            if not cell:
                continue
            cells.append(parser._convert(cell) if is_first else _inline_only(cell))
        if not cells:
            continue
        tag = "th" if is_first else "td"
        row = "".join(f"<{tag}>{c}</{tag}>" for c in cells)
        rows_html.append(f"<tr>{row}</tr>")
        is_first = False
    return f'<table class="wiki-table"><tbody>{"".join(rows_html)}</tbody></table>'


def _inline_only(text: str) -> str:
    text = RE_BOLD.sub(r"<strong>\1</strong>", text)
    text = RE_ITALIC.sub(r"<em>\1</em>", text)
    text = RE_UNDERLINE.sub(r"<u>\1</u>", text)
    text = RE_STRIKETHROUGH.sub(r"<s>\1</s>", text)
    text = RE_SUPERSCRIPT.sub(r"<sup>\1</sup>", text)
    text = RE_SUBSCRIPT.sub(r"<sub>\1</sub>", text)
    text = RE_INLINE_CODE.sub(r"<code>\1</code>", text)
    text = RE_WIKI_LINK.sub(_link_replacer, text)
    return text


def _link_replacer(m: re.Match) -> str:
    url = m.group(1).strip()
    text = m.group(2).strip() if m.group(2) else url
    if url.startswith("/"):
        href = url
    elif url.startswith("http://") or url.startswith("https://"):
        href = url
    else:
        href = f"/wikidot/{url}"
    return f'<a href="{href}">{text}</a>'


def _admonition_replacer(parser: WikidotParser, m: re.Match) -> str:
    atype = m.group(1).lower()
    content = parser._convert(m.group(2).strip())
    title_map = {
        "note": "📝 注意",
        "warning": "⚠️ 警告",
        "danger": "🚫 危险",
        "info": "ℹ️ 信息",
        "tip": "💡 提示",
    }
    title = title_map.get(atype, atype)
    return f'<div class="admonition {atype}"><div class="admonition-title">{title}</div>{content}</div>'


def _render_blockquotes(text: str) -> str:
    lines = text.splitlines()
    result = []
    buf = []
    for line in lines:
        m = RE_BLOCKQUOTE.match(line)
        if m:
            buf.append(m.group(2))
        else:
            if buf:
                result.append(f"<blockquote>{'<br />'.join(buf)}</blockquote>")
                buf.clear()
            result.append(line)
    if buf:
        result.append(f"<blockquote>{'<br />'.join(buf)}</blockquote>")
    return "\n".join(result)


def _render_lists(text: str) -> str:
    lines = text.splitlines()
    result = []
    list_buf = []
    list_type = None

    def _flush():
        nonlocal list_buf, list_type
        if list_buf:
            tag = list_type or "ul"
            items = "".join(f"<li>{item}</li>" for item in list_buf)
            result.append(f"<{tag}>{items}</{tag}>")
            list_buf.clear()
            list_type = None

    for line in lines:
        um = RE_UNORDERED_LIST_ITEM.match(line)
        om = RE_ORDERED_LIST_ITEM.match(line)
        if um:
            if list_type == "ol":
                _flush()
            list_type = "ul"
            indent = len(um.group(1))
            prefix = "  " * indent if indent > 0 else ""
            list_buf.append(f"{prefix}{_inline_only(um.group(2))}")
        elif om:
            if list_type == "ul":
                _flush()
            list_type = "ol"
            indent = len(om.group(1))
            prefix = "  " * indent if indent > 0 else ""
            list_buf.append(f"{prefix}{_inline_only(om.group(2))}")
        else:
            _flush()
            result.append(line)

    _flush()
    return "\n".join(result)


def _wrap_paragraphs(text: str) -> str:
    # 保护多行 HTML 块
    placeholders: list = []

    def _protect(m: re.Match) -> str:
        ph = f"%%WRAP_BLOCK_{len(placeholders)}%%"
        placeholders.append((ph, m.group(0)))
        return ph

    text = RE_HTML_BLOCK.sub(_protect, text)

    block_tags = {"<h1", "<h2", "<h3", "<h4", "<h5", "<h6", "<hr", "<li", "<img"}
    lines = text.splitlines()
    result = []
    buf = []

    def _flush_p():
        if buf:
            content = "\n".join(buf).strip()
            if content:
                result.append(f"<p>{content}</p>")
            buf.clear()

    for line in lines:
        stripped = line.strip()
        if not stripped:
            _flush_p()
            continue
        if any(stripped.startswith(tag) for tag in block_tags) or stripped.startswith("%%WRAP_BLOCK_"):
            _flush_p()
            result.append(line)
        else:
            buf.append(line)

    _flush_p()

    output = "\n".join(result)
    for ph, html in placeholders:
        output = output.replace(ph, html)

    return output
