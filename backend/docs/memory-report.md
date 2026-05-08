# YuQing 记忆系统技术报告

> 最后更新: 2026-05-06
> 适用于: YuQing v3 (分层注入 + 多类型记忆 + 隐性影响)

---

## 1. 架构总览

YuQing 的认知系统由 6 个子系统组成，共同实现"有记忆、有情绪、有性格"的对话体验：

```
用户消息
  │
  ▼
┌─────────────────────────────────────────────────────────┐
│                  CognitiveProcessor                       │
│                  (cognitive.py)                          │
│                                                          │
│  Phase 1  情绪分析 (emotion.py)                          │
│  Phase 2  用户情绪上下文                                  │
│  Phase 2.5 雨晴自身心情更新 (mood.py)                     │
│  Phase 3  分层记忆召回 (memory.py ← mem0 + MySQL)        │
│  Phase 4  人格系统提示构建 (personality.py + jinja2)      │
│  Phase 5  存储用户消息到 MySQL                            │
│  Phase 6  加载上下文消息                                  │
│  Phase 7  LLM 流式生成                                   │
│  Phase 7.5 表情包选择（BGE 语义匹配，后处理）              │
│  Phase 8  存储助手回复 + 表情包 + 自动标题                 │
│  Phase 9  后台任务:                                       │
│          - 记忆衰减 (decay)                               │
│          - 记忆合并 (consolidation)                       │
│          - 情绪快照存储                                   │
│          - 记忆提取 + 分类 (extract → classify → store)  │
│          - 自我记忆提取 (self-memory)                     │
│          - 用户偏好学习 (preferences.py)                  │
└─────────────────────────────────────────────────────────┘
  │
  ▼
后台任务 (proactive.py):
  - 每 120s 检查主动消息触发条件
  - 触发类型: 情绪跟踪 / 缺席关注 / 记忆唤醒 / 时段问候
  - 最小间隔 3 小时，安静时段 0:00-7:00
```

### 存储分层

| 层 | 技术 | 用途 |
|----|------|------|
| **短期记忆** | MySQL `messages` 表 | 最近 N 条对话（默认 20 条） |
| **长期记忆（向量）** | BGE-base-zh-v1.5 本地嵌入 | 语义检索、记忆去重、聚类合并、sticker 匹配 |
| **长期记忆（结构化）** | MySQL `memories` 表 | 7 种记忆类型、元数据、衰减计算、CRUD |
| **自我记忆** | MySQL `self_memories` 表 | 雨晴自身的兴趣/经历认知 |
| **情绪快照** | MySQL `emotion_snapshots` | 情绪跟踪、主动消息触发 |
| **雨晴心情** | MySQL `yuqing_mood_log` | 三维心情状态（温暖/开放/活力） |
| **用户偏好** | MySQL `user_preferences` | 沟通风格学习、置信度加权 |
| **人格配置** | YAML + MySQL `personality_config` | 人格定义 + 运行时覆盖 |

---

## 2. v3 核心改进

### 2.1 从 v2 到 v3 的变化

| 维度 | v2 | v3 |
|------|-----|-----|
| 记忆类型 | 4 种 (fact/preference/event/emotion_pattern) | 7 种 (+ episodic/procedural/self_reflection) |
| 记忆 metadata | 无情绪标注 | valence/arousal/emotion_label/confidence |
| 注入方式 | 纯文本列表注入 prompt | 分层注入：显式层 + 情感层 + 隐性行为层 |
| 行为影响 | 记忆原文交由 LLM 自行理解 | preference/procedural 转化为行为规则直接指令 |
| 幻觉控制 | 无专门约束 | 强制记忆锚定 + 反幻觉约束 |
| 兴趣爱好 | YAML 写死 | 从 self_memories 动态生成 |
| mem0 使用 | `infer=True`（LLM 提取） | `infer=False`（纯向量存储） |
| 提取方式 | mem0 或 LLM 二选一 | LLM 分类提取 + mem0 向量存储（双路径并行） |

### 2.2 记忆类型体系

