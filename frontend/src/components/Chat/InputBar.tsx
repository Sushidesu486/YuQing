import React, { useState, useRef, useEffect } from 'react';

interface Props {
  onSend: (message: string) => void;
  disabled: boolean;
}

export function InputBar({ onSend, disabled }: Props) {
  const [text, setText] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

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
    <div className="bg-white border-t border-gray-200 px-3 py-2.5 flex-shrink-0">
      <div className="flex items-end gap-2">
        {/* Voice button (placeholder, disabled) */}
        <button
          disabled
          className="flex-shrink-0 w-9 h-9 rounded-full flex items-center justify-center text-gray-400 cursor-not-allowed"
        >
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
          </svg>
        </button>

        {/* Text input */}
        <div className="flex-1 bg-gray-100 rounded-lg px-3 py-1.5 min-h-[36px] max-h-[120px]">
          <textarea
            ref={textareaRef}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="发消息..."
            disabled={disabled}
            rows={1}
            className="w-full resize-none bg-transparent text-sm leading-relaxed focus:outline-none text-gray-900 placeholder-gray-400 disabled:opacity-50"
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
