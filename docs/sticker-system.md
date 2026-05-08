# 表情包系统（Sticker System）

> 实现日期：2026-05-06
> 状态：已实现

## 概述

雨晴能在对话中发送表情包图片，表情包的选择完全由 BGE 语义后处理决定，不占用 LLM token。用户也能通过表情包选择器发送表情包。

## 架构

```
Phase 7:   LLM 流式回复完成
              │
              ▼
Phase 7.5: BGE 语义匹配（Python 后处理）
              │  1. _get_embedding_model_for_sticker() 加载 BGE
              │  2. encode(full_response) → 回复向量
              │  3. encode(sticker.desc) × 16 → 所有 sticker 描述向量
              │  4. cosine_similarity 选最佳匹配
              │  5. similarity > 0.35 → sticker_name = best_path
              │
              ▼
Phase 8:   存储消息
              │  文本消息（清理 sticker 引用后）→ content_type='text'
              │  sticker（如有）→ content_type='sticker'（独立 row）
              │
              ▼
SSE 事件:   done → sticker（如有）
```

**核心设计决策**：
- LLM 不知道 sticker 存在，system prompt 中无任何 sticker 信息
- 选择完全在 Python 中完成，零 LLM 开销
- 不需要数据库表，定义在代码中（`STICKER_DEFINITIONS`）
- 加新 sticker 只需在 `personality.py` 加一行定义 + 放一张 PNG

## Sticker 定义

文件：`backend/app/core/personality.py`

```python
STICKER_DEFINITIONS = [
    {"path": "happy/peekaboo", "desc": "探出半个头偷偷看，好奇期待对方反应，适合轻松愉快的对话氛围"},
    {"path": "happy/smile_blink", "desc": "笑着眨眼，温暖俏皮，适合对方说了有趣的话或者气氛轻松时"},
    {"path": "happy/clap", "desc": "鼓掌，表示赞赏和祝贺，对方取得了成就或说了精彩的话"},
    {"path": "happy/celebrate", "desc": "庆祝撒花，非常开心激动的时刻，对方分享了好消息"},
    {"path": "sad/pat_pat", "desc": "YuQing微笑着摸摸对方的头，亲拍，表示安慰或者亲呢"},
    {"path": "sad/hug", "desc": "给一个拥抱，对方情绪低落、感到孤独或需要温暖时"},
    {"path": "sad/tissue", "desc": "感到心情有点低落，用纸巾擦自己的眼泪"},
    {"path": "teasing/pout", "desc": "嘟嘴不高兴，被调侃或被开玩笑时傲娇地表达不满"},
    {"path": "teasing/whatever", "desc": "无所谓耸肩摊手，对方说的事情自己不在意或者觉得好笑"},
    {"path": "shy/fidding_with_hair", "desc": "害羞地玩头发，被夸奖、害羞或者被关注到时会紧张地摆弄头发"},
    {"path": "angry/glare", "desc": "怒视瞪眼，真的生气或不耐烦的时候盯着对方"},
    {"path": "angry/ignore", "desc": "别过脸不理人，生气但不想说话，用沉默表达不满"},
    {"path": "love/heart_eyes", "desc": "花痴眼冒心心，看到喜欢的东西或对方做了让自己心动的事"},
    {"path": "tired/yawn", "desc": "打哈欠，犯困了或对话有点无聊的时候自然地打个哈欠"},
    {"path": "tired/sleepy", "desc": "半睁眼睛，似睡非睡的样子"},
    {"path": "eating/eating_chips", "desc": "吃零食薯片，闲聊吃零食的轻松氛围，或者对方提到了吃的"},
]
```

每个 sticker 的 `desc` 是**中文语义描述**，用于 BGE 编码匹配。描述写得越贴合实际对话语境，匹配越准确。

## 文件结构

| 文件 | 说明 |
|------|------|
| `backend/app/core/cognitive.py` | Phase 7.5 BGE 选择 + Phase 8 存储 |
| `backend/app/core/personality.py` | `STICKER_DEFINITIONS` 定义 |
| `backend/app/api/routes/chat.py` | 用户 sticker 发送 + SSE sticker 事件 |
| `frontend/public/stickers/` | PNG 图片，按类别分子目录 |
| `frontend/src/components/Chat/MessageBubble.tsx` | sticker 消息渲染 |
| `frontend/src/components/Chat/InputBar.tsx` | 表情包选择器 |
| `frontend/src/hooks/useChat.ts` | sticker SSE 事件处理 |
| `frontend/src/types/index.ts` | `content_type` / `sticker_name` 类型 |

## 用户发送表情包

1. 用户点击 InputBar 的表情包图标
2. 弹出面板显示所有可用 sticker 的 PNG 预览
3. 选择后发送 `/category/name` 格式的文本消息
4. 后端 `chat.py` 检测到 sticker 格式 → 存储 `content_type='sticker'` → 返回 SSE sticker 事件
5. 同时发送描述性文本触发雨晴回复

## SSE 事件

```json
// sticker 事件（雨晴发送）
{"type": "sticker", "name": "happy/smile_blink", "conversation_id": "xxx"}

// sticker 事件（用户发送，后端 echo）
{"type": "sticker", "name": "sad/pat_pat", "sender": "user", "conversation_id": "xxx"}
```

## 历史消息

从数据库加载历史消息时，sticker 消息（`content_type='sticker'`）转换为文本注入 LLM 上下文：
```
[发送了 /happy/smile_blink 表情包]
```

这样 LLM 能"记住"之前发了什么 sticker，但不需要知道 sticker 系统的存在。

## 添加新 Sticker

1. 在 `frontend/public/stickers/{category}/` 放入 `{name}.png`
2. 在 `backend/app/core/personality.py` 的 `STICKER_DEFINITIONS` 添加一行：
   ```python
   {"path": "category/name", "desc": "中文语义描述，越详细越好"},
   ```
3. 重启后端，无需其他操作

## 匹配阈值

| 参数 | 值 | 说明 |
|------|-----|------|
| 选择阈值 | 0.35 | cosine similarity 高于此值才附加 sticker |
| 选择数量 | 1 | 只选最佳匹配，不选多个 |

如果匹配效果不佳，可以：
- 调低阈值（如 0.30）让 sticker 更频繁出现
- 优化 sticker 的 `desc` 描述，使其更贴合实际对话语义
