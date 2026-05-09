# YuQing 数据库技术文档

> 数据库: MySQL 9 | 字符集: utf8mb4 | 引擎: InnoDB
> 最后更新: 2026-05-09

---

## 1. ER 关系概览

```
conversations ──┬── 1:N ── messages
                ├── 1:N ── emotion_snapshots
                ├── 1:N ── yuqing_mood_log
                ├── 1:N ── proactive_messages
                └── 1:N ── memories (source_conversation_id)

messages ──────── 1:N ── memories (source_message_id)

memories ──────── 1:N ── memory_links (source_id / target_id)

单例表 (无外键):
  personality_config    (id=1, config JSON)
  app_settings          (key-value)

审计日志:
  personality_evolution (trigger_type, snapshot_before/after)

独立表:
  user_preferences      (自增 PK, preference_key UNIQUE)
  knowledge_items       (独立表，带 expires_at 时效性)
  memory_links          (source_id → target_id, link_type + strength)
```

---

## 2. 表结构

### 2.1 conversations — 对话列表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | CHAR(32) | PK | 32 位十六进制（secrets.token_hex） |
| `title` | VARCHAR(255) | NOT NULL, DEFAULT '' | 对话标题，前 50 字自动生成 |
| `created_at` | DATETIME | NOT NULL, DEFAULT NOW | 创建时间 |
| `updated_at` | DATETIME | NOT NULL, ON UPDATE NOW | 最后消息时间（自动更新） |
| `is_archived` | TINYINT | NOT NULL, DEFAULT 0 | 是否归档（预留） |

**索引**: 仅 PK。

**级联删除**: 删除对话时级联删除 messages 和 proactive_messages；memories/emotion_snapshots/yuqing_mood_log 置 NULL。

