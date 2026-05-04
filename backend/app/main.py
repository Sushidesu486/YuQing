import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.database import init_db, close_pool
from app.core.memory import init_mem0, sync_memories_to_mem0
from app.api.routes import chat, conversations, health, personality, memory, emotions, settings, preferences, proactive
from app.core.proactive import proactive_background_task
from app.core.info_retrieval import info_retrieval_background_task
from app.core.memory import sleep_cleanup_background_task

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting YuQing...")
    await init_db()
    init_mem0()
    await sync_memories_to_mem0()
    logger.info("Database and mem0 ready")

    # Start proactive background task
    task = asyncio.create_task(proactive_background_task())
    info_task = asyncio.create_task(info_retrieval_background_task())
    cleanup_task = asyncio.create_task(sleep_cleanup_background_task())

    yield

    # Cancel background tasks on shutdown
    task.cancel()
    info_task.cancel()
    cleanup_task.cancel()
    for t in (task, info_task, cleanup_task):
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


@app.get("/")
async def root():
    return {"name": "YuQing", "version": "0.1.0"}
