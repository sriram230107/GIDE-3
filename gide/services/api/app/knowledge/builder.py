"""Phase 2 orchestration: ContentUnits -> chunks -> embeddings -> topics/concepts -> prerequisite graph.

Knowledge rebuilds are transactional:
- Existing derived knowledge is removed only inside the active transaction.
- If any AI/retrieval/build step fails, the transaction rolls back.
- Existing knowledge therefore survives a failed rebuild.
"""

from __future__ import annotations

import random
from collections import Counter, defaultdict
from uuid import UUID, uuid4

from sqlalchemy import delete, select

from app.ai import llm
from app.core.database import AsyncSessionLocal
from app.core.config import settings
from app.database.models import (
    Chunk,
    Concept,
    ConceptPrereq,
    ContentUnit,
    Source,
    Topic,
)
from app.knowledge.canonical import (
    add_edges_acyclic,
    canonical_key,
    cluster_by_similarity,
)
from app.knowledge.chunking import chunk_units, search_text


TOPIC_SYSTEM = (
    "You organise university course material. "
    "Be precise and conservative. Output JSON only."
)


def _unit_dict(u: ContentUnit) -> dict:
    return {
        "id": str(u.id),
        "source_type": u.source_type,
        "unit_type": u.unit_type,
        "sequence_index": u.sequence_index,
        "page_number": u.page_number,
        "slide_number": u.slide_number,
        "time_start": u.time_start,
        "time_end": u.time_end,
        "text": search_text(
            u.content,
            u.vision_caption,
            u.ocr_text,
        ),
    }


async def _propose_topics(chunks: list[dict]) -> list[dict]:
    sample = (
        chunks
        if len(chunks) <= 60
        else random.Random(0).sample(chunks, 60)
    )

    heads = "\n".join(
        f"- {c['text'][:260].replace(chr(10), ' ')}"
        for c in sample
    )

    prompt = (
        "Below are excerpts from one course's lectures, slides and "
        "textbook.\n"
        f"{heads}\n\n"
        "List the 4-12 MAJOR TOPICS of this material, in teaching order. "
        'Return JSON: '
        '{"topics":[{"name":"short title",'
        '"description":"one sentence"}]}'
    )

    out = await llm.agenerate_json(
        prompt,
        system=TOPIC_SYSTEM,
    )

    topics = [
        t
        for t in out.get("topics", [])
        if str(t.get("name", "")).strip()
    ]

    if not topics:
        raise RuntimeError(
            "topic extraction returned no topics"
        )

    return topics


async def _assign(
    batch: list[dict],
    topic_names: list[str],
) -> dict[int, dict]:

    items = "\n".join(
        f"[{i}] {c['text'][:700]}"
        for i, c in enumerate(batch)
    )

    prompt = (
        f"Topics: {topic_names}\n\n"
        "For EACH excerpt below choose the single best topic "
        "(must be copied exactly from the list) "
        "and name the ONE key concept it teaches: "
        "a short canonical noun phrase (1-5 words, singular, "
        "no filler like 'introduction to'). "
        "Reuse the same concept name when excerpts teach the same idea.\n\n"
        f"{items}\n\n"
        "Return JSON: "
        '{"assignments":[{"i":0,"topic":"...",'
        '"concept":"...","concept_description":"one sentence"}]}'
    )

    out = await llm.agenerate_json(
        prompt,
        system=TOPIC_SYSTEM,
    )

    return {
        int(a["i"]): a
        for a in out.get("assignments", [])
        if "i" in a
    }


async def _prereqs(
    concepts: list[dict],
) -> list[tuple[str, str]]:
    """
    concepts: [{id,name,topic}]
    -> [(concept_id, prereq_id)]

    Proposed by the LLM and validated later.
    """

    by_name = {
        c["name"].lower(): c["id"]
        for c in concepts
    }

    edges: list[tuple[str, str]] = []

    names = [
        c["name"]
        for c in concepts
    ]

    for i in range(0, len(names), 40):
        group = names[i:i + 40]

        context = (
            names
            if len(names) <= 120
            else group
        )

        prompt = (
            f"Course concepts: {context}\n\n"
            f"For each concept in this list: {group}\n"
            "list which of the course concepts a student must "
            "understand FIRST (direct prerequisites only, max 3). "
            "Use exact names. "
            'Return JSON: '
            '{"prerequisites":[{"concept":"...",'
            '"requires":["..."]}]}'
        )

        out = await llm.agenerate_json(
            prompt,
            system=TOPIC_SYSTEM,
        )

        for row in out.get("prerequisites", []):
            concept_id = by_name.get(
                str(row.get("concept", "")).lower()
            )

            for required in row.get("requires", []) or []:
                prereq_id = by_name.get(
                    str(required).lower()
                )

                if concept_id and prereq_id:
                    edges.append(
                        (concept_id, prereq_id)
                    )

    return edges


