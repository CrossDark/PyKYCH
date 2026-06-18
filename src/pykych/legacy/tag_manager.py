"""
标签管理模块（旧版兼容层） — 从 content.tags 重新导出。

⚠️ 此模块已废弃，请使用 pykych.content.tags 替代。
"""

# 从新版模块重新导出所有符号，保持向后兼容
from ..content.tags import (
    get_or_create_tag,
    get_all_tags,
    get_tag_by_name,
    get_tag_by_id,
    get_all_tags_with_counts,
    create_tag,
    rename_tag,
    delete_tag,
    add_tag_to_article,
    remove_tag_from_article,
    get_tags_for_article,
    set_article_tags,
    get_articles_by_tag,
    auto_tag_article,
    cleanup_orphan_tags,
)

