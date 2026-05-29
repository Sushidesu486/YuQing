#!/bin/bash
# YuQing 状态查看

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="$PROJECT_DIR/logs"

echo "=== YuQing 状态 ==="
echo ""

for name in backend frontend; do
    PIDFILE="$LOG_DIR/$name.pid"
    if [ -f "$PIDFILE" ]; then
        PID=$(cat "$PIDFILE")
        if kill -0 "$PID" 2>/dev/null; then
            echo "  $name: 运行中 (PID $PID)"
        else
            echo "  $name: 已停止 (PID 文件残留)"
        fi
    else
        echo "  $name: 未启动"
    fi
done
echo ""

# GPU info
if command -v nvidia-smi &>/dev/null; then
    echo "=== GPU 状态 ==="
    nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu --format=csv,noheader 2>/dev/null | \
        awk -F', ' '{printf "  GPU: %s%% | 显存: %s / %s | 温度: %s°C\n", $1, $2, $3, $4}'
    echo ""
fi

# Memory info
echo "=== 进程内存 ==="
for pidfile in backend.pid frontend.pid; do
    if [ -f "$LOG_DIR/$pidfile" ]; then
        PID=$(cat "$LOG_DIR/$pidfile")
        name=$(basename "$pidfile" .pid)
        if kill -0 "$PID" 2>/dev/null; then
            RSS=$(ps -o rss= -p "$PID" 2>/dev/null | awk '{printf "%.0f MB", $1/1024}')
            echo "  $name: $RSS"
        fi
    fi
done
echo ""

echo "=== 最近日志 ==="
for logfile in backend.log frontend.log; do
    if [ -f "$LOG_DIR/$logfile" ]; then
        echo "--- $logfile (最后 5 行) ---"
        tail -5 "$LOG_DIR/$logfile"
        echo ""
    fi
done
