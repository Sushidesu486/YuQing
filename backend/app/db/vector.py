import logging
from typing import Optional

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.config import settings

logger = logging.getLogger(__name__)

_client: Optional[chromadb.ClientAPI] = None
_collection_name = "long_term_memory"


async def init_chroma() -> chromadb.Collection:
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(
            path=settings.chroma_abs_path,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        logger.info(f"ChromaDB initialized at {settings.chroma_abs_path}")
    # Get or create collection
    try:
        collection = _client.get_collection(_collection_name)
    except Exception:
        collection = _client.create_collection(_collection_name)
        logger.info(f"Created ChromaDB collection: {_collection_name}")
    return collection


async def get_collection() -> chromadb.Collection:
    return await init_chroma()


async def search_memories(query: str, top_k: int = 5) -> list:
    """Vector search for relevant memories."""
    collection = await get_collection()
    if collection.count() == 0:
        return []
    results = collection.query(
        query_texts=[query],
        n_results=min(top_k, collection.count()),
    )
    memories = []
    for i, doc in enumerate(results["documents"][0]):
        memories.append({
            "content": doc,
            "id": results["ids"][0][i],
            "distance": results["distances"][0][i],
            "metadata": results["metadatas"][0][i],
        })
    return memories


async def add_memory(memory_id: str, content: str, metadata: dict):
    """Add a memory to the vector store."""
    collection = await get_collection()
    collection.add(
        documents=[content],
        ids=[memory_id],
        metadatas=[metadata],
    )


async def update_memory_metadata(memory_id: str, metadata: dict):
    """Update metadata for an existing memory in the vector store."""
    collection = await get_collection()
    try:
        collection.update(
            ids=[memory_id],
            metadatas=[metadata],
        )
    except Exception:
        pass


async def delete_memory(memory_id: str):
    """Remove a memory from the vector store."""
    collection = await get_collection()
    try:
        collection.delete(ids=[memory_id])
    except Exception:
        pass
