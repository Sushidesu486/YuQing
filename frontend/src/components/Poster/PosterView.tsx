import { useEffect, useState } from 'react';
import { api } from '../../services/api';

const YUQING_AVATAR = '/avatar-yuqing.png';

interface Post {
  id: string;
  content: string;
  mood_label: string | null;
  warmth: number | null;
  openness: number | null;
  energy: number | null;
  trigger_type: string;
  created_at: string | null;
}

const MOOD_LABELS: Record<string, string> = {
  guarded: '平静',
  withdrawn: '心不在焉',
  relaxed: '悠闲',
  softened: '心情不错',
  vulnerable: '感性中',
};

const MOOD_COLORS: Record<string, string> = {
  guarded: 'text-gray-400 dark:text-gray-500',
  withdrawn: 'text-slate-400 dark:text-slate-400',
  relaxed: 'text-emerald-500 dark:text-emerald-400',
  softened: 'text-rose-400 dark:text-rose-400',
  vulnerable: 'text-purple-400 dark:text-purple-300',
};

function formatTime(iso: string | null): string {
  if (!iso) return '';
  const d = new Date(iso);
  const month = d.getMonth() + 1;
  const day = d.getDate();
  const hour = String(d.getHours()).padStart(2, '0');
  const min = String(d.getMinutes()).padStart(2, '0');
  return `${month}月${day}日 ${hour}:${min}`;
}

export function PosterView({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [posts, setPosts] = useState<Post[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchPosts = async () => {
    setLoading(true);
    try {
      const data = await api.get<{ posts: Post[] }>('/posts?limit=30');
      setPosts(data.posts);
    } catch (e) {
      console.error('Failed to fetch posts:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open) fetchPosts();
  }, [open]);

  const handleGenerate = async () => {
    setLoading(true);
    try {
      const data = await api.post<{ post: Post }>('/posts/generate');
      setPosts(prev => [data.post, ...prev]);
    } catch (e) {
      console.error('Failed to generate post:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && open) onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="absolute inset-0 z-30 bg-white dark:bg-gray-900 flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100 dark:border-gray-800">
        <h2 className="text-sm font-semibold text-gray-800 dark:text-gray-100">雨晴的说说</h2>
        <div className="flex gap-2">
          <button
            onClick={handleGenerate}
            disabled={loading}
            className="px-3 py-1 text-xs bg-blue-500 text-white rounded-lg hover:bg-blue-600 disabled:opacity-50 transition"
          >
            {loading ? '...' : '生成说说'}
          </button>
          <button onClick={onClose} className="text-sm text-blue-500">
            关闭
          </button>
        </div>
      </div>

      {/* Posts */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-4">
        {loading && posts.length === 0 && (
          <p className="text-gray-400 dark:text-gray-500 text-sm text-center mt-8">加载中...</p>
        )}
        {!loading && posts.length === 0 && (
          <div className="flex flex-col items-center justify-center mt-16 text-gray-400 dark:text-gray-500">
            <svg className="w-12 h-12 mb-3 opacity-30" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M6 12L3.269 3.125A59.769 59.769 0 0121.485 12 59.768 59.768 0 013.27 20.875L5.999 12zm0 0h7.5" />
            </svg>
            <span className="text-sm">还没有说说</span>
            <span className="text-xs mt-1">每天晚上，雨晴会发一条说说</span>
          </div>
        )}
        {posts.map((post) => {
          const moodLabel = post.mood_label || 'guarded';
          const moodText = MOOD_LABELS[moodLabel] || moodLabel;
          const moodColor = MOOD_COLORS[moodLabel] || 'text-gray-400 dark:text-gray-500';
          return (
            <div key={post.id} className="border-b border-gray-50 dark:border-gray-800 pb-3 last:border-0">
              {/* Avatar + Name + Time */}
              <div className="flex items-center gap-2 mb-2">
                <img
                  src={YUQING_AVATAR}
                  alt="雨晴"
                  className="w-9 h-9 rounded-full object-cover flex-shrink-0"
                />
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-gray-800 dark:text-gray-100">雨晴</span>
                    <span className={`text-xs ${moodColor}`}>{moodText}</span>
                  </div>
                  {post.created_at && (
                    <span className="text-xs text-gray-300 dark:text-gray-600">{formatTime(post.created_at)}</span>
                  )}
                </div>
              </div>
              {/* Content */}
              <p className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed ml-11">{post.content}</p>
            </div>
          );
        })}
      </div>
    </div>
  );
}
