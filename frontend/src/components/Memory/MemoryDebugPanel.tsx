import React, { useState, useEffect, useCallback, useRef, useMemo, Component } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import { memoryApi } from '../../services/api';
import type {
  MemoryStats,
  MemoryItem,
  RecallDebugResult,
  MemoryLink,
  CleanupResult,
} from '../../types';

interface Props {
  open: boolean;
  onClose: () => void;
}

/* ── helpers ────────────────────────────────────────────── */

const TYPE_COLORS: Record<string, string> = {
  fact: 'bg-blue-100 text-blue-700',
  preference: 'bg-purple-100 text-purple-700',
  event: 'bg-green-100 text-green-700',
  episodic: 'bg-orange-100 text-orange-700',
  emotion: 'bg-red-100 text-red-700',
  procedural: 'bg-gray-100 text-gray-700',
};
const TYPE_NODE_COLORS: Record<string, string> = {
  fact: '#3b82f6',
  preference: '#8b5cf6',
  event: '#22c55e',
  episodic: '#f97316',
  emotion: '#ef4444',
  procedural: '#6b7280',
  self_interest: '#ec4899',
  self_experience: '#f59e0b',
  self_opinion: '#06b6d4',
  self_habit: '#14b8a6',
};
const DEFAULT_NODE_COLOR = '#9ca3af';
const TYPE_OPTIONS = ['all', 'fact', 'preference', 'event', 'episodic', 'emotion', 'procedural'];

function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return '-';
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return '-';
  return d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
}

function StatusBadge({ on, label }: { on: boolean; label: string }) {
  return (
    <span className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full ${on ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${on ? 'bg-green-500' : 'bg-gray-400'}`} />
      {label} {on ? 'ON' : 'OFF'}
    </span>
  );
}

function ImportanceBar({ value }: { value: number | undefined }) {
  const v = value ?? 0;
  return (
    <div className="flex items-center gap-1.5">
      <div className="w-16 h-1.5 bg-gray-200 rounded-full overflow-hidden">
        <div className="h-full bg-blue-500 rounded-full" style={{ width: `${Math.round(v * 100)}%` }} />
      </div>
      <span className="text-[10px] text-gray-400">{v.toFixed(2)}</span>
    </div>
  );
}

function ScoreBar({ label, value, color }: { label: string; value: number | undefined; color: string }) {
  const v = value ?? 0;
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="text-gray-500 w-16 shrink-0">{label}</span>
      <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${Math.round(v * 100)}%` }} />
      </div>
      <span className="text-gray-400 w-8 text-right">{v.toFixed(3)}</span>
    </div>
  );
}

/* ── Tab: Overview ──────────────────────────────────────── */

