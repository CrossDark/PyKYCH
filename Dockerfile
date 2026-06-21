# ── PyKYCH Docker 镜像 ─────────────────────────────────────

FROM python:3.12-slim

WORKDIR /app

# 使用国内 Debian 镜像加速（阿里云）
RUN sed -i 's|http://deb.debian.org|http://mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources && \
    sed -i 's|http://security.debian.org|http://mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 安装 Typst CLI（用于 Typst 文章渲染）
# 从 GitHub Releases 下载预编译二进制
RUN ARCH=$(uname -m | sed 's/x86_64/x86_64/;s/aarch64/aarch64/') && \
    TYPST_VERSION="0.14.2" && \
    curl -fsSL "https://github.com/typst/typst/releases/download/v${TYPST_VERSION}/typst-${ARCH}-unknown-linux-musl.tar.xz" \
        -o /tmp/typst.tar.xz && \
    tar -xJf /tmp/typst.tar.xz -C /usr/local/bin --strip-components=1 && \
    rm /tmp/typst.tar.xz && \
    typst --version

# 安装 Python 依赖
COPY pyproject.toml .
RUN pip install --no-cache-dir \
    "lihil[standard]>=0.2.41" \
    "jinja2>=3.1.0" \
    "aiomysql>=0.2.0" \
    "pyyaml>=6.0" \
    "markdown>=3.5" \
    "cryptography>=42.0" \
    "itsdangerous>=2.1" \
    "aiohttp>=3.9" \
    uvicorn

# 复制应用源码
COPY src/ ./src/
COPY data/ ./data/

# 复制启动脚本
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# 创建运行时数据目录
RUN mkdir -p /app/data/avatars /app/data/plugins /app/data/themes

# 创建非 root 用户
RUN groupadd -r pykych && useradd -r -g pykych pykych && \
    chown -R pykych:pykych /app

USER pykych

# 设置 Python 路径
ENV PYTHONPATH=/app/src

EXPOSE 8000

ENTRYPOINT ["/docker-entrypoint.sh"]
