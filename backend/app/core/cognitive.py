import asyncio
import json
import logging
import re
from typing import AsyncGenerator, Optional

import aiomysql

from app.core.llm import stream_completion, stream_with_tools
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

        # --- Phase 2.1: Get user emotion trajectory ---
        emotion_trajectory = None
        try:
            emotion_trajectory = await mood_regulator.get_emotion_trajectory(conversation_id)
        except Exception as e:
            logger.debug(f"Emotion trajectory failed: {e}")

        # --- Phase 2.15: Get user emotion profile (cross-session) ---
        emotion_profile = None
        try:
            emotion_profile = await mood_regulator.get_emotion_profile()
            # Trigger background update if enough new snapshots
            if await mood_regulator.should_update_profile(conversation_id):
                asyncio.create_task(mood_regulator.update_emotion_profile())
        except Exception as e:
            logger.debug(f"Emotion profile failed: {e}")

        # --- Phase 2.2: Compute temporal context ---
        temporal_context = None
        if settings.TEMPORAL_ENABLED:
            try:
                from app.core.temporal import get_temporal_context
                temporal_context = await get_temporal_context(conversation_id)
            except Exception as e:
                logger.debug(f"Temporal context failed: {e}")

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
        current_mood_warmth = yuqing_mood["warmth"] if yuqing_mood else 0.0
        _, layered_memory = await memory_manager.build_context(
            conversation_id, user_message,
            current_mood_warmth=current_mood_warmth,
        )

        # Touch all recalled memories (update access time)
        all_recalled = (
            layered_memory.get("facts", []) +
            layered_memory.get("events", []) +
            layered_memory.get("episodic", []) +
            layered_memory.get("emotion_influences", [])
        )
        for mem in all_recalled:
            mem_id = mem.get("id")
            if not mem_id:
                continue
            try:
                await memory_manager.touch_memory(mem_id)
            except Exception as e:
                logger.debug(f"Failed to touch memory {mem_id}: {e}")

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

        # --- Phase 4: Build system prompts (split for prefix cache) ---
        stable_prompt, dynamic_prompt = await personality_engine.build_system_prompts(
            language=language,
            conversation_id=conversation_id,
            current_mood=current_mood if current_mood["label"] != "neutral" else None,
            recalled_memories=layered_memory,
            yuqing_mood=yuqing_mood,
            temporal_context=temporal_context,
            emotion_trajectory=emotion_trajectory,
            emotion_profile=emotion_profile,
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
        # Merge split prompts into one system message (multiple system messages break some LLM APIs)
        system_prompt = stable_prompt + "\n\n" + dynamic_prompt
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
                    "SELECT role, content, content_type FROM messages "
                    "WHERE conversation_id = %s ORDER BY created_at DESC LIMIT %s",
                    (conversation_id, settings.MAX_CONTEXT_MESSAGES),
                )
                rows = await cur.fetchall()
        for row in reversed(rows):
            if row.get("content_type") == "sticker":
                # Inject sticker as /name format so LLM sees the correct format in history
                if row["role"] == "assistant":
                    sticker_path = row.get("content", "")
                    basename = sticker_path.split("/")[-1] if "/" in sticker_path else sticker_path
                    messages.append({"role": "assistant", "content": f"/{basename}"})
                continue
            messages.append({"role": row["role"], "content": row["content"]})

        # --- Phase 7: Stream LLM response (with tool calling support) ---
        assistant_msg_id = secrets.token_hex(16)
        full_response = ""

        # Load tool schemas if enabled
        tools_schemas = []
        if settings.TOOLS_ENABLED:
            try:
                from app.core.tools.registry import tool_registry
                tools_schemas = tool_registry.get_all_definitions()
            except Exception as e:
                logger.debug(f"Tool loading failed: {e}")

        has_tools = len(tools_schemas) > 0
        max_tool_rounds = settings.TOOLS_MAX_ROUNDS if has_tools else 0
        tool_round = 0

        try:
            while tool_round <= max_tool_rounds:
                tool_round += 1
                tool_calls_collected = []

                if has_tools and tool_round <= max_tool_rounds:
                    # Use tool-aware streaming
                    async for event in stream_with_tools(
                        messages,
                        tools=tools_schemas,
                    ):
                        if event.type == "content":
                            full_response += event.content
                            yield {"event": "token", "data": json.dumps({"type": "token", "content": event.content}, ensure_ascii=True)}
                        elif event.type == "tool_call_start":
                            yield {"event": "tool_call", "data": json.dumps({
                                "type": "tool_call", "status": "started", "tool": event.tool_name,
                            }, ensure_ascii=True)}
                        elif event.type == "tool_call_end":
                            tool_calls_collected.append({
                                "id": event.tool_call_id,
                                "name": event.tool_name,
                                "arguments_json": event.arguments_json,
                            })
                else:
                    # Fallback: plain streaming (no tools or max rounds reached)
                    async for chunk in stream_completion(messages):
                        full_response += chunk
                        yield {"event": "token", "data": json.dumps({"type": "token", "content": chunk}, ensure_ascii=True)}

                # No tool calls → done
                if not tool_calls_collected:
                    break

                # Execute tool calls and build response messages
                for tc in tool_calls_collected:
                    tool_name = tc["name"]
                    try:
                        arguments = json.loads(tc["arguments_json"]) if tc["arguments_json"] else {}
                    except json.JSONDecodeError:
                        arguments = {}

                    logger.info(f"Tool call: {tool_name}({arguments})")
                    result = await tool_registry.execute_tool(tool_name, arguments)

                    yield {"event": "tool_call", "data": json.dumps({
                        "type": "tool_call", "status": "completed",
                        "tool": tool_name, "display": result.display,
                        "success": result.success,
                    }, ensure_ascii=True)}

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": result.content,
                    })

                # Append assistant message with tool_calls (OpenAI format requirement)
                messages.append({
                    "role": "assistant",
                    "content": full_response if full_response else None,
                    "tool_calls": [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {"name": tc["name"], "arguments": tc["arguments_json"]},
                        }
                        for tc in tool_calls_collected
                    ],
                })

                # Reset for continuation stream
                full_response = ""

        except Exception as e:
            logger.error(f"LLM stream error: {e}")
            yield {"event": "error", "data": json.dumps({"type": "error", "error": str(e)}, ensure_ascii=True)}
            return

        logger.info(f"LLM response ({len(full_response)} chars): {full_response[:200]}...")

        # --- Phase 7.5: Extract sticker from LLM output ---
        # LLM writes /sticker_name on a separate line; parse and validate against STICKER_DEFINITIONS
        sticker_name = None
        sticker_defs = []
        try:
            from app.core.personality import STICKER_DEFINITIONS
            sticker_defs = STICKER_DEFINITIONS
            valid_names = {s["path"]: s for s in sticker_defs}
            valid_basenames = {s["path"].split("/")[-1]: s["path"] for s in sticker_defs}
            # Also support matching by full path (e.g. /happy/peekaboo)
            valid_names_set = set(valid_names.keys()) | set(valid_basenames.keys())

            # Parse /sticker_name from LLM response (check all lines, prefer last match)
            lines = full_response.strip().split('\n')
            for line in reversed(lines):
                stripped = line.strip()
                # Match patterns: /peekaboo, /happy/peekaboo, /peekaboo （with trailing junk）
                match = re.match(r'^(/[\w/]+)', stripped)
                if match:
                    candidate = match.group(1)
                    # Strip leading slash for lookup
                    candidate_key = candidate.lstrip('/')
                    # Try basename first
                    if candidate_key in valid_basenames:
                        sticker_name = valid_basenames[candidate_key]
                    elif candidate in valid_names:
                        sticker_name = valid_names[candidate]
                    elif candidate_key in valid_names:
                        sticker_name = valid_names[candidate_key]
                    if sticker_name:
                        break
        except Exception as e:
            logger.debug(f"Sticker extraction skipped: {e}")

        # --- Phase 8: Store assistant message ---
        # Clean response text (remove sticker reference from stored text)
        clean_response = full_response
        if sticker_name:
            basename = sticker_name.split('/')[-1]
            clean_response = clean_response.replace(f"/{sticker_name}", "")
            clean_response = clean_response.replace(f"/{basename}", "")
            clean_response = re.sub(r'\n{3,}', '\n\n', clean_response).strip()

        # Safety: strip text-based sticker descriptions the LLM might mistakenly output
        clean_response = re.sub(r'[（(]发了[一张个]?贴纸[）)]', '', clean_response)
        clean_response = re.sub(r'\n{3,}', '\n\n', clean_response).strip()

        display_response = clean_response if clean_response else full_response
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO messages (id, conversation_id, role, content, content_type, model_used) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    (assistant_msg_id, conversation_id, "assistant", display_response, "text", settings.LITELLM_MODEL),
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

        # Store sticker as a separate message row
        if sticker_name:
            sticker_msg_id = secrets.token_hex(16)
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "INSERT INTO messages (id, conversation_id, role, content, content_type) "
                        "VALUES (%s, %s, %s, %s, %s)",
                        (sticker_msg_id, conversation_id, "assistant", sticker_name, "sticker"),
                    )

        # --- Done (yield immediately after storing, before background tasks) ---
        yield {
            "event": "done",
            "data": json.dumps(
                {"type": "done", "message_id": assistant_msg_id, "conversation_id": conversation_id},
                ensure_ascii=True,
            ),
        }

        # --- Sticker event (after done) ---
        if sticker_name:
            yield {
                "event": "sticker",
                "data": json.dumps(
                    {"type": "sticker", "name": sticker_name, "conversation_id": conversation_id},
                    ensure_ascii=True,
                ),
            }

        # Generator ends here — stream closes, frontend spinner stops.
        # All background tasks run as true fire-and-forget (don't block the stream).

        # Save emotion snapshot (fast, keep inline)
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

        # --- Phase 9: Background tasks (true fire-and-forget) ---
        async def _background_tasks():
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

                # Memory decay
                if msg_count % 10 == 0:
                    await memory_manager.apply_decay()

                # Memory consolidation
                if msg_count % 20 == 0:
                    await memory_manager.consolidate_memories()

                # Self-narrative update
                if msg_count % 10 == 0:
                    from app.core.self_cognition import self_cognition_engine
                    await self_cognition_engine.check_and_update()

                # Reflect-Evolve
                from app.config import settings as cfg
                if msg_count % cfg.EVOLVE_REFLECT_INTERVAL == 0:
                    from app.core.self_cognition import self_cognition_engine
                    await self_cognition_engine.reflect_and_evolve(msg_count)

                # Extract memories
                if settings.AUTO_MEMORY_EXTRACTION:
                    # --- Phase 8.5: Inner monologue (fire-and-forget, don't block extraction) ---
                    if settings.INNER_MONOLOGUE_ENABLED:
                        async def _monologue_task():
                            try:
                                await memory_manager._generate_inner_monologue(
                                    user_message, full_response, language,
                                    conversation_id=conversation_id,
                                )
                            except Exception as e:
                                logger.debug(f"Inner monologue bg failed: {e}")
                        asyncio.create_task(_monologue_task())

                    extracted = await memory_manager.extract_and_store_memories(
                        conversation_id, user_message, full_response, language,
                        recalled_facts=layered_memory.get("facts", []) + layered_memory.get("events", []),
                    )
                    if extracted:
                        logger.info(f"Background: extracted {len(extracted)} memories")

                # Learn user preferences
                if msg_count % (settings.PREFERENCE_LEARN_INTERVAL * 2) == 0:
                    learned = await preference_learner.learn_from_conversation(
                        conversation_id, user_message, full_response
                    )
                    if learned:
                        logger.info(f"Background: preferences learned: {learned}")
            except Exception as e:
                logger.debug(f"Background tasks error: {e}")

        asyncio.create_task(_background_tasks())


cognitive_processor = CognitiveProcessor()
