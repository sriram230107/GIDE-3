"use client";
import { useEffect, useRef, useState } from "react";
import { api, post } from "@/lib/api";
import { Btn, Card, ErrorBox, NeedCourse } from "@/components/Shell";
import { SourceViewer, ViewTarget } from "@/components/SourceViewer";
import { Citation, citeLabel } from "@/lib/types";

interface Item { item_id: string; position: number; qtype: string; stem: string; options: string[] | null; tags: { topic: string | null; concept: string | null; difficulty: number } }

function Assessments({ courseId }: { courseId: string }) {
  const [topics, setTopics] = useState<{ id: string; name: string }[]>([]);
  const [sel, setSel] = useState<string[]>([]);
  const [n, setN] = useState(6);
  const [types, setTypes] = useState<string[]>(["mcq"]);
  const [difficulty, setDifficulty] = useState("adaptive");
  const [focus, setFocus] = useState("weak");
  const [quiz, setQuiz] = useState<{ assessment_id: string; items: Item[]; shortfall: any[]; requested: number } | null>(null);
  const [idx, setIdx] = useState(0);
  const [answer, setAnswer] = useState("");
  const [fb, setFb] = useState<any>(null);
  const [report, setReport] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [target, setTarget] = useState<ViewTarget | null>(null);
  const t0 = useRef(Date.now());

  useEffect(() => { api(`/api/courses/${courseId}/graph`).then((g) => setTopics(g.topics)).catch((e) => setErr(e.message)); }, [courseId]);
  useEffect(() => { t0.current = Date.now(); }, [idx, quiz]);

  const create = async (kind: "quiz" | "diagnostic") => {
    setBusy(true); setErr(null); setReport(null); setFb(null); setIdx(0); setAnswer("");
    try { setQuiz(await post("/api/assessments", { course_id: courseId, kind, n, topic_ids: sel, qtypes: types, difficulty, focus })); }
    catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };
  const submit = async () => {
    if (!quiz || answer === "") return;
    setBusy(true); setErr(null);
    try { setFb(await post("/api/assessments/answer", { item_id: quiz.items[idx].item_id, answer, response_time: (Date.now() - t0.current) / 1000 })); }
    catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };
  const next = async () => {
    if (!quiz) return;
    if (idx + 1 < quiz.items.length) { setIdx(idx + 1); setAnswer(""); setFb(null); return; }
    setReport(await api(`/api/assessments/${quiz.assessment_id}/report`));
  };
  const openCite = (c: Citation) => setTarget({ source_id: c.source_id, source_type: c.source_type, title: c.source_title, media_url: c.media_url, page: c.page, slide: c.slide, time_start: c.time_start, image_path: c.image_path, note: c.snippet });
  const toggle = (arr: string[], v: string, set: (a: string[]) => void) => set(arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v]);
  const item = quiz?.items[idx];

  return (
    <div className="grid gap-6 xl:grid-cols-2">
      <div className="space-y-4">
        <h1 className="text-2xl font-semibold">Assessments</h1>
        <ErrorBox msg={err} />
        {!quiz && (
          <Card className="space-y-4 text-sm">
            <div><div className="mb-1 text-zinc-400">Scope (none selected = whole course)</div><div className="flex flex-wrap gap-2">{topics.map((t) => <button key={t.id} onClick={() => toggle(sel, t.id, setSel)} className={`rounded-lg border px-2.5 py-1 ${sel.includes(t.id) ? "border-emerald-500 bg-emerald-500/10 text-emerald-300" : "border-zinc-700 text-zinc-400"}`}>{t.name}</button>)}{topics.length === 0 && <span className="text-zinc-500">Build the knowledge base first (Sources page).</span>}</div></div>
            <div className="flex flex-wrap gap-6">
              <label>Questions <input type="number" min={1} max={20} value={n} onChange={(e) => setN(+e.target.value)} className="ml-2 w-16 rounded border border-zinc-700 bg-zinc-900 p-1" /></label>
              <div className="flex gap-3">{[["mcq", "MCQ"], ["short", "Short answer"], ["numeric", "Numerical"]].map(([v, l]) => <label key={v}><input type="checkbox" checked={types.includes(v)} onChange={() => types.includes(v) && types.length === 1 ? null : toggle(types, v, setTypes)} /> {l}</label>)}</div>
            </div>
            <div className="flex flex-wrap gap-6">
              <label>Difficulty <select value={difficulty} onChange={(e) => setDifficulty(e.target.value)} className="ml-2 rounded border border-zinc-700 bg-zinc-900 p-1"><option value="easy">Easy</option><option value="adaptive">Adaptive</option><option value="hard">Hard</option></select></label>
              <label>Focus <select value={focus} onChange={(e) => setFocus(e.target.value)} className="ml-2 rounded border border-zinc-700 bg-zinc-900 p-1"><option value="weak">Weak concepts</option><option value="balanced">Balanced</option><option value="exam">Exam simulation</option></select></label>
            </div>
            <div className="flex gap-2"><Btn disabled={busy} onClick={() => create("quiz")}>{busy ? "Generating & verifying…" : "Generate assessment"}</Btn><Btn tone="ghost" disabled={busy} onClick={() => create("diagnostic")}>Diagnostic quiz (new student)</Btn></div>
            {busy && <p className="text-xs text-zinc-500">Each question is generated, then independently solved and checked against the source. This can take a minute.</p>}
          </Card>
        )}
        {quiz && item && !report && (
          <Card className="space-y-4">
            <div className="flex flex-wrap items-center gap-2 text-xs text-zinc-400"><span>Question {idx + 1} / {quiz.items.length}</span>{item.tags.topic && <span className="rounded bg-zinc-800 px-2 py-0.5">{item.tags.topic}</span>}{item.tags.concept && <span className="rounded bg-zinc-800 px-2 py-0.5">{item.tags.concept}</span>}<span className="rounded bg-zinc-800 px-2 py-0.5">difficulty {item.tags.difficulty}</span></div>
            {quiz.shortfall.length > 0 && idx === 0 && <div className="rounded-lg border border-amber-900 bg-amber-950/40 p-2 text-xs text-amber-300">{quiz.items.length} of {quiz.requested} questions passed verification; {quiz.shortfall.length} slot(s) could not be filled (e.g. “{quiz.shortfall[0].concept}”).</div>}
            <p className="text-base">{item.stem}</p>
            {item.qtype === "mcq" ? (
              <div className="space-y-2">{item.options!.map((o, i) => <button key={i} disabled={!!fb} onClick={() => setAnswer(String(i))} className={`block w-full rounded-lg border p-3 text-left text-sm ${answer === String(i) ? "border-emerald-500 bg-emerald-500/10" : "border-zinc-700 hover:bg-zinc-800"}`}>{o}</button>)}</div>
            ) : <input value={answer} disabled={!!fb} onChange={(e) => setAnswer(e.target.value)} placeholder={item.qtype === "numeric" ? "Number" : "Your answer"} className="w-full rounded-lg border border-zinc-700 bg-zinc-900 p-3 text-sm" />}
            {!fb ? <Btn disabled={busy || answer === ""} onClick={submit}>Submit</Btn> : (
              <div className="space-y-2 text-sm">
                <div className={`font-medium ${fb.correct ? "text-emerald-300" : "text-red-300"}`}>{fb.correct ? "Correct" : "Incorrect"}</div>
                {!fb.correct && <div>Correct answer: <span className="text-zinc-100">{fb.correct_answer}</span></div>}
                <p className="text-zinc-300">{fb.explanation}</p>
                {fb.grader_note && <p className="text-zinc-400">{fb.grader_note}</p>}
                {fb.misconception && <div className="rounded-lg border border-amber-900 bg-amber-950/40 p-2 text-amber-300">Likely misconception: {fb.misconception}</div>}
                {fb.citation && <button onClick={() => openCite(fb.citation)} className="rounded-lg border border-zinc-700 px-2 py-1 text-xs hover:bg-zinc-800">Source: {citeLabel(fb.citation)}</button>}
                {fb.mastery && <div className="text-xs text-zinc-500">Concept mastery {fb.mastery.before} → {fb.mastery.after}</div>}
                <Btn onClick={next}>{idx + 1 < quiz.items.length ? "Next question" : "See report"}</Btn>
              </div>
            )}
          </Card>
        )}
        {report && (
          <Card className="space-y-4 text-sm">
            <h2 className="text-lg font-semibold">Report: {report.answered}/{report.total} answered · score {report.score != null ? Math.round(report.score * 100) + "%" : "–"}</h2>
            <div className="space-y-2">{report.by_concept.map((r: any) => <div key={r.concept_id} className="flex items-center gap-3"><div className="w-48 truncate">{r.concept}</div><div className="h-2 flex-1 rounded bg-zinc-800"><div className={`h-2 rounded ${r.weak ? "bg-red-500" : "bg-emerald-500"}`} style={{ width: `${r.accuracy * 100}%` }} /></div><div className="w-12 text-right text-zinc-400">{r.correct}/{r.answered}</div></div>)}</div>
            {report.weak_concepts.length > 0 && <div><div className="text-zinc-400">Weak topics</div>{report.weak_concepts.map((w: any) => <div key={w.concept_id} className="text-amber-300">• {w.concept}</div>)}</div>}
            {report.likely_misconceptions.length > 0 && <div><div className="text-zinc-400">Likely misconceptions</div>{report.likely_misconceptions.map((m: any, i: number) => <div key={i} className="mb-1">• <span className="text-zinc-400">{m.concept}:</span> {m.misconception} ({m.count}×) {m.citation && <button onClick={() => openCite(m.citation)} className="ml-1 text-xs text-emerald-400 underline">source</button>}</div>)}</div>}
            {report.next_steps?.length > 0 && <div><div className="text-zinc-400">Suggested next</div>{report.next_steps.map((s: any, i: number) => <div key={i}>• {s.activity}: {s.concept} ({s.minutes} min)</div>)}</div>}
            <Btn onClick={() => { setQuiz(null); setReport(null); }}>New assessment</Btn>
          </Card>
        )}
      </div>
      <div className="xl:sticky xl:top-8 xl:self-start"><SourceViewer target={target} onClose={() => setTarget(null)} /></div>
    </div>
  );
}

export default function Page() { return <NeedCourse>{(id) => <Assessments courseId={id} />}</NeedCourse>; }