function OverviewTab({ onCleanup }: { onCleanup: (r: CleanupResult) => void }) {
  const [stats, setStats] = useState<MemoryStats | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await memoryApi.getStats();
      setStats(data);
    } catch (e) { console.error('[Memory Debug]', e); }
    setLoading(false);
  }, []);

  useEffect(() => { if (stats === null) load(); }, [load, stats]);

  const [cleaning, setCleaning] = useState(false);
  const handleCleanup = async () => {
    setCleaning(true);
    try {
      const r = await memoryApi.cleanup();
      onCleanup(r);
      setStats(null); // force reload
    } catch (e) { console.error('[Memory Debug]', e); }
    setCleaning(false);
  };

  if (loading) return <div className="flex items-center justify-center py-16 text-sm text-gray-400">加载中...</div>;
  if (!stats) return null;

  const totalTypes = Object.values(stats.by_type).reduce((s, v) => s + v.count, 0);
  const maxCount = Math.max(...Object.values(stats.by_type).map(v => v.count), 1);

  return (
    <div className="space-y-4">
      {/* Feature toggles */}
      <div className="flex flex-wrap gap-2">
        <StatusBadge on={stats.memory_link_enabled} label="关联" />
        <StatusBadge on={stats.dedup_enabled} label="去重" />
        <StatusBadge on={stats.sleep_cleanup_enabled} label="睡眠清理" />
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-3 gap-2">
        <StatCard label="记忆总数" value={stats.total_memories} />
        <StatCard label="关联链接" value={stats.total_links} />
        <StatCard label="已合并" value={stats.consolidated_count} />
        <StatCard label="已失效" value={stats.invalid_count} />
        <StatCard label="平均重要性" value={stats.avg_importance} isFloat />
        <StatCard label="上次清理" value={stats.last_sleep_cleanup ? formatDate(stats.last_sleep_cleanup) : '从未'} isText />
      </div>

      {/* Type distribution */}
      <div>
        <div className="text-xs font-medium text-gray-500 mb-2">类型分布 ({totalTypes})</div>
        <div className="space-y-1.5">
          {Object.entries(stats.by_type).map(([type, info]) => (
            <div key={type} className="flex items-center gap-2">
              <span className={`text-[10px] px-1.5 py-0.5 rounded ${TYPE_COLORS[type] || 'bg-gray-100 text-gray-600'}`}>
                {type}
              </span>
              <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
                <div className="h-full bg-blue-400 rounded-full" style={{ width: `${(info.count / maxCount) * 100}%` }} />
              </div>
              <span className="text-[10px] text-gray-400 w-6 text-right">{info.count}</span>
              <span className="text-[10px] text-gray-300">avg {info.avg_importance}</span>
            </div>
          ))}
          {Object.keys(stats.by_type).length === 0 && (
            <div className="text-xs text-gray-400 py-2">暂无记忆</div>
          )}
        </div>
      </div>

      {/* Cleanup */}
      <button
        onClick={handleCleanup}
        disabled={cleaning}
        className="w-full py-2 text-xs font-medium rounded-lg border border-gray-200 text-gray-600 hover:bg-gray-50 disabled:opacity-50 transition"
      >
        {cleaning ? '清理中...' : '手动触发睡眠清理'}
      </button>
    </div>
  );
}

function StatCard({ label, value, isFloat, isText }: { label: string; value: string | number; isFloat?: boolean; isText?: boolean }) {
  return (
    <div className="bg-gray-50 rounded-lg p-2.5 text-center">
      <div className="text-lg font-semibold text-gray-800">
        {isText ? value : isFloat ? (value as number).toFixed(3) : value}
      </div>
      <div className="text-[10px] text-gray-400 mt-0.5">{label}</div>
    </div>
  );
}

/* ── Tab: Memory List ───────────────────────────────────── */

