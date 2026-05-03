import React, { useState } from 'react';
import { Header } from './Header';
import { ChatView } from '../Chat/ChatView';
import { SettingsModal } from '../Settings/SettingsModal';

export function Layout() {
  const [showSettings, setShowSettings] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);

  return (
    <div className="h-screen flex flex-col bg-white">
      <Header
        onToggleSettings={() => setShowSettings(!showSettings)}
        onToggleSearch={() => setSearchOpen(!searchOpen)}
      />
      <ChatView searchOpen={searchOpen} onSearchOpenChange={setSearchOpen} />
      <SettingsModal open={showSettings} onClose={() => setShowSettings(false)} />
    </div>
  );
}
