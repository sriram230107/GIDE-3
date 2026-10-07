"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import { Card, ErrorBox, NeedCourse } from "@/components/Shell";
import { SourceViewer, ViewTarget } from "@/components/SourceViewer";
import { Citation } from "@/lib/types";

interface Flashcard { question_id: string; concept: string; front: string; back: string; explanation: string; citation: Citation | null }

export default function FlashcardsPage() {
  return <NeedCourse>{(courseId) => <Body courseId={courseId} />}</NeedCourse>;
}

function Body({ courseId }: { courseId: string }) {
  const [cards, setCards] = useState<Flashcard[] | null>(null);
  const [shown, setShown] = useState<Record<string, boolean>>({});
  const [target, setTarget] = useState<ViewTarget | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const load = async () => {
    setErr(null); setLoading(true);
    try { setCards((await api<{ cards: Flashcard[] }>(`/api/learner/${courseId}/flashcards`)).cards); }
    catch (e: unknown) { setErr(e instanceof Error ? e.message : String(e)); } finally { setLoading(false); }
  };
  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <h1 className="text-xl font-semibold">Flashcards</h1>
      <Card>
        <div className="flex items-center gap-3">
          <button onClick={load} disabled={loading} className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium disabled:opacity-50">{loading ? "Loading…" : "Weak-concept cards"}</button>
          <span className="text-xs text-zinc-500">Verified short-answer questions on your weakest concepts.</span>
        </div>
      </Card>
      {err && <ErrorBox msg={err} />}
      {cards && cards.length === 0 && <p className="text-sm text-zinc-400">No weak concepts with verified questions — build knowledge and take a quiz first.</p>}
      {(cards ?? []).map((c) => (
        <Card key={c.question_id}>
          <div className="mb-1 text-xs text-zinc-500">{c.concept}</div>
          <div className="text-sm font-medium">{c.front}</div>
          {shown[c.question_id] ? (
            <div className="mt-2 border-t border-zinc-800 pt-2 text-sm">
              <div>{c.back}</div>
              <div className="mt-1 text-xs text-zinc-500">{c.explanation}</div>
              {c.citation && <button onClick={() => setTarget({ source_id: c.citation!.source_id, source_type: c.citation!.source_type, title: c.citation!.source_title, media_url: c.citation!.media_url, page: c.citation!.page, slide: c.citation!.slide, time_start: c.citation!.time_start, image_path: c.citation!.image_path, note: c.citation!.snippet })} className="mt-1 text-xs text-emerald-400 underline">Open source</button>}
            </div>
          ) : (
            <button onClick={() => setShown({ ...shown, [c.question_id]: true })} className="mt-2 rounded-lg border border-zinc-700 px-3 py-1 text-xs text-zinc-300 hover:bg-zinc-800">Reveal answer</button>
          )}
        </Card>
      ))}
      <SourceViewer target={target} />
    </div>
  );
}
