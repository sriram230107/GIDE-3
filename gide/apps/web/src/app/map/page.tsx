"use client";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { Card, ErrorBox, NeedCourse } from "@/components/Shell";
import { SourceViewer, ViewTarget } from "@/components/SourceViewer";
import { Citation, citeLabel, ConceptStat } from "@/lib/types";

interface GNode { id: string; name: string; topic_id: string | null; depth: number; chunks: number }
interface Graph { topics: { id: string; name: string }[]; concepts: GNode[]; edges: { concept_id: string; prereq_id: string }[] }

const colour = (c?: ConceptStat) => !c || !c.practised ? "#52525b" : c.eff >= 0.7 ? "#10b981" : c.eff >= 0.45 ? "#f59e0b" : "#ef4444";

function MapView({ courseId }: { courseId: string }) {
  const [g, setG] = useState<Graph | null>(null);
  const [stats, setStats] = useState<Record<string, ConceptStat>>({});
  const [plan, setPlan] = useState<string[]>([]);
  const [sel, setSel] = useState<string | null>(null);
  const [srcs, setSrcs] = useState<Citation[]>([]);
  const [mode, setMode] = useState<"all" | "weak" | "next">("all");
  const [target, setTarget] = useState<ViewTarget | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const [gr, ov, rec] = await Promise.all([api<Graph>(`/api/courses/${courseId}/graph`), api(`/api/learner/${courseId}/overview`), api(`/api/learner/${courseId}/recommend?minutes=30`)]);
        setG(gr); setStats(Object.fromEntries(ov.concepts.map((c: ConceptStat) => [c.id, c]))); setPlan(rec.plan.map((p: any) => p.concept_id));
      } catch (e: any) { setErr(e.message); }
    })();
  }, [courseId]);
  useEffect(() => { if (sel) api<Citation[]>(`/api/courses/concepts/${sel}/sources`).then(setSrcs).catch(() => setSrcs([])); }, [sel]);

  const layout = useMemo(() => {
    if (!g) return null;
    const cols = new Map<number, GNode[]>();
    g.concepts.forEach((c) => cols.set(c.depth, [...(cols.get(c.depth) ?? []), c]));
    const pos: Record<string, { x: number; y: number }> = {};
    let maxRows = 1;
    [...cols.entries()].forEach(([d, list]) => { list.sort((a, b) => (a.topic_id ?? "").localeCompare(b.topic_id ?? "")); maxRows = Math.max(maxRows, list.length); list.forEach((c, i) => { pos[c.id] = { x: 90 + d * 230, y: 40 + i * 62 }; }); });
    return { pos, w: 90 + (Math.max(...cols.keys(), 0) + 1) * 230, h: 40 + maxRows * 62 };
  }, [g]);

  if (err) return <ErrorBox msg={err} />;
  if (!g || !layout) return <p className="text-sm text-zinc-500">Loading…</p>;
  if (g.concepts.length === 0) return <p className="text-sm text-zinc-400">No concepts yet. Upload sources and press “Build knowledge base” on the Sources page.</p>;

  const dim = (id: string) => (mode === "weak" && !(stats[id]?.practised && stats[id].eff < 0.5)) || (mode === "next" && !plan.includes(id));
  const s = sel ? stats[sel] : undefined; const node = g.concepts.find((c) => c.id === sel);
  const nm = (id: string) => g.concepts.find((c) => c.id === id)?.name ?? "";
  const hi = new Set(sel ? [sel, ...(s?.prereq_ids ?? []), ...(s?.dependent_ids ?? [])] : []);

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
      <div className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h1 className="text-2xl font-semibold">Knowledge map</h1>
          <div className="flex gap-1 text-xs">{([["all", "All"], ["weak", "My weak areas"], ["next", "Learn next"]] as const).map(([k, l]) => <button key={k} onClick={() => setMode(k)} className={`rounded-md px-2.5 py-1 ${mode === k ? "bg-zinc-700" : "bg-zinc-900 text-zinc-400"}`}>{l}</button>)}</div>
        </div>
        <div className="flex flex-wrap gap-3 text-xs text-zinc-400"><span><i className="mr-1 inline-block h-2 w-2 rounded-full bg-emerald-500" />strong</span><span><i className="mr-1 inline-block h-2 w-2 rounded-full bg-amber-500" />learning</span><span><i className="mr-1 inline-block h-2 w-2 rounded-full bg-red-500" />weak</span><span><i className="mr-1 inline-block h-2 w-2 rounded-full bg-zinc-600" />not practised yet</span><span>→ arrows point from prerequisite to concept</span></div>
        <div className="overflow-auto rounded-2xl border border-zinc-800 bg-zinc-900/30">
          <svg width={layout.w} height={layout.h} className="block">
            <defs><marker id="ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0L10 5L0 10z" fill="#71717a" /></marker></defs>
            {g.edges.map((e, i) => { const a = layout.pos[e.prereq_id], b = layout.pos[e.concept_id]; if (!a || !b) return null; const on = sel && hi.has(e.prereq_id) && hi.has(e.concept_id);
              return <line key={i} x1={a.x + 75} y1={a.y} x2={b.x - 75} y2={b.y} stroke={on ? "#a1a1aa" : "#3f3f46"} strokeWidth={on ? 1.8 : 1} markerEnd="url(#ar)" opacity={sel && !on ? 0.25 : 1} />; })}
            {g.concepts.map((c) => { const p = layout.pos[c.id]; const st = stats[c.id]; const faded = dim(c.id) || (sel && !hi.has(c.id));
              return (<g key={c.id} transform={`translate(${p.x - 75},${p.y - 20})`} onClick={() => setSel(c.id)} className="cursor-pointer" opacity={faded ? 0.25 : 1}>
                <rect width={150} height={40} rx={10} fill="#18181b" stroke={colour(st)} strokeWidth={sel === c.id ? 3 : 1.5} strokeDasharray={st?.practised ? undefined : "4 3"} />
                <text x={75} y={17} textAnchor="middle" fontSize={11} fill="#e4e4e7">{c.name.length > 22 ? c.name.slice(0, 21) + "…" : c.name}</text>
                <text x={75} y={31} textAnchor="middle" fontSize={9} fill="#a1a1aa">{st?.practised ? `mastery ${Math.round(st.eff * 100)}%` : "not practised"}</text>
              </g>); })}
          </svg>
        </div>
      </div>
      <div className="space-y-4">
        {node ? (
          <Card className="space-y-3 text-sm">
            <h2 className="text-lg font-semibold">{node.name}</h2>
            {s && <div className="text-zinc-400">{s.practised ? <>Mastery {Math.round(s.eff * 100)}% · forgetting risk {Math.round(s.risk * 100)}% · {s.correct}/{s.attempts} correct</> : <>Not practised yet{s.prior_source === "intake" ? " (self-rated prior)" : ""}</>}</div>}
            {s && s.prereq_ids.length > 0 && <div><span className="text-zinc-500">Needs first:</span> {s.prereq_ids.map(nm).join(", ")}</div>}
            {s && s.dependent_ids.length > 0 && <div><span className="text-zinc-500">Unlocks:</span> {s.dependent_ids.map(nm).join(", ")}</div>}
            {plan.includes(node.id) && <div className="rounded-lg bg-emerald-500/10 p-2 text-emerald-300">In your recommended study plan right now.</div>}
            <Link href={`/tutor?q=${encodeURIComponent("Explain " + node.name)}`} className="inline-block rounded-lg border border-zinc-700 px-3 py-1.5 hover:bg-zinc-800">Ask the tutor</Link>
            <div className="space-y-1">{srcs.map((c) => <button key={c.chunk_id ?? c.unit_id} onClick={() => setTarget({ source_id: c.source_id, source_type: c.source_type, title: c.source_title, media_url: c.media_url, page: c.page, slide: c.slide, time_start: c.time_start, image_path: c.image_path, note: c.snippet })} className="block w-full rounded-lg border border-zinc-800 p-2 text-left text-xs hover:border-zinc-600">{citeLabel(c)}</button>)}</div>
          </Card>
        ) : <Card className="text-sm text-zinc-400">Click a concept to see its mastery, prerequisites and the sources that teach it.</Card>}
        {target && <SourceViewer target={target} onClose={() => setTarget(null)} />}
      </div>
    </div>
  );
}

export default function Page() { return <NeedCourse>{(id) => <MapView courseId={id} />}</NeedCourse>; }
