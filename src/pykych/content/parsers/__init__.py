"""
语法解析器模块 — BBCode、Wikidot 和 Typst 标记语言到 HTML 的转换。

支持的解析器:
    - bbcode.py:       BBCode（论坛标记语言）→ HTML
    - wikidot.py:      Wikidot 标记语言 → HTML
    - typst_parser.py: Typst 排版语言 → HTML / PDF

用法:
    from pykych.content.parsers.bbcode import parse_bbcode
    from pykych.content.parsers.wikidot import parse_wikidot
    from pykych.content.parsers.typst_parser import compile_typst_to_html
"""

from .bbcode import parse_bbcode
from .wikidot import parse_wikidot
from .typst_parser import (
    compile_typst_to_html,
    compile_typst_to_pdf,
    check_typst_available,
    get_aux_files,
    save_aux_file,
    delete_aux_file,
    build_and_cache_typst,
    get_cached_typst_html,
    get_cached_typst_pdf,
    invalidate_typst_cache,
)

__all__ = [
    "parse_bbcode",
    "parse_wikidot",
    "compile_typst_to_html",
    "compile_typst_to_pdf",
    "check_typst_available",
    "get_aux_files",
    "save_aux_file",
    "delete_aux_file",
    "build_and_cache_typst",
    "get_cached_typst_html",
    "get_cached_typst_pdf",
    "invalidate_typst_cache",
]
