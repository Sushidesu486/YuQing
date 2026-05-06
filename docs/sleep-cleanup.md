# 睡眠清理（Sleep Cleanup）

> 实现日期：2026-05-06
> 状态：已实现
> 执行时间：每天早上 7:00（可配置 `MEMORY_SLEEP_CLEANUP_HOUR`）

---

## 概述

模拟人类睡眠中的记忆巩固过程，每天自动对长期记忆进行 5 阶段维护。灵感来自神经科学研究中的突触稳态假说（SHY）和 ZenBrain 的选择性 Replay 机制。

## 学术背景

| 来源 | 采用的机制 | 核心思想 |
|------|-----------|---------|
| **突触稳态假说（SHY）** (Tononi & Cirelli, 2003) | 突触归一化 | 睡眠中等比压缩所有突触连接强度，防止"通胀"。高重要性记忆通过白天的 Replay 重新强化 |
| **ZenBrain TAG 评分** | 选择性 Replay | replay_priority = 0.35×reward + 0.25×surprise + 0.20×recency + 0.20×salience。高 TAG 记忆在睡眠中被强化 |
| **ZenBrain 三时间尺度衰减** | 长期保留 | S_deep(t) = S₀ × ln(1 + t/τ)，深度睡眠中的保留函数 |

## 5 个阶段

```
每天 7:00 自动执行
    │
    ▼
Phase 1: 突触归一化（Synaptic Downscaling）
    │  importance *= (1 - 0.03)  对所有记忆等比压缩
    │  防止重要性通胀，模拟 SHY 的总体突触 weaken
    │
    ▼
Phase 2: 选择性 Replay（Selective Replay）
    │  计算 TAG 评分 → 强化高 TAG 记忆（+0.05）
    │                    → 减弱低 TAG 记忆（-0.03）
    │  模拟睡眠中重要记忆被重新激活巩固
    │
    ▼
Phase 3: 聚类合并（Cluster Merge）
    │  BGE embedding 聚类（cosine > 0.70）
    │  组内 ≥ 3 条 → LLM 合并为精炼总结
    │  旧记忆标记 is_consolidated=1
    │
    ▼
Phase 4: 休眠剪枝（Prune Stale）
    │  三级删除策略：
    │  - importance < 0.05 且 > 30天未访问 → 删除
    │  - importance < 0.10 且 > 60天未访问 → 删除
    │  - importance < 0.15 且 > 90天未访问 → 删除
    │  同时清理弱关联链接（strength < 0.1）
    │
    ▼
Phase 5: 孤儿链接清理（Orphan Links）
       DELETE FROM memory_links
       WHERE source_id NOT IN (SELECT id FROM memories)
          OR target_id NOT IN (SELECT id FROM memories)
```

## TAG 评分公式

```
TAG = 0.35 × reward + 0.25 × surprise + 0.20 × recency + 0.20 × salience

其中：
- reward = importance（记忆本身的重要性，0-1）
- surprise = 1 - average_cosine_similarity_to_other_memories（越独特越高）
- recency = 1 / (1 + days_since_access)，最近访问过的高
- salience = importance × (1 + access_count × 0.1)（被多次召回的加权重要性）
```

## 配置参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `MEMORY_SLEEP_CLEANUP_ENABLED` | true | 启用睡眠清理 |
| `MEMORY_SLEEP_CLEANUP_HOUR` | 7 | 执行时间（小时） |
| `MEMORY_SLEEP_CLEANUP_CLUSTER_MERGE` | true | 启用聚类合并 |
| `MEMORY_SLEEP_CLEANUP_CLUSTER_THRESHOLD` | 0.70 | 聚类合并相似度阈值 |
| `SLEEP_DOWNSCALE_ENABLED` | true | 启用突触归一化 |
| `SLEEP_DOWNSCALE_FACTOR` | 0.03 | 归一化缩小系数 |
| `SLEEP_REPLAY_ENABLED` | true | 启用选择性 Replay |
| `SLEEP_REPLAY_STRENGTHEN` | 0.05 | 高 TAG 记忆强化幅度 |
| `SLEEP_REPLAY_WEAKEN` | 0.03 | 低 TAG 记忆减弱幅度 |
| `SLEEP_PRUNE_ENABLED` | true | 启用休眠剪枝 |

## 手动触发

可通过 API 或调试面板手动触发：
```bash
# API
POST /api/memories/debug/cleanup

# 调试面板 → 概览 Tab → "手动触发睡眠清理" 按钮
```

## 相关文件

| 文件 | 说明 |
|------|------|
| `backend/app/core/memory.py` | `_synaptic_downscaling()`, `_selective_replay()`, `_cluster_merge_memories()`, `_prune_stale()`, `_cleanup_orphan_links()` |
| `backend/app/config.py` | 睡眠清理配置参数 |
