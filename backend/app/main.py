import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.database import init_db, close_pool
from app.core.memory import _get_embedding_model, maybe_unload_idle_model
from app.api.routes import chat, conversations, health, personality, memory, emotions, settings, preferences, proactive, diary, posts
from app.core.proactive import proactive_background_task
from app.core.info_retrieval import info_retrieval_background_task, close_http_session
from app.core.openai_client import close_openai_session
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
logging.getLogger("openai").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting YuQing...")
    await init_db()
    _get_embedding_model()  # Pre-load embedding model

    # Compute identity hash baseline on first startup (async, non-blocking)
    asyncio.create_task(_init_identity_baseline())

    logger.info("Database and embedding model ready")

    # Start background tasks
    proactive_task = asyncio.create_task(proactive_background_task())
    info_task = asyncio.create_task(info_retrieval_background_task())
    cleanup_task = asyncio.create_task(sleep_cleanup_background_task())
    model_gc_task = asyncio.create_task(model_idle_gc_task())
    poster_task = asyncio.create_task(poster_background_task())

    yield

    # Cancel background tasks on shutdown
    proactive_task.cancel()
    info_task.cancel()
    cleanup_task.cancel()
    model_gc_task.cancel()
    poster_task.cancel()
    for t in (proactive_task, info_task, cleanup_task, model_gc_task, poster_task):
        try:
            await t
        except asyncio.CancelledError:
            pass

    await close_pool()
    await close_http_session()
    await close_openai_session()
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
app.include_router(diary.router)
app.include_router(posts.router)


@app.get("/")
async def root():
    return {"name": "YuQing", "version": "0.1.0"}


async def model_idle_gc_task():
    """Background task: release idle model + periodically clean GPU/CPU memory."""
    await asyncio.sleep(120)  # wait 2 min after startup
    import gc
    import torch
    from app.config import settings
    while True:
        try:
            maybe_unload_idle_model()
            # Periodically force Python GC + PyTorch CPU cache cleanup to prevent
            # CPU memory leak from model.encode() tensor allocations on macOS.
            gc.collect()
            try:
                torch.cuda.empty_cache()
            except Exception:
                pass
            try:
                torch.cpu.empty_cache()
            except Exception:
                pass
        except Exception as e:
            logger.debug(f"Model GC check failed: {e}")

        await asyncio.sleep(300)  # check every 5 minutes


async def _init_identity_baseline():
    """Compute and store identity hash baseline on first startup."""
    try:
        from app.core.self_cognition import self_cognition_engine
        await self_cognition_engine.check_identity_baseline()
    except Exception as e:
        logger.warning(f"Identity baseline init skipped: {e}")
