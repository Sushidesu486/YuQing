import React, { useEffect, useRef } from 'react';
import type { Message } from '../../types';
import { MessageBubble } from './MessageBubble';

interface Props {
  messages: Message[];
  isStreaming: boolean;
  highlightMessageId?: string | null;
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

export function MessageList({ messages, isStreaming, highlightMessageId }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const isAtBottomRef = useRef(true);
  const highlightTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (isAtBottomRef.current) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages]);

  // Scroll to highlighted message
  useEffect(() => {
    if (!highlightMessageId) return;
    const el = document.getElementById(`msg-${highlightMessageId}`);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
    // Clear highlight after 2.5s
    if (highlightTimerRef.current) clearTimeout(highlightTimerRef.current);
    highlightTimerRef.current = setTimeout(() => {
      // The parent component handles clearing highlightMessageId state
    }, 2500);
    return () => {
      if (highlightTimerRef.current) clearTimeout(highlightTimerRef.current);
    };
  }, [highlightMessageId]);

  const handleScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    isAtBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 100;
  };

  if (messages.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center chat-bg">
        <div className="text-center text-gray-400 dark:text-gray-500">
          <img src="/avatar-yuqing.png" alt="雨晴" className="w-16 h-16 mx-auto mb-3 rounded-2xl object-cover shadow-lg opacity-70" />
          <div className="text-sm">雨晴已上线</div>
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
        const isHighlighted = msg.id === highlightMessageId;

        return (
          <React.Fragment key={msg.id}>
            {showDivider && msg.created_at && (
              <div className="flex justify-center mb-3">
                <span className="text-[11px] font-medium text-gray-500 dark:text-gray-300 bg-gray-100 dark:bg-gray-800 rounded-full px-3 py-0.5 shadow-sm">
                  {formatTimeDivider(msg.created_at)}
                </span>
              </div>
            )}
            <div
              id={`msg-${msg.id}`}
              className={`transition-all duration-700 rounded-lg ${
                isHighlighted
                  ? 'ring-2 ring-yellow-400 ring-offset-1 ring-offset-transparent bg-yellow-50 dark:bg-yellow-900/20'
                  : ''
              }`}
            >
              <MessageBubble message={msg} />
            </div>
          </React.Fragment>
        );
      })}
      {isStreaming && (
        <div className="flex justify-start mb-3 px-4">
          <div className="max-w-[65%] flex items-end gap-2">
            <img src="/avatar-yuqing.png" alt="雨晴" className="w-9 h-9 rounded-lg flex-shrink-0 object-cover" />
            <div className="bg-white dark:bg-gray-800 rounded-lg px-3 py-2 shadow-sm dark:shadow-gray-900/50">
              <div className="flex space-x-1">
                <span className="w-1.5 h-1.5 bg-gray-400 dark:bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="w-1.5 h-1.5 bg-gray-400 dark:bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="w-1.5 h-1.5 bg-gray-400 dark:bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
            </div>
          </div>
        </div>
      )}
      <div ref={bottomRef} className="h-1" />
    </div>
  );
}