async def build_knowledge(course_id: UUID) -> dict:
    """
    Build the complete derived knowledge layer for a course.

    The entire rebuild happens inside one database transaction.
    Any exception causes rollback, preserving the previous knowledge.
    """

    stats: dict = {}

    async with AsyncSessionLocal() as s:

        # ============================================================
        # 1. Stage replacement of derived data
        # ============================================================
        #
        # IMPORTANT:
        # Do NOT commit here.
        #
        # If a later Ollama/Gemini/build operation fails, the database
        # transaction rolls back and the previous knowledge remains.
        #

        await s.execute(
            delete(Chunk).where(
                Chunk.course_id == course_id
            )
        )

        await s.execute(
            delete(ConceptPrereq).where(
                ConceptPrereq.concept_id.in_(
                    select(Concept.id).where(
                        Concept.course_id == course_id
                    )
                )
            )
        )

        await s.execute(
            delete(Concept).where(
                Concept.course_id == course_id
            )
        )

        await s.execute(
            delete(Topic).where(
                Topic.course_id == course_id
            )
        )

        # Flush the staged deletes without committing.
        await s.flush()

        # ============================================================
        # 2. Chunk ContentUnits
        # ============================================================

        sources = (
            await s.execute(
                select(Source).where(
                    Source.course_id == course_id,
                    Source.status == "completed",
                )
            )
        ).scalars().all()

        if not sources:
            raise RuntimeError(
                "no completed sources in this course"
            )

        chunk_rows: list[Chunk] = []

        for src in sources:

            units = (
                await s.execute(
                    select(ContentUnit)
                    .where(
                        ContentUnit.source_id == src.id
                    )
                    .order_by(
                        ContentUnit.sequence_index
                    )
                )
            ).scalars().all()

            unit_dicts = [
                _unit_dict(u)
                for u in units
            ]

            for c in chunk_units(unit_dicts):

                chunk_rows.append(
                    Chunk(
                        id=uuid4(),
                        course_id=course_id,
                        source_id=src.id,
                        text=c["text"],
                        primary_unit_id=UUID(
                            c["primary_unit_id"]
                        ),
                        unit_ids=c["unit_ids"],
                    )
                )

        if not chunk_rows:
            raise RuntimeError(
                "no chunks produced "
                "(sources have no usable text; "
                "check vision/ASR warnings)"
            )

        stats["chunks"] = len(chunk_rows)

        # ============================================================
        # 3. Generate embeddings using Ollama
        # ============================================================

        embs = await llm.aembed_texts(
            [c.text for c in chunk_rows],
            "RETRIEVAL_DOCUMENT",
        )

        if len(embs) != len(chunk_rows):
            raise RuntimeError(
                "embedding count does not match chunk count"
            )

        for c, e in zip(chunk_rows, embs):
            c.embedding = [
                float(x)
                for x in e
            ]
            c.embedding_model = settings.OLLAMA_EMBED_MODEL if settings.EMBED_PROVIDER == "ollama" else settings.GEMINI_EMBED_MODEL

        s.add_all(chunk_rows)
        await s.flush()

        # ============================================================
        # 4. Topics + per-chunk concept assignment
        # ============================================================

        cdicts = [
            {"text": c.text}
            for c in chunk_rows
        ]

        topics_raw = await _propose_topics(
            cdicts
        )

        topic_rows = [
            Topic(
                id=uuid4(),
                course_id=course_id,
                name=str(
                    t["name"]
                ).strip()[:255],
                description=t.get(
                    "description"
                ),
                sequence=i,
            )
            for i, t in enumerate(topics_raw)
        ]

        s.add_all(topic_rows)
        await s.flush()

        topic_by_name = {
            t.name.lower(): t
            for t in topic_rows
        }

        topic_names = [
            t.name
            for t in topic_rows
        ]

        assigned: list[
            tuple[Chunk, str, str, str]
        ] = []

        for i in range(
            0,
            len(chunk_rows),
            10,
        ):

            batch = chunk_rows[
                i:i + 10
            ]

            res = await _assign(
                [
                    {"text": c.text}
                    for c in batch
                ],
                topic_names,
            )

            for j, c in enumerate(batch):

                a = res.get(j)

                if (
                    not a
                    or not str(
                        a.get("concept", "")
                    ).strip()
                ):
                    continue

                assigned.append(
                    (
                        c,
                        str(
                            a.get(
                                "topic",
                                ""
                            )
                        ),
                        str(
                            a["concept"]
                        ).strip(),
                        str(
                            a.get(
                                "concept_description",
                                "",
                            )
                        ),
                    )
                )

        stats["chunks_tagged"] = len(
            assigned
        )

        stats["chunks_untagged"] = (
            len(chunk_rows)
            - len(assigned)
        )

        # ============================================================
        # 5. Canonicalise concepts
        # ============================================================

        names = sorted(
            {
                a[2]
                for a in assigned
            }
        )

        if not names:
            raise RuntimeError(
                "no concepts were produced "
                "from the chunk assignments"
            )

        keys = {
            n: canonical_key(n)
            for n in names
        }

        uniq_keys = sorted(
            set(keys.values())
        )

        kvec = await llm.aembed_texts(
            uniq_keys,
            "SEMANTIC_SIMILARITY",
        )

        if len(kvec) != len(uniq_keys):
            raise RuntimeError(
                "concept embedding count does not "
                "match canonical key count"
            )

        labels = cluster_by_similarity(
            kvec,
            0.88,
        )

        key_to_cluster = dict(
            zip(
                uniq_keys,
                labels,
            )
        )

        freq = Counter(
            a[2]
            for a in assigned
        )

        cluster_names: dict[
            int,
            list[str],
        ] = defaultdict(list)

        for n in names:
            cluster_names[
                key_to_cluster[
                    keys[n]
                ]
            ].append(n)

        canon_name: dict[
            int,
            str,
        ] = {
            cl: max(
                ns,
                key=lambda x: (
                    freq[x],
                    -len(x),
                ),
            )
            for cl, ns
            in cluster_names.items()
        }

        stats["concept_names_raw"] = len(
            names
        )

        stats["concepts_canonical"] = len(
            canon_name
        )

        topic_votes: dict[
            int,
            Counter,
        ] = defaultdict(Counter)

        desc: dict[
            int,
            str,
        ] = {}

        for c, t, n, d in assigned:

            cl = key_to_cluster[
                keys[n]
            ]

            topic_votes[
                cl
            ][t.lower()] += 1

            if d and cl not in desc:
                desc[cl] = d

        concept_rows: dict[
            int,
            Concept,
        ] = {}

        cvecs = {
            k: v
            for k, v
            in zip(
                uniq_keys,
                kvec,
            )
        }

        for cl, nm in canon_name.items():

            tv = (
                topic_votes[cl]
                .most_common(1)[0][0]
            )

            topic = (
                topic_by_name.get(tv)
                or topic_rows[0]
            )

            concept_key = canonical_key(
                nm
            )

            concept_rows[cl] = Concept(
                id=uuid4(),
                course_id=course_id,
                topic_id=topic.id,
                name=nm[:255],
                key=concept_key,
                description=desc.get(cl),
                aliases=sorted(
                    set(
                        cluster_names[cl]
                    ) - {nm}
                ),
                embedding=[
                    float(x)
                    for x in cvecs[
                        concept_key
                    ]
                ]
                if concept_key in cvecs
                else None,
                embedding_model=(settings.OLLAMA_EMBED_MODEL if settings.EMBED_PROVIDER == "ollama" else settings.GEMINI_EMBED_MODEL)
                if concept_key in cvecs
                else None,
            )

        s.add_all(
            concept_rows.values()
        )

        await s.flush()

        for c, t, n, d in assigned:

            cl = key_to_cluster[
                keys[n]
            ]

            c.concept_id = (
                concept_rows[cl].id
            )

            c.topic_id = (
                concept_rows[cl].topic_id
            )

        # ============================================================
        # 6. Prerequisite graph
        # ============================================================

        cl_list = [
            {
                "id": str(c.id),
                "name": c.name,
                "topic": str(c.topic_id),
            }
            for c in concept_rows.values()
        ]

        proposed = await _prereqs(
            cl_list
        )

        accepted, rejected = (
            add_edges_acyclic(
                proposed,
                {
                    c["id"]
                    for c in cl_list
                },
            )
        )

        for cid, pid in accepted:

            s.add(
                ConceptPrereq(
                    concept_id=UUID(cid),
                    prereq_id=UUID(pid),
                )
            )

        stats[
            "prereq_edges_proposed"
        ] = len(proposed)

        stats[
            "prereq_edges_accepted"
        ] = len(accepted)

        stats[
            "prereq_edges_rejected"
        ] = len(rejected)

        # ============================================================
        # 7. Final commit
        # ============================================================
        #
        # This is the ONLY commit in the rebuild.
        # If anything above raises an exception, AsyncSession
        # transaction handling rolls back the staged changes.
        #

        await s.commit()

    return stats