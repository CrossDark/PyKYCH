"""
内容管理模块 (content) — 文章、标签、评论、评分、文件、外部站点。

提供 PyKYCH 核心内容功能的统一接口:
    - articles.py:  统一文章 CRUD（MD/Wikidot/HTML/BBCode）
    - tags.py:      标签管理与文章关联
    - comments.py:  全文评论 + 行评论
    - ratings.py:   评分系统（[-1, 1] 区间）
    - files.py:     静态文件上传管理
    - external.py:  外部 HTML 站点抓取与管理
    - parsers/:     语法解析器（BBCode、Wikidot）

用法:
    from pykych.content import articles, tags, comments, ratings
"""

from .articles import (
    ARTICLE_TYPES,
    get_article_config,
    list_articles,
    get_article,
    create_article,
    update_article,
    delete_article,
    seed_db,
)
from .tags import (
    get_all_tags,
    get_all_tags_with_counts,
    get_tags_for_article,
    set_article_tags,
    auto_tag_article,
    create_tag,
    rename_tag,
    delete_tag,
    get_articles_by_tag,
)
from .comments import (
    get_comments,
    add_comment,
    get_comment_count,
    delete_comment,
    get_line_comments,
    get_line_comments_by_line,
    get_line_comment_counts,
    add_line_comment,
    delete_line_comment,
)
from .ratings import (
    get_article_rating,
    get_user_rating,
    set_rating,
    delete_rating,
    get_all_ratings,
)

__all__ = [
    # 文章
    "ARTICLE_TYPES",
    "get_article_config",
    "list_articles",
    "get_article",
    "create_article",
    "update_article",
    "delete_article",
    "seed_db",
    # 标签
    "get_all_tags",
    "get_all_tags_with_counts",
    "get_tags_for_article",
    "set_article_tags",
    "auto_tag_article",
    "create_tag",
    "rename_tag",
    "delete_tag",
    "get_articles_by_tag",
    # 评论
    "get_comments",
    "add_comment",
    "get_comment_count",
    "delete_comment",
    "get_line_comments",
    "get_line_comments_by_line",
    "get_line_comment_counts",
    "add_line_comment",
    "delete_line_comment",
    # 评分
    "get_article_rating",
    "get_user_rating",
    "set_rating",
    "delete_rating",
    "get_all_ratings",
]
