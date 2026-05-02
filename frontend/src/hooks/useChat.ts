import { useState, useCallback, useRef, useEffect } from 'react';
import type { Message } from '../types';
import { api } from '../services/api';

interface SSEEvent {
  type: string;
  content?: string;
  message_id?: string;
  conversation_id?: string;
  error?: string;
  valence?: number;
  arousal?: number;
  dominant_emotion?: string;
}

const CONVERSATION_KEY = 'yuqing_conversation_id';

export function useChat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const abortRef = useRef<AbortController | null>(null);
  const conversationIdRef = useRef<string | null>(localStorage.getItem(CONVERSATION_KEY));

  const initSession = useCallback(async () => {
    setLoading(true);
    try {
      // Try to load existing conversation
      const savedId = localStorage.getItem(CONVERSATION_KEY);
      if (savedId) {
        conversationIdRef.current = savedId;
        try {
          const data = await api.get<{ messages: Message[] }>(`/conversations/${savedId}`);
          if (data.messages && data.messages.length > 0) {
            setMessages(data.messages);
            setLoading(false);
            return;
          }
        } catch {
          // conversation might have been deleted
        }
      }

      // No saved conversation or it was empty, create a new one
      const conv = await api.post<{ id: string }>('/conversations');
      conversationIdRef.current = conv.id;
      localStorage.setItem(CONVERSATION_KEY, conv.id);
      setMessages([]);
    } catch (e) {
      console.error('Failed to init session:', e);
      setMessages([]);
    } finally {
      setLoading(false);
    }
  }, []);

  const sendMessage = useCallback(
    async (content: string) => {
      if (!content.trim() || isStreaming) return;
      setError(null);

      const userMessage: Message = {
        id: `temp-${Date.now()}`,
        role: 'user',
        content: content.trim(),
      };
      setMessages((prev) => [...prev, userMessage]);
      setIsStreaming(true);

      const assistantMessage: Message = {
        id: '',
        role: 'assistant',
        content: '',
      };
      setMessages((prev) => [...prev, assistantMessage]);

      abortRef.current = new AbortController();

      try {
        const response = await fetch('/api/chat/send', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            conversation_id: conversationIdRef.current,
            message: content.trim(),
            language: localStorage.getItem('language') || 'zh',
          }),
          signal: abortRef.current.signal,
        });

        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const reader = response.body?.getReader();
        if (!reader) throw new Error('No response body');

        const decoder = new TextDecoder();
        let buffer = '';
        let fullContent = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            if (!line.startsWith('data: ')) continue;
            try {
              const data: SSEEvent = JSON.parse(line.slice(6));

              if (data.type === 'token' && data.content) {
                fullContent += data.content;
                setMessages((prev) => {
                  const updated = [...prev];
                  updated[updated.length - 1] = {
                    ...updated[updated.length - 1],
                    content: fullContent,
                  };
                  return updated;
                });
              } else if (data.type === 'error') {
                setError(data.error || 'Unknown error');
              } else if (data.type === 'done') {
                setMessages((prev) => {
                  const updated = [...prev];
                  updated[updated.length - 1] = {
                    ...updated[updated.length - 1],
                    id: data.message_id || updated[updated.length - 1].id,
                    created_at: new Date().toISOString(),
                  };
                  return updated;
                });
                if (data.conversation_id) {
                  conversationIdRef.current = data.conversation_id;
                  localStorage.setItem(CONVERSATION_KEY, data.conversation_id);
                }
              }
            } catch {
              // ignore malformed JSON
            }
          }
        }
      } catch (err: unknown) {
        if (err instanceof Error && err.name === 'AbortError') return;
        setError(err instanceof Error ? err.message : 'Unknown error');
        setMessages((prev) => prev.slice(0, -1));
      } finally {
        setIsStreaming(false);
        abortRef.current = null;
      }
    },
    [isStreaming]
  );

  return { messages, isStreaming, error, loading, sendMessage, initSession };
}
