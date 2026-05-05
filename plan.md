# YuQing 语晴 — 开发计划

> 最后更新：2026-05-04

---

## 已完成

### 核心框架
- [x] FastAPI + React + TypeScript + MySQL + ChromaDB 全栈搭建
- [x] litellm 多模型支持（DeepSeek / GLM / Claude / OpenAI）
- [x] 中英文双语 UI（i18next）
- [x] SSE 流式消息推送（行缓冲机制防止 chunk 边界分割丢失事件）
- [x] 微信风格单会话聊天界面
- [x] 消息冷却合并发送（20 秒窗口）
- [x] 对话列表侧栏
- [x] 历史消息搜索（SearchPanel + 后端搜索 API，关键词高亮 + 滚动定位）
- [x] 实时流式显示（LLM 回复逐字渲染，无需等待完成）
- [x] 消息打包 UX 优化：打包发送后才显示输入指示器，避免误触

### 认知处理器（CognitiveProcessor）
- [x] 10 阶段流水线：情绪分析 → 心情更新 → 记忆召回 → 被动信息检索 → 人格 prompt → 消息存储 → 上下文加载 → LLM 流式生成 → 消息存储 → 后台任务
- [x] SSE 事件类型：emotion / mood / token / memory_extracted / knowledge / proactive / done / error
- [x] 用户消息按行拆分存储，合并文本用于记忆提取
- [x] 硬格式约束禁止 "..." 输出 + 前端三层清理（prompt 约束 / EMPTY_RESPONSES 过滤 / done 事件段落清洗）

### 记忆系统（MemoryManager）
- [x] 多层记忆架构：工作记忆（20 条上下文）+ 长期记忆（MySQL + BGE 语义搜索）
- [x] 7 种用户记忆类型：fact / event / episodic / emotion / preference / procedural
- [x] 4 种自我记忆类型：self_interest / self_experience / self_opinion / self_habit
- [x] 分层注入机制：显式层（fact+event）→ 情感层（episodic）→ 行为层（preference/procedural）
- [x] mem0 v2 集成（后移除，改为本地 BGE + MySQL）
- [x] 本地中文嵌入模型 BAAI/bge-small-zh-v1.5（512 维，无需额外 API）
- [x] 自动记忆提取：LLM 分类（7 种类型 + valence + confidence）→ MySQL + ChromaDB
- [x] 语义召回：BGE embedding cosine similarity 搜索（200 候选 → 批量 encode → 排序）
- [x] Pinned facts 保障：importance >= 0.8 的记忆强制注入，不参与排序竞争
- [x] 记忆衰减：90 天半衰期，未被访问的记忆重要性逐渐降低
- [x] 记忆巩固：每 20 轮合并相关记忆，压缩冗余
- [x] 休眠记忆唤醒：30 天未召回的语义相关记忆被主动消息系统重新激活
- [x] Self-memory LLM 提取：搭便车现有记忆提取 LLM 调用（零额外 API 开销），4 种细分类别（self_interest/self_experience/self_opinion/self_habit）
- [x] Self-memory embedding 语义去重：本地 bge cosine similarity（>0.85 跳过，0.6-0.85 强化已有 memory）
- [x] Self-memory 定期合并：embedding 聚类（> 0.75）+ LLM 合并 ≥ 3 条相似自我记忆，is_consolidated 标记
- [x] mem0 全量同步：已移除 mem0，不再需要同步
- [x] 记忆关联网络（Memory Graph）：co_occurrence 建链 + 合并/纠正继承 + 激活传播扩散召回
- [x] Triple Hybrid Scoring：语义相似度 × 0.5 + 激活值 × 0.3 + 重要性 × 0.2
- [x] 移除 mem0 + ChromaDB：统一为 MySQL + 本地 BGE 语义搜索，消除 ID 脱节，激活传播恢复正常
- [x] 写入去重：bge embedding 比对（> 0.90 跳过，0.75-0.90 LLM 合并）
- [x] 睡眠清理：每天凌晨 4 点自动清理 ChromaDB 孤儿 + 同类型聚类合并
- [x] 错误记忆纠正：LLM 检测用户信息与已有记忆矛盾，旧记忆标记 is_invalid，正确版本插入
- [x] 失效记忆过滤：所有记忆召回查询排除 is_invalid=1 的记忆

