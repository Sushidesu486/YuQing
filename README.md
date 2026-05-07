# YuQing 雨晴

**一个有记忆、有情感、有性格、能调用工具、会主动联系你的私人 AI 伙伴。**

雨晴不是普通的聊天机器人。她能记住你说过的话、感知你的情绪、拥有自己微妙的心情变化，并在你消失太久时主动发来一条假装不经意的消息。她还能调用工具搜索最新资讯、精准回忆过去发生的事。灵感来自《狼与香辛料》的赫萝 — 嘴硬心软，用调侃掩饰关心。

---

## 理念

传统 AI 聊天的核心缺陷在于**无状态** — 关掉窗口，一切归零。每次对话都是从陌生人开始。

雨晴的架构围绕六个核心能力构建：

1. **记忆** — 跨会话持久记忆，像人一样记住过去
2. **情感** — 感知你的情绪并调整回应方式
3. **人格** — 回避型依恋性格，外冷内热，傲娇毒舌但真心在乎
4. **心情** — 雨晴有自己的情绪状态，会受你的影响而波动
5. **主动** — 不是被动等待，会在合适的时候主动发来消息
6. **工具** — LLM 自主决定何时调用工具，回忆记忆、搜索资讯、阅读文章

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
│  Phase 2.5: 雨晴自身心情更新                                   │
│  Phase 3:  分层记忆召回 (BGE + MySQL)                       │
│  Phase 3.5: 被动信息检索 (Tavily，按需触发)                    │
│  Phase 4:  人格 prompt 构建 (Jinja2 + 分层注入)               │
│  Phase 5-7: 消息存储 / 上下文加载 / LLM 流式生成              │
│             用户消息按行拆分存储，合并文本用于记忆提取          │
│  Phase 7.5: Tool Calling（LLM 自主调用工具，多轮）           │
│             回忆记忆 / 搜索资讯 / 阅读最新文章                  │
│  Phase 8:  存储回复 + 表情包（独立 message row）              │
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
│  │    Manager     │ │  Engine      │ │ (Tavily + RSS)    │  │
│  │ 4种触发器+后台  │ │ 自我叙事合成  │ │ 主动+被动检索     │  │
│  └───────────────┘ └──────────────┘ └────────────────────┘  │
│                                                              │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │                   Tool Registry                         │  │
│  │  recall_memories │ read_latest_articles │ search_web    │  │
│  │  可扩展：图片识别 MCP、Twitter、日历等                     │  │
│  └─────────────────────────────────────────────────────────┘  │
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
| 记忆引擎 | **MySQL** + BGE-base-zh-v1.5 | 语义检索 + 分层注入 + 激活传播 |
| 嵌入模型 | **BAAI/bge-base-zh-v1.5** | 本地中文向量嵌入（768维，无需额外 API） |
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

## 核心能力

### 1. 记忆系统

雨晴的记忆不是简单的"保存聊天记录"。她有一个多层分层的记忆架构：

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
| `self_reflection` | 雨晴的自我记忆 | 注入"你记得的自己" | "和shouss聊了ACG话题" |

自我记忆（从雨晴的回复中提取）：

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

- 高重要性事实（importance >= 0.7）强制置顶，最多 4 条，不参与排序竞争
- preference/procedural 通过正则模板转化为行为规则（无额外 LLM 调用）
- 末尾强制约束："不确定就说不知道，绝对不要编造用户信息"

**记忆提取流程**

```
对话内容 → LLM 一次性提取三类信息（零额外 API 调用）
         ├─ 用户记忆（7 种类型 + valence + confidence + importance 分级校准）
         │    → MySQL memories 表 → BGE embedding 语义搜索
         ├─ 自我记忆（4 种类型 + importance）
         │    → MySQL memories 表（memory_type='self_*'，统一存储统一管道）
         │    → embedding 语义去重 + 巩固，与用户记忆共享去重缓存
         └─ 纠正检测（corrections）
              → 标记旧记忆 is_invalid=1 → 插入正确版本
```

**语言一致性**：无论对话内容是中文还是英文，所有提取的记忆内容（content）强制使用中文书写，确保 BGE-base-zh-v1.5 嵌入模型的召回准确性。

