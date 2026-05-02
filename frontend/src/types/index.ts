export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  valence?: number | null;
  arousal?: number | null;
  model_used?: string;
  created_at?: string;
  trigger_type?: string | null;
}

export interface Conversation {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  is_archived: number;
}

export interface EmotionState {
  valence: number;
  arousal: number;
  dominant_emotion?: string;
}

export interface PersonalityConfig {
  name: string;
  description: string;
  traits: {
    warmth: number;
    humor: number;
    formality: number;
    empathy: number;
    verbosity: number;
  };
  communication_style: {
    use_emoji: boolean;
    proactive_care: boolean;
    response_tone: string;
  };
  values: string[];
  constraints: string[];
}
