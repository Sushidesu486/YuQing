import json
import logging
from typing import AsyncGenerator, Optional

import aiomysql

from app.core.llm import stream_completion
from app.core.memory import memory_manager
from app.core.emotion import mood_regulator
from app.core.mood import yuqing_mood_tracker
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

        # --- Phase 2.5: Update YuQing's own mood ---
        yuqing_mood = None
        try:
            from datetime import datetime
            # Detect return-from-absence
            pool_for_absence = await get_pool()
            async with pool_for_absence.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "SELECT created_at FROM messages "
                        "WHERE conversation_id = %s AND role = 'user' "
                        "ORDER BY created_at DESC LIMIT 1 OFFSET 1",
                        (conversation_id,),
                    )
                    row = await cur.fetchone()
            if row:
                hours_since_last = (datetime.utcnow() - row[0]).total_seconds() / 3600
                if hours_since_last >= settings.PROACTIVE_ABSENCE_THRESHOLD_HOURS:
                    yuqing_mood = await yuqing_mood_tracker.apply_return_bump(conversation_id)

            # Normal mood update
            if yuqing_mood is None:
                yuqing_mood = await yuqing_mood_tracker.update_mood(
                    conversation_id=conversation_id,
                    user_emotion=user_emotion,
                    user_message=user_message,
                    trigger_type="conversation",
                )
        except Exception as e:
            logger.warning(f"YuQing mood update failed: {e}")

        if yuqing_mood:
            yield {"event": "mood", "data": json.dumps({"type": "yuqing_mood", **yuqing_mood}, ensure_ascii=True)}

        # --- Phase 3: Memory recall (layered) ---
        _, layered_memory = await memory_manager.build_context(
            conversation_id, user_message
        )

        # Touch all recalled memories (update access time)
        all_recalled = (
            layered_memory.get("facts", []) +
            layered_memory.get("events", [])
        )
        for mem in all_recalled:
            try:
                await memory_manager.touch_memory(mem["id"])
            except Exception as e:
                logger.debug(f"Failed to touch memory {mem.get('id')}: {e}")

        # --- Phase 3.5: Reactive info retrieval ---
        reactive_knowledge = None
        if settings.INFO_RETRIEVAL_REACTIVE_ENABLED and settings.TAVILY_API_KEY:
            try:
                from app.core.info_retrieval import InfoRetrievalEngine
                engine = InfoRetrievalEngine()
                reactive_knowledge = await engine.reactive_retrieval(
                    conversation_id, user_message
                )
                if reactive_knowledge:
                    yield {"event": "knowledge", "data": json.dumps({
                        "type": "knowledge_retrieved",
                        "count": len(reactive_knowledge),
                    }, ensure_ascii=True)}
            except Exception as e:
                logger.debug(f"Reactive retrieval skipped: {e}")

        # --- Phase 4: Build system prompt ---
        system_prompt = await personality_engine.build_system_prompt(
            language=language,
            current_mood=current_mood if current_mood["label"] != "neutral" else None,
            recalled_memories=layered_memory,
            yuqing_mood=yuqing_mood,
        )

        # --- Phase 5: Store user message(s) (split batched messages) ---
        pool = await get_pool()
        user_lines = [line.strip() for line in user_message.split('\n') if line.strip()]
        v = user_emotion["valence"] if user_emotion else None
        a = user_emotion["arousal"] if user_emotion else None
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                for line in user_lines:
                    msg_id = _generate_id()
                    await cur.execute(
                        "INSERT INTO messages (id, conversation_id, role, content, valence, arousal) "
                        "VALUES (%s, %s, %s, %s, %s, %s)",
                        (msg_id, conversation_id, "user", line, v, a),
                    )

        # --- Phase 6: Load recent messages for context (includes the just-stored user message) ---
        messages = [{"role": "system", "content": system_prompt}]

        # Inject reactive knowledge as system context
        if reactive_knowledge:
            knowledge_text = "\n".join(
                f"- [{k['topic']}] {k['content']}" for k in reactive_knowledge
            )
            messages.append({
                "role": "system",
                "content": f"你刚刚查到了以下信息，可以在回复中自然地引用：\n{knowledge_text}",
            })

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

        # Memory consolidation (trigger when count exceeds threshold, run every 20 exchanges)
        try:
            if msg_count % 20 == 0:
                await memory_manager.consolidate_memories()
                await memory_manager.consolidate_self_memories()
        except Exception as e:
            logger.debug(f"Memory consolidation skipped: {e}")

        # Self-narrative update (check if regeneration needed, every 10 messages)
        try:
            if msg_count % 10 == 0:
                from app.core.self_cognition import self_cognition_engine
                await self_cognition_engine.check_and_update()
        except Exception as e:
            logger.debug(f"Self-narrative update skipped: {e}")

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

        # Extract memories (pass recalled facts for contradiction detection)
        if settings.AUTO_MEMORY_EXTRACTION:
            try:
                extracted = await memory_manager.extract_and_store_memories(
                    conversation_id, user_message, full_response, language,
                    recalled_facts=layered_memory.get("facts", []) + layered_memory.get("events", []),
                )
                if extracted:
                    yield {
                        "event": "memory_extracted",
                        "data": json.dumps({"type": "memory_extracted", "count": len(extracted)}, ensure_ascii=True),
                    }
            except Exception as e:
                logger.warning(f"Memory extraction failed: {e}")

        # Learn user preferences (every N user messages ≈ N*2 total messages)
        try:
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "SELECT COUNT(*) as cnt FROM messages WHERE conversation_id = %s",
                        (conversation_id,),
                    )
                    row = await cur.fetchone()
                    msg_count = row[0] if row else 0
            if msg_count % (settings.PREFERENCE_LEARN_INTERVAL * 2) == 0:
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