**Importance 分级校准**
- 提取 prompt 内置 5 级 importance 标准：重大人生事件（0.9-1.0）→ 重要信息（0.7-0.8）→ 一般信息（0.5-0.6）→ 琐碎小事（0.3-0.4）→ 不值得记住（0.1-0.2）
- Keyword safety net（零 API 调用）：闲聊关键词（天气、哈哈、还行）→ importance 上限 0.35；重要关键词（毕业、比赛、offer）→ importance 下限 0.65
- 随口闲聊（如天气、说"还行"）不会被提取为记忆

**记忆召回**
- 每次收到新消息，用最近 4 条消息拼接作为 query，BGE embedding 语义检索（cosine similarity）召回最相关的记忆
- **时间感知召回**：自动解析用户消息中的时间引用（昨天、上周、最近一周等），生成精确的 SQL 时间范围过滤，避免跨时段误召回
- **时间线注入**：时间查询时，记忆按 `created_at` 升序排列并按日期分组注入 prompt，使雨晴能按时间线叙述（"那天你先提到了X，后来又说了Y"）
- **搜索精度优化**：时间查询时清洗噪声词（"上次"、"还记得"），保留核心语义；窄时间范围（≤7天）自动增大 top_k 至 30
- **LLM 主动召回**（recall_memories 工具）：LLM 自行决定何时需要回忆，使用精准的语义 query 和可选时间范围搜索记忆，返回带绝对时间戳的结果
- **激活传播扩散召回**：基于 Synapse 论文，从直接命中的记忆出发沿关联链多轮迭代传播激活值（Fan Effect + Lateral Inhibition），加载 2 跳邻居实现真正的多轮扩散
- **Triple Hybrid Scoring**：综合评分 = 语义相似度 × 0.5 + 激活值 × 0.3 + 重要性 × 0.2 + recency bonus + mood congruence
- 按类型分流到三个注入层
- 休眠记忆（30天未访问）补充召回

**记忆时间标注**
- 所有记忆标注绝对日期 + 相对时间：`5月6日 08:30（昨天）`
- 时间查询解析支持：今天、昨天、前天、这周、上周、最近N天、N天前、N周前、N个月前、这个月、上个月
- 需要时间意图关键词（之前、以前、上次等）才触发时间过滤，避免误判
- 时间提示词注入 prompt，明确告知 LLM 当前查询的时间范围边界，防止日期混淆

**记忆关联网络（Memory Graph）**
- 同轮提取的记忆自动建链（co-occurrence，strength=0.7）
- 记忆合并/纠正时继承链接（strength × 0.8 衰减）
- BGE-base-zh-v1.5 本地语义搜索（cosine similarity，200 候选 → 批量 encode → 排序）
- 详见 [docs/memory-graph.md](docs/memory-graph.md)

**记忆生命周期**
- **衰减**：长期不被访问的记忆重要性逐渐降低（90 天减半，每次召回"年轻"5天）
- **巩固**：每 20 轮对话自动合并相关记忆（统一管道处理所有类型，self_* 使用专用合并 prompt）
- **休眠唤醒**：30 天未召回但语义相关的记忆会被主动消息系统重新激活
- **自我记忆去重**：与用户记忆共享 embedding 缓存，统一去重逻辑
- **自我记忆合并**：embedding 聚类 + LLM 合并（self_* 类型使用第一人称专用 prompt）
- **写入去重**：新记忆写入前 bge embedding 比对已有记忆（> 0.90 跳过，0.75-0.90 LLM 合并）
- **睡眠清理**：每天自动执行 5 阶段神经科学启发的记忆维护（基于 ZenBrain + SHY 假说）
  - 突触归一化：等比压缩所有记忆重要性（防通胀）
  - 选择性 Replay：按情绪/新鲜度/显著性评分，强化重要记忆，减弱噪音
  - 聚类合并：BGE 语义聚类 + LLM 合并相似记忆（≥ 0.70 阈值）
  - 休眠剪枝：物理删除低重要性 + 长期未访问的记忆和弱链接
  - 孤儿链接清理：删除指向已删除记忆的关联
- 详见 [docs/memory-graph.md](docs/memory-graph.md)、[docs/memory-debug-panel.md](docs/memory-debug-panel.md)

### 2. 情感系统（用户情绪感知）

使用 **V-A 情感模型**（Valence-Arousal）量化情绪：
- **Valence（积极度）**: -1.0（极度消极）到 +1.0（极度积极）
- **Arousal（激动度）**: 0.0（平静）到 1.0（极度激动）