| 类型 | 说明 | 注入方式 | 示例 |
|------|------|---------|------|
| `fact` | 用户事实信息 | 显式原文 | "用户叫shouss" |
| `event` | 重要的生活事件 | 显式原文（带时间） | "2026-05 用户拿到ASC比赛名额" |
| `episodic` | 带情绪色彩的情景记忆 | 情感层注入 | "用户聊到学历偏见时很激动(valence=0.8)" |
| `emotion` | 情绪记忆（用户情感模式） | 影响 mood 系统 | "用户被质疑能力时会愤怒" |
| `preference` | 用户偏好 | 转化为行为规则 | "用户不喜欢被说教" |
| `procedural` | 行为互动模式 | 转化为行为规则 | "用户习惯晚上聊天" |
| `self_reflection` | 雨晴的自我记忆 | 替代 YAML interests | "和shouss聊了ACG话题，发现对老番有共鸣" |

---

## 3. mem0 集成详解

### 3.1 架构变更 (v3)

**核心变化**: mem0 从"记忆提取 + 向量存储"变为**纯向量存储**。

原因: 用户的 LLM (`openai/mimo-v2.5`) 不支持 function calling，而 `mem0.add(infer=True)` 依赖 function calling 来提取记忆。

**新架构**:
```
记忆提取:
  LLM (MEMORY_CLASSIFY_PROMPT_ZH) → 7种类型分类 + valence + confidence
  ↓
  MySQL memories 表（结构化存储，全 CRUD）
  ↓
  mem0.add(infer=False) → ChromaDB（纯向量存储，供语义检索）

记忆检索:
  mem0.search() → 返回向量匹配结果
  ↓
  _build_layered_memory() → 按类型分流
  ↓
  分层注入 system prompt
```

### 3.2 初始化配置

```python
# backend/app/core/memory.py — _get_mem0()

config = {
    "llm": {
        "provider": "litellm",
        "config": {
            "model": settings.LITELLM_MODEL,      # openai/mimo-v2.5
            "api_key": settings.LITELLM_API_KEY,
            "temperature": 0.1,
        },
    },
    "vector_store": {
        "provider": "chroma",
        "config": {
            "collection_name": "long_term_memory",
            "path": settings.chroma_abs_path,      # data/chroma_db/
        },
    },
    "embedder": {
        "provider": "huggingface",
        "config": {
            "model": "BAAI/bge-small-zh-v1.5",     # 512维中文向量，本地缓存
        },
    },
}
# 注意: api_base 通过环境变量传递（mem0 的 BaseLlmConfig 不支持 api_base 参数）
os.environ["LITELLM_API_BASE"] = settings.LITELLM_API_BASE
os.environ["OPENAI_API_BASE"] = settings.LITELLM_API_BASE
```

**关键决策:**
- **LLM**: 复用现有 LiteLLM 配置，`infer=False` 避免 function calling 依赖
- **Embedder**: 本地 HuggingFace 模型 BAAI/bge-base-zh-v1.5（768维），缓存于 `~/.cache/huggingface/`
- **Vector Store**: ChromaDB PersistentClient，数据持久化在磁盘
- **提取**: 所有 `mem0.add()` 调用均带 `infer=False`，记忆分类由自有 LLM prompt 完成

### 3.3 数据流

```
对话发生
  │
  ▼ (Phase 9, cognitive.py)
memory_manager.extract_and_store_memories()
  │
  ├── MEM0_ENABLED=True ──────────────────────────────┐
  │   _extract_via_mem0()                             │
  │                                                   │
  │   Step 1: LLM 分类提取                            │
  │   构造文本: "用户: {msg}\n雨晴: {resp}"          │
  │   调用 MEMORY_CLASSIFY_PROMPT_ZH                  │
  │   → [{content, memory_type, importance,           │
  │       valence, confidence}, ...]                  │
  │   写入 MySQL memories 表                          │
  │                                                   │
  │   Step 2: mem0 向量存储                           │
  │   对每条分类结果:                                  │
  │   mem0.add(content, infer=False,                  │
  │     metadata={memory_type, valence, importance})  │
  │   → ChromaDB (纯向量索引)                         │
  │                                                   │
  ├── MEM0_ENABLED=False ─────────────────────────────┤
  │   _extract_via_llm()                              │
  │   用 MEMORY_CLASSIFY_PROMPT_ZH 调 LLM             │
  │   解析 JSON → 写入 MySQL memories 表              │
  │   （降级路径，无向量存储）                          │
  │                                                   │
  ▼                                                   │
Step 3: 自我记忆提取                                  │
  _extract_self_memory(assistant_response)            │
  检测 "我喜欢/我觉得/我认为/我看过" 等模式            │
  匹配 → self_memories 表                             │
                                                       │
下次对话                                               │
  │                                                   │
  ▼ (Phase 3, cognitive.py)                           │
memory_manager.build_context()                        │
  │                                                   │
  ├── search_memories(query, top_k=10)                │
  │   ├── _search_via_mem0() ─────────────────────────┘
  │   │   mem0.search(query, filters={"user_id":"default"})
  │   │   返回: [{id, memory, score, metadata}, ...]
  │   │   转换: score → distance (1.0 - score)
  │   │
  │   └── _search_via_mysql()  # 降级: 返回高重要性记忆
  │
  ├── get_dormant_memories(query)
  │   查 MySQL 中 >30天未访问的记忆
  │   补充到召回结果中
  │
  ├── _build_layered_memory(recalled)
  │   按类型分流 → 分层结构
  │
  └── touch_memory(id)
      更新 last_accessed + access_count
```