### 信息检索系统（InfoRetrievalEngine）
- [x] Tavily API 集成（aiohttp 异步，15s 超时）
- [x] 主动检索：后台任务每 8 小时按 YuQing 兴趣自动搜索新闻，LLM 第一人称总结后存入 knowledge_items
- [x] 被动检索：对话中 LLM 判断用户消息是否需要搜索（新闻/时事/新动态），触发实时搜索
- [x] 知识时效性：7 天自动过期（expires_at），过期知识不再注入 prompt
- [x] 知识注入 prompt：system prompt「最近了解的事」区块，自然提及不刻意展示
- [x] 被动检索结果实时注入 messages context，语晴可在回复中引用
- [x] 频率控制：每个兴趣独立记录上次检索时间（app_settings），避免重复搜索
- [x] 手动触发 API：POST /api/memories/trigger-info-retrieval + GET /api/knowledge
- [x] 无 API key 时全部功能静默跳过

### 自我认知系统（SelfCognitionEngine）
- [x] 自我叙事合成：LLM 将零散 self_* 记忆 + YAML 性格 traits 合成为连贯的第一人称叙事
- [x] 触发条件：self_* 记忆数量变化 ≥ 5 条时重新生成（最低 8 条才生成）
- [x] 缓存机制：叙事存入 app_settings KV（self_narrative + self_narrative_mem_count）
- [x] 一致性保障：LLM prompt 包含 YAML traits 数值，确保叙事风格与核心性格一致
- [x] 不冲突设计：YAML 静态骨架（不可变）+ 自我叙事（动态补充）共存
- [x] 注入位置：system prompt「你发现自己的一些事」区块（性格之后、原则之前）

### 情感系统（MoodRegulator）
- [x] V-A 情感模型：Valence（积极度 -1~1）+ Arousal（激动度 0~1）
- [x] LLM 情绪分析：每条用户消息自动分析，映射到 8 种标签
- [x] 情绪快照：存入 `emotion_snapshots` 表
- [x] 用户心情：取最近 5 条快照的平均值

### 语晴心情系统（YuQingMoodTracker）
- [x] 三维情绪模型：warmth（温暖度）/ openness（敞开度）/ energy（能量）
- [x] 五种状态：guarded / withdrawn / relaxed / softened / vulnerable
- [x] 对话驱动更新：关键词 + 启发式信号，EMA 指数移动平均（alpha=0.15）
- [x] 缺席衰减：用户消失时逐小时衰减
- [x] 返场 bump：用户回来时温暖上升但敞开下降（防御性掩饰）
- [x] 基线引力：每次更新后温和拉回基线，防止永久漂移
- [x] 动态回复节奏：根据心情状态调整回复长度（withdrawn 极简 / relaxed 轻松 / softened 多说一点 / vulnerable 允许展开）
- [x] 回复长度自然波动：连续短回复后偶尔来条长的，不固定
- [x] `yuqing_mood_log` 表持久化心情变化历史
- [x] 心情注入 system prompt（"你现在的状态" + "回复节奏"模板区块）
- [x] API：`GET /api/mood/current`、`GET /api/mood/history`

### 人格系统（PersonalityEngine）
- [x] YAML 人格配置 + 数据库覆写
- [x] 5 维性格特征：warmth / humor / formality / empathy / verbosity
- [x] 好感度系统（user_affection）：默认拉满 1.0
- [x] 回避型依恋防御机制：撒娇式调侃 / 害羞转移 / 俏皮唱反调
- [x] 说话习惯规则集（核心风格 + 回避型特征 + 智力特征 + 禁忌）
- [x] 6 种情绪响应策略：sad / angry / excited / anxious / leaving / affectionate
- [x] 4 阶段关系动态：new_acquaintance → familiar → close → very_close
- [x] Jinja2 模板动态 prompt：中英文双语
- [x] 前端设置面板实时调整
- [x] 人格温度调整：从 0.25（太冷）调整为 0.45（傲娇），去掉攻击性表述
- [x] "不像真人"问题修复：减少刻意表演指令，性格自然流露

