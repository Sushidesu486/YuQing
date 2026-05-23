import React, { useState } from 'react';
import { Header } from './Header';
import { ChatView } from '../Chat/ChatView';
import { SettingsModal } from '../Settings/SettingsModal';
import { MemoryDebugPanel } from '../Memory/MemoryDebugPanel';
import { DiaryPanel } from '../Chat/DiaryPanel';
import { PosterView } from '../Poster/PosterView';

export function Layout() {
  const [showSettings, setShowSettings] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [memoryPanelOpen, setMemoryPanelOpen] = useState(false);
  const [diaryOpen, setDiaryOpen] = useState(false);
  const [posterOpen, setPosterOpen] = useState(false);

  return (
    <div className="h-screen flex flex-col bg-white dark:bg-gray-900">
      <Header
        onToggleSettings={() => setShowSettings(!showSettings)}
        onToggleSearch={() => setSearchOpen(!searchOpen)}
        onToggleMemory={() => setMemoryPanelOpen(!memoryPanelOpen)}
        onToggleDiary={() => setDiaryOpen(!diaryOpen)}
        onTogglePoster={() => setPosterOpen(!posterOpen)}
      />
      <div className="flex-1 min-h-0 relative flex flex-col">
        <ChatView searchOpen={searchOpen || memoryPanelOpen} onSearchOpenChange={(v) => {
          if (searchOpen) setSearchOpen(v);
          else setMemoryPanelOpen(v);
        }} />
        <DiaryPanel open={diaryOpen} onClose={() => setDiaryOpen(false)} />
      </div>
      <SettingsModal open={showSettings} onClose={() => setShowSettings(false)} />
      <MemoryDebugPanel open={memoryPanelOpen} onClose={() => setMemoryPanelOpen(false)} />
      <PosterView open={posterOpen} onClose={() => setPosterOpen(false)} />
    </div>
  );
}
