import React, { useEffect } from 'react';
import { useChat } from '../../hooks/useChat';
import { MessageList } from './MessageList';
import { InputBar } from './InputBar';

export function ChatView() {
  const { messages, isStreaming, error, loading, sendMessage, initSession } = useChat();

  useEffect(() => {
    initSession();
  }, [initSession]);

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center text-gray-400 chat-bg">
        <div className="animate-pulse text-sm">加载中...</div>
      </div>
    );
  }

  return (
    <div className="flex flex-col flex-1 min-h-0">
      <MessageList messages={messages} isStreaming={isStreaming} />
      {error && (
        <div className="px-4 pb-1 bg-white">
          <div className="text-xs text-red-500 px-3 py-1.5">
            {error}
          </div>
        </div>
      )}
      <InputBar onSend={sendMessage} disabled={isStreaming} />
    </div>
  );
}
