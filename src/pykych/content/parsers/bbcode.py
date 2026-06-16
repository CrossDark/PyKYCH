"""
BBCode 语法解析器 — 将 BBCode（论坛标记语言）转换为 HTML。

支持的语法：
  粗体:       [b]text[/b]
  斜体:       [i]text[/i]
  下划线:     [u]text[/u]
  删除线:     [s]text[/s]
  上标:       [sup]text[/sup]
  下标:       [sub]text[/sub]
  链接:       [url]https://...[/url]
              [url=https://...]text[/url]
  邮箱:       [email]a@b.com[/email]
  图片:       [img]https://...[/img]
  引用:       [quote]text[/quote]
              [quote=作者]text[/quote]
  代码:       [code]...[/code]
              [code=python]...[/code]
  列表:       [list][*]item1[*]item2[/list]
              [list=1][*]item1[*]item2[/list]  (有序)
  字号:       [size=large]text[/size]
  颜色:       [color=red]text[/color]
              [color=#ff0000]text[/color]
  居中:       [center]text[/center]
  右对齐:     [right]text[/right]
  左对齐:     [left]text[/left]
  表格:       [table][tr][td]cell[/td][/tr][/table]
              [table][tr][th]header[/th][/tr][/table]
  水平线:     [hr]
  锚点:       [anchor]name[/anchor]
  折叠:       [spoiler]text[/spoiler]
              [spoiler=标题]text[/spoiler]
  字体:       [font=fontname]text[/font]
  背景色:     [bg=color]text[/bg]
  多媒体:     [video]url[/video]
              [audio]url[/audio]
  转义:       \\[b\\] → 字面量显示
  嵌套列表:   [list][*]item1[*][list][*]subitem[/list][/list]
"""

import re
from html import escape as html_escape