---

## 4. 分层记忆注入

### 4.1 注入架构

```
召回的记忆 (10-15条)
  │
  ▼ _build_layered_memory()
  │
  ├── 置顶事实 (pinned facts)
  │   importance >= 0.8 且 memory_type=fact
  │   最多 2 条，强制包含（不参与排序竞争）
  │
  ├── 显式层 (facts + events)
  │   facts: 最多 5 条（含置顶）
  │   events: 全部（通常 <5 条）
  │   → "你记得的关于用户的事"
  │
  ├── 情感层 (episodic)
  │   最多 3 条，带 valence 情绪标注
  │   → "最近想起的画面"
  │
  └── 隐性行为层 (preference + procedural → behavior rules)
      最多 8 条，通过正则模板转化
      → "你自然形成的态度"
```

### 4.2 行为规则生成

preference 和 procedural 类型记忆通过**正则模板匹配**（非 LLM 调用）转化为行为指令：

```python
_BEHAVIOR_RULE_PATTERNS = [
    (r"不喜欢?[\s\S]*?(?:说教|教导|指导|指挥)", "避免说教语气，用平等的讨论方式"),
    (r"不喜欢?[\s\S]*?(?:太甜|太腻|亲昵|肉麻)", "不要过于甜腻或亲昵，保持正常的调侃距离"),
    (r"不喜欢?[\s\S]*?(?:啰嗦|冗长|废话)", "回复要简洁，不要铺垫太多"),
    (r"喜欢?[\s\S]*?(?:详细|深入|展开|多说)", "遇到用户感兴趣的话题可以多展开"),
    (r"偏好?[\s\S]*?(?:轻松|随便|日常)", "保持轻松的闲聊氛围，不要太严肃"),
    (r"习惯?[\s\S]*?(?:晚上|深夜|睡前)", "晚上/深夜的对话可以更放松一些"),
    (r"总是?[\s\S]*?(?:简短|一两句|短)", "用户偏好简短的交流，回复不要过长"),
    (r"经常?[\s\S]*?(?:主动|自己|先说)", "用户习惯主动发起话题，不需要你一直找话题"),
    (r"不喜欢?[\s\S]*?(?:被忽视|不被在意|不关心)", "要表现出你在关注用户说的话"),
]
```

匹配失败的 preference/procedural 记忆降级为 fact，放入显式层。

### 4.3 System Prompt 中的注入

```jinja
{% if layered_memory.facts or layered_memory.events %}
## 你记得的关于用户的事
这些是你确定知道的信息。不要猜测或编造其他内容——如果你不确定，直接说不知道。
- [fact memories...]
- [event memories...]（N天前）
{% endif %}

{% if layered_memory.episodic %}
## 最近想起的画面
- [episodic memories with valence...]
{% endif %}

{% if layered_memory.behavior_rules %}
## 你自然形成的态度
- [behavior rules from preference/procedural...]
{% endif %}
```

### 4.4 兴趣爱好动态化

YAML 中的 interests 不再作为唯一来源：

```jinja
{% if personality.interests %}
## 你的兴趣
- [YAML interests...]
{% elif self_memories %}
## 你的兴趣
- [self_memories content...]
{% endif %}
```

self_memories 为空时 fallback 到 YAML 基线。

