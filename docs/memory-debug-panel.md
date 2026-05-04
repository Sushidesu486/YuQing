# 记忆调试面板（Memory Debug Panel）

> 实现日期：2025-05-04
> 状态：已实现

## 概述

前端可视化调试面板，用于实时观察记忆系统状态、调试召回链路、浏览记忆内容、查看记忆关联图。

## 功能

### Tab 1: 概览 (Overview)
- 记忆系统开关状态（mem0 / 关联网络 / 去重 / 睡眠清理）
- 统计卡片：记忆总数、关联链接数、已合并数、已失效数、平均重要性、上次清理时间
- 类型分布条形图（按 memory_type 分组）
- 手动触发睡眠清理按钮

### Tab 2: 记忆列表 (Memories)
- 语义搜索框（调用 `/memories/search`，bge-small-zh 语义匹配）
- 类型筛选下拉（all / fact / preference / event / episodic / emotion / procedural）
- 记忆卡片：内容、类型 badge、重要性进度条、创建时间、删除按钮

### Tab 3: 召回调试 (Recall Debug)
- 输入框模拟用户消息，调用 `/memories/debug/recall`
- 手风琴展示 6 个召回阶段：
  1. mem0 直接命中（语义相似度 + 重要性）
  2. Pinned Facts（importance ≥ 0.8 的高权重记忆）
  3. 激活传播（种子数 / 扩散数 / 迭代数，每条记忆的激活值）
  4. 休眠唤醒（休眠天数）
  5. 最终排序（Triple Hybrid Score = 语义×0.5 + 激活×0.3 + 重要性×0.2）
  6. 分层注入结果（facts / events / episodic / behavior_rules / emotion_influences）

### Tab 4: 关联图 (Graph)
- SVG 圆形布局，节点按 memory_type 着色
- 边粗细按 link strength
- 悬停高亮关联链路，显示记忆内容 tooltip

## 入口

Header 右侧烧杯图标按钮，面板从右侧滑入（slideIn 动画）。

## 文件

| 文件 | 说明 |
|------|------|
| `frontend/src/components/Memory/MemoryDebugPanel.tsx` | 主面板组件（4 tabs + ErrorBoundary） |
| `frontend/src/components/Layout/Header.tsx` | 添加调试按钮 |
| `frontend/src/components/Layout/Layout.tsx` | 面板状态管理 |
| `frontend/src/services/api.ts` | `memoryApi` 对象 |
| `frontend/src/types/index.ts` | MemoryStats / MemoryItem / RecallDebugResult / MemoryLink / CleanupResult |
| `frontend/src/index.css` | slideIn 动画 |

## 后端 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/memories/debug/stats` | 记忆系统状态概览 |
| POST | `/api/memories/debug/recall` | 完整召回链路调试 |
| POST | `/api/memories/debug/cleanup` | 手动触发睡眠清理 |
| GET | `/api/memories/links` | 所有记忆关联链接（含 source/target 内容 JOIN） |
