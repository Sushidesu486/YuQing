import { useEffect, useState } from 'react';

const YUQING_AVATAR = '/avatar-yuqing.png';

interface Post {
  id: string;
  content: string;
  mood_label: string | null;
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
      const res = await fetch('/api/posts?limit=30');
      const data = await res.json();
      if (data.ok) setPosts(data.posts);
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
      const res = await fetch('/api/posts/generate', { method: 'POST' });
      const data = await res.json();
      if (data.ok) {
        setPosts(prev => [data.post, ...prev]);
      }
    } catch (e) {
      console.error('Failed to generate post:', e);
    } finally {
      setLoading(false);
    }
  };

  if (!open) return null;

  return (
    <div className="fixed right-0 top-0 h-full w-96 bg-white shadow-2xl z-50 flex flex-col border-l border-gray-200">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
        <h2 className="text-lg font-semibold text-gray-800">YuQing Poster</h2>
        <div className="flex gap-2">
          <button
            onClick={handleGenerate}
            disabled={loading}
            className="px-3 py-1 text-sm bg-blue-500 text-white rounded-lg hover:bg-blue-600 disabled:opacity-50"
          >
            {loading ? '...' : '生成'}
          </button>
          <button
            onClick={onClose}
            className="px-3 py-1 text-sm text-gray-400 hover:text-gray-600"
          >
            关闭
          </button>
        </div>
      </div>

      {/* Posts */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-4">
        {posts.length === 0 && !loading && (
          <p className="text-gray-400 text-sm text-center mt-8">还没有动态</p>
        )}
        {posts.map((post) => {
          const moodLabel = post.mood_label || 'guarded';
          const moodText = MOOD_LABELS[moodLabel] || moodLabel;
          return (
            <div key={post.id} className="border-b border-gray-50 pb-3 last:border-0">
              {/* Avatar + Name + Time */}
              <div className="flex items-center gap-2 mb-2">
                <img
                  src={YUQING_AVATAR}
                  alt="雨晴"
                  className="w-9 h-9 rounded-full object-cover flex-shrink-0"
                />
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-gray-800">雨晴</span>
                    <span className="text-xs text-gray-400">{moodText}</span>
                  </div>
                  {post.created_at && (
                    <span className="text-xs text-gray-300">{formatTime(post.created_at)}</span>
                  )}
                </div>
              </div>
              {/* Content */}
              <p className="text-sm text-gray-700 leading-relaxed ml-11">{post.content}</p>
            </div>
          );
        })}
      </div>
    </div>
  );
}
