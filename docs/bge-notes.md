# BGE 嵌入模型使用笔记

> 最后更新：2026-05-06
> 适用于：YuQing 项目中所有 BGE 使用场景

---

## 什么是 BGE

BGE（BAAI General Embedding）是北京智源研究院开发的文本嵌入模型系列，将任意文本映射为固定维度的稠密向量（dense vector）。语义相近的文本在向量空间中距离更近。

**核心用途**：通过 cosine similarity 比较两段文本的语义相似度。

## 模型选择

| 模型 | 维度 | 中文效果 | 推理速度 | 项目选择 |
|------|------|---------|---------|---------|
| `BAAI/bge-small-zh-v1.5` | 512 | 良好 | 快 | 早期使用（已升级） |
| `BAAI/bge-base-zh-v1.5` | 768 | 优秀 | 中等 | **当前使用** |
| `BAAI/bge-large-zh-v1.5` | 1024 | 最优 | 慢 | 未使用 |

**为什么选 base 而不是 small**：small (512维) 在记忆去重任务中误判率较高（0.90 阈值下仍有相似但不完全相同的记忆被误判为重复）。base (768维) 在精度和速度之间有更好的平衡。

**为什么不用 large**：单用户场景下 base 的精度已足够，large 推理慢约 2 倍，且占用更多内存。

## 本地部署

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("BAAI/bge-base-zh-v1.5")
# 首次运行会从 HuggingFace 下载模型到 ~/.cache/huggingface/
# 后续使用缓存，无需联网

embedding = model.encode("你好世界")  # → numpy array, shape=(768,)
```

**内存占用**：约 1.5 GB（模型权重 + sentence-transformers 框架）

**缓存位置**：`~/.cache/huggingface/hub/models--BAAI--bge-base-zh-v1.5/`

## 在 YuQing 中的使用场景

### 1. 记忆语义搜索（memory.py）

最主要的用途。将用户消息 encode 后与候选记忆的 embedding 计算 cosine similarity，召回语义最相关的记忆。

```python
# backend/app/core/memory.py — _get_embedding_model()
model = _get_embedding_model()  # 全局单例，懒加载
query_emb = model.encode(query).tolist()
```

**使用方式**：
- `_search_via_mysql()`：MySQL 降级搜索，加载 200 条候选 → 批量 encode → cosine 排序
- `extract_and_store_memories()`：写入去重，新记忆与已有记忆比对（> 0.90 跳过，0.75-0.90 合并）
- `consolidate_memories()`：聚类合并，相似记忆分组（> 0.75 归一组）
- `_cluster_merge_memories()`：睡眠清理中的聚类合并
- `self_*` 记忆的语义去重和巩固

### 2. 表情包语义匹配（cognitive.py）

将 LLM 回复文本 encode 后与每张 sticker 的描述 encode 做 cosine similarity，选择最贴合语境的 sticker。

```python
# backend/app/core/cognitive.py — Phase 7.5
response_emb = model.encode(full_response).tolist()
for s in STICKER_DEFINITIONS:
    sticker_emb = model.encode(s["desc"]).tolist()
    sim = cosine_similarity(response_emb, sticker_emb)
```

**关键区别**：这里 encode 的是中文语义描述（如"嘟嘴不高兴，被调侃或被开玩笑时傲娇地表达不满"），而不是图片。匹配的是"回复文本的语义"和"sticker 使用场景的语义"之间的相似度。

### 3. 未来可能的使用

- **记忆激活传播**中的语义边创建（目前基于 co-occurrence）
- **用户偏好语义匹配**（目前基于关键词正则）
- **对话摘要相似度**去重

## Cosine Similarity

```python
import numpy as np

def cosine_similarity(a, b):
    a, b = np.array(a), np.array(b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
```

- 范围：-1.0（完全相反）到 1.0（完全相同）
- YuQing 中使用场景的典型值：
  - 相同/几乎相同文本：> 0.95
  - 语义相似但不完全相同：0.75 - 0.90
  - 相关但不相似：0.50 - 0.75
  - 基本无关：< 0.50

## 性能优化

### 批量 Encode

```python
# 慢：逐条 encode
for text in texts:
    emb = model.encode(text)

# 快：批量 encode
embeddings = model.encode(texts)  # 一次性 encode 所有文本
```

`sentence-transformers` 的 `encode()` 方法接受 list 输入，内部会做 batched inference，比循环快 3-5 倍。

### 全局单例

```python
# backend/app/core/memory.py
_embedding_model = None

def _get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer
        _embedding_model = SentenceTransformer(settings.EMBEDDING_MODEL)
    return _embedding_model
```

模型只加载一次，后续所有模块复用同一实例。

### Embedding 缓存

```python
_mem_embedding_cache: Dict[str, dict] = {}

# 缓存结构：{memory_id: {"emb": [...], "content": "..."}}
# 用于避免重复 encode 同一条记忆
```

记忆系统中维护了 embedding 缓存，避免每次操作都重新 encode 同一条记忆。

## 注意事项

1. **中文不需要额外分词**：BGE-zh 模型内置中文 tokenizer，直接传入中文句子即可
2. **max_seq_length**：默认 512 tokens，超过会截断。正常对话内容不会超限
3. **GPU 加速**：如果有 CUDA GPU，`SentenceTransformer` 会自动使用。Mac M 系列不支持 CUDA，使用 CPU
4. **首次加载耗时**：首次调用 `encode()` 时会加载模型权重，约需 2-3 秒。后续调用秒级
5. **与 mem0 的关系**：早期 YuQing 使用 mem0 内置的 bge-small-zh 做向量存储。现已替换为直接使用 BGE + MySQL，不再依赖 mem0 的嵌入能力

## 参考资源

- [BGE GitHub](https://github.com/FlagOpen/FlagEmbedding) — 官方仓库
- [BGE HuggingFace](https://huggingface.co/BAAI/bge-base-zh-v1.5) — 模型页面
- [sentence-transformers 文档](https://www.sbert.net/) — Python 库文档
