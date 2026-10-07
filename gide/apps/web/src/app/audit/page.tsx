"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import { Card, ErrorBox, NeedCourse } from "@/components/Shell";

interface Audit { mark: string; note: string }
interface Q { id: string; qtype: string; stem: string; answer: string; options: { text: string; is_correct: boolean }[] | null; explanation: string; verified: boolean; audit: Audit | null }
interface AuditStats { n_reviewed: number; n_decided: number; n_key_wrong: number; audited_error_rate: number | null; n_unclear: number }

const MARKS = [["key_ok", "Key OK"], ["key_wrong", "Key wrong"], ["unclear", "Unclear"]] as const;

export default function AuditPage() {
  return <NeedCourse>{(courseId) => <Body courseId={courseId} />}</NeedCourse>;
}

function Body({ courseId }: { courseId: string }) {
  const [qs, setQs] = useState<Q[] | null>(null);
  const [stats, setStats] = useState<AuditStats | null>(null);
  const [note, setNote] = useState<Record<string, string>>({});
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const load = async () => {
    setErr(null); setLoading(true);
    try {
      const [l, s] = await Promise.all([api<{ questions: Q[] }>(`/api/assessments/questions?course_id=${courseId}`), api(`/api/assessments/stats/${courseId}`)]);
      setQs(l.questions); setStats(s.audit ?? null);
    } catch (e: unknown) { setErr(e instanceof Error ? e.message : String(e)); } finally { setLoading(false); }
  };
  const mark = async (id: string, m: string) => {
    setErr(null);
    try {
      const r = await api<{ audit: Audit }>(`/api/assessments/questions/${id}/audit`, { method: "POST", body: JSON.stringify({ mark: m, note: note[id] ?? "" }) });
      setQs((qs ?? []).map((q) => q.id === id ? { ...q, audit: r.audit } : q));
      const s = await api(`/api/assessments/stats/${courseId}`);
      setStats(s.audit ?? null);
    } catch (e: unknown) { setErr(e instanceof Error ? e.message : String(e)); }
  };
  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <h1 className="text-xl font-semibold">Question audit</h1>
      <Card>
        <div className="flex flex-wrap items-center gap-3">
          <button onClick={load} disabled={loading} className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium disabled:opacity-50">{loading ? "Loading…" : "Load question bank"}</button>
          {stats && <span className="text-xs text-zinc-400">reviewed {stats.n_reviewed} · decided {stats.n_decided} · key-wrong {stats.n_key_wrong} · audited error rate {stats.audited_error_rate === null ? "—" : `${(stats.audited_error_rate * 100).toFixed(1)}%`} · unclear {stats.n_unclear}</span>}
        </div>
      </Card>
      {err && <ErrorBox msg={err} />}
      {qs && qs.length === 0 && <p className="text-sm text-zinc-400">No questions in the bank yet — generate a quiz first.</p>}
      {(qs ?? []).map((q) => (
        <Card key={q.id}>
          <div className="mb-1 flex items-center gap-2 text-xs text-zinc-500"><span>{q.qtype}</span><span>{q.verified ? "verified" : "unverified"}</span>{q.audit && <span className={q.audit.mark === "key_wrong" ? "text-red-400" : "text-emerald-400"}>audit: {q.audit.mark}</span>}</div>
          <div className="text-sm font-medium">{q.stem}</div>
          <div className="mt-1 text-sm text-zinc-300">Key: {q.answer}</div>
          <div className="mt-1 text-xs text-zinc-500">{q.explanation}</div>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            {MARKS.map(([v, l]) => <button key={v} onClick={() => mark(q.id, v)} className="rounded-lg border border-zinc-700 px-3 py-1 text-xs text-zinc-300 hover:bg-zinc-800">{l}</button>)}
            <input value={note[q.id] ?? ""} onChange={(e) => setNote({ ...note, [q.id]: e.target.value })} placeholder="note (optional)" className="w-48 rounded border border-zinc-700 bg-zinc-900 p-1 text-xs" />
          </div>
        </Card>
      ))}
    </div>
  );
}
