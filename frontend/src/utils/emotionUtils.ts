export function getEmotionLabel(valence: number, arousal: number): string {
  if (valence > 0.3 && arousal > 0.5) return 'excited';
  if (valence > 0.3) return 'happy';
  if (valence > -0.3 && arousal < 0.3) return 'calm';
  if (valence < -0.3 && arousal > 0.5) return 'anxious';
  if (valence < -0.3) return 'sad';
  if (arousal > 0.7) return 'stressed';
  return 'neutral';
}

export function getEmotionColor(valence: number, arousal: number): string {
  const label = getEmotionLabel(valence, arousal);
  const colors: Record<string, string> = {
    excited: '#f59e0b',
    happy: '#10b981',
    calm: '#6366f1',
    content: '#10b981',
    serene: '#6366f1',
    anxious: '#ef4444',
    angry: '#ef4444',
    stressed: '#f97316',
    sad: '#3b82f6',
    depressed: '#6366f1',
    tired: '#6b7280',
    neutral: '#9ca3af',
  };
  return colors[label] || '#9ca3af';
}

export function getEmotionEmoji(valence: number, arousal: number): string {
  const label = getEmotionLabel(valence, arousal);
  const emojis: Record<string, string> = {
    excited: '🤩',
    happy: '😊',
    calm: '😌',
    content: '🙂',
    serene: '🧘',
    anxious: '😰',
    angry: '😤',
    stressed: '😰',
    sad: '😢',
    depressed: '😔',
    tired: '😴',
    neutral: '😐',
  };
  return emojis[label] || '😐';
}
