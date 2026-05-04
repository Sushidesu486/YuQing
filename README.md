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
│  SearchPanel ─ EmotionDisplay ─ SettingsModal ─ Sidebar    │
│  useChat ─ useConversations ─ useProactive (SSE hooks)      │
└────────────────────────┬────────────────────────────────────┘
                         │ SSE Streaming + EventSource
┌────────────────────────▼────────────────────────────────────┐
│                    CognitiveProcessor                         │
│                  （认知处理器 · 总编排）                        │
│                                                              │
│  Phase 1:  用户情绪分析 (V-A 模型)                             │
│  Phase 2:  用户当前情绪状态                                    │
│  Phase 2.5: 语晴自身心情更新                                   │
│  Phase 3:  分层记忆召回 (BGE + MySQL)                       │
│  Phase 3.5: 被动信息检索 (Tavily，按需触发)                    │
│  Phase 4:  人格 prompt 构建 (Jinja2 + 分层注入)               │
│  Phase 5-7: 消息存储 / 上下文加载 / LLM 流式生成              │
│             用户消息按行拆分存储，合并文本用于记忆提取          │
│  Phase 9:  记忆提取 / 纠正 / 衰减 / 巩固 / 自我叙事 / 偏好   │
│                                                              │
│  ┌───────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────┐   │
│  │Personality │ │  Memory  │ │ Emotion  │ │  YuQing Mood  │   │
│  │  Engine    │ │ Manager  │ │Regulator │ │   Tracker     │   │
│  │ YAML+Jinja │ │MySQL+BGE │ │ V-A LLM  │ │  EMA + 关键词 │   │
│  └───────────┘ └──────────┘ └──────────┘ └───────────────┘   │
│                                                              │
│  ┌───────────────┐ ┌──────────────┐ ┌────────────────────┐  │
│  │    Proactive   │ │  SelfCog     │ │  InfoRetrieval    │  │
│  │    Manager     │ │  Engine      │ │  (Tavily API)     │  │
│  │ 4种触发器+后台  │ │ 自我叙事合成  │ │ 主动+被动检索     │  │
│  └───────────────┘ └──────────────┘ └────────────────────┘  │
│                                                              │
│  ┌──────────────┐ ┌────────────────────┐                     │
│  │ Preference   │ │      LLM           │                    │
│  │  Learner     │ │  (litellm 统一接口) │                    │
│  │ 5维偏好学习   │ │ DeepSeek/GLM/etc  │                     │
│  └──────────────┘ └────────────────────┘                     │
└──────────────────────────────────────────────────────────────┘
```

### 后端技术栈

| 组件 | 技术 | 说明 |
|------|------|------|
| Web 框架 | **FastAPI** (Python, async) | 异步，高性能 |
| 数据库 | **MySQL 9** | 结构化数据持久化 |
| 记忆引擎 | **MySQL** + BGE-small-zh-v1.5 | 语义检索 + 分层注入 + 激活传播 |
| 嵌入模型 | **BAAI/bge-small-zh-v1.5** | 本地中文向量嵌入（512维，无需额外 API） |
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

## 七大核心能力

### 1. 记忆系统

语晴的记忆不是简单的"保存聊天记录"。她有一个多层分层的记忆架构：

**工作记忆（Working Memory）**
- 最近 20 条对话上下文（可配置）
- 当前对话的短期记忆，关闭页面后丢失

**长期记忆 — 7 种用户记忆 + 4 种自我记忆**

用户记忆：

| 类型 | 说明 | 注入方式 | 示例 |
|------|------|---------|------|
| `fact` | 用户事实信息 | 显式原文 | "用户叫shouss" |
| `event` | 重要的生活事件 | 显式原文（带时间） | "用户拿到ASC比赛名额" |
| `episodic` | 带情绪色彩的情景记忆 | 情感层注入 | "聊到学历偏见时用户很激动" |
| `emotion` | 情绪记忆（情感模式） | 影响 mood 系统 | "用户被质疑能力时会愤怒" |
| `preference` | 用户偏好 | 转化为行为规则 | "用户不喜欢被说教" |
| `procedural` | 行为互动模式 | 转化为行为规则 | "用户习惯晚上聊天" |
| `self_reflection` | 语晴的自我记忆 | 注入"你记得的自己" | "和shouss聊了ACG话题" |

自我记忆（从语晴的回复中提取）：

| 类型 | 说明 | 示例 |
|------|------|------|
| `self_interest` | 兴趣爱好 | "我喜欢看番"、"我对音乐挺挑剔的" |
| `self_experience` | 个人经历 | "我以前也学过这个"、"那个我看过了" |
| `self_opinion` | 观点和态度 | "我觉得这没什么"、"我认为" |
| `self_habit` | 习惯和倾向 | "我一般不..."、"我习惯..." |

**分层注入机制**

记忆不是简单丢进 prompt，而是按类型分三层注入：

```
显式层 → "你记得的关于用户的事"    ← fact + event 原文（带时间标注）
情感层 → "最近想起的画面"          ← episodic 情景记忆（带情绪极性）
行为层 → "你自然形成的态度"        ← preference/procedural 转化为行为指令
```

- 高重要性事实（importance >= 0.8）强制置顶，不参与排序竞争
- preference/procedural 通过正则模板转化为行为规则（无额外 LLM 调用）
- 末尾强制约束："不确定就说不知道，绝对不要编造用户信息"

**记忆提取流程**

```
对话内容 → LLM 一次性提取三类信息（零额外 API 调用）
         ├─ 用户记忆（7 种类型 + valence + confidence）
         │    → MySQL memories 表 → BGE embedding 语义搜索
         ├─ 自我记忆（4 种类型 + importance）
         │    → embedding 语义去重（bge cosine similarity）
         │    → MySQL self_memories 表
         └─ 纠正检测（corrections）
              → 标记旧记忆 is_invalid=1 → 插入正确版本