function MemoriesTab() {
  const [items, setItems] = useState<MemoryItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [typeFilter, setTypeFilter] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = useCallback(async (q?: string) => {
    setLoading(true);
    try {
      const data = q?.trim()
        ? await memoryApi.search(q.trim(), 50)
        : await memoryApi.list(typeFilter === 'all' ? undefined : typeFilter, 50);
      setItems(data);
    } catch { setItems([]); }
    setLoading(false);
  }, [typeFilter]);

  useEffect(() => { load(searchQuery); }, [load, searchQuery]);

  const handleSearch = (val: string) => {
    setSearchQuery(val);
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => load(val), 300);
  };

  const handleDelete = async (id: string) => {
    try {
      await memoryApi.delete(id);
      setItems(prev => prev.filter(m => m.id !== id));
    } catch (e) { console.error('[Memory Debug]', e); }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Search & filter */}
      <div className="flex gap-2 pb-3">
        <div className="flex-1 relative">
          <svg className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            type="text"
            value={searchQuery}
            onChange={e => handleSearch(e.target.value)}
            placeholder="搜索记忆内容..."
            className="w-full pl-8 pr-2 py-1.5 text-xs rounded-lg border border-gray-200 outline-none focus:border-blue-400 bg-gray-50"
          />
        </div>
        <select
          value={typeFilter}
          onChange={e => setTypeFilter(e.target.value)}
          className="text-xs rounded-lg border border-gray-200 px-2 py-1.5 bg-gray-50 outline-none focus:border-blue-400"
        >
          {TYPE_OPTIONS.map(t => (
            <option key={t} value={t}>{t === 'all' ? '全部类型' : t}</option>
          ))}
        </select>
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto -mx-1 space-y-1.5">
        {loading && <div className="py-8 text-center text-xs text-gray-400">加载中...</div>}
        {!loading && items.length === 0 && (
          <div className="py-8 text-center text-xs text-gray-400">暂无记忆</div>
        )}
        {items.map(item => (
          <div key={item.id} className="group relative p-2.5 rounded-lg border border-gray-100 hover:border-gray-200 bg-white">
            <div className="flex items-start justify-between gap-2">
              <p className="text-xs text-gray-700 leading-relaxed flex-1 line-clamp-3">{item.content}</p>
              <button
                onClick={() => handleDelete(item.id)}
                className="shrink-0 p-1 rounded text-gray-300 hover:text-red-500 opacity-0 group-hover:opacity-100 transition"
                title="删除"
              >
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
              </button>
            </div>
            <div className="flex items-center gap-2 mt-1.5">
              <span className={`text-[10px] px-1.5 py-0.5 rounded ${TYPE_COLORS[item.memory_type || ''] || TYPE_COLORS.fact}`}>
                {item.memory_type || 'unknown'}
              </span>
              <ImportanceBar value={item.importance} />
              {item.created_at && <span className="text-[10px] text-gray-300 ml-auto">{formatDate(item.created_at)}</span>}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ── Tab: Recall Debug ──────────────────────────────────── */

function RecallDebugTab() {
  const [query, setQuery] = useState('');
  const [result, setResult] = useState<RecallDebugResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({
    semantic_search: true, pinned: true, spread: true, dormant: true, final: true, layered: true,
  });

  const toggle = (key: string) => setExpanded(prev => ({ ...prev, [key]: !prev[key] }));

  const handleRecall = async () => {
    if (!query.trim()) return;
    setLoading(true);
    setResult(null);
    try {
      const data = await memoryApi.recall(query.trim());
      setResult(data);
    } catch (e) { console.error('[Memory Debug]', e); }
    setLoading(false);
  };

  const stages = [
    { key: 'semantic_search', label: '语义搜索', color: 'bg-green-500', count: result?.stage_semantic_search?.length ?? 0 },
    { key: 'pinned', label: 'Pinned Facts', color: 'bg-blue-500', count: result?.stage_pinned?.length ?? 0 },
    { key: 'spread', label: '激活传播', color: 'bg-purple-500', count: result?.stage_activation_spread?.spread_memories?.length ?? 0 },
    { key: 'dormant', label: '休眠唤醒', color: 'bg-yellow-500', count: result?.stage_dormant?.length ?? 0 },
    { key: 'final', label: '最终排序', color: 'bg-red-500', count: result?.stage_final_scored?.length ?? 0 },
    { key: 'layered', label: '分层注入', color: 'bg-gray-500', count: 1 },
  ];

  return (
    <div className="flex flex-col h-full">
      {/* Input */}
      <div className="flex gap-2 pb-3">
        <input
          type="text"
          value={query}
          onChange={e => setQuery(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleRecall()}
          placeholder="输入一条用户消息测试召回..."
          className="flex-1 px-3 py-2 text-xs rounded-lg border border-gray-200 outline-none focus:border-blue-400 bg-gray-50"
        />
        <button
          onClick={handleRecall}
          disabled={loading || !query.trim()}
          className="px-4 py-2 text-xs font-medium rounded-lg bg-blue-500 text-white hover:bg-blue-600 disabled:opacity-50 transition"
        >
          {loading ? '...' : '测试'}
        </button>
      </div>

      {!result && !loading && (
        <div className="flex-1 flex items-center justify-center text-xs text-gray-400">
          输入消息后点击"测试"查看召回链路
        </div>
      )}

      {loading && (
        <div className="flex-1 flex items-center justify-center text-xs text-gray-400">召回中...</div>
      )}

      {result && (
        <div className="flex-1 overflow-y-auto space-y-2">
          {/* Summary bar */}
          <div className="flex items-center gap-2 text-[10px] text-gray-400 px-1">
            <span>记忆: {result.total_memories_count}</span>
            <span>|</span>
            <span>链接: {result.memory_links_count}</span>
          </div>

          {/* Stages accordion */}
          {stages.map(stage => (
            <div key={stage.key} className="border border-gray-100 rounded-lg overflow-hidden">
              <button
                onClick={() => toggle(stage.key)}
                className="w-full flex items-center gap-2 px-3 py-2 text-xs font-medium text-gray-700 hover:bg-gray-50 transition"
              >
                <span className={`w-2 h-2 rounded-full ${stage.color} shrink-0`} />
                {stage.label}
                <span className="text-gray-400 font-normal">({stage.count})</span>
                <svg className={`w-3.5 h-3.5 ml-auto text-gray-400 transition-transform ${expanded[stage.key] ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </button>

              {expanded[stage.key] && (
                <div className="px-3 pb-3 border-t border-gray-50">
                  {/* mem0 stage */}
                  {stage.key === 'semantic_search' && (result.stage_semantic_search?.length ? result.stage_semantic_search.map((m, i) => (
                    <StageItem key={i} content={m.content} type={m.memory_type}>
                      <ScoreBar label="语义相似度" value={m.semantic_sim} color="bg-green-500" />
                      {m.importance !== undefined && <ScoreBar label="重要性" value={m.importance} color="bg-blue-500" />}
                    </StageItem>
                  )) : <EmptyStage />)}

                  {/* pinned stage */}
                  {stage.key === 'pinned' && (result.stage_pinned?.length ? result.stage_pinned.map((m, i) => (
                    <StageItem key={i} content={m.content} type={m.memory_type}>
                      {m.importance !== undefined && <ScoreBar label="重要性" value={m.importance} color="bg-blue-500" />}
                    </StageItem>
                  )) : <EmptyStage />)}

                  {/* activation spread stage */}
                  {stage.key === 'spread' && (() => {
                    const sp = result.stage_activation_spread;
                    return sp && sp.enabled ? (
                      <div className="mt-2 space-y-1">
                        <div className="text-[10px] text-gray-400">
                          种子: {sp.seed_count} | 扩散: {sp.spread_count} | 迭代: {sp.iterations}
                        </div>
                        {sp.spread_memories?.map((m, i) => (
                          <StageItem key={i} content={m.content} type={m.memory_type}>
                            <ScoreBar label="激活值" value={m.activation} color="bg-purple-500" />
                            {m.importance !== undefined && <ScoreBar label="重要性" value={m.importance} color="bg-blue-500" />}
                          </StageItem>
                        ))}
                      </div>
                    ) : <div className="text-[10px] text-gray-400 py-2">未启用</div>;
                  })()}

                  {/* dormant stage */}
                  {stage.key === 'dormant' && (result.stage_dormant?.length ? result.stage_dormant.map((m, i) => (
                    <StageItem key={i} content={m.content} type={m.memory_type}>
                      <ScoreBar label="休眠天数" value={m.dormant_days ? Math.min(m.dormant_days / 30, 1) : undefined} color="bg-yellow-500" />
                      {m.dormant_days !== undefined && <span className="text-[10px] text-gray-400">{m.dormant_days.toFixed(1)} 天</span>}
                    </StageItem>
                  )) : <EmptyStage />)}

                  {/* final scored stage */}
                  {stage.key === 'final' && (result.stage_final_scored?.length ? result.stage_final_scored.map((m, i) => (
                    <StageItem key={i} content={m.content} type={m.memory_type}>
                      <ScoreBar label="综合评分" value={m.hybrid_score} color="bg-red-500" />
                      <ScoreBar label="语义" value={m.semantic_sim} color="bg-green-500" />
                      <ScoreBar label="激活" value={m.activation} color="bg-purple-500" />
                      <ScoreBar label="重要性" value={m.importance} color="bg-blue-500" />
                    </StageItem>
                  )) : <EmptyStage />)}

                  {/* layered stage */}
                  {stage.key === 'layered' && result.stage_layered && (
                    <div className="mt-2 space-y-2">
                      <LayeredSection title="Facts" items={result.stage_layered.facts} />
                      <LayeredSection title="Events" items={result.stage_layered.events} />
                      <LayeredSection title="Episodic" items={result.stage_layered.episodic?.map(e => ({ content: e.content }))} />
                      {result.stage_layered.behavior_rules?.length > 0 && (
                        <div>
                          <div className="text-[10px] font-medium text-gray-500 mb-1">Behavior Rules</div>
                          {result.stage_layered.behavior_rules.map((r, i) => (
                            <div key={i} className="text-xs text-gray-600 pl-2 border-l-2 border-gray-200 mb-1">{r}</div>
                          ))}
                        </div>
                      )}
                      {result.stage_layered.emotion_influences?.length > 0 && (
                        <div>
                          <div className="text-[10px] font-medium text-gray-500 mb-1">Emotion Influences</div>
                          {result.stage_layered.emotion_influences.map((e, i) => (
                            <div key={i} className="text-xs text-gray-600 pl-2 border-l-2 border-red-200 mb-1">
                              {e.trigger} → valence {e.expected_valence > 0 ? '+' : ''}{e.expected_valence}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function StageItem({ content, type, children }: { content: string; type?: string; children?: React.ReactNode }) {
  return (
    <div className="mt-2 p-2 rounded bg-gray-50">
      <div className="flex items-start gap-1.5">
        {type && <span className={`text-[10px] px-1 py-0.5 rounded shrink-0 mt-0.5 ${TYPE_COLORS[type] || TYPE_COLORS.fact}`}>{type}</span>}
        <p className="text-xs text-gray-700 leading-relaxed line-clamp-3">{content}</p>
      </div>
      {children && <div className="mt-1.5 space-y-1 pl-0.5">{children}</div>}
    </div>
  );
}

function EmptyStage() {
  return <div className="text-[10px] text-gray-400 py-2">无匹配记忆</div>;
}

function LayeredSection({ title, items }: { title: string; items: Array<{ content: string; id?: string; memory_type?: string; created_at_relative?: string }> }) {
  if (!items?.length) return null;
  return (
    <div>
      <div className="text-[10px] font-medium text-gray-500 mb-1">{title} ({items.length})</div>
      {items.map((item, i) => (
        <div key={item.id ?? i} className="text-xs text-gray-600 pl-2 border-l-2 border-gray-200 mb-1">
          {item.content}
          {item.created_at_relative && <span className="text-[10px] text-gray-400 ml-1">({item.created_at_relative})</span>}
        </div>
      ))}
    </div>
  );
}

/* ── Tab: Graph (react-force-graph-2d) ──────────────────── */

interface GraphNode {
  id: string;
  name: string;
  memory_type?: string;
  importance?: number;
  val?: number;
  color: string;
  created_at?: string;
}

interface GraphLink {
  source: string;
  target: string;
  strength: number;
}

function GraphTab() {
  const [memories, setMemories] = useState<MemoryItem[]>([]);
  const [links, setLinks] = useState<MemoryLink[]>([]);
  const [loading, setLoading] = useState(true);
  const [hoveredNode, setHoveredNode] = useState<GraphNode | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const graphRef = useRef<any>(null);

  useEffect(() => {
    (async () => {
      const [mRes, lRes] = await Promise.allSettled([
        memoryApi.list(undefined, 999),
        memoryApi.getLinks(),
      ]);
      if (mRes.status === 'fulfilled') setMemories(mRes.value);
      else console.error('[Memory Debug] list failed:', mRes.reason);
      if (lRes.status === 'fulfilled') setLinks(lRes.value);
      else console.error('[Memory Debug] links failed:', lRes.reason);
      setLoading(false);
    })();
  }, []);

  const memoryMap = useMemo(() => {
    const map = new Map<string, MemoryItem>();
    memories.forEach(m => map.set(m.id, m));
    return map;
  }, [memories]);

  // Stable graph data — only changes when memories/links change, NOT on hover/search
  const graphData = useMemo(() => {
    const memIds = new Set(memories.map(m => m.id));
    const validLinks = links.filter(l => memIds.has(l.source_id) && memIds.has(l.target_id));

    const nodes: GraphNode[] = memories.map(m => ({
      id: m.id,
      name: m.content,
      memory_type: m.memory_type,
      importance: m.importance,
      val: Math.max(3, Math.min(15, (m.importance ?? 0.5) * 12)),
      color: TYPE_NODE_COLORS[m.memory_type || ''] || DEFAULT_NODE_COLOR,
      created_at: m.created_at,
    }));

    const graphLinks: GraphLink[] = validLinks.map(l => ({
      source: l.source_id,
      target: l.target_id,
      strength: l.strength,
    }));

    return { nodes, links: graphLinks };
  }, [memories, links]);

  // Hover highlight — separate from graphData to prevent re-animation
  const linkedIds = useMemo(() => {
    const ids = new Set<string>();
    if (!hoveredNode) return ids;
    ids.add(hoveredNode.id);
    links.forEach(l => {
      if (l.source_id === hoveredNode.id) ids.add(l.target_id);
      if (l.target_id === hoveredNode.id) ids.add(l.source_id);
    });
    return ids;
  }, [hoveredNode, links]);

  // Search match highlight
  const searchMatchIds = useMemo(() => {
    if (!searchQuery.trim()) return null; // null = no search active
    const q = searchQuery.trim().toLowerCase();
    const ids = new Set<string>();
    graphData.nodes.forEach(n => {
      if (n.name.toLowerCase().includes(q)) ids.add(n.id);
    });
    return ids;
  }, [searchQuery, graphData]);

  // Focus camera on first search match
  useEffect(() => {
    if (!searchMatchIds || searchMatchIds.size === 0 || !graphRef.current) return;
    const firstId = [...searchMatchIds][0];
    const node = graphData.nodes.find(n => n.id === firstId);
    if (node && node.x !== undefined && node.y !== undefined) {
      graphRef.current.centerAt(node.x, node.y, 800);
      graphRef.current.zoom(2, 800);
    }
  }, [searchMatchIds, graphData]);

  // Whether any highlight mode is active (hover or search)
  const highlightIds = useMemo(() => {
    if (linkedIds.size > 0) return linkedIds;
    if (searchMatchIds) return searchMatchIds;
    return null;
  }, [linkedIds, searchMatchIds]);

  if (loading) return <div className="flex items-center justify-center py-16 text-sm text-gray-400">加载中...</div>;

  const usedTypes = [...new Set(memories.map(m => m.memory_type).filter(Boolean))];
  const matchCount = searchMatchIds?.size;

  return (
    <div className="flex flex-col h-full">
      {/* Search + legend bar */}
      <div className="flex items-center gap-3 mb-2">
        <div className="flex-1 relative">
          <svg className="absolute left-2 top-1/2 -translate-y-1/2 w-3 h-3 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            type="text"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            placeholder="搜索记忆内容定位..."
            className="w-full pl-7 pr-2 py-1 text-xs rounded border border-gray-200 outline-none focus:border-blue-400 bg-gray-50"
          />
        </div>
        <div className="text-xs text-gray-400 shrink-0">
          {memories.length} memories, {graphData.links.length}条关联
        </div>
      </div>

      {/* Type legend + search result count */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex flex-wrap gap-x-3 gap-y-0.5">
          {usedTypes.map(type => (
            <div key={type} className="flex items-center gap-1">
              <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: TYPE_NODE_COLORS[type] || DEFAULT_NODE_COLOR }} />
              <span className="text-[9px] text-gray-500">{type}</span>
            </div>
          ))}
        </div>
        {matchCount !== undefined && (
          <span className="text-[10px] text-blue-500">{matchCount} 条匹配</span>
        )}
      </div>

      <div className="flex-1 relative">
        <ForceGraph2D
          ref={graphRef}
          graphData={graphData}
          nodeLabel={node => {
            const m = memoryMap.get(node.id);
            if (!m) return '';
            const lines = [
              m.content.length > 80 ? m.content.slice(0, 80) + '...' : m.content,
              `[${m.memory_type || 'unknown'}] importance: ${(m.importance ?? 0).toFixed(2)}`,
              m.created_at ? formatDate(m.created_at) : '',
            ].filter(Boolean);
            return lines.join('\n');
          }}
          nodeColor={node => {
            if (highlightIds) {
              return highlightIds.has(node.id) ? node.color : 'rgba(200,200,200,0.15)';
            }
            return node.color;
          }}
          nodeVal={node => node.val}
          nodeCanvasObjectMode={() => 'after'}
          nodeCanvasObject={(node, ctx, globalScale) => {
            const label = memoryMap.get(node.id)?.content ?? '';
            if (!label) return;
            const fontSize = 10 / globalScale;
            ctx.font = `${fontSize}px Sans-Serif`;
            const truncated = label.length > 18 ? label.slice(0, 18) + '...' : label;
            const textWidth = ctx.measureText(truncated).width;
            const x = node.x ?? 0;
            const y = node.y ?? 0;

            // Text background pill
            const bgPadX = fontSize * 0.4;
            const bgPadY = fontSize * 0.2;
            ctx.fillStyle = 'rgba(255,255,255,0.8)';
            ctx.beginPath();
            ctx.roundRect(
              x - textWidth / 2 - bgPadX,
              y - fontSize / 2 - bgPadY,
              textWidth + bgPadX * 2,
              fontSize + bgPadY * 2,
              fontSize * 0.3,
            );
            ctx.fill();

            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillStyle = '#374151';
            ctx.fillText(truncated, x, y);
          }}
          linkWidth={link => 1 + link.strength * 3}
          linkColor={link => {
            if (hoveredNode) {
              const src = typeof link.source === 'object' ? link.source.id : link.source;
              const tgt = typeof link.target === 'object' ? link.target.id : link.target;
              if (src === hoveredNode.id || tgt === hoveredNode.id) return 'rgba(99,102,241,0.7)';
              return 'rgba(0,0,0,0.03)';
            }
            return 'rgba(99,102,241,0.15)';
          }}
          linkDirectionalArrowLength={0}
          onNodeHover={node => {
            setHoveredNode(node as GraphNode | null);
          }}
          onNodeDragEnd={node => {
            if (node) {
              node.fx = node.x;
              node.fy = node.y;
            }
          }}
          cooldownTicks={100}
          enableNodeDrag={true}
          enableZoomInteraction={true}
          enablePanInteraction={true}
          d3={{ forceCharge: { strength: -120 }, forceLink: { distance: 100 } }}
          backgroundColor="#f9fafb"
        />
      </div>
    </div>
  );
}

/* ── Main Panel ─────────────────────────────────────────── */

class TabErrorBoundary extends Component<
  { children: React.ReactNode; onReset: () => void },
  { hasError: boolean }
> {
  state = { hasError: false };
  static getDerivedStateFromError() { return { hasError: true }; }
  componentDidUpdate(prev: { children: React.ReactNode }) {
    if (prev.children !== this.props.children && this.state.hasError) {
      this.props.onReset();
      this.setState({ hasError: false });
    }
  }
  render() {
    if (this.state.hasError) {
      return (
        <div className="flex flex-col items-center justify-center py-16 text-gray-400 gap-2">
          <span className="text-xs">该标签页出现错误</span>
          <button
            onClick={() => { this.props.onReset(); this.setState({ hasError: false }); }}
            className="text-xs text-blue-500 hover:underline"
          >
            重试
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

type TabId = 'overview' | 'memories' | 'recall' | 'graph';

const TABS: { id: TabId; label: string }[] = [
  { id: 'overview', label: '概览' },
  { id: 'memories', label: '记忆' },
  { id: 'recall', label: '召回' },
  { id: 'graph', label: '关联图' },
];

export function MemoryDebugPanel({ open, onClose }: Props) {
  const [tab, setTab] = useState<TabId>('overview');
  const [tabKey, setTabKey] = useState(0);
  const [cleanupResult, setCleanupResult] = useState<CleanupResult | null>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && open) onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="absolute inset-0 z-30 bg-white flex flex-col" style={{ animation: 'slideIn 0.2s ease-out' }}>
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-gray-200">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold text-gray-800">Memory Debug</h2>
          {cleanupResult && (
            <span className="text-[10px] text-green-600 bg-green-50 px-1.5 py-0.5 rounded">
              清理完成: 合并 {cleanupResult.clusters_merged}
            </span>
          )}
        </div>
        <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400">
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-gray-100 px-4">
        {TABS.map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-3 py-2 text-xs font-medium border-b-2 transition ${
              tab === t.id
                ? 'border-blue-500 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden p-4">
        <TabErrorBoundary onReset={() => setTabKey(k => k + 1)} key={tabKey}>
          {tab === 'overview' && <OverviewTab onCleanup={setCleanupResult} />}
          {tab === 'memories' && <MemoriesTab />}
          {tab === 'recall' && <RecallDebugTab />}
          {tab === 'graph' && <GraphTab />}
        </TabErrorBoundary>
      </div>
    </div>
  );
}
