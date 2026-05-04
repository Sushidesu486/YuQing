# 记忆关联网络（Memory Graph）

> 实现日期：2025-05-04
> 状态：已实现

## 背景问题

语晴的原记忆系统是**扁平孤岛模型**——每条记忆独立存储和召回，记忆之间没有关联。导致：

1. **召回不完整**：用户聊"比赛"，只命中"ASC比赛"那条记忆，"压力"、"ACG兴趣"等相关记忆全部丢失
2. **合并策略缺失**：只做同类型合并，跨类型关联记忆无法合并
3. **MySQL fallback 无语义搜索**：`_search_via_mysql()` 只按 importance 排序
4. **mem0 v2.0.0 不支持 `add_relation()`**（平台付费 API），关联系统需自建

## 学术参考

基于三篇 2025 年论文设计：

| 论文 | 来源 | 采用的机制 |
|------|------|-----------|
| **Synapse** (arXiv 2601.02744) | 神经科学启发的记忆图 | 激活传播、Fan Effect、Lateral Inhibition |
| **ACT-R Inspired** (ACM HAI 2025) | 认知架构记忆模型 | access_factor boost |
| **Associa** (ACL Findings 2025) | 事件中心记忆图 | Triple Hybrid Scoring（PageRank → importance 替代） |

### 机制取舍

| 机制 | 决定 | 理由 |
|------|------|------|
| 完整激活传播（多轮迭代） | 采用 | 记忆库会随时间增长 |
| Fan Effect（出度归一化） | 采用 | 防止 hub 节点淹没 |
| Lateral Inhibition（Top-K 竞争） | 采用，可配置 | 防止噪声扩散 |
| 边时间衰减 | 不采用 | 用记忆 importance 间接实现，避免双重衰减 |
| Sigmoid 激活函数 | 暂不 | 小规模图不需要，记忆量 >500 时加入 |
| ACT-R B(m) | 部分 | 不替换 importance，补充 access_factor |
| Triple Hybrid Scoring | 采用 | semantic + activation + importance |

## 核心算法：激活传播

### 数据结构

```sql
CREATE TABLE IF NOT EXISTS memory_links (
    id CHAR(32) PRIMARY KEY,
    source_id CHAR(32) NOT NULL,         -- 记忆 A
    target_id CHAR(32) NOT NULL,         -- 记忆 B
    link_type VARCHAR(32) NOT NULL,      -- co_occurrence / semantic / consolidated
    strength FLOAT NOT NULL DEFAULT 0.5,  -- 链接强度 0-1
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_source (source_id),
    INDEX idx_target (target_id),
    UNIQUE INDEX idx_pair (source_id, target_id)
);
```

### 激活传播算法 (`_activation_spread`)

```
输入：种子记忆列表（mem0 语义搜索直接命中的结果）
输出：扩散召回的相关记忆列表

1. 初始化：
   - 种子记忆 activation = 1 - distance（mem0 语义相似度）
   - 加载子图（种子 + 一度邻居 + 相关边）

2. 迭代传播（最多 MAX_ITERATIONS=3 轮）：
   a. 对每个已激活节点，沿边向邻居传播激活值
   b. 每跳衰减：propagated = activation × edge.strength × DECAY_RATE(0.5)
   c. Fan Effect：propagated /= out_degree（出度归一化）
   d. 间接时间衰减：propagated × target.importance
   e. 累加到邻居的 activation（多次激活可叠加）
   f. Lateral Inhibition：每轮结束只保留 Top-K=15 高激活节点

3. 过滤：activation < THRESHOLD(0.1) 的记忆丢弃
4. 返回扩散召回的记忆（不含种子），按激活值降序
```

### Triple Hybrid Scoring (`_compute_relevance_score`)

在 `_build_layered_memory()` 中替代纯语义排序：

```
Score = semantic × 0.5 + activation × 0.3 + effective_importance × 0.2

其中：
- semantic = 1 - distance（mem0 cosine similarity）
- activation = 直接命中=1.0，扩散=传播激活值
- effective_importance = importance × access_factor
- access_factor = 0.5 + 0.5 × min(1, access_count / 10)  ← ACT-R inspired
```

## 链接创建

### 同轮共现链接（Co-occurrence）

在同一轮 LLM 记忆提取中，所有被提取的记忆两两建链：
- `link_type = 'co_occurrence'`
- `strength = 0.7`
- 3 条记忆 → C(3,2) = 3 条链接

### 合并继承（Consolidation）

记忆合并时，新记忆继承所有来源记忆的链接：
- 继承的链接 strength × 0.8 衰减
- 排除已合并的其他来源（避免自环）
- 额外创建 consolidated 类型链接

### 纠正转移（Correction）

记忆被纠正时，正确版本的新记忆继承旧记忆的所有链接。

## MySQL Fallback 升级

mem0 不可用时，`_search_via_mysql()` 改用本地 bge-small-zh-v1.5 做语义搜索：
- 加载最近访问的 200 条候选记忆
- 对 query 和每个候选计算 cosine similarity
- 按相似度降序返回 top_k
- embedding 模型不可用时降级到 importance 排序

## 配置项

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `MEMORY_LINK_ENABLED` | true | 启用记忆关联网络 |
| `MEMORY_LINK_MAX_ITERATIONS` | 3 | 激活传播最大迭代轮数 |
| `MEMORY_LINK_DECAY_RATE` | 0.5 | 每跳激活衰减率 |
| `MEMORY_LINK_FAN_EFFECT` | true | 启用 Fan Effect |
| `MEMORY_LINK_LATERAL_INHIBITION` | true | 启用 Lateral Inhibition |
| `MEMORY_LINK_LATERAL_K` | 15 | Lateral Inhibition 保留的 Top-K |
| `MEMORY_LINK_ACTIVATION_THRESHOLD` | 0.1 | 激活值召回阈值 |
| `MEMORY_LINK_CO_OCCURRENCE_STRENGTH` | 0.7 | 共现链接初始强度 |
| `MEMORY_LINK_CONSOLIDATION_STRENGTH` | 0.4 | 合并链接初始强度 |
| `MEMORY_LINK_STRENGTH_DECAY_ON_INHERIT` | 0.8 | 继承链接强度衰减系数 |

## 文件改动

| 文件 | 改动 |
|------|------|
| `backend/app/db/database.py` | 新增 `memory_links` 表 |
| `backend/app/config.py` | +11 项配置 |
| `backend/app/core/memory.py` | +`_create_co_occurrence_links()` +`_inherit_links()` +`_activation_spread()` +Triple Hybrid Scoring +MySQL embedding fallback |

## TODO: Sigmoid 激活函数

当记忆量增长到 500+ 条时，应加入 Sigmoid 激活函数：

```python
def _sigmoid_activation(raw_activation: float) -> float:
    """将累积激活值通过 sigmoid 映射到 [0,1]。"""
    return 1.0 / (1.0 + math.exp(-steepness * (raw_activation - threshold)))
```

加入时机：记忆平均数 > 500 时启用。Sigmoid 让激活值有平滑过渡区间，避免硬阈值在大规模图中导致"全有全无"。
