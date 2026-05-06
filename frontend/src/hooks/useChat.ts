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
const COOLDOWN_MS = 20000;

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

    // Show typing indicator only when actually flushing (packing and sending)
    setIsTyping(true);

    // Add assistant placeholder (empty content — MessageBubble won't render it)
    setMessages((prev) => [...prev, { id: PLACEHOLDER_ID, role: 'assistant' as const, content: '' }]);

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

      // Read the full SSE response with line buffering to handle chunk boundaries
      const reader = postRes.body?.getReader();
      if (!reader) throw new Error('No response body');

      const decoder = new TextDecoder();
      let fullContent = '';
      let lineBuffer = '';
      let doneHandled = false;
      let streamFinished = false;

      const applyCleanedContent = (messageId?: string) => {
        const cleaned = fullContent
          .split(/\n\n+/)
          .map(p => p.trim())
          .filter(p => p && !/^[.……]+$/.test(p))
          .join('\n\n')
          .trim();
        const isEmpty = !cleaned || ['...', '。。.', '嗯', '哦', '嗯...', '哦...', '。', '…'].includes(cleaned);
        setMessages((prev) => {
          const idx = prev.findIndex(m => m.id === PLACEHOLDER_ID);
          if (idx === -1) return prev;
          if (isEmpty) return prev.filter((_, i) => i !== idx);
          const updated = [...prev];
          updated[idx] = {
            ...updated[idx],
            id: messageId || updated[idx].id,
            content: cleaned,
            created_at: new Date().toISOString(),
          };
          return updated;
        });
      };

      while (true) {
        if (streamFinished) break;
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        // Append to buffer and process complete lines
        lineBuffer += chunk;
        const lines = lineBuffer.split('\n');
        // Keep the last incomplete line in the buffer
        lineBuffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const jsonStr = line.slice(6).trim();
          if (!jsonStr) continue;

          let data: SSEData;
          try {
            data = JSON.parse(jsonStr);
          } catch {
            // Malformed JSON line, skip
            continue;
          }

          if (data.type === 'token' && data.content) {
            fullContent += data.content;
            // Strip /sticker_name refs from displayed content
            const displayContent = fullContent.replace(/\/\w+/g, '').replace(/\n{3,}/g, '\n\n').trim();
            // Update placeholder with streaming content for real-time display
            setMessages((prev) => {
              const idx = prev.findIndex(m => m.id === PLACEHOLDER_ID);
              if (idx === -1) return prev;
              const updated = [...prev];
              updated[idx] = { ...updated[idx], content: displayContent || fullContent };
              return updated;
            });
          } else if (data.type === 'error') {
            console.error('SSE error:', data.error);
            setError(data.error || 'Unknown error');
          } else if (data.type === 'done' && !doneHandled) {
            doneHandled = true;
            console.log('[Chat] done event received, content length:', fullContent.length);
            applyCleanedContent(data.message_id);
            if (data.conversation_id) {
              conversationIdRef.current = data.conversation_id;
              localStorage.setItem(CONVERSATION_KEY, data.conversation_id);
            }
            // Don't break yet — sticker events may follow
          } else if (data.type === 'sticker') {
            setMessages((prev) => [
              ...prev,
              { id: data.message_id || `sticker-${Date.now()}`, role: 'assistant', content: data.name,
                content_type: 'sticker', sticker_name: data.name, created_at: new Date().toISOString() },
            ]);
            // After receiving sticker(s), we can close the stream
            streamFinished = true;
            break;
          }
        }
      }

      // Process any remaining buffered data after stream ends
      if (lineBuffer.startsWith('data: ')) {
        const jsonStr = lineBuffer.slice(6).trim();
        if (jsonStr) {
          try {
            const data: SSEData = JSON.parse(jsonStr);
            if (data.type === 'done' && !doneHandled) {
              doneHandled = true;
              applyCleanedContent(data.message_id);
            }
          } catch {
            // Malformed JSON in buffer
          }
        }
      }

      // Fallback: if done event was never received but we have content, update anyway
      if (!doneHandled && fullContent) {
        applyCleanedContent();
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

      // Check if user is sending a sticker
      const stickerMatch = content.trim().match(/^\/(\w+)$/);
      if (stickerMatch) {
        const stickerName = stickerMatch[1];
        // Send sticker directly via API
        const convId = conversationIdRef.current;
        const lang = localStorage.getItem('language') || 'zh';
        fetch('/api/chat/send', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ conversation_id: convId, message: content.trim(), language: lang }),
        }).then(async (res) => {
          if (!res.ok) return;
          const reader = res.body?.getReader();
          if (!reader) return;
          const decoder = new TextDecoder();
          let buffer = '';
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';
            for (const line of lines) {
              if (!line.startsWith('data: ')) continue;
              try {
                const data = JSON.parse(line.slice(6).trim());
                if (data.type === 'sticker') {
                  setMessages((prev) => [
                    ...prev,
                    { id: data.message_id || `sticker-${Date.now()}`, role: 'user', content: data.name,
                      content_type: 'sticker', sticker_name: data.name },
                  ]);
                  // If this was a user sticker, also trigger YuQing's response
                  // by sending a descriptive text message
                  if (data.sender === 'user') {
                    pendingRef.current.push(`[发送了 /${data.name} 表情包]`);
                    setTimeout(() => {
                      if (!sendingRef.current) flushMessages();
                    }, 300);
                  }
                }
              } catch { /* skip */ }
            }
          }
        }).catch(console.error);
        return;
      }

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
