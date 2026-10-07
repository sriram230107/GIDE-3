"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, post } from "@/lib/api";
import { Btn, Card, ErrorBox, NeedCourse } from "@/components/Shell";
import { ConceptStat } from "@/lib/types";

interface Overview { concepts: ConceptStat[]; topics: { id: string; name: string; mastery: number; concepts: number; practised: number }[]; overall: number; overall_practised_only: number | null; concepts_practised: number; concepts_total: number }

function Dashboard({ courseId }: { courseId: string }) {
  const [ov, setOv] = useState<Overview | null>(null);
  const [plan, setPlan] = useState<any>(null);
  const [minutes, setMinutes] = useState(30);
  const [ks, setKs] = useState<any>(null);
  const [stats, setStats] = useState<any>(null);
  const [models, setModels] = useState<any>(null);
  const [levels, setLevels] = useState<Record<string, string>>({});
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [o, k, s] = await Promise.all([api(`/api/learner/${courseId}/overview`), api(`/api/courses/${courseId}/knowledge-status`), api(`/api/assessments/stats/${courseId}`)]);
      setOv(o); setKs(k); setStats(s);
      try { setModels(await api(`/api/system/models`)); } catch { /* models panel optional */ }
    } catch (e: any) { setErr(e.message); }
  }, [courseId]);
  useEffect(() => { load(); }, [load]);
  const recommend = async () => { try { setPlan(await api(`/api/learner/${courseId}/recommend?minutes=${minutes}`)); } catch (e: any) { setErr(e.message); } };

  const weakest = ov ? [...ov.concepts].filter((c) => c.practised).sort((a, b) => a.eff - b.eff).slice(0, 5) : [];
  const needIntake = ov && ov.concepts_total > 0 && ov.concepts_practised === 0;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Dashboard</h1>
      <ErrorBox msg={err} />
      {ks && !ks.ready && <Card className="text-sm text-zinc-300">Your knowledge base is not built yet. <Link href="/sources" className="text-emerald-400 underline">Upload sources and build it</Link>, then topics, concepts, citations and quizzes become available.</Card>}
      {ov && ks?.ready && (
        <div className="grid gap-4 md:grid-cols-3">
          <Card><div className="text-xs uppercase text-zinc-500">Mastery of practised concepts</div><div className="mt-2 text-4xl font-semibold">{ov.overall_practised_only != null ? Math.round(ov.overall_practised_only * 100) + "%" : "–"}</div><div className="mt-1 text-xs text-zinc-500">{ov.concepts_practised} of {ov.concepts_total} concepts practised</div></Card>
          <Card><div className="text-xs uppercase text-zinc-500">Knowledge base</div><div className="mt-2 text-sm text-zinc-300">{ks.topics} topics · {ks.concepts} concepts · {ks.chunks} source chunks ({ks.chunks_tagged} tagged)</div></Card>
          <Card><div className="text-xs uppercase text-zinc-500">Question quality</div><div className="mt-2 text-sm text-zinc-300">{stats?.questions_in_bank ?? 0} verified questions · verification pass rate {stats?.verification_pass_rate != null ? Math.round(stats.verification_pass_rate * 100) + "%" : "–"} ({stats?.generation_attempts ?? 0} attempts)</div></Card>
        </div>
      )}
      {models?.models && (
        <Card className="text-sm"><div className="text-xs uppercase text-zinc-500">AI providers</div><div className="mt-2 flex flex-wrap gap-4 text-zinc-300">{["text", "embed", "vision"].map((cap) => { const m = (models.models as any)[cap]; return m ? <span key={cap}>{cap}: {m.provider}/{m.model} {m.reachable ? (m.installed ? "●" : "◐ not installed") : "○ unreachable"}</span> : null; })}</div></Card>
      )}
      {needIntake && (
        <Card className="space-y-3 text-sm">
          <div className="font-medium">New here? Tell Gide where you are (then take a diagnostic quiz).</div>
          {ov!.topics.map((t) => <div key={t.id} className="flex items-center justify-between gap-3"><span>{t.name}</span><select value={levels[t.id] ?? ""} onChange={(e) => setLevels({ ...levels, [t.id]: e.target.value })} className="rounded border border-zinc-700 bg-zinc-900 p-1"><option value="">skip</option><option value="new">New to it</option><option value="some">Some familiarity</option><option value="comfortable">Comfortable</option></select></div>)}
          <div className="flex gap-2"><Btn onClick={async () => { await post("/api/learner/intake", { course_id: courseId, levels: Object.fromEntries(Object.entries(levels).filter(([, v]) => v)) }); load(); }}>Save</Btn><Link href="/assessments" className="rounded-lg border border-zinc-700 px-4 py-2 text-sm hover:bg-zinc-800">Go to diagnostic quiz</Link></div>
        </Card>
      )}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="space-y-3">
          <div className="flex items-center justify-between"><h2 className="font-medium">What should I study now?</h2><div className="flex items-center gap-2 text-sm"><input type="number" min={5} max={240} value={minutes} onChange={(e) => setMinutes(+e.target.value)} className="w-16 rounded border border-zinc-700 bg-zinc-900 p-1" /> min<Btn onClick={recommend}>Plan</Btn></div></div>
          {plan && plan.plan.length === 0 && <p className="text-sm text-zinc-400">Nothing urgent. Try a diagnostic or a quiz to give the planner evidence.</p>}
          {plan?.plan.map((p: any, i: number) => (
            <div key={i} className="rounded-xl border border-zinc-800 p-3 text-sm">
              <div className="flex justify-between"><span className="font-medium">{p.activity}: {p.concept}</span><span className="text-zinc-400">{p.minutes} min</span></div>
              <ul className="mt-1 list-disc pl-5 text-xs text-zinc-400">{p.reasons.map((r: string, j: number) => <li key={j}>{r}</li>)}</ul>
            </div>
          ))}
        </Card>
        <Card className="space-y-3">
          <h2 className="font-medium">Topics</h2>
          {ov?.topics.map((t) => <div key={t.id} className="text-sm"><div className="flex justify-between"><span>{t.name}</span><span className="text-zinc-400">{t.practised ? Math.round(t.mastery * 100) + "%" : "not practised"}</span></div><div className="mt-1 h-1.5 rounded bg-zinc-800"><div className="h-1.5 rounded bg-emerald-500" style={{ width: `${t.practised ? t.mastery * 100 : 0}%` }} /></div></div>)}
          {weakest.length > 0 && <div className="pt-2 text-sm"><div className="text-zinc-400">Weakest concepts</div>{weakest.map((c) => <div key={c.id} className="text-amber-300">• {c.name} ({Math.round(c.eff * 100)}%)</div>)}</div>}
        </Card>
      </div>
    </div>
  );
}

export default function Page() { return <NeedCourse>{(id) => <Dashboard courseId={id} />}</NeedCourse>; }
