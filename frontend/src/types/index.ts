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

// Memory debug types
export interface MemoryStats {
  memory_link_enabled: boolean;
  dedup_enabled: boolean;
  sleep_cleanup_enabled: boolean;
  total_memories: number;
  total_links: number;
  by_type: Record<string, { count: number; avg_importance: number }>;
  consolidated_count: number;
  invalid_count: number;
  avg_importance: number;
  last_sleep_cleanup: string | null;
}

export interface MemoryItem {
  id: string;
  content: string;
  category?: string;
  memory_type?: string;
  importance?: number;
  valence?: number;
  confidence?: number;
  created_at?: string;
}

export interface RecallStage {
  source: string;
  content: string;
  memory_type?: string;
  importance?: number;
  semantic_sim?: number;
  activation?: number;
  hybrid_score?: number;
  score?: number;
  dormant_days?: number;
  id?: string;
}

export interface RecallDebugResult {
  query: string;
  stage_semantic_search: RecallStage[];
  stage_pinned: RecallStage[];
  stage_activation_spread: {
    enabled: boolean;
    seed_count: number;
    spread_count: number;
    iterations: number;
    spread_memories: Array<{
      id: string;
      content: string;
      activation: number;
      memory_type?: string;
      importance?: number;
    }>;
  };
  stage_dormant: RecallStage[];
  stage_final_scored: RecallStage[];
  stage_layered: {
    facts: Array<{ id: string; content: string; memory_type?: string; created_at_relative?: string }>;
    events: Array<{ id: string; content: string; created_at_relative?: string }>;
    episodic: Array<{ content: string; valence: number }>;
    behavior_rules: string[];
    emotion_influences: Array<{ trigger: string; expected_valence: number }>;
  };
  memory_links_count: number;
  total_memories_count: number;
}

export interface MemoryLink {
  id: string;
  source_id: string;
  target_id: string;
  link_type: string;
  strength: number;
  created_at: string;
  source_content?: string;
  source_type?: string;
  target_content?: string;
  target_type?: string;
}

export interface CleanupResult {
  invalid_deleted: number;
  clusters_merged: number;
}
