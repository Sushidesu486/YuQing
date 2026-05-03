import { useState, useCallback, useRef, useEffect } from 'react';
import type { Message } from '../types';
import { api } from '../services/api';

interface SSEData {
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
const COOLDOWN_MS = 10000;

const PLACEHOLDER_ID = '__streaming_placeholder__';

export function useChat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isTyping, setIsTyping] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const conversationIdRef = useRef<string | null>(localStorage.getItem(CONVERSATION_KEY));
  const cooldownTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pendingRef = useRef<string[]>([]);
  const sendingRef = useRef(false);
  const esRef = useRef<EventSource | null>(null);

  const initSession = useCallback(async () => {
    setLoading(true);
    try {
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

  const flushMessages = useCallback(() => {
    if (sendingRef.current) return;
    const pending = pendingRef.current;
    if (pending.length === 0) return;

    sendingRef.current = true;
    pendingRef.current = [];

    // Add assistant placeholder (empty content — MessageBubble won't render it)
    setMessages((prev) => [...prev, { id: PLACEHOLDER_ID, role: 'assistant' as const, content: '' }]);

    // Build form data for POST (EventSource only supports GET, so we use fetch + EventSource differently)
    // Actually, EventSource is GET-only. We need to use fetch for POST, but parse SSE manually.
    // Instead, let's use a simpler approach: POST to send, then GET to stream.
    const convId = conversationIdRef.current;
    const batch = pending.join('\n');
    const lang = localStorage.getItem('language') || 'zh';

    // POST the message first to get it stored
    fetch('/api/chat/send', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        conversation_id: convId,
        message: batch,
        language: lang,
      }),
    }).then(async (postRes) => {
      if (!postRes.ok) {
        throw new Error(`HTTP ${postRes.status}`);
      }

      // Read the full SSE response
      const reader = postRes.body?.getReader();
      if (!reader) throw new Error('No response body');

      const decoder = new TextDecoder();
      let fullContent = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        // Parse SSE format: lines starting with "data: " contain JSON
        for (const line of chunk.split('\n')) {
          if (!line.startsWith('data: ')) continue;
          const jsonStr = line.slice(6).trim();
          if (!jsonStr) continue;

          try {
            const data: SSEData = JSON.parse(jsonStr);
            if (data.type === 'token' && data.content) {
              fullContent += data.content;
            } else if (data.type === 'error') {
              console.error('SSE error:', data.error);
              setError(data.error || 'Unknown error');
            } else if (data.type === 'done') {
              console.log('[Chat] done event received, content length:', fullContent.length);
              const trimmed = fullContent.trim();
              const isEmpty = !trimmed || ['...', '。。.', '嗯', '哦', '嗯...', '哦...', '。'].includes(trimmed);
              setMessages((prev) => {
                const idx = prev.findIndex(m => m.id === PLACEHOLDER_ID);
                if (idx === -1) return prev; // placeholder already removed
                if (isEmpty) {
                  // Remove placeholder — don't show empty/useless responses
                  return prev.filter((_, i) => i !== idx);
                }
                const updated = [...prev];
                updated[idx] = {
                  ...updated[idx],
                  id: data.message_id || updated[idx].id,
                  content: fullContent,
                  created_at: new Date().toISOString(),
                };
                return updated;
              });
              if (data.conversation_id) {
                conversationIdRef.current = data.conversation_id;
                localStorage.setItem(CONVERSATION_KEY, data.conversation_id);
              }
            }
          } catch (e) {
            // Malformed JSON line, skip
          }
        }
      }

      // If done event was never received but we have content, update anyway
      if (fullContent) {
        const trimmed = fullContent.trim();
        const isEmpty = !trimmed || ['...', '。。.', '嗯', '哦', '嗯...', '哦...', '。'].includes(trimmed);
        setMessages((prev) => {
          const idx = prev.findIndex(m => m.id === PLACEHOLDER_ID);
          if (idx === -1) return prev;
          if (isEmpty) return prev.filter((_, i) => i !== idx);
          const updated = [...prev];
          updated[idx] = {
            ...updated[idx],
            content: fullContent,
            created_at: new Date().toISOString(),
          };
          return updated;
        });
      }
    }).catch((err) => {
      console.error('[Chat] flush error:', err);
      setError(err instanceof Error ? err.message : 'Unknown error');
      // Remove the empty assistant placeholder on error
      setMessages((prev) => prev.filter(m => m.id !== PLACEHOLDER_ID));
    }).finally(() => {
      sendingRef.current = false;
      setIsTyping(false);

      // If more messages accumulated, flush after a short delay
      if (pendingRef.current.length > 0) {
        setTimeout(() => flushMessages(), 500);
      }
    });
  }, []);

  const sendMessage = useCallback(
    (content: string) => {
      if (!content.trim()) return;

      setError(null);

      // Add user message to UI immediately
      setMessages((prev) => [
        ...prev,
        { id: `temp-${Date.now()}`, role: 'user', content: content.trim() },
      ]);

      // Queue the message
      pendingRef.current.push(content.trim());

      // Reset cooldown timer
      if (cooldownTimerRef.current) {
        clearTimeout(cooldownTimerRef.current);
      }

      // Show typing indicator during cooldown
      setIsTyping(true);

      // Flush after cooldown
      cooldownTimerRef.current = setTimeout(() => {
        cooldownTimerRef.current = null;
        if (!sendingRef.current) {
          flushMessages();
        }
      }, COOLDOWN_MS);
    },
    [flushMessages],
  );

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (cooldownTimerRef.current) clearTimeout(cooldownTimerRef.current);
      if (esRef.current) esRef.current.close();
    };
  }, []);

  const addProactiveMessage = useCallback((message: Message) => {
    setMessages((prev) => {
      if (prev.some((m) => m.id === message.id)) return prev;
      return [...prev, message];
    });
  }, []);

  return {
    messages,
    isTyping,
    error,
    loading,
    sendMessage,
    initSession,
    addProactiveMessage,
    conversationId: conversationIdRef.current,
  };
}
