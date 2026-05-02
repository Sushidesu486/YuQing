import React, { useState, useEffect } from 'react';
import type { PersonalityConfig } from '../../types';
import { api } from '../../services/api';

interface Props {
  open: boolean;
  onClose: () => void;
}

export function SettingsModal({ open, onClose }: Props) {
  const [activeTab, setActiveTab] = useState<'personality' | 'model'>('personality');
  const [personality, setPersonality] = useState<PersonalityConfig | null>(null);
  const [model, setModel] = useState('');
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (open) {
      api.get<PersonalityConfig>('/personality').then(setPersonality);
      api.get<{ value: string }>('/settings').then((s) => {
        // settings is a key-value store; we'd need a model key
      }).catch(() => {});
    }
  }, [open]);

  const handleSavePersonality = async () => {
    if (!personality) return;
    await api.put('/personality', { config: personality });
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const handleReset = async () => {
    await api.post('/personality/reset');
    const fresh = await api.get<PersonalityConfig>('/personality');
    setPersonality(fresh);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const updateTrait = (key: string, value: number) => {
    if (!personality) return;
    setPersonality({
      ...personality,
      traits: { ...personality.traits, [key]: value },
    });
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div
        className="bg-white dark:bg-gray-800 rounded-xl shadow-xl w-full max-w-lg max-h-[80vh] overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-700">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">设置</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-gray-200 dark:border-gray-700">
          <button
            onClick={() => setActiveTab('personality')}
            className={`flex-1 px-4 py-3 text-sm font-medium ${
              activeTab === 'personality'
                ? 'text-blue-600 border-b-2 border-blue-600'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            人格设置
          </button>
          <button
            onClick={() => setActiveTab('model')}
            className={`flex-1 px-4 py-3 text-sm font-medium ${
              activeTab === 'model'
                ? 'text-blue-600 border-b-2 border-blue-600'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            模型设置
          </button>
        </div>

        {/* Content */}
        <div className="p-6 overflow-y-auto max-h-[50vh]">
          {activeTab === 'personality' && personality && (
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">名称</label>
                <input
                  type="text"
                  value={personality.name}
                  onChange={(e) => setPersonality({ ...personality, name: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">描述</label>
                <textarea
                  value={personality.description}
                  onChange={(e) => setPersonality({ ...personality, description: e.target.value })}
                  rows={2}
                  className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm resize-none"
                />
              </div>
              {/* Trait sliders */}
              {[
                { key: 'warmth', label: '温暖度' },
                { key: 'humor', label: '幽默感' },
                { key: 'formality', label: '正式度' },
                { key: 'empathy', label: '同理心' },
                { key: 'verbosity', label: '话痨度' },
              ].map(({ key, label }) => (
                <div key={key}>
                  <div className="flex justify-between text-sm mb-1">
                    <span className="text-gray-600 dark:text-gray-400">{label}</span>
                    <span className="text-gray-900 dark:text-white font-mono">
                      {(personality.traits as any)[key]?.toFixed(1)}
                    </span>
                  </div>
                  <input
                    type="range"
                    min="0"
                    max="1"
                    step="0.1"
                    value={(personality.traits as any)[key] || 0}
                    onChange={(e) => updateTrait(key, parseFloat(e.target.value))}
                    className="w-full accent-blue-500"
                  />
                </div>
              ))}
            </div>
          )}

          {activeTab === 'model' && (
            <div className="space-y-4">
              <div className="text-sm text-gray-500 dark:text-gray-400">
                模型配置通过 <code className="bg-gray-100 dark:bg-gray-700 px-1 rounded">.env</code> 文件设置。
              </div>
              <div className="text-sm text-gray-500 dark:text-gray-400 space-y-1">
                <p>当前配置:</p>
                <ul className="list-disc pl-4 space-y-0.5">
                  <li>修改 <code className="bg-gray-100 dark:bg-gray-700 px-1 rounded">.env</code> 中的 <code className="bg-gray-100 dark:bg-gray-700 px-1 rounded">LITELLM_MODEL</code> 来切换模型</li>
                  <li>修改 <code className="bg-gray-100 dark:bg-gray-700 px-1 rounded">LITELLM_API_KEY</code> 来设置 API Key</li>
                  <li>支持 DeepSeek、GLM、Claude、OpenAI 等</li>
                </ul>
              </div>
              <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-3 text-xs font-mono text-gray-600 dark:text-gray-300">
                <p>LITELLM_MODEL=deepseek/deepseek-chat</p>
                <p>LITELLM_API_KEY=sk-xxx</p>
                <p>LITELLM_API_BASE=https://api.deepseek.com/v1</p>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-gray-200 dark:border-gray-700">
          {activeTab === 'personality' ? (
            <button
              onClick={handleReset}
              className="px-3 py-1.5 text-sm text-gray-500 hover:text-gray-700"
            >
              重置默认
            </button>
          ) : (
            <div />
          )}
          <div className="flex items-center gap-2">
            {saved && <span className="text-sm text-green-500">已保存</span>}
            {activeTab === 'personality' && (
              <button
                onClick={handleSavePersonality}
                className="px-4 py-1.5 text-sm font-medium bg-blue-500 text-white rounded-lg hover:bg-blue-600"
              >
                保存
              </button>
            )}
            <button
              onClick={onClose}
              className="px-4 py-1.5 text-sm text-gray-600 dark:text-gray-300 hover:text-gray-900"
            >
              关闭
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
