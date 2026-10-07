import numpy as np
from app.knowledge.canonical import (canonical_key, cluster_by_similarity, creates_cycle, add_edges_acyclic, topo_depths)
from app.knowledge.chunking import chunk_units, search_text
from app.retrieval.fusion import cosine_topk, rrf_fuse, normalize_rows


def test_canonical_key_merges_variants():
    assert canonical_key("Self-Attention Mechanism") == canonical_key("self attention")
    assert canonical_key("Gradient Descents") == canonical_key("gradient descent")
    assert canonical_key("Chain Rule") != canonical_key("Learning Rate")


def test_cluster_by_similarity():
    v = normalize_rows(np.array([[1, 0, 0], [0.99, 0.1, 0], [0, 1, 0]], dtype=float))
    labels = cluster_by_similarity(v, 0.9)
    assert labels[0] == labels[1] != labels[2]


def test_cycle_rejection():
    edges = {("b", "a"), ("c", "b")}  # c requires b requires a
    assert creates_cycle(edges, "a", "c")
    assert creates_cycle(edges, "a", "a")
    assert not creates_cycle(edges, "d", "a")
    acc, rej = add_edges_acyclic([("b", "a"), ("a", "b"), ("c", "b"), ("x", "a")], {"a", "b", "c"})
    assert ("a", "b") in rej and ("x", "a") in rej and ("b", "a") in acc and ("c", "b") in acc
    d = topo_depths(["a", "b", "c"], acc)
    assert d == {"a": 0, "b": 1, "c": 2}


def U(i, st, ut, seq, text, **kw):
    base = dict(id=i, source_type=st, unit_type=ut, sequence_index=seq, text=text, page_number=None,
                slide_number=None, time_start=None, time_end=None)
    base.update(kw)
    return base


def test_search_text_drops_placeholder_when_caption_present():
    assert search_text("[Figure on Page 3]", "A diagram of a perceptron", "x1 w1") == "A diagram of a perceptron\nx1 w1"
    assert search_text("[Figure on Page 3]", None, None) == "[Figure on Page 3]"


def test_pdf_chunks_never_span_pages_and_keep_provenance():
    long = "word " * 120
    us = [U("1", "pdf", "heading", 0, "CHAPTER 1 Intro to learning", page_number=1),
          U("2", "pdf", "text", 1, long, page_number=1),
          U("3", "pdf", "text", 2, long, page_number=2),
          U("4", "pdf", "diagram", 3, "Perceptron diagram with inputs and weights", page_number=2)]
    cs = chunk_units(us)
    for c in cs:
        pages = {u["page_number"] for u in us if u["id"] in c["unit_ids"]}
        assert len(pages) == 1
        assert c["location"]["page"] in (1, 2)
    fig = [c for c in cs if c["primary_unit_id"] == "4"]
    assert len(fig) == 1 and fig[0]["unit_ids"] == ["4"]


def test_slide_chunks_one_per_slide_primary_is_slide_unit():
    us = [U("n", "pptx", "text", 1, "speaker note text about gradients", slide_number=1),
          U("s", "pptx", "slide", 0, "Gradients\nthe slope of the loss", slide_number=1),
          U("s2", "pptx", "slide", 2, "Backprop\nchain rule applied layer by layer", slide_number=2)]
    cs = chunk_units(us)
    assert len(cs) == 2
    assert cs[0]["primary_unit_id"] == "s" and cs[0]["location"]["slide"] == 1


def test_video_windows_and_onscreen_text():
    us = [U("c1", "video", "caption", 0, "Today we discuss gradient descent updates", time_start=1.0, time_end=6.0),
          U("c2", "video", "caption", 1, "We move against the gradient direction", time_start=6.0, time_end=12.0),
          U("k1", "video", "keyframe", 2, "Slide: Gradient Descent w = w - lr * grad", time_start=3.0, time_end=20.0),
          U("c3", "video", "caption", 3, "Now the learning rate matters a lot here", time_start=70.0, time_end=80.0)]
    cs = chunk_units(us)
    assert len(cs) == 2
    assert cs[0]["primary_unit_id"] == "c1" and cs[0]["location"]["time_start"] == 1.0
    assert "On screen" in cs[0]["text"] and "k1" in cs[0]["unit_ids"]
    assert cs[1]["location"]["time_start"] == 70.0


def test_retrieval_math():
    m = normalize_rows(np.array([[1, 0], [0, 1], [0.7, 0.7]], dtype=float))
    q = normalize_rows(np.array([[1, 0.1]], dtype=float))[0]
    top = cosine_topk(m, q, 2)
    assert top[0][0] == 0 and top[0][1] > top[1][1]
    fused = rrf_fuse([["a", "b", "c"], ["b", "a", "d"]])
    assert {fused[0][0], fused[1][0]} == {"a", "b"}
    assert fused[-1][0] in {"c", "d"}