### 主动消息系统（ProactiveManager）
- [x] 后台 asyncio 任务，每 2 分钟检查触发器
- [x] 4 种触发器（按优先级）：emotion_followup / absence / memory / time_of_day
- [x] LLM 生成符合人设的主动消息（temperature=0.8）
- [x] Rate limiting：两次主动消息间隔 ≥ 3 小时
- [x] 安静时段（0-7 点）不发送
- [x] SSE 推送：EventSource 长连接 + 30 秒 keep-alive + 断连检测（Ctrl+C 优雅退出）
- [x] 离线兜底：`/api/proactive/recent` 页面刷新时补发
- [x] 心情集成：缺席时应用心情衰减

### 用户偏好学习（PreferenceLearner）
- [x] 5 维偏好自动学习：response_length / topic_style / emotional_tone / humor_level / depth_style
- [x] 每 5 轮对话触发一次
- [x] 加权移动平均置信度递增
- [x] 置信度 ≥ 0.5 的偏好注入 system prompt

### 前端组件
- [x] ChatView：聊天主视图（集成搜索面板状态 + 高亮消息管理）
- [x] MessageList：消息列表（自动滚动 + 消息定位高亮 + 2.5s 自动清除）
- [x] MessageBubble：消息气泡（\n\n 多气泡拆分，空消息/"..." 不渲染）
- [x] SearchPanel：历史消息搜索（右侧滑入面板，防抖 300ms，关键词高亮，点击跳转定位）
- [x] InputBar：消息输入框
- [x] Header：标题栏（语言切换 + 搜索入口 + 设置按钮 + 调试面板入口）
- [x] Layout：页面布局（搜索面板状态管理 + 调试面板状态管理）
- [x] EmotionDisplay：情绪显示
- [x] SettingsModal：设置面板
- [x] Sidebar：对话列表侧栏
- [x] MemoryDebugPanel：记忆调试面板（4 tabs：概览/记忆列表/召回调试/关联图 SVG）

### 数据库 Bug 修复
- [x] `user_preferences`：SELECT 缺少 `created_at`/`updated_at` 列
- [x] `yuqing_mood_log`：`get_current_mood`/`get_mood_history` 缺少 `conversation_id` 过滤
- [x] 偏好学习触发间隔：偶数取模导致实际每 10 条而非 5 条触发
- [x] `proactive`：`check_absence`、`check_time_of_day` 缺少 `conversation_id` 过滤
- [x] `cognitive.py`：返场检测查询缺少 `conversation_id` 过滤
- [x] `memories`：`extract_and_store_memories`、`consolidate_memories` INSERT 缺少 `source_conversation_id`
- [x] mem0 移除：去掉 mem0 + ChromaDB，统一为 MySQL + 本地 BGE 语义搜索（消除 ID 脱节，激活传播恢复正常）
- [x] self_memories 合并：去掉 self_memories 表，统一存入 memories 表（memory_type='self_*'），消除 ~150 行重复逻辑
- [x] 召回算法修复：激活传播加载 2 跳邻居（原 1 跳导致多轮迭代空转）；搜索批量 encode + embedding 缓存复用
- [x] 前端 SSE：chunk 边界分割导致 done 事件 JSON 解析失败（行缓冲修复）
- [x] 前端 fallback handler：双重展开导致 cleaned 内容被 fullContent 覆盖
- [x] 信息检索 hash 去重：Python `hash()` 跨进程不稳定导致重启后重复检索，改用 `hashlib.md5`

### 文档
- [x] README.md：完整架构说明 + 快速开始 + API 接口 + 配置参考
- [x] backend/docs/sql.md：12 表 DDL + ER 关系 + 后端连接架构 + 常用查询

### 已知未修复问题
- [ ] `messages` 表：`prompt_tokens`/`completion_tokens` 列从未写入（litellm streaming 不暴露 token 用量）
- [ ] `emotion_snapshots`：无清理机制，数据无限增长
- [ ] `yuqing_mood_log`：无清理机制，数据无限增长
- [ ] `knowledge_items`：无清理机制，过期数据不会自动删除（查询时已通过 expires_at 过滤）
- [ ] `memories`：`source_message_id` 仍未填充（extract 时未传 message_id，仅填充了 source_conversation_id）