```

**记忆召回**
- 每次收到新消息，BGE embedding 语义检索（cosine similarity）召回最相关的记忆
- **激活传播扩散召回**：基于 Synapse 论文，从直接命中的记忆出发沿关联链多轮迭代传播激活值（Fan Effect + Lateral Inhibition），联想扩散到相关记忆
- **Triple Hybrid Scoring**：综合评分 = 语义相似度 × 0.5 + 激活值 × 0.3 + 重要性 × 0.2，替代纯语义排序
- 按类型分流到三个注入层
- 休眠记忆（30天未访问）补充召回

**记忆关联网络（Memory Graph）**
- 同轮提取的记忆自动建链（co-occurrence，strength=0.7）
- 记忆合并/纠正时继承链接（strength × 0.8 衰减）
- BGE-small-zh-v1.5 本地语义搜索（cosine similarity，200 候选 → 批量 encode → 排序）
- 详见 [docs/memory-graph.md](docs/memory-graph.md)

**记忆生命周期**
- **衰减**：长期不被访问的记忆重要性逐渐降低（90 天减半，每次召回"年轻"5天）
- **巩固**：每 20 轮对话自动合并相关记忆（用户记忆 + 自我记忆分别合并）
- **休眠唤醒**：30 天未召回但语义相关的记忆会被主动消息系统重新激活
- **自我记忆去重**：本地 bge embedding 语义去重（相似度 > 0.85 跳过，0.6-0.85 强化已有记忆）
- **自我记忆合并**：embedding 聚类（> 0.75 归一组）+ LLM 合并 ≥ 3 条相似自我记忆为精炼总结
- **写入去重**：新记忆写入前 bge embedding 比对已有记忆（> 0.90 跳过，0.75-0.90 LLM 合并）
- **睡眠清理**：每天凌晨 4 点自动聚类合并（≥ 0.70 阈值）
- 详见 [docs/memory-graph.md](docs/memory-graph.md)、[docs/memory-debug-panel.md](docs/memory-debug-panel.md)

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
- 兴趣爱好：从 self_memories 动态生成（LLM 提取 + embedding 去重），YAML interests 作为降级方案

### 4. 语晴的心情系统

语晴拥有自己独立的情绪状态，参照 Project Neuro 的 CognitiveState 设计：

**三个维度**：
| 维度 | 基线 | 含义 |
|------|------|------|
| `warmth` | 0.40 | 内在温暖度（0=冷漠 1=温暖） |
| `openness` | 0.45 | 防线松紧度（0=高防御 1=敞开心扉） |
| `energy` | 0.45 | 能量水平（0=安静 1=有活力） |

**五种状态**：
| 状态 | 触发条件 | 行为表现 |
|------|----------|----------|
| `guarded` | 默认状态 | 正常人格表现 |
| `withdrawn` | warmth<0.25 且 openness<0.30 | 更安静简短，偶尔刻薄，但绝不敷衍 |
| `relaxed` | warmth>0.40 或 openness>0.45 | 放松，调侃更轻松，允许多说两句 |
| `softened` | warmth>0.60 且 openness>0.60 | 不太一样，偶尔说平时不会说的话 |
| `vulnerable` | warmth>0.80 且 openness>0.75 | 极罕见，防线崩塌，会说真正想说的话 |

**心情更新机制**：
- **对话驱动**：每轮对话根据用户情绪 + 关键词信号更新（EMA 指数移动平均，alpha=0.15）
- **缺席衰减**：用户消失时温暖/敞开/能量逐小时衰减
- **返场 bump**：用户回来时温暖+0.10（如释重负）但敞开-0.05（防御性掩饰）
- **基线引力**：每次更新后温和拉回基线值，防止永久漂移

### 5. 主动消息系统

语晴不是被动等待，会主动发来消息。但因为她的人格是回避型，主动消息的风格是：
- 偶尔流露一丝关心："今天有没有乖乖吃饭"，然后迅速转移话题
- 绝不用"..."敷衍 — 即使简短也要有内容

**4 种触发器**（按优先级）：
| 触发器 | 条件 | 示例消息 |
|--------|------|----------|
| `emotion_followup` | 用户上次情绪很低落且已过 3 小时 | 推荐一首歌过来 |
| `absence` | 用户 4 小时没发消息 | "你还活着啊" |
| `memory` | 高重要性休眠记忆被随机选中 | "突然想起你说过..." |
| `time_of_day` | 早 7-9 点 / 晚 9-11 点（每天一次） | "起了？" |

**Rate Limiting**：任意两次主动消息间隔 >= 3 小时。安静时段 0:00-7:00。

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
- 置信度 >= 0.5 的偏好注入 system prompt

### 6. 自我认知系统（SelfCognitionEngine）

语晴不只是被动收集碎片化的自我记忆，还能将它们合成为连贯的自我叙事：

**自我叙事合成**
- 将零散 self_memories + YAML 性格 traits 综合为 3-5 句第一人称叙事
- LLM prompt 包含性格维度数值，确保叙事风格一致（warmth 0.45 不会写出热情奔放的风格）
- 缓存到 app_settings，self_memories 变化 ≥ 5 条时重新生成
- 注入 system prompt「你发现自己的一些事」区块

**设计原则**：YAML 静态骨架（不可变）+ 自我叙事（动态补充）共存，不冲突。

### 7. 信息检索系统（InfoRetrievalEngine）

语晴能主动了解外部世界，不只是依赖对话学习：

**主动检索**
- 后台任务每 8 小时按 YuQing 兴趣自动搜索新闻（ACG、AI/HPC、音乐等）
- Tavily API 搜索 → LLM 第一人称总结 → 存入 knowledge_items 表
- 每个兴趣独立频率控制，避免重复搜索

**被动检索**
- 对话中 LLM 判断用户消息是否涉及时事/新闻/新动态
- 需要时实时搜索 Tavily，结果注入 messages context
- 语晴可在回复中自然引用刚查到的信息

**时效性管理**
- 知识 7 天后自动过期（expires_at）
- 过期知识不再注入 system prompt
- 存储在独立 knowledge_items 表，与记忆系统分离

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

### 前端特性

| 特性 | 说明 |
|------|------|
| 微信风格聊天 | 绿色气泡（用户）/ 白色气泡（语晴），支持多气泡拆分 |
| 消息搜索 | 右上角搜索入口，关键词/日期搜索，点击定位到消息位置 |
| 实时流式显示 | LLM 回复逐字显示，无需等待完成 |
| 消息批量发送 | 20 秒冷却窗口内多条消息自动合并发送 |
| 自动清理 | 空白/"..."等无意义回复自动过滤不显示 |

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
│       │   ├── memory.py             # MemoryManager — 分层记忆系统（BGE+MySQL）
│       │   ├── emotion.py            # MoodRegulator — 用户情绪分析（V-A 模型）
│       │   ├── mood.py               # YuQingMoodTracker — 语晴心情系统
│       │   ├── personality.py        # PersonalityEngine — 人格引擎（YAML + Jinja2）
│       │   ├── self_cognition.py     # SelfCognitionEngine — 自我认知（叙事合成）
│       │   ├── info_retrieval.py     # InfoRetrievalEngine — 信息检索（Tavily）
│       │   ├── preferences.py        # PreferenceLearner — 用户偏好学习
│       │   ├── proactive.py          # ProactiveManager — 主动消息系统
│       │   └── llm.py                # litellm 封装（流式/非流式）
│       ├── db/
│       │   └── database.py           # MySQL 建表 + 连接池（10 张表）
│       ├── prompts/
│       │   ├── system_zh.txt.j2      # 中文 system prompt 模板（分层注入）
│       │   └── system_en.txt.j2      # 英文 system prompt 模板（分层注入）
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
│       │   │   ├── ChatView.tsx       # 聊天主视图
│       │   │   ├── MessageList.tsx    # 消息列表（滚动定位 + 高亮）
│       │   │   ├── MessageBubble.tsx  # 消息气泡（多气泡拆分）
│       │   │   ├── SearchPanel.tsx    # 历史消息搜索面板
│       │   │   └── InputBar.tsx       # 消息输入框
│       │   ├── Layout/               # 页面布局 + Header
│       │   ├── Emotion/              # 情绪显示
│       │   ├── Settings/             # 设置面板
│       │   └── Sidebar/              # 对话列表侧栏
│       ├── hooks/                    # useChat, useConversations, useProactive
│       ├── services/api.ts           # API 请求封装
│       ├── types/index.ts            # TypeScript 类型定义
│       └── i18n/                     # 中英文翻译
├── data/                            # 运行时数据
└── docs/
    └── memory-report.md              # 记忆系统技术报告
```