### 4.5 反幻觉机制

1. **强约束**: "关于用户的任何事情，只能基于上面'你记得的事'中的内容。如果你不确定，直接说不知道，绝对不要编造或猜测用户的信息。"
2. **记忆锚定**: importance >= 0.8 的 fact 强制置顶，不参与排序竞争
3. **明确来源标记**: 事件带相对时间标注（"N天前"），增强可信度

---

## 5. 记忆提取与分类

### 5.1 LLM 分类 Prompt

```python
MEMORY_CLASSIFY_PROMPT_ZH = """分析以下对话，提取关于用户的重要信息并分类。

类型说明：
- fact: 用户的事实信息（姓名、身份、职业、位置等）
- preference: 用户明确表达的喜好、厌恶、习惯偏好
- event: 发生的具体事件（有时间节点）
- episodic: 带有强烈情绪色彩的经历或场景
- emotion: 持续的情感反应模式（反复出现的情绪触发）
- procedural: 行为互动模式（用户习惯的聊天方式、时间习惯等）

返回 JSON 数组: [{content, memory_type, importance, valence, confidence}]
"""
```

每条记忆包含:
- `content`: 记忆内容（简洁描述）
- `memory_type`: 7 种类型之一
- `importance`: 0.0-1.0 重要性
- `valence`: -1.0 到 1.0 情感极性
- `confidence`: 0.0-1.0 提取置信度

### 5.2 自我记忆提取

```python
_SELF_EXPRESSION_PATTERNS = [
    r"我喜欢[^\n。]*",
    r"我觉得[^\n。]*",
    r"我认为[^\n。]*",
    r"我看[过|完][^\n。]*",
    r"我最[^\n。]*",
    r"其实我[^\n。]*",
    r"我也[^\n。]*",
]
```

当 assistant_response 匹配到以上模式时，提取内容存入 `self_memories` 表。使用 LIKE 去重（前 20 字符匹配），避免重复存储。

---

## 6. 记忆衰减机制

### 6.1 指数衰减公式

```
new_importance = original_importance × 0.5^(effective_days / half_life)
```

参数:
- `half_life` = 90 天（`MEMORY_DECAY_HALF_LIFE_DAYS`）
- `effective_days` = `max(0, days_since_access - access_bonus)`
- `access_bonus` = `min(access_count × 5, 30)` 天

**含义**: 每被召回一次，相当于让这条记忆"年轻" 5 天（最多 30 天）。

### 6.2 触发时机

每 10 条消息（`msg_count % 10 == 0`），在 Phase 9 后台执行。每次最多处理 200 条记忆。

### 6.3 与 mem0 的同步

衰减更新 MySQL 后，同步调用 `mem0.update(memory_id, metadata={"importance": new_importance})`。

---

## 7. 记忆合并（Consolidation）

### 7.1 触发条件

- `MEMORY_CONSOLIDATION_ENABLED = True`
- 未合并记忆总数 ≥ `MEMORY_CONSOLIDATION_MIN_COUNT`（默认 20）
- 每 20 条消息执行一次

### 7.2 流程

```
for memory_type in [fact, preference, event, episodic, emotion, procedural]:
    1. 从 MySQL 取该类型下 15 条重要性最高的记忆
    2. 如果 < 3 条，跳过
    3. 调 LLM 合并（CONSOLIDATE_PROMPT_ZH）
    4. 对每条合并结果（source_ids >= 2）:
       - MySQL: 标记旧记忆 is_consolidated=1
       - MySQL: 插入新合并记忆
       - mem0: add(infer=False) 新记忆, delete() 所有旧记忆
```

---

## 8. 休眠记忆唤醒（Dormant Reactivation）

### 8.1 定义

一条记忆如果满足以下条件，被标记为"休眠":
- `last_accessed` 为 NULL，或者距离上次访问 > `MEMORY_DORMANT_DAYS`（默认 30 天）
- `importance > 0.2`

### 8.2 唤醒路径

**路径 A: 被动唤醒（build_context 中）**
- 在 `search_memories()` 召回之后，额外查询休眠记忆
- 取 top-2 重要性与当前查询相关的休眠记忆

**路径 B: 主动唤醒（proactive.py）**
- `check_memory_trigger()` 随机选一条休眠记忆（importance > 0.4）
- 作为触发原因生成主动消息

