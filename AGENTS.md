# AGENTS.md — YuQing

## What this is

Full-stack AI companion app: **FastAPI** (Python) backend + **React 19 / TypeScript / Vite** frontend + **MySQL 9**. The AI persona "YuQing" has memory, emotion, personality, mood, proactive messaging, and tool calling. Chinese-first (i18n supported).

## Running

Requires: MySQL 8+ running, Python 3.9+, Node.js 18+.

```bash
# 1. Create database
mysql -u root -p -e "CREATE DATABASE yuqing CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

# 2. Copy .env and fill in LLM API key + MySQL password
cp .env.example .env

# 3. Backend (from project root, NOT from backend/)
cd backend
pip install -r requirements.txt
PYTHONPATH=. python3 -m uvicorn app.main:app --reload --port 8000

# 4. Frontend (separate terminal)
cd frontend
npm install
npm run dev
```

Frontend runs on `:5173`, proxies `/api` to backend on `:8000` (configured in `frontend/vite.config.ts`).

**Critical**: Backend must be launched with `PYTHONPATH=.` from the `backend/` directory. All imports use `app.*` prefix (e.g., `from app.config import settings`).

## .env location

The `.env` file lives in the **project root** (`/Users/shouss/Project/YuQing/.env`), not in `backend/`. `config.py` resolves it via `_PROJECT_ROOT / ".env"`.

## No tests or CI

There are no test files, no test runner config, no CI workflows, no Makefile, no Dockerfile. When making changes, verify manually by running both servers and testing in the browser.

## Lint / format

```bash
# Frontend
cd frontend && npm run lint      # ESLint (flat config, eslint.config.js)
cd frontend && npm run build     # tsc -b && vite build (catches type errors)
```

No Python linter/formatter configured. No pre-commit hooks.

## Backend architecture

The central orchestrator is `backend/app/core/cognitive.py` — a 10-phase pipeline:
1. Emotion analysis (V-A model)
2. Mood update
3. Temporal context
4. Memory recall (BGE embedding + MySQL)
5. Passive info retrieval (Tavily/RSS, on-demand)
6. Personality prompt construction (Jinja2 templates)
7. Message store + context load + LLM streaming
8. Tool calling (multi-round, max 3)
9. Reply storage + stickers
10. Memory extraction / correction / decay / consolidation

**Key modules** (`backend/app/core/`):
| File | Role |
|------|------|
| `memory.py` | BGE embedding + MySQL memory system (largest file, ~2000+ lines) |
| `personality.py` | YAML personality + Jinja2 prompt generation |
| `mood.py` | YuQing's 3D mood tracker (warmth/openness/energy) |
| `emotion.py` | User emotion analysis (V-A model) |
| `temporal.py` | Time awareness (session gaps, time-of-day, tenure) |
| `proactive.py` | Background proactive messaging (4 triggers) |
| `self_cognition.py` | Self-narrative synthesis + Reflect-Evolve personality evolution (audit log: `personality_evolution` table) |
| `info_retrieval.py` | Tavily + RSS knowledge retrieval |
| `tools/` | Tool registry + 4 built-in tools (recall_memories, search_web, read_latest_articles, search_knowledge) |
| `llm.py` | litellm wrapper (streaming/non-streaming) |

## Frontend architecture

`frontend/src/`:
- `components/Chat/` — WeChat-style chat UI (ChatView, MessageList, MessageBubble, InputBar, SearchPanel)
- `components/Memory/` — Memory debug panel (4 tabs: overview, list, recall debug, force graph)
- `components/Layout/` — Page layout + Header
- `components/Sidebar/` — Conversation list
- `hooks/` — `useChat`, `useConversations`, `useProactive` (SSE)
- `services/api.ts` — API client
- `types/index.ts` — TypeScript types
- `i18n/` — Chinese/English translations (zh.json, en.json)

Uses **Tailwind CSS v4** (via `@tailwindcss/vite` plugin, NOT PostCSS). React 19, no state management library (hooks + props).

## Database

MySQL, auto-initialized on startup (`database.py` `init_db()` creates all tables). 12 tables:
`conversations`, `messages`, `memories`, `emotion_snapshots`, `yuqing_mood_log`, `proactive_messages`, `personality_config`, `app_settings`, `user_preferences`, `knowledge_items`, `memory_links`, `personality_evolution`.

Connection pool via `aiomysql` (pool size 10). All IDs are UUID hex (32 chars).

## Embedding model

`BAAI/bge-base-zh-v1.5` (768-dim, local via `sentence-transformers`). Loads on startup and stays in memory. First request after startup is slow (~30s for model load). All memory content must be in Chinese for optimal recall.

## Personality config

`backend/personality/default.yaml` — YuQing's base personality. DB can override traits at runtime. Jinja2 templates in `backend/app/prompts/` are split into `system_{lang}_stable.txt.j2` (personality + rules, rarely changed) and `system_{lang}_dynamic.txt.j2` (mood/memory/temporal, refreshed each request), composed via `system_{lang}.txt.j2`.

## Tool calling

Extensible: create a class inheriting `BaseTool`, implement `get_definition()` and `execute()`, import in `app/core/tools/__init__.py`. Auto-registered via singleton `ToolRegistry`.

## Known issues (from plan.md)

- `messages.prompt_tokens` / `completion_tokens` never written (litellm streaming limitation)
- `emotion_snapshots`, `yuqing_mood_log`, `knowledge_items` have no cleanup (grow indefinitely)
- `memories.source_message_id` never populated
