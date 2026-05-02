import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.database import init_db, close_pool
from app.db.vector import init_chroma
from app.api.routes import chat, conversations, health, personality, memory, emotions, settings, preferences, proactive
from app.core.proactive import proactive_background_task

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting YuQing...")
    await init_db()
    await init_chroma()
    logger.info("Database and ChromaDB ready")

    # Start proactive background task
    task = asyncio.create_task(proactive_background_task())

    yield

    # Cancel background task on shutdown
    task.cancel()
    try:
        await task
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
