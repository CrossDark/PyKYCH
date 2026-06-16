# Content 内容管理模块

文章、标签、评论、评分、文件的统一管理接口。

## 模块结构

| 文件 | 说明 |
|------|------|
| `__init__.py` | 公开接口导出 |
| `articles.py` | 统一文章 CRUD（支持 MD/Wikidot/HTML/BBCode 四种类型） |
| `tags.py` | 标签 CRUD、文章-标签关联、按标签查询 |
| `comments.py` | 全文评论 + 行评论（逐行短评，限 20 字） |
| `ratings.py` | 评分系统（[-1.00, 1.00] 区间） |
| `files.py` | 静态文件上传管理（UUID 文件名，50MB 限制） |
| `external.py` | 外部 HTML 站点抓取与缓存 |
| `parsers/` | 语法解析器 |

## 语法解析器

| 解析器 | 输入 | 输出 |
|--------|------|------|
| `parsers/bbcode.py` | BBCode（论坛标记语言） | HTML |
| `parsers/wikidot.py` | Wikidot 标记语言 | HTML |

### BBCode 支持语法
粗体、斜体、下划线、删除线、上标/下标、链接、图片、引用、代码块、列表、表格、折叠块、字体/颜色/背景色、对齐、水平线、锚点、视频/音频

### Wikidot 支持语法
标题(h1~h4)、粗体/斜体/下划线/删除线、上下标、行内代码、DIV/SPAN/表格/折叠块、对齐、字号/颜色、换行/锚点/转义、引用、列表、Wiki链接、图片、提示框(note/warning/danger/info/tip)

## 使用示例

```python
from pykych.content.articles import list_articles, get_article, create_article
from pykych.content.tags import get_all_tags, set_article_tags
from pykych.content.comments import get_comments, add_comment
from pykych.content.ratings import get_article_rating, set_rating
from pykych.content.parsers import parse_bbcode, parse_wikidot

# 文章操作
articles = await list_articles("md", page=1, per_page=10)
article = await get_article("html", "my-slug")
new_article = await create_article("bbcode", "test", "标题", "内容", author_id=1)

# 标签
tags = await get_all_tags()
await set_article_tags("md", "my-article", ["python", "教程"])

# 评分
rating = await get_article_rating("md", "my-article")
await set_rating("md", "my-article", "用户名", 0.8)

# 解析
html = parse_bbcode("[b]粗体[/b]")
html = parse_wikidot("**粗体**")
```