### 数据库表

| 表 | 说明 |
|----|------|
| `conversations` | 对话列表 |
| `messages` | 消息记录（含情绪标注） |
| `memories` | 长期记忆（7种类型 + 情绪metadata + 衰减/巩固标记） |
| `self_memories` | 语晴的自我记忆（4 种类型 + embedding 去重 + 合并） |
| `emotion_snapshots` | 用户情绪快照 |
| `yuqing_mood_log` | 语晴心情变化日志 |
| `proactive_messages` | 主动消息发送记录 |
| `personality_config` | 人格配置（JSON，单例） |
| `app_settings` | 应用设置（KV）— 含自我叙事缓存、检索时间戳 |
| `user_preferences` | 用户学习到的偏好 |
| `knowledge_items` | 信息检索知识条目（带时效性，7 天过期） |
| `memory_links` | 记忆关联链接（co_occurrence/consolidated，激活传播用） |

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
| `EMBEDDING_MODEL` | BAAI/bge-small-zh-v1.5 | 中文嵌入模型（本地，512维） |
| `MEMORY_FACT_TOP_K` | 6 | 显式注入的事实/事件条数上限 |
| `MEMORY_BEHAVIOR_RULES_MAX` | 8 | 行为规则最大条数 |
| `MEMORY_EPISODIC_MAX` | 3 | 情景记忆最大条数 |
| `SELF_MEMORY_ENABLED` | true | 是否启用自我记忆 |

