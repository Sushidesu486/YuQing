import { useState, useEffect, useCallback } from 'react';
import type { Conversation } from '../types';
import { api } from '../services/api';

interface UseConversationsReturn {
  conversations: Conversation[];
  loading: boolean;
  refresh: () => Promise<void>;
  createConversation: () => Promise<Conversation>;
  deleteConversation: (id: string) => Promise<void>;
  renameConversation: (id: string, title: string) => Promise<void>;
}

export function useConversations(): UseConversationsReturn {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.get<{ conversations: Conversation[] }>('/conversations');
      setConversations(data.conversations);
    } catch {
      // silently fail
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const createConversation = useCallback(async () => {
    const data = await api.post<Conversation>('/conversations');
    setConversations((prev) => [data, ...prev]);
    return data;
  }, []);

  const deleteConversation = useCallback(
    async (id: string) => {
      await api.delete(`/conversations/${id}`);
      setConversations((prev) => prev.filter((c) => c.id !== id));
    },
    []
  );

  const renameConversation = useCallback(async (id: string, title: string) => {
    await api.put(`/conversations/${id}`, { title });
    setConversations((prev) =>
      prev.map((c) => (c.id === id ? { ...c, title } : c))
    );
  }, []);

  return { conversations, loading, refresh, createConversation, deleteConversation, renameConversation };
}