### 自我认知现状评估

当前自我认知体系的成熟度：

| 问题 | 状态 | 说明 |
|------|------|------|
| **碎片化** | ✅ 已解决 | SelfCognitionEngine 将零散 self_* 记忆合成为连贯的自我叙事 |
| **注入薄弱** | ✅ 已改善 | 新增"你发现自己的一些事"和"最近了解的事"两个注入区块 |
| **无关系认知** | 待实现 | 对"我和这个人的关系"缺乏积累（L2 Relationship Awareness） |
| **无变化感知** | 待实现 | 兴趣/观点演变追踪（L3 Self-Evolution） |
| **维度单一** | 待实现 | 只有"说了什么"，缺少"为什么说"（触发情境、情感驱动力） |

---

## P0 — 记忆系统核心重构

### 0. 记忆关联网络（Memory Graph）— 神经元式记忆链接

当前记忆是扁平孤岛：每条记忆独立存储和召回，没有关联。人类记忆是网络结构——想起一条自动联想到相关条。

**根因**：mem0 v2.0.0 开源包不支持 `add_relation()`（那是平台付费 API），需要自建关联系统。已完成（后移除 mem0，统一为 MySQL + BGE）。

**核心改动**：

#### 新增 `memory_links` 表
```sql
CREATE TABLE memory_links (
    id CHAR(32) PRIMARY KEY,
    source_id CHAR(32) NOT NULL,  -- 记忆A
    target_id CHAR(32) NOT NULL,  -- 记忆B
    link_type VARCHAR(32) DEFAULT 'co_occurrence',
    strength FLOAT DEFAULT 0.5,
    UNIQUE INDEX idx_pair (source_id, target_id)
);
```

#### 3 种建链时机
- [x] **共现建链**：同一轮 LLM 提取的记忆天然关联，写入时自动建 `co_occurrence` 链（strength=0.7）
- [x] **合并继承链**：consolidate 合并后，新记忆继承所有来源记忆的链接，标记为 `consolidated`（strength=0.4）
- [x] **纠正转移链**：correction 后，正确版本继承旧记忆的所有链接

#### 关联扩散召回（联想扩散）
- [x] `build_context()` 中：mem0.search() 返回后，BFS 沿链接扩散 1-2 跳，带回相关记忆
- [x] 扩散结果与直接命中合并后进入分层注入
- [x] `_activation_spread()`: 多轮迭代传播（Fan Effect + Lateral Inhibition）

#### 综合评分排序
- [x] 替代纯语义排序：Triple Hybrid Score = 语义(0.5) + 激活(0.3) + 重要性(0.2)
- [x] ACT-R access_factor 加权

#### MySQL fallback embedding 语义搜索
- [x] `_search_via_mysql()` 改用本地 bge 做 cosine similarity 搜索（已加载的 `_get_embedding_model()`）
- [x] 查询 200 条候选 → encode → cosine 排序 → top_k，替代纯 importance 排序

#### 新增配置项
```python
MEMORY_LINK_ENABLED: bool = True
MEMORY_LINK_MAX_HOPS: int = 2
MEMORY_LINK_CO_OCCURRENCE_STRENGTH: float = 0.7
MEMORY_LINK_SEMANTIC_THRESHOLD: float = 0.4
```

#### 涉及文件
- `backend/app/core/memory.py` — 核心改动（建链 + 扩散 + 评分 + fallback + 合并继承）
- `backend/app/db/database.py` — memory_links 表
- `backend/app/config.py` — 配置项

---

## P1 — 认知深度增强

### 1. 情绪轨迹分析与可视化
- [ ] 7/14/30 天情绪趋势图表（valence/arousal 走向）
- [ ] 5 种预警模式：情绪恶化、持续低落、社交孤立、愤怒升级、自我伤害念头
- [ ] 学习哪些话题让用户情绪好转/恶化
- [ ] 预警时调整语晴的主动关心行为
- 相关文件：`emotion.py` 扩展，新增前端图表组件

