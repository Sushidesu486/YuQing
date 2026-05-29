import { useEffect, useRef } from 'react';
import { api } from '../services/api';
import type { Message } from '../types';

interface ProactiveEvent {
  type: 'proactive_message';
  message_id: string;
  conversation_id: string;
  content: string;
  trigger_type: string;
}

interface UseProactiveOptions {
  conversationId: string | null;
  onMessage: (message: Message) => void;
}

export function useProactive({ conversationId, onMessage }: UseProactiveOptions) {
  const eventSourceRef = useRef<EventSource | null>(null);
  const lastMessageIdRef = useRef<string>('');

  useEffect(() => {
    if (!conversationId) return;

    // Check for pending proactive messages sent while page was closed
    (async () => {
      try {
        const data = await api.get<{ message: Message | null }>(
          `/proactive/recent?conversation_id=${conversationId}`
        );
        if (data.message && data.message.id && data.message.id !== lastMessageIdRef.current) {
          lastMessageIdRef.current = data.message.id;
          onMessage(data.message);
        }
      } catch {
        // no pending messages
      }
    })();

    // Open SSE connection for real-time proactive messages
    const es = new EventSource('/api/proactive/listen');
    eventSourceRef.current = es;

    es.addEventListener('proactive', (event) => {
      try {
        const data: ProactiveEvent = JSON.parse(event.data);
        if (data.type === 'proactive_message') {
          lastMessageIdRef.current = data.message_id;
          onMessage({
            id: data.message_id,
            role: 'assistant',
            content: data.content,
            trigger_type: data.trigger_type,
            created_at: new Date().toISOString(),
          });
        }
      } catch {
        // ignore parse errors
      }
    });

    es.onerror = () => {
      // EventSource auto-reconnects
    };

    return () => {
      es.close();
      eventSourceRef.current = null;
    };
  }, [conversationId, onMessage]);
}
