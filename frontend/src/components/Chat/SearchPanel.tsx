import React, { useState, useEffect, useRef, useCallback } from 'react';
import { api } from '../../services/api';

interface SearchResult {
  id: string;
  role: string;
  content: string;
  created_at: string;
}

interface Props {
  open: boolean;
  conversationId: string | null;
  onClose: () => void;
  onSelect: (messageId: string) => void;
}

function formatDate(dateStr: string): string {
  const d = new Date(dateStr);
  const now = new Date();
  const diffDays = Math.floor((now.getTime() - d.getTime()) / (1000 * 60 * 60 * 24));
  const time = d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
  if (diffDays === 0) return time;
  if (diffDays === 1) return `昨天 ${time}`;
  return `${d.getMonth() + 1}/${d.getDate()} ${time}`;
}

function highlightMatch(text: string, query: string): React.ReactNode {
  if (!query.trim()) return text;
  const idx = text.toLowerCase().indexOf(query.toLowerCase());
  if (idx === -1) return text;
  return (
    <>
      {text.slice(0, idx)}
      <span className="bg-yellow-200 rounded px-0.5">{text.slice(idx, idx + query.length)}</span>
      {text.slice(idx + query.length)}
    </>
  );
}

export function SearchPanel({ open, conversationId, onClose, onSelect }: Props) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 100);
    } else {
      setQuery('');
      setResults([]);
      setTotal(0);
      setSearched(false);
    }
  }, [open]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && open) onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  const doSearch = useCallback(async (q: string) => {
    if (!q.trim() || !conversationId) {
      setResults([]);
      setTotal(0);
      setSearched(false);
      return;
    }
    setLoading(true);
    try {
      const data = await api.get<{ results: SearchResult[]; total: number }>(
        `/conversations/${conversationId}/search?q=${encodeURIComponent(q.trim())}&limit=50`
      );
      setResults(data.results);
      setTotal(data.total);
      setSearched(true);
    } catch {
      setResults([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [conversationId]);

  const handleInput = (val: string) => {
    setQuery(val);
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => doSearch(val), 300);
  };

  const handleSelect = (msgId: string) => {
    onSelect(msgId);
    onClose();
  };

  if (!open) return null;

  return (
    <div className="absolute inset-0 z-30 bg-white flex flex-col">
      {/* Search bar */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-gray-200">
        <svg className="w-5 h-5 text-gray-400 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
        </svg>
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={e => handleInput(e.target.value)}
          placeholder="搜索消息"
          className="flex-1 text-sm outline-none bg-transparent placeholder-gray-400"
        />
        <button onClick={onClose} className="text-sm text-blue-500 flex-shrink-0">取消</button>
      </div>

      {/* Results */}
      <div className="flex-1 overflow-y-auto">
        {loading && (
          <div className="flex items-center justify-center py-8 text-sm text-gray-400">搜索中...</div>
        )}

        {!loading && searched && results.length === 0 && (
          <div className="flex items-center justify-center py-8 text-sm text-gray-400">没有找到相关消息</div>
        )}

        {!loading && total > 0 && query.trim() && (
          <div className="px-4 py-2 text-xs text-gray-400">找到 {total} 条结果</div>
        )}

        {results.map(msg => (
          <button
            key={msg.id}
            onClick={() => handleSelect(msg.id)}
            className="w-full text-left px-4 py-3 border-b border-gray-100 hover:bg-gray-50 active:bg-gray-100 transition-colors"
          >
            <div className="flex items-center gap-2 mb-1">
              <span className={`text-xs px-1.5 py-0.5 rounded ${
                msg.role === 'user' ? 'bg-green-100 text-green-600' : 'bg-blue-100 text-blue-600'
              }`}>
                {msg.role === 'user' ? '你' : '雨晴'}
              </span>
              <span className="text-xs text-gray-400">{formatDate(msg.created_at)}</span>
            </div>
            <div className="text-sm text-gray-700 line-clamp-2 leading-relaxed">
              {highlightMatch(msg.content, query)}
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
