import React from 'react';
import { getEmotionLabel, getEmotionColor, getEmotionEmoji } from '../../utils/emotionUtils';

interface Props {
  valence: number;
  arousal: number;
}

export function EmotionDisplay({ valence, arousal }: Props) {
  const label = getEmotionLabel(valence, arousal);
  const color = getEmotionColor(valence, arousal);
  const emoji = getEmotionEmoji(valence, arousal);

  // Map to position in a 200x200 box
  // valence: -1 (left) to +1 (right) → x: 20 to 180
  // arousal: 0 (bottom) to 1 (top) → y: 180 to 20
  const x = 100 + valence * 80;
  const y = 180 - arousal * 160;

  return (
    <div className="flex items-center gap-3">
      <div className="text-2xl">{emoji}</div>
      <div className="text-xs text-gray-500 dark:text-gray-400">
        <span className="font-medium" style={{ color }}>{label}</span>
        <span className="ml-1">
          V:{valence.toFixed(1)} A:{arousal.toFixed(1)}
        </span>
      </div>
    </div>
  );
}
