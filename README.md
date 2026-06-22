# YuQing 雨晴

一个面向长期对话、个性化交互与记忆增强生成的 RAG Chat AI 实验项目。

项目核心问题是：在 LLM 固定 context window 之外，如何利用 embedding 模型、长期记忆库、关联网络和时间感知机制，构建一个能够跨会话召回、更新和压缩个人上下文的 Chat AI 系统。YuQing 保留拟人化人格、情绪和主动交互作为长期对话评测场景，项目定位则聚焦于 **embedding-based RAG memory architecture** 的工程化探索。

---

## 探索方向与系统能力

| 能力 | 说明 |
|------|------|
| **长程记忆 RAG** | BGE embedding 语义召回 + 今日全量注入 + 记忆关联网络扩散，用外部记忆突破单次 context 限制 |
| **混合召回评分** | 结合 semantic similarity、activation spread、importance、access frequency，减少只靠向量相似度的误召回 |
| **记忆生命周期** | LLM 抽取、语义去重、纠错、衰减、聚类合并、睡眠清理，模拟长期记忆的压缩与巩固 |
| **时间感知上下文** | 引入会话间隔、时段、关系阶段和今日对话轨迹，让召回结果具备时间位置 |
| **情绪与人格条件化** | V-A 情绪模型、三维心情状态、YAML 人格与 Jinja2 prompt 模板共同影响生成策略 |
| **主动与工具增强** | 主动消息触发器 + 内置工具（回忆记忆 / 搜索网络 / RSS 文章 / 本地知识）扩展信息来源 |
| **可观测调试** | 记忆面板、召回链路调试、ForceGraph 关联图，用于观察 RAG 召回质量和记忆结构 |

---

## 研究问题

- **Context 边界外的个人上下文**：将对话历史转化为可检索、可压缩、可演化的长期记忆，而不是简单堆叠 prompt。
- **从向量召回到认知式召回**：在 embedding 相似度之外加入关联扩散、重要性、访问频率和时间因素，提升跨主题记忆的可达性。
- **记忆写入与记忆清理的闭环**：在每轮对话后抽取新记忆，并通过合并、衰减和睡眠清理控制记忆库规模。
- **人格化交互作为评测场景**：用持续人格、情绪和主动交互测试 RAG 记忆是否真的改善长期一致性。

---

## 技术栈

| 层 | 技术 |
|----|------|
| 后端 | FastAPI (Python) + aiomysql + aiohttp |
| 前端 | React 19 + TypeScript + Vite + Tailwind CSS v4 |
| 数据库 | MySQL (12 表，自动建表) |
| 嵌入模型 | BAAI/bge-base-zh-v1.5（本地加载，768 维） |
| LLM 接口 | OpenAI 兼容 API（支持 mimo / deepseek-chat / GPT-4o 等） |
| 模板 | Jinja2（System prompt 拆分 stable/dynamic 双模板） |

---

## 架构概要

```
用户消息
  → emotion.py    情绪分析 (V-A)
  → mood.py       雨晴心情更新
  → temporal.py   时间感知 (间隔/时段/任期)
  → memory.py     BGE 语义召回 + 今日全量注入
  → personality.py 人格 prompt 构建 (stable + dynamic)
  → llm.py        流式 LLM 生成
  → memory.py     LLM 记忆提取 + 独白写入
```

### 关键模块 (`backend/app/core/`)

| 文件 | 职责 |
|------|------|
| `cognitive.py` | 10 阶段认知处理流水线 |
| `memory.py` | 记忆系统（召回/提取/衰减/巩固/清理/独白） |
| `personality.py` | 人格引擎（YAML + Jinja2 prompt 渲染） |
| `mood.py` | 雨晴三维心情追踪 |
| `emotion.py` | 用户情绪分析 |
| `temporal.py` | 时间感知上下文 |
| `proactive.py` | 主动消息系统 |
| `openai_client.py` | OpenAI API 直连客户端（aiohttp） |
| `tools/` | 4 个内置工具（recall/search/RSS/knowledge） |

---

## 快速开始

### 环境要求

- Python 3.9+ / Node.js 18+ / MySQL 8+

### 安装

```bash
# 1. 创建数据库
mysql -u root -p -e "CREATE DATABASE yuqing CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 LLM API Key 和 MySQL 密码

# 3. 安装后端依赖
cd backend
pip install -r requirements.txt

# 4. 启动后端
PYTHONPATH=. python3 -m uvicorn app.main:app --reload --port 8000

# 5. 安装前端依赖并启动（新终端）
cd frontend
npm install
npm run dev
```

