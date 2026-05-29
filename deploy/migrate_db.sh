#!/bin/bash
# YuQing 数据库迁移脚本
# 用法:
#   导出 (macOS):  bash deploy/migrate_db.sh export
#   导入 (Linux):  bash deploy/migrate_db.sh import yuqing_dump.sql
set -e

DB_NAME="${MYSQL_DATABASE:-yuqing}"
DB_USER="${MYSQL_USER:-root}"
DB_HOST="${MYSQL_HOST:-127.0.0.1}"
DB_PORT="${MYSQL_PORT:-3306}"

MYSQL_CMD="mysql -h $DB_HOST -P $DB_PORT -u $DB_USER"

if [ "$1" = "export" ]; then
    DUMPFILE="${2:-yuqing_dump_$(date +%Y%m%d).sql}"
    echo ">> 导出数据库 $DB_NAME → $DUMPFILE"
    mysqldump -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" -p \
        --single-transaction \
        --routines \
        --triggers \
        --default-character-set=utf8mb4 \
        "$DB_NAME" > "$DUMPFILE"
    echo "   完成: $(wc -c < "$DUMPFILE") bytes"

elif [ "$1" = "import" ]; then
    DUMPFILE="$2"
    if [ ! -f "$DUMPFILE" ]; then
        echo "错误: 文件不存在: $DUMPFILE"
        exit 1
    fi
    echo ">> 创建数据库 $DB_NAME (如已存在先跳过)..."
    $MYSQL_CMD -p -e "CREATE DATABASE IF NOT EXISTS \`$DB_NAME\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

    echo ">> 导入数据到 $DB_NAME..."
    $MYSQL_CMD -p "$DB_NAME" < "$DUMPFILE"
    echo "   完成"

else
    echo "用法:"
    echo "  导出: bash $0 export [dumpfile.sql]"
    echo "  导入: bash $0 import <dumpfile.sql>"
    exit 1
fi
