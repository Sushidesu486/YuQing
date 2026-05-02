# YuQing 语晴

**一个有记忆、有情感、有性格的私人 AI 伙伴。**

语晴不是一个普通的聊天机器人。她能记住你说过的话、感知你的情绪、理解你的处境，并随着时间推移越来越了解你。就像一个永远不会离开、永远耐心倾听的朋友。

---

## 理念

传统 AI 聊天的核心缺陷在于**无状态** — 关掉窗口，一切归零。每次对话都是从陌生人开始。

语晴的灵感来自认知科学对人类记忆的研究，以及 [Project Neuro](https://github.com/litmajor/Project-Neuro) 的情感智能架构。我们相信，一个真正有用的私人 AI 伙伴需要三个能力：

1. **记忆** — 跨会话的持久记忆，像人一样记住过去的经历
2. **情感** — 感知并回应你的情绪状态
3. **人格** — 一致的性格特征，让你觉得在和"一个人"交流

---

## 架构

```
┌─────────────────────────────────────────────────┐
│                  Frontend                       │
│        微信风格单会话聊天界面 (React)            │
└────────────────────┬────────────────────────────┘
                     │ SSE Streaming
┌────────────────────▼────────────────────────────┐
│              CognitiveProcessor                   │
│              (认知处理器 · 总编排)                 │
│                                                   │
│  ┌──────────┐  ┌──────────┐  ┌─────────────────┐  │
│  │Personality│  │  Memory  │  │    Emotion      │  │
│  │  Engine   │  │ Manager  │  │    Regulator    │  │
│  │ 人格引擎  │  │ 记忆管理  │  │    情绪调节器    │  │
│  └──────────┘  └──────────┘  └─────────────────┘  │
│       │              │                  │          │
│  Jinja2 模板    ChromaDB          V-A 模型       │
│  注入人格      语义向量搜索       情感分析       │
│       │              │                  │          │
└───────┼──────────────┼──────────────────┼─────────┘
        │              │                  │
        └──────────────┴──────────────────┘
                       │
              ┌────────▼────────┐
              │  LLM (litellm)  │
              │   统一模型接口    │
              └────────┬────────┘
                       │
          DeepSeek / GLM / Claude / OpenAI / ...
```

### 后端技术栈

| 组件 | 技术 | 说明 |
|------|------|------|
| Web 框架 | **FastAPI** (Python) | 异步，高性能 |
| 数据库 | **MySQL 9** | 结构化数据持久化 |
| 向量检索 | **ChromaDB** | 长期记忆的语义搜索 |
| LLM 接口 | **litellm** | 一套代码切换多家 API |
| 模板引擎 | **Jinja2** | 动态生成 system prompt |

### 前端技术栈

| 组件 | 技术 |
|------|------|
| 框架 | React + TypeScript |
| 样式 | Tailwind CSS |
| 构建 | Vite |
| 国际化 | i18next |

---

## 三大核心能力

### 1. 记忆系统

语晴的记忆不是简单的"保存聊天记录"。她有一个类人脑的多层记忆架构：

**工作记忆（Working Memory）**
- 最近 20 条对话上下文（可配置）
- 当前对话的短期记忆，关闭页面后丢失
- 通过 `.env` 中 `MAX_CONTEXT_MESSAGES` 控制

**长期记忆（Long-term Memory）**
- 每次对话结束后，LLM 自动分析对话内容，提取值得记住的信息
- 存入 MySQL（结构化）+ ChromaDB（向量化）
- 分为 4 个类别：
  - `fact` — 事实信息（"你在上海工作"、"你养了一只猫"）
  - `preference` — 偏好爱好（"你讨厌早起"、"你喜欢深夜写代码"）
  - `event` — 重要事件（"你通过了面试"、"你搬了新家"）
  - `emotion_pattern` — 情感模式（"你压力大时倾向于独处"）
- 每条记忆带有重要性评分（0~1），影响检索优先级

**记忆召回**
- 每次收到新消息时，用 ChromaDB 做语义相似度搜索，召回最相关的 5 条长期记忆
- 召回的记忆注入 system prompt，让 LLM 能"想起来"之前说过的话
- 这意味着即使对话已经很长，语晴仍然能引用你几个月前提到的事情

**效果**：你不需要重复告诉语晴你的喜好，她会记住。

### 2. 情感系统

语晴使用 **V-A 情感模型**（Valence-Arousal）来量化情绪：

- **Valence（积极度）**: -1.0（极度消极）到 +1.0（极度积极）
- **Arousal（激动度）**: 0.0（平静）到 1.0（极度激动）

每条用户消息都会被分析情感状态，映射到 8 种情绪标签：

```
         激动度 ↑
    anxious    excited
         │
消极 ←──────────────→ 积极
         │
     sad        calm / happy
         │
    tired    (低激动)
```

情感数据用于：
- 调整回复风格（检测到用户情绪低落时，自动变得更温柔）
- 记录情绪轨迹，追踪长期心理状态变化
- 未来可扩展为心理健康趋势分析

### 3. 人格系统

语晴的性格通过 YAML 配置文件定义，由 5 个核心维度构成：

| 维度 | 当前值 | 含义 |
|------|--------|------|
| `warmth` | 0.9 | 温暖度 — 对你的亲近和热情程度 |
| `humor` | 0.5 | 幽默感 — 开玩笑的频率 |
| `formality` | 0.2 | 正式度 — 0=像朋友聊天，1=像写邮件 |
| `empathy` | 0.95 | 同理心 — 对你情绪的感知和回应深度 |
| `verbosity` | 0.5 | 话痨度 — 0=惜字如金，1=小作文 |

加上沟通风格（emoji、主动关心、语气）和价值观/约束，共同塑造一个完整的 AI 人格。

人格配置通过 Jinja2 模板注入 system prompt，每次对话时动态生成。你可以在浏览器设置面板中实时拖动滑块调整性格，也可以直接编辑 `backend/personality/default.yaml`。

---

## 快速开始

### 环境要求

- Python 3.9+
- Node.js 18+
- MySQL 8+
- 一个 LLM API Key（支持 DeepSeek、GLM、Claude、OpenAI 等）

### 安装

```bash
# 1. 创建数据库
mysql -u root -p -e "CREATE DATABASE yuqing CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，填入你的 LLM API Key 和 MySQL 密码

# 3. 后端
cd backend
pip install -r requirements.txt
PYTHONPATH=. python3 -m uvicorn app.main:app --reload --port 8000

# 4. 前端（新终端）
cd frontend
npm install
npm run dev
```

打开 `http://localhost:5173` 开始聊天。

### 切换 LLM

编辑 `.env`：

```env
# DeepSeek（便宜，推荐个人使用）
LITELLM_MODEL=openai/deepseek-chat
LITELLM_API_KEY=sk-xxx
LITELLM_API_BASE=https://api.deepseek.com/v1

# GLM（智谱）
LITELLM_MODEL=glm-4
LITELLM_API_KEY=xxx
LITELLM_API_BASE=https://open.bigmodel.cn/api/paas/v4

# Claude
LITELLM_MODEL=anthropic/claude-3-5-sonnet-20241022
LITELLM_API_KEY=sk-ant-xxx
```

模型名需要 `openai/` 或 `anthropic/` 前缀告诉 litellm 使用哪种协议。

---

## 项目结构

```
yuqing/
├── .env                            # 环境配置（API keys、数据库等）
├── backend/
│   ├── requirements.txt
│   └── app/
│       ├── main.py                   # FastAPI 入口
│       ├── config.py                 # 配置管理（pydantic-settings）
│       ├── core/
│       │   ├── cognitive.py          # CognitiveProcessor — 认知处理器（总编排）
│       │   ├── memory.py             # MemoryManager — 记忆管理（MySQL + ChromaDB）
│       │   ├── emotion.py            # MoodRegulator — 情绪调节（V-A 模型）
│       │   ├── personality.py        # PersonalityEngine — 人格引擎（YAML + Jinja2）
│       │   └── llm.py                # litellm 封装（流式/非流式）
│       ├── db/
│       │   ├── database.py           # MySQL 建表 + 连接池
│       │   └── vector.py             # ChromaDB 向量存储
│       ├── prompts/
│       │   ├── system_zh.txt.j2      # 中文 system prompt 模板
│       │   └── system_en.txt.j2      # 英文 system prompt 模板
│       └── api/routes/               # REST API 路由
├── frontend/
│   └── src/
│       ├── components/
│       │   ├── Chat/                 # 微信风格聊天组件
│       │   ├── Layout/               # 页面布局
│       │   ├── Emotion/              # 情绪显示组件
│       │   └── Settings/             # 设置面板
│       ├── hooks/                    # useChat, useConversations
│       └── i18n/                     # 中英文翻译
└── data/chroma_db/                   # ChromaDB 持久化存储
```

---

## 配置参考

### 记忆参数（.env）

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `MAX_CONTEXT_MESSAGES` | 20 | 工作记忆保留的最近消息条数 |
| `MEMORY_RECALL_COUNT` | 5 | 每次对话召回的长期记忆条数 |
| `AUTO_MEMORY_EXTRACTION` | true | 是否自动从对话中提取记忆 |

### 人格参数（personality/default.yaml）

| 参数 | 范围 | 说明 |
|------|------|------|
| `traits.warmth` | 0~1 | 温暖度，越高越热情 |
| `traits.humor` | 0~1 | 幽默感，越高越爱开玩笑 |
| `traits.formality` | 0~1 | 正式度，0=随意 1=正式 |
| `traits.empathy` | 0~1 | 同理心，越高越关注你的感受 |
| `traits.verbosity` | 0~1 | 话痨度，0=简洁 1=详尽 |
| `communication_style.use_emoji` | bool | 是否使用 emoji |
| `communication_style.proactive_care` | bool | 是否主动关心你的状态 |
| `communication_style.response_tone` | string | 语气：gentle/calm/playful/energetic/sage |

---

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/chat/send` | 发送消息，SSE 流式返回 |
| GET | `/api/conversations` | 获取对话列表 |
| GET | `/api/conversations/{id}` | 获取对话详情 + 历史消息 |
| GET | `/api/memories` | 查看所有长期记忆 |
| GET | `/api/memories/search?q=xxx` | 语义搜索记忆 |
| DELETE | `/api/memories/{id}` | 删除某条记忆 |
| GET | `/api/emotions/current` | 当前情绪状态 |
| GET | `/api/emotions/history` | 情绪历史轨迹 |
| GET | `/api/personality` | 获取人格配置 |
| PUT | `/api/personality` | 更新人格配置 |
| POST | `/api/personality/reset` | 重置为默认人格 |
| GET | `/api/health` | 健康检查 |

---

## 与 Project Neuro 的关系

语晴的架构借鉴了 [Project Neuro](https://github.com/litmajor/Project-Neuro) 的核心设计思想，但做了大幅精简和本地化改造：

| 维度 | Project Neuro | YuQing 语晴 |
|------|---------------|-------------|
| **定位** | 研究/教育平台的完整认知架构 | 个人使用的情感 AI 伙伴 |
| **LLM** | 仅 OpenAI GPT-4 | 多模型支持（litellm） |
| **数据库** | SQLite（文件数据库） | MySQL（生产级） |
| **向量检索** | 未内置 | ChromaDB（语义搜索） |
| **用户系统** | 多用户注册登录 | 单用户，无认证 |
| **认知引擎** | 6+ 个处理器（因果推理、假设引擎等） | 3 个核心引擎（记忆、情感、人格） |
| **心理健康** | 完整的心理健康追踪模块 | 情绪感知 + 轨迹记录 |
| **部署** | Replit 云部署 | 本地 Docker/直接运行 |

Project Neuro 证明了"情感智能 AI 伙伴"的技术可行性。语晴将它落地为一个真正能在个人电脑上跑起来、每天陪你聊天的私人伙伴。

---

## 致谢

- [Project Neuro](https://github.com/litmajor/Project-Neuro) — 情感智能架构的灵感来源
- [Mem0](https://mem0.ai) — Agent Memory 领域的前沿实践
- [litellm](https://github.com/BerriAI/litellm) — 统一 LLM 调用接口
- [ChromaDB](https://www.trychroma.com/) — 轻量级向量数据库
