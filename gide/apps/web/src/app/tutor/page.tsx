"use client";
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { post } from "@/lib/api";
import { Btn, Card, ErrorBox, NeedCourse } from "@/components/Shell";
import { SourceViewer, ViewTarget } from "@/components/SourceViewer";
import { Citation, citeLabel } from "@/lib/types";

interface Msg { role: "user" | "assistant"; text: string; label?: string; citations?: Citation[]; related?: string[]; check?: any; offerGeneral?: boolean; q?: string; meta?: string }

const BADGE: Record<string, [string, string]> = {
  GROUNDED: ["● Source grounded", "bg-emerald-500/15 text-emerald-300"],
  PARTIAL: ["◐ Partially grounded", "bg-amber-500/15 text-amber-300"],
  NOT_COVERED: ["○ Not covered by your material", "bg-red-500/15 text-red-300"],
  OUTSIDE_COURSE: ["⚠ Outside course material (general knowledge)", "bg-sky-500/15 text-sky-300"],
};

function CiteText({ text, cites, onOpen }: { text: string; cites: Citation[]; onOpen: (c: Citation) => void }) {
  // Turn [n] markers into clickable chips; text is rendered as plain text (no HTML injection).
  const parts = text.split(/(\[\d+\])/g);
  return (
    <p className="whitespace-pre-wrap text-sm leading-relaxed text-zinc-200">
      {parts.map((p, i) => {
        const m = p.match(/^\[(\d+)\]$/); const c = m && cites.find((x) => x.n === Number(m[1]));
        return c ? <button key={i} onClick={() => onOpen(c)} className="mx-0.5 rounded bg-emerald-500/20 px-1 text-xs text-emerald-300 hover:bg-emerald-500/30">{p}</button> : <span key={i}>{p}</span>;
      })}
    </p>
  );
}

function Tutor({ courseId }: { courseId: string }) {
  const params = useSearchParams();
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState(params.get("q") ?? "");
  const [level, setLevel] = useState("current");
  const [conv, setConv] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [target, setTarget] = useState<ViewTarget | null>(null);
  const [checkAns, setCheckAns] = useState<Record<number, string>>({});
  const [checkRes, setCheckRes] = useState<Record<number, any>>({});
  const [checking, setChecking] = useState<Record<number, boolean>>({});
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs]);

  const open = (c: Citation) => setTarget({ source_id: c.source_id, source_type: c.source_type, title: c.source_title, media_url: c.media_url, page: c.page, slide: c.slide, time_start: c.time_start, image_path: c.image_path, note: c.snippet });

  const ask = async (q: string, mode: "course_only" | "general" = "course_only") => {
    if (!q.trim() || busy) return;
    setBusy(true); setErr(null);
    if (mode === "course_only") setMsgs((m) => [...m, { role: "user", text: q }]);
    try {
      const r = await post("/api/tutor/ask", { course_id: courseId, question: q, conversation_id: conv, level, mode });
      setConv(r.conversation_id);
      setMsgs((m) => [...m, { role: "assistant", text: r.answer, label: r.label, citations: r.citations, related: r.related_concepts, check: r.check, offerGeneral: r.offer_general, q,
        meta: `evidence chunks: ${r.evidence_chunks} · top similarity ${r.top_dense}${r.gate.calibrated ? "" : " · gate UNCALIBRATED"}` }]);
      setInput("");
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <div className="flex h-[calc(100vh-4rem)] flex-col">
        <div className="mb-3 flex items-center justify-between">
          <h1 className="text-2xl font-semibold">AI Tutor</h1>
          <select value={level} onChange={(e) => setLevel(e.target.value)} className="rounded-lg border border-zinc-800 bg-zinc-900 p-2 text-sm">
            <option value="beginner">Beginner</option><option value="current">My level</option><option value="exam">Exam style</option><option value="expert">Expert</option>
          </select>
        </div>
        <div className="flex-1 space-y-4 overflow-y-auto pr-1">
          {msgs.length === 0 && <p className="text-sm text-zinc-500">Ask anything about your course. Answers use only your uploaded material and cite the exact page, slide or timestamp. If the material does not cover it, I will say so.</p>}
          {msgs.map((m, i) => m.role === "user" ? (
            <div key={i} className="ml-auto max-w-[85%] rounded-2xl bg-zinc-800 p-3 text-sm">{m.text}</div>
          ) : (
            <Card key={i} className="space-y-3">
              {m.label && <span className={`inline-block rounded-full px-2.5 py-1 text-xs font-medium ${BADGE[m.label][1]}`}>{BADGE[m.label][0]}</span>}
              <CiteText text={m.text} cites={m.citations ?? []} onOpen={open} />
              {m.citations && m.citations.length > 0 && (
                <div className="flex flex-wrap gap-2">{m.citations.map((c) => <button key={c.n} onClick={() => open(c)} className="rounded-lg border border-zinc-700 px-2 py-1 text-xs text-zinc-300 hover:bg-zinc-800">[{c.n}] {citeLabel(c)}</button>)}</div>
              )}
              {m.related && m.related.length > 0 && <div className="text-xs text-zinc-400">Related: {m.related.join(" · ")}</div>}
              {m.offerGeneral && m.q && <Btn tone="ghost" onClick={() => ask(m.q!, "general")} disabled={busy}>Answer from general knowledge (marked as outside your sources)</Btn>}
              {m.check && (
                <div className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-3 text-sm">
                  <div className="mb-2 text-xs uppercase text-zinc-500">Quick check (counts toward your mastery)</div>
                  <div className="mb-2">{m.check.question}</div>
                  {checkRes[i] ? <div className={checkRes[i].correct ? "text-emerald-300" : "text-amber-300"}>{checkRes[i].correct ? "Correct. " : "Not quite. "}{checkRes[i].feedback} <span className="text-zinc-500">(mastery {checkRes[i].mastery.before} → {checkRes[i].mastery.after})</span></div> : (
                    <div className="flex gap-2"><input value={checkAns[i] ?? ""} onChange={(e) => setCheckAns({ ...checkAns, [i]: e.target.value })} className="min-w-0 flex-1 rounded-lg border border-zinc-800 bg-zinc-900 p-2" placeholder="Your answer" />
                      <Btn disabled={checking[i]} onClick={async () => { setChecking({ ...checking, [i]: true }); try { const r = await post("/api/tutor/check", { course_id: courseId, concept_id: m.check.concept_id, question: m.check.question, student_answer: checkAns[i] ?? "", chunk_ids: m.check.chunk_ids }); setCheckRes({ ...checkRes, [i]: r }); } catch (e: any) { setErr(e.message); } finally { setChecking({ ...checking, [i]: false }); } }}>{checking[i] ? "Checking…" : "Check"}</Btn></div>
                  )}
                </div>
              )}
              {m.meta && <div className="text-[11px] text-zinc-600">{m.meta}</div>}
            </Card>
          ))}
          <div ref={end} />
        </div>
        <ErrorBox msg={err} />
        <form onSubmit={(e) => { e.preventDefault(); ask(input); }} className="mt-3 flex gap-2">
          <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Ask about your course…" className="min-w-0 flex-1 rounded-xl border border-zinc-800 bg-zinc-900 p-3 text-sm" />
          <Btn disabled={busy}>{busy ? "Thinking…" : "Ask"}</Btn>
        </form>
      </div>
      <div className="xl:sticky xl:top-8 xl:self-start"><SourceViewer target={target} onClose={() => setTarget(null)} /></div>
    </div>
  );
}

export default function Page() { return <Suspense><NeedCourse>{(id) => <Tutor courseId={id} />}</NeedCourse></Suspense>; }
