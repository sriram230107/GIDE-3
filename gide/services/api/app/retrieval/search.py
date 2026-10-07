"""Hybrid retrieval: dense cosine (numpy over the course's chunk matrix) + Postgres full-text, fused with RRF."""
from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Optional
from uuid import UUID

import numpy as np
from sqlalchemy import func, select, text

from app.ai import llm
from app.database.models import Chunk, ContentUnit, Source
from app.retrieval.fusion import cosine_topk, normalize_rows, rrf_fuse

_cache: dict[UUID, tuple] = {}  # course_id -> (signature, ids, matrix)


@dataclass
class Hit:
    chunk_id: UUID
    text: str
    source_id: UUID
    primary_unit_id: UUID
    concept_id: Optional[UUID]
    topic_id: Optional[UUID]
    dense: float          # cosine similarity of the chunk to the query (0 if only found lexically)
    fused: float


async def _matrix(session, course_id: UUID):
    from app.core.config import settings
    active_model = settings.OLLAMA_EMBED_MODEL if settings.EMBED_PROVIDER == "ollama" else settings.GEMINI_EMBED_MODEL
    sig = (await session.execute(select(func.count(Chunk.id), func.max(Chunk.created_at)).where(Chunk.course_id == course_id))).one()
    sig = (sig[0], sig[1])
    cached = _cache.get(course_id)
    if cached and cached[0] == sig:
        return cached[1], cached[2]
    rows = (await session.execute(select(Chunk.id, Chunk.embedding, Chunk.embedding_model).where(Chunk.course_id == course_id, Chunk.embedding.is_not(None)))).all()
    if rows:
        for r in rows:
            if r[2] and r[2] != active_model:
                raise RuntimeError(f"rebuild required: chunk embedded with {r[2]} but active is {active_model}")
    ids = [r[0] for r in rows]
    mat = normalize_rows(np.asarray([r[1] for r in rows], dtype=np.float32)) if rows else np.zeros((0, 1), np.float32)
    _cache[course_id] = (sig, ids, mat)
    return ids, mat


def _or_query(q: str) -> str:
    words = [w for w in re.findall(r"[A-Za-z0-9]{3,}", q.lower())]
    return " | ".join(dict.fromkeys(words))


async def hybrid_search(session, course_id: UUID, query: str, k: int = 6, concept_ids: Optional[list[UUID]] = None,
                        use_lexical: bool = True) -> list[Hit]:
    ids, mat = await _matrix(session, course_id)
    if not ids:
        return []
    qv = (await llm.aembed_texts([query], "RETRIEVAL_QUERY"))[0]
    dense_top = cosine_topk(mat, qv, 30)
    dense_sims = {str(ids[i]): s for i, s in dense_top}
    dense_rank = [str(ids[i]) for i, _ in dense_top]

    lex_rank: list[str] = []
    tsq = _or_query(query)
    if use_lexical and tsq:
        rows = (await session.execute(text(
            "SELECT id::text FROM chunks WHERE course_id = :c AND to_tsvector('english', text) @@ to_tsquery('english', :q) "
            "ORDER BY ts_rank_cd(to_tsvector('english', text), to_tsquery('english', :q)) DESC LIMIT 30"),
            {"c": str(course_id), "q": tsq})).all()
        lex_rank = [r[0] for r in rows]

    fused = rrf_fuse([dense_rank, lex_rank] if lex_rank else [dense_rank])
    want = [cid for cid, _ in fused]
    chunks = {str(c.id): c for c in (await session.execute(select(Chunk).where(Chunk.id.in_([UUID(x) for x in want[:60]])))).scalars()}
    hits: list[Hit] = []
    id_pos = {str(i): n for n, i in enumerate(ids)}
    for cid, score in fused:
        c = chunks.get(cid)
        if not c:
            continue
        if concept_ids and c.concept_id not in concept_ids:
            continue
        dense = dense_sims.get(cid)
        if dense is None and cid in id_pos:
            dense = float(mat[id_pos[cid]] @ qv)
        hits.append(Hit(c.id, c.text, c.source_id, c.primary_unit_id, c.concept_id, c.topic_id, float(dense or 0.0), score))
        if len(hits) >= k:
            break
    return hits


async def citation_for(session, hit: Hit, n: int) -> dict:
    """Build a citation from the PRIMARY ContentUnit (the single provenance model)."""
    u = (await session.execute(select(ContentUnit).where(ContentUnit.id == hit.primary_unit_id))).scalar_one()
    src = (await session.execute(select(Source).where(Source.id == hit.source_id))).scalar_one()
    from app.core.storage import media_url_for
    return {"n": n, "chunk_id": str(hit.chunk_id), "unit_id": str(u.id), "source_id": str(src.id),
            "source_title": src.title, "source_type": src.source_type, "media_url": media_url_for(src.id, src.file_path),
            "page": u.page_number, "slide": u.slide_number, "time_start": u.time_start, "time_end": u.time_end,
            "image_path": u.image_path, "snippet": hit.text[:240]}


async def citation_for_unit(session, unit_id: UUID, n: int = 1, snippet: str = "") -> dict:
    from app.core.storage import media_url_for
    u = (await session.execute(select(ContentUnit).where(ContentUnit.id == unit_id))).scalar_one()
    src = (await session.execute(select(Source).where(Source.id == u.source_id))).scalar_one()
    return {"n": n, "unit_id": str(u.id), "source_id": str(src.id), "source_title": src.title,
            "source_type": src.source_type, "media_url": media_url_for(src.id, src.file_path),
            "page": u.page_number, "slide": u.slide_number, "time_start": u.time_start, "time_end": u.time_end,
            "image_path": u.image_path, "snippet": snippet or (u.content or "")[:240]}