### 记忆关联网络参数（.env）

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `MEMORY_LINK_ENABLED` | true | 启用记忆关联网络（激活传播） |
| `MEMORY_LINK_MAX_ITERATIONS` | 3 | 激活传播最大迭代轮数 |
| `MEMORY_LINK_DECAY_RATE` | 0.5 | 每跳激活衰减率 |
| `MEMORY_LINK_FAN_EFFECT` | true | 启用 Fan Effect（出度归一化） |
| `MEMORY_LINK_LATERAL_INHIBITION` | true | 启用 Lateral Inhibition（Top-K 竞争） |
| `MEMORY_LINK_LATERAL_K` | 15 | Lateral Inhibition 保留数 |
| `MEMORY_LINK_ACTIVATION_THRESHOLD` | 0.1 | 激活值召回阈值 |

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
| `YUQING_MOOD_BASELINE_WARMTH` | 0.40 | 温暖度基线 |
| `YUQING_MOOD_BASELINE_OPENNESS` | 0.45 | 敞开度基线 |
| `YUQING_MOOD_BASELINE_ENERGY` | 0.45 | 能量基线 |

### 信息检索参数（.env）

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `TAVILY_API_KEY` | (空) | Tavily API Key（去 tavily.com 免费注册） |
| `INFO_RETRIEVAL_ENABLED` | true | 是否启用信息检索 |
| `INFO_RETRIEVAL_INTERVAL_HOURS` | 8 | 主动检索间隔（小时） |
| `INFO_RETRIEVAL_KNOWLEDGE_EXPIRE_DAYS` | 7 | 知识过期天数 |
| `INFO_RETRIEVAL_REACTIVE_ENABLED` | true | 是否启用被动检索 |

