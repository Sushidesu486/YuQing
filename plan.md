# YuQing 语晴 — 开发计划

> 最后更新：2026-05-06

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
- [x] 10 阶段流水线：情绪分析 → 心情更新 → 时间感知 → 记忆召回 → 被动信息检索 → 人格 prompt → 消息存储 → 上下文加载 → LLM 流式生成 → 消息存储 → 后台任务
- [x] SSE 事件类型：emotion / mood / token / memory_extracted / knowledge / proactive / done / error
- [x] 用户消息按行拆分存储，合并文本用于记忆提取
- [x] 硬格式约束禁止 "..." 输出 + 前端三层清理（prompt 约束 / EMPTY_RESPONSES 过滤 / done 事件段落清洗）
- [x] SSE done 事件提前：done yield 移到 Phase 8 之后、Phase 9 之前（记忆提取 LLM 不再阻塞前端）

### 记忆系统（MemoryManager）
- [x] 多层记忆架构：工作记忆（20 条上下文）+ 长期记忆（MySQL + BGE 语义搜索）
- [x] 7 种用户记忆类型：fact / event / episodic / emotion / preference / procedural
- [x] 4 种自我记忆类型：self_interest / self_experience / self_opinion / self_habit
- [x] 分层注入机制：显式层（fact+event）→ 情感层（episodic）→ 行为层（preference/procedural）
- [x] mem0 v2 集成（后移除，改为本地 BGE + MySQL）
- [x] 本地中文嵌入模型 BAAI/bge-base-zh-v1.5（768 维，无需额外 API）
- [x] 自动记忆提取：LLM 分类（7 种类型 + valence + confidence）→ MySQL + ChromaDB
- [x] 语义召回：BGE embedding cosine similarity 搜索（200 候选 → 批量 encode → 排序，top_k=20）
- [x] Pinned facts 保障：importance >= 0.7 的记忆强制注入（最多 4 条），不参与排序竞争
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
- [x] 睡眠清理：5 阶段神经科学启发记忆维护（突触归一化 + 选择性 Replay + 聚类合并 + 休眠剪枝 + 孤儿链接清理）
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
- [x] 跨会话心情保留：mood_session_peak/end 存入 app_settings，残留 48h 线性衰减到基线
- [x] 非对称情绪传染：warmth α=0.10（慢跟随）vs energy α=0.20（快响应）
- [x] 负面状态持久化：warmth < 0.25 时衰减速率减半
- [x] 自适应基线引力：value > 0.85 或 < 0.15 时额外 baseline pull（防止极端值）
- [x] 天花板/地板阻尼：接近 0/1 极值时边际递减（resistance=0.03）
- [x] 情绪惯性：momentum 机制（velocity 跨会话保留，inertia=0.8）
- [x] 7 天情绪趋势分析：get_mood_trend_summary()

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

---

## 待办

### Tavily 信息检索优化

**问题分析（2026-05-06）**

1. **搜索 query 太泛**：从 YAML interests 提取 topic 后只拼接"最新资讯"，如"ACG 文化 最新资讯"、"历史和神话 最新资讯"，返回的是大路货新闻，不符合语晴人设。语晴的兴趣描述中有具体方向（"老玩家品味洁癖"、"高性能计算"、"后朋克和摇滚"），完全没利用。

2. **总结 prompt 返回"感想"而非"事实"**：当前 prompt 要求"以语晴的第一人称视角，像是她看到了这些信息后的感想"。实际存入 knowledge_items 的全是"我觉得…真不错"、"这脑洞也太大了"之类的感叹，没有任何实际信息量。7 天内可引用，但对对话毫无价值——语晴不可能只说一句"最近有个事挺有意思"但不提是什么事。

3. **LLM 总结时无人格上下文**：`generate_completion(messages=[{"role": "user", "content": prompt}])` 没有传 system prompt，导致：
   - 总结语气不像语晴（"真是让人又期待又着急呀"这种不像她会说的话）
   - 没有利用语晴的性格特质（吐槽、调侃、毒舌风格）来过滤/评价信息