---

## 9. 情绪系统

### 9.1 用户情绪分析

每次收到用户消息，调用 LLM 分析 valence/arousal/label：

```
valence:  -1.0 ─────────── 0 ─────────── 1.0
           消极                           积极

arousal:   0.0 ─────────── 0.5 ─────────── 1.0
           平静                           激动

label: happy | sad | angry | anxious | calm | excited | tired | neutral
```

### 9.2 雨晴心情系统

独立于用户情绪的**三维心情状态**:

```
warmth:    温暖度 — 0=极冷  1=异常温暖
openness:  开放度 — 0=极度防御  1=完全敞开
energy:    活力度 — 0=沉默  1=活跃
```

更新方式 — EMA (指数移动平均)，含基线引力防止极端漂移。

**心情标签**:

| 标签 | 条件 | 行为表现 |
|------|------|---------|
| withdrawn | warmth<0.25, openness<0.30, energy<0.40 | 安静简短，偶尔刻薄 |
| guarded | 默认 | 正常状态 |
| relaxed | warmth>0.40 或 openness>0.45 | 放松，多说两句 |
| softened | warmth>0.60, openness>0.60 | 偶尔流露真诚 |
| vulnerable | warmth>0.80, openness>0.75 | 极罕见，防线崩塌 |

---

## 10. 用户偏好学习

每 5 轮对话分析最近 20 条消息，由 LLM 推断用户沟通偏好（response_length, topic_style, emotional_tone, humor_level, depth_style）。

置信度加权更新，只有 confidence >= 0.5 的偏好注入 system prompt。

---

## 11. 主动消息系统

触发器: 情绪跟踪 > 缺席关注 > 记忆唤醒 > 时段问候。节流机制: 最小间隔 3 小时，安静时段 0:00-7:00。

---

## 12. 数据库 Schema

### memories 表

```sql
CREATE TABLE memories (
    id              CHAR(32) PRIMARY KEY,
    content         TEXT NOT NULL,
    category        VARCHAR(64) DEFAULT 'general',  -- 旧分类字段（兼容保留）
    importance      FLOAT DEFAULT 0.5,
    original_importance FLOAT DEFAULT 0.5,
    source_conversation_id CHAR(32),
    source_message_id CHAR(32),
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_accessed   DATETIME,
    access_count    INT DEFAULT 0,
    is_consolidated TINYINT DEFAULT 0,
    consolidated_from VARCHAR(255),
    -- v3 新增字段
    memory_type     VARCHAR(32) DEFAULT 'fact',      -- 7种类型
    valence         FLOAT DEFAULT NULL,               -- 情感极性 -1.0~1.0
    arousal         FLOAT DEFAULT NULL,               -- 唤醒度 0.0~1.0
    emotion_label   VARCHAR(32) DEFAULT NULL,         -- 情绪标签
    confidence      FLOAT DEFAULT 0.5,                -- 提取置信度
    INDEX idx_memory_type (memory_type)
);
```

### self_memories 表 (v3 新增)

```sql
CREATE TABLE IF NOT EXISTS self_memories (
    id                          CHAR(32) PRIMARY KEY,
    content                     TEXT NOT NULL,
    memory_type                 VARCHAR(32) DEFAULT 'self_reflection',
    importance                  FLOAT DEFAULT 0.5,
    source_conversation_id      CHAR(32) DEFAULT NULL,
    created_at                  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    access_count                INT DEFAULT 0,
    INDEX idx_type_importance (memory_type, importance)
);
```

存储雨晴关于自身的认知（兴趣发展、经历积累），在 prompt 中注入到"你的兴趣"区段替代 YAML 写死的列表。

### 迁移映射

| 旧 category | 新 memory_type |
|------------|----------------|
| fact | fact |
| preference | preference |
| event | event |
| emotion_pattern | emotion |
| general | fact |

---

## 13. 配置参数参考

