# YuQing 语晴 — 开发计划

> 最后更新：2026-05-03

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

### 认知处理器（CognitiveProcessor）
- [x] 9 阶段流水线：情绪分析 → 心情更新 → 记忆召回 → 人格 prompt → 消息存储 → 上下文加载 → LLM 流式生成 → 消息存储 → 后台任务
- [x] SSE 事件类型：emotion / mood / token / memory_extracted / proactive / done / error
- [x] 用户消息按行拆分存储，合并文本用于记忆提取
- [x] 硬格式约束禁止 "..." 输出 + 前端三层清理（prompt 约束 / EMPTY_RESPONSES 过滤 / done 事件段落清洗）

### 记忆系统（MemoryManager）
- [x] 多层记忆架构：工作记忆（20 条上下文）+ 长期记忆（MySQL + mem0 + ChromaDB）
- [x] 7 种用户记忆类型：fact / event / episodic / emotion / preference / procedural
- [x] 4 种自我记忆类型：self_interest / self_experience / self_opinion / self_habit
- [x] 分层注入机制：显式层（fact+event）→ 情感层（episodic）→ 行为层（preference/procedural）
- [x] mem0 v2 集成（infer=False 适配不支持 function calling 的模型）
- [x] 本地中文嵌入模型 BAAI/bge-small-zh-v1.5（512 维，无需额外 API）
- [x] 自动记忆提取：LLM 分类（7 种类型 + valence + confidence）→ MySQL + ChromaDB
- [x] 语义召回：mem0 混合检索 + MySQL 补充（mem0 返回不足时补充高重要性记忆）
- [x] Pinned facts 保障：importance >= 0.8 的记忆强制注入，不参与排序竞争
- [x] 记忆衰减：90 天半衰期，未被访问的记忆重要性逐渐降低
- [x] 记忆巩固：每 20 轮合并相关记忆，压缩冗余
- [x] 休眠记忆唤醒：30 天未召回的语义相关记忆被主动消息系统重新激活
- [x] Self-memory LLM 提取：搭便车现有记忆提取 LLM 调用（零额外 API 开销），4 种细分类别（self_interest/self_experience/self_opinion/self_habit）
- [x] Self-memory embedding 语义去重：本地 bge cosine similarity（>0.85 跳过，0.6-0.85 强化已有 memory）
- [x] Self-memory 定期合并：embedding 聚类（> 0.75）+ LLM 合并 ≥ 3 条相似自我记忆，is_consolidated 标记
- [x] mem0 全量同步：启动时同步所有 MySQL 记忆到 mem0（包括 consolidated），完整 metadata（type/valence/confidence），排除 None 值

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
- [x] SSE 推送：EventSource 长连接 + 30 秒 keep-alive
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
- [x] Header：标题栏（语言切换 + 搜索入口 + 设置按钮）
- [x] Layout：页面布局（搜索面板状态管理）
- [x] EmotionDisplay：情绪显示
- [x] SettingsModal：设置面板
- [x] Sidebar：对话列表侧栏

### 数据库 Bug 修复
- [x] `user_preferences`：SELECT 缺少 `created_at`/`updated_at` 列
- [x] `yuqing_mood_log`：`get_current_mood`/`get_mood_history` 缺少 `conversation_id` 过滤
- [x] 偏好学习触发间隔：偶数取模导致实际每 10 条而非 5 条触发
- [x] `proactive`：`check_absence`、`check_time_of_day` 缺少 `conversation_id` 过滤
- [x] `cognitive.py`：返场检测查询缺少 `conversation_id` 过滤
- [x] `memories`：`extract_and_store_memories`、`consolidate_memories` INSERT 缺少 `source_conversation_id`
- [x] mem0 同步：`sync_memories_to_mem0` 过滤 `is_consolidated=0` 导致大部分记忆未同步
- [x] mem0 metadata：None 值导致 TypeError，修复为排除 None 字段
- [x] 前端 SSE：chunk 边界分割导致 done 事件 JSON 解析失败（行缓冲修复）
- [x] 前端 fallback handler：双重展开导致 cleaned 内容被 fullContent 覆盖

### 文档
- [x] README.md：完整架构说明 + 快速开始 + API 接口 + 配置参考
- [x] backend/docs/sql.md：11 表 DDL + ER 关系 + 后端连接架构 + 常用查询

### 已知未修复问题
- [ ] `messages` 表：`prompt_tokens`/`completion_tokens` 列从未写入（litellm streaming 不暴露 token 用量）
- [ ] `app_settings` 表：被 API 读写但未被核心模块消费（死数据，等待前端运行时配置功能）
- [ ] `emotion_snapshots`：无清理机制，数据无限增长
- [ ] `yuqing_mood_log`：无清理机制，数据无限增长
- [ ] `memories`：`source_message_id` 仍未填充（extract 时未传 message_id，仅填充了 source_conversation_id）

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
                ├── 1:N ── memories (source_conversation)
                ├── 1:N ── self_memories (source_conversation)
                ├── 1:N ── proactive_messages
                └── 1:N ── yuqing_mood_log
messages ──────── 1:N ── memories (source_message)
personality_config (singleton)
yuqing_mood (singleton)
app_settings (KV)
user_preferences (KV with confidence)
```