4. **Tavily 高风险结果被直接存入**："各种诡辩论和思维实验"和"历史和神话"的搜索被 Tavily 标记为 high risk，但存入的是 "The request was rejected because it was considered high risk" 这段错误文本。

5. **被动检索 query 不够具体**：LLM 判断需要搜索后返回的 query（如"今日有趣新闻事件"）太模糊，搜索结果质量差。

6. **被动检索总结也无人设约束**：同样只有 `[{"role": "user", "content": prompt}]`，语气不统一。

**改进方向**：

- [ ] 从 YAML interests 中提取具体关键词构造精准搜索 query（如 "新番 2026年4月"、"后朋克 新专辑" 而非 "ACG 文化 最新资讯"）
- [ ] 总结 prompt 改为"提取 2-3 条具体事实"（具体事件/数据/发布信息），不要感想
- [ ] 总结时传入精简人格 system prompt（姓名 + 语气 + 说话习惯），让语气回归人设
- [ ] Tavily 返回空结果或高风险内容时直接跳过，不存入数据库
- [ ] 被动检索：对 LLM 生成的搜索关键词增加质量判断（太泛则不搜索）
- [ ] 被动检索总结也加入人格约束

### 时间感知系统（Temporal Awareness）✅ 已完成
- [x] 新建 `temporal.py`：TemporalContext dataclass，SessionGapTier（6 档），TimeOfDayZone（6 档），关系任期、会话时长、今日统计
- [x] 集成认知管线：cognitive.py Phase 2.2 计算 temporal_context，传入 personality.build_system_prompt()
- [x] 模板注入：system_zh.txt.j2 / system_en.txt.j2 新增「时间感知」区块（时段、间隔、任期、时长、深夜提示）
- [x] 记忆时间维度补全：episodic/emotion 补上 `created_at_relative`，facts 模板显示"（3天前了解到）"
- [x] 召回评分加 recency bonus：近 7 天 +0.05，近 30 天 +0.02
- [x] 昼夜节律：mood.py 深夜 energy -0.05
- [x] 主动消息时段风格：proactive.py 深夜/清晨提示简短安静

### 记忆召回优化 ✅ 已完成
- [x] Embedding 模型升级：bge-small-zh-v1.5（512维）→ bge-base-zh-v1.5（768维），更强语义区分能力
- [x] 召回容量扩容：语义搜索 top_k 10→20，fact 上限 6→8，episodic 上限 3→5，pinned facts 上限 2→4
- [x] 查询增强：用最近 4 条消息拼接作为搜索 query（而非单条用户消息），提供更丰富的语义上下文
- [x] 候选池优化：阈值 importance > 0.2 → > 0.05（扩大候选范围），排序改为 importance DESC（而非 last_accessed DESC）
- [x] Pinned facts 阈值下调：0.8 → 0.7（更多高重要性记忆强制注入）
- [x] 记忆提取上限提升：用户记忆 5→8 条/轮，自我记忆 3→5 条/轮
- [x] Dormant 记忆阈值：importance > 0.2 → > 0.1（更多休眠记忆可被唤醒）
- [x] Mood congruence：评分加入情绪一致性加成（warmth × valence × 0.15），情绪低落时优先召回积极记忆

---

## ~~时间感知系统（Temporal Awareness）~~ ✅ 已完成

### 背景调研

**当前语晴的时间感知能力**：

语晴对时间的感知几乎是"盲"的。当前代码中只有零散的时间相关逻辑，没有统一的时间上下文模块：

| 现有能力 | 位置 | 问题 |
|---------|------|------|
| 返场检测 | cognitive.py:49-62 | 二值判断：≥4h 就是"缺席"，没有中间状态 |
| 缺席检测 | proactive.py:88-111 | 只返回 hours_absent 数字，没有分级语义 |
| 时段问候 | proactive.py:113-143 | 只有 morning/evening 两档，不影响人格表现 |
| 心情衰减 | mood.py:269-298 | 线性衰减到固定 absence baseline，没有时段差异 |
| msg_count | cognitive.py:207 | 只用于触发定期任务，不注入 prompt |