前端 `http://localhost:5173`，自动代理 `/api` 到后端 `:8000`。

### .env 最小配置

```env
# LLM API（OpenAI 兼容格式，支持 mimo / deepseek-chat / GPT-4o 等）
LITELLM_MODEL=openai/deepseek-chat
LITELLM_API_KEY=sk-your-key
LITELLM_API_BASE=https://api.deepseek.com/v1

# MySQL
MYSQL_HOST=127.0.0.1
MYSQL_USER=root
MYSQL_PASSWORD=your-password
MYSQL_DATABASE=yuqing
```

---

## API 接口

### 对话
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/chat/send` | 发送消息，SSE 流式返回 |
| GET | `/api/conversations` | 对话列表 |
| GET | `/api/conversations/{id}` | 对话详情 + 历史消息 |

### 记忆
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/memories` | 所有长期记忆 |
| GET | `/api/memories/search?q=xxx` | 语义搜索记忆 |
| DELETE | `/api/memories/{id}` | 删除记忆 |
| POST | `/api/memories/debug/recall` | 调试：完整召回链路 |
| POST | `/api/memories/debug/cleanup` | 手动触发睡眠清理 |
| POST | `/api/memories/trigger-info-retrieval` | 手动触发 RSS/Tavily 抓取 |
| POST | `/api/memory/unload-model` | 释放 BGE 模型内存（自动重载） |

### 情绪与心情
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/emotions/current` | 用户当前情绪 |
| GET | `/api/mood/current` | 雨晴当前心情 |
| GET | `/api/mood/history` | 心情变化历史 |

### 其它
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/proactive/listen` | SSE 主动消息监听 |
| GET | `/api/posts` | 雨晴说说列表 |
| POST | `/api/posts/generate` | 手动生成说说 |
| GET | `/api/personality` | 获取/更新人格配置 |
| GET | `/api/rss/articles?limit=5` | 查看 RSS 源文章 |
| GET | `/api/health` | 健康检查 |

---

## 分支说明

| 分支 | 定位 | 平台 | 特点 |
|------|------|------|------|
| `main` | 稳定版 | macOS | bge-base-zh, CPU 推理, 含说说+日记+睡眠优化 |
| `feature/deploy-linux` | Linux 主开发 | Linux + GPU | bge-m3 (多语言), CUDA 加速, TUI 监控, 部署脚本 |

```bash
# macOS 轻量部署
git clone https://github.com/Sushidesu486/My_YuQing.git
cd YuQing && git checkout main

# Linux GPU 部署
git clone https://github.com/Sushidesu486/My_YuQing.git
cd YuQing && git checkout feature/deploy-linux
bash deploy/start.sh
```

### 功能对比

| 功能 | main | deploy-linux |
|------|:--:|:--:|
| 说说 (poster) | ✅ | ✅ |
| 日记系统 | ✅ | ✅ |
| 消息分页 | ✅ | ✅ |
| 睡眠参数优化 | ✅ | ✅ |
| 记忆淘汰硬上限 | ✅ | ✅ |
| 深色模式 | ✅ | ✅ |
| 页面刷新自动滚底 | ✅ | ✅ |
| ForceGraph 自适应 | ✅ | ✅ |
| BGE 嵌入模型 | base-zh-v1.5 | m3 (中英混合) |
| GPU CUDA 加速 | — | ✅ RTX 4060 |
| GPU/CPU 内存管理 | ✅ cpu | ✅ cpu + cuda |
| TUI 实时监控 | — | ✅ rich.live |
| deploy/ 运维脚本 | — | ✅ |
| 前端开发模式 | `npm run dev` | `bash deploy/start.sh` |
| 前端生产模式 | — | `npx vite preview` |

---

## 项目结构

```
YuQing/
├── backend/
│   ├── app/
│   │   ├── main.py           # FastAPI 入口 + lifespan
│   │   ├── config.py         # 配置管理 (pydantic-settings)
│   │   ├── core/             # 认知引擎
│   │   ├── db/database.py    # MySQL 建表 + 连接池
│   │   ├── api/routes/       # REST API 路由
│   │   └── prompts/          # Jinja2 模板 (stable/dynamic)
│   ├── personality/          # YAML 人格配置
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── components/       # Chat / Memory / Layout / Settings
│       ├── hooks/            # useChat / useConversations / useProactive
│       └── services/         # API 客户端
├── docs/                     # 技术文档
└── .env.example
```

---

## 许可证

私有项目。仅限个人使用。
