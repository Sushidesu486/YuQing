import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.database import init_db, close_pool
from app.core.memory import _get_embedding_model
from app.api.routes import chat, conversations, health, personality, memory, emotions, settings, preferences, proactive, posts
from app.core.proactive import proactive_background_task
from app.core.info_retrieval import info_retrieval_background_task
from app.core.memory import sleep_cleanup_background_task
from app.core.poster import poster_background_task


class ColoredFormatter(logging.Formatter):
    """Color-coded log levels for terminal visibility."""

    COLORS = {
        logging.DEBUG:    "\033[90m",   # gray
        logging.INFO:     "\033[36m",   # cyan
        logging.WARNING:  "\033[33m",   # yellow
        logging.ERROR:    "\033[31m",   # red
        logging.CRITICAL: "\033[35m",   # magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelno, "")
        if color:
            record.levelname = f"{color}{record.levelname}{self.RESET}"
            record.msg = f"{color}{record.msg}{self.RESET}"
        return super().format(record)


handler = logging.StreamHandler()
handler.setFormatter(ColoredFormatter(
    "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
))
logging.root.handlers = [handler]
logging.root.setLevel(logging.INFO)

# Suppress noisy third-party INFO logs
logging.getLogger("LiteLLM").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting YuQing...")
    await init_db()
    _get_embedding_model()  # Pre-load embedding model

    # Enable litellm local response cache (for deterministic calls like emotion analysis)
    import litellm
    litellm.enable_cache(type="local", supported_call_types=["acompletion"])

    # Compute identity hash baseline on first startup (async, non-blocking)
    asyncio.create_task(_init_identity_baseline())

    logger.info("Database and embedding model ready")

    # Start proactive background task
    task = asyncio.create_task(proactive_background_task())
    info_task = asyncio.create_task(info_retrieval_background_task())
    cleanup_task = asyncio.create_task(sleep_cleanup_background_task())
    poster_task = asyncio.create_task(poster_background_task())

    yield

    # Cancel background tasks on shutdown
    task.cancel()
    info_task.cancel()
    cleanup_task.cancel()
    poster_task.cancel()
    for t in (task, info_task, cleanup_task, poster_task):
        try:
            await t
        except asyncio.CancelledError:
            pass

    await close_pool()
    logger.info("YuQing stopped")


app = FastAPI(title="YuQing", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router)
app.include_router(conversations.router)
app.include_router(health.router)
app.include_router(personality.router)
app.include_router(memory.router)
app.include_router(emotions.router)
app.include_router(settings.router)
app.include_router(preferences.router)
app.include_router(proactive.router)
app.include_router(posts.router)


@app.get("/")
async def root():
    return {"name": "YuQing", "version": "0.1.0"}


async def _init_identity_baseline():
    """Compute and store identity hash baseline on first startup."""
    try:
        from app.core.self_cognition import self_cognition_engine
        await self_cognition_engine.check_identity_baseline()
    except Exception as e:
        logger.warning(f"Identity baseline init skipped: {e}")
