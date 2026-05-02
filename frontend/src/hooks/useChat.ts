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
const COOLDOWN_MS = 10000; // 10 seconds cooldown before sending

export function useChat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isTyping, setIsTyping] = useState(false); // true during cooldown AND while waiting for API
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const abortRef = useRef<AbortController | null>(null);
  const conversationIdRef = useRef<string | null>(localStorage.getItem(CONVERSATION_KEY));
  const cooldownTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pendingMessagesRef = useRef<string[]>([]);
  const isSendingRef = useRef(false);

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

  const flushMessages = useCallback(async () => {
    if (isSendingRef.current) return;
    if (pendingMessagesRef.current.length === 0) return;

    isSendingRef.current = true;
    const batch = pendingMessagesRef.current.join('\n');
    pendingMessagesRef.current = [];

    // Add assistant placeholder right before sending
    const assistantMessage: Message = {
      id: '',
      role: 'assistant',
      content: '',
    };
    setMessages((prev) => [...prev, assistantMessage]);
    // isTyping stays true — bouncing dots will be replaced by "..." bubble then by content

    abortRef.current = new AbortController();

    try {
      const response = await fetch('/api/chat/send', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          conversation_id: conversationIdRef.current,
          message: batch,
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

      const processLine = (line: string) => {
        if (!line.startsWith('data: ')) return;
        try {
          const data: SSEEvent = JSON.parse(line.slice(6));
          if (data.type === 'token' && data.content) {
            fullContent += data.content;
          } else if (data.type === 'error') {
            setError(data.error || 'Unknown error');
          } else if (data.type === 'done') {
            setMessages((prev) => {
              const updated = [...prev];
              updated[updated.length - 1] = {
                ...updated[updated.length - 1],
                id: data.message_id || updated[updated.length - 1].id,
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
        } catch {
          // ignore malformed JSON
        }
      };

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          processLine(line);
        }
      }

      if (buffer.trim()) {
        processLine(buffer);
      }
    } catch (err: unknown) {
      if (err instanceof Error && err.name === 'AbortError') return;
      setError(err instanceof Error ? err.message : 'Unknown error');
      setMessages((prev) => prev.slice(0, -1));
    } finally {
      isSendingRef.current = false;

      // If more messages accumulated while we were sending, flush them
      if (pendingMessagesRef.current.length > 0) {
        // Small delay before sending next batch
        setTimeout(() => flushMessages(), 500);
      } else {
        setIsTyping(false);
      }
    }
  }, []);

  const sendMessage = useCallback(
    (content: string) => {
      if (!content.trim()) return;

      setError(null);

      // Add user message to UI immediately
      const userMessage: Message = {
        id: `temp-${Date.now()}`,
        role: 'user',
        content: content.trim(),
      };
      setMessages((prev) => [...prev, userMessage]);

      // Queue the message
      pendingMessagesRef.current.push(content.trim());

      // Reset cooldown timer
      if (cooldownTimerRef.current) {
        clearTimeout(cooldownTimerRef.current);
      }

      // Show typing indicator during cooldown
      setIsTyping(true);

      // Set timer to flush after cooldown
      cooldownTimerRef.current = setTimeout(() => {
        cooldownTimerRef.current = null;
        if (!isSendingRef.current) {
          flushMessages();
        }
      }, COOLDOWN_MS);
    },
    [flushMessages]
  );

  // Cleanup timer on unmount
  useEffect(() => {
    return () => {
      if (cooldownTimerRef.current) {
        clearTimeout(cooldownTimerRef.current);
      }
    };
  }, []);

  const addProactiveMessage = useCallback((message: Message) => {
    setMessages((prev) => {
      // Dedup: don't add if already in list
      if (prev.some((m) => m.id === message.id)) return prev;
      return [...prev, message];
    });
  }, []);

  return { messages, isTyping, error, loading, sendMessage, initSession, addProactiveMessage, conversationId: conversationIdRef.current };
}