def parse_bbcode(text: str) -> str:
    """将 BBCode 文本渲染为 HTML。"""
    if not text:
        return ""

    # 先转义 HTML 以防止 XSS（除了我们要生成的标签）
    out = html_escape(text)

    # ── 块级元素（先处理，防止被内联标签干扰）────

    # 代码块 [code]...[/code] 或 [code=lang]...[/code]
    out = re.sub(
        r'\[code(?:=(\w+))?\](.*?)\[/code\]',
        lambda m: _render_code(m.group(2), m.group(1)),
        out,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # 引用块 [quote]...[/quote] 或 [quote=author]...[/quote]
    out = re.sub(
        r'\[quote(?:=(.*?))?\](.*?)\[/quote\]',
        lambda m: _render_quote(m.group(2), m.group(1)),
        out,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # 折叠块 [spoiler]...[/spoiler] 或 [spoiler=title]...[/spoiler]
    out = re.sub(
        r'\[spoiler(?:=(.*?))?\](.*?)\[/spoiler\]',
        lambda m: _render_spoiler(m.group(2), m.group(1)),
        out,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # 列表 [list]...[/*][/list] 支持 [*] 和 [/*] 两种标记
    out = _parse_lists(out)

    # 表格 [table]...[tr]...[td]...[/td]...[/tr]...[/table]
    out = re.sub(
        r'\[table\](.*?)\[/table\]',
        lambda m: _render_table(m.group(1)),
        out,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # 水平线 [hr]
    out = re.sub(r'\[hr\]', '<hr>', out, flags=re.IGNORECASE)

    # ── 对齐标签（块级）──

    # 居中 [center]...[/center]
    out = re.sub(
        r'\[center\](.*?)\[/center\]',
        r'<div style="text-align:center">\1</div>',
        out,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # 右对齐 [right]...[/right]
    out = re.sub(
        r'\[right\](.*?)\[/right\]',
        r'<div style="text-align:right">\1</div>',
        out,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # 左对齐 [left]...[/left]
    out = re.sub(
        r'\[left\](.*?)\[/left\]',
        r'<div style="text-align:left">\1</div>',
        out,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # ── 内联元素 ──

    # 粗体 [b]...[/b]
    out = re.sub(
        r'\[b\](.*?)\[/b\]', r'<strong>\1</strong>',
        out, flags=re.DOTALL | re.IGNORECASE,
    )

    # 斜体 [i]...[/i]
    out = re.sub(
        r'\[i\](.*?)\[/i\]', r'<em>\1</em>',
        out, flags=re.DOTALL | re.IGNORECASE,
    )

    # 下划线 [u]...[/u]
    out = re.sub(
        r'\[u\](.*?)\[/u\]', r'<u>\1</u>',
        out, flags=re.DOTALL | re.IGNORECASE,
    )

    # 删除线 [s]...[/s]
    out = re.sub(
        r'\[s\](.*?)\[/s\]', r'<s>\1</s>',
        out, flags=re.DOTALL | re.IGNORECASE,
    )

    # 上标 [sup]...[/sup]
    out = re.sub(
        r'\[sup\](.*?)\[/sup\]', r'<sup>\1</sup>',
        out, flags=re.DOTALL | re.IGNORECASE,
    )

    # 下标 [sub]...[/sub]
    out = re.sub(
        r'\[sub\](.*?)\[/sub\]', r'<sub>\1</sub>',
        out, flags=re.DOTALL | re.IGNORECASE,
    )

    # 链接 [url]url[/url] 和 [url=url]text[/url]
    out = re.sub(
        r'\[url=([^\]]+)\](.*?)\[/url\]',
        r'<a href="\1" target="_blank" rel="noopener noreferrer">\2</a>',
        out, flags=re.DOTALL | re.IGNORECASE,
    )
    out = re.sub(
        r'\[url\](.*?)\[/url\]',
        r'<a href="\1" target="_blank" rel="noopener noreferrer">\1</a>',
        out, flags=re.DOTALL | re.IGNORECASE,
    )

    # 邮箱 [email]email[/email]
    out = re.sub(
        r'\[email\](.*?)\[/email\]',
        r'<a href="mailto:\1">\1</a>',
        out, flags=re.DOTALL | re.IGNORECASE,
    )

    # 图片 [img]url[/img]
    out = re.sub(
        r'\[img\](.*?)\[/img\]',
        r'<img src="\1" alt="" loading="lazy" style="max-width:100%">',
        out, flags=re.DOTALL | re.IGNORECASE,
    )

    # 字号 [size=...]...[/size]
    out = re.sub(
        r'\[size=([^\]]+)\](.*?)\[/size\]',
        r'<span style="font-size:\1">\2</span>',
        out, flags=re.DOTALL | re.IGNORECASE,
    )

    # 颜色 [color=...]...[/color]
    out = re.sub(
        r'\[color=([^\]]+)\](.*?)\[/color\]',
        r'<span style="color:\1">\2</span>',
        out, flags=re.DOTALL | re.IGNORECASE,
    )

    # 字体 [font=...]...[/font]
    out = re.sub(
        r'\[font=([^\]]+)\](.*?)\[/font\]',
        r'<span style="font-family:\1">\2</span>',
        out, flags=re.DOTALL | re.IGNORECASE,
    )

    # 背景色 [bg=...]...[/bg]
    out = re.sub(
        r'\[bg=([^\]]+)\](.*?)\[/bg\]',
        r'<span style="background-color:\1">\2</span>',
        out, flags=re.DOTALL | re.IGNORECASE,
    )

    # 视频 [video]url[/video]
    out = re.sub(
        r'\[video\](.*?)\[/video\]',
        r'<video controls style="max-width:100%"><source src="\1"></video>',
        out, flags=re.DOTALL | re.IGNORECASE,
    )

    # 音频 [audio]url[/audio]
    out = re.sub(
        r'\[audio\](.*?)\[/audio\]',
        r'<audio controls><source src="\1"></audio>',
        out, flags=re.DOTALL | re.IGNORECASE,
    )

    # 锚点 [anchor]name[/anchor]
    out = re.sub(
        r'\[anchor\](.*?)\[/anchor\]',
        r'<span id="\1" class="bbcode-anchor"></span>',
        out, flags=re.DOTALL | re.IGNORECASE,
    )

    # ── 清理：恢复被 html_escape 转义的等号（在已被我们替换的标签中不存在了）
    # 这个不需要额外处理，因为我们先 escape 了，然后用正则匹配的字面量
    # 但正则匹配的是 [] 包裹的内容，所以 HTML 实体在 [] 外的保持转义

    # 转义 \[ → [ (恢复被转义的方括号，使其保持字面意义)
    out = re.sub(r'\\\[', '[', out)
    out = re.sub(r'\\\]', ']', out)

    return out


# ── 辅助渲染函数 ────────────────────────────────────────


def _render_code(code: str, lang: str = None) -> str:
    """渲染代码块。"""
    # 代码块内的 HTML 实体已经被 escape 处理
    lang_attr = f' class="language-{lang}"' if lang else ""
    return f'<pre><code{lang_attr}>{code.strip()}</code></pre>'


def _render_quote(text: str, author: str = None) -> str:
    """渲染引用块。"""
    author_html = f'<cite>{author}</cite>' if author else ""
    return f'<blockquote class="bbcode-quote">{author_html}{text.strip()}</blockquote>'


def _render_spoiler(text: str, title: str = None) -> str:
    """渲染折叠块。"""
    label = title or "Spoiler"
    # 使用 details/summary 实现原生折叠
    return (
        f'<details class="bbcode-spoiler">'
        f'<summary>{label}</summary>'
        f'<div class="bbcode-spoiler-content">{text.strip()}</div>'
        f'</details>'
    )


def _render_table(content: str) -> str:
    """渲染表格。"""
    rows_html = []
    rows = re.split(r'\[/tr\]', content, flags=re.IGNORECASE)
    for row in rows:
        row = row.strip()
        if not row:
            continue
        # 移除开头可能的 [tr]
        row = re.sub(r'^\[tr\]', '', row, flags=re.IGNORECASE).strip()

        cells = []
        # 匹配 [td]...[/td] 和 [th]...[/th]
        for m in re.finditer(
            r'\[(td|th)\](.*?)\[/\1\]', row, re.DOTALL | re.IGNORECASE
        ):
            tag = m.group(1)
            cell_content = m.group(2).strip()
            cells.append(f'<{tag}>{cell_content}</{tag}>')

        if cells:
            rows_html.append(f'<tr>{"".join(cells)}</tr>')

    return (
        f'<div class="bbcode-table-wrapper">'
        f'<table class="bbcode-table">{"".join(rows_html)}</table>'
        f'</div>'
    )


def _parse_lists(text: str) -> str:
    """解析 BBCode 列表，支持嵌套。"""

    # 递归处理 [list]...[/*][/list]
    def replace_list(match: re.Match) -> str:
        list_type = match.group(1)  # "1" for ordered, None for unordered
        inner = match.group(2)      # list content
        is_ordered = list_type == "1"

        # 解析列表项：先按 [/*] 闭合标签拆分，否则按 [*] 开头拆分
        items = []
        if re.search(r'\[/\*\]', inner, re.IGNORECASE):
            # 使用 [/*] 闭合标签
            parts = re.split(r'\[/\*\]', inner, flags=re.IGNORECASE)
        else:
            # 使用 [*] 开头拆分
            parts = re.split(r'\[\*\]', inner, flags=re.IGNORECASE)

        for part in parts:
            part = part.strip()
            if not part:
                continue
            # Remove leading [*] if present
            part = re.sub(r'^\[\*\]', '', part, flags=re.IGNORECASE).strip()
            if not part:
                continue
            # 递归处理嵌套列表
            part = _parse_lists(part)
            items.append(f'<li>{part}</li>')

        tag = "ol" if is_ordered else "ul"
        return f'<{tag} class="bbcode-list">{"".join(items)}</{tag}>'

    return re.sub(
        r'\[list(?:=(1))?\](.*?)\[/list\]',
        replace_list,
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
