import json
import logging
from typing import AsyncGenerator, Optional

import aiomysql

from app.core.llm import stream_completion
from app.core.memory import memory_manager
from app.core.emotion import mood_regulator
from app.core.personality import personality_engine
from app.core.preferences import preference_learner
from app.config import settings

logger = logging.getLogger(__name__)


class CognitiveProcessor:
    """Central orchestrator: memory recall → emotion analysis → personality prompt → LLM → memory store."""

    async def process_message(
        self,
        conversation_id: Optional[str],
        user_message: str,
        language: str = "zh",
    ) -> AsyncGenerator:
        """
        Full cognitive pipeline. Yields SSE event dicts.
        Returns (conversation_id, full_response) via the "done" event.
        """
        import secrets
        from app.db.database import get_pool, _generate_id

        # --- Phase 1: Emotion analysis of user message ---
        user_emotion = None
        try:
            user_emotion = await mood_regulator.analyze_message_emotion(user_message)
            yield {"event": "emotion", "data": json.dumps({"type": "emotion", "valence": user_emotion["valence"], "arousal": user_emotion["arousal"], "dominant_emotion": user_emotion["label"]}, ensure_ascii=True)}
        except Exception as e:
            logger.warning(f"User emotion analysis failed: {e}")

        # --- Phase 2: Get current mood ---
        current_mood = await mood_regulator.get_current_mood(conversation_id)

        # --- Phase 3: Memory recall ---
        _, recalled_memories = await memory_manager.build_context(
            conversation_id, user_message
        )

        # Touch recalled memories (update access time)
        for mem in recalled_memories:
            try:
                await memory_manager.touch_memory(mem["id"])
            except Exception as e:
                logger.debug(f"Failed to touch memory {mem.get('id')}: {e}")

        # --- Phase 4: Build system prompt ---
        system_prompt = await personality_engine.build_system_prompt(
            language=language,
            current_mood=current_mood if current_mood["label"] != "neutral" else None,
            recalled_memories=recalled_memories,
        )

        # --- Phase 5: Store user message (before loading context so it's included) ---
        pool = await get_pool()
        user_msg_id = _generate_id()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                v = user_emotion["valence"] if user_emotion else None
                a = user_emotion["arousal"] if user_emotion else None
                await cur.execute(
                    "INSERT INTO messages (id, conversation_id, role, content, valence, arousal) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    (user_msg_id, conversation_id, "user", user_message, v, a),
                )

        # --- Phase 6: Load recent messages for context (includes the just-stored user message) ---
        messages = [{"role": "system", "content": system_prompt}]
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT role, content FROM messages "
                    "WHERE conversation_id = %s ORDER BY created_at DESC LIMIT %s",
                    (conversation_id, settings.MAX_CONTEXT_MESSAGES),
                )
                rows = await cur.fetchall()
        for row in reversed(rows):
            messages.append({"role": row["role"], "content": row["content"]})

        # --- Phase 7: Stream LLM response ---
        assistant_msg_id = secrets.token_hex(16)
        full_response = ""

        try:
            async for chunk in stream_completion(messages):
                full_response += chunk
                yield {"event": "token", "data": json.dumps({"type": "token", "content": chunk}, ensure_ascii=True)}
        except Exception as e:
            logger.error(f"LLM stream error: {e}")
            yield {"event": "error", "data": json.dumps({"type": "error", "error": str(e)}, ensure_ascii=True)}
            return

        logger.info(f"LLM response ({len(full_response)} chars): {full_response[:200]}...")

        # --- Phase 8: Store assistant message ---
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO messages (id, conversation_id, role, content, model_used) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (assistant_msg_id, conversation_id, "assistant", full_response, settings.LITELLM_MODEL),
                )
                # Auto-title
                await cur.execute(
                    "SELECT COUNT(*) as cnt FROM messages WHERE conversation_id = %s",
                    (conversation_id,),
                )
                row = await cur.fetchone()
                if row and row[0] <= 2:
                    title = user_message[:50] + ("..." if len(user_message) > 50 else "")
                    await cur.execute(
                        "UPDATE conversations SET title = %s WHERE id = %s AND (title = '' OR title IS NULL)",
                        (title, conversation_id),
                    )

        # --- Phase 9: Background tasks ---

        # Memory decay (run every ~10 exchanges based on conversation message count)
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "SELECT COUNT(*) as cnt FROM messages WHERE conversation_id = %s",
                        (conversation_id,),
                    )
                    row = await cur.fetchone()
                    msg_count = row[0] if row else 0
            if msg_count % 10 == 0:
                await memory_manager.apply_decay()
        except Exception as e:
            logger.debug(f"Memory decay skipped: {e}")

        # Memory consolidation (trigger when count exceeds threshold)
        try:
            await memory_manager.consolidate_memories()
        except Exception as e:
            logger.debug(f"Memory consolidation skipped: {e}")

        # Save emotion snapshot
        if user_emotion:
            try:
                await mood_regulator.save_emotion_snapshot(
                    conversation_id,
                    user_emotion["valence"],
                    user_emotion["arousal"],
                    user_emotion["label"],
                    trigger_summary=user_message[:100],
                )
            except Exception as e:
                logger.warning(f"Failed to save emotion snapshot: {e}")

        # Extract memories
        if settings.AUTO_MEMORY_EXTRACTION:
            try:
                extracted = await memory_manager.extract_and_store_memories(
                    conversation_id, user_message, full_response, language
                )
                if extracted:
                    yield {
                        "event": "memory_extracted",
                        "data": json.dumps({"type": "memory_extracted", "count": len(extracted)}, ensure_ascii=True),
                    }
            except Exception as e:
                logger.warning(f"Memory extraction failed: {e}")

        # Learn user preferences (every N exchanges)
        try:
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "SELECT COUNT(*) as cnt FROM messages WHERE conversation_id = %s",
                        (conversation_id,),
                    )
                    row = await cur.fetchone()
                    msg_count = row[0] if row else 0
            if msg_count % settings.PREFERENCE_LEARN_INTERVAL == 0:
                learned = await preference_learner.learn_from_conversation(
                    conversation_id, user_message, full_response
                )
                if learned:
                    logger.info(f"Preferences learned: {learned}")
        except Exception as e:
            logger.debug(f"Preference learning skipped: {e}")

        # --- Done ---
        yield {
            "event": "done",
            "data": json.dumps(
                {"type": "done", "message_id": assistant_msg_id, "conversation_id": conversation_id},
                ensure_ascii=True,
            ),
        }


cognitive_processor = CognitiveProcessor()
