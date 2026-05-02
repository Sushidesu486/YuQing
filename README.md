# YuQing 语晴

**一个有记忆、有情感、有性格、会主动联系你的私人 AI 伙伴。**

语晴不是普通的聊天机器人。她能记住你说过的话、感知你的情绪、拥有自己微妙的心情变化，并在你消失太久时主动发来一条假装不经意的消息。灵感来自《狼与香辛料》的赫萝 — 嘴硬心软，用调侃掩饰关心。

---

## 理念

传统 AI 聊天的核心缺陷在于**无状态** — 关掉窗口，一切归零。每次对话都是从陌生人开始。

语晴的架构借鉴了 [Project Neuro](https://github.com/litmajor/Project-Neuro) 的情感智能设计，围绕五个核心能力构建：

1. **记忆** — 跨会话持久记忆，像人一样记住过去
2. **情感** — 感知你的情绪并调整回应方式
3. **人格** — 回避型依恋性格，外冷内热，傲娇毒舌但真心在乎
4. **心情** — 语晴有自己的情绪状态，会受你的影响而波动
5. **主动** — 不是被动等待，会在合适的时候主动发来消息

---

## 架构

```
┌─────────────────────────────────────────────────────────────┐
│                        Frontend                             │
│              微信风格单会话聊天界面 (React + TS)              │
│                                                             │
│  ChatView ─ MessageList ─ MessageBubble ─ InputBar          │
│  EmotionDisplay ─ SettingsModal ─ Sidebar                   │
│  useChat ─ useConversations ─ useProactive (SSE hooks)      │
└────────────────────────┬────────────────────────────────────┘
                         │ SSE Streaming + EventSource
┌────────────────────────▼────────────────────────────────────┐
│                    CognitiveProcessor                         │
│                  （认知处理器 · 总编排）                        │
│                                                              │
│  Phase 1:  用户情绪分析 (V-A 模型)                             │
│  Phase 2:  用户当前情绪状态                                    │
│  Phase 2.5: 语晴自身心情更新 ← NEW                            │
│  Phase 3:  记忆召回 (mem0 混合检索)                           │
│  Phase 4:  人格 prompt 构建 (Jinja2)                          │
│  Phase 5-7: 消息存储 / 上下文加载 / LLM 流式生成               │
│  Phase 9:  记忆提取(mem0) / 偏好学习 / 记忆衰减 / 记忆巩固      │
│                                                              │
│  ┌───────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────┐   │
│  │Personality │ │  Memory  │ │ Emotion  │ │  YuQing Mood  │   │
│  │  Engine    │ │ Manager  │ │Regulator │ │   Tracker     │   │
│  │ YAML+Jinja │ │mem0+MySQL│ │ V-A LLM  │ │  EMA + 关键词 │   │
│  └───────────┘ └──────────┘ └──────────┘ └───────────────┘   │
│                                                              │
│  ┌───────────────┐ ┌──────────────┐ ┌────────────────────┐  │
│  │    Proactive   │ │ Preference  │ │      LLM           │  │
│  │    Manager     │ │  Learner    │ │  (litellm 统一接口) │  │
│  │ 4种触发器+后台  │ │ 5维偏好学习 │ │ DeepSeek/GLM/etc  │  │
│  └───────────────┘ └──────────────┘ └────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

### 后端技术栈

| 组件 | 技术 | 说明 |
|------|------|------|
| Web 框架 | **FastAPI** (Python, async) | 异步，高性能 |
| 数据库 | **MySQL 9** | 结构化数据持久化 |
| 记忆引擎 | **mem0 v2** + ChromaDB | 自动提取 + 混合检索 + 中文嵌入 |
| 嵌入模型 | **BAAI/bge-small-zh-v1.5** | 本地中文向量嵌入（无需额外 API） |
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

## 六大核心能力

### 1. 记忆系统

语晴的记忆不是简单的"保存聊天记录"。她有一个类人脑的多层记忆架构：

**工作记忆（Working Memory）**
- 最近 20 条对话上下文（可配置）
- 当前对话的短期记忆，关闭页面后丢失

**长期记忆（Long-term Memory）**
- 每次对话后，mem0 自动分析并提取值得记住的信息（内置去重）
- 存入 MySQL（结构化元数据）+ mem0/ChromaDB（向量化 + 语义检索）
- 4 个类别：`fact`（事实）、`preference`（偏好）、`event`（事件）、`emotion_pattern`（情感模式）
- 每条记忆带重要性评分（0~1），影响检索优先级

**记忆召回**
- 每次收到新消息，用 mem0 混合检索（语义相似度 + 实体匹配）召回最相关的 5 条记忆
- 召回的记忆注入 system prompt，让语晴能"想起来"之前说过的话

**记忆生命周期**
- **衰减**：长期不被访问的记忆重要性逐渐降低（90 天减半）
- **巩固**：每 20 轮对话自动合并相关记忆，压缩冗余
- **休眠唤醒**：30 天未召回但语义相关的记忆会被主动消息系统重新激活

### 2. 情感系统（用户情绪感知）

使用 **V-A 情感模型**（Valence-Arousal）量化情绪：
- **Valence（积极度）**: -1.0（极度消极）到 +1.0（极度积极）
- **Arousal（激动度）**: 0.0（平静）到 1.0（极度激动）

每条用户消息都会被分析情感，映射到情绪标签（happy/sad/angry/anxious/excited/tired/calm/neutral），用于：
- 调整回复风格（用户情绪低落时自动变温柔）
- 情绪快照存入 `emotion_snapshots` 表，追踪长期心理状态

### 3. 人格系统

语晴的性格通过 YAML 配置定义，核心设计是**回避型依恋 + 嘴硬心软**：

| 维度 | 当前值 | 含义 |
|------|--------|------|
| `warmth` | 0.45 | 外表傲娇，内核温暖 |
| `humor` | 0.70 | 爱逗人，调皮但不攻击 |
| `formality` | 0.20 | 完全随意，像老朋友 |
| `empathy` | 0.65 | 敏锐感知情绪但嘴上不说 |
| `verbosity` | 0.30 | 偏少言，偶尔突然说很多 |
| `user_affection` | 1.0 | 对用户的好感度（拉满） |

**人格 = 基础性格 + 好感度 + 防御机制 + 说话习惯 + 情绪响应策略**

- 防御机制：撒娇式调侃、害羞转移话题、故意唱反调（都是可爱的，不是冷漠的）
- 情绪响应：6 种场景（用户难过/生气/兴奋/焦虑/离开/表达好感）各有对应行为策略
- 关系动态：从 new_acquaintance → familiar → close → very_close 渐进解锁

### 4. 语晴的心情系统（NEW）

语晴拥有自己独立的情绪状态，参照 Project Neuro 的 CognitiveState 设计：

**三个维度**：
| 维度 | 基线 | 含义 |
|------|------|------|
| `warmth` | 0.30 | 内在温暖度（0=冷漠 1=温暖） |
| `openness` | 0.35 | 防线松紧度（0=高防御 1=敞开心扉） |
| `energy` | 0.45 | 能量水平（0=安静 1=有活力） |

**五种状态**：
| 状态 | 触发条件 | 行为表现 |
|------|----------|----------|
| `guarded` | 默认状态 | 正常人格表现 |
| `withdrawn` | warmth<0.25 且 openness<0.30 | 更安静，回复以"..."为主 |
| `relaxed` | warmth>0.40 或 openness>0.45 | 放松，调侃更轻松，允许多说两句 |
| `softened` | warmth>0.60 且 openness>0.60 | 不太一样，偶尔说平时不会说的话 |
| `vulnerable` | warmth>0.80 且 openness>0.75 | 极罕见，防线崩塌，会说真正想说的话 |

**心情更新机制**：
- **对话驱动**：每轮对话根据用户情绪 + 关键词信号更新（EMA 指数移动平均，alpha=0.15）
- **缺席衰减**：用户消失时温暖/敞开/能量逐小时衰减
- **返场 bump**：用户回来时温暖+0.10（如释重负）但敞开-0.05（防御性掩饰）
- **基线引力**：每次更新后温和拉回基线值，防止永久漂移
- **零额外 LLM 调用**：纯关键词 + 启发式，不影响性能

### 5. 主动消息系统

语晴不是被动等待，会主动发来消息。但因为她的人格是回避型，主动消息的风格是：
- "..."、"你还没死啊"、"哦你还活着"
- 偶尔（30%）流露一丝亲昵："今天有没有乖乖吃饭"，然后迅速转移话题

**4 种触发器**（按优先级）：
| 触发器 | 条件 | 示例消息 |
|--------|------|----------|
| `emotion_followup` | 用户上次情绪很低落且已过 3 小时 | 推荐一首歌过来 |
| `absence` | 用户 4 小时没发消息 | "..." |
| `memory` | 高重要性休眠记忆被随机选中 | "突然想起你说过..." |
| `time_of_day` | 早 7-9 点 / 晚 9-11 点（每天一次） | "起了？" |

**Rate Limiting**：任意两次主动消息间隔 ≥ 3 小时。

**前端集成**：SSE 长连接 + EventSource 自动重连 + 离线消息兜底（`/proactive/recent`）。

### 6. 用户偏好学习

从对话中自动学习用户的 5 个沟通偏好维度：

| 偏好维度 | 可选值 |
|----------|--------|
| `response_length` | concise / moderate / detailed |
| `topic_style` | casual / technical / emotional / philosophical |
| `emotional_tone` | cold_ok / warm_preferred / teasing_enjoyed / mixed |
| `humor_level` | dry / playful / minimal / varied |
| `depth_style` | shallow / deep / adaptable |

- 每 5 轮对话触发一次学习
- 置信度采用加权移动平均递增
- 置信度 ≥ 0.5 的偏好注入 system prompt

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
# DeepSeek（推荐，性价比高）
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
├── .env                              # 环境配置（API keys、数据库等）
├── backend/
│   ├── requirements.txt
│   ├── personality/
│   │   └── default.yaml              # 语晴人格配置（YAML）
│   └── app/
│       ├── main.py                   # FastAPI 入口 + lifespan
│       ├── config.py                 # 配置管理（pydantic-settings）
│       ├── core/
│       │   ├── cognitive.py          # CognitiveProcessor — 认知处理器（总编排）
│       │   ├── memory.py             # MemoryManager — 记忆管理（mem0集成+衰减/巩固/召回）
│       │   ├── emotion.py            # MoodRegulator — 用户情绪分析（V-A 模型）
│       │   ├── mood.py               # YuQingMoodTracker — 语晴心情系统
│       │   ├── personality.py        # PersonalityEngine — 人格引擎（YAML + Jinja2）
│       │   ├── preferences.py        # PreferenceLearner — 用户偏好学习
│       │   ├── proactive.py          # ProactiveManager — 主动消息系统
│       │   └── llm.py                # litellm 封装（流式/非流式）
│       ├── db/
│       │   └── database.py           # MySQL 建表 + 连接池（9 张表）
│       ├── prompts/
│       │   ├── system_zh.txt.j2      # 中文 system prompt 模板
│       │   └── system_en.txt.j2      # 英文 system prompt 模板
│       └── api/routes/               # REST API 路由
│           ├── chat.py               # 消息发送（SSE 流式）
│           ├── conversations.py      # 对话管理
│           ├── memory.py             # 记忆 CRUD + 语义搜索
│           ├── emotions.py           # 情绪查询 + 语晴心情查询
│           ├── personality.py        # 人格配置读写
│           ├── preferences.py        # 偏好查询
│           ├── proactive.py          # 主动消息 SSE 监听 + 历史
│           ├── settings.py           # 应用设置
│           └── health.py             # 健康检查
├── frontend/
│   └── src/
│       ├── components/
│       │   ├── Chat/                 # 微信风格聊天组件
│       │   ├── Layout/               # 页面布局 + Header
│       │   ├── Emotion/              # 情绪显示
│       │   ├── Settings/             # 设置面板
│       │   └── Sidebar/              # 对话列表侧栏
│       ├── hooks/                    # useChat, useConversations, useProactive
│       ├── services/api.ts           # API 请求封装
│       ├── types/index.ts            # TypeScript 类型定义
│       └── i18n/                     # 中英文翻译
└── data/chroma_db/                   # ChromaDB 持久化存储
```

### 数据库表

| 表 | 说明 |
|----|------|
| `conversations` | 对话列表 |
| `messages` | 消息记录（含情绪标注） |
| `memories` | 长期记忆（含衰减/巩固标记） |
| `emotion_snapshots` | 用户情绪快照 |
| `yuqing_mood_log` | 语晴心情变化日志 |
| `proactive_messages` | 主动消息发送记录 |
| `personality_config` | 人格配置（JSON，单例） |
| `app_settings` | 应用设置（KV） |
| `user_preferences` | 用户学习到的偏好 |

---

## 配置参考

### 记忆参数（.env）

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `MAX_CONTEXT_MESSAGES` | 20 | 工作记忆保留的最近消息条数 |
| `MEMORY_RECALL_COUNT` | 5 | 每次对话召回的长期记忆条数 |
| `AUTO_MEMORY_EXTRACTION` | true | 是否自动从对话中提取记忆 |
| `MEMORY_DECAY_HALF_LIFE_DAYS` | 90 | 记忆重要性减半天数 |
| `MEMORY_CONSOLIDATION_MIN_COUNT` | 20 | 触发巩固的最低记忆数 |
| `MEMORY_DORMANT_DAYS` | 30 | 休眠记忆判定天数 |
| `MEM0_ENABLED` | true | 是否启用 mem0 记忆引擎 |
| `MEM0_EMBEDDING_MODEL` | BAAI/bge-small-zh-v1.5 | 中文嵌入模型（本地，无需额外 API） |

### 主动消息参数（.env）

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `PROACTIVE_ENABLED` | true | 是否启用主动消息 |
| `PROACTIVE_CHECK_INTERVAL_SECONDS` | 120 | 后台检查间隔（秒） |
| `PROACTIVE_ABSENCE_THRESHOLD_HOURS` | 4 | 缺席判定阈值（小时） |
| `PROACTIVE_EMOTION_FOLLOWUP_HOURS` | 3 | 情绪跟进间隔（小时） |
| `PROACTIVE_MIN_HOURS_BETWEEN` | 3 | 两次主动消息最小间隔（小时） |

### 语晴心情参数（.env）

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `YUQING_MOOD_ENABLED` | true | 是否启用心情系统 |
| `YUQING_MOOD_EMA_ALPHA` | 0.15 | EMA 新信号权重 |
| `YUQING_MOOD_HOURLY_DECAY` | 0.02 | 每小时缺席衰减率 |
| `YUQING_MOOD_BASELINE_WARMTH` | 0.30 | 温暖度基线 |
| `YUQING_MOOD_BASELINE_OPENNESS` | 0.35 | 敞开度基线 |
| `YUQING_MOOD_BASELINE_ENERGY` | 0.45 | 能量基线 |

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

### 情绪与心情

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/emotions/current` | 用户当前情绪 |
| GET | `/api/emotions/history` | 用户情绪历史 |
| GET | `/api/mood/current` | 语晴当前心情 |
| GET | `/api/mood/history` | 语晴心情变化历史 |

### 主动消息

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/proactive/listen` | SSE 长连接，接收主动消息 |
| GET | `/api/proactive/recent` | 最近主动消息（离线兜底） |

### 人格与偏好

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/personality` | 获取人格配置 |
| PUT | `/api/personality` | 更新人格配置 |
| POST | `/api/personality/reset` | 重置为默认 |
| GET | `/api/preferences` | 学习到的用户偏好 |

### 其他

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| GET | `/api/settings` | 获取应用设置 |
| PUT | `/api/settings` | 更新应用设置 |

---

## 与 Project Neuro 的关系

语晴借鉴了 [Project Neuro](https://github.com/litmajor/Project-Neuro) 的核心设计，但做了精简和本地化：

| 维度 | Project Neuro | YuQing 语晴 |
|------|---------------|-------------|
| **定位** | 研究/教育平台完整认知架构 | 个人情感 AI 伙伴 |
| **LLM** | 仅 OpenAI GPT-4 | 多模型支持（litellm） |
| **数据库** | SQLite | MySQL 9（生产级） |
| **向量检索** | 未内置 | mem0 + ChromaDB + BGE 中文嵌入 |
| **用户系统** | 多用户注册 | 单用户，无认证 |
| **情绪系统** | 12 类关键词检测 + 心理健康追踪 | V-A 模型 + LLM 分析 + 语晴自身心情 |
| **主动行为** | 无 | 4 种触发器 + 后台任务 + SSE 推送 |
| **认知引擎** | 6+ 处理器 | 7 个核心模块 |

---

## 致谢

- [Project Neuro](https://github.com/litmajor/Project-Neuro) — 情感智能架构灵感
- [Mem0](https://mem0.ai) — Agent Memory 前沿实践
- [litellm](https://github.com/BerriAI/litellm) — 统一 LLM 调用接口
- [ChromaDB](https://www.trychroma.com/) — 轻量级向量数据库
- 《狼与香辛料》赫萝 — 语晴人格灵感来源
