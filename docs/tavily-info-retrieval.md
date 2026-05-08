# Tavily 信息检索系统

> 实现日期：2026-05-03
> 最后更新：2026-05-06
> 状态：已实现

---

## 概述

雨晴通过 [Tavily](https://tavily.com) API 搜索互联网信息，弥补 LLM 知识截止日期的局限。支持两种检索模式：后台主动搜索和对话中被动触发。

## Tavily API 简介

[Tavily](https://tavily.com) 是专为 AI Agent 设计的搜索 API，与传统搜索引擎相比：

| 特点 | 说明 |
|------|------|
| **返回结构化结果** | 直接返回 title + content + url，不需要解析 HTML |
| **专为 LLM 优化** | content 字段是总结性文本，适合直接喂给 LLM |
| **免费额度** | 免费计划每月 1000 次搜索请求 |
| **搜索深度** | `basic`（快速）/ `advanced`（深度，更慢但更全） |

### API 调用

```python
# backend/app/core/info_retrieval.py — _tavily_search()

POST https://api.tavily.com/search
{
    "api_key": "tvly-xxx",
    "query": "ACG 文化 最新资讯",
    "max_results": 3,
    "include_answer": false,
    "search_depth": "basic"
}

# 响应
{
    "results": [
        {
            "title": "...",
            "content": "搜索结果的摘要文本（直接可用）",
            "url": "https://...",
            "score": 0.85,
            ...
        },
        ...
    ]
}
```

### 配置

```env
TAVILY_API_KEY=tvly-xxx                    # 去 tavily.com 免费注册获取
INFO_RETRIEVAL_ENABLED=true                # 启用信息检索
INFO_RETRIEVAL_INTERVAL_HOURS=8            # 主动检索间隔（小时）
INFO_RETRIEVAL_KNOWLEDGE_EXPIRE_DAYS=7     # 知识过期天数
INFO_RETRIEVAL_REACTIVE_ENABLED=true       # 启用被动检索
```

## 两种检索模式

### 1. 主动检索（Proactive）

后台定时任务，按雨晴的兴趣自动搜索最新资讯。

**流程**：
```
后台循环（每 8 小时）
    │
    ▼
读取 personality.interests（如 "ACG 文化"、"AI 技术"、"音乐"）
    │
    ▼
对每个兴趣：
    ├─ 检查上次检索时间（app_settings 表，key = info_retrieval_{md5(interest)}）
    │  未到 8 小时 → 跳过
    │
    ├─ 构造搜索 query："{兴趣名} 最新资讯"
    │
    ├─ 调用 Tavily API → [{title, content, url}, ...]
    │
    ├─ LLM 第一人称总结（2-3 句话，雨晴视角的感想）
    │  prompt: "以下是关于「{topic}」的最新搜索结果...请用2-3句话总结...以雨晴的第一人称视角"
    │
    ├─ 存入 knowledge_items 表（source_type='proactive'）
    │
    └─ 更新上次检索时间
```

**注入位置**：system prompt「最近了解的事」区块，雨晴可在对话中自然引用。

**首次延迟**：启动后等待 5 分钟再执行第一次检索，避免启动时负载过高。

### 2. 被动检索（Reactive）

用户发消息时，判断是否需要实时搜索。

**流程**：
```
用户消息 → LLM 判断是否需要搜索
              │
              ├─ 不需要（返回 "NO"）→ 跳过，正常对话
              │
              └─ 需要搜索（返回搜索关键词）
                    │
                    ▼
                Tavily API 搜索
                    │
                    ▼
                LLM 总结（雨晴视角）
                    │
                    ▼
                注入 messages 上下文（system 角色）
                "你刚刚查到了以下信息，可以在回复中自然地引用："
                    │
                    ▼
                LLM 生成回复（自然引用搜索到的信息）
                同时存入 knowledge_items 表（source_type='reactive'）
```

**触发条件**：LLM 判断用户消息涉及新闻、时事、最新发布、近期事件、具体产品/作品的新动态。

**判断 prompt**：
```
判断以下用户消息是否需要搜索最新信息才能回答。
如果涉及：新闻、时事、最新发布、近期事件、具体产品/作品的新动态
返回搜索关键词（5-20字），不要加引号。
否则只返回 "NO"。

用户消息：{user_message}
```

**注意**：被动检索每次都需要一次额外 LLM 调用（判断是否需要搜索），这是不可避免的成本。如果 Tavily API key 未配置，被动检索自动跳过。

## 数据存储

### knowledge_items 表

```sql
CREATE TABLE knowledge_items (
    id CHAR(32) PRIMARY KEY,
    topic VARCHAR(128) NOT NULL,           -- 话题分类
    content TEXT NOT NULL,                 -- LLM 总结后的内容（2-3 句话）
    source_url VARCHAR(512) DEFAULT NULL,  -- 原始来源链接
    retrieved_at DATETIME NOT NULL,         -- 检索时间
    expires_at DATETIME NOT NULL,           -- 过期时间（retrieved_at + 7 天）
    is_valid TINYINT NOT NULL DEFAULT 1,    -- 是否有效（可手动失效）
    source_type ENUM('proactive','reactive') DEFAULT 'proactive'
);
```

### 时效性管理

- 知识默认 7 天后过期（`INFO_RETRIEVAL_KNOWLEDGE_EXPIRE_DAYS`）
- 过期知识不再注入 system prompt
- 查询条件：`WHERE is_valid = 1 AND expires_at > NOW()`

### 在 system prompt 中的注入

```jinja
{% if recent_knowledge %}
## 最近了解的事
{% for item in recent_knowledge %}- [{{ item.topic }}] {{ item.content }}（{{ item.retrieved_at_relative }}）
{% endfor %}

你可以自然地在对话中提到这些信息，但不要刻意展示。
{% endif %}
```

### 在对话中的实时注入（被动检索）

被动检索的结果不会存入 system prompt（太慢），而是作为额外的 system 消息直接注入 messages 上下文：

```python
messages.append({
    "role": "system",
    "content": f"你刚刚查到了以下信息，可以在回复中自然地引用：\n{knowledge_text}",
})
```

## LLM 总结 Prompt

主动检索和被动检索使用不同的总结 prompt：

**主动检索**（注入 system prompt，长期有效）：
```
以下是关于「{topic}」的最新搜索结果：
{search_results}

请用2-3句话总结这些信息中有趣的部分，用中文写。
以雨晴的第一人称视角，像是她看到了这些信息后的感想。
只返回总结文本，不要其他格式。
```

**被动检索**（注入 messages 上下文，单次使用）：
```
以下是关于「{query}」的搜索结果：
{search_results}

请用2-3句话总结最相关的信息，用中文写。
以雨晴的视角，像她刚刚查到了这些信息。
只返回总结文本，不要其他格式。
```

区别：主动检索强调"感想"（因为是存入长期知识），被动检索强调"相关信息"（因为是即时回答用户）。

## 后台任务生命周期

```python
# backend/app/main.py — lifespan
info_task = asyncio.create_task(info_retrieval_background_task())

# backend/app/core/info_retrieval.py
async def info_retrieval_background_task():
    await asyncio.sleep(300)  # 首次延迟 5 分钟
    while True:
        if settings.INFO_RETRIEVAL_ENABLED and settings.TAVILY_API_KEY:
            engine = InfoRetrievalEngine()
            await engine.proactive_retrieval()
        await asyncio.sleep(settings.INFO_RETRIEVAL_INTERVAL_HOURS * 3600)
```

## API 用量估算

| 场景 | 频率 | Tavily 调用 | LLM 调用 |
|------|------|-------------|---------|
| 主动检索 | 每 8 小时 × N 个兴趣 | N 次 | N 次（总结） |
| 被动检索 | 每次用户消息可能触发 | 0-1 次 | 1 次（判断）+ 0-1 次（总结） |

**免费计划（1000 次/月）**：
- 主动检索：3 个兴趣 × 3 次/天 = 9 次/天 = 270 次/月
- 被动检索：约 5-10 次/天（取决于用户聊什么）= 150-300 次/月
- 总计约 400-570 次/月，免费额度足够

## 相关文件

| 文件 | 说明 |
|------|------|
| `backend/app/core/info_retrieval.py` | `InfoRetrievalEngine` 类 + `_tavily_search()` + 后台任务 |
| `backend/app/core/cognitive.py` | Phase 3.5 调用被动检索 |
| `backend/app/core/personality.py` | `build_system_prompt()` 注入 recent_knowledge |
| `backend/app/prompts/system_zh.txt.j2` | 「最近了解的事」模板区块 |
| `backend/app/config.py` | 检索配置参数 |

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/knowledge` | 查看当前未过期的知识条目 |
| POST | `/api/memories/trigger-info-retrieval` | 手动触发主动检索（调试用） |