每条用户消息都会被分析情感，映射到情绪标签（happy/sad/angry/anxious/excited/tired/calm/neutral），用于：
- 调整回复风格（用户情绪低落时自动变温柔）
- 情绪快照存入 `emotion_snapshots` 表，追踪长期心理状态

### 3. 人格系统

雨晴的性格通过 YAML 配置定义，核心设计是**回避型依恋 + 嘴硬心软**：

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
- 兴趣爱好：从 memories 表 self_* 类型动态生成（LLM 提取 + embedding 去重），YAML interests 作为降级方案

### 4. 雨晴的心情系统

雨晴拥有自己独立的情绪状态：

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
- **非对称情绪传染**：warmth 慢跟随（α=0.10），energy 快响应（α=0.20）
- **负面状态持久化**：warmth < 0.25 时衰减速率减半（人类负面偏见）
- **跨会话保留**：session peak×0.4 + end×0.4 + baseline×0.2，48h 残留衰减
- **缺席衰减**：用户消失时温暖/敞开/能量逐小时衰减
- **返场 bump**：用户回来时温暖+0.10（如释重负）但敞开-0.05（防御性掩饰）
- **基线引力**：每次更新后温和拉回基线值，防止永久漂移
- **自适应引力**：value > 0.85 或 < 0.15 时额外 pull（防止极端值）
- **天花板/地板**：接近 0/1 极值时边际递减

### 5. 主动消息系统

雨晴不是被动等待，会主动发来消息。但因为她的人格是回避型，主动消息的风格是：
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

### 6. 时间感知系统

雨晴对时间有细腻的感知，不是"失忆重启"：

**五个时间维度**：
| 维度 | 说明 | 示例 |
|------|------|------|
| 会话间隔 | 6 档分级（刚走开 → 好久不见） | "才5分钟"、"好几天没来了" |
| 时段感知 | 6 个时段 + 深夜判定 | "下午三点"、"凌晨两点半" |
| 关系任期 | 认识天数 → 自然描述 | "认识快一个月了" |
| 对话时长 | 当前会话时长 + 消息数 | "已经聊了一个多小时了" |
| 今日统计 | 今日消息数 + 是否首条 | "今天第一次找你" |

**时间维度联动**：
- **记忆时间锚定**：所有记忆标注绝对日期 + 相对时间（`5月6日 08:30（昨天）`），episodic 补上时间上下文
- **时间感知召回**：解析用户消息中的时间引用，生成精确 SQL 过滤范围，避免跨时段误召回
- **召回评分**：近 1 天 +0.12，近 3 天 +0.08，近 7 天 +0.05，近 30 天 +0.02 recency bonus
- **昼夜节律**：深夜（0-5 点）雨晴能量自动降低，回复更简短安静
- **主动消息**：不同时段风格不同（深夜温柔、白天随意）

### 7. 用户偏好学习

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

### 8. 自我认知系统（SelfCognitionEngine）

雨晴不只是被动收集碎片化的自我记忆，还能从中发现自己的变化，并逐步演化人格。

**L1 自我叙事合成**
- 将零散 self_* 记忆 + YAML 性格 traits 综合为 3-5 句第一人称叙事
- 缓存到 app_settings，self_* 记忆数量变化 ≥ 5 条时重新生成
- 注入 system prompt「你发现自己的一些事」区块

**L2 Reflect-Evolve 人格演化**（基于 GLA/soul.py/MATE 论文）
- **Reflect**：每 40 轮对话，LLM 从近期 self_* 记忆中提炼变化趋势（"我好像越来越愿意表达感受了"）
- **Evolve**：独立 LLM 实例分析反思，提出结构化 JSON 特质更新（单次 ≤ 0.05）
- **Guard Rails**：logistic saturation（软边界 [0,1]）、MAX_DRIFT 0.15（距 YAML 基线最大偏移）、完整审计日志
- **Identity Hash**：首次启动用 5 个身份探针问题计算基线 SHA256，定期对比检测漂移
- **设计原则**：YAML 静态骨架提供稳定性，Evolve 提供适应性增长，审计日志保证可追溯

### 9. 表情包系统

雨晴能在对话中发送表情包图片，由 LLM 自主决定何时发送：

