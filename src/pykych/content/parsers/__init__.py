"""
语法解析器模块 — BBCode 和 Wikidot 标记语言到 HTML 的转换。

支持的解析器:
    - bbcode.py:  BBCode（论坛标记语言）→ HTML
    - wikidot.py: Wikidot 标记语言 → HTML

用法:
    from pykych.content.parsers.bbcode import parse_bbcode
    from pykych.content.parsers.wikidot import parse_wikidot
"""

from .bbcode import parse_bbcode
from .wikidot import parse_wikidot

__all__ = ["parse_bbcode", "parse_wikidot"]
