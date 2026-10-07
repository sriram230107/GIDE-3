"""T6: citation provenance — citation_for opens the PRIMARY unit's page/slide/time.

DB-free: stub session returning canned ContentUnit/Source rows.
"""
from uuid import uuid4

import pytest

from app.retrieval import search
from app.retrieval.search import Hit


class FakeScalar:
    def __init__(self, obj):
        self._obj = obj

    def scalar_one(self):
        return self._obj


class FakeSession:
    def __init__(self, unit, source):
        self._unit = unit
        self._source = source

    async def execute(self, stmt):
        text = str(stmt)
        if "content_units" in text:
            return FakeScalar(self._unit)
        return FakeScalar(self._source)


class U:
    def __init__(self, **kw):
        self.id = kw.get("id", uuid4())
        self.page_number = kw.get("page_number")
        self.slide_number = kw.get("slide_number")
        self.time_start = kw.get("time_start")
        self.time_end = kw.get("time_end")
        self.image_path = kw.get("image_path")


class S:
    def __init__(self, **kw):
        self.id = kw.get("id", uuid4())
        self.title = kw.get("title", "Attention Is All You Need")
        self.source_type = kw.get("source_type", "pdf")
        self.file_path = kw.get("file_path", "/uploads/attention.pdf")


def _hit(unit_id, source_id):
    return Hit(chunk_id=uuid4(), text="x" * 300, source_id=source_id,
              primary_unit_id=unit_id, concept_id=None, topic_id=None,
              dense=0.9, fused=1.0)


@pytest.mark.asyncio
async def test_citation_opens_primary_unit_page():
    uid, sid = uuid4(), uuid4()
    unit = U(id=uid, page_number=7)
    cit = await search.citation_for(FakeSession(unit, S(id=sid)), _hit(uid, sid), 1)
    assert cit["page"] == 7 and cit["slide"] is None and cit["time_start"] is None
    assert cit["unit_id"] == str(uid) and cit["source_id"] == str(sid)
    assert cit["media_url"].endswith(".pdf")


@pytest.mark.asyncio
async def test_citation_opens_primary_unit_slide():
    uid, sid = uuid4(), uuid4()
    cit = await search.citation_for(FakeSession(U(id=uid, slide_number=12), S(id=sid, source_type="pptx", file_path="/u/s.pptx")), _hit(uid, sid), 2)
    assert cit["slide"] == 12 and cit["page"] is None


@pytest.mark.asyncio
async def test_citation_opens_primary_unit_timestamp():
    uid, sid = uuid4(), uuid4()
    cit = await search.citation_for(
        FakeSession(U(id=uid, time_start=95.5, time_end=120.0), S(id=sid, source_type="video", file_path="/u/v.mp4")),
        _hit(uid, sid), 3)
    assert cit["time_start"] == 95.5 and cit["time_end"] == 120.0
    assert cit["media_url"].endswith(".mp4")