**核心缺失**：
1. 语晴不知道"我和这个人认识多久了"（关系任期）
2. 语晴不知道"现在是深夜还是下午"（时段感知不影响回复风格）
3. 语晴不知道"用户刚走开5分钟还是消失了3天"（会话间隔语义）
4. 语晴不知道"这轮对话已经聊了2小时"（对话时长感知）
5. 记忆召回没有时间锚定（无法说"上次你提到X是上周"）

**学术与开源参考**：
- **Zep**（[GitHub](https://github.com/getzep/zep)）：最成熟的时间感知记忆系统。核心设计：消息自动标注 `created_at`，召回时按时间排序，`session_summary` 机制跨会话传递上下文。时间戳作为一等公民贯穿整个记忆生命周期。
- **Cognee**（[GitHub](https://github.com/topoteretes/cognee)）：temporal cognification 框架，时间维度作为记忆图的固有属性，支持时间范围查询（"上个月"）。
- **passage-of-time-mcp**（[GitHub](https://github.com/mcndt/passage-of-time-mcp)）：轻量 MCP 插件，返回当前时间、距上次交互间隔、当日时段描述。
- **MemGPT/Letta**：消息列表按时间排序，对话历史有清晰的时间边界。
- **Human temporal cognition**（认知心理学）：人类的时间感知分为时间顺序（sequence）、时间持续（duration）、时间频率（frequency）三个维度。Companion AI 应至少覆盖这三个维度。

### 可信性分析

| 维度 | 可信性 | 说明 |
|------|--------|------|
| 会话间隔感知 | ⭐⭐⭐⭐⭐ | 纯计算，零风险。messages 表已有 created_at，查询最近消息时间戳即可。分档语义（刚走开/半天没来/几天没来）提升回复自然度。 |
| 时段感知 | ⭐⭐⭐⭐⭐ | 纯计算。`datetime.now().hour` 映射到时段描述，注入 prompt 让语晴知道"现在是深夜/下午"。低风险高回报。 |
| 关系任期 | ⭐⭐⭐⭐⭐ | `conversations.created_at` 或最早消息时间 → 计算认识天数。纯查询，无风险。让语晴能说"我们认识快一个月了"。 |
| 对话时长感知 | ⭐⭐⭐⭐ | 当前会话的消息跨度。可能影响回复节奏（聊久了可以更放松）。低风险。 |
| 时间锚定记忆 | ⭐⭐⭐⭐ | 记忆的 created_at 在查询时转为相对时间描述（"上周"、"昨天"、"去年"）。纯格式化，无风险。 |
| 昼夜节律 | ⭐⭐⭐ | 深夜语晴应该更安静/迷糊，白天更活跃。中度风险（过度表演），需要微妙编码。 |
| 时段情感调制 | ⭐⭐⭐ | 不同时段的心情基线微调（凌晨 baseline 更低沉）。需要和 mood.py 联动。 |

### 优化点分析

时间感知带来的系统性优化：

1. **回复自然度提升**：语晴能根据时段调整语气（深夜简短、白天正常），根据间隔调整开场（"刚走？" vs "好久不见"），根据认识天数调整亲密程度暗示
2. **记忆召回增强**：时间锚定记忆让语晴能引用具体时间（"你上个月说的那个项目"），比纯内容引用更真实
3. **心情系统深化**：昼夜节律让心情变化更有物理基础（凌晨能量低不是随机的，是"困了"）
4. **主动消息个性化**：不同时段的主动消息风格不同（深夜温柔、白天随意）
5. **关系认知基础**：任期追踪是 L3 关系认知的前置条件
6. **跨会话连续性**：session gap 分档让跨会话对话不再是"失忆重启"

### 实施设计

#### 核心模块：`backend/app/core/temporal.py`

新建 `TemporalContext` dataclass，统一计算所有时间维度的上下文：

```python
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

class SessionGapTier(Enum):
    CONTINUATION = "continuation"     # < 10 min — 没走远
    SHORT_BREAK = "short_break"       # 10min ~ 2h — 短暂离开
    SAME_DAY = "same_day"             # 2h ~ 当天早些时候
    DAY_GAP = "day_gap"               # 昨天或前天
    WEEK_GAP = "week_gap"             # 3-7 天
    LONG_ABSENCE = "long_absence"     # > 7 天

class TimeOfDayZone(Enum):
    EARLY_MORNING = "early_morning"   # 5-8
    MORNING = "morning"               # 8-12
    AFTERNOON = "afternoon"           # 12-17
    EVENING = "evening"               # 17-21
    NIGHT = "night"                   # 21-24
    LATE_NIGHT = "late_night"         # 0-5

@dataclass
class TemporalContext:
    # 当前时间
    current_time: datetime
    time_zone: TimeOfDayZone
    time_description_zh: str          # "下午三点"、"凌晨两点半"

    # 会话间隔
    minutes_since_last_message: float
    session_gap: SessionGapTier
    gap_description_zh: str           # "你刚走开一会儿"、"好久不见"

    # 关系任期
    days_known: int
    relationship_description_zh: str  # "我们认识快一个月了"

    # 对话时长（当前会话）
    session_duration_minutes: float
    session_message_count: int
    session_description_zh: str       # "已经聊了一个多小时了"

    # 今日时段统计
    messages_today: int
    is_first_message_today: bool
```

#### 集成点

| 集成位置 | 用途 | 改动量 |
|---------|------|--------|
| `cognitive.py` Phase 2.5 | 计算 TemporalContext，传入后续管线 | 新增 ~5 行 |
| `personality.py build_system_prompt()` | 新增 `temporal_context` 参数传入模板 | 改签名 + 传参 |
| `system_zh.txt.j2` | 新增时间上下文注入区块 | 新增 ~15 行模板 |
| `mood.py` | 昼夜节律微调基线（深夜 energy-0.05） | 改 `_compute_energy_signal` |
| `proactive.py` | 主动消息利用时间上下文 | 改 `_generate_message` 的 extra_context |
| `memory.py build_context()` | 记忆召回加时间锚定（relative time 描述） | 格式化 created_at |

#### 数据库

无需新建表。所有时间信息来自现有 `messages.created_at` 和 `conversations.created_at` 查询。

#### 配置项（config.py）

```python
TEMPORAL_ENABLED: bool = True
TEMPORAL_CONTINUATION_MINUTES: int = 10     # < 此值为"刚走"
TEMPORAL_SHORT_BREAK_MINUTES: int = 120     # < 此值为"短暂离开"
TEMPORAL_LATE_NIGHT_START: int = 0          # 凌晨时段开始
TEMPORAL_LATE_NIGHT_END: int = 5            # 凌晨时段结束
TEMPORAL_ENERGY_NIGHT_PENALTY: float = 0.05 # 深夜能量衰减
```

#### prompt 注入示例

```
{% if temporal_context %}
## 时间感知
{% if temporal_context.is_first_message_today %}
今天是 {{ temporal_context.time_description_zh }}，这是用户今天第一次找你。
{% else %}
现在是 {{ temporal_context.time_description_zh }}。
{% endif %}
{% if temporal_context.gap_description_zh and temporal_context.session_gap.value != "continuation" %}
{{ temporal_context.gap_description_zh }}。
{% endif %}
{% if temporal_context.relationship_description_zh %}
{{ temporal_context.relationship_description_zh }}。
{% endif %}
{% if temporal_context.session_duration_minutes > 60 %}
{{ temporal_context.session_description_zh }}，可以稍微放松一些。
{% endif %}
{% endif %}
```

### 记忆的时间维度（现状分析与改进）

**现状**：每条记忆都有 `created_at`，但时间信息的利用非常薄弱：

| 记忆类型 | `created_at_relative` 是否计算 | 模板是否显示时间 | 问题 |
|---------|------|------|------|
| fact | ✅ 已计算 | ❌ 只显示 `{{ mem.content }}` | 知道用户换了工作，但不知道什么时候换的 |
| event | ✅ 已计算 | ✅ `{{ mem.created_at_relative }}` | 唯一正常的时间展示 |
| episodic | ❌ 未计算 | ❌ 无时间字段 | 带有强烈情绪的场景经历，完全丢失时间锚点 |
| emotion | ❌ 未计算 | N/A（转为 trigger） | 情感模式无时间上下文 |
| preference | 部分（fallback 到 fact 时） | ❌ | 用户偏好可能有变化历史，但没有时间线 |

**`_time_ago()` 已存在**（memory.py:203-219），返回"今天/昨天/3天前/2周前/3个月前/2年前"，直接复用。

**改进设计**：

1. **所有记忆类型统一计算 `created_at_relative`**：build_context() 中 episodic、emotion 等全部补上
2. **模板全面显示时间**：
   - facts：`- {{ mem.content }}（{{ mem.created_at_relative }}了解到）`
   - episodic：`- {{ mem.content }}（{{ mem.created_at_relative }}）`
   - preference/procedural 转为 behavior_rules 时不需要时间（规则是当前状态）
3. **召回评分加入时间新鲜度因子**：recency 作为 Triple Hybrid Score 的第四维度
   - 近 7 天记忆 +0.05 bonus，近 30 天 +0.02，更早的 +0
   - 权重不宜过大（记忆内容相关性 > 新鲜度），作为 tiebreaker
4. **时间锚定记忆召回**（Phase 3.6 情感真实性的 mood-congruent recall 前置）：
   - 当前对话提到"上次"、"之前"、"去年"等时间词时，优先召回对应时间段的记忆
   - LLM prompt 中已有 `recalled_memories`，但语晴无法说"你去年说的那个"因为不知道记忆的时间

### 实施路线

```
Phase 1 — 基础时间上下文（核心，优先）
  ├─ 新建 temporal.py：TemporalContext 计算
  │  ├─ get_temporal_context(conversation_id) → TemporalContext
  │  ├─ _classify_session_gap(minutes) → SessionGapTier
  │  ├─ _classify_time_zone(hour) → TimeOfDayZone
  │  └─ _compute_relationship_tenure(conversation_id) → days_known
  ├─ cognitive.py 集成：Phase 2 后计算 temporal_context
  ├─ personality.py 传参：build_system_prompt 新增 temporal_context
  ├─ system_zh.txt.j2 注入：时间感知区块
  └─ system_en.txt.j2 注入：英文版

Phase 2 — 记忆时间维度补全
  ├─ memory.py build_context()：
  │  ├─ episodic 补上 created_at_relative 计算
  │  ├─ emotion 补上 created_at_relative 计算
  │  └─ 召回评分加 recency bonus（近7天 +0.05）
  ├─ system_zh.txt.j2：
  │  ├─ facts 区块加（{{ mem.created_at_relative }}）
  │  ├─ episodic 区块加（{{ mem.created_at_relative }}）
  │  └─ 优化时间显示格式（fact 用"了解到"，event 用无后缀）
  └─ system_en.txt.j2：英文版时间锚定

Phase 3 — 情绪-时间联动
  ├─ mood.py 昼夜节律：深夜 energy baseline -0.05，凌晨 openness -0.03
  ├─ mood.py 长对话微调：session > 30min 时 openness +0.02
  └─ proactive.py 时段风格：深夜主动消息更简短温柔
```

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

基于 GLA（Generative Life Agents, 2025）、soul.py（arXiv:2604.09588）、MATE（SSRN:6553448）的背调。

**核心发现**：
- YAML 静态骨架 + 自我叙事（L1）共存是正确设计，但缺少从经验反馈到性格参数的闭环
- GLA 的 Reflect-Evolve 架构最适合 YuQing：Reflect 合成洞察 → Evolve 提出结构化 JSON 更新 → 日志审计
- soul.py 的 identity hash 提供了量化漂移检测方法：定期用身份探针问题测试，hash 对比基线
- MATE 的 Hebbian micro-nudge + logistic saturation 确保特质变化有界、可复现

**关键论文**：
- GLA: [ResearchSquare PDF](https://www.researchsquare.com/article/rs-7018899/v1.pdf) | [GitHub](https://github.com/Eeman1113/Sira)
- soul.py: [arXiv:2604.09588](https://arxiv.org/abs/2604.09588) | [GitHub](https://github.com/menonpg/soul.py)
- MATE: [SSRN:6553448](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6553448)
- Subaharan 情感动力学: [arXiv:2601.16087](https://arxiv.org/abs/2601.16087)
- EmoACT (Affect Control Theory): [arXiv:2504.12125](https://arxiv.org/html/2504.12125v1)

**三层架构（修订）**：

```
L1 自我叙事（Self-Narrative）✅ 已完成
  └─ self_* 记忆数量变化 ≥ 5 条时，LLM 综合为连贯叙事
  └─ 缓存到 app_settings KV，注入 prompt「你发现自己的一些事」

L2 Reflect-Evolve（人格演化引擎）✅ 已完成
  └─ Reflect: 每 40 轮对话，LLM 从最近 self_* 记忆 + 对话片段中合成自我反思（1-3 句）
  └─ Evolve: 独立 LLM 实例分析反思，提出结构化 JSON 特质更新（每次 ≤ 0.05）
  └─ 漂移约束: logistic saturation + MAX_TRAIT_DRIFT = 0.15（距 YAML 基线最大偏移）
  └─ 审计日志: personality_evolution 表记录每次变更的 before/after/reasoning
  └─ Identity Hash: 首次启动时用 5 个身份探针问题计算基线，SHA256 存储到 app_settings

L3 关系认知（Relationship Awareness）待实现
  └─ 从对话历史中提取关系信号：互动频率、共同话题、情感里程碑
  └─ 注入 prompt，让语晴知道自己和用户"走到哪一步了"
  - [ ] build_relationship_context(): 统计互动频率、共同话题、情感亲近度趋势

L4 主动自我反思（Proactive Reflection）远期
  └─ 每日定时回顾当天对话，产出自省（存储到 self_reflections 表）
  └─ 累积反思作为 Evolve 的额外输入
  └─ 语晴偶尔在对话中引用反思（"我昨天想了一件事..."）
```

**L2 具体设计**：

```sql
CREATE TABLE personality_evolution (
    id VARCHAR(32) PRIMARY KEY,
    triggered_at DATETIME,
    trigger_type ENUM('reflect', 'drift_correction'),
    reflection_text TEXT,
    evolve_json JSON,              -- {"traits": {"warmth": 0.02}, "interests": {"add": [...]}}
    reasoning TEXT,
    applied BOOLEAN DEFAULT FALSE,
    snapshot_before JSON,          -- 演化前的完整性格状态
    snapshot_after JSON,           -- 演化后的完整性格状态
    identity_hash_before VARCHAR(64),
    identity_hash_after VARCHAR(64)
);
```

- `Reflect` 触发: `check_and_update()` 中 msg_count % 20 时触发
- `Evolve` prompt: 分析反思 → 判断是否需要调整 → 结构化 JSON 输出 → 大多数时候返回空 updates
- `apply_evolve()`: 解析 JSON → 校验漂移范围 → logistic saturation → 更新 personality_config → 写审计日志
- `compute_identity_hash()`: 5 个固定探针问题 → LLM 回答 → SHA256 前 16 位 → 对比基线
- 漂移修正: hash 偏移超阈值 → 回滚到 YAML 基线 + 保留累积漂移的 50%

**Guard Rails（防止人格崩塌）**:
1. 单次特质调整 ≤ 0.05（防止大跳变）
2. 累计漂移 ≤ MAX_TRAIT_DRIFT = 0.15（距 YAML 基线）
3. Logistic saturation: `saturate(v) = 1/(1+exp(-10*(v-0.5)))`（软边界 [0,1]）
4. 非对称衰减: 负向漂移（冷漠化）衰减更快（12 小时恢复 30%），正向漂移保留更久
5. 审计日志不可删除，可追溯每次变更链: trait change → Evolve JSON → Reflection → memories

---

### 3.6 情感真实性增强（Emotional Authenticity）

基于 Subaharan (2026)、EmoACT (2025)、Chain-of-Emotion (PLOS ONE, 2024) 的背调。

**当前问题**：
- 语晴心情在会话间几乎完全衰减到基线（48h 后无痕迹）
- 情绪触发靠关键词匹配（`_WARM_KEYWORDS`），不是事件评估
- 情绪表达是显式的（"我现在很开心"），不是行为层面的
- 记忆无情感标签，无法实现情绪一致性召回

**核心发现**：
- Subaharan (2026): 二阶情感动力学（位置+速度）比一阶 EMA 更真实，mu=0.8 惯性最佳
- EmoACT: 情绪 = 身份与印象的落差，不是关键词匹配。事件评估 → 情绪生成 → 表达
- ScienceDirect (2026): AI 过度积极表达会让用户感到不真实。微妙行为变化 > 显式情绪声明
- 情绪惯性: 负面状态应比正面状态持续更久（人类负面偏见），让关系冲突有真实感

**实施路线**：

```
Phase 1 — 低成本高回报 ✅ 已完成
  ├─ 情绪一致性召回: build_context() 新增 current_mood_warmth 参数，
  │  评分加入 mood_congruence = warmth × valence × 0.15
  ├─ 跨会话心情保留: app_settings 存 mood_session_peak/end，
  │  get_current_mood() 衰减目标 = peak×0.4 + end×0.4 + baseline×0.2，
  │  残留48h线性衰减到纯baseline
  └─ 微妙行为编码: system_zh/en 模板重写，去掉显式情绪声明，
     改为行为描述（回复长度变化、主动/被动、是否会 deflect）

Phase 2 — 中等投入 ✅ 已完成
  ├─ 非对称情绪传染: MOOD_WARMTH_ALPHA=0.10（慢）vs MOOD_ENERGY_ALPHA=0.20（快）
  └─ 负面状态持久化: warmth < 0.25 时 decay_rate × 0.5

Phase 3 — 差异化 ✅ 已完成
  ├─ 自适应基线引力: value > 0.85 或 < 0.15 时额外 baseline pull
  ├─ 情绪天花板/地板: 接近 0/1 极值时边际递减（resistance=0.03）
  └─ 情绪自反思: get_mood_trend_summary() 7天趋势分析（预留，未注入prompt）
```

**涉及文件**：

| 文件 | 改动 |
|------|------|
| `config.py` | 新增 12 个 MOOD_* 配置项 |
| `mood.py` | 跨会话残留 + 非对称传染 + 负面持久化 + 自适应引力 + 天花板地板 + 趋势分析 |
| `memory.py` | build_context() 新增 current_mood_warmth，评分加 mood_congruence_bonus |
| `cognitive.py` | 传入 current_mood_warmth 到 build_context |
| `system_zh.txt.j2` | 微妙行为编码重写（withdrawn/relaxed/softened/vulnerable） |
| `system_en.txt.j2` | 英文版行为编码重写 |

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
personality_config (singleton) — 含 Evolve 更新后的 traits/interests
personality_evolution — 人格演化审计日志（before/after/reasoning/hash）
yuqing_mood (singleton)
app_settings (KV) — 含 self_narrative / knowledge 检索时间戳
user_preferences (KV with confidence)
knowledge_items (独立表，带 expires_at 时效性)

时间感知（无新表，纯计算）：
  temporal.py ← messages.created_at（间隔/时长/今日统计）
             ← conversations.created_at（关系任期）
             ← datetime.now()（时段/昼夜节律）
```