```sql
CREATE TABLE conversations (
    id CHAR(32) PRIMARY KEY,
    title VARCHAR(255) NOT NULL DEFAULT '',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    is_archived TINYINT NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

---

### 2.2 messages — 消息记录

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | CHAR(32) | PK | 32 位十六进制 |
| `conversation_id` | CHAR(32) | FK → conversations, ON DELETE CASCADE | 所属对话 |
| `role` | ENUM('user','assistant','system') | NOT NULL | 消息角色 |
| `content` | TEXT | NOT NULL | 消息内容（text 类型为正文，sticker 类型为 sticker path） |
| `content_type` | VARCHAR(16) | NOT NULL, DEFAULT 'text' | 内容类型：`text`（默认）或 `sticker`（表情包） |
| `valence` | FLOAT | NULL | 用户消息情绪极性 (-1.0 ~ +1.0) |
| `arousal` | FLOAT | NULL | 用户消息唤醒度 (0.0 ~ 1.0) |
| `prompt_tokens` | INT | DEFAULT 0 | prompt 消耗 token 数 |
| `completion_tokens` | INT | DEFAULT 0 | 补全消耗 token 数 |
| `model_used` | VARCHAR(128) | DEFAULT '' | 使用的模型名 |
| `created_at` | DATETIME | NOT NULL, DEFAULT NOW | 发送时间 |

**索引**: `idx_conv_time (conversation_id, created_at)` — 按对话+时间查询上下文。

**级联删除**: 删除对话时级联删除所有消息。

```sql
CREATE TABLE messages (
    id CHAR(32) PRIMARY KEY,
    conversation_id CHAR(32) NOT NULL,
    role ENUM('user', 'assistant', 'system') NOT NULL,
    content TEXT NOT NULL,
    content_type VARCHAR(16) NOT NULL DEFAULT 'text',  -- 'text' | 'sticker'
    valence FLOAT DEFAULT NULL,
    arousal FLOAT DEFAULT NULL,
    prompt_tokens INT DEFAULT 0,
    completion_tokens INT DEFAULT 0,
    model_used VARCHAR(128) DEFAULT '',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,
    INDEX idx_conv_time (conversation_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

---

### 2.3 memories — 长期记忆

核心表，存储雨晴关于用户的所有长期记忆。与 mem0/ChromaDB 双写（mem0 负责向量检索，MySQL 负责 CRUD + 衰减计算）。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | CHAR(32) | PK | 优先用 mem0 生成的 ID，否则自生成 |
| `content` | TEXT | NOT NULL | 记忆内容 |
| `category` | VARCHAR(64) | DEFAULT 'general' | 旧分类字段（兼容保留） |
| `importance` | FLOAT | DEFAULT 0.5 | 当前重要性（经衰减计算后） |
| `original_importance` | FLOAT | DEFAULT 0.5 | 原始重要性（衰减基准，不被修改） |
| `source_conversation_id` | CHAR(32) | FK → conversations, ON DELETE SET NULL | 来源对话 |
| `source_message_id` | CHAR(32) | FK → messages, ON DELETE SET NULL | 来源消息 |
| `created_at` | DATETIME | NOT NULL, DEFAULT NOW | 创建时间 |
| `last_accessed` | DATETIME | NULL | 上次被召回时间（用于衰减计算） |
| `access_count` | INT | DEFAULT 0 | 被召回次数（每次 +5 天 access_bonus） |
| `is_consolidated` | TINYINT | NOT NULL, DEFAULT 0 | 是否已被合并（1=已合并，不参与召回） |
| `consolidated_from` | VARCHAR(255) | NULL | 合并来源 ID 列表（JSON 数组） |
| `memory_type` | VARCHAR(32) | DEFAULT 'fact' | 记忆类型（v3 新增） |
| `valence` | FLOAT | NULL | 提取时的情绪极性（v3 新增） |
| `arousal` | FLOAT | NULL | 提取时的唤醒度（v3 新增） |
| `emotion_label` | VARCHAR(32) | NULL | 提取时的情绪标签（v3 新增） |
| `confidence` | FLOAT | DEFAULT 0.5 | 提取置信度（v3 新增） |

**索引**:
- `idx_category_importance (category, importance)` — 按类型+重要性查询
- `idx_last_accessed (last_accessed)` — 衰减计算按时间排序
- `idx_memory_type (memory_type)` — v3 分层召回按类型筛选

**memory_type 取值**:

| 值 | 说明 | 注入方式 |
|----|------|---------|
| `fact` | 用户事实信息 | 显式原文（"你记得的事"） |
| `event` | 重要的生活事件 | 显式原文（带时间） |
| `episodic` | 带情绪色彩的情景 | 情感层（"最近想起的画面"） |
| `emotion` | 情绪反应模式 | 影响 mood 系统 |
| `preference` | 用户偏好 | 转化为行为规则 |
| `procedural` | 行为互动模式 | 转化为行为规则 |
| `self_reflection` | 雨晴的内心独白 | 动态 prompt「你最近的内心活动」+ 驱动 mood 更新 |

**category → memory_type 迁移映射**:

| 旧 category | 新 memory_type |
|------------|----------------|
| `fact` | `fact` |
| `preference` | `preference` |
| `event` | `event` |
| `emotion_pattern` | `emotion` |
| `general` | `fact` |

```sql
CREATE TABLE memories (
    id CHAR(32) PRIMARY KEY,
    content TEXT NOT NULL,
    category VARCHAR(64) DEFAULT 'general',
    importance FLOAT DEFAULT 0.5,
    original_importance FLOAT DEFAULT 0.5,
    source_conversation_id CHAR(32) DEFAULT NULL,
    source_message_id CHAR(32) DEFAULT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_accessed DATETIME DEFAULT NULL,
    access_count INT DEFAULT 0,
    is_consolidated TINYINT NOT NULL DEFAULT 0,
    consolidated_from VARCHAR(255) DEFAULT NULL,
    FOREIGN KEY (source_conversation_id) REFERENCES conversations(id) ON DELETE SET NULL,
    FOREIGN KEY (source_message_id) REFERENCES messages(id) ON DELETE SET NULL,
    INDEX idx_category_importance (category, importance),
    INDEX idx_last_accessed (last_accessed)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- v3 migration columns
ALTER TABLE memories ADD COLUMN memory_type VARCHAR(32) DEFAULT 'fact';
ALTER TABLE memories ADD COLUMN valence FLOAT DEFAULT NULL;
ALTER TABLE memories ADD COLUMN arousal FLOAT DEFAULT NULL;
ALTER TABLE memories ADD COLUMN emotion_label VARCHAR(32) DEFAULT NULL;
ALTER TABLE memories ADD COLUMN confidence FLOAT DEFAULT 0.5;
CREATE INDEX idx_memory_type ON memories (memory_type);
```

---

### 2.4 self_memories — 雨晴的自我记忆

存储雨晴关于自身的认知（兴趣、经历、观点、习惯），在 system prompt 中注入到"你记得的自己"区段，动态替代 YAML 中写死的 interests 列表。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | CHAR(32) | PK | 自生成 ID |
| `content` | TEXT | NOT NULL | 自我认知内容（如"我喜欢看老番"） |
| `memory_type` | VARCHAR(32) | DEFAULT 'self_reflection' | 细分类别：self_interest / self_experience / self_opinion / self_habit |
| `importance` | FLOAT | DEFAULT 0.5 | 重要性（相似记忆强化时会 +0.05） |
| `source_conversation_id` | CHAR(32) | NULL | 来源对话 |
| `created_at` | DATETIME | NOT NULL, DEFAULT NOW | 创建时间 |
| `access_count` | INT | DEFAULT 0 | 被引用次数 |
| `is_consolidated` | TINYINT | NOT NULL, DEFAULT 0 | 是否已被合并（1=是，合并后的记忆 is_consolidated=0） |

**索引**: `idx_type_importance (memory_type, importance)`、`idx_consolidated (is_consolidated)`

**提取逻辑**: 搭便车用户记忆提取的 LLM 调用，一次 API 调用同时返回 `user_memories` 和 `self_memories`。提取后通过本地 bge embedding 语义去重（cosine > 0.85 跳过，0.6-0.85 强化已有记忆）。

**合并逻辑**: 每 20 轮对话触发。对未合并的记忆做 embedding 聚类（cosine > 0.75 归一组），组内 ≥ 3 条时调用 LLM 合并为精炼总结，原始记忆标记 `is_consolidated=1`。

```sql
CREATE TABLE IF NOT EXISTS self_memories (
    id CHAR(32) PRIMARY KEY,
    content TEXT NOT NULL,
    memory_type VARCHAR(32) DEFAULT 'self_reflection',
    importance FLOAT DEFAULT 0.5,
    source_conversation_id CHAR(32) DEFAULT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    access_count INT DEFAULT 0,
    is_consolidated TINYINT NOT NULL DEFAULT 0,
    INDEX idx_type_importance (memory_type, importance),
    INDEX idx_consolidated (is_consolidated)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

---

### 2.5 emotion_snapshots — 用户情绪快照

每条用户消息分析后存储情绪快照，用于情绪趋势追踪和主动消息触发。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | CHAR(32) | PK | 自生成 ID |
| `conversation_id` | CHAR(32) | FK → conversations, ON DELETE SET NULL | 所属对话 |
| `valence` | FLOAT | NOT NULL | 情绪极性 (-1.0 ~ +1.0) |
| `arousal` | FLOAT | NOT NULL | 唤醒度 (0.0 ~ 1.0) |
| `dominant_emotion` | VARCHAR(64) | NULL | 情绪标签（happy/sad/angry/anxious/calm/excited/tired/neutral） |
| `trigger_summary` | TEXT | NULL | 触发摘要（用户消息前 100 字） |
| `created_at` | DATETIME | NOT NULL, DEFAULT NOW | 分析时间 |

**索引**: `idx_emo_time (created_at)` — 按时间查询情绪历史。

```sql
CREATE TABLE IF NOT EXISTS emotion_snapshots (
    id CHAR(32) PRIMARY KEY,
    conversation_id CHAR(32) DEFAULT NULL,
    valence FLOAT NOT NULL,
    arousal FLOAT NOT NULL,
    dominant_emotion VARCHAR(64) DEFAULT NULL,
    trigger_summary TEXT DEFAULT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE SET NULL,
    INDEX idx_emo_time (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

---

### 2.6 yuqing_mood — 雨晴心情当前值（单例）

存储雨晴心情的三维状态机当前值，`id=1` 单例行（CHECK 约束强制）。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INT | PK, CHECK(id=1) | 强制单例 |
| `energy` | FLOAT | NOT NULL, DEFAULT 0.5 | 活力度（0=安静 1=活跃） |
| `warmth` | FLOAT | NOT NULL, DEFAULT 0.3 | 温暖度（0=冷漠 1=温暖） |
| `patience` | FLOAT | NOT NULL, DEFAULT 0.5 | 耐心值（旧维度，v2 遗留） |
| `current_label` | VARCHAR(32) | NOT NULL, DEFAULT 'neutral' | 当前心情标签 |
| `last_updated` | DATETIME | NOT NULL, ON UPDATE NOW | 最后更新时间 |
| `interaction_count` | INT | NOT NULL, DEFAULT 0 | 累计交互次数 |

> **注意**: 此表结构为 v2 遗留设计，包含 `patience` 字段但当前代码已不使用。v3 的心情系统使用 `warmth/openness/energy` 三维，存储在 `yuqing_mood_log` 中。此表仅保留 `warmth` 和 `energy` 字段被读取，`openness` 维度由 `yuqing_mood_tracker` 模块在内存中维护。

```sql
CREATE TABLE yuqing_mood (
    id INT PRIMARY KEY CHECK (id = 1),
    energy FLOAT NOT NULL DEFAULT 0.5,
    warmth FLOAT NOT NULL DEFAULT 0.3,
    patience FLOAT NOT NULL DEFAULT 0.5,
    current_label VARCHAR(32) NOT NULL DEFAULT 'neutral',
    last_updated DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    interaction_count INT NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

---

### 2.7 yuqing_mood_log — 雨晴心情变化日志

记录每次心情更新的历史，用于心情趋势追踪和调试。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | CHAR(32) | PK | 自生成 ID |
| `conversation_id` | CHAR(32) | FK → conversations, ON DELETE SET NULL | 所属对话 |
| `warmth` | FLOAT | NOT NULL | 温暖度快照 |
| `openness` | FLOAT | NOT NULL | 开放度快照 |
| `energy` | FLOAT | NOT NULL | 活力度快照 |
| `mood_label` | VARCHAR(32) | NOT NULL | 心情标签（guarded/withdrawn/relaxed/softened/vulnerable） |
| `trigger_type` | VARCHAR(32) | NULL | 触发类型（conversation/absence_decay/return_bump/monologue） |
| `trigger_summary` | TEXT | NULL | 触发摘要（monologue 类型时为独白内容前 200 字） |
| `created_at` | DATETIME | NOT NULL, DEFAULT NOW | 记录时间 |

**索引**: `idx_mood_time (created_at)` — 按时间查询心情变化历史。

```sql
CREATE TABLE IF NOT EXISTS yuqing_mood_log (
    id CHAR(32) PRIMARY KEY,
    conversation_id CHAR(32) DEFAULT NULL,
    warmth FLOAT NOT NULL,
    openness FLOAT NOT NULL,
    energy FLOAT NOT NULL,
    mood_label VARCHAR(32) NOT NULL,
    trigger_type VARCHAR(32) DEFAULT NULL,
    trigger_summary TEXT DEFAULT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE SET NULL,
    INDEX idx_mood_time (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

---

### 2.8 proactive_messages — 主动消息记录

记录雨晴主动发送的消息及其触发原因。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | CHAR(32) | PK | 自生成 ID |
| `conversation_id` | CHAR(32) | FK → conversations, ON DELETE CASCADE | 目标对话 |
| `trigger_type` | VARCHAR(32) | NOT NULL | 触发类型 |
| `message_content` | TEXT | NOT NULL | 主动消息内容 |
| `trigger_detail` | TEXT | NULL | 触发详情 |
| `created_at` | DATETIME | NOT NULL, DEFAULT NOW | 发送时间 |

**trigger_type 取值**: `emotion_followup` / `absence` / `memory` / `time_of_day`

**索引**: `idx_proactive_time (conversation_id, created_at)` — 按对话+时间查询。

**级联删除**: 删除对话时级联删除主动消息记录。

```sql
CREATE TABLE IF NOT EXISTS proactive_messages (
    id CHAR(32) PRIMARY KEY,
    conversation_id CHAR(32) NOT NULL,
    trigger_type VARCHAR(32) NOT NULL,
    message_content TEXT NOT NULL,
    trigger_detail TEXT DEFAULT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,
    INDEX idx_proactive_time (conversation_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

---

### 2.9 user_preferences — 用户偏好

存储从对话中学习到的用户沟通偏好。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INT | PK, AUTO_INCREMENT | 自增 ID |
| `preference_key` | VARCHAR(64) | NOT NULL, UNIQUE | 偏好维度名 |
| `preference_value` | VARCHAR(255) | NOT NULL, DEFAULT '' | 偏好值 |
| `confidence` | FLOAT | NOT NULL, DEFAULT 0 | 置信度（0~1，>= 0.5 才注入 prompt） |
| `sample_count` | INT | NOT NULL, DEFAULT 0 | 学习样本数 |
| `created_at` | DATETIME | NOT NULL, DEFAULT NOW | 首次学习时间 |
| `updated_at` | DATETIME | NOT NULL, ON UPDATE NOW | 最后更新时间 |

**preference_key 取值**: `response_length` / `topic_style` / `emotional_tone` / `humor_level` / `depth_style`

**置信度更新公式**: `new = old × (1 - weight) + evidence × weight`，其中 `weight = min(0.3, 1.0 / (count + 2))`

```sql
CREATE TABLE IF NOT EXISTS user_preferences (
    id INT AUTO_INCREMENT PRIMARY KEY,
    preference_key VARCHAR(64) NOT NULL UNIQUE,
    preference_value VARCHAR(255) NOT NULL DEFAULT '',
    confidence FLOAT NOT NULL DEFAULT 0.0,
    sample_count INT NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

---

### 2.10 personality_config — 人格配置（单例）

存储运行时人格覆盖配置，与 YAML 默认配置深度合并。`id=1` 单例行。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INT | PK, CHECK(id=1) | 强制单例 |
| `config` | JSON | NOT NULL | 人格覆盖配置（深度合并到 YAML 默认值） |
| `updated_at` | DATETIME | NOT NULL, ON UPDATE NOW | 最后更新时间 |

**config JSON 结构示例**:
```json
{
    "traits": {"warmth": 0.6},
    "rules": ["新的约束规则"],
    "interests": ["新的兴趣"]
}
```

**合并逻辑**: `personality_engine._deep_merge(default_yaml, db_override)` — override 中的值覆盖 default，嵌套字典递归合并。

```sql
CREATE TABLE personality_config (
    id INT PRIMARY KEY CHECK (id = 1),
    config JSON NOT NULL,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

---

### 2.11 app_settings — 应用设置（KV）

通用键值对存储，用于保存应用级设置。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `key` | VARCHAR(128) | PK | 设置键 |
| `value` | TEXT | NOT NULL | 设置值 |
| `updated_at` | DATETIME | NOT NULL, ON UPDATE NOW | 最后更新时间 |

```sql
CREATE TABLE IF NOT EXISTS app_settings (
    `key` VARCHAR(128) PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

---

### 2.12 knowledge_items — 信息检索知识条目

存储雨晴通过 Tavily API 主动/被动检索到的知识，带时效性。7 天后自动过期，不再注入 system prompt。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | CHAR(32) | PK | 自生成 ID |
| `topic` | VARCHAR(128) | NOT NULL | 话题分类（"ACG"、"AI技术"、"音乐"等） |
| `content` | TEXT | NOT NULL | LLM 总结后的内容（2-3 句话） |
| `source_url` | VARCHAR(512) | NULL | 原始来源链接 |
| `retrieved_at` | DATETIME | NOT NULL, DEFAULT NOW | 检索时间 |
| `expires_at` | DATETIME | NOT NULL | 过期时间（retrieved_at + N 天） |
| `is_valid` | TINYINT | NOT NULL, DEFAULT 1 | 是否有效（可手动失效） |
| `source_type` | ENUM('proactive','reactive') | DEFAULT 'proactive' | proactive=主动定时检索，reactive=对话中触发 |

**索引**: `idx_topic_valid (topic, is_valid)`、`idx_expires (expires_at)`

**查询方式**: `WHERE is_valid = 1 AND expires_at > NOW() ORDER BY retrieved_at DESC`

```sql
CREATE TABLE IF NOT EXISTS knowledge_items (
    id CHAR(32) PRIMARY KEY,
    topic VARCHAR(128) NOT NULL,
    content TEXT NOT NULL,
    source_url VARCHAR(512) DEFAULT NULL,
    retrieved_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME NOT NULL,
    is_valid TINYINT NOT NULL DEFAULT 1,
    source_type ENUM('proactive', 'reactive') DEFAULT 'proactive',
    INDEX idx_topic_valid (topic, is_valid),
    INDEX idx_expires (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

---

## 3. 外键关系

```
messages.conversation_id       → conversations.id       ON DELETE CASCADE
memories.source_conversation_id → conversations.id       ON DELETE SET NULL
memories.source_message_id      → messages.id            ON DELETE SET NULL
emotion_snapshots.conversation_id → conversations.id     ON DELETE SET NULL
yuqing_mood_log.conversation_id   → conversations.id     ON DELETE SET NULL
proactive_messages.conversation_id → conversations.id    ON DELETE CASCADE
```

**设计决策**:
- messages 和 proactive_messages: CASCADE — 删除对话时彻底清理
- memories / emotion_snapshots / yuqing_mood_log: SET NULL — 记忆和情绪数据保留，对话删除后记忆不丢失

---

## 4. 索引汇总

| 表 | 索引名 | 字段 | 用途 |
|----|--------|------|------|
| messages | idx_conv_time | (conversation_id, created_at) | 加载对话上下文（DESC + LIMIT） |
| memories | idx_category_importance | (category, importance) | 按类型+重要性查询 |
| memories | idx_last_accessed | (last_accessed) | 衰减计算排序 |
| memories | idx_memory_type | (memory_type) | v3 分层召回 |
| self_memories | idx_type_importance | (memory_type, importance) | 按重要性排序自我记忆 |
| emotion_snapshots | idx_emo_time | (created_at) | 情绪历史查询 |
| yuqing_mood_log | idx_mood_time | (created_at) | 心情趋势查询 |
| proactive_messages | idx_proactive_time | (conversation_id, created_at) | 主动消息历史查询 |
| user_preferences | preference_key (UNIQUE) | (preference_key) | 保证每个维度唯一 |
| knowledge_items | idx_topic_valid | (topic, is_valid) | 按话题查询有效知识 |
| knowledge_items | idx_expires | (expires_at) | 过期知识过滤 |

---

## 5. 后端连接架构

### 5.1 连接池

使用 `aiomysql` 异步连接池，应用生命周期内全局单例。

```python
# app/db/database.py

_pool: Optional[aiomysql.Pool] = None

async def init_pool() -> aiomysql.Pool:
    global _pool
    _pool = await aiomysql.create_pool(
        host=settings.MYSQL_HOST,       # 127.0.0.1
        port=settings.MYSQL_PORT,       # 3306
        user=settings.MYSQL_USER,       # root
        password=settings.MYSQL_PASSWORD,
        db=settings.MYSQL_DATABASE,     # yuqing
        charset="utf8mb4",
        autocommit=True,                # 自动提交，不手动 commit
        minsize=2,                      # 最小空闲连接
        maxsize=10,                     # 最大连接数
    )

async def get_pool() -> aiomysql.Pool:
    """延迟初始化：首次调用时创建池，后续返回单例。"""
    if _pool is None:
        return await init_pool()
    return _pool

async def close_pool():
    """应用关闭时释放连接池。"""
    global _pool
    if _pool is not None:
        _pool.close()
        await _pool.wait_closed()
        _pool = None
```

**关键设计**:
- `autocommit=True` — 所有 SQL 执行后立即提交，不使用事务。原因：认知管线各阶段（情绪分析→记忆召回→LLM生成→记忆提取）是独立操作，不需要跨阶段事务。
- `minsize=2, maxsize=10` — 适合单用户场景。大量并发时连接不够会导致等待，但对个人 AI 伙伴足够。
- 延迟初始化（`get_pool()`）— 模块导入时不创建连接，首次使用时才初始化。避免测试和工具脚本导入时触发连接。

### 5.2 应用生命周期

```python
# app/main.py

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动
    await init_db()           # 建表 + 迁移
    init_mem0()               # 初始化 mem0 客户端（同步）
    await sync_memories_to_mem0()  # 旧记忆同步到 mem0 向量库
    task = asyncio.create_task(proactive_background_task())  # 启动主动消息后台任务
    info_task = asyncio.create_task(info_retrieval_background_task())  # 启动信息检索后台任务

    yield  # 应用运行中

    # 关闭
    task.cancel()
    info_task.cancel()
    await close_pool()        # 释放连接池
```

**启动顺序**:
1. `init_db()` — 创建连接池 → 建表 → 执行迁移 → 回填数据
2. `init_mem0()` — 初始化 mem0 Memory 客户端（设置 `LITELLM_API_BASE` 环境变量 → `Memory.from_config()`）
3. `sync_memories_to_mem0()` — 查询 MySQL 中 `is_consolidated=0` 的记忆，逐条 `mem0.add(infer=False)` 同步到 ChromaDB（跳过已存在的）
4. 启动 `proactive_background_task()` — 每 120s 检查主动消息触发条件
5. 启动 `info_retrieval_background_task()` — 启动 5 分钟后首次检索，之后每 8 小时按兴趣搜索新闻

**关闭顺序**: 取消所有后台任务 → 释放连接池。

### 5.3 连接使用模式

全项目统一使用 `pool.acquire()` 上下文管理器获取连接：

```python
# 标准模式：获取池 → 获取连接 → 执行 SQL → 释放连接
pool = await get_pool()
async with pool.acquire() as conn:
    async with conn.cursor() as cur:
        await cur.execute("SELECT ...", (param1, param2))
        rows = await cur.fetchall()
```

**两种游标类型**:

```python
# 默认游标：返回 tuple
async with conn.cursor() as cur:
    await cur.execute("SELECT COUNT(*) FROM messages")
    row = await cur.fetchone()  # (count,)
    count = row[0]

# DictCursor：返回 dict（需要按字段名访问时）
from aiomysql import DictCursor
async with conn.cursor(aiomysql.DictCursor) as cur:
    await cur.execute("SELECT role, content FROM messages WHERE conversation_id = %s", (cid,))
    rows = await cur.fetchall()  # [{'role': 'user', 'content': '...'}, ...]
```

**使用场景统计**:

| 使用位置 | 游标类型 | 典型操作 |
|---------|---------|---------|
| `cognitive.py` | 默认 + DictCursor | 消息存储(COUNT)、上下文加载(DictCursor) |
| `memory.py` | DictCursor | 记忆召回/衰减/合并/查询 |
| `emotion.py` | 默认 + DictCursor | 情绪快照存储/查询 |
| `mood.py` | 默认 | 心情读取/更新 |
| `preferences.py` | DictCursor | 偏好读写 |
| `personality.py` | 默认 | 人格配置读写 |
| `conversations.py` | DictCursor | 对话 CRUD |
| `health.py` | 默认 | 健康检查(COUNT) |
| `database.py init_db` | 默认 | 建表 + 迁移 |

### 5.4 参数化查询

所有查询均使用 `%s` 占位符 + 参数元组，防止 SQL 注入：

```python
# 正确
await cur.execute("SELECT * FROM messages WHERE conversation_id = %s", (cid,))

# 错误（SQL 注入风险）
await cur.execute(f"SELECT * FROM messages WHERE conversation_id = '{cid}'")
```

唯一的动态 SQL 是 `init_db()` 中的迁移逻辑（`ALTER TABLE` 拼接列定义），输入来源是硬编码的迁移列表，不接受外部输入，因此安全。

### 5.5 ID 生成

```python
def _generate_id() -> str:
    import secrets
    return secrets.token_hex(16)  # 32 字符十六进制字符串
```

使用 `secrets.token_hex` 而非 UUID：
- 格式：`a1b2c3d4e5f6...`（32 字符，刚好符合 CHAR(32)）
- mem0 返回的 ID 也是类似格式，保持一致
- 比 UUID 更短，存储更紧凑

### 5.6 mem0 与 MySQL 的数据同步

mem0 和 MySQL 双写，各有职责：

```
写入路径:
  LLM 分类 → MySQL (结构化存储，全 CRUD)
           → mem0.add(infer=False) → ChromaDB (纯向量索引)

读取路径:
  mem0.search(query) → 语义匹配结果 → 按类型分流注入
  MySQL (touch/update/delete) → CRUD 操作 + 衰减计算

同步路径 (启动时):
  sync_memories_to_mem0(): MySQL → mem0 (迁移旧记忆)
  sync_memories_to_mem0(): 跳过 mem0 中已存在的 (幂等)

删除路径:
  delete_memory(id) → MySQL DELETE + mem0.delete(id)
```

mem0 的 `api_base` 通过环境变量传递（mem0 的 `BaseLlmConfig` 不接受 `api_base` 参数）：
```python
os.environ["LITELLM_API_BASE"] = settings.LITELLM_API_BASE
os.environ["OPENAI_API_BASE"] = settings.LITELLM_API_BASE
```

### 5.7 配置来源

```python
# app/config.py — pydantic-settings 自动从 .env 加载

class Settings(BaseSettings):
    MYSQL_HOST: str = "127.0.0.1"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "root"
    MYSQL_PASSWORD: str = ""
    MYSQL_DATABASE: str = "yuqing"

    class Config:
        env_file = str(_PROJECT_ROOT / ".env")  # 项目根目录的 .env
```

`.env` 文件位于项目根目录（`backend/` 的父级），`pydantic-settings` 自动读取。

### 5.8 连接池配置参考

| 参数 | 当前值 | 说明 |
|------|--------|------|
| `autocommit` | True | 自动提交，无需手动 commit/rollback |
| `minsize` | 2 | 最小空闲连接数 |
| `maxsize` | 10 | 最大连接数 |
| `charset` | utf8mb4 | 支持 emoji 和中文 |
| `pool_recycle` | 默认(-1) | 连接回收时间（未设置，使用 aiomysql 默认值） |

> 如果遇到 "MySQL server has gone away" 错误，可以设置 `pool_recycle=3600` 让连接每小时回收一次。

---

## 6. 数据库初始化

应用启动时 `init_db()` 自动执行:

1. 调用 `init_pool()` 创建连接池
2. 创建所有表（`CREATE TABLE IF NOT EXISTS`）
3. 插入 personality_config 单例行（`INSERT IGNORE`）
4. 执行迁移（`DESCRIBE` 检查列是否存在，不存在则 `ALTER TABLE ADD COLUMN`）
5. 回填 `original_importance`（对已有记忆）
6. 回填 `memory_type`（从 category 映射）
7. 创建缺失索引（忽略已存在的错误）

迁移策略: **向前兼容** — 不删除列/数据，只添加新列并回填。

---

## 7. 常用查询示例

```sql
-- 查看所有记忆及类型分布
SELECT memory_type, COUNT(*) AS cnt, AVG(importance) AS avg_imp
FROM memories WHERE is_consolidated = 0
GROUP BY memory_type;

-- 查看高重要性记忆
SELECT memory_type, content, importance, valence, confidence
FROM memories WHERE importance >= 0.7 AND is_consolidated = 0
ORDER BY importance DESC;

-- 查看雨晴心情趋势
SELECT warmth, openness, energy, mood_label, created_at
FROM yuqing_mood_log ORDER BY created_at DESC LIMIT 20;

-- 查看用户情绪趋势
SELECT dominant_emotion, AVG(valence) AS avg_valence, created_at
FROM emotion_snapshots GROUP BY DATE(created_at), dominant_emotion
ORDER BY created_at DESC LIMIT 30;

-- 查看主动消息记录
SELECT trigger_type, message_content, created_at
FROM proactive_messages ORDER BY created_at DESC;

-- 查看学习到的用户偏好
SELECT preference_key, preference_value, confidence, sample_count
FROM user_preferences ORDER BY confidence DESC;

-- 查看需要衰减的记忆（30天未访问）
SELECT id, content, importance, last_accessed, access_count
FROM memories
WHERE (last_accessed IS NULL OR last_accessed < NOW() - INTERVAL 30 DAY)
  AND importance > 0.2
  AND is_consolidated = 0
ORDER BY last_accessed ASC;

-- 搜索对话内消息（前端搜索功能使用）
SELECT id, role, content, created_at
FROM messages
WHERE conversation_id = ?
  AND content LIKE ?
ORDER BY created_at DESC LIMIT ? OFFSET ?;

-- 查看雨晴的自我记忆分布
SELECT memory_type, COUNT(*) AS cnt, AVG(importance) AS avg_imp
FROM self_memories WHERE is_consolidated = 0
GROUP BY memory_type;

-- 查看已被合并的自我记忆（原始条目）
SELECT memory_type, content, importance, created_at
FROM self_memories WHERE is_consolidated = 1
ORDER BY created_at DESC LIMIT 20;

-- 查看当前有效的知识条目（未过期）
SELECT topic, content, source_type, retrieved_at, expires_at
FROM knowledge_items
WHERE is_valid = 1 AND expires_at > NOW()
ORDER BY retrieved_at DESC;

-- 查看已过期的知识条目
SELECT topic, content, source_type, retrieved_at, expires_at
FROM knowledge_items
WHERE expires_at <= NOW()
ORDER BY expires_at DESC;

-- 查看雨晴当前的自我叙事
SELECT `key`, value FROM app_settings WHERE `key` = 'self_narrative';

-- 查看记忆纠正记录（被标记失效的记忆）
SELECT id, content, memory_type, is_invalid
FROM memories WHERE is_invalid = 1
ORDER BY created_at DESC LIMIT 10;
```
