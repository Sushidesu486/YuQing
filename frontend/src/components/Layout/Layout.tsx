import React, { useState } from 'react';
import { Header } from './Header';
import { ChatView } from '../Chat/ChatView';
import { SettingsModal } from '../Settings/SettingsModal';
import { MemoryDebugPanel } from '../Memory/MemoryDebugPanel';

export function Layout() {
  const [showSettings, setShowSettings] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [memoryPanelOpen, setMemoryPanelOpen] = useState(false);

  return (
    <div className="h-screen flex flex-col bg-white dark:bg-gray-900">
      <Header
        onToggleSettings={() => setShowSettings(!showSettings)}
        onToggleSearch={() => setSearchOpen(!searchOpen)}
        onToggleMemory={() => setMemoryPanelOpen(!memoryPanelOpen)}
      />
      <ChatView searchOpen={searchOpen || memoryPanelOpen} onSearchOpenChange={(v) => {
        if (searchOpen) setSearchOpen(v);
        else setMemoryPanelOpen(v);
      }} />
      <SettingsModal open={showSettings} onClose={() => setShowSettings(false)} />
      <MemoryDebugPanel open={memoryPanelOpen} onClose={() => setMemoryPanelOpen(false)} />
    </div>
  );
}
