import React, { useState, useEffect } from 'react';
import type { PersonalityConfig } from '../../types';
import { api } from '../../services/api';

interface Props {
  open: boolean;
  onClose: () => void;
}

export function SettingsModal({ open, onClose }: Props) {
  const [activeTab, setActiveTab] = useState<'personality' | 'model' | 'appearance'>('personality');
  const [personality, setPersonality] = useState<PersonalityConfig | null>(null);
  const [saved, setSaved] = useState(false);
  const [fontScale, setFontScale] = useState(() => parseFloat(localStorage.getItem('yuqing_font_scale') || '1'));
  const [iconScale, setIconScale] = useState(() => parseFloat(localStorage.getItem('yuqing_icon_scale') || '1'));

  useEffect(() => {
    if (open) {
      api.get<PersonalityConfig>('/personality').then(setPersonality);
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
    setPersonality({ ...personality, traits: { ...personality.traits, [key]: value } });
  };

  const updateFontScale = (v: number) => {
    setFontScale(v);
    localStorage.setItem('yuqing_font_scale', String(v));
    document.documentElement.style.setProperty('--font-scale', String(v));
  };
  const updateIconScale = (v: number) => {
    setIconScale(v);
    localStorage.setItem('yuqing_icon_scale', String(v));
    document.documentElement.style.setProperty('--icon-scale', String(v));
  };

  if (!open) return null;

  const tabClass = (name: string) =>
    `flex-1 px-4 py-3 text-sm font-medium ${
      activeTab === name
        ? 'text-blue-600 border-b-2 border-blue-600'
        : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'
    }`;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-xl w-full max-w-lg max-h-[80vh] overflow-hidden" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-700">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">设置</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </div>

        <div className="flex border-b border-gray-200 dark:border-gray-700">
          <button onClick={() => setActiveTab('personality')} className={tabClass('personality')}>人格设置</button>
          <button onClick={() => setActiveTab('model')} className={tabClass('model')}>模型设置</button>
          <button onClick={() => setActiveTab('appearance')} className={tabClass('appearance')}>外观</button>
        </div>

        <div className="p-6 overflow-y-auto max-h-[50vh]">
          {activeTab === 'personality' && personality && (
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">名称</label>
                <input type="text" value={personality.name} onChange={(e) => setPersonality({ ...personality, name: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm" />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">描述</label>
                <textarea value={personality.description} onChange={(e) => setPersonality({ ...personality, description: e.target.value })} rows={2}
                  className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm resize-none" />
              </div>
              {[{ key: 'warmth', label: '温暖度' }, { key: 'humor', label: '幽默感' }, { key: 'formality', label: '正式度' }, { key: 'empathy', label: '同理心' }, { key: 'verbosity', label: '话痨度' }].map(({ key, label }) => (
                <div key={key}>
                  <div className="flex justify-between text-sm mb-1">
                    <span className="text-gray-600 dark:text-gray-400">{label}</span>
                    <span className="text-gray-900 dark:text-white font-mono">{(personality.traits as any)[key]?.toFixed(1)}</span>
                  </div>
                  <input type="range" min="0" max="1" step="0.1" value={(personality.traits as any)[key] || 0}
                    onChange={(e) => updateTrait(key, parseFloat(e.target.value))} className="w-full accent-blue-500" />
                </div>
              ))}
            </div>
          )}

          {activeTab === 'model' && (
            <div className="space-y-4">
              <div className="text-sm text-gray-500 dark:text-gray-400">模型配置通过 <code className="bg-gray-100 dark:bg-gray-700 px-1 rounded">.env</code> 文件设置。</div>
              <div className="text-sm text-gray-500 dark:text-gray-400 space-y-1">
                <p>当前配置:</p>
                <ul className="list-disc pl-4 space-y-0.5">
                  <li>修改 <code className="bg-gray-100 dark:bg-gray-700 px-1 rounded">.env</code> 中的 LITELLM_MODEL 来切换模型</li>
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

          {activeTab === 'appearance' && (
            <div className="space-y-5">
              <div>
                <div className="flex justify-between text-sm mb-1">
                  <span className="text-gray-600 dark:text-gray-400">正文字号</span>
                  <span className="text-gray-900 dark:text-white font-mono">{fontScale.toFixed(1)}x</span>
                </div>
                <input type="range" min="0.8" max="1.5" step="0.1" value={fontScale}
                  onChange={(e) => updateFontScale(parseFloat(e.target.value))} className="w-full accent-blue-500" />
                <p className="text-xs text-gray-400 mt-1">预览：<span style={{ fontSize: `calc(0.875rem * ${fontScale})` }}>这行字会跟随调整</span></p>
              </div>
              <div>
                <div className="flex justify-between text-sm mb-1">
                  <span className="text-gray-600 dark:text-gray-400">图标大小</span>
                  <span className="text-gray-900 dark:text-white font-mono">{iconScale.toFixed(1)}x</span>
                </div>
                <input type="range" min="0.8" max="1.5" step="0.1" value={iconScale}
                  onChange={(e) => updateIconScale(parseFloat(e.target.value))} className="w-full accent-blue-500" />
              </div>
            </div>
          )}
        </div>

        <div className="flex items-center justify-between px-6 py-4 border-t border-gray-200 dark:border-gray-700">
          {activeTab === 'personality' ? (
            <button onClick={handleReset} className="px-3 py-1.5 text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200">重置默认</button>
          ) : <div />}
          <div className="flex items-center gap-2">
            {saved && <span className="text-sm text-green-500">已保存</span>}
            {activeTab === 'personality' && (
              <button onClick={handleSavePersonality} className="px-4 py-1.5 text-sm font-medium bg-blue-500 text-white rounded-lg hover:bg-blue-600">保存</button>
            )}
            <button onClick={onClose} className="px-4 py-1.5 text-sm text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-gray-100">关闭</button>
          </div>
        </div>
      </div>
    </div>
  );
}
