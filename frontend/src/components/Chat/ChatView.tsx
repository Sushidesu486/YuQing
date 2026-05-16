import React, { useEffect, useCallback, useState } from 'react';
import { useChat } from '../../hooks/useChat';
import { useProactive } from '../../hooks/useProactive';
import { MessageList } from './MessageList';
import { InputBar } from './InputBar';
import { SearchPanel } from './SearchPanel';
import type { Message } from '../../types';

interface Props {
  searchOpen: boolean;
  onSearchOpenChange: (open: boolean) => void;
}

export function ChatView({ searchOpen, onSearchOpenChange }: Props) {
  const { messages, isTyping, error, loading, sendMessage, initSession, addProactiveMessage, conversationId } = useChat();
  const [highlightMessageId, setHighlightMessageId] = useState<string | null>(null);

  useEffect(() => {
    initSession();
  }, [initSession]);

  const handleProactiveMessage = useCallback((message: Message) => {
    addProactiveMessage(message);
  }, [addProactiveMessage]);

  useProactive({
    conversationId,
    onMessage: handleProactiveMessage,
  });

  // Auto-clear highlight after 2.5s
  useEffect(() => {
    if (!highlightMessageId) return;
    const t = setTimeout(() => setHighlightMessageId(null), 2500);
    return () => clearTimeout(t);
  }, [highlightMessageId]);

  const handleSearchSelect = useCallback((msgId: string) => {
    setHighlightMessageId(msgId);
  }, []);

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center text-gray-400 dark:text-gray-500 chat-bg">
        <div className="animate-pulse text-sm">加载中...</div>
      </div>
    );
  }

  return (
    <div className="flex flex-col flex-1 min-h-0 relative">
      <MessageList messages={messages} isStreaming={isTyping} highlightMessageId={highlightMessageId} />
      {error && (
        <div className="px-4 pb-1 bg-white">
          <div className="text-xs text-red-500 px-3 py-1.5">
            {error}
          </div>
        </div>
      )}
      <InputBar onSend={sendMessage} disabled={false} />
      <SearchPanel
        open={searchOpen}
        conversationId={conversationId}
        onClose={() => onSearchOpenChange(false)}
        onSelect={handleSearchSelect}
      />
    </div>
  );
}
