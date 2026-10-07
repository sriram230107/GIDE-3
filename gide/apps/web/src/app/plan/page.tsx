"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import { Card, ErrorBox, NeedCourse } from "@/components/Shell";

interface Block { concept: string; activity: string; minutes: number; reasons: string[] }
interface Day { date: string; minutes: number; blocks: Block[] }

export default function PlanPage() {
  return <NeedCourse>{(courseId) => <Body courseId={courseId} />}</NeedCourse>;
}

function Body({ courseId }: { courseId: string }) {
  const [exam, setExam] = useState("");
  const [mins, setMins] = useState(30);
  const [plan, setPlan] = useState<{ days: Day[]; total_minutes: number } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const go = async () => {
    setErr(null); setLoading(true);
    try {
      setPlan(await api(`/api/learner/${courseId}/exam-plan?exam_date=${exam}&minutes_per_day=${mins}`));
    } catch (e: unknown) { setErr(e instanceof Error ? e.message : String(e)); } finally { setLoading(false); }
  };
  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <h1 className="text-xl font-semibold">Study plan</h1>
      <Card>
        <div className="flex flex-wrap gap-2">
          <input type="date" value={exam} onChange={(e) => setExam(e.target.value)} className="rounded-lg border border-zinc-800 bg-zinc-900 p-2 text-sm" />
          <input type="number" value={mins} min={5} max={240} onChange={(e) => setMins(Number(e.target.value))} className="w-24 rounded-lg border border-zinc-800 bg-zinc-900 p-2 text-sm" />
          <button onClick={go} disabled={!exam || loading} className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium disabled:opacity-50">{loading ? "Planning…" : "Build plan"}</button>
        </div>
      </Card>
      {err && <ErrorBox msg={err} />}
      {!plan && !err && <p className="text-sm text-zinc-500">Pick an exam date and minutes per day.</p>}
      {plan && <p className="text-sm text-zinc-400">{plan.days.length} days · {plan.total_minutes} min total</p>}
      {(plan?.days ?? []).map((d) => (
        <Card key={d.date}>
          <div className="mb-2 text-sm font-medium">{d.date} · {d.minutes} min</div>
          {d.blocks.length === 0 && <p className="text-sm text-zinc-500">Nothing scheduled — concepts look solid.</p>}
          {d.blocks.map((b, i) => (
            <div key={i} className="border-t border-zinc-800 py-2 text-sm">
              <span className="font-medium">{b.concept}</span> — {b.activity} ({b.minutes} min)
              <div className="text-xs text-zinc-500">{b.reasons.join(" · ")}</div>
            </div>
          ))}
        </Card>
      ))}
    </div>
  );
}
