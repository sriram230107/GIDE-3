"""T3: embedding-model mismatch refusal (no DB needed; stub session)."""
from uuid import uuid4

import pytest

from app.retrieval import search
from app.assessment import service


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def one(self):
        return (1, None)


class _Session:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, *a, **k):
        return _Result(self._rows)


@pytest.mark.asyncio
async def test_matrix_refuses_mixed_embedding_model(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(search, "_cache", {})
    rows = [(uuid4(), [0.1, 0.2], "some-other-model-xyz")]
    with pytest.raises(RuntimeError, match="rebuild required"):
        await search._matrix(_Session(rows), uuid4())
    # matching model passes through
    monkeypatch.setattr(search, "_cache", {})
    active = settings.OLLAMA_EMBED_MODEL if settings.EMBED_PROVIDER == "ollama" else settings.GEMINI_EMBED_MODEL
    ids, mat = await search._matrix(_Session([(uuid4(), [1.0, 0.0], active)]), uuid4())
    assert len(ids) == 1


@pytest.mark.asyncio
async def test_known_for_dedupe_refuses_mixed_embedding_model(monkeypatch):
    from app.core.config import settings
    rows = [("stem", "hash", [0.1, 0.2], "some-other-model-xyz")]
    with pytest.raises(RuntimeError, match="rebuild required"):
        await service._known_for_dedupe(_Session(rows), uuid4(), uuid4())
    active = settings.OLLAMA_EMBED_MODEL if settings.EMBED_PROVIDER == "ollama" else settings.GEMINI_EMBED_MODEL
    stems, hashes, embs = await service._known_for_dedupe(
        _Session([("stem", "hash", [0.1, 0.2], active)]), uuid4(), uuid4()
    )
    assert stems == ["stem"]