---

## API 接口

### 对话

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/chat/send` | 发送消息，SSE 流式返回 |
| GET | `/api/conversations` | 对话列表 |
| GET | `/api/conversations/{id}` | 对话详情 + 历史消息 |
| GET | `/api/conversations/{id}/search?q=xxx` | 搜索对话内消息 |

### 记忆

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/memories` | 所有长期记忆 |
| GET | `/api/memories/search?q=xxx` | 语义搜索记忆 |
| DELETE | `/api/memories/{id}` | 删除记忆 |
| POST | `/api/memories/debug/recall` | 调试：传入消息，返回完整召回链路（语义搜索 → 激活传播 → 最终排序） |
| GET | `/api/memories/debug/stats` | 调试：记忆系统状态概览（总数、链接数、类型分布） |
| POST | `/api/memories/debug/cleanup` | 手动触发睡眠清理 |
| GET | `/api/memories/links` | 所有记忆关联链接（调试面板用） |
| POST | `/api/memories/trigger-info-retrieval` | 手动触发信息检索（调试用） |
| GET | `/api/knowledge` | 查看当前未过期的知识条目 |

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
| **向量检索** | 未内置 | MySQL + BGE-small-zh-v1.5 本地语义搜索 || **记忆类型** | 基础分类 | 7种类型 + 分层注入 + 行为规则 |
| **用户系统** | 多用户注册 | 单用户，无认证 |
| **情绪系统** | 12 类关键词检测 + 心理健康追踪 | V-A 模型 + LLM 分析 + 语晴自身心情 |
| **主动行为** | 无 | 4 种触发器 + 后台任务 + SSE 推送 |
| **认知引擎** | 6+ 处理器 | 7 个核心模块 |

---

## 致谢

- [Project Neuro](https://github.com/litmajor/Project-Neuro) — 情感智能架构灵感
- [Mem0](https://mem0.ai) — Agent Memory 前沿实践（早期参考，已替换为本地 BGE + MySQL）
- [litellm](https://github.com/BerriAI/litellm) — 统一 LLM 调用接口
- 《狼与香辛料》赫萝 — 语晴人格灵感来源
