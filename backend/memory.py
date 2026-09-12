"""Long-term memory for the VoxPath agent.

Facts worth remembering across conversations live in the LangGraph store,
which is Postgres-backed with a pgvector index (see main.lifespan). That is a
different thing from the checkpointer: the checkpointer replays one thread's
raw messages, while this survives across every thread for a given user.

The store is reached through get_store() rather than being passed in, so these
stay plain functions whose signatures are exactly what the model sees. The cost
is that they only work inside a LangGraph run -- calling them over the /mcp HTTP
mount raises, which is why each one says so in its error.
"""

from __future__ import annotations

import os
import uuid

from langgraph.config import get_config, get_store

from logging_config import get_logger

log = get_logger("voxpath.memory")

# Namespaced per user so memories never leak between people. There is no auth
# yet, so everything lands under one id; the shape is what matters, since
# re-namespacing existing rows later is far more painful than carrying the
# parameter now.
DEFAULT_USER_ID = "default"
MEMORY_NAMESPACE = "memories"

# Absolute cosine scores move a lot with how the question is phrased, so this is
# only a noise floor, not a relevance test. Measured against two stored facts:
# the correct memory scored 0.466 for "home station" but 0.133 for the terser
# "class preference", while an unrelated memory scored as high as 0.198 -- the
# ranges overlap, so any threshold strict enough to exclude the noise also drops
# correct answers. The model is given each score and decides what to trust; this
# floor only removes hits that are clearly nothing.
MIN_SCORE = float(os.getenv("MEMORY_MIN_SCORE", "0.12"))


def _require_store():
    store = get_store()
    if store is None:
        raise RuntimeError(
            "No memory store configured. Set DATABASE_URL and restart the API."
        )
    return store


def _user_id() -> str:
    """Current user id, from the run config when the caller supplies one."""
    try:
        config = get_config()
    except RuntimeError:
        return DEFAULT_USER_ID
    configurable = (config or {}).get("configurable") or {}
    return configurable.get("user_id") or DEFAULT_USER_ID


def _namespace() -> tuple[str, str]:
    return (MEMORY_NAMESPACE, _user_id())


async def save_memory(text: str) -> dict[str, str]:
    """Store one durable fact about the user."""
    fact = text.strip()
    if not fact:
        return {"status": "ignored", "reason": "empty memory"}

    store = _require_store()
    namespace = _namespace()
    key = uuid.uuid4().hex[:12]
    await store.aput(namespace, key, {"text": fact})
    log.info("saved memory %s for %s: %r", key, namespace[1], fact[:80])
    return {"status": "saved", "id": key, "text": fact}


async def search_memories(query: str, limit: int = 3) -> dict[str, object]:
    """Recall previously saved facts most similar in meaning to the query."""
    store = _require_store()
    namespace = _namespace()
    limit = max(1, min(limit, 10))

    hits = await store.asearch(namespace, query=query, limit=limit)
    memories = [
        {"id": hit.key, "text": hit.value.get("text", ""), "score": round(hit.score, 3)}
        for hit in hits
        # score is None when the store has no vector index, in which case this
        # degrades to prefix search and every hit is worth returning.
        if hit.score is None or hit.score >= MIN_SCORE
    ]
    log.info(
        "memory search %r for %s: %d/%d above %.2f",
        query[:60], namespace[1], len(memories), len(hits), MIN_SCORE,
    )
    return {"memories": memories, "count": len(memories)}