### 2. 矛盾与认知扭曲检测
- [ ] 对比用户当前陈述与过去记忆，发现自我认知矛盾
- [ ] 检测 5 种 CBT 认知扭曲（全有全无、过度概括、自我贬低等）
- [ ] 以语晴的口吻委婉指出
- 相关文件：新增 `backend/app/core/contradiction.py`

### 3. 目标追踪
- [ ] 从对话中检测用户目标（工作、学习、健康、关系等）
- [ ] 追踪进度，后续对话中自然跟进
- [ ] 目标停滞时给出温和推动
- 相关文件：新增 `backend/app/core/goals.py`

### 3.5 语晴自我认知深化（SelfCognitionEngine）

当前 self_* 记忆只是碎片化条目收集（统一存储在 memories 表），已实现 L1 自我叙事合成。

**三层架构**：

```
L1 自我叙事（Self-Narrative）✅ 已完成
  └─ self_* 记忆数量变化 ≥ 5 条时，LLM 综合为连贯叙事
  └─ 缓存到 app_settings KV，注入 prompt「你发现自己的一些事」

L2 关系认知（Relationship Awareness）待实现
  └─ 从对话历史中提取关系信号：互动频率、共同话题、情感里程碑
  └─ 注入 prompt，让语晴知道自己和用户"走到哪一步了"
  - [ ] 新增 `build_relationship_context()`：统计互动频率、共同话题、情感亲近度趋势
  - [ ] 关系描述注入 system prompt
  - [ ] 存储方案：复用 app_settings KV 或 conversations 表扩展字段

L3 自我变化追踪（Self-Evolution）待实现
  └─ 检测 self_* 记忆中的矛盾/演变信号
  └─ 复用错误记忆纠正机制
  - [ ] 新增 memory_type=self_evolution 记录变化事件
  - [ ] 变化事件触发自我叙事重新生成
  - [ ] 检测兴趣转移、观点变化的 LLM prompt
```

---

## P2 — 高级认知能力

### 4. 元记忆系统
- [ ] 追踪"用户的想法如何演变"
- [ ] 识别想法的催化剂（挫折、灵感、限制、机会）
- [ ] 追踪想法经历阶段（细化→扩展→修正→综合→突破）
- 相关文件：`memory.py` 扩展

### 5. 创意联想与跨域桥接
- [ ] 预设跨领域知识桥
- [ ] 休眠概念与当前上下文结合，生成创意性联想
- 相关文件：新增 `backend/app/core/creativity.py`

### 6. 因果推理
- [ ] 从对话中提取因果关系
- [ ] 预测行为的意外后果
- [ ] 类比推理：从不同领域找到相似的问题模式
- 相关文件：新增 `backend/app/core/causal.py`

---

## P3 — 体验增强

### 7. 语音输入/输出
- [ ] 语音转文字（Web Speech API / Whisper）
- [ ] TTS 语音回复
- 相关文件：新增 `frontend/src/components/Voice/`

### 8. 对话数据分析面板
- [ ] 情绪趋势可视化图表
- [ ] 语晴心情状态可视化
- [ ] 记忆统计（各类别占比、重要性分布）
- [ ] 对话时长和频率统计
- 相关文件：新增 `frontend/src/components/Dashboard/`

### 9. 深色模式 + 主题
- [ ] 深色/浅色主题切换
- 相关文件：`frontend/src/index.css`、Layout 组件

### 10. 多对话支持
- [ ] 支持创建多个独立对话
- [ ] 每个对话有独立的消息历史和情绪记录
- 相关文件：前端 Sidebar 扩展、后端 API 已部分支持

---

## 数据库 ER 关系

```
conversations ──┬── 1:N ── messages
                ├── 1:N ── emotion_snapshots
                ├── 1:N ── memories (source_conversation, 含 user + self 两种 memory_type)
                ├── 1:N ── proactive_messages
                └── 1:N ── yuqing_mood_log
messages ──────── 1:N ── memories (source_message)
personality_config (singleton)
yuqing_mood (singleton)
app_settings (KV) — 含 self_narrative / knowledge 检索时间戳
user_preferences (KV with confidence)
knowledge_items (独立表，带 expires_at 时效性)
```
