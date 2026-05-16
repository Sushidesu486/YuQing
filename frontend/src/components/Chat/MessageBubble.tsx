import React from 'react';
import type { Message } from '../../types';

const YUQING_AVATAR = '/avatar-yuqing.png';
const USER_AVATAR = '/avatar-user.png';

// Responses that are essentially empty and should not be rendered
const EMPTY_RESPONSES = ['...', '。。.', '嗯', '哦', '嗯...', '哦...', '。'];

interface Props {
  message: Message;
}

export function MessageBubble({ message }: Props) {
  const isUser = message.role === 'user';

  // Render sticker message
  const stickerPath = message.sticker_name || message.content;
  if (message.content_type === 'sticker' && stickerPath) {
    return (
      <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-3 px-4`}>
        <div className="flex items-end gap-2">
          {!isUser && (
            <img src={YUQING_AVATAR} alt="雨晴" className="w-9 h-9 rounded-lg flex-shrink-0 object-cover" />
          )}
          <img
            src={`/stickers/${stickerPath}.png`}
            alt={stickerPath}
            className="w-56 h-56 rounded-lg object-contain bg-gray-50/50"
            draggable={false}
            onError={(e) => {
              const img = e.target as HTMLImageElement;
              // If full path fails, try without category prefix
              if (!img.dataset.retried) {
                const basename = stickerPath.split('/').pop();
                img.src = `/stickers/${basename}.png`;
                img.dataset.retried = '1';
              } else {
                img.style.display = 'none';
              }
            }}
          />
          {isUser && (
            <img src={USER_AVATAR} alt="shouss" className="w-9 h-9 rounded-lg flex-shrink-0 object-cover" />
          )}
        </div>
      </div>
    );
  }

  // Don't render empty assistant messages (placeholder during streaming)
  if (!isUser && !message.content) return null;

  // Don't render essentially-empty assistant responses
  if (!isUser && EMPTY_RESPONSES.includes(message.content.trim())) return null;

  const segments = message.content.split(/\n\n+/).filter(block => {
    const t = block.trim();
    return t && !EMPTY_RESPONSES.includes(t);
  });
  const isSingleBubble = isUser || segments.length <= 1;

  if (isUser) {
    return (
      <div className="flex justify-end mb-3 px-4">
        <div className="max-w-[65%] flex items-end gap-2">
          <div className="relative bg-[#95EC69] text-black rounded-lg px-3 py-2 text-sm leading-relaxed whitespace-pre-wrap break-words">
            <div className="absolute top-2 right-[-6px] w-0 h-0 border-t-[6px] border-t-transparent border-b-[6px] border-b-transparent border-l-[6px] border-l-[#95EC69]" />
            {message.content}
          </div>
          <img src={USER_AVATAR} alt="shouss" className="w-9 h-9 rounded-lg flex-shrink-0 object-cover" />
        </div>
      </div>
    );
  }

  // Single bubble assistant message
  if (isSingleBubble) {
    return (
      <div className="flex justify-start mb-3 px-4">
        <div className="max-w-[65%] flex items-end gap-2">
          <img src={YUQING_AVATAR} alt="雨晴" className="w-9 h-9 rounded-lg flex-shrink-0 object-cover" />
          <div>
            {message.trigger_type && (
              <div className="text-[10px] text-gray-400 mb-0.5 ml-1">雨晴想起了什么...</div>
            )}
            <div className="relative bg-white dark:bg-gray-800 text-black dark:text-gray-100 rounded-lg px-3 py-2 text-sm leading-relaxed whitespace-pre-wrap break-words shadow-sm">
              <div className="absolute top-2 left-[-6px] w-0 h-0 border-t-[6px] border-t-transparent border-b-[6px] border-b-transparent border-r-[6px] border-r-white dark:border-r-gray-800" />
              {message.content}
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Multi-bubble assistant message
  return (
    <div className="mb-3">
      {message.trigger_type && (
        <div className="text-[10px] text-gray-400 mb-0.5 px-4 ml-12">雨晴想起了什么...</div>
      )}
      {segments.map((seg, i) => (
        <div key={i} className="flex justify-start px-4 mb-1.5">
          <div className="max-w-[65%] flex items-start gap-2">
            <img src={YUQING_AVATAR} alt="雨晴" className="w-9 h-9 rounded-lg flex-shrink-0 object-cover" />
            <div className="relative bg-white dark:bg-gray-800 text-black dark:text-gray-100 rounded-lg px-3 py-2 text-sm leading-relaxed whitespace-pre-wrap break-words shadow-sm">
              <div className="absolute top-2 left-[-6px] w-0 h-0 border-t-[6px] border-t-transparent border-b-[6px] border-b-transparent border-r-[6px] border-r-white dark:border-r-gray-800" />
              {seg}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
