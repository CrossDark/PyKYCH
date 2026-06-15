#!/bin/bash
# ── PyKYCH Docker 启动脚本 ──────────────────────────────────
# 从环境变量生成 settings/db.yaml，等待 MySQL 就绪，然后启动 uvicorn

set -e

DB_YAML="/app/settings/db.yaml"
DB_HOST="${DB_HOST:-mysql}"
DB_PORT="${DB_PORT:-3306}"
DB_USER="${DB_USER:-pykych}"
DB_PASSWORD="${DB_PASSWORD:-pykych}"
DB_NAME="${DB_NAME:-pykych}"

# 如果 db.yaml 不存在（未挂载），则从环境变量生成
if [ ! -f "$DB_YAML" ]; then
    echo "📝 从环境变量生成数据库配置..."
    cat > "$DB_YAML" << EOF
# ── PyKYCH 数据库配置（Docker 自动生成）──────────────────
mysql:
  host: ${DB_HOST}
  port: ${DB_PORT}
  user: ${DB_USER}
  password: ${DB_PASSWORD}
  database: ${DB_NAME}
  charset: utf8mb4
  pool:
    minsize: ${DB_POOL_MIN:-2}
    maxsize: ${DB_POOL_MAX:-10}
    pool_recycle: 3600
EOF
    echo "✅ 数据库配置已生成"
else
    echo "📄 使用挂载的数据库配置: $DB_YAML"
fi

# 等待 MySQL 就绪（通过 TCP 端口检测）
echo "⏳ 等待 MySQL 就绪 (${DB_HOST}:${DB_PORT})..."

for i in $(seq 1 30); do
    if python3 -c "
import socket, sys
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(2)
try:
    s.connect(('${DB_HOST}', ${DB_PORT}))
    s.close()
    sys.exit(0)
except Exception:
    sys.exit(1)
" 2>/dev/null; then
        echo "✅ MySQL 已就绪"
        break
    fi
    echo "   等待中... ($i/30)"
    sleep 2
done

echo "🚀 启动 PyKYCH 服务..."
exec uvicorn src.pykych.main:app --host 0.0.0.0 --port 8000
