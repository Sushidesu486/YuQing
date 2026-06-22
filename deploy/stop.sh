#!/bin/bash
# YuQing 停止脚本
set -e

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="$PROJECT_DIR/logs"

for pidfile in backend.pid frontend.pid; do
    if [ -f "$LOG_DIR/$pidfile" ]; then
        PID=$(cat "$LOG_DIR/$pidfile")
        if kill -0 "$PID" 2>/dev/null; then
            echo "停止 $pidfile (PID $PID)..."
            kill "$PID"
            sleep 1
            if kill -0 "$PID" 2>/dev/null; then
                kill -9 "$PID"
            fi
        fi
        rm -f "$LOG_DIR/$pidfile"
    fi
done

echo "YuQing 已停止"
