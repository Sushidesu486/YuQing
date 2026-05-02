import React, { useState, useEffect } from 'react';
import { Header } from './Header';
import { ChatView } from '../Chat/ChatView';
import { SettingsModal } from '../Settings/SettingsModal';

export function Layout() {
  const [showSettings, setShowSettings] = useState(false);

  return (
    <div className="h-screen flex flex-col bg-white">
      <Header onToggleSettings={() => setShowSettings(!showSettings)} />
      <ChatView />
      <SettingsModal open={showSettings} onClose={() => setShowSettings(false)} />
    </div>
  );
}
