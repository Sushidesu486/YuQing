#!/bin/bash
# YuQing 管理脚本 — 启动 / 停止 / 状态 / TUI 监控
# 用法:
#   bash deploy/start.sh          # 静默后台启动
#   bash deploy/start.sh tui      # 启动 TUI 监控面板
#   bash deploy/start.sh stop     # 停止所有服务
#   bash deploy/start.sh status   # 状态快照
set -e

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="$PROJECT_DIR/logs"
VENV_DIR="$PROJECT_DIR/backend/.venv"
PID_BACKEND="$LOG_DIR/backend.pid"
PID_FRONTEND="$LOG_DIR/frontend.pid"

mkdir -p "$LOG_DIR"

# ── helpers ──
stop_services() {
    echo ">> 停止服务..."
    for pf in "$PID_BACKEND" "$PID_FRONTEND"; do
        if [ -f "$pf" ]; then
            pid=$(cat "$pf")
            if kill -0 "$pid" 2>/dev/null; then
                kill "$pid" 2>/dev/null || true
                sleep 0.5
                kill -9 "$pid" 2>/dev/null || true
                echo "   stopped PID $pid ($(basename "$pf"))"
            fi
            rm -f "$pf"
        fi
    done
    # Also kill any leftover uvicorn/vite on our ports
    for port in 8000 5173; do
        pids=$(lsof -ti :"$port" 2>/dev/null || true)
        [ -n "$pids" ] && kill $pids 2>/dev/null || true
    done
    echo "YuQing 已停止"
}

status_snapshot() {
    echo "=== YuQing 状态 ==="
    echo ""
    for name in backend frontend; do
        pf="$LOG_DIR/$name.pid"
        if [ -f "$pf" ]; then
            pid=$(cat "$pf")
            if kill -0 "$pid" 2>/dev/null; then
                echo "  $name: 运行中 (PID $pid)"
            else
                echo "  $name: 已停止 (PID 文件残留)"
            fi
        else
            echo "  $name: 未启动"
        fi
    done
    echo ""
    # GPU
    if command -v nvidia-smi &>/dev/null; then
        echo "=== GPU ==="
        nvidia-smi --query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu \
            --format=csv,noheader 2>/dev/null | \
            awk -F', ' '{printf "  %s | 利用 %s | 显存 %s/%s | %s°C\n", $1,$2,$3,$4,$5}'
        echo ""
    fi
    # Memory
    echo "=== 进程内存 ==="
    for name in backend frontend; do
        pf="$LOG_DIR/$name.pid"
        if [ -f "$pf" ]; then
            pid=$(cat "$pf")
            if kill -0 "$pid" 2>/dev/null; then
                rss=$(ps -o rss= -p "$pid" 2>/dev/null | awk '{printf "%.0f MB", $1/1024}')
                echo "  $name: $rss"
            fi
        fi
    done
    echo ""
    echo "=== 最近日志 ==="
    for log in backend.log frontend.log; do
        lf="$LOG_DIR/$log"
        if [ -f "$lf" ]; then
            echo "--- $log ---"
            tail -5 "$lf"
            echo ""
        fi
    done
}

start_services() {
    echo ">> 检查环境..."
    if ! command -v python3 &>/dev/null; then echo "错误: Python3 未安装"; exit 1; fi
    if ! command -v node &>/dev/null; then echo "错误: Node.js 未安装"; exit 1; fi
    if ! mysqladmin ping -h "${MYSQL_HOST:-127.0.0.1}" -u "${MYSQL_USER:-root}" --silent 2>/dev/null; then
        echo "警告: MySQL 未运行"
    fi

    [ ! -d "$VENV_DIR" ] && python3 -m venv "$VENV_DIR"

    echo ">> 安装 Python 依赖..."
    cd "$PROJECT_DIR/backend"
    "$VENV_DIR/bin/pip" install -r requirements.txt -q 2>/dev/null || true

    echo ">> 安装前端依赖..."
    cd "$PROJECT_DIR/frontend"
    npm install --silent 2>/dev/null || true

    echo ">> 启动后端..."
    cd "$PROJECT_DIR/backend"
    HF_HUB_OFFLINE=1 PYTHONPATH=. nohup "$VENV_DIR/bin/python3" -m uvicorn app.main:app \
        --host 0.0.0.0 --port 8000 \
        >> "$LOG_DIR/backend.log" 2>&1 &
    echo "$!" > "$PID_BACKEND"
    echo "   后端 PID $(cat "$PID_BACKEND")"

    echo ">> 启动前端..."
    cd "$PROJECT_DIR/frontend"
    nohup npx vite --host 0.0.0.0 --port 5173 \
        >> "$LOG_DIR/frontend.log" 2>&1 &
    echo "$!" > "$PID_FRONTEND"
    echo "   前端 PID $(cat "$PID_FRONTEND")"

    LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
    echo ""
    echo "============================================"
    echo "  YuQing 已启动"
    echo "  后端: http://${LOCAL_IP:-localhost}:8000"
    echo "  前端: http://${LOCAL_IP:-localhost}:5173"
    echo "  SSH 隧道: ssh -fNL 5173:localhost:5173 g18"
    echo "  日志:    $LOG_DIR/"
    echo "  TUI:     bash $PROJECT_DIR/deploy/start.sh tui"
    echo "============================================"
}

start_tui() {
    # Install rich if missing
    "$VENV_DIR/bin/pip" install rich -q 2>/dev/null || pip install rich -q 2>/dev/null || {
        echo "rich install failed, falling back to log tail"
        tail -f "$LOG_DIR/backend.log" "$LOG_DIR/frontend.log"
        return
    }
    PYTHONPATH="$PROJECT_DIR/backend" exec python3 "$PROJECT_DIR/deploy/tui.py"
}

# ── main ──
case "${1:-start}" in
    start|up|run)
        start_services
        ;;
    tui|monitor|watch)
        start_tui
        ;;
    stop|down|kill)
        stop_services
        ;;
    status|stat|ps)
        status_snapshot
        ;;
    restart)
        stop_services
        sleep 2
        start_services
        ;;
    *)
        echo "用法: bash deploy/start.sh [start|tui|stop|status|restart]"
        exit 1
        ;;
esac