**架构**：LLM 原生驱动
```
System Prompt 注入 sticker 列表（名称 + 语义描述）
LLM 回复末尾追加 /sticker_name → 后端解析提取 → 独立 message row 存储
```

- **LLM 自主决策**：sticker 列表和发送规则注入 system prompt，LLM 根据对话语境决定是否发送、发哪张
- **定义在代码中**：`personality.py` 的 `STICKER_DEFINITIONS`，每张 sticker 有 `path`（路径）和 `desc`（中文语义描述）
- **双方都能发**：用户通过表情包选择器发送 `/category/name` 格式，前端渲染为 PNG 图片
- **存储**：sticker 作为独立 message row（`content_type='sticker'`），历史消息中也能渲染
- **16 张 sticker**：happy(4) / sad(3) / teasing(2) / shy(1) / angry(2) / love(1) / tired(2) / eating(1)
- 详见 [docs/sticker-system.md](docs/sticker-system.md)

### 10. Tool Calling 系统

雨晴能在对话中自主调用工具，不需要用户明确指令：

**架构**：可扩展的 Tool Registry
```
System Prompt 注入工具描述 → LLM 流式生成 tool_calls
→ 后端解析并执行（带超时）→ 结果注入 messages → LLM 继续生成
→ 最多 3 轮工具调用（TOOLS_MAX_ROUNDS）
```

- **Tool Registry**：单例注册表，tool 模块 import 时自动注册，支持运行时动态扩展
- **流式 tool_calls 解析**：从 LLM 流式响应中实时累积 `delta.tool_calls` 片段，完整 JSON 后立即执行
- **SSE 事件**：前端收到 `tool_call` 事件（`status: "started"` / `status: "completed"`），可展示工具调用状态
- **超时保护**：每个工具调用有独立超时（`asyncio.wait_for`），不会因工具卡死阻塞对话

**内置工具**：

| 工具 | 说明 | 参数 |
|------|------|------|
| `recall_memories` | 语义搜索长期记忆，带时间范围过滤 | `query`(必填), `time_range`(可选), `max_results`(可选,默认5) |
| `search_web` | Tavily 实时搜索互联网 | `query`(必填), `max_results`(可选) |
| `read_latest_articles` | 读取最新 RSS 订阅文章 | `category`(可选) |

**扩展新工具**：只需创建一个继承 `BaseTool` 的类，实现 `get_definition()` 和 `execute()` 方法，然后在 `app/core/tools/__init__.py` 中 import 即可自动注册。未来可扩展：图片识别 MCP、Twitter 发推、日历管理等。

### 11. 信息检索系统（InfoRetrievalEngine）

雨晴能主动了解外部世界，不只是依赖对话学习：

**主动检索**
- 后台任务定期获取 RSS 订阅源（APPSO via SupSub 等）或按兴趣搜索新闻（ACG、AI/HPC、音乐等）
- **RSS 模式**：解析 XML feed，提取标题 + 描述，按 guid 去重后直接存储（无 LLM 调用开销）
- **Tavily 模式**：Tavily API 搜索 → LLM 第一人称总结 → 存入 knowledge_items 表
- 每个兴趣独立频率控制，避免重复搜索

