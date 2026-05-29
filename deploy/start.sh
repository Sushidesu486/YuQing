#!/bin/bash
# YuQing 一键启动脚本 (Linux + NVIDIA GPU)
set -e

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"

# ── 1. 检查依赖 ──
echo ">> 检查环境..."

if ! command -v python3 &>/dev/null; then
    echo "错误: 需要 Python 3.9+"
    exit 1
fi

if ! command -v node &>/dev/null; then
    echo "错误: 需要 Node.js 18+"
    exit 1
fi

if ! python3 -c "import torch; assert torch.cuda.is_available(), 'CUDA not available'" 2>/dev/null; then
    echo "警告: PyTorch CUDA 不可用，嵌入将使用 CPU（很慢）"
    echo "      运行: pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124"
fi

if ! mysqladmin ping -h "${MYSQL_HOST:-127.0.0.1}" -u "${MYSQL_USER:-root}" --silent 2>/dev/null; then
    echo "警告: MySQL 未运行，请先启动 MySQL"
fi

# ── 2. 安装依赖 ──
echo ">> 安装 Python 依赖..."
cd "$PROJECT_DIR/backend"
pip install -r requirements.txt -q

echo ">> 安装前端依赖..."
cd "$PROJECT_DIR/frontend"
npm install --silent 2>/dev/null

# ── 3. 构建前端 ──
echo ">> 构建前端..."
npm run build

# ── 4. 启动后端 ──
echo ">> 启动后端 (后台运行)..."
cd "$PROJECT_DIR/backend"
PYTHONPATH=. nohup python3 -m uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    >> "$LOG_DIR/backend.log" 2>&1 &
BACKEND_PID=$!
echo "   后端 PID: $BACKEND_PID  日志: $LOG_DIR/backend.log"

# ── 5. 启动前端 (生产模式) ──
echo ">> 启动前端 (后台运行)..."
cd "$PROJECT_DIR/frontend"
nohup npx vite preview --host 0.0.0.0 --port 5678 \
    >> "$LOG_DIR/frontend.log" 2>&1 &
FRONTEND_PID=$!
echo "   前端 PID: $FRONTEND_PID  日志: $LOG_DIR/frontend.log"

# ── 6. 保存 PID ──
echo "$BACKEND_PID" > "$LOG_DIR/backend.pid"
echo "$FRONTEND_PID" > "$LOG_DIR/frontend.pid"

echo ""
echo "============================================"
echo "  YuQing 已启动"
echo "  后端: http://$(hostname -I 2>/dev/null | awk '{print $1}' || echo 'localhost'):8000"
echo "  前端: http://$(hostname -I 2>/dev/null | awk '{print $1}' || echo 'localhost'):5678"
echo "  日志: $LOG_DIR/"
echo ""
echo "  停止: bash $PROJECT_DIR/deploy/stop.sh"
echo "  状态: bash $PROJECT_DIR/deploy/status.sh"
echo "============================================"
