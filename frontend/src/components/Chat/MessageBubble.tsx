import React from 'react';
import type { Message } from '../../types';

interface Props {
  message: Message;
}

export function MessageBubble({ message }: Props) {
  const isUser = message.role === 'user';

  if (isUser) {
    return (
      <div className="flex justify-end mb-3 px-4">
        <div className="max-w-[65%] flex items-end gap-2">
          <div className="relative bg-[#95EC69] text-black rounded-lg px-3 py-2 text-sm leading-relaxed whitespace-pre-wrap break-words">
            {/* Arrow */}
            <div className="absolute top-2 right-[-6px] w-0 h-0 border-t-[6px] border-t-transparent border-b-[6px] border-b-transparent border-l-[6px] border-l-[#95EC69]" />
            {message.content || '...'}
          </div>
          {/* User avatar */}
          <div className="w-9 h-9 rounded-lg bg-gray-300 flex-shrink-0 flex items-center justify-center">
            <svg className="w-5 h-5 text-gray-500" fill="currentColor" viewBox="0 0 24 24">
              <path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/>
            </svg>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start mb-3 px-4">
      <div className="max-w-[65%] flex items-end gap-2">
        {/* AI avatar */}
        <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-blue-400 to-purple-500 flex-shrink-0 flex items-center justify-center text-white text-xs font-bold">
          Q
        </div>
        <div className="relative bg-white text-black rounded-lg px-3 py-2 text-sm leading-relaxed whitespace-pre-wrap break-words shadow-sm">
          {/* Arrow */}
          <div className="absolute top-2 left-[-6px] w-0 h-0 border-t-[6px] border-t-transparent border-b-[6px] border-b-transparent border-r-[6px] border-r-white" />
          {message.content || '...'}
        </div>
      </div>
    </div>
  );
}