**被动检索**
- 对话中 LLM 判断用户消息是否涉及时事/新闻/新动态
- 需要时实时搜索 Tavily，结果注入 messages context
- 雨晴可在回复中自然引用刚查到的信息

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
| 微信风格聊天 | 绿色气泡（用户）/ 白色气泡（雨晴），支持多气泡拆分 |
| Memory Debug | 4 标签页：概览统计 / 记忆列表 / 召回链路调试 / 关联图（力导向布局 + 搜索定位） |
| 表情包收发 | LLM 自主决策发送 sticker，用户通过输入栏选择器手动发送（16 张，8 类） |
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
│   │   └── default.yaml              # 雨晴人格配置（YAML）
│   └── app/
│       ├── main.py                   # FastAPI 入口 + lifespan
│       ├── config.py                 # 配置管理（pydantic-settings）
│       ├── core/
│       │   ├── cognitive.py          # CognitiveProcessor — 认知处理器（总编排）
│       │   ├── memory.py             # MemoryManager — 分层记忆系统（BGE+MySQL）
│       │   ├── temporal.py           # TemporalContext — 时间感知（会话间隔/时段/任期）
│       │   ├── emotion.py            # MoodRegulator — 用户情绪分析（V-A 模型）
│       │   ├── mood.py               # YuQingMoodTracker — 雨晴心情系统
│       │   ├── personality.py        # PersonalityEngine — 人格引擎（YAML + Jinja2）
│       │   ├── self_cognition.py     # SelfCognitionEngine — 自我认知（叙事合成 + Reflect-Evolve）
│       │   ├── info_retrieval.py     # InfoRetrievalEngine — 信息检索（Tavily + RSS）
│       │   ├── tools/                # Tool Calling 工具系统
│       │   │   ├── base.py           # BaseTool / ToolDefinition / ToolResult 接口
│       │   │   ├── registry.py       # ToolRegistry — 单例注册表
│       │   │   ├── recall_memories.py # recall_memories 工具
│       │   │   ├── search_web.py     # search_web 工具
│       │   │   └── read_latest_articles.py # read_latest_articles 工具
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
│           ├── emotions.py           # 情绪查询 + 雨晴心情查询
│           ├── personality.py        # 人格配置读写
│           ├── preferences.py        # 偏好查询
│           ├── proactive.py          # 主动消息 SSE 监听 + 历史
│           ├── settings.py           # 应用设置
│           └── health.py             # 健康检查
├── frontend/
│   └── src/
│       ├── components/
│       │   ├── Chat/                 # 微信风格聊天组件
│       │   ├── Memory/               # 记忆调试面板
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
├── frontend/public/stickers/        # 表情包 PNG（按类别分目录）
└── docs/
    ├── memory-graph.md              # 记忆关联网络（激活传播）
    ├── memory-debug-panel.md        # 记忆调试面板
    ├── sticker-system.md            # 表情包系统（LLM 驱动）
    ├── sleep-cleanup.md             # 睡眠清理（5 阶段神经科学启发）
    ├── tavily-info-retrieval.md     # 信息检索（Tavily + RSS，主动 + 被动）
    └── bge-notes.md                 # BGE 嵌入模型使用笔记