### 记忆系统

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `MEM0_ENABLED` | true | 是否启用 mem0（关闭则回退到 LLM 提取） |
| `MEM0_EMBEDDING_MODEL` | BAAI/bge-base-zh-v1.5 | 本地中文嵌入模型（768维） |
| `MEMORY_RECALL_COUNT` | 5 | 每次对话召回的记忆条数 |
| `AUTO_MEMORY_EXTRACTION` | true | 是否自动提取记忆 |
| `MEMORY_DECAY_ENABLED` | true | 是否启用衰减 |
| `MEMORY_DECAY_HALF_LIFE_DAYS` | 90 | 半衰期（天） |
| `MEMORY_CONSOLIDATION_ENABLED` | true | 是否启用合并 |
| `MEMORY_CONSOLIDATION_MIN_COUNT` | 20 | 触发合并的最低记忆数 |
| `MEMORY_DORMANT_DAYS` | 30 | 休眠阈值（天） |
| `MEMORY_FACT_TOP_K` | 6 | 显式注入的事实/事件条数 (v3) |
| `MEMORY_BEHAVIOR_RULES_MAX` | 8 | 行为规则最大条数 (v3) |
| `MEMORY_EPISODIC_MAX` | 3 | 情景记忆最大条数 (v3) |
| `SELF_MEMORY_ENABLED` | true | 是否启用自我记忆 (v3) |
| `MEMORY_CLASSIFY_ENABLED` | true | 是否启用记忆二次分类 (v3) |

### 情绪系统

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `YUQING_MOOD_EMA_ALPHA` | 0.15 | 心情 EMA 平滑系数 |
| `YUQING_MOOD_HOURLY_DECAY` | 0.02 | 心情每小时衰减率 |
| `YUQING_MOOD_BASELINE_WARMTH` | 0.40 | 温暖基线 |
| `YUQING_MOOD_BASELINE_OPENNESS` | 0.45 | 开放基线 |
| `YUQING_MOOD_BASELINE_ENERGY` | 0.45 | 活力基线 |

### 主动消息

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `PROACTIVE_ENABLED` | true | 是否启用主动消息 |
| `PROACTIVE_CHECK_INTERVAL_SECONDS` | 120 | 检查间隔（秒） |
| `PROACTIVE_ABSENCE_THRESHOLD_HOURS` | 4 | 缺席触发阈值（小时） |
| `PROACTIVE_EMOTION_FOLLOWUP_HOURS` | 3 | 情绪跟进间隔（小时） |
| `PROACTIVE_EMOTION_VALENCE_THRESHOLD` | -0.4 | 触发跟进的 valence 下限 |
| `PROACTIVE_MIN_HOURS_BETWEEN` | 3 | 主动消息最小间隔（小时） |

### 偏好学习

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `PREFERENCE_LEARNING_ENABLED` | true | 是否学习用户偏好 |
| `PREFERENCE_LEARN_INTERVAL` | 5 | 每 N 轮学习一次 |

---

## 14. 已知局限与改进方向

### 当前局限

1. **记忆衰减未参与检索排序**
   - mem0 search 返回结果基于语义 score，不考虑 MySQL 中的 importance
   - 改进: 在 `_search_via_mem0` 中将 importance 作为 rerank 因子

2. **合并的时机可能不理想**
   - 固定每 20 条消息检查一次
   - 改进: 基于新记忆与旧记忆的相似度实时触发合并

3. **情绪分析每次调用 LLM**
   - 对于日常闲聊（"嗯"、"好"），这是不必要的开销
   - 改进: 增加轻量级关键词预判

4. **行为规则模板覆盖有限**
   - 当前 9 条正则模式，无法覆盖所有偏好表述
   - 改进: 逐步扩充模板，或对未匹配的记忆用 LLM 生成规则

5. **单用户设计**
   - 当前 `user_id` 固定为 "default"
   - 改进: 多用户时用真实 user_id 隔离记忆

6. **self_memories 去重简单**
   - 使用前 20 字符 LIKE 匹配，可能误判
   - 改进: 使用 embedding 相似度去重

### 未来可探索的方向

- **forgetting 曲线**: 用 ZenBrain 的三时间尺度衰减函数替代简单指数衰减（睡眠清理 Phase 2 已部分实现 TAG 评分）
- **睡眠清理效果监控**: 添加清理前后的记忆质量指标（平均重要性、去重率、合并率）
- **跨对话推理**: 利用记忆进行跨越多个独立对话的推理
- **人格微调**: 基于积累的记忆和用户互动模式，动态微调人格参数
- **关系演进模型**: 随对话积累自然推进关系深度
- **对话摘要**: 长对话自动生成摘要，减少上下文窗口压力
