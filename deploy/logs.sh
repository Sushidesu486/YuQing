#!/bin/bash
# YuQing 实时日志监控 — ANSI 颜色直接终端渲染
# 用法:
#   bash deploy/logs.sh            # 同时看后端+前端
#   bash deploy/logs.sh backend    # 只看后端
#   bash deploy/logs.sh frontend   # 只看前端

LOG_DIR="$(cd "$(dirname "$0")/.." && pwd)/logs"

BACKEND="$LOG_DIR/backend.log"
FRONTEND="$LOG_DIR/frontend.log"

trap 'echo ""; echo "日志监控已退出"; exit 0' INT

show_all() {
    echo "╔══════════════════════════════════════════╗"
    echo "║           YuQing 实时日志监控            ║"
    echo "╠══════════════════════════════════════════╣"
    echo "║  后端: $BACKEND   ║"
    echo "║  前端: $FRONTEND   ║"
    echo "║  Ctrl+C 退出                             ║"
    echo "╚══════════════════════════════════════════╝"
    echo ""

    if [ -f "$BACKEND" ] && [ -f "$FRONTEND" ]; then
        tail -f "$BACKEND" "$FRONTEND"
    elif [ -f "$BACKEND" ]; then
        tail -f "$BACKEND"
    elif [ -f "$FRONTEND" ]; then
        tail -f "$FRONTEND"
    else
        echo "暂无日志文件"
    fi
}

case "${1:-all}" in
    backend|be)
        [ -f "$BACKEND" ] && tail -f "$BACKEND" || echo "后端日志不存在: $BACKEND"
        ;;
    frontend|fe)
        [ -f "$FRONTEND" ] && tail -f "$FRONTEND" || echo "前端日志不存在: $FRONTEND"
        ;;
    all|*)
        show_all
        ;;
esac
