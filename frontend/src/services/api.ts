const API_BASE = '/api';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...options?.headers },
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined }),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'PUT', body: body ? JSON.stringify(body) : undefined }),
  delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
};

export const memoryApi = {
  getStats: () => request<import('./types').MemoryStats>('/memories/debug/stats'),
  recall: (query: string, conversationId?: string) =>
    request<import('./types').RecallDebugResult>('/memories/debug/recall', {
      method: 'POST',
      body: JSON.stringify({ query, ...(conversationId ? { conversation_id: conversationId } : {}) }),
    }),
  cleanup: () => request<import('./types').CleanupResult>('/memories/debug/cleanup', { method: 'POST' }),
  list: (category?: string, limit?: number) =>
    request<import('./types').MemoryItem[]>(`/memories?category=${category || ''}&limit=${limit || 50}`),
  search: async (q: string, topK?: number) => {
    const raw = await request<Array<{ id: string; content: string; distance?: number; metadata?: Record<string, unknown> }>>(
      `/memories/search?q=${encodeURIComponent(q)}&top_k=${topK || 10}`
    );
    return raw.map(r => ({
      id: r.id,
      content: r.content,
      category: (r.metadata?.category as string) ?? undefined,
      memory_type: (r.metadata?.memory_type as string) ?? (r.metadata?.category as string) ?? undefined,
      importance: (r.metadata?.importance as number) ?? undefined,
      valence: (r.metadata?.valence as number) ?? undefined,
      confidence: (r.metadata?.confidence as number) ?? undefined,
    }));
  },
  delete: (id: string) => request<unknown>(`/memories/${id}`, { method: 'DELETE' }),
  getLinks: () => request<import('./types').MemoryLink[]>('/memories/links'),
};
