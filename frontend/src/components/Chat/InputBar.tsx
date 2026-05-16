import React, { useState, useRef, useEffect } from 'react';

// Sticker definitions — must match backend STICKER_DEFINITIONS paths
const STICKER_LIST = [
  { path: 'happy/peekaboo', label: '偷看' },
  { path: 'happy/smile_blink', label: '眨眼笑' },
  { path: 'happy/clap', label: '鼓掌' },
  { path: 'happy/celebrate', label: '庆祝' },
  { path: 'sad/pat_pat', label: '摸头' },
  { path: 'sad/hug', label: '抱抱' },
  { path: 'sad/tissue', label: '递纸巾' },
  { path: 'teasing/pout', label: '嘟嘴' },
  { path: 'teasing/whatever', label: '无所谓' },
  { path: 'shy/fidding_with_hair', label: '玩头发' },
  { path: 'angry/glare', label: '怒视' },
  { path: 'angry/ignore', label: '不理人' },
  { path: 'love/heart_eyes', label: '花痴' },
  { path: 'tired/yawn', label: '打哈欠' },
  { path: 'tired/sleepy', label: '困了' },
  { path: 'eating/eating_chips', label: '吃薯片' },
];

interface Props {
  onSend: (message: string) => void;
  disabled: boolean;
}

export function InputBar({ onSend, disabled }: Props) {
  const [text, setText] = useState('');
  const [showStickers, setShowStickers] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  const handleSend = () => {
    if (!text.trim() || disabled) return;
    onSend(text.trim());
    setText('');
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleStickerSelect = (path: string) => {
    setShowStickers(false);
    onSend(`/${path}`);
  };

  // Close sticker panel on outside click
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        setShowStickers(false);
      }
    };
    if (showStickers) {
      document.addEventListener('mousedown', handleClick);
      return () => document.removeEventListener('mousedown', handleClick);
    }
  }, [showStickers]);

  // Auto-resize textarea
  useEffect(() => {
    const el = textareaRef.current;
    if (el) {
      el.style.height = 'auto';
      el.style.height = Math.min(el.scrollHeight, 120) + 'px';
    }
  }, [text]);

  // Focus textarea on mount
  useEffect(() => {
    textareaRef.current?.focus();
  }, []);

  return (
    <div className="bg-white dark:bg-gray-900 border-t border-gray-200 dark:border-gray-700 px-3 py-2.5 flex-shrink-0 relative">
      {/* Sticker picker panel */}
      {showStickers && (
        <div
          ref={panelRef}
          className="absolute bottom-full left-3 right-3 mb-2 bg-white dark:bg-gray-800 rounded-xl shadow-lg border border-gray-200 dark:border-gray-700 p-3 max-h-64 overflow-y-auto"
        >
          <div className="grid grid-cols-4 gap-2">
            {STICKER_LIST.map((s) => (
              <button
                key={s.path}
                onClick={() => handleStickerSelect(s.path)}
                className="flex flex-col items-center gap-1 p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 active:bg-gray-200 dark:active:bg-gray-600 transition-colors"
              >
                <img
                  src={`/stickers/${s.path}.png`}
                  alt={s.label}
                  className="w-14 h-14 object-contain"
                  draggable={false}
                />
                <span className="text-[10px] text-gray-500 dark:text-gray-400 truncate w-full text-center">{s.label}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="flex items-end gap-2">
        {/* Sticker button */}
        <button
          onClick={() => setShowStickers(!showStickers)}
          disabled={disabled}
          className={`flex-shrink-0 w-9 h-9 rounded-full flex items-center justify-center transition-colors ${
            showStickers
              ? 'text-orange-500 bg-orange-50 dark:bg-orange-900/30'
              : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800'
          } ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
        >
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M14.828 14.828a4 4 0 01-5.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        </button>

        {/* Text input */}
        <div className="flex-1 bg-gray-100 dark:bg-gray-800 rounded-lg px-3 py-1.5 min-h-[36px] max-h-[120px]">
          <textarea
            ref={textareaRef}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="发消息..."
            disabled={disabled}
            rows={1}
            className="w-full resize-none bg-transparent text-sm leading-relaxed focus:outline-none text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 disabled:opacity-50"
            style={{ maxHeight: '100px' }}
          />
        </div>

        {/* Send / Plus button */}
        {text.trim() ? (
          <button
            onClick={handleSend}
            disabled={disabled}
            className="flex-shrink-0 w-9 h-9 rounded-full bg-[#95EC69] flex items-center justify-center text-gray-700 hover:bg-[#89d960] disabled:opacity-50 transition-colors"
          >
            <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor">
              <path d="M2.01 21L23 12 2.01 3 2.01 21l6.99-5.99L2.01 21z" />
            </svg>
          </button>
        ) : (
          <button
            disabled
            className="flex-shrink-0 w-9 h-9 rounded-full flex items-center justify-center text-gray-400 cursor-not-allowed"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 4v16m8-8H4" />
            </svg>
          </button>
        )}
      </div>
    </div>
  );
}
