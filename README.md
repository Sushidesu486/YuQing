# YuQing 雨晴

一个有记忆、有情感、有性格、能主动联系你的私密 AI 伙伴。

**不只是聊天机器人** — 她能记住你们聊过的一切、感知你的情绪波动、拥有自己微妙的心情变化、在夜深人静时翻开日记写下独白、甚至在你消失太久时主动发来一条假装不经意的消息。

---

## 她能做到的事

| 能力 | 说明 |
|------|------|
| **持续记忆** | 跨会话持久记忆，BGE 语义搜索 + 今日全量注入 + 关联网络扩散 |
| **情感感知** | 分析你的情绪（V-A 模型），调整回应方式 |
| **固定人格** | 回避型依恋 + 傲娇毒舌，YAML 配置 + Jinja2 模板驱动 |
| **自有心情** | 温暖度 / 敞开度 / 能量三维追踪，受对话和内心独白双向驱动 |
| **主动关心** | 4 种触发器（情绪跟进 / 缺席 / 记忆 / 时段），后台自动生成 |
| **工具调用** | 4 个内置工具（回忆记忆 / 搜索网络 / RSS 文章 / 本地知识） |
| **内心独白** | 每轮对话后写日记，自我反思并存入记忆系统 |
| **今日感知** | 看到今天的完整对话轨迹，不会在同一天反复聊同一件事 |
| **暗色模式** | 一键切换暗色主题，字号和图标大小可调 |

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
