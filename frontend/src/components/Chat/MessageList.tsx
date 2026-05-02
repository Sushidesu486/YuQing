import React, { useEffect, useRef } from 'react';
import type { Message } from '../../types';
import { MessageBubble } from './MessageBubble';

interface Props {
  messages: Message[];
  isStreaming: boolean;
}

function formatTimeDivider(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  const timeStr = date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });

  if (diffDays === 0) return timeStr;
  if (diffDays === 1) return `昨天 ${timeStr}`;
  if (diffDays < 7) {
    const dayNames = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];
    return `${dayNames[date.getDay()]} ${timeStr}`;
  }
  return `${date.getMonth() + 1}月${date.getDate()}日 ${timeStr}`;
}

function shouldShowDivider(current: Message, prev: Message | null): boolean {
  if (!prev || !prev.created_at || !current.created_at) return true;
  const diff = new Date(current.created_at).getTime() - new Date(prev.created_at).getTime();
  return diff > 5 * 60 * 1000; // 5 minutes
}

export function MessageList({ messages, isStreaming }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const isAtBottomRef = useRef(true);

  useEffect(() => {
    if (isAtBottomRef.current) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages]);

  const handleScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    isAtBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 100;
  };

  if (messages.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center chat-bg">
        <div className="text-center text-gray-400">
          <div className="w-16 h-16 mx-auto mb-3 rounded-2xl bg-gradient-to-br from-blue-400 to-purple-500 flex items-center justify-center text-white text-2xl font-bold shadow-lg">
            Q
          </div>
          <div className="text-sm">语晴已上线</div>
        </div>
      </div>
    );
  }

  return (
    <div
      ref={scrollRef}
      onScroll={handleScroll}
      className="flex-1 overflow-y-auto py-4 chat-bg"
    >
      {messages.map((msg, i) => {
        const prev = i > 0 ? messages[i - 1] : null;
        const showDivider = shouldShowDivider(msg, prev);

        return (
          <React.Fragment key={msg.id}>
            {showDivider && msg.created_at && (
              <div className="flex justify-center mb-3">
                <span className="text-xs text-gray-400 bg-gray-200/60 rounded px-2 py-0.5">
                  {formatTimeDivider(msg.created_at)}
                </span>
              </div>
            )}
            <MessageBubble message={msg} />
          </React.Fragment>
        );
      })}
      {isStreaming && (
        <div className="flex justify-start mb-3 px-4">
          <div className="max-w-[65%] flex items-end gap-2">
            <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-blue-400 to-purple-500 flex-shrink-0 flex items-center justify-center text-white text-xs font-bold">
              Q
            </div>
            <div className="bg-white rounded-lg px-3 py-2 shadow-sm">
              <div className="flex space-x-1">
                <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
            </div>
          </div>
        </div>
      )}
      <div ref={bottomRef} className="h-1" />
    </div>
  );
}
