"""T11: weak-concept selection + flashcard shape (pure parts, stub session for the DB part)."""
from uuid import uuid4

import pytest

from app.learner.director import weak_concepts
from app.learner import service


def test_weak_concepts_threshold_and_order():
    cs = [{"id": "a", "eff": 0.8}, {"id": "b", "eff": 0.2}, {"id": "c", "eff": 0.5}, {"id": "d"}]
    assert [c["id"] for c in weak_concepts(cs)] == ["d", "b", "c"]
    assert [c["id"] for c in weak_concepts(cs, 0.3)] == ["d", "b"]


class _Q:
    def __init__(self, cid, uid):
        self.id = uuid4()
        self.concept_id = cid
        self.unit_id = uid
        self.stem = "front?"
        self.answer = "back"
        self.explanation = "why"


class _Scalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _Scalars(self._rows)


class _Session:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, *a, **k):
        return _Result(self._rows)


@pytest.mark.asyncio
async def test_flashcards_only_verified_short_with_citations(monkeypatch):
    cid = uuid4()

    async def fake_overview(*a, **k):
        return {"concepts": [{"id": str(cid), "name": "C", "eff": 0.2}]}
    monkeypatch.setattr(service, "course_overview", fake_overview)
    async def fake_cite(session, uid, n=1, snippet=""):
        return {"unit_id": str(uid), "page": 3}
    import app.retrieval.search as search
    monkeypatch.setattr(search, "citation_for_unit", fake_cite)
    out = await service.flashcards(_Session([_Q(cid, uuid4())]), uuid4(), uuid4())
    assert len(out["cards"]) == 1
    card = out["cards"][0]
    assert (card["front"], card["back"], card["citation"]["page"]) == ("front?", "back", 3)


@pytest.mark.asyncio
async def test_flashcards_empty_when_no_weak(monkeypatch):
    async def fake_overview(*a, **k):
        return {"concepts": [{"id": "x", "name": "C", "eff": 0.95}]}
    monkeypatch.setattr(service, "course_overview", fake_overview)
    out = await service.flashcards(_Session([]), uuid4(), uuid4())
    assert out == {"cards": []}