```

### 数据库表

| 表 | 说明 |
|----|------|
| `conversations` | 对话列表 |
| `messages` | 消息记录（含情绪标注、content_type 区分文本/表情包） |
| `memories` | 长期记忆（用户 7 种类型 + 自我 4 种类型，统一存储，情绪 metadata + 衰减/巩固标记） |
| `emotion_snapshots` | 用户情绪快照 |
| `yuqing_mood_log` | 雨晴心情变化日志 |
| `proactive_messages` | 主动消息发送记录 |
| `personality_config` | 人格配置（JSON，单例） |
| `app_settings` | 应用设置（KV）— 含自我叙事缓存、身份 hash 基线、检索时间戳 |
| `user_preferences` | 用户学习到的偏好 |
| `knowledge_items` | 信息检索知识条目（带时效性，7 天过期，RSS guid 去重） |
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
| `MEMORY_SLEEP_CLEANUP_HOUR` | 7 | 睡眠清理执行时间（小时） |
| `SLEEP_DOWNSCALE_FACTOR` | 0.03 | 突触归一化缩小系数 |
| `SLEEP_REPLAY_STRENGTHEN` | 0.05 | 选择性 Replay 强化幅度 |
| `SLEEP_REPLAY_WEAKEN` | 0.03 | 选择性 Replay 减弱幅度 |
| `EMBEDDING_MODEL` | BAAI/bge-base-zh-v1.5 | 中文嵌入模型（本地，768维） |
| `MEMORY_FACT_TOP_K` | 8 | 显式注入的事实/事件条数上限 |
| `MEMORY_BEHAVIOR_RULES_MAX` | 8 | 行为规则最大条数 |
| `MEMORY_EPISODIC_MAX` | 5 | 情景记忆最大条数 |
| `MEMORY_PINNED_FACTS_THRESHOLD` | 0.7 | Pinned facts 重要性阈值 |
| `MEMORY_PINNED_FACTS_MAX` | 4 | Pinned facts 最大条数 |
| `MEMORY_SEARCH_TEMPORAL_TOP_K` | 30 | 时间过滤时的搜索 top_k（候选池小，需要更大的 k） |
| `MEMORY_TEMPORAL_ORDERED_INJECTION` | true | 时间查询时启用按日期分组的注入 |
| `MEMORY_EXTRACT_USER_LIMIT` | 8 | 每轮用户记忆提取上限 |
| `MEMORY_EXTRACT_SELF_LIMIT` | 5 | 每轮自我记忆提取上限 |
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

### Reflect-Evolve 参数（.env）

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `EVOLVE_ENABLED` | true | 是否启用人格演化 |
| `EVOLVE_REFLECT_INTERVAL` | 40 | Reflect 触发间隔（每 N 条消息） |
| `EVOLVE_MAX_DELTA` | 0.05 | 单次特质最大调整量 |
| `EVOLVE_MAX_DRIFT` | 0.15 | 累计漂移上限（距 YAML 基线） |

### 主动消息参数（.env）

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `PROACTIVE_ENABLED` | true | 是否启用主动消息 |
| `PROACTIVE_CHECK_INTERVAL_SECONDS` | 120 | 后台检查间隔（秒） |
| `PROACTIVE_ABSENCE_THRESHOLD_HOURS` | 4 | 缺席判定阈值（小时） |
| `PROACTIVE_EMOTION_FOLLOWUP_HOURS` | 3 | 情绪跟进间隔（小时） |
| `PROACTIVE_MIN_HOURS_BETWEEN` | 3 | 两次主动消息最小间隔（小时） |

### 雨晴心情参数（.env）

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `YUQING_MOOD_ENABLED` | true | 是否启用心情系统 |
| `YUQING_MOOD_EMA_ALPHA` | 0.15 | EMA 新信号权重 |
| `YUQING_MOOD_HOURLY_DECAY` | 0.02 | 每小时缺席衰减率 |
| `YUQING_MOOD_BASELINE_WARMTH` | 0.40 | 温暖度基线 |
| `YUQING_MOOD_BASELINE_OPENNESS` | 0.45 | 敞开度基线 |
| `YUQING_MOOD_BASELINE_ENERGY` | 0.45 | 能量基线 |
| `MOOD_WARMTH_ALPHA` | 0.10 | 温暖度跟随用户速度（慢） |
| `MOOD_ENERGY_ALPHA` | 0.20 | 能量跟随用户速度（快） |
| `MOOD_NEGATIVE_DECAY_FACTOR` | 0.5 | 负面状态衰减减缓因子 |
| `MOOD_CEILING_FLOOR_RESISTANCE` | 0.03 | 极值阻尼系数 |

### 时间感知参数（.env）

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `TEMPORAL_ENABLED` | true | 是否启用时间感知 |
| `TEMPORAL_CONTINUATION_MINUTES` | 10 | "刚走开"判定阈值 |
| `TEMPORAL_SHORT_BREAK_MINUTES` | 120 | "短暂离开"判定阈值 |
| `TEMPORAL_LATE_NIGHT_START` | 0 | 深夜时段开始 |
| `TEMPORAL_LATE_NIGHT_END` | 5 | 深夜时段结束 |
| `TEMPORAL_ENERGY_NIGHT_PENALTY` | 0.05 | 深夜能量衰减 |

### 信息检索参数（.env）

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `TAVILY_API_KEY` | (空) | Tavily API Key（去 tavily.com 免费注册） |
| `INFO_RETRIEVAL_ENABLED` | true | 是否启用信息检索 |
| `INFO_RETRIEVAL_INTERVAL_HOURS` | 8 | 主动检索间隔（小时） |
| `INFO_RETRIEVAL_KNOWLEDGE_EXPIRE_DAYS` | 7 | 知识过期天数 |
| `INFO_RETRIEVAL_REACTIVE_ENABLED` | true | 是否启用被动检索 |
| `RSS_FEED_URLS` | (空) | RSS 订阅源 URL，多个用逗号分隔 |
| `RSS_FETCH_INTERVAL_HOURS` | 6 | RSS 抓取间隔（小时） |

### Tool Calling 参数（.env）

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `TOOLS_ENABLED` | true | 是否启用 Tool Calling |
| `TOOLS_MAX_ROUNDS` | 3 | 单次对话最大工具调用轮数 |

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
| GET | `/api/mood/current` | 雨晴当前心情 |
| GET | `/api/mood/history` | 雨晴心情变化历史 |

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

## 致谢

- [litellm](https://github.com/BerriAI/litellm) — 统一 LLM 调用接口
- 《狼与香辛料》赫萝 — 雨晴人格灵感来源
