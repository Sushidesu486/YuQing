import React, { useState, useEffect, useCallback, useRef } from 'react';
import { api } from '../../services/api';

interface DiaryEntry {
  id: string;
  content: string;
  valence: number | null;
  created_at: string;
  date_label: string;
}

interface Props {
  open: boolean;
  onClose: () => void;
}

function formatDate(dateStr: string): string {
  const d = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  const timeStr = d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });

  if (diffDays === 0) return `今天 ${timeStr}`;
  if (diffDays === 1) return `昨天 ${timeStr}`;
  if (diffDays < 7) {
    const dayNames = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];
    return `${dayNames[d.getDay()]} ${timeStr}`;
  }
  return `${d.getMonth() + 1}月${d.getDate()}日 ${timeStr}`;
}

const PAGE_SIZE = 20;

export function DiaryPanel({ open, onClose }: Props) {
  const [entries, setEntries] = useState<DiaryEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const offsetRef = useRef(0);

  const loadEntries = useCallback(async (append: boolean = false) => {
    setLoading(true);
    try {
      const off = append ? offsetRef.current : 0;
      const data = await api.get<{ entries: DiaryEntry[]; total: number; has_more: boolean }>(
        `/diary?limit=${PAGE_SIZE}&offset=${off}`
      );
      if (append) {
        setEntries((prev) => [...prev, ...data.entries]);
      } else {
        setEntries(data.entries);
        offsetRef.current = 0;
      }
      offsetRef.current = off + data.entries.length;
      setHasMore(data.has_more);
    } catch (e) {
      console.error('Diary load failed:', e);
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  }, []);

  useEffect(() => {
    if (open) {
      offsetRef.current = 0;
      loadEntries(false);
    }
  }, [open, loadEntries]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && open) onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  const handleScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    if (el.scrollHeight - el.scrollTop - el.clientHeight < 80 && hasMore && !loadingMore) {
      setLoadingMore(true);
      loadEntries(true);
    }
  }, [hasMore, loadingMore, loadEntries]);

  if (!open) return null;

  return (
    <div className="absolute inset-0 z-30 bg-white dark:bg-gray-900 flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-gray-200 dark:border-gray-700">
        <div className="flex items-center gap-2">
          <svg className="w-5 h-5 text-rose-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
          </svg>
          <span className="text-sm font-medium text-gray-900 dark:text-gray-100">雨晴的日记</span>
        </div>
        <button onClick={onClose} className="text-sm text-blue-500">关闭</button>
      </div>

      {/* Content */}
      <div ref={scrollRef} onScroll={handleScroll} className="flex-1 overflow-y-auto px-4 py-3">
        {loading && !loadingMore && (
          <div className="flex items-center justify-center py-12 text-sm text-gray-400">加载中...</div>
        )}

        {!loading && entries.length === 0 && (
          <div className="flex flex-col items-center justify-center py-16 text-gray-400 dark:text-gray-500">
            <svg className="w-12 h-12 mb-3 opacity-40" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
            </svg>
            <span className="text-sm">还没有日记</span>
            <span className="text-xs mt-1">每天凌晨，雨晴会写下今天的日记</span>
          </div>
        )}

        {/* Timeline */}
        <div className="relative">
          {entries.map((entry, i) => {
            const prev = i > 0 ? entries[i - 1] : null;
            const showDate = !prev || prev.date_label !== entry.date_label;
            const valenceColor = entry.valence !== null
              ? entry.valence > 0.2
                ? 'bg-rose-400'
                : entry.valence < -0.2
                  ? 'bg-slate-400'
                  : 'bg-amber-400'
              : 'bg-gray-300';

            return (
              <React.Fragment key={entry.id}>
                {showDate && (
                  <div className="flex items-center gap-3 mb-3 mt-6 first:mt-0">
                    <div className="w-2 h-2 rounded-full bg-rose-300 dark:bg-rose-600 flex-shrink-0" />
                    <span className="text-xs font-medium text-gray-500 dark:text-gray-400">
                      {formatDate(entry.created_at).split(' ').slice(0, -1).join(' ')}
                    </span>
                  </div>
                )}
                <div className="flex gap-3 ml-0 pl-1">
                  {/* Timeline dot + line */}
                  <div className="flex flex-col items-center flex-shrink-0" style={{ marginTop: 4 }}>
                    <div className={`w-2 h-2 rounded-full ${valenceColor} ring-2 ring-white dark:ring-gray-900`} />
                    {i < entries.length - 1 && (
                      <div className="w-px flex-1 bg-gray-200 dark:bg-gray-700 my-0.5" />
                    )}
                  </div>
                  {/* Entry card */}
                  <div className="flex-1 pb-4">
                    <div className="text-sm text-gray-500 dark:text-gray-400 mb-1">
                      {formatDate(entry.created_at).split(' ').slice(-1)[0]}
                    </div>
                    <div className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed whitespace-pre-line">
                      {entry.content}
                    </div>
                    {entry.valence !== null && (
                      <div className="flex items-center gap-1 mt-1.5">
                        <span className="text-xs text-gray-400 dark:text-gray-500">心情</span>
                        <span className={`text-xs font-medium ${
                          entry.valence > 0.2
                            ? 'text-rose-500'
                            : entry.valence < -0.2
                              ? 'text-slate-500'
                              : 'text-amber-500'
                        }`}>
                          {entry.valence > 0 ? '+' : ''}{entry.valence.toFixed(2)}
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              </React.Fragment>
            );
          })}
        </div>

        {loadingMore && (
          <div className="flex justify-center py-4 text-xs text-gray-400">加载中...</div>
        )}
        {!hasMore && entries.length > 0 && (
          <div className="text-center py-6 text-xs text-gray-300 dark:text-gray-600">
            —— 这就是所有日子 ——
          </div>
        )}
      </div>
    </div>
  );
}
